"""Pure canonical contracts for Raw-V8 capacity-measurement Step 2.

This module freezes the Raw-V8 operation union, returned-result evidence,
complete target-field registry, typed observations, and compact-counter schema.
It is deliberately independent from the transport runtime, Raw-V7 lifecycle,
projection, actor, TLS, socket, SQLite, collection, signing, and enforcement
paths.  The records below are evidence contracts only; none authorizes a
transport effect or a trading decision.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, TypeVar

from .canonical import (
    CANONICALIZATION_VERSION,
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    canonical_hash,
    canonical_json_bytes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)

PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
)
RAW_V8_UNICODE_DATA_VERSION_V49F = "15.0.0"
# This is the exact edge-whitespace set used by the governed CPython 3.12/UCD
# 15 runtime.  It intentionally includes U+001C..U+001F in addition to
# Unicode 15 White_Space and avoids ambient ``str.strip()`` semantics.
RAW_V8_EDGE_TRIM_CODE_POINTS_V49F = frozenset(
    {
        0x0009,
        0x000A,
        0x000B,
        0x000C,
        0x000D,
        0x001C,
        0x001D,
        0x001E,
        0x001F,
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        0x2000,
        0x2001,
        0x2002,
        0x2003,
        0x2004,
        0x2005,
        0x2006,
        0x2007,
        0x2008,
        0x2009,
        0x200A,
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    }
)

RAW_V8_OPERATION_SPEC_DOMAIN_V49F = "RiskYieldMMA2MOperationSpecV4_9F_RawV8"
RAW_V8_OPERATION_DECLARATION_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationDeclarationV4_9F_RawV8"
)
RAW_V8_OPERATION_RESULT_EVIDENCE_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8"
)
RAW_V8_DISPATCH_WINDOW_EVIDENCE_DOMAIN_V49F = (
    "RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8"
)
RAW_V8_DUE_DECISION_CLOCK_EVIDENCE_DOMAIN_V49F = (
    "RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8"
)
RAW_V8_TARGET_FIELD_REGISTRY_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8"
)
RAW_V8_SOURCE_ERROR_DETAIL_DOMAIN_V49F = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
RAW_V8_TARGET_FIELD_OBSERVATION_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8"
)
RAW_V8_TARGET_OBSERVATION_CONTEXT_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetObservationContextV4_9F_RawV8"
)
RAW_V8_TARGET_OBSERVATION_DOMAIN_V49F = "RiskYieldMMA2MTargetObservationV4_9F_RawV8"
RAW_V8_TARGET_OBSERVATION_ROOT_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetObservationRootV4_9F_RawV8"
)
RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_DOMAIN_V49F = (
    "RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8"
)
RAW_V8_MARKER_CONTRACT_DOMAIN_V49F = "RiskYieldMMA2MMarkerContractV1V4_9F_RawV8"
RAW_V8_CHECKPOINT_SELECTOR_ENTRY_DOMAIN_V49F = (
    "RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8"
)
RAW_V8_CHECKPOINT_SELECTOR_DOMAIN_V49F = "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8"
RAW_V8_TARGET_OBSERVATION_CONTEXT_V2_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8"
)
RAW_V8_TARGET_OBSERVATION_V2_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetObservationV2V4_9F_RawV8"
)
RAW_V8_TARGET_OBSERVATION_ROOT_V2_DOMAIN_V49F = (
    "RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8"
)
RAW_V8_OPERATION_COUNTER_SCHEMA_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8"
)

RAW_V8_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F = 256
RAW_V8_MAXIMUM_STAGE_UTF8_BYTES_V49F = 128
RAW_V8_MAXIMUM_WORKLOAD_FAMILY_UTF8_BYTES_V49F = 128
RAW_V8_MAXIMUM_VALUE_UNION_BYTES_V49F = 3 * 1024
RAW_V8_MAXIMUM_SOURCE_ERROR_DETAIL_BYTES_V49F = 2 * 1024
RAW_V8_MAXIMUM_FIELD_OBSERVATION_BYTES_V49F = 4 * 1024
RAW_V8_MAXIMUM_CLOCK_SPAN_BYTES_V49F = 512
RAW_V8_MAXIMUM_OBSERVATION_CONTEXT_BYTES_V49F = 2 * 1024
RAW_V8_MAXIMUM_TARGET_OBSERVATION_BYTES_V49F = 256 * 1024
RAW_V8_MAXIMUM_TARGET_FIELD_REGISTRY_BYTES_V49F = 2 * 1024 * 1024
RAW_V8_MAXIMUM_TARGET_OBSERVATION_ROOT_BYTES_V49F = 8 * 1024
RAW_V8_MAXIMUM_COUNTER_SCHEMA_BYTES_V49F = 8 * 1024
RAW_V8_MAXIMUM_COUNTER_SNAPSHOT_BYTES_V49F = 2 * 1024
RAW_V8_MAXIMUM_OPERATION_SPEC_BYTES_V49F = 2 * 1024 * 1024
RAW_V8_MAXIMUM_OPERATION_DECLARATION_BYTES_V49F = 3 * 1024 * 1024
RAW_V8_MAXIMUM_OPERATION_RESULT_BYTES_V49F = 512 * 1024
RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F = 128
RAW_V8_MAXIMUM_INPUT_OCTETS_V49F = 65_536
RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F = 32_768
RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F = 32_768
RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F = 32_768
RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F = 65_536
RAW_V8_MAXIMUM_CONTROL_PAYLOAD_OCTETS_V49F = 125
RAW_V8_MAXIMUM_INGRESS_CHUNK_BASE64_BYTES_V49F = 87_384
RAW_V8_MAXIMUM_CONTROL_PAYLOAD_BASE64_BYTES_V49F = 168
RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F = 256
RAW_V8_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F = 4_194_304
RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F = 67
RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F = 64
RAW_V8_MAXIMUM_OBSERVATION_METHOD_ROLE_PAIRS_V49F = 8
RAW_V8_MINIMUM_MARKER_RING_CAPACITY_V49F = 8
RAW_V8_MAXIMUM_MARKER_RING_CAPACITY_V49F = 4_096
RAW_V8_TARGET_FIELD_COUNT_V49F = 185
RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F = 66
RAW_V8_MAXIMUM_JSON_NESTING_DEPTH_V49F = 64
RAW_V8_MAXIMUM_JSON_OBJECT_MEMBERS_V49F = 512
RAW_V8_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F = 524_288
RAW_V8_MAXIMUM_TYPED_NESTING_DEPTH_V49F = 16
RAW_V8_MAXIMUM_TYPED_OBJECT_MEMBERS_V49F = 32

RAW_V8_JSON_DEPTH_LIMIT_EXCEEDED_V49F = "V8_JSON_DEPTH_LIMIT_EXCEEDED"
RAW_V8_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F = "V8_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED"
RAW_V8_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F = "V8_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED"
RAW_V8_JSON_MALFORMED_STRUCTURE_V49F = "V8_JSON_MALFORMED_STRUCTURE"

_SHA256_ASCII_RE = re.compile(r"^[0-9a-f]{64}$", flags=re.ASCII)
_UINT128_ASCII_RE = re.compile(r"^(?:0|[1-9][0-9]*)$", flags=re.ASCII)
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$", flags=re.ASCII)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,36}$", flags=re.ASCII)
_ERRNO_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$", flags=re.ASCII)
_SAFE_EXCEPTION_CLASS_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$",
    flags=re.ASCII,
)
_FIELD_ID_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z0-9_]+$", flags=re.ASCII)


class CapacityMeasurementOperationKindV49FV8(str, Enum):
    ACK_DEADLINE_EXPIRY = "ACK_DEADLINE_EXPIRY"
    INGRESS = "INGRESS"
    LOCAL_SHUTDOWN = "LOCAL_SHUTDOWN"
    SUBSCRIPTION_DISPATCH = "SUBSCRIPTION_DISPATCH"


class CapacityMeasurementOperationSpecTypeV49FV8(str, Enum):
    ACK_DEADLINE_EXPIRY_SPEC_V1 = "ACK_DEADLINE_EXPIRY_SPEC_V1"
    INGRESS_OPERATION_SPEC_V2 = "INGRESS_OPERATION_SPEC_V2"
    LOCAL_SHUTDOWN_SPEC_V2 = "LOCAL_SHUTDOWN_SPEC_V2"
    SUBSCRIPTION_DISPATCH_SPEC_V2 = "SUBSCRIPTION_DISPATCH_SPEC_V2"


class CapacityMeasurementOperationResultTypeV49FV8(str, Enum):
    ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1 = "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1"
    INGRESS_RESULT_EVIDENCE_V2 = "INGRESS_RESULT_EVIDENCE_V2"
    LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2 = "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"
    SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2 = (
        "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2"
    )


class CapacityMeasurementLogicalOutputOpcodeV49FV8(str, Enum):
    CLOSE = "CLOSE"
    PONG = "PONG"


class CapacityMeasurementDispatchDispositionV49FV8(str, Enum):
    COMPLETE_LOCAL_SUBMISSION = "COMPLETE_LOCAL_SUBMISSION"
    UNKNOWN_DELIVERY = "UNKNOWN_DELIVERY"


class CapacityMeasurementAckDueScenarioV49FV8(str, Enum):
    DUE = "DUE"
    NOT_DUE = "NOT_DUE"


class CapacityMeasurementTerminalOutcomeV49FV8(str, Enum):
    CLEAN_ALL_LAYERS = "CLEAN_ALL_LAYERS"
    FATAL = "FATAL"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    TIMEOUT = "TIMEOUT"
    TRUNCATED = "TRUNCATED"
    UNKNOWN_SEND = "UNKNOWN_SEND"


class CapacityMeasurementInstrumentationModeV49FV8(str, Enum):
    OFF = "OFF"
    ON = "ON"


class CapacityMeasurementObservationRoleV49FV8(str, Enum):
    AFTER_OPERATION = "AFTER_OPERATION"
    BEFORE_OPERATION = "BEFORE_OPERATION"
    OPERATION_AGGREGATE = "OPERATION_AGGREGATE"
    STABLE_CHECKPOINT = "STABLE_CHECKPOINT"
    STARTUP_RECOVERY = "STARTUP_RECOVERY"


class CapacityMeasurementMarkerKindV49FV8(str, Enum):
    ACK_DEADLINE_NOT_DUE = "ACK_DEADLINE_NOT_DUE"
    ACK_DEADLINE_TERMINAL_CONVERGED = "ACK_DEADLINE_TERMINAL_CONVERGED"
    ADMISSION_CANDIDATE_COMMITTED = "ADMISSION_CANDIDATE_COMMITTED"
    ADMISSION_GRANTED = "ADMISSION_GRANTED"
    ADMISSION_NOT_GRANTED = "ADMISSION_NOT_GRANTED"
    ADMISSION_TICKET_ACCEPTED = "ADMISSION_TICKET_ACCEPTED"
    DISPATCH_RETURN_READY = "DISPATCH_RETURN_READY"
    INGRESS_RETURN_READY = "INGRESS_RETURN_READY"
    KERNEL_SEND_RESULT_CONVERGED = "KERNEL_SEND_RESULT_CONVERGED"
    LOCAL_CLOSE_DISPATCH_CONVERGED = "LOCAL_CLOSE_DISPATCH_CONVERGED"
    OUTBOUND_ARTIFACTS_PREPARED = "OUTBOUND_ARTIFACTS_PREPARED"
    PARSER_UNIT_CONVERGED = "PARSER_UNIT_CONVERGED"
    RAW_PREFIX_COMMITTED = "RAW_PREFIX_COMMITTED"
    SHUTDOWN_COMMAND_STARTED = "SHUTDOWN_COMMAND_STARTED"
    SHUTDOWN_TERMINAL_CONVERGED = "SHUTDOWN_TERMINAL_CONVERGED"
    TARGET_EFFECT_ENTRY = "TARGET_EFFECT_ENTRY"
    TARGET_ESCAPE_OBSERVED = "TARGET_ESCAPE_OBSERVED"
    TCP_HALF_CLOSE_CONVERGED = "TCP_HALF_CLOSE_CONVERGED"
    TLS_CONTROL_CONVERGED = "TLS_CONTROL_CONVERGED"


class CapacityMeasurementTargetAvailabilityV49FV8(str, Enum):
    AVAILABLE = "AVAILABLE"
    CENSORED = "CENSORED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CapacityMeasurementTargetValueKindV49FV8(str, Enum):
    BOOL = "BOOL"
    DURATION_BOUND = "DURATION_BOUND"
    FIXED_UINT_MAP = "FIXED_UINT_MAP"
    OPTIONAL_TEXT = "OPTIONAL_TEXT"
    OPTIONAL_UINT = "OPTIONAL_UINT"
    TEXT = "TEXT"
    TEXT_LIST = "TEXT_LIST"
    UINT = "UINT"
    UINT_LIST = "UINT_LIST"


class CapacityMeasurementTargetObservationMethodV49FV8(str, Enum):
    A1_OUTCOME_CAPABILITY = "A1_OUTCOME_CAPABILITY"
    A1_OWNER_SNAPSHOT = "A1_OWNER_SNAPSHOT"
    ACTOR_OWNER_SNAPSHOT = "ACTOR_OWNER_SNAPSHOT"
    CGROUP_V2_MEMORY_CURRENT = "CGROUP_V2_MEMORY_CURRENT"
    DURABLE_GOVERNED_CLOCK_DERIVATION = "DURABLE_GOVERNED_CLOCK_DERIVATION"
    DURABLE_PREFIX_REPLAY = "DURABLE_PREFIX_REPLAY"
    EXACT_REGISTERED_FIELD_DERIVATION = "EXACT_REGISTERED_FIELD_DERIVATION"
    FILESYSTEM_STAT = "FILESYSTEM_STAT"
    GC_CALLBACK_ACCUMULATOR = "GC_CALLBACK_ACCUMULATOR"
    GC_GET_COUNT = "GC_GET_COUNT"
    INGRESS_OWNER_SCALAR = "INGRESS_OWNER_SCALAR"
    LINUX_GETSOCKOPT = "LINUX_GETSOCKOPT"
    LINUX_IOCTL = "LINUX_IOCTL"
    LINUX_POLL = "LINUX_POLL"
    LINUX_SOCKET_IDENTITY = "LINUX_SOCKET_IDENTITY"
    LOOP_MANIFEST_CONFIGURATION = "LOOP_MANIFEST_CONFIGURATION"
    LOOP_PROBE_ACCUMULATOR = "LOOP_PROBE_ACCUMULATOR"
    LOOP_RUNTIME_CONFIGURATION = "LOOP_RUNTIME_CONFIGURATION"
    MANIFEST_IDENTITY_LINK = "MANIFEST_IDENTITY_LINK"
    MARKER_ACCUMULATOR = "MARKER_ACCUMULATOR"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    OPERATION_COUNTER_ACCUMULATOR = "OPERATION_COUNTER_ACCUMULATOR"
    OWNER_THREAD_CPU_CLOCK = "OWNER_THREAD_CPU_CLOCK"
    PARSER_OWNER_SCALAR = "PARSER_OWNER_SCALAR"
    PROCESS_CPU_CLOCK = "PROCESS_CPU_CLOCK"
    PROCFS_SMAPS_ROLLUP = "PROCFS_SMAPS_ROLLUP"
    PROCFS_STATM = "PROCFS_STATM"
    PROCFS_STATUS = "PROCFS_STATUS"
    SQLITE_CONNECTION_CONFIGURATION = "SQLITE_CONNECTION_CONFIGURATION"
    SQLITE_QUIESCENT_PRAGMA = "SQLITE_QUIESCENT_PRAGMA"
    SQLITE_TRANSACTION_ACCUMULATOR = "SQLITE_TRANSACTION_ACCUMULATOR"
    TLS_OWNER_SCALAR = "TLS_OWNER_SCALAR"


class CapacityMeasurementObservationAttemptV49FV8(str, Enum):
    ATTEMPTED = "ATTEMPTED"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


class CapacityMeasurementAdapterSpanStatusV49FV8(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CapacityMeasurementClockSpanStatusV49FV8(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CapacityMeasurementClockDomainV49FV8(str, Enum):
    BOOTTIME = "BOOTTIME"
    EVENT_LOOP = "EVENT_LOOP"
    OBSERVER_MONOTONIC = "OBSERVER_MONOTONIC"


class CapacityMeasurementCheckpointBindingStatusV49FV8(str, Enum):
    EXACT_MARKER = "EXACT_MARKER"
    UNAVAILABLE_MARKER_OBSERVER_FAILURE = "UNAVAILABLE_MARKER_OBSERVER_FAILURE"
    UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED = "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"


class CapacityMeasurementCensoringV49FV8(str, Enum):
    INTERVAL = "INTERVAL"
    LEFT = "LEFT"
    NONE = "NONE"
    RIGHT = "RIGHT"


class CapacityMeasurementDurationRelationV49FV8(str, Enum):
    EXACT = "EXACT"
    INTERVAL = "INTERVAL"
    LOWER_BOUND = "LOWER_BOUND"
    UPPER_BOUND = "UPPER_BOUND"


class CapacityMeasurementLaterThresholdActionV49FV8(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"


class CapacityMeasurementStatusReasonV49FV8(str, Enum):
    ARTIFACT_BOUND_EXCEEDED = "ARTIFACT_BOUND_EXCEEDED"
    CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED = (
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"
    )
    CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR = (
        "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
    )
    CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE = (
        "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
    )
    CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED = (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    )
    INSTRUMENTATION_DISABLED = "INSTRUMENTATION_DISABLED"
    MARKER_RING_OVERWROTE_PREFIX = "MARKER_RING_OVERWROTE_PREFIX"
    NOT_APPLICABLE_TO_OPERATION = "NOT_APPLICABLE_TO_OPERATION"
    NOT_APPLICABLE_TO_REACHED_STATE = "NOT_APPLICABLE_TO_REACHED_STATE"
    NO_FROZEN_PRESSURE_POLICY = "NO_FROZEN_PRESSURE_POLICY"
    NO_STABLE_SLOW_CALLBACK_SOURCE = "NO_STABLE_SLOW_CALLBACK_SOURCE"
    OBSERVATION_WOULD_MUTATE_TARGET = "OBSERVATION_WOULD_MUTATE_TARGET"
    OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION = (
        "OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION"
    )
    OBSERVATION_WOULD_REENTER_TARGET_LOCK = "OBSERVATION_WOULD_REENTER_TARGET_LOCK"
    OBSERVER_INTERNAL_ERROR = "OBSERVER_INTERNAL_ERROR"
    OS_OBSERVATION_ERROR = "OS_OBSERVATION_ERROR"
    PERIODIC_PROBE_DID_NOT_FIRE = "PERIODIC_PROBE_DID_NOT_FIRE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PROBE_RING_OVERWROTE_PREFIX = "PROBE_RING_OVERWROTE_PREFIX"
    PROCESS_LOSS_VOLATILE_MARKER_STATE = "PROCESS_LOSS_VOLATILE_MARKER_STATE"
    SOURCE_CLOCK_UNAVAILABLE = "SOURCE_CLOCK_UNAVAILABLE"
    SOURCE_COUNTER_NOT_INSTRUMENTED = "SOURCE_COUNTER_NOT_INSTRUMENTED"
    SOURCE_DURABLE_RECORD_ABSENT = "SOURCE_DURABLE_RECORD_ABSENT"
    TARGET_BOUNDARY_NOT_REACHED = "TARGET_BOUNDARY_NOT_REACHED"
    UNSUPPORTED_BY_KERNEL = "UNSUPPORTED_BY_KERNEL"
    UNSUPPORTED_BY_PYTHON_RUNTIME = "UNSUPPORTED_BY_PYTHON_RUNTIME"


class CapacityMeasurementSourceFailurePhaseV49FV8(str, Enum):
    FIRST_CLOCK_READ = "FIRST_CLOCK_READ"
    NONE = "NONE"
    SECOND_CLOCK_READ = "SECOND_CLOCK_READ"
    SOURCE_ADAPTER = "SOURCE_ADAPTER"
    VALUE_VALIDATION = "VALUE_VALIDATION"


class CapacityMeasurementA1AdmissionOutcomeV49FV8(str, Enum):
    CANCELLED_BEFORE_ENTRY = "CANCELLED_BEFORE_ENTRY"
    CLOSED_BEFORE_ENTRY = "CLOSED_BEFORE_ENTRY"
    FAILED_BEFORE_ENTRY = "FAILED_BEFORE_ENTRY"
    GRANTED = "GRANTED"
    INTERRUPTED_BEFORE_ENTRY = "INTERRUPTED_BEFORE_ENTRY"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    UNRESOLVED_PROCESS_LOSS = "UNRESOLVED_PROCESS_LOSS"


class CapacityMeasurementA1RejectionClassV49FV8(str, Enum):
    CANCELLED_BEFORE_ENTRY = "CANCELLED_BEFORE_ENTRY"
    CAPACITY_REJECTED = "CAPACITY_REJECTED"
    CLOSED_BEFORE_ENTRY = "CLOSED_BEFORE_ENTRY"
    DUPLICATE_KIND_REJECTED = "DUPLICATE_KIND_REJECTED"
    FAILED_BEFORE_ENTRY = "FAILED_BEFORE_ENTRY"
    INTERRUPTED_BEFORE_ENTRY = "INTERRUPTED_BEFORE_ENTRY"
    TERMINAL_BARRIER_REJECTED = "TERMINAL_BARRIER_REJECTED"
    TIMED_OUT = "TIMED_OUT"


class CapacityMeasurementErrorFormV49FV8(str, Enum):
    NONE = "NONE"
    NON_OS = "NON_OS"
    OS = "OS"
    STATUS_ONLY = "STATUS_ONLY"


class CapacityMeasurementSQLitePrimaryResultV49FV8(str, Enum):
    BEGIN_BUSY = "BEGIN.BUSY"
    BEGIN_FULL = "BEGIN.FULL"
    BEGIN_INTERRUPT = "BEGIN.INTERRUPT"
    BEGIN_IOERR = "BEGIN.IOERR"
    BEGIN_LOCKED = "BEGIN.LOCKED"
    BEGIN_NOMEM = "BEGIN.NOMEM"
    BEGIN_OK = "BEGIN.OK"
    BEGIN_OTHER = "BEGIN.OTHER"
    BODY_BUSY = "BODY.BUSY"
    BODY_FULL = "BODY.FULL"
    BODY_INTERRUPT = "BODY.INTERRUPT"
    BODY_IOERR = "BODY.IOERR"
    BODY_LOCKED = "BODY.LOCKED"
    BODY_NOMEM = "BODY.NOMEM"
    BODY_OK = "BODY.OK"
    BODY_OTHER = "BODY.OTHER"
    COMMIT_BUSY = "COMMIT.BUSY"
    COMMIT_FULL = "COMMIT.FULL"
    COMMIT_INTERRUPT = "COMMIT.INTERRUPT"
    COMMIT_IOERR = "COMMIT.IOERR"
    COMMIT_LOCKED = "COMMIT.LOCKED"
    COMMIT_NOMEM = "COMMIT.NOMEM"
    COMMIT_OK = "COMMIT.OK"
    COMMIT_OTHER = "COMMIT.OTHER"
    NONE = "NONE"


_RecordT = TypeVar("_RecordT", bound="_StandaloneRecordV49FV8")


def _exact_enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    if type(value) is not enum_type:
        raise CanonicalizationError(f"{field} must be an exact {enum_type.__name__}")
    return value


def _enum_from_json(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    if type(value) is not str:
        raise CanonicalizationError(f"{field} must be an exact JSON string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise CanonicalizationError(f"{field} is unsupported") from exc


def _exact_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be an exact boolean")
    return value


def _safe_uint(
    value: Any,
    *,
    field: str,
    minimum: int = 0,
    maximum: int = MAX_IJSON_INTEGER,
) -> int:
    if type(value) is not int:
        raise CanonicalizationError(f"{field} must be an exact integer")
    return canonical_safe_int(value, field=field, minimum=minimum, maximum=maximum)


def _optional_safe_uint(
    value: Any,
    *,
    field: str,
    minimum: int = 0,
    maximum: int = MAX_IJSON_INTEGER,
) -> int | None:
    return (
        None
        if value is None
        else _safe_uint(value, field=field, minimum=minimum, maximum=maximum)
    )


def validate_capacity_measurement_unicode_authority_v49f_v8() -> None:
    """Reject Raw-V8 text validation under an unfrozen Unicode database."""

    if unicodedata.unidata_version != RAW_V8_UNICODE_DATA_VERSION_V49F:
        raise CanonicalizationError(
            "Raw V8 Unicode authority differs: expected "
            f"{RAW_V8_UNICODE_DATA_VERSION_V49F}, observed "
            f"{unicodedata.unidata_version}"
        )


def _utf8_identifier(
    value: Any,
    *,
    field: str,
    maximum: int,
    maximum_utf8_octets: int | None = None,
) -> str:
    if type(value) is not str:
        raise CanonicalizationError(f"{field} must be an exact string")
    validate_capacity_measurement_unicode_authority_v49f_v8()
    if (
        not value
        or ord(value[0]) in RAW_V8_EDGE_TRIM_CODE_POINTS_V49F
        or ord(value[-1]) in RAW_V8_EDGE_TRIM_CODE_POINTS_V49F
    ):
        raise CanonicalizationError(f"{field} must be non-empty and trimmed")
    if len(value) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} code points")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CanonicalizationError(f"{field} contains a forbidden C0/DEL control")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CanonicalizationError(f"{field} contains invalid Unicode") from exc
    if not unicodedata.is_normalized("NFC", value):
        raise CanonicalizationError(f"{field} must use NFC-normalized Unicode")
    text = value
    octet_limit = maximum if maximum_utf8_octets is None else maximum_utf8_octets
    if len(text.encode("utf-8")) > octet_limit:
        raise CanonicalizationError(f"{field} exceeds {octet_limit} UTF-8 octets")
    return text


def _ascii_text(
    value: Any,
    *,
    field: str,
    minimum: int,
    maximum: int,
    pattern: re.Pattern[str] | None = None,
) -> str:
    # ASCII-only languages are UCD-invariant and must remain usable for
    # diagnostics even when unrestricted-Unicode validation is unavailable.
    if (
        type(value) is not str
        or not minimum <= len(value) <= maximum
        or not value.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
        or value[0] == " "
        or value[-1] == " "
    ):
        raise CanonicalizationError(f"{field} must be {minimum}..{maximum} ASCII bytes")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise CanonicalizationError(f"{field} has unsupported ASCII syntax")
    return value


def _hash(value: Any, *, field: str) -> str:
    if type(value) is not str or _SHA256_ASCII_RE.fullmatch(value) is None:
        raise CanonicalizationError(f"{field} must be a lowercase SHA-256 digest")
    return canonical_hash(value, field=field)


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else _hash(value, field=field)


def _uint128_text(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or len(value) > 39
        or _UINT128_ASCII_RE.fullmatch(value) is None
        or int(value) >= 1 << 128
    ):
        raise CanonicalizationError(
            f"{field} must be canonical unsigned 128-bit decimal text"
        )
    return value


def _exact_utc(value: Any, *, field: str) -> datetime:
    if type(value) not in {datetime, str}:
        raise CanonicalizationError(f"{field} must be an exact datetime or string")
    return utc_datetime(value, field=field)


def _canonical_base64(
    value: Any,
    *,
    field: str,
    maximum_encoded_octets: int,
    maximum_decoded_octets: int,
    require_nonempty: bool,
) -> bytes:
    if type(value) is not str or not value.isascii():
        raise CanonicalizationError(f"{field} must be exact ASCII base64 text")
    if len(value) > maximum_encoded_octets or (require_nonempty and not value):
        raise CanonicalizationError(f"{field} exceeds its encoded safety bound")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CanonicalizationError(
            f"{field} must be canonical standard base64"
        ) from exc
    if (
        len(decoded) > maximum_decoded_octets
        or (require_nonempty and not decoded)
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        raise CanonicalizationError(f"{field} exceeds its bound or is noncanonical")
    return decoded


def _exact_tuple(value: Any, *, field: str) -> tuple[Any, ...]:
    if type(value) is not tuple:
        raise CanonicalizationError(f"{field} must be an exact tuple")
    return value


def _exact_json_list(value: Any, *, field: str, maximum: int) -> list[Any]:
    if type(value) is not list or len(value) > maximum:
        raise CanonicalizationError(f"{field} must be a bounded exact JSON array")
    return value


def _exact_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CanonicalizationError(f"{field} must be an exact JSON object")
    return value


def _exact_string(value: Any, *, field: str) -> str:
    if type(value) is not str:
        raise CanonicalizationError(f"{field} must be an exact string")
    return value


def _exact_string_tuple(
    value: Any,
    *,
    field: str,
    unique: bool = True,
    sorted_values: bool = False,
) -> tuple[str, ...]:
    items = _exact_tuple(value, field=field)
    if any(type(item) is not str for item in items):
        raise CanonicalizationError(f"{field} must contain exact strings")
    if unique and len(set(items)) != len(items):
        raise CanonicalizationError(f"{field} must contain unique strings")
    if sorted_values and items != tuple(sorted(items)):
        raise CanonicalizationError(f"{field} must be ascending UTF-8 strings")
    return items


def _semantic_id(*, domain: str, payload: Mapping[str, Any]) -> str:
    if type(payload) is not dict:
        payload = dict(payload)
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": payload,
            "schema_version": PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION,
        }
    )


def _bounded_canonical_bytes(
    payload: Mapping[str, Any],
    *,
    context: str,
    maximum: int,
    maximum_is_exclusive: bool = False,
) -> bytes:
    encoded = canonical_json_bytes(dict(payload))
    if maximum_is_exclusive and len(encoded) >= maximum:
        raise CanonicalizationError(
            f"{context} reaches or exceeds its {maximum}-byte canonical "
            "exclusive ceiling"
        )
    if not maximum_is_exclusive and len(encoded) > maximum:
        raise CanonicalizationError(
            f"{context} exceeds its {maximum}-byte canonical inclusive bound"
        )
    return encoded


def validate_capacity_measurement_json_structure_before_parse_v49f_v8(
    payload: bytes,
) -> None:
    """Bound Raw-V8 JSON structure before materializing the JSON tree."""

    malformed = RAW_V8_JSON_MALFORMED_STRUCTURE_V49F

    def reject(reason: str) -> None:
        raise CanonicalizationError(f"Raw V8 JSON structural guard rejected: {reason}")

    if type(payload) is not bytes or not payload:
        reject(malformed)

    stack: list[list[Any]] = []
    root_state = "VALUE"
    whitespace = b" \t\r\n"
    hexadecimal = b"0123456789abcdefABCDEF"
    simple_escapes = b'"\\/bfnrt'

    def scan_string(index: int) -> int:
        index += 1
        while index < len(payload):
            value = payload[index]
            if value == 0x22:
                return index + 1
            if value < 0x20:
                reject(malformed)
            if value != 0x5C:
                index += 1
                continue
            index += 1
            if index >= len(payload):
                reject(malformed)
            escape = payload[index]
            if escape in simple_escapes:
                index += 1
                continue
            if escape != ord("u") or index + 4 >= len(payload):
                reject(malformed)
            if any(item not in hexadecimal for item in payload[index + 1 : index + 5]):
                reject(malformed)
            index += 5
        reject(malformed)
        raise AssertionError("unreachable")

    def begin_value() -> None:
        nonlocal root_state
        if not stack:
            if root_state != "VALUE":
                reject(malformed)
            root_state = "END"
            return
        frame = stack[-1]
        if frame[0] == "ARRAY":
            if frame[1] not in {"VALUE_OR_END", "VALUE"}:
                reject(malformed)
            frame[2] += 1
            if frame[2] > RAW_V8_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F:
                reject(RAW_V8_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F)
            frame[1] = "COMMA_OR_END"
            return
        if frame[1] != "VALUE":
            reject(malformed)
        frame[1] = "COMMA_OR_END"

    def open_container(kind: str) -> None:
        if len(stack) >= RAW_V8_MAXIMUM_JSON_NESTING_DEPTH_V49F:
            reject(RAW_V8_JSON_DEPTH_LIMIT_EXCEEDED_V49F)
        stack.append([kind, "KEY_OR_END" if kind == "OBJECT" else "VALUE_OR_END", 0])

    index = 0
    try:
        while True:
            while index < len(payload) and payload[index] in whitespace:
                index += 1
            if index >= len(payload):
                break
            value = payload[index]
            if stack:
                frame = stack[-1]
                kind = frame[0]
                state = frame[1]
                if kind == "OBJECT" and state in {"KEY_OR_END", "KEY"}:
                    if value == ord("}") and state == "KEY_OR_END":
                        stack.pop()
                        index += 1
                        continue
                    if value != ord('"'):
                        reject(malformed)
                    index = scan_string(index)
                    frame[2] += 1
                    if frame[2] > RAW_V8_MAXIMUM_JSON_OBJECT_MEMBERS_V49F:
                        reject(RAW_V8_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F)
                    frame[1] = "COLON"
                    continue
                if kind == "OBJECT" and state == "COLON":
                    if value != ord(":"):
                        reject(malformed)
                    frame[1] = "VALUE"
                    index += 1
                    continue
                if state == "COMMA_OR_END":
                    closing = ord("}") if kind == "OBJECT" else ord("]")
                    if value == closing:
                        stack.pop()
                        index += 1
                        continue
                    if value != ord(","):
                        reject(malformed)
                    frame[1] = "KEY" if kind == "OBJECT" else "VALUE"
                    index += 1
                    continue
                if kind == "ARRAY" and state == "VALUE_OR_END" and value == ord("]"):
                    stack.pop()
                    index += 1
                    continue
            elif root_state == "END":
                reject(malformed)

            begin_value()
            if value == ord("{"):
                open_container("OBJECT")
                index += 1
                continue
            if value == ord("["):
                open_container("ARRAY")
                index += 1
                continue
            if value == ord('"'):
                index = scan_string(index)
                continue
            if value in b",:]}{[":
                reject(malformed)
            start = index
            while index < len(payload) and payload[index] not in b" \t\r\n,:]}{[":
                index += 1
            if index == start:
                reject(malformed)
    except CanonicalizationError:
        raise
    except (IndexError, TypeError, ValueError) as exc:
        raise CanonicalizationError(
            f"Raw V8 JSON structural guard rejected: {malformed}"
        ) from exc
    if stack or root_state != "END":
        reject(malformed)


def _validate_typed_structure(value: Any) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > RAW_V8_MAXIMUM_TYPED_NESTING_DEPTH_V49F:
            raise CanonicalizationError("Raw V8 typed nesting depth exceeds 16")
        if type(current) is dict:
            if len(current) > RAW_V8_MAXIMUM_TYPED_OBJECT_MEMBERS_V49F:
                raise CanonicalizationError("Raw V8 typed object exceeds 32 members")
            stack.extend((child, depth + 1) for child in current.values())
        elif type(current) is list:
            stack.extend((child, depth + 1) for child in current)


class _StandaloneRecordV49FV8:
    _DOMAIN: ClassVar[str]
    _IDENTITY_FIELD: ClassVar[str]
    _MAXIMUM_BYTES: ClassVar[int]
    _MAXIMUM_BYTES_IS_EXCLUSIVE: ClassVar[bool] = False

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        raise TypeError("base Raw V8 record has no identity payload")

    def _seal_identity(self) -> None:
        payload = self._identity_payload_unchecked()
        reserved_members = {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            self._IDENTITY_FIELD,
        }
        collisions = reserved_members.intersection(payload)
        if collisions:
            raise CanonicalizationError(
                "Raw V8 identity payload collides with standalone envelope "
                f"members: {sorted(collisions)!r}"
            )
        identity = _semantic_id(domain=self._DOMAIN, payload=payload)
        supplied = getattr(self, self._IDENTITY_FIELD)
        if (
            supplied is not None
            and _hash(supplied, field=self._IDENTITY_FIELD) != identity
        ):
            raise CanonicalizationError(
                f"{self._IDENTITY_FIELD} differs from canonical Raw V8 members"
            )
        object.__setattr__(self, self._IDENTITY_FIELD, identity)
        _bounded_canonical_bytes(
            self._envelope_unchecked(),
            context=type(self).__name__,
            maximum=self._MAXIMUM_BYTES,
            maximum_is_exclusive=self._MAXIMUM_BYTES_IS_EXCLUSIVE,
        )

    def _envelope_unchecked(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "measurement_schema_version": (
                PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION
            ),
            "record_domain": self._DOMAIN,
            **self._identity_payload_unchecked(),
            self._IDENTITY_FIELD: getattr(self, self._IDENTITY_FIELD),
        }

    def _revalidated(self: _RecordT) -> _RecordT:
        reconstructed = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if reconstructed != self:
            raise CanonicalizationError(
                f"{type(self).__name__} differs from exact reconstruction"
            )
        return reconstructed

    def identity_payload(self) -> dict[str, Any]:
        return self._revalidated()._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        record = self._revalidated()
        result = record._envelope_unchecked()
        _bounded_canonical_bytes(
            result,
            context=type(self).__name__,
            maximum=self._MAXIMUM_BYTES,
            maximum_is_exclusive=self._MAXIMUM_BYTES_IS_EXCLUSIVE,
        )
        return result

    def canonical_bytes(self) -> bytes:
        return _bounded_canonical_bytes(
            self.as_dict(),
            context=type(self).__name__,
            maximum=self._MAXIMUM_BYTES,
            maximum_is_exclusive=self._MAXIMUM_BYTES_IS_EXCLUSIVE,
        )

    @classmethod
    def from_json_bytes(cls: type[_RecordT], payload: bytes) -> _RecordT:
        if (
            type(payload) is not bytes
            or not payload
            or (
                len(payload) >= cls._MAXIMUM_BYTES
                if cls._MAXIMUM_BYTES_IS_EXCLUSIVE
                else len(payload) > cls._MAXIMUM_BYTES
            )
        ):
            raise CanonicalizationError(
                f"{cls.__name__} bytes are empty, non-exact, or exceed their bound"
            )
        validate_capacity_measurement_json_structure_before_parse_v49f_v8(payload)
        decoded = strict_json_loads(payload)
        _validate_typed_structure(decoded)
        if type(decoded) is not dict:
            raise CanonicalizationError(f"{cls.__name__} must decode to an object")
        result = cls.from_mapping(decoded)  # type: ignore[attr-defined]
        if result.canonical_bytes() != payload:
            raise CanonicalizationError(f"{cls.__name__} bytes are not canonical")
        return result


def _validate_envelope(
    payload: Any,
    *,
    record_type: type[Any],
    domain: str,
    identity_field: str,
) -> dict[str, Any]:
    mapping = _exact_mapping(payload, field=record_type.__name__)
    expected = {item.name for item in fields(record_type)} | {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
    }
    require_exact_keys(mapping, expected=expected, context=record_type.__name__)
    if mapping["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("Raw V8 canonicalization version differs")
    if (
        mapping["measurement_schema_version"]
        != PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION
    ):
        raise CanonicalizationError("Raw V8 measurement schema version differs")
    if mapping["record_domain"] != domain:
        raise CanonicalizationError("Raw V8 record domain differs")
    _hash(mapping[identity_field], field=identity_field)
    return mapping


class _NestedRecordV49FV8:
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_DECLARATION_BYTES_V49F

    def _as_dict_unchecked(self) -> dict[str, Any]:
        raise TypeError("base Raw V8 nested record has no payload")

    def _revalidated(self) -> Any:
        reconstructed = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if reconstructed != self:
            raise CanonicalizationError(
                f"{type(self).__name__} differs from exact reconstruction"
            )
        return reconstructed

    def as_dict(self) -> dict[str, Any]:
        result = self._revalidated()._as_dict_unchecked()
        _bounded_canonical_bytes(
            result,
            context=type(self).__name__,
            maximum=self._MAXIMUM_BYTES,
        )
        return result


def _require_nested_keys(
    payload: Any, *, expected: frozenset[str], context: str
) -> dict[str, Any]:
    mapping = _exact_mapping(payload, field=context)
    require_exact_keys(mapping, expected=expected, context=context)
    return mapping


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLogicalOutputFrameV49FV8(_NestedRecordV49FV8):
    opcode: CapacityMeasurementLogicalOutputOpcodeV49FV8
    payload_base64: str

    def __post_init__(self) -> None:
        _exact_enum(
            self.opcode,
            CapacityMeasurementLogicalOutputOpcodeV49FV8,
            field="opcode",
        )
        decoded = _canonical_base64(
            self.payload_base64,
            field="payload_base64",
            maximum_encoded_octets=RAW_V8_MAXIMUM_CONTROL_PAYLOAD_BASE64_BYTES_V49F,
            maximum_decoded_octets=RAW_V8_MAXIMUM_CONTROL_PAYLOAD_OCTETS_V49F,
            require_nonempty=False,
        )
        if self.opcode is CapacityMeasurementLogicalOutputOpcodeV49FV8.CLOSE:
            if len(decoded) == 1:
                raise CanonicalizationError(
                    "CLOSE payload cannot contain one status octet"
                )
            if len(decoded) >= 2:
                close_code = int.from_bytes(decoded[:2], "big")
                if not (
                    close_code
                    in {
                        1000,
                        1001,
                        1002,
                        1003,
                        1007,
                        1008,
                        1009,
                        1010,
                        1011,
                        1012,
                        1013,
                        1014,
                    }
                    or 3000 <= close_code <= 4999
                ):
                    raise CanonicalizationError(
                        "CLOSE payload contains an unsupported status code"
                    )
                try:
                    decoded[2:].decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise CanonicalizationError(
                        "CLOSE reason must be strictly valid UTF-8"
                    ) from exc

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"opcode": self.opcode.value, "payload_base64": self.payload_base64}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLogicalOutputFrameV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"opcode", "payload_base64"}),
            context=cls.__name__,
        )
        return cls(
            opcode=_enum_from_json(
                item["opcode"],
                CapacityMeasurementLogicalOutputOpcodeV49FV8,
                field="opcode",
            ),
            payload_base64=item["payload_base64"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressLogicalOracleProfileV49FV8(_StandaloneRecordV49FV8):
    profile_version: str
    oracle_kind: str
    input_chunk_semantics: str
    requires_empty_fragmentation_baseline: bool
    requires_empty_complete_unit_baseline: bool
    maximum_input_chunks: int
    maximum_input_octets: int
    maximum_parser_units: int
    maximum_completed_application_messages: int
    maximum_logical_output_frames: int
    maximum_logical_output_payload_octets: int
    logical_output_frame_domain: str
    raw_ingress_batch_domain: str
    streamed_digest_algorithm: str
    parser_oracle_descriptor_requirement: str
    logical_oracle_profile_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "logical_oracle_profile_id"
    _MAXIMUM_BYTES: ClassVar[int] = 8 * 1024

    def __post_init__(self) -> None:
        exact_text = {
            "profile_version": "riskyieldmm_ingress_logical_oracle_profile_v1",
            "oracle_kind": "INDEPENDENT_RESTRICTED_WASM_RFC6455_STREAM",
            "input_chunk_semantics": "EXACT_ORDERED_DECRYPTED_APPLICATION_OCTETS",
            "logical_output_frame_domain": (
                "RiskYieldMMA2MExactLogicalOutputFramesV4_9F"
            ),
            "raw_ingress_batch_domain": (
                "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"
            ),
            "streamed_digest_algorithm": ("CANONICAL_JSON_SHA256_INCREMENTAL_V1"),
            "parser_oracle_descriptor_requirement": (
                "COMPLETE_DESCRIPTOR_AND_CONFORMANCE_CORPUS_IN_TARGET_BOUND_UNIVERSE"
            ),
        }
        for name, expected in exact_text.items():
            value = getattr(self, name)
            if type(value) is not str or value != expected:
                raise CanonicalizationError(
                    f"{name} differs from the frozen ingress oracle profile"
                )
        for name in (
            "requires_empty_fragmentation_baseline",
            "requires_empty_complete_unit_baseline",
        ):
            if not _exact_bool(getattr(self, name), field=name):
                raise CanonicalizationError(f"{name} must be true")
        exact_integers = {
            "maximum_input_chunks": RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F,
            "maximum_input_octets": RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
            "maximum_parser_units": RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F,
            "maximum_completed_application_messages": (
                RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F
            ),
            "maximum_logical_output_frames": (
                RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F
            ),
            "maximum_logical_output_payload_octets": (
                RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F
            ),
        }
        for name, expected in exact_integers.items():
            if (
                _safe_uint(
                    getattr(self, name),
                    field=name,
                    minimum=expected,
                    maximum=expected,
                )
                != expected
            ):
                raise CanonicalizationError(
                    f"{name} differs from the frozen ingress oracle profile"
                )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "profile_version": self.profile_version,
            "oracle_kind": self.oracle_kind,
            "input_chunk_semantics": self.input_chunk_semantics,
            "requires_empty_fragmentation_baseline": (
                self.requires_empty_fragmentation_baseline
            ),
            "requires_empty_complete_unit_baseline": (
                self.requires_empty_complete_unit_baseline
            ),
            "maximum_input_chunks": self.maximum_input_chunks,
            "maximum_input_octets": self.maximum_input_octets,
            "maximum_parser_units": self.maximum_parser_units,
            "maximum_completed_application_messages": (
                self.maximum_completed_application_messages
            ),
            "maximum_logical_output_frames": self.maximum_logical_output_frames,
            "maximum_logical_output_payload_octets": (
                self.maximum_logical_output_payload_octets
            ),
            "logical_output_frame_domain": self.logical_output_frame_domain,
            "raw_ingress_batch_domain": self.raw_ingress_batch_domain,
            "streamed_digest_algorithm": self.streamed_digest_algorithm,
            "parser_oracle_descriptor_requirement": (
                self.parser_oracle_descriptor_requirement
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIngressLogicalOracleProfileV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(**{field.name: item[field.name] for field in fields(cls)})


RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_V49F = (
    CapacityMeasurementIngressLogicalOracleProfileV49FV8(
        profile_version="riskyieldmm_ingress_logical_oracle_profile_v1",
        oracle_kind="INDEPENDENT_RESTRICTED_WASM_RFC6455_STREAM",
        input_chunk_semantics="EXACT_ORDERED_DECRYPTED_APPLICATION_OCTETS",
        requires_empty_fragmentation_baseline=True,
        requires_empty_complete_unit_baseline=True,
        maximum_input_chunks=RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F,
        maximum_input_octets=RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
        maximum_parser_units=RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F,
        maximum_completed_application_messages=(
            RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F
        ),
        maximum_logical_output_frames=RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F,
        maximum_logical_output_payload_octets=(
            RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F
        ),
        logical_output_frame_domain=("RiskYieldMMA2MExactLogicalOutputFramesV4_9F"),
        raw_ingress_batch_domain=("RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"),
        streamed_digest_algorithm="CANONICAL_JSON_SHA256_INCREMENTAL_V1",
        parser_oracle_descriptor_requirement=(
            "COMPLETE_DESCRIPTOR_AND_CONFORMANCE_CORPUS_IN_TARGET_BOUND_UNIVERSE"
        ),
    )
)
RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_ID_V49F = (
    RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_V49F.logical_oracle_profile_id
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressOperationSpecV49FV8(_NestedRecordV49FV8):
    workload_family: str
    ordered_input_chunks_base64: tuple[str, ...]
    input_chunk_count: int
    input_octet_count: int
    input_sha256: str
    raw_ingress_batch_sha256: str
    timeout_seconds: int
    logical_oracle_profile_id: str
    expected_parser_unit_count: int
    expected_completed_application_message_count: int
    expected_logical_output_frame_count: int
    expected_logical_output_payload_octets: int
    expected_logical_output_frames_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workload_family",
            _utf8_identifier(
                self.workload_family,
                field="workload_family",
                maximum=RAW_V8_MAXIMUM_WORKLOAD_FAMILY_UTF8_BYTES_V49F,
            ),
        )
        chunks = _exact_tuple(
            self.ordered_input_chunks_base64,
            field="ordered_input_chunks_base64",
        )
        if not 1 <= len(chunks) <= RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F:
            raise CanonicalizationError("input chunks are outside the 1..128 bound")
        input_digest = hashlib.sha256()
        total_input_octets = 0
        for index, value in enumerate(chunks):
            decoded = _canonical_base64(
                value,
                field=f"ordered_input_chunks_base64[{index}]",
                maximum_encoded_octets=(RAW_V8_MAXIMUM_INGRESS_CHUNK_BASE64_BYTES_V49F),
                maximum_decoded_octets=RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
                require_nonempty=True,
            )
            total_input_octets += len(decoded)
            if total_input_octets > RAW_V8_MAXIMUM_INPUT_OCTETS_V49F:
                raise CanonicalizationError("aggregate ingress bytes exceed 65,536")
            input_digest.update(decoded)
        if _safe_uint(
            self.input_chunk_count,
            field="input_chunk_count",
            minimum=1,
            maximum=RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F,
        ) != len(chunks):
            raise CanonicalizationError("input_chunk_count differs from chunks")
        if (
            _safe_uint(
                self.input_octet_count,
                field="input_octet_count",
                minimum=1,
                maximum=RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
            )
            != total_input_octets
        ):
            raise CanonicalizationError("input_octet_count differs from chunks")
        if _hash(self.input_sha256, field="input_sha256") != input_digest.hexdigest():
            raise CanonicalizationError("input_sha256 differs from exact chunk bytes")
        raw_batch_id = sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(chunks),
            }
        )
        if (
            _hash(
                self.raw_ingress_batch_sha256,
                field="raw_ingress_batch_sha256",
            )
            != raw_batch_id
        ):
            raise CanonicalizationError(
                "raw_ingress_batch_sha256 differs from exact ordered chunks"
            )
        object.__setattr__(
            self,
            "timeout_seconds",
            _safe_uint(
                self.timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            ),
        )
        object.__setattr__(
            self,
            "logical_oracle_profile_id",
            _hash(
                self.logical_oracle_profile_id,
                field="logical_oracle_profile_id",
            ),
        )
        if (
            self.logical_oracle_profile_id
            != RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_ID_V49F
        ):
            raise CanonicalizationError(
                "ingress spec uses a foreign logical-oracle profile"
            )
        parser_units = _safe_uint(
            self.expected_parser_unit_count,
            field="expected_parser_unit_count",
            maximum=RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F,
        )
        completed_messages = _safe_uint(
            self.expected_completed_application_message_count,
            field="expected_completed_application_message_count",
            maximum=RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F,
        )
        output_frames = _safe_uint(
            self.expected_logical_output_frame_count,
            field="expected_logical_output_frame_count",
            maximum=RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F,
        )
        output_octets = _safe_uint(
            self.expected_logical_output_payload_octets,
            field="expected_logical_output_payload_octets",
            maximum=RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F,
        )
        object.__setattr__(
            self,
            "expected_logical_output_frames_sha256",
            _hash(
                self.expected_logical_output_frames_sha256,
                field="expected_logical_output_frames_sha256",
            ),
        )
        # These are necessary shape constraints derivable without running the
        # independently supplied parser oracle.  Exact achievability remains
        # the target-bound oracle/corpus verifier's authority.
        if (
            parser_units > total_input_octets // 2
            or completed_messages > parser_units
            or output_frames > parser_units
            or output_octets
            > output_frames * RAW_V8_MAXIMUM_CONTROL_PAYLOAD_OCTETS_V49F
        ):
            raise CanonicalizationError(
                "ingress oracle expectations are not mutually achievable"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "workload_family": self.workload_family,
            "ordered_input_chunks_base64": list(self.ordered_input_chunks_base64),
            "input_chunk_count": self.input_chunk_count,
            "input_octet_count": self.input_octet_count,
            "input_sha256": self.input_sha256,
            "raw_ingress_batch_sha256": self.raw_ingress_batch_sha256,
            "timeout_seconds": self.timeout_seconds,
            "logical_oracle_profile_id": self.logical_oracle_profile_id,
            "expected_parser_unit_count": self.expected_parser_unit_count,
            "expected_completed_application_message_count": (
                self.expected_completed_application_message_count
            ),
            "expected_logical_output_frame_count": (
                self.expected_logical_output_frame_count
            ),
            "expected_logical_output_payload_octets": (
                self.expected_logical_output_payload_octets
            ),
            "expected_logical_output_frames_sha256": (
                self.expected_logical_output_frames_sha256
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIngressOperationSpecV49FV8:
        expected = frozenset(item.name for item in fields(cls))
        item = _require_nested_keys(payload, expected=expected, context=cls.__name__)
        chunks = _exact_json_list(
            item["ordered_input_chunks_base64"],
            field="ordered_input_chunks_base64",
            maximum=RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F,
        )
        return cls(
            workload_family=item["workload_family"],
            ordered_input_chunks_base64=tuple(chunks),
            input_chunk_count=item["input_chunk_count"],
            input_octet_count=item["input_octet_count"],
            input_sha256=item["input_sha256"],
            raw_ingress_batch_sha256=item["raw_ingress_batch_sha256"],
            timeout_seconds=item["timeout_seconds"],
            logical_oracle_profile_id=item["logical_oracle_profile_id"],
            expected_parser_unit_count=item["expected_parser_unit_count"],
            expected_completed_application_message_count=item[
                "expected_completed_application_message_count"
            ],
            expected_logical_output_frame_count=item[
                "expected_logical_output_frame_count"
            ],
            expected_logical_output_payload_octets=item[
                "expected_logical_output_payload_octets"
            ],
            expected_logical_output_frames_sha256=item[
                "expected_logical_output_frames_sha256"
            ],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSubscriptionDispatchSpecV49FV8(_NestedRecordV49FV8):
    workload_family: str
    idempotency_key: str
    transport_subscription_policy_id: str
    adapter_policy_id: str
    expected_topic: str
    expected_operation: str
    expected_logical_opcode: str
    expected_dispatch_disposition: CapacityMeasurementDispatchDispositionV49FV8

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workload_family",
            _utf8_identifier(
                self.workload_family,
                field="workload_family",
                maximum=RAW_V8_MAXIMUM_WORKLOAD_FAMILY_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "idempotency_key",
            _ascii_text(
                self.idempotency_key,
                field="idempotency_key",
                minimum=1,
                maximum=128,
                pattern=_IDEMPOTENCY_KEY_RE,
            ),
        )
        for name in (
            "transport_subscription_policy_id",
            "adapter_policy_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        topic = _utf8_identifier(
            self.expected_topic,
            field="expected_topic",
            maximum=256,
            maximum_utf8_octets=1_024,
        )
        object.__setattr__(self, "expected_topic", topic)
        if type(self.expected_operation) is not str or self.expected_operation != (
            "subscribe"
        ):
            raise CanonicalizationError("expected_operation must be exact subscribe")
        if (
            self.expected_logical_opcode != "TEXT"
            or type(self.expected_logical_opcode) is not str
        ):
            raise CanonicalizationError("expected_logical_opcode must be exact TEXT")
        _exact_enum(
            self.expected_dispatch_disposition,
            CapacityMeasurementDispatchDispositionV49FV8,
            field="expected_dispatch_disposition",
        )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "workload_family": self.workload_family,
            "idempotency_key": self.idempotency_key,
            "transport_subscription_policy_id": (self.transport_subscription_policy_id),
            "adapter_policy_id": self.adapter_policy_id,
            "expected_topic": self.expected_topic,
            "expected_operation": self.expected_operation,
            "expected_logical_opcode": self.expected_logical_opcode,
            "expected_dispatch_disposition": self.expected_dispatch_disposition.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSubscriptionDispatchSpecV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["expected_dispatch_disposition"] = _enum_from_json(
            item["expected_dispatch_disposition"],
            CapacityMeasurementDispatchDispositionV49FV8,
            field="expected_dispatch_disposition",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAckDeadlineExpirySpecV49FV8(_NestedRecordV49FV8):
    workload_family: str
    expected_outbound_subscription_intent_id: str
    due_scenario: CapacityMeasurementAckDueScenarioV49FV8
    expected_terminal_cause_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workload_family",
            _utf8_identifier(
                self.workload_family,
                field="workload_family",
                maximum=RAW_V8_MAXIMUM_WORKLOAD_FAMILY_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "expected_outbound_subscription_intent_id",
            _hash(
                self.expected_outbound_subscription_intent_id,
                field="expected_outbound_subscription_intent_id",
            ),
        )
        _exact_enum(
            self.due_scenario,
            CapacityMeasurementAckDueScenarioV49FV8,
            field="due_scenario",
        )
        expected = (
            "ACK_DEADLINE_EXPIRED"
            if self.due_scenario is CapacityMeasurementAckDueScenarioV49FV8.DUE
            else None
        )
        if (
            self.expected_terminal_cause_code is not None
            and type(self.expected_terminal_cause_code) is not str
        ):
            raise CanonicalizationError(
                "expected_terminal_cause_code must be an exact string or null"
            )
        if self.expected_terminal_cause_code != expected:
            raise CanonicalizationError(
                "ACK due scenario and terminal cause code disagree"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "workload_family": self.workload_family,
            "expected_outbound_subscription_intent_id": (
                self.expected_outbound_subscription_intent_id
            ),
            "due_scenario": self.due_scenario.value,
            "expected_terminal_cause_code": self.expected_terminal_cause_code,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAckDeadlineExpirySpecV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            workload_family=item["workload_family"],
            expected_outbound_subscription_intent_id=item[
                "expected_outbound_subscription_intent_id"
            ],
            due_scenario=_enum_from_json(
                item["due_scenario"],
                CapacityMeasurementAckDueScenarioV49FV8,
                field="due_scenario",
            ),
            expected_terminal_cause_code=item["expected_terminal_cause_code"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLocalShutdownSpecV49FV8(_NestedRecordV49FV8):
    workload_family: str
    timeout_seconds: int
    expected_terminal_outcome: CapacityMeasurementTerminalOutcomeV49FV8
    expected_local_close_code: int
    expected_local_close_reason_sha256: str
    maximum_terminal_ingress_batches: int
    maximum_terminal_ingress_ciphertext_octets: int
    maximum_terminal_ingress_plaintext_octets: int
    maximum_terminal_socket_receive_calls: int
    maximum_terminal_tls_records: int
    maximum_terminal_tls_unwrap_iterations: int
    maximum_terminal_zero_progress_iterations: int
    maximum_terminal_ingress_parser_units: int
    maximum_terminal_ingress_automatic_outputs: int
    maximum_websocket_send_attempts: int
    maximum_tls_control_send_attempts: int
    maximum_peer_shutdown_polls: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workload_family",
            _utf8_identifier(
                self.workload_family,
                field="workload_family",
                maximum=RAW_V8_MAXIMUM_WORKLOAD_FAMILY_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "timeout_seconds",
            _safe_uint(
                self.timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            ),
        )
        _exact_enum(
            self.expected_terminal_outcome,
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="expected_terminal_outcome",
        )
        if (
            _safe_uint(
                self.expected_local_close_code,
                field="expected_local_close_code",
                minimum=1000,
                maximum=1000,
            )
            != 1000
        ):
            raise CanonicalizationError("local shutdown Close code must be 1000")
        expected_digest = hashlib.sha256(b"").hexdigest()
        if (
            _hash(
                self.expected_local_close_reason_sha256,
                field="expected_local_close_reason_sha256",
            )
            != expected_digest
        ):
            raise CanonicalizationError("local shutdown Close reason must be empty")
        limits = (
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
        )
        for name in limits:
            object.__setattr__(
                self,
                name,
                _safe_uint(getattr(self, name), field=name, minimum=1),
            )
        minimum_batches_for_plaintext = (
            self.maximum_terminal_ingress_plaintext_octets // 16_384
            + (1 if self.maximum_terminal_ingress_plaintext_octets % 16_384 else 0)
        )
        if (
            minimum_batches_for_plaintext > self.maximum_terminal_ingress_batches
            or self.maximum_terminal_ingress_parser_units
            > self.maximum_terminal_ingress_plaintext_octets // 2
            or self.maximum_terminal_ingress_parser_units > 4_096
            or self.maximum_terminal_tls_records > self.maximum_terminal_ingress_batches
            or self.maximum_terminal_ingress_automatic_outputs
            > self.maximum_terminal_ingress_parser_units
            or self.maximum_websocket_send_attempts
            > 256 * (1 + self.maximum_terminal_ingress_automatic_outputs)
            or self.maximum_tls_control_send_attempts > 256
            or self.maximum_peer_shutdown_polls != 2
        ):
            raise CanonicalizationError(
                "local-shutdown signed limit vector is internally inconsistent"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "workload_family": self.workload_family,
            "timeout_seconds": self.timeout_seconds,
            "expected_terminal_outcome": self.expected_terminal_outcome.value,
            "expected_local_close_code": self.expected_local_close_code,
            "expected_local_close_reason_sha256": (
                self.expected_local_close_reason_sha256
            ),
            "maximum_terminal_ingress_batches": (self.maximum_terminal_ingress_batches),
            "maximum_terminal_ingress_ciphertext_octets": (
                self.maximum_terminal_ingress_ciphertext_octets
            ),
            "maximum_terminal_ingress_plaintext_octets": (
                self.maximum_terminal_ingress_plaintext_octets
            ),
            "maximum_terminal_socket_receive_calls": (
                self.maximum_terminal_socket_receive_calls
            ),
            "maximum_terminal_tls_records": self.maximum_terminal_tls_records,
            "maximum_terminal_tls_unwrap_iterations": (
                self.maximum_terminal_tls_unwrap_iterations
            ),
            "maximum_terminal_zero_progress_iterations": (
                self.maximum_terminal_zero_progress_iterations
            ),
            "maximum_terminal_ingress_parser_units": (
                self.maximum_terminal_ingress_parser_units
            ),
            "maximum_terminal_ingress_automatic_outputs": (
                self.maximum_terminal_ingress_automatic_outputs
            ),
            "maximum_websocket_send_attempts": self.maximum_websocket_send_attempts,
            "maximum_tls_control_send_attempts": (
                self.maximum_tls_control_send_attempts
            ),
            "maximum_peer_shutdown_polls": self.maximum_peer_shutdown_polls,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLocalShutdownSpecV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["expected_terminal_outcome"] = _enum_from_json(
            item["expected_terminal_outcome"],
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="expected_terminal_outcome",
        )
        return cls(**values)


_OperationSpecBodyV49FV8 = (
    CapacityMeasurementIngressOperationSpecV49FV8
    | CapacityMeasurementSubscriptionDispatchSpecV49FV8
    | CapacityMeasurementAckDeadlineExpirySpecV49FV8
    | CapacityMeasurementLocalShutdownSpecV49FV8
)

_SPEC_TAG_MATRIX_V49FV8: dict[
    CapacityMeasurementOperationKindV49FV8,
    tuple[CapacityMeasurementOperationSpecTypeV49FV8, type[Any]],
] = {
    CapacityMeasurementOperationKindV49FV8.INGRESS: (
        CapacityMeasurementOperationSpecTypeV49FV8.INGRESS_OPERATION_SPEC_V2,
        CapacityMeasurementIngressOperationSpecV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.SUBSCRIPTION_DISPATCH: (
        CapacityMeasurementOperationSpecTypeV49FV8.SUBSCRIPTION_DISPATCH_SPEC_V2,
        CapacityMeasurementSubscriptionDispatchSpecV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY: (
        CapacityMeasurementOperationSpecTypeV49FV8.ACK_DEADLINE_EXPIRY_SPEC_V1,
        CapacityMeasurementAckDeadlineExpirySpecV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN: (
        CapacityMeasurementOperationSpecTypeV49FV8.LOCAL_SHUTDOWN_SPEC_V2,
        CapacityMeasurementLocalShutdownSpecV49FV8,
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationSpecV49FV8(_StandaloneRecordV49FV8):
    operation_kind: CapacityMeasurementOperationKindV49FV8
    spec_type: CapacityMeasurementOperationSpecTypeV49FV8
    spec: _OperationSpecBodyV49FV8
    operation_spec_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_OPERATION_SPEC_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "operation_spec_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_SPEC_BYTES_V49F

    def __post_init__(self) -> None:
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.spec_type,
            CapacityMeasurementOperationSpecTypeV49FV8,
            field="spec_type",
        )
        expected_tag, expected_type = _SPEC_TAG_MATRIX_V49FV8[self.operation_kind]
        if self.spec_type is not expected_tag or type(self.spec) is not expected_type:
            raise CanonicalizationError("operation kind, spec tag, and body disagree")
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "operation_kind": self.operation_kind.value,
            "spec_type": self.spec_type.value,
            "spec": self.spec.as_dict(),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationSpecV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        operation_kind = _enum_from_json(
            item["operation_kind"],
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        spec_type = _enum_from_json(
            item["spec_type"],
            CapacityMeasurementOperationSpecTypeV49FV8,
            field="spec_type",
        )
        _, body_type = _SPEC_TAG_MATRIX_V49FV8[operation_kind]
        return cls(
            operation_kind=operation_kind,
            spec_type=spec_type,
            spec=body_type.from_mapping(item["spec"]),
            operation_spec_id=item["operation_spec_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationDeclarationV49FV8(_StandaloneRecordV49FV8):
    campaign_manifest_id: str
    manifest_authority_id: str
    measurement_design_id: str
    workload_plan_id: str
    workload_id: str
    workload_sha256: str
    sample_sequence: int
    operation_sequence: int
    trial_index: int
    repetition_index: int
    is_warmup: bool
    stage: str
    timeout_policy_id: str
    operation_kind: CapacityMeasurementOperationKindV49FV8
    operation_spec: CapacityMeasurementOperationSpecV49FV8
    operation_spec_id: str
    declaration_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_OPERATION_DECLARATION_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "declaration_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_DECLARATION_BYTES_V49F

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "measurement_design_id",
            "workload_plan_id",
            "workload_sha256",
            "timeout_policy_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        object.__setattr__(
            self,
            "workload_id",
            _utf8_identifier(
                self.workload_id,
                field="workload_id",
                maximum=RAW_V8_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "stage",
            _utf8_identifier(
                self.stage,
                field="stage",
                maximum=RAW_V8_MAXIMUM_STAGE_UTF8_BYTES_V49F,
            ),
        )
        for name, minimum in (
            ("sample_sequence", 1),
            ("operation_sequence", 1),
            ("trial_index", 0),
            ("repetition_index", 0),
        ):
            object.__setattr__(
                self,
                name,
                _safe_uint(getattr(self, name), field=name, minimum=minimum),
            )
        object.__setattr__(
            self, "is_warmup", _exact_bool(self.is_warmup, field="is_warmup")
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        if type(self.operation_spec) is not CapacityMeasurementOperationSpecV49FV8:
            raise CanonicalizationError("operation_spec must be the exact V8 spec")
        object.__setattr__(
            self,
            "operation_spec_id",
            _hash(self.operation_spec_id, field="operation_spec_id"),
        )
        if (
            self.operation_spec.operation_kind is not self.operation_kind
            or self.operation_spec.operation_spec_id != self.operation_spec_id
        ):
            raise CanonicalizationError(
                "declaration operation and nested specification disagree"
            )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "campaign_manifest_id": self.campaign_manifest_id,
            "manifest_authority_id": self.manifest_authority_id,
            "measurement_design_id": self.measurement_design_id,
            "workload_plan_id": self.workload_plan_id,
            "workload_id": self.workload_id,
            "workload_sha256": self.workload_sha256,
            "sample_sequence": self.sample_sequence,
            "operation_sequence": self.operation_sequence,
            "trial_index": self.trial_index,
            "repetition_index": self.repetition_index,
            "is_warmup": self.is_warmup,
            "stage": self.stage,
            "timeout_policy_id": self.timeout_policy_id,
            "operation_kind": self.operation_kind.value,
            "operation_spec": self.operation_spec.as_dict(),
            "operation_spec_id": self.operation_spec_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationDeclarationV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            campaign_manifest_id=item["campaign_manifest_id"],
            manifest_authority_id=item["manifest_authority_id"],
            measurement_design_id=item["measurement_design_id"],
            workload_plan_id=item["workload_plan_id"],
            workload_id=item["workload_id"],
            workload_sha256=item["workload_sha256"],
            sample_sequence=item["sample_sequence"],
            operation_sequence=item["operation_sequence"],
            trial_index=item["trial_index"],
            repetition_index=item["repetition_index"],
            is_warmup=item["is_warmup"],
            stage=item["stage"],
            timeout_policy_id=item["timeout_policy_id"],
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            operation_spec=CapacityMeasurementOperationSpecV49FV8.from_mapping(
                item["operation_spec"]
            ),
            operation_spec_id=item["operation_spec_id"],
            declaration_id=item["declaration_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementDispatchWindowEvidenceV49FV8(_StandaloneRecordV49FV8):
    transport_session_id: str
    outbound_subscription_intent_id: str
    socket_lease_id: str
    monotonic_clock_domain_id: str
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    dispatch_started_monotonic_ns: str
    dispatch_completed_monotonic_ns: str
    dispatch_window_evidence_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_DISPATCH_WINDOW_EVIDENCE_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "dispatch_window_evidence_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_RESULT_BYTES_V49F

    def __post_init__(self) -> None:
        for name in (
            "transport_session_id",
            "outbound_subscription_intent_id",
            "socket_lease_id",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        started = _exact_utc(self.dispatch_started_at, field="dispatch_started_at")
        completed = _exact_utc(
            self.dispatch_completed_at, field="dispatch_completed_at"
        )
        if completed < started:
            raise CanonicalizationError("dispatch wall completion precedes start")
        object.__setattr__(self, "dispatch_started_at", started)
        object.__setattr__(self, "dispatch_completed_at", completed)
        started_ns = _uint128_text(
            self.dispatch_started_monotonic_ns,
            field="dispatch_started_monotonic_ns",
        )
        completed_ns = _uint128_text(
            self.dispatch_completed_monotonic_ns,
            field="dispatch_completed_monotonic_ns",
        )
        if int(completed_ns) <= int(started_ns):
            raise CanonicalizationError(
                "dispatch monotonic completion must strictly follow start"
            )
        object.__setattr__(self, "dispatch_started_monotonic_ns", started_ns)
        object.__setattr__(self, "dispatch_completed_monotonic_ns", completed_ns)
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "transport_session_id": self.transport_session_id,
            "outbound_subscription_intent_id": (self.outbound_subscription_intent_id),
            "socket_lease_id": self.socket_lease_id,
            "monotonic_clock_domain_id": self.monotonic_clock_domain_id,
            "dispatch_started_at": utc_iso(self.dispatch_started_at),
            "dispatch_completed_at": utc_iso(self.dispatch_completed_at),
            "dispatch_started_monotonic_ns": self.dispatch_started_monotonic_ns,
            "dispatch_completed_monotonic_ns": self.dispatch_completed_monotonic_ns,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementDispatchWindowEvidenceV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            transport_session_id=item["transport_session_id"],
            outbound_subscription_intent_id=item["outbound_subscription_intent_id"],
            socket_lease_id=item["socket_lease_id"],
            monotonic_clock_domain_id=item["monotonic_clock_domain_id"],
            dispatch_started_at=item["dispatch_started_at"],
            dispatch_completed_at=item["dispatch_completed_at"],
            dispatch_started_monotonic_ns=item["dispatch_started_monotonic_ns"],
            dispatch_completed_monotonic_ns=item["dispatch_completed_monotonic_ns"],
            dispatch_window_evidence_id=item["dispatch_window_evidence_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAckDueDecisionClockEvidenceV49FV8(_StandaloneRecordV49FV8):
    transport_session_id: str
    outbound_subscription_intent_id: str
    dispatch_window_evidence: CapacityMeasurementDispatchWindowEvidenceV49FV8
    dispatch_window_evidence_id: str
    clock_source_manifest_id: str
    monotonic_clock_domain_id: str
    wall_before_at: datetime
    sampled_at: datetime
    wall_after_at: datetime
    monotonic_before_ns: str
    monotonic_sampled_ns: str
    monotonic_after_ns: str
    uncertainty_milliseconds: int
    synchronized: bool
    valid_until: datetime
    clock_resolution_ns: int | None
    source_observation_sha256: str | None
    selectable_source_count: int | None
    chronyd_launch_id: str | None
    chronyd_runtime_observation_sha256: str | None
    committed_ack_deadline_at: datetime
    committed_ack_deadline_monotonic_ns: str
    due_scenario: CapacityMeasurementAckDueScenarioV49FV8
    due_decision_clock_evidence_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_DUE_DECISION_CLOCK_EVIDENCE_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "due_decision_clock_evidence_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_RESULT_BYTES_V49F

    def __post_init__(self) -> None:
        if (
            type(self.dispatch_window_evidence)
            is not CapacityMeasurementDispatchWindowEvidenceV49FV8
        ):
            raise CanonicalizationError(
                "dispatch_window_evidence must be an exact Raw V8 envelope"
            )
        for name in (
            "transport_session_id",
            "outbound_subscription_intent_id",
            "dispatch_window_evidence_id",
            "clock_source_manifest_id",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        if (
            self.dispatch_window_evidence.dispatch_window_evidence_id
            != self.dispatch_window_evidence_id
            or self.dispatch_window_evidence.transport_session_id
            != self.transport_session_id
            or self.dispatch_window_evidence.outbound_subscription_intent_id
            != self.outbound_subscription_intent_id
            or self.dispatch_window_evidence.monotonic_clock_domain_id
            != self.monotonic_clock_domain_id
        ):
            raise CanonicalizationError(
                "due-clock evidence differs from its dispatch-window authority"
            )
        wall_before = _exact_utc(self.wall_before_at, field="wall_before_at")
        sampled = _exact_utc(self.sampled_at, field="sampled_at")
        wall_after = _exact_utc(self.wall_after_at, field="wall_after_at")
        valid_until = _exact_utc(self.valid_until, field="valid_until")
        deadline = _exact_utc(
            self.committed_ack_deadline_at,
            field="committed_ack_deadline_at",
        )
        if not wall_before <= sampled <= wall_after:
            raise CanonicalizationError("sampled wall time lies outside its bracket")
        if valid_until < sampled:
            raise CanonicalizationError("clock evidence expires before sampling")
        if deadline <= self.dispatch_window_evidence.dispatch_completed_at:
            raise CanonicalizationError(
                "ACK wall deadline must follow dispatch completion"
            )
        for name, value in (
            ("wall_before_at", wall_before),
            ("sampled_at", sampled),
            ("wall_after_at", wall_after),
            ("valid_until", valid_until),
            ("committed_ack_deadline_at", deadline),
        ):
            object.__setattr__(self, name, value)
        monotonic_values: dict[str, str] = {}
        for name in (
            "monotonic_before_ns",
            "monotonic_sampled_ns",
            "monotonic_after_ns",
            "committed_ack_deadline_monotonic_ns",
        ):
            monotonic_values[name] = _uint128_text(getattr(self, name), field=name)
            object.__setattr__(self, name, monotonic_values[name])
        if not (
            int(monotonic_values["monotonic_before_ns"])
            <= int(monotonic_values["monotonic_sampled_ns"])
            <= int(monotonic_values["monotonic_after_ns"])
        ):
            raise CanonicalizationError(
                "sampled monotonic time lies outside its bracket"
            )
        if int(monotonic_values["committed_ack_deadline_monotonic_ns"]) <= int(
            self.dispatch_window_evidence.dispatch_completed_monotonic_ns
        ):
            raise CanonicalizationError(
                "ACK monotonic deadline must follow dispatch completion"
            )
        object.__setattr__(
            self,
            "uncertainty_milliseconds",
            _safe_uint(
                self.uncertainty_milliseconds,
                field="uncertainty_milliseconds",
                maximum=3_600_000,
            ),
        )
        if not _exact_bool(self.synchronized, field="synchronized"):
            raise CanonicalizationError("due-decision clock must be synchronized")
        object.__setattr__(
            self,
            "clock_resolution_ns",
            _optional_safe_uint(
                self.clock_resolution_ns,
                field="clock_resolution_ns",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "source_observation_sha256",
            _optional_hash(
                self.source_observation_sha256,
                field="source_observation_sha256",
            ),
        )
        object.__setattr__(
            self,
            "selectable_source_count",
            _optional_safe_uint(
                self.selectable_source_count,
                field="selectable_source_count",
                minimum=1,
                maximum=64,
            ),
        )
        chronyd_values = (
            _optional_hash(self.chronyd_launch_id, field="chronyd_launch_id"),
            _optional_hash(
                self.chronyd_runtime_observation_sha256,
                field="chronyd_runtime_observation_sha256",
            ),
        )
        if (chronyd_values[0] is None) != (chronyd_values[1] is None):
            raise CanonicalizationError(
                "chronyd launch and runtime-observation IDs must be paired"
            )
        object.__setattr__(self, "chronyd_launch_id", chronyd_values[0])
        object.__setattr__(
            self, "chronyd_runtime_observation_sha256", chronyd_values[1]
        )
        _exact_enum(
            self.due_scenario,
            CapacityMeasurementAckDueScenarioV49FV8,
            field="due_scenario",
        )
        wall_due = wall_before >= deadline
        monotonic_due = int(monotonic_values["monotonic_before_ns"]) >= int(
            monotonic_values["committed_ack_deadline_monotonic_ns"]
        )
        if self.due_scenario is CapacityMeasurementAckDueScenarioV49FV8.DUE:
            if not (wall_due and monotonic_due):
                raise CanonicalizationError(
                    "DUE requires both bracket beginnings at or after deadline"
                )
        elif wall_due and monotonic_due:
            raise CanonicalizationError(
                "NOT_DUE requires at least one bracket beginning before deadline"
            )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "transport_session_id": self.transport_session_id,
            "outbound_subscription_intent_id": (self.outbound_subscription_intent_id),
            "dispatch_window_evidence": self.dispatch_window_evidence.as_dict(),
            "dispatch_window_evidence_id": self.dispatch_window_evidence_id,
            "clock_source_manifest_id": self.clock_source_manifest_id,
            "monotonic_clock_domain_id": self.monotonic_clock_domain_id,
            "wall_before_at": utc_iso(self.wall_before_at),
            "sampled_at": utc_iso(self.sampled_at),
            "wall_after_at": utc_iso(self.wall_after_at),
            "monotonic_before_ns": self.monotonic_before_ns,
            "monotonic_sampled_ns": self.monotonic_sampled_ns,
            "monotonic_after_ns": self.monotonic_after_ns,
            "uncertainty_milliseconds": self.uncertainty_milliseconds,
            "synchronized": self.synchronized,
            "valid_until": utc_iso(self.valid_until),
            "clock_resolution_ns": self.clock_resolution_ns,
            "source_observation_sha256": self.source_observation_sha256,
            "selectable_source_count": self.selectable_source_count,
            "chronyd_launch_id": self.chronyd_launch_id,
            "chronyd_runtime_observation_sha256": (
                self.chronyd_runtime_observation_sha256
            ),
            "committed_ack_deadline_at": utc_iso(self.committed_ack_deadline_at),
            "committed_ack_deadline_monotonic_ns": (
                self.committed_ack_deadline_monotonic_ns
            ),
            "due_scenario": self.due_scenario.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAckDueDecisionClockEvidenceV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        values = {name: item[name] for name in (field.name for field in fields(cls))}
        values["dispatch_window_evidence"] = (
            CapacityMeasurementDispatchWindowEvidenceV49FV8.from_mapping(
                item["dispatch_window_evidence"]
            )
        )
        values["due_scenario"] = _enum_from_json(
            item["due_scenario"],
            CapacityMeasurementAckDueScenarioV49FV8,
            field="due_scenario",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressResultEvidenceV49FV8(_NestedRecordV49FV8):
    ingress_progress_evidence_id: str
    final_parser_cursor_id: str
    final_retained_tail_id: str
    final_retained_tail_octets: int
    final_retained_tail_sha256: str
    sealed_pending_input_id: str
    ingress_oracle_baseline_id: str
    observed_consumed_new_input_octets: int
    observed_parser_unit_count: int
    observed_completed_application_message_count: int
    observed_logical_output_frame_count: int
    observed_logical_output_payload_octets: int
    observed_logical_output_frames_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "ingress_progress_evidence_id",
            "final_parser_cursor_id",
            "final_retained_tail_id",
            "final_retained_tail_sha256",
            "sealed_pending_input_id",
            "ingress_oracle_baseline_id",
            "observed_logical_output_frames_sha256",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        integer_bounds = {
            "final_retained_tail_octets": RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
            "observed_consumed_new_input_octets": RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
            "observed_parser_unit_count": RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F,
            "observed_completed_application_message_count": (
                RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F
            ),
            "observed_logical_output_frame_count": (
                RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F
            ),
            "observed_logical_output_payload_octets": (
                RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F
            ),
        }
        for name, maximum in integer_bounds.items():
            object.__setattr__(
                self,
                name,
                _safe_uint(getattr(self, name), field=name, maximum=maximum),
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "ingress_progress_evidence_id": self.ingress_progress_evidence_id,
            "final_parser_cursor_id": self.final_parser_cursor_id,
            "final_retained_tail_id": self.final_retained_tail_id,
            "final_retained_tail_octets": self.final_retained_tail_octets,
            "final_retained_tail_sha256": self.final_retained_tail_sha256,
            "sealed_pending_input_id": self.sealed_pending_input_id,
            "ingress_oracle_baseline_id": self.ingress_oracle_baseline_id,
            "observed_consumed_new_input_octets": (
                self.observed_consumed_new_input_octets
            ),
            "observed_parser_unit_count": self.observed_parser_unit_count,
            "observed_completed_application_message_count": (
                self.observed_completed_application_message_count
            ),
            "observed_logical_output_frame_count": (
                self.observed_logical_output_frame_count
            ),
            "observed_logical_output_payload_octets": (
                self.observed_logical_output_payload_octets
            ),
            "observed_logical_output_frames_sha256": (
                self.observed_logical_output_frames_sha256
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIngressResultEvidenceV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(**item)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8(_NestedRecordV49FV8):
    outbound_subscription_intent_id: str
    generated_request_id: str
    generated_request_command_sha256: str
    generated_logical_opcode: str
    generated_logical_payload_sha256: str
    generated_logical_payload_octets: int
    dispatch_window_evidence: CapacityMeasurementDispatchWindowEvidenceV49FV8
    dispatch_window_evidence_id: str
    outbound_wire_prepared_event_id: str
    tls_ciphertext_prepared_event_id: str
    ordered_kernel_attempt_event_ids: tuple[str, ...]
    ordered_kernel_result_event_ids: tuple[str, ...]
    outbound_dispatch_completed_event_id: str
    submitted_ciphertext_octets: int
    local_dispatch_disposition: CapacityMeasurementDispatchDispositionV49FV8

    def __post_init__(self) -> None:
        if (
            type(self.dispatch_window_evidence)
            is not CapacityMeasurementDispatchWindowEvidenceV49FV8
        ):
            raise CanonicalizationError(
                "subscription result requires an exact dispatch-window envelope"
            )
        for name in (
            "outbound_subscription_intent_id",
            "generated_request_command_sha256",
            "generated_logical_payload_sha256",
            "dispatch_window_evidence_id",
            "outbound_wire_prepared_event_id",
            "tls_ciphertext_prepared_event_id",
            "outbound_dispatch_completed_event_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        object.__setattr__(
            self,
            "generated_request_id",
            _ascii_text(
                self.generated_request_id,
                field="generated_request_id",
                minimum=1,
                maximum=36,
                pattern=_REQUEST_ID_RE,
            ),
        )
        if type(self.generated_logical_opcode) is not str or (
            self.generated_logical_opcode != "TEXT"
        ):
            raise CanonicalizationError("generated_logical_opcode must be exact TEXT")
        object.__setattr__(
            self,
            "generated_logical_payload_octets",
            _safe_uint(
                self.generated_logical_payload_octets,
                field="generated_logical_payload_octets",
                minimum=1,
                maximum=RAW_V8_MAXIMUM_INPUT_OCTETS_V49F,
            ),
        )
        if (
            self.generated_request_command_sha256
            != self.generated_logical_payload_sha256
        ):
            raise CanonicalizationError(
                "generated request-command and logical-payload digests differ"
            )
        if (
            self.dispatch_window_evidence.dispatch_window_evidence_id
            != self.dispatch_window_evidence_id
            or self.dispatch_window_evidence.outbound_subscription_intent_id
            != self.outbound_subscription_intent_id
        ):
            raise CanonicalizationError(
                "subscription result differs from dispatch-window evidence"
            )
        attempts = _exact_tuple(
            self.ordered_kernel_attempt_event_ids,
            field="ordered_kernel_attempt_event_ids",
        )
        results = _exact_tuple(
            self.ordered_kernel_result_event_ids,
            field="ordered_kernel_result_event_ids",
        )
        if not (
            1 <= len(attempts) == len(results) <= RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F
        ):
            raise CanonicalizationError(
                "subscription kernel attempt/result cardinality is invalid"
            )
        normalized_attempts = tuple(
            _hash(value, field="ordered_kernel_attempt_event_ids") for value in attempts
        )
        normalized_results = tuple(
            _hash(value, field="ordered_kernel_result_event_ids") for value in results
        )
        if len(set(normalized_attempts)) != len(normalized_attempts) or len(
            set(normalized_results)
        ) != len(normalized_results):
            raise CanonicalizationError(
                "subscription kernel IDs must be unique within each tuple"
            )
        object.__setattr__(
            self, "ordered_kernel_attempt_event_ids", normalized_attempts
        )
        object.__setattr__(self, "ordered_kernel_result_event_ids", normalized_results)
        object.__setattr__(
            self,
            "submitted_ciphertext_octets",
            _safe_uint(
                self.submitted_ciphertext_octets,
                field="submitted_ciphertext_octets",
                minimum=1,
                maximum=RAW_V8_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
            ),
        )
        _exact_enum(
            self.local_dispatch_disposition,
            CapacityMeasurementDispatchDispositionV49FV8,
            field="local_dispatch_disposition",
        )
        if (
            self.local_dispatch_disposition
            is not CapacityMeasurementDispatchDispositionV49FV8.COMPLETE_LOCAL_SUBMISSION
        ):
            raise CanonicalizationError(
                "returned subscription evidence must be COMPLETE_LOCAL_SUBMISSION"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "outbound_subscription_intent_id": self.outbound_subscription_intent_id,
            "generated_request_id": self.generated_request_id,
            "generated_request_command_sha256": (self.generated_request_command_sha256),
            "generated_logical_opcode": self.generated_logical_opcode,
            "generated_logical_payload_sha256": (self.generated_logical_payload_sha256),
            "generated_logical_payload_octets": (self.generated_logical_payload_octets),
            "dispatch_window_evidence": self.dispatch_window_evidence.as_dict(),
            "dispatch_window_evidence_id": self.dispatch_window_evidence_id,
            "outbound_wire_prepared_event_id": self.outbound_wire_prepared_event_id,
            "tls_ciphertext_prepared_event_id": self.tls_ciphertext_prepared_event_id,
            "ordered_kernel_attempt_event_ids": list(
                self.ordered_kernel_attempt_event_ids
            ),
            "ordered_kernel_result_event_ids": list(
                self.ordered_kernel_result_event_ids
            ),
            "outbound_dispatch_completed_event_id": (
                self.outbound_dispatch_completed_event_id
            ),
            "submitted_ciphertext_octets": self.submitted_ciphertext_octets,
            "local_dispatch_disposition": self.local_dispatch_disposition.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["dispatch_window_evidence"] = (
            CapacityMeasurementDispatchWindowEvidenceV49FV8.from_mapping(
                item["dispatch_window_evidence"]
            )
        )
        for name in (
            "ordered_kernel_attempt_event_ids",
            "ordered_kernel_result_event_ids",
        ):
            values[name] = tuple(
                _exact_json_list(
                    item[name],
                    field=name,
                    maximum=RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F,
                )
            )
        values["local_dispatch_disposition"] = _enum_from_json(
            item["local_dispatch_disposition"],
            CapacityMeasurementDispatchDispositionV49FV8,
            field="local_dispatch_disposition",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8(_NestedRecordV49FV8):
    expired: bool
    due_decision_clock_evidence: CapacityMeasurementAckDueDecisionClockEvidenceV49FV8
    due_decision_clock_evidence_id: str
    ack_deadline_expired_event_id: str | None
    terminal_transition_event_id: str | None
    transport_session_termination_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "expired", _exact_bool(self.expired, field="expired"))
        if (
            type(self.due_decision_clock_evidence)
            is not CapacityMeasurementAckDueDecisionClockEvidenceV49FV8
        ):
            raise CanonicalizationError(
                "ACK result requires exact due-decision clock evidence"
            )
        object.__setattr__(
            self,
            "due_decision_clock_evidence_id",
            _hash(
                self.due_decision_clock_evidence_id,
                field="due_decision_clock_evidence_id",
            ),
        )
        if (
            self.due_decision_clock_evidence.due_decision_clock_evidence_id
            != self.due_decision_clock_evidence_id
        ):
            raise CanonicalizationError("ACK result duplicates the wrong clock ID")
        optional_ids = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in (
                "ack_deadline_expired_event_id",
                "terminal_transition_event_id",
                "transport_session_termination_id",
            )
        )
        for name, value in zip(
            (
                "ack_deadline_expired_event_id",
                "terminal_transition_event_id",
                "transport_session_termination_id",
            ),
            optional_ids,
        ):
            object.__setattr__(self, name, value)
        if self.expired:
            if (
                any(value is None for value in optional_ids)
                or len(set(optional_ids)) != 3
            ):
                raise CanonicalizationError(
                    "expired ACK requires three distinct terminal identities"
                )
        elif any(value is not None for value in optional_ids):
            raise CanonicalizationError(
                "not-due ACK result must not contain terminal identities"
            )
        due = (
            self.due_decision_clock_evidence.due_scenario
            is CapacityMeasurementAckDueScenarioV49FV8.DUE
        )
        if self.expired != due:
            raise CanonicalizationError("ACK result disagrees with due-clock scenario")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "expired": self.expired,
            "due_decision_clock_evidence": self.due_decision_clock_evidence.as_dict(),
            "due_decision_clock_evidence_id": self.due_decision_clock_evidence_id,
            "ack_deadline_expired_event_id": self.ack_deadline_expired_event_id,
            "terminal_transition_event_id": self.terminal_transition_event_id,
            "transport_session_termination_id": (self.transport_session_termination_id),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["due_decision_clock_evidence"] = (
            CapacityMeasurementAckDueDecisionClockEvidenceV49FV8.from_mapping(
                item["due_decision_clock_evidence"]
            )
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class _HistoricalCapacityMeasurementLocalShutdownResultEvidenceV1V49FV8(
    _NestedRecordV49FV8
):
    local_shutdown_started_event_id: str
    local_shutdown_deadline_evidence_event_id: str | None
    local_close_dispatch_completion_event_id: str | None
    tls_control_terminal_event_ids: tuple[str, ...]
    tcp_half_close_result_event_id: str | None
    tls_shutdown_observed_event_id: str | None
    terminal_transition_event_id: str
    transport_session_termination_id: str
    terminal_outcome: CapacityMeasurementTerminalOutcomeV49FV8

    def __post_init__(self) -> None:
        for name in (
            "local_shutdown_started_event_id",
            "terminal_transition_event_id",
            "transport_session_termination_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        for name in (
            "local_shutdown_deadline_evidence_event_id",
            "local_close_dispatch_completion_event_id",
            "tcp_half_close_result_event_id",
            "tls_shutdown_observed_event_id",
        ):
            object.__setattr__(
                self, name, _optional_hash(getattr(self, name), field=name)
            )
        tls_ids = _exact_tuple(
            self.tls_control_terminal_event_ids,
            field="tls_control_terminal_event_ids",
        )
        if len(tls_ids) > RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F:
            raise CanonicalizationError("TLS-control terminal tuple exceeds 256")
        normalized_tls_ids = tuple(
            _hash(value, field="tls_control_terminal_event_ids") for value in tls_ids
        )
        if len(set(normalized_tls_ids)) != len(normalized_tls_ids):
            raise CanonicalizationError("TLS-control terminal IDs must be unique")
        object.__setattr__(self, "tls_control_terminal_event_ids", normalized_tls_ids)
        if self.local_close_dispatch_completion_event_id is None and (
            normalized_tls_ids
            or self.tcp_half_close_result_event_id is not None
            or self.tls_shutdown_observed_event_id is not None
        ):
            raise CanonicalizationError(
                "shutdown evidence exists beyond an absent local Close completion"
            )
        if not normalized_tls_ids and (
            self.tcp_half_close_result_event_id is not None
            or self.tls_shutdown_observed_event_id is not None
        ):
            raise CanonicalizationError(
                "shutdown half-close evidence requires TLS-control convergence"
            )
        if (
            self.tls_shutdown_observed_event_id is not None
            and self.tcp_half_close_result_event_id is None
        ):
            raise CanonicalizationError(
                "TLS shutdown observation requires TCP half-close result"
            )
        all_ids = (
            self.local_shutdown_started_event_id,
            self.local_shutdown_deadline_evidence_event_id,
            self.local_close_dispatch_completion_event_id,
            *normalized_tls_ids,
            self.tcp_half_close_result_event_id,
            self.tls_shutdown_observed_event_id,
            self.terminal_transition_event_id,
            self.transport_session_termination_id,
        )
        present_ids = tuple(value for value in all_ids if value is not None)
        if len(set(present_ids)) != len(present_ids):
            raise CanonicalizationError("shutdown result identities must be distinct")
        _exact_enum(
            self.terminal_outcome,
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="terminal_outcome",
        )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "local_shutdown_started_event_id": self.local_shutdown_started_event_id,
            "local_shutdown_deadline_evidence_event_id": (
                self.local_shutdown_deadline_evidence_event_id
            ),
            "local_close_dispatch_completion_event_id": (
                self.local_close_dispatch_completion_event_id
            ),
            "tls_control_terminal_event_ids": list(self.tls_control_terminal_event_ids),
            "tcp_half_close_result_event_id": self.tcp_half_close_result_event_id,
            "tls_shutdown_observed_event_id": self.tls_shutdown_observed_event_id,
            "terminal_transition_event_id": self.terminal_transition_event_id,
            "transport_session_termination_id": (self.transport_session_termination_id),
            "terminal_outcome": self.terminal_outcome.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLocalShutdownResultEvidenceV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["tls_control_terminal_event_ids"] = tuple(
            _exact_json_list(
                item["tls_control_terminal_event_ids"],
                field="tls_control_terminal_event_ids",
                maximum=RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F,
            )
        )
        values["terminal_outcome"] = _enum_from_json(
            item["terminal_outcome"],
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="terminal_outcome",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLocalShutdownResultEvidenceV49FV8(_NestedRecordV49FV8):
    local_shutdown_started_event_id: str
    local_shutdown_deadline_evidence_event_id: str | None
    local_close_dispatch_completion_event_id: str | None
    ordered_terminal_ingress_read_attempt_event_ids: tuple[str, ...]
    ordered_terminal_ingress_read_result_event_ids: tuple[str, ...]
    ordered_terminal_raw_ingress_commit_ids: tuple[str, ...]
    ordered_terminal_raw_ingress_actor_event_ids: tuple[str, ...]
    ordered_terminal_parser_transition_event_ids: tuple[str, ...]
    websocket_close_received_transition_event_id: str | None
    shutdown_trace_step_count: int
    shutdown_trace_root_sha256: str
    final_terminal_ingress_batch_count: int
    final_terminal_ingress_ciphertext_octets: int
    final_terminal_ingress_plaintext_octets: int
    final_terminal_socket_receive_call_count: int
    final_terminal_tls_record_count: int
    final_terminal_tls_unwrap_iteration_count: int
    final_terminal_zero_progress_iteration_count: int
    final_terminal_ingress_parser_unit_count: int
    final_terminal_ingress_automatic_output_count: int
    final_websocket_send_attempt_count: int
    final_tls_control_send_attempt_count: int
    final_peer_shutdown_poll_count: int
    final_terminal_tls_staging_state_id: str
    decisive_terminal_transition_event_id: str
    transport_session_termination_id: str
    terminal_outcome: CapacityMeasurementTerminalOutcomeV49FV8

    def __post_init__(self) -> None:
        for name in (
            "local_shutdown_started_event_id",
            "shutdown_trace_root_sha256",
            "final_terminal_tls_staging_state_id",
            "decisive_terminal_transition_event_id",
            "transport_session_termination_id",
        ):
            object.__setattr__(self, name, _hash(getattr(self, name), field=name))
        for name in (
            "local_shutdown_deadline_evidence_event_id",
            "local_close_dispatch_completion_event_id",
            "websocket_close_received_transition_event_id",
        ):
            object.__setattr__(
                self,
                name,
                _optional_hash(getattr(self, name), field=name),
            )
        tuple_names = (
            "ordered_terminal_ingress_read_attempt_event_ids",
            "ordered_terminal_ingress_read_result_event_ids",
            "ordered_terminal_raw_ingress_commit_ids",
            "ordered_terminal_raw_ingress_actor_event_ids",
            "ordered_terminal_parser_transition_event_ids",
        )
        normalized: dict[str, tuple[str, ...]] = {}
        for name in tuple_names:
            values = _exact_tuple(getattr(self, name), field=name)
            if len(values) > RAW_V8_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F:
                raise CanonicalizationError(f"{name} exceeds the structural bound")
            ids = tuple(_hash(value, field=name) for value in values)
            if len(set(ids)) != len(ids):
                raise CanonicalizationError(f"{name} must be internally unique")
            normalized[name] = ids
            object.__setattr__(self, name, ids)
        attempts = normalized["ordered_terminal_ingress_read_attempt_event_ids"]
        results = normalized["ordered_terminal_ingress_read_result_event_ids"]
        raw_commits = normalized["ordered_terminal_raw_ingress_commit_ids"]
        raw_actors = normalized["ordered_terminal_raw_ingress_actor_event_ids"]
        parser_transitions = normalized["ordered_terminal_parser_transition_event_ids"]
        if len(attempts) != len(results):
            raise CanonicalizationError(
                "terminal ingress attempt/result cardinalities differ"
            )
        if len(raw_commits) != len(raw_actors) or len(raw_commits) > len(results):
            raise CanonicalizationError(
                "terminal RAW lineage cardinalities are inconsistent"
            )
        if len(parser_transitions) > 4_096:
            raise CanonicalizationError(
                "terminal parser transitions exceed the schema limit"
            )
        counter_names = (
            "shutdown_trace_step_count",
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
        )
        for name in counter_names:
            object.__setattr__(
                self,
                name,
                _safe_uint(getattr(self, name), field=name),
            )
        if self.final_terminal_ingress_batch_count != len(attempts):
            raise CanonicalizationError(
                "final terminal batch count differs from read evidence"
            )
        if self.final_terminal_ingress_parser_unit_count < len(parser_transitions):
            raise CanonicalizationError(
                "terminal parser transition count exceeds final parser-unit count"
            )
        if self.final_peer_shutdown_poll_count > 2:
            raise CanonicalizationError("final peer-shutdown polls exceed two")
        _exact_enum(
            self.terminal_outcome,
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="terminal_outcome",
        )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "local_shutdown_started_event_id": self.local_shutdown_started_event_id,
            "local_shutdown_deadline_evidence_event_id": (
                self.local_shutdown_deadline_evidence_event_id
            ),
            "local_close_dispatch_completion_event_id": (
                self.local_close_dispatch_completion_event_id
            ),
            "ordered_terminal_ingress_read_attempt_event_ids": list(
                self.ordered_terminal_ingress_read_attempt_event_ids
            ),
            "ordered_terminal_ingress_read_result_event_ids": list(
                self.ordered_terminal_ingress_read_result_event_ids
            ),
            "ordered_terminal_raw_ingress_commit_ids": list(
                self.ordered_terminal_raw_ingress_commit_ids
            ),
            "ordered_terminal_raw_ingress_actor_event_ids": list(
                self.ordered_terminal_raw_ingress_actor_event_ids
            ),
            "ordered_terminal_parser_transition_event_ids": list(
                self.ordered_terminal_parser_transition_event_ids
            ),
            "websocket_close_received_transition_event_id": (
                self.websocket_close_received_transition_event_id
            ),
            "shutdown_trace_step_count": self.shutdown_trace_step_count,
            "shutdown_trace_root_sha256": self.shutdown_trace_root_sha256,
            "final_terminal_ingress_batch_count": (
                self.final_terminal_ingress_batch_count
            ),
            "final_terminal_ingress_ciphertext_octets": (
                self.final_terminal_ingress_ciphertext_octets
            ),
            "final_terminal_ingress_plaintext_octets": (
                self.final_terminal_ingress_plaintext_octets
            ),
            "final_terminal_socket_receive_call_count": (
                self.final_terminal_socket_receive_call_count
            ),
            "final_terminal_tls_record_count": self.final_terminal_tls_record_count,
            "final_terminal_tls_unwrap_iteration_count": (
                self.final_terminal_tls_unwrap_iteration_count
            ),
            "final_terminal_zero_progress_iteration_count": (
                self.final_terminal_zero_progress_iteration_count
            ),
            "final_terminal_ingress_parser_unit_count": (
                self.final_terminal_ingress_parser_unit_count
            ),
            "final_terminal_ingress_automatic_output_count": (
                self.final_terminal_ingress_automatic_output_count
            ),
            "final_websocket_send_attempt_count": (
                self.final_websocket_send_attempt_count
            ),
            "final_tls_control_send_attempt_count": (
                self.final_tls_control_send_attempt_count
            ),
            "final_peer_shutdown_poll_count": self.final_peer_shutdown_poll_count,
            "final_terminal_tls_staging_state_id": (
                self.final_terminal_tls_staging_state_id
            ),
            "decisive_terminal_transition_event_id": (
                self.decisive_terminal_transition_event_id
            ),
            "transport_session_termination_id": (self.transport_session_termination_id),
            "terminal_outcome": self.terminal_outcome.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLocalShutdownResultEvidenceV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        for name in (
            "ordered_terminal_ingress_read_attempt_event_ids",
            "ordered_terminal_ingress_read_result_event_ids",
            "ordered_terminal_raw_ingress_commit_ids",
            "ordered_terminal_raw_ingress_actor_event_ids",
            "ordered_terminal_parser_transition_event_ids",
        ):
            values[name] = tuple(
                _exact_json_list(
                    item[name],
                    field=name,
                    maximum=RAW_V8_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F,
                )
            )
        values["terminal_outcome"] = _enum_from_json(
            item["terminal_outcome"],
            CapacityMeasurementTerminalOutcomeV49FV8,
            field="terminal_outcome",
        )
        return cls(**values)


_OperationResultBodyV49FV8 = (
    CapacityMeasurementIngressResultEvidenceV49FV8
    | CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8
    | CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8
    | CapacityMeasurementLocalShutdownResultEvidenceV49FV8
)

_RESULT_TAG_MATRIX_V49FV8: dict[
    CapacityMeasurementOperationKindV49FV8,
    tuple[CapacityMeasurementOperationResultTypeV49FV8, type[Any]],
] = {
    CapacityMeasurementOperationKindV49FV8.INGRESS: (
        CapacityMeasurementOperationResultTypeV49FV8.INGRESS_RESULT_EVIDENCE_V2,
        CapacityMeasurementIngressResultEvidenceV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.SUBSCRIPTION_DISPATCH: (
        CapacityMeasurementOperationResultTypeV49FV8.SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2,
        CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY: (
        CapacityMeasurementOperationResultTypeV49FV8.ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1,
        CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8,
    ),
    CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN: (
        CapacityMeasurementOperationResultTypeV49FV8.LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2,
        CapacityMeasurementLocalShutdownResultEvidenceV49FV8,
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationResultEvidenceV49FV8(_StandaloneRecordV49FV8):
    candidate_id: str
    attempt_id: str
    operation_kind: CapacityMeasurementOperationKindV49FV8
    result_type: CapacityMeasurementOperationResultTypeV49FV8
    result: _OperationResultBodyV49FV8
    result_evidence_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_OPERATION_RESULT_EVIDENCE_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "result_evidence_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OPERATION_RESULT_BYTES_V49F
    _MAXIMUM_BYTES_IS_EXCLUSIVE: ClassVar[bool] = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _hash(self.candidate_id, field="candidate_id")
        )
        object.__setattr__(
            self, "attempt_id", _hash(self.attempt_id, field="attempt_id")
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.result_type,
            CapacityMeasurementOperationResultTypeV49FV8,
            field="result_type",
        )
        expected_tag, expected_type = _RESULT_TAG_MATRIX_V49FV8[self.operation_kind]
        if (
            self.result_type is not expected_tag
            or type(self.result) is not expected_type
        ):
            raise CanonicalizationError("operation kind, result tag, and body disagree")
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "operation_kind": self.operation_kind.value,
            "result_type": self.result_type.value,
            "result": self.result.as_dict(),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationResultEvidenceV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        operation_kind = _enum_from_json(
            item["operation_kind"],
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        result_type = _enum_from_json(
            item["result_type"],
            CapacityMeasurementOperationResultTypeV49FV8,
            field="result_type",
        )
        _, body_type = _RESULT_TAG_MATRIX_V49FV8[operation_kind]
        return cls(
            candidate_id=item["candidate_id"],
            attempt_id=item["attempt_id"],
            operation_kind=operation_kind,
            result_type=result_type,
            result=body_type.from_mapping(item["result"]),
            result_evidence_id=item["result_evidence_id"],
        )


def validate_capacity_measurement_result_against_spec_v49f_v8(
    *,
    result: CapacityMeasurementOperationResultEvidenceV49FV8,
    spec: CapacityMeasurementOperationSpecV49FV8,
) -> None:
    """Validate the exact cross-record result expectations without runtime imports."""

    if (
        type(result) is not CapacityMeasurementOperationResultEvidenceV49FV8
        or type(spec) is not CapacityMeasurementOperationSpecV49FV8
    ):
        raise CanonicalizationError("result and operation spec are incompatible")
    # Reconstruct both complete records before consulting any member.  Frozen
    # dataclasses can still be forged with ``object.__setattr__``; cross-record
    # validation must therefore never trust an already-constructed instance.
    result = result._revalidated()
    spec = spec._revalidated()
    if result.operation_kind is not spec.operation_kind:
        raise CanonicalizationError("result and operation spec are incompatible")
    if (
        result.operation_kind
        is CapacityMeasurementOperationKindV49FV8.SUBSCRIPTION_DISPATCH
    ):
        result_body = result.result
        spec_body = spec.spec
        if (
            type(result_body)
            is not CapacityMeasurementSubscriptionDispatchResultEvidenceV49FV8
            or type(spec_body) is not CapacityMeasurementSubscriptionDispatchSpecV49FV8
        ):
            raise CanonicalizationError(
                "subscription result and operation spec bodies are incompatible"
            )
        if (
            result_body.generated_logical_opcode != spec_body.expected_logical_opcode
            or result_body.local_dispatch_disposition
            is not spec_body.expected_dispatch_disposition
        ):
            raise CanonicalizationError("subscription result differs from its spec")
    elif result.operation_kind is CapacityMeasurementOperationKindV49FV8.INGRESS:
        result_body = result.result
        spec_body = spec.spec
        if (
            type(result_body) is not CapacityMeasurementIngressResultEvidenceV49FV8
            or type(spec_body) is not CapacityMeasurementIngressOperationSpecV49FV8
        ):
            raise CanonicalizationError(
                "ingress result and operation spec bodies are incompatible"
            )
        expected_equalities = (
            (
                result_body.observed_consumed_new_input_octets,
                spec_body.input_octet_count,
            ),
            (
                result_body.observed_parser_unit_count,
                spec_body.expected_parser_unit_count,
            ),
            (
                result_body.observed_completed_application_message_count,
                spec_body.expected_completed_application_message_count,
            ),
            (
                result_body.observed_logical_output_frame_count,
                spec_body.expected_logical_output_frame_count,
            ),
            (
                result_body.observed_logical_output_payload_octets,
                spec_body.expected_logical_output_payload_octets,
            ),
            (
                result_body.observed_logical_output_frames_sha256,
                spec_body.expected_logical_output_frames_sha256,
            ),
        )
        if any(observed != expected for observed, expected in expected_equalities):
            raise CanonicalizationError("ingress result differs from its spec")
    elif (
        result.operation_kind
        is CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY
    ):
        result_body = result.result
        spec_body = spec.spec
        if (
            type(result_body)
            is not CapacityMeasurementAckDeadlineExpiryResultEvidenceV49FV8
            or type(spec_body) is not CapacityMeasurementAckDeadlineExpirySpecV49FV8
        ):
            raise CanonicalizationError(
                "ACK result and operation spec bodies are incompatible"
            )
        if (
            result_body.due_decision_clock_evidence.outbound_subscription_intent_id
            != spec_body.expected_outbound_subscription_intent_id
            or result_body.due_decision_clock_evidence.due_scenario
            is not spec_body.due_scenario
        ):
            raise CanonicalizationError("ACK result differs from its spec")
    elif result.operation_kind is CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN:
        result_body = result.result
        spec_body = spec.spec
        if (
            type(result_body)
            is not CapacityMeasurementLocalShutdownResultEvidenceV49FV8
            or type(spec_body) is not CapacityMeasurementLocalShutdownSpecV49FV8
        ):
            raise CanonicalizationError(
                "shutdown result and operation spec bodies are incompatible"
            )
        if result_body.terminal_outcome is not spec_body.expected_terminal_outcome:
            raise CanonicalizationError("shutdown result differs from its spec")
        counter_limit_pairs = (
            (
                result_body.final_terminal_ingress_batch_count,
                spec_body.maximum_terminal_ingress_batches,
            ),
            (
                result_body.final_terminal_ingress_ciphertext_octets,
                spec_body.maximum_terminal_ingress_ciphertext_octets,
            ),
            (
                result_body.final_terminal_ingress_plaintext_octets,
                spec_body.maximum_terminal_ingress_plaintext_octets,
            ),
            (
                result_body.final_terminal_socket_receive_call_count,
                spec_body.maximum_terminal_socket_receive_calls,
            ),
            (
                result_body.final_terminal_tls_record_count,
                spec_body.maximum_terminal_tls_records,
            ),
            (
                result_body.final_terminal_tls_unwrap_iteration_count,
                spec_body.maximum_terminal_tls_unwrap_iterations,
            ),
            (
                result_body.final_terminal_zero_progress_iteration_count,
                spec_body.maximum_terminal_zero_progress_iterations,
            ),
            (
                result_body.final_terminal_ingress_parser_unit_count,
                spec_body.maximum_terminal_ingress_parser_units,
            ),
            (
                result_body.final_terminal_ingress_automatic_output_count,
                spec_body.maximum_terminal_ingress_automatic_outputs,
            ),
            (
                result_body.final_websocket_send_attempt_count,
                spec_body.maximum_websocket_send_attempts,
            ),
            (
                result_body.final_tls_control_send_attempt_count,
                spec_body.maximum_tls_control_send_attempts,
            ),
            (
                result_body.final_peer_shutdown_poll_count,
                spec_body.maximum_peer_shutdown_polls,
            ),
        )
        if any(value > limit for value, limit in counter_limit_pairs):
            raise CanonicalizationError("shutdown result exceeds its signed spec limit")
        if (
            len(result_body.ordered_terminal_ingress_read_attempt_event_ids)
            > spec_body.maximum_terminal_ingress_batches
            or len(result_body.ordered_terminal_parser_transition_event_ids)
            > spec_body.maximum_terminal_ingress_parser_units
        ):
            raise CanonicalizationError(
                "shutdown result evidence exceeds its signed spec limit"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementObservationMethodRolePairV49FV8(_NestedRecordV49FV8):
    observation_method: CapacityMeasurementTargetObservationMethodV49FV8
    allowed_roles: tuple[CapacityMeasurementObservationRoleV49FV8, ...]

    def __post_init__(self) -> None:
        _exact_enum(
            self.observation_method,
            CapacityMeasurementTargetObservationMethodV49FV8,
            field="observation_method",
        )
        roles = _exact_tuple(self.allowed_roles, field="allowed_roles")
        if (
            not roles
            or any(
                type(role) is not CapacityMeasurementObservationRoleV49FV8
                for role in roles
            )
            or roles != tuple(sorted(roles, key=lambda role: role.value))
            or len(set(roles)) != len(roles)
        ):
            raise CanonicalizationError(
                "allowed_roles must be a nonempty sorted exact role tuple"
            )
        if (
            self.observation_method
            is CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
        ):
            raise CanonicalizationError(
                "NOT_ATTEMPTED is a sentinel, not a descriptor method"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "observation_method": self.observation_method.value,
            "allowed_roles": [role.value for role in self.allowed_roles],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementObservationMethodRolePairV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"observation_method", "allowed_roles"}),
            context=cls.__name__,
        )
        return cls(
            observation_method=_enum_from_json(
                item["observation_method"],
                CapacityMeasurementTargetObservationMethodV49FV8,
                field="observation_method",
            ),
            allowed_roles=tuple(
                _enum_from_json(
                    role,
                    CapacityMeasurementObservationRoleV49FV8,
                    field="allowed_roles",
                )
                for role in _exact_json_list(
                    item["allowed_roles"], field="allowed_roles", maximum=5
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementVocabularyDefinitionV49FV8(_NestedRecordV49FV8):
    vocabulary_id: str
    members: tuple[str, ...]

    def __post_init__(self) -> None:
        _ascii_text(
            self.vocabulary_id,
            field="vocabulary_id",
            minimum=1,
            maximum=128,
        )
        members = _exact_string_tuple(self.members, field="members", sorted_values=True)
        if not members or len(members) > 512:
            raise CanonicalizationError(
                "vocabulary members must contain between 1 and 512 values"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"vocabulary_id": self.vocabulary_id, "members": list(self.members)}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementVocabularyDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"vocabulary_id", "members"}),
            context=cls.__name__,
        )
        return cls(
            vocabulary_id=item["vocabulary_id"],
            members=tuple(
                _exact_json_list(item["members"], field="members", maximum=512)
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementValueShapeDefinitionV49FV8(_NestedRecordV49FV8):
    value_shape_id: str
    container_kind: str
    minimum_items: int | None
    maximum_items: int | None
    ordered_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _ascii_text(
            self.value_shape_id,
            field="value_shape_id",
            minimum=1,
            maximum=128,
        )
        if type(self.container_kind) is not str or self.container_kind not in {
            "SCALAR",
            "LIST",
            "FIXED_MAP",
        }:
            raise CanonicalizationError("container_kind is unsupported")
        minimum = _optional_safe_uint(self.minimum_items, field="minimum_items")
        maximum = _optional_safe_uint(self.maximum_items, field="maximum_items")
        if (minimum is None) != (maximum is None) or (
            minimum is not None and maximum is not None and minimum > maximum
        ):
            raise CanonicalizationError("shape item bounds are inconsistent")
        keys = _exact_string_tuple(
            self.ordered_keys, field="ordered_keys", sorted_values=True
        )
        if len(keys) > 512:
            raise CanonicalizationError("shape ordered_keys exceeds 512 values")
        if self.container_kind == "SCALAR":
            if minimum is not None or keys:
                raise CanonicalizationError("scalar shapes cannot have bounds or keys")
        elif self.container_kind == "LIST":
            if minimum is None or keys:
                raise CanonicalizationError("list shapes require bounds and no keys")
        elif minimum != maximum or minimum != len(keys):
            raise CanonicalizationError(
                "fixed-map shapes require exact bounds matching their key tuple"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "value_shape_id": self.value_shape_id,
            "container_kind": self.container_kind,
            "minimum_items": self.minimum_items,
            "maximum_items": self.maximum_items,
            "ordered_keys": list(self.ordered_keys),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementValueShapeDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            value_shape_id=item["value_shape_id"],
            container_kind=item["container_kind"],
            minimum_items=item["minimum_items"],
            maximum_items=item["maximum_items"],
            ordered_keys=tuple(
                _exact_json_list(
                    item["ordered_keys"], field="ordered_keys", maximum=512
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementValueConstraintDefinitionV49FV8(_NestedRecordV49FV8):
    value_constraint_id: str
    value_kind: CapacityMeasurementTargetValueKindV49FV8
    scalar_profile: str
    vocabulary_id: str | None
    integer_minimum: int | None
    integer_maximum: int | None
    text_minimum_utf8_bytes: int | None
    text_maximum_utf8_bytes: int | None
    text_ascii_pattern: str | None
    decimal_maximum: str | None
    collection_item_constraint_id: str | None
    external_authority_profile: str | None

    def __post_init__(self) -> None:
        _ascii_text(
            self.value_constraint_id,
            field="value_constraint_id",
            minimum=1,
            maximum=128,
        )
        _exact_enum(
            self.value_kind,
            CapacityMeasurementTargetValueKindV49FV8,
            field="value_kind",
        )
        if type(self.scalar_profile) is not str or self.scalar_profile not in {
            "SAFE_IJSON_UINT",
            "EXACT_BOOL",
            "SHA256",
            "UINT128_DECIMAL",
            "PLATFORM_ERRNO",
            "ENUM",
            "SAFE_IJSON_COLLECTION",
            "DURATION_BOUND",
        }:
            raise CanonicalizationError("scalar_profile is unsupported")
        for name in (
            "vocabulary_id",
            "text_ascii_pattern",
            "collection_item_constraint_id",
            "external_authority_profile",
        ):
            value = getattr(self, name)
            if value is not None:
                _ascii_text(value, field=name, minimum=1, maximum=256)
        for name in (
            "integer_minimum",
            "integer_maximum",
            "text_minimum_utf8_bytes",
            "text_maximum_utf8_bytes",
        ):
            _optional_safe_uint(getattr(self, name), field=name)
        if self.decimal_maximum is not None:
            _uint128_text(self.decimal_maximum, field="decimal_maximum")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "value_constraint_id": self.value_constraint_id,
            "value_kind": self.value_kind.value,
            "scalar_profile": self.scalar_profile,
            "vocabulary_id": self.vocabulary_id,
            "integer_minimum": self.integer_minimum,
            "integer_maximum": self.integer_maximum,
            "text_minimum_utf8_bytes": self.text_minimum_utf8_bytes,
            "text_maximum_utf8_bytes": self.text_maximum_utf8_bytes,
            "text_ascii_pattern": self.text_ascii_pattern,
            "decimal_maximum": self.decimal_maximum,
            "collection_item_constraint_id": self.collection_item_constraint_id,
            "external_authority_profile": self.external_authority_profile,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementValueConstraintDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["value_kind"] = _enum_from_json(
            item["value_kind"],
            CapacityMeasurementTargetValueKindV49FV8,
            field="value_kind",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAvailabilityStateRuleV49FV8(_NestedRecordV49FV8):
    availability: CapacityMeasurementTargetAvailabilityV49FV8
    value_policy: str
    reason_policy: str
    censoring_policy: str
    attempt_policy: str
    adapter_span_policy: str

    def __post_init__(self) -> None:
        _exact_enum(
            self.availability,
            CapacityMeasurementTargetAvailabilityV49FV8,
            field="availability",
        )
        allowed = {
            "value_policy": {
                "REQUIRED",
                "FORBIDDEN",
                "DURATION_BOUND_REQUIRED",
            },
            "reason_policy": {
                "FORBIDDEN",
                "NOT_APPLICABLE_REQUIRED",
                "UNAVAILABLE_REQUIRED",
            },
            "censoring_policy": {"NONE_ONLY", "DESCRIPTOR_BOUND_MAPPING"},
            "attempt_policy": {
                "ATTEMPTED_ONLY",
                "NOT_ATTEMPTED_ONLY",
                "REASON_RULE",
            },
            "adapter_span_policy": {
                "AVAILABLE_ONLY",
                "NOT_APPLICABLE_ONLY",
                "REASON_RULE",
            },
        }
        for name, members in allowed.items():
            value = getattr(self, name)
            if type(value) is not str or value not in members:
                raise CanonicalizationError(f"{name} is unsupported")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "availability": self.availability.value,
            "value_policy": self.value_policy,
            "reason_policy": self.reason_policy,
            "censoring_policy": self.censoring_policy,
            "attempt_policy": self.attempt_policy,
            "adapter_span_policy": self.adapter_span_policy,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAvailabilityStateRuleV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["availability"] = _enum_from_json(
            item["availability"],
            CapacityMeasurementTargetAvailabilityV49FV8,
            field="availability",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAttemptStateErrorFormsV49FV8(_NestedRecordV49FV8):
    attempt_state: CapacityMeasurementObservationAttemptV49FV8
    permitted_error_forms: tuple[CapacityMeasurementErrorFormV49FV8, ...]
    permitted_failure_phases: tuple[CapacityMeasurementSourceFailurePhaseV49FV8, ...]
    adapter_span_policy: str

    def __post_init__(self) -> None:
        _exact_enum(
            self.attempt_state,
            CapacityMeasurementObservationAttemptV49FV8,
            field="attempt_state",
        )
        for name, enum_type in (
            ("permitted_error_forms", CapacityMeasurementErrorFormV49FV8),
            (
                "permitted_failure_phases",
                CapacityMeasurementSourceFailurePhaseV49FV8,
            ),
        ):
            values = _exact_tuple(getattr(self, name), field=name)
            if (
                not values
                or any(type(value) is not enum_type for value in values)
                or values != tuple(sorted(values, key=lambda value: value.value))
                or len(values) != len(set(values))
            ):
                raise CanonicalizationError(f"{name} must be a sorted exact tuple")
        if type(
            self.adapter_span_policy
        ) is not str or self.adapter_span_policy not in {
            "AVAILABLE_ONLY",
            "NOT_APPLICABLE_ONLY",
            "UNAVAILABLE_ONLY",
        }:
            raise CanonicalizationError("adapter_span_policy is unsupported")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "attempt_state": self.attempt_state.value,
            "permitted_error_forms": [
                value.value for value in self.permitted_error_forms
            ],
            "permitted_failure_phases": [
                value.value for value in self.permitted_failure_phases
            ],
            "adapter_span_policy": self.adapter_span_policy,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAttemptStateErrorFormsV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            attempt_state=_enum_from_json(
                item["attempt_state"],
                CapacityMeasurementObservationAttemptV49FV8,
                field="attempt_state",
            ),
            permitted_error_forms=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementErrorFormV49FV8,
                    field="permitted_error_forms",
                )
                for value in _exact_json_list(
                    item["permitted_error_forms"],
                    field="permitted_error_forms",
                    maximum=4,
                )
            ),
            permitted_failure_phases=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementSourceFailurePhaseV49FV8,
                    field="permitted_failure_phases",
                )
                for value in _exact_json_list(
                    item["permitted_failure_phases"],
                    field="permitted_failure_phases",
                    maximum=5,
                )
            ),
            adapter_span_policy=item["adapter_span_policy"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementStatusReasonRuleV49FV8(_NestedRecordV49FV8):
    reason: CapacityMeasurementStatusReasonV49FV8
    required_availability: CapacityMeasurementTargetAvailabilityV49FV8
    context_predicate: str | None
    attempt_state_error_forms: tuple[
        CapacityMeasurementAttemptStateErrorFormsV49FV8, ...
    ]

    def __post_init__(self) -> None:
        _exact_enum(self.reason, CapacityMeasurementStatusReasonV49FV8, field="reason")
        _exact_enum(
            self.required_availability,
            CapacityMeasurementTargetAvailabilityV49FV8,
            field="required_availability",
        )
        if self.required_availability not in {
            CapacityMeasurementTargetAvailabilityV49FV8.NOT_APPLICABLE,
            CapacityMeasurementTargetAvailabilityV49FV8.UNAVAILABLE,
        }:
            raise CanonicalizationError("reason rule availability is unsupported")
        if self.context_predicate is not None and (
            type(self.context_predicate) is not str
            or self.context_predicate
            not in {
                "OPERATION_EXCLUDED",
                "REACHED_STATE_EXCLUDED",
                "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND",
                "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
                "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
                "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
            }
        ):
            raise CanonicalizationError("context_predicate is unsupported")
        states = _exact_tuple(
            self.attempt_state_error_forms, field="attempt_state_error_forms"
        )
        if (
            not states
            or any(
                type(state) is not CapacityMeasurementAttemptStateErrorFormsV49FV8
                for state in states
            )
            or states
            != tuple(sorted(states, key=lambda state: state.attempt_state.value))
            or len({state.attempt_state for state in states}) != len(states)
        ):
            raise CanonicalizationError(
                "attempt_state_error_forms must be sorted and unique"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "reason": self.reason.value,
            "required_availability": self.required_availability.value,
            "context_predicate": self.context_predicate,
            "attempt_state_error_forms": [
                state.as_dict() for state in self.attempt_state_error_forms
            ],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementStatusReasonRuleV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            reason=_enum_from_json(
                item["reason"], CapacityMeasurementStatusReasonV49FV8, field="reason"
            ),
            required_availability=_enum_from_json(
                item["required_availability"],
                CapacityMeasurementTargetAvailabilityV49FV8,
                field="required_availability",
            ),
            context_predicate=item["context_predicate"],
            attempt_state_error_forms=tuple(
                CapacityMeasurementAttemptStateErrorFormsV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["attempt_state_error_forms"],
                    field="attempt_state_error_forms",
                    maximum=2,
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementErrorFormDefinitionV49FV8(_NestedRecordV49FV8):
    error_form: CapacityMeasurementErrorFormV49FV8
    errno_pair_policy: str
    error_class_policy: str
    error_digest_policy: str
    class_digest_pair_policy: str

    def __post_init__(self) -> None:
        _exact_enum(
            self.error_form,
            CapacityMeasurementErrorFormV49FV8,
            field="error_form",
        )
        policies = {
            "errno_pair_policy": {"FORBIDDEN", "REQUIRED"},
            "error_class_policy": {"FORBIDDEN", "OPTIONAL", "REQUIRED"},
            "error_digest_policy": {"FORBIDDEN", "OPTIONAL", "REQUIRED"},
            "class_digest_pair_policy": {
                "BOTH_FORBIDDEN",
                "BOTH_OR_NEITHER",
                "BOTH_REQUIRED",
            },
        }
        for name, members in policies.items():
            value = getattr(self, name)
            if type(value) is not str or value not in members:
                raise CanonicalizationError(f"{name} is unsupported")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "error_form": self.error_form.value,
            "errno_pair_policy": self.errno_pair_policy,
            "error_class_policy": self.error_class_policy,
            "error_digest_policy": self.error_digest_policy,
            "class_digest_pair_policy": self.class_digest_pair_policy,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementErrorFormDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        values = dict(item)
        values["error_form"] = _enum_from_json(
            item["error_form"],
            CapacityMeasurementErrorFormV49FV8,
            field="error_form",
        )
        return cls(**values)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementStatusReasonPolicyDefinitionV49FV8(_NestedRecordV49FV8):
    status_reason_policy_id: str
    availability_state_rules: tuple[CapacityMeasurementAvailabilityStateRuleV49FV8, ...]
    reason_rules: tuple[CapacityMeasurementStatusReasonRuleV49FV8, ...]
    error_form_definitions: tuple[CapacityMeasurementErrorFormDefinitionV49FV8, ...]

    def __post_init__(self) -> None:
        _ascii_text(
            self.status_reason_policy_id,
            field="status_reason_policy_id",
            minimum=1,
            maximum=128,
        )
        checks: tuple[tuple[str, type[Any], Any], ...] = (
            (
                "availability_state_rules",
                CapacityMeasurementAvailabilityStateRuleV49FV8,
                lambda value: value.availability.value,
            ),
            (
                "reason_rules",
                CapacityMeasurementStatusReasonRuleV49FV8,
                lambda value: value.reason.value,
            ),
            (
                "error_form_definitions",
                CapacityMeasurementErrorFormDefinitionV49FV8,
                lambda value: value.error_form.value,
            ),
        )
        for name, expected_type, key in checks:
            values = _exact_tuple(getattr(self, name), field=name)
            if (
                any(type(value) is not expected_type for value in values)
                or values != tuple(sorted(values, key=key))
                or len({key(value) for value in values}) != len(values)
            ):
                raise CanonicalizationError(f"{name} must be exact, sorted, and unique")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "status_reason_policy_id": self.status_reason_policy_id,
            "availability_state_rules": [
                value.as_dict() for value in self.availability_state_rules
            ],
            "reason_rules": [value.as_dict() for value in self.reason_rules],
            "error_form_definitions": [
                value.as_dict() for value in self.error_form_definitions
            ],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementStatusReasonPolicyDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            status_reason_policy_id=item["status_reason_policy_id"],
            availability_state_rules=tuple(
                CapacityMeasurementAvailabilityStateRuleV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["availability_state_rules"],
                    field="availability_state_rules",
                    maximum=4,
                )
            ),
            reason_rules=tuple(
                CapacityMeasurementStatusReasonRuleV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["reason_rules"], field="reason_rules", maximum=26
                )
            ),
            error_form_definitions=tuple(
                CapacityMeasurementErrorFormDefinitionV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["error_form_definitions"],
                    field="error_form_definitions",
                    maximum=4,
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCrossFieldConstraintDefinitionV49FV8(_NestedRecordV49FV8):
    cross_field_constraint_id: str
    count_field_id: str
    sequence_field_id: str
    kind_field_id: str
    activation_condition: str
    maximum_items: int
    sequence_order: str
    cardinality_rule: str
    pairing_rule: str

    def __post_init__(self) -> None:
        for name in (
            "cross_field_constraint_id",
            "count_field_id",
            "sequence_field_id",
            "kind_field_id",
            "activation_condition",
            "sequence_order",
            "cardinality_rule",
            "pairing_rule",
        ):
            _ascii_text(getattr(self, name), field=name, minimum=1, maximum=128)
        _safe_uint(self.maximum_items, field="maximum_items", minimum=1)

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {field.name: getattr(self, field.name) for field in fields(type(self))}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCrossFieldConstraintDefinitionV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(**item)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetFieldDescriptorV49FV8(_NestedRecordV49FV8):
    field_id: str
    layer: str
    value_kind: CapacityMeasurementTargetValueKindV49FV8
    unit: str
    value_constraint_id: str
    observation_method_role_pairs: tuple[
        CapacityMeasurementObservationMethodRolePairV49FV8, ...
    ]
    allowed_checkpoint_marker_kinds: tuple[CapacityMeasurementMarkerKindV49FV8, ...]
    applicable_operation_kinds: tuple[CapacityMeasurementOperationKindV49FV8, ...]
    allowed_status_reasons: tuple[CapacityMeasurementStatusReasonV49FV8, ...]
    status_reason_policy_id: str
    censoring_allowed: bool
    later_threshold_action_if_unavailable: CapacityMeasurementLaterThresholdActionV49FV8
    value_shape_id: str
    value_shape_keys: tuple[str, ...]
    cross_field_constraint_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _ascii_text(
            self.field_id,
            field="field_id",
            minimum=3,
            maximum=256,
            pattern=_FIELD_ID_RE,
        )
        if (
            type(self.layer) is not str
            or self.layer != self.field_id.split(".", 1)[0].upper()
        ):
            raise CanonicalizationError("descriptor layer differs from field prefix")
        _exact_enum(
            self.value_kind,
            CapacityMeasurementTargetValueKindV49FV8,
            field="value_kind",
        )
        for name in (
            "unit",
            "value_constraint_id",
            "status_reason_policy_id",
            "value_shape_id",
        ):
            _ascii_text(getattr(self, name), field=name, minimum=1, maximum=128)
        method_pairs = _exact_tuple(
            self.observation_method_role_pairs,
            field="observation_method_role_pairs",
        )
        if (
            len(method_pairs) > RAW_V8_MAXIMUM_OBSERVATION_METHOD_ROLE_PAIRS_V49F
            or any(
                type(value) is not CapacityMeasurementObservationMethodRolePairV49FV8
                for value in method_pairs
            )
            or method_pairs
            != tuple(
                sorted(method_pairs, key=lambda value: value.observation_method.value)
            )
            or len({value.observation_method for value in method_pairs})
            != len(method_pairs)
        ):
            raise CanonicalizationError("descriptor method-role pairs are invalid")
        for name, enum_type in (
            ("allowed_checkpoint_marker_kinds", CapacityMeasurementMarkerKindV49FV8),
            ("applicable_operation_kinds", CapacityMeasurementOperationKindV49FV8),
            ("allowed_status_reasons", CapacityMeasurementStatusReasonV49FV8),
        ):
            values = _exact_tuple(getattr(self, name), field=name)
            if (
                any(type(value) is not enum_type for value in values)
                or values != tuple(sorted(values, key=lambda value: value.value))
                or len(values) != len(set(values))
            ):
                raise CanonicalizationError(f"{name} must be an exact sorted tuple")
        if not self.applicable_operation_kinds:
            raise CanonicalizationError("descriptor must apply to an operation")
        _exact_bool(self.censoring_allowed, field="censoring_allowed")
        _exact_enum(
            self.later_threshold_action_if_unavailable,
            CapacityMeasurementLaterThresholdActionV49FV8,
            field="later_threshold_action_if_unavailable",
        )
        value_shape_keys = _exact_string_tuple(
            self.value_shape_keys, field="value_shape_keys", sorted_values=True
        )
        cross_field_constraint_ids = _exact_string_tuple(
            self.cross_field_constraint_ids,
            field="cross_field_constraint_ids",
            sorted_values=True,
        )
        if len(value_shape_keys) > 512:
            raise CanonicalizationError("value_shape_keys exceeds 512 values")
        if len(cross_field_constraint_ids) > 16:
            raise CanonicalizationError("cross_field_constraint_ids exceeds 16 values")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "layer": self.layer,
            "value_kind": self.value_kind.value,
            "unit": self.unit,
            "value_constraint_id": self.value_constraint_id,
            "observation_method_role_pairs": [
                value.as_dict() for value in self.observation_method_role_pairs
            ],
            "allowed_checkpoint_marker_kinds": [
                value.value for value in self.allowed_checkpoint_marker_kinds
            ],
            "applicable_operation_kinds": [
                value.value for value in self.applicable_operation_kinds
            ],
            "allowed_status_reasons": [
                value.value for value in self.allowed_status_reasons
            ],
            "status_reason_policy_id": self.status_reason_policy_id,
            "censoring_allowed": self.censoring_allowed,
            "later_threshold_action_if_unavailable": (
                self.later_threshold_action_if_unavailable.value
            ),
            "value_shape_id": self.value_shape_id,
            "value_shape_keys": list(self.value_shape_keys),
            "cross_field_constraint_ids": list(self.cross_field_constraint_ids),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetFieldDescriptorV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            field_id=item["field_id"],
            layer=item["layer"],
            value_kind=_enum_from_json(
                item["value_kind"],
                CapacityMeasurementTargetValueKindV49FV8,
                field="value_kind",
            ),
            unit=item["unit"],
            value_constraint_id=item["value_constraint_id"],
            observation_method_role_pairs=tuple(
                CapacityMeasurementObservationMethodRolePairV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["observation_method_role_pairs"],
                    field="observation_method_role_pairs",
                    maximum=RAW_V8_MAXIMUM_OBSERVATION_METHOD_ROLE_PAIRS_V49F,
                )
            ),
            allowed_checkpoint_marker_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementMarkerKindV49FV8,
                    field="allowed_checkpoint_marker_kinds",
                )
                for value in _exact_json_list(
                    item["allowed_checkpoint_marker_kinds"],
                    field="allowed_checkpoint_marker_kinds",
                    maximum=19,
                )
            ),
            applicable_operation_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementOperationKindV49FV8,
                    field="applicable_operation_kinds",
                )
                for value in _exact_json_list(
                    item["applicable_operation_kinds"],
                    field="applicable_operation_kinds",
                    maximum=4,
                )
            ),
            allowed_status_reasons=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementStatusReasonV49FV8,
                    field="allowed_status_reasons",
                )
                for value in _exact_json_list(
                    item["allowed_status_reasons"],
                    field="allowed_status_reasons",
                    maximum=26,
                )
            ),
            status_reason_policy_id=item["status_reason_policy_id"],
            censoring_allowed=item["censoring_allowed"],
            later_threshold_action_if_unavailable=_enum_from_json(
                item["later_threshold_action_if_unavailable"],
                CapacityMeasurementLaterThresholdActionV49FV8,
                field="later_threshold_action_if_unavailable",
            ),
            value_shape_id=item["value_shape_id"],
            value_shape_keys=tuple(
                _exact_json_list(
                    item["value_shape_keys"], field="value_shape_keys", maximum=512
                )
            ),
            cross_field_constraint_ids=tuple(
                _exact_json_list(
                    item["cross_field_constraint_ids"],
                    field="cross_field_constraint_ids",
                    maximum=16,
                )
            ),
        )


RAW_V8_STATUS_REASON_POLICY_ID_V49F = "RAW_V8_STATUS_REASON_ATTEMPT_ERROR_POLICY_V1"
RAW_V8_A1_FIFO_CROSS_FIELD_CONSTRAINT_ID_V49F = (
    "A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1"
)
RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F = (
    "ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618"
)
RAW_V8_OPERATION_COUNTER_SCHEMA_ID_V49F = (
    "5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3"
)

_RAW_V8_ALL_OPERATION_KINDS_V49F = tuple(CapacityMeasurementOperationKindV49FV8)
_RAW_V8_ALL_OBSERVATION_ROLES_V49F = tuple(CapacityMeasurementObservationRoleV49FV8)
_RAW_V8_FULL_CHECKPOINT_MARKERS_V49F = tuple(
    CapacityMeasurementMarkerKindV49FV8(value)
    for value in (
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
)
_RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F = {
    CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY: frozenset(
        {
            CapacityMeasurementMarkerKindV49FV8.ACK_DEADLINE_NOT_DUE,
            CapacityMeasurementMarkerKindV49FV8.ACK_DEADLINE_TERMINAL_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
        }
    ),
    CapacityMeasurementOperationKindV49FV8.INGRESS: frozenset(
        {
            CapacityMeasurementMarkerKindV49FV8.INGRESS_RETURN_READY,
            CapacityMeasurementMarkerKindV49FV8.PARSER_UNIT_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.RAW_PREFIX_COMMITTED,
            CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
        }
    ),
    CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN: frozenset(
        {
            CapacityMeasurementMarkerKindV49FV8.LOCAL_CLOSE_DISPATCH_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.SHUTDOWN_TERMINAL_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
            CapacityMeasurementMarkerKindV49FV8.TCP_HALF_CLOSE_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.TLS_CONTROL_CONVERGED,
        }
    ),
    CapacityMeasurementOperationKindV49FV8.SUBSCRIPTION_DISPATCH: frozenset(
        {
            CapacityMeasurementMarkerKindV49FV8.DISPATCH_RETURN_READY,
            CapacityMeasurementMarkerKindV49FV8.KERNEL_SEND_RESULT_CONVERGED,
            CapacityMeasurementMarkerKindV49FV8.OUTBOUND_ARTIFACTS_PREPARED,
            CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
        }
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCheckpointOperationRecordV49FV8(_NestedRecordV49FV8):
    checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8
    applicable_operation_kinds: tuple[CapacityMeasurementOperationKindV49FV8, ...]

    def __post_init__(self) -> None:
        _exact_enum(
            self.checkpoint_marker_kind,
            CapacityMeasurementMarkerKindV49FV8,
            field="checkpoint_marker_kind",
        )
        if self.checkpoint_marker_kind not in _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F:
            raise CanonicalizationError(
                "checkpoint operation record uses a non-checkpoint marker"
            )
        operations = _exact_tuple(
            self.applicable_operation_kinds,
            field="applicable_operation_kinds",
        )
        if (
            not operations
            or any(
                type(value) is not CapacityMeasurementOperationKindV49FV8
                for value in operations
            )
            or operations != tuple(sorted(operations, key=lambda value: value.value))
            or len(set(operations)) != len(operations)
        ):
            raise CanonicalizationError(
                "checkpoint operations must be a nonempty sorted exact tuple"
            )
        expected = tuple(
            operation
            for operation in CapacityMeasurementOperationKindV49FV8
            if self.checkpoint_marker_kind
            in _RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F[operation]
        )
        if operations != expected:
            raise CanonicalizationError(
                "checkpoint operation record differs from the frozen marker map"
            )

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "checkpoint_marker_kind": self.checkpoint_marker_kind.value,
            "applicable_operation_kinds": [
                value.value for value in self.applicable_operation_kinds
            ],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCheckpointOperationRecordV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            checkpoint_marker_kind=_enum_from_json(
                item["checkpoint_marker_kind"],
                CapacityMeasurementMarkerKindV49FV8,
                field="checkpoint_marker_kind",
            ),
            applicable_operation_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementOperationKindV49FV8,
                    field="applicable_operation_kinds",
                )
                for value in _exact_json_list(
                    item["applicable_operation_kinds"],
                    field="applicable_operation_kinds",
                    maximum=4,
                )
            ),
        )


_RAW_V8_FORBIDDEN_FULL_CHECKPOINT_MARKERS_V49F = tuple(
    CapacityMeasurementMarkerKindV49FV8(value)
    for value in (
        "ADMISSION_CANDIDATE_COMMITTED",
        "ADMISSION_GRANTED",
        "ADMISSION_NOT_GRANTED",
        "ADMISSION_TICKET_ACCEPTED",
        "TARGET_EFFECT_ENTRY",
    )
)
_RAW_V8_CHECKPOINT_OPERATION_RECORDS_V49F = tuple(
    CapacityMeasurementCheckpointOperationRecordV49FV8(
        checkpoint_marker_kind=marker,
        applicable_operation_kinds=tuple(
            operation
            for operation in CapacityMeasurementOperationKindV49FV8
            if marker in _RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F[operation]
        ),
    )
    for marker in _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementMarkerContractV49FV8(_StandaloneRecordV49FV8):
    contract_version: str
    ordered_marker_kinds: tuple[CapacityMeasurementMarkerKindV49FV8, ...]
    ordered_full_checkpoint_marker_kinds: tuple[
        CapacityMeasurementMarkerKindV49FV8, ...
    ]
    ordered_checkpoint_operation_records: tuple[
        CapacityMeasurementCheckpointOperationRecordV49FV8, ...
    ]
    forbidden_full_checkpoint_marker_kinds: tuple[
        CapacityMeasurementMarkerKindV49FV8, ...
    ]
    minimum_marker_ring_capacity: int
    maximum_marker_ring_capacity: int
    maximum_checkpoint_selector_length: int
    stable_checkpoint_requires_attempt: bool
    marker_contract_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_MARKER_CONTRACT_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "marker_contract_id"
    _MAXIMUM_BYTES: ClassVar[int] = 32 * 1024

    def __post_init__(self) -> None:
        if (
            type(self.contract_version) is not str
            or self.contract_version != "riskyieldmm_raw_v8_marker_contract_v1"
        ):
            raise CanonicalizationError("marker contract version differs")
        expected_markers = tuple(
            sorted(CapacityMeasurementMarkerKindV49FV8, key=lambda value: value.value)
        )
        marker_tuple_specs = (
            self.ordered_marker_kinds,
            self.ordered_full_checkpoint_marker_kinds,
            self.forbidden_full_checkpoint_marker_kinds,
        )
        if (
            any(
                any(
                    type(value) is not CapacityMeasurementMarkerKindV49FV8
                    for value in values
                )
                for values in marker_tuple_specs
            )
            or any(
                type(value) is not CapacityMeasurementCheckpointOperationRecordV49FV8
                for value in self.ordered_checkpoint_operation_records
            )
            or _exact_tuple(self.ordered_marker_kinds, field="ordered_marker_kinds")
            != expected_markers
            or _exact_tuple(
                self.ordered_full_checkpoint_marker_kinds,
                field="ordered_full_checkpoint_marker_kinds",
            )
            != _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F
            or _exact_tuple(
                self.ordered_checkpoint_operation_records,
                field="ordered_checkpoint_operation_records",
            )
            != _RAW_V8_CHECKPOINT_OPERATION_RECORDS_V49F
            or _exact_tuple(
                self.forbidden_full_checkpoint_marker_kinds,
                field="forbidden_full_checkpoint_marker_kinds",
            )
            != _RAW_V8_FORBIDDEN_FULL_CHECKPOINT_MARKERS_V49F
        ):
            raise CanonicalizationError("marker contract catalog differs")
        if set(self.ordered_full_checkpoint_marker_kinds) & set(
            self.forbidden_full_checkpoint_marker_kinds
        ):
            raise CanonicalizationError(
                "full and forbidden checkpoint marker sets overlap"
            )
        exact_integers = {
            "minimum_marker_ring_capacity": (RAW_V8_MINIMUM_MARKER_RING_CAPACITY_V49F),
            "maximum_marker_ring_capacity": (RAW_V8_MAXIMUM_MARKER_RING_CAPACITY_V49F),
            "maximum_checkpoint_selector_length": (
                RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F
            ),
        }
        for name, expected in exact_integers.items():
            if (
                _safe_uint(
                    getattr(self, name),
                    field=name,
                    minimum=expected,
                    maximum=expected,
                )
                != expected
            ):
                raise CanonicalizationError(f"{name} differs")
        if not _exact_bool(
            self.stable_checkpoint_requires_attempt,
            field="stable_checkpoint_requires_attempt",
        ):
            raise CanonicalizationError("stable checkpoints must require an attempt")
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "ordered_marker_kinds": [
                value.value for value in self.ordered_marker_kinds
            ],
            "ordered_full_checkpoint_marker_kinds": [
                value.value for value in self.ordered_full_checkpoint_marker_kinds
            ],
            "ordered_checkpoint_operation_records": [
                value.as_dict() for value in self.ordered_checkpoint_operation_records
            ],
            "forbidden_full_checkpoint_marker_kinds": [
                value.value for value in self.forbidden_full_checkpoint_marker_kinds
            ],
            "minimum_marker_ring_capacity": self.minimum_marker_ring_capacity,
            "maximum_marker_ring_capacity": self.maximum_marker_ring_capacity,
            "maximum_checkpoint_selector_length": (
                self.maximum_checkpoint_selector_length
            ),
            "stable_checkpoint_requires_attempt": (
                self.stable_checkpoint_requires_attempt
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementMarkerContractV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            contract_version=item["contract_version"],
            ordered_marker_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementMarkerKindV49FV8,
                    field="ordered_marker_kinds",
                )
                for value in _exact_json_list(
                    item["ordered_marker_kinds"],
                    field="ordered_marker_kinds",
                    maximum=19,
                )
            ),
            ordered_full_checkpoint_marker_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementMarkerKindV49FV8,
                    field="ordered_full_checkpoint_marker_kinds",
                )
                for value in _exact_json_list(
                    item["ordered_full_checkpoint_marker_kinds"],
                    field="ordered_full_checkpoint_marker_kinds",
                    maximum=13,
                )
            ),
            ordered_checkpoint_operation_records=tuple(
                CapacityMeasurementCheckpointOperationRecordV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered_checkpoint_operation_records"],
                    field="ordered_checkpoint_operation_records",
                    maximum=13,
                )
            ),
            forbidden_full_checkpoint_marker_kinds=tuple(
                _enum_from_json(
                    value,
                    CapacityMeasurementMarkerKindV49FV8,
                    field="forbidden_full_checkpoint_marker_kinds",
                )
                for value in _exact_json_list(
                    item["forbidden_full_checkpoint_marker_kinds"],
                    field="forbidden_full_checkpoint_marker_kinds",
                    maximum=5,
                )
            ),
            minimum_marker_ring_capacity=item["minimum_marker_ring_capacity"],
            maximum_marker_ring_capacity=item["maximum_marker_ring_capacity"],
            maximum_checkpoint_selector_length=item[
                "maximum_checkpoint_selector_length"
            ],
            stable_checkpoint_requires_attempt=item[
                "stable_checkpoint_requires_attempt"
            ],
            marker_contract_id=item["marker_contract_id"],
        )


RAW_V8_MARKER_CONTRACT_V49F = CapacityMeasurementMarkerContractV49FV8(
    contract_version="riskyieldmm_raw_v8_marker_contract_v1",
    ordered_marker_kinds=tuple(
        sorted(CapacityMeasurementMarkerKindV49FV8, key=lambda value: value.value)
    ),
    ordered_full_checkpoint_marker_kinds=_RAW_V8_FULL_CHECKPOINT_MARKERS_V49F,
    ordered_checkpoint_operation_records=_RAW_V8_CHECKPOINT_OPERATION_RECORDS_V49F,
    forbidden_full_checkpoint_marker_kinds=(
        _RAW_V8_FORBIDDEN_FULL_CHECKPOINT_MARKERS_V49F
    ),
    minimum_marker_ring_capacity=RAW_V8_MINIMUM_MARKER_RING_CAPACITY_V49F,
    maximum_marker_ring_capacity=RAW_V8_MAXIMUM_MARKER_RING_CAPACITY_V49F,
    maximum_checkpoint_selector_length=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
    stable_checkpoint_requires_attempt=True,
)
RAW_V8_MARKER_CONTRACT_ID_V49F = RAW_V8_MARKER_CONTRACT_V49F.marker_contract_id


_RAW_V8_SELECTOR_MARKER_ORDER_BY_OPERATION_V49F = {
    CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY: (
        CapacityMeasurementMarkerKindV49FV8.ACK_DEADLINE_NOT_DUE,
        CapacityMeasurementMarkerKindV49FV8.ACK_DEADLINE_TERMINAL_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
    ),
    CapacityMeasurementOperationKindV49FV8.INGRESS: (
        CapacityMeasurementMarkerKindV49FV8.RAW_PREFIX_COMMITTED,
        CapacityMeasurementMarkerKindV49FV8.PARSER_UNIT_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.INGRESS_RETURN_READY,
        CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
    ),
    CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN: (
        CapacityMeasurementMarkerKindV49FV8.LOCAL_CLOSE_DISPATCH_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.TLS_CONTROL_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.TCP_HALF_CLOSE_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.SHUTDOWN_TERMINAL_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
    ),
    CapacityMeasurementOperationKindV49FV8.SUBSCRIPTION_DISPATCH: (
        CapacityMeasurementMarkerKindV49FV8.OUTBOUND_ARTIFACTS_PREPARED,
        CapacityMeasurementMarkerKindV49FV8.KERNEL_SEND_RESULT_CONVERGED,
        CapacityMeasurementMarkerKindV49FV8.DISPATCH_RETURN_READY,
        CapacityMeasurementMarkerKindV49FV8.TARGET_ESCAPE_OBSERVED,
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCheckpointSelectorEntryV49FV8(_StandaloneRecordV49FV8):
    selector_position: int
    operation_kind: CapacityMeasurementOperationKindV49FV8
    checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8
    occurrence_index_within_kind: int
    checkpoint_selector_entry_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_CHECKPOINT_SELECTOR_ENTRY_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "checkpoint_selector_entry_id"
    _MAXIMUM_BYTES: ClassVar[int] = 2 * 1024

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selector_position",
            _safe_uint(
                self.selector_position,
                field="selector_position",
                minimum=1,
                maximum=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
            ),
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.checkpoint_marker_kind,
            CapacityMeasurementMarkerKindV49FV8,
            field="checkpoint_marker_kind",
        )
        if (
            self.checkpoint_marker_kind
            not in _RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F[self.operation_kind]
        ):
            raise CanonicalizationError(
                "selector entry marker is incompatible with its operation"
            )
        object.__setattr__(
            self,
            "occurrence_index_within_kind",
            _safe_uint(
                self.occurrence_index_within_kind,
                field="occurrence_index_within_kind",
                minimum=1,
            ),
        )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "selector_position": self.selector_position,
            "operation_kind": self.operation_kind.value,
            "checkpoint_marker_kind": self.checkpoint_marker_kind.value,
            "occurrence_index_within_kind": self.occurrence_index_within_kind,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCheckpointSelectorEntryV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            selector_position=item["selector_position"],
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            checkpoint_marker_kind=_enum_from_json(
                item["checkpoint_marker_kind"],
                CapacityMeasurementMarkerKindV49FV8,
                field="checkpoint_marker_kind",
            ),
            occurrence_index_within_kind=item["occurrence_index_within_kind"],
            checkpoint_selector_entry_id=item["checkpoint_selector_entry_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCheckpointSelectorV49FV8(_StandaloneRecordV49FV8):
    operation_kind: CapacityMeasurementOperationKindV49FV8
    ordered_entries: tuple[CapacityMeasurementCheckpointSelectorEntryV49FV8, ...]
    selector_length: int
    ordered_checkpoint_selector_entry_ids: tuple[str, ...]
    checkpoint_selector_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_CHECKPOINT_SELECTOR_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "checkpoint_selector_id"
    _MAXIMUM_BYTES: ClassVar[int] = 256 * 1024

    def __post_init__(self) -> None:
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        entries = _exact_tuple(self.ordered_entries, field="ordered_entries")
        if len(entries) > RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F or any(
            type(value) is not CapacityMeasurementCheckpointSelectorEntryV49FV8
            for value in entries
        ):
            raise CanonicalizationError("selector entries are invalid or unbounded")
        entries = tuple(value._revalidated() for value in entries)
        if tuple(value.selector_position for value in entries) != tuple(
            range(1, len(entries) + 1)
        ):
            raise CanonicalizationError("selector positions must be exactly 1..N")
        if any(value.operation_kind is not self.operation_kind for value in entries):
            raise CanonicalizationError("selector entries use a different operation")
        coordinates = tuple(
            (value.checkpoint_marker_kind, value.occurrence_index_within_kind)
            for value in entries
        )
        if len(set(coordinates)) != len(coordinates):
            raise CanonicalizationError(
                "selector entries duplicate a marker occurrence"
            )
        order = _RAW_V8_SELECTOR_MARKER_ORDER_BY_OPERATION_V49F[self.operation_kind]
        rank = {marker: index for index, marker in enumerate(order)}
        ranks = tuple(rank[value.checkpoint_marker_kind] for value in entries)
        if ranks != tuple(sorted(ranks)):
            raise CanonicalizationError(
                "selector marker order is incompatible with the operation DFA"
            )
        last_occurrence_by_kind: dict[CapacityMeasurementMarkerKindV49FV8, int] = {}
        for value in entries:
            previous = last_occurrence_by_kind.get(value.checkpoint_marker_kind, 0)
            if value.occurrence_index_within_kind <= previous:
                raise CanonicalizationError(
                    "selector occurrences must increase within each marker kind"
                )
            last_occurrence_by_kind[value.checkpoint_marker_kind] = (
                value.occurrence_index_within_kind
            )
        if _safe_uint(
            self.selector_length,
            field="selector_length",
            maximum=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
        ) != len(entries):
            raise CanonicalizationError("selector_length differs from entries")
        ids = _exact_tuple(
            self.ordered_checkpoint_selector_entry_ids,
            field="ordered_checkpoint_selector_entry_ids",
        )
        normalized_ids = tuple(
            _hash(value, field="ordered_checkpoint_selector_entry_ids") for value in ids
        )
        expected_ids = tuple(value.checkpoint_selector_entry_id for value in entries)
        if normalized_ids != expected_ids:
            raise CanonicalizationError(
                "selector entry IDs differ from embedded entries"
            )
        object.__setattr__(
            self,
            "ordered_checkpoint_selector_entry_ids",
            normalized_ids,
        )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "operation_kind": self.operation_kind.value,
            "selector_length": self.selector_length,
            "ordered_checkpoint_selector_entry_ids": list(
                self.ordered_checkpoint_selector_entry_ids
            ),
        }

    def _envelope_unchecked(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "measurement_schema_version": (
                PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION
            ),
            "record_domain": self._DOMAIN,
            "operation_kind": self.operation_kind.value,
            "ordered_entries": [value.as_dict() for value in self.ordered_entries],
            "selector_length": self.selector_length,
            "ordered_checkpoint_selector_entry_ids": list(
                self.ordered_checkpoint_selector_entry_ids
            ),
            "checkpoint_selector_id": self.checkpoint_selector_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCheckpointSelectorV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            ordered_entries=tuple(
                CapacityMeasurementCheckpointSelectorEntryV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered_entries"],
                    field="ordered_entries",
                    maximum=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
                )
            ),
            selector_length=item["selector_length"],
            ordered_checkpoint_selector_entry_ids=tuple(
                _exact_json_list(
                    item["ordered_checkpoint_selector_entry_ids"],
                    field="ordered_checkpoint_selector_entry_ids",
                    maximum=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
                )
            ),
            checkpoint_selector_id=item["checkpoint_selector_id"],
        )


_RAW_V8_ACTOR_KIND_KEYS_V49F = (
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
_RAW_V8_SQLITE_RESULT_CLASSES_V49F = (
    "BUSY",
    "FULL",
    "INTERRUPT",
    "IOERR",
    "LOCKED",
    "NOMEM",
    "OK",
    "OTHER",
)
_RAW_V8_SQLITE_STAGE_RESULT_KEYS_V49F = tuple(
    sorted(
        f"{stage}.{result}"
        for stage in ("BEGIN", "BODY", "COMMIT", "ROLLBACK")
        for result in _RAW_V8_SQLITE_RESULT_CLASSES_V49F
    )
)
_RAW_V8_GC_GENERATION_KEYS_V49F = (
    "GENERATION_0",
    "GENERATION_1",
    "GENERATION_2",
)


@dataclass(frozen=True, slots=True)
class _DescriptorProfileV49FV8:
    method_role_pairs: tuple[CapacityMeasurementObservationMethodRolePairV49FV8, ...]
    checkpoint_markers: tuple[CapacityMeasurementMarkerKindV49FV8, ...]
    operation_kinds: tuple[CapacityMeasurementOperationKindV49FV8, ...]
    reason_profile: str
    censoring_allowed: bool


_RAW_V8_UNAVAILABILITY_PROFILES_V49F: dict[str, frozenset[str]] = {
    "U_OWNER": frozenset(
        {
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
        }
    ),
    "U_COUNTER": frozenset(
        {
            "INSTRUMENTATION_DISABLED",
            "TARGET_BOUNDARY_NOT_REACHED",
            "UNSUPPORTED_BY_PYTHON_RUNTIME",
            "OBSERVER_INTERNAL_ERROR",
            "PROCESS_LOSS_VOLATILE_MARKER_STATE",
            "SOURCE_DURABLE_RECORD_ABSENT",
            "SOURCE_COUNTER_NOT_INSTRUMENTED",
            "SOURCE_CLOCK_UNAVAILABLE",
            "ARTIFACT_BOUND_EXCEEDED",
        }
    ),
    "U_POLICY": frozenset({"NO_FROZEN_PRESSURE_POLICY"}),
    "U_STATIC": frozenset(),
}
_RAW_V8_UNAVAILABILITY_PROFILES_V49F["U_OS"] = _RAW_V8_UNAVAILABILITY_PROFILES_V49F[
    "U_OWNER"
] | frozenset({"UNSUPPORTED_BY_KERNEL", "PERMISSION_DENIED", "OS_OBSERVATION_ERROR"})
_RAW_V8_UNAVAILABILITY_PROFILES_V49F["U_SQLITE"] = _RAW_V8_UNAVAILABILITY_PROFILES_V49F[
    "U_OS"
] | frozenset({"OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION"})
_RAW_V8_UNAVAILABILITY_PROFILES_V49F["U_LOOP"] = _RAW_V8_UNAVAILABILITY_PROFILES_V49F[
    "U_COUNTER"
] | frozenset(
    {
        "NO_STABLE_SLOW_CALLBACK_SOURCE",
        "PERIODIC_PROBE_DID_NOT_FIRE",
        "PROBE_RING_OVERWROTE_PREFIX",
    }
)
_RAW_V8_UNAVAILABILITY_PROFILES_V49F["U_GC"] = _RAW_V8_UNAVAILABILITY_PROFILES_V49F[
    "U_COUNTER"
]
_RAW_V8_UNAVAILABILITY_PROFILES_V49F["U_MARKER"] = _RAW_V8_UNAVAILABILITY_PROFILES_V49F[
    "U_COUNTER"
] | frozenset({"MARKER_RING_OVERWROTE_PREFIX"})
_RAW_V8_CHECKPOINT_PLACEHOLDER_FIELD_REASONS_V49F = frozenset(
    {
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
        "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
        "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
    }
)
for _reason_profile_id_v49f_v8 in tuple(_RAW_V8_UNAVAILABILITY_PROFILES_V49F):
    _RAW_V8_UNAVAILABILITY_PROFILES_V49F[_reason_profile_id_v49f_v8] = (
        _RAW_V8_UNAVAILABILITY_PROFILES_V49F[_reason_profile_id_v49f_v8]
        | _RAW_V8_CHECKPOINT_PLACEHOLDER_FIELD_REASONS_V49F
    )
del _reason_profile_id_v49f_v8
_RAW_V8_NON_APPLICABLE_REASONS_V49F = frozenset(
    {"NOT_APPLICABLE_TO_OPERATION", "NOT_APPLICABLE_TO_REACHED_STATE"}
)

_RAW_V8_DESCRIPTOR_PROFILE_ROWS_V49F = """
P_A1_POINT|A1_OWNER_SNAPSHOT@B,C,A|CP_TARGET|ALL4|U_OWNER|no
P_A1_OUTCOME|A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ALL4|U_COUNTER|no
P_A1_BOUND|A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ALL4|U_COUNTER|yes
P_KERNEL_ID|LINUX_SOCKET_IDENTITY@B,C,A|CP_TARGET|ALL4|U_OS|no
P_KERNEL_SOCKOPT|LINUX_GETSOCKOPT@B,C,A|CP_TARGET|ALL4|U_OS|no
P_KERNEL_IOCTL|LINUX_IOCTL@B,C,A|CP_TARGET|ALL4|U_OS|no
P_KERNEL_POLL|LINUX_POLL@B,C,A|CP_TARGET|ALL4|U_OS|no
P_POINT_DERIVED|EXACT_REGISTERED_FIELD_DERIVATION@B,C,A|CP_TARGET|ALL4|U_OWNER|no
P_OP_ACCUM|OPERATION_COUNTER_ACCUMULATOR@C,A,G|CP_TARGET|ALL4|U_COUNTER|no
P_OP_DURABLE|DURABLE_PREFIX_REPLAY@C,A,G,R|CP_TARGET|ALL4|U_COUNTER|no
P_TLS_POINT|TLS_OWNER_SCALAR@B,C,A|CP_TARGET|ALL4|U_OWNER|no
P_INGRESS_POINT|INGRESS_OWNER_SCALAR@B,C,A;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ALL4|U_OWNER|no
P_PARSER_POINT|PARSER_OWNER_SCALAR@B,C,A;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ALL4|U_OWNER|no
P_ACTOR_POINT|ACTOR_OWNER_SNAPSHOT@B,C,A;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ALL4|U_OWNER|no
P_SQLITE_CONFIG|SQLITE_CONNECTION_CONFIGURATION@B,C,A,R|CP_TARGET|ALL4|U_SQLITE|no
P_SQLITE_OP|SQLITE_TRANSACTION_ACCUMULATOR@C,A,G|CP_TARGET|ALL4|U_SQLITE|no
P_SQLITE_FILE|FILESYSTEM_STAT@B,C,A,R|CP_TARGET|ALL4|U_SQLITE|no
P_SQLITE_PRAGMA|SQLITE_QUIESCENT_PRAGMA@B,C,A,R|CP_TARGET|ALL4|U_SQLITE|no
P_LOOP_STATIC|LOOP_MANIFEST_CONFIGURATION@B,C,A,G,R|CP_TARGET|ALL4|U_STATIC|no
P_LOOP_OP|LOOP_PROBE_ACCUMULATOR@C,A,G|CP_TARGET|ALL4|U_LOOP|no
P_LOOP_BOUND|LOOP_PROBE_ACCUMULATOR@C,A,G|CP_TARGET|ALL4|U_LOOP|yes
P_LOOP_CONFIG|LOOP_RUNTIME_CONFIGURATION@B,C,A|CP_TARGET|ALL4|U_LOOP|no
P_PROCESS_POINT|ROW_SELECTED|CP_TARGET|ALL4|U_OS|no
P_PROCESS_CPU|ROW_SELECTED|CP_TARGET|ALL4|U_COUNTER|no
P_GC_BEFORE|GC_GET_COUNT@B|-|ALL4|U_GC|no
P_GC_AFTER|GC_GET_COUNT@A|-|ALL4|U_GC|no
P_GC_OP|GC_CALLBACK_ACCUMULATOR@C,A,G|CP_TARGET|ALL4|U_GC|no
P_STATIC_LINK|MANIFEST_IDENTITY_LINK@B,C,A,G,R|CP_TARGET|ALL4|U_STATIC|no
P_FRESH_STATE|DURABLE_GOVERNED_CLOCK_DERIVATION@B,C,A,R|CP_TARGET|ALL4|U_COUNTER|no
P_POLICY_ABSENT|NONE|-|ALL4|U_POLICY|no
P_FRESH_UNITS|DURABLE_PREFIX_REPLAY@C,A,G,R|CP_TARGET|ALL4|U_COUNTER|no
P_FRESH_LATENCY|DURABLE_GOVERNED_CLOCK_DERIVATION@C,A,G,R|CP_TARGET|ALL4|U_COUNTER|no
P_FRESH_ACK|A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R|CP_TARGET|ACK|U_COUNTER|no
P_FRESH_SHUTDOWN|A1_OUTCOME_CAPABILITY@C,A,G;DURABLE_PREFIX_REPLAY@R|CP_TARGET|SHUTDOWN|U_COUNTER|no
P_CANDIDATE_BOUND|DURABLE_GOVERNED_CLOCK_DERIVATION@A,G,R|-|ALL4|U_COUNTER|yes
P_TARGET_BOUND|DURABLE_GOVERNED_CLOCK_DERIVATION@A,G,R|-|ALL4|U_COUNTER|yes
P_MARKER_AGE|MARKER_ACCUMULATOR@A,G|-|ALL4|U_MARKER|no
""".strip().splitlines()


def _build_descriptor_profiles_v49f_v8() -> dict[str, _DescriptorProfileV49FV8]:
    role_aliases = {
        "A": CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION,
        "B": CapacityMeasurementObservationRoleV49FV8.BEFORE_OPERATION,
        "C": CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT,
        "G": CapacityMeasurementObservationRoleV49FV8.OPERATION_AGGREGATE,
        "R": CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY,
    }
    result: dict[str, _DescriptorProfileV49FV8] = {}
    for row in _RAW_V8_DESCRIPTOR_PROFILE_ROWS_V49F:
        cells = row.split("|")
        if len(cells) != 6:
            raise RuntimeError("invalid frozen Raw V8 descriptor profile row")
        profile_id, methods, checkpoints, operations, reasons, censoring = cells
        method_pairs: list[CapacityMeasurementObservationMethodRolePairV49FV8] = []
        if methods not in {"NONE", "ROW_SELECTED"}:
            for pair in methods.split(";"):
                method, role_text = pair.split("@", 1)
                method_pairs.append(
                    CapacityMeasurementObservationMethodRolePairV49FV8(
                        observation_method=CapacityMeasurementTargetObservationMethodV49FV8(
                            method
                        ),
                        allowed_roles=tuple(
                            sorted(
                                (role_aliases[value] for value in role_text.split(",")),
                                key=lambda value: value.value,
                            )
                        ),
                    )
                )
        operation_kinds = {
            "ALL4": _RAW_V8_ALL_OPERATION_KINDS_V49F,
            "ACK": (CapacityMeasurementOperationKindV49FV8.ACK_DEADLINE_EXPIRY,),
            "SHUTDOWN": (CapacityMeasurementOperationKindV49FV8.LOCAL_SHUTDOWN,),
        }[operations]
        result[profile_id] = _DescriptorProfileV49FV8(
            method_role_pairs=tuple(
                sorted(method_pairs, key=lambda value: value.observation_method.value)
            ),
            checkpoint_markers=(
                _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F
                if checkpoints == "CP_TARGET"
                else ()
            ),
            operation_kinds=operation_kinds,
            reason_profile=reasons,
            censoring_allowed=censoring == "yes",
        )
    if len(result) != 37:
        raise RuntimeError("Raw V8 descriptor profile inventory must contain 37 rows")
    return result


_RAW_V8_DESCRIPTOR_PROFILES_V49F = _build_descriptor_profiles_v49f_v8()


def _build_vocabulary_definitions_v49f_v8() -> tuple[
    CapacityMeasurementVocabularyDefinitionV49FV8, ...
]:
    sqlite_primary_results = tuple(
        value.value for value in CapacityMeasurementSQLitePrimaryResultV49FV8
    )
    definitions: dict[str, tuple[str, ...]] = {
        "RAW_V8_OPERATION_KIND": tuple(
            value.value for value in CapacityMeasurementOperationKindV49FV8
        ),
        "RAW_V8_OBSERVATION_ROLE": tuple(
            value.value for value in CapacityMeasurementObservationRoleV49FV8
        ),
        "RAW_V8_MARKER_KIND": tuple(
            value.value for value in CapacityMeasurementMarkerKindV49FV8
        ),
        "RAW_V8_FULL_CHECKPOINT_MARKER_KIND": tuple(
            value.value for value in _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F
        ),
        "RAW_V8_OBSERVATION_METHOD": tuple(
            value.value for value in CapacityMeasurementTargetObservationMethodV49FV8
        ),
        "RAW_V8_STATUS_REASON": tuple(
            value.value for value in CapacityMeasurementStatusReasonV49FV8
        ),
        "RAW_V8_AVAILABILITY": tuple(
            value.value for value in CapacityMeasurementTargetAvailabilityV49FV8
        ),
        "RAW_V8_OBSERVATION_ATTEMPT": tuple(
            value.value for value in CapacityMeasurementObservationAttemptV49FV8
        ),
        "RAW_V8_SOURCE_FAILURE_PHASE": tuple(
            value.value for value in CapacityMeasurementSourceFailurePhaseV49FV8
        ),
        "RAW_V8_ADAPTER_SPAN_STATUS": tuple(
            value.value for value in CapacityMeasurementAdapterSpanStatusV49FV8
        ),
        "RAW_V8_CLOCK_SPAN_STATUS": tuple(
            value.value for value in CapacityMeasurementClockSpanStatusV49FV8
        ),
        "RAW_V8_CLOCK_DOMAIN": tuple(
            value.value for value in CapacityMeasurementClockDomainV49FV8
        ),
        "RAW_V8_INSTRUMENTATION_MODE": tuple(
            value.value for value in CapacityMeasurementInstrumentationModeV49FV8
        ),
        "RAW_V8_CENSORING": tuple(
            value.value for value in CapacityMeasurementCensoringV49FV8
        ),
        "RAW_V8_VALUE_KIND": tuple(
            value.value for value in CapacityMeasurementTargetValueKindV49FV8
        ),
        "RAW_V8_DURATION_RELATION": tuple(
            value.value for value in CapacityMeasurementDurationRelationV49FV8
        ),
        "RAW_V8_LATER_ACTION": tuple(
            value.value for value in CapacityMeasurementLaterThresholdActionV49FV8
        ),
        "RAW_V8_A1_COMMAND_KIND": tuple(
            value.value for value in CapacityMeasurementOperationKindV49FV8
        ),
        "RAW_V8_A1_ADMISSION_OUTCOME": tuple(
            value.value for value in CapacityMeasurementA1AdmissionOutcomeV49FV8
        ),
        "RAW_V8_A1_REJECTION_CLASS": tuple(
            value.value for value in CapacityMeasurementA1RejectionClassV49FV8
        ),
        "RAW_V8_SQLITE_PRIMARY_RESULT": sqlite_primary_results,
        "RAW_V8_ACTOR_KIND_MAP_KEY": _RAW_V8_ACTOR_KIND_KEYS_V49F,
        "RAW_V8_SQLITE_STAGE_RESULT_MAP_KEY": (_RAW_V8_SQLITE_STAGE_RESULT_KEYS_V49F),
        "RAW_V8_GC_GENERATION_MAP_KEY": _RAW_V8_GC_GENERATION_KEYS_V49F,
        "RAW_V8_ERROR_FORM": tuple(
            value.value for value in CapacityMeasurementErrorFormV49FV8
        ),
    }
    if len(definitions) != 25:
        raise RuntimeError("Raw V8 registry must contain 25 vocabularies")
    return tuple(
        CapacityMeasurementVocabularyDefinitionV49FV8(
            vocabulary_id=vocabulary_id,
            members=tuple(sorted(members)),
        )
        for vocabulary_id, members in sorted(definitions.items())
    )


def _build_value_shape_definitions_v49f_v8() -> tuple[
    CapacityMeasurementValueShapeDefinitionV49FV8, ...
]:
    values = (
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="S",
            container_kind="SCALAR",
            minimum_items=None,
            maximum_items=None,
            ordered_keys=(),
        ),
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="L_A1_FIFO_4",
            container_kind="LIST",
            minimum_items=0,
            maximum_items=4,
            ordered_keys=(),
        ),
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="L_GC_GENERATIONS_3",
            container_kind="LIST",
            minimum_items=3,
            maximum_items=3,
            ordered_keys=(),
        ),
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="M_ACTOR_KINDS_25",
            container_kind="FIXED_MAP",
            minimum_items=25,
            maximum_items=25,
            ordered_keys=_RAW_V8_ACTOR_KIND_KEYS_V49F,
        ),
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="M_SQLITE_STAGE_RESULTS_32",
            container_kind="FIXED_MAP",
            minimum_items=32,
            maximum_items=32,
            ordered_keys=_RAW_V8_SQLITE_STAGE_RESULT_KEYS_V49F,
        ),
        CapacityMeasurementValueShapeDefinitionV49FV8(
            value_shape_id="M_GC_GENERATIONS_3",
            container_kind="FIXED_MAP",
            minimum_items=3,
            maximum_items=3,
            ordered_keys=_RAW_V8_GC_GENERATION_KEYS_V49F,
        ),
    )
    return tuple(sorted(values, key=lambda value: value.value_shape_id))


def _value_constraint_v49f_v8(
    value_constraint_id: str,
    value_kind: CapacityMeasurementTargetValueKindV49FV8,
    scalar_profile: str,
    *,
    vocabulary_id: str | None = None,
    integer_minimum: int | None = None,
    integer_maximum: int | None = None,
    text_minimum_utf8_bytes: int | None = None,
    text_maximum_utf8_bytes: int | None = None,
    text_ascii_pattern: str | None = None,
    decimal_maximum: str | None = None,
    collection_item_constraint_id: str | None = None,
    external_authority_profile: str | None = None,
) -> CapacityMeasurementValueConstraintDefinitionV49FV8:
    return CapacityMeasurementValueConstraintDefinitionV49FV8(
        value_constraint_id=value_constraint_id,
        value_kind=value_kind,
        scalar_profile=scalar_profile,
        vocabulary_id=vocabulary_id,
        integer_minimum=integer_minimum,
        integer_maximum=integer_maximum,
        text_minimum_utf8_bytes=text_minimum_utf8_bytes,
        text_maximum_utf8_bytes=text_maximum_utf8_bytes,
        text_ascii_pattern=text_ascii_pattern,
        decimal_maximum=decimal_maximum,
        collection_item_constraint_id=collection_item_constraint_id,
        external_authority_profile=external_authority_profile,
    )


def _build_value_constraint_definitions_v49f_v8() -> tuple[
    CapacityMeasurementValueConstraintDefinitionV49FV8, ...
]:
    safe_range = {"integer_minimum": 0, "integer_maximum": MAX_IJSON_INTEGER}
    sha_range = {
        "text_minimum_utf8_bytes": 64,
        "text_maximum_utf8_bytes": 64,
        "text_ascii_pattern": "[0-9a-f]{64}",
    }
    enum_range = {"text_minimum_utf8_bytes": 1, "text_maximum_utf8_bytes": 256}
    kind = CapacityMeasurementTargetValueKindV49FV8
    values = (
        _value_constraint_v49f_v8(
            "UINT_SAFE_IJSON", kind.UINT, "SAFE_IJSON_UINT", **safe_range
        ),
        _value_constraint_v49f_v8(
            "UINT_LOOP_PROBE_INTERVAL_NS",
            kind.UINT,
            "SAFE_IJSON_UINT",
            integer_minimum=1_000_000,
            integer_maximum=60_000_000_000,
        ),
        _value_constraint_v49f_v8(
            "OPTIONAL_UINT_SAFE_IJSON",
            kind.OPTIONAL_UINT,
            "SAFE_IJSON_UINT",
            **safe_range,
        ),
        _value_constraint_v49f_v8("BOOL_EXACT", kind.BOOL, "EXACT_BOOL"),
        _value_constraint_v49f_v8("TEXT_SHA256", kind.TEXT, "SHA256", **sha_range),
        _value_constraint_v49f_v8(
            "OPTIONAL_TEXT_SHA256", kind.OPTIONAL_TEXT, "SHA256", **sha_range
        ),
        _value_constraint_v49f_v8(
            "OPTIONAL_TEXT_UINT128_DECIMAL",
            kind.OPTIONAL_TEXT,
            "UINT128_DECIMAL",
            text_minimum_utf8_bytes=1,
            text_maximum_utf8_bytes=39,
            text_ascii_pattern="0|[1-9][0-9]*",
            decimal_maximum="340282366920938463463374607431768211455",
        ),
        _value_constraint_v49f_v8(
            "OPTIONAL_TEXT_PLATFORM_ERRNO",
            kind.OPTIONAL_TEXT,
            "PLATFORM_ERRNO",
            text_minimum_utf8_bytes=1,
            text_maximum_utf8_bytes=64,
            text_ascii_pattern="[A-Z][A-Z0-9_]{0,63}",
            external_authority_profile=(
                "MANIFEST_BOUND_PLATFORM_ERRNO_MAP_AND_DURABLE_SEND_PREFIX_V1"
            ),
        ),
        _value_constraint_v49f_v8(
            "UINT_LIST_SAFE_IJSON",
            kind.UINT_LIST,
            "SAFE_IJSON_COLLECTION",
            collection_item_constraint_id="UINT_SAFE_IJSON",
            **safe_range,
        ),
        _value_constraint_v49f_v8(
            "FIXED_UINT_MAP_SAFE_IJSON",
            kind.FIXED_UINT_MAP,
            "SAFE_IJSON_COLLECTION",
            collection_item_constraint_id="UINT_SAFE_IJSON",
            **safe_range,
        ),
        _value_constraint_v49f_v8(
            "DURATION_BOUND_SAFE_IJSON",
            kind.DURATION_BOUND,
            "DURATION_BOUND",
            **safe_range,
        ),
        _value_constraint_v49f_v8(
            "TEXT_ENUM_A1_COMMAND_KIND",
            kind.TEXT,
            "ENUM",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            **enum_range,
        ),
        _value_constraint_v49f_v8(
            "OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND",
            kind.OPTIONAL_TEXT,
            "ENUM",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            **enum_range,
        ),
        _value_constraint_v49f_v8(
            "TEXT_LIST_ENUM_A1_COMMAND_KIND",
            kind.TEXT_LIST,
            "SAFE_IJSON_COLLECTION",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            collection_item_constraint_id="TEXT_ENUM_A1_COMMAND_KIND",
            **enum_range,
        ),
        _value_constraint_v49f_v8(
            "TEXT_ENUM_A1_ADMISSION_OUTCOME",
            kind.TEXT,
            "ENUM",
            vocabulary_id="RAW_V8_A1_ADMISSION_OUTCOME",
            **enum_range,
        ),
        _value_constraint_v49f_v8(
            "OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS",
            kind.OPTIONAL_TEXT,
            "ENUM",
            vocabulary_id="RAW_V8_A1_REJECTION_CLASS",
            **enum_range,
        ),
        _value_constraint_v49f_v8(
            "TEXT_ENUM_SQLITE_PRIMARY_RESULT",
            kind.TEXT,
            "ENUM",
            vocabulary_id="RAW_V8_SQLITE_PRIMARY_RESULT",
            **enum_range,
        ),
    )
    if len(values) != 17:
        raise RuntimeError("Raw V8 registry must contain 17 value constraints")
    return tuple(sorted(values, key=lambda value: value.value_constraint_id))


def _attempt_state_rule_v49f_v8(
    attempt: CapacityMeasurementObservationAttemptV49FV8,
    forms: tuple[CapacityMeasurementErrorFormV49FV8, ...],
    phases: tuple[CapacityMeasurementSourceFailurePhaseV49FV8, ...],
    span_policy: str,
) -> CapacityMeasurementAttemptStateErrorFormsV49FV8:
    return CapacityMeasurementAttemptStateErrorFormsV49FV8(
        attempt_state=attempt,
        permitted_error_forms=tuple(sorted(forms, key=lambda value: value.value)),
        permitted_failure_phases=tuple(sorted(phases, key=lambda value: value.value)),
        adapter_span_policy=span_policy,
    )


def _build_status_reason_policy_definition_v49f_v8() -> (
    CapacityMeasurementStatusReasonPolicyDefinitionV49FV8
):
    availability = CapacityMeasurementTargetAvailabilityV49FV8
    availability_rules = tuple(
        sorted(
            (
                CapacityMeasurementAvailabilityStateRuleV49FV8(
                    availability=availability.AVAILABLE,
                    value_policy="REQUIRED",
                    reason_policy="FORBIDDEN",
                    censoring_policy="NONE_ONLY",
                    attempt_policy="ATTEMPTED_ONLY",
                    adapter_span_policy="AVAILABLE_ONLY",
                ),
                CapacityMeasurementAvailabilityStateRuleV49FV8(
                    availability=availability.CENSORED,
                    value_policy="DURATION_BOUND_REQUIRED",
                    reason_policy="FORBIDDEN",
                    censoring_policy="DESCRIPTOR_BOUND_MAPPING",
                    attempt_policy="ATTEMPTED_ONLY",
                    adapter_span_policy="AVAILABLE_ONLY",
                ),
                CapacityMeasurementAvailabilityStateRuleV49FV8(
                    availability=availability.NOT_APPLICABLE,
                    value_policy="FORBIDDEN",
                    reason_policy="NOT_APPLICABLE_REQUIRED",
                    censoring_policy="NONE_ONLY",
                    attempt_policy="NOT_ATTEMPTED_ONLY",
                    adapter_span_policy="NOT_APPLICABLE_ONLY",
                ),
                CapacityMeasurementAvailabilityStateRuleV49FV8(
                    availability=availability.UNAVAILABLE,
                    value_policy="FORBIDDEN",
                    reason_policy="UNAVAILABLE_REQUIRED",
                    censoring_policy="NONE_ONLY",
                    attempt_policy="REASON_RULE",
                    adapter_span_policy="REASON_RULE",
                ),
            ),
            key=lambda value: value.availability.value,
        )
    )
    attempt = CapacityMeasurementObservationAttemptV49FV8
    form = CapacityMeasurementErrorFormV49FV8
    phase = CapacityMeasurementSourceFailurePhaseV49FV8

    def not_attempted(
        *, failure_phase: CapacityMeasurementSourceFailurePhaseV49FV8 = phase.NONE
    ) -> CapacityMeasurementAttemptStateErrorFormsV49FV8:
        return _attempt_state_rule_v49f_v8(
            attempt.NOT_ATTEMPTED,
            (form.NONE,),
            (failure_phase,),
            "NOT_APPLICABLE_ONLY",
        )

    def attempted(
        forms: tuple[CapacityMeasurementErrorFormV49FV8, ...],
        phases: tuple[CapacityMeasurementSourceFailurePhaseV49FV8, ...],
        *,
        span: str = "AVAILABLE_ONLY",
    ) -> CapacityMeasurementAttemptStateErrorFormsV49FV8:
        return _attempt_state_rule_v49f_v8(attempt.ATTEMPTED, forms, phases, span)

    reason_states: dict[
        CapacityMeasurementStatusReasonV49FV8,
        tuple[CapacityMeasurementAttemptStateErrorFormsV49FV8, ...],
    ] = {}
    for name in (
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
        reason_states[CapacityMeasurementStatusReasonV49FV8(name)] = (not_attempted(),)
    for name in ("UNSUPPORTED_BY_KERNEL", "PERMISSION_DENIED", "OS_OBSERVATION_ERROR"):
        reason_states[CapacityMeasurementStatusReasonV49FV8(name)] = (
            attempted((form.OS,), (phase.SOURCE_ADAPTER,)),
        )
    for name in (
        "MARKER_RING_OVERWROTE_PREFIX",
        "PERIODIC_PROBE_DID_NOT_FIRE",
        "PROBE_RING_OVERWROTE_PREFIX",
        "ARTIFACT_BOUND_EXCEEDED",
    ):
        reason_states[CapacityMeasurementStatusReasonV49FV8(name)] = (
            attempted((form.STATUS_ONLY,), (phase.NONE,)),
        )
    reason_states[
        CapacityMeasurementStatusReasonV49FV8.UNSUPPORTED_BY_PYTHON_RUNTIME
    ] = (
        attempted((form.NON_OS,), (phase.SOURCE_ADAPTER,)),
        not_attempted(),
    )
    reason_states[CapacityMeasurementStatusReasonV49FV8.OBSERVER_INTERNAL_ERROR] = (
        attempted(
            (form.NON_OS,),
            (phase.SOURCE_ADAPTER, phase.VALUE_VALIDATION),
        ),
    )
    reason_states[CapacityMeasurementStatusReasonV49FV8.SOURCE_CLOCK_UNAVAILABLE] = (
        attempted(
            (form.NON_OS, form.OS),
            (phase.SECOND_CLOCK_READ,),
            span="UNAVAILABLE_ONLY",
        ),
        not_attempted(failure_phase=phase.FIRST_CLOCK_READ),
    )
    if set(reason_states) != set(CapacityMeasurementStatusReasonV49FV8):
        raise RuntimeError("Raw V8 status-reason policy coverage differs")
    reason_rules: list[CapacityMeasurementStatusReasonRuleV49FV8] = []
    for reason, states in reason_states.items():
        if reason is CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_OPERATION:
            required = availability.NOT_APPLICABLE
            predicate: str | None = "OPERATION_EXCLUDED"
        elif (
            reason
            is CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_REACHED_STATE
        ):
            required = availability.NOT_APPLICABLE
            predicate = "REACHED_STATE_EXCLUDED"
        elif (
            reason
            is CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED
        ):
            required = availability.UNAVAILABLE
            predicate = "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND"
        elif (
            reason
            is CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
        ):
            required = availability.UNAVAILABLE
            predicate = "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
        elif (
            reason
            is CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE
        ):
            required = availability.UNAVAILABLE
            predicate = "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
        elif (
            reason
            is CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED
        ):
            required = availability.UNAVAILABLE
            predicate = "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
        else:
            required = availability.UNAVAILABLE
            predicate = None
        reason_rules.append(
            CapacityMeasurementStatusReasonRuleV49FV8(
                reason=reason,
                required_availability=required,
                context_predicate=predicate,
                attempt_state_error_forms=tuple(
                    sorted(states, key=lambda value: value.attempt_state.value)
                ),
            )
        )
    error_definitions = (
        CapacityMeasurementErrorFormDefinitionV49FV8(
            error_form=form.NONE,
            errno_pair_policy="FORBIDDEN",
            error_class_policy="FORBIDDEN",
            error_digest_policy="FORBIDDEN",
            class_digest_pair_policy="BOTH_FORBIDDEN",
        ),
        CapacityMeasurementErrorFormDefinitionV49FV8(
            error_form=form.NON_OS,
            errno_pair_policy="FORBIDDEN",
            error_class_policy="REQUIRED",
            error_digest_policy="REQUIRED",
            class_digest_pair_policy="BOTH_REQUIRED",
        ),
        CapacityMeasurementErrorFormDefinitionV49FV8(
            error_form=form.OS,
            errno_pair_policy="REQUIRED",
            error_class_policy="OPTIONAL",
            error_digest_policy="OPTIONAL",
            class_digest_pair_policy="BOTH_OR_NEITHER",
        ),
        CapacityMeasurementErrorFormDefinitionV49FV8(
            error_form=form.STATUS_ONLY,
            errno_pair_policy="FORBIDDEN",
            error_class_policy="FORBIDDEN",
            error_digest_policy="FORBIDDEN",
            class_digest_pair_policy="BOTH_FORBIDDEN",
        ),
    )
    return CapacityMeasurementStatusReasonPolicyDefinitionV49FV8(
        status_reason_policy_id=RAW_V8_STATUS_REASON_POLICY_ID_V49F,
        availability_state_rules=availability_rules,
        reason_rules=tuple(sorted(reason_rules, key=lambda value: value.reason.value)),
        error_form_definitions=error_definitions,
    )


_RAW_V8_TARGET_FIELD_ROWS_V49F = """
a1.policy_id|text / identity|P_A1_POINT|S
a1.epoch|uint / epoch|P_A1_POINT|S
a1.closed|bool / state|P_A1_POINT|S
a1.terminal_barrier_sequence|optional uint / admission|P_A1_POINT|S
a1.terminal_barrier_committed|bool / state|P_A1_POINT|S
a1.active_count|uint / commands|P_A1_POINT|S
a1.active_sequence|optional uint / admission|P_A1_POINT|S
a1.active_kind|optional text / enum|P_A1_POINT|S
a1.waiting_count|uint / commands|P_A1_POINT|S
a1.waiting_sequences|uint-list / admissions|P_A1_POINT|L_A1_FIFO_4
a1.waiting_kinds|text-list / enums|P_A1_POINT|L_A1_FIFO_4
a1.oldest_waiting_age_ns|uint / ns|P_A1_POINT|S
a1.reserved_work_units|uint / abstract work|P_A1_POINT|S
a1.maximum_observed_admitted_commands|uint / commands|P_A1_POINT|S
a1.maximum_observed_reserved_work_units|uint / abstract work|P_A1_POINT|S
a1.last_started_queue_wait_ns|optional uint / ns|P_A1_POINT|S
a1.maximum_observed_queue_wait_ns|uint / ns|P_A1_POINT|S
a1.released_commands|uint / commands|P_A1_POINT|S
a1.rejected_commands|uint / commands|P_A1_POINT|S
a1.duplicate_kind_rejections|uint / commands|P_A1_POINT|S
a1.terminal_barrier_rejections|uint / commands|P_A1_POINT|S
a1.capacity_rejections|uint / commands|P_A1_POINT|S
a1.closed_rejections|uint / commands|P_A1_POINT|S
a1.timed_out_commands|uint / commands|P_A1_POINT|S
a1.cancelled_before_entry_commands|uint / commands|P_A1_POINT|S
a1.closed_before_entry_commands|uint / commands|P_A1_POINT|S
a1.target_admission_outcome|text / enum|P_A1_OUTCOME|S
a1.target_admission_sequence|optional uint / admission|P_A1_OUTCOME|S
a1.target_command_kind|text / enum|P_A1_OUTCOME|S
a1.target_reservation_work_units|uint / abstract work|P_A1_OUTCOME|S
a1.target_admitted_loop_time_ns|optional text / absolute ns|P_A1_OUTCOME|S
a1.target_started_loop_time_ns|optional text / absolute ns|P_A1_OUTCOME|S
a1.target_start_deadline_loop_time_ns|optional text / absolute ns|P_A1_OUTCOME|S
a1.target_queue_wait_ns|duration bound / ns|P_A1_BOUND|S
a1.target_rejection_class|optional text / enum|P_A1_OUTCOME|S
kernel.socket_identity|text / hash|P_KERNEL_ID|S
kernel.so_rcvbuf_literal_octets|uint / bytes|P_KERNEL_SOCKOPT|S
kernel.so_sndbuf_literal_octets|uint / bytes|P_KERNEL_SOCKOPT|S
kernel.siocinq_unread_octets|uint / bytes|P_KERNEL_IOCTL|S
kernel.siocoutq_unsent_octets|uint / bytes|P_KERNEL_IOCTL|S
kernel.read_poll_mask|uint / bit mask|P_KERNEL_POLL|S
kernel.write_poll_mask|uint / bit mask|P_KERNEL_POLL|S
kernel.read_ready|bool / state|P_POINT_DERIVED|S
kernel.write_ready|bool / state|P_POINT_DERIVED|S
kernel.operation_recv_calls|uint / calls|P_OP_ACCUM|S
kernel.operation_recv_ciphertext_octets|uint / bytes|P_OP_ACCUM|S
kernel.operation_send_attempts|uint / attempts|P_OP_DURABLE|S
kernel.operation_send_positive_results|uint / results|P_OP_DURABLE|S
kernel.operation_send_accepted_octets|uint / bytes|P_OP_DURABLE|S
kernel.operation_send_failures|uint / failures|P_OP_DURABLE|S
kernel.operation_last_send_errno|optional text / errno|P_OP_DURABLE|S
tls.incoming_memory_bio_pending_octets|uint / bytes|P_TLS_POINT|S
tls.outgoing_memory_bio_pending_octets|uint / bytes|P_TLS_POINT|S
tls.ssl_plaintext_pending_octets|uint / bytes|P_TLS_POINT|S
tls.operation_read_calls|uint / calls|P_OP_ACCUM|S
tls.operation_ciphertext_fed_octets|uint / bytes|P_OP_ACCUM|S
tls.operation_plaintext_produced_octets|uint / bytes|P_OP_ACCUM|S
tls.operation_write_calls|uint / calls|P_OP_ACCUM|S
tls.operation_plaintext_accepted_octets|uint / bytes|P_OP_ACCUM|S
tls.operation_ciphertext_produced_octets|uint / bytes|P_OP_ACCUM|S
tls.operation_want_read_count|uint / exceptions|P_OP_ACCUM|S
tls.operation_want_write_count|uint / exceptions|P_OP_ACCUM|S
tls.protocol_output_chunks|uint / chunks|P_TLS_POINT|S
tls.protocol_output_octets|uint / bytes|P_TLS_POINT|S
tls.staged_websocket_wire_chunks|uint / chunks|P_TLS_POINT|S
tls.staged_websocket_wire_octets|uint / bytes|P_TLS_POINT|S
tls.pending_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.remaining_pending_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.staged_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.remaining_staged_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.staged_control_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.remaining_staged_control_ciphertext_octets|uint / bytes|P_TLS_POINT|S
tls.pending_send_eof|bool / state|P_TLS_POINT|S
ingress.pending_raw_chunks|uint / chunks|P_INGRESS_POINT|S
ingress.pending_raw_octets|uint / bytes|P_INGRESS_POINT|S
ingress.durable_buffer_octets|uint / bytes|P_INGRESS_POINT|S
ingress.has_complete_durable_unit|bool / state|P_INGRESS_POINT|S
ingress.retained_incomplete_tail_octets|uint / bytes|P_INGRESS_POINT|S
ingress.oldest_unparsed_raw_age_boottime_ns|uint / ns|P_INGRESS_POINT|S
ingress.oldest_unparsed_raw_commit_id|optional text / hash|P_INGRESS_POINT|S
ingress.latest_raw_sequence|optional uint / RAW sequence|P_INGRESS_POINT|S
ingress.latest_raw_commit_id|optional text / hash|P_INGRESS_POINT|S
ingress.operation_new_raw_count|uint / RAW records|P_OP_DURABLE|S
ingress.operation_new_raw_octets|uint / bytes|P_OP_DURABLE|S
parser.operation_units|uint / units|P_OP_DURABLE|S
parser.operation_complete_frames|uint / frames|P_OP_DURABLE|S
parser.operation_error_units|uint / errors|P_OP_DURABLE|S
parser.operation_source_octets|uint / bytes|P_OP_DURABLE|S
parser.operation_payload_octets|uint / bytes|P_OP_DURABLE|S
parser.operation_fragment_units|uint / fragments|P_OP_DURABLE|S
parser.current_fragment_payload_octets|uint / bytes|P_PARSER_POINT|S
parser.operation_application_completions|uint / messages|P_OP_DURABLE|S
parser.operation_automatic_output_chunks|uint / chunks|P_OP_DURABLE|S
parser.operation_automatic_output_octets|uint / bytes|P_OP_DURABLE|S
parser.last_unit_elapsed_ns|uint / ns|P_OP_ACCUM|S
parser.total_unit_elapsed_ns|uint / ns|P_OP_ACCUM|S
parser.maximum_unit_elapsed_ns|uint / ns|P_OP_ACCUM|S
parser.last_unit_thread_cpu_ns|uint / ns|P_OP_ACCUM|S
parser.total_unit_thread_cpu_ns|uint / ns|P_OP_ACCUM|S
parser.maximum_unit_thread_cpu_ns|uint / ns|P_OP_ACCUM|S
actor.event_count|uint / events|P_ACTOR_POINT|S
actor.tail_event_id|optional text / hash|P_ACTOR_POINT|S
actor.event_kind_counts|fixed uint map / events|P_ACTOR_POINT|M_ACTOR_KINDS_25
actor.operation_single_append_calls|uint / calls|P_OP_ACCUM|S
actor.operation_batch_append_calls|uint / calls|P_OP_ACCUM|S
actor.operation_appended_events|uint / events|P_OP_DURABLE|S
actor.single_append_total_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.single_append_maximum_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.batch_append_total_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.batch_append_maximum_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.validation_total_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.validation_maximum_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.rebuild_total_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.rebuild_maximum_elapsed_ns|uint / ns|P_OP_ACCUM|S
actor.pending_wire_obligations|uint / events|P_ACTOR_POINT|S
actor.pending_wire_octets|uint / bytes|P_ACTOR_POINT|S
actor.pending_control_obligations|uint / events|P_ACTOR_POINT|S
actor.pending_control_octets|uint / bytes|P_ACTOR_POINT|S
actor.oldest_wire_obligation_age_boottime_ns|uint / ns|P_ACTOR_POINT|S
sqlite.busy_timeout_milliseconds|uint / ms|P_SQLITE_CONFIG|S
sqlite.operation_transactions_attempted|uint / transactions|P_SQLITE_OP|S
sqlite.operation_transactions_begun|uint / transactions|P_SQLITE_OP|S
sqlite.operation_transactions_committed|uint / transactions|P_SQLITE_OP|S
sqlite.operation_rollbacks_attempted|uint / transactions|P_SQLITE_OP|S
sqlite.operation_transactions_rolled_back|uint / transactions|P_SQLITE_OP|S
sqlite.operation_transactions_uncertain|uint / transactions|P_SQLITE_OP|S
sqlite.begin_total_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.begin_maximum_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.body_total_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.body_maximum_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.commit_total_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.commit_maximum_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.rollback_total_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.rollback_maximum_elapsed_ns|uint / ns|P_SQLITE_OP|S
sqlite.result_class_counts|fixed uint map / results|P_SQLITE_OP|M_SQLITE_STAGE_RESULTS_32
sqlite.last_primary_result_class|text / enum|P_SQLITE_OP|S
sqlite.operation_rows_written|uint / rows|P_SQLITE_OP|S
sqlite.operation_canonical_record_octets|uint / bytes|P_SQLITE_OP|S
sqlite.database_file_octets|uint / bytes|P_SQLITE_FILE|S
sqlite.journal_file_octets|uint / bytes|P_SQLITE_FILE|S
sqlite.wal_file_octets|uint / bytes|P_SQLITE_FILE|S
sqlite.shm_file_octets|uint / bytes|P_SQLITE_FILE|S
sqlite.page_count|uint / pages|P_SQLITE_PRAGMA|S
sqlite.freelist_count|uint / pages|P_SQLITE_PRAGMA|S
loop.probe_interval_ns|uint / ns|P_LOOP_STATIC|S
loop.probes_scheduled|uint / callbacks|P_LOOP_OP|S
loop.probes_fired|uint / callbacks|P_LOOP_OP|S
loop.probe_phases_missed|uint / phases|P_LOOP_OP|S
loop.probe_last_delay_ns|duration bound / ns|P_LOOP_BOUND|S
loop.probe_total_delay_ns|uint / ns|P_LOOP_OP|S
loop.probe_maximum_delay_ns|uint / ns|P_LOOP_OP|S
loop.final_unfired_delay_lower_bound_ns|duration bound / ns|P_LOOP_BOUND|S
loop.debug_enabled|bool / state|P_LOOP_CONFIG|S
loop.slow_callback_threshold_ns|uint / ns|P_LOOP_CONFIG|S
loop.slow_callback_events|uint / callbacks|P_LOOP_OP|S
loop.probe_ring_overwritten|uint / callbacks|P_LOOP_OP|S
process.rss_approximate_octets|uint / bytes|P_PROCESS_POINT(PROCFS_STATM)|S
process.pss_rollup_octets|uint / bytes|P_PROCESS_POINT(PROCFS_SMAPS_ROLLUP)|S
process.rss_high_water_octets|uint / bytes|P_PROCESS_POINT(PROCFS_STATUS)|S
process.cgroup_memory_current_octets|uint / bytes|P_PROCESS_POINT(CGROUP_V2_MEMORY_CURRENT)|S
process.operation_process_cpu_ns|uint / ns|P_PROCESS_CPU(PROCESS_CPU_CLOCK)|S
process.operation_owner_thread_cpu_ns|uint / ns|P_PROCESS_CPU(OWNER_THREAD_CPU_CLOCK)|S
process.gc_count_before|uint-list / generation counters|P_GC_BEFORE|L_GC_GENERATIONS_3
process.gc_count_after|uint-list / generation counters|P_GC_AFTER|L_GC_GENERATIONS_3
process.gc_collections_by_generation|fixed uint map / collections|P_GC_OP|M_GC_GENERATIONS_3
process.gc_collected_objects_by_generation|fixed uint map / objects|P_GC_OP|M_GC_GENERATIONS_3
process.gc_uncollectable_by_generation|fixed uint map / objects|P_GC_OP|M_GC_GENERATIONS_3
process.gc_pause_count|uint / pauses|P_GC_OP|S
process.gc_pause_total_elapsed_ns|uint / ns|P_GC_OP|S
process.gc_pause_maximum_elapsed_ns|uint / ns|P_GC_OP|S
process.runtime_environment_id|text / identity|P_STATIC_LINK|S
process.filesystem_mount_cgroup_identity_id|text / identity|P_STATIC_LINK|S
freshness.oldest_unparsed_durable_byte_age_boottime_ns|uint / ns|P_FRESH_STATE|S
freshness.analysis_pressure_episode_age_boottime_ns|uint / ns|P_POLICY_ABSENT|S
freshness.ping_units|uint / controls|P_FRESH_UNITS|S
freshness.ping_to_pong_terminal_last_ns|uint / ns|P_FRESH_LATENCY|S
freshness.ping_to_pong_terminal_maximum_ns|uint / ns|P_FRESH_LATENCY|S
freshness.close_units|uint / controls|P_FRESH_UNITS|S
freshness.close_to_response_terminal_last_ns|uint / ns|P_FRESH_LATENCY|S
freshness.close_to_response_terminal_maximum_ns|uint / ns|P_FRESH_LATENCY|S
freshness.ack_command_queue_wait_ns|uint / ns|P_FRESH_ACK|S
freshness.shutdown_command_queue_wait_ns|uint / ns|P_FRESH_SHUTDOWN|S
freshness.candidate_elapsed_boottime_ns|duration bound / ns|P_CANDIDATE_BOUND|S
freshness.target_effect_elapsed_boottime_ns|duration bound / ns|P_TARGET_BOUND|S
freshness.marker_last_age_at_terminal_ns|uint / ns|P_MARKER_AGE|S
""".strip().splitlines()


_RAW_V8_ATTEMPT_REQUIRED_PROFILE_IDS_V49F = frozenset(
    {
        "P_FRESH_LATENCY",
        "P_FRESH_UNITS",
        "P_GC_OP",
        "P_LOOP_BOUND",
        "P_LOOP_OP",
        "P_OP_ACCUM",
        "P_OP_DURABLE",
        "P_PROCESS_CPU",
        "P_SQLITE_OP",
    }
)
RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F = tuple(
    """
actor.batch_append_maximum_elapsed_ns
actor.batch_append_total_elapsed_ns
actor.operation_appended_events
actor.operation_batch_append_calls
actor.operation_single_append_calls
actor.rebuild_maximum_elapsed_ns
actor.rebuild_total_elapsed_ns
actor.single_append_maximum_elapsed_ns
actor.single_append_total_elapsed_ns
actor.validation_maximum_elapsed_ns
actor.validation_total_elapsed_ns
freshness.close_to_response_terminal_last_ns
freshness.close_to_response_terminal_maximum_ns
freshness.close_units
freshness.ping_to_pong_terminal_last_ns
freshness.ping_to_pong_terminal_maximum_ns
freshness.ping_units
freshness.target_effect_elapsed_boottime_ns
ingress.operation_new_raw_count
ingress.operation_new_raw_octets
kernel.operation_last_send_errno
kernel.operation_recv_calls
kernel.operation_recv_ciphertext_octets
kernel.operation_send_accepted_octets
kernel.operation_send_attempts
kernel.operation_send_failures
kernel.operation_send_positive_results
loop.final_unfired_delay_lower_bound_ns
loop.probe_last_delay_ns
loop.probe_maximum_delay_ns
loop.probe_phases_missed
loop.probe_ring_overwritten
loop.probe_total_delay_ns
loop.probes_fired
loop.probes_scheduled
loop.slow_callback_events
parser.last_unit_elapsed_ns
parser.last_unit_thread_cpu_ns
parser.maximum_unit_elapsed_ns
parser.maximum_unit_thread_cpu_ns
parser.operation_application_completions
parser.operation_automatic_output_chunks
parser.operation_automatic_output_octets
parser.operation_complete_frames
parser.operation_error_units
parser.operation_fragment_units
parser.operation_payload_octets
parser.operation_source_octets
parser.operation_units
parser.total_unit_elapsed_ns
parser.total_unit_thread_cpu_ns
process.gc_collected_objects_by_generation
process.gc_collections_by_generation
process.gc_pause_count
process.gc_pause_maximum_elapsed_ns
process.gc_pause_total_elapsed_ns
process.gc_uncollectable_by_generation
process.operation_owner_thread_cpu_ns
process.operation_process_cpu_ns
sqlite.begin_maximum_elapsed_ns
sqlite.begin_total_elapsed_ns
sqlite.body_maximum_elapsed_ns
sqlite.body_total_elapsed_ns
sqlite.commit_maximum_elapsed_ns
sqlite.commit_total_elapsed_ns
sqlite.last_primary_result_class
sqlite.operation_canonical_record_octets
sqlite.operation_rollbacks_attempted
sqlite.operation_rows_written
sqlite.operation_transactions_attempted
sqlite.operation_transactions_begun
sqlite.operation_transactions_committed
sqlite.operation_transactions_rolled_back
sqlite.operation_transactions_uncertain
sqlite.result_class_counts
sqlite.rollback_maximum_elapsed_ns
sqlite.rollback_total_elapsed_ns
tls.operation_ciphertext_fed_octets
tls.operation_ciphertext_produced_octets
tls.operation_plaintext_accepted_octets
tls.operation_plaintext_produced_octets
tls.operation_read_calls
tls.operation_want_read_count
tls.operation_want_write_count
tls.operation_write_calls
""".strip().splitlines()
)
RAW_V8_ATTEMPT_REQUIRED_FIELD_COUNT_V49F = len(RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F)
_RAW_V8_ATTEMPT_REQUIRED_FIELD_ID_SET_V49F = frozenset(
    RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F
)


def _derive_attempt_required_field_ids_v49f_v8() -> tuple[str, ...]:
    field_ids: list[str] = []
    for row in _RAW_V8_TARGET_FIELD_ROWS_V49F:
        field_id, _, profile_spelling, _ = row.split("|")
        profile_id = profile_spelling.split("(", 1)[0]
        if (
            profile_id in _RAW_V8_ATTEMPT_REQUIRED_PROFILE_IDS_V49F
            or field_id == "freshness.target_effect_elapsed_boottime_ns"
        ):
            field_ids.append(field_id)
    return tuple(sorted(field_ids))


if (
    RAW_V8_ATTEMPT_REQUIRED_FIELD_COUNT_V49F != 85
    or RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F
    != tuple(sorted(RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F))
    or len(_RAW_V8_ATTEMPT_REQUIRED_FIELD_ID_SET_V49F) != 85
    or RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F
    != _derive_attempt_required_field_ids_v49f_v8()
):
    raise RuntimeError("Raw V8 attempt-required field inventory differs")


def _normalize_descriptor_token_v49f_v8(value: str) -> str:
    if type(value) is not str or not value or not value.isascii():
        raise RuntimeError("Raw V8 descriptor token must be nonempty ASCII")
    return re.sub(r"[ -]+", "_", value.upper())


def _constraint_id_for_field_v49f_v8(
    *, field_id: str, value_kind: str, unit: str
) -> str:
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
    direct = {
        "UINT": "UINT_SAFE_IJSON",
        "BOOL": "BOOL_EXACT",
        "OPTIONAL_UINT": "OPTIONAL_UINT_SAFE_IJSON",
        "UINT_LIST": "UINT_LIST_SAFE_IJSON",
        "FIXED_UINT_MAP": "FIXED_UINT_MAP_SAFE_IJSON",
        "DURATION_BOUND": "DURATION_BOUND_SAFE_IJSON",
    }
    if value_kind in direct:
        return direct[value_kind]
    if value_kind == "TEXT" and unit in {"IDENTITY", "HASH"}:
        return "TEXT_SHA256"
    if value_kind == "OPTIONAL_TEXT" and unit in {"IDENTITY", "HASH"}:
        return "OPTIONAL_TEXT_SHA256"
    if value_kind == "OPTIONAL_TEXT" and unit == "ABSOLUTE_NS":
        return "OPTIONAL_TEXT_UINT128_DECIMAL"
    if value_kind == "OPTIONAL_TEXT" and unit == "ERRNO":
        return "OPTIONAL_TEXT_PLATFORM_ERRNO"
    raise RuntimeError(f"Raw V8 has no constraint for {field_id}")


def _profile_for_field_v49f_v8(profile_spelling: str) -> _DescriptorProfileV49FV8:
    match = re.fullmatch(
        r"(P_PROCESS_POINT|P_PROCESS_CPU)\(([A-Z0-9_]+)\)", profile_spelling
    )
    if match is None:
        try:
            return _RAW_V8_DESCRIPTOR_PROFILES_V49F[profile_spelling]
        except KeyError as exc:
            raise RuntimeError("unknown Raw V8 descriptor profile") from exc
    profile_id, method_text = match.groups()
    admitted = {
        "P_PROCESS_POINT": {
            "CGROUP_V2_MEMORY_CURRENT",
            "PROCFS_SMAPS_ROLLUP",
            "PROCFS_STATM",
            "PROCFS_STATUS",
        },
        "P_PROCESS_CPU": {"OWNER_THREAD_CPU_CLOCK", "PROCESS_CPU_CLOCK"},
    }
    if method_text not in admitted[profile_id]:
        raise RuntimeError("unsupported Raw V8 row-selected method")
    roles = (
        (
            CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION,
            CapacityMeasurementObservationRoleV49FV8.BEFORE_OPERATION,
            CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT,
            CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY,
        )
        if profile_id == "P_PROCESS_POINT"
        else (
            CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION,
            CapacityMeasurementObservationRoleV49FV8.OPERATION_AGGREGATE,
            CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT,
        )
    )
    template = _RAW_V8_DESCRIPTOR_PROFILES_V49F[profile_id]
    return _DescriptorProfileV49FV8(
        method_role_pairs=(
            CapacityMeasurementObservationMethodRolePairV49FV8(
                observation_method=CapacityMeasurementTargetObservationMethodV49FV8(
                    method_text
                ),
                allowed_roles=roles,
            ),
        ),
        checkpoint_markers=template.checkpoint_markers,
        operation_kinds=template.operation_kinds,
        reason_profile=template.reason_profile,
        censoring_allowed=template.censoring_allowed,
    )


def _build_target_field_descriptors_v49f_v8(
    shape_definitions: tuple[CapacityMeasurementValueShapeDefinitionV49FV8, ...],
) -> tuple[CapacityMeasurementTargetFieldDescriptorV49FV8, ...]:
    shapes = {value.value_shape_id: value for value in shape_definitions}
    descriptors: list[CapacityMeasurementTargetFieldDescriptorV49FV8] = []
    cross_fields = {
        "a1.waiting_count",
        "a1.waiting_sequences",
        "a1.waiting_kinds",
    }
    for row in _RAW_V8_TARGET_FIELD_ROWS_V49F:
        cells = row.split("|")
        if len(cells) != 4 or cells[1].count(" / ") != 1:
            raise RuntimeError("invalid frozen Raw V8 target-field row")
        field_id, value_unit, profile_spelling, shape_id = cells
        raw_kind, raw_unit = value_unit.split(" / ")
        value_kind = _normalize_descriptor_token_v49f_v8(raw_kind)
        unit = _normalize_descriptor_token_v49f_v8(raw_unit)
        profile = _profile_for_field_v49f_v8(profile_spelling)
        shape = shapes[shape_id]
        reasons = tuple(
            CapacityMeasurementStatusReasonV49FV8(value)
            for value in sorted(
                _RAW_V8_UNAVAILABILITY_PROFILES_V49F[profile.reason_profile]
                | _RAW_V8_NON_APPLICABLE_REASONS_V49F
            )
        )
        descriptors.append(
            CapacityMeasurementTargetFieldDescriptorV49FV8(
                field_id=field_id,
                layer=field_id.split(".", 1)[0].upper(),
                value_kind=CapacityMeasurementTargetValueKindV49FV8(value_kind),
                unit=unit,
                value_constraint_id=_constraint_id_for_field_v49f_v8(
                    field_id=field_id, value_kind=value_kind, unit=unit
                ),
                observation_method_role_pairs=profile.method_role_pairs,
                allowed_checkpoint_marker_kinds=profile.checkpoint_markers,
                applicable_operation_kinds=profile.operation_kinds,
                allowed_status_reasons=reasons,
                status_reason_policy_id=RAW_V8_STATUS_REASON_POLICY_ID_V49F,
                censoring_allowed=profile.censoring_allowed,
                later_threshold_action_if_unavailable=(
                    CapacityMeasurementLaterThresholdActionV49FV8.FAIL_CLOSED
                ),
                value_shape_id=shape_id,
                value_shape_keys=shape.ordered_keys,
                cross_field_constraint_ids=(
                    (RAW_V8_A1_FIFO_CROSS_FIELD_CONSTRAINT_ID_V49F,)
                    if field_id in cross_fields
                    else ()
                ),
            )
        )
    descriptors.sort(key=lambda value: value.field_id)
    if (
        len(descriptors) != RAW_V8_TARGET_FIELD_COUNT_V49F
        or len({value.field_id for value in descriptors})
        != RAW_V8_TARGET_FIELD_COUNT_V49F
    ):
        raise RuntimeError("Raw V8 target-field inventory must contain 185 rows")
    return tuple(descriptors)


_RAW_V8_FROZEN_VOCABULARY_DEFINITIONS_V49F = _build_vocabulary_definitions_v49f_v8()
_RAW_V8_FROZEN_VALUE_SHAPE_DEFINITIONS_V49F = _build_value_shape_definitions_v49f_v8()
_RAW_V8_FROZEN_VALUE_CONSTRAINT_DEFINITIONS_V49F = (
    _build_value_constraint_definitions_v49f_v8()
)
_RAW_V8_FROZEN_STATUS_REASON_POLICY_V49F = (
    _build_status_reason_policy_definition_v49f_v8()
)
_RAW_V8_FROZEN_CROSS_FIELD_CONSTRAINT_DEFINITIONS_V49F = (
    CapacityMeasurementCrossFieldConstraintDefinitionV49FV8(
        cross_field_constraint_id=(RAW_V8_A1_FIFO_CROSS_FIELD_CONSTRAINT_ID_V49F),
        count_field_id="a1.waiting_count",
        sequence_field_id="a1.waiting_sequences",
        kind_field_id="a1.waiting_kinds",
        activation_condition="ALL_MEMBERS_AVAILABLE",
        maximum_items=4,
        sequence_order="STRICTLY_INCREASING_UNIQUE",
        cardinality_rule="COUNT_EQUALS_BOTH_ARRAY_LENGTHS",
        pairing_rule="SAME_INDEX",
    ),
)
_RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F = _build_target_field_descriptors_v49f_v8(
    _RAW_V8_FROZEN_VALUE_SHAPE_DEFINITIONS_V49F
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetFieldRegistryV49FV8(_StandaloneRecordV49FV8):
    target_registry_profile: str
    status_reason_policy_definition: (
        CapacityMeasurementStatusReasonPolicyDefinitionV49FV8
    )
    ordered_vocabulary_definitions: tuple[
        CapacityMeasurementVocabularyDefinitionV49FV8, ...
    ]
    ordered_value_shape_definitions: tuple[
        CapacityMeasurementValueShapeDefinitionV49FV8, ...
    ]
    ordered_value_constraint_definitions: tuple[
        CapacityMeasurementValueConstraintDefinitionV49FV8, ...
    ]
    ordered_cross_field_constraint_definitions: tuple[
        CapacityMeasurementCrossFieldConstraintDefinitionV49FV8, ...
    ]
    field_count: int
    descriptors: tuple[CapacityMeasurementTargetFieldDescriptorV49FV8, ...]
    target_field_registry_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_FIELD_REGISTRY_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "target_field_registry_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_TARGET_FIELD_REGISTRY_BYTES_V49F

    def __post_init__(self) -> None:
        if (
            type(self.target_registry_profile) is not str
            or self.target_registry_profile != "COMPLETE_TYPED_FIELD_AVAILABILITY_V1"
        ):
            raise CanonicalizationError("target_registry_profile differs")
        if (
            type(self.status_reason_policy_definition)
            is not CapacityMeasurementStatusReasonPolicyDefinitionV49FV8
        ):
            raise CanonicalizationError("status reason policy type differs")
        tuple_specs: tuple[tuple[str, type[Any], str], ...] = (
            (
                "ordered_vocabulary_definitions",
                CapacityMeasurementVocabularyDefinitionV49FV8,
                "vocabulary_id",
            ),
            (
                "ordered_value_shape_definitions",
                CapacityMeasurementValueShapeDefinitionV49FV8,
                "value_shape_id",
            ),
            (
                "ordered_value_constraint_definitions",
                CapacityMeasurementValueConstraintDefinitionV49FV8,
                "value_constraint_id",
            ),
            (
                "ordered_cross_field_constraint_definitions",
                CapacityMeasurementCrossFieldConstraintDefinitionV49FV8,
                "cross_field_constraint_id",
            ),
            (
                "descriptors",
                CapacityMeasurementTargetFieldDescriptorV49FV8,
                "field_id",
            ),
        )
        for name, item_type, id_name in tuple_specs:
            values = _exact_tuple(getattr(self, name), field=name)
            if (
                any(type(value) is not item_type for value in values)
                or values
                != tuple(sorted(values, key=lambda value: getattr(value, id_name)))
                or len({getattr(value, id_name) for value in values}) != len(values)
            ):
                raise CanonicalizationError(f"{name} differs from sorted exact records")
        if _safe_uint(
            self.field_count,
            field="field_count",
            minimum=RAW_V8_TARGET_FIELD_COUNT_V49F,
            maximum=RAW_V8_TARGET_FIELD_COUNT_V49F,
        ) != len(self.descriptors):
            raise CanonicalizationError("registry field_count differs")
        if (
            self.status_reason_policy_definition
            != _RAW_V8_FROZEN_STATUS_REASON_POLICY_V49F
            or self.ordered_vocabulary_definitions
            != _RAW_V8_FROZEN_VOCABULARY_DEFINITIONS_V49F
            or self.ordered_value_shape_definitions
            != _RAW_V8_FROZEN_VALUE_SHAPE_DEFINITIONS_V49F
            or self.ordered_value_constraint_definitions
            != _RAW_V8_FROZEN_VALUE_CONSTRAINT_DEFINITIONS_V49F
            or self.ordered_cross_field_constraint_definitions
            != _RAW_V8_FROZEN_CROSS_FIELD_CONSTRAINT_DEFINITIONS_V49F
            or self.descriptors != _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
        ):
            raise CanonicalizationError(
                "target registry differs from the complete frozen V8 inventory"
            )
        self._seal_identity()
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError(
                "target registry identity differs from its independent golden"
            )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "target_registry_profile": self.target_registry_profile,
            "status_reason_policy_definition": (
                self.status_reason_policy_definition.as_dict()
            ),
            "ordered_vocabulary_definitions": [
                value.as_dict() for value in self.ordered_vocabulary_definitions
            ],
            "ordered_value_shape_definitions": [
                value.as_dict() for value in self.ordered_value_shape_definitions
            ],
            "ordered_value_constraint_definitions": [
                value.as_dict() for value in self.ordered_value_constraint_definitions
            ],
            "ordered_cross_field_constraint_definitions": [
                value.as_dict()
                for value in self.ordered_cross_field_constraint_definitions
            ],
            "field_count": self.field_count,
            "descriptors": [value.as_dict() for value in self.descriptors],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetFieldRegistryV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            target_registry_profile=item["target_registry_profile"],
            status_reason_policy_definition=(
                CapacityMeasurementStatusReasonPolicyDefinitionV49FV8.from_mapping(
                    item["status_reason_policy_definition"]
                )
            ),
            ordered_vocabulary_definitions=tuple(
                CapacityMeasurementVocabularyDefinitionV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered_vocabulary_definitions"],
                    field="ordered_vocabulary_definitions",
                    maximum=25,
                )
            ),
            ordered_value_shape_definitions=tuple(
                CapacityMeasurementValueShapeDefinitionV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered_value_shape_definitions"],
                    field="ordered_value_shape_definitions",
                    maximum=6,
                )
            ),
            ordered_value_constraint_definitions=tuple(
                CapacityMeasurementValueConstraintDefinitionV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered_value_constraint_definitions"],
                    field="ordered_value_constraint_definitions",
                    maximum=17,
                )
            ),
            ordered_cross_field_constraint_definitions=tuple(
                CapacityMeasurementCrossFieldConstraintDefinitionV49FV8.from_mapping(
                    value
                )
                for value in _exact_json_list(
                    item["ordered_cross_field_constraint_definitions"],
                    field="ordered_cross_field_constraint_definitions",
                    maximum=1,
                )
            ),
            field_count=item["field_count"],
            descriptors=tuple(
                CapacityMeasurementTargetFieldDescriptorV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["descriptors"],
                    field="descriptors",
                    maximum=RAW_V8_TARGET_FIELD_COUNT_V49F,
                )
            ),
            target_field_registry_id=item["target_field_registry_id"],
        )


def capacity_measurement_target_field_registry_v49f_v8() -> (
    CapacityMeasurementTargetFieldRegistryV49FV8
):
    """Return the exact complete target registry bound to the golden identity."""

    return CapacityMeasurementTargetFieldRegistryV49FV8(
        target_registry_profile="COMPLETE_TYPED_FIELD_AVAILABILITY_V1",
        status_reason_policy_definition=_RAW_V8_FROZEN_STATUS_REASON_POLICY_V49F,
        ordered_vocabulary_definitions=(_RAW_V8_FROZEN_VOCABULARY_DEFINITIONS_V49F),
        ordered_value_shape_definitions=(_RAW_V8_FROZEN_VALUE_SHAPE_DEFINITIONS_V49F),
        ordered_value_constraint_definitions=(
            _RAW_V8_FROZEN_VALUE_CONSTRAINT_DEFINITIONS_V49F
        ),
        ordered_cross_field_constraint_definitions=(
            _RAW_V8_FROZEN_CROSS_FIELD_CONSTRAINT_DEFINITIONS_V49F
        ),
        field_count=RAW_V8_TARGET_FIELD_COUNT_V49F,
        descriptors=_RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F,
    )


RAW_V8_TARGET_FIELD_DESCRIPTORS_V49F = _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
RAW_V8_TARGET_FIELD_REGISTRY_V49F = capacity_measurement_target_field_registry_v49f_v8()


class _TargetValueV49FV8(_NestedRecordV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_VALUE_UNION_BYTES_V49F


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementUIntValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    value: int

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.UINT:
            raise CanonicalizationError("UINT value carries the wrong kind tag")
        _safe_uint(self.value, field="value")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementUIntValueV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"kind", "value"}), context=cls.__name__
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            value=item["value"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementBoolValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    value: bool

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.BOOL:
            raise CanonicalizationError("BOOL value carries the wrong kind tag")
        _exact_bool(self.value, field="value")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementBoolValueV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"kind", "value"}), context=cls.__name__
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            value=item["value"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTextValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    value: str

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.TEXT:
            raise CanonicalizationError("TEXT value carries the wrong kind tag")
        _utf8_identifier(self.value, field="value", maximum=256)

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTextValueV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"kind", "value"}), context=cls.__name__
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            value=item["value"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOptionalUIntValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    present: bool
    value: int | None

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.OPTIONAL_UINT:
            raise CanonicalizationError(
                "OPTIONAL_UINT value carries the wrong kind tag"
            )
        _exact_bool(self.present, field="present")
        _optional_safe_uint(self.value, field="value")
        if self.present != (self.value is not None):
            raise CanonicalizationError("OPTIONAL_UINT presence and value disagree")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "present": self.present, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOptionalUIntValueV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"kind", "present", "value"}),
            context=cls.__name__,
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            present=item["present"],
            value=item["value"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOptionalTextValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    present: bool
    value: str | None

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.OPTIONAL_TEXT:
            raise CanonicalizationError(
                "OPTIONAL_TEXT value carries the wrong kind tag"
            )
        _exact_bool(self.present, field="present")
        if self.value is not None:
            _utf8_identifier(self.value, field="value", maximum=256)
        if self.present != (self.value is not None):
            raise CanonicalizationError("OPTIONAL_TEXT presence and value disagree")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "present": self.present, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOptionalTextValueV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"kind", "present", "value"}),
            context=cls.__name__,
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            present=item["present"],
            value=item["value"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementUIntListValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    values: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.UINT_LIST:
            raise CanonicalizationError("UINT_LIST value carries the wrong kind tag")
        values = _exact_tuple(self.values, field="values")
        if len(values) > 4:
            raise CanonicalizationError("UINT_LIST exceeds its maximum shape")
        for index, value in enumerate(values):
            _safe_uint(value, field=f"values[{index}]")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "values": list(self.values)}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementUIntListValueV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"kind", "values"}), context=cls.__name__
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            values=tuple(_exact_json_list(item["values"], field="values", maximum=4)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTextListValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.TEXT_LIST:
            raise CanonicalizationError("TEXT_LIST value carries the wrong kind tag")
        values = _exact_tuple(self.values, field="values")
        if len(values) > 4:
            raise CanonicalizationError("TEXT_LIST exceeds its maximum shape")
        for index, value in enumerate(values):
            _utf8_identifier(value, field=f"values[{index}]", maximum=256)

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "values": list(self.values)}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTextListValueV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"kind", "values"}), context=cls.__name__
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            values=tuple(_exact_json_list(item["values"], field="values", maximum=4)),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementFixedUIntMapEntryV49FV8(_NestedRecordV49FV8):
    key: str
    value: int

    def __post_init__(self) -> None:
        _ascii_text(self.key, field="key", minimum=1, maximum=128)
        _safe_uint(self.value, field="value")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementFixedUIntMapEntryV49FV8:
        item = _require_nested_keys(
            payload, expected=frozenset({"key", "value"}), context=cls.__name__
        )
        return cls(key=item["key"], value=item["value"])


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementFixedUIntMapValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    ordered: tuple[CapacityMeasurementFixedUIntMapEntryV49FV8, ...]

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.FIXED_UINT_MAP:
            raise CanonicalizationError(
                "FIXED_UINT_MAP value carries the wrong kind tag"
            )
        items = _exact_tuple(self.ordered, field="ordered")
        if (
            not items
            or len(items) > 32
            or any(
                type(item) is not CapacityMeasurementFixedUIntMapEntryV49FV8
                for item in items
            )
            or tuple(item.key for item in items)
            != tuple(sorted(item.key for item in items))
            or len({item.key for item in items}) != len(items)
        ):
            raise CanonicalizationError("FIXED_UINT_MAP items are invalid")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "ordered": [item.as_dict() for item in self.ordered],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementFixedUIntMapValueV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset({"kind", "ordered"}),
            context=cls.__name__,
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            ordered=tuple(
                CapacityMeasurementFixedUIntMapEntryV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["ordered"], field="ordered", maximum=32
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementDurationBoundValueV49FV8(_TargetValueV49FV8):
    kind: CapacityMeasurementTargetValueKindV49FV8
    relation: CapacityMeasurementDurationRelationV49FV8
    lower_nanoseconds: int | None
    upper_nanoseconds: int | None

    def __post_init__(self) -> None:
        if self.kind is not CapacityMeasurementTargetValueKindV49FV8.DURATION_BOUND:
            raise CanonicalizationError("DURATION_BOUND carries the wrong kind tag")
        _exact_enum(
            self.relation,
            CapacityMeasurementDurationRelationV49FV8,
            field="relation",
        )
        lower = _optional_safe_uint(self.lower_nanoseconds, field="lower_nanoseconds")
        upper = _optional_safe_uint(self.upper_nanoseconds, field="upper_nanoseconds")
        valid = {
            CapacityMeasurementDurationRelationV49FV8.EXACT: (
                lower is not None and upper == lower
            ),
            CapacityMeasurementDurationRelationV49FV8.LOWER_BOUND: (
                lower is not None and upper is None
            ),
            CapacityMeasurementDurationRelationV49FV8.UPPER_BOUND: (
                lower is None and upper is not None
            ),
            CapacityMeasurementDurationRelationV49FV8.INTERVAL: (
                lower is not None and upper is not None and lower <= upper
            ),
        }[self.relation]
        if not valid:
            raise CanonicalizationError("duration relation and endpoints disagree")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "relation": self.relation.value,
            "lower_nanoseconds": self.lower_nanoseconds,
            "upper_nanoseconds": self.upper_nanoseconds,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementDurationBoundValueV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(
                {"kind", "relation", "lower_nanoseconds", "upper_nanoseconds"}
            ),
            context=cls.__name__,
        )
        return cls(
            kind=_enum_from_json(
                item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
            ),
            relation=_enum_from_json(
                item["relation"],
                CapacityMeasurementDurationRelationV49FV8,
                field="relation",
            ),
            lower_nanoseconds=item["lower_nanoseconds"],
            upper_nanoseconds=item["upper_nanoseconds"],
        )


_TargetValueUnionV49FV8 = (
    CapacityMeasurementUIntValueV49FV8
    | CapacityMeasurementBoolValueV49FV8
    | CapacityMeasurementTextValueV49FV8
    | CapacityMeasurementOptionalUIntValueV49FV8
    | CapacityMeasurementOptionalTextValueV49FV8
    | CapacityMeasurementUIntListValueV49FV8
    | CapacityMeasurementTextListValueV49FV8
    | CapacityMeasurementFixedUIntMapValueV49FV8
    | CapacityMeasurementDurationBoundValueV49FV8
)
_RAW_V8_VALUE_CLASS_BY_KIND_V49F: dict[
    CapacityMeasurementTargetValueKindV49FV8, type[_TargetValueV49FV8]
] = {
    CapacityMeasurementTargetValueKindV49FV8.UINT: CapacityMeasurementUIntValueV49FV8,
    CapacityMeasurementTargetValueKindV49FV8.BOOL: CapacityMeasurementBoolValueV49FV8,
    CapacityMeasurementTargetValueKindV49FV8.TEXT: CapacityMeasurementTextValueV49FV8,
    CapacityMeasurementTargetValueKindV49FV8.OPTIONAL_UINT: (
        CapacityMeasurementOptionalUIntValueV49FV8
    ),
    CapacityMeasurementTargetValueKindV49FV8.OPTIONAL_TEXT: (
        CapacityMeasurementOptionalTextValueV49FV8
    ),
    CapacityMeasurementTargetValueKindV49FV8.UINT_LIST: (
        CapacityMeasurementUIntListValueV49FV8
    ),
    CapacityMeasurementTargetValueKindV49FV8.TEXT_LIST: (
        CapacityMeasurementTextListValueV49FV8
    ),
    CapacityMeasurementTargetValueKindV49FV8.FIXED_UINT_MAP: (
        CapacityMeasurementFixedUIntMapValueV49FV8
    ),
    CapacityMeasurementTargetValueKindV49FV8.DURATION_BOUND: (
        CapacityMeasurementDurationBoundValueV49FV8
    ),
}


def _target_value_from_mapping_v49f_v8(payload: Any) -> _TargetValueUnionV49FV8:
    item = _exact_mapping(payload, field="value")
    if "kind" not in item:
        raise CanonicalizationError("value kind is absent")
    kind = _enum_from_json(
        item["kind"], CapacityMeasurementTargetValueKindV49FV8, field="kind"
    )
    return _RAW_V8_VALUE_CLASS_BY_KIND_V49F[kind].from_mapping(item)  # type: ignore[no-any-return,attr-defined]


def _validate_value_against_descriptor_v49f_v8(
    value: _TargetValueUnionV49FV8,
    descriptor: CapacityMeasurementTargetFieldDescriptorV49FV8,
) -> None:
    expected_type = _RAW_V8_VALUE_CLASS_BY_KIND_V49F[descriptor.value_kind]
    if type(value) is not expected_type:
        raise CanonicalizationError("field value type differs from its descriptor")
    value.as_dict()
    constraint = descriptor.value_constraint_id
    if constraint == "UINT_LOOP_PROBE_INTERVAL_NS":
        if type(value) is not CapacityMeasurementUIntValueV49FV8:
            raise CanonicalizationError("loop interval must be an exact UINT")
        _safe_uint(
            value.value,
            field="value",
            minimum=1_000_000,
            maximum=60_000_000_000,
        )
    elif constraint in {"TEXT_SHA256", "OPTIONAL_TEXT_SHA256"}:
        text_value = value.value  # type: ignore[union-attr]
        if text_value is not None:
            _hash(text_value, field="value")
    elif constraint == "OPTIONAL_TEXT_UINT128_DECIMAL":
        absolute_value = value.value  # type: ignore[union-attr]
        if absolute_value is not None:
            _uint128_text(absolute_value, field="value")
    elif constraint == "OPTIONAL_TEXT_PLATFORM_ERRNO":
        errno_value = value.value  # type: ignore[union-attr]
        if errno_value is not None:
            _ascii_text(
                errno_value,
                field="value",
                minimum=1,
                maximum=64,
                pattern=_ERRNO_NAME_RE,
            )
    enum_constraints: dict[str, type[Enum]] = {
        "TEXT_ENUM_A1_COMMAND_KIND": CapacityMeasurementOperationKindV49FV8,
        "OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND": CapacityMeasurementOperationKindV49FV8,
        "TEXT_LIST_ENUM_A1_COMMAND_KIND": CapacityMeasurementOperationKindV49FV8,
        "TEXT_ENUM_A1_ADMISSION_OUTCOME": CapacityMeasurementA1AdmissionOutcomeV49FV8,
        "OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS": CapacityMeasurementA1RejectionClassV49FV8,
        "TEXT_ENUM_SQLITE_PRIMARY_RESULT": CapacityMeasurementSQLitePrimaryResultV49FV8,
    }
    if constraint in enum_constraints:
        enum_type = enum_constraints[constraint]
        if type(value) is CapacityMeasurementTextListValueV49FV8:
            texts = value.values
        else:
            single = value.value  # type: ignore[union-attr]
            texts = () if single is None else (single,)
        for text in texts:
            try:
                enum_type(text)
            except ValueError as exc:
                raise CanonicalizationError("field value is outside its enum") from exc
    shape = next(
        value_shape
        for value_shape in _RAW_V8_FROZEN_VALUE_SHAPE_DEFINITIONS_V49F
        if value_shape.value_shape_id == descriptor.value_shape_id
    )
    if type(value) in {
        CapacityMeasurementUIntListValueV49FV8,
        CapacityMeasurementTextListValueV49FV8,
    }:
        count = len(value.values)
        if not shape.minimum_items <= count <= shape.maximum_items:  # type: ignore[operator]
            raise CanonicalizationError("field list cardinality differs from its shape")
    elif type(value) is CapacityMeasurementFixedUIntMapValueV49FV8:
        if tuple(item.key for item in value.ordered) != descriptor.value_shape_keys:
            raise CanonicalizationError("fixed-map keys differ from the descriptor")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSourceErrorDetailV49FV8(_StandaloneRecordV49FV8):
    field_id: str
    observation_method: CapacityMeasurementTargetObservationMethodV49FV8
    source_failure_phase: CapacityMeasurementSourceFailurePhaseV49FV8
    source_errno_number: int | None
    source_errno_name: str | None
    source_error_class: str
    source_error_detail_sha256: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_SOURCE_ERROR_DETAIL_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "source_error_detail_sha256"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_SOURCE_ERROR_DETAIL_BYTES_V49F

    def __post_init__(self) -> None:
        _ascii_text(
            self.field_id,
            field="field_id",
            minimum=3,
            maximum=256,
            pattern=_FIELD_ID_RE,
        )
        _exact_enum(
            self.observation_method,
            CapacityMeasurementTargetObservationMethodV49FV8,
            field="observation_method",
        )
        if (
            self.observation_method
            is CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
        ):
            raise CanonicalizationError("source error requires a registered method")
        _exact_enum(
            self.source_failure_phase,
            CapacityMeasurementSourceFailurePhaseV49FV8,
            field="source_failure_phase",
        )
        if self.source_failure_phase not in {
            CapacityMeasurementSourceFailurePhaseV49FV8.SECOND_CLOCK_READ,
            CapacityMeasurementSourceFailurePhaseV49FV8.SOURCE_ADAPTER,
            CapacityMeasurementSourceFailurePhaseV49FV8.VALUE_VALIDATION,
        }:
            raise CanonicalizationError("source error detail has no failure phase")
        number = _optional_safe_uint(
            self.source_errno_number,
            field="source_errno_number",
            minimum=1,
        )
        if self.source_errno_name is not None:
            _ascii_text(
                self.source_errno_name,
                field="source_errno_name",
                minimum=1,
                maximum=64,
                pattern=_ERRNO_NAME_RE,
            )
        if (number is None) != (self.source_errno_name is None):
            raise CanonicalizationError("source errno number and name must be paired")
        _ascii_text(
            self.source_error_class,
            field="source_error_class",
            minimum=1,
            maximum=256,
            pattern=_SAFE_EXCEPTION_CLASS_RE,
        )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "observation_method": self.observation_method.value,
            "source_failure_phase": self.source_failure_phase.value,
            "source_errno_number": self.source_errno_number,
            "source_errno_name": self.source_errno_name,
            "source_error_class": self.source_error_class,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSourceErrorDetailV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            field_id=item["field_id"],
            observation_method=_enum_from_json(
                item["observation_method"],
                CapacityMeasurementTargetObservationMethodV49FV8,
                field="observation_method",
            ),
            source_failure_phase=_enum_from_json(
                item["source_failure_phase"],
                CapacityMeasurementSourceFailurePhaseV49FV8,
                field="source_failure_phase",
            ),
            source_errno_number=item["source_errno_number"],
            source_errno_name=item["source_errno_name"],
            source_error_class=item["source_error_class"],
            source_error_detail_sha256=item["source_error_detail_sha256"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementClockSpanV49FV8(_NestedRecordV49FV8):
    clock_domain: CapacityMeasurementClockDomainV49FV8
    span_status: CapacityMeasurementClockSpanStatusV49FV8
    started_offset_nanoseconds: int | None
    completed_offset_nanoseconds: int | None
    unavailable_reason: CapacityMeasurementStatusReasonV49FV8 | None

    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_CLOCK_SPAN_BYTES_V49F

    def __post_init__(self) -> None:
        _exact_enum(
            self.clock_domain,
            CapacityMeasurementClockDomainV49FV8,
            field="clock_domain",
        )
        _exact_enum(
            self.span_status,
            CapacityMeasurementClockSpanStatusV49FV8,
            field="span_status",
        )
        started = _optional_safe_uint(
            self.started_offset_nanoseconds,
            field="started_offset_nanoseconds",
        )
        completed = _optional_safe_uint(
            self.completed_offset_nanoseconds,
            field="completed_offset_nanoseconds",
        )
        if self.unavailable_reason is not None:
            _exact_enum(
                self.unavailable_reason,
                CapacityMeasurementStatusReasonV49FV8,
                field="unavailable_reason",
            )
        if self.span_status is CapacityMeasurementClockSpanStatusV49FV8.AVAILABLE:
            if (
                started is None
                or completed is None
                or completed < started
                or self.unavailable_reason is not None
            ):
                raise CanonicalizationError("available clock span is incomplete")
        elif (
            started is not None
            or completed is not None
            or self.unavailable_reason
            not in {
                CapacityMeasurementStatusReasonV49FV8.SOURCE_CLOCK_UNAVAILABLE,
                CapacityMeasurementStatusReasonV49FV8.PROCESS_LOSS_VOLATILE_MARKER_STATE,
            }
        ):
            raise CanonicalizationError("unavailable clock span is inconsistent")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "clock_domain": self.clock_domain.value,
            "span_status": self.span_status.value,
            "started_offset_nanoseconds": self.started_offset_nanoseconds,
            "completed_offset_nanoseconds": self.completed_offset_nanoseconds,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementClockSpanV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            clock_domain=_enum_from_json(
                item["clock_domain"],
                CapacityMeasurementClockDomainV49FV8,
                field="clock_domain",
            ),
            span_status=_enum_from_json(
                item["span_status"],
                CapacityMeasurementClockSpanStatusV49FV8,
                field="span_status",
            ),
            started_offset_nanoseconds=item["started_offset_nanoseconds"],
            completed_offset_nanoseconds=item["completed_offset_nanoseconds"],
            unavailable_reason=(
                None
                if item["unavailable_reason"] is None
                else _enum_from_json(
                    item["unavailable_reason"],
                    CapacityMeasurementStatusReasonV49FV8,
                    field="unavailable_reason",
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationContextV49FV8(_StandaloneRecordV49FV8):
    observation_role: CapacityMeasurementObservationRoleV49FV8
    operation_kind: CapacityMeasurementOperationKindV49FV8
    instrumentation_mode: CapacityMeasurementInstrumentationModeV49FV8
    candidate_id: str
    attempt_id: str | None
    target_field_registry_id: str
    marker_ordinal: int | None
    checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8 | None
    observer_clock_span: CapacityMeasurementClockSpanV49FV8
    boottime_clock_span: CapacityMeasurementClockSpanV49FV8
    loop_clock_span: CapacityMeasurementClockSpanV49FV8
    observation_context_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_CONTEXT_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "observation_context_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OBSERVATION_CONTEXT_BYTES_V49F

    def __post_init__(self) -> None:
        _exact_enum(
            self.observation_role,
            CapacityMeasurementObservationRoleV49FV8,
            field="observation_role",
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.instrumentation_mode,
            CapacityMeasurementInstrumentationModeV49FV8,
            field="instrumentation_mode",
        )
        object.__setattr__(
            self, "candidate_id", _hash(self.candidate_id, field="candidate_id")
        )
        object.__setattr__(
            self, "attempt_id", _optional_hash(self.attempt_id, field="attempt_id")
        )
        object.__setattr__(
            self,
            "target_field_registry_id",
            _hash(self.target_field_registry_id, field="target_field_registry_id"),
        )
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError("observation context uses a foreign registry")
        for name, domain in (
            (
                "observer_clock_span",
                CapacityMeasurementClockDomainV49FV8.OBSERVER_MONOTONIC,
            ),
            ("boottime_clock_span", CapacityMeasurementClockDomainV49FV8.BOOTTIME),
            ("loop_clock_span", CapacityMeasurementClockDomainV49FV8.EVENT_LOOP),
        ):
            span = getattr(self, name)
            if type(span) is not CapacityMeasurementClockSpanV49FV8:
                raise CanonicalizationError(f"{name} must be an exact clock span")
            span.as_dict()
            if span.clock_domain is not domain:
                raise CanonicalizationError(f"{name} carries the wrong clock domain")
        if (
            self.instrumentation_mode
            is CapacityMeasurementInstrumentationModeV49FV8.OFF
            and self.observation_role
            not in {
                CapacityMeasurementObservationRoleV49FV8.BEFORE_OPERATION,
                CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION,
                CapacityMeasurementObservationRoleV49FV8.OPERATION_AGGREGATE,
                CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY,
            }
        ):
            raise CanonicalizationError(
                "OFF instrumentation forbids only stable-checkpoint observations"
            )
        if (
            self.observation_role
            is CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT
        ):
            ordinal = _optional_safe_uint(
                self.marker_ordinal, field="marker_ordinal", minimum=1
            )
            if (
                ordinal is None
                or self.attempt_id is None
                or type(self.checkpoint_marker_kind)
                is not CapacityMeasurementMarkerKindV49FV8
                or self.checkpoint_marker_kind
                not in _RAW_V8_FULL_CHECKPOINT_MARKERS_V49F
                or self.checkpoint_marker_kind
                not in _RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F[self.operation_kind]
            ):
                raise CanonicalizationError(
                    "stable checkpoint context is incomplete or operation-incompatible"
                )
        else:
            if (
                self.marker_ordinal is not None
                or self.checkpoint_marker_kind is not None
            ):
                raise CanonicalizationError(
                    "non-checkpoint context carries marker members"
                )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "observation_role": self.observation_role.value,
            "operation_kind": self.operation_kind.value,
            "instrumentation_mode": self.instrumentation_mode.value,
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "target_field_registry_id": self.target_field_registry_id,
            "marker_ordinal": self.marker_ordinal,
            "checkpoint_marker_kind": (
                None
                if self.checkpoint_marker_kind is None
                else self.checkpoint_marker_kind.value
            ),
            "observer_clock_span": self.observer_clock_span.as_dict(),
            "boottime_clock_span": self.boottime_clock_span.as_dict(),
            "loop_clock_span": self.loop_clock_span.as_dict(),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationContextV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            observation_role=_enum_from_json(
                item["observation_role"],
                CapacityMeasurementObservationRoleV49FV8,
                field="observation_role",
            ),
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            instrumentation_mode=_enum_from_json(
                item["instrumentation_mode"],
                CapacityMeasurementInstrumentationModeV49FV8,
                field="instrumentation_mode",
            ),
            candidate_id=item["candidate_id"],
            attempt_id=item["attempt_id"],
            target_field_registry_id=item["target_field_registry_id"],
            marker_ordinal=item["marker_ordinal"],
            checkpoint_marker_kind=(
                None
                if item["checkpoint_marker_kind"] is None
                else _enum_from_json(
                    item["checkpoint_marker_kind"],
                    CapacityMeasurementMarkerKindV49FV8,
                    field="checkpoint_marker_kind",
                )
            ),
            observer_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["observer_clock_span"]
            ),
            boottime_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["boottime_clock_span"]
            ),
            loop_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["loop_clock_span"]
            ),
            observation_context_id=item["observation_context_id"],
        )


_RAW_V8_DESCRIPTOR_BY_FIELD_ID_V49F = {
    value.field_id: value for value in _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
}
_RAW_V8_REASON_RULE_BY_REASON_V49F = {
    value.reason: value
    for value in _RAW_V8_FROZEN_STATUS_REASON_POLICY_V49F.reason_rules
}
_RAW_V8_OFF_STATIC_FIELD_IDS_V49F = frozenset(
    {
        "loop.probe_interval_ns",
        "process.filesystem_mount_cgroup_identity_id",
        "process.runtime_environment_id",
    }
)


def _validate_adapter_span_v49f_v8(
    *,
    status: CapacityMeasurementAdapterSpanStatusV49FV8,
    started: int | None,
    completed: int | None,
) -> None:
    _exact_enum(
        status, CapacityMeasurementAdapterSpanStatusV49FV8, field="adapter_span_status"
    )
    started_value = _optional_safe_uint(
        started, field="observation_started_offset_nanoseconds"
    )
    completed_value = _optional_safe_uint(
        completed, field="observation_completed_offset_nanoseconds"
    )
    if status is CapacityMeasurementAdapterSpanStatusV49FV8.AVAILABLE:
        if (
            started_value is None
            or completed_value is None
            or completed_value < started_value
        ):
            raise CanonicalizationError("available adapter span is incomplete")
    elif started_value is not None or completed_value is not None:
        raise CanonicalizationError("non-available adapter span carries endpoints")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetFieldObservationV49FV8(_StandaloneRecordV49FV8):
    target_field_registry_id: str
    observation_context_id: str
    field_id: str
    availability: CapacityMeasurementTargetAvailabilityV49FV8
    value: _TargetValueUnionV49FV8 | None
    observation_method: CapacityMeasurementTargetObservationMethodV49FV8
    observation_attempt: CapacityMeasurementObservationAttemptV49FV8
    adapter_span_status: CapacityMeasurementAdapterSpanStatusV49FV8
    observation_started_offset_nanoseconds: int | None
    observation_completed_offset_nanoseconds: int | None
    unavailable_reason: CapacityMeasurementStatusReasonV49FV8 | None
    censoring: CapacityMeasurementCensoringV49FV8
    source_errno_number: int | None
    source_errno_name: str | None
    source_failure_phase: CapacityMeasurementSourceFailurePhaseV49FV8
    source_error_class: str | None
    source_error_detail_sha256: str | None
    field_observation_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_FIELD_OBSERVATION_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "field_observation_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_FIELD_OBSERVATION_BYTES_V49F

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_field_registry_id",
            _hash(self.target_field_registry_id, field="target_field_registry_id"),
        )
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError("field observation uses a foreign registry")
        object.__setattr__(
            self,
            "observation_context_id",
            _hash(self.observation_context_id, field="observation_context_id"),
        )
        _ascii_text(
            self.field_id,
            field="field_id",
            minimum=3,
            maximum=256,
            pattern=_FIELD_ID_RE,
        )
        try:
            descriptor = _RAW_V8_DESCRIPTOR_BY_FIELD_ID_V49F[self.field_id]
        except KeyError as exc:
            raise CanonicalizationError(
                "field_id is outside the frozen registry"
            ) from exc
        _exact_enum(
            self.availability,
            CapacityMeasurementTargetAvailabilityV49FV8,
            field="availability",
        )
        _exact_enum(
            self.observation_method,
            CapacityMeasurementTargetObservationMethodV49FV8,
            field="observation_method",
        )
        _exact_enum(
            self.observation_attempt,
            CapacityMeasurementObservationAttemptV49FV8,
            field="observation_attempt",
        )
        _validate_adapter_span_v49f_v8(
            status=self.adapter_span_status,
            started=self.observation_started_offset_nanoseconds,
            completed=self.observation_completed_offset_nanoseconds,
        )
        if self.unavailable_reason is not None:
            _exact_enum(
                self.unavailable_reason,
                CapacityMeasurementStatusReasonV49FV8,
                field="unavailable_reason",
            )
            if self.unavailable_reason not in descriptor.allowed_status_reasons:
                raise CanonicalizationError(
                    "unavailable_reason is not descriptor-admitted"
                )
        _exact_enum(
            self.censoring,
            CapacityMeasurementCensoringV49FV8,
            field="censoring",
        )
        _exact_enum(
            self.source_failure_phase,
            CapacityMeasurementSourceFailurePhaseV49FV8,
            field="source_failure_phase",
        )
        errno_number = _optional_safe_uint(
            self.source_errno_number,
            field="source_errno_number",
            minimum=1,
        )
        if self.source_errno_name is not None:
            _ascii_text(
                self.source_errno_name,
                field="source_errno_name",
                minimum=1,
                maximum=64,
                pattern=_ERRNO_NAME_RE,
            )
        if (errno_number is None) != (self.source_errno_name is None):
            raise CanonicalizationError("source errno number and name must be paired")
        if self.source_error_class is not None:
            _ascii_text(
                self.source_error_class,
                field="source_error_class",
                minimum=1,
                maximum=256,
                pattern=_SAFE_EXCEPTION_CLASS_RE,
            )
        detail_digest = _optional_hash(
            self.source_error_detail_sha256,
            field="source_error_detail_sha256",
        )
        if (self.source_error_class is None) != (detail_digest is None):
            raise CanonicalizationError("source error class and digest must be paired")
        if self.source_error_class is not None:
            detail = CapacityMeasurementSourceErrorDetailV49FV8(
                field_id=self.field_id,
                observation_method=self.observation_method,
                source_failure_phase=self.source_failure_phase,
                source_errno_number=errno_number,
                source_errno_name=self.source_errno_name,
                source_error_class=self.source_error_class,
                source_error_detail_sha256=detail_digest,
            )
            if detail.source_error_detail_sha256 != detail_digest:
                raise CanonicalizationError("source error detail digest differs")
        if self.availability is CapacityMeasurementTargetAvailabilityV49FV8.AVAILABLE:
            self._validate_available_or_censored(descriptor, censored=False)
        elif self.availability is CapacityMeasurementTargetAvailabilityV49FV8.CENSORED:
            self._validate_available_or_censored(descriptor, censored=True)
        elif (
            self.availability
            is CapacityMeasurementTargetAvailabilityV49FV8.NOT_APPLICABLE
        ):
            self._validate_not_applicable()
        else:
            self._validate_unavailable()
        self._seal_identity()

    def _validate_no_source_error(self) -> None:
        if (
            self.source_errno_number is not None
            or self.source_errno_name is not None
            or self.source_error_class is not None
            or self.source_error_detail_sha256 is not None
        ):
            raise CanonicalizationError("field state forbids source error metadata")

    def _validate_available_or_censored(
        self,
        descriptor: CapacityMeasurementTargetFieldDescriptorV49FV8,
        *,
        censored: bool,
    ) -> None:
        if self.value is None:
            raise CanonicalizationError("available or censored field requires a value")
        _validate_value_against_descriptor_v49f_v8(self.value, descriptor)
        if (
            self.observation_attempt
            is not CapacityMeasurementObservationAttemptV49FV8.ATTEMPTED
            or self.observation_method
            is CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
            or self.adapter_span_status
            is not CapacityMeasurementAdapterSpanStatusV49FV8.AVAILABLE
            or self.unavailable_reason is not None
            or self.source_failure_phase
            is not CapacityMeasurementSourceFailurePhaseV49FV8.NONE
        ):
            raise CanonicalizationError(
                "available or censored field state is inconsistent"
            )
        self._validate_no_source_error()
        if not censored:
            if self.censoring is not CapacityMeasurementCensoringV49FV8.NONE:
                raise CanonicalizationError("available field cannot be censored")
            if type(self.value) is CapacityMeasurementDurationBoundValueV49FV8 and (
                self.value.relation
                is not CapacityMeasurementDurationRelationV49FV8.EXACT
            ):
                raise CanonicalizationError("available duration must be exact")
            return
        if (
            not descriptor.censoring_allowed
            or type(self.value) is not CapacityMeasurementDurationBoundValueV49FV8
            or self.censoring is CapacityMeasurementCensoringV49FV8.NONE
        ):
            raise CanonicalizationError("descriptor does not admit censored value")
        expected_relation = {
            CapacityMeasurementCensoringV49FV8.LEFT: (
                CapacityMeasurementDurationRelationV49FV8.UPPER_BOUND
            ),
            CapacityMeasurementCensoringV49FV8.RIGHT: (
                CapacityMeasurementDurationRelationV49FV8.LOWER_BOUND
            ),
            CapacityMeasurementCensoringV49FV8.INTERVAL: (
                CapacityMeasurementDurationRelationV49FV8.INTERVAL
            ),
        }[self.censoring]
        if self.value.relation is not expected_relation:
            raise CanonicalizationError("censoring and duration relation disagree")

    def _validate_not_applicable(self) -> None:
        if (
            self.value is not None
            or self.unavailable_reason
            not in {
                CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_OPERATION,
                CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_REACHED_STATE,
            }
            or self.observation_method
            is not CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
            or self.observation_attempt
            is not CapacityMeasurementObservationAttemptV49FV8.NOT_ATTEMPTED
            or self.adapter_span_status
            is not CapacityMeasurementAdapterSpanStatusV49FV8.NOT_APPLICABLE
            or self.censoring is not CapacityMeasurementCensoringV49FV8.NONE
            or self.source_failure_phase
            is not CapacityMeasurementSourceFailurePhaseV49FV8.NONE
        ):
            raise CanonicalizationError("not-applicable field state is inconsistent")
        self._validate_no_source_error()

    def _validate_unavailable(self) -> None:
        if (
            self.value is not None
            or self.unavailable_reason is None
            or self.censoring is not CapacityMeasurementCensoringV49FV8.NONE
        ):
            raise CanonicalizationError("unavailable field state is inconsistent")
        reason_rule = _RAW_V8_REASON_RULE_BY_REASON_V49F[self.unavailable_reason]
        if (
            reason_rule.required_availability
            is not CapacityMeasurementTargetAvailabilityV49FV8.UNAVAILABLE
        ):
            raise CanonicalizationError("reason requires a different availability")
        state = next(
            (
                value
                for value in reason_rule.attempt_state_error_forms
                if value.attempt_state is self.observation_attempt
            ),
            None,
        )
        if state is None:
            raise CanonicalizationError(
                "reason does not admit observation attempt state"
            )
        if (
            self.observation_attempt
            is CapacityMeasurementObservationAttemptV49FV8.ATTEMPTED
        ):
            if (
                self.observation_method
                is CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
            ):
                raise CanonicalizationError("attempted field needs a registered method")
        elif (
            self.observation_method
            is not CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
        ):
            raise CanonicalizationError("not-attempted field needs the sentinel method")
        required_span = {
            "AVAILABLE_ONLY": CapacityMeasurementAdapterSpanStatusV49FV8.AVAILABLE,
            "NOT_APPLICABLE_ONLY": (
                CapacityMeasurementAdapterSpanStatusV49FV8.NOT_APPLICABLE
            ),
            "UNAVAILABLE_ONLY": CapacityMeasurementAdapterSpanStatusV49FV8.UNAVAILABLE,
        }[state.adapter_span_policy]
        if self.adapter_span_status is not required_span:
            raise CanonicalizationError("reason and adapter span status disagree")
        if self.source_failure_phase not in state.permitted_failure_phases:
            raise CanonicalizationError("reason and source failure phase disagree")
        errno_present = self.source_errno_number is not None
        class_present = self.source_error_class is not None
        if errno_present:
            error_form = CapacityMeasurementErrorFormV49FV8.OS
        elif class_present:
            error_form = CapacityMeasurementErrorFormV49FV8.NON_OS
        elif (
            CapacityMeasurementErrorFormV49FV8.STATUS_ONLY
            in state.permitted_error_forms
        ):
            error_form = CapacityMeasurementErrorFormV49FV8.STATUS_ONLY
        else:
            error_form = CapacityMeasurementErrorFormV49FV8.NONE
        if error_form not in state.permitted_error_forms:
            raise CanonicalizationError("reason and source error form disagree")

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "target_field_registry_id": self.target_field_registry_id,
            "observation_context_id": self.observation_context_id,
            "field_id": self.field_id,
            "availability": self.availability.value,
            "value": None if self.value is None else self.value.as_dict(),
            "observation_method": self.observation_method.value,
            "observation_attempt": self.observation_attempt.value,
            "adapter_span_status": self.adapter_span_status.value,
            "observation_started_offset_nanoseconds": (
                self.observation_started_offset_nanoseconds
            ),
            "observation_completed_offset_nanoseconds": (
                self.observation_completed_offset_nanoseconds
            ),
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
            "censoring": self.censoring.value,
            "source_errno_number": self.source_errno_number,
            "source_errno_name": self.source_errno_name,
            "source_failure_phase": self.source_failure_phase.value,
            "source_error_class": self.source_error_class,
            "source_error_detail_sha256": self.source_error_detail_sha256,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetFieldObservationV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            target_field_registry_id=item["target_field_registry_id"],
            observation_context_id=item["observation_context_id"],
            field_id=item["field_id"],
            availability=_enum_from_json(
                item["availability"],
                CapacityMeasurementTargetAvailabilityV49FV8,
                field="availability",
            ),
            value=(
                None
                if item["value"] is None
                else _target_value_from_mapping_v49f_v8(item["value"])
            ),
            observation_method=_enum_from_json(
                item["observation_method"],
                CapacityMeasurementTargetObservationMethodV49FV8,
                field="observation_method",
            ),
            observation_attempt=_enum_from_json(
                item["observation_attempt"],
                CapacityMeasurementObservationAttemptV49FV8,
                field="observation_attempt",
            ),
            adapter_span_status=_enum_from_json(
                item["adapter_span_status"],
                CapacityMeasurementAdapterSpanStatusV49FV8,
                field="adapter_span_status",
            ),
            observation_started_offset_nanoseconds=item[
                "observation_started_offset_nanoseconds"
            ],
            observation_completed_offset_nanoseconds=item[
                "observation_completed_offset_nanoseconds"
            ],
            unavailable_reason=(
                None
                if item["unavailable_reason"] is None
                else _enum_from_json(
                    item["unavailable_reason"],
                    CapacityMeasurementStatusReasonV49FV8,
                    field="unavailable_reason",
                )
            ),
            censoring=_enum_from_json(
                item["censoring"],
                CapacityMeasurementCensoringV49FV8,
                field="censoring",
            ),
            source_errno_number=item["source_errno_number"],
            source_errno_name=item["source_errno_name"],
            source_failure_phase=_enum_from_json(
                item["source_failure_phase"],
                CapacityMeasurementSourceFailurePhaseV49FV8,
                field="source_failure_phase",
            ),
            source_error_class=item["source_error_class"],
            source_error_detail_sha256=item["source_error_detail_sha256"],
            field_observation_id=item["field_observation_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationV49FV8(_StandaloneRecordV49FV8):
    observation_role: CapacityMeasurementObservationRoleV49FV8
    operation_kind: CapacityMeasurementOperationKindV49FV8
    instrumentation_mode: CapacityMeasurementInstrumentationModeV49FV8
    candidate_id: str
    attempt_id: str | None
    target_field_registry_id: str
    observation_context_id: str
    marker_ordinal: int | None
    checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8 | None
    observer_clock_span: CapacityMeasurementClockSpanV49FV8
    boottime_clock_span: CapacityMeasurementClockSpanV49FV8
    loop_clock_span: CapacityMeasurementClockSpanV49FV8
    field_observations: tuple[CapacityMeasurementTargetFieldObservationV49FV8, ...]
    observation_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "observation_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_TARGET_OBSERVATION_BYTES_V49F

    def __post_init__(self) -> None:
        context = CapacityMeasurementTargetObservationContextV49FV8(
            observation_role=self.observation_role,
            operation_kind=self.operation_kind,
            instrumentation_mode=self.instrumentation_mode,
            candidate_id=self.candidate_id,
            attempt_id=self.attempt_id,
            target_field_registry_id=self.target_field_registry_id,
            marker_ordinal=self.marker_ordinal,
            checkpoint_marker_kind=self.checkpoint_marker_kind,
            observer_clock_span=self.observer_clock_span,
            boottime_clock_span=self.boottime_clock_span,
            loop_clock_span=self.loop_clock_span,
            observation_context_id=self.observation_context_id,
        )
        # Normalize the scalar members exactly as the independently identified
        # context did; no caller-authored aliases survive into observation bytes.
        for name in (
            "candidate_id",
            "attempt_id",
            "target_field_registry_id",
            "observation_context_id",
        ):
            object.__setattr__(self, name, getattr(context, name))
        observations = _exact_tuple(self.field_observations, field="field_observations")
        if len(observations) != RAW_V8_TARGET_FIELD_COUNT_V49F or any(
            type(value) is not CapacityMeasurementTargetFieldObservationV49FV8
            for value in observations
        ):
            raise CanonicalizationError(
                "target observation requires exactly 185 exact field envelopes"
            )
        expected_ids = tuple(
            descriptor.field_id
            for descriptor in _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
        )
        if tuple(value.field_id for value in observations) != expected_ids:
            raise CanonicalizationError("field observations differ from registry order")
        observer_span = context.observer_clock_span
        for field_observation, descriptor in zip(
            observations, _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
        ):
            field_observation.as_dict()
            if (
                field_observation.target_field_registry_id
                != context.target_field_registry_id
                or field_observation.observation_context_id
                != context.observation_context_id
            ):
                raise CanonicalizationError("field envelope differs from its context")
            self._validate_field_in_context(
                field_observation=field_observation,
                descriptor=descriptor,
                context=context,
            )
            if (
                field_observation.adapter_span_status
                is CapacityMeasurementAdapterSpanStatusV49FV8.AVAILABLE
            ):
                if (
                    observer_span.span_status
                    is not CapacityMeasurementClockSpanStatusV49FV8.AVAILABLE
                ):
                    raise CanonicalizationError(
                        "available field span requires available observer span"
                    )
                field_start = field_observation.observation_started_offset_nanoseconds
                field_end = field_observation.observation_completed_offset_nanoseconds
                observer_start = observer_span.started_offset_nanoseconds
                observer_end = observer_span.completed_offset_nanoseconds
                if (
                    field_start is None
                    or field_end is None
                    or observer_start is None
                    or observer_end is None
                    or field_start < observer_start
                    or field_end > observer_end
                ):
                    raise CanonicalizationError(
                        "field adapter span lies outside observer span"
                    )
        self._validate_a1_fifo_constraint(observations)
        self._seal_identity()

    @staticmethod
    def _validate_field_in_context(
        *,
        field_observation: CapacityMeasurementTargetFieldObservationV49FV8,
        descriptor: CapacityMeasurementTargetFieldDescriptorV49FV8,
        context: CapacityMeasurementTargetObservationContextV49FV8,
    ) -> None:
        operation_applies = (
            context.operation_kind in descriptor.applicable_operation_kinds
        )
        if not operation_applies:
            if (
                field_observation.availability
                is not CapacityMeasurementTargetAvailabilityV49FV8.NOT_APPLICABLE
                or field_observation.unavailable_reason
                is not CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_OPERATION
            ):
                raise CanonicalizationError(
                    "operation-excluded field must be explicitly not applicable"
                )
            return
        if (
            field_observation.unavailable_reason
            is CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_OPERATION
        ):
            raise CanonicalizationError(
                "operation-applicable field uses excluded reason"
            )
        if (
            context.attempt_id is None
            and descriptor.field_id in _RAW_V8_ATTEMPT_REQUIRED_FIELD_ID_SET_V49F
        ):
            if (
                field_observation.availability
                is not CapacityMeasurementTargetAvailabilityV49FV8.NOT_APPLICABLE
                or field_observation.unavailable_reason
                is not CapacityMeasurementStatusReasonV49FV8.NOT_APPLICABLE_TO_REACHED_STATE
            ):
                raise CanonicalizationError(
                    "null-attempt field must be explicitly not applicable to reached state"
                )
            return
        if (
            context.instrumentation_mode
            is CapacityMeasurementInstrumentationModeV49FV8.OFF
        ):
            if descriptor.field_id in _RAW_V8_OFF_STATIC_FIELD_IDS_V49F:
                if (
                    field_observation.availability
                    is not CapacityMeasurementTargetAvailabilityV49FV8.AVAILABLE
                ):
                    raise CanonicalizationError(
                        "OFF static authority field must remain available"
                    )
            elif descriptor.field_id == (
                "freshness.analysis_pressure_episode_age_boottime_ns"
            ):
                if (
                    field_observation.availability
                    is not CapacityMeasurementTargetAvailabilityV49FV8.UNAVAILABLE
                    or field_observation.unavailable_reason
                    is not CapacityMeasurementStatusReasonV49FV8.NO_FROZEN_PRESSURE_POLICY
                ):
                    raise CanonicalizationError(
                        "OFF no-policy field must retain its frozen unavailability"
                    )
            elif (
                field_observation.availability
                is not CapacityMeasurementTargetAvailabilityV49FV8.UNAVAILABLE
                or field_observation.unavailable_reason
                is not CapacityMeasurementStatusReasonV49FV8.INSTRUMENTATION_DISABLED
            ):
                raise CanonicalizationError(
                    "OFF field requiring instrumentation must be disabled"
                )
        elif (
            field_observation.unavailable_reason
            is CapacityMeasurementStatusReasonV49FV8.INSTRUMENTATION_DISABLED
        ):
            raise CanonicalizationError(
                "ON instrumentation cannot emit INSTRUMENTATION_DISABLED"
            )
        if (
            field_observation.observation_attempt
            is CapacityMeasurementObservationAttemptV49FV8.ATTEMPTED
        ):
            method_pair = next(
                (
                    value
                    for value in descriptor.observation_method_role_pairs
                    if value.observation_method is field_observation.observation_method
                ),
                None,
            )
            if (
                method_pair is None
                or context.observation_role not in method_pair.allowed_roles
            ):
                raise CanonicalizationError(
                    "attempted field method is not registered for this role"
                )
            if (
                context.observation_role
                is CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT
                and context.checkpoint_marker_kind
                not in descriptor.allowed_checkpoint_marker_kinds
            ):
                raise CanonicalizationError(
                    "attempted field is not admitted at this checkpoint"
                )

    @staticmethod
    def _validate_a1_fifo_constraint(
        observations: tuple[CapacityMeasurementTargetFieldObservationV49FV8, ...],
    ) -> None:
        by_id = {value.field_id: value for value in observations}
        count = by_id["a1.waiting_count"]
        sequences = by_id["a1.waiting_sequences"]
        kinds = by_id["a1.waiting_kinds"]
        if not all(
            value.availability is CapacityMeasurementTargetAvailabilityV49FV8.AVAILABLE
            for value in (count, sequences, kinds)
        ):
            return
        if (
            type(count.value) is not CapacityMeasurementUIntValueV49FV8
            or type(sequences.value) is not CapacityMeasurementUIntListValueV49FV8
            or type(kinds.value) is not CapacityMeasurementTextListValueV49FV8
        ):
            raise CanonicalizationError("A1 FIFO values carry incompatible types")
        sequence_values = sequences.value.values
        if (
            count.value.value != len(sequence_values)
            or len(sequence_values) != len(kinds.value.values)
            or len(sequence_values) > 4
            or any(
                left >= right
                for left, right in zip(sequence_values, sequence_values[1:])
            )
        ):
            raise CanonicalizationError("A1 FIFO cross-field constraint failed")

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "observation_role": self.observation_role.value,
            "operation_kind": self.operation_kind.value,
            "instrumentation_mode": self.instrumentation_mode.value,
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "target_field_registry_id": self.target_field_registry_id,
            "observation_context_id": self.observation_context_id,
            "marker_ordinal": self.marker_ordinal,
            "checkpoint_marker_kind": (
                None
                if self.checkpoint_marker_kind is None
                else self.checkpoint_marker_kind.value
            ),
            "observer_clock_span": self.observer_clock_span.as_dict(),
            "boottime_clock_span": self.boottime_clock_span.as_dict(),
            "loop_clock_span": self.loop_clock_span.as_dict(),
            "field_observations": [
                value.as_dict() for value in self.field_observations
            ],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            observation_role=_enum_from_json(
                item["observation_role"],
                CapacityMeasurementObservationRoleV49FV8,
                field="observation_role",
            ),
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            instrumentation_mode=_enum_from_json(
                item["instrumentation_mode"],
                CapacityMeasurementInstrumentationModeV49FV8,
                field="instrumentation_mode",
            ),
            candidate_id=item["candidate_id"],
            attempt_id=item["attempt_id"],
            target_field_registry_id=item["target_field_registry_id"],
            observation_context_id=item["observation_context_id"],
            marker_ordinal=item["marker_ordinal"],
            checkpoint_marker_kind=(
                None
                if item["checkpoint_marker_kind"] is None
                else _enum_from_json(
                    item["checkpoint_marker_kind"],
                    CapacityMeasurementMarkerKindV49FV8,
                    field="checkpoint_marker_kind",
                )
            ),
            observer_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["observer_clock_span"]
            ),
            boottime_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["boottime_clock_span"]
            ),
            loop_clock_span=CapacityMeasurementClockSpanV49FV8.from_mapping(
                item["loop_clock_span"]
            ),
            field_observations=tuple(
                CapacityMeasurementTargetFieldObservationV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["field_observations"],
                    field="field_observations",
                    maximum=RAW_V8_TARGET_FIELD_COUNT_V49F,
                )
            ),
            observation_id=item["observation_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationRootV49FV8(_StandaloneRecordV49FV8):
    candidate_id: str
    attempt_id: str | None
    operation_kind: CapacityMeasurementOperationKindV49FV8
    instrumentation_mode: CapacityMeasurementInstrumentationModeV49FV8
    target_field_registry_id: str
    observation_count: int
    ordered_observation_ids: tuple[str, ...]
    target_observation_root_sha256: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_ROOT_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "target_observation_root_sha256"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_TARGET_OBSERVATION_ROOT_BYTES_V49F

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _hash(self.candidate_id, field="candidate_id")
        )
        object.__setattr__(
            self, "attempt_id", _optional_hash(self.attempt_id, field="attempt_id")
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.instrumentation_mode,
            CapacityMeasurementInstrumentationModeV49FV8,
            field="instrumentation_mode",
        )
        object.__setattr__(
            self,
            "target_field_registry_id",
            _hash(self.target_field_registry_id, field="target_field_registry_id"),
        )
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError("observation root uses a foreign registry")
        ids = _exact_tuple(
            self.ordered_observation_ids, field="ordered_observation_ids"
        )
        if not 1 <= len(ids) <= RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F:
            raise CanonicalizationError("observation root count is outside 1..67")
        normalized = tuple(
            _hash(value, field="ordered_observation_ids") for value in ids
        )
        if len(set(normalized)) != len(normalized):
            raise CanonicalizationError("ordered observation IDs must be unique")
        object.__setattr__(self, "ordered_observation_ids", normalized)
        if _safe_uint(
            self.observation_count,
            field="observation_count",
            minimum=1,
            maximum=RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F,
        ) != len(normalized):
            raise CanonicalizationError("observation_count differs from ID tuple")
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "operation_kind": self.operation_kind.value,
            "instrumentation_mode": self.instrumentation_mode.value,
            "target_field_registry_id": self.target_field_registry_id,
            "observation_count": self.observation_count,
            "ordered_observation_ids": list(self.ordered_observation_ids),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationRootV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            candidate_id=item["candidate_id"],
            attempt_id=item["attempt_id"],
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            instrumentation_mode=_enum_from_json(
                item["instrumentation_mode"],
                CapacityMeasurementInstrumentationModeV49FV8,
                field="instrumentation_mode",
            ),
            target_field_registry_id=item["target_field_registry_id"],
            observation_count=item["observation_count"],
            ordered_observation_ids=tuple(
                _exact_json_list(
                    item["ordered_observation_ids"],
                    field="ordered_observation_ids",
                    maximum=RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F,
                )
            ),
            target_observation_root_sha256=item["target_observation_root_sha256"],
        )


def validate_capacity_measurement_target_observation_root_v49f_v8(
    *,
    root: CapacityMeasurementTargetObservationRootV49FV8,
    observations: tuple[CapacityMeasurementTargetObservationV49FV8, ...],
) -> None:
    """Validate root membership, context agreement, and exact lifecycle order."""

    if type(root) is not CapacityMeasurementTargetObservationRootV49FV8:
        raise CanonicalizationError("root must be the exact Raw V8 root type")
    root = root._revalidated()
    values = _exact_tuple(observations, field="observations")
    if len(values) != root.observation_count or any(
        type(value) is not CapacityMeasurementTargetObservationV49FV8
        for value in values
    ):
        raise CanonicalizationError("root observations have incompatible cardinality")
    values = tuple(value._revalidated() for value in values)
    if tuple(value.observation_id for value in values) != root.ordered_observation_ids:
        raise CanonicalizationError("root ordered IDs differ from observations")
    for value in values:
        if (
            value.candidate_id != root.candidate_id
            or value.attempt_id != root.attempt_id
            or value.operation_kind is not root.operation_kind
            or value.instrumentation_mode is not root.instrumentation_mode
            or value.target_field_registry_id != root.target_field_registry_id
        ):
            raise CanonicalizationError("observation context differs from root")
    if (
        values[0].observation_role
        is CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY
    ):
        if len(values) != 1:
            raise CanonicalizationError(
                "startup recovery root must contain one observation"
            )
        return
    if len(values) < 3:
        raise CanonicalizationError(
            "same-process root requires at least three observations"
        )
    if (
        values[0].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.BEFORE_OPERATION
        or values[-2].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION
        or values[-1].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.OPERATION_AGGREGATE
        or any(
            value.observation_role
            is not CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT
            for value in values[1:-2]
        )
    ):
        raise CanonicalizationError("same-process observation role order differs")
    ordinals = tuple(value.marker_ordinal for value in values[1:-2])
    if any(value is None for value in ordinals) or tuple(sorted(ordinals)) != ordinals:
        raise CanonicalizationError("checkpoint marker ordinals are not increasing")
    if len(set(ordinals)) != len(ordinals):
        raise CanonicalizationError("checkpoint coordinates must be unique")
    if (
        root.instrumentation_mode is CapacityMeasurementInstrumentationModeV49FV8.OFF
        and len(values) != 3
    ):
        raise CanonicalizationError("OFF root must contain exactly three observations")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationClockSpanV2V49FV8(_NestedRecordV49FV8):
    clock_domain: CapacityMeasurementClockDomainV49FV8
    span_status: CapacityMeasurementClockSpanStatusV49FV8
    started_offset_nanoseconds: int | None
    completed_offset_nanoseconds: int | None
    unavailable_reason: CapacityMeasurementStatusReasonV49FV8 | None

    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_CLOCK_SPAN_BYTES_V49F

    def __post_init__(self) -> None:
        _exact_enum(
            self.clock_domain,
            CapacityMeasurementClockDomainV49FV8,
            field="clock_domain",
        )
        _exact_enum(
            self.span_status,
            CapacityMeasurementClockSpanStatusV49FV8,
            field="span_status",
        )
        started = _optional_safe_uint(
            self.started_offset_nanoseconds,
            field="started_offset_nanoseconds",
        )
        completed = _optional_safe_uint(
            self.completed_offset_nanoseconds,
            field="completed_offset_nanoseconds",
        )
        reason = self.unavailable_reason
        if reason is not None:
            _exact_enum(
                reason,
                CapacityMeasurementStatusReasonV49FV8,
                field="unavailable_reason",
            )
        if self.span_status is CapacityMeasurementClockSpanStatusV49FV8.AVAILABLE:
            if (
                started is None
                or completed is None
                or completed < started
                or reason is not None
            ):
                raise CanonicalizationError("available V2 clock span is incomplete")
        elif (
            started is not None
            or completed is not None
            or reason
            not in {
                CapacityMeasurementStatusReasonV49FV8.ARTIFACT_BOUND_EXCEEDED,
                CapacityMeasurementStatusReasonV49FV8.OBSERVER_INTERNAL_ERROR,
                CapacityMeasurementStatusReasonV49FV8.PROCESS_LOSS_VOLATILE_MARKER_STATE,
                CapacityMeasurementStatusReasonV49FV8.SOURCE_CLOCK_UNAVAILABLE,
                CapacityMeasurementStatusReasonV49FV8.TARGET_BOUNDARY_NOT_REACHED,
            }
        ):
            raise CanonicalizationError("unavailable V2 clock span is inconsistent")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "clock_domain": self.clock_domain.value,
            "span_status": self.span_status.value,
            "started_offset_nanoseconds": self.started_offset_nanoseconds,
            "completed_offset_nanoseconds": self.completed_offset_nanoseconds,
            "unavailable_reason": (
                None
                if self.unavailable_reason is None
                else self.unavailable_reason.value
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationClockSpanV2V49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            clock_domain=_enum_from_json(
                item["clock_domain"],
                CapacityMeasurementClockDomainV49FV8,
                field="clock_domain",
            ),
            span_status=_enum_from_json(
                item["span_status"],
                CapacityMeasurementClockSpanStatusV49FV8,
                field="span_status",
            ),
            started_offset_nanoseconds=item["started_offset_nanoseconds"],
            completed_offset_nanoseconds=item["completed_offset_nanoseconds"],
            unavailable_reason=(
                None
                if item["unavailable_reason"] is None
                else _enum_from_json(
                    item["unavailable_reason"],
                    CapacityMeasurementStatusReasonV49FV8,
                    field="unavailable_reason",
                )
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationContextV2V49FV8(_StandaloneRecordV49FV8):
    observation_role: CapacityMeasurementObservationRoleV49FV8
    operation_kind: CapacityMeasurementOperationKindV49FV8
    instrumentation_mode: CapacityMeasurementInstrumentationModeV49FV8
    candidate_id: str
    attempt_id: str | None
    target_field_registry_id: str
    marker_ordinal: int | None
    checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8 | None
    full_checkpoint_selector_id: str | None
    checkpoint_selector_position: int | None
    checkpoint_selector_entry_id: str | None
    expected_checkpoint_marker_kind: CapacityMeasurementMarkerKindV49FV8 | None
    expected_occurrence_index_within_kind: int | None
    checkpoint_binding_status: CapacityMeasurementCheckpointBindingStatusV49FV8 | None
    checkpoint_binding_unavailable_reason: CapacityMeasurementStatusReasonV49FV8 | None
    observer_clock_span: CapacityMeasurementTargetObservationClockSpanV2V49FV8
    boottime_clock_span: CapacityMeasurementTargetObservationClockSpanV2V49FV8
    loop_clock_span: CapacityMeasurementTargetObservationClockSpanV2V49FV8
    observation_context_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_CONTEXT_V2_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "observation_context_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_OBSERVATION_CONTEXT_BYTES_V49F

    def __post_init__(self) -> None:
        _exact_enum(
            self.observation_role,
            CapacityMeasurementObservationRoleV49FV8,
            field="observation_role",
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.instrumentation_mode,
            CapacityMeasurementInstrumentationModeV49FV8,
            field="instrumentation_mode",
        )
        object.__setattr__(
            self,
            "candidate_id",
            _hash(self.candidate_id, field="candidate_id"),
        )
        object.__setattr__(
            self,
            "attempt_id",
            _optional_hash(self.attempt_id, field="attempt_id"),
        )
        object.__setattr__(
            self,
            "target_field_registry_id",
            _hash(self.target_field_registry_id, field="target_field_registry_id"),
        )
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError("V2 context uses a foreign registry")
        object.__setattr__(
            self,
            "marker_ordinal",
            _optional_safe_uint(
                self.marker_ordinal,
                field="marker_ordinal",
                minimum=1,
            ),
        )
        if self.checkpoint_marker_kind is not None:
            _exact_enum(
                self.checkpoint_marker_kind,
                CapacityMeasurementMarkerKindV49FV8,
                field="checkpoint_marker_kind",
            )
        object.__setattr__(
            self,
            "full_checkpoint_selector_id",
            _optional_hash(
                self.full_checkpoint_selector_id,
                field="full_checkpoint_selector_id",
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_selector_position",
            _optional_safe_uint(
                self.checkpoint_selector_position,
                field="checkpoint_selector_position",
                minimum=1,
                maximum=RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F,
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_selector_entry_id",
            _optional_hash(
                self.checkpoint_selector_entry_id,
                field="checkpoint_selector_entry_id",
            ),
        )
        if self.expected_checkpoint_marker_kind is not None:
            _exact_enum(
                self.expected_checkpoint_marker_kind,
                CapacityMeasurementMarkerKindV49FV8,
                field="expected_checkpoint_marker_kind",
            )
        object.__setattr__(
            self,
            "expected_occurrence_index_within_kind",
            _optional_safe_uint(
                self.expected_occurrence_index_within_kind,
                field="expected_occurrence_index_within_kind",
                minimum=1,
            ),
        )
        if self.checkpoint_binding_status is not None:
            _exact_enum(
                self.checkpoint_binding_status,
                CapacityMeasurementCheckpointBindingStatusV49FV8,
                field="checkpoint_binding_status",
            )
        if self.checkpoint_binding_unavailable_reason is not None:
            _exact_enum(
                self.checkpoint_binding_unavailable_reason,
                CapacityMeasurementStatusReasonV49FV8,
                field="checkpoint_binding_unavailable_reason",
            )
        for name, domain in (
            (
                "observer_clock_span",
                CapacityMeasurementClockDomainV49FV8.OBSERVER_MONOTONIC,
            ),
            ("boottime_clock_span", CapacityMeasurementClockDomainV49FV8.BOOTTIME),
            ("loop_clock_span", CapacityMeasurementClockDomainV49FV8.EVENT_LOOP),
        ):
            span = getattr(self, name)
            if (
                type(span) is not CapacityMeasurementTargetObservationClockSpanV2V49FV8
                or span.clock_domain is not domain
            ):
                raise CanonicalizationError(f"{name} is not the exact V2 domain span")
            span.as_dict()
        checkpoint_members = (
            self.full_checkpoint_selector_id,
            self.checkpoint_selector_position,
            self.checkpoint_selector_entry_id,
            self.expected_checkpoint_marker_kind,
            self.expected_occurrence_index_within_kind,
            self.checkpoint_binding_status,
        )
        if (
            self.observation_role
            is not CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT
        ):
            if (
                self.marker_ordinal is not None
                or self.checkpoint_marker_kind is not None
                or any(value is not None for value in checkpoint_members)
                or self.checkpoint_binding_unavailable_reason is not None
            ):
                raise CanonicalizationError(
                    "non-checkpoint V2 context carries selector or binding members"
                )
            if (
                self.observation_role
                is CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY
                and self.attempt_id is not None
            ):
                raise CanonicalizationError(
                    "startup-recovery V2 context must not bind an attempt"
                )
            self._seal_identity()
            return
        if (
            self.instrumentation_mode
            is not CapacityMeasurementInstrumentationModeV49FV8.ON
            or self.attempt_id is None
            or any(value is None for value in checkpoint_members)
            or self.expected_checkpoint_marker_kind
            not in _RAW_V8_CHECKPOINT_MARKERS_BY_OPERATION_V49F[self.operation_kind]
        ):
            raise CanonicalizationError("stable-checkpoint V2 context is incomplete")
        spans = (
            self.observer_clock_span,
            self.boottime_clock_span,
            self.loop_clock_span,
        )
        binding = self.checkpoint_binding_status
        if binding is CapacityMeasurementCheckpointBindingStatusV49FV8.EXACT_MARKER:
            if (
                self.marker_ordinal is None
                or self.checkpoint_marker_kind
                is not self.expected_checkpoint_marker_kind
                or self.checkpoint_binding_unavailable_reason is not None
                or any(
                    span.span_status
                    is not CapacityMeasurementClockSpanStatusV49FV8.AVAILABLE
                    for span in spans
                )
            ):
                raise CanonicalizationError(
                    "EXACT_MARKER V2 context contradicts marker truth"
                )
        elif (
            binding
            is CapacityMeasurementCheckpointBindingStatusV49FV8.UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED
        ):
            reason = CapacityMeasurementStatusReasonV49FV8.TARGET_BOUNDARY_NOT_REACHED
            if (
                self.marker_ordinal is not None
                or self.checkpoint_marker_kind is not None
                or self.checkpoint_binding_unavailable_reason is not reason
                or any(
                    span.span_status
                    is not CapacityMeasurementClockSpanStatusV49FV8.UNAVAILABLE
                    or span.unavailable_reason is not reason
                    for span in spans
                )
            ):
                raise CanonicalizationError(
                    "boundary-not-reached V2 context contradicts placeholder truth"
                )
        elif (
            binding
            is CapacityMeasurementCheckpointBindingStatusV49FV8.UNAVAILABLE_MARKER_OBSERVER_FAILURE
        ):
            reason = self.checkpoint_binding_unavailable_reason
            if (
                self.marker_ordinal is not None
                or self.checkpoint_marker_kind is not None
                or reason
                not in {
                    CapacityMeasurementStatusReasonV49FV8.ARTIFACT_BOUND_EXCEEDED,
                    CapacityMeasurementStatusReasonV49FV8.OBSERVER_INTERNAL_ERROR,
                    CapacityMeasurementStatusReasonV49FV8.SOURCE_CLOCK_UNAVAILABLE,
                }
                or any(
                    span.span_status
                    is not CapacityMeasurementClockSpanStatusV49FV8.UNAVAILABLE
                    or span.unavailable_reason is not reason
                    for span in spans
                )
            ):
                raise CanonicalizationError(
                    "observer-failure V2 context contradicts placeholder truth"
                )
        else:
            raise CanonicalizationError("unsupported V2 checkpoint binding status")
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "observation_role": self.observation_role.value,
            "operation_kind": self.operation_kind.value,
            "instrumentation_mode": self.instrumentation_mode.value,
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "target_field_registry_id": self.target_field_registry_id,
            "marker_ordinal": self.marker_ordinal,
            "checkpoint_marker_kind": (
                None
                if self.checkpoint_marker_kind is None
                else self.checkpoint_marker_kind.value
            ),
            "full_checkpoint_selector_id": self.full_checkpoint_selector_id,
            "checkpoint_selector_position": self.checkpoint_selector_position,
            "checkpoint_selector_entry_id": self.checkpoint_selector_entry_id,
            "expected_checkpoint_marker_kind": (
                None
                if self.expected_checkpoint_marker_kind is None
                else self.expected_checkpoint_marker_kind.value
            ),
            "expected_occurrence_index_within_kind": (
                self.expected_occurrence_index_within_kind
            ),
            "checkpoint_binding_status": (
                None
                if self.checkpoint_binding_status is None
                else self.checkpoint_binding_status.value
            ),
            "checkpoint_binding_unavailable_reason": (
                None
                if self.checkpoint_binding_unavailable_reason is None
                else self.checkpoint_binding_unavailable_reason.value
            ),
            "observer_clock_span": self.observer_clock_span.as_dict(),
            "boottime_clock_span": self.boottime_clock_span.as_dict(),
            "loop_clock_span": self.loop_clock_span.as_dict(),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationContextV2V49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        enum_or_none = {
            "checkpoint_marker_kind": CapacityMeasurementMarkerKindV49FV8,
            "expected_checkpoint_marker_kind": (CapacityMeasurementMarkerKindV49FV8),
            "checkpoint_binding_status": (
                CapacityMeasurementCheckpointBindingStatusV49FV8
            ),
            "checkpoint_binding_unavailable_reason": (
                CapacityMeasurementStatusReasonV49FV8
            ),
        }
        values = {field.name: item[field.name] for field in fields(cls)}
        values["observation_role"] = _enum_from_json(
            item["observation_role"],
            CapacityMeasurementObservationRoleV49FV8,
            field="observation_role",
        )
        values["operation_kind"] = _enum_from_json(
            item["operation_kind"],
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        values["instrumentation_mode"] = _enum_from_json(
            item["instrumentation_mode"],
            CapacityMeasurementInstrumentationModeV49FV8,
            field="instrumentation_mode",
        )
        for name, enum_type in enum_or_none.items():
            values[name] = (
                None
                if item[name] is None
                else _enum_from_json(item[name], enum_type, field=name)
            )
        for name in (
            "observer_clock_span",
            "boottime_clock_span",
            "loop_clock_span",
        ):
            values[name] = (
                CapacityMeasurementTargetObservationClockSpanV2V49FV8.from_mapping(
                    item[name]
                )
            )
        return cls(**values)


_RAW_V8_V2_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON_V49F = {
    CapacityMeasurementStatusReasonV49FV8.TARGET_BOUNDARY_NOT_REACHED: (
        CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED
    ),
    CapacityMeasurementStatusReasonV49FV8.SOURCE_CLOCK_UNAVAILABLE: (
        CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE
    ),
    CapacityMeasurementStatusReasonV49FV8.ARTIFACT_BOUND_EXCEEDED: (
        CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED
    ),
    CapacityMeasurementStatusReasonV49FV8.OBSERVER_INTERNAL_ERROR: (
        CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationV2V49FV8(_StandaloneRecordV49FV8):
    observation_context: CapacityMeasurementTargetObservationContextV2V49FV8
    observation_context_id: str
    field_observations: tuple[CapacityMeasurementTargetFieldObservationV49FV8, ...]
    observation_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_V2_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "observation_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_TARGET_OBSERVATION_BYTES_V49F
    _MAXIMUM_BYTES_IS_EXCLUSIVE: ClassVar[bool] = True

    def __post_init__(self) -> None:
        if (
            type(self.observation_context)
            is not CapacityMeasurementTargetObservationContextV2V49FV8
        ):
            raise CanonicalizationError(
                "V2 observation requires an exact embedded V2 context"
            )
        context = self.observation_context._revalidated()
        object.__setattr__(
            self,
            "observation_context_id",
            _hash(self.observation_context_id, field="observation_context_id"),
        )
        if context.observation_context_id != self.observation_context_id:
            raise CanonicalizationError(
                "V2 observation duplicates the wrong context ID"
            )
        observations = _exact_tuple(
            self.field_observations,
            field="field_observations",
        )
        if len(observations) != RAW_V8_TARGET_FIELD_COUNT_V49F or any(
            type(value) is not CapacityMeasurementTargetFieldObservationV49FV8
            for value in observations
        ):
            raise CanonicalizationError(
                "V2 observation requires exactly 185 V1 field envelopes"
            )
        observations = tuple(value._revalidated() for value in observations)
        expected_ids = tuple(
            descriptor.field_id
            for descriptor in _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F
        )
        if tuple(value.field_id for value in observations) != expected_ids:
            raise CanonicalizationError(
                "V2 field observations differ from registry order"
            )
        is_placeholder = context.checkpoint_binding_status in {
            CapacityMeasurementCheckpointBindingStatusV49FV8.UNAVAILABLE_MARKER_OBSERVER_FAILURE,
            CapacityMeasurementCheckpointBindingStatusV49FV8.UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED,
        }
        expected_placeholder_reason = (
            None
            if not is_placeholder
            else _RAW_V8_V2_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON_V49F[
                context.checkpoint_binding_unavailable_reason
            ]
        )
        observer_span = context.observer_clock_span
        for field_observation, descriptor in zip(
            observations,
            _RAW_V8_FROZEN_TARGET_FIELD_DESCRIPTORS_V49F,
        ):
            if (
                field_observation.target_field_registry_id
                != context.target_field_registry_id
                or field_observation.observation_context_id
                != context.observation_context_id
            ):
                raise CanonicalizationError(
                    "V2 field envelope differs from its embedded context"
                )
            if is_placeholder:
                if (
                    field_observation.availability
                    is not CapacityMeasurementTargetAvailabilityV49FV8.UNAVAILABLE
                    or field_observation.value is not None
                    or field_observation.unavailable_reason
                    is not expected_placeholder_reason
                    or field_observation.observation_method
                    is not CapacityMeasurementTargetObservationMethodV49FV8.NOT_ATTEMPTED
                    or field_observation.observation_attempt
                    is not CapacityMeasurementObservationAttemptV49FV8.NOT_ATTEMPTED
                    or field_observation.adapter_span_status
                    is not CapacityMeasurementAdapterSpanStatusV49FV8.NOT_APPLICABLE
                    or field_observation.observation_started_offset_nanoseconds
                    is not None
                    or field_observation.observation_completed_offset_nanoseconds
                    is not None
                    or field_observation.censoring
                    is not CapacityMeasurementCensoringV49FV8.NONE
                    or field_observation.source_errno_number is not None
                    or field_observation.source_errno_name is not None
                    or field_observation.source_failure_phase
                    is not CapacityMeasurementSourceFailurePhaseV49FV8.NONE
                    or field_observation.source_error_class is not None
                    or field_observation.source_error_detail_sha256 is not None
                ):
                    raise CanonicalizationError(
                        "V2 checkpoint placeholder field state is inconsistent"
                    )
                continue
            if field_observation.unavailable_reason in {
                CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED,
                CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR,
                CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE,
                CapacityMeasurementStatusReasonV49FV8.CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED,
            }:
                raise CanonicalizationError(
                    "checkpoint-only field reason escaped its V2 placeholder"
                )
            CapacityMeasurementTargetObservationV49FV8._validate_field_in_context(
                field_observation=field_observation,
                descriptor=descriptor,
                context=context,  # type: ignore[arg-type]
            )
            if (
                field_observation.adapter_span_status
                is CapacityMeasurementAdapterSpanStatusV49FV8.AVAILABLE
            ):
                start = field_observation.observation_started_offset_nanoseconds
                end = field_observation.observation_completed_offset_nanoseconds
                if (
                    observer_span.span_status
                    is not CapacityMeasurementClockSpanStatusV49FV8.AVAILABLE
                    or start is None
                    or end is None
                    or observer_span.started_offset_nanoseconds is None
                    or observer_span.completed_offset_nanoseconds is None
                    or start < observer_span.started_offset_nanoseconds
                    or end > observer_span.completed_offset_nanoseconds
                ):
                    raise CanonicalizationError(
                        "V2 field adapter span lies outside observer span"
                    )
        CapacityMeasurementTargetObservationV49FV8._validate_a1_fifo_constraint(
            observations
        )
        object.__setattr__(self, "field_observations", observations)
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "observation_context": self.observation_context.as_dict(),
            "observation_context_id": self.observation_context_id,
            "field_observations": [
                value.as_dict() for value in self.field_observations
            ],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationV2V49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            observation_context=(
                CapacityMeasurementTargetObservationContextV2V49FV8.from_mapping(
                    item["observation_context"]
                )
            ),
            observation_context_id=item["observation_context_id"],
            field_observations=tuple(
                CapacityMeasurementTargetFieldObservationV49FV8.from_mapping(value)
                for value in _exact_json_list(
                    item["field_observations"],
                    field="field_observations",
                    maximum=RAW_V8_TARGET_FIELD_COUNT_V49F,
                )
            ),
            observation_id=item["observation_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementTargetObservationRootV2V49FV8(_StandaloneRecordV49FV8):
    candidate_id: str
    attempt_id: str | None
    operation_kind: CapacityMeasurementOperationKindV49FV8
    instrumentation_mode: CapacityMeasurementInstrumentationModeV49FV8
    target_field_registry_id: str
    full_checkpoint_selector_id: str | None
    observation_count: int
    ordered_observation_ids: tuple[str, ...]
    target_observation_root_sha256: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_TARGET_OBSERVATION_ROOT_V2_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "target_observation_root_sha256"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_TARGET_OBSERVATION_ROOT_BYTES_V49F

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "candidate_id",
            _hash(self.candidate_id, field="candidate_id"),
        )
        object.__setattr__(
            self,
            "attempt_id",
            _optional_hash(self.attempt_id, field="attempt_id"),
        )
        _exact_enum(
            self.operation_kind,
            CapacityMeasurementOperationKindV49FV8,
            field="operation_kind",
        )
        _exact_enum(
            self.instrumentation_mode,
            CapacityMeasurementInstrumentationModeV49FV8,
            field="instrumentation_mode",
        )
        object.__setattr__(
            self,
            "target_field_registry_id",
            _hash(self.target_field_registry_id, field="target_field_registry_id"),
        )
        if self.target_field_registry_id != RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F:
            raise CanonicalizationError("V2 root uses a foreign registry")
        object.__setattr__(
            self,
            "full_checkpoint_selector_id",
            _optional_hash(
                self.full_checkpoint_selector_id,
                field="full_checkpoint_selector_id",
            ),
        )
        ids = _exact_tuple(
            self.ordered_observation_ids,
            field="ordered_observation_ids",
        )
        if not 1 <= len(ids) <= RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F:
            raise CanonicalizationError("V2 root observation count is outside 1..67")
        normalized = tuple(
            _hash(value, field="ordered_observation_ids") for value in ids
        )
        if len(set(normalized)) != len(normalized):
            raise CanonicalizationError("V2 root observation IDs must be unique")
        object.__setattr__(self, "ordered_observation_ids", normalized)
        if _safe_uint(
            self.observation_count,
            field="observation_count",
            minimum=1,
            maximum=RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F,
        ) != len(normalized):
            raise CanonicalizationError(
                "V2 root observation_count differs from its ID tuple"
            )
        self._seal_identity()

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "attempt_id": self.attempt_id,
            "operation_kind": self.operation_kind.value,
            "instrumentation_mode": self.instrumentation_mode.value,
            "target_field_registry_id": self.target_field_registry_id,
            "full_checkpoint_selector_id": self.full_checkpoint_selector_id,
            "observation_count": self.observation_count,
            "ordered_observation_ids": list(self.ordered_observation_ids),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementTargetObservationRootV2V49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            candidate_id=item["candidate_id"],
            attempt_id=item["attempt_id"],
            operation_kind=_enum_from_json(
                item["operation_kind"],
                CapacityMeasurementOperationKindV49FV8,
                field="operation_kind",
            ),
            instrumentation_mode=_enum_from_json(
                item["instrumentation_mode"],
                CapacityMeasurementInstrumentationModeV49FV8,
                field="instrumentation_mode",
            ),
            target_field_registry_id=item["target_field_registry_id"],
            full_checkpoint_selector_id=item["full_checkpoint_selector_id"],
            observation_count=item["observation_count"],
            ordered_observation_ids=tuple(
                _exact_json_list(
                    item["ordered_observation_ids"],
                    field="ordered_observation_ids",
                    maximum=RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F,
                )
            ),
            target_observation_root_sha256=item["target_observation_root_sha256"],
        )


def validate_capacity_measurement_target_observation_root_v2_v49f_v8(
    *,
    root: CapacityMeasurementTargetObservationRootV2V49FV8,
    observations: tuple[CapacityMeasurementTargetObservationV2V49FV8, ...],
    full_checkpoint_selector: CapacityMeasurementCheckpointSelectorV49FV8 | None,
) -> None:
    """Validate exact V2 selector membership, binding truth, and lifecycle order."""

    if type(root) is not CapacityMeasurementTargetObservationRootV2V49FV8:
        raise CanonicalizationError("root must be the exact Raw V8 V2 root")
    root = root._revalidated()
    values = _exact_tuple(observations, field="observations")
    if len(values) != root.observation_count or any(
        type(value) is not CapacityMeasurementTargetObservationV2V49FV8
        for value in values
    ):
        raise CanonicalizationError(
            "V2 root observations have incompatible cardinality"
        )
    values = tuple(value._revalidated() for value in values)
    if tuple(value.observation_id for value in values) != root.ordered_observation_ids:
        raise CanonicalizationError("V2 root ordered IDs differ from observations")
    contexts = tuple(value.observation_context for value in values)
    for context in contexts:
        if (
            context.candidate_id != root.candidate_id
            or context.attempt_id != root.attempt_id
            or context.operation_kind is not root.operation_kind
            or context.instrumentation_mode is not root.instrumentation_mode
            or context.target_field_registry_id != root.target_field_registry_id
        ):
            raise CanonicalizationError("V2 observation context differs from root")
    if (
        contexts[0].observation_role
        is CapacityMeasurementObservationRoleV49FV8.STARTUP_RECOVERY
    ):
        if (
            len(contexts) != 1
            or root.attempt_id is not None
            or root.full_checkpoint_selector_id is not None
            or full_checkpoint_selector is not None
        ):
            raise CanonicalizationError(
                "startup-recovery V2 root must be one selector-free observation"
            )
        return
    if (
        len(contexts) < 3
        or contexts[0].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.BEFORE_OPERATION
        or contexts[-2].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.AFTER_OPERATION
        or contexts[-1].observation_role
        is not CapacityMeasurementObservationRoleV49FV8.OPERATION_AGGREGATE
        or any(
            value.observation_role
            is not CapacityMeasurementObservationRoleV49FV8.STABLE_CHECKPOINT
            for value in contexts[1:-2]
        )
    ):
        raise CanonicalizationError("same-process V2 observation order differs")
    selector_required = (
        root.instrumentation_mode is CapacityMeasurementInstrumentationModeV49FV8.ON
        and root.attempt_id is not None
    )
    if not selector_required:
        if (
            len(contexts) != 3
            or root.full_checkpoint_selector_id is not None
            or full_checkpoint_selector is not None
        ):
            raise CanonicalizationError(
                "OFF or no-attempt V2 root must be selector-free with three roles"
            )
        return
    if (
        type(full_checkpoint_selector)
        is not CapacityMeasurementCheckpointSelectorV49FV8
    ):
        raise CanonicalizationError(
            "attempted ON V2 root requires the exact complete selector"
        )
    selector = full_checkpoint_selector._revalidated()
    if (
        selector.operation_kind is not root.operation_kind
        or selector.checkpoint_selector_id != root.full_checkpoint_selector_id
        or len(contexts) != selector.selector_length + 3
    ):
        raise CanonicalizationError("V2 root differs from its complete selector")
    exact_ordinals: list[int] = []
    for context, entry in zip(contexts[1:-2], selector.ordered_entries):
        if (
            context.full_checkpoint_selector_id != selector.checkpoint_selector_id
            or context.checkpoint_selector_position != entry.selector_position
            or context.checkpoint_selector_entry_id
            != entry.checkpoint_selector_entry_id
            or context.expected_checkpoint_marker_kind
            is not entry.checkpoint_marker_kind
            or context.expected_occurrence_index_within_kind
            != entry.occurrence_index_within_kind
        ):
            raise CanonicalizationError(
                "V2 checkpoint context differs from its selector entry"
            )
        if (
            context.checkpoint_binding_status
            is CapacityMeasurementCheckpointBindingStatusV49FV8.EXACT_MARKER
        ):
            if context.marker_ordinal is None:
                raise CanonicalizationError("exact V2 marker has no ordinal")
            exact_ordinals.append(context.marker_ordinal)
    if exact_ordinals != sorted(exact_ordinals) or len(set(exact_ordinals)) != len(
        exact_ordinals
    ):
        raise CanonicalizationError("exact-marker ordinals are not strictly increasing")


_RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F = tuple(
    """
actor.batch_append_maximum_elapsed_ns
actor.batch_append_total_elapsed_ns
actor.event_count
actor.operation_appended_events
actor.operation_batch_append_calls
actor.operation_single_append_calls
actor.pending_control_obligations
actor.pending_control_octets
actor.pending_wire_obligations
actor.pending_wire_octets
actor.rebuild_maximum_elapsed_ns
actor.rebuild_total_elapsed_ns
actor.single_append_maximum_elapsed_ns
actor.single_append_total_elapsed_ns
actor.validation_maximum_elapsed_ns
actor.validation_total_elapsed_ns
ingress.durable_buffer_octets
ingress.operation_new_raw_count
ingress.operation_new_raw_octets
ingress.pending_raw_chunks
ingress.pending_raw_octets
kernel.operation_recv_calls
kernel.operation_recv_ciphertext_octets
kernel.operation_send_accepted_octets
kernel.operation_send_attempts
kernel.operation_send_failures
kernel.operation_send_positive_results
parser.last_unit_elapsed_ns
parser.last_unit_thread_cpu_ns
parser.maximum_unit_elapsed_ns
parser.maximum_unit_thread_cpu_ns
parser.operation_application_completions
parser.operation_automatic_output_chunks
parser.operation_automatic_output_octets
parser.operation_complete_frames
parser.operation_error_units
parser.operation_fragment_units
parser.operation_payload_octets
parser.operation_source_octets
parser.operation_units
parser.total_unit_elapsed_ns
parser.total_unit_thread_cpu_ns
sqlite.begin_maximum_elapsed_ns
sqlite.begin_total_elapsed_ns
sqlite.body_maximum_elapsed_ns
sqlite.body_total_elapsed_ns
sqlite.commit_maximum_elapsed_ns
sqlite.commit_total_elapsed_ns
sqlite.operation_canonical_record_octets
sqlite.operation_rollbacks_attempted
sqlite.operation_rows_written
sqlite.operation_transactions_attempted
sqlite.operation_transactions_begun
sqlite.operation_transactions_committed
sqlite.operation_transactions_rolled_back
sqlite.operation_transactions_uncertain
sqlite.rollback_maximum_elapsed_ns
sqlite.rollback_total_elapsed_ns
tls.operation_ciphertext_fed_octets
tls.operation_ciphertext_produced_octets
tls.operation_plaintext_accepted_octets
tls.operation_plaintext_produced_octets
tls.operation_read_calls
tls.operation_want_read_count
tls.operation_want_write_count
tls.operation_write_calls
""".strip().splitlines()
)
RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F = tuple(
    field_id
    for field_id in _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
    if field_id in _RAW_V8_ATTEMPT_REQUIRED_FIELD_ID_SET_V49F
)
RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F = tuple(
    field_id
    for field_id in _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
    if field_id not in _RAW_V8_ATTEMPT_REQUIRED_FIELD_ID_SET_V49F
)
RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_COUNT_V49F = len(
    RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F
)
RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_COUNT_V49F = len(
    RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F
)
if (
    RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_COUNT_V49F != 58
    or RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_COUNT_V49F != 8
    or RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F
    != tuple(sorted(RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F))
    or RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F
    != tuple(sorted(RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F))
    or set(RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F)
    & set(RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F)
    or tuple(
        sorted(
            (
                *RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F,
                *RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F,
            )
        )
    )
    != _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
):
    raise RuntimeError("Raw V8 compact-counter semantic partition differs")
_RAW_V8_NON_MONOTONE_COUNTER_FIELD_IDS_V49F = frozenset(
    {
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
)
_RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F = tuple(
    value
    for value in _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
    if value not in _RAW_V8_NON_MONOTONE_COUNTER_FIELD_IDS_V49F
)
if (
    len(_RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F)
    != RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F
    or _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
    != tuple(sorted(_RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F))
    or len(_RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F) != 57
):
    raise RuntimeError("Raw V8 compact-counter inventory differs")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationCounterSnapshotSchemaV49FV8(_StandaloneRecordV49FV8):
    counter_field_count: int
    ordered_counter_field_ids: tuple[str, ...]
    monotone_counter_field_ids: tuple[str, ...]
    counter_schema_id: str | None = None

    _DOMAIN: ClassVar[str] = RAW_V8_OPERATION_COUNTER_SCHEMA_DOMAIN_V49F
    _IDENTITY_FIELD: ClassVar[str] = "counter_schema_id"
    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_COUNTER_SCHEMA_BYTES_V49F

    def __post_init__(self) -> None:
        _safe_uint(
            self.counter_field_count,
            field="counter_field_count",
            minimum=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
            maximum=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
        )
        _exact_string_tuple(
            self.ordered_counter_field_ids,
            field="ordered_counter_field_ids",
            sorted_values=True,
        )
        _exact_string_tuple(
            self.monotone_counter_field_ids,
            field="monotone_counter_field_ids",
            sorted_values=True,
        )
        if (
            self.ordered_counter_field_ids != _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
            or self.monotone_counter_field_ids
            != _RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F
        ):
            raise CanonicalizationError("counter schema differs from frozen inventory")
        self._seal_identity()
        if self.counter_schema_id != RAW_V8_OPERATION_COUNTER_SCHEMA_ID_V49F:
            raise CanonicalizationError(
                "counter schema identity differs from independent golden"
            )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "counter_field_count": self.counter_field_count,
            "ordered_counter_field_ids": list(self.ordered_counter_field_ids),
            "monotone_counter_field_ids": list(self.monotone_counter_field_ids),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationCounterSnapshotSchemaV49FV8:
        item = _validate_envelope(
            payload,
            record_type=cls,
            domain=cls._DOMAIN,
            identity_field=cls._IDENTITY_FIELD,
        )
        return cls(
            counter_field_count=item["counter_field_count"],
            ordered_counter_field_ids=tuple(
                _exact_json_list(
                    item["ordered_counter_field_ids"],
                    field="ordered_counter_field_ids",
                    maximum=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
                )
            ),
            monotone_counter_field_ids=tuple(
                _exact_json_list(
                    item["monotone_counter_field_ids"],
                    field="monotone_counter_field_ids",
                    maximum=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
                )
            ),
            counter_schema_id=item["counter_schema_id"],
        )


def capacity_measurement_operation_counter_snapshot_schema_v49f_v8() -> (
    CapacityMeasurementOperationCounterSnapshotSchemaV49FV8
):
    return CapacityMeasurementOperationCounterSnapshotSchemaV49FV8(
        counter_field_count=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
        ordered_counter_field_ids=_RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F,
        monotone_counter_field_ids=_RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F,
    )


RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F = _RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F
RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F = _RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F
RAW_V8_MONOTONE_COUNTER_FIELD_COUNT_V49F = len(RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F)
RAW_V8_OPERATION_COUNTER_SCHEMA_V49F = (
    capacity_measurement_operation_counter_snapshot_schema_v49f_v8()
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationCounterSnapshotV49FV8(_NestedRecordV49FV8):
    counter_schema_id: str
    availability_bitmap: str
    values: tuple[int | None, ...]

    _MAXIMUM_BYTES: ClassVar[int] = RAW_V8_MAXIMUM_COUNTER_SNAPSHOT_BYTES_V49F

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "counter_schema_id",
            _hash(self.counter_schema_id, field="counter_schema_id"),
        )
        if self.counter_schema_id != RAW_V8_OPERATION_COUNTER_SCHEMA_ID_V49F:
            raise CanonicalizationError("counter snapshot uses a foreign schema")
        if (
            type(self.availability_bitmap) is not str
            or len(self.availability_bitmap)
            != RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F
            or not self.availability_bitmap.isascii()
            or any(value not in "01" for value in self.availability_bitmap)
        ):
            raise CanonicalizationError("counter availability bitmap must be 66 bits")
        values = _exact_tuple(self.values, field="values")
        if len(values) != RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F:
            raise CanonicalizationError("counter values must contain 66 positions")
        for index, (bit, value) in enumerate(zip(self.availability_bitmap, values)):
            if bit == "1":
                _safe_uint(value, field=f"values[{index}]")
            elif value is not None:
                raise CanonicalizationError("unavailable counter position must be null")

    def _as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "counter_schema_id": self.counter_schema_id,
            "availability_bitmap": self.availability_bitmap,
            "values": list(self.values),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationCounterSnapshotV49FV8:
        item = _require_nested_keys(
            payload,
            expected=frozenset(field.name for field in fields(cls)),
            context=cls.__name__,
        )
        return cls(
            counter_schema_id=item["counter_schema_id"],
            availability_bitmap=item["availability_bitmap"],
            values=tuple(
                _exact_json_list(
                    item["values"],
                    field="values",
                    maximum=RAW_V8_OPERATION_COUNTER_FIELD_COUNT_V49F,
                )
            ),
        )

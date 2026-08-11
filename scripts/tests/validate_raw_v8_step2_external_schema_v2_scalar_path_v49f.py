#!/usr/bin/env python3
"""Generate or validate the isolated Raw-V8 Step-2 scalar/path ledger.

This authority is intentionally standard-library-only.  It reads exactly the
frozen topology and Unicode-foundation ledgers and never imports production
code, the historical inventory generator, or a schema registry implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
COMPONENT_STATUS: Final = "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY"
LEDGER_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.scalar_path_ledger.v1"
)
TOPOLOGY_SHA256: Final = (
    "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
)
CORE_SHA256: Final = "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
TOPOLOGY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
)
CORE_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
)
LEDGER_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
)
LEDGER_SHA256: Final = (
    "b0b8783c8783012d5dc966578c82f348c902f6bf0d44583a4a7d5be6a16079aa"
)
LEDGER_OCTETS: Final = 394_277
MAXIMUM_LEDGER_OCTETS: Final = 2_097_152
MAXIMUM_DEPENDENCY_OCTETS: Final = 1_048_576
MAXIMUM_JSON_DEPTH: Final = 16
SAFE_UINT_MAX: Final = 9_007_199_254_740_991
UINT128_MAX: Final = 340_282_366_920_938_463_463_374_607_431_768_211_455

DFA_DOMAIN: Final = "RiskYieldMMA2MStep2AsciiDfaDescriptorV2V4_9F_RawV8"
LANGUAGE_DOMAIN: Final = "RiskYieldMMA2MStep2TextLanguageDescriptorV2V4_9F_RawV8"
SCHEMA_DOMAIN: Final = "RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8"
PATH_DOMAIN: Final = "RiskYieldMMA2MStep2MemberValueSchemaAssignmentV1V4_9F_RawV8"
COMPONENT_DOMAIN: Final = "RiskYieldMMA2MStep2ScalarPathComponentV1V4_9F_RawV8"
UNICODE_SOURCE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeSourceRecordV1V4_9F_RawV8"
UNICODE_PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2UnicodeIdentifierProfileV1V4_9F_RawV8"
)

EXPECTED_COUNTS: Final = {
    "ascii_dfa_count": 9,
    "member_path_assignment_count": 421,
    "text_language_count": 103,
    "unicode_identifier_profile_count": 3,
    "value_schema_count": 200,
}
EXPECTED_SCHEMA_KIND_COUNTS: Final = {
    "ARRAY": 37,
    "EXACT_BOOLEAN": 2,
    "OBJECT_REF": 23,
    "SAFE_INTEGER": 29,
    "TEXT": 109,
}
EXPECTED_LANGUAGE_KIND_COUNTS: Final = {
    "ASCII_DFA": 9,
    "BUILTIN": 6,
    "ENUM": 44,
    "LITERAL": 41,
    "UNICODE_IDENTIFIER": 3,
}


class ScalarPathValidationError(ValueError):
    """Raised for a controlled scalar/path authority rejection."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScalarPathValidationError(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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


def _words(value: str) -> tuple[str, ...]:
    return tuple(value.split())


OPERATION_KIND = _words(
    "ACK_DEADLINE_EXPIRY INGRESS LOCAL_SHUTDOWN SUBSCRIPTION_DISPATCH"
)
MARKER_19 = _words(
    """
    ACK_DEADLINE_NOT_DUE ACK_DEADLINE_TERMINAL_CONVERGED
    ADMISSION_CANDIDATE_COMMITTED ADMISSION_GRANTED ADMISSION_NOT_GRANTED
    ADMISSION_TICKET_ACCEPTED DISPATCH_RETURN_READY INGRESS_RETURN_READY
    KERNEL_SEND_RESULT_CONVERGED LOCAL_CLOSE_DISPATCH_CONVERGED
    OUTBOUND_ARTIFACTS_PREPARED PARSER_UNIT_CONVERGED RAW_PREFIX_COMMITTED
    SHUTDOWN_COMMAND_STARTED SHUTDOWN_TERMINAL_CONVERGED TARGET_EFFECT_ENTRY
    TARGET_ESCAPE_OBSERVED TCP_HALF_CLOSE_CONVERGED TLS_CONTROL_CONVERGED
    """
)
FULL_MARKER_13 = _words(
    """
    ACK_DEADLINE_NOT_DUE ACK_DEADLINE_TERMINAL_CONVERGED DISPATCH_RETURN_READY
    INGRESS_RETURN_READY KERNEL_SEND_RESULT_CONVERGED
    LOCAL_CLOSE_DISPATCH_CONVERGED OUTBOUND_ARTIFACTS_PREPARED
    PARSER_UNIT_CONVERGED RAW_PREFIX_COMMITTED SHUTDOWN_TERMINAL_CONVERGED
    TARGET_ESCAPE_OBSERVED TCP_HALF_CLOSE_CONVERGED TLS_CONTROL_CONVERGED
    """
)
FORBIDDEN_MARKER_5 = _words(
    """
    ADMISSION_CANDIDATE_COMMITTED ADMISSION_GRANTED ADMISSION_NOT_GRANTED
    ADMISSION_TICKET_ACCEPTED TARGET_EFFECT_ENTRY
    """
)
OBSERVATION_METHOD_32 = _words(
    """
    A1_OUTCOME_CAPABILITY A1_OWNER_SNAPSHOT ACTOR_OWNER_SNAPSHOT
    CGROUP_V2_MEMORY_CURRENT DURABLE_GOVERNED_CLOCK_DERIVATION
    DURABLE_PREFIX_REPLAY EXACT_REGISTERED_FIELD_DERIVATION FILESYSTEM_STAT
    GC_CALLBACK_ACCUMULATOR GC_GET_COUNT INGRESS_OWNER_SCALAR LINUX_GETSOCKOPT
    LINUX_IOCTL LINUX_POLL LINUX_SOCKET_IDENTITY LOOP_MANIFEST_CONFIGURATION
    LOOP_PROBE_ACCUMULATOR LOOP_RUNTIME_CONFIGURATION MANIFEST_IDENTITY_LINK
    MARKER_ACCUMULATOR NOT_ATTEMPTED OPERATION_COUNTER_ACCUMULATOR
    OWNER_THREAD_CPU_CLOCK PARSER_OWNER_SCALAR PROCESS_CPU_CLOCK
    PROCFS_SMAPS_ROLLUP PROCFS_STATM PROCFS_STATUS
    SQLITE_CONNECTION_CONFIGURATION SQLITE_QUIESCENT_PRAGMA
    SQLITE_TRANSACTION_ACCUMULATOR TLS_OWNER_SCALAR
    """
)
STATUS_REASON_26 = _words(
    """
    ARTIFACT_BOUND_EXCEEDED CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED
    CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR
    CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE
    CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED
    INSTRUMENTATION_DISABLED MARKER_RING_OVERWROTE_PREFIX
    NOT_APPLICABLE_TO_OPERATION NOT_APPLICABLE_TO_REACHED_STATE
    NO_FROZEN_PRESSURE_POLICY NO_STABLE_SLOW_CALLBACK_SOURCE
    OBSERVATION_WOULD_MUTATE_TARGET
    OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION
    OBSERVATION_WOULD_REENTER_TARGET_LOCK OBSERVER_INTERNAL_ERROR
    OS_OBSERVATION_ERROR PERIODIC_PROBE_DID_NOT_FIRE PERMISSION_DENIED
    PROBE_RING_OVERWROTE_PREFIX PROCESS_LOSS_VOLATILE_MARKER_STATE
    SOURCE_CLOCK_UNAVAILABLE SOURCE_COUNTER_NOT_INSTRUMENTED
    SOURCE_DURABLE_RECORD_ABSENT TARGET_BOUNDARY_NOT_REACHED
    UNSUPPORTED_BY_KERNEL UNSUPPORTED_BY_PYTHON_RUNTIME
    """
)
COUNTER_ID_66 = _words(
    """
    actor.batch_append_maximum_elapsed_ns actor.batch_append_total_elapsed_ns
    actor.event_count actor.operation_appended_events
    actor.operation_batch_append_calls actor.operation_single_append_calls
    actor.pending_control_obligations actor.pending_control_octets
    actor.pending_wire_obligations actor.pending_wire_octets
    actor.rebuild_maximum_elapsed_ns actor.rebuild_total_elapsed_ns
    actor.single_append_maximum_elapsed_ns actor.single_append_total_elapsed_ns
    actor.validation_maximum_elapsed_ns actor.validation_total_elapsed_ns
    ingress.durable_buffer_octets ingress.operation_new_raw_count
    ingress.operation_new_raw_octets ingress.pending_raw_chunks
    ingress.pending_raw_octets kernel.operation_recv_calls
    kernel.operation_recv_ciphertext_octets kernel.operation_send_accepted_octets
    kernel.operation_send_attempts kernel.operation_send_failures
    kernel.operation_send_positive_results parser.last_unit_elapsed_ns
    parser.last_unit_thread_cpu_ns parser.maximum_unit_elapsed_ns
    parser.maximum_unit_thread_cpu_ns parser.operation_application_completions
    parser.operation_automatic_output_chunks parser.operation_automatic_output_octets
    parser.operation_complete_frames parser.operation_error_units
    parser.operation_fragment_units parser.operation_payload_octets
    parser.operation_source_octets parser.operation_units
    parser.total_unit_elapsed_ns parser.total_unit_thread_cpu_ns
    sqlite.begin_maximum_elapsed_ns sqlite.begin_total_elapsed_ns
    sqlite.body_maximum_elapsed_ns sqlite.body_total_elapsed_ns
    sqlite.commit_maximum_elapsed_ns sqlite.commit_total_elapsed_ns
    sqlite.operation_canonical_record_octets sqlite.operation_rollbacks_attempted
    sqlite.operation_rows_written sqlite.operation_transactions_attempted
    sqlite.operation_transactions_begun sqlite.operation_transactions_committed
    sqlite.operation_transactions_rolled_back sqlite.operation_transactions_uncertain
    sqlite.rollback_maximum_elapsed_ns sqlite.rollback_total_elapsed_ns
    tls.operation_ciphertext_fed_octets tls.operation_ciphertext_produced_octets
    tls.operation_plaintext_accepted_octets tls.operation_plaintext_produced_octets
    tls.operation_read_calls tls.operation_want_read_count
    tls.operation_want_write_count tls.operation_write_calls
    """
)
NON_MONOTONE_COUNTER_IDS = frozenset(
    _words(
        """
        actor.pending_control_obligations actor.pending_control_octets
        actor.pending_wire_obligations actor.pending_wire_octets
        ingress.durable_buffer_octets ingress.pending_raw_chunks
        ingress.pending_raw_octets parser.last_unit_elapsed_ns
        parser.last_unit_thread_cpu_ns
        """
    )
)
MONOTONE_COUNTER_ID_57 = tuple(
    value for value in COUNTER_ID_66 if value not in NON_MONOTONE_COUNTER_IDS
)

ENUMS: Final = {
    "ACK_DUE": _words("DUE NOT_DUE"),
    "ADAPTER_SPAN_STATUS": _words("AVAILABLE NOT_APPLICABLE UNAVAILABLE"),
    "ATTEMPT_ADAPTER_POLICY": _words(
        "AVAILABLE_ONLY NOT_APPLICABLE_ONLY UNAVAILABLE_ONLY"
    ),
    "ATTEMPT_POLICY": _words("ATTEMPTED_ONLY NOT_ATTEMPTED_ONLY REASON_RULE"),
    "AVAILABILITY": _words("AVAILABLE CENSORED NOT_APPLICABLE UNAVAILABLE"),
    "AVAILABILITY_ADAPTER_POLICY": _words(
        "AVAILABLE_ONLY NOT_APPLICABLE_ONLY REASON_RULE"
    ),
    "BINDING_REASON_4": _words(
        "ARTIFACT_BOUND_EXCEEDED OBSERVER_INTERNAL_ERROR "
        "SOURCE_CLOCK_UNAVAILABLE TARGET_BOUNDARY_NOT_REACHED"
    ),
    "CENSORING": _words("INTERVAL LEFT NONE RIGHT"),
    "CENSORING_POLICY": _words("DESCRIPTOR_BOUND_MAPPING NONE_ONLY"),
    "CHECKPOINT_BINDING": _words(
        "EXACT_MARKER UNAVAILABLE_MARKER_OBSERVER_FAILURE "
        "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
    ),
    "CLASS_DIGEST_PAIR_POLICY": _words("BOTH_FORBIDDEN BOTH_OR_NEITHER BOTH_REQUIRED"),
    "CLOCK_DOMAIN": _words("BOOTTIME EVENT_LOOP OBSERVER_MONOTONIC"),
    "CLOCK_REASON_5": _words(
        "ARTIFACT_BOUND_EXCEEDED OBSERVER_INTERNAL_ERROR "
        "PROCESS_LOSS_VOLATILE_MARKER_STATE SOURCE_CLOCK_UNAVAILABLE "
        "TARGET_BOUNDARY_NOT_REACHED"
    ),
    "CLOCK_STATUS": _words("AVAILABLE UNAVAILABLE"),
    "CONTAINER_KIND": _words("FIXED_MAP LIST SCALAR"),
    "CONTEXT_PREDICATE_6": _words(
        "OPERATION_EXCLUDED REACHED_STATE_EXCLUDED "
        "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND "
        "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR "
        "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE "
        "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
    "COUNTER_ID_66": COUNTER_ID_66,
    "DISPATCH_DISPOSITION": _words("COMPLETE_LOCAL_SUBMISSION UNKNOWN_DELIVERY"),
    "DURATION_RELATION": _words("EXACT INTERVAL LOWER_BOUND UPPER_BOUND"),
    "ERROR_FORM_4": _words("NONE NON_OS OS STATUS_ONLY"),
    "ERROR_VALUE_POLICY": _words("FORBIDDEN OPTIONAL REQUIRED"),
    "ERRNO_PAIR_POLICY": _words("FORBIDDEN REQUIRED"),
    "FORBIDDEN_MARKER_5": FORBIDDEN_MARKER_5,
    "FULL_MARKER_13": FULL_MARKER_13,
    "INSTRUMENTATION_MODE": _words("OFF ON"),
    "LOGICAL_OPCODE": _words("CLOSE PONG"),
    "MARKER_19": MARKER_19,
    "MONOTONE_COUNTER_ID_57": MONOTONE_COUNTER_ID_57,
    "OBSERVATION_ATTEMPT": _words("ATTEMPTED NOT_ATTEMPTED"),
    "OBSERVATION_METHOD_32": OBSERVATION_METHOD_32,
    "OBSERVATION_ROLE": _words(
        "AFTER_OPERATION BEFORE_OPERATION OPERATION_AGGREGATE "
        "STABLE_CHECKPOINT STARTUP_RECOVERY"
    ),
    "OPERATION_KIND": OPERATION_KIND,
    "OPERATION_RESULT_TYPE": _words(
        "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1 INGRESS_RESULT_EVIDENCE_V2 "
        "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2 "
        "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2"
    ),
    "OPERATION_SPEC_TYPE": _words(
        "ACK_DEADLINE_EXPIRY_SPEC_V1 INGRESS_OPERATION_SPEC_V2 "
        "LOCAL_SHUTDOWN_SPEC_V2 SUBSCRIPTION_DISPATCH_SPEC_V2"
    ),
    "REASON_POLICY": _words("FORBIDDEN NOT_APPLICABLE_REQUIRED UNAVAILABLE_REQUIRED"),
    "REGISTERED_METHOD_31": tuple(
        value for value in OBSERVATION_METHOD_32 if value != "NOT_ATTEMPTED"
    ),
    "REQUIRED_AVAILABILITY_2": _words("NOT_APPLICABLE UNAVAILABLE"),
    "SCALAR_PROFILE": _words(
        "DURATION_BOUND ENUM EXACT_BOOL PLATFORM_ERRNO SAFE_IJSON_COLLECTION "
        "SAFE_IJSON_UINT SHA256 UINT128_DECIMAL"
    ),
    "SOURCE_ERROR_PHASE_3": _words("SECOND_CLOCK_READ SOURCE_ADAPTER VALUE_VALIDATION"),
    "SOURCE_FAILURE_5": _words(
        "FIRST_CLOCK_READ NONE SECOND_CLOCK_READ SOURCE_ADAPTER VALUE_VALIDATION"
    ),
    "STATUS_REASON_26": STATUS_REASON_26,
    "TARGET_VALUE_KIND": _words(
        "BOOL DURATION_BOUND FIXED_UINT_MAP OPTIONAL_TEXT OPTIONAL_UINT TEXT "
        "TEXT_LIST UINT UINT_LIST"
    ),
    "TERMINAL_OUTCOME": _words(
        "CLEAN_ALL_LAYERS FATAL STORAGE_FAILURE TIMEOUT TRUNCATED UNKNOWN_SEND"
    ),
    "VALUE_POLICY": _words("DURATION_BOUND_REQUIRED FORBIDDEN REQUIRED"),
}

ORDERABLE_ENUMS: Final = frozenset(
    {
        "AVAILABILITY",
        "COUNTER_ID_66",
        "ERROR_FORM_4",
        "MARKER_19",
        "MONOTONE_COUNTER_ID_57",
        "OBSERVATION_ATTEMPT",
        "OBSERVATION_ROLE",
        "OPERATION_KIND",
        "REGISTERED_METHOD_31",
        "SOURCE_FAILURE_5",
        "STATUS_REASON_26",
    }
)


def _rows(*values: tuple[int, int, int, int]) -> list[dict[str, int]]:
    return [
        {
            "inclusive_byte_maximum": maximum,
            "inclusive_byte_minimum": minimum,
            "source_state": source,
            "target_state": target,
        }
        for source, minimum, maximum, target in values
    ]


def _dfa_specs() -> dict[str, dict[str, Any]]:
    alpha_upper = ((0x41, 0x5A),)
    alpha_lower = ((0x61, 0x7A),)
    digit = ((0x30, 0x39),)
    underscore = ((0x5F, 0x5F),)

    def transitions(
        source: int, ranges: tuple[tuple[int, int], ...], target: int
    ) -> tuple[tuple[int, int, int, int], ...]:
        return tuple((source, lo, hi, target) for lo, hi in ranges)

    printable = (
        (0, 0x21, 0x7E, 2),
        (1, 0x20, 0x20, 1),
        (1, 0x21, 0x7E, 2),
        (2, 0x20, 0x20, 1),
        (2, 0x21, 0x7E, 2),
    )
    alpha = alpha_upper + alpha_lower
    alnum = digit + alpha
    word = alnum + underscore
    idempotency_tail = digit + ((0x2D, 0x2E), (0x3A, 0x3A)) + alpha + underscore
    request = ((0x2D, 0x2D),) + digit + alpha_upper + underscore + alpha_lower
    return {
        "AVAILABILITY_BITMAP": {
            "accepting": (1,),
            "maximum": 66,
            "minimum": 66,
            "rows": ((0, 0x30, 0x31, 1), (1, 0x30, 0x31, 1)),
            "start": 0,
            "states": 2,
        },
        "ERRNO_NAME": {
            "accepting": (1,),
            "maximum": 64,
            "minimum": 1,
            "rows": (
                *transitions(0, alpha_upper, 1),
                *transitions(1, digit + alpha_upper + underscore, 1),
            ),
            "start": 0,
            "states": 2,
        },
        "EXCEPTION_CLASS": {
            "accepting": (1,),
            "maximum": 256,
            "minimum": 1,
            "rows": (
                *transitions(0, alpha + underscore, 1),
                (1, 0x2E, 0x2E, 2),
                *transitions(1, word, 1),
                *transitions(2, alpha + underscore, 1),
            ),
            "start": 0,
            "states": 3,
        },
        "FIELD_ID": {
            "accepting": (3,),
            "maximum": 256,
            "minimum": 3,
            "rows": (
                *transitions(0, alpha_lower, 1),
                (1, 0x2E, 0x2E, 2),
                *transitions(1, digit + underscore + alpha_lower, 1),
                *transitions(2, digit + underscore + alpha_lower, 3),
                *transitions(3, digit + underscore + alpha_lower, 3),
            ),
            "start": 0,
            "states": 4,
        },
        "IDEMPOTENCY_KEY": {
            "accepting": (1,),
            "maximum": 128,
            "minimum": 1,
            "rows": (
                *transitions(0, alnum, 1),
                *transitions(1, idempotency_tail, 1),
            ),
            "start": 0,
            "states": 2,
        },
        "LAYER": {
            "accepting": (1,),
            "maximum": 254,
            "minimum": 1,
            "rows": (
                *transitions(0, alpha_upper, 1),
                *transitions(1, digit + alpha_upper + underscore, 1),
            ),
            "start": 0,
            "states": 2,
        },
        "PRINTABLE_TRIM_128": {
            "accepting": (2,),
            "maximum": 128,
            "minimum": 1,
            "rows": printable,
            "start": 0,
            "states": 3,
        },
        "PRINTABLE_TRIM_256": {
            "accepting": (2,),
            "maximum": 256,
            "minimum": 1,
            "rows": printable,
            "start": 0,
            "states": 3,
        },
        "REQUEST_ID": {
            "accepting": (1,),
            "maximum": 36,
            "minimum": 1,
            "rows": (
                *transitions(0, request, 1),
                *transitions(1, request, 1),
            ),
            "start": 0,
            "states": 2,
        },
    }


def _lit(value: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("TEXT", nullable, ("LITERAL", value))


def _enum(name: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("TEXT", nullable, ("ENUM", name))


def _dfa(name: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("TEXT", nullable, ("ASCII_DFA", name))


def _unicode(name: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("TEXT", nullable, ("UNICODE_IDENTIFIER", name))


def _builtin(name: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("TEXT", nullable, ("BUILTIN", name))


def _integer(
    minimum: int = 0,
    maximum: int = SAFE_UINT_MAX,
    *,
    nullable: bool = False,
) -> tuple[Any, ...]:
    return ("SAFE_INTEGER", nullable, minimum, maximum)


def _boolean(literal: bool | None = None) -> tuple[Any, ...]:
    return ("EXACT_BOOLEAN", False, literal)


def _array(
    minimum: int,
    maximum: int,
    item: tuple[Any, ...],
) -> tuple[Any, ...]:
    return ("ARRAY", False, minimum, maximum, item)


def _object(type_name: str, *, nullable: bool = False) -> tuple[Any, ...]:
    return ("OBJECT_REF", nullable, type_name)


H = _builtin("LOWERCASE_SHA256")
H_NULL = _builtin("LOWERCASE_SHA256", nullable=True)
RFC3339 = _builtin("RFC3339_UTC")
UINT128 = _builtin("UINT128_DECIMAL")
UINT128_NULL = _builtin("UINT128_DECIMAL", nullable=True)
RAW_JSON = _builtin("RAW_CANONICAL_JSON_STRING")
BASE64_CONTROL = _builtin("CANONICAL_BASE64_CONTROL")
BASE64_INGRESS = _builtin("CANONICAL_BASE64_INGRESS")
UINT = _integer()
UINT_NULL = _integer(nullable=True)
POSITIVE_UINT = _integer(1)
POSITIVE_UINT_NULL = _integer(1, nullable=True)
BOOL = _boolean()
TRUE = _boolean(True)


def _payload_assignments() -> dict[tuple[str, str], tuple[Any, ...]]:
    result: dict[tuple[str, str], tuple[Any, ...]] = {}

    def put(type_name: str, names: str, schema: tuple[Any, ...]) -> None:
        for name in names.split():
            key = (type_name, name)
            _require(key not in result, f"duplicate explicit path authority: {key}")
            result[key] = schema

    # 1. AckDeadlineExpirySpecV1
    t = "CapacityMeasurementAckDeadlineExpirySpecV1"
    put(t, "workload_family", _unicode("RAW_V8_UNICODE_IDENTIFIER_A_V1"))
    put(t, "expected_outbound_subscription_intent_id", H)
    put(t, "due_scenario", _enum("ACK_DUE"))
    put(t, "expected_terminal_cause_code", _lit("ACK_DEADLINE_EXPIRED", nullable=True))

    # 2. AckDeadlineExpiryResultEvidenceV1
    t = "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1"
    put(t, "expired", BOOL)
    put(
        t,
        "due_decision_clock_evidence",
        _object("CapacityMeasurementDueDecisionClockEvidenceV1"),
    )
    put(t, "due_decision_clock_evidence_id", H)
    put(
        t,
        "ack_deadline_expired_event_id terminal_transition_event_id "
        "transport_session_termination_id",
        H_NULL,
    )

    # 3. DispatchWindowEvidenceV1
    t = "CapacityMeasurementDispatchWindowEvidenceV1"
    put(
        t,
        "transport_session_id outbound_subscription_intent_id socket_lease_id "
        "monotonic_clock_domain_id",
        H,
    )
    put(t, "dispatch_started_at dispatch_completed_at", RFC3339)
    put(
        t,
        "dispatch_started_monotonic_ns dispatch_completed_monotonic_ns",
        UINT128,
    )

    # 4. DueDecisionClockEvidenceV1
    t = "CapacityMeasurementDueDecisionClockEvidenceV1"
    put(
        t,
        "transport_session_id outbound_subscription_intent_id "
        "dispatch_window_evidence_id clock_source_manifest_id "
        "monotonic_clock_domain_id",
        H,
    )
    put(
        t,
        "dispatch_window_evidence",
        _object("CapacityMeasurementDispatchWindowEvidenceV1"),
    )
    put(
        t,
        "wall_before_at sampled_at wall_after_at valid_until committed_ack_deadline_at",
        RFC3339,
    )
    put(
        t,
        "monotonic_before_ns monotonic_sampled_ns monotonic_after_ns "
        "committed_ack_deadline_monotonic_ns",
        UINT128,
    )
    put(t, "uncertainty_milliseconds", _integer(0, 3_600_000))
    put(t, "synchronized", TRUE)
    put(t, "clock_resolution_ns", POSITIVE_UINT_NULL)
    put(
        t,
        "source_observation_sha256 chronyd_launch_id "
        "chronyd_runtime_observation_sha256",
        H_NULL,
    )
    put(t, "selectable_source_count", _integer(1, 64, nullable=True))
    put(t, "due_scenario", _enum("ACK_DUE"))

    # 5. IngressLogicalOracleProfileV1
    t = "CapacityMeasurementIngressLogicalOracleProfileV1"
    for name, value in {
        "profile_version": "riskyieldmm_ingress_logical_oracle_profile_v1",
        "oracle_kind": "INDEPENDENT_RESTRICTED_WASM_RFC6455_STREAM",
        "input_chunk_semantics": "EXACT_ORDERED_DECRYPTED_APPLICATION_OCTETS",
        "logical_output_frame_domain": ("RiskYieldMMA2MExactLogicalOutputFramesV4_9F"),
        "raw_ingress_batch_domain": (
            "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"
        ),
        "streamed_digest_algorithm": "CANONICAL_JSON_SHA256_INCREMENTAL_V1",
        "parser_oracle_descriptor_requirement": (
            "COMPLETE_DESCRIPTOR_AND_CONFORMANCE_CORPUS_IN_TARGET_BOUND_UNIVERSE"
        ),
    }.items():
        put(t, name, _lit(value))
    put(
        t,
        "requires_empty_fragmentation_baseline requires_empty_complete_unit_baseline",
        TRUE,
    )
    put(t, "maximum_input_chunks", _integer(128, 128))
    put(
        t,
        "maximum_input_octets maximum_logical_output_payload_octets",
        _integer(65_536, 65_536),
    )
    put(
        t,
        "maximum_parser_units maximum_completed_application_messages "
        "maximum_logical_output_frames",
        _integer(32_768, 32_768),
    )

    # 6. IngressOperationSpecV2
    t = "CapacityMeasurementIngressOperationSpecV2"
    put(t, "workload_family", _unicode("RAW_V8_UNICODE_IDENTIFIER_A_V1"))
    put(t, "ordered_input_chunks_base64", _array(1, 128, BASE64_INGRESS))
    put(t, "input_chunk_count", _integer(1, 128))
    put(t, "input_octet_count", _integer(1, 65_536))
    put(
        t,
        "input_sha256 raw_ingress_batch_sha256 logical_oracle_profile_id "
        "expected_logical_output_frames_sha256",
        H,
    )
    put(t, "timeout_seconds", _integer(1, 300))
    put(
        t,
        "expected_parser_unit_count "
        "expected_completed_application_message_count "
        "expected_logical_output_frame_count",
        _integer(0, 32_768),
    )
    put(t, "expected_logical_output_payload_octets", _integer(0, 65_536))

    # 7. IngressResultEvidenceV2
    t = "CapacityMeasurementIngressResultEvidenceV2"
    put(
        t,
        "ingress_progress_evidence_id final_parser_cursor_id "
        "final_retained_tail_id final_retained_tail_sha256 "
        "sealed_pending_input_id ingress_oracle_baseline_id "
        "observed_logical_output_frames_sha256",
        H,
    )
    put(
        t,
        "final_retained_tail_octets observed_consumed_new_input_octets "
        "observed_logical_output_payload_octets",
        _integer(0, 65_536),
    )
    put(
        t,
        "observed_parser_unit_count observed_completed_application_message_count "
        "observed_logical_output_frame_count",
        _integer(0, 32_768),
    )

    # 8. LocalShutdownSpecV2
    t = "CapacityMeasurementLocalShutdownSpecV2"
    put(t, "workload_family", _unicode("RAW_V8_UNICODE_IDENTIFIER_A_V1"))
    put(t, "timeout_seconds", _integer(1, 300))
    put(t, "expected_terminal_outcome", _enum("TERMINAL_OUTCOME"))
    put(t, "expected_local_close_code", _integer(1000, 1000))
    put(
        t,
        "expected_local_close_reason_sha256",
        _lit(hashlib.sha256(b"").hexdigest()),
    )
    put(
        t,
        "maximum_terminal_ingress_batches "
        "maximum_terminal_ingress_ciphertext_octets "
        "maximum_terminal_ingress_plaintext_octets "
        "maximum_terminal_socket_receive_calls maximum_terminal_tls_records "
        "maximum_terminal_tls_unwrap_iterations "
        "maximum_terminal_zero_progress_iterations",
        POSITIVE_UINT,
    )
    put(
        t,
        "maximum_terminal_ingress_parser_units "
        "maximum_terminal_ingress_automatic_outputs",
        _integer(1, 4_096),
    )
    put(t, "maximum_websocket_send_attempts", _integer(1, 1_048_832))
    put(t, "maximum_tls_control_send_attempts", _integer(1, 256))
    put(t, "maximum_peer_shutdown_polls", _integer(2, 2))

    # 9. LocalShutdownResultEvidenceV2
    t = "CapacityMeasurementLocalShutdownResultEvidenceV2"
    put(t, "local_shutdown_started_event_id", H)
    put(
        t,
        "local_shutdown_deadline_evidence_event_id "
        "local_close_dispatch_completion_event_id "
        "websocket_close_received_transition_event_id",
        H_NULL,
    )
    put(
        t,
        "ordered_terminal_ingress_read_attempt_event_ids "
        "ordered_terminal_ingress_read_result_event_ids "
        "ordered_terminal_raw_ingress_commit_ids "
        "ordered_terminal_raw_ingress_actor_event_ids",
        _array(0, 524_288, H),
    )
    put(
        t,
        "ordered_terminal_parser_transition_event_ids",
        _array(0, 4_096, H),
    )
    put(
        t,
        "shutdown_trace_step_count final_terminal_ingress_batch_count "
        "final_terminal_ingress_ciphertext_octets "
        "final_terminal_ingress_plaintext_octets "
        "final_terminal_socket_receive_call_count "
        "final_terminal_tls_record_count "
        "final_terminal_tls_unwrap_iteration_count "
        "final_terminal_zero_progress_iteration_count "
        "final_terminal_ingress_parser_unit_count "
        "final_terminal_ingress_automatic_output_count "
        "final_websocket_send_attempt_count "
        "final_tls_control_send_attempt_count",
        UINT,
    )
    put(t, "final_peer_shutdown_poll_count", _integer(0, 2))
    put(
        t,
        "shutdown_trace_root_sha256 final_terminal_tls_staging_state_id "
        "decisive_terminal_transition_event_id transport_session_termination_id",
        H,
    )
    put(t, "terminal_outcome", _enum("TERMINAL_OUTCOME"))

    # 10. LogicalOutputFrameV1
    t = "CapacityMeasurementLogicalOutputFrameV1"
    put(t, "opcode", _enum("LOGICAL_OPCODE"))
    put(t, "payload_base64", BASE64_CONTROL)

    # 11. OperationDeclarationV1
    t = "CapacityMeasurementOperationDeclarationV1"
    put(
        t,
        "campaign_manifest_id manifest_authority_id measurement_design_id "
        "workload_plan_id workload_sha256 timeout_policy_id operation_spec_id",
        H,
    )
    put(t, "workload_id", _unicode("RAW_V8_UNICODE_IDENTIFIER_B_V1"))
    put(t, "sample_sequence operation_sequence", POSITIVE_UINT)
    put(t, "trial_index repetition_index", UINT)
    put(t, "is_warmup", BOOL)
    put(t, "stage", _unicode("RAW_V8_UNICODE_IDENTIFIER_A_V1"))
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "operation_spec", _object("CapacityMeasurementOperationSpec"))

    # 12. OperationSpec
    t = "CapacityMeasurementOperationSpec"
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "spec_type", _enum("OPERATION_SPEC_TYPE"))
    put(t, "spec", _object("CapacityMeasurementOperationSpecBody"))

    # 13. OperationResultEvidence
    t = "CapacityMeasurementOperationResultEvidence"
    put(t, "candidate_id attempt_id", H)
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "result_type", _enum("OPERATION_RESULT_TYPE"))
    put(t, "result", _object("CapacityMeasurementOperationResultBody"))

    # 14. SubscriptionDispatchSpecV2
    t = "CapacityMeasurementSubscriptionDispatchSpecV2"
    put(t, "workload_family", _unicode("RAW_V8_UNICODE_IDENTIFIER_A_V1"))
    put(t, "idempotency_key", _dfa("IDEMPOTENCY_KEY"))
    put(t, "transport_subscription_policy_id adapter_policy_id", H)
    put(t, "expected_topic", _unicode("RAW_V8_UNICODE_IDENTIFIER_C_V1"))
    put(t, "expected_operation", _lit("subscribe"))
    put(t, "expected_logical_opcode", _lit("TEXT"))
    put(t, "expected_dispatch_disposition", _enum("DISPATCH_DISPOSITION"))

    # 15. SubscriptionDispatchResultEvidenceV2
    t = "CapacityMeasurementSubscriptionDispatchResultEvidenceV2"
    put(
        t,
        "outbound_subscription_intent_id generated_request_command_sha256 "
        "generated_logical_payload_sha256 dispatch_window_evidence_id "
        "outbound_wire_prepared_event_id tls_ciphertext_prepared_event_id "
        "outbound_dispatch_completed_event_id",
        H,
    )
    put(t, "generated_request_id", _dfa("REQUEST_ID"))
    put(t, "generated_logical_opcode", _lit("TEXT"))
    put(t, "generated_logical_payload_octets", _integer(1, 65_536))
    put(
        t,
        "dispatch_window_evidence",
        _object("CapacityMeasurementDispatchWindowEvidenceV1"),
    )
    put(
        t,
        "ordered_kernel_attempt_event_ids ordered_kernel_result_event_ids",
        _array(1, 256, H),
    )
    put(t, "submitted_ciphertext_octets", _integer(1, 4_194_304))
    put(t, "local_dispatch_disposition", _lit("COMPLETE_LOCAL_SUBMISSION"))

    # 16. CheckpointSelectorEntryV1
    t = "CheckpointSelectorEntryV1"
    put(t, "selector_position", _integer(1, 64))
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "checkpoint_marker_kind", _enum("MARKER_19"))
    put(t, "occurrence_index_within_kind", POSITIVE_UINT)

    # 17. CheckpointSelectorV1
    t = "CheckpointSelectorV1"
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "ordered_entries", _array(0, 64, _object("CheckpointSelectorEntryV1")))
    put(t, "selector_length", _integer(0, 64))
    put(t, "ordered_checkpoint_selector_entry_ids", _array(0, 64, H))

    # 18. MarkerContractV1
    t = "MarkerContractV1"
    put(t, "contract_version", _lit("riskyieldmm_raw_v8_marker_contract_v1"))
    put(t, "ordered_marker_kinds", _array(19, 19, _enum("MARKER_19")))
    put(
        t,
        "ordered_full_checkpoint_marker_kinds",
        _array(13, 13, _enum("FULL_MARKER_13")),
    )
    put(
        t,
        "ordered_checkpoint_operation_records",
        _array(
            13,
            13,
            _object("CapacityMeasurementCheckpointOperationRecordV1"),
        ),
    )
    put(
        t,
        "forbidden_full_checkpoint_marker_kinds",
        _array(5, 5, _enum("FORBIDDEN_MARKER_5")),
    )
    put(t, "minimum_marker_ring_capacity", _integer(8, 8))
    put(t, "maximum_marker_ring_capacity", _integer(4_096, 4_096))
    put(t, "maximum_checkpoint_selector_length", _integer(64, 64))
    put(t, "stable_checkpoint_requires_attempt", TRUE)

    # 19. TargetObservationClockSpanV2
    t = "TargetObservationClockSpanV2"
    put(t, "clock_domain", _enum("CLOCK_DOMAIN"))
    put(t, "span_status", _enum("CLOCK_STATUS"))
    put(t, "started_offset_nanoseconds completed_offset_nanoseconds", UINT_NULL)
    put(t, "unavailable_reason", _enum("CLOCK_REASON_5", nullable=True))

    # 20. TargetObservationContextV2
    t = "TargetObservationContextV2"
    put(t, "observation_role", _enum("OBSERVATION_ROLE"))
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "instrumentation_mode", _enum("INSTRUMENTATION_MODE"))
    put(t, "candidate_id target_field_registry_id", H)
    put(
        t,
        "attempt_id full_checkpoint_selector_id checkpoint_selector_entry_id",
        H_NULL,
    )
    put(t, "marker_ordinal expected_occurrence_index_within_kind", POSITIVE_UINT_NULL)
    put(
        t,
        "checkpoint_marker_kind expected_checkpoint_marker_kind",
        _enum("FULL_MARKER_13", nullable=True),
    )
    put(t, "checkpoint_selector_position", _integer(1, 64, nullable=True))
    put(t, "checkpoint_binding_status", _enum("CHECKPOINT_BINDING", nullable=True))
    put(
        t,
        "checkpoint_binding_unavailable_reason",
        _enum("BINDING_REASON_4", nullable=True),
    )
    put(
        t,
        "observer_clock_span boottime_clock_span loop_clock_span",
        _object("TargetObservationClockSpanV2"),
    )

    # 21. TargetFieldObservationV1
    t = "TargetFieldObservationV1"
    put(t, "target_field_registry_id observation_context_id", H)
    put(t, "field_id", _dfa("FIELD_ID"))
    put(t, "availability", _enum("AVAILABILITY"))
    put(t, "value", _object("CapacityMeasurementTargetValue", nullable=True))
    put(t, "observation_method", _enum("OBSERVATION_METHOD_32"))
    put(t, "observation_attempt", _enum("OBSERVATION_ATTEMPT"))
    put(t, "adapter_span_status", _enum("ADAPTER_SPAN_STATUS"))
    put(
        t,
        "observation_started_offset_nanoseconds "
        "observation_completed_offset_nanoseconds",
        UINT_NULL,
    )
    put(t, "unavailable_reason", _enum("STATUS_REASON_26", nullable=True))
    put(t, "censoring", _enum("CENSORING"))
    put(t, "source_errno_number", POSITIVE_UINT_NULL)
    put(t, "source_errno_name", _dfa("ERRNO_NAME", nullable=True))
    put(t, "source_failure_phase", _enum("SOURCE_FAILURE_5"))
    put(t, "source_error_class", _dfa("EXCEPTION_CLASS", nullable=True))
    put(t, "source_error_detail_sha256", H_NULL)

    # 22. TargetObservationV2
    t = "TargetObservationV2"
    put(t, "observation_context", _object("TargetObservationContextV2"))
    put(t, "observation_context_id", H)
    put(
        t,
        "field_observations",
        _array(185, 185, _object("TargetFieldObservationV1")),
    )

    # 23. TargetObservationRootV2
    t = "TargetObservationRootV2"
    put(t, "candidate_id target_field_registry_id", H)
    put(t, "attempt_id full_checkpoint_selector_id", H_NULL)
    put(t, "operation_kind", _enum("OPERATION_KIND"))
    put(t, "instrumentation_mode", _enum("INSTRUMENTATION_MODE"))
    put(t, "observation_count", _integer(1, 67))
    put(t, "ordered_observation_ids", _array(1, 67, H))

    # 24. TargetFieldRegistryV1
    t = "TargetFieldRegistryV1"
    put(
        t,
        "target_registry_profile",
        _lit("COMPLETE_TYPED_FIELD_AVAILABILITY_V1"),
    )
    put(
        t,
        "status_reason_policy_definition",
        _object("CapacityMeasurementStatusReasonPolicyDefinitionV1"),
    )
    for name, minimum, maximum, item_type in (
        (
            "ordered_vocabulary_definitions",
            25,
            25,
            "CapacityMeasurementVocabularyDefinitionV1",
        ),
        (
            "ordered_value_shape_definitions",
            6,
            6,
            "CapacityMeasurementValueShapeDefinitionV1",
        ),
        (
            "ordered_value_constraint_definitions",
            17,
            17,
            "CapacityMeasurementValueConstraintDefinitionV1",
        ),
        (
            "ordered_cross_field_constraint_definitions",
            1,
            1,
            "CapacityMeasurementCrossFieldConstraintDefinitionV1",
        ),
        (
            "descriptors",
            185,
            185,
            "CapacityMeasurementTargetFieldDescriptorV1",
        ),
    ):
        put(t, name, _array(minimum, maximum, _object(item_type)))
    put(t, "field_count", _integer(185, 185))

    # 25. OperationCounterSnapshotSchemaV1
    t = "OperationCounterSnapshotSchemaV1"
    put(t, "counter_field_count", _integer(66, 66))
    put(t, "ordered_counter_field_ids", _array(66, 66, _enum("COUNTER_ID_66")))
    put(
        t,
        "monotone_counter_field_ids",
        _array(57, 57, _enum("MONOTONE_COUNTER_ID_57")),
    )

    # 26. OperationCounterSnapshotV1
    t = "OperationCounterSnapshotV1"
    put(t, "counter_schema_id", H)
    put(t, "availability_bitmap", _dfa("AVAILABILITY_BITMAP"))
    put(t, "values", _array(66, 66, UINT_NULL))

    # 27. SourceErrorDetailV1
    t = "SourceErrorDetailV1"
    put(t, "field_id", _dfa("FIELD_ID"))
    put(t, "observation_method", _enum("REGISTERED_METHOD_31"))
    put(t, "source_failure_phase", _enum("SOURCE_ERROR_PHASE_3"))
    put(t, "source_errno_number", POSITIVE_UINT_NULL)
    put(t, "source_errno_name", _dfa("ERRNO_NAME", nullable=True))
    put(t, "source_error_class", _dfa("EXCEPTION_CLASS"))

    # 28-39. Registry closure records.
    t = "CapacityMeasurementObservationMethodRolePairV1"
    put(t, "observation_method", _enum("REGISTERED_METHOD_31"))
    put(t, "allowed_roles", _array(1, 5, _enum("OBSERVATION_ROLE")))

    t = "CapacityMeasurementVocabularyDefinitionV1"
    put(t, "vocabulary_id", _dfa("PRINTABLE_TRIM_128"))
    put(t, "members", _array(1, 512, RAW_JSON))

    t = "CapacityMeasurementValueShapeDefinitionV1"
    put(t, "value_shape_id", _dfa("PRINTABLE_TRIM_128"))
    put(t, "container_kind", _enum("CONTAINER_KIND"))
    put(t, "minimum_items maximum_items", UINT_NULL)
    put(t, "ordered_keys", _array(0, 512, RAW_JSON))

    t = "CapacityMeasurementValueConstraintDefinitionV1"
    put(t, "value_constraint_id", _dfa("PRINTABLE_TRIM_128"))
    put(t, "value_kind", _enum("TARGET_VALUE_KIND"))
    put(t, "scalar_profile", _enum("SCALAR_PROFILE"))
    put(
        t,
        "vocabulary_id text_ascii_pattern collection_item_constraint_id "
        "external_authority_profile",
        _dfa("PRINTABLE_TRIM_256", nullable=True),
    )
    put(
        t,
        "integer_minimum integer_maximum text_minimum_utf8_bytes "
        "text_maximum_utf8_bytes",
        UINT_NULL,
    )
    put(t, "decimal_maximum", UINT128_NULL)

    t = "CapacityMeasurementAvailabilityStateRuleV1"
    put(t, "availability", _enum("AVAILABILITY"))
    put(t, "value_policy", _enum("VALUE_POLICY"))
    put(t, "reason_policy", _enum("REASON_POLICY"))
    put(t, "censoring_policy", _enum("CENSORING_POLICY"))
    put(t, "attempt_policy", _enum("ATTEMPT_POLICY"))
    put(t, "adapter_span_policy", _enum("AVAILABILITY_ADAPTER_POLICY"))

    t = "CapacityMeasurementAttemptStateErrorFormsV1"
    put(t, "attempt_state", _enum("OBSERVATION_ATTEMPT"))
    put(t, "permitted_error_forms", _array(1, 4, _enum("ERROR_FORM_4")))
    put(
        t,
        "permitted_failure_phases",
        _array(1, 5, _enum("SOURCE_FAILURE_5")),
    )
    put(t, "adapter_span_policy", _enum("ATTEMPT_ADAPTER_POLICY"))

    t = "CapacityMeasurementStatusReasonRuleV1"
    put(t, "reason", _enum("STATUS_REASON_26"))
    put(t, "required_availability", _enum("REQUIRED_AVAILABILITY_2"))
    put(t, "context_predicate", _enum("CONTEXT_PREDICATE_6", nullable=True))
    put(
        t,
        "attempt_state_error_forms",
        _array(1, 2, _object("CapacityMeasurementAttemptStateErrorFormsV1")),
    )

    t = "CapacityMeasurementErrorFormDefinitionV1"
    put(t, "error_form", _enum("ERROR_FORM_4"))
    put(t, "errno_pair_policy", _enum("ERRNO_PAIR_POLICY"))
    put(t, "error_class_policy error_digest_policy", _enum("ERROR_VALUE_POLICY"))
    put(t, "class_digest_pair_policy", _enum("CLASS_DIGEST_PAIR_POLICY"))

    t = "CapacityMeasurementStatusReasonPolicyDefinitionV1"
    put(t, "status_reason_policy_id", _dfa("PRINTABLE_TRIM_128"))
    put(
        t,
        "availability_state_rules",
        _array(0, 4, _object("CapacityMeasurementAvailabilityStateRuleV1")),
    )
    put(
        t,
        "reason_rules",
        _array(0, 26, _object("CapacityMeasurementStatusReasonRuleV1")),
    )
    put(
        t,
        "error_form_definitions",
        _array(0, 4, _object("CapacityMeasurementErrorFormDefinitionV1")),
    )

    t = "CapacityMeasurementCrossFieldConstraintDefinitionV1"
    put(
        t,
        "cross_field_constraint_id count_field_id sequence_field_id "
        "kind_field_id activation_condition sequence_order cardinality_rule "
        "pairing_rule",
        _dfa("PRINTABLE_TRIM_128"),
    )
    put(t, "maximum_items", POSITIVE_UINT)

    t = "CapacityMeasurementTargetFieldDescriptorV1"
    put(t, "field_id", _dfa("FIELD_ID"))
    put(t, "layer", _dfa("LAYER"))
    put(t, "value_kind", _enum("TARGET_VALUE_KIND"))
    put(
        t,
        "unit value_constraint_id status_reason_policy_id value_shape_id",
        _dfa("PRINTABLE_TRIM_128"),
    )
    put(
        t,
        "observation_method_role_pairs",
        _array(
            0,
            8,
            _object("CapacityMeasurementObservationMethodRolePairV1"),
        ),
    )
    put(
        t,
        "allowed_checkpoint_marker_kinds",
        _array(0, 19, _enum("MARKER_19")),
    )
    put(
        t,
        "applicable_operation_kinds",
        _array(1, 4, _enum("OPERATION_KIND")),
    )
    put(
        t,
        "allowed_status_reasons",
        _array(0, 26, _enum("STATUS_REASON_26")),
    )
    put(t, "censoring_allowed", BOOL)
    put(t, "later_threshold_action_if_unavailable", _lit("FAIL_CLOSED"))
    put(t, "value_shape_keys", _array(0, 512, RAW_JSON))
    put(t, "cross_field_constraint_ids", _array(0, 16, RAW_JSON))

    t = "CapacityMeasurementCheckpointOperationRecordV1"
    put(t, "checkpoint_marker_kind", _enum("FULL_MARKER_13"))
    put(
        t,
        "applicable_operation_kinds",
        _array(1, 4, _enum("OPERATION_KIND")),
    )

    # 40-49. Target-value closure.
    kind_by_type = {
        "CapacityMeasurementUIntValueV1": "UINT",
        "CapacityMeasurementBoolValueV1": "BOOL",
        "CapacityMeasurementTextValueV1": "TEXT",
        "CapacityMeasurementOptionalUIntValueV1": "OPTIONAL_UINT",
        "CapacityMeasurementOptionalTextValueV1": "OPTIONAL_TEXT",
        "CapacityMeasurementUIntListValueV1": "UINT_LIST",
        "CapacityMeasurementTextListValueV1": "TEXT_LIST",
        "CapacityMeasurementFixedUIntMapValueV1": "FIXED_UINT_MAP",
        "CapacityMeasurementDurationBoundValueV1": "DURATION_BOUND",
    }
    for type_name, literal in kind_by_type.items():
        put(type_name, "kind", _lit(literal))

    put("CapacityMeasurementUIntValueV1", "value", UINT)
    put("CapacityMeasurementBoolValueV1", "value", BOOL)
    put(
        "CapacityMeasurementTextValueV1",
        "value",
        _unicode("RAW_V8_UNICODE_IDENTIFIER_B_V1"),
    )
    put("CapacityMeasurementOptionalUIntValueV1", "present", BOOL)
    put("CapacityMeasurementOptionalUIntValueV1", "value", UINT_NULL)
    put("CapacityMeasurementOptionalTextValueV1", "present", BOOL)
    put(
        "CapacityMeasurementOptionalTextValueV1",
        "value",
        _unicode("RAW_V8_UNICODE_IDENTIFIER_B_V1", nullable=True),
    )
    put(
        "CapacityMeasurementUIntListValueV1",
        "values",
        _array(0, 4, UINT),
    )
    put(
        "CapacityMeasurementTextListValueV1",
        "values",
        _array(0, 4, _unicode("RAW_V8_UNICODE_IDENTIFIER_B_V1")),
    )
    put(
        "CapacityMeasurementFixedUIntMapEntryV1",
        "key",
        _dfa("PRINTABLE_TRIM_128"),
    )
    put("CapacityMeasurementFixedUIntMapEntryV1", "value", UINT)
    put(
        "CapacityMeasurementFixedUIntMapValueV1",
        "ordered",
        _array(1, 32, _object("CapacityMeasurementFixedUIntMapEntryV1")),
    )
    put(
        "CapacityMeasurementDurationBoundValueV1",
        "relation",
        _enum("DURATION_RELATION"),
    )
    put(
        "CapacityMeasurementDurationBoundValueV1",
        "lower_nanoseconds upper_nanoseconds",
        UINT_NULL,
    )
    return result


def _ascii_dfa_descriptors() -> tuple[list[dict[str, Any]], dict[str, str]]:
    descriptors: list[dict[str, Any]] = []
    identifier_by_name: dict[str, str] = {}
    for name, spec in sorted(_dfa_specs().items()):
        payload = {
            "maximum_octets": spec["maximum"],
            "minimum_octets": spec["minimum"],
            "ordered_accepting_states": list(spec["accepting"]),
            "ordered_transition_rows": _rows(*sorted(spec["rows"])),
            "start_state": spec["start"],
            "state_count": spec["states"],
        }
        identifier = _semantic_id(DFA_DOMAIN, payload)
        identifier_by_name[name] = identifier
        descriptors.append({**payload, "ascii_dfa_id": identifier})
    return sorted(
        descriptors, key=lambda item: item["ascii_dfa_id"]
    ), identifier_by_name


def _unicode_profile_records(
    core: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    source_identifier_by_name: dict[str, str] = {}
    for source in core["unicode_source_specs"]:
        payload = {
            key: source[key]
            for key in (
                "source_name",
                "unicode_version",
                "official_url",
                "byte_count",
                "sha256",
            )
        }
        source_identifier_by_name[source["source_name"]] = _semantic_id(
            UNICODE_SOURCE_DOMAIN,
            payload,
        )
    records: list[dict[str, Any]] = []
    identifier_by_name: dict[str, str] = {}
    for profile in core["identifier_profile_specs"]:
        payload = {
            "profile_id": profile["profile_id"],
            "unicode_version": profile["unicode_version"],
            "normalization_form": profile["normalization_form"],
            "maximum_scalar_values": profile["maximum_scalar_values"],
            "maximum_utf8_octets": profile["maximum_utf8_octets"],
            "forbidden_code_point_ranges": profile["forbidden_code_point_ranges"],
            "edge_trim_code_points": profile["edge_trim_code_points"],
            "unicode_source_record_ids": [
                source_identifier_by_name[name]
                for name in profile["unicode_source_names"]
            ],
        }
        identifier = _semantic_id(UNICODE_PROFILE_DOMAIN, payload)
        identifier_by_name[profile["profile_id"]] = identifier
        records.append({**payload, "unicode_identifier_profile_id": identifier})
    return (
        sorted(records, key=lambda item: item["unicode_identifier_profile_id"]),
        identifier_by_name,
    )


def _language_payload(
    key: tuple[Any, ...],
    dfa_identifier_by_name: dict[str, str],
    profile_identifier_by_name: dict[str, str],
) -> dict[str, Any]:
    kind, name = key
    payload: dict[str, Any] = {
        "ascii_dfa_id": None,
        "built_in_language_kind": None,
        "decimal_maximum": None,
        "language_kind": kind,
        "maximum_decoded_octets": None,
        "maximum_utf8_octets": None,
        "minimum_decoded_octets": None,
        "minimum_utf8_octets": None,
        "ordered_literals": [],
        "ordering_semantics": "NONE",
        "unicode_identifier_profile_id": None,
    }
    if kind == "LITERAL":
        payload["ordered_literals"] = [name]
    elif kind == "ENUM":
        _require(name in ENUMS, f"unknown explicit enum language: {name}")
        payload["ordered_literals"] = list(ENUMS[name])
        if name in ORDERABLE_ENUMS:
            payload["ordering_semantics"] = "UNICODE_SCALAR_LEXICOGRAPHIC"
    elif kind == "ASCII_DFA":
        _require(name in dfa_identifier_by_name, f"unknown explicit DFA: {name}")
        payload["ascii_dfa_id"] = dfa_identifier_by_name[name]
        if name in {"FIELD_ID", "PRINTABLE_TRIM_128"}:
            payload["ordering_semantics"] = "UNICODE_SCALAR_LEXICOGRAPHIC"
    elif kind == "UNICODE_IDENTIFIER":
        _require(
            name in profile_identifier_by_name,
            f"unknown explicit Unicode profile: {name}",
        )
        payload["unicode_identifier_profile_id"] = profile_identifier_by_name[name]
    elif kind == "BUILTIN":
        if name == "CANONICAL_BASE64_CONTROL":
            payload.update(
                {
                    "built_in_language_kind": "CANONICAL_BASE64",
                    "maximum_decoded_octets": 125,
                    "maximum_utf8_octets": 168,
                    "minimum_decoded_octets": 0,
                    "minimum_utf8_octets": 0,
                }
            )
        elif name == "CANONICAL_BASE64_INGRESS":
            payload.update(
                {
                    "built_in_language_kind": "CANONICAL_BASE64",
                    "maximum_decoded_octets": 65_536,
                    "maximum_utf8_octets": 87_384,
                    "minimum_decoded_octets": 1,
                    "minimum_utf8_octets": 4,
                }
            )
        elif name == "UINT128_DECIMAL":
            payload["built_in_language_kind"] = "UINT128_DECIMAL"
            payload["decimal_maximum"] = str(UINT128_MAX)
        elif name in {
            "LOWERCASE_SHA256",
            "RAW_CANONICAL_JSON_STRING",
            "RFC3339_UTC",
        }:
            payload["built_in_language_kind"] = name
            if name == "RAW_CANONICAL_JSON_STRING":
                payload["ordering_semantics"] = "UNICODE_SCALAR_LEXICOGRAPHIC"
        else:
            raise ScalarPathValidationError(
                f"unknown explicit built-in language: {name}"
            )
    else:
        raise ScalarPathValidationError(f"unknown language kind: {kind}")
    return payload


def _collect_schema_specs(
    assignments: dict[tuple[str, str], tuple[Any, ...]],
    topology: dict[str, Any],
) -> tuple[set[tuple[Any, ...]], set[tuple[Any, ...]]]:
    schema_specs: set[tuple[Any, ...]] = set()
    language_keys: set[tuple[Any, ...]] = set()

    def visit(spec: tuple[Any, ...]) -> None:
        if spec in schema_specs:
            return
        schema_specs.add(spec)
        if spec[0] == "TEXT":
            language_keys.add(spec[2])
        elif spec[0] == "ARRAY":
            visit(spec[4])

    for schema in assignments.values():
        visit(schema)
    visit(_lit(CANONICALIZATION_VERSION))
    visit(_lit(MEASUREMENT_SCHEMA_VERSION))
    visit(H)
    for descriptor in topology["type_descriptors"]:
        if (
            descriptor["type_form"] == "RECORD"
            and descriptor["type_role"] == "STANDALONE"
        ):
            visit(_lit(descriptor["described_record_domain"]))
    return schema_specs, language_keys


def _schema_payload(
    spec: tuple[Any, ...],
    language_identifier_by_key: dict[tuple[Any, ...], str],
    schema_identifier_by_spec: dict[tuple[Any, ...], str],
) -> dict[str, Any]:
    kind = spec[0]
    payload: dict[str, Any] = {
        "array_item_value_schema_id": None,
        "array_maximum_items": None,
        "array_minimum_items": None,
        "boolean_literal": None,
        "integer_maximum": None,
        "integer_minimum": None,
        "nullable": spec[1],
        "referenced_type_name": None,
        "schema_kind": kind,
        "text_language_id": None,
    }
    if kind == "EXACT_BOOLEAN":
        payload["boolean_literal"] = spec[2]
    elif kind == "SAFE_INTEGER":
        payload["integer_minimum"] = spec[2]
        payload["integer_maximum"] = spec[3]
    elif kind == "TEXT":
        payload["text_language_id"] = language_identifier_by_key[spec[2]]
    elif kind == "ARRAY":
        payload["array_minimum_items"] = spec[2]
        payload["array_maximum_items"] = spec[3]
        payload["array_item_value_schema_id"] = schema_identifier_by_spec[spec[4]]
    elif kind == "OBJECT_REF":
        payload["referenced_type_name"] = spec[2]
    else:
        raise ScalarPathValidationError(f"unknown value-schema kind: {kind}")
    return payload


def _catalogs(
    assignments: dict[tuple[str, str], tuple[Any, ...]],
    topology: dict[str, Any],
    core: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[tuple[Any, ...], str],
]:
    dfa_descriptors, dfa_identifier_by_name = _ascii_dfa_descriptors()
    profile_records, profile_identifier_by_name = _unicode_profile_records(core)
    schema_specs, language_keys = _collect_schema_specs(assignments, topology)

    language_descriptors: list[dict[str, Any]] = []
    language_identifier_by_key: dict[tuple[Any, ...], str] = {}
    for key in sorted(language_keys, key=repr):
        payload = _language_payload(
            key,
            dfa_identifier_by_name,
            profile_identifier_by_name,
        )
        identifier = _semantic_id(LANGUAGE_DOMAIN, payload)
        language_identifier_by_key[key] = identifier
        language_descriptors.append({**payload, "text_language_id": identifier})

    schema_identifier_by_spec: dict[tuple[Any, ...], str] = {}
    unresolved = set(schema_specs)
    while unresolved:
        progressed = False
        for spec in sorted(unresolved, key=repr):
            if spec[0] == "ARRAY" and spec[4] not in schema_identifier_by_spec:
                continue
            payload = _schema_payload(
                spec,
                language_identifier_by_key,
                schema_identifier_by_spec,
            )
            schema_identifier_by_spec[spec] = _semantic_id(SCHEMA_DOMAIN, payload)
            unresolved.remove(spec)
            progressed = True
            break
        _require(progressed, "value-schema dependency graph is cyclic")

    value_schemas = []
    for spec, identifier in schema_identifier_by_spec.items():
        payload = _schema_payload(
            spec,
            language_identifier_by_key,
            schema_identifier_by_spec,
        )
        value_schemas.append({**payload, "value_schema_id": identifier})
    return (
        dfa_descriptors,
        sorted(language_descriptors, key=lambda item: item["text_language_id"]),
        profile_records,
        sorted(value_schemas, key=lambda item: item["value_schema_id"]),
        schema_identifier_by_spec,
    )


def _member_path_assignments(
    topology: dict[str, Any],
    explicit: dict[tuple[str, str], tuple[Any, ...]],
    schema_identifier_by_spec: dict[tuple[Any, ...], str],
) -> list[dict[str, Any]]:
    descriptor_by_name = {
        descriptor["type_name"]: descriptor
        for descriptor in topology["type_descriptors"]
        if descriptor["type_form"] == "RECORD"
    }
    assignments: list[dict[str, Any]] = []
    consumed: set[tuple[str, str]] = set()
    for path in topology["path_ledger"]["record_member_paths"]:
        type_name = path["source_type_name"]
        member_name = path["member_name"]
        member_role = path["member_role"]
        key = (type_name, member_name)
        if member_role == "ENVELOPE_PREFIX":
            if member_name == "canonicalization_version":
                spec = _lit(CANONICALIZATION_VERSION)
            elif member_name == "measurement_schema_version":
                spec = _lit(MEASUREMENT_SCHEMA_VERSION)
            elif member_name == "record_domain":
                spec = _lit(descriptor_by_name[type_name]["described_record_domain"])
            else:
                raise ScalarPathValidationError(
                    f"unknown envelope-prefix path without fallback: {key}"
                )
        elif member_role == "IDENTITY_FIELD":
            _require(
                member_name == descriptor_by_name[type_name]["identity_field"],
                f"identity-field topology differs: {key}",
            )
            spec = H
        else:
            _require(key in explicit, f"member path has no explicit schema: {key}")
            spec = explicit[key]
            consumed.add(key)
        payload = {
            "assignment_position": path["path_position"],
            "member_name": member_name,
            "member_position": path["member_position"],
            "member_role": member_role,
            "source_type_name": type_name,
            "typed_member_path": path["typed_member_path"],
            "value_schema_id": schema_identifier_by_spec[spec],
        }
        assignments.append(
            {
                **payload,
                "member_value_schema_assignment_id": _semantic_id(
                    PATH_DOMAIN,
                    payload,
                ),
            }
        )
    _require(
        consumed == set(explicit),
        "explicit path authority has unreachable or unconsumed assignments",
    )
    return assignments


def _expected_ledger(
    topology: dict[str, Any],
    core: dict[str, Any],
) -> dict[str, Any]:
    explicit = _payload_assignments()
    (
        dfa_descriptors,
        language_descriptors,
        profile_records,
        value_schemas,
        schema_identifier_by_spec,
    ) = _catalogs(explicit, topology, core)
    path_assignments = _member_path_assignments(
        topology,
        explicit,
        schema_identifier_by_spec,
    )
    language_kind_counts = dict(
        sorted(Counter(item["language_kind"] for item in language_descriptors).items())
    )
    schema_kind_counts = dict(
        sorted(Counter(item["schema_kind"] for item in value_schemas).items())
    )
    counts = {
        "ascii_dfa_count": len(dfa_descriptors),
        "member_path_assignment_count": len(path_assignments),
        "text_language_count": len(language_descriptors),
        "unicode_identifier_profile_count": len(profile_records),
        "value_schema_count": len(value_schemas),
    }
    _require(counts == EXPECTED_COUNTS, f"scalar catalog count drift: {counts}")
    _require(
        language_kind_counts == EXPECTED_LANGUAGE_KIND_COUNTS,
        f"text-language kind count drift: {language_kind_counts}",
    )
    _require(
        schema_kind_counts == EXPECTED_SCHEMA_KIND_COUNTS,
        f"value-schema kind count drift: {schema_kind_counts}",
    )
    component_payload = {
        "ascii_dfa_ids": [item["ascii_dfa_id"] for item in dfa_descriptors],
        "component_status": COMPONENT_STATUS,
        "core_ledger_sha256": CORE_SHA256,
        "member_value_schema_assignment_ids": [
            item["member_value_schema_assignment_id"] for item in path_assignments
        ],
        "text_language_ids": [
            item["text_language_id"] for item in language_descriptors
        ],
        "topology_ledger_sha256": TOPOLOGY_SHA256,
        "unicode_identifier_profile_ids": [
            item["unicode_identifier_profile_id"] for item in profile_records
        ],
        "value_schema_ids": [item["value_schema_id"] for item in value_schemas],
    }
    return {
        "ascii_dfa_count": counts["ascii_dfa_count"],
        "canonicalization_version": CANONICALIZATION_VERSION,
        "component_status": COMPONENT_STATUS,
        "core_ledger_sha256": CORE_SHA256,
        "language_kind_counts": language_kind_counts,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "member_path_assignment_count": counts["member_path_assignment_count"],
        "ordered_ascii_dfa_descriptors": dfa_descriptors,
        "ordered_member_path_assignments": path_assignments,
        "ordered_text_language_descriptors": language_descriptors,
        "ordered_unicode_identifier_profiles": profile_records,
        "ordered_value_schemas": value_schemas,
        "scalar_path_component_sha256": _semantic_id(
            COMPONENT_DOMAIN,
            component_payload,
        ),
        "scalar_path_ledger_version": LEDGER_VERSION,
        "text_language_count": counts["text_language_count"],
        "topology_ledger_sha256": TOPOLOGY_SHA256,
        "unicode_identifier_profile_count": counts["unicode_identifier_profile_count"],
        "value_schema_count": counts["value_schema_count"],
        "value_schema_kind_counts": schema_kind_counts,
    }


def _reject_json_constant(value: str) -> Any:
    raise ScalarPathValidationError(f"ledger contains non-finite JSON: {value}")


def _reject_json_float(value: str) -> Any:
    raise ScalarPathValidationError(f"ledger contains a float: {value}")


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"ledger contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_json_nesting(text: str) -> None:
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
                depth <= MAXIMUM_JSON_DEPTH,
                "ledger JSON nesting exceeds the reviewed bound",
            )
        elif character in "]}":
            depth -= 1
            _require(depth >= 0, "ledger JSON closes an unopened container")
    _require(not in_string, "ledger contains an unterminated JSON string")
    _require(depth == 0, "ledger JSON has unclosed containers")


def _require_scalar_strings(value: Any) -> None:
    if type(value) is str:
        _require(
            not any(0xD800 <= ord(character) <= 0xDFFF for character in value),
            "ledger contains a non-scalar JSON string",
        )
    elif type(value) is list:
        for item in value:
            _require_scalar_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require_scalar_strings(key)
            _require_scalar_strings(item)


def _secure_read_json(
    path: Path,
    *,
    maximum_octets: int,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScalarPathValidationError(f"cannot open {label}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a direct regular file")
        _require(0 < before.st_size <= maximum_octets, f"{label} size is invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(maximum_octets + 1)
        after = os.fstat(descriptor)
        before_fingerprint = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_fingerprint = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        _require(
            before_fingerprint == after_fingerprint,
            f"{label} changed while it was read",
        )
        _require(len(raw) == before.st_size, f"{label} read was incomplete")
    finally:
        os.close(descriptor)
    _require(len(raw) <= maximum_octets, f"{label} exceeds the reviewed bound")
    _require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} contains a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScalarPathValidationError(f"{label} is not strict UTF-8") from exc
    _validate_json_nesting(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except (
        json.JSONDecodeError,
        RecursionError,
        ScalarPathValidationError,
        ValueError,
    ) as exc:
        raise ScalarPathValidationError(f"{label} is not valid JSON: {exc}") from exc
    _require(type(value) is dict, f"{label} root is not an exact object")
    _require_scalar_strings(value)
    _require(
        raw == _canonical_pretty_bytes(value),
        f"{label} bytes are not canonical pretty JSON",
    )
    return value, raw


def _validate_dfa(descriptor: dict[str, Any]) -> None:
    state_count = descriptor["state_count"]
    _require(
        type(state_count) is int and 1 <= state_count <= SAFE_UINT_MAX,
        "DFA state_count is invalid",
    )
    start = descriptor["start_state"]
    accepting = descriptor["ordered_accepting_states"]
    rows = descriptor["ordered_transition_rows"]
    _require(type(start) is int and 0 <= start < state_count, "DFA start is invalid")
    _require(
        type(accepting) is list
        and accepting
        and all(type(item) is int and 0 <= item < state_count for item in accepting)
        and accepting == sorted(set(accepting)),
        "DFA accepting states are invalid",
    )
    row_keys = [
        (
            row["source_state"],
            row["inclusive_byte_minimum"],
            row["inclusive_byte_maximum"],
            row["target_state"],
        )
        for row in rows
    ]
    _require(row_keys == sorted(row_keys), "DFA transition rows are not canonical")
    previous_by_source: dict[int, int] = {}
    forward: dict[int, set[int]] = {state: set() for state in range(state_count)}
    reverse: dict[int, set[int]] = {state: set() for state in range(state_count)}
    for source, minimum, maximum, target in row_keys:
        _require(
            all(type(item) is int for item in (source, minimum, maximum, target))
            and 0 <= source < state_count
            and 0 <= target < state_count
            and 0 <= minimum <= maximum <= 0x7F,
            "DFA transition row is invalid",
        )
        _require(
            minimum > previous_by_source.get(source, -1),
            "DFA transition ranges overlap",
        )
        previous_by_source[source] = maximum
        forward[source].add(target)
        reverse[target].add(source)

    def reachable(seed: set[int], graph: dict[int, set[int]]) -> set[int]:
        found = set(seed)
        queue = deque(seed)
        while queue:
            for target in graph[queue.popleft()]:
                if target not in found:
                    found.add(target)
                    queue.append(target)
        return found

    _require(
        reachable({start}, forward) == set(range(state_count)),
        "DFA contains an unreachable state",
    )
    _require(
        reachable(set(accepting), reverse) == set(range(state_count)),
        "DFA state cannot reach acceptance",
    )
    minimum = descriptor["minimum_octets"]
    maximum = descriptor["maximum_octets"]
    _require(
        type(minimum) is int
        and type(maximum) is int
        and 0 <= minimum <= maximum <= SAFE_UINT_MAX,
        "DFA octet bounds are invalid",
    )
    payload = {key: value for key, value in descriptor.items() if key != "ascii_dfa_id"}
    _require(
        descriptor["ascii_dfa_id"] == _semantic_id(DFA_DOMAIN, payload),
        "DFA semantic ID differs",
    )


def _validate_graph(ledger: dict[str, Any], topology: dict[str, Any]) -> None:
    dfa_descriptors = ledger["ordered_ascii_dfa_descriptors"]
    languages = ledger["ordered_text_language_descriptors"]
    profiles = ledger["ordered_unicode_identifier_profiles"]
    schemas = ledger["ordered_value_schemas"]
    assignments = ledger["ordered_member_path_assignments"]
    for descriptor in dfa_descriptors:
        _validate_dfa(descriptor)
    for catalog, id_name, label in (
        (dfa_descriptors, "ascii_dfa_id", "DFA"),
        (languages, "text_language_id", "language"),
        (profiles, "unicode_identifier_profile_id", "Unicode profile"),
        (schemas, "value_schema_id", "value schema"),
        (
            assignments,
            "member_value_schema_assignment_id",
            "member assignment",
        ),
    ):
        identifiers = [item[id_name] for item in catalog]
        _require(len(identifiers) == len(set(identifiers)), f"duplicate {label} ID")
        if label != "member assignment":
            _require(identifiers == sorted(identifiers), f"{label} order differs")
    language_ids = {item["text_language_id"] for item in languages}
    schema_ids = {item["value_schema_id"] for item in schemas}
    dfa_ids = {item["ascii_dfa_id"] for item in dfa_descriptors}
    profile_ids = {item["unicode_identifier_profile_id"] for item in profiles}
    referenced_languages: set[str] = set()
    referenced_schemas: set[str] = set()
    for schema in schemas:
        payload = {
            key: value for key, value in schema.items() if key != "value_schema_id"
        }
        _require(
            schema["value_schema_id"] == _semantic_id(SCHEMA_DOMAIN, payload),
            "value-schema semantic ID differs",
        )
        if schema["text_language_id"] is not None:
            _require(
                schema["text_language_id"] in language_ids,
                "value schema references an unknown text language",
            )
            referenced_languages.add(schema["text_language_id"])
        if schema["array_item_value_schema_id"] is not None:
            _require(
                schema["array_item_value_schema_id"] in schema_ids,
                "array references an unknown item schema",
            )
            referenced_schemas.add(schema["array_item_value_schema_id"])
    for language in languages:
        payload = {
            key: value for key, value in language.items() if key != "text_language_id"
        }
        _require(
            language["text_language_id"] == _semantic_id(LANGUAGE_DOMAIN, payload),
            "text-language semantic ID differs",
        )
        if language["ascii_dfa_id"] is not None:
            _require(language["ascii_dfa_id"] in dfa_ids, "language DFA is unresolved")
        if language["unicode_identifier_profile_id"] is not None:
            _require(
                language["unicode_identifier_profile_id"] in profile_ids,
                "language Unicode profile is unresolved",
            )
    _require(
        referenced_languages == language_ids,
        "text-language catalog contains unreachable rows",
    )
    assignment_schema_ids = {item["value_schema_id"] for item in assignments}
    reachable_schemas = set(assignment_schema_ids)
    queue = deque(assignment_schema_ids)
    schema_by_id = {item["value_schema_id"]: item for item in schemas}
    topology_type_names = {item["type_name"] for item in topology["type_descriptors"]}
    for schema in schemas:
        if schema["schema_kind"] == "OBJECT_REF":
            _require(
                schema["referenced_type_name"] in topology_type_names,
                "object schema references a type outside the 52-node topology",
            )
    while queue:
        item = schema_by_id[queue.popleft()]
        child = item["array_item_value_schema_id"]
        if child is not None and child not in reachable_schemas:
            reachable_schemas.add(child)
            queue.append(child)
    _require(
        reachable_schemas == schema_ids, "value-schema catalog has unreachable rows"
    )
    _require(
        [item["assignment_position"] for item in assignments] == list(range(1, 422)),
        "member assignment positions differ",
    )
    expected_path_keys = [
        (
            item["source_type_name"],
            item["member_position"],
            item["member_name"],
            tuple(item["typed_member_path"]),
            item["member_role"],
        )
        for item in topology["path_ledger"]["record_member_paths"]
    ]
    actual_path_keys = [
        (
            item["source_type_name"],
            item["member_position"],
            item["member_name"],
            tuple(item["typed_member_path"]),
            item["member_role"],
        )
        for item in assignments
    ]
    _require(actual_path_keys == expected_path_keys, "member path closure differs")
    assignment_by_path = {
        (item["source_type_name"], tuple(item["typed_member_path"])): item
        for item in assignments
    }
    for reference in topology["path_ledger"]["typed_reference_paths"]:
        assignment = assignment_by_path[
            (reference["source_type_name"], tuple(reference["typed_member_path"]))
        ]
        schema = schema_by_id[assignment["value_schema_id"]]
        if reference["reference_kind"] == "ARRAY_OBJECT_REF":
            _require(
                schema["schema_kind"] == "ARRAY",
                "array-object topology path is not assigned an ARRAY schema",
            )
            schema = schema_by_id[schema["array_item_value_schema_id"]]
        _require(
            schema["schema_kind"] == "OBJECT_REF"
            and schema["referenced_type_name"] == reference["referenced_type_name"],
            "typed-reference schema target differs from topology",
        )
    for assignment in assignments:
        _require(
            assignment["value_schema_id"] in schema_ids,
            "member assignment references an unknown schema",
        )
        payload = {
            key: value
            for key, value in assignment.items()
            if key != "member_value_schema_assignment_id"
        }
        _require(
            assignment["member_value_schema_assignment_id"]
            == _semantic_id(PATH_DOMAIN, payload),
            "member assignment semantic ID differs",
        )


def validate_scalar_path_ledger(
    ledger_path: Path,
    topology_path: Path,
    core_path: Path,
) -> dict[str, Any]:
    topology, topology_raw = _secure_read_json(
        topology_path,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        label="topology ledger",
    )
    core, core_raw = _secure_read_json(
        core_path,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        label="core ledger",
    )
    _require(_sha256(topology_raw) == TOPOLOGY_SHA256, "topology digest differs")
    _require(_sha256(core_raw) == CORE_SHA256, "core digest differs")
    ledger, raw = _secure_read_json(
        ledger_path,
        maximum_octets=MAXIMUM_LEDGER_OCTETS,
        label="scalar/path ledger",
    )
    expected = _expected_ledger(topology, core)
    _validate_graph(ledger, topology)
    _require(ledger == expected, "scalar/path ledger differs from explicit authority")
    _require(len(raw) == LEDGER_OCTETS, "scalar/path ledger octet count differs")
    _require(_sha256(raw) == LEDGER_SHA256, "scalar/path ledger digest differs")
    return {
        "ascii_dfa_count": ledger["ascii_dfa_count"],
        "component_status": ledger["component_status"],
        "core_ledger_sha256": CORE_SHA256,
        "ledger_octets": len(raw),
        "ledger_path": str(ledger_path),
        "ledger_sha256": _sha256(raw),
        "member_path_assignment_count": ledger["member_path_assignment_count"],
        "scalar_path_component_sha256": ledger["scalar_path_component_sha256"],
        "text_language_count": ledger["text_language_count"],
        "topology_ledger_sha256": TOPOLOGY_SHA256,
        "unicode_identifier_profile_count": ledger["unicode_identifier_profile_count"],
        "value_schema_count": ledger["value_schema_count"],
    }


def _write_expected(
    output: Path,
    topology_path: Path,
    core_path: Path,
) -> None:
    topology, topology_raw = _secure_read_json(
        topology_path,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        label="topology ledger",
    )
    core, core_raw = _secure_read_json(
        core_path,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        label="core ledger",
    )
    _require(_sha256(topology_raw) == TOPOLOGY_SHA256, "topology digest differs")
    _require(_sha256(core_raw) == CORE_SHA256, "core digest differs")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_canonical_pretty_bytes(_expected_ledger(topology, core)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--topology", type=Path, required=True)
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--write-expected-ledger", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _require(
            (arguments.ledger is None) != (arguments.write_expected_ledger is None),
            "exactly one of --ledger and --write-expected-ledger is required",
        )
        if arguments.write_expected_ledger is not None:
            _write_expected(
                arguments.write_expected_ledger,
                arguments.topology,
                arguments.core,
            )
            return 0
        report = validate_scalar_path_ledger(
            arguments.ledger,
            arguments.topology,
            arguments.core,
        )
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        ScalarPathValidationError,
        TypeError,
    ) as exc:
        print(
            f"Raw-V8 Step-2 external-schema V2 scalar/path error: {exc}",
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

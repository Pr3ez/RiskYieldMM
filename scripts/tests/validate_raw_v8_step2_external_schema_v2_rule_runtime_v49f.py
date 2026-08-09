#!/usr/bin/env python3
"""Execute the frozen Raw-V8 External Schema V2 value-schema runtime.

This component is deliberately independent of production and of the legacy
inventory generator.  It securely loads and hash-pins the accepted structural
registry and the reviewed composite-literal authority.  It implements
declared-type value validation for every frozen scalar, array, record, and
tagged-union schema plus all 52 operators, all 42 frozen rule-expression
roots, all eight frozen rule applications, and both fixed-position resolvers.
Constructive maxima and production integration remain explicit later gates.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
RUNTIME_STATUS: Final = (
    "APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING"
)

STRUCTURAL_REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
RULE_LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
STRUCTURAL_REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
RULE_LITERAL_AUTHORITY_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
RULE_LITERAL_AUTHORITY_OCTETS: Final = 484_301
MAXIMUM_ARTIFACT_OCTETS: Final = 16_777_216
MAXIMUM_JSON_DEPTH: Final = 16
MAXIMUM_VALIDATION_WORK: Final = 4_202_555
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
UINT128_MAXIMUM: Final = (1 << 128) - 1
UINT128_MAXIMUM_TEXT: Final = str(UINT128_MAXIMUM)
INT128_MINIMUM: Final = -(1 << 127)
INT128_MAXIMUM: Final = (1 << 127) - 1
_LOAD_CAPABILITY: Final = object()

COMPLEX_OPERATOR_NAMES: Final = frozenset(
    {
        "A1_FIFO_FIELDS_VALID",
        "BITMAP_NULLABILITY_MATCHES",
        "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
        "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED",
        "FIELD_OBSERVATION_INTRINSIC_VALID",
        "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
        "OPERATION_RESULT_MATCHES_SIGNED_SPEC",
        "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD",
        "TARGET_VALUE_SATISFIES_DESCRIPTOR",
        "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        "V2_ROOT_SEQUENCE_SELECTOR_VALID",
    }
)
GENERIC_OPERATOR_NAMES: Final = frozenset(
    {
        "AND",
        "ARRAY_CONTAINS",
        "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
        "ARRAY_LENGTH",
        "ARRAY_POSITIONAL_EQUAL",
        "ARRAY_PROJECT_REQUIRED_MEMBER",
        "ARRAY_STRICT_ASCENDING",
        "ARRAY_UNIQUE",
        "BASE64_ARRAY_DECODE_CONCAT",
        "BASE64_DECODE",
        "CANONICAL_BYTES_SATISFY_BOUND",
        "EQ",
        "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX",
        "GE",
        "GT",
        "IMPLIES",
        "INPUT_PATH",
        "INTERNAL_BYTES_LENGTH",
        "IS_NULL",
        "LE",
        "LITERAL",
        "LT",
        "NE",
        "NOT",
        "OBJECT_MEMBER",
        "OR",
        "PRESENT_EQ",
        "PRESENT_LE",
        "RAW_INGRESS_BATCH_ID_RECOMPUTES",
        "RFC6455_CLOSE_PAYLOAD_VALID",
        "SAFE_ADD",
        "SAFE_CEIL_DIVIDE",
        "SAFE_FLOOR_DIVIDE",
        "SAFE_MULTIPLY",
        "SAFE_UINT_TO_INTERNAL_UINT128",
        "SEMANTIC_ID_RECOMPUTES",
        "SHA256_BYTES",
        "TIMESTAMP_TO_EPOCH_MICROSECONDS",
        "UINT128_ADD",
        "UINT128_MULTIPLY",
        "UINT128_PARSE",
    }
)
ALL_OPERATOR_NAMES: Final = GENERIC_OPERATOR_NAMES | COMPLEX_OPERATOR_NAMES

APPLICATION_RUNTIME_SPEC: Final = {
    "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1": ("RECORD_TUPLE", 1, 10),
    "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1": ("RECORD_TUPLE", 1, 8),
    "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1": ("RECORD_TUPLE", 1, 3),
    "APPLY/SELECTOR_MARKER_CONTRACT_V1": ("RECORD_TUPLE", 1, 3),
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1": ("RECORD_TUPLE", 1, 3),
    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1": ("ARRAY_EACH", 185, 10),
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1": (
        "FOR_EACH_FIXED_POSITION_BINDING",
        67,
        19,
    ),
    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1": ("FIXED_SEQUENCE_AGGREGATE", 1, 4),
}
SELECTOR_RESOLVER_ID: Final = (
    "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
)
OBSERVATION_RESOLVER_ID: Final = (
    "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
)

SOURCE_ERROR_DETAIL_DOMAIN: Final = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
SOURCE_ERROR_DETAIL_CANONICAL_OCTET_LIMIT: Final = 2_048

SELECTOR_MARKER_ORDER_BY_OPERATION: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "ACK_DEADLINE_NOT_DUE",
        "ACK_DEADLINE_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "INGRESS": (
        "RAW_PREFIX_COMMITTED",
        "PARSER_UNIT_CONVERGED",
        "INGRESS_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "LOCAL_SHUTDOWN": (
        "LOCAL_CLOSE_DISPATCH_CONVERGED",
        "TLS_CONTROL_CONVERGED",
        "TCP_HALF_CLOSE_CONVERGED",
        "SHUTDOWN_TERMINAL_CONVERGED",
        "TARGET_ESCAPE_OBSERVED",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "OUTBOUND_ARTIFACTS_PREPARED",
        "KERNEL_SEND_RESULT_CONVERGED",
        "DISPATCH_RETURN_READY",
        "TARGET_ESCAPE_OBSERVED",
    ),
}

PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON: Final = {
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
    "SOURCE_CLOCK_UNAVAILABLE": ("CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"),
    "ARTIFACT_BOUND_EXCEEDED": ("CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"),
    "OBSERVER_INTERNAL_ERROR": ("CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"),
}
PLACEHOLDER_FIELD_REASONS: Final = frozenset(
    PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON.values()
)
OFF_STATIC_FIELD_IDS: Final = frozenset(
    {
        "loop.probe_interval_ns",
        "process.filesystem_mount_cgroup_identity_id",
        "process.runtime_environment_id",
    }
)
ATTEMPT_REQUIRED_FIELD_IDS: Final = frozenset(
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
""".split()
)

OPERATION_UNION_MATRIX: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "ACK_DEADLINE_EXPIRY_SPEC_V1",
        "CapacityMeasurementAckDeadlineExpirySpecV1",
        "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
        "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1",
    ),
    "INGRESS": (
        "INGRESS_OPERATION_SPEC_V2",
        "CapacityMeasurementIngressOperationSpecV2",
        "INGRESS_RESULT_EVIDENCE_V2",
        "CapacityMeasurementIngressResultEvidenceV2",
    ),
    "LOCAL_SHUTDOWN": (
        "LOCAL_SHUTDOWN_SPEC_V2",
        "CapacityMeasurementLocalShutdownSpecV2",
        "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
        "CapacityMeasurementLocalShutdownResultEvidenceV2",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "SUBSCRIPTION_DISPATCH_SPEC_V2",
        "CapacityMeasurementSubscriptionDispatchSpecV2",
        "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
        "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
    ),
}


class RuntimeFailure(Exception):
    """Base class for exact, machine-distinguishable runtime failures."""

    failure_class = "RUNTIME_FAILURE"

    def __init__(self, message: str, *, path: tuple[str | int, ...] = ()) -> None:
        super().__init__(message)
        self.path = path


class MalformedValue(RuntimeFailure):
    failure_class = "MALFORMED_VALUE"


class TypeMismatch(RuntimeFailure):
    failure_class = "TYPE_MISMATCH"


class ConstraintViolation(RuntimeFailure):
    failure_class = "CONSTRAINT_VIOLATION"


class UnresolvedReference(RuntimeFailure):
    failure_class = "UNRESOLVED_REFERENCE"


class ImpossibleState(RuntimeFailure):
    failure_class = "IMPOSSIBLE_STATE"


class WorkBoundExceeded(RuntimeFailure):
    failure_class = "WORK_BOUND_EXCEEDED"


class ArtifactFailure(RuntimeFailure):
    failure_class = "ARTIFACT_FAILURE"


class BusinessRuleFalse(RuntimeFailure):
    failure_class = "BUSINESS_RULE_FALSE"


class UnsupportedRule(RuntimeFailure):
    failure_class = "UNSUPPORTED_RULE"


class UnionMismatch:
    """Structured marker while retaining legacy runtime-failure base classes."""


class UnionMalformedValue(MalformedValue, UnionMismatch):
    pass


class UnionTypeMismatch(TypeMismatch, UnionMismatch):
    pass


class UnionConstraintViolation(ConstraintViolation, UnionMismatch):
    pass


class UnionUnresolvedReference(UnresolvedReference, UnionMismatch):
    pass


class UnionImpossibleState(ImpossibleState, UnionMismatch):
    pass


class CandidateImpossibleState(ImpossibleState):
    """An explicitly candidate-reachable impossible branch."""


@dataclass(frozen=True, slots=True)
class TypedValue:
    """A value paired with its declared registry schema and/or record type."""

    value: Any
    value_schema_id: str | None = None
    type_name: str | None = None

    def __post_init__(self) -> None:
        if (self.value_schema_id is None) == (self.type_name is None):
            raise ValueError("TypedValue requires exactly one declared schema or type")
        identifier = (
            self.value_schema_id if self.value_schema_id is not None else self.type_name
        )
        if type(identifier) is not str or not identifier:
            raise ValueError("TypedValue declaration must be nonempty exact text")


@dataclass(frozen=True, slots=True)
class ApplicationRecordInput:
    """One explicitly named, declared root record for an application."""

    binding_name: str
    declared: TypedValue


@dataclass(frozen=True, slots=True)
class ApplicationSequenceInput:
    """One explicitly named caller-supplied complete-record sequence."""

    binding_name: str
    ordered_records: tuple[TypedValue, ...]


@dataclass(frozen=True, slots=True)
class ApplicationFailureCoordinate:
    application_name: str
    rule_application_id: str
    rule_id: str
    iteration_ordinal: int | None
    failure_class: str | None


@dataclass(frozen=True, slots=True)
class ApplicationRuleStepEvidence:
    iteration_ordinal: int | None
    root_value: bool
    direct_expression_nodes: int
    total_expression_nodes: int
    complex_operator_invocations: int
    complex_row_item_visits: int
    complex_canonicalized_octets: int


@dataclass(frozen=True, slots=True)
class ApplicationEvaluationEvidence:
    """Deterministic evidence for one complete frozen application execution."""

    application_name: str
    rule_application_id: str
    rule_id: str
    accepted: bool
    result_coordinate: ApplicationFailureCoordinate
    maximum_rule_evaluations: int
    charged_rule_evaluations: int
    completed_rule_evaluations: int
    intrinsic_rule_logical_invocations: int
    intrinsic_rule_physical_executions: int
    intrinsic_rule_cache_hits: int
    resolver_invocations: int
    resolver_source_identity_count: int
    resolver_identity_logical_recomputations: int
    resolver_identity_physical_recomputations: int
    resolver_identity_cache_hits: int
    resolver_logical_comparisons: int
    logical_record_graph_validations: int
    physical_record_graph_validations: int
    record_graph_validation_cache_hits: int
    validation_work_used: int
    snapshot_canonicalized_octets: int
    total_expression_nodes: int
    complex_operator_invocations: int
    complex_row_item_visits: int
    complex_canonicalized_octets: int
    ordered_rule_step_evidence: tuple[ApplicationRuleStepEvidence, ...]


@dataclass(slots=True)
class _Budget:
    initial: int
    remaining: int

    def charge(self, *, path: tuple[str | int, ...]) -> None:
        if type(self.remaining) is not int or self.remaining <= 0:
            raise WorkBoundExceeded("value-validation work bound exceeded", path=path)
        self.remaining -= 1

    @property
    def used(self) -> int:
        return self.initial - self.remaining


@dataclass(frozen=True, slots=True)
class ValidationEvidence:
    declared: TypedValue
    validation_work_limit: int
    validation_work_used: int


@dataclass(frozen=True, slots=True)
class RuleEvaluationEvidence:
    """Exact generic-rule execution evidence, including composite literals."""

    rule_id: str
    root_value: bool
    direct_expression_nodes: int
    intrinsic_rule_invocations: int
    total_expression_nodes: int
    complex_operator_invocations: int
    complex_row_item_visits: int
    complex_canonicalized_octets: int


@dataclass(frozen=True, slots=True)
class _ExpressionValue:
    value: Any
    result_type_kind: str
    value_schema_id: str | None


@dataclass(slots=True)
class _RuleCounters:
    intrinsic_rule_invocations: int = 0
    total_expression_nodes: int = 0
    complex_operator_invocations: int = 0
    complex_row_item_visits: int = 0
    complex_canonicalized_octets: int = 0


@dataclass(slots=True)
class _ApplicationCounters:
    charged_rule_evaluations: int = 0
    completed_rule_evaluations: int = 0
    intrinsic_rule_logical_invocations: int = 0
    intrinsic_rule_physical_executions: int = 0
    intrinsic_rule_cache_hits: int = 0
    resolver_invocations: int = 0
    resolver_source_identity_count: int = 0
    resolver_identity_logical_recomputations: int = 0
    resolver_identity_physical_recomputations: int = 0
    resolver_identity_cache_hits: int = 0
    resolver_logical_comparisons: int = 0
    logical_record_graph_validations: int = 0
    physical_record_graph_validations: int = 0
    record_graph_validation_cache_hits: int = 0
    validation_work_used: int = 0
    snapshot_canonicalized_octets: int = 0


@dataclass(frozen=True, slots=True)
class _CompiledResolverPlan:
    resolver_id: str
    profile_name: str
    source_root_type_name: str
    resolved_item_type_name: str
    minimum_items: int
    maximum_items: int
    item_identity_field: str
    source_paths: tuple[tuple[str, str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class _CompiledRootBinding:
    binding_name: str
    expected_type_name: str


@dataclass(frozen=True, slots=True)
class _CompiledSequenceBinding:
    binding_name: str
    source_kind: str
    binding_mode: str
    source_root_binding_name: str
    expected_item_type_name: str
    embedded_array_typed_member_path: tuple[str, ...]
    resolver_id: str | None


@dataclass(frozen=True, slots=True)
class _CompiledApplicationPlan:
    application_name: str
    rule_application_id: str
    rule_id: str
    application_kind: str
    maximum_rule_evaluations: int
    iteration_ordinal_binding_name: str | None
    requires_equal_cardinality: bool
    root_bindings: tuple[_CompiledRootBinding, ...]
    sequence_bindings: tuple[_CompiledSequenceBinding, ...]
    external_sequence_bindings: tuple[_CompiledSequenceBinding, ...]
    effective_binding_ledger: tuple[tuple[str, str, str | None, str], ...]


@dataclass(slots=True)
class _ApplicationExecutionContext:
    counters: _ApplicationCounters
    rule_counters: _RuleCounters
    intrinsic_accept_cache: set[tuple[str, str, bytes]]
    ordered_rule_steps: list[ApplicationRuleStepEvidence]


class _ApplicationCandidateFailure(Exception):
    """Internal carrier for a candidate failure and its exact failing rule."""

    def __init__(self, failure: RuntimeFailure, *, rule_id: str) -> None:
        super().__init__(str(failure))
        self.failure = failure
        self.rule_id = rule_id


@dataclass(frozen=True, slots=True)
class _TargetRegistryIndexes:
    descriptors: dict[str, dict[str, Any]]
    constraints: dict[str, dict[str, Any]]
    shapes: dict[str, dict[str, Any]]
    vocabularies: dict[str, dict[str, Any]]
    reasons: dict[str, dict[str, Any]]
    cross_field_constraints: dict[str, dict[str, Any]]
    recomputed_registry_id: str


def _fail(
    failure: type[RuntimeFailure],
    message: str,
    *,
    path: tuple[str | int, ...],
) -> NoReturn:
    raise failure(message, path=path)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise MalformedValue("value is not canonical-I-JSON encodable") from exc


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
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ArtifactFailure("artifact is not canonical-I-JSON encodable") from exc


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


def _reject_json_constant(value: str) -> NoReturn:
    raise ArtifactFailure(f"non-finite JSON constant is forbidden: {value}")


def _reject_json_float(value: str) -> NoReturn:
    raise ArtifactFailure(f"JSON floating-point number is forbidden: {value}")


def _parse_json_integer(value: str) -> int:
    if len(value) > 17:
        raise ArtifactFailure("JSON integer exceeds the predecode digit bound")
    parsed = int(value)
    if not -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM:
        raise ArtifactFailure("JSON integer is outside the safe-I-JSON domain")
    return parsed


def _parse_uint128_decimal(
    value: str,
    *,
    path: tuple[str | int, ...],
) -> int:
    if (
        len(value) > len(UINT128_MAXIMUM_TEXT)
        or re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None
        or (len(value) == len(UINT128_MAXIMUM_TEXT) and value > UINT128_MAXIMUM_TEXT)
    ):
        _fail(
            ConstraintViolation,
            "uint128 decimal text is not canonical or is out of range",
            path=path,
        )
    return int(value)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactFailure(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _scan_json_structure(text: str) -> int:
    """Bound raw nesting before decode without interpreting JSON values."""

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
            elif ord(character) < 0x20:
                raise ArtifactFailure("raw JSON string contains an unescaped control")
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            stack.append(character)
            maximum = max(maximum, len(stack))
            if maximum > MAXIMUM_JSON_DEPTH:
                raise ArtifactFailure("raw JSON nesting exceeds structural bound")
        elif character in "]}":
            if not stack or stack[-1] != closing[character]:
                raise ArtifactFailure("raw JSON delimiters are unbalanced")
            stack.pop()
    if in_string or escaped:
        raise ArtifactFailure("raw JSON string is unterminated")
    if stack:
        raise ArtifactFailure("raw JSON delimiters are unterminated")
    return maximum


def _validate_json_scalars(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            for key, item in current.items():
                if type(key) is not str or any(
                    0xD800 <= ord(character) <= 0xDFFF for character in key
                ):
                    raise ArtifactFailure("JSON object key is outside scalar domain")
                stack.append(item)
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise ArtifactFailure("JSON string contains a lone surrogate")
        elif not (
            current is None
            or type(current) is bool
            or (
                type(current) is int
                and -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM
            )
        ):
            raise ArtifactFailure("JSON scalar is outside controlled I-JSON domain")


def _decode_document(path: Path, raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _scan_json_structure(text)
        decoded = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_int=_parse_json_integer,
            parse_float=_reject_json_float,
            parse_constant=_reject_json_constant,
        )
    except (
        ArtifactFailure,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as exc:
        if isinstance(exc, ArtifactFailure):
            raise
        raise ArtifactFailure(f"artifact JSON is malformed: {path}") from exc
    if type(decoded) is not dict:
        raise ArtifactFailure(f"artifact root is not an object: {path}")
    _validate_json_scalars(decoded)
    if _pretty_bytes(decoded) != raw:
        raise ArtifactFailure(f"artifact is not canonical pretty JSON: {path}")
    return decoded


def _read_pinned_json(
    path: Path,
    *,
    expected_sha256: str,
    expected_octets: int,
) -> dict[str, Any]:
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ArtifactFailure(f"cannot securely open artifact: {path}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ArtifactFailure(f"artifact is not a regular file: {path}")
        if before.st_size != expected_octets:
            raise ArtifactFailure(f"artifact byte count differs: {path}")
        if before.st_size >= MAXIMUM_ARTIFACT_OCTETS:
            raise ArtifactFailure(f"artifact reaches exclusive byte limit: {path}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                raise ArtifactFailure(f"artifact was truncated during read: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ArtifactFailure(f"artifact grew during read: {path}")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ArtifactFailure(f"artifact changed during read: {path}")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if _sha256(raw) != expected_sha256:
        raise ArtifactFailure(f"artifact SHA-256 differs: {path}")
    return _decode_document(path, raw)


def _index_exact(
    records: list[dict[str, Any]],
    key: str,
    *,
    expected_count: int,
) -> dict[str, dict[str, Any]]:
    if type(records) is not list or len(records) != expected_count:
        raise ArtifactFailure(f"{key} catalog count differs")
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        if type(record) is not dict or type(record.get(key)) is not str:
            raise ArtifactFailure(f"{key} catalog entry is malformed")
        identifier = record[key]
        if identifier in result:
            raise ArtifactFailure(f"duplicate {key}: {identifier}")
        result[identifier] = record
    return result


class ExternalSchemaV2Runtime:
    """Schema-directed validator over the exact accepted structural registry."""

    def __init__(
        self,
        registry: dict[str, Any],
        literal_authority: dict[str, Any],
        *,
        _capability: object,
    ) -> None:
        if _capability is not _LOAD_CAPABILITY:
            raise ArtifactFailure("runtime construction requires the pinned loader")
        _validate_json_scalars(registry)
        _validate_json_scalars(literal_authority)
        registry_raw = _pretty_bytes(registry)
        literal_raw = _pretty_bytes(literal_authority)
        if (
            len(registry_raw) != STRUCTURAL_REGISTRY_OCTETS
            or _sha256(registry_raw) != STRUCTURAL_REGISTRY_SHA256
            or len(literal_raw) != RULE_LITERAL_AUTHORITY_OCTETS
            or _sha256(literal_raw) != RULE_LITERAL_AUTHORITY_SHA256
        ):
            raise ArtifactFailure("in-memory authority bytes differ from frozen pins")
        registry = copy.deepcopy(registry)
        literal_authority = copy.deepcopy(literal_authority)
        self.registry = registry
        self.literal_authority = literal_authority
        self.schemas = _index_exact(
            registry.get("value_schema_catalog"),
            "value_schema_id",
            expected_count=236,
        )
        self.languages = _index_exact(
            registry.get("text_language_catalog"),
            "text_language_id",
            expected_count=103,
        )
        self.dfas = _index_exact(
            registry.get("ascii_dfa_catalog"),
            "ascii_dfa_id",
            expected_count=9,
        )
        self.profiles = _index_exact(
            registry.get("identifier_profile_catalog"),
            "unicode_identifier_profile_id",
            expected_count=3,
        )
        self.types = _index_exact(
            registry.get("ordered_external_type_descriptors"),
            "type_name",
            expected_count=52,
        )
        self.rules = _index_exact(
            registry.get("ordered_cross_field_rule_descriptors"),
            "rule_id",
            expected_count=42,
        )
        self.applications = _index_exact(
            registry.get("ordered_rule_application_descriptors"),
            "application_name",
            expected_count=8,
        )
        self.resolvers = _index_exact(
            registry.get("fixed_position_resolver_profile_catalog"),
            "fixed_position_resolver_profile_id",
            expected_count=2,
        )
        self.records = {
            name: descriptor
            for name, descriptor in self.types.items()
            if descriptor.get("type_form") == "RECORD"
        }
        self.unions = {
            name: descriptor
            for name, descriptor in self.types.items()
            if descriptor.get("type_form") == "TAGGED_UNION"
        }
        if len(self.records) != 49 or len(self.unions) != 3:
            raise ArtifactFailure("record/tagged-union partition differs")
        observed_operators = {
            node["operator"]
            for rule in self.rules.values()
            for node in rule["ordered_expression_nodes"]
        }
        if observed_operators - ALL_OPERATOR_NAMES:
            raise ArtifactFailure("rule catalog contains an unknown operator")
        self.generic_rule_ids = frozenset(
            rule_id
            for rule_id, rule in self.rules.items()
            if not any(
                node["operator"] in COMPLEX_OPERATOR_NAMES
                for node in rule["ordered_expression_nodes"]
            )
        )
        self.complex_rule_ids = frozenset(self.rules) - self.generic_rule_ids
        if (
            len(self.generic_rule_ids) != 33
            or sum(
                len(self.rules[rule_id]["ordered_expression_nodes"])
                for rule_id in self.generic_rule_ids
            )
            != 1_017
            or len(self.complex_rule_ids) != 9
            or sum(
                len(self.rules[rule_id]["ordered_expression_nodes"])
                for rule_id in self.complex_rule_ids
            )
            != 40
        ):
            raise ArtifactFailure("generic/complex rule partition differs")
        if registry.get("external_schema_registry_id") != (
            "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
        ):
            raise ArtifactFailure("structural registry semantic identity differs")
        if literal_authority.get("rule_literal_authority_sha256") != (
            "5239e6ec09244d772c72c7883393da5707984408f7a7e21e1731948a82ea647e"
        ):
            raise ArtifactFailure("rule-literal authority semantic identity differs")
        (
            self.compiled_resolvers,
            self.compiled_applications,
        ) = self._compile_application_runtime_plans()
        (
            self.derived_maximum_validation_work,
            self.maximum_work_schema_id,
            self.maximum_work_type_name,
        ) = self._derive_maximum_validation_work()
        if self.derived_maximum_validation_work != MAXIMUM_VALIDATION_WORK:
            raise ArtifactFailure("derived value-validation work maximum differs")

    @classmethod
    def load(cls, repository_root: Path | None = None) -> ExternalSchemaV2Runtime:
        root = (
            Path(__file__).resolve().parents[2]
            if repository_root is None
            else Path(repository_root)
        )
        registry = _read_pinned_json(
            root / STRUCTURAL_REGISTRY_RELATIVE_PATH,
            expected_sha256=STRUCTURAL_REGISTRY_SHA256,
            expected_octets=STRUCTURAL_REGISTRY_OCTETS,
        )
        literals = _read_pinned_json(
            root / RULE_LITERAL_AUTHORITY_RELATIVE_PATH,
            expected_sha256=RULE_LITERAL_AUTHORITY_SHA256,
            expected_octets=RULE_LITERAL_AUTHORITY_OCTETS,
        )
        return cls(registry, literals, _capability=_LOAD_CAPABILITY)

    def _schema_id_at_record_path(
        self,
        type_name: str,
        typed_member_path: list[str],
    ) -> str:
        current_type = type_name
        schema_id: str | None = None
        for position, member_name in enumerate(typed_member_path):
            descriptor = self.records.get(current_type)
            if descriptor is None:
                raise ArtifactFailure("application path crosses a non-record type")
            matches = [
                member
                for member in descriptor["record_member_descriptors"]
                if member["member_name"] == member_name
            ]
            if len(matches) != 1:
                raise ArtifactFailure("application typed-member path is unresolved")
            schema_id = matches[0]["value_schema_id"]
            if position != len(typed_member_path) - 1:
                schema = self.schemas[schema_id]
                if (
                    schema["schema_kind"] != "OBJECT_REF"
                    or schema["nullable"] is not False
                    or schema["referenced_type_name"] not in self.records
                ):
                    raise ArtifactFailure(
                        "application path crosses a non-record schema"
                    )
                current_type = schema["referenced_type_name"]
        if schema_id is None:
            raise ArtifactFailure("application typed-member path is empty")
        return schema_id

    def _schema_id_at_value_path(
        self,
        schema_id: str,
        typed_member_path: list[str],
    ) -> str:
        current_schema_id = schema_id
        for member_name in typed_member_path:
            schema = self.schemas[current_schema_id]
            if schema["schema_kind"] != "OBJECT_REF":
                raise ArtifactFailure(
                    "application expression path crosses a non-object schema"
                )
            descriptor = self.records.get(schema["referenced_type_name"])
            if descriptor is None:
                raise ArtifactFailure(
                    "application expression path crosses a non-record type"
                )
            matches = [
                member
                for member in descriptor["record_member_descriptors"]
                if member["member_name"] == member_name
            ]
            if len(matches) != 1:
                raise ArtifactFailure("application expression typed path is unresolved")
            current_schema_id = matches[0]["value_schema_id"]
        return current_schema_id

    def _exact_schema_id(
        self,
        *,
        schema_kind: str,
        nullable: bool,
        boolean_literal: bool | None = None,
        integer_minimum: int | None = None,
        integer_maximum: int | None = None,
        text_language_id: str | None = None,
        array_minimum_items: int | None = None,
        array_maximum_items: int | None = None,
        array_item_value_schema_id: str | None = None,
        referenced_type_name: str | None = None,
    ) -> str:
        payload = {
            "array_item_value_schema_id": array_item_value_schema_id,
            "array_maximum_items": array_maximum_items,
            "array_minimum_items": array_minimum_items,
            "boolean_literal": boolean_literal,
            "integer_maximum": integer_maximum,
            "integer_minimum": integer_minimum,
            "nullable": nullable,
            "referenced_type_name": referenced_type_name,
            "schema_kind": schema_kind,
            "text_language_id": text_language_id,
        }
        matches = [
            schema_id
            for schema_id, schema in self.schemas.items()
            if {key: value for key, value in schema.items() if key != "value_schema_id"}
            == payload
        ]
        if len(matches) != 1:
            raise ArtifactFailure("derived application schema is not uniquely frozen")
        return matches[0]

    def _compile_application_runtime_plans(
        self,
    ) -> tuple[
        dict[str, _CompiledResolverPlan],
        dict[str, _CompiledApplicationPlan],
    ]:
        """Compile and cross-check immutable application ledgers at load time."""

        if tuple(self.applications) != tuple(sorted(APPLICATION_RUNTIME_SPEC)):
            raise ArtifactFailure("application lexical catalog order differs")
        if tuple(self.resolvers) != (SELECTOR_RESOLVER_ID, OBSERVATION_RESOLVER_ID):
            raise ArtifactFailure("fixed-position resolver catalog order differs")

        expected_resolvers: dict[
            str,
            tuple[str, str, str, int, int, str, str, list[str]],
        ] = {
            SELECTOR_RESOLVER_ID: (
                "RAW_V8_V2_ROOT_SELECTOR_RESOLVER_V1",
                "TargetObservationRootV2",
                "CheckpointSelectorV1",
                0,
                1,
                "OPTIONAL_SCALAR",
                "NULL_TO_EMPTY_SEQUENCE",
                ["full_checkpoint_selector_id"],
            ),
            OBSERVATION_RESOLVER_ID: (
                "RAW_V8_V2_ROOT_OBSERVATION_RESOLVER_V1",
                "TargetObservationRootV2",
                "TargetObservationV2",
                1,
                67,
                "ARRAY",
                "REJECT_NULL",
                ["ordered_observation_ids"],
            ),
        }
        compiled_resolvers: dict[str, _CompiledResolverPlan] = {}
        for resolver_id, resolver in self.resolvers.items():
            (
                profile_name,
                root_type,
                item_type,
                minimum,
                maximum,
                result_kind,
                null_semantics,
                source_path,
            ) = expected_resolvers[resolver_id]
            paths = resolver["ordered_source_identity_path_descriptors"]
            if (
                resolver["profile_name"] != profile_name
                or resolver["source_root_type_name"] != root_type
                or resolver["resolved_item_type_name"] != item_type
                or resolver["minimum_items"] != minimum
                or resolver["maximum_items"] != maximum
                or resolver["resolution_semantics"]
                != "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER"
                or len(paths) != 1
                or paths[0]["path_position"] != 1
                or paths[0]["result_kind"] != result_kind
                or paths[0]["null_semantics"] != null_semantics
                or paths[0]["typed_member_path"] != source_path
            ):
                raise ArtifactFailure("fixed-position resolver plan differs")
            item_descriptor = self.records.get(item_type)
            if (
                item_descriptor is None
                or item_descriptor["type_role"] != "STANDALONE"
                or type(item_descriptor["identity_field"]) is not str
            ):
                raise ArtifactFailure("resolver item identity contract differs")
            identity_schema_id = self._schema_id_at_record_path(
                item_type,
                [item_descriptor["identity_field"]],
            )
            identity_schema = self.schemas[identity_schema_id]
            source_schema_id = self._schema_id_at_record_path(root_type, source_path)
            source_schema = self.schemas[source_schema_id]
            if result_kind == "ARRAY":
                source_contract_ok = (
                    source_schema["schema_kind"] == "ARRAY"
                    and source_schema["nullable"] is False
                    and source_schema["array_minimum_items"] == minimum
                    and source_schema["array_maximum_items"] == maximum
                    and source_schema["array_item_value_schema_id"]
                    == identity_schema_id
                )
            else:
                source_contract_ok = (
                    result_kind == "OPTIONAL_SCALAR"
                    and minimum == 0
                    and maximum == 1
                    and source_schema["nullable"] is True
                    and {
                        key: value
                        for key, value in source_schema.items()
                        if key not in {"value_schema_id", "nullable"}
                    }
                    == {
                        key: value
                        for key, value in identity_schema.items()
                        if key not in {"value_schema_id", "nullable"}
                    }
                )
            if not source_contract_ok:
                raise ArtifactFailure("resolver source identity schema differs")
            compiled_resolvers[resolver_id] = _CompiledResolverPlan(
                resolver_id=resolver_id,
                profile_name=profile_name,
                source_root_type_name=root_type,
                resolved_item_type_name=item_type,
                minimum_items=minimum,
                maximum_items=maximum,
                item_identity_field=item_descriptor["identity_field"],
                source_paths=((result_kind, null_semantics, tuple(source_path)),),
            )

        compiled_applications: dict[str, _CompiledApplicationPlan] = {}
        observed_rule_ids: set[str] = set()
        for application_name, application in self.applications.items():
            expected_kind, expected_maximum, expected_nodes = APPLICATION_RUNTIME_SPEC[
                application_name
            ]
            rule_id = application["rule_id"]
            rule = self.rules.get(rule_id)
            if (
                rule is None
                or rule["rule_scope"] != "CROSS_RECORD"
                or application["application_kind"] != expected_kind
                or application["maximum_rule_evaluations"] != expected_maximum
                or len(rule["ordered_expression_nodes"]) != expected_nodes
                or rule_id in observed_rule_ids
            ):
                raise ArtifactFailure("application rule plan differs")
            observed_rule_ids.add(rule_id)

            roots = application["ordered_root_input_bindings"]
            root_names: set[str] = set()
            compiled_roots: list[_CompiledRootBinding] = []
            derived_effective: list[tuple[str, str, str | None, str]] = []
            for position, root in enumerate(roots, start=1):
                if (
                    root["tuple_position"] != position
                    or root["binding_name"] in root_names
                    or root["expected_type_name"] not in self.records
                ):
                    raise ArtifactFailure("application root ledger differs")
                root_names.add(root["binding_name"])
                compiled_roots.append(
                    _CompiledRootBinding(
                        binding_name=root["binding_name"],
                        expected_type_name=root["expected_type_name"],
                    )
                )
                derived_effective.append(
                    (
                        root["binding_name"],
                        "RECORD",
                        root["expected_type_name"],
                        self._exact_schema_id(
                            schema_kind="OBJECT_REF",
                            nullable=False,
                            referenced_type_name=root["expected_type_name"],
                        ),
                    )
                )
            root_by_name = {root["binding_name"]: root for root in roots}

            sequences = application["ordered_sequence_input_bindings"]
            compiled_sequences: list[_CompiledSequenceBinding] = []
            external_sequences: list[_CompiledSequenceBinding] = []
            sequence_names: set[str] = set()
            sequence_maxima: list[int] = []
            for sequence in sequences:
                name = sequence["binding_name"]
                source_root_name = sequence["source_root_binding_name"]
                if (
                    name in root_names
                    or name in sequence_names
                    or source_root_name not in root_by_name
                    or sequence["expected_item_type_name"] not in self.records
                ):
                    raise ArtifactFailure("application sequence ledger differs")
                sequence_names.add(name)
                compiled_sequence = _CompiledSequenceBinding(
                    binding_name=name,
                    source_kind=sequence["source_kind"],
                    binding_mode=sequence["binding_mode"],
                    source_root_binding_name=source_root_name,
                    expected_item_type_name=sequence["expected_item_type_name"],
                    embedded_array_typed_member_path=tuple(
                        sequence["embedded_array_typed_member_path"]
                    ),
                    resolver_id=sequence["fixed_position_resolver_profile_id"],
                )
                compiled_sequences.append(compiled_sequence)
                if sequence["source_kind"] == "EMBEDDED_ARRAY":
                    if (
                        sequence["binding_mode"] != "ITERATED_RECORD"
                        or not sequence["embedded_array_typed_member_path"]
                        or sequence["fixed_position_resolver_profile_id"] is not None
                    ):
                        raise ArtifactFailure("embedded application sequence differs")
                    source_schema_id = self._schema_id_at_record_path(
                        root_by_name[source_root_name]["expected_type_name"],
                        sequence["embedded_array_typed_member_path"],
                    )
                    source_schema = self.schemas[source_schema_id]
                    item_schema = self.schemas.get(
                        source_schema.get("array_item_value_schema_id")
                    )
                    if (
                        source_schema["schema_kind"] != "ARRAY"
                        or source_schema["nullable"] is not False
                        or item_schema is None
                        or item_schema["schema_kind"] != "OBJECT_REF"
                        or item_schema["nullable"] is not False
                        or item_schema["referenced_type_name"]
                        != sequence["expected_item_type_name"]
                    ):
                        raise ArtifactFailure("embedded sequence schema differs")
                    sequence_maxima.append(source_schema["array_maximum_items"])
                    derived_effective.append(
                        (
                            name,
                            "RECORD",
                            sequence["expected_item_type_name"],
                            source_schema["array_item_value_schema_id"],
                        )
                    )
                elif sequence["source_kind"] == "EXTERNAL_FIXED_SEQUENCE":
                    resolver_id = sequence["fixed_position_resolver_profile_id"]
                    resolver_plan = compiled_resolvers.get(resolver_id)
                    if (
                        sequence["embedded_array_typed_member_path"] != []
                        or resolver_plan is None
                        or resolver_plan.source_root_type_name
                        != root_by_name[source_root_name]["expected_type_name"]
                        or resolver_plan.resolved_item_type_name
                        != sequence["expected_item_type_name"]
                    ):
                        raise ArtifactFailure("external sequence resolver differs")
                    external_sequences.append(compiled_sequence)
                    item_schema_id = self._exact_schema_id(
                        schema_kind="OBJECT_REF",
                        nullable=False,
                        referenced_type_name=sequence["expected_item_type_name"],
                    )
                    mode = sequence["binding_mode"]
                    if mode == "ITERATED_RECORD":
                        sequence_maxima.append(resolver_plan.maximum_items)
                        derived_effective.append(
                            (
                                name,
                                "RECORD",
                                sequence["expected_item_type_name"],
                                item_schema_id,
                            )
                        )
                    elif mode == "COMPLETE_RECORD_SEQUENCE":
                        derived_effective.append(
                            (
                                name,
                                "FIXED_RECORD_SEQUENCE",
                                sequence["expected_item_type_name"],
                                self._exact_schema_id(
                                    schema_kind="ARRAY",
                                    nullable=False,
                                    array_minimum_items=resolver_plan.minimum_items,
                                    array_maximum_items=resolver_plan.maximum_items,
                                    array_item_value_schema_id=item_schema_id,
                                ),
                            )
                        )
                    elif mode == "OPTIONAL_RECORD":
                        if (
                            resolver_plan.minimum_items != 0
                            or resolver_plan.maximum_items != 1
                        ):
                            raise ArtifactFailure(
                                "optional resolver cardinality differs"
                            )
                        derived_effective.append(
                            (
                                name,
                                "OPTIONAL_FIXED_RECORD",
                                sequence["expected_item_type_name"],
                                self._exact_schema_id(
                                    schema_kind="OBJECT_REF",
                                    nullable=True,
                                    referenced_type_name=sequence[
                                        "expected_item_type_name"
                                    ],
                                ),
                            )
                        )
                    else:
                        raise ArtifactFailure("external sequence mode differs")
                else:
                    raise ArtifactFailure("unknown application sequence source")

            ordinal_name = application["iteration_ordinal_binding_name"]
            if ordinal_name is not None:
                derived_effective.append(
                    (
                        ordinal_name,
                        "SAFE_UINT",
                        None,
                        self._exact_schema_id(
                            schema_kind="SAFE_INTEGER",
                            nullable=False,
                            integer_minimum=0,
                            integer_maximum=expected_maximum - 1,
                        ),
                    )
                )
            frozen_effective = tuple(
                (
                    item["binding_name"],
                    item["binding_kind"],
                    item["expected_type_name"],
                    item["expected_value_schema_id"],
                )
                for item in rule["ordered_rule_input_bindings"]
            )
            if tuple(derived_effective) != frozen_effective:
                raise ArtifactFailure("application effective binding ledger differs")
            for binding in rule["ordered_rule_input_bindings"]:
                self._assert_binding_type_contract(binding)
            effective_schema_by_name = {
                binding_name: schema_id
                for binding_name, _kind, _type_name, schema_id in derived_effective
            }
            for node in rule["ordered_expression_nodes"]:
                if node["operator"] != "INPUT_PATH":
                    continue
                binding_name = node["input_binding_name"]
                if binding_name not in effective_schema_by_name:
                    raise ArtifactFailure(
                        "application input-path binding is unresolved"
                    )
                derived_result_schema_id = self._schema_id_at_value_path(
                    effective_schema_by_name[binding_name],
                    node["typed_member_path"],
                )
                if (
                    node["result_type_kind"] != "VALUE_SCHEMA"
                    or node["result_value_schema_id"] != derived_result_schema_id
                ):
                    raise ArtifactFailure(
                        "application input-path result schema differs"
                    )

            kind = application["application_kind"]
            if kind == "RECORD_TUPLE":
                shape_ok = (
                    len(roots) >= 2
                    and not sequences
                    and ordinal_name is None
                    and application["requires_equal_cardinality"] is False
                    and application["evaluation_order"] == "SINGLE_EVALUATION"
                )
            elif kind in {"ARRAY_EACH", "FOR_EACH_FIXED_POSITION_BINDING"}:
                external_count = sum(
                    sequence.source_kind == "EXTERNAL_FIXED_SEQUENCE"
                    for sequence in compiled_sequences
                )
                shape_ok = (
                    bool(sequences)
                    and all(
                        sequence["binding_mode"] == "ITERATED_RECORD"
                        for sequence in sequences
                    )
                    and type(ordinal_name) is str
                    and bool(ordinal_name)
                    and application["requires_equal_cardinality"]
                    is (len(sequences) > 1)
                    and application["evaluation_order"]
                    == "LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL"
                    and bool(sequence_maxima)
                    and expected_maximum == min(sequence_maxima)
                    and (
                        (kind == "ARRAY_EACH" and external_count == 0)
                        or (
                            kind == "FOR_EACH_FIXED_POSITION_BINDING"
                            and external_count >= 1
                        )
                    )
                )
            elif kind == "FIXED_SEQUENCE_AGGREGATE":
                shape_ok = (
                    bool(sequences)
                    and all(
                        sequence["source_kind"] == "EXTERNAL_FIXED_SEQUENCE"
                        and sequence["binding_mode"]
                        in {"COMPLETE_RECORD_SEQUENCE", "OPTIONAL_RECORD"}
                        for sequence in sequences
                    )
                    and ordinal_name is None
                    and application["requires_equal_cardinality"] is False
                    and application["evaluation_order"] == "SINGLE_EVALUATION"
                )
            else:
                shape_ok = False
            if not shape_ok:
                raise ArtifactFailure("application execution shape differs")
            compiled_applications[application_name] = _CompiledApplicationPlan(
                application_name=application_name,
                rule_application_id=application["rule_application_id"],
                rule_id=rule_id,
                application_kind=kind,
                maximum_rule_evaluations=expected_maximum,
                iteration_ordinal_binding_name=ordinal_name,
                requires_equal_cardinality=application["requires_equal_cardinality"],
                root_bindings=tuple(compiled_roots),
                sequence_bindings=tuple(compiled_sequences),
                external_sequence_bindings=tuple(external_sequences),
                effective_binding_ledger=tuple(derived_effective),
            )
        if len(observed_rule_ids) != 8:
            raise ArtifactFailure("application cross-rule coverage differs")
        return compiled_resolvers, compiled_applications

    def _derive_maximum_validation_work(self) -> tuple[int, str, str]:
        """Derive a conservative schema-node visit ceiling from frozen maxima."""

        schema_costs: dict[str, int] = {}
        type_costs: dict[str, int] = {}
        active: set[tuple[str, str]] = set()

        def schema_cost(schema_id: str) -> int:
            if schema_id in schema_costs:
                return schema_costs[schema_id]
            key = ("schema", schema_id)
            if key in active:
                raise ArtifactFailure("value-schema work graph is cyclic")
            active.add(key)
            schema = self.schemas[schema_id]
            kind = schema["schema_kind"]
            if kind in {"EXACT_BOOLEAN", "SAFE_INTEGER"}:
                result = 1
            elif kind == "TEXT":
                result = 2
            elif kind == "ARRAY":
                result = 1 + schema["array_maximum_items"] * schema_cost(
                    schema["array_item_value_schema_id"]
                )
            elif kind == "OBJECT_REF":
                result = 1 + type_cost(schema["referenced_type_name"])
            else:
                raise ArtifactFailure(f"unknown schema kind in work graph: {kind}")
            active.remove(key)
            schema_costs[schema_id] = result
            return result

        def type_cost(type_name: str) -> int:
            if type_name in type_costs:
                return type_costs[type_name]
            key = ("type", type_name)
            if key in active:
                raise ArtifactFailure("external-type work graph is cyclic")
            active.add(key)
            descriptor = self.types[type_name]
            if descriptor["type_form"] == "RECORD":
                result = 1 + sum(
                    schema_cost(member["value_schema_id"])
                    for member in descriptor["record_member_descriptors"]
                )
            elif descriptor["type_form"] == "TAGGED_UNION":
                topology = descriptor["tagged_union_descriptor"]
                result = (
                    1
                    + len(topology["ordered_discriminator_descriptors"])
                    + max(
                        type_cost(alternative["referenced_type_name"])
                        for alternative in topology["ordered_alternatives"]
                    )
                )
            else:
                raise ArtifactFailure("unknown external type form in work graph")
            active.remove(key)
            type_costs[type_name] = result
            return result

        for schema_id in self.schemas:
            schema_cost(schema_id)
        for type_name in self.types:
            type_cost(type_name)
        maximum_schema_id = max(schema_costs, key=schema_costs.__getitem__)
        maximum_type_name = max(type_costs, key=type_costs.__getitem__)
        maximum = max(
            schema_costs[maximum_schema_id],
            type_costs[maximum_type_name],
        )
        self._schema_validation_work = schema_costs
        self._type_validation_work = type_costs
        return maximum, maximum_schema_id, maximum_type_name

    def _assert_authority_intact(self) -> None:
        current_schema_work = dict(self._schema_validation_work)
        current_type_work = dict(self._type_validation_work)
        registry_raw = _pretty_bytes(self.registry)
        literal_raw = _pretty_bytes(self.literal_authority)
        if (
            len(registry_raw) != STRUCTURAL_REGISTRY_OCTETS
            or _sha256(registry_raw) != STRUCTURAL_REGISTRY_SHA256
            or len(literal_raw) != RULE_LITERAL_AUTHORITY_OCTETS
            or _sha256(literal_raw) != RULE_LITERAL_AUTHORITY_SHA256
        ):
            raise ArtifactFailure("loaded runtime authority was mutated")
        if (
            self.schemas
            != {
                item["value_schema_id"]: item
                for item in self.registry["value_schema_catalog"]
            }
            or self.languages
            != {
                item["text_language_id"]: item
                for item in self.registry["text_language_catalog"]
            }
            or self.dfas
            != {
                item["ascii_dfa_id"]: item
                for item in self.registry["ascii_dfa_catalog"]
            }
            or self.profiles
            != {
                item["unicode_identifier_profile_id"]: item
                for item in self.registry["identifier_profile_catalog"]
            }
            or self.types
            != {
                item["type_name"]: item
                for item in self.registry["ordered_external_type_descriptors"]
            }
            or self.rules
            != {
                item["rule_id"]: item
                for item in self.registry["ordered_cross_field_rule_descriptors"]
            }
            or self.applications
            != {
                item["application_name"]: item
                for item in self.registry["ordered_rule_application_descriptors"]
            }
            or self.resolvers
            != {
                item["fixed_position_resolver_profile_id"]: item
                for item in self.registry["fixed_position_resolver_profile_catalog"]
            }
            or set(self.compiled_applications) != set(self.applications)
            or set(self.compiled_resolvers) != set(self.resolvers)
        ):
            raise ArtifactFailure("runtime catalog indexes were substituted")
        fresh_resolvers, fresh_applications = self._compile_application_runtime_plans()
        if (
            self.compiled_resolvers != fresh_resolvers
            or self.compiled_applications != fresh_applications
        ):
            raise ArtifactFailure("compiled application authority was substituted")
        derived = self._derive_maximum_validation_work()
        if (
            current_schema_work != self._schema_validation_work
            or current_type_work != self._type_validation_work
            or derived
            != (
                self.derived_maximum_validation_work,
                self.maximum_work_schema_id,
                self.maximum_work_type_name,
            )
        ):
            raise ArtifactFailure("compiled validation-work authority was substituted")

    def validate(
        self,
        declared: TypedValue,
        *,
        maximum_work: int = MAXIMUM_VALIDATION_WORK,
    ) -> TypedValue:
        return self.validate_with_evidence(
            declared,
            maximum_work=maximum_work,
        ).declared

    def validate_with_evidence(
        self,
        declared: TypedValue,
        *,
        maximum_work: int = MAXIMUM_VALIDATION_WORK,
    ) -> ValidationEvidence:
        self._assert_authority_intact()
        if type(maximum_work) is not int or maximum_work <= 0:
            raise ValueError("maximum_work must be a positive exact integer")
        if maximum_work > self.derived_maximum_validation_work:
            raise ValueError("maximum_work exceeds the frozen validation ceiling")
        budget = _Budget(maximum_work, maximum_work)
        active: set[int] = set()
        if declared.value_schema_id is not None:
            self._validate_schema(
                declared.value_schema_id,
                declared.value,
                owner=None,
                path=(),
                budget=budget,
                active=active,
            )
        else:
            assert declared.type_name is not None
            self._validate_type(
                declared.type_name,
                declared.value,
                owner=None,
                path=(),
                budget=budget,
                active=active,
            )
        return ValidationEvidence(
            declared=declared,
            validation_work_limit=maximum_work,
            validation_work_used=budget.used,
        )

    def validate_type(
        self,
        type_name: str,
        value: Any,
        *,
        maximum_work: int = MAXIMUM_VALIDATION_WORK,
    ) -> TypedValue:
        return self.validate(
            TypedValue(value=value, type_name=type_name),
            maximum_work=maximum_work,
        )

    def validate_schema(
        self,
        schema_id: str,
        value: Any,
        *,
        maximum_work: int = MAXIMUM_VALIDATION_WORK,
    ) -> TypedValue:
        return self.validate(
            TypedValue(value=value, value_schema_id=schema_id),
            maximum_work=maximum_work,
        )

    def _validate_schema(
        self,
        schema_id: str,
        value: Any,
        *,
        owner: TypedValue | None,
        path: tuple[str | int, ...],
        budget: _Budget,
        active: set[int],
    ) -> None:
        budget.charge(path=path)
        schema = self.schemas.get(schema_id)
        if schema is None:
            _fail(
                UnresolvedReference,
                f"value schema is unresolved: {schema_id}",
                path=path,
            )
        if value is None:
            if schema["nullable"] is not True:
                _fail(ConstraintViolation, "null is not permitted", path=path)
            return
        kind = schema["schema_kind"]
        if kind == "EXACT_BOOLEAN":
            if type(value) is not bool:
                _fail(TypeMismatch, "expected exact Boolean", path=path)
            literal = schema["boolean_literal"]
            if literal is not None and value is not literal:
                _fail(ConstraintViolation, "exact Boolean literal differs", path=path)
            return
        if kind == "SAFE_INTEGER":
            if type(value) is not int:
                _fail(TypeMismatch, "expected exact safe integer", path=path)
            if not (
                -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM
                and schema["integer_minimum"] <= value <= schema["integer_maximum"]
            ):
                _fail(ConstraintViolation, "safe integer is out of bounds", path=path)
            return
        if kind == "TEXT":
            if type(value) is not str:
                _fail(TypeMismatch, "expected exact text", path=path)
            self._validate_text(
                schema["text_language_id"],
                value,
                path=path,
                budget=budget,
            )
            return
        if kind == "ARRAY":
            if type(value) is not list:
                _fail(TypeMismatch, "expected exact array", path=path)
            self._enter_container(value, active=active, path=path)
            try:
                if not (
                    schema["array_minimum_items"]
                    <= len(value)
                    <= schema["array_maximum_items"]
                ):
                    _fail(
                        ConstraintViolation,
                        "array cardinality is out of bounds",
                        path=path,
                    )
                for ordinal, item in enumerate(value):
                    self._validate_schema(
                        schema["array_item_value_schema_id"],
                        item,
                        owner=None,
                        path=(*path, ordinal),
                        budget=budget,
                        active=active,
                    )
            finally:
                active.remove(id(value))
            return
        if kind == "OBJECT_REF":
            if type(value) is not dict:
                _fail(TypeMismatch, "expected exact object", path=path)
            target = schema["referenced_type_name"]
            self._validate_type(
                target,
                value,
                owner=owner,
                path=path,
                budget=budget,
                active=active,
            )
            return
        _fail(ImpossibleState, f"unknown schema kind: {kind}", path=path)

    def _validate_type(
        self,
        type_name: str,
        value: Any,
        *,
        owner: TypedValue | None,
        path: tuple[str | int, ...],
        budget: _Budget,
        active: set[int],
    ) -> None:
        budget.charge(path=path)
        descriptor = self.types.get(type_name)
        if descriptor is None:
            _fail(
                UnresolvedReference,
                f"external type is unresolved: {type_name}",
                path=path,
            )
        if type(value) is not dict:
            _fail(TypeMismatch, "external type value is not an object", path=path)
        if any(type(key) is not str for key in value):
            _fail(
                MalformedValue,
                "external type object keys require exact text",
                path=path,
            )
        if descriptor["type_form"] == "RECORD":
            self._validate_record(
                descriptor,
                value,
                path=path,
                budget=budget,
                active=active,
            )
            return
        if descriptor["type_form"] == "TAGGED_UNION":
            self._validate_union(
                descriptor,
                value,
                owner=owner,
                path=path,
                budget=budget,
                active=active,
            )
            return
        _fail(ImpossibleState, "external type form is unknown", path=path)

    @staticmethod
    def _enter_container(
        value: dict[str, Any] | list[Any],
        *,
        active: set[int],
        path: tuple[str | int, ...],
    ) -> None:
        identity = id(value)
        if identity in active:
            _fail(MalformedValue, "cyclic Python value graph", path=path)
        active.add(identity)

    def _validate_record(
        self,
        descriptor: dict[str, Any],
        value: dict[str, Any],
        *,
        path: tuple[str | int, ...],
        budget: _Budget,
        active: set[int],
    ) -> None:
        self._enter_container(value, active=active, path=path)
        try:
            members = descriptor["record_member_descriptors"]
            expected = [item["member_name"] for item in members]
            if len(value) != len(expected) or set(value) != set(expected):
                _fail(
                    MalformedValue,
                    f"record members differ for {descriptor['type_name']}",
                    path=path,
                )
            owner = TypedValue(value=value, type_name=descriptor["type_name"])
            for member in members:
                name = member["member_name"]
                self._validate_schema(
                    member["value_schema_id"],
                    value[name],
                    owner=owner,
                    path=(*path, name),
                    budget=budget,
                    active=active,
                )
            self._validate_codec_bound(descriptor, value, path=path)
            if descriptor["type_role"] == "STANDALONE":
                self._validate_standalone_identity(descriptor, value, path=path)
        finally:
            active.remove(id(value))

    @staticmethod
    def _validate_codec_bound(
        descriptor: dict[str, Any],
        value: dict[str, Any],
        *,
        path: tuple[str | int, ...],
    ) -> None:
        encoded_octets = len(_canonical_bytes(value))
        relation = descriptor["codec_byte_bound_relation"]
        limit = descriptor["codec_octet_limit"]
        if not (
            (relation == "LE" and encoded_octets <= limit)
            or (relation == "LT" and encoded_octets < limit)
        ):
            _fail(
                ConstraintViolation,
                f"{descriptor['type_form'].lower()} codec {relation} bound violated",
                path=path,
            )

    def _validate_standalone_identity(
        self,
        descriptor: dict[str, Any],
        value: dict[str, Any],
        *,
        path: tuple[str | int, ...],
    ) -> None:
        if value.get("canonicalization_version") != CANONICALIZATION_VERSION:
            _fail(
                ConstraintViolation,
                "standalone canonicalization version differs",
                path=(*path, "canonicalization_version"),
            )
        if value.get("measurement_schema_version") != MEASUREMENT_SCHEMA_VERSION:
            _fail(
                ConstraintViolation,
                "standalone measurement schema version differs",
                path=(*path, "measurement_schema_version"),
            )
        if value.get("record_domain") != descriptor["described_record_domain"]:
            _fail(
                ConstraintViolation,
                "standalone record domain differs",
                path=(*path, "record_domain"),
            )
        payload = {
            name: value[name] for name in descriptor["identity_payload_member_order"]
        }
        expected = _semantic_id(descriptor["described_record_domain"], payload)
        identity_field = descriptor["identity_field"]
        if value[identity_field] != expected:
            _fail(
                ConstraintViolation,
                "standalone semantic identity differs",
                path=(*path, identity_field),
            )

    @staticmethod
    def _resolve_path(
        root: Any,
        typed_member_path: list[str],
        *,
        path: tuple[str | int, ...],
    ) -> Any:
        current = root
        for member in typed_member_path:
            if type(current) is not dict or member not in current:
                _fail(
                    UnresolvedReference,
                    "typed member path is unresolved",
                    path=(*path, member),
                )
            current = current[member]
        return current

    def _validate_union(
        self,
        descriptor: dict[str, Any],
        value: dict[str, Any],
        *,
        owner: TypedValue | None,
        path: tuple[str | int, ...],
        budget: _Budget,
        active: set[int],
    ) -> None:
        topology = descriptor["tagged_union_descriptor"]
        scope = topology["payload_binding_scope"]
        if scope == "SELF_VALUE":
            selected_root = value
        elif scope == "OWNER_MEMBER":
            expected_owner = topology["payload_owner_type_name"]
            if owner is None or owner.type_name != expected_owner:
                _fail(
                    UnionUnresolvedReference,
                    f"owner-scoped union requires declared owner {expected_owner}",
                    path=path,
                )
            selected_root = owner.value
            try:
                payload = self._resolve_path(
                    selected_root,
                    topology["payload_typed_member_path"],
                    path=path,
                )
            except UnresolvedReference as exc:
                raise UnionUnresolvedReference(
                    "owner-scoped union payload path differs",
                    path=path,
                ) from exc
            if payload is not value:
                _fail(
                    UnionImpossibleState,
                    "owner-scoped union payload does not match owner member",
                    path=path,
                )
        else:
            _fail(ImpossibleState, "unknown union payload scope", path=path)

        actual_literals: dict[str, str] = {}
        for discriminator in topology["ordered_discriminator_descriptors"]:
            discriminator_scope = discriminator["discriminator_scope"]
            if discriminator_scope == "SELECTED_VALUE":
                root = value
            elif discriminator_scope == "OWNER_OBJECT":
                expected_owner = discriminator["discriminator_owner_type_name"]
                if owner is None or owner.type_name != expected_owner:
                    _fail(
                        UnionUnresolvedReference,
                        f"union discriminator requires owner {expected_owner}",
                        path=path,
                    )
                root = selected_root
            else:
                _fail(ImpossibleState, "unknown discriminator scope", path=path)
            member_path = discriminator["discriminator_typed_member_path"]
            try:
                actual = self._resolve_path(root, member_path, path=path)
            except UnresolvedReference as exc:
                raise UnionUnresolvedReference(
                    "tagged-union discriminator path differs",
                    path=(*path, *member_path),
                ) from exc
            try:
                self._validate_text(
                    discriminator["text_language_id"],
                    actual,
                    path=(*path, *member_path),
                    budget=budget,
                )
            except TypeMismatch as exc:
                raise UnionTypeMismatch(
                    "tagged-union discriminator differs",
                    path=(*path, *member_path),
                ) from exc
            except ConstraintViolation as exc:
                raise UnionConstraintViolation(
                    "tagged-union discriminator differs",
                    path=(*path, *member_path),
                ) from exc
            actual_literals[member_path[-1]] = actual

        matches = []
        for alternative in topology["ordered_alternatives"]:
            required = {
                literal["member_name"]: literal["text_value"]
                for literal in alternative["ordered_discriminator_literals"]
            }
            if actual_literals == required:
                matches.append(alternative)
        if len(matches) != 1:
            _fail(
                UnionConstraintViolation,
                "tagged-union discriminator does not select exactly one alternative",
                path=path,
            )
        try:
            self._validate_type(
                matches[0]["referenced_type_name"],
                value,
                owner=None,
                path=path,
                budget=budget,
                active=active,
            )
        except MalformedValue as exc:
            raise UnionMalformedValue(
                "tagged-union selected concrete body differs", path=path
            ) from exc
        except TypeMismatch as exc:
            raise UnionTypeMismatch(
                "tagged-union selected concrete body differs", path=path
            ) from exc
        except ConstraintViolation as exc:
            raise UnionConstraintViolation(
                "tagged-union selected concrete body differs", path=path
            ) from exc
        self._validate_codec_bound(descriptor, value, path=path)

    def _validate_text(
        self,
        language_id: str,
        value: Any,
        *,
        path: tuple[str | int, ...],
        budget: _Budget,
    ) -> None:
        budget.charge(path=path)
        if type(value) is not str:
            _fail(TypeMismatch, "text language requires exact text", path=path)
        language = self.languages.get(language_id)
        if language is None:
            _fail(
                UnresolvedReference,
                f"text language is unresolved: {language_id}",
                path=path,
            )
        minimum = language["minimum_utf8_octets"]
        maximum = language["maximum_utf8_octets"]
        if maximum is not None and len(value) > maximum:
            _fail(
                ConstraintViolation,
                "text exceeds its UTF-8 bound before encoding",
                path=path,
            )
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            _fail(MalformedValue, "text contains a surrogate", path=path)
        encoded = value.encode("utf-8")
        if minimum is not None and not minimum <= len(encoded) <= maximum:
            _fail(
                ConstraintViolation,
                "text UTF-8 length is out of language bounds",
                path=path,
            )
        kind = language["language_kind"]
        if kind in {"LITERAL", "ENUM"}:
            if value not in language["ordered_literals"]:
                _fail(
                    ConstraintViolation,
                    "text is outside the closed language",
                    path=path,
                )
            return
        if kind == "ASCII_DFA":
            self._validate_ascii_dfa(language["ascii_dfa_id"], value, path=path)
            return
        if kind == "UNICODE_IDENTIFIER":
            self._validate_unicode_identifier(
                language["unicode_identifier_profile_id"],
                value,
                path=path,
            )
            return
        if kind != "BUILTIN":
            _fail(ImpossibleState, "unknown text language kind", path=path)
        self._validate_builtin(language, value, path=path)

    def _validate_ascii_dfa(
        self,
        dfa_id: str,
        value: str,
        *,
        path: tuple[str | int, ...],
    ) -> None:
        dfa = self.dfas.get(dfa_id)
        if dfa is None:
            _fail(UnresolvedReference, "ASCII DFA is unresolved", path=path)
        if not dfa["minimum_octets"] <= len(value) <= dfa["maximum_octets"]:
            _fail(ConstraintViolation, "ASCII-DFA length is out of bounds", path=path)
        try:
            octets = value.encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise ConstraintViolation(
                "ASCII-DFA text contains non-ASCII characters",
                path=path,
            ) from exc
        transitions: dict[tuple[int, int], int] = {}
        for row in dfa["ordered_transition_rows"]:
            for byte in range(
                row["inclusive_byte_minimum"],
                row["inclusive_byte_maximum"] + 1,
            ):
                key = (row["source_state"], byte)
                if key in transitions:
                    _fail(ImpossibleState, "ASCII-DFA transitions overlap", path=path)
                transitions[key] = row["target_state"]
        state = dfa["start_state"]
        for byte in octets:
            target = transitions.get((state, byte))
            if target is None:
                _fail(
                    ConstraintViolation,
                    "ASCII-DFA has no transition for text",
                    path=path,
                )
            state = target
        if state not in dfa["ordered_accepting_states"]:
            _fail(ConstraintViolation, "ASCII-DFA rejects text", path=path)

    def _validate_unicode_identifier(
        self,
        profile_id: str,
        value: str,
        *,
        path: tuple[str | int, ...],
    ) -> None:
        profile = self.profiles.get(profile_id)
        if profile is None:
            _fail(UnresolvedReference, "Unicode profile is unresolved", path=path)
        if (
            unicodedata.unidata_version != "15.0.0"
            or profile["unicode_version"] != "15.0.0"
        ):
            _fail(
                ImpossibleState,
                "host/profile Unicode authority is not frozen at 15.0.0",
                path=path,
            )
        if not value:
            _fail(ConstraintViolation, "Unicode identifier is empty", path=path)
        if (
            len(value) > profile["maximum_scalar_values"]
            or len(value) > profile["maximum_utf8_octets"]
        ):
            _fail(
                ConstraintViolation,
                "Unicode identifier exceeds scalar/octet lower bound",
                path=path,
            )
        if (
            profile["normalization_form"] != "NFC"
            or unicodedata.normalize("NFC", value) != value
        ):
            _fail(ConstraintViolation, "Unicode identifier is not NFC", path=path)
        if len(value.encode("utf-8")) > profile["maximum_utf8_octets"]:
            _fail(
                ConstraintViolation,
                "Unicode identifier exceeds scalar/octet bound",
                path=path,
            )

        def code_point(text: str) -> int:
            if re.fullmatch(r"U\+[0-9A-F]{4,6}", text) is None:
                _fail(
                    ImpossibleState,
                    "Unicode code-point authority is malformed",
                    path=path,
                )
            return int(text[2:], 16)

        forbidden = [
            (code_point(lower), code_point(upper))
            for lower, upper in profile["forbidden_code_point_ranges"]
        ]
        if any(
            lower <= ord(character) <= upper
            for character in value
            for lower, upper in forbidden
        ):
            _fail(
                ConstraintViolation,
                "Unicode identifier contains forbidden code point",
                path=path,
            )
        edge_trim = {code_point(item) for item in profile["edge_trim_code_points"]}
        if value and (ord(value[0]) in edge_trim or ord(value[-1]) in edge_trim):
            _fail(
                ConstraintViolation,
                "Unicode identifier has forbidden edge trim",
                path=path,
            )

    def _validate_builtin(
        self,
        language: dict[str, Any],
        value: str,
        *,
        path: tuple[str | int, ...],
    ) -> None:
        built_in = language["built_in_language_kind"]
        if built_in == "LOWERCASE_SHA256":
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                _fail(ConstraintViolation, "SHA-256 text is not canonical", path=path)
            return
        if built_in == "UINT128_DECIMAL":
            if language["decimal_maximum"] != UINT128_MAXIMUM_TEXT:
                _fail(
                    ImpossibleState,
                    "uint128 decimal authority maximum differs",
                    path=path,
                )
            _parse_uint128_decimal(value, path=path)
            return
        if built_in == "CANONICAL_BASE64":
            try:
                encoded = value.encode("ascii", errors="strict")
                decoded = base64.b64decode(encoded, validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ConstraintViolation(
                    "base64 text is malformed",
                    path=path,
                ) from exc
            if base64.b64encode(decoded) != encoded:
                _fail(ConstraintViolation, "base64 text is not canonical", path=path)
            if not (
                language["minimum_decoded_octets"]
                <= len(decoded)
                <= language["maximum_decoded_octets"]
            ):
                _fail(
                    ConstraintViolation,
                    "base64 decoded length is out of bounds",
                    path=path,
                )
            return
        if built_in == "RFC3339_UTC":
            match = re.fullmatch(
                r"([0-9]{4})-([0-9]{2})-([0-9]{2})T"
                r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
                r"(?:\.([0-9]{6}))?Z",
                value,
            )
            if match is None or len(value.encode("utf-8")) not in {20, 27}:
                _fail(
                    ConstraintViolation,
                    "timestamp is outside exact UTC grammar",
                    path=path,
                )
            if match.group(7) == "000000":
                _fail(
                    ConstraintViolation,
                    "zero fractional timestamp is not canonical",
                    path=path,
                )
            try:
                dt.datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    int(match.group(4)),
                    int(match.group(5)),
                    int(match.group(6)),
                    int(match.group(7) or "0"),
                    tzinfo=dt.timezone.utc,
                )
            except ValueError as exc:
                raise ConstraintViolation(
                    "timestamp is not a valid UTC instant",
                    path=path,
                ) from exc
            return
        if built_in == "RAW_CANONICAL_JSON_STRING":
            return
        _fail(ImpossibleState, f"unknown built-in language: {built_in}", path=path)

    @staticmethod
    def _complex_visit(
        counters: _RuleCounters,
        count: int = 1,
    ) -> None:
        if type(count) is not int or count < 0:
            raise ImpossibleState("complex work charge is invalid")
        counters.complex_row_item_visits += count

    def _complex_canonical_bytes(
        self,
        value: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bytes:
        try:
            encoded = _canonical_bytes(value)
        except RuntimeFailure as exc:
            raise MalformedValue(
                "complex operand is not canonical-I-JSON encodable",
                path=path,
            ) from exc
        counters.complex_canonicalized_octets += len(encoded)
        return encoded

    def _complex_semantic_id(
        self,
        domain: str,
        payload: dict[str, Any],
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> str:
        envelope = {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": payload,
            "schema_version": MEASUREMENT_SCHEMA_VERSION,
        }
        return _sha256(
            self._complex_canonical_bytes(
                envelope,
                counters=counters,
                path=path,
            )
        )

    def _complex_record_identity(
        self,
        type_name: str,
        record: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> str:
        descriptor = self.records.get(type_name)
        if descriptor is None or descriptor["type_role"] != "STANDALONE":
            _fail(
                ImpossibleState,
                f"identity descriptor is not a standalone record: {type_name}",
                path=path,
            )
        if type(record) is not dict:
            _fail(TypeMismatch, "identity operand is not an object", path=path)
        try:
            payload = {
                name: record[name]
                for name in descriptor["identity_payload_member_order"]
            }
        except KeyError as exc:
            raise MalformedValue(
                "identity operand lacks a required payload member",
                path=path,
            ) from exc
        return self._complex_semantic_id(
            descriptor["described_record_domain"],
            payload,
            counters=counters,
            path=path,
        )

    def _complex_exact_equal(
        self,
        left: Any,
        right: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(left) is not type(right):
            return False
        if type(left) in {dict, list}:
            return self._complex_canonical_bytes(
                left,
                counters=counters,
                path=(*path, "left"),
            ) == self._complex_canonical_bytes(
                right,
                counters=counters,
                path=(*path, "right"),
            )
        return left == right

    def _index_supplied_records(
        self,
        records: Any,
        key: str,
        *,
        expected_count: int,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> dict[str, dict[str, Any]]:
        if type(records) is not list:
            _fail(TypeMismatch, f"{key} authority is not an array", path=path)
        if len(records) != expected_count:
            _fail(
                UnresolvedReference,
                f"{key} authority count differs from {expected_count}",
                path=path,
            )
        result: dict[str, dict[str, Any]] = {}
        for ordinal, record in enumerate(records):
            self._complex_visit(counters)
            if type(record) is not dict or type(record.get(key)) is not str:
                _fail(
                    ImpossibleState,
                    f"{key} authority row is malformed",
                    path=(*path, ordinal),
                )
            identifier = record[key]
            if identifier in result:
                _fail(
                    UnresolvedReference,
                    f"{key} authority is duplicated: {identifier}",
                    path=(*path, ordinal),
                )
            result[identifier] = record
        return result

    def _resolve_unique_by_member(
        self,
        records: Any,
        member: str,
        key: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> dict[str, Any]:
        if type(records) is not list:
            _fail(TypeMismatch, "unique resolver input is not an array", path=path)
        selected: dict[str, Any] | None = None
        for ordinal, record in enumerate(records):
            self._complex_visit(counters)
            if type(record) is not dict or member not in record:
                _fail(
                    ImpossibleState,
                    "unique resolver authority row is malformed",
                    path=(*path, ordinal),
                )
            if self._raw_exact_equal(record[member], key):
                if selected is not None:
                    _fail(
                        UnresolvedReference,
                        f"authority member is duplicated: {member}",
                        path=path,
                    )
                selected = record
        if selected is None:
            _fail(
                UnresolvedReference,
                f"authority member is unresolved: {member}",
                path=path,
            )
        return selected

    def _build_target_registry_indexes(
        self,
        registry: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> _TargetRegistryIndexes:
        if type(registry) is not dict:
            _fail(TypeMismatch, "target registry operand is not an object", path=path)
        try:
            status_policy = registry["status_reason_policy_definition"]
            if type(status_policy) is not dict:
                raise TypeError
            descriptors = self._index_supplied_records(
                registry["descriptors"],
                "field_id",
                expected_count=185,
                counters=counters,
                path=(*path, "descriptors"),
            )
            constraints = self._index_supplied_records(
                registry["ordered_value_constraint_definitions"],
                "value_constraint_id",
                expected_count=17,
                counters=counters,
                path=(*path, "constraints"),
            )
            shapes = self._index_supplied_records(
                registry["ordered_value_shape_definitions"],
                "value_shape_id",
                expected_count=6,
                counters=counters,
                path=(*path, "shapes"),
            )
            vocabularies = self._index_supplied_records(
                registry["ordered_vocabulary_definitions"],
                "vocabulary_id",
                expected_count=25,
                counters=counters,
                path=(*path, "vocabularies"),
            )
            reasons = self._index_supplied_records(
                status_policy["reason_rules"],
                "reason",
                expected_count=26,
                counters=counters,
                path=(*path, "reason_rules"),
            )
            cross_field_constraints = self._index_supplied_records(
                registry["ordered_cross_field_constraint_definitions"],
                "cross_field_constraint_id",
                expected_count=1,
                counters=counters,
                path=(*path, "cross_field_constraints"),
            )
        except KeyError as exc:
            raise MalformedValue(
                "target registry lacks a required authority catalog",
                path=path,
            ) from exc
        except TypeError as exc:
            raise TypeMismatch(
                "target registry authority catalog has the wrong type",
                path=path,
            ) from exc
        recomputed = self._complex_record_identity(
            "TargetFieldRegistryV1",
            registry,
            counters=counters,
            path=(*path, "target_field_registry_id"),
        )
        if registry.get("target_field_registry_id") != recomputed:
            _fail(
                UnresolvedReference,
                "supplied target registry identity does not recompute",
                path=(*path, "target_field_registry_id"),
            )
        return _TargetRegistryIndexes(
            descriptors=descriptors,
            constraints=constraints,
            shapes=shapes,
            vocabularies=vocabularies,
            reasons=reasons,
            cross_field_constraints=cross_field_constraints,
            recomputed_registry_id=recomputed,
        )

    def _selected_union_record(
        self,
        union_type_name: str,
        selected_value: Any,
        *,
        owner_type_name: str | None,
        owner_value: dict[str, Any] | None,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        union_descriptor = self.unions.get(union_type_name)
        if union_descriptor is None:
            _fail(
                ImpossibleState,
                f"tagged-union descriptor is unresolved: {union_type_name}",
                path=path,
            )
        if type(selected_value) is not dict:
            _fail(TypeMismatch, "selected union payload is not an object", path=path)
        topology = union_descriptor["tagged_union_descriptor"]
        payload_scope = topology["payload_binding_scope"]
        if payload_scope == "SELF_VALUE":
            payload = selected_value
        elif payload_scope == "OWNER_MEMBER":
            expected_owner = topology["payload_owner_type_name"]
            if owner_type_name != expected_owner or type(owner_value) is not dict:
                _fail(
                    UnionUnresolvedReference,
                    f"union requires owner {expected_owner}",
                    path=path,
                )
            try:
                payload = self._resolve_path(
                    owner_value,
                    topology["payload_typed_member_path"],
                    path=path,
                )
            except UnresolvedReference as exc:
                raise UnionUnresolvedReference(
                    "union owner payload path differs",
                    path=path,
                ) from exc
            if payload is not selected_value:
                _fail(
                    UnionImpossibleState,
                    "owner-scoped union payload differs from its owner member",
                    path=path,
                )
        else:
            _fail(ImpossibleState, "union payload scope is unknown", path=path)
        actual: dict[str, str] = {}
        for discriminator in topology["ordered_discriminator_descriptors"]:
            self._complex_visit(counters)
            scope = discriminator["discriminator_scope"]
            if scope == "SELECTED_VALUE":
                root = selected_value
            elif scope == "OWNER_OBJECT":
                if (
                    owner_type_name != discriminator["discriminator_owner_type_name"]
                    or type(owner_value) is not dict
                ):
                    _fail(
                        UnionUnresolvedReference,
                        "union discriminator owner differs",
                        path=path,
                    )
                root = owner_value
            else:
                _fail(
                    ImpossibleState, "union discriminator scope is unknown", path=path
                )
            member_path = discriminator["discriminator_typed_member_path"]
            try:
                literal = self._resolve_path(root, member_path, path=path)
            except UnresolvedReference as exc:
                raise UnionUnresolvedReference(
                    "union discriminator path differs",
                    path=path,
                ) from exc
            if type(literal) is not str:
                _fail(
                    UnionTypeMismatch,
                    "union discriminator is not text",
                    path=path,
                )
            actual[member_path[-1]] = literal
        match: dict[str, Any] | None = None
        for alternative in topology["ordered_alternatives"]:
            self._complex_visit(counters)
            required = {
                literal["member_name"]: literal["text_value"]
                for literal in alternative["ordered_discriminator_literals"]
            }
            if required == actual:
                if match is not None:
                    _fail(
                        ImpossibleState,
                        "tagged-union alternatives are ambiguous",
                        path=path,
                    )
                match = alternative
        if match is None:
            _fail(
                UnionUnresolvedReference,
                "tagged-union alternative is unresolved",
                path=path,
            )
        record_descriptor = self.records.get(match["referenced_type_name"])
        if record_descriptor is None:
            _fail(
                ImpossibleState,
                "tagged-union alternative is not a concrete record",
                path=path,
            )
        return match, record_descriptor, payload

    def _snapshot_application_record(
        self,
        value: Any,
        *,
        type_name: str,
        counters: _ApplicationCounters,
        path: tuple[str | int, ...],
    ) -> tuple[dict[str, Any], bytes]:
        """Copy an untrusted value into a bounded, plain, exact-I-JSON graph."""

        descriptor = self.types[type_name]
        node_limit = self._type_validation_work[type_name]
        codec_limit = descriptor["codec_octet_limit"]
        active: set[int] = set()
        nodes = 0
        scalar_octets = 0

        def copy_value(
            current: Any,
            *,
            depth: int,
            current_path: tuple[str | int, ...],
        ) -> Any:
            nonlocal nodes, scalar_octets
            if depth > MAXIMUM_JSON_DEPTH:
                _fail(
                    WorkBoundExceeded,
                    "application snapshot depth bound exceeded",
                    path=current_path,
                )
            nodes += 1
            if nodes > node_limit:
                _fail(
                    WorkBoundExceeded,
                    "application snapshot node bound exceeded",
                    path=current_path,
                )
            if current is None or type(current) is bool:
                return current
            if type(current) is int:
                if not -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM:
                    _fail(
                        MalformedValue,
                        "application integer is outside safe I-JSON",
                        path=current_path,
                    )
                return current
            if type(current) is str:
                if len(current) > codec_limit or any(
                    0xD800 <= ord(character) <= 0xDFFF for character in current
                ):
                    _fail(
                        MalformedValue,
                        "application text is outside exact I-JSON",
                        path=current_path,
                    )
                encoded = current.encode("utf-8", errors="strict")
                scalar_octets += len(encoded)
                if scalar_octets > codec_limit:
                    _fail(
                        WorkBoundExceeded,
                        "application snapshot scalar-octet bound exceeded",
                        path=current_path,
                    )
                return current
            if type(current) not in {dict, list}:
                _fail(
                    MalformedValue,
                    "application value is not an exact I-JSON value",
                    path=current_path,
                )
            identity = id(current)
            if identity in active:
                _fail(
                    MalformedValue,
                    "application value graph is cyclic",
                    path=current_path,
                )
            active.add(identity)
            try:
                if type(current) is list:
                    return [
                        copy_value(
                            item,
                            depth=depth + 1,
                            current_path=(*current_path, ordinal),
                        )
                        for ordinal, item in enumerate(current)
                    ]
                copied: dict[str, Any] = {}
                for key, item in current.items():
                    if type(key) is not str or any(
                        0xD800 <= ord(character) <= 0xDFFF for character in key
                    ):
                        _fail(
                            MalformedValue,
                            "application object key is not exact I-JSON text",
                            path=current_path,
                        )
                    if len(key) > codec_limit:
                        _fail(
                            WorkBoundExceeded,
                            "application object key exceeds codec bound",
                            path=current_path,
                        )
                    scalar_octets += len(key.encode("utf-8", errors="strict"))
                    if scalar_octets > codec_limit:
                        _fail(
                            WorkBoundExceeded,
                            "application snapshot scalar-octet bound exceeded",
                            path=current_path,
                        )
                    copied[key] = copy_value(
                        item,
                        depth=depth + 1,
                        current_path=(*current_path, key),
                    )
                return copied
            finally:
                active.remove(identity)

        try:
            snapshot = copy_value(value, depth=0, current_path=path)
        except (RuntimeError, RecursionError) as exc:
            raise MalformedValue(
                "application source changed during snapshot",
                path=path,
            ) from exc
        if type(snapshot) is not dict:
            _fail(TypeMismatch, "application record is not an object", path=path)
        canonical = _canonical_bytes(snapshot)
        counters.snapshot_canonicalized_octets += len(canonical)
        return snapshot, canonical

    def _validate_application_record_graph(
        self,
        type_name: str,
        snapshot: dict[str, Any],
        *,
        counters: _ApplicationCounters,
        path: tuple[str | int, ...],
    ) -> None:
        counters.logical_record_graph_validations += 1
        counters.physical_record_graph_validations += 1
        maximum_work = self._type_validation_work[type_name]
        budget = _Budget(maximum_work, maximum_work)
        try:
            self._validate_type(
                type_name,
                snapshot,
                owner=None,
                path=path,
                budget=budget,
                active=set(),
            )
        finally:
            counters.validation_work_used += budget.used

    def _walk_application_schema_intrinsics(
        self,
        schema_id: str,
        value: Any,
        *,
        owner: TypedValue | None,
        context: _ApplicationExecutionContext,
        execute_prevalidated: Callable[[str, dict[str, Any], str | None], bool],
        path: tuple[str | int, ...],
    ) -> None:
        if value is None:
            return
        schema = self.schemas[schema_id]
        kind = schema["schema_kind"]
        if kind == "ARRAY":
            item_schema_id = schema["array_item_value_schema_id"]
            for ordinal, item in enumerate(value):
                self._walk_application_schema_intrinsics(
                    item_schema_id,
                    item,
                    owner=None,
                    context=context,
                    execute_prevalidated=execute_prevalidated,
                    path=(*path, ordinal),
                )
            return
        if kind != "OBJECT_REF":
            return
        self._walk_application_type_intrinsics(
            schema["referenced_type_name"],
            value,
            owner=owner,
            context=context,
            execute_prevalidated=execute_prevalidated,
            path=path,
        )

    def _walk_application_type_intrinsics(
        self,
        type_name: str,
        value: dict[str, Any],
        *,
        owner: TypedValue | None,
        context: _ApplicationExecutionContext,
        execute_prevalidated: Callable[[str, dict[str, Any], str | None], bool],
        path: tuple[str | int, ...],
    ) -> None:
        descriptor = self.types[type_name]
        if descriptor["type_form"] == "TAGGED_UNION":
            try:
                descriptor = self._selected_literal_record_descriptor(
                    descriptor,
                    value,
                    owner=owner,
                    path=path,
                )
            except RuntimeFailure as exc:
                raise ArtifactFailure(
                    "validated application union traversal diverged",
                    path=path,
                ) from exc
        record_owner = TypedValue(value=value, type_name=descriptor["type_name"])
        for member in descriptor["record_member_descriptors"]:
            self._walk_application_schema_intrinsics(
                member["value_schema_id"],
                value[member["member_name"]],
                owner=record_owner,
                context=context,
                execute_prevalidated=execute_prevalidated,
                path=(*path, member["member_name"]),
            )
        intrinsic_rules = descriptor["ordered_intrinsic_rule_ids"]
        canonical: bytes | None = None
        for rule_id in intrinsic_rules:
            context.counters.intrinsic_rule_logical_invocations += 1
            if canonical is None:
                canonical = _canonical_bytes(value)
            cache_key = (descriptor["type_name"], rule_id, canonical)
            if cache_key in context.intrinsic_accept_cache:
                context.counters.intrinsic_rule_cache_hits += 1
                continue
            context.counters.intrinsic_rule_physical_executions += 1
            try:
                root = execute_prevalidated(
                    rule_id,
                    {"self": value},
                    descriptor["type_name"],
                )
            except (ArtifactFailure, UnsupportedRule):
                raise
            except RuntimeFailure as exc:
                raise _ApplicationCandidateFailure(exc, rule_id=rule_id) from exc
            if not root:
                failure = BusinessRuleFalse(
                    f"application intrinsic root is false: {rule_id}",
                    path=path,
                )
                raise _ApplicationCandidateFailure(
                    failure,
                    rule_id=rule_id,
                )
            context.intrinsic_accept_cache.add(cache_key)

    def _resolve_application_fixed_sequence(
        self,
        sequence: _CompiledSequenceBinding,
        roots: dict[str, dict[str, Any]],
        supplied_records: tuple[dict[str, Any], ...],
        *,
        context: _ApplicationExecutionContext,
    ) -> tuple[dict[str, Any], ...]:
        if sequence.resolver_id is None:
            raise ArtifactFailure("external sequence lacks a compiled resolver")
        resolver = self.compiled_resolvers[sequence.resolver_id]
        root = roots[sequence.source_root_binding_name]
        context.counters.resolver_invocations += 1
        source_ids: list[Any] = []
        for result_kind, null_semantics, typed_path in resolver.source_paths:
            value = self._resolve_path(
                root,
                list(typed_path),
                path=("resolver", resolver.profile_name),
            )
            if result_kind == "ARRAY":
                if value is None and null_semantics == "REJECT_NULL":
                    _fail(
                        MalformedValue,
                        "resolver array source is null",
                        path=("resolver", resolver.profile_name),
                    )
                if type(value) is not list:
                    _fail(
                        TypeMismatch,
                        "resolver array source is not an array",
                        path=("resolver", resolver.profile_name),
                    )
                source_ids.extend(value)
            elif result_kind == "OPTIONAL_SCALAR":
                if value is None and null_semantics == "NULL_TO_EMPTY_SEQUENCE":
                    continue
                source_ids.append(value)
            else:
                raise ArtifactFailure("compiled resolver result kind differs")
        context.counters.resolver_source_identity_count += len(source_ids)
        if not (resolver.minimum_items <= len(source_ids) <= resolver.maximum_items):
            _fail(
                ConstraintViolation,
                "resolver source cardinality differs",
                path=("resolver", resolver.profile_name),
            )
        if len(source_ids) != len(supplied_records):
            _fail(
                UnresolvedReference,
                "resolver supplied/source cardinality differs",
                path=("resolver", resolver.profile_name),
            )
        for ordinal, (source_id, record) in enumerate(
            zip(source_ids, supplied_records, strict=True)
        ):
            context.counters.resolver_identity_logical_recomputations += 1
            context.counters.resolver_identity_physical_recomputations += 1
            recomputed = self._complex_record_identity(
                resolver.resolved_item_type_name,
                record,
                counters=context.rule_counters,
                path=("resolver", resolver.profile_name, ordinal),
            )
            context.counters.resolver_logical_comparisons += 1
            if type(source_id) is not str or source_id != recomputed:
                _fail(
                    UnresolvedReference,
                    "resolver record identity differs in source order",
                    path=("resolver", resolver.profile_name, ordinal),
                )
        return supplied_records

    @staticmethod
    def _application_failure_class(failure: RuntimeFailure) -> str:
        if isinstance(failure, BusinessRuleFalse):
            return "BUSINESS_RULE_FALSE"
        if isinstance(failure, UnionMismatch) or isinstance(failure, TypeMismatch):
            return "TYPE_OR_UNION_MISMATCH"
        if isinstance(failure, (MalformedValue, ConstraintViolation)):
            return "MALFORMED_OPERAND"
        if isinstance(failure, UnresolvedReference):
            return "UNRESOLVED_AUTHORITY"
        if isinstance(failure, CandidateImpossibleState):
            return "IMPOSSIBLE_BRANCH"
        if isinstance(failure, WorkBoundExceeded):
            return "WORK_BOUND_EXCEEDED"
        raise ArtifactFailure("application failure has no frozen mapping") from failure

    @staticmethod
    def _application_evidence(
        plan: _CompiledApplicationPlan,
        context: _ApplicationExecutionContext,
        *,
        accepted: bool,
        coordinate: ApplicationFailureCoordinate,
    ) -> ApplicationEvaluationEvidence:
        counters = context.counters
        rule_counters = context.rule_counters
        return ApplicationEvaluationEvidence(
            application_name=plan.application_name,
            rule_application_id=plan.rule_application_id,
            rule_id=plan.rule_id,
            accepted=accepted,
            result_coordinate=coordinate,
            maximum_rule_evaluations=plan.maximum_rule_evaluations,
            charged_rule_evaluations=counters.charged_rule_evaluations,
            completed_rule_evaluations=counters.completed_rule_evaluations,
            intrinsic_rule_logical_invocations=(
                counters.intrinsic_rule_logical_invocations
            ),
            intrinsic_rule_physical_executions=(
                counters.intrinsic_rule_physical_executions
            ),
            intrinsic_rule_cache_hits=counters.intrinsic_rule_cache_hits,
            resolver_invocations=counters.resolver_invocations,
            resolver_source_identity_count=(counters.resolver_source_identity_count),
            resolver_identity_logical_recomputations=(
                counters.resolver_identity_logical_recomputations
            ),
            resolver_identity_physical_recomputations=(
                counters.resolver_identity_physical_recomputations
            ),
            resolver_identity_cache_hits=counters.resolver_identity_cache_hits,
            resolver_logical_comparisons=counters.resolver_logical_comparisons,
            logical_record_graph_validations=(
                counters.logical_record_graph_validations
            ),
            physical_record_graph_validations=(
                counters.physical_record_graph_validations
            ),
            record_graph_validation_cache_hits=(
                counters.record_graph_validation_cache_hits
            ),
            validation_work_used=counters.validation_work_used,
            snapshot_canonicalized_octets=(counters.snapshot_canonicalized_octets),
            total_expression_nodes=rule_counters.total_expression_nodes,
            complex_operator_invocations=(rule_counters.complex_operator_invocations),
            complex_row_item_visits=rule_counters.complex_row_item_visits,
            complex_canonicalized_octets=(rule_counters.complex_canonicalized_octets),
            ordered_rule_step_evidence=tuple(context.ordered_rule_steps),
        )

    def evaluate_application(
        self,
        application_name: str,
        ordered_root_inputs: tuple[ApplicationRecordInput, ...],
        ordered_external_sequences: tuple[ApplicationSequenceInput, ...] = (),
    ) -> ApplicationEvaluationEvidence:
        """Execute one frozen application over immutable caller snapshots.

        A production adapter must snapshot/call while holding the mutable
        source owner's lock.  This evaluator cannot make concurrent mutation
        of a caller-owned graph atomic; after Phase 1 it drops all caller
        references and never rereads the original values.
        """

        self._assert_authority_intact()
        if type(application_name) is not str:
            raise TypeMismatch("application name requires exact text")
        plan = self.compiled_applications.get(application_name)
        if plan is None:
            raise UnresolvedReference(f"application is unresolved: {application_name}")
        exact_rule_authority = {
            rule_id: _canonical_bytes(rule) for rule_id, rule in self.rules.items()
        }
        context = _ApplicationExecutionContext(
            counters=_ApplicationCounters(),
            rule_counters=_RuleCounters(),
            intrinsic_accept_cache=set(),
            ordered_rule_steps=[],
        )
        current_ordinal: int | None = None

        def reject(
            failure: RuntimeFailure,
            *,
            rule_id: str,
        ) -> ApplicationEvaluationEvidence:
            if isinstance(failure, (ArtifactFailure, UnsupportedRule)):
                raise failure
            self._assert_authority_intact()
            failure_class = self._application_failure_class(failure)
            coordinate = ApplicationFailureCoordinate(
                application_name=plan.application_name,
                rule_application_id=plan.rule_application_id,
                rule_id=rule_id,
                iteration_ordinal=current_ordinal,
                failure_class=failure_class,
            )
            return self._application_evidence(
                plan,
                context,
                accepted=False,
                coordinate=coordinate,
            )

        # This closure is the only unchecked node executor.  It is lexically
        # confined to this call and bound to the already reverified immutable
        # application plan and an exact attached intrinsic owner.
        def execute_prevalidated(
            rule_id: str,
            bindings: dict[str, Any],
            intrinsic_owner_type_name: str | None,
        ) -> bool:
            if self.compiled_applications.get(plan.application_name) != plan:
                raise ArtifactFailure("application plan changed during execution")
            rule = self.rules.get(rule_id)
            if rule is None:
                raise ArtifactFailure("application rule is unresolved")
            try:
                current_rule_authority = _canonical_bytes(rule)
            except RuntimeFailure as exc:
                raise ArtifactFailure(
                    "application rule authority became malformed"
                ) from exc
            if current_rule_authority != exact_rule_authority.get(rule_id):
                raise ArtifactFailure(
                    "application rule authority changed during execution"
                )
            descriptors = rule["ordered_rule_input_bindings"]
            expected_names = [descriptor["binding_name"] for descriptor in descriptors]
            if list(bindings) != expected_names:
                raise ArtifactFailure("application binding order differs")
            if intrinsic_owner_type_name is None:
                effective = tuple(
                    (
                        descriptor["binding_name"],
                        descriptor["binding_kind"],
                        descriptor["expected_type_name"],
                        descriptor["expected_value_schema_id"],
                    )
                    for descriptor in descriptors
                )
                if (
                    rule_id != plan.rule_id
                    or rule["rule_scope"] != "CROSS_RECORD"
                    or effective != plan.effective_binding_ledger
                ):
                    raise ArtifactFailure("application cross-rule ledger differs")
            else:
                owner_descriptor = self.records.get(intrinsic_owner_type_name)
                if (
                    owner_descriptor is None
                    or rule_id not in owner_descriptor["ordered_intrinsic_rule_ids"]
                    or rule["rule_scope"] != "INTRINSIC_RECORD"
                    or len(descriptors) != 1
                    or descriptors[0]["binding_name"] != "self"
                    or descriptors[0]["binding_kind"] != "RECORD"
                    or descriptors[0]["expected_type_name"] != intrinsic_owner_type_name
                    or bindings["self"] is None
                ):
                    raise ArtifactFailure(
                        "application intrinsic-rule attachment differs"
                    )
            for descriptor in descriptors:
                self._assert_binding_type_contract(descriptor)
            evaluation_rule_stack = (rule_id,)
            nodes = rule["ordered_expression_nodes"]
            if len(nodes) != rule["maximum_expression_nodes"] or rule[
                "root_expression_position"
            ] != len(nodes):
                raise ArtifactFailure("application rule node boundary differs")
            results: dict[int, _ExpressionValue] = {}
            if rule["rule_scope"] == "INTRINSIC_RECORD":
                context.rule_counters.intrinsic_rule_invocations += 1
            context.rule_counters.total_expression_nodes += len(nodes)
            for expected_position, node in enumerate(nodes, start=1):
                position = node["expression_position"]
                if position != expected_position:
                    raise ArtifactFailure(
                        "application rule positions are not contiguous"
                    )
                try:
                    operands = [
                        results[operand_position]
                        for operand_position in node["ordered_operand_positions"]
                    ]
                except KeyError as exc:
                    raise ArtifactFailure(
                        "application rule operand is not earlier"
                    ) from exc
                value = self._execute_operator(
                    node,
                    operands,
                    bindings=bindings,
                    counters=context.rule_counters,
                    literal_rule_stack=evaluation_rule_stack,
                )
                result = _ExpressionValue(
                    value=value,
                    result_type_kind=node["result_type_kind"],
                    value_schema_id=node["result_value_schema_id"],
                )
                if node["operator"] != "INPUT_PATH":
                    self._validate_expression_result(node, result)
                results[position] = result
            root = results[rule["root_expression_position"]]
            if root.result_type_kind != "VALUE_SCHEMA" or type(root.value) is not bool:
                raise ArtifactFailure("application rule root is not Boolean")
            return root.value

        try:
            if type(ordered_root_inputs) is not tuple:
                raise TypeMismatch("application roots require an exact tuple")
            if type(ordered_external_sequences) is not tuple:
                raise TypeMismatch(
                    "application external sequences require an exact tuple"
                )
            if len(ordered_root_inputs) != len(plan.root_bindings):
                raise MalformedValue("application root count differs")
            if len(ordered_external_sequences) != len(plan.external_sequence_bindings):
                raise MalformedValue("application external sequence count differs")

            root_declared: list[tuple[_CompiledRootBinding, TypedValue]] = []
            for supplied, expected in zip(
                ordered_root_inputs,
                plan.root_bindings,
                strict=True,
            ):
                if type(supplied) is not ApplicationRecordInput:
                    raise TypeMismatch("application root envelope type differs")
                if (
                    type(supplied.binding_name) is not str
                    or supplied.binding_name != expected.binding_name
                ):
                    raise MalformedValue("application root binding order/name differs")
                declared = supplied.declared
                if (
                    type(declared) is not TypedValue
                    or declared.value_schema_id is not None
                    or declared.type_name != expected.expected_type_name
                ):
                    raise TypeMismatch("application root declared type differs")
                root_declared.append((expected, declared))

            sequence_declared: list[
                tuple[
                    _CompiledSequenceBinding,
                    tuple[TypedValue, ...],
                ]
            ] = []
            for supplied, expected in zip(
                ordered_external_sequences,
                plan.external_sequence_bindings,
                strict=True,
            ):
                if type(supplied) is not ApplicationSequenceInput:
                    raise TypeMismatch("application sequence envelope type differs")
                if (
                    type(supplied.binding_name) is not str
                    or supplied.binding_name != expected.binding_name
                ):
                    raise MalformedValue(
                        "application sequence binding order/name differs"
                    )
                records = supplied.ordered_records
                if type(records) is not tuple:
                    raise TypeMismatch(
                        "application sequence records require an exact tuple"
                    )
                if expected.resolver_id is None:
                    raise ArtifactFailure("external sequence resolver plan is absent")
                resolver = self.compiled_resolvers[expected.resolver_id]
                if not (
                    resolver.minimum_items <= len(records) <= resolver.maximum_items
                ):
                    raise UnresolvedReference(
                        "application sequence envelope cardinality differs"
                    )
                for declared in records:
                    if (
                        type(declared) is not TypedValue
                        or declared.value_schema_id is not None
                        or declared.type_name != expected.expected_item_type_name
                    ):
                        raise TypeMismatch(
                            "application sequence item declared type differs"
                        )
                sequence_declared.append((expected, records))

            # Phase 1: snapshot every accepted envelope before inspecting any
            # record graph semantically.
            root_snapshots: dict[str, dict[str, Any]] = {}
            root_snapshot_order: list[tuple[_CompiledRootBinding, dict[str, Any]]] = []
            for expected, declared in root_declared:
                snapshot, _canonical = self._snapshot_application_record(
                    declared.value,
                    type_name=expected.expected_type_name,
                    counters=context.counters,
                    path=("root", expected.binding_name),
                )
                root_snapshots[expected.binding_name] = snapshot
                root_snapshot_order.append((expected, snapshot))

            external_snapshots: dict[str, tuple[dict[str, Any], ...]] = {}
            external_snapshot_order: list[
                tuple[
                    _CompiledSequenceBinding,
                    tuple[dict[str, Any], ...],
                ]
            ] = []
            for expected, records in sequence_declared:
                snapshots = tuple(
                    self._snapshot_application_record(
                        declared.value,
                        type_name=expected.expected_item_type_name,
                        counters=context.counters,
                        path=("sequence", expected.binding_name, ordinal),
                    )[0]
                    for ordinal, declared in enumerate(records)
                )
                external_snapshots[expected.binding_name] = snapshots
                external_snapshot_order.append((expected, snapshots))

            # Drop every caller-owned envelope/value reference before semantic
            # validation.  Only the private plain snapshots survive Phase 1.
            ordered_root_inputs = ()
            ordered_external_sequences = ()
            root_declared.clear()
            sequence_declared.clear()
            supplied = None
            declared = None
            records = ()

            # Phase 2: structurally validate every complete graph.
            for expected, snapshot in root_snapshot_order:
                self._validate_application_record_graph(
                    expected.expected_type_name,
                    snapshot,
                    counters=context.counters,
                    path=("root", expected.binding_name),
                )
            for expected, snapshots in external_snapshot_order:
                for ordinal, snapshot in enumerate(snapshots):
                    self._validate_application_record_graph(
                        expected.expected_item_type_name,
                        snapshot,
                        counters=context.counters,
                        path=("sequence", expected.binding_name, ordinal),
                    )

            # Phase 3: execute attached intrinsic rules dependency-postorder
            # for every occurrence.  Cache lookup occurs only after children.
            for expected, snapshot in root_snapshot_order:
                self._walk_application_type_intrinsics(
                    expected.expected_type_name,
                    snapshot,
                    owner=None,
                    context=context,
                    execute_prevalidated=execute_prevalidated,
                    path=("root", expected.binding_name),
                )
            for expected, snapshots in external_snapshot_order:
                for ordinal, snapshot in enumerate(snapshots):
                    self._walk_application_type_intrinsics(
                        expected.expected_item_type_name,
                        snapshot,
                        owner=None,
                        context=context,
                        execute_prevalidated=execute_prevalidated,
                        path=("sequence", expected.binding_name, ordinal),
                    )

            # Phase 4: resolve all fixed-position sequences, then materialize
            # embedded sequences from the private root snapshots.
            materialized_sequences: dict[str, tuple[dict[str, Any], ...]] = {}
            for sequence in plan.external_sequence_bindings:
                materialized_sequences[sequence.binding_name] = (
                    self._resolve_application_fixed_sequence(
                        sequence,
                        root_snapshots,
                        external_snapshots[sequence.binding_name],
                        context=context,
                    )
                )
            for sequence in plan.sequence_bindings:
                if sequence.source_kind != "EMBEDDED_ARRAY":
                    continue
                embedded = self._resolve_path(
                    root_snapshots[sequence.source_root_binding_name],
                    list(sequence.embedded_array_typed_member_path),
                    path=("embedded", sequence.binding_name),
                )
                if type(embedded) is not list:
                    raise TypeMismatch("application embedded sequence is not an array")
                materialized_sequences[sequence.binding_name] = tuple(embedded)

            sequence_lengths = [
                len(materialized_sequences[sequence.binding_name])
                for sequence in plan.sequence_bindings
            ]
            if plan.requires_equal_cardinality and len(set(sequence_lengths)) != 1:
                raise ConstraintViolation(
                    "application iterated sequence cardinalities differ"
                )

            if plan.application_kind in {
                "ARRAY_EACH",
                "FOR_EACH_FIXED_POSITION_BINDING",
            }:
                evaluation_count = sequence_lengths[0]
            else:
                evaluation_count = 1
            if evaluation_count > plan.maximum_rule_evaluations:
                raise WorkBoundExceeded("application rule-evaluation maximum exceeded")

            # Phase 5: build the exact effective ledger and charge each
            # candidate before its predicate begins.
            for ordinal in range(evaluation_count):
                current_ordinal = (
                    ordinal
                    if plan.application_kind
                    in {
                        "ARRAY_EACH",
                        "FOR_EACH_FIXED_POSITION_BINDING",
                    }
                    else None
                )
                bindings: dict[str, Any] = {
                    root.binding_name: root_snapshots[root.binding_name]
                    for root in plan.root_bindings
                }
                for sequence in plan.sequence_bindings:
                    values = materialized_sequences[sequence.binding_name]
                    if sequence.binding_mode == "ITERATED_RECORD":
                        bindings[sequence.binding_name] = values[ordinal]
                    elif sequence.binding_mode == "COMPLETE_RECORD_SEQUENCE":
                        bindings[sequence.binding_name] = list(values)
                    elif sequence.binding_mode == "OPTIONAL_RECORD":
                        bindings[sequence.binding_name] = (
                            None if not values else values[0]
                        )
                    else:
                        raise ArtifactFailure("compiled sequence binding mode differs")
                if plan.iteration_ordinal_binding_name is not None:
                    bindings[plan.iteration_ordinal_binding_name] = ordinal
                if tuple(bindings) != tuple(
                    item[0] for item in plan.effective_binding_ledger
                ):
                    raise ArtifactFailure(
                        "application effective binding materialization differs"
                    )

                context.counters.charged_rule_evaluations += 1
                before_nodes = context.rule_counters.total_expression_nodes
                before_complex = context.rule_counters.complex_operator_invocations
                before_rows = context.rule_counters.complex_row_item_visits
                before_octets = context.rule_counters.complex_canonicalized_octets
                try:
                    root_value = execute_prevalidated(
                        plan.rule_id,
                        bindings,
                        None,
                    )
                except (ArtifactFailure, UnsupportedRule):
                    raise
                except RuntimeFailure as exc:
                    raise _ApplicationCandidateFailure(
                        exc,
                        rule_id=plan.rule_id,
                    ) from exc
                context.counters.completed_rule_evaluations += 1
                context.ordered_rule_steps.append(
                    ApplicationRuleStepEvidence(
                        iteration_ordinal=current_ordinal,
                        root_value=root_value,
                        direct_expression_nodes=len(
                            self.rules[plan.rule_id]["ordered_expression_nodes"]
                        ),
                        total_expression_nodes=(
                            context.rule_counters.total_expression_nodes - before_nodes
                        ),
                        complex_operator_invocations=(
                            context.rule_counters.complex_operator_invocations
                            - before_complex
                        ),
                        complex_row_item_visits=(
                            context.rule_counters.complex_row_item_visits - before_rows
                        ),
                        complex_canonicalized_octets=(
                            context.rule_counters.complex_canonicalized_octets
                            - before_octets
                        ),
                    )
                )
                if not root_value:
                    raise _ApplicationCandidateFailure(
                        BusinessRuleFalse(
                            f"application cross-rule root is false: {plan.rule_id}"
                        ),
                        rule_id=plan.rule_id,
                    )

            current_ordinal = None
            self._assert_authority_intact()
            return self._application_evidence(
                plan,
                context,
                accepted=True,
                coordinate=ApplicationFailureCoordinate(
                    application_name=plan.application_name,
                    rule_application_id=plan.rule_application_id,
                    rule_id=plan.rule_id,
                    iteration_ordinal=None,
                    failure_class=None,
                ),
            )
        except _ApplicationCandidateFailure as exc:
            return reject(exc.failure, rule_id=exc.rule_id)
        except (ArtifactFailure, UnsupportedRule):
            raise
        except RuntimeFailure as exc:
            current_ordinal = None
            return reject(exc, rule_id=plan.rule_id)

    def evaluate_rule(
        self,
        rule_id: str,
        bindings: dict[str, Any],
        *,
        require_true: bool = True,
    ) -> RuleEvaluationEvidence:
        """Evaluate one frozen rule exactly once in DAG position order."""

        self._assert_authority_intact()
        if type(rule_id) is not str:
            raise TypeMismatch("rule identifier requires exact text")
        if type(bindings) is not dict or any(
            type(name) is not str for name in bindings
        ):
            raise TypeMismatch("rule bindings require an exact text-keyed object")
        if type(require_true) is not bool:
            raise TypeMismatch("require_true requires an exact Boolean")
        counters = _RuleCounters()
        root = self._evaluate_rule(
            rule_id,
            bindings,
            counters=counters,
            literal_rule_stack=(),
        )
        if require_true and not root:
            raise BusinessRuleFalse(f"rule root is false: {rule_id}")
        return RuleEvaluationEvidence(
            rule_id=rule_id,
            root_value=root,
            direct_expression_nodes=len(
                self.rules[rule_id]["ordered_expression_nodes"]
            ),
            intrinsic_rule_invocations=counters.intrinsic_rule_invocations,
            total_expression_nodes=counters.total_expression_nodes,
            complex_operator_invocations=counters.complex_operator_invocations,
            complex_row_item_visits=counters.complex_row_item_visits,
            complex_canonicalized_octets=counters.complex_canonicalized_octets,
        )

    def _evaluate_rule(
        self,
        rule_id: str,
        bindings: dict[str, Any],
        *,
        counters: _RuleCounters,
        literal_rule_stack: tuple[str, ...],
    ) -> bool:
        rule = self.rules.get(rule_id)
        if rule is None:
            raise UnresolvedReference(f"rule is unresolved: {rule_id}")
        descriptors = rule["ordered_rule_input_bindings"]
        expected_names = [descriptor["binding_name"] for descriptor in descriptors]
        if set(bindings) != set(expected_names) or len(bindings) != len(expected_names):
            raise MalformedValue(f"rule binding names differ: {rule_id}")
        for descriptor in descriptors:
            name = descriptor["binding_name"]
            schema_id = descriptor["expected_value_schema_id"]
            self._validate_schema_runtime(schema_id, bindings[name])
            self._assert_binding_type_contract(descriptor)
        if rule_id in literal_rule_stack:
            raise ImpossibleState(
                f"composite literal rule dependency is cyclic: {rule_id}"
            )
        evaluation_rule_stack = (*literal_rule_stack, rule_id)
        nodes = rule["ordered_expression_nodes"]
        if len(nodes) != rule["maximum_expression_nodes"] or rule[
            "root_expression_position"
        ] != len(nodes):
            raise ImpossibleState(f"rule node boundary differs: {rule_id}")
        results: dict[int, _ExpressionValue] = {}
        if rule["rule_scope"] == "INTRINSIC_RECORD":
            counters.intrinsic_rule_invocations += 1
        counters.total_expression_nodes += len(nodes)
        for expected_position, node in enumerate(nodes, start=1):
            position = node["expression_position"]
            if position != expected_position:
                raise ImpossibleState(f"rule positions are not contiguous: {rule_id}")
            try:
                operands = [
                    results[operand_position]
                    for operand_position in node["ordered_operand_positions"]
                ]
            except KeyError as exc:
                raise ImpossibleState(
                    f"rule operand is not an earlier evaluated node: {rule_id}"
                ) from exc
            value = self._execute_operator(
                node,
                operands,
                bindings=bindings,
                counters=counters,
                literal_rule_stack=evaluation_rule_stack,
            )
            result = _ExpressionValue(
                value=value,
                result_type_kind=node["result_type_kind"],
                value_schema_id=node["result_value_schema_id"],
            )
            self._validate_expression_result(node, result)
            results[position] = result
        root = results[rule["root_expression_position"]]
        if root.result_type_kind != "VALUE_SCHEMA" or type(root.value) is not bool:
            raise ImpossibleState(f"rule root is not exact Boolean: {rule_id}")
        return root.value

    def _assert_binding_type_contract(self, descriptor: dict[str, Any]) -> None:
        schema = self.schemas[descriptor["expected_value_schema_id"]]
        kind = descriptor["binding_kind"]
        expected_type_name = descriptor["expected_type_name"]
        if kind == "RECORD":
            if (
                schema["schema_kind"] != "OBJECT_REF"
                or schema["nullable"] is not False
                or schema["referenced_type_name"] != expected_type_name
                or expected_type_name not in self.records
            ):
                raise ImpossibleState("record binding schema/type contract differs")
        elif kind == "OPTIONAL_FIXED_RECORD":
            if (
                schema["schema_kind"] != "OBJECT_REF"
                or schema["nullable"] is not True
                or schema["referenced_type_name"] != expected_type_name
                or expected_type_name not in self.records
            ):
                raise ImpossibleState(
                    "optional-record binding schema/type contract differs"
                )
        elif kind == "FIXED_RECORD_SEQUENCE":
            if schema["schema_kind"] != "ARRAY" or schema["nullable"] is not False:
                raise ImpossibleState("sequence binding schema/type contract differs")
            item = self.schemas[schema["array_item_value_schema_id"]]
            if (
                item["schema_kind"] != "OBJECT_REF"
                or item["nullable"] is not False
                or item["referenced_type_name"] != expected_type_name
                or expected_type_name not in self.records
            ):
                raise ImpossibleState("sequence binding schema/type contract differs")
        elif kind == "SAFE_UINT":
            if (
                schema["schema_kind"] != "SAFE_INTEGER"
                or schema["nullable"] is not False
                or expected_type_name is not None
            ):
                raise ImpossibleState("safe-uint binding schema/type contract differs")
        else:
            raise ImpossibleState(f"unknown binding kind: {kind}")

    def _execute_operator(
        self,
        node: dict[str, Any],
        operands: list[_ExpressionValue],
        *,
        bindings: dict[str, Any],
        counters: _RuleCounters,
        literal_rule_stack: tuple[str, ...],
    ) -> Any:
        operator = node["operator"]
        path = ("rule_node", node["expression_position"])
        if operator in COMPLEX_OPERATOR_NAMES:
            return self._execute_complex_operator(
                operator,
                operands,
                counters=counters,
                path=path,
            )
        if operator == "INPUT_PATH":
            binding_name = node["input_binding_name"]
            if binding_name not in bindings:
                _fail(
                    UnresolvedReference,
                    f"input binding is unresolved: {binding_name}",
                    path=path,
                )
            return self._resolve_path(
                bindings[binding_name],
                node["typed_member_path"],
                path=path,
            )
        if operator == "LITERAL":
            literal = copy.deepcopy(node["literal_value"])
            literal_schema_id = node["literal_value_schema_id"]
            if literal_schema_id != node["result_value_schema_id"]:
                _fail(
                    ImpossibleState,
                    "literal/result schema declarations differ",
                    path=path,
                )
            self._validate_rule_literal_schema(
                literal_schema_id,
                literal,
                counters=counters,
                literal_rule_stack=literal_rule_stack,
                path=path,
            )
            return literal
        if operator == "IS_NULL":
            return operands[0].value is None
        if operator == "NOT":
            return not self._boolean_operand(operands[0], path=path)
        if operator in {"AND", "OR", "IMPLIES"}:
            left = self._boolean_operand(operands[0], path=path)
            right = self._boolean_operand(operands[1], path=path)
            if operator == "AND":
                return left and right
            if operator == "OR":
                return left or right
            return (not left) or right
        if operator in {"EQ", "NE"}:
            self._require_same_expression_type(operands[0], operands[1], path=path)
            equal = self._expression_equal(operands[0], operands[1])
            return equal if operator == "EQ" else not equal
        if operator in {"LT", "LE", "GT", "GE"}:
            self._require_same_expression_type(operands[0], operands[1], path=path)
            left = operands[0].value
            right = operands[1].value
            if left is None or right is None or type(left) is not type(right):
                _fail(TypeMismatch, "ordered operands differ or are null", path=path)
            if type(left) not in {int, str}:
                _fail(TypeMismatch, "ordered operands are not scalar", path=path)
            if operator == "LT":
                return left < right
            if operator == "LE":
                return left <= right
            if operator == "GT":
                return left > right
            return left >= right
        if operator == "PRESENT_EQ":
            if operands[0].value is None:
                return False
            return self._raw_exact_equal(operands[0].value, operands[1].value)
        if operator == "PRESENT_LE":
            if operands[0].value is None or operands[1].value is None:
                return False
            left = operands[0].value
            right = operands[1].value
            if type(left) is not type(right) or type(left) not in {int, str}:
                _fail(TypeMismatch, "present ordered operands differ", path=path)
            return left <= right
        if operator in {
            "SAFE_ADD",
            "SAFE_MULTIPLY",
            "SAFE_FLOOR_DIVIDE",
            "SAFE_CEIL_DIVIDE",
        }:
            left = self._safe_uint_operand(operands[0], path=path)
            right = self._safe_uint_operand(operands[1], path=path)
            if operator == "SAFE_ADD":
                result = left + right
            elif operator == "SAFE_MULTIPLY":
                result = left * right
            elif right == 0:
                _fail(ConstraintViolation, "safe division by zero", path=path)
            elif operator == "SAFE_FLOOR_DIVIDE":
                result = left // right
            else:
                result = left // right + (left % right != 0)
            if result > SAFE_INTEGER_MAXIMUM:
                _fail(ConstraintViolation, "safe arithmetic overflow", path=path)
            return result
        if operator == "ARRAY_LENGTH":
            return len(self._array_operand(operands[0], path=path))
        if operator == "ARRAY_UNIQUE":
            values = self._array_operand(operands[0], path=path)
            seen: set[tuple[type[Any], bytes]] = set()
            for value in values:
                exact_key = (type(value), _canonical_bytes(value))
                if exact_key in seen:
                    return False
                seen.add(exact_key)
            return True
        if operator == "ARRAY_STRICT_ASCENDING":
            values = self._array_operand(operands[0], path=path)
            return all(
                type(left) is type(right) and type(left) in {int, str} and left < right
                for left, right in zip(values, values[1:])
            )
        if operator == "ARRAY_POSITIONAL_EQUAL":
            left = self._array_operand(operands[0], path=path)
            right = self._array_operand(operands[1], path=path)
            self._require_same_expression_type(operands[0], operands[1], path=path)
            return len(left) == len(right) and all(
                self._raw_exact_equal(left_item, right_item)
                for left_item, right_item in zip(left, right)
            )
        if operator == "ARRAY_PROJECT_REQUIRED_MEMBER":
            values = self._array_operand(operands[0], path=path)
            return [
                self._resolve_path(item, node["typed_member_path"], path=(*path, index))
                for index, item in enumerate(values)
            ]
        if operator == "ARRAY_CONTAINS":
            values = self._array_operand(operands[0], path=path)
            return any(
                self._raw_exact_equal(item, operands[1].value) for item in values
            )
        if operator == "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER":
            values = self._array_operand(operands[0], path=path)
            matches = [
                item
                for index, item in enumerate(values)
                if self._raw_exact_equal(
                    self._resolve_path(
                        item,
                        node["typed_member_path"],
                        path=(*path, index),
                    ),
                    operands[1].value,
                )
            ]
            if len(matches) != 1:
                _fail(
                    UnresolvedReference,
                    "array member lookup did not resolve exactly one object",
                    path=path,
                )
            return matches[0]
        if operator == "OBJECT_MEMBER":
            if type(operands[0].value) is not dict:
                _fail(TypeMismatch, "object-member operand is not an object", path=path)
            return self._resolve_path(
                operands[0].value,
                node["typed_member_path"],
                path=path,
            )
        if operator == "TIMESTAMP_TO_EPOCH_MICROSECONDS":
            return self._timestamp_to_epoch_microseconds(
                self._text_operand(operands[0], path=path),
                path=path,
            )
        if operator == "UINT128_PARSE":
            value = self._text_operand(operands[0], path=path)
            return _parse_uint128_decimal(value, path=path)
        if operator == "SAFE_UINT_TO_INTERNAL_UINT128":
            return self._safe_uint_operand(operands[0], path=path)
        if operator in {"UINT128_ADD", "UINT128_MULTIPLY"}:
            left = self._uint128_operand(operands[0], path=path)
            right = self._uint128_operand(operands[1], path=path)
            result = left + right if operator == "UINT128_ADD" else left * right
            if result > UINT128_MAXIMUM:
                _fail(ConstraintViolation, "uint128 arithmetic overflow", path=path)
            return result
        if operator == "BASE64_DECODE":
            return self._decode_canonical_base64(
                self._text_operand(operands[0], path=path),
                path=path,
            )
        if operator == "BASE64_ARRAY_DECODE_CONCAT":
            values = self._array_operand(operands[0], path=path)
            maximum = self._safe_uint_operand(operands[1], path=path)
            decoded_parts: list[bytes] = []
            decoded_octets = 0
            for index, value in enumerate(values):
                if type(value) is not str:
                    _fail(
                        TypeMismatch,
                        "base64 array item is not exact text",
                        path=(*path, index),
                    )
                part = self._decode_canonical_base64(value, path=(*path, index))
                decoded_octets += len(part)
                if decoded_octets > maximum:
                    _fail(
                        ConstraintViolation,
                        "decoded base64 aggregate exceeds supplied cap",
                        path=path,
                    )
                decoded_parts.append(part)
            return b"".join(decoded_parts)
        if operator == "INTERNAL_BYTES_LENGTH":
            value = self._bytes_operand(operands[0], path=path)
            if len(value) > SAFE_INTEGER_MAXIMUM:
                _fail(ConstraintViolation, "internal byte length overflows", path=path)
            return len(value)
        if operator == "SHA256_BYTES":
            return _sha256(self._bytes_operand(operands[0], path=path))
        if operator == "RAW_INGRESS_BATCH_ID_RECOMPUTES":
            chunks = self._array_operand(operands[0], path=path)
            supplied = self._text_operand(operands[1], path=path)
            expected = _sha256(
                _canonical_bytes(
                    {
                        "domain": ("RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"),
                        "ordered_chunks_base64": chunks,
                    }
                )
            )
            return supplied == expected
        if operator == "RFC6455_CLOSE_PAYLOAD_VALID":
            opcode = self._text_operand(operands[0], path=path)
            payload = self._bytes_operand(operands[1], path=path)
            return self._rfc6455_close_payload_valid(opcode, payload)
        if operator == "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX":
            layer = self._text_operand(operands[0], path=path)
            field_id = self._text_operand(operands[1], path=path)
            if field_id.count(".") != 1:
                return False
            prefix, _member = field_id.split(".", 1)
            try:
                prefix_ascii = prefix.encode("ascii", errors="strict")
                layer_ascii = layer.encode("ascii", errors="strict")
            except UnicodeEncodeError:
                return False
            return prefix_ascii.upper() == layer_ascii
        if operator == "SEMANTIC_ID_RECOMPUTES":
            record = operands[0].value
            supplied = self._text_operand(operands[1], path=path)
            descriptor = self._record_descriptor_for_expression(
                operands[0],
                path=path,
            )
            if type(record) is not dict:
                _fail(TypeMismatch, "semantic-ID operand is not a record", path=path)
            domain = descriptor["described_record_domain"]
            identity_order = descriptor["identity_payload_member_order"]
            if (
                descriptor["type_role"] != "STANDALONE"
                or type(domain) is not str
                or type(identity_order) is not list
            ):
                _fail(
                    TypeMismatch,
                    "semantic-ID operand is not a standalone record",
                    path=path,
                )
            expected = _semantic_id(
                domain,
                {name: record[name] for name in identity_order},
            )
            return supplied == expected
        if operator == "CANONICAL_BYTES_SATISFY_BOUND":
            descriptor = self._record_descriptor_for_expression(
                operands[0],
                path=path,
            )
            encoded_octets = len(_canonical_bytes(operands[0].value))
            relation = descriptor["codec_byte_bound_relation"]
            limit = descriptor["codec_octet_limit"]
            if relation == "LE":
                return encoded_octets <= limit
            if relation == "LT":
                return encoded_octets < limit
            _fail(ImpossibleState, "record codec relation is unknown", path=path)
        raise UnsupportedRule(f"generic operator is not implemented yet: {operator}")

    def _execute_complex_operator(
        self,
        operator: str,
        operands: list[_ExpressionValue],
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        arities = {
            "A1_FIFO_FIELDS_VALID": 2,
            "BITMAP_NULLABILITY_MATCHES": 2,
            "CHECKPOINT_SELECTOR_INTRINSIC_VALID": 1,
            "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED": 2,
            "FIELD_OBSERVATION_INTRINSIC_VALID": 1,
            "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY": 3,
            "OPERATION_RESULT_MATCHES_SIGNED_SPEC": 2,
            "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD": 1,
            "TARGET_VALUE_SATISFIES_DESCRIPTOR": 3,
            "V2_FIELD_OBSERVATION_CONTEXT_VALID": 5,
            "V2_ROOT_SEQUENCE_SELECTOR_VALID": 3,
        }
        expected_arity = arities.get(operator)
        if expected_arity is None:
            _fail(ImpossibleState, "complex operator dispatch is unknown", path=path)
        if len(operands) != expected_arity:
            _fail(
                ImpossibleState,
                f"complex operator arity differs: {operator}",
                path=path,
            )
        counters.complex_operator_invocations += 1
        values = [operand.value for operand in operands]
        if operator == "BITMAP_NULLABILITY_MATCHES":
            return self._bitmap_nullability_matches(
                values[0],
                values[1],
                counters=counters,
                path=path,
            )
        if operator == "CHECKPOINT_SELECTOR_INTRINSIC_VALID":
            return self._checkpoint_selector_intrinsic_valid(
                values[0],
                counters=counters,
                path=path,
            )
        if operator == "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED":
            return self._checkpoint_selector_marker_contract_admitted(
                values[0],
                values[1],
                counters=counters,
                path=path,
            )
        if operator == "FIELD_OBSERVATION_INTRINSIC_VALID":
            return self._field_observation_intrinsic_valid(
                values[0],
                counters=counters,
                path=path,
            )
        if operator == "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD":
            return self._source_error_detail_id_recomputes_from_field(
                values[0],
                counters=counters,
                path=path,
            )
        if operator == "OPERATION_RESULT_MATCHES_SIGNED_SPEC":
            return self._operation_result_matches_signed_spec(
                values[0],
                values[1],
                counters=counters,
                path=path,
            )
        if operator == "TARGET_VALUE_SATISFIES_DESCRIPTOR":
            return self._target_value_satisfies_descriptor(
                values[0],
                values[1],
                values[2],
                counters=counters,
                path=path,
            )
        if operator == "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY":
            return self._field_observation_satisfies_descriptor_policy(
                values[0],
                values[1],
                values[2],
                counters=counters,
                path=path,
            )
        if operator == "V2_FIELD_OBSERVATION_CONTEXT_VALID":
            return self._v2_field_observation_context_valid(
                values[0],
                values[1],
                values[2],
                values[3],
                values[4],
                counters=counters,
                path=path,
            )
        if operator == "A1_FIFO_FIELDS_VALID":
            return self._a1_fifo_fields_valid(
                values[0],
                values[1],
                counters=counters,
                path=path,
            )
        if operator == "V2_ROOT_SEQUENCE_SELECTOR_VALID":
            return self._v2_root_sequence_selector_valid(
                values[0],
                values[1],
                values[2],
                counters=counters,
                path=path,
            )
        _fail(ImpossibleState, "complex operator dispatch fell through", path=path)

    def _bitmap_nullability_matches(
        self,
        bitmap: Any,
        values: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(bitmap) is not str or type(values) is not list:
            _fail(TypeMismatch, "bitmap operator operands have wrong types", path=path)
        if len(bitmap) != 66 or len(values) != 66:
            return False
        for ordinal, (bit, value) in enumerate(zip(bitmap, values)):
            self._complex_visit(counters)
            if bit not in {"0", "1"}:
                _fail(
                    TypeMismatch,
                    "bitmap contains a non-binary symbol",
                    path=(*path, ordinal),
                )
            if (bit == "1") != (value is not None):
                return False
        return True

    def _checkpoint_selector_intrinsic_valid(
        self,
        selector: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(selector) is not dict:
            _fail(TypeMismatch, "selector operand is not an object", path=path)
        try:
            operation = selector["operation_kind"]
            entries = selector["ordered_entries"]
            declared_length = selector["selector_length"]
            declared_ids = selector["ordered_checkpoint_selector_entry_ids"]
        except KeyError as exc:
            raise MalformedValue("selector lacks a required member", path=path) from exc
        if type(entries) is not list or type(declared_ids) is not list:
            _fail(TypeMismatch, "selector arrays have wrong types", path=path)
        if len(entries) > 64 or len(declared_ids) > 64:
            _fail(TypeMismatch, "selector exceeds the frozen length", path=path)
        order = SELECTOR_MARKER_ORDER_BY_OPERATION.get(operation)
        if order is None:
            _fail(
                UnresolvedReference,
                "selector operation has no frozen rank row",
                path=path,
            )
        rank_by_marker = {marker: rank for rank, marker in enumerate(order)}
        last_rank = -1
        last_occurrence_by_marker: dict[str, int] = {}
        coordinates: set[tuple[str, int]] = set()
        recomputed_ids: list[str] = []
        for ordinal, entry in enumerate(entries, start=1):
            self._complex_visit(counters)
            if type(entry) is not dict:
                _fail(
                    TypeMismatch,
                    "selector entry is not an object",
                    path=(*path, "ordered_entries", ordinal - 1),
                )
            try:
                position = entry["selector_position"]
                entry_operation = entry["operation_kind"]
                marker = entry["checkpoint_marker_kind"]
                occurrence = entry["occurrence_index_within_kind"]
            except KeyError as exc:
                raise MalformedValue(
                    "selector entry lacks a required member",
                    path=(*path, "ordered_entries", ordinal - 1),
                ) from exc
            if (
                type(position) is not int
                or type(occurrence) is not int
                or type(marker) is not str
                or type(entry_operation) is not str
            ):
                _fail(
                    TypeMismatch,
                    "selector entry scalar type differs",
                    path=(*path, "ordered_entries", ordinal - 1),
                )
            if position != ordinal or entry_operation != operation:
                return False
            rank = rank_by_marker.get(marker)
            if rank is None:
                return False
            if rank < last_rank:
                return False
            last_rank = rank
            coordinate = (marker, occurrence)
            if coordinate in coordinates:
                return False
            coordinates.add(coordinate)
            previous = last_occurrence_by_marker.get(marker, 0)
            if occurrence <= previous:
                return False
            last_occurrence_by_marker[marker] = occurrence
            recomputed_ids.append(
                self._complex_record_identity(
                    "CheckpointSelectorEntryV1",
                    entry,
                    counters=counters,
                    path=(*path, "ordered_entries", ordinal - 1),
                )
            )
        return (
            type(declared_length) is int
            and declared_length == len(entries)
            and declared_ids == recomputed_ids
        )

    def _checkpoint_selector_marker_contract_admitted(
        self,
        selector: Any,
        marker_contract: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(selector) is not dict or type(marker_contract) is not dict:
            _fail(
                TypeMismatch,
                "selector/marker-contract operands require objects",
                path=path,
            )
        try:
            records = marker_contract["ordered_checkpoint_operation_records"]
            full_markers = marker_contract["ordered_full_checkpoint_marker_kinds"]
            forbidden = marker_contract["forbidden_full_checkpoint_marker_kinds"]
            maximum = marker_contract["maximum_checkpoint_selector_length"]
            entries = selector["ordered_entries"]
            selector_length = selector["selector_length"]
            operation = selector["operation_kind"]
        except KeyError as exc:
            raise MalformedValue(
                "selector marker authority lacks a required member",
                path=path,
            ) from exc
        record_index = self._index_supplied_records(
            records,
            "checkpoint_marker_kind",
            expected_count=13,
            counters=counters,
            path=(*path, "ordered_checkpoint_operation_records"),
        )
        if (
            type(full_markers) is not list
            or type(forbidden) is not list
            or type(entries) is not list
            or type(maximum) is not int
            or type(selector_length) is not int
        ):
            _fail(TypeMismatch, "marker contract member type differs", path=path)
        self._complex_visit(counters, len(full_markers) + len(forbidden))
        if (
            len(full_markers) != 13
            or len(set(full_markers)) != 13
            or set(full_markers) != set(record_index)
            or set(full_markers) & set(forbidden)
        ):
            _fail(
                UnresolvedReference,
                "supplied marker contract is internally inconsistent",
                path=path,
            )
        if selector_length > maximum:
            return False
        for ordinal, entry in enumerate(entries):
            self._complex_visit(counters)
            if type(entry) is not dict:
                _fail(TypeMismatch, "selector entry is not an object", path=path)
            marker = entry.get("checkpoint_marker_kind")
            record = record_index.get(marker)
            if record is None:
                _fail(
                    UnresolvedReference,
                    "selector marker has no contract authority row",
                    path=(*path, ordinal),
                )
            applicable = record.get("applicable_operation_kinds")
            if type(applicable) is not list or not applicable:
                _fail(
                    UnresolvedReference,
                    "marker contract operation row is inconsistent",
                    path=(*path, ordinal),
                )
            self._complex_visit(counters, len(applicable))
            if operation not in applicable:
                return False
        return True

    def _field_observation_intrinsic_valid(
        self,
        field: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        del counters
        if type(field) is not dict:
            _fail(TypeMismatch, "field observation is not an object", path=path)
        try:
            availability = field["availability"]
            value = field["value"]
            method = field["observation_method"]
            attempt = field["observation_attempt"]
            span_status = field["adapter_span_status"]
            started = field["observation_started_offset_nanoseconds"]
            completed = field["observation_completed_offset_nanoseconds"]
            reason = field["unavailable_reason"]
            censoring = field["censoring"]
            errno_number = field["source_errno_number"]
            errno_name = field["source_errno_name"]
            failure_phase = field["source_failure_phase"]
            error_class = field["source_error_class"]
            error_digest = field["source_error_detail_sha256"]
        except KeyError as exc:
            raise MalformedValue(
                "field observation lacks a required member",
                path=path,
            ) from exc
        span_valid = (
            span_status == "AVAILABLE"
            and type(started) is int
            and type(completed) is int
            and started <= completed
        ) or (span_status != "AVAILABLE" and started is None and completed is None)
        if not span_valid:
            return False
        if (errno_number is None) != (errno_name is None):
            return False
        if (error_class is None) != (error_digest is None):
            return False
        source_members_absent = (
            errno_number is None
            and errno_name is None
            and error_class is None
            and error_digest is None
        )
        attempted_method_valid = (
            attempt == "ATTEMPTED" and method != "NOT_ATTEMPTED"
        ) or (attempt == "NOT_ATTEMPTED" and method == "NOT_ATTEMPTED")
        if not attempted_method_valid:
            return False
        if availability in {"AVAILABLE", "CENSORED"}:
            if (
                value is None
                or attempt != "ATTEMPTED"
                or method == "NOT_ATTEMPTED"
                or span_status != "AVAILABLE"
                or reason is not None
                or failure_phase != "NONE"
                or not source_members_absent
            ):
                return False
            if availability == "AVAILABLE":
                return censoring == "NONE" and (
                    type(value) is not dict
                    or value.get("kind") != "DURATION_BOUND"
                    or value.get("relation") == "EXACT"
                )
            relation_by_censoring = {
                "LEFT": "UPPER_BOUND",
                "RIGHT": "LOWER_BOUND",
                "INTERVAL": "INTERVAL",
            }
            return (
                type(value) is dict
                and value.get("kind") == "DURATION_BOUND"
                and censoring in relation_by_censoring
                and value.get("relation") == relation_by_censoring[censoring]
            )
        if availability == "NOT_APPLICABLE":
            return (
                value is None
                and reason
                in {
                    "NOT_APPLICABLE_TO_OPERATION",
                    "NOT_APPLICABLE_TO_REACHED_STATE",
                }
                and method == "NOT_ATTEMPTED"
                and attempt == "NOT_ATTEMPTED"
                and span_status == "NOT_APPLICABLE"
                and censoring == "NONE"
                and failure_phase == "NONE"
                and source_members_absent
            )
        if availability == "UNAVAILABLE":
            return value is None and reason is not None and censoring == "NONE"
        return False

    def _source_error_detail_id_recomputes_from_field(
        self,
        field: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(field) is not dict:
            _fail(TypeMismatch, "field observation is not an object", path=path)
        try:
            error_class = field["source_error_class"]
            supplied = field["source_error_detail_sha256"]
        except KeyError as exc:
            raise MalformedValue(
                "field source-error members are absent",
                path=path,
            ) from exc
        if error_class is None:
            return supplied is None
        payload = {
            "field_id": field["field_id"],
            "observation_method": field["observation_method"],
            "source_failure_phase": field["source_failure_phase"],
            "source_errno_number": field["source_errno_number"],
            "source_errno_name": field["source_errno_name"],
            "source_error_class": error_class,
        }
        octets_before = counters.complex_canonicalized_octets
        expected = self._complex_semantic_id(
            SOURCE_ERROR_DETAIL_DOMAIN,
            payload,
            counters=counters,
            path=path,
        )
        preimage_octets = counters.complex_canonicalized_octets - octets_before
        if preimage_octets > SOURCE_ERROR_DETAIL_CANONICAL_OCTET_LIMIT:
            _fail(
                ImpossibleState,
                "source-error preimage exceeds the frozen codec ceiling",
                path=path,
            )
        return supplied == expected

    def _operation_result_matches_signed_spec(
        self,
        result: Any,
        signed_spec: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(result) is not dict or type(signed_spec) is not dict:
            _fail(TypeMismatch, "result/spec operands require objects", path=path)
        result_kind = result.get("operation_kind")
        spec_kind = signed_spec.get("operation_kind")
        if type(result_kind) is not str or type(spec_kind) is not str:
            _fail(TypeMismatch, "result/spec operation kind is not text", path=path)
        if result_kind != spec_kind:
            return False
        matrix = OPERATION_UNION_MATRIX.get(result_kind)
        if matrix is None:
            _fail(
                UnresolvedReference,
                "result/spec operation kind has no frozen matrix",
                path=path,
            )
        spec_alternative, spec_descriptor, spec_body = self._selected_union_record(
            "CapacityMeasurementOperationSpecBody",
            signed_spec.get("spec"),
            owner_type_name="CapacityMeasurementOperationSpec",
            owner_value=signed_spec,
            counters=counters,
            path=(*path, "spec"),
        )
        result_alternative, result_descriptor, result_body = (
            self._selected_union_record(
                "CapacityMeasurementOperationResultBody",
                result.get("result"),
                owner_type_name="CapacityMeasurementOperationResultEvidence",
                owner_value=result,
                counters=counters,
                path=(*path, "result"),
            )
        )
        (
            expected_spec_tag,
            expected_spec_type,
            expected_result_tag,
            expected_result_type,
        ) = matrix
        if (
            spec_alternative["alternative_name"] != expected_spec_tag
            or spec_descriptor["type_name"] != expected_spec_type
            or result_alternative["alternative_name"] != expected_result_tag
            or result_descriptor["type_name"] != expected_result_type
        ):
            _fail(
                UnresolvedReference,
                "result/spec union branch differs from the frozen matrix",
                path=path,
            )
        if result_kind == "SUBSCRIPTION_DISPATCH":
            comparisons = (
                (
                    result_body["generated_logical_opcode"],
                    spec_body["expected_logical_opcode"],
                ),
                (
                    result_body["local_dispatch_disposition"],
                    spec_body["expected_dispatch_disposition"],
                ),
            )
            self._complex_visit(counters, len(comparisons))
            return all(left == right for left, right in comparisons)
        if result_kind == "INGRESS":
            comparisons = (
                (
                    result_body["observed_consumed_new_input_octets"],
                    spec_body["input_octet_count"],
                ),
                (
                    result_body["observed_parser_unit_count"],
                    spec_body["expected_parser_unit_count"],
                ),
                (
                    result_body["observed_completed_application_message_count"],
                    spec_body["expected_completed_application_message_count"],
                ),
                (
                    result_body["observed_logical_output_frame_count"],
                    spec_body["expected_logical_output_frame_count"],
                ),
                (
                    result_body["observed_logical_output_payload_octets"],
                    spec_body["expected_logical_output_payload_octets"],
                ),
                (
                    result_body["observed_logical_output_frames_sha256"],
                    spec_body["expected_logical_output_frames_sha256"],
                ),
            )
            self._complex_visit(counters, len(comparisons))
            return all(left == right for left, right in comparisons)
        if result_kind == "ACK_DEADLINE_EXPIRY":
            due_clock = result_body.get("due_decision_clock_evidence")
            if type(due_clock) is not dict:
                _fail(
                    TypeMismatch,
                    "ACK result due-clock evidence is not an object",
                    path=path,
                )
            self._complex_visit(counters, 2)
            return (
                due_clock.get("outbound_subscription_intent_id")
                == spec_body["expected_outbound_subscription_intent_id"]
                and due_clock.get("due_scenario") == spec_body["due_scenario"]
            )
        if result_kind == "LOCAL_SHUTDOWN":
            if (
                result_body["terminal_outcome"]
                != spec_body["expected_terminal_outcome"]
            ):
                return False
            limit_pairs = (
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
            for result_member, spec_member in limit_pairs:
                self._complex_visit(counters)
                if result_body[result_member] > spec_body[spec_member]:
                    return False
            self._complex_visit(counters, 2)
            return (
                len(result_body["ordered_terminal_ingress_read_attempt_event_ids"])
                <= spec_body["maximum_terminal_ingress_batches"]
                and len(result_body["ordered_terminal_parser_transition_event_ids"])
                <= spec_body["maximum_terminal_ingress_parser_units"]
            )
        _fail(ImpossibleState, "result/spec matrix branch fell through", path=path)

    def _resolve_field_descriptor_authority(
        self,
        field: Any,
        descriptor: Any,
        registry: Any,
        indexes: _TargetRegistryIndexes,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> dict[str, Any]:
        if (
            type(field) is not dict
            or type(descriptor) is not dict
            or type(registry) is not dict
        ):
            _fail(
                TypeMismatch,
                "field/descriptor/registry authority requires objects",
                path=path,
            )
        field_id = field.get("field_id")
        if type(field_id) is not str:
            _fail(TypeMismatch, "field identifier is not text", path=path)
        resolved = indexes.descriptors.get(field_id)
        if resolved is None:
            _fail(
                UnresolvedReference,
                "field descriptor is unresolved in supplied registry",
                path=path,
            )
        if not self._complex_exact_equal(
            resolved,
            descriptor,
            counters=counters,
            path=(*path, "descriptor"),
        ):
            _fail(
                UnresolvedReference,
                "explicit descriptor differs from supplied registry authority",
                path=path,
            )
        if field.get("target_field_registry_id") != indexes.recomputed_registry_id:
            _fail(
                UnresolvedReference,
                "field observation names a different target registry",
                path=path,
            )
        return resolved

    def _resolved_vocabulary_members(
        self,
        vocabulary_id: Any,
        indexes: _TargetRegistryIndexes,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> list[str]:
        if type(vocabulary_id) is not str:
            _fail(
                UnresolvedReference,
                "constraint vocabulary identifier is absent",
                path=path,
            )
        vocabulary = indexes.vocabularies.get(vocabulary_id)
        if vocabulary is None:
            _fail(
                UnresolvedReference,
                "constraint vocabulary is unresolved",
                path=path,
            )
        members = vocabulary.get("members")
        if (
            type(members) is not list
            or len(members) > 32
            or any(type(member) is not str for member in members)
            or len(set(members)) != len(members)
        ):
            _fail(
                UnresolvedReference,
                "constraint vocabulary members are inconsistent",
                path=path,
            )
        self._complex_visit(counters, len(members))
        return members

    def _scalar_constraint_valid(
        self,
        value: Any,
        constraint: dict[str, Any],
        indexes: _TargetRegistryIndexes,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        profile = constraint.get("scalar_profile")
        kind = constraint.get("value_kind")
        if profile == "EXACT_BOOL":
            if kind != "BOOL":
                _fail(
                    UnresolvedReference,
                    "Boolean constraint has a wrong value kind",
                    path=path,
                )
            return type(value) is bool
        if profile == "SAFE_IJSON_UINT":
            if kind not in {"UINT", "OPTIONAL_UINT"}:
                _fail(
                    UnresolvedReference,
                    "integer constraint has a wrong value kind",
                    path=path,
                )
            minimum = constraint.get("integer_minimum")
            maximum = constraint.get("integer_maximum")
            if type(minimum) is not int or type(maximum) is not int:
                _fail(
                    UnresolvedReference,
                    "integer constraint bounds are unresolved",
                    path=path,
                )
            return type(value) is int and minimum <= value <= maximum
        if profile in {"ENUM", "PLATFORM_ERRNO", "SHA256", "UINT128_DECIMAL"}:
            if kind not in {"TEXT", "OPTIONAL_TEXT"}:
                _fail(
                    UnresolvedReference,
                    "text constraint has a wrong value kind",
                    path=path,
                )
            if type(value) is not str:
                return False
            encoded_length = len(value.encode("utf-8"))
            minimum = constraint.get("text_minimum_utf8_bytes")
            maximum = constraint.get("text_maximum_utf8_bytes")
            if (
                type(minimum) is not int
                or type(maximum) is not int
                or not minimum <= encoded_length <= maximum
            ):
                return False
            if profile == "ENUM":
                return value in self._resolved_vocabulary_members(
                    constraint.get("vocabulary_id"),
                    indexes,
                    counters=counters,
                    path=path,
                )
            pattern = constraint.get("text_ascii_pattern")
            if type(pattern) is not str:
                _fail(
                    UnresolvedReference,
                    "text constraint pattern is unresolved",
                    path=path,
                )
            try:
                pattern_matches = (
                    re.fullmatch(pattern, value, flags=re.ASCII) is not None
                )
            except re.error as exc:
                raise UnresolvedReference(
                    "text constraint pattern is malformed",
                    path=path,
                ) from exc
            if not pattern_matches:
                return False
            if profile == "UINT128_DECIMAL":
                decimal_maximum = constraint.get("decimal_maximum")
                if type(decimal_maximum) is not str:
                    _fail(
                        UnresolvedReference,
                        "uint128 constraint maximum is unresolved",
                        path=path,
                    )
                return len(value) < len(decimal_maximum) or (
                    len(value) == len(decimal_maximum) and value <= decimal_maximum
                )
            return True
        _fail(
            UnresolvedReference,
            f"scalar constraint profile is not closed: {profile}",
            path=path,
        )

    def _target_value_satisfies_descriptor(
        self,
        field: Any,
        descriptor: Any,
        registry: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        indexes = self._build_target_registry_indexes(
            registry,
            counters=counters,
            path=(*path, "registry"),
        )
        resolved_descriptor = self._resolve_field_descriptor_authority(
            field,
            descriptor,
            registry,
            indexes,
            counters=counters,
            path=path,
        )
        value = field.get("value")
        if value is None:
            return True
        alternative, _value_descriptor, payload = self._selected_union_record(
            "CapacityMeasurementTargetValue",
            value,
            owner_type_name=None,
            owner_value=None,
            counters=counters,
            path=(*path, "value"),
        )
        expected_kind = resolved_descriptor.get("value_kind")
        if alternative["alternative_name"] != expected_kind:
            _fail(
                TypeMismatch,
                "target value union alternative differs from descriptor kind",
                path=path,
            )
        constraint_id = resolved_descriptor.get("value_constraint_id")
        constraint = indexes.constraints.get(constraint_id)
        if constraint is None:
            _fail(
                UnresolvedReference,
                "target value constraint is unresolved",
                path=path,
            )
        if constraint.get("value_kind") != expected_kind:
            _fail(
                UnresolvedReference,
                "target value constraint kind differs from descriptor",
                path=path,
            )
        shape_id = resolved_descriptor.get("value_shape_id")
        shape = indexes.shapes.get(shape_id)
        if shape is None:
            _fail(
                UnresolvedReference,
                "target value shape is unresolved",
                path=path,
            )
        collection_kinds = {"UINT_LIST", "TEXT_LIST", "FIXED_UINT_MAP"}
        expected_container = (
            "FIXED_MAP"
            if expected_kind == "FIXED_UINT_MAP"
            else "LIST"
            if expected_kind in {"UINT_LIST", "TEXT_LIST"}
            else "SCALAR"
        )
        if shape.get("container_kind") != expected_container:
            _fail(
                UnresolvedReference,
                "target value shape container differs from value kind",
                path=path,
            )
        item_constraint_id = constraint.get("collection_item_constraint_id")
        if expected_kind in collection_kinds:
            if type(item_constraint_id) is not str:
                _fail(
                    UnresolvedReference,
                    "collection item constraint is unresolved",
                    path=path,
                )
            item_constraint = indexes.constraints.get(item_constraint_id)
            if item_constraint is None:
                _fail(
                    UnresolvedReference,
                    "collection item constraint is missing",
                    path=path,
                )
            if (
                item_constraint_id == constraint_id
                or item_constraint.get("collection_item_constraint_id") is not None
            ):
                _fail(
                    UnresolvedReference,
                    "collection item constraint is cyclic or nested",
                    path=path,
                )
            expected_item_kind = "TEXT" if expected_kind == "TEXT_LIST" else "UINT"
            if item_constraint.get("value_kind") != expected_item_kind:
                _fail(
                    UnresolvedReference,
                    "collection item constraint kind differs",
                    path=path,
                )
        else:
            if item_constraint_id is not None:
                _fail(
                    UnresolvedReference,
                    "scalar constraint unexpectedly names an item constraint",
                    path=path,
                )
            item_constraint = None

        if expected_kind == "DURATION_BOUND":
            if constraint.get("scalar_profile") != "DURATION_BOUND":
                _fail(
                    UnresolvedReference,
                    "duration constraint profile differs",
                    path=path,
                )
            relation = payload.get("relation")
            lower = payload.get("lower_nanoseconds")
            upper = payload.get("upper_nanoseconds")
            relation_valid = {
                "EXACT": (type(lower) is int and type(upper) is int and lower == upper),
                "LOWER_BOUND": type(lower) is int and upper is None,
                "UPPER_BOUND": lower is None and type(upper) is int,
                "INTERVAL": (
                    type(lower) is int and type(upper) is int and lower <= upper
                ),
            }.get(relation, False)
            if not relation_valid:
                return False
            minimum = constraint.get("integer_minimum")
            maximum = constraint.get("integer_maximum")
            if type(minimum) is not int or type(maximum) is not int:
                _fail(
                    UnresolvedReference,
                    "duration constraint bounds are unresolved",
                    path=path,
                )
            return all(
                endpoint is None
                or (type(endpoint) is int and minimum <= endpoint <= maximum)
                for endpoint in (lower, upper)
            )
        if expected_kind == "BOOL":
            return self._scalar_constraint_valid(
                payload.get("value"),
                constraint,
                indexes,
                counters=counters,
                path=path,
            )
        if expected_kind in {"UINT", "TEXT"}:
            return self._scalar_constraint_valid(
                payload.get("value"),
                constraint,
                indexes,
                counters=counters,
                path=path,
            )
        if expected_kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
            present = payload.get("present")
            scalar = payload.get("value")
            if type(present) is not bool or present != (scalar is not None):
                return False
            if scalar is None:
                return True
            return self._scalar_constraint_valid(
                scalar,
                constraint,
                indexes,
                counters=counters,
                path=path,
            )
        if expected_kind in {"UINT_LIST", "TEXT_LIST"}:
            values = payload.get("values")
            if type(values) is not list:
                _fail(TypeMismatch, "target list payload is not an array", path=path)
            minimum_items = shape.get("minimum_items")
            maximum_items = shape.get("maximum_items")
            if type(minimum_items) is not int or type(maximum_items) is not int:
                _fail(
                    UnresolvedReference,
                    "target list shape bounds are unresolved",
                    path=path,
                )
            if not minimum_items <= len(values) <= maximum_items:
                return False
            assert item_constraint is not None
            for ordinal, item in enumerate(values):
                self._complex_visit(counters)
                if not self._scalar_constraint_valid(
                    item,
                    item_constraint,
                    indexes,
                    counters=counters,
                    path=(*path, ordinal),
                ):
                    return False
            return True
        if expected_kind == "FIXED_UINT_MAP":
            ordered = payload.get("ordered")
            if type(ordered) is not list:
                _fail(TypeMismatch, "fixed-map payload is not an array", path=path)
            expected_keys = resolved_descriptor.get("value_shape_keys")
            shape_keys = shape.get("ordered_keys")
            if (
                type(expected_keys) is not list
                or type(shape_keys) is not list
                or expected_keys != shape_keys
            ):
                _fail(
                    UnresolvedReference,
                    "fixed-map descriptor/shape keys differ",
                    path=path,
                )
            minimum_items = shape.get("minimum_items")
            maximum_items = shape.get("maximum_items")
            if type(minimum_items) is not int or type(maximum_items) is not int:
                _fail(
                    UnresolvedReference,
                    "fixed-map shape bounds are unresolved",
                    path=path,
                )
            if not minimum_items <= len(ordered) <= maximum_items:
                return False
            actual_keys: list[str] = []
            assert item_constraint is not None
            for ordinal, entry in enumerate(ordered):
                self._complex_visit(counters)
                if type(entry) is not dict:
                    _fail(
                        TypeMismatch,
                        "fixed-map entry is not an object",
                        path=(*path, ordinal),
                    )
                actual_keys.append(entry.get("key"))
                if not self._scalar_constraint_valid(
                    entry.get("value"),
                    item_constraint,
                    indexes,
                    counters=counters,
                    path=(*path, ordinal),
                ):
                    return False
            return actual_keys == expected_keys
        _fail(
            UnresolvedReference,
            f"target value kind is not closed: {expected_kind}",
            path=path,
        )

    def _field_observation_satisfies_descriptor_policy(
        self,
        field: Any,
        descriptor: Any,
        registry: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        indexes = self._build_target_registry_indexes(
            registry,
            counters=counters,
            path=(*path, "registry"),
        )
        resolved_descriptor = self._resolve_field_descriptor_authority(
            field,
            descriptor,
            registry,
            indexes,
            counters=counters,
            path=path,
        )
        status_policy = registry.get("status_reason_policy_definition")
        if type(status_policy) is not dict:
            _fail(
                UnresolvedReference,
                "status-reason policy is unresolved",
                path=path,
            )
        if resolved_descriptor.get("status_reason_policy_id") != status_policy.get(
            "status_reason_policy_id"
        ):
            _fail(
                UnresolvedReference,
                "descriptor status-policy authority differs",
                path=path,
            )
        reason = field.get("unavailable_reason")
        allowed_reasons = resolved_descriptor.get("allowed_status_reasons")
        if type(allowed_reasons) is not list:
            _fail(
                UnresolvedReference,
                "descriptor allowed-reason authority is malformed",
                path=path,
            )
        self._complex_visit(counters, len(allowed_reasons))
        if reason is not None and reason not in allowed_reasons:
            return False
        if (
            field.get("availability") == "CENSORED"
            and resolved_descriptor.get("censoring_allowed") is not True
        ):
            return False
        if reason is None:
            return True
        reason_rule = indexes.reasons.get(reason)
        if reason_rule is None:
            _fail(
                UnresolvedReference,
                "field reason has no supplied policy row",
                path=path,
            )
        if reason_rule.get("required_availability") != field.get("availability"):
            return False
        attempt_rows = reason_rule.get("attempt_state_error_forms")
        if type(attempt_rows) is not list or not 1 <= len(attempt_rows) <= 2:
            _fail(
                UnresolvedReference,
                "reason attempt-state authority is malformed",
                path=path,
            )
        matching_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(attempt_rows):
            self._complex_visit(counters)
            if type(row) is not dict:
                _fail(
                    UnresolvedReference,
                    "reason attempt-state row is malformed",
                    path=(*path, ordinal),
                )
            if row.get("attempt_state") == field.get("observation_attempt"):
                matching_rows.append(row)
        if len(matching_rows) != 1:
            _fail(
                UnresolvedReference,
                "reason attempt state does not resolve exactly once",
                path=path,
            )
        row = matching_rows[0]
        required_span = {
            "AVAILABLE_ONLY": "AVAILABLE",
            "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
            "UNAVAILABLE_ONLY": "UNAVAILABLE",
        }.get(row.get("adapter_span_policy"))
        if required_span is None:
            _fail(
                UnresolvedReference,
                "reason adapter-span policy is unresolved",
                path=path,
            )
        if field.get("adapter_span_status") != required_span:
            return False
        phases = row.get("permitted_failure_phases")
        forms = row.get("permitted_error_forms")
        if type(phases) is not list or type(forms) is not list:
            _fail(
                UnresolvedReference,
                "reason failure/error-form authority is malformed",
                path=path,
            )
        self._complex_visit(counters, len(phases) + len(forms))
        if field.get("source_failure_phase") not in phases:
            return False
        if field.get("source_errno_number") is not None:
            effective_form = "OS"
        elif field.get("source_error_class") is not None:
            effective_form = "NON_OS"
        elif "STATUS_ONLY" in forms:
            effective_form = "STATUS_ONLY"
        else:
            effective_form = "NONE"
        return effective_form in forms

    def _v2_field_observation_context_valid(
        self,
        field: Any,
        descriptor: Any,
        registry: Any,
        context: Any,
        ordinal: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(context) is not dict:
            _fail(TypeMismatch, "V2 observation context is not an object", path=path)
        if type(ordinal) is not int or ordinal < 0:
            _fail(TypeMismatch, "V2 field ordinal is not an exact safe uint", path=path)
        if ordinal >= 185:
            return False
        indexes = self._build_target_registry_indexes(
            registry,
            counters=counters,
            path=(*path, "registry"),
        )
        resolved_descriptor = self._resolve_field_descriptor_authority(
            field,
            descriptor,
            registry,
            indexes,
            counters=counters,
            path=path,
        )
        descriptors = registry["descriptors"]
        self._complex_visit(counters)
        if not self._complex_exact_equal(
            descriptors[ordinal],
            resolved_descriptor,
            counters=counters,
            path=(*path, "ordinal_descriptor"),
        ):
            return False
        if (
            field.get("field_id") != resolved_descriptor.get("field_id")
            or field.get("target_field_registry_id")
            != context.get("target_field_registry_id")
            or context.get("target_field_registry_id") != indexes.recomputed_registry_id
            or field.get("observation_context_id")
            != context.get("observation_context_id")
        ):
            return False

        binding_reason = context.get("checkpoint_binding_unavailable_reason")
        placeholder_reason = PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON.get(
            binding_reason
        )
        if placeholder_reason is not None:
            return (
                field.get("availability") == "UNAVAILABLE"
                and field.get("value") is None
                and field.get("unavailable_reason") == placeholder_reason
                and field.get("observation_method") == "NOT_ATTEMPTED"
                and field.get("observation_attempt") == "NOT_ATTEMPTED"
                and field.get("adapter_span_status") == "NOT_APPLICABLE"
                and field.get("observation_started_offset_nanoseconds") is None
                and field.get("observation_completed_offset_nanoseconds") is None
                and field.get("censoring") == "NONE"
                and field.get("source_failure_phase") == "NONE"
                and field.get("source_errno_number") is None
                and field.get("source_errno_name") is None
                and field.get("source_error_class") is None
                and field.get("source_error_detail_sha256") is None
            )
        if field.get("unavailable_reason") in PLACEHOLDER_FIELD_REASONS:
            return False

        applicable_operations = resolved_descriptor.get("applicable_operation_kinds")
        if type(applicable_operations) is not list:
            _fail(
                UnresolvedReference,
                "descriptor operation authority is malformed",
                path=path,
            )
        self._complex_visit(counters, len(applicable_operations))
        operation_applies = context.get("operation_kind") in applicable_operations
        if not operation_applies:
            return (
                field.get("availability") == "NOT_APPLICABLE"
                and field.get("unavailable_reason") == "NOT_APPLICABLE_TO_OPERATION"
            )
        if field.get("unavailable_reason") == "NOT_APPLICABLE_TO_OPERATION":
            return False
        field_id = field.get("field_id")
        if context.get("attempt_id") is None and field_id in ATTEMPT_REQUIRED_FIELD_IDS:
            return (
                field.get("availability") == "NOT_APPLICABLE"
                and field.get("unavailable_reason") == "NOT_APPLICABLE_TO_REACHED_STATE"
            )
        if context.get("instrumentation_mode") == "OFF":
            if field_id in OFF_STATIC_FIELD_IDS:
                if field.get("availability") != "AVAILABLE":
                    return False
            elif field_id == "freshness.analysis_pressure_episode_age_boottime_ns":
                if not (
                    field.get("availability") == "UNAVAILABLE"
                    and field.get("unavailable_reason") == "NO_FROZEN_PRESSURE_POLICY"
                ):
                    return False
            elif not (
                field.get("availability") == "UNAVAILABLE"
                and field.get("unavailable_reason") == "INSTRUMENTATION_DISABLED"
            ):
                return False
        elif field.get("unavailable_reason") == "INSTRUMENTATION_DISABLED":
            return False

        if field.get("observation_attempt") == "ATTEMPTED":
            method_rows = resolved_descriptor.get("observation_method_role_pairs")
            if type(method_rows) is not list or len(method_rows) > 2:
                _fail(
                    UnresolvedReference,
                    "descriptor method/role authority is malformed",
                    path=path,
                )
            matches: list[dict[str, Any]] = []
            for row in method_rows:
                self._complex_visit(counters)
                if type(row) is not dict:
                    _fail(
                        UnresolvedReference,
                        "descriptor method/role row is malformed",
                        path=path,
                    )
                if row.get("observation_method") == field.get("observation_method"):
                    matches.append(row)
            if len(matches) != 1:
                _fail(
                    UnresolvedReference,
                    "attempted observation method does not resolve exactly once",
                    path=path,
                )
            roles = matches[0].get("allowed_roles")
            if type(roles) is not list:
                _fail(
                    UnresolvedReference,
                    "descriptor role authority is malformed",
                    path=path,
                )
            self._complex_visit(counters, len(roles))
            if context.get("observation_role") not in roles:
                return False
            if context.get("observation_role") == "STABLE_CHECKPOINT":
                markers = resolved_descriptor.get("allowed_checkpoint_marker_kinds")
                if type(markers) is not list:
                    _fail(
                        UnresolvedReference,
                        "descriptor checkpoint authority is malformed",
                        path=path,
                    )
                self._complex_visit(counters, len(markers))
                if context.get("checkpoint_marker_kind") not in markers:
                    return False

        if field.get("adapter_span_status") == "AVAILABLE":
            observer_span = context.get("observer_clock_span")
            if type(observer_span) is not dict:
                _fail(
                    TypeMismatch,
                    "observer clock span is not an object",
                    path=path,
                )
            field_start = field.get("observation_started_offset_nanoseconds")
            field_end = field.get("observation_completed_offset_nanoseconds")
            observer_start = observer_span.get("started_offset_nanoseconds")
            observer_end = observer_span.get("completed_offset_nanoseconds")
            if (
                observer_span.get("span_status") != "AVAILABLE"
                or any(
                    type(value) is not int
                    for value in (
                        field_start,
                        field_end,
                        observer_start,
                        observer_end,
                    )
                )
                or not observer_start <= field_start <= field_end <= observer_end
            ):
                return False
        return True

    def _a1_fifo_fields_valid(
        self,
        fields: Any,
        registry: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(fields) is not list or len(fields) > 185:
            _fail(TypeMismatch, "A1 field input is not a bounded array", path=path)
        indexes = self._build_target_registry_indexes(
            registry,
            counters=counters,
            path=(*path, "registry"),
        )
        constraint = indexes.cross_field_constraints.get(
            "A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1"
        )
        if constraint is None:
            _fail(
                UnresolvedReference,
                "A1 FIFO authority record is unresolved",
                path=path,
            )
        expected_authority = {
            "activation_condition": "ALL_MEMBERS_AVAILABLE",
            "cardinality_rule": "COUNT_EQUALS_BOTH_ARRAY_LENGTHS",
            "maximum_items": 4,
            "pairing_rule": "SAME_INDEX",
            "sequence_order": "STRICTLY_INCREASING_UNIQUE",
        }
        if any(
            constraint.get(key) != value for key, value in expected_authority.items()
        ):
            _fail(
                UnresolvedReference,
                "A1 FIFO authority record is inconsistent",
                path=path,
            )
        by_id: dict[str, dict[str, Any]] = {}
        for ordinal, field in enumerate(fields):
            self._complex_visit(counters)
            if type(field) is not dict or type(field.get("field_id")) is not str:
                _fail(
                    TypeMismatch,
                    "A1 field observation row is malformed",
                    path=(*path, ordinal),
                )
            field_id = field["field_id"]
            if field_id in by_id:
                _fail(
                    UnresolvedReference,
                    "A1 field observation identifier is duplicated",
                    path=(*path, ordinal),
                )
            by_id[field_id] = field
        count_id = constraint.get("count_field_id")
        sequence_id = constraint.get("sequence_field_id")
        kind_id = constraint.get("kind_field_id")
        try:
            count_field = by_id[count_id]
            sequence_field = by_id[sequence_id]
            kind_field = by_id[kind_id]
        except (KeyError, TypeError) as exc:
            raise UnresolvedReference(
                "A1 FIFO named field is unresolved",
                path=path,
            ) from exc
        for field_id in (count_id, sequence_id, kind_id):
            if field_id not in indexes.descriptors:
                _fail(
                    UnresolvedReference,
                    "A1 FIFO field descriptor is unresolved",
                    path=path,
                )
        if any(
            field.get("availability") != "AVAILABLE"
            for field in (count_field, sequence_field, kind_field)
        ):
            return True
        count_value = count_field.get("value")
        sequence_value = sequence_field.get("value")
        kind_value = kind_field.get("value")
        if (
            type(count_value) is not dict
            or count_value.get("kind") != "UINT"
            or type(sequence_value) is not dict
            or sequence_value.get("kind") != "UINT_LIST"
            or type(kind_value) is not dict
            or kind_value.get("kind") != "TEXT_LIST"
        ):
            _fail(
                TypeMismatch,
                "A1 FIFO field values carry incompatible union alternatives",
                path=path,
            )
        count = count_value.get("value")
        sequences = sequence_value.get("values")
        kinds = kind_value.get("values")
        if (
            type(count) is not int
            or type(sequences) is not list
            or type(kinds) is not list
        ):
            _fail(TypeMismatch, "A1 FIFO payload types differ", path=path)
        self._complex_visit(counters, len(sequences) + len(kinds))
        return (
            count == len(sequences)
            and len(sequences) == len(kinds)
            and len(sequences) <= constraint["maximum_items"]
            and all(
                type(left) is int and type(right) is int and left < right
                for left, right in zip(sequences, sequences[1:])
            )
        )

    def _v2_root_sequence_selector_valid(
        self,
        root: Any,
        observations: Any,
        selector: Any,
        *,
        counters: _RuleCounters,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(root) is not dict or type(observations) is not list:
            _fail(TypeMismatch, "V2 root/sequence operand type differs", path=path)
        if not 1 <= len(observations) <= 67:
            _fail(TypeMismatch, "V2 observation sequence is outside 1..67", path=path)
        if root.get("observation_count") != len(observations):
            return False
        recomputed_ids: list[str] = []
        contexts: list[dict[str, Any]] = []
        for ordinal, observation in enumerate(observations):
            self._complex_visit(counters)
            if type(observation) is not dict:
                _fail(
                    TypeMismatch,
                    "V2 observation is not an object",
                    path=(*path, ordinal),
                )
            recomputed = self._complex_record_identity(
                "TargetObservationV2",
                observation,
                counters=counters,
                path=(*path, ordinal),
            )
            if observation.get("observation_id") != recomputed:
                _fail(
                    UnresolvedReference,
                    "V2 observation identity does not recompute",
                    path=(*path, ordinal),
                )
            context = observation.get("observation_context")
            if type(context) is not dict:
                _fail(
                    TypeMismatch,
                    "V2 observation context is not an object",
                    path=(*path, ordinal),
                )
            recomputed_ids.append(recomputed)
            contexts.append(context)
        if root.get("ordered_observation_ids") != recomputed_ids:
            _fail(
                UnresolvedReference,
                "V2 root ordered identities do not resolve to its sequence",
                path=path,
            )
        for context in contexts:
            self._complex_visit(counters)
            if any(
                context.get(member) != root.get(member)
                for member in (
                    "candidate_id",
                    "attempt_id",
                    "operation_kind",
                    "instrumentation_mode",
                    "target_field_registry_id",
                )
            ):
                return False
        if contexts[0].get("observation_role") == "STARTUP_RECOVERY":
            return (
                len(contexts) == 1
                and root.get("attempt_id") is None
                and root.get("full_checkpoint_selector_id") is None
                and selector is None
            )
        roles = [context.get("observation_role") for context in contexts]
        self._complex_visit(counters, len(roles))
        if not (
            len(roles) >= 3
            and roles[0] == "BEFORE_OPERATION"
            and roles[-2:] == ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
            and all(role == "STABLE_CHECKPOINT" for role in roles[1:-2])
        ):
            return False
        selector_required = (
            root.get("instrumentation_mode") == "ON"
            and root.get("attempt_id") is not None
        )
        if not selector_required:
            return (
                len(contexts) == 3
                and root.get("full_checkpoint_selector_id") is None
                and selector is None
            )
        if type(selector) is not dict:
            _fail(
                TypeMismatch,
                "attempted ON root requires a selector object",
                path=path,
            )
        if not self._checkpoint_selector_intrinsic_valid(
            selector,
            counters=counters,
            path=(*path, "selector"),
        ):
            return False
        selector_id = self._complex_record_identity(
            "CheckpointSelectorV1",
            selector,
            counters=counters,
            path=(*path, "selector"),
        )
        if selector.get("checkpoint_selector_id") != selector_id:
            _fail(
                UnresolvedReference,
                "V2 selector identity does not recompute",
                path=path,
            )
        entries = selector.get("ordered_entries")
        if (
            selector.get("operation_kind") != root.get("operation_kind")
            or selector_id != root.get("full_checkpoint_selector_id")
            or type(entries) is not list
            or len(contexts) != selector.get("selector_length", -1) + 3
        ):
            return False
        exact_ordinals: list[int] = []
        for ordinal, (context, entry) in enumerate(zip(contexts[1:-2], entries)):
            self._complex_visit(counters)
            if type(entry) is not dict:
                _fail(
                    TypeMismatch,
                    "V2 selector entry is not an object",
                    path=(*path, ordinal),
                )
            if (
                context.get("full_checkpoint_selector_id") != selector_id
                or context.get("checkpoint_selector_position")
                != entry.get("selector_position")
                or context.get("checkpoint_selector_entry_id")
                != entry.get("checkpoint_selector_entry_id")
                or context.get("expected_checkpoint_marker_kind")
                != entry.get("checkpoint_marker_kind")
                or context.get("expected_occurrence_index_within_kind")
                != entry.get("occurrence_index_within_kind")
            ):
                return False
            if context.get("checkpoint_binding_status") == "EXACT_MARKER":
                marker_ordinal = context.get("marker_ordinal")
                if type(marker_ordinal) is not int:
                    return False
                exact_ordinals.append(marker_ordinal)
        return all(
            left < right for left, right in zip(exact_ordinals, exact_ordinals[1:])
        )

    @staticmethod
    def _boolean_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> bool:
        if type(operand.value) is not bool:
            _fail(TypeMismatch, "operator requires exact Boolean", path=path)
        return operand.value

    @staticmethod
    def _safe_uint_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> int:
        if (
            type(operand.value) is not int
            or not 0 <= operand.value <= SAFE_INTEGER_MAXIMUM
        ):
            _fail(TypeMismatch, "operator requires exact safe uint", path=path)
        return operand.value

    @staticmethod
    def _uint128_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> int:
        if (
            operand.result_type_kind != "INTERNAL_UINT128"
            or type(operand.value) is not int
            or not 0 <= operand.value <= UINT128_MAXIMUM
        ):
            _fail(TypeMismatch, "operator requires internal uint128", path=path)
        return operand.value

    @staticmethod
    def _bytes_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> bytes:
        if (
            operand.result_type_kind != "INTERNAL_BYTES"
            or type(operand.value) is not bytes
        ):
            _fail(TypeMismatch, "operator requires internal bytes", path=path)
        return operand.value

    @staticmethod
    def _text_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> str:
        if type(operand.value) is not str:
            _fail(TypeMismatch, "operator requires exact text", path=path)
        return operand.value

    @staticmethod
    def _array_operand(
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> list[Any]:
        if type(operand.value) is not list:
            _fail(TypeMismatch, "operator requires an exact array", path=path)
        return operand.value

    @staticmethod
    def _decode_canonical_base64(
        value: str,
        *,
        path: tuple[str | int, ...],
    ) -> bytes:
        try:
            encoded = value.encode("ascii", errors="strict")
            decoded = base64.b64decode(encoded, validate=True)
        except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
            raise ConstraintViolation("base64 operand is malformed", path=path) from exc
        if base64.b64encode(decoded) != encoded:
            _fail(ConstraintViolation, "base64 operand is noncanonical", path=path)
        return decoded

    @staticmethod
    def _timestamp_to_epoch_microseconds(
        value: str,
        *,
        path: tuple[str | int, ...],
    ) -> int:
        match = re.fullmatch(
            r"([0-9]{4})-([0-9]{2})-([0-9]{2})T"
            r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
            r"(?:\.([0-9]{6}))?Z",
            value,
        )
        if match is None or len(value.encode("utf-8")) not in {20, 27}:
            _fail(ConstraintViolation, "timestamp operand is malformed", path=path)
        year, month, day, hour, minute, second = (
            int(match.group(index)) for index in range(1, 7)
        )
        microsecond = int(match.group(7) or "0")
        if match.group(7) == "000000":
            _fail(ConstraintViolation, "timestamp operand is noncanonical", path=path)
        try:
            dt.datetime(
                year,
                month,
                day,
                hour,
                minute,
                second,
                microsecond,
                tzinfo=dt.timezone.utc,
            )
        except ValueError as exc:
            raise ConstraintViolation(
                "timestamp operand is not a valid date",
                path=path,
            ) from exc

        def days_before_year(selected_year: int) -> int:
            previous = selected_year - 1
            return previous * 365 + previous // 4 - previous // 100 + previous // 400

        month_offsets = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        day_index = (
            days_before_year(year)
            + month_offsets[month - 1]
            + (1 if leap and month > 2 else 0)
            + day
            - 1
        )
        epoch_day_index = days_before_year(1970)
        seconds = (
            (day_index - epoch_day_index) * 86_400 + hour * 3_600 + minute * 60 + second
        )
        return seconds * 1_000_000 + microsecond

    @staticmethod
    def _rfc6455_close_payload_valid(opcode: str, payload: bytes) -> bool:
        if opcode != "CLOSE":
            return True
        if not payload:
            return True
        if len(payload) == 1:
            return False
        code = int.from_bytes(payload[:2], byteorder="big", signed=False)
        if (
            code
            not in {
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
            and not 3000 <= code <= 4999
        ):
            return False
        try:
            payload[2:].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return False
        return True

    def _record_descriptor_for_expression(
        self,
        operand: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> dict[str, Any]:
        if (
            operand.result_type_kind != "VALUE_SCHEMA"
            or operand.value_schema_id is None
        ):
            _fail(TypeMismatch, "operator requires a value-schema record", path=path)
        schema = self.schemas[operand.value_schema_id]
        if schema["schema_kind"] != "OBJECT_REF":
            _fail(TypeMismatch, "operator requires an object reference", path=path)
        descriptor = self.types[schema["referenced_type_name"]]
        if descriptor["type_form"] != "RECORD":
            _fail(TypeMismatch, "operator requires a concrete record", path=path)
        return descriptor

    @staticmethod
    def _require_same_expression_type(
        left: _ExpressionValue,
        right: _ExpressionValue,
        *,
        path: tuple[str | int, ...],
    ) -> None:
        if (
            left.result_type_kind != right.result_type_kind
            or left.value_schema_id != right.value_schema_id
        ):
            _fail(TypeMismatch, "operator operand declarations differ", path=path)

    @staticmethod
    def _raw_exact_equal(left: Any, right: Any) -> bool:
        if type(left) is not type(right):
            return False
        if type(left) in {dict, list}:
            return _canonical_bytes(left) == _canonical_bytes(right)
        return left == right

    def _expression_equal(
        self,
        left: _ExpressionValue,
        right: _ExpressionValue,
    ) -> bool:
        if left.result_type_kind == "INTERNAL_BYTES":
            return type(left.value) is bytes and left.value == right.value
        return self._raw_exact_equal(left.value, right.value)

    def _validate_expression_result(
        self,
        node: dict[str, Any],
        result: _ExpressionValue,
    ) -> None:
        path = ("rule_node", node["expression_position"], "result")
        if (
            result.result_type_kind != node["result_type_kind"]
            or result.value_schema_id != node["result_value_schema_id"]
        ):
            _fail(
                ImpossibleState,
                "expression result declaration differs from its frozen node",
                path=path,
            )
        kind = result.result_type_kind
        if kind == "VALUE_SCHEMA":
            if result.value_schema_id is None:
                _fail(ImpossibleState, "value result lacks schema", path=path)
            self._validate_schema_runtime(result.value_schema_id, result.value)
            return
        if result.value_schema_id is not None:
            _fail(ImpossibleState, "internal result names a value schema", path=path)
        if kind == "INTERNAL_BYTES":
            if type(result.value) is not bytes:
                _fail(TypeMismatch, "internal bytes result differs", path=path)
            return
        if kind == "INTERNAL_UINT128":
            if (
                type(result.value) is not int
                or not 0 <= result.value <= UINT128_MAXIMUM
            ):
                _fail(TypeMismatch, "internal uint128 result differs", path=path)
            return
        if kind == "INTERNAL_INT128":
            if (
                type(result.value) is not int
                or not INT128_MINIMUM <= result.value <= INT128_MAXIMUM
            ):
                _fail(TypeMismatch, "internal int128 result differs", path=path)
            return
        _fail(ImpossibleState, f"unknown result kind: {kind}", path=path)

    def _validate_schema_runtime(self, schema_id: str, value: Any) -> None:
        budget = _Budget(MAXIMUM_VALIDATION_WORK, MAXIMUM_VALIDATION_WORK)
        self._validate_schema(
            schema_id,
            value,
            owner=None,
            path=(),
            budget=budget,
            active=set(),
        )

    def _validate_rule_literal_schema(
        self,
        schema_id: str,
        value: Any,
        *,
        counters: _RuleCounters,
        literal_rule_stack: tuple[str, ...],
        path: tuple[str | int, ...],
    ) -> None:
        """Validate literal structure and execute only its attached intrinsic rules."""

        self._validate_schema_runtime(schema_id, value)
        self._walk_literal_schema_rules(
            schema_id,
            value,
            owner=None,
            counters=counters,
            literal_rule_stack=literal_rule_stack,
            path=path,
        )

    def _walk_literal_schema_rules(
        self,
        schema_id: str,
        value: Any,
        *,
        owner: TypedValue | None,
        counters: _RuleCounters,
        literal_rule_stack: tuple[str, ...],
        path: tuple[str | int, ...],
    ) -> None:
        if value is None:
            return
        schema = self.schemas[schema_id]
        kind = schema["schema_kind"]
        if kind == "ARRAY":
            item_schema_id = schema["array_item_value_schema_id"]
            for index, item in enumerate(value):
                self._walk_literal_schema_rules(
                    item_schema_id,
                    item,
                    owner=None,
                    counters=counters,
                    literal_rule_stack=literal_rule_stack,
                    path=(*path, index),
                )
            return
        if kind != "OBJECT_REF":
            return
        descriptor = self.types[schema["referenced_type_name"]]
        if descriptor["type_form"] == "TAGGED_UNION":
            descriptor = self._selected_literal_record_descriptor(
                descriptor,
                value,
                owner=owner,
                path=path,
            )
        record_owner = TypedValue(value=value, type_name=descriptor["type_name"])
        for member in descriptor["record_member_descriptors"]:
            self._walk_literal_schema_rules(
                member["value_schema_id"],
                value[member["member_name"]],
                owner=record_owner,
                counters=counters,
                literal_rule_stack=literal_rule_stack,
                path=(*path, member["member_name"]),
            )
        for rule_id in descriptor["ordered_intrinsic_rule_ids"]:
            if rule_id in literal_rule_stack:
                _fail(
                    ImpossibleState,
                    f"composite literal re-enters intrinsic rule: {rule_id}",
                    path=path,
                )
            root = self._evaluate_rule(
                rule_id,
                {"self": value},
                counters=counters,
                literal_rule_stack=literal_rule_stack,
            )
            if not root:
                _fail(
                    BusinessRuleFalse,
                    f"composite literal intrinsic root is false: {rule_id}",
                    path=path,
                )

    def _selected_literal_record_descriptor(
        self,
        union_descriptor: dict[str, Any],
        value: dict[str, Any],
        *,
        owner: TypedValue | None,
        path: tuple[str | int, ...],
    ) -> dict[str, Any]:
        topology = union_descriptor["tagged_union_descriptor"]
        actual: dict[str, str] = {}
        for discriminator in topology["ordered_discriminator_descriptors"]:
            if discriminator["discriminator_scope"] == "SELECTED_VALUE":
                root = value
            elif discriminator["discriminator_scope"] == "OWNER_OBJECT":
                expected_owner = discriminator["discriminator_owner_type_name"]
                if owner is None or owner.type_name != expected_owner:
                    _fail(
                        UnresolvedReference,
                        f"literal union requires owner {expected_owner}",
                        path=path,
                    )
                root = owner.value
            else:
                _fail(
                    ImpossibleState,
                    "literal union discriminator scope is unknown",
                    path=path,
                )
            member_path = discriminator["discriminator_typed_member_path"]
            selected = self._resolve_path(root, member_path, path=path)
            if type(selected) is not str:
                _fail(TypeMismatch, "union discriminator is not text", path=path)
            actual[member_path[-1]] = selected
        matches = [
            alternative
            for alternative in topology["ordered_alternatives"]
            if {
                literal["member_name"]: literal["text_value"]
                for literal in alternative["ordered_discriminator_literals"]
            }
            == actual
        ]
        if len(matches) != 1:
            _fail(
                ConstraintViolation,
                "literal union does not select exactly one alternative",
                path=path,
            )
        descriptor = self.records.get(matches[0]["referenced_type_name"])
        if descriptor is None:
            _fail(
                ImpossibleState,
                "literal union alternative is not a concrete record",
                path=path,
            )
        return descriptor

    def validation_report(self) -> dict[str, Any]:
        validated_authorities: dict[str, dict[str, Any]] = {}
        total_intrinsic_invocations = 0
        total_expression_nodes = 0
        total_complex_operator_invocations = 0
        total_complex_row_item_visits = 0
        total_complex_canonicalized_octets = 0
        for authority_name, type_name in (
            ("marker_contract", "MarkerContractV1"),
            ("operation_counter_schema", "OperationCounterSnapshotSchemaV1"),
            ("target_field_registry", "TargetFieldRegistryV1"),
        ):
            evidence = self.validate_with_evidence(
                TypedValue(
                    value=self.literal_authority[authority_name],
                    type_name=type_name,
                )
            )
            rule_id = f"RULE/INTRINSIC/{type_name}/V1"
            rule_evidence = self.evaluate_rule(
                rule_id,
                {"self": self.literal_authority[authority_name]},
            )
            total_intrinsic_invocations += rule_evidence.intrinsic_rule_invocations
            total_expression_nodes += rule_evidence.total_expression_nodes
            total_complex_operator_invocations += (
                rule_evidence.complex_operator_invocations
            )
            total_complex_row_item_visits += rule_evidence.complex_row_item_visits
            total_complex_canonicalized_octets += (
                rule_evidence.complex_canonicalized_octets
            )
            validated_authorities[authority_name] = {
                "complex_canonicalized_octets": (
                    rule_evidence.complex_canonicalized_octets
                ),
                "complex_operator_invocations": (
                    rule_evidence.complex_operator_invocations
                ),
                "complex_row_item_visits": (rule_evidence.complex_row_item_visits),
                "direct_rule_id": rule_id,
                "executed_expression_nodes": rule_evidence.total_expression_nodes,
                "executed_intrinsic_rule_invocations": (
                    rule_evidence.intrinsic_rule_invocations
                ),
                "type_name": type_name,
                "validation_work_used": evidence.validation_work_used,
            }
        generic_operator_nodes = sum(
            node["operator"] in GENERIC_OPERATOR_NAMES
            for rule in self.rules.values()
            for node in rule["ordered_expression_nodes"]
        )
        return {
            "ascii_dfa_count": len(self.dfas),
            "complex_operator_count": len(COMPLEX_OPERATOR_NAMES),
            "complex_operator_node_count_across_full_catalog": (
                sum(
                    node["operator"] in COMPLEX_OPERATOR_NAMES
                    for rule in self.rules.values()
                    for node in rule["ordered_expression_nodes"]
                )
            ),
            "derived_maximum_validation_work": self.derived_maximum_validation_work,
            "executable_application_count": len(self.compiled_applications),
            "executable_complex_rule_count": len(self.complex_rule_ids),
            "executable_expression_node_count": sum(
                len(rule["ordered_expression_nodes"]) for rule in self.rules.values()
            ),
            "executable_generic_rule_count": len(self.generic_rule_ids),
            "executable_rule_count": len(self.rules),
            "executed_literal_authority_complex_canonicalized_octets": (
                total_complex_canonicalized_octets
            ),
            "executed_literal_authority_complex_operator_invocations": (
                total_complex_operator_invocations
            ),
            "executed_literal_authority_complex_row_item_visits": (
                total_complex_row_item_visits
            ),
            "executed_literal_authority_expression_nodes": total_expression_nodes,
            "executed_literal_authority_intrinsic_rule_invocations": (
                total_intrinsic_invocations
            ),
            "external_type_count": len(self.types),
            "fixed_position_resolver_count": len(self.compiled_resolvers),
            "generic_operator_count": len(GENERIC_OPERATOR_NAMES),
            "generic_operator_node_count_across_full_catalog": generic_operator_nodes,
            "maximum_work_schema_id": self.maximum_work_schema_id,
            "maximum_work_type_name": self.maximum_work_type_name,
            "record_type_count": len(self.records),
            "status": RUNTIME_STATUS,
            "sum_of_per_application_maximum_rule_evaluations": sum(
                plan.maximum_rule_evaluations
                for plan in self.compiled_applications.values()
            ),
            "sum_of_per_application_direct_expression_node_maxima": sum(
                plan.maximum_rule_evaluations
                * len(self.rules[plan.rule_id]["ordered_expression_nodes"])
                for plan in self.compiled_applications.values()
            ),
            "validated_and_rule_executed_composite_authorities": (
                validated_authorities
            ),
            "tagged_union_type_count": len(self.unions),
            "text_language_count": len(self.languages),
            "total_rule_count": 42,
            "total_rule_expression_node_count": sum(
                len(rule["ordered_expression_nodes"]) for rule in self.rules.values()
            ),
            "unsupported_complex_rule_count": 0,
            "unsupported_complex_rule_expression_node_count": 0,
            "validation_work_limit": MAXIMUM_VALIDATION_WORK,
            "validation_work_limit_kind": (
                "CONSERVATIVE_FROZEN_SCHEMA_MAXIMA_NOT_LEGAL_VALUE_MAXIMUM"
            ),
            "validation_work_unit": "SCHEMA_NODE_VISIT",
            "value_schema_count": len(self.schemas),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path)
    args = parser.parse_args()
    try:
        runtime = ExternalSchemaV2Runtime.load(args.repository_root)
        print(json.dumps(runtime.validation_report(), sort_keys=True))
        return 0
    except RuntimeFailure as exc:
        print(
            f"Raw-V8 Step-2 runtime validation error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

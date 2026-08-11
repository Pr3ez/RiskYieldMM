"""Durable Raw-V7 measurement-operation lifecycle contracts.

The records in this module describe the local lifecycle of one measured
transport ingress operation.  They deliberately do not claim peer receipt,
exchange acknowledgement, profitability, or a retry right.  An attempt is
durable before the operation can create effects; exactly one terminal record
later classifies the locally provable prefix, including cancellation and
process-loss recovery.

These contracts are versioned independently from the Raw-V6 artifact codec.
There is no V6-to-V7 upgrade path.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, TypeVar

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .physical_transport_actor_v49c import (
    TransportActorEventV49C,
    WebSocketParserCursorV49C,
)
from .physical_transport_capacity_v49f import TransportCapacityPolicyV49F
from .physical_transport_control_v4 import RawIngressCommitV4
from .physical_transport_terminal_v49c import TerminalOutcomeV49C

CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F = (
    "riskyieldmm_physical_transport_a2m_lifecycle_v49f_raw_v7"
)
CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationAttemptV4_9F_RawV7"
)
CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationTerminalV4_9F_RawV7"
)
CAPACITY_MEASUREMENT_OPERATION_DECLARATION_DOMAIN_V49F = (
    "RiskYieldMMA2MOperationDeclarationV4_9F_RawV7"
)
CAPACITY_MEASUREMENT_RECOVERED_PREFIX_DOMAIN_V49F = (
    "RiskYieldMMA2MRecoveredOperationPrefixV4_9F_RawV7"
)
CAPACITY_MEASUREMENT_FINAL_PREFIX_DOMAIN_V49F = (
    "RiskYieldMMA2MFinalOperationPrefixV4_9F_RawV7"
)

# Frozen parser and operation-envelope bounds.  These are safety limits, not
# measured capacity conclusions.
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F = 256
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_UTF8_BYTES_V49F = 128
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F = 128
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F = 256
# Compatibility aliases retain the original public spellings. Their values are
# UTF-8 byte ceilings; new code must use the authoritative names above.
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_CHARACTERS_V49F = (
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F
)
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_CHARACTERS_V49F = (
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_UTF8_BYTES_V49F
)
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_CHARACTERS_V49F = (
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F
)
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_CHARACTERS_V49F = (
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F
)
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_CHUNKS_V49F = 128
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_OCTETS_V49F = 65_536
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F = 64
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F = 262_144
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F = 48 * 1024 * 1024
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F = 256 * 1024
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F = 8
CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECEIPTS_V49F = 524_288
CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7 = 64
CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7 = 512
CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7 = 524_288
CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7 = "V7_JSON_DEPTH_LIMIT_EXCEEDED"
CAPACITY_MEASUREMENT_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F_V7 = (
    "V7_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED"
)
CAPACITY_MEASUREMENT_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F_V7 = (
    "V7_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED"
)
CAPACITY_MEASUREMENT_JSON_MALFORMED_STRUCTURE_V49F_V7 = "V7_JSON_MALFORMED_STRUCTURE"

_ATTEMPT_RECORD_KIND_V49F = "CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V7"
_TERMINAL_RECORD_KIND_V49F = "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7"
_RAW_RECORD_KIND_V49F = "RAW_INGRESS_COMMIT_V4"
_ACTOR_RECORD_KIND_V49F = "TRANSPORT_ACTOR_EVENT_V49C"
_RUNTIME_STATE_VALUES_V49F = frozenset(
    {
        "COLD",
        "STARTING",
        "READY",
        "SESSION_COMMITTED",
        "INTENT_COMMITTED",
        "DISPATCHING",
        "AWAITING_ACK",
        "ACK_BOUND",
        "FENCED",
        "FAULT_LATCHED",
        "CLOSED",
    }
)


class CapacityMeasurementLifecycleOperationV49F(str, Enum):
    """The sole effectful operation admitted by the Raw-V7 journal."""

    INGRESS = "INGRESS"


class CapacityMeasurementLifecycleTerminalTriggerV49F(str, Enum):
    """Why terminal observation ran; orthogonal to the effect certainty."""

    RETURNED = "RETURNED"
    RAISED_EXCEPTION = "RAISED_EXCEPTION"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    RECOVERED_ORPHAN = "RECOVERED_ORPHAN"


class CapacityMeasurementLifecycleEffectCertaintyV49F(str, Enum):
    """Strongest local effect statement supported by durable evidence."""

    NO_DURABLE_EFFECT = "NO_DURABLE_EFFECT"
    EXACT_COMPLETED_PREFIX = "EXACT_COMPLETED_PREFIX"
    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"


class CapacityMeasurementLifecycleProgressAvailabilityV49F(str, Enum):
    """How progress can be obtained; never a peer-delivery assertion."""

    EXACT_RETURNED_PROGRESS = "EXACT_RETURNED_PROGRESS"
    EXACT_DURABLE_PREFIX = "EXACT_DURABLE_PREFIX"
    UNAVAILABLE = "UNAVAILABLE"


class CapacityMeasurementLifecycleTerminalWriterV49F(str, Enum):
    SAME_TASK = "SAME_TASK"
    STARTUP_RECOVERY = "STARTUP_RECOVERY"


class CapacityMeasurementLifecycleCancellationV49F(str, Enum):
    NONE = "NONE"
    ASYNCIO_CANCELLED_ERROR = "ASYNCIO_CANCELLED_ERROR"
    PROCESS_LOSS_UNKNOWN = "PROCESS_LOSS_UNKNOWN"


class CapacityMeasurementSessionTerminalAuthorityV49F(str, Enum):
    DURABLE_ACTOR_TERMINAL = "DURABLE_ACTOR_TERMINAL"
    VOLATILE_RUNTIME_FAULT_LATCHED = "VOLATILE_RUNTIME_FAULT_LATCHED"
    NONTERMINAL_RUNTIME = "NONTERMINAL_RUNTIME"
    UNAVAILABLE_AFTER_ORPHAN = "UNAVAILABLE_AFTER_ORPHAN"


_RecordT = TypeVar("_RecordT")


def _exact_enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    if type(value) is not enum_type:
        raise CanonicalizationError(f"{field} must be an exact {enum_type.__name__}")
    return value


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _canonical_uint128_text(value: Any, *, field: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 39
        or not value.isascii()
        or not value.isdecimal()
        or (len(value) > 1 and value.startswith("0"))
        or int(value) >= 1 << 128
    ):
        raise CanonicalizationError(
            f"{field} must be canonical unsigned 128-bit decimal text"
        )
    return value


def validate_capacity_measurement_json_structure_before_parse_v49f_v7(
    payload: bytes,
) -> None:
    """Bound Raw-V7 JSON structure without materializing the JSON tree."""

    malformed = CAPACITY_MEASUREMENT_JSON_MALFORMED_STRUCTURE_V49F_V7

    def reject(reason: str) -> None:
        raise CanonicalizationError(f"Raw V7 JSON structural guard rejected: {reason}")

    if type(payload) is not bytes or not payload:
        reject(malformed)

    # Frames are [kind, state, member_count]. Container values are counted in
    # their parent when their opening delimiter is encountered.
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
            if frame[2] > CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7:
                reject(CAPACITY_MEASUREMENT_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F_V7)
            frame[1] = "COMMA_OR_END"
            return
        if frame[1] != "VALUE":
            reject(malformed)
        frame[1] = "COMMA_OR_END"

    def open_container(kind: str) -> None:
        if len(stack) >= CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7:
            reject(CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7)
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
                    if (
                        frame[2]
                        > CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7
                    ):
                        reject(
                            CAPACITY_MEASUREMENT_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F_V7
                        )
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
            f"Raw V7 JSON structural guard rejected: {malformed}"
        ) from exc

    if stack or root_state != "END":
        reject(malformed)


def _canonical_utf8_identifier(value: Any, *, field: str, maximum: int) -> str:
    """Validate identifier text against the protocol's UTF-8 byte ceiling."""

    text = canonical_identifier(value, field=field, maximum=maximum)
    if len(text.encode("utf-8")) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} UTF-8 bytes")
    return text


def _optional_identifier(value: Any, *, field: str, maximum: int) -> str | None:
    return (
        None
        if value is None
        else _canonical_utf8_identifier(value, field=field, maximum=maximum)
    )


def _record_field_names(record_type: type[Any]) -> frozenset[str]:
    return frozenset(item.name for item in fields(record_type))


def _semantic_id(*, domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
        }
    )


def _bounded_canonical_bytes(
    payload: Mapping[str, Any], *, context: str, maximum: int
) -> bytes:
    encoded = canonical_json_bytes(dict(payload))
    if len(encoded) > maximum:
        raise CanonicalizationError(
            f"{context} exceeds its {maximum}-byte canonical bound"
        )
    return encoded


def _canonical_base64(value: Any, *, field: str, maximum_decoded_octets: int) -> bytes:
    text = canonical_identifier(
        value,
        field=field,
        maximum=4 * ((maximum_decoded_octets + 2) // 3),
    )
    try:
        decoded = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CanonicalizationError(f"{field} must be canonical base64") from exc
    if (
        len(decoded) > maximum_decoded_octets
        or base64.b64encode(decoded).decode("ascii") != text
    ):
        raise CanonicalizationError(f"{field} exceeds its bound or is noncanonical")
    return decoded


def _decode_record(
    payload: Mapping[str, Any],
    *,
    record_type: type[_RecordT],
    domain: str,
    identity_field: str,
    enum_fields: Mapping[str, type[Enum]],
) -> _RecordT:
    if not isinstance(payload, Mapping):
        raise CanonicalizationError(f"{record_type.__name__} must be a mapping")
    field_names = _record_field_names(record_type)
    require_exact_keys(
        payload,
        expected=field_names
        | {
            "canonicalization_version",
            "lifecycle_schema_version",
            "record_domain",
        },
        context=record_type.__name__,
    )
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("lifecycle canonicalization version differs")
    if (
        payload["lifecycle_schema_version"]
        != CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
    ):
        raise CanonicalizationError("lifecycle schema version differs")
    if payload["record_domain"] != domain:
        raise CanonicalizationError("lifecycle record domain differs")
    values = {name: payload[name] for name in field_names}
    for name, enum_type in enum_fields.items():
        try:
            if type(values[name]) is not str:
                raise ValueError
            values[name] = enum_type(values[name])
        except ValueError as exc:
            raise CanonicalizationError(f"{name} is unsupported") from exc
    result = record_type(**values)
    if canonical_hash(payload[identity_field], field=identity_field) != getattr(
        result, identity_field
    ):
        raise CanonicalizationError(
            f"{identity_field} differs from canonical lifecycle members"
        )
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationDeclarationV49F:
    """Strict pre-admission input; it contains no runtime-authority facts."""

    campaign_manifest_id: str
    manifest_authority_id: str
    measurement_design_id: str
    workload_id: str
    workload_sha256: str
    sample_sequence: int
    operation_sequence: int
    trial_index: int
    repetition_index: int
    is_warmup: bool
    stage: str
    operation: CapacityMeasurementLifecycleOperationV49F
    input_chunk_count: int
    input_octet_count: int
    input_sha256: str
    raw_ingress_batch_sha256: str
    timeout_seconds: int
    expected_output_frame_count: int
    expected_output_frames_sha256: str
    declaration_id: str | None = None

    _ENUM_FIELDS: ClassVar[Mapping[str, type[Enum]]] = {
        "operation": CapacityMeasurementLifecycleOperationV49F,
    }

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "measurement_design_id",
            "workload_sha256",
            "input_sha256",
            "raw_ingress_batch_sha256",
            "expected_output_frames_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "workload_id",
            _canonical_utf8_identifier(
                self.workload_id,
                field="workload_id",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "stage",
            _canonical_utf8_identifier(
                self.stage,
                field="stage",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_UTF8_BYTES_V49F,
            ),
        )
        _exact_enum(
            self.operation,
            CapacityMeasurementLifecycleOperationV49F,
            field="operation",
        )
        if self.operation is not CapacityMeasurementLifecycleOperationV49F.INGRESS:
            raise CanonicalizationError("Raw-V7 declaration operation must be INGRESS")
        for name, minimum, maximum in (
            ("sample_sequence", 1, None),
            ("operation_sequence", 1, None),
            ("trial_index", 0, None),
            ("repetition_index", 0, None),
            (
                "input_chunk_count",
                1,
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_CHUNKS_V49F,
            ),
            (
                "input_octet_count",
                1,
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_OCTETS_V49F,
            ),
            ("expected_output_frame_count", 0, None),
            ("timeout_seconds", 1, 300),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(
                    getattr(self, name), field=name, minimum=minimum, maximum=maximum
                ),
            )
        if type(self.is_warmup) is not bool:
            raise CanonicalizationError("is_warmup must be an exact boolean")
        identity = _semantic_id(
            domain=CAPACITY_MEASUREMENT_OPERATION_DECLARATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.declaration_id is not None
            and canonical_hash(self.declaration_id, field="declaration_id") != identity
        ):
            raise CanonicalizationError("declaration_id differs from canonical members")
        object.__setattr__(self, "declaration_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in fields(type(self)):
            if item.name == "declaration_id":
                continue
            value = getattr(self, item.name)
            if isinstance(value, Enum):
                value = value.value
            result[item.name] = value
        return result

    def identity_payload(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError(
                "operation declaration was mutated after validation"
            )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "declaration_id": self.declaration_id,
            "lifecycle_schema_version": (
                CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
            ),
            "record_domain": CAPACITY_MEASUREMENT_OPERATION_DECLARATION_DOMAIN_V49F,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationDeclarationV49F:
        return _decode_record(
            payload,
            record_type=cls,
            domain=CAPACITY_MEASUREMENT_OPERATION_DECLARATION_DOMAIN_V49F,
            identity_field="declaration_id",
            enum_fields=cls._ENUM_FIELDS,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementRetainedRawDependencyV49F:
    """Attempt-time same-ledger membership witness for retained older RAW."""

    raw_ingress_commit_id: str
    content_hash: str
    original_receipt_sequence: int
    original_receipt_hash: str

    def __post_init__(self) -> None:
        for name in (
            "raw_ingress_commit_id",
            "content_hash",
            "original_receipt_hash",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "original_receipt_sequence",
            canonical_safe_int(
                self.original_receipt_sequence,
                field="original_receipt_sequence",
                minimum=1,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_hash": self.content_hash,
            "original_receipt_hash": self.original_receipt_hash,
            "original_receipt_sequence": self.original_receipt_sequence,
            "raw_ingress_commit_id": self.raw_ingress_commit_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementRetainedRawDependencyV49F:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationAttemptV49F:
    """Pre-effect durable intent and exact local projection baseline."""

    campaign_manifest_id: str
    manifest_authority_id: str
    measurement_design_id: str
    declaration_id: str
    previous_operation_terminal_id: str | None
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    transport_capacity_policy: TransportCapacityPolicyV49F
    projection_ledger_id: str
    projection_schema_version: str
    projection_validation_version: str
    projection_schema_fingerprint: str
    projection_store_observation_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    pre_attempt_receipt_sequence: int
    pre_attempt_receipt_hash: str
    retained_raw_dependencies: tuple[CapacityMeasurementRetainedRawDependencyV49F, ...]
    initial_pending_ingress_present_before: bool
    workload_id: str
    workload_sha256: str
    sample_sequence: int
    operation_sequence: int
    trial_index: int
    repetition_index: int
    is_warmup: bool
    stage: str
    operation: CapacityMeasurementLifecycleOperationV49F
    input_chunk_count: int
    input_octet_count: int
    input_sha256: str
    raw_ingress_batch_sha256: str
    timeout_seconds: int
    expected_output_frame_count: int
    expected_output_frames_sha256: str
    observer_start_offset_nanoseconds: int
    boottime_start_offset_nanoseconds: int
    loop_time_start_offset_nanoseconds: int
    loop_time_origin_nanoseconds: str
    admission_policy_id: str
    admission_epoch: int
    admission_sequence: int
    admission_command_kind: CapacityMeasurementLifecycleOperationV49F
    admission_reservation_work_units: int
    admission_admitted_loop_time_ns: str
    admission_started_loop_time_ns: str
    admission_start_deadline_loop_time_ns: str
    admission_queue_wait_nanoseconds: int
    baseline_raw_ingress_sequence: int
    baseline_raw_ingress_commit_id: str | None
    baseline_actor_event_count: int
    baseline_actor_tail_event_id: str | None
    parser_cursor_before: WebSocketParserCursorV49C
    parser_cursor_id_before: str
    runtime_state_before: str
    started_at: datetime
    started_monotonic_ns: str
    monotonic_clock_domain_id: str
    attempt_id: str | None = None

    _ENUM_FIELDS: ClassVar[Mapping[str, type[Enum]]] = {
        "operation": CapacityMeasurementLifecycleOperationV49F,
        "admission_command_kind": CapacityMeasurementLifecycleOperationV49F,
    }

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "measurement_design_id",
            "declaration_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
            "projection_ledger_id",
            "projection_schema_fingerprint",
            "projection_store_observation_id",
            "writer_fence_token_sha256",
            "workload_sha256",
            "input_sha256",
            "raw_ingress_batch_sha256",
            "expected_output_frames_sha256",
            "admission_policy_id",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "workload_id",
            _canonical_utf8_identifier(
                self.workload_id,
                field="workload_id",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "pre_attempt_receipt_sequence",
            canonical_safe_int(
                self.pre_attempt_receipt_sequence,
                field="pre_attempt_receipt_sequence",
                minimum=0,
            ),
        )
        if type(self.retained_raw_dependencies) is not tuple or any(
            type(item) is not CapacityMeasurementRetainedRawDependencyV49F
            for item in self.retained_raw_dependencies
        ):
            raise CanonicalizationError(
                "retained_raw_dependencies must be an exact tuple"
            )
        if len(self.retained_raw_dependencies) > (
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F
        ):
            raise CanonicalizationError(
                "retained RAW dependency witness count exceeds its bound"
            )
        if type(self.initial_pending_ingress_present_before) is not bool:
            raise CanonicalizationError(
                "initial_pending_ingress_present_before must be an exact boolean"
            )
        witness_ids = tuple(
            item.raw_ingress_commit_id for item in self.retained_raw_dependencies
        )
        witness_sequences = tuple(
            item.original_receipt_sequence for item in self.retained_raw_dependencies
        )
        if (
            len(set(witness_ids)) != len(witness_ids)
            or witness_sequences != tuple(sorted(witness_sequences))
            or any(
                sequence > self.pre_attempt_receipt_sequence
                for sequence in witness_sequences
            )
        ):
            raise CanonicalizationError(
                "retained RAW dependency witnesses are duplicate, unordered, or future"
            )
        object.__setattr__(
            self,
            "stage",
            _canonical_utf8_identifier(
                self.stage,
                field="stage",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_UTF8_BYTES_V49F,
            ),
        )
        _exact_enum(
            self.operation, CapacityMeasurementLifecycleOperationV49F, field="operation"
        )
        _exact_enum(
            self.admission_command_kind,
            CapacityMeasurementLifecycleOperationV49F,
            field="admission_command_kind",
        )
        if self.operation is not CapacityMeasurementLifecycleOperationV49F.INGRESS:
            raise CanonicalizationError("Raw-V7 lifecycle operation must be INGRESS")
        if self.admission_command_kind is not self.operation:
            raise CanonicalizationError(
                "lifecycle operation differs from its exact admission command"
            )
        if self.admission_policy_id != self.transport_capacity_policy_id:
            raise CanonicalizationError(
                "attempt admission policy differs from its transport capacity policy"
            )
        if type(self.transport_capacity_policy) is not TransportCapacityPolicyV49F:
            raise CanonicalizationError(
                "transport_capacity_policy must be an exact frozen A1 policy"
            )
        if (
            self.transport_capacity_policy.policy_id
            != self.transport_capacity_policy_id
            or self.admission_reservation_work_units
            != self.transport_capacity_policy.ingress_reservation_work_units
        ):
            raise CanonicalizationError(
                "attempt grant differs from its complete transport capacity policy"
            )
        for name, minimum, maximum in (
            ("sample_sequence", 1, None),
            ("operation_sequence", 1, None),
            ("trial_index", 0, None),
            ("repetition_index", 0, None),
            (
                "input_chunk_count",
                1,
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_CHUNKS_V49F,
            ),
            (
                "input_octet_count",
                1,
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_OCTETS_V49F,
            ),
            ("admission_epoch", 1, None),
            ("admission_sequence", 1, None),
            ("admission_reservation_work_units", 1, None),
            ("admission_queue_wait_nanoseconds", 0, None),
            ("baseline_raw_ingress_sequence", 0, None),
            ("baseline_actor_event_count", 0, None),
            ("writer_fence_generation", 1, None),
            ("pre_attempt_receipt_sequence", 0, None),
            ("expected_output_frame_count", 0, None),
            ("timeout_seconds", 1, 300),
            ("observer_start_offset_nanoseconds", 0, None),
            ("boottime_start_offset_nanoseconds", 0, None),
            ("loop_time_start_offset_nanoseconds", 0, None),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(
                    getattr(self, name), field=name, minimum=minimum, maximum=maximum
                ),
            )
        if type(self.is_warmup) is not bool:
            raise CanonicalizationError("is_warmup must be an exact boolean")
        for name in (
            "loop_time_origin_nanoseconds",
            "admission_admitted_loop_time_ns",
            "admission_started_loop_time_ns",
            "admission_start_deadline_loop_time_ns",
            "started_monotonic_ns",
        ):
            object.__setattr__(
                self,
                name,
                _canonical_uint128_text(getattr(self, name), field=name),
            )
        origin_ns = int(self.loop_time_origin_nanoseconds)
        admitted_ns = int(self.admission_admitted_loop_time_ns)
        started_ns = int(self.admission_started_loop_time_ns)
        deadline_ns = int(self.admission_start_deadline_loop_time_ns)
        if not (admitted_ns <= started_ns <= deadline_ns):
            raise CanonicalizationError("admission grant timing is invalid")
        if self.admission_queue_wait_nanoseconds != (started_ns - admitted_ns):
            raise CanonicalizationError(
                "admission queue wait differs from the exact grant span"
            )
        if (
            admitted_ns < origin_ns
            or origin_ns + self.loop_time_start_offset_nanoseconds < started_ns
        ):
            raise CanonicalizationError(
                "attempt loop-time origin/offset does not follow its started grant"
            )
        object.__setattr__(
            self,
            "projection_schema_version",
            _canonical_utf8_identifier(
                self.projection_schema_version,
                field="projection_schema_version",
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "projection_validation_version",
            _canonical_utf8_identifier(
                self.projection_validation_version,
                field="projection_validation_version",
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "pre_attempt_receipt_hash",
            canonical_hash(
                self.pre_attempt_receipt_hash, field="pre_attempt_receipt_hash"
            ),
        )
        object.__setattr__(
            self,
            "previous_operation_terminal_id",
            _optional_hash(
                self.previous_operation_terminal_id,
                field="previous_operation_terminal_id",
            ),
        )
        if (self.operation_sequence == 1) != (
            self.previous_operation_terminal_id is None
        ):
            raise CanonicalizationError(
                "only the first campaign operation may omit its prior terminal"
            )
        object.__setattr__(
            self,
            "baseline_raw_ingress_commit_id",
            _optional_hash(
                self.baseline_raw_ingress_commit_id,
                field="baseline_raw_ingress_commit_id",
            ),
        )
        object.__setattr__(
            self,
            "baseline_actor_tail_event_id",
            _optional_hash(
                self.baseline_actor_tail_event_id,
                field="baseline_actor_tail_event_id",
            ),
        )
        if (self.baseline_raw_ingress_sequence == 0) != (
            self.baseline_raw_ingress_commit_id is None
        ):
            raise CanonicalizationError(
                "baseline RAW tail must be present exactly after RAW ingress"
            )
        if (self.baseline_actor_event_count == 0) != (
            self.baseline_actor_tail_event_id is None
        ):
            raise CanonicalizationError(
                "baseline actor tail must be present exactly after actor events"
            )
        object.__setattr__(
            self, "started_at", utc_datetime(self.started_at, field="started_at")
        )
        object.__setattr__(
            self,
            "parser_cursor_id_before",
            canonical_hash(
                self.parser_cursor_id_before, field="parser_cursor_id_before"
            ),
        )
        if type(self.parser_cursor_before) is not WebSocketParserCursorV49C:
            raise CanonicalizationError(
                "parser_cursor_before must be an exact WebSocket parser cursor"
            )
        if self.parser_cursor_id_before != self.parser_cursor_before.parser_cursor_id:
            raise CanonicalizationError(
                "parser_cursor_id_before differs from exact cursor state"
            )
        object.__setattr__(
            self,
            "runtime_state_before",
            _canonical_utf8_identifier(
                self.runtime_state_before, field="runtime_state_before", maximum=64
            ),
        )
        if self.runtime_state_before not in _RUNTIME_STATE_VALUES_V49F:
            raise CanonicalizationError("runtime_state_before is unsupported")
        declaration = CapacityMeasurementOperationDeclarationV49F(
            campaign_manifest_id=self.campaign_manifest_id,
            manifest_authority_id=self.manifest_authority_id,
            measurement_design_id=self.measurement_design_id,
            workload_id=self.workload_id,
            workload_sha256=self.workload_sha256,
            sample_sequence=self.sample_sequence,
            operation_sequence=self.operation_sequence,
            trial_index=self.trial_index,
            repetition_index=self.repetition_index,
            is_warmup=self.is_warmup,
            stage=self.stage,
            operation=self.operation,
            input_chunk_count=self.input_chunk_count,
            input_octet_count=self.input_octet_count,
            input_sha256=self.input_sha256,
            raw_ingress_batch_sha256=self.raw_ingress_batch_sha256,
            timeout_seconds=self.timeout_seconds,
            expected_output_frame_count=self.expected_output_frame_count,
            expected_output_frames_sha256=self.expected_output_frames_sha256,
            declaration_id=self.declaration_id,
        )
        if declaration.declaration_id != self.declaration_id:
            raise CanonicalizationError(
                "attempt differs from its exact non-effect declaration"
            )
        identity = _semantic_id(
            domain=CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.attempt_id is not None
            and canonical_hash(self.attempt_id, field="attempt_id") != identity
        ):
            raise CanonicalizationError("attempt_id differs from canonical members")
        object.__setattr__(self, "attempt_id", identity)
        _bounded_canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                **self._identity_payload_unchecked(),
                "attempt_id": identity,
                "lifecycle_schema_version": (
                    CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
                ),
                "record_domain": CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F,
            },
            context="canonical operation attempt",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in fields(type(self)):
            if item.name == "attempt_id":
                continue
            value = getattr(self, item.name)
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, datetime):
                value = utc_iso(value)
            elif isinstance(value, TransportCapacityPolicyV49F):
                value = value.as_dict()
            elif isinstance(value, WebSocketParserCursorV49C):
                value = value.as_dict()
            elif isinstance(value, tuple):
                value = [
                    item.as_dict()
                    if isinstance(item, CapacityMeasurementRetainedRawDependencyV49F)
                    else item
                    for item in value
                ]
            result[item.name] = value
        return result

    def identity_payload(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError(
                "operation attempt was mutated after validation"
            )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        payload = self.identity_payload()
        result = {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **payload,
            "attempt_id": self.attempt_id,
            "lifecycle_schema_version": (
                CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
            ),
            "record_domain": CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F,
        }
        _bounded_canonical_bytes(
            result,
            context="canonical operation attempt",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationAttemptV49F:
        if not isinstance(payload, Mapping):
            raise CanonicalizationError("operation attempt must be a mapping")
        require_exact_keys(
            payload,
            expected=_record_field_names(cls)
            | {
                "canonicalization_version",
                "lifecycle_schema_version",
                "record_domain",
            },
            context=cls.__name__,
        )
        raw_dependencies = payload.get("retained_raw_dependencies")
        if type(raw_dependencies) is not list or len(raw_dependencies) > (
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F
        ):
            raise CanonicalizationError(
                "retained_raw_dependencies must be a bounded JSON array"
            )
        _bounded_canonical_bytes(
            payload,
            context="canonical operation attempt",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )
        raw_policy = payload.get("transport_capacity_policy")
        if not isinstance(raw_policy, Mapping):
            raise CanonicalizationError("transport_capacity_policy must be a mapping")
        normalized = dict(payload)
        normalized["transport_capacity_policy"] = (
            TransportCapacityPolicyV49F.from_mapping(raw_policy)
        )
        raw_cursor = payload.get("parser_cursor_before")
        if not isinstance(raw_cursor, Mapping):
            raise CanonicalizationError("parser_cursor_before must be a mapping")
        normalized["parser_cursor_before"] = WebSocketParserCursorV49C.from_mapping(
            raw_cursor
        )
        normalized["retained_raw_dependencies"] = tuple(
            CapacityMeasurementRetainedRawDependencyV49F.from_mapping(item)
            for item in raw_dependencies
        )
        return _decode_record(
            normalized,
            record_type=cls,
            domain=CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F,
            identity_field="attempt_id",
            enum_fields=cls._ENUM_FIELDS,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSameTaskTerminalObservationV49F:
    """Bounded post-effect facts; the store derives the terminal record."""

    terminal_trigger: CapacityMeasurementLifecycleTerminalTriggerV49F
    surfaced_exception_class: str | None
    exception_class_chain: tuple[str, ...]
    exception_message_sha256_chain: tuple[str, ...]
    runtime_state_after: str
    observer_end_offset_nanoseconds: int
    boottime_end_offset_nanoseconds: int
    loop_time_end_offset_nanoseconds: int

    def __post_init__(self) -> None:
        _exact_enum(
            self.terminal_trigger,
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            field="terminal_trigger",
        )
        if self.terminal_trigger is (
            CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
        ):
            raise CanonicalizationError(
                "same-task observation cannot claim startup recovery"
            )
        object.__setattr__(
            self,
            "surfaced_exception_class",
            _optional_identifier(
                self.surfaced_exception_class,
                field="surfaced_exception_class",
                maximum=(
                    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F
                ),
            ),
        )
        if (
            type(self.exception_class_chain) is not tuple
            or type(self.exception_message_sha256_chain) is not tuple
        ):
            raise CanonicalizationError("exception chains must be exact tuples")
        if not (
            len(self.exception_class_chain)
            == len(self.exception_message_sha256_chain)
            <= CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F
        ):
            raise CanonicalizationError(
                "exception chains differ or exceed their depth bound"
            )
        classes = tuple(
            _canonical_utf8_identifier(
                value,
                field="exception_class_chain",
                maximum=(
                    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F
                ),
            )
            for value in self.exception_class_chain
        )
        messages = tuple(
            canonical_hash(value, field="exception_message_sha256_chain")
            for value in self.exception_message_sha256_chain
        )
        object.__setattr__(self, "exception_class_chain", classes)
        object.__setattr__(self, "exception_message_sha256_chain", messages)
        if (self.surfaced_exception_class is None) != (not classes) or (
            classes and classes[0] != self.surfaced_exception_class
        ):
            raise CanonicalizationError(
                "surfaced exception must exactly head both exception chains"
            )
        returned = self.terminal_trigger is (
            CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
        )
        if returned != (self.surfaced_exception_class is None):
            raise CanonicalizationError(
                "same-task trigger differs from surfaced exception evidence"
            )
        if (
            self.terminal_trigger
            is (CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED)
            and self.surfaced_exception_class != "asyncio.exceptions.CancelledError"
        ):
            raise CanonicalizationError(
                "CANCELLED requires asyncio.exceptions.CancelledError"
            )
        runtime_state = _canonical_utf8_identifier(
            self.runtime_state_after, field="runtime_state_after", maximum=64
        )
        if runtime_state not in _RUNTIME_STATE_VALUES_V49F:
            raise CanonicalizationError("runtime_state_after is unsupported")
        object.__setattr__(self, "runtime_state_after", runtime_state)
        for name in (
            "observer_end_offset_nanoseconds",
            "boottime_end_offset_nanoseconds",
            "loop_time_end_offset_nanoseconds",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=0),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "boottime_end_offset_nanoseconds": (self.boottime_end_offset_nanoseconds),
            "exception_class_chain": list(self.exception_class_chain),
            "exception_message_sha256_chain": list(self.exception_message_sha256_chain),
            "loop_time_end_offset_nanoseconds": (self.loop_time_end_offset_nanoseconds),
            "observer_end_offset_nanoseconds": (self.observer_end_offset_nanoseconds),
            "runtime_state_after": self.runtime_state_after,
            "surfaced_exception_class": self.surfaced_exception_class,
            "terminal_trigger": self.terminal_trigger.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSameTaskTerminalObservationV49F:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        for name in ("exception_class_chain", "exception_message_sha256_chain"):
            if type(payload[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
        try:
            trigger = CapacityMeasurementLifecycleTerminalTriggerV49F(
                payload["terminal_trigger"]
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("terminal_trigger is unsupported") from exc
        return cls(
            **{
                **dict(payload),
                "terminal_trigger": trigger,
                "exception_class_chain": tuple(payload["exception_class_chain"]),
                "exception_message_sha256_chain": tuple(
                    payload["exception_message_sha256_chain"]
                ),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationTerminalV49F:
    """Exactly-once terminal classification of one durable attempt."""

    attempt_id: str
    previous_operation_terminal_id: str | None
    terminal_writer: CapacityMeasurementLifecycleTerminalWriterV49F
    terminal_trigger: CapacityMeasurementLifecycleTerminalTriggerV49F
    cancellation_classification: CapacityMeasurementLifecycleCancellationV49F
    effect_certainty: CapacityMeasurementLifecycleEffectCertaintyV49F
    progress_availability: CapacityMeasurementLifecycleProgressAvailabilityV49F
    progress_unavailable_reason: str | None
    operation_error_code: str | None
    surfaced_exception_class: str | None
    exception_class_chain: tuple[str, ...]
    exception_message_sha256_chain: tuple[str, ...]
    returned_progress_evidence_id: str | None
    terminal_raw_ingress_sequence: int
    terminal_raw_ingress_commit_id: str | None
    terminal_actor_event_count: int
    terminal_actor_tail_event_id: str | None
    parser_cursor_id_after: str | None
    runtime_state_after: str | None
    actor_terminal_state_id_after: str
    actor_terminal_outcome: str | None
    actor_terminal_cause_code: str | None
    session_terminal_authority: CapacityMeasurementSessionTerminalAuthorityV49F
    recovered_prefix_id: str
    observer_end_offset_nanoseconds: int | None
    boottime_end_offset_nanoseconds: int | None
    loop_time_end_offset_nanoseconds: int | None
    completed_at: datetime
    completed_monotonic_ns: str | None
    terminal_id: str | None = None

    _ENUM_FIELDS: ClassVar[Mapping[str, type[Enum]]] = {
        "terminal_writer": CapacityMeasurementLifecycleTerminalWriterV49F,
        "terminal_trigger": CapacityMeasurementLifecycleTerminalTriggerV49F,
        "cancellation_classification": CapacityMeasurementLifecycleCancellationV49F,
        "effect_certainty": CapacityMeasurementLifecycleEffectCertaintyV49F,
        "progress_availability": CapacityMeasurementLifecycleProgressAvailabilityV49F,
        "session_terminal_authority": CapacityMeasurementSessionTerminalAuthorityV49F,
    }

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "attempt_id", canonical_hash(self.attempt_id, field="attempt_id")
        )
        object.__setattr__(
            self,
            "previous_operation_terminal_id",
            _optional_hash(
                self.previous_operation_terminal_id,
                field="previous_operation_terminal_id",
            ),
        )
        _exact_enum(
            self.terminal_writer,
            CapacityMeasurementLifecycleTerminalWriterV49F,
            field="terminal_writer",
        )
        _exact_enum(
            self.cancellation_classification,
            CapacityMeasurementLifecycleCancellationV49F,
            field="cancellation_classification",
        )
        _exact_enum(
            self.terminal_trigger,
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            field="terminal_trigger",
        )
        _exact_enum(
            self.effect_certainty,
            CapacityMeasurementLifecycleEffectCertaintyV49F,
            field="effect_certainty",
        )
        _exact_enum(
            self.progress_availability,
            CapacityMeasurementLifecycleProgressAvailabilityV49F,
            field="progress_availability",
        )
        _exact_enum(
            self.session_terminal_authority,
            CapacityMeasurementSessionTerminalAuthorityV49F,
            field="session_terminal_authority",
        )
        for name in (
            "terminal_raw_ingress_sequence",
            "terminal_actor_event_count",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=0),
            )
        for name in (
            "observer_end_offset_nanoseconds",
            "boottime_end_offset_nanoseconds",
            "loop_time_end_offset_nanoseconds",
        ):
            value = getattr(self, name)
            if value is not None:
                value = canonical_safe_int(value, field=name, minimum=0)
            object.__setattr__(self, name, value)
        if self.completed_monotonic_ns is not None:
            object.__setattr__(
                self,
                "completed_monotonic_ns",
                _canonical_uint128_text(
                    self.completed_monotonic_ns,
                    field="completed_monotonic_ns",
                ),
            )
        object.__setattr__(
            self,
            "terminal_raw_ingress_commit_id",
            _optional_hash(
                self.terminal_raw_ingress_commit_id,
                field="terminal_raw_ingress_commit_id",
            ),
        )
        object.__setattr__(
            self,
            "terminal_actor_tail_event_id",
            _optional_hash(
                self.terminal_actor_tail_event_id,
                field="terminal_actor_tail_event_id",
            ),
        )
        if (self.terminal_raw_ingress_sequence == 0) != (
            self.terminal_raw_ingress_commit_id is None
        ):
            raise CanonicalizationError(
                "terminal RAW tail must be present exactly after RAW ingress"
            )
        if (self.terminal_actor_event_count == 0) != (
            self.terminal_actor_tail_event_id is None
        ):
            raise CanonicalizationError(
                "terminal actor tail must be present exactly after actor events"
            )
        object.__setattr__(
            self,
            "progress_unavailable_reason",
            _optional_identifier(
                self.progress_unavailable_reason,
                field="progress_unavailable_reason",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "operation_error_code",
            _optional_identifier(
                self.operation_error_code,
                field="operation_error_code",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "surfaced_exception_class",
            _optional_identifier(
                self.surfaced_exception_class,
                field="surfaced_exception_class",
                maximum=(
                    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F
                ),
            ),
        )
        if (
            type(self.exception_class_chain) is not tuple
            or type(self.exception_message_sha256_chain) is not tuple
        ):
            raise CanonicalizationError("exception chains must be exact tuples")
        if not (
            len(self.exception_class_chain)
            == len(self.exception_message_sha256_chain)
            <= CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F
        ):
            raise CanonicalizationError(
                "exception chains differ or exceed their depth bound"
            )
        normalized_classes = tuple(
            _canonical_utf8_identifier(
                value,
                field="exception_class_chain",
                maximum=(
                    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F
                ),
            )
            for value in self.exception_class_chain
        )
        normalized_messages = tuple(
            canonical_hash(value, field="exception_message_sha256_chain")
            for value in self.exception_message_sha256_chain
        )
        object.__setattr__(self, "exception_class_chain", normalized_classes)
        object.__setattr__(self, "exception_message_sha256_chain", normalized_messages)
        if (self.surfaced_exception_class is None) != (not normalized_classes):
            raise CanonicalizationError(
                "surfaced exception and exception chains must be present together"
            )
        if (
            normalized_classes
            and normalized_classes[0] != self.surfaced_exception_class
        ):
            raise CanonicalizationError(
                "surfaced exception must head the bounded exception chain"
            )
        object.__setattr__(
            self,
            "returned_progress_evidence_id",
            _optional_hash(
                self.returned_progress_evidence_id,
                field="returned_progress_evidence_id",
            ),
        )
        object.__setattr__(
            self,
            "parser_cursor_id_after",
            _optional_hash(self.parser_cursor_id_after, field="parser_cursor_id_after"),
        )
        object.__setattr__(
            self,
            "actor_terminal_state_id_after",
            canonical_hash(
                self.actor_terminal_state_id_after,
                field="actor_terminal_state_id_after",
            ),
        )
        object.__setattr__(
            self,
            "runtime_state_after",
            _optional_identifier(
                self.runtime_state_after,
                field="runtime_state_after",
                maximum=64,
            ),
        )
        if (
            self.runtime_state_after is not None
            and self.runtime_state_after not in _RUNTIME_STATE_VALUES_V49F
        ):
            raise CanonicalizationError("runtime_state_after is unsupported")
        object.__setattr__(
            self,
            "actor_terminal_outcome",
            _optional_identifier(
                self.actor_terminal_outcome,
                field="actor_terminal_outcome",
                maximum=64,
            ),
        )
        if self.actor_terminal_outcome is not None:
            try:
                TerminalOutcomeV49C(self.actor_terminal_outcome)
            except ValueError as exc:
                raise CanonicalizationError(
                    "actor_terminal_outcome is unsupported"
                ) from exc
        object.__setattr__(
            self,
            "actor_terminal_cause_code",
            _optional_identifier(
                self.actor_terminal_cause_code,
                field="actor_terminal_cause_code",
                maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F,
            ),
        )
        object.__setattr__(
            self,
            "recovered_prefix_id",
            canonical_hash(self.recovered_prefix_id, field="recovered_prefix_id"),
        )
        unavailable = (
            self.progress_availability
            is CapacityMeasurementLifecycleProgressAvailabilityV49F.UNAVAILABLE
        )
        if unavailable != (self.progress_unavailable_reason is not None):
            raise CanonicalizationError(
                "progress unavailable reason must be present exactly for UNAVAILABLE"
            )
        if (
            self.progress_availability
            is CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_RETURNED_PROGRESS
            and self.terminal_trigger
            is not CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
        ):
            raise CanonicalizationError(
                "exact returned progress requires a RETURN terminal trigger"
            )
        returned = (
            self.terminal_trigger
            is CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
        )
        expected_error_code = {
            CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED: None,
            CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED: (
                "ASYNCIO_CANCELLED_ERROR"
            ),
            CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED: (
                "PYTHON_BASE_EXCEPTION"
            ),
            CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION: (
                "PYTHON_EXCEPTION"
            ),
            CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN: (
                "PROCESS_LOSS_UNKNOWN"
            ),
        }[self.terminal_trigger]
        if self.operation_error_code != expected_error_code:
            raise CanonicalizationError(
                "operation_error_code differs from the exact terminal trigger"
            )
        exact_returned = (
            self.progress_availability
            is CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_RETURNED_PROGRESS
        )
        if returned != exact_returned or returned != (
            self.returned_progress_evidence_id is not None
        ):
            raise CanonicalizationError(
                "RETURN requires exactly one returned-progress identity and availability"
            )
        if (
            self.effect_certainty
            is CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE
        ) != returned:
            raise CanonicalizationError(
                "COMPLETE effect certainty is reserved for an exact returned result"
            )
        cancelled = (
            self.terminal_trigger
            is CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
        )
        if cancelled != (
            self.cancellation_classification
            is CapacityMeasurementLifecycleCancellationV49F.ASYNCIO_CANCELLED_ERROR
        ):
            raise CanonicalizationError(
                "cancellation classification differs from the terminal trigger"
            )
        recovery = (
            self.terminal_trigger
            is CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
        )
        if recovery != (
            self.terminal_writer
            is CapacityMeasurementLifecycleTerminalWriterV49F.STARTUP_RECOVERY
        ):
            raise CanonicalizationError(
                "startup recovery writer must be used exactly for process-loss recovery"
            )
        process_loss_classification = (
            self.cancellation_classification
            is CapacityMeasurementLifecycleCancellationV49F.PROCESS_LOSS_UNKNOWN
        )
        if recovery != process_loss_classification:
            raise CanonicalizationError(
                "process-loss cancellation uncertainty is recovery-only"
            )
        if (
            not recovery
            and not cancelled
            and (
                self.cancellation_classification
                is not CapacityMeasurementLifecycleCancellationV49F.NONE
            )
        ):
            raise CanonicalizationError(
                "non-cancelled same-task terminal requires cancellation NONE"
            )
        if returned:
            if (
                self.operation_error_code is not None
                or self.surfaced_exception_class is not None
            ):
                raise CanonicalizationError(
                    "RETURN terminal cannot carry an operation error"
                )
        elif recovery:
            if (
                self.operation_error_code is None
                or self.surfaced_exception_class is not None
            ):
                raise CanonicalizationError(
                    "process-loss recovery requires a code and no synthetic exception"
                )
        elif self.operation_error_code is None or self.surfaced_exception_class is None:
            raise CanonicalizationError(
                "exception and cancellation terminals require exact error metadata"
            )
        if cancelled and self.surfaced_exception_class != (
            "asyncio.exceptions.CancelledError"
        ):
            raise CanonicalizationError(
                "CANCELLED requires asyncio.exceptions.CancelledError"
            )
        durable_terminal = (
            self.session_terminal_authority
            is CapacityMeasurementSessionTerminalAuthorityV49F.DURABLE_ACTOR_TERMINAL
        )
        if durable_terminal != (self.actor_terminal_outcome is not None):
            raise CanonicalizationError(
                "durable actor-terminal authority requires its exact outcome"
            )
        if not durable_terminal and self.actor_terminal_cause_code is not None:
            raise CanonicalizationError(
                "non-durable session authority cannot carry an actor terminal cause"
            )
        if durable_terminal and (
            self.actor_terminal_outcome == TerminalOutcomeV49C.CLEAN_ALL_LAYERS.value
        ) != (self.actor_terminal_cause_code is None):
            raise CanonicalizationError(
                "actor terminal outcome and cause have an invalid exact shape"
            )
        orphan_authority = (
            self.session_terminal_authority
            is CapacityMeasurementSessionTerminalAuthorityV49F.UNAVAILABLE_AFTER_ORPHAN
        )
        if recovery != orphan_authority:
            raise CanonicalizationError(
                "orphan recovery must use unavailable-after-orphan session authority"
            )
        volatile_end_values = (
            self.runtime_state_after,
            self.observer_end_offset_nanoseconds,
            self.boottime_end_offset_nanoseconds,
            self.loop_time_end_offset_nanoseconds,
            self.completed_monotonic_ns,
        )
        if recovery:
            if any(value is not None for value in volatile_end_values):
                raise CanonicalizationError(
                    "orphan recovery cannot fabricate volatile runtime/clock facts"
                )
        elif self.parser_cursor_id_after is None or any(
            value is None for value in volatile_end_values
        ):
            raise CanonicalizationError(
                "same-task terminal requires complete parser/runtime/clock facts"
            )
        object.__setattr__(
            self,
            "completed_at",
            utc_datetime(self.completed_at, field="completed_at"),
        )
        identity = _semantic_id(
            domain=CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.terminal_id is not None
            and canonical_hash(self.terminal_id, field="terminal_id") != identity
        ):
            raise CanonicalizationError("terminal_id differs from canonical members")
        object.__setattr__(self, "terminal_id", identity)
        _bounded_canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                **self._identity_payload_unchecked(),
                "lifecycle_schema_version": (
                    CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
                ),
                "record_domain": CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F,
                "terminal_id": identity,
            },
            context="canonical operation terminal",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in fields(type(self)):
            if item.name == "terminal_id":
                continue
            value = getattr(self, item.name)
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, datetime):
                value = utc_iso(value)
            elif isinstance(value, tuple):
                value = list(value)
            result[item.name] = value
        return result

    def identity_payload(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError(
                "operation terminal was mutated after validation"
            )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        payload = self.identity_payload()
        result = {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **payload,
            "lifecycle_schema_version": (
                CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
            ),
            "record_domain": CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F,
            "terminal_id": self.terminal_id,
        }
        _bounded_canonical_bytes(
            result,
            context="canonical operation terminal",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationTerminalV49F:
        if not isinstance(payload, Mapping):
            raise CanonicalizationError("operation terminal must be a mapping")
        require_exact_keys(
            payload,
            expected=_record_field_names(cls)
            | {
                "canonicalization_version",
                "lifecycle_schema_version",
                "record_domain",
            },
            context=cls.__name__,
        )
        for name in ("exception_class_chain", "exception_message_sha256_chain"):
            raw = payload.get(name)
            if type(raw) is not list or len(raw) > (
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F
            ):
                raise CanonicalizationError(f"{name} must be a bounded JSON array")
        _bounded_canonical_bytes(
            payload,
            context="canonical operation terminal",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECORD_BYTES_V49F,
        )
        normalized = dict(payload)
        normalized["exception_class_chain"] = tuple(payload["exception_class_chain"])
        normalized["exception_message_sha256_chain"] = tuple(
            payload["exception_message_sha256_chain"]
        )
        return _decode_record(
            normalized,
            record_type=cls,
            domain=CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F,
            identity_field="terminal_id",
            enum_fields=cls._ENUM_FIELDS,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementProjectionReceiptEvidenceV49F:
    """Serializable exact projection receipt, including its ledger authority."""

    ledger_id: str
    global_sequence: int
    receipt_hash: str
    previous_receipt_hash: str
    record_kind: str
    identity_id: str
    content_hash: str
    committed_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "ledger_id",
            "receipt_hash",
            "previous_receipt_hash",
            "identity_id",
            "content_hash",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "global_sequence",
            canonical_safe_int(
                self.global_sequence, field="global_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "record_kind",
            _canonical_utf8_identifier(
                self.record_kind, field="record_kind", maximum=128
            ),
        )
        object.__setattr__(
            self,
            "committed_at",
            utc_datetime(self.committed_at, field="committed_at"),
        )
        expected = hashlib.sha256(
            canonical_json_bytes(
                {
                    "content_hash": self.content_hash,
                    "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
                    "global_sequence": self.global_sequence,
                    "identity_id": self.identity_id,
                    "ledger_id": self.ledger_id,
                    "previous_receipt_hash": self.previous_receipt_hash,
                    "record_kind": self.record_kind,
                }
            )
        ).hexdigest()
        if self.receipt_hash != expected:
            raise CanonicalizationError(
                "projection receipt hash differs from its exact semantic members"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "committed_at": utc_iso(self.committed_at),
            "content_hash": self.content_hash,
            "global_sequence": self.global_sequence,
            "identity_id": self.identity_id,
            "ledger_id": self.ledger_id,
            "previous_receipt_hash": self.previous_receipt_hash,
            "receipt_hash": self.receipt_hash,
            "record_kind": self.record_kind,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementProjectionReceiptEvidenceV49F:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementProjectionRecordEvidenceV49F:
    """Canonical bytes paired one-to-one with a reconstructed receipt."""

    record_kind: str
    identity_id: str
    content_hash: str
    canonical_record_base64: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_kind",
            _canonical_utf8_identifier(
                self.record_kind, field="record_kind", maximum=128
            ),
        )
        for name in ("identity_id", "content_hash"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        decoded = _canonical_base64(
            self.canonical_record_base64,
            field="canonical_record_base64",
            maximum_decoded_octets=(
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F
            ),
        )
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(decoded)
        value = strict_json_loads(decoded)
        if (
            not isinstance(value, Mapping)
            or canonical_json_bytes(dict(value)) != decoded
        ):
            raise CanonicalizationError(
                "projection record evidence must contain canonical JSON object bytes"
            )
        if hashlib.sha256(decoded).hexdigest() != self.content_hash:
            raise CanonicalizationError(
                "projection record content hash differs from canonical bytes"
            )

    @property
    def canonical_record_bytes(self) -> bytes:
        return _canonical_base64(
            self.canonical_record_base64,
            field="canonical_record_base64",
            maximum_decoded_octets=(
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_record_base64": self.canonical_record_base64,
            "content_hash": self.content_hash,
            "identity_id": self.identity_id,
            "record_kind": self.record_kind,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementProjectionRecordEvidenceV49F:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementOperationPrefixV49F:
    """Receipt-complete, canonical reconstruction of one operation prefix.

    ``recovered_prefix_id`` commits the pre-terminal subject.  A terminal can
    therefore commit that identity without depending on its own future receipt.
    ``prefix_id`` is a separate final/export identity which also commits the
    terminal and its receipt.  Keeping these domains separate prevents a hash
    cycle while preserving attempt-through-terminal receipt closure.
    """

    attempt: CapacityMeasurementOperationAttemptV49F
    terminal: CapacityMeasurementOperationTerminalV49F | None
    new_raw_ingress_commits: tuple[RawIngressCommitV4, ...]
    raw_dependencies: tuple[RawIngressCommitV4, ...]
    actor_events: tuple[TransportActorEventV49C, ...]
    projection_receipts: tuple[CapacityMeasurementProjectionReceiptEvidenceV49F, ...]
    projection_records: tuple[CapacityMeasurementProjectionRecordEvidenceV49F, ...]
    recovered_prefix_id: str | None = None
    prefix_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.attempt) is not CapacityMeasurementOperationAttemptV49F:
            raise CanonicalizationError(
                "prefix attempt must be an exact lifecycle attempt"
            )
        if self.terminal is not None and (
            type(self.terminal) is not CapacityMeasurementOperationTerminalV49F
            or self.terminal.attempt_id != self.attempt.attempt_id
        ):
            raise CanonicalizationError("prefix terminal does not close its attempt")
        for name, expected_type in (
            (
                "projection_receipts",
                CapacityMeasurementProjectionReceiptEvidenceV49F,
            ),
            (
                "projection_records",
                CapacityMeasurementProjectionRecordEvidenceV49F,
            ),
        ):
            values = getattr(self, name)
            if type(values) is not tuple or any(
                type(item) is not expected_type for item in values
            ):
                raise CanonicalizationError(f"{name} must be an exact tuple")
            if not values or len(values) > (
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECEIPTS_V49F
            ):
                raise CanonicalizationError(f"{name} count is outside its bound")
        if len(self.projection_receipts) != len(self.projection_records):
            raise CanonicalizationError(
                "projection receipt and canonical-record evidence counts differ"
            )
        if type(self.new_raw_ingress_commits) is not tuple or any(
            type(item) is not RawIngressCommitV4
            for item in self.new_raw_ingress_commits
        ):
            raise CanonicalizationError("new prefix RAW records must be an exact tuple")
        if len(self.new_raw_ingress_commits) > 1:
            raise CanonicalizationError(
                "one ingress operation cannot append more than one RAW batch"
            )
        if type(self.raw_dependencies) is not tuple or any(
            type(item) is not RawIngressCommitV4 for item in self.raw_dependencies
        ):
            raise CanonicalizationError("RAW dependencies must be an exact tuple")
        if len(self.raw_dependencies) > (
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F
        ):
            raise CanonicalizationError("RAW dependency count exceeds its bound")
        dependency_ids = tuple(
            item.raw_ingress_commit_id for item in self.raw_dependencies
        )
        if len(set(dependency_ids)) != len(dependency_ids) or tuple(
            item.ingress_sequence for item in self.raw_dependencies
        ) != tuple(sorted(item.ingress_sequence for item in self.raw_dependencies)):
            raise CanonicalizationError(
                "RAW dependencies must be unique and ordered by ingress sequence"
            )
        if any(
            item.transport_session_id != self.attempt.transport_session_id
            for item in self.raw_dependencies
        ):
            raise CanonicalizationError("RAW dependency leaves the attempt session")
        if any(
            item.writer_fence_token_sha256 != self.attempt.writer_fence_token_sha256
            or item.writer_fence_generation != self.attempt.writer_fence_generation
            or item.monotonic_clock_domain_id != self.attempt.monotonic_clock_domain_id
            for item in self.raw_dependencies
        ):
            raise CanonicalizationError(
                "RAW dependency leaves the attempt writer/clock authority"
            )
        if type(self.actor_events) is not tuple or any(
            type(item) is not TransportActorEventV49C for item in self.actor_events
        ):
            raise CanonicalizationError("prefix actor records must be an exact tuple")
        if len(self.actor_events) > (
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F
        ):
            raise CanonicalizationError("prefix actor event count exceeds its bound")
        if any(
            item.writer_fence_token_sha256 != self.attempt.writer_fence_token_sha256
            or item.writer_fence_generation != self.attempt.writer_fence_generation
            or item.monotonic_clock_domain_id != self.attempt.monotonic_clock_domain_id
            for item in self.actor_events
        ):
            raise CanonicalizationError(
                "actor prefix leaves the attempt writer/clock authority"
            )
        expected_raw_sequence = self.attempt.baseline_raw_ingress_sequence + 1
        for item in self.new_raw_ingress_commits:
            if (
                item.transport_session_id != self.attempt.transport_session_id
                or item.ingress_sequence != expected_raw_sequence
            ):
                raise CanonicalizationError("prefix RAW records are not gap-free")
            expected_raw_sequence += 1
        expected_actor_sequence = self.attempt.baseline_actor_event_count + 1
        for item in self.actor_events:
            if (
                item.transport_session_id != self.attempt.transport_session_id
                or item.actor_sequence != expected_actor_sequence
            ):
                raise CanonicalizationError("prefix actor records are not gap-free")
            expected_actor_sequence += 1
        if self.actor_events and (
            self.actor_events[0].previous_event_id
            != self.attempt.baseline_actor_tail_event_id
        ):
            raise CanonicalizationError(
                "first prefix actor event does not extend the attempt baseline"
            )
        for previous, current in zip(self.actor_events, self.actor_events[1:]):
            if current.previous_event_id != previous.transport_actor_event_id:
                raise CanonicalizationError("prefix actor events are not hash-linked")
        parser_cursor = self.attempt.parser_cursor_before
        for event in self.actor_events:
            if event.event_kind.value != "PARSER_TRANSITION":
                continue
            payload = event.payload
            if payload.cursor_before != parser_cursor:
                raise CanonicalizationError(
                    "prefix parser transition does not extend the attempt cursor"
                )
            parser_cursor = payload.cursor_after

        receipts = self.projection_receipts
        records = self.projection_records
        ledger_ids = {item.ledger_id for item in receipts}
        if ledger_ids != {self.attempt.projection_ledger_id}:
            raise CanonicalizationError("prefix receipts leave the attempt ledger")
        if (
            receipts[0].global_sequence != self.attempt.pre_attempt_receipt_sequence + 1
            or receipts[0].previous_receipt_hash
            != self.attempt.pre_attempt_receipt_hash
            or receipts[0].record_kind != _ATTEMPT_RECORD_KIND_V49F
            or receipts[0].identity_id != self.attempt.attempt_id
        ):
            raise CanonicalizationError(
                "attempt receipt does not extend its declared pre-attempt anchor"
            )
        for previous, current in zip(receipts, receipts[1:]):
            if (
                current.global_sequence != previous.global_sequence + 1
                or current.previous_receipt_hash != previous.receipt_hash
            ):
                raise CanonicalizationError(
                    "projection receipts are not contiguous and hash-linked"
                )
        for receipt, record in zip(receipts, records):
            if (
                receipt.record_kind != record.record_kind
                or receipt.identity_id != record.identity_id
                or receipt.content_hash != record.content_hash
            ):
                raise CanonicalizationError(
                    "projection receipt differs from its canonical record evidence"
                )

        expected_known_records: dict[tuple[str, str], bytes] = {
            (_ATTEMPT_RECORD_KIND_V49F, str(self.attempt.attempt_id)): (
                canonical_json_bytes(self.attempt.as_dict())
            )
        }
        for raw in self.new_raw_ingress_commits:
            expected_known_records[
                (_RAW_RECORD_KIND_V49F, raw.raw_ingress_commit_id)
            ] = canonical_json_bytes(raw.as_dict())
        for event in self.actor_events:
            expected_known_records[
                (_ACTOR_RECORD_KIND_V49F, event.transport_actor_event_id)
            ] = canonical_json_bytes(event.as_dict())
        if self.terminal is not None:
            expected_known_records[
                (_TERMINAL_RECORD_KIND_V49F, str(self.terminal.terminal_id))
            ] = canonical_json_bytes(self.terminal.as_dict())
        evidence_by_key = {
            (record.record_kind, record.identity_id): record for record in records
        }
        if len(evidence_by_key) != len(records):
            raise CanonicalizationError(
                "projection record evidence contains duplicate identities"
            )
        for key, expected_blob in expected_known_records.items():
            evidence = evidence_by_key.get(key)
            if evidence is None or evidence.canonical_record_bytes != expected_blob:
                raise CanonicalizationError(
                    "canonical prefix record is missing or content-substituted"
                )

        raw_by_id = {item.raw_ingress_commit_id: item for item in self.raw_dependencies}
        raw_actor_payloads: dict[str, Any] = {}
        dependency_references: set[str] = set()
        for event in self.actor_events:
            payload = event.payload
            # Importing the actor payload types here would only duplicate the
            # module import above; exact event construction already fixes the
            # payload type for each closed event kind.
            if event.event_kind.value == "RAW_INGRESS_COMMITTED":
                raw_id = payload.raw_ingress_commit_id
                if raw_id in raw_actor_payloads:
                    raise CanonicalizationError(
                        "multiple actor events claim one RAW dependency"
                    )
                raw_actor_payloads[raw_id] = payload
                dependency_references.add(raw_id)
            elif event.event_kind.value == "PARSER_TRANSITION":
                dependency_references.update(
                    source.raw_ingress_commit_id for source in payload.source_slices
                )
        retained_witness_by_id = {
            item.raw_ingress_commit_id: item
            for item in self.attempt.retained_raw_dependencies
        }
        if set(raw_by_id) != dependency_references | set(retained_witness_by_id):
            raise CanonicalizationError(
                "RAW dependencies differ from exact actor source references"
            )
        for raw_id, witness in retained_witness_by_id.items():
            raw = raw_by_id[raw_id]
            if (
                raw.ingress_sequence > self.attempt.baseline_raw_ingress_sequence
                or hashlib.sha256(canonical_json_bytes(raw.as_dict())).hexdigest()
                != witness.content_hash
            ):
                raise CanonicalizationError(
                    "retained RAW dependency differs from its attempt-time witness"
                )
        if {item.raw_ingress_commit_id for item in self.new_raw_ingress_commits} != set(
            raw_actor_payloads
        ):
            raise CanonicalizationError(
                "new RAW commits differ from RAW actor-event mappings"
            )
        receipt_by_key = {
            (receipt.record_kind, receipt.identity_id): receipt for receipt in receipts
        }
        for event in self.actor_events:
            if event.event_kind.value != "PARSER_TRANSITION":
                continue
            for source in event.payload.source_slices:
                witness = retained_witness_by_id.get(source.raw_ingress_commit_id)
                new_receipt = receipt_by_key.get(
                    (_RAW_RECORD_KIND_V49F, source.raw_ingress_commit_id)
                )
                if witness is not None:
                    coordinates = (
                        witness.original_receipt_sequence,
                        witness.original_receipt_hash,
                    )
                elif new_receipt is not None:
                    coordinates = (
                        new_receipt.global_sequence,
                        new_receipt.receipt_hash,
                    )
                else:
                    raise CanonicalizationError(
                        "parser RAW source has no same-ledger membership witness"
                    )
                if coordinates != (
                    source.projection_receipt_sequence,
                    source.projection_receipt_hash,
                ):
                    raise CanonicalizationError(
                        "parser RAW source receipt differs from its membership witness"
                    )
        for raw_id, payload in raw_actor_payloads.items():
            raw = raw_by_id.get(raw_id)
            receipt = receipt_by_key.get((_RAW_RECORD_KIND_V49F, raw_id))
            if raw is None or receipt is None:
                raise CanonicalizationError(
                    "RAW actor event cannot resolve one receipt-backed RAW record"
                )
            chunks = tuple(
                base64.b64decode(value, validate=True)
                for value in raw.raw_ingress_chunks_base64
            )
            previous_raw_id = (
                None
                if raw.ingress_sequence == 1
                else (
                    self.attempt.baseline_raw_ingress_commit_id
                    if raw.ingress_sequence
                    == self.attempt.baseline_raw_ingress_sequence + 1
                    else None
                )
            )
            if (
                payload.receipt.ledger_id != receipt.ledger_id
                or payload.receipt.global_sequence != receipt.global_sequence
                or payload.receipt.receipt_hash != receipt.receipt_hash
                or payload.receipt.previous_receipt_hash
                != receipt.previous_receipt_hash
                or payload.receipt.record_kind != receipt.record_kind
                or payload.receipt.identity_id != receipt.identity_id
                or payload.receipt.content_hash != receipt.content_hash
                or payload.receipt.committed_at != receipt.committed_at
                or payload.ingress_sequence != raw.ingress_sequence
                or payload.previous_raw_ingress_commit_id != previous_raw_id
                or payload.stream_end_octet - payload.stream_start_octet
                != len(raw.raw_bytes)
                or payload.ordered_chunk_octet_lengths
                != tuple(len(chunk) for chunk in chunks)
                or payload.ordered_chunk_sha256 != raw.raw_ingress_chunks_sha256
                or payload.raw_ingress_batch_sha256 != raw.raw_ingress_batch_sha256
                or payload.received_at != raw.received_at
                or payload.received_monotonic_ns != raw.received_monotonic_ns
            ):
                raise CanonicalizationError(
                    "RAW actor event differs from its exact RAW record and receipt"
                )
        if self.new_raw_ingress_commits:
            raw = self.new_raw_ingress_commits[0]
            if (
                raw.raw_ingress_batch_sha256 != self.attempt.raw_ingress_batch_sha256
                or len(raw.raw_ingress_chunks_base64) != self.attempt.input_chunk_count
                or len(raw.raw_bytes) != self.attempt.input_octet_count
                or hashlib.sha256(raw.raw_bytes).hexdigest()
                != self.attempt.input_sha256
            ):
                raise CanonicalizationError(
                    "new RAW record differs from the declared ingress workload"
                )
        if self.terminal is not None:
            raw_tail_id = (
                self.attempt.baseline_raw_ingress_commit_id
                if not self.new_raw_ingress_commits
                else self.new_raw_ingress_commits[-1].raw_ingress_commit_id
            )
            actor_tail_id = (
                self.attempt.baseline_actor_tail_event_id
                if not self.actor_events
                else self.actor_events[-1].transport_actor_event_id
            )
            if (
                self.terminal.terminal_raw_ingress_sequence != expected_raw_sequence - 1
                or self.terminal.terminal_raw_ingress_commit_id != raw_tail_id
                or self.terminal.terminal_actor_event_count
                != expected_actor_sequence - 1
                or self.terminal.terminal_actor_tail_event_id != actor_tail_id
            ):
                raise CanonicalizationError(
                    "prefix records differ from terminal durable coordinates"
                )
            if (
                self.terminal.parser_cursor_id_after is not None
                and self.terminal.parser_cursor_id_after
                != parser_cursor.parser_cursor_id
            ):
                raise CanonicalizationError(
                    "terminal parser cursor differs from exact offline prefix replay"
                )

        terminal_receipt = self.terminal is not None
        if terminal_receipt and (
            receipts[-1].record_kind != _TERMINAL_RECORD_KIND_V49F
            or receipts[-1].identity_id != self.terminal.terminal_id
        ):
            raise CanonicalizationError(
                "final prefix does not end at its exact terminal receipt"
            )
        recovered_receipts = receipts[:-1] if terminal_receipt else receipts
        recovered_records = records[:-1] if terminal_receipt else records
        recovered_identity = _semantic_id(
            domain=CAPACITY_MEASUREMENT_RECOVERED_PREFIX_DOMAIN_V49F,
            payload=self._recovered_identity_payload(
                recovered_receipts=recovered_receipts,
                recovered_records=recovered_records,
            ),
        )
        if (
            self.recovered_prefix_id is not None
            and canonical_hash(self.recovered_prefix_id, field="recovered_prefix_id")
            != recovered_identity
        ):
            raise CanonicalizationError(
                "recovered_prefix_id differs from the exact pre-terminal prefix"
            )
        object.__setattr__(self, "recovered_prefix_id", recovered_identity)
        if self.terminal is not None and (
            self.terminal.recovered_prefix_id != recovered_identity
        ):
            raise CanonicalizationError(
                "terminal recovered-prefix commitment differs from replay"
            )
        final_identity = _semantic_id(
            domain=CAPACITY_MEASUREMENT_FINAL_PREFIX_DOMAIN_V49F,
            payload=self._final_identity_payload_unchecked(),
        )
        if self.prefix_id is not None and (
            canonical_hash(self.prefix_id, field="prefix_id") != final_identity
        ):
            raise CanonicalizationError("prefix_id differs from canonical members")
        object.__setattr__(self, "prefix_id", final_identity)
        _bounded_canonical_bytes(
            self.as_dict_unchecked(),
            context="canonical operation prefix",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F,
        )

    def _recovered_identity_payload(
        self,
        *,
        recovered_receipts: tuple[
            CapacityMeasurementProjectionReceiptEvidenceV49F, ...
        ],
        recovered_records: tuple[CapacityMeasurementProjectionRecordEvidenceV49F, ...],
    ) -> dict[str, Any]:
        return {
            "actor_events": [item.as_dict() for item in self.actor_events],
            "attempt": self.attempt.as_dict(),
            "new_raw_ingress_commits": [
                item.as_dict() for item in self.new_raw_ingress_commits
            ],
            "projection_receipts": [item.as_dict() for item in recovered_receipts],
            "projection_records": [item.as_dict() for item in recovered_records],
            "raw_dependencies": [item.as_dict() for item in self.raw_dependencies],
        }

    def _final_identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "actor_events": [item.as_dict() for item in self.actor_events],
            "attempt": self.attempt.as_dict(),
            "new_raw_ingress_commits": [
                item.as_dict() for item in self.new_raw_ingress_commits
            ],
            "projection_receipts": [
                item.as_dict() for item in self.projection_receipts
            ],
            "projection_records": [item.as_dict() for item in self.projection_records],
            "raw_dependencies": [item.as_dict() for item in self.raw_dependencies],
            "recovered_prefix_id": self.recovered_prefix_id,
            "terminal": None if self.terminal is None else self.terminal.as_dict(),
        }

    def as_dict_unchecked(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self._final_identity_payload_unchecked(),
            "lifecycle_schema_version": (
                CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
            ),
            "prefix_id": self.prefix_id,
            "record_domain": CAPACITY_MEASUREMENT_FINAL_PREFIX_DOMAIN_V49F,
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("operation prefix was mutated after validation")
        result = self.as_dict_unchecked()
        _bounded_canonical_bytes(
            result,
            context="canonical operation prefix",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F,
        )
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementOperationPrefixV49F:
        if not isinstance(payload, Mapping):
            raise CanonicalizationError("operation prefix must be a mapping")
        expected = {
            "actor_events",
            "attempt",
            "canonicalization_version",
            "lifecycle_schema_version",
            "new_raw_ingress_commits",
            "prefix_id",
            "projection_receipts",
            "projection_records",
            "raw_dependencies",
            "record_domain",
            "recovered_prefix_id",
            "terminal",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("prefix canonicalization version differs")
        if payload["lifecycle_schema_version"] != (
            CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F
        ):
            raise CanonicalizationError("prefix lifecycle schema version differs")
        if payload["record_domain"] != CAPACITY_MEASUREMENT_FINAL_PREFIX_DOMAIN_V49F:
            raise CanonicalizationError("prefix record domain differs")
        for name, maximum in (
            ("new_raw_ingress_commits", 1),
            (
                "raw_dependencies",
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F,
            ),
            (
                "actor_events",
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F,
            ),
            (
                "projection_receipts",
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECEIPTS_V49F,
            ),
            (
                "projection_records",
                CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RECEIPTS_V49F,
            ),
        ):
            value = payload[name]
            if type(value) is not list or len(value) > maximum:
                raise CanonicalizationError(f"{name} must be a bounded JSON array")
        _bounded_canonical_bytes(
            payload,
            context="canonical operation prefix",
            maximum=CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F,
        )
        attempt_payload = payload["attempt"]
        terminal_payload = payload["terminal"]
        if not isinstance(attempt_payload, Mapping) or (
            terminal_payload is not None and not isinstance(terminal_payload, Mapping)
        ):
            raise CanonicalizationError("prefix lifecycle records must be mappings")
        return cls(
            attempt=CapacityMeasurementOperationAttemptV49F.from_mapping(
                attempt_payload
            ),
            terminal=(
                None
                if terminal_payload is None
                else CapacityMeasurementOperationTerminalV49F.from_mapping(
                    terminal_payload
                )
            ),
            new_raw_ingress_commits=tuple(
                RawIngressCommitV4.from_mapping(item)
                for item in payload["new_raw_ingress_commits"]
            ),
            raw_dependencies=tuple(
                RawIngressCommitV4.from_mapping(item)
                for item in payload["raw_dependencies"]
            ),
            actor_events=tuple(
                TransportActorEventV49C.from_mapping(item)
                for item in payload["actor_events"]
            ),
            projection_receipts=tuple(
                CapacityMeasurementProjectionReceiptEvidenceV49F.from_mapping(item)
                for item in payload["projection_receipts"]
            ),
            projection_records=tuple(
                CapacityMeasurementProjectionRecordEvidenceV49F.from_mapping(item)
                for item in payload["projection_records"]
            ),
            recovered_prefix_id=payload["recovered_prefix_id"],
            prefix_id=payload["prefix_id"],
        )


__all__ = [
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_CHARACTERS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ERROR_CODE_UTF8_BYTES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_CHARACTERS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CLASS_UTF8_BYTES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_CHARACTERS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_IDENTIFIER_UTF8_BYTES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_CHUNKS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_INPUT_OCTETS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_PREFIX_BYTES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_CHARACTERS_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_STAGE_UTF8_BYTES_V49F",
    "CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F",
    "CAPACITY_MEASUREMENT_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED_V49F_V7",
    "CAPACITY_MEASUREMENT_JSON_DEPTH_LIMIT_EXCEEDED_V49F_V7",
    "CAPACITY_MEASUREMENT_JSON_MALFORMED_STRUCTURE_V49F_V7",
    "CAPACITY_MEASUREMENT_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED_V49F_V7",
    "CAPACITY_MEASUREMENT_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F_V7",
    "CAPACITY_MEASUREMENT_MAXIMUM_JSON_NESTING_DEPTH_V49F_V7",
    "CAPACITY_MEASUREMENT_MAXIMUM_JSON_OBJECT_MEMBERS_V49F_V7",
    "CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_DOMAIN_V49F",
    "CAPACITY_MEASUREMENT_OPERATION_DECLARATION_DOMAIN_V49F",
    "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_DOMAIN_V49F",
    "CAPACITY_MEASUREMENT_RECOVERED_PREFIX_DOMAIN_V49F",
    "CAPACITY_MEASUREMENT_FINAL_PREFIX_DOMAIN_V49F",
    "CapacityMeasurementLifecycleEffectCertaintyV49F",
    "CapacityMeasurementLifecycleCancellationV49F",
    "CapacityMeasurementLifecycleOperationV49F",
    "CapacityMeasurementLifecycleProgressAvailabilityV49F",
    "CapacityMeasurementLifecycleTerminalTriggerV49F",
    "CapacityMeasurementLifecycleTerminalWriterV49F",
    "CapacityMeasurementSessionTerminalAuthorityV49F",
    "CapacityMeasurementOperationAttemptV49F",
    "CapacityMeasurementOperationDeclarationV49F",
    "CapacityMeasurementOperationPrefixV49F",
    "CapacityMeasurementOperationTerminalV49F",
    "CapacityMeasurementProjectionReceiptEvidenceV49F",
    "CapacityMeasurementProjectionRecordEvidenceV49F",
    "CapacityMeasurementRetainedRawDependencyV49F",
    "CapacityMeasurementSameTaskTerminalObservationV49F",
    "validate_capacity_measurement_json_structure_before_parse_v49f_v7",
]

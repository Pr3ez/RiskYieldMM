"""Exploratory-only physical-transport raw-evidence contracts (V4.9F-A2-M).

This module intentionally persists observations, not performance conclusions.
It has no calibration, confirmation, summary, threshold, or runtime-policy
surface.  One evidence bundle is an exact four-member byte closure:
``manifest.json``, ``samples.jsonl``, ``correctness.json``, and
``integrity.json``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, ClassVar, Protocol, TypeVar

from .canonical import (
    CANONICALIZATION_VERSION,
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_iso,
)
from .physical_transport_capacity_lifecycle_v49f import (
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleOperationV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationAttemptV49F,
    CapacityMeasurementOperationPrefixV49F,
    CapacityMeasurementOperationTerminalV49F,
    CapacityMeasurementProjectionReceiptEvidenceV49F,
    validate_capacity_measurement_json_structure_before_parse_v49f_v7,
)
from .physical_transport_capacity_manifest_authority_v49f import (
    A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7,
    A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F,
    CapacityMeasurementActorBaselineV49FV7,
    CapacityMeasurementLifecycleContractV49FV7,
    CapacityMeasurementManifestAuthorityV49F,
    CapacityMeasurementManifestAuthorityV49FV7,
    CapacityMeasurementManifestRequestV49F,
    CapacityMeasurementProcessEnvironmentObservationV49F,
    CapacityMeasurementProjectionAuthorityV49FV7,
    CapacityMeasurementRuntimeObservationV49F,
    CapacityMeasurementSourceInventoryV49FV7,
)
from .physical_transport_capacity_source_observation_v49f import (
    RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
    SourceObservationSnapshotV49F,
)

MANIFEST_ARTIFACT_NAME_V49F = "manifest.json"
SAMPLES_ARTIFACT_NAME_V49F = "samples.jsonl"
CORRECTNESS_ARTIFACT_NAME_V49F = "correctness.json"
INTEGRITY_ARTIFACT_NAME_V49F = "integrity.json"
A2M_LEGACY_DECLARED_PROVENANCE_SCHEMA_VERSION_V49F_V5 = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v5"
)
A2M_MEASUREMENT_SCHEMA_VERSION_V49F = "riskyieldmm_physical_transport_a2m_raw_v49f_v6"
A2M_ENVIRONMENT_DOMAIN_V49F = "RiskYieldMMA2MEnvironmentV4_9F_RawV6"
A2M_DESIGN_DOMAIN_V49F = "RiskYieldMMA2MDesignV4_9F_RawV6"
A2M_MANIFEST_DOMAIN_V49F = "RiskYieldMMA2MManifestV4_9F_RawV6"
A2M_SAMPLE_DOMAIN_V49F = "RiskYieldMMA2MSampleV4_9F_RawV6"
A2M_RUNTIME_BOUNDARY_DOMAIN_V49F = "RiskYieldMMA2MRuntimeBoundaryEvidenceV4_9F_RawV6"
A2M_INGRESS_PROGRESS_DOMAIN_V49F = "RiskYieldMMA2MIngressProgressEvidenceV4_9F_RawV6"
A2M_CORRECTNESS_DOMAIN_V49F = "RiskYieldMMA2MCorrectnessV4_9F_RawV6"
A2M_INTEGRITY_DOMAIN_V49F = "RiskYieldMMA2MIntegrityV4_9F_RawV6"
A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F = "CORRECTNESS_FINALIZER_NOT_IMPLEMENTED"
A2M_INGRESS_WORKLOAD_SCHEMA_VERSION_V49F = (
    "riskyieldmm_physical_transport_a2m_ingress_workload_v49f_v2"
)
A2M_TRIAL_ORDER_V49F = "WARMUPS_DECLARED_THEN_SHA256_SEEDED_MEASURED_V49F"

# Raw V6 is decoded from potentially untrusted artifact bytes. These are
# parser/resource safety limits, not measured transport-capacity conclusions.
A2M_MAXIMUM_WORKLOADS_V49F = A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F
A2M_MAXIMUM_WORKLOAD_CORPUS_BYTES_V49F = 16 * 1024 * 1024
A2M_MAXIMUM_WARMUP_REPETITIONS_V49F = 10_000
A2M_MAXIMUM_MEASURED_REPETITIONS_V49F = 100_000
A2M_MAXIMUM_TOTAL_TRIALS_V49F = 100_000
A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F = 32 * 1024 * 1024
A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F = 64 * 1024 * 1024
A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F = 256 * 1024 * 1024
A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F = 4 * 1024 * 1024
A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F = 1 * 1024 * 1024
A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F = (
    A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F
    + A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F
    + A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F
    + A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F
)

# Frozen source-snapshot bounds.  A source change requires an explicit schema
# review rather than silently widening already-versioned evidence semantics.
A2M_MAXIMUM_PENDING_RAW_CHUNKS_V49F = 128
A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F = 65_536
A2M_MAXIMUM_DURABLE_INGRESS_OCTETS_V49F = 1_114_126
A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F = 32
A2M_MAXIMUM_STAGED_WIRE_OCTETS_V49F = 65_536
A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F = 4_194_304
A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F = (
    A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F // 2
)
# Frozen schema/source-snapshot bounds for one raw sample's serialized
# WebSocket-wire output.  They are neither measured capacity nor TLS limits.
A2M_MAXIMUM_RAW_SAMPLE_OUTPUT_CHUNKS_V49F = (
    A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F
    * A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F
)
A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F = (
    A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F * 131
)
A2M_MAXIMUM_RAW_SAMPLE_OUTPUT_BASE64_CHARACTERS_V49F = 4 * (
    (A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F + 2) // 3
)
A2M_RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION_V49F = (
    "RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION"
)

_RAW_ARTIFACT_NAMES = frozenset(
    {
        MANIFEST_ARTIFACT_NAME_V49F,
        SAMPLES_ARTIFACT_NAME_V49F,
        CORRECTNESS_ARTIFACT_NAME_V49F,
    }
)
_BUNDLE_ARTIFACT_NAMES = _RAW_ARTIFACT_NAMES | {INTEGRITY_ARTIFACT_NAME_V49F}
_ARTIFACT_BYTE_LIMITS_V49F = {
    MANIFEST_ARTIFACT_NAME_V49F: A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F,
    SAMPLES_ARTIFACT_NAME_V49F: A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F,
    CORRECTNESS_ARTIFACT_NAME_V49F: A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F,
    INTEGRITY_ARTIFACT_NAME_V49F: A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F,
}
_SEMANTIC_RECORD_KEYS_V49F = frozenset(
    {"canonicalization_version", "measurement_schema_version", "record_domain"}
)
_MAX_UINT128_DECIMAL_DIGITS_V49F = 39


class CapacityMeasurementArtifactErrorV49F(CanonicalizationError):
    """Raised when an exploratory raw-evidence bundle cannot replay exactly."""


class CapacityMeasurementCampaignPhaseV49F(str, Enum):
    """The only phase admitted by this raw-observation contract."""

    EXPLORATORY = "EXPLORATORY"


class CapacityMeasurementOutcomeV49F(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


def _exact_enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    if type(value) is not enum_type:
        raise CanonicalizationError(f"{field} must be an exact {enum_type.__name__}")
    return value


def _optional_identifier(value: Any, *, field: str, maximum: int = 256) -> str | None:
    if value is None:
        return None
    return canonical_identifier(value, field=field, maximum=maximum)


def _optional_hash(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return canonical_hash(value, field=field)


def _optional_safe_int(value: Any, *, field: str) -> int | None:
    if value is None:
        return None
    return canonical_safe_int(value, field=field, minimum=0)


def _canonical_base64_bytes(
    value: Any,
    *,
    field: str,
    maximum_decoded_octets: int,
) -> bytes:
    """Decode one bounded canonical RFC 4648 base64 value fail-closed."""

    if type(value) is not str:
        raise CanonicalizationError(f"{field} must be canonical base64 text")
    maximum_characters = 4 * ((maximum_decoded_octets + 2) // 3)
    if len(value) > maximum_characters:
        raise CanonicalizationError(f"{field} exceeds its encoded safety bound")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise CanonicalizationError(f"{field} contains invalid base64") from exc
    if len(decoded) > maximum_decoded_octets:
        raise CanonicalizationError(f"{field} exceeds its decoded safety bound")
    if base64.b64encode(decoded).decode("ascii") != value:
        raise CanonicalizationError(f"{field} contains non-canonical base64")
    return decoded


def _canonical_uint_text(value: Any, *, field: str) -> str:
    """Canonical arbitrary-length unsigned integer text (not an I-JSON number)."""

    if not isinstance(value, str) or len(value) > _MAX_UINT128_DECIMAL_DIGITS_V49F:
        raise CanonicalizationError(f"{field} must be unsigned integer text")
    if not value or not value.isascii() or not value.isdecimal():
        raise CanonicalizationError(f"{field} must be unsigned integer text")
    if len(value) > 1 and value.startswith("0"):
        raise CanonicalizationError(f"{field} must not contain leading zeroes")
    return value


def _mapping(payload: Any, *, expected: set[str], context: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CanonicalizationError(f"{context} must be a mapping")
    require_exact_keys(payload, expected=expected, context=context)
    return payload


def _record_keys(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _revalidate_exact_dataclass_v49f(
    record: Any,
    *,
    record_type: type[Any],
    context: str,
) -> None:
    """Reject forged or post-construction-mutated exact record instances."""

    if type(record) is not record_type:
        raise CanonicalizationError(f"{context} must be exact")
    reconstructed = record_type(
        **{item.name: getattr(record, item.name) for item in fields(record_type)}
    )
    if reconstructed != record:
        raise CanonicalizationError(f"{context} differs from exact reconstruction")


def _semantic_identity_v49f(*, domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": payload,
            "schema_version": A2M_MEASUREMENT_SCHEMA_VERSION_V49F,
        }
    )


def _canonical_logical_output_frames_v49f(
    frames: Any,
    *,
    field: str,
    maximum_frames: int = A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F,
) -> tuple[tuple[str, bytes], ...]:
    if type(frames) is not tuple or len(frames) > maximum_frames:
        raise CanonicalizationError(f"{field} is outside the logical-frame bounds")
    normalized: list[tuple[str, bytes]] = []
    total_payload_octets = 0
    for frame in frames:
        if type(frame) is not tuple or len(frame) != 2:
            raise CanonicalizationError(
                f"{field} must contain exact opcode/payload pairs"
            )
        opcode = canonical_identifier(frame[0], field=f"{field}_opcode", maximum=16)
        payload = frame[1]
        if opcode not in {"CLOSE", "PONG"} or type(payload) is not bytes:
            raise CanonicalizationError(
                f"{field} supports exact automatic CLOSE/PONG byte payloads only"
            )
        if len(payload) > 125:
            raise CanonicalizationError(f"{field} control payload exceeds 125 octets")
        if opcode == "CLOSE":
            if len(payload) == 1:
                raise CanonicalizationError(
                    f"{field} CLOSE payload cannot contain one status octet"
                )
            if len(payload) >= 2:
                code = int.from_bytes(payload[:2], "big")
                valid_code = (
                    code
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
                    or 3000 <= code <= 4999
                )
                if not valid_code:
                    raise CanonicalizationError(
                        f"{field} CLOSE payload contains a reserved status code"
                    )
                try:
                    payload[2:].decode("utf-8", errors="strict")
                except UnicodeDecodeError as exc:
                    raise CanonicalizationError(
                        f"{field} CLOSE reason must be valid UTF-8"
                    ) from exc
        total_payload_octets += len(payload)
        normalized.append((opcode, payload))
    if total_payload_octets > A2M_MAXIMUM_STAGED_WIRE_OCTETS_V49F:
        raise CanonicalizationError(f"{field} payload bytes exceed the workload bound")
    return tuple(normalized)


def capacity_measurement_logical_frames_sha256_v49f(
    frames: tuple[tuple[str, bytes], ...],
) -> str:
    normalized = _canonical_logical_output_frames_v49f(
        frames, field="logical_output_frames"
    )
    return sha256_digest(
        {
            "domain": "RiskYieldMMA2MExactLogicalOutputFramesV4_9F",
            "ordered_frames": [
                {
                    "opcode": opcode,
                    "payload_base64": base64.b64encode(payload).decode("ascii"),
                }
                for opcode, payload in normalized
            ],
        }
    )


def _decode_exact_masked_control_frame_v49f(
    chunks: tuple[bytes, ...],
) -> tuple[str, bytes]:
    """Decode one complete client Close/Pong frame from exact ordered chunks."""

    if (
        type(chunks) is not tuple
        or not chunks
        or any(type(chunk) is not bytes or not chunk for chunk in chunks)
    ):
        raise CanonicalizationError(
            "automatic physical frame must contain exact non-empty chunks"
        )
    wire = b"".join(chunks)
    if len(wire) < 6:
        raise CanonicalizationError("automatic physical control frame is truncated")
    first, second = wire[0], wire[1]
    opcode = {0x88: "CLOSE", 0x8A: "PONG"}.get(first)
    if opcode is None:
        raise CanonicalizationError(
            "automatic physical output is not one final Close/Pong frame"
        )
    if second & 0x80 == 0:
        raise CanonicalizationError("automatic client control frame must be masked")
    payload_length = second & 0x7F
    if payload_length > 125 or len(wire) != 6 + payload_length:
        raise CanonicalizationError(
            "automatic physical control-frame length is non-canonical"
        )
    mask = wire[2:6]
    payload = bytes(value ^ mask[index % 4] for index, value in enumerate(wire[6:]))
    return _canonical_logical_output_frames_v49f(
        ((opcode, payload),),
        field="decoded_automatic_physical_output",
        maximum_frames=1,
    )[0]


def _semantic_record_v49f(
    *, domain: str, payload: Mapping[str, Any], identity_field: str, identity: str
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": A2M_MEASUREMENT_SCHEMA_VERSION_V49F,
        "record_domain": domain,
        **payload,
        identity_field: identity,
    }


def _decode_semantic_record_v49f(
    payload: Mapping[str, Any],
    *,
    record_type: type[Any],
    domain: str,
    context: str,
) -> dict[str, Any]:
    item = _mapping(
        payload,
        expected=_record_keys(record_type) | _SEMANTIC_RECORD_KEYS_V49F,
        context=context,
    )
    if item["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError(
            f"{context} canonicalization_version is unsupported"
        )
    if item["measurement_schema_version"] != A2M_MEASUREMENT_SCHEMA_VERSION_V49F:
        raise CanonicalizationError(
            f"{context} measurement_schema_version is unsupported"
        )
    if item["record_domain"] != domain:
        raise CanonicalizationError(f"{context} record_domain is unsupported")
    return {name: item[name] for name in _record_keys(record_type)}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementEnvironmentV49F:
    kernel_release: str
    machine_architecture: str
    cpu_model: str
    logical_cpu_count: int
    cpu_affinity: tuple[int, ...]
    python_version: str
    event_loop_implementation: str
    openssl_version: str
    websockets_version: str
    sqlite_version: str
    filesystem_type: str
    storage_identity_sha256: str
    sqlite_pragmas_sha256: str
    environment_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "kernel_release",
            "machine_architecture",
            "cpu_model",
            "python_version",
            "event_loop_implementation",
            "openssl_version",
            "websockets_version",
            "sqlite_version",
            "filesystem_type",
        ):
            object.__setattr__(
                self, name, canonical_identifier(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "logical_cpu_count",
            canonical_safe_int(
                self.logical_cpu_count, field="logical_cpu_count", minimum=1
            ),
        )
        if type(self.cpu_affinity) is not tuple or not self.cpu_affinity:
            raise CanonicalizationError("cpu_affinity must be a non-empty exact tuple")
        affinity = tuple(
            canonical_safe_int(value, field="cpu_affinity", minimum=0)
            for value in self.cpu_affinity
        )
        if len(set(affinity)) != len(affinity):
            raise CanonicalizationError("cpu_affinity contains duplicate CPUs")
        if any(value >= self.logical_cpu_count for value in affinity):
            raise CanonicalizationError("cpu_affinity exceeds logical_cpu_count")
        object.__setattr__(self, "cpu_affinity", tuple(sorted(affinity)))
        for name in ("storage_identity_sha256", "sqlite_pragmas_sha256"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        identity = _semantic_identity_v49f(
            domain=A2M_ENVIRONMENT_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if self.environment_id is not None and self.environment_id != identity:
            raise CanonicalizationError(
                "environment_id differs from canonical environment"
            )
        object.__setattr__(self, "environment_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"environment_id"}
        }

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementEnvironmentV49F,
            context="measurement environment",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementEnvironmentV49F,
            context="measurement environment",
        )
        return _semantic_record_v49f(
            domain=A2M_ENVIRONMENT_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="environment_id",
            identity=self.environment_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementEnvironmentV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_ENVIRONMENT_DOMAIN_V49F,
            context="measurement environment",
        )
        affinity = item["cpu_affinity"]
        if type(affinity) is not list:
            raise CanonicalizationError("cpu_affinity must be a JSON array")
        return cls(**{**item, "cpu_affinity": tuple(affinity)})


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementDesignV49F:
    observer_clock: str
    observer_clock_resolution_nanoseconds: int
    observer_overhead_subtracted: bool
    instrumentation_overhead_method: str
    warmup_repetitions: int
    measured_repetitions: int
    trial_order: str
    random_seed: int
    analysis_plan_sha256: str
    exclusion_policy_sha256: str
    measurement_design_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "observer_clock",
            "instrumentation_overhead_method",
            "trial_order",
        ):
            object.__setattr__(
                self, name, canonical_identifier(getattr(self, name), field=name)
            )
        if self.trial_order != A2M_TRIAL_ORDER_V49F:
            raise CanonicalizationError("trial_order is unsupported")
        object.__setattr__(
            self,
            "observer_clock_resolution_nanoseconds",
            canonical_safe_int(
                self.observer_clock_resolution_nanoseconds,
                field="observer_clock_resolution_nanoseconds",
                minimum=1,
            ),
        )
        if type(self.observer_overhead_subtracted) is not bool:
            raise CanonicalizationError(
                "observer_overhead_subtracted must be an exact boolean"
            )
        if self.observer_overhead_subtracted:
            raise CanonicalizationError(
                "exploratory observer overhead must not be subtracted"
            )
        for name, minimum, maximum in (
            (
                "warmup_repetitions",
                0,
                A2M_MAXIMUM_WARMUP_REPETITIONS_V49F,
            ),
            (
                "measured_repetitions",
                1,
                A2M_MAXIMUM_MEASURED_REPETITIONS_V49F,
            ),
            ("random_seed", 0, MAX_IJSON_INTEGER),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(
                    getattr(self, name),
                    field=name,
                    minimum=minimum,
                    maximum=maximum,
                ),
            )
        for name in ("analysis_plan_sha256", "exclusion_policy_sha256"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        identity = _semantic_identity_v49f(
            domain=A2M_DESIGN_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.measurement_design_id is not None
            and self.measurement_design_id != identity
        ):
            raise CanonicalizationError(
                "measurement_design_id differs from canonical measurement design"
            )
        object.__setattr__(self, "measurement_design_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"measurement_design_id"}
        }

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementDesignV49F,
            context="measurement design",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementDesignV49F,
            context="measurement design",
        )
        return _semantic_record_v49f(
            domain=A2M_DESIGN_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="measurement_design_id",
            identity=self.measurement_design_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CapacityMeasurementDesignV49F:
        return cls(
            **_decode_semantic_record_v49f(
                payload,
                record_type=cls,
                domain=A2M_DESIGN_DOMAIN_V49F,
                context="measurement design",
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressWorkloadSpecV49F:
    """Exact executable vector for the currently implemented ingress runner."""

    workload_family: str
    stage: str
    input_chunks: tuple[bytes, ...]
    expected_output_frames: tuple[tuple[str, bytes], ...]
    timeout_seconds: int

    def __post_init__(self) -> None:
        for name in ("workload_family", "stage"):
            object.__setattr__(
                self, name, canonical_identifier(getattr(self, name), field=name)
            )
        chunks = self.input_chunks
        if (
            type(chunks) is not tuple
            or not chunks
            or len(chunks) > A2M_MAXIMUM_PENDING_RAW_CHUNKS_V49F
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
            or sum(map(len, chunks)) > A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F
        ):
            raise CanonicalizationError(
                "input_chunks is outside the exact ingress workload bounds"
            )
        object.__setattr__(
            self,
            "expected_output_frames",
            _canonical_logical_output_frames_v49f(
                self.expected_output_frames,
                field="expected_output_frames",
                maximum_frames=A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F,
            ),
        )
        object.__setattr__(
            self,
            "timeout_seconds",
            canonical_safe_int(
                self.timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            ),
        )

    def manifest_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIngressWorkloadSpecV49F,
            context="measurement ingress workload specification",
        )
        return {
            "expected_output_frames": [
                {
                    "opcode": opcode,
                    "payload_base64": base64.b64encode(payload).decode("ascii"),
                }
                for opcode, payload in self.expected_output_frames
            ],
            "input_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in self.input_chunks
            ],
            "operation_kind": "INGRESS",
            "stage": self.stage,
            "timeout_seconds": self.timeout_seconds,
            "workload_family": self.workload_family,
            "workload_schema_version": A2M_INGRESS_WORKLOAD_SCHEMA_VERSION_V49F,
        }

    @property
    def workload_manifest_json(self) -> str:
        return canonical_json_bytes(self.manifest_payload()).decode("utf-8")

    @property
    def workload_sha256(self) -> str:
        return hashlib.sha256(self.workload_manifest_json.encode("utf-8")).hexdigest()

    @property
    def raw_ingress_batch_sha256(self) -> str:
        return sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": self.manifest_payload()["input_chunks_base64"],
            }
        )

    @property
    def expected_output_frames_sha256(self) -> str:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIngressWorkloadSpecV49F,
            context="measurement ingress workload specification",
        )
        return capacity_measurement_logical_frames_sha256_v49f(
            self.expected_output_frames
        )

    @classmethod
    def from_manifest_json(
        cls, workload_manifest_json: str
    ) -> CapacityMeasurementIngressWorkloadSpecV49F:
        if type(workload_manifest_json) is not str:
            raise CanonicalizationError("workload_manifest_json must be a string")
        try:
            encoded = workload_manifest_json.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise CanonicalizationError(
                "workload_manifest_json contains invalid Unicode"
            ) from exc
        if not encoded or len(encoded) > 1_048_576:
            raise CanonicalizationError(
                "workload_manifest_json must contain at most 1048576 bytes"
            )
        decoded = strict_json_loads(encoded)
        item = _mapping(
            decoded,
            expected={
                "expected_output_frames",
                "input_chunks_base64",
                "operation_kind",
                "stage",
                "timeout_seconds",
                "workload_family",
                "workload_schema_version",
            },
            context="ingress workload manifest",
        )
        if canonical_json_bytes(item) != encoded:
            raise CanonicalizationError("workload manifest JSON must be canonical")
        if (
            item["workload_schema_version"] != A2M_INGRESS_WORKLOAD_SCHEMA_VERSION_V49F
            or item["operation_kind"] != "INGRESS"
        ):
            raise CanonicalizationError(
                "workload manifest schema or operation is unsupported"
            )

        def chunks(field: str) -> tuple[bytes, ...]:
            values = item[field]
            if type(values) is not list:
                raise CanonicalizationError(f"{field} must be a JSON array")
            decoded_chunks: list[bytes] = []
            for value in values:
                if type(value) is not str:
                    raise CanonicalizationError(f"{field} must contain base64 strings")
                try:
                    chunk = base64.b64decode(value, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise CanonicalizationError(
                        f"{field} contains invalid base64"
                    ) from exc
                if base64.b64encode(chunk).decode("ascii") != value:
                    raise CanonicalizationError(
                        f"{field} contains non-canonical base64"
                    )
                decoded_chunks.append(chunk)
            return tuple(decoded_chunks)

        encoded_frames = item["expected_output_frames"]
        if type(encoded_frames) is not list:
            raise CanonicalizationError("expected_output_frames must be a JSON array")
        frames: list[tuple[str, bytes]] = []
        for value in encoded_frames:
            frame = _mapping(
                value,
                expected={"opcode", "payload_base64"},
                context="expected output frame",
            )
            encoded_payload = frame["payload_base64"]
            if type(encoded_payload) is not str:
                raise CanonicalizationError(
                    "expected output frame payload must be base64 text"
                )
            try:
                payload = base64.b64decode(encoded_payload, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise CanonicalizationError(
                    "expected output frame contains invalid base64"
                ) from exc
            if base64.b64encode(payload).decode("ascii") != encoded_payload:
                raise CanonicalizationError(
                    "expected output frame contains non-canonical base64"
                )
            frames.append((frame["opcode"], payload))

        return cls(
            workload_family=item["workload_family"],
            stage=item["stage"],
            input_chunks=chunks("input_chunks_base64"),
            expected_output_frames=tuple(frames),
            timeout_seconds=item["timeout_seconds"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementWorkloadV49F:
    workload_id: str
    workload_sha256: str
    workload_manifest_json: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workload_id",
            canonical_identifier(self.workload_id, field="workload_id"),
        )
        object.__setattr__(
            self,
            "workload_sha256",
            canonical_hash(self.workload_sha256, field="workload_sha256"),
        )
        spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
            self.workload_manifest_json
        )
        expected_hash = spec.workload_sha256
        if self.workload_sha256 != expected_hash:
            raise CanonicalizationError(
                "workload_sha256 differs from canonical workload manifest bytes"
            )

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementWorkloadV49F,
            context="measurement workload",
        )
        return {
            "workload_id": self.workload_id,
            "workload_sha256": self.workload_sha256,
            "workload_manifest_json": self.workload_manifest_json,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementWorkloadV49F:
        return cls(
            **_mapping(
                payload, expected=_record_keys(cls), context="measurement workload"
            )
        )


def capacity_measurement_workload_corpus_sha256_v49f(
    workloads: Sequence[CapacityMeasurementWorkloadV49F],
) -> str:
    if (
        type(workloads) not in {list, tuple}
        or not workloads
        or len(workloads) > A2M_MAXIMUM_WORKLOADS_V49F
    ):
        raise CanonicalizationError(
            "workloads must contain a bounded set of exact workload records"
        )
    normalized = tuple(workloads)
    if any(type(item) is not CapacityMeasurementWorkloadV49F for item in normalized):
        raise CanonicalizationError("workloads must contain exact workload records")
    if (
        sum(len(item.workload_manifest_json.encode("utf-8")) for item in normalized)
        > A2M_MAXIMUM_WORKLOAD_CORPUS_BYTES_V49F
    ):
        raise CanonicalizationError("workload corpus exceeds its byte bound")
    return sha256_digest([item.as_dict() for item in normalized])


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementManifestV49F:
    campaign_label: str
    phase: CapacityMeasurementCampaignPhaseV49F
    started_at_utc: str
    source_revision: str
    source_identity_sha256: str
    source_tree_clean: bool
    runtime_identity_sha256: str
    workload_corpus_sha256: str
    transport_capacity_policy_id: str
    transport_runtime_version: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    monotonic_origin_nanoseconds: str
    boottime_origin_nanoseconds: str
    loop_time_origin_nanoseconds: str
    workloads: tuple[CapacityMeasurementWorkloadV49F, ...]
    environment: CapacityMeasurementEnvironmentV49F
    design: CapacityMeasurementDesignV49F
    manifest_request: CapacityMeasurementManifestRequestV49F
    source_observation: SourceObservationSnapshotV49F
    runtime_observation: CapacityMeasurementRuntimeObservationV49F
    process_environment_observation: (
        CapacityMeasurementProcessEnvironmentObservationV49F
    )
    manifest_authority: CapacityMeasurementManifestAuthorityV49F
    campaign_manifest_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "phase",
            _exact_enum(
                self.phase, CapacityMeasurementCampaignPhaseV49F, field="phase"
            ),
        )
        object.__setattr__(
            self,
            "campaign_label",
            canonical_identifier(self.campaign_label, field="campaign_label"),
        )
        object.__setattr__(
            self, "started_at_utc", utc_iso(self.started_at_utc, field="started_at_utc")
        )
        object.__setattr__(
            self,
            "source_revision",
            canonical_identifier(self.source_revision, field="source_revision"),
        )
        for name in (
            "source_identity_sha256",
            "runtime_identity_sha256",
            "workload_corpus_sha256",
            "transport_capacity_policy_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        if type(self.source_tree_clean) is not bool:
            raise CanonicalizationError("source_tree_clean must be an exact boolean")
        object.__setattr__(
            self,
            "transport_runtime_version",
            canonical_identifier(
                self.transport_runtime_version, field="transport_runtime_version"
            ),
        )
        object.__setattr__(
            self,
            "monotonic_origin_nanoseconds",
            _canonical_uint_text(
                self.monotonic_origin_nanoseconds, field="monotonic_origin_nanoseconds"
            ),
        )
        for name in (
            "boottime_origin_nanoseconds",
            "loop_time_origin_nanoseconds",
        ):
            object.__setattr__(
                self,
                name,
                _canonical_uint_text(getattr(self, name), field=name),
            )
        if type(self.workloads) is not tuple or not self.workloads:
            raise CanonicalizationError("workloads must be a non-empty exact tuple")
        if any(
            type(item) is not CapacityMeasurementWorkloadV49F for item in self.workloads
        ):
            raise CanonicalizationError("workloads contain an unsupported record")
        workload_ids = tuple(item.workload_id for item in self.workloads)
        if len(set(workload_ids)) != len(workload_ids):
            raise CanonicalizationError("workloads contain duplicate workload IDs")
        if workload_ids != tuple(sorted(workload_ids)):
            raise CanonicalizationError("workloads must be ordered by workload_id")
        if self.workload_corpus_sha256 != (
            capacity_measurement_workload_corpus_sha256_v49f(self.workloads)
        ):
            raise CanonicalizationError(
                "workload_corpus_sha256 differs from declared workload manifests"
            )
        if type(self.environment) is not CapacityMeasurementEnvironmentV49F:
            raise CanonicalizationError("environment must be exact")
        if type(self.design) is not CapacityMeasurementDesignV49F:
            raise CanonicalizationError("design must be exact")
        if (
            len(self.workloads)
            * (self.design.warmup_repetitions + self.design.measured_repetitions)
            > A2M_MAXIMUM_TOTAL_TRIALS_V49F
        ):
            raise CanonicalizationError(
                "workload and repetition product exceeds the total-trial bound"
            )
        for name, record_type in (
            ("manifest_request", CapacityMeasurementManifestRequestV49F),
            ("source_observation", SourceObservationSnapshotV49F),
            ("runtime_observation", CapacityMeasurementRuntimeObservationV49F),
            (
                "process_environment_observation",
                CapacityMeasurementProcessEnvironmentObservationV49F,
            ),
            ("manifest_authority", CapacityMeasurementManifestAuthorityV49F),
        ):
            record = getattr(self, name)
            if type(record) is not record_type:
                raise CanonicalizationError(f"{name} must be exact")
            try:
                reconstructed = record_type.from_mapping(record.as_dict())
            except (AttributeError, TypeError) as exc:
                raise CanonicalizationError(
                    f"{name} differs from reconstructable evidence"
                ) from exc
            if reconstructed != record:
                raise CanonicalizationError(f"{name} differs from exact reconstruction")

        request = self.manifest_request
        source = self.source_observation
        runtime = self.runtime_observation
        process = self.process_environment_observation
        authority = self.manifest_authority
        if (
            request.campaign_label != self.campaign_label
            or request.phase != self.phase.value
            or request.measurement_design_id != self.design.measurement_design_id
            or request.workload_corpus_sha256 != self.workload_corpus_sha256
            or request.workload_ids != workload_ids
            or request.workload_sha256s
            != tuple(item.workload_sha256 for item in self.workloads)
        ):
            raise CanonicalizationError(
                "manifest request differs from the executable campaign declaration"
            )
        if not source.deployment_source_tree_matches:
            raise CanonicalizationError(
                "observed source differs from the signed deployment source tree"
            )
        if source.deployment_source_tree_sha256 != runtime.declared_source_tree_sha256:
            raise CanonicalizationError(
                "source observation is not bound to the signed release source tree"
            )
        if (
            self.source_revision != source.git_state.head_commit
            or self.source_identity_sha256 != source.source_tree_sha256
            or self.source_tree_clean != source.git_state.source_tree_clean
        ):
            raise CanonicalizationError(
                "manifest source aliases differ from the authoritative observation"
            )
        if (
            self.runtime_identity_sha256 != runtime.runtime_observation_id
            or self.transport_runtime_version
            != runtime.transport_runtime_schema_version
            or self.transport_capacity_policy_id != runtime.transport_capacity_policy_id
            or self.transport_session_id != runtime.transport_session_id
            or self.driver_evidence_nonce_sha256 != runtime.driver_evidence_nonce_sha256
            or self.kernel_socket_identity != runtime.kernel_socket_identity
        ):
            raise CanonicalizationError(
                "manifest runtime aliases differ from the authoritative observation"
            )
        if (
            self.environment.kernel_release != process.kernel_release
            or self.environment.machine_architecture != process.machine_architecture
            or self.environment.cpu_model != process.cpu_model
            or self.environment.logical_cpu_count != process.logical_cpu_count
            or self.environment.cpu_affinity != process.cpu_affinity
            or self.environment.python_version != process.python_version
            or self.environment.event_loop_implementation
            != process.event_loop_implementation
            or self.environment.openssl_version != process.openssl_version
            or self.environment.websockets_version != process.websockets_version
            or self.environment.sqlite_version != process.sqlite_version
            or self.environment.filesystem_type != process.filesystem_type
            or self.environment.storage_identity_sha256
            != process.storage_identity_sha256
            or self.environment.sqlite_pragmas_sha256 != process.sqlite_pragmas_sha256
        ):
            raise CanonicalizationError(
                "manifest environment aliases differ from the process observation"
            )
        if (
            process.kernel_boot_id != runtime.kernel_boot_id
            or process.time_namespace_id != runtime.time_namespace_id
            or process.network_namespace_id != runtime.network_namespace_id
        ):
            raise CanonicalizationError(
                "process and retained runtime authorities describe different host contexts"
            )
        if (
            authority.manifest_request_id != request.manifest_request_id
            or authority.source_observation_id != source.source_observation_id
            or authority.runtime_observation_id != runtime.runtime_observation_id
            or authority.environment_observation_id
            != process.environment_observation_id
            or authority.deployment_bundle_id != runtime.deployment_bundle_id
            or authority.deployment_trust_root_id != runtime.deployment_trust_root_id
            or authority.collector_release_manifest_id
            != runtime.collector_release_manifest_id
            or authority.runtime_environment_manifest_id
            != runtime.runtime_environment_manifest_id
            or authority.collector_attestation_key_id
            != runtime.collector_attestation_key_id
            or authority.transport_session_id != runtime.transport_session_id
            or authority.driver_evidence_nonce_sha256
            != runtime.driver_evidence_nonce_sha256
            or authority.kernel_socket_identity != runtime.kernel_socket_identity
            or authority.transport_capacity_policy_id
            != runtime.transport_capacity_policy_id
            or authority.started_at_utc != self.started_at_utc
            or authority.monotonic_origin_nanoseconds
            != self.monotonic_origin_nanoseconds
            or authority.boottime_origin_nanoseconds != self.boottime_origin_nanoseconds
            or authority.loop_time_origin_nanoseconds
            != self.loop_time_origin_nanoseconds
        ):
            raise CanonicalizationError(
                "signed manifest authority differs from its exact observations"
            )
        identity = _semantic_identity_v49f(
            domain=A2M_MANIFEST_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.campaign_manifest_id is not None
            and self.campaign_manifest_id != identity
        ):
            raise CanonicalizationError(
                "campaign_manifest_id differs from canonical manifest"
            )
        object.__setattr__(self, "campaign_manifest_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "campaign_label": self.campaign_label,
            "design": self.design.as_dict(),
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "environment": self.environment.as_dict(),
            "manifest_authority": self.manifest_authority.as_dict(),
            "manifest_request": self.manifest_request.as_dict(),
            "process_environment_observation": (
                self.process_environment_observation.as_dict()
            ),
            "kernel_socket_identity": self.kernel_socket_identity,
            "boottime_origin_nanoseconds": self.boottime_origin_nanoseconds,
            "loop_time_origin_nanoseconds": self.loop_time_origin_nanoseconds,
            "monotonic_origin_nanoseconds": self.monotonic_origin_nanoseconds,
            "phase": self.phase.value,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "runtime_observation": self.runtime_observation.as_dict(),
            "source_observation": self.source_observation.as_dict(),
            "source_identity_sha256": self.source_identity_sha256,
            "source_revision": self.source_revision,
            "source_tree_clean": self.source_tree_clean,
            "started_at_utc": self.started_at_utc,
            "transport_capacity_policy_id": self.transport_capacity_policy_id,
            "transport_runtime_version": self.transport_runtime_version,
            "transport_session_id": self.transport_session_id,
            "workload_corpus_sha256": self.workload_corpus_sha256,
            "workloads": [item.as_dict() for item in self.workloads],
        }

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementManifestV49F,
            context="measurement manifest",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementManifestV49F,
            context="measurement manifest",
        )
        return _semantic_record_v49f(
            domain=A2M_MANIFEST_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="campaign_manifest_id",
            identity=self.campaign_manifest_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementManifestV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_MANIFEST_DOMAIN_V49F,
            context="measurement manifest",
        )
        if item["phase"] != CapacityMeasurementCampaignPhaseV49F.EXPLORATORY.value:
            raise CanonicalizationError("measurement phase must be exactly EXPLORATORY")
        workloads = item["workloads"]
        if type(workloads) is not list:
            raise CanonicalizationError("workloads must be a JSON array")
        return cls(
            **{
                **item,
                "phase": CapacityMeasurementCampaignPhaseV49F.EXPLORATORY,
                "workloads": tuple(
                    CapacityMeasurementWorkloadV49F.from_mapping(value)
                    for value in workloads
                ),
                "environment": CapacityMeasurementEnvironmentV49F.from_mapping(
                    item["environment"]
                ),
                "design": CapacityMeasurementDesignV49F.from_mapping(item["design"]),
                "manifest_request": CapacityMeasurementManifestRequestV49F.from_mapping(
                    item["manifest_request"]
                ),
                "source_observation": SourceObservationSnapshotV49F.from_mapping(
                    item["source_observation"]
                ),
                "runtime_observation": CapacityMeasurementRuntimeObservationV49F.from_mapping(
                    item["runtime_observation"]
                ),
                "process_environment_observation": (
                    CapacityMeasurementProcessEnvironmentObservationV49F.from_mapping(
                        item["process_environment_observation"]
                    )
                ),
                "manifest_authority": CapacityMeasurementManifestAuthorityV49F.from_mapping(
                    item["manifest_authority"]
                ),
            }
        )


_LAYER_INTEGER_FIELDS = frozenset(
    {
        "effective_so_rcvbuf_octets",
        "effective_so_sndbuf_octets",
        "siocinq_queued_octets",
        "siocoutq_queued_octets",
        "memory_bio_incoming_pending_octets",
        "memory_bio_outgoing_pending_octets",
        "ssl_plaintext_pending_octets",
        "pending_raw_chunks",
        "pending_raw_octets",
        "durable_ingress_buffer_octets",
        "protocol_output_chunks",
        "protocol_output_octets",
        "staged_websocket_wire_chunks",
        "staged_websocket_wire_octets",
        "pending_tls_ciphertext_octets",
        "remaining_pending_tls_ciphertext_octets",
        "staged_tls_ciphertext_octets",
        "remaining_staged_tls_ciphertext_octets",
        "staged_tls_control_ciphertext_octets",
        "remaining_staged_tls_control_ciphertext_octets",
        "admission_active_commands",
        "admission_waiting_commands",
        "admission_reserved_work_units",
        "admission_capacity_rejections",
        "admission_queue_wait_nanoseconds",
        "actor_event_count",
        "actor_wire_queue_events",
        "actor_wire_queue_octets",
        "sqlite_database_bytes",
        "sqlite_journal_bytes",
        "sqlite_wal_bytes",
        "sqlite_shm_bytes",
        "sqlite_page_count",
        "sqlite_freelist_count",
        "process_rss_bytes",
        "process_pss_bytes",
        "cgroup_memory_bytes",
        "event_loop_lag_nanoseconds",
    }
)
_LAYER_BOOLEAN_FIELDS = frozenset({"has_complete_durable_unit", "pending_send_eof"})
_LAYER_STRING_FIELDS = frozenset({"kernel_socket_identity", "driver_state"})
_LAYER_VALUE_FIELDS = (
    _LAYER_INTEGER_FIELDS | _LAYER_BOOLEAN_FIELDS | _LAYER_STRING_FIELDS
)
A2M_LAYER_VALUE_FIELDS_V49F = tuple(sorted(_LAYER_VALUE_FIELDS))
A2M_LAYER_ADAPTER_FIELDS_V49F = tuple(
    sorted(
        (
            (
                "TRANSPORT_FLOW",
                tuple(
                    sorted(
                        _LAYER_VALUE_FIELDS
                        - {
                            "actor_event_count",
                            "actor_wire_queue_events",
                            "actor_wire_queue_octets",
                            "admission_active_commands",
                            "admission_capacity_rejections",
                            "admission_queue_wait_nanoseconds",
                            "admission_reserved_work_units",
                            "admission_waiting_commands",
                            "event_loop_lag_nanoseconds",
                            "cgroup_memory_bytes",
                            "process_pss_bytes",
                            "process_rss_bytes",
                            "sqlite_database_bytes",
                            "sqlite_freelist_count",
                            "sqlite_journal_bytes",
                            "sqlite_page_count",
                            "sqlite_shm_bytes",
                            "sqlite_wal_bytes",
                        }
                    )
                ),
            ),
            (
                "ADMISSION",
                tuple(
                    sorted(
                        {
                            "admission_active_commands",
                            "admission_capacity_rejections",
                            "admission_queue_wait_nanoseconds",
                            "admission_reserved_work_units",
                            "admission_waiting_commands",
                        }
                    )
                ),
            ),
            (
                "ACTOR",
                tuple(
                    sorted(
                        {
                            "actor_event_count",
                            "actor_wire_queue_events",
                            "actor_wire_queue_octets",
                        }
                    )
                ),
            ),
            (
                "SQLITE",
                tuple(
                    sorted(
                        {
                            "sqlite_database_bytes",
                            "sqlite_freelist_count",
                            "sqlite_journal_bytes",
                            "sqlite_page_count",
                            "sqlite_shm_bytes",
                            "sqlite_wal_bytes",
                        }
                    )
                ),
            ),
            (
                "PROCESS",
                tuple(
                    sorted(
                        {
                            "cgroup_memory_bytes",
                            "process_pss_bytes",
                            "process_rss_bytes",
                        }
                    )
                ),
            ),
            ("EVENT_LOOP", ("event_loop_lag_nanoseconds",)),
        )
    )
)
_DRIVER_STATES_V49F = frozenset(
    {
        "DORMANT",
        "TLS_HANDSHAKING",
        "WS_RESPONSE_BUFFERING",
        "WS_OPEN_UNBOUND",
        "RAW_INGRESS_PENDING",
        "WS_OPEN_BOUND",
        "OUTBOUND_WIRE_PREPARED_V49C",
        "TLS_CIPHERTEXT_PREPARED_V49C",
        "TLS_CONTROL_CIPHERTEXT_PREPARED_V49E",
        "TLS_SHUTDOWN_V49E",
        "PROTOCOL_OUTPUT_PENDING",
        "WS_CLOSING",
        "FAULT_LATCHED",
        "CLOSED",
    }
)
_COUNT_OCTET_PAIRS_V49F = (
    ("pending_raw_chunks", "pending_raw_octets"),
    ("protocol_output_chunks", "protocol_output_octets"),
    ("staged_websocket_wire_chunks", "staged_websocket_wire_octets"),
    ("actor_wire_queue_events", "actor_wire_queue_octets"),
)
_TOTAL_REMAINING_PAIRS_V49F = (
    ("pending_tls_ciphertext_octets", "remaining_pending_tls_ciphertext_octets"),
    ("staged_tls_ciphertext_octets", "remaining_staged_tls_ciphertext_octets"),
    (
        "staged_tls_control_ciphertext_octets",
        "remaining_staged_tls_control_ciphertext_octets",
    ),
)
_LAYER_UPPER_BOUNDS_V49F = {
    "pending_raw_chunks": A2M_MAXIMUM_PENDING_RAW_CHUNKS_V49F,
    "pending_raw_octets": A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F,
    "durable_ingress_buffer_octets": A2M_MAXIMUM_DURABLE_INGRESS_OCTETS_V49F,
    "staged_websocket_wire_chunks": A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F,
    "staged_websocket_wire_octets": A2M_MAXIMUM_STAGED_WIRE_OCTETS_V49F,
    "pending_tls_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
    "remaining_pending_tls_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
    "staged_tls_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
    "remaining_staged_tls_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
    "staged_tls_control_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
    "remaining_staged_tls_control_ciphertext_octets": A2M_MAXIMUM_TLS_CIPHERTEXT_OCTETS_V49F,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementAdapterSpanV49F:
    """Timing and availability for one declared snapshot adapter.

    A combined layer snapshot is never an atomic cross-layer observation.  The
    span records which flat fields one adapter owns and the interval during
    which it observed them.  Overlap is permitted for independently scheduled
    observers, but spans must have one deterministic chronological order.
    """

    adapter_name: str
    observation_method: str
    observation_started_offset_nanoseconds: int
    observation_completed_offset_nanoseconds: int
    observed_fields: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    unavailable_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("adapter_name", "observation_method"):
            object.__setattr__(
                self,
                name,
                canonical_identifier(getattr(self, name), field=name),
            )
        for name in (
            "observation_started_offset_nanoseconds",
            "observation_completed_offset_nanoseconds",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=0),
            )
        if (
            self.observation_completed_offset_nanoseconds
            < self.observation_started_offset_nanoseconds
        ):
            raise CanonicalizationError(
                "adapter observation completion precedes its start"
            )
        observed = canonical_reason_codes(self.observed_fields, field="observed_fields")
        if not observed or any(name not in _LAYER_VALUE_FIELDS for name in observed):
            raise CanonicalizationError(
                "adapter observed_fields must name supported layer fields"
            )
        unavailable = canonical_reason_codes(
            self.unavailable_fields, field="unavailable_fields"
        )
        if not set(unavailable).issubset(observed):
            raise CanonicalizationError(
                "adapter unavailable_fields must be a subset of observed_fields"
            )
        reasons = canonical_reason_codes(
            self.unavailable_reason_codes, field="unavailable_reason_codes"
        )
        if bool(reasons) != bool(unavailable):
            raise CanonicalizationError(
                "adapter reason codes must be non-empty iff fields are unavailable"
            )
        object.__setattr__(self, "observed_fields", observed)
        object.__setattr__(self, "unavailable_fields", unavailable)
        object.__setattr__(self, "unavailable_reason_codes", reasons)

    @property
    def observation_duration_nanoseconds(self) -> int:
        return (
            self.observation_completed_offset_nanoseconds
            - self.observation_started_offset_nanoseconds
        )

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementAdapterSpanV49F,
            context="measurement adapter span",
        )
        return {
            "adapter_name": self.adapter_name,
            "observation_completed_offset_nanoseconds": (
                self.observation_completed_offset_nanoseconds
            ),
            "observation_method": self.observation_method,
            "observation_started_offset_nanoseconds": (
                self.observation_started_offset_nanoseconds
            ),
            "observed_fields": list(self.observed_fields),
            "unavailable_fields": list(self.unavailable_fields),
            "unavailable_reason_codes": list(self.unavailable_reason_codes),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementAdapterSpanV49F:
        item = _mapping(
            payload, expected=_record_keys(cls), context="measurement adapter span"
        )
        for name in (
            "observed_fields",
            "unavailable_fields",
            "unavailable_reason_codes",
        ):
            if type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
        return cls(
            **{
                **item,
                "observed_fields": tuple(item["observed_fields"]),
                "unavailable_fields": tuple(item["unavailable_fields"]),
                "unavailable_reason_codes": tuple(item["unavailable_reason_codes"]),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLayerSnapshotV49F:
    observation_method: str
    observed_offset_nanoseconds: int
    adapter_spans: tuple[CapacityMeasurementAdapterSpanV49F, ...]
    unavailable_fields: tuple[str, ...]
    unavailable_reason_codes: tuple[str, ...]
    kernel_socket_identity: str | None
    effective_so_rcvbuf_octets: int | None
    effective_so_sndbuf_octets: int | None
    siocinq_queued_octets: int | None
    siocoutq_queued_octets: int | None
    driver_state: str | None
    memory_bio_incoming_pending_octets: int | None
    memory_bio_outgoing_pending_octets: int | None
    ssl_plaintext_pending_octets: int | None
    pending_raw_chunks: int | None
    pending_raw_octets: int | None
    durable_ingress_buffer_octets: int | None
    has_complete_durable_unit: bool | None
    protocol_output_chunks: int | None
    protocol_output_octets: int | None
    pending_send_eof: bool | None
    staged_websocket_wire_chunks: int | None
    staged_websocket_wire_octets: int | None
    pending_tls_ciphertext_octets: int | None
    remaining_pending_tls_ciphertext_octets: int | None
    staged_tls_ciphertext_octets: int | None
    remaining_staged_tls_ciphertext_octets: int | None
    staged_tls_control_ciphertext_octets: int | None
    remaining_staged_tls_control_ciphertext_octets: int | None
    admission_active_commands: int | None
    admission_waiting_commands: int | None
    admission_reserved_work_units: int | None
    admission_capacity_rejections: int | None
    admission_queue_wait_nanoseconds: int | None
    actor_event_count: int | None
    actor_wire_queue_events: int | None
    actor_wire_queue_octets: int | None
    sqlite_database_bytes: int | None
    sqlite_journal_bytes: int | None
    sqlite_wal_bytes: int | None
    sqlite_shm_bytes: int | None
    sqlite_page_count: int | None
    sqlite_freelist_count: int | None
    process_rss_bytes: int | None
    process_pss_bytes: int | None
    cgroup_memory_bytes: int | None
    event_loop_lag_nanoseconds: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_method",
            canonical_identifier(self.observation_method, field="observation_method"),
        )
        object.__setattr__(
            self,
            "observed_offset_nanoseconds",
            canonical_safe_int(
                self.observed_offset_nanoseconds,
                field="observed_offset_nanoseconds",
                minimum=0,
            ),
        )
        if type(self.adapter_spans) is not tuple or not self.adapter_spans:
            raise CanonicalizationError("adapter_spans must be a non-empty exact tuple")
        if any(
            type(span) is not CapacityMeasurementAdapterSpanV49F
            for span in self.adapter_spans
        ):
            raise CanonicalizationError("adapter_spans contain an unsupported record")
        ordered = tuple(
            sorted(
                self.adapter_spans,
                key=lambda span: (
                    span.observation_started_offset_nanoseconds,
                    span.observation_completed_offset_nanoseconds,
                    span.adapter_name,
                ),
            )
        )
        if self.adapter_spans != ordered:
            raise CanonicalizationError(
                "adapter_spans must use deterministic chronological order"
            )
        adapter_names = tuple(span.adapter_name for span in self.adapter_spans)
        if len(set(adapter_names)) != len(adapter_names):
            raise CanonicalizationError("adapter_spans contain duplicate adapter names")
        actual_adapter_fields = tuple(
            sorted(
                (span.adapter_name, span.observed_fields) for span in self.adapter_spans
            )
        )
        if actual_adapter_fields != A2M_LAYER_ADAPTER_FIELDS_V49F:
            raise CanonicalizationError(
                "adapter_spans differ from the frozen adapter field ownership"
            )
        covered_fields = tuple(
            name for span in self.adapter_spans for name in span.observed_fields
        )
        if (
            len(set(covered_fields)) != len(covered_fields)
            or set(covered_fields) != _LAYER_VALUE_FIELDS
        ):
            raise CanonicalizationError(
                "adapter_spans must partition every layer value field exactly once"
            )
        if self.observed_offset_nanoseconds != max(
            span.observation_completed_offset_nanoseconds for span in self.adapter_spans
        ):
            raise CanonicalizationError(
                "observed_offset_nanoseconds must equal the last adapter completion"
            )
        for name in _LAYER_INTEGER_FIELDS:
            minimum = (
                1
                if name
                in {
                    "effective_so_rcvbuf_octets",
                    "effective_so_sndbuf_octets",
                }
                else 0
            )
            object.__setattr__(
                self,
                name,
                _optional_safe_int(getattr(self, name), field=name),
            )
            value = getattr(self, name)
            if value is not None and value < minimum:
                raise CanonicalizationError(f"{name} must be at least {minimum}")
            maximum = _LAYER_UPPER_BOUNDS_V49F.get(name)
            if value is not None and maximum is not None and value > maximum:
                raise CanonicalizationError(f"{name} exceeds its frozen V4.9 bound")
        for name in _LAYER_BOOLEAN_FIELDS:
            value = getattr(self, name)
            if value is not None and type(value) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean or null")
        object.__setattr__(
            self,
            "kernel_socket_identity",
            _optional_hash(self.kernel_socket_identity, field="kernel_socket_identity"),
        )
        object.__setattr__(
            self,
            "driver_state",
            _optional_identifier(self.driver_state, field="driver_state", maximum=64),
        )
        if (
            self.driver_state is not None
            and self.driver_state not in _DRIVER_STATES_V49F
        ):
            raise CanonicalizationError(
                "driver_state is outside the V4.9 state machine"
            )
        for count_name, octet_name in _COUNT_OCTET_PAIRS_V49F:
            count = getattr(self, count_name)
            octets = getattr(self, octet_name)
            if (count is None) != (octets is None):
                raise CanonicalizationError(
                    f"{count_name} and {octet_name} availability differs"
                )
            if count is not None and (count == 0) != (octets == 0):
                raise CanonicalizationError(
                    f"{count_name} and {octet_name} zero states differ"
                )
        for total_name, remaining_name in _TOTAL_REMAINING_PAIRS_V49F:
            total = getattr(self, total_name)
            remaining = getattr(self, remaining_name)
            if (total is None) != (remaining is None):
                raise CanonicalizationError(
                    f"{total_name} and {remaining_name} availability differs"
                )
            if total is not None and remaining > total:
                raise CanonicalizationError(f"{remaining_name} exceeds {total_name}")
        for total_name, remaining_name in _TOTAL_REMAINING_PAIRS_V49F:
            total = getattr(self, total_name)
            remaining = getattr(self, remaining_name)
            if total is not None and (total == 0) != (remaining == 0):
                raise CanonicalizationError(
                    f"{total_name} and {remaining_name} zero states differ"
                )
        if (
            self.has_complete_durable_unit is True
            and self.durable_ingress_buffer_octets in {None, 0}
        ):
            raise CanonicalizationError(
                "has_complete_durable_unit requires retained durable ingress bytes"
            )
        unavailable = tuple(
            sorted(name for name in _LAYER_VALUE_FIELDS if getattr(self, name) is None)
        )
        supplied = canonical_reason_codes(
            self.unavailable_fields, field="unavailable_fields"
        )
        if supplied != unavailable:
            raise CanonicalizationError(
                "unavailable_fields must exactly equal every null observation field"
            )
        object.__setattr__(self, "unavailable_fields", supplied)
        span_unavailable = tuple(
            sorted(
                name for span in self.adapter_spans for name in span.unavailable_fields
            )
        )
        if span_unavailable != unavailable:
            raise CanonicalizationError(
                "adapter spans must attribute every unavailable snapshot field"
            )
        reasons = canonical_reason_codes(
            self.unavailable_reason_codes, field="unavailable_reason_codes"
        )
        if bool(reasons) != bool(unavailable):
            raise CanonicalizationError(
                "unavailable_reason_codes must be non-empty iff fields are unavailable"
            )
        span_reasons = tuple(
            sorted(
                {
                    reason
                    for span in self.adapter_spans
                    for reason in span.unavailable_reason_codes
                }
            )
        )
        if span_reasons != reasons:
            raise CanonicalizationError(
                "snapshot reason codes must equal the adapter-span reason union"
            )
        object.__setattr__(self, "unavailable_reason_codes", reasons)

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementLayerSnapshotV49F,
            context="measurement layer snapshot",
        )
        result = {name: getattr(self, name) for name in _record_keys(type(self))}
        result["adapter_spans"] = [span.as_dict() for span in self.adapter_spans]
        result["unavailable_fields"] = list(self.unavailable_fields)
        result["unavailable_reason_codes"] = list(self.unavailable_reason_codes)
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLayerSnapshotV49F:
        item = _mapping(
            payload, expected=_record_keys(cls), context="measurement layer snapshot"
        )
        for name in (
            "adapter_spans",
            "unavailable_fields",
            "unavailable_reason_codes",
        ):
            if type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
        return cls(
            **{
                **item,
                "adapter_spans": tuple(
                    CapacityMeasurementAdapterSpanV49F.from_mapping(value)
                    for value in item["adapter_spans"]
                ),
                "unavailable_fields": tuple(item["unavailable_fields"]),
                "unavailable_reason_codes": tuple(item["unavailable_reason_codes"]),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLogicalOutputFrameV49F:
    """One exact logical automatic Close/Pong observation."""

    opcode: str
    payload_base64: str

    def __post_init__(self) -> None:
        opcode = canonical_identifier(self.opcode, field="opcode", maximum=16)
        payload = _canonical_base64_bytes(
            self.payload_base64,
            field="payload_base64",
            maximum_decoded_octets=125,
        )
        _canonical_logical_output_frames_v49f(
            ((opcode, payload),),
            field="automatic_protocol_output_frame",
            maximum_frames=1,
        )
        object.__setattr__(self, "opcode", opcode)

    @property
    def payload(self) -> bytes:
        return _canonical_base64_bytes(
            self.payload_base64,
            field="payload_base64",
            maximum_decoded_octets=125,
        )

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementLogicalOutputFrameV49F,
            context="measurement logical output frame",
        )
        return {"opcode": self.opcode, "payload_base64": self.payload_base64}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLogicalOutputFrameV49F:
        item = _mapping(
            payload,
            expected=_record_keys(cls),
            context="measurement logical output frame",
        )
        return cls(**item)


_A2M_RUNTIME_BOUNDARY_ROLES_V49F = {
    "AFTER_OPERATION",
    "BEFORE_OPERATION",
    "INITIAL",
}
_A2M_RUNTIME_STATES_V49F = {
    "ACK_BOUND",
    "AWAITING_ACK",
    "CLOSED",
    "COLD",
    "DISPATCHING",
    "FAULT_LATCHED",
    "FENCED",
    "INTENT_COMMITTED",
    "READY",
    "SESSION_COMMITTED",
    "STARTING",
}
_A2M_TRANSPORT_COMMAND_KINDS_V49F = {
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementRuntimeBoundaryEvidenceV49F:
    """Role-bound exact copy of one quiescent runtime/A1 boundary."""

    boundary_role: str
    capture_started_offset_nanoseconds: int
    capture_completed_offset_nanoseconds: int
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    admission_epoch: int
    admission_closed: bool
    admission_terminal_barrier_admission_sequence: int | None
    admission_terminal_barrier_committed: bool
    admission_active_admission_sequence: int | None
    admission_active_command_kind: str | None
    admission_waiting_admission_sequences: tuple[int, ...]
    admission_waiting_command_kinds: tuple[str, ...]
    admission_oldest_waiting_age_nanoseconds: int
    admission_reserved_work_units: int
    admission_maximum_observed_admitted_commands: int
    admission_maximum_observed_reserved_work_units: int
    admission_last_started_queue_wait_nanoseconds: int
    admission_maximum_observed_queue_wait_nanoseconds: int
    admission_released_commands: int
    admission_rejected_commands: int
    admission_duplicate_kind_rejections: int
    admission_terminal_barrier_rejections: int
    admission_capacity_rejections: int
    admission_closed_rejections: int
    admission_timed_out_commands: int
    admission_cancelled_before_entry_commands: int
    admission_closed_before_entry_commands: int
    actor_event_count: int
    actor_tail_event_id: str | None
    actor_wire_queue_events: int
    actor_wire_queue_octets: int
    runtime_state: str
    boundary_evidence_id: str | None = None

    def __post_init__(self) -> None:
        role = canonical_identifier(
            self.boundary_role, field="boundary_role", maximum=32
        )
        if role not in _A2M_RUNTIME_BOUNDARY_ROLES_V49F:
            raise CanonicalizationError("boundary_role is unsupported")
        object.__setattr__(self, "boundary_role", role)
        for name in (
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name, minimum in (
            ("capture_started_offset_nanoseconds", 0),
            ("capture_completed_offset_nanoseconds", 0),
            ("admission_epoch", 1),
            ("admission_oldest_waiting_age_nanoseconds", 0),
            ("admission_reserved_work_units", 0),
            ("admission_maximum_observed_admitted_commands", 0),
            ("admission_maximum_observed_reserved_work_units", 0),
            ("admission_last_started_queue_wait_nanoseconds", 0),
            ("admission_maximum_observed_queue_wait_nanoseconds", 0),
            ("admission_released_commands", 0),
            ("admission_rejected_commands", 0),
            ("admission_duplicate_kind_rejections", 0),
            ("admission_terminal_barrier_rejections", 0),
            ("admission_capacity_rejections", 0),
            ("admission_closed_rejections", 0),
            ("admission_timed_out_commands", 0),
            ("admission_cancelled_before_entry_commands", 0),
            ("admission_closed_before_entry_commands", 0),
            ("actor_event_count", 0),
            ("actor_wire_queue_events", 0),
            ("actor_wire_queue_octets", 0),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=minimum),
            )
        if (
            self.capture_completed_offset_nanoseconds
            < self.capture_started_offset_nanoseconds
        ):
            raise CanonicalizationError("boundary capture completion precedes start")
        for name in ("admission_closed", "admission_terminal_barrier_committed"):
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        for name in (
            "admission_terminal_barrier_admission_sequence",
            "admission_active_admission_sequence",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    canonical_safe_int(value, field=name, minimum=1),
                )
        active_kind = self.admission_active_command_kind
        if active_kind is not None:
            active_kind = canonical_identifier(
                active_kind, field="admission_active_command_kind", maximum=64
            )
            if active_kind not in _A2M_TRANSPORT_COMMAND_KINDS_V49F:
                raise CanonicalizationError(
                    "active admission command kind is unsupported"
                )
            object.__setattr__(self, "admission_active_command_kind", active_kind)
        if (self.admission_active_admission_sequence is None) != (
            self.admission_active_command_kind is None
        ):
            raise CanonicalizationError(
                "active admission sequence and command kind availability differs"
            )
        sequences = self.admission_waiting_admission_sequences
        kinds = self.admission_waiting_command_kinds
        if type(sequences) is not tuple or type(kinds) is not tuple:
            raise CanonicalizationError(
                "waiting admission evidence must use exact tuples"
            )
        normalized_sequences = tuple(
            canonical_safe_int(value, field="waiting_admission_sequence", minimum=1)
            for value in sequences
        )
        normalized_kinds = tuple(
            canonical_identifier(value, field="waiting_command_kind", maximum=64)
            for value in kinds
        )
        if any(
            value not in _A2M_TRANSPORT_COMMAND_KINDS_V49F for value in normalized_kinds
        ):
            raise CanonicalizationError("waiting admission command kind is unsupported")
        if (
            len(normalized_sequences) != len(normalized_kinds)
            or len(set(normalized_sequences)) != len(normalized_sequences)
            or normalized_sequences != tuple(sorted(normalized_sequences))
        ):
            raise CanonicalizationError("waiting admission order is invalid")
        object.__setattr__(
            self, "admission_waiting_admission_sequences", normalized_sequences
        )
        object.__setattr__(self, "admission_waiting_command_kinds", normalized_kinds)
        if (
            self.admission_active_admission_sequence is not None
            or normalized_sequences
            or self.admission_oldest_waiting_age_nanoseconds != 0
            or self.admission_reserved_work_units != 0
        ):
            raise CanonicalizationError("persisted runtime boundary must be quiescent")
        barrier = self.admission_terminal_barrier_admission_sequence
        if (barrier is None) != (not self.admission_terminal_barrier_committed):
            raise CanonicalizationError(
                "quiescent terminal barrier identity and committed state differ"
            )
        if (
            self.admission_maximum_observed_queue_wait_nanoseconds
            < self.admission_last_started_queue_wait_nanoseconds
        ):
            raise CanonicalizationError("maximum admission queue wait regressed")
        if self.admission_rejected_commands != (
            self.admission_duplicate_kind_rejections
            + self.admission_terminal_barrier_rejections
            + self.admission_capacity_rejections
            + self.admission_closed_rejections
        ):
            raise CanonicalizationError(
                "admission rejection total differs from its exact decomposition"
            )
        completed_admissions = (
            self.admission_released_commands
            + self.admission_timed_out_commands
            + self.admission_cancelled_before_entry_commands
            + self.admission_closed_before_entry_commands
        )
        if self.admission_maximum_observed_admitted_commands > completed_admissions:
            raise CanonicalizationError(
                "maximum admitted commands exceeds quiescent completed admissions"
            )
        if (
            self.admission_released_commands > 0
            and self.admission_maximum_observed_admitted_commands == 0
        ):
            raise CanonicalizationError(
                "released admissions require a non-zero historical admitted maximum"
            )
        if (self.admission_maximum_observed_admitted_commands == 0) != (
            self.admission_maximum_observed_reserved_work_units == 0
        ):
            raise CanonicalizationError(
                "admission maximum count and reserved work have different zero states"
            )
        tail = self.actor_tail_event_id
        if tail is not None:
            object.__setattr__(
                self,
                "actor_tail_event_id",
                canonical_hash(tail, field="actor_tail_event_id"),
            )
        if (self.actor_event_count == 0) != (tail is None):
            raise CanonicalizationError(
                "actor tail identity must be present exactly when events exist"
            )
        if (self.actor_wire_queue_events == 0) != (self.actor_wire_queue_octets == 0):
            raise CanonicalizationError(
                "actor wire queue count and octets must have the same zero state"
            )
        state = canonical_identifier(
            self.runtime_state, field="runtime_state", maximum=64
        )
        if state not in _A2M_RUNTIME_STATES_V49F:
            raise CanonicalizationError("runtime_state is unsupported")
        object.__setattr__(self, "runtime_state", state)
        identity = _semantic_identity_v49f(
            domain=A2M_RUNTIME_BOUNDARY_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.boundary_evidence_id is not None
            and self.boundary_evidence_id != identity
        ):
            raise CanonicalizationError(
                "boundary_evidence_id differs from canonical runtime boundary"
            )
        object.__setattr__(self, "boundary_evidence_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"boundary_evidence_id"}
        }
        result["admission_waiting_admission_sequences"] = list(
            self.admission_waiting_admission_sequences
        )
        result["admission_waiting_command_kinds"] = list(
            self.admission_waiting_command_kinds
        )
        return result

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementRuntimeBoundaryEvidenceV49F,
            context="measurement runtime boundary evidence",
        )
        return self._identity_payload_unchecked()

    def _state_payload_unchecked(self) -> dict[str, Any]:
        return {
            name: value
            for name, value in self._identity_payload_unchecked().items()
            if name
            not in {
                "boundary_role",
                "capture_completed_offset_nanoseconds",
                "capture_started_offset_nanoseconds",
            }
        }

    def state_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementRuntimeBoundaryEvidenceV49F,
            context="measurement runtime boundary evidence",
        )
        return self._state_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementRuntimeBoundaryEvidenceV49F,
            context="measurement runtime boundary evidence",
        )
        return _semantic_record_v49f(
            domain=A2M_RUNTIME_BOUNDARY_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="boundary_evidence_id",
            identity=self.boundary_evidence_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementRuntimeBoundaryEvidenceV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_RUNTIME_BOUNDARY_DOMAIN_V49F,
            context="measurement runtime boundary evidence",
        )
        for name in (
            "admission_waiting_admission_sequences",
            "admission_waiting_command_kinds",
        ):
            if type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
        return cls(
            **{
                **item,
                "admission_waiting_admission_sequences": tuple(
                    item["admission_waiting_admission_sequences"]
                ),
                "admission_waiting_command_kinds": tuple(
                    item["admission_waiting_command_kinds"]
                ),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressProgressEvidenceV49F:
    """Exact, bounded, non-capability copy of one returned ingress progress."""

    raw_ingress_commit_id: str
    ingress_sequence: int
    committed_raw_octets: int
    raw_ingress_batch_sha256: str
    parser_event_ids: tuple[str, ...]
    automatic_output_source_parser_event_ids: tuple[str, ...]
    automatic_dispatch_completion_event_ids: tuple[str, ...]
    automatic_protocol_output_base64: str
    automatic_protocol_output_chunk_octet_counts: tuple[int, ...]
    automatic_output_wire_chunk_counts: tuple[int, ...]
    automatic_protocol_output_frames: tuple[
        CapacityMeasurementLogicalOutputFrameV49F, ...
    ]
    actor_event_count_before: int
    actor_tail_event_id_before: str | None
    actor_event_count_after: int
    actor_tail_event_id_after: str | None
    retained_incomplete_octets: int
    used_initial_pending_ingress: bool
    websocket_parser_state: str
    admission_policy_id: str
    admission_epoch: int
    admission_sequence: int
    admission_command_kind: str
    admission_reservation_work_units: int
    admission_admitted_loop_time_offset_nanoseconds: int
    admission_started_loop_time_offset_nanoseconds: int
    admission_start_deadline_loop_time_offset_nanoseconds: int
    admission_queue_wait_nanoseconds: int
    ingress_progress_evidence_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "raw_ingress_commit_id",
            "raw_ingress_batch_sha256",
            "admission_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name, minimum, maximum in (
            ("ingress_sequence", 1, None),
            ("committed_raw_octets", 1, A2M_MAXIMUM_PENDING_RAW_OCTETS_V49F),
            ("actor_event_count_before", 0, None),
            ("actor_event_count_after", 0, None),
            ("retained_incomplete_octets", 0, A2M_MAXIMUM_DURABLE_INGRESS_OCTETS_V49F),
            ("admission_epoch", 1, None),
            ("admission_sequence", 1, None),
            ("admission_reservation_work_units", 1, None),
            ("admission_admitted_loop_time_offset_nanoseconds", 0, None),
            ("admission_started_loop_time_offset_nanoseconds", 0, None),
            ("admission_start_deadline_loop_time_offset_nanoseconds", 0, None),
            ("admission_queue_wait_nanoseconds", 0, None),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(
                    getattr(self, name), field=name, minimum=minimum, maximum=maximum
                ),
            )
        command_kind = canonical_identifier(
            self.admission_command_kind, field="admission_command_kind", maximum=64
        )
        if command_kind != "INGRESS":
            raise CanonicalizationError("returned admission command must be INGRESS")
        object.__setattr__(self, "admission_command_kind", command_kind)
        admitted = self.admission_admitted_loop_time_offset_nanoseconds
        started = self.admission_started_loop_time_offset_nanoseconds
        deadline = self.admission_start_deadline_loop_time_offset_nanoseconds
        if not admitted <= started <= deadline:
            raise CanonicalizationError("returned admission grant timing is invalid")
        if self.admission_queue_wait_nanoseconds != started - admitted:
            raise CanonicalizationError(
                "returned admission queue wait differs from its exact grant span"
            )
        if type(self.used_initial_pending_ingress) is not bool:
            raise CanonicalizationError(
                "used_initial_pending_ingress must be an exact boolean"
            )
        state = canonical_identifier(
            self.websocket_parser_state, field="websocket_parser_state", maximum=32
        )
        if state not in {"OPEN", "CLOSING", "CLOSED", "FAILED"}:
            raise CanonicalizationError("websocket_parser_state is unsupported")
        object.__setattr__(self, "websocket_parser_state", state)

        for name in (
            "parser_event_ids",
            "automatic_output_source_parser_event_ids",
            "automatic_dispatch_completion_event_ids",
        ):
            values = getattr(self, name)
            if values is None:
                continue
            if type(values) is not tuple:
                raise CanonicalizationError(f"{name} must be an exact tuple")
            if len(values) > A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F:
                raise CanonicalizationError(f"{name} exceeds the ingress-unit bound")
            normalized = tuple(canonical_hash(value, field=name) for value in values)
            if len(set(normalized)) != len(normalized):
                raise CanonicalizationError(f"{name} contains duplicate event IDs")
            object.__setattr__(self, name, normalized)
        if any(
            value not in self.parser_event_ids
            for value in self.automatic_output_source_parser_event_ids
        ):
            raise CanonicalizationError(
                "automatic output source is absent from parser event IDs"
            )
        source_positions = tuple(
            self.parser_event_ids.index(value)
            for value in self.automatic_output_source_parser_event_ids
        )
        if source_positions != tuple(sorted(source_positions)):
            raise CanonicalizationError(
                "automatic output sources are not an ordered parser subsequence"
            )
        if set(self.parser_event_ids) & set(
            self.automatic_dispatch_completion_event_ids
        ):
            raise CanonicalizationError(
                "parser and automatic completion event IDs must be disjoint"
            )

        encoded = self.automatic_protocol_output_base64
        output = _canonical_base64_bytes(
            encoded,
            field="automatic_protocol_output_base64",
            maximum_decoded_octets=(
                A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F
            ),
        )
        lengths = self.automatic_protocol_output_chunk_octet_counts
        if type(lengths) is not tuple:
            raise CanonicalizationError(
                "automatic_protocol_output_chunk_octet_counts must be an exact tuple"
            )
        if len(lengths) > A2M_MAXIMUM_RAW_SAMPLE_OUTPUT_CHUNKS_V49F:
            raise CanonicalizationError(
                "automatic output chunk count exceeds its bound"
            )
        normalized_lengths = tuple(
            canonical_safe_int(
                value,
                field="automatic_protocol_output_chunk_octet_counts",
                minimum=1,
                maximum=131,
            )
            for value in lengths
        )
        if sum(normalized_lengths) != len(output):
            raise CanonicalizationError(
                "automatic output chunk partition differs from exact output bytes"
            )
        object.__setattr__(
            self, "automatic_protocol_output_chunk_octet_counts", normalized_lengths
        )
        group_counts = self.automatic_output_wire_chunk_counts
        if type(group_counts) is not tuple:
            raise CanonicalizationError(
                "automatic_output_wire_chunk_counts must be an exact tuple"
            )
        normalized_groups = tuple(
            canonical_safe_int(
                value,
                field="automatic_output_wire_chunk_counts",
                minimum=1,
                maximum=A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F,
            )
            for value in group_counts
        )
        object.__setattr__(
            self, "automatic_output_wire_chunk_counts", normalized_groups
        )
        frames = self.automatic_protocol_output_frames
        if type(frames) is not tuple or any(
            type(frame) is not CapacityMeasurementLogicalOutputFrameV49F
            for frame in frames
        ):
            raise CanonicalizationError(
                "automatic_protocol_output_frames must contain exact frame evidence"
            )
        _canonical_logical_output_frames_v49f(
            tuple((frame.opcode, frame.payload) for frame in frames),
            field="automatic_protocol_output_frames",
        )
        if not (
            len(frames)
            == len(self.automatic_output_source_parser_event_ids)
            == len(self.automatic_dispatch_completion_event_ids)
            == len(normalized_groups)
        ) or sum(normalized_groups) != len(normalized_lengths):
            raise CanonicalizationError(
                "automatic logical, physical, source, and completion evidence differs"
            )
        if bool(frames) != bool(output):
            raise CanonicalizationError(
                "logical and physical automatic output zero states differ"
            )
        physical_chunks: list[bytes] = []
        octet_cursor = 0
        for length in normalized_lengths:
            physical_chunks.append(output[octet_cursor : octet_cursor + length])
            octet_cursor += length
        decoded_frames: list[tuple[str, bytes]] = []
        chunk_cursor = 0
        for group_count in normalized_groups:
            group = tuple(physical_chunks[chunk_cursor : chunk_cursor + group_count])
            decoded_frames.append(_decode_exact_masked_control_frame_v49f(group))
            chunk_cursor += group_count
        if tuple(decoded_frames) != tuple(
            (frame.opcode, frame.payload) for frame in frames
        ):
            raise CanonicalizationError(
                "automatic physical output differs from logical frame evidence"
            )
        for count_name, tail_name in (
            ("actor_event_count_before", "actor_tail_event_id_before"),
            ("actor_event_count_after", "actor_tail_event_id_after"),
        ):
            tail = getattr(self, tail_name)
            if tail is not None:
                object.__setattr__(
                    self, tail_name, canonical_hash(tail, field=tail_name)
                )
            if (getattr(self, count_name) == 0) != (tail is None):
                raise CanonicalizationError(
                    f"{tail_name} must be present exactly when actor events exist"
                )
        if self.actor_event_count_after < self.actor_event_count_before:
            raise CanonicalizationError("actor event count regressed during ingress")
        identity = _semantic_identity_v49f(
            domain=A2M_INGRESS_PROGRESS_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.ingress_progress_evidence_id is not None
            and self.ingress_progress_evidence_id != identity
        ):
            raise CanonicalizationError(
                "ingress_progress_evidence_id differs from canonical progress"
            )
        object.__setattr__(self, "ingress_progress_evidence_id", identity)

    @property
    def automatic_protocol_output_chunks(self) -> tuple[bytes, ...]:
        output = _canonical_base64_bytes(
            self.automatic_protocol_output_base64,
            field="automatic_protocol_output_base64",
            maximum_decoded_octets=(
                A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F
            ),
        )
        chunks: list[bytes] = []
        cursor = 0
        for length in self.automatic_protocol_output_chunk_octet_counts:
            chunks.append(output[cursor : cursor + length])
            cursor += length
        return tuple(chunks)

    @property
    def logical_output_frames(self) -> tuple[tuple[str, bytes], ...]:
        return tuple(
            (frame.opcode, frame.payload)
            for frame in self.automatic_protocol_output_frames
        )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in _record_keys(type(self)) - {"ingress_progress_evidence_id"}:
            value = getattr(self, name)
            if name in {
                "parser_event_ids",
                "automatic_output_source_parser_event_ids",
                "automatic_dispatch_completion_event_ids",
                "automatic_protocol_output_chunk_octet_counts",
                "automatic_output_wire_chunk_counts",
            }:
                value = list(value)
            elif name == "automatic_protocol_output_frames":
                value = [frame.as_dict() for frame in value]
            result[name] = value
        return result

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIngressProgressEvidenceV49F,
            context="measurement ingress progress evidence",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIngressProgressEvidenceV49F,
            context="measurement ingress progress evidence",
        )
        return _semantic_record_v49f(
            domain=A2M_INGRESS_PROGRESS_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="ingress_progress_evidence_id",
            identity=self.ingress_progress_evidence_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIngressProgressEvidenceV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_INGRESS_PROGRESS_DOMAIN_V49F,
            context="measurement ingress progress evidence",
        )
        for name in (
            "parser_event_ids",
            "automatic_output_source_parser_event_ids",
            "automatic_dispatch_completion_event_ids",
            "automatic_protocol_output_chunk_octet_counts",
            "automatic_output_wire_chunk_counts",
            "automatic_protocol_output_frames",
        ):
            if type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
        return cls(
            **{
                **item,
                "parser_event_ids": tuple(item["parser_event_ids"]),
                "automatic_output_source_parser_event_ids": tuple(
                    item["automatic_output_source_parser_event_ids"]
                ),
                "automatic_dispatch_completion_event_ids": tuple(
                    item["automatic_dispatch_completion_event_ids"]
                ),
                "automatic_protocol_output_chunk_octet_counts": tuple(
                    item["automatic_protocol_output_chunk_octet_counts"]
                ),
                "automatic_output_wire_chunk_counts": tuple(
                    item["automatic_output_wire_chunk_counts"]
                ),
                "automatic_protocol_output_frames": tuple(
                    CapacityMeasurementLogicalOutputFrameV49F.from_mapping(value)
                    for value in item["automatic_protocol_output_frames"]
                ),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSampleV49F:
    campaign_manifest_id: str
    manifest_authority_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    source_identity_sha256: str
    runtime_identity_sha256: str
    workload_corpus_sha256: str
    measurement_design_id: str
    sample_sequence: int
    parent_sample_id: str | None
    workload_id: str
    workload_sha256: str
    trial_index: int
    repetition_index: int
    is_warmup: bool
    stage: str
    observer_start_offset_nanoseconds: int
    observer_end_offset_nanoseconds: int
    boottime_start_offset_nanoseconds: int
    boottime_end_offset_nanoseconds: int
    loop_time_start_offset_nanoseconds: int
    loop_time_end_offset_nanoseconds: int
    operation_start_offset_nanoseconds: int
    operation_end_offset_nanoseconds: int
    initial_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F
    before_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F
    returned_ingress_progress: CapacityMeasurementIngressProgressEvidenceV49F | None
    returned_ingress_progress_unavailable_reason: str | None
    after_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F
    raw_ingress_commit_id: str | None
    raw_ingress_sequence: int | None
    raw_ingress_batch_sha256: str | None
    parser_event_ids: tuple[str, ...] | None
    automatic_output_source_parser_event_ids: tuple[str, ...] | None
    automatic_dispatch_completion_event_ids: tuple[str, ...] | None
    automatic_output_wire_chunk_counts: tuple[int, ...] | None
    admission_attribution: str
    admission_policy_id: str | None
    admission_epoch: int | None
    admission_sequence: int | None
    admission_queue_wait_nanoseconds: int | None
    input_chunk_count: int
    input_octet_count: int
    input_sha256: str
    output_chunk_count: int | None
    output_octet_count: int | None
    observed_output_sha256: str | None
    observed_output_batch_sha256: str | None
    output_frame_count: int | None
    expected_output_frame_count: int
    observed_output_frames_sha256: str | None
    expected_output_frames_sha256: str
    before_snapshot: CapacityMeasurementLayerSnapshotV49F
    in_operation_snapshot: CapacityMeasurementLayerSnapshotV49F
    after_snapshot: CapacityMeasurementLayerSnapshotV49F
    operation_outcome: CapacityMeasurementOutcomeV49F
    operation_error_code: str | None
    operation_exception_class: str | None
    measurement_outcome: CapacityMeasurementOutcomeV49F
    measurement_error_code: str | None
    sample_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "source_identity_sha256",
            "runtime_identity_sha256",
            "workload_corpus_sha256",
            "measurement_design_id",
            "workload_sha256",
            "input_sha256",
            "expected_output_frames_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in (
            "observed_output_sha256",
            "observed_output_batch_sha256",
            "observed_output_frames_sha256",
        ):
            object.__setattr__(
                self, name, _optional_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "parent_sample_id",
            _optional_hash(self.parent_sample_id, field="parent_sample_id"),
        )
        object.__setattr__(
            self,
            "raw_ingress_commit_id",
            _optional_hash(self.raw_ingress_commit_id, field="raw_ingress_commit_id"),
        )
        object.__setattr__(
            self,
            "raw_ingress_batch_sha256",
            _optional_hash(
                self.raw_ingress_batch_sha256, field="raw_ingress_batch_sha256"
            ),
        )
        for name in (
            "parser_event_ids",
            "automatic_output_source_parser_event_ids",
            "automatic_dispatch_completion_event_ids",
        ):
            values = getattr(self, name)
            if values is None:
                continue
            if type(values) is not tuple:
                raise CanonicalizationError(f"{name} must be an exact tuple")
            if (
                name == "parser_event_ids"
                and len(values) > A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F
            ):
                raise CanonicalizationError(
                    "parser_event_ids exceeds the aggregate ingress-unit bound"
                )
            normalized = tuple(canonical_hash(value, field=name) for value in values)
            if len(set(normalized)) != len(normalized):
                raise CanonicalizationError(f"{name} contains duplicate event IDs")
            object.__setattr__(self, name, normalized)
        chunk_counts = self.automatic_output_wire_chunk_counts
        if chunk_counts is not None and type(chunk_counts) is not tuple:
            raise CanonicalizationError(
                "automatic_output_wire_chunk_counts must be an exact tuple or null"
            )
        if chunk_counts is not None:
            object.__setattr__(
                self,
                "automatic_output_wire_chunk_counts",
                tuple(
                    canonical_safe_int(
                        value,
                        field="automatic_output_wire_chunk_counts",
                        minimum=1,
                        maximum=A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F,
                    )
                    for value in chunk_counts
                ),
            )
        object.__setattr__(
            self,
            "workload_id",
            canonical_identifier(self.workload_id, field="workload_id"),
        )
        object.__setattr__(
            self, "stage", canonical_identifier(self.stage, field="stage")
        )
        object.__setattr__(
            self,
            "admission_attribution",
            canonical_identifier(
                self.admission_attribution, field="admission_attribution", maximum=64
            ),
        )
        if self.admission_attribution not in {
            "EXACT_RETURNED_GRANT",
            "UNAVAILABLE",
        }:
            raise CanonicalizationError("admission_attribution is unsupported")
        for name, minimum in (
            ("sample_sequence", 1),
            ("trial_index", 0),
            ("repetition_index", 0),
            ("observer_start_offset_nanoseconds", 0),
            ("observer_end_offset_nanoseconds", 0),
            ("boottime_start_offset_nanoseconds", 0),
            ("boottime_end_offset_nanoseconds", 0),
            ("loop_time_start_offset_nanoseconds", 0),
            ("loop_time_end_offset_nanoseconds", 0),
            ("operation_start_offset_nanoseconds", 0),
            ("operation_end_offset_nanoseconds", 0),
            ("input_chunk_count", 0),
            ("input_octet_count", 0),
            ("expected_output_frame_count", 0),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=minimum),
            )
        for name in ("output_chunk_count", "output_octet_count", "output_frame_count"):
            object.__setattr__(
                self, name, _optional_safe_int(getattr(self, name), field=name)
            )
        if (
            self.output_chunk_count is not None
            and self.output_chunk_count > A2M_MAXIMUM_RAW_SAMPLE_OUTPUT_CHUNKS_V49F
        ):
            raise CanonicalizationError(
                "output_chunk_count exceeds the raw-sample source-snapshot bound"
            )
        if (
            self.output_octet_count is not None
            and self.output_octet_count
            > A2M_MAXIMUM_RAW_SAMPLE_SERIALIZED_WEBSOCKET_WIRE_OCTETS_V49F
        ):
            raise CanonicalizationError(
                "output_octet_count exceeds the serialized WebSocket-wire "
                "source-snapshot bound"
            )
        if (
            self.output_frame_count is not None
            and self.output_frame_count
            > A2M_MAXIMUM_AUTOMATIC_OUTPUT_FRAMES_PER_INGRESS_V49F
        ):
            raise CanonicalizationError(
                "output_frame_count exceeds the aggregate automatic-output bound"
            )
        if self.expected_output_frame_count > A2M_MAXIMUM_STAGED_WIRE_CHUNKS_V49F:
            raise CanonicalizationError(
                "expected_output_frame_count exceeds the workload output bound"
            )
        if (
            self.observer_end_offset_nanoseconds
            < self.observer_start_offset_nanoseconds
        ):
            raise CanonicalizationError("observer end offset precedes start offset")
        for start_name, end_name, domain in (
            (
                "boottime_start_offset_nanoseconds",
                "boottime_end_offset_nanoseconds",
                "BOOTTIME",
            ),
            (
                "loop_time_start_offset_nanoseconds",
                "loop_time_end_offset_nanoseconds",
                "EVENT_LOOP",
            ),
        ):
            if getattr(self, end_name) < getattr(self, start_name):
                raise CanonicalizationError(
                    f"{domain} end offset precedes its start offset"
                )
        if not (
            self.observer_start_offset_nanoseconds
            <= self.operation_start_offset_nanoseconds
            <= self.operation_end_offset_nanoseconds
            <= self.observer_end_offset_nanoseconds
        ):
            raise CanonicalizationError(
                "operation span must be enclosed by its observer span"
            )
        if type(self.is_warmup) is not bool:
            raise CanonicalizationError("is_warmup must be an exact boolean")
        for name in ("before_snapshot", "in_operation_snapshot", "after_snapshot"):
            if type(getattr(self, name)) is not CapacityMeasurementLayerSnapshotV49F:
                raise CanonicalizationError(f"{name} must be an exact layer snapshot")
        for name, expected_role in (
            ("initial_runtime_boundary", "INITIAL"),
            ("before_runtime_boundary", "BEFORE_OPERATION"),
            ("after_runtime_boundary", "AFTER_OPERATION"),
        ):
            boundary = getattr(self, name)
            if type(boundary) is not CapacityMeasurementRuntimeBoundaryEvidenceV49F:
                raise CanonicalizationError(f"{name} must be exact runtime evidence")
            if boundary.boundary_role != expected_role:
                raise CanonicalizationError(f"{name} has the wrong boundary role")
            if (
                boundary.transport_session_id != self.transport_session_id
                or boundary.driver_evidence_nonce_sha256
                != self.driver_evidence_nonce_sha256
                or boundary.kernel_socket_identity != self.kernel_socket_identity
            ):
                raise CanonicalizationError(f"{name} has a foreign runtime identity")
            if not (
                self.observer_start_offset_nanoseconds
                <= boundary.capture_started_offset_nanoseconds
                <= boundary.capture_completed_offset_nanoseconds
                <= self.observer_end_offset_nanoseconds
            ):
                raise CanonicalizationError(f"{name} falls outside the observer span")
        if not (
            self.initial_runtime_boundary.capture_completed_offset_nanoseconds
            <= self.before_snapshot.observed_offset_nanoseconds
            <= self.before_runtime_boundary.capture_started_offset_nanoseconds
            <= self.before_runtime_boundary.capture_completed_offset_nanoseconds
            <= self.operation_start_offset_nanoseconds
            <= self.operation_end_offset_nanoseconds
            <= self.after_snapshot.observed_offset_nanoseconds
            <= self.after_runtime_boundary.capture_started_offset_nanoseconds
        ):
            raise CanonicalizationError(
                "runtime boundaries do not enclose the operation in causal order"
            )
        for before_boundary, after_boundary in (
            (self.initial_runtime_boundary, self.before_runtime_boundary),
            (self.before_runtime_boundary, self.after_runtime_boundary),
        ):
            if after_boundary.admission_epoch < before_boundary.admission_epoch:
                raise CanonicalizationError("runtime admission epoch regressed")
            if after_boundary.actor_event_count < before_boundary.actor_event_count:
                raise CanonicalizationError("runtime actor event count regressed")
            for field in (
                "admission_released_commands",
                "admission_rejected_commands",
                "admission_duplicate_kind_rejections",
                "admission_terminal_barrier_rejections",
                "admission_capacity_rejections",
                "admission_closed_rejections",
                "admission_timed_out_commands",
                "admission_cancelled_before_entry_commands",
                "admission_closed_before_entry_commands",
                "admission_maximum_observed_admitted_commands",
                "admission_maximum_observed_reserved_work_units",
                "admission_maximum_observed_queue_wait_nanoseconds",
            ):
                if getattr(after_boundary, field) < getattr(before_boundary, field):
                    raise CanonicalizationError(
                        f"runtime boundary counter {field} regressed"
                    )
        progress = self.returned_ingress_progress
        reason = _optional_identifier(
            self.returned_ingress_progress_unavailable_reason,
            field="returned_ingress_progress_unavailable_reason",
            maximum=128,
        )
        object.__setattr__(self, "returned_ingress_progress_unavailable_reason", reason)
        if progress is None:
            if reason != A2M_RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION_V49F:
                raise CanonicalizationError(
                    "missing returned ingress progress requires its exact reason"
                )
        else:
            if type(progress) is not CapacityMeasurementIngressProgressEvidenceV49F:
                raise CanonicalizationError(
                    "returned_ingress_progress must be exact progress evidence"
                )
            if reason is not None:
                raise CanonicalizationError(
                    "returned ingress progress cannot also be unavailable"
                )
            if not (
                self.loop_time_start_offset_nanoseconds
                <= progress.admission_admitted_loop_time_offset_nanoseconds
                <= progress.admission_started_loop_time_offset_nanoseconds
                <= self.loop_time_end_offset_nanoseconds
                and progress.admission_started_loop_time_offset_nanoseconds
                <= progress.admission_start_deadline_loop_time_offset_nanoseconds
            ):
                raise CanonicalizationError(
                    "returned admission grant falls outside the sample loop-clock span"
                )
            if (
                progress.admission_reservation_work_units
                > self.after_runtime_boundary.admission_maximum_observed_reserved_work_units
            ):
                raise CanonicalizationError(
                    "returned admission reservation exceeds the after-boundary "
                    "historical maximum"
                )
            if (
                progress.admission_queue_wait_nanoseconds
                > self.after_runtime_boundary.admission_maximum_observed_queue_wait_nanoseconds
            ):
                raise CanonicalizationError(
                    "returned admission queue wait exceeds the after-boundary "
                    "historical maximum"
                )
        raw_values = (
            self.raw_ingress_commit_id,
            self.raw_ingress_sequence,
            self.raw_ingress_batch_sha256,
        )
        if any(value is None for value in raw_values) and not all(
            value is None for value in raw_values
        ):
            raise CanonicalizationError(
                "RAW commit ID, sequence, and batch hash must be present together"
            )
        if self.raw_ingress_sequence is not None:
            object.__setattr__(
                self,
                "raw_ingress_sequence",
                canonical_safe_int(
                    self.raw_ingress_sequence, field="raw_ingress_sequence", minimum=1
                ),
            )
        admission_values = (
            self.admission_policy_id,
            self.admission_epoch,
            self.admission_sequence,
            self.admission_queue_wait_nanoseconds,
        )
        if any(value is None for value in admission_values) and not all(
            value is None for value in admission_values
        ):
            raise CanonicalizationError(
                "admission coordinates must be present together"
            )
        if self.admission_policy_id is not None:
            object.__setattr__(
                self,
                "admission_policy_id",
                canonical_hash(self.admission_policy_id, field="admission_policy_id"),
            )
            for name, minimum in (
                ("admission_epoch", 1),
                ("admission_sequence", 1),
                ("admission_queue_wait_nanoseconds", 0),
            ):
                object.__setattr__(
                    self,
                    name,
                    canonical_safe_int(
                        getattr(self, name), field=name, minimum=minimum
                    ),
                )
        if self.admission_attribution == "EXACT_RETURNED_GRANT":
            if self.admission_policy_id is None:
                raise CanonicalizationError(
                    "exact admission attribution requires grant coordinates"
                )
        elif self.admission_policy_id is not None:
            raise CanonicalizationError(
                "non-exact admission attribution cannot claim grant coordinates"
            )
        if (self.input_chunk_count == 0) != (self.input_octet_count == 0):
            raise CanonicalizationError(
                "input_chunk_count and input_octet_count zero states differ"
            )
        empty_sha256 = hashlib.sha256(b"").hexdigest()
        if self.input_octet_count == 0 and self.input_sha256 != empty_sha256:
            raise CanonicalizationError(
                "zero input requires the SHA-256 of empty bytes"
            )
        progress_summary_fields = (
            self.raw_ingress_commit_id,
            self.raw_ingress_sequence,
            self.raw_ingress_batch_sha256,
            self.parser_event_ids,
            self.automatic_output_source_parser_event_ids,
            self.automatic_dispatch_completion_event_ids,
            self.automatic_output_wire_chunk_counts,
            self.admission_policy_id,
            self.admission_epoch,
            self.admission_sequence,
            self.admission_queue_wait_nanoseconds,
            self.output_chunk_count,
            self.output_octet_count,
            self.observed_output_sha256,
            self.observed_output_batch_sha256,
            self.output_frame_count,
            self.observed_output_frames_sha256,
        )
        if progress is None:
            if any(value is not None for value in progress_summary_fields):
                raise CanonicalizationError(
                    "unavailable returned progress cannot claim derived summaries"
                )
            if self.admission_attribution != "UNAVAILABLE":
                raise CanonicalizationError(
                    "unavailable returned progress requires unavailable admission attribution"
                )
        else:
            if any(value is None for value in progress_summary_fields):
                raise CanonicalizationError(
                    "returned progress requires every derived summary"
                )
            output_chunks = progress.automatic_protocol_output_chunks
            output_bytes = b"".join(output_chunks)
            expected_summary = {
                "raw_ingress_commit_id": progress.raw_ingress_commit_id,
                "raw_ingress_sequence": progress.ingress_sequence,
                "raw_ingress_batch_sha256": progress.raw_ingress_batch_sha256,
                "parser_event_ids": progress.parser_event_ids,
                "automatic_output_source_parser_event_ids": (
                    progress.automatic_output_source_parser_event_ids
                ),
                "automatic_dispatch_completion_event_ids": (
                    progress.automatic_dispatch_completion_event_ids
                ),
                "automatic_output_wire_chunk_counts": (
                    progress.automatic_output_wire_chunk_counts
                ),
                "admission_policy_id": progress.admission_policy_id,
                "admission_epoch": progress.admission_epoch,
                "admission_sequence": progress.admission_sequence,
                "admission_queue_wait_nanoseconds": (
                    progress.admission_queue_wait_nanoseconds
                ),
                "output_chunk_count": len(output_chunks),
                "output_octet_count": len(output_bytes),
                "observed_output_sha256": hashlib.sha256(output_bytes).hexdigest(),
                "observed_output_batch_sha256": sha256_digest(
                    {
                        "domain": "RiskYieldMMA2MExactOrderedOutputChunksV4_9F",
                        "ordered_chunks_base64": [
                            base64.b64encode(chunk).decode("ascii")
                            for chunk in output_chunks
                        ],
                    }
                ),
                "output_frame_count": len(progress.logical_output_frames),
                "observed_output_frames_sha256": (
                    capacity_measurement_logical_frames_sha256_v49f(
                        progress.logical_output_frames
                    )
                ),
            }
            for name, expected in expected_summary.items():
                if getattr(self, name) != expected:
                    raise CanonicalizationError(
                        f"{name} differs from exact returned progress evidence"
                    )
            if self.admission_attribution != "EXACT_RETURNED_GRANT":
                raise CanonicalizationError(
                    "returned progress requires exact admission attribution"
                )
            assert self.output_chunk_count is not None
            assert self.output_octet_count is not None
            assert self.output_frame_count is not None
            if (self.output_chunk_count == 0) != (self.output_octet_count == 0):
                raise CanonicalizationError("output chunk and octet zero states differ")
            if (self.output_frame_count == 0) != (self.output_chunk_count == 0):
                raise CanonicalizationError(
                    "logical and physical output zero states differ"
                )
            if (
                self.output_octet_count == 0
                and self.observed_output_sha256 != empty_sha256
            ):
                raise CanonicalizationError(
                    "zero observed output requires the SHA-256 of empty bytes"
                )
        empty_logical_frames = capacity_measurement_logical_frames_sha256_v49f(())
        if self.output_frame_count == 0 and (
            self.observed_output_frames_sha256 != empty_logical_frames
        ):
            raise CanonicalizationError(
                "zero observed frames require the canonical empty logical-frame hash"
            )
        if self.expected_output_frame_count == 0 and (
            self.expected_output_frames_sha256 != empty_logical_frames
        ):
            raise CanonicalizationError(
                "zero expected frames require the canonical empty logical-frame hash"
            )
        for name in (
            "before_snapshot",
            "in_operation_snapshot",
            "after_snapshot",
        ):
            snapshot = getattr(self, name)
            if type(snapshot) is not CapacityMeasurementLayerSnapshotV49F:
                raise CanonicalizationError(f"{name} must be an exact layer snapshot")
            if not (
                self.observer_start_offset_nanoseconds
                <= snapshot.observed_offset_nanoseconds
                <= self.observer_end_offset_nanoseconds
            ):
                raise CanonicalizationError(
                    f"{name} falls outside the observed sample span"
                )
            if (
                snapshot.kernel_socket_identity is not None
                and snapshot.kernel_socket_identity != self.kernel_socket_identity
            ):
                raise CanonicalizationError(
                    f"{name} has a foreign kernel socket identity"
                )
            for span in snapshot.adapter_spans:
                if not (
                    self.observer_start_offset_nanoseconds
                    <= span.observation_started_offset_nanoseconds
                    <= span.observation_completed_offset_nanoseconds
                    <= self.observer_end_offset_nanoseconds
                ):
                    raise CanonicalizationError(
                        f"{name} adapter span falls outside the observed sample span"
                    )
        if (
            self.before_snapshot.observed_offset_nanoseconds
            > self.operation_start_offset_nanoseconds
        ):
            raise CanonicalizationError(
                "before_snapshot must complete before the operation starts"
            )
        if any(
            span.observation_started_offset_nanoseconds
            < self.operation_start_offset_nanoseconds
            or span.observation_completed_offset_nanoseconds
            > self.operation_end_offset_nanoseconds
            for span in self.in_operation_snapshot.adapter_spans
        ):
            raise CanonicalizationError(
                "in_operation_snapshot must lie inside the operation span"
            )
        if any(
            span.observation_started_offset_nanoseconds
            < self.operation_end_offset_nanoseconds
            for span in self.after_snapshot.adapter_spans
        ):
            raise CanonicalizationError(
                "after_snapshot must start after the operation completes"
            )
        if not (
            self.before_snapshot.observed_offset_nanoseconds
            <= self.in_operation_snapshot.observed_offset_nanoseconds
            <= self.after_snapshot.observed_offset_nanoseconds
        ):
            raise CanonicalizationError(
                "snapshot observation offsets are not monotonic"
            )
        for snapshot_name, snapshot in (
            ("before_snapshot", self.before_snapshot),
            ("after_snapshot", self.after_snapshot),
        ):
            boundary_values = (
                snapshot.admission_active_commands,
                snapshot.admission_waiting_commands,
                snapshot.admission_reserved_work_units,
            )
            if all(
                value is not None for value in boundary_values
            ) and boundary_values != (
                0,
                0,
                0,
            ):
                raise CanonicalizationError(
                    f"{snapshot_name} must be an admission-quiescent boundary"
                )
        for field in ("actor_event_count", "admission_capacity_rejections"):
            before_value = getattr(self.before_snapshot, field)
            after_value = getattr(self.after_snapshot, field)
            if (
                before_value is not None
                and after_value is not None
                and after_value < before_value
            ):
                raise CanonicalizationError(f"{field} regressed across the operation")
        object.__setattr__(
            self,
            "operation_outcome",
            _exact_enum(
                self.operation_outcome,
                CapacityMeasurementOutcomeV49F,
                field="operation_outcome",
            ),
        )
        object.__setattr__(
            self,
            "operation_error_code",
            _optional_identifier(
                self.operation_error_code, field="operation_error_code"
            ),
        )
        object.__setattr__(
            self,
            "operation_exception_class",
            _optional_identifier(
                self.operation_exception_class,
                field="operation_exception_class",
                maximum=128,
            ),
        )
        object.__setattr__(
            self,
            "measurement_outcome",
            _exact_enum(
                self.measurement_outcome,
                CapacityMeasurementOutcomeV49F,
                field="measurement_outcome",
            ),
        )
        object.__setattr__(
            self,
            "measurement_error_code",
            _optional_identifier(
                self.measurement_error_code, field="measurement_error_code"
            ),
        )
        if self.operation_outcome is CapacityMeasurementOutcomeV49F.PASS:
            if self.operation_error_code is not None:
                raise CanonicalizationError(
                    "PASS operation cannot contain an operation_error_code"
                )
            if (
                self.output_frame_count != self.expected_output_frame_count
                or self.observed_output_frames_sha256
                != self.expected_output_frames_sha256
            ):
                raise CanonicalizationError(
                    "PASS sample logical output differs from expected output"
                )
            if self.raw_ingress_commit_id is None:
                raise CanonicalizationError(
                    "PASS ingress operation requires exact RAW commit evidence"
                )
            if self.admission_attribution != "EXACT_RETURNED_GRANT":
                raise CanonicalizationError(
                    "PASS ingress operation requires an exact admission grant"
                )
        elif self.operation_error_code is None:
            raise CanonicalizationError(
                "non-PASS operation requires an operation_error_code"
            )
        exception_expected = self.operation_error_code == "INGRESS_OPERATION_EXCEPTION"
        if exception_expected != (self.operation_exception_class is not None):
            raise CanonicalizationError(
                "operation exception class must be present exactly for an ingress exception"
            )
        if exception_expected != (progress is None):
            raise CanonicalizationError(
                "returned progress availability differs from operation exception evidence"
            )
        boundary_policies = {
            self.initial_runtime_boundary.transport_capacity_policy_id,
            self.before_runtime_boundary.transport_capacity_policy_id,
            self.after_runtime_boundary.transport_capacity_policy_id,
        }
        if len(boundary_policies) != 1:
            raise CanonicalizationError("runtime boundaries cross admission policies")
        if self.measurement_outcome is CapacityMeasurementOutcomeV49F.PASS:
            if self.measurement_error_code is not None:
                raise CanonicalizationError(
                    "PASS measurement cannot contain a measurement_error_code"
                )
            if any(
                snapshot.unavailable_fields
                for snapshot in (
                    self.before_snapshot,
                    self.in_operation_snapshot,
                    self.after_snapshot,
                )
            ):
                raise CanonicalizationError(
                    "PASS measurement cannot contain unavailable observations"
                )
            for snapshot, boundary in (
                (self.before_snapshot, self.before_runtime_boundary),
                (self.after_snapshot, self.after_runtime_boundary),
            ):
                if (
                    snapshot.kernel_socket_identity != boundary.kernel_socket_identity
                    or snapshot.admission_active_commands != 0
                    or snapshot.admission_waiting_commands != 0
                    or snapshot.admission_reserved_work_units
                    != boundary.admission_reserved_work_units
                    or snapshot.admission_capacity_rejections
                    != boundary.admission_capacity_rejections
                    or snapshot.admission_queue_wait_nanoseconds
                    != boundary.admission_last_started_queue_wait_nanoseconds
                    or snapshot.actor_event_count != boundary.actor_event_count
                    or snapshot.actor_wire_queue_events
                    != boundary.actor_wire_queue_events
                    or snapshot.actor_wire_queue_octets
                    != boundary.actor_wire_queue_octets
                ):
                    raise CanonicalizationError(
                        "PASS measurement snapshot differs from exact runtime boundary"
                    )
            if progress is None:
                raise CanonicalizationError(
                    "PASS measurement requires exact returned progress"
                )
            if (
                self.initial_runtime_boundary.state_payload()
                != self.before_runtime_boundary.state_payload()
                or progress.actor_event_count_before
                != self.before_runtime_boundary.actor_event_count
                or progress.actor_tail_event_id_before
                != self.before_runtime_boundary.actor_tail_event_id
                or progress.actor_event_count_after
                != self.after_runtime_boundary.actor_event_count
                or progress.actor_tail_event_id_after
                != self.after_runtime_boundary.actor_tail_event_id
                or progress.admission_policy_id
                != self.before_runtime_boundary.transport_capacity_policy_id
                or progress.admission_epoch
                != self.before_runtime_boundary.admission_epoch
                or self.after_runtime_boundary.admission_epoch
                != self.before_runtime_boundary.admission_epoch
                or self.after_runtime_boundary.admission_released_commands
                != self.before_runtime_boundary.admission_released_commands + 1
                or progress.admission_queue_wait_nanoseconds
                != self.after_runtime_boundary.admission_last_started_queue_wait_nanoseconds
            ):
                raise CanonicalizationError(
                    "PASS measurement runtime boundary/progress evidence is inconsistent"
                )
            unchanged_counters = (
                "admission_rejected_commands",
                "admission_duplicate_kind_rejections",
                "admission_terminal_barrier_rejections",
                "admission_capacity_rejections",
                "admission_closed_rejections",
                "admission_timed_out_commands",
                "admission_cancelled_before_entry_commands",
                "admission_closed_before_entry_commands",
            )
            if any(
                getattr(self.after_runtime_boundary, name)
                != getattr(self.before_runtime_boundary, name)
                for name in unchanged_counters
            ):
                raise CanonicalizationError(
                    "PASS measurement contains non-target admission activity"
                )
        elif self.measurement_error_code is None:
            raise CanonicalizationError(
                "non-PASS measurement requires a measurement_error_code"
            )
        if self.measurement_outcome not in {
            CapacityMeasurementOutcomeV49F.PASS,
            CapacityMeasurementOutcomeV49F.ERROR,
            CapacityMeasurementOutcomeV49F.CANCELLED,
        }:
            raise CanonicalizationError(
                "measurement_outcome must be PASS, ERROR, or CANCELLED"
            )
        identity = _semantic_identity_v49f(
            domain=A2M_SAMPLE_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if self.sample_id is not None and self.sample_id != identity:
            raise CanonicalizationError("sample_id differs from canonical sample")
        object.__setattr__(self, "sample_id", identity)

    @property
    def duration_nanoseconds(self) -> int:
        return (
            self.observer_end_offset_nanoseconds
            - self.observer_start_offset_nanoseconds
        )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in _record_keys(type(self)) - {"sample_id"}:
            value = getattr(self, name)
            if name in {
                "before_snapshot",
                "in_operation_snapshot",
                "after_snapshot",
            }:
                value = value.as_dict()
            elif name in {
                "initial_runtime_boundary",
                "before_runtime_boundary",
                "after_runtime_boundary",
            }:
                value = value.as_dict()
            elif name == "returned_ingress_progress":
                value = None if value is None else value.as_dict()
            elif name in {"operation_outcome", "measurement_outcome"}:
                value = value.value
            elif name in {
                "parser_event_ids",
                "automatic_output_source_parser_event_ids",
                "automatic_dispatch_completion_event_ids",
                "automatic_output_wire_chunk_counts",
            }:
                value = None if value is None else list(value)
            result[name] = value
        return result

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementSampleV49F,
            context="measurement sample",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementSampleV49F,
            context="measurement sample",
        )
        return _semantic_record_v49f(
            domain=A2M_SAMPLE_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="sample_id",
            identity=self.sample_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CapacityMeasurementSampleV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_SAMPLE_DOMAIN_V49F,
            context="measurement sample",
        )
        try:
            operation_outcome = CapacityMeasurementOutcomeV49F(
                item["operation_outcome"]
            )
            measurement_outcome = CapacityMeasurementOutcomeV49F(
                item["measurement_outcome"]
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError("outcome is unsupported") from exc
        for name in (
            "parser_event_ids",
            "automatic_output_source_parser_event_ids",
            "automatic_dispatch_completion_event_ids",
            "automatic_output_wire_chunk_counts",
        ):
            if item[name] is not None and type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array or null")
        returned_progress = item["returned_ingress_progress"]
        if returned_progress is not None and not isinstance(returned_progress, Mapping):
            raise CanonicalizationError(
                "returned_ingress_progress must be an object or null"
            )
        return cls(
            **{
                **item,
                "parser_event_ids": (
                    None
                    if item["parser_event_ids"] is None
                    else tuple(item["parser_event_ids"])
                ),
                "automatic_output_source_parser_event_ids": (
                    None
                    if item["automatic_output_source_parser_event_ids"] is None
                    else tuple(item["automatic_output_source_parser_event_ids"])
                ),
                "automatic_dispatch_completion_event_ids": (
                    None
                    if item["automatic_dispatch_completion_event_ids"] is None
                    else tuple(item["automatic_dispatch_completion_event_ids"])
                ),
                "automatic_output_wire_chunk_counts": (
                    None
                    if item["automatic_output_wire_chunk_counts"] is None
                    else tuple(item["automatic_output_wire_chunk_counts"])
                ),
                "operation_outcome": operation_outcome,
                "measurement_outcome": measurement_outcome,
                "initial_runtime_boundary": (
                    CapacityMeasurementRuntimeBoundaryEvidenceV49F.from_mapping(
                        item["initial_runtime_boundary"]
                    )
                ),
                "before_runtime_boundary": (
                    CapacityMeasurementRuntimeBoundaryEvidenceV49F.from_mapping(
                        item["before_runtime_boundary"]
                    )
                ),
                "returned_ingress_progress": (
                    None
                    if returned_progress is None
                    else CapacityMeasurementIngressProgressEvidenceV49F.from_mapping(
                        returned_progress
                    )
                ),
                "after_runtime_boundary": (
                    CapacityMeasurementRuntimeBoundaryEvidenceV49F.from_mapping(
                        item["after_runtime_boundary"]
                    )
                ),
                "before_snapshot": CapacityMeasurementLayerSnapshotV49F.from_mapping(
                    item["before_snapshot"]
                ),
                "in_operation_snapshot": CapacityMeasurementLayerSnapshotV49F.from_mapping(
                    item["in_operation_snapshot"]
                ),
                "after_snapshot": CapacityMeasurementLayerSnapshotV49F.from_mapping(
                    item["after_snapshot"]
                ),
            }
        )


_SAMPLE_IDENTITY_FIELDS = (
    "campaign_manifest_id",
    "manifest_authority_id",
    "transport_session_id",
    "driver_evidence_nonce_sha256",
    "kernel_socket_identity",
    "source_identity_sha256",
    "runtime_identity_sha256",
    "workload_corpus_sha256",
    "measurement_design_id",
)


def validate_capacity_measurement_samples_v49f(
    samples: Sequence[CapacityMeasurementSampleV49F],
    *,
    manifest: CapacityMeasurementManifestV49F | None = None,
) -> tuple[CapacityMeasurementSampleV49F, ...]:
    if manifest is not None:
        _revalidate_exact_dataclass_v49f(
            manifest,
            record_type=CapacityMeasurementManifestV49F,
            context="measurement manifest",
        )
    if (
        type(samples) not in {list, tuple}
        or not samples
        or len(samples) > A2M_MAXIMUM_TOTAL_TRIALS_V49F
    ):
        raise CanonicalizationError(
            "samples must contain a bounded set of exact sample records"
        )
    normalized = tuple(samples)
    if any(type(item) is not CapacityMeasurementSampleV49F for item in normalized):
        raise CanonicalizationError("samples must contain exact sample records")
    first = normalized[0]
    known_ids: set[str] = set()
    samples_by_id: dict[str, CapacityMeasurementSampleV49F] = {}
    raw_sequence_by_commit: dict[str, int] = {}
    raw_commit_by_sequence: dict[int, str] = {}
    last_raw_sequence: int | None = None
    admission_epoch: int | None = None
    last_admission_sequence: int | None = None
    seen_actor_event_ids: set[str] = set()
    for index, sample in enumerate(normalized, start=1):
        try:
            sample.as_dict()
        except (AttributeError, TypeError) as exc:
            raise CanonicalizationError(
                "sample differs from exact reconstructable evidence"
            ) from exc
        if sample.sample_sequence != index or sample.trial_index != index - 1:
            raise CanonicalizationError("sample schedule is not contiguous")
        if any(
            getattr(sample, name) != getattr(first, name)
            for name in _SAMPLE_IDENTITY_FIELDS
        ):
            raise CanonicalizationError(
                "sample stream crosses a manifest or transport session"
            )
        if index == 1:
            if sample.parent_sample_id is not None:
                raise CanonicalizationError("first sample cannot have a parent")
        elif sample.parent_sample_id != normalized[index - 2].sample_id:
            raise CanonicalizationError(
                "sample parent must identify the immediately preceding sample"
            )
        else:
            parent = samples_by_id[sample.parent_sample_id]
            if (
                parent.observer_end_offset_nanoseconds
                > sample.observer_start_offset_nanoseconds
                or parent.boottime_end_offset_nanoseconds
                > sample.boottime_start_offset_nanoseconds
                or parent.loop_time_end_offset_nanoseconds
                > sample.loop_time_start_offset_nanoseconds
            ):
                raise CanonicalizationError(
                    "sample starts before its parent completed in every clock domain"
                )
        if sample.raw_ingress_sequence is not None:
            raw_sequence = sample.raw_ingress_sequence
            raw_commit = sample.raw_ingress_commit_id
            assert raw_commit is not None
            if last_raw_sequence is not None and raw_sequence <= last_raw_sequence:
                raise CanonicalizationError(
                    "RAW ingress sequence did not move strictly forward"
                )
            if raw_commit in raw_sequence_by_commit:
                raise CanonicalizationError(
                    "RAW ingress commit is referenced by multiple samples"
                )
            if raw_sequence in raw_commit_by_sequence:
                raise CanonicalizationError(
                    "RAW ingress sequence is referenced by multiple samples"
                )
            raw_sequence_by_commit[raw_commit] = raw_sequence
            raw_commit_by_sequence[raw_sequence] = raw_commit
            last_raw_sequence = raw_sequence
        if sample.admission_sequence is not None:
            if admission_epoch is None:
                admission_epoch = sample.admission_epoch
            elif sample.admission_epoch != admission_epoch:
                raise CanonicalizationError(
                    "sample stream crosses a transport admission epoch"
                )
            if (
                last_admission_sequence is not None
                and sample.admission_sequence <= last_admission_sequence
            ):
                raise CanonicalizationError(
                    "transport admission sequence did not move forward"
                )
            last_admission_sequence = sample.admission_sequence
        sample_actor_event_ids = set(sample.parser_event_ids or ()) | set(
            sample.automatic_dispatch_completion_event_ids or ()
        )
        if seen_actor_event_ids & sample_actor_event_ids:
            raise CanonicalizationError(
                "actor event ID is referenced by multiple samples"
            )
        seen_actor_event_ids.update(sample_actor_event_ids)
        known_ids.add(sample.sample_id)
        samples_by_id[sample.sample_id] = sample
    if manifest is not None:
        expected_identity = {
            "campaign_manifest_id": manifest.campaign_manifest_id,
            "manifest_authority_id": manifest.manifest_authority.manifest_authority_id,
            "transport_session_id": manifest.transport_session_id,
            "driver_evidence_nonce_sha256": manifest.driver_evidence_nonce_sha256,
            "kernel_socket_identity": manifest.kernel_socket_identity,
            "source_identity_sha256": manifest.source_identity_sha256,
            "runtime_identity_sha256": manifest.runtime_identity_sha256,
            "workload_corpus_sha256": manifest.workload_corpus_sha256,
            "measurement_design_id": manifest.design.measurement_design_id,
        }
        for sample in normalized:
            if any(
                getattr(sample, name) != value
                for name, value in expected_identity.items()
            ):
                raise CanonicalizationError(
                    "sample differs from its exact manifest/session identity"
                )
            if (
                sample.admission_policy_id is not None
                and sample.admission_policy_id != manifest.transport_capacity_policy_id
            ):
                raise CanonicalizationError(
                    "sample admission policy differs from its manifest"
                )
        workload_map = {item.workload_id: item for item in manifest.workloads}
        for sample in normalized:
            workload = workload_map.get(sample.workload_id)
            if workload is None or workload.workload_sha256 != sample.workload_sha256:
                raise CanonicalizationError(
                    "sample workload is undeclared or has a foreign identity"
                )
            spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
                workload.workload_manifest_json
            )
            input_bytes = b"".join(spec.input_chunks)
            if (
                sample.stage != spec.stage
                or sample.input_chunk_count != len(spec.input_chunks)
                or sample.input_octet_count != len(input_bytes)
                or sample.input_sha256 != hashlib.sha256(input_bytes).hexdigest()
                or sample.expected_output_frame_count
                != len(spec.expected_output_frames)
                or sample.expected_output_frames_sha256
                != spec.expected_output_frames_sha256
            ):
                raise CanonicalizationError(
                    "sample declaration differs from its executable workload vector"
                )
            if (
                sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
                and sample.raw_ingress_batch_sha256 != spec.raw_ingress_batch_sha256
            ):
                raise CanonicalizationError(
                    "PASS sample RAW batch differs from its executable workload"
                )
            if sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS and (
                sample.output_frame_count != len(spec.expected_output_frames)
                or sample.observed_output_frames_sha256
                != spec.expected_output_frames_sha256
            ):
                raise CanonicalizationError(
                    "PASS sample logical output differs from its executable workload"
                )
        expected_schedule = [
            (workload.workload_id, True, repetition)
            for workload in manifest.workloads
            for repetition in range(manifest.design.warmup_repetitions)
        ]
        measured_schedule = [
            (workload.workload_id, False, repetition)
            for workload in manifest.workloads
            for repetition in range(manifest.design.measured_repetitions)
        ]
        measured_schedule.sort(
            key=lambda item: sha256_digest(
                {
                    "domain": "RiskYieldMMA2MSeededMeasuredTrialOrderV4_9F",
                    "is_warmup": item[1],
                    "random_seed": manifest.design.random_seed,
                    "repetition_index": item[2],
                    "workload_id": item[0],
                }
            )
        )
        expected_schedule.extend(measured_schedule)
        actual_schedule = [
            (sample.workload_id, sample.is_warmup, sample.repetition_index)
            for sample in normalized
        ]
        if actual_schedule != expected_schedule:
            raise CanonicalizationError(
                "sample trial order differs from the frozen deterministic schedule"
            )
        for workload_id in workload_map:
            for is_warmup, expected_count in (
                (True, manifest.design.warmup_repetitions),
                (False, manifest.design.measured_repetitions),
            ):
                selected = [
                    item
                    for item in normalized
                    if item.workload_id == workload_id and item.is_warmup is is_warmup
                ]
                if len(selected) != expected_count:
                    raise CanonicalizationError(
                        "sample schedule count differs from manifest design"
                    )
                if {item.repetition_index for item in selected} != set(
                    range(expected_count)
                ):
                    raise CanonicalizationError(
                        "sample repetition schedule differs from manifest design"
                    )
    return normalized


def encode_capacity_measurement_samples_jsonl_v49f(
    samples: Sequence[CapacityMeasurementSampleV49F],
    *,
    manifest: CapacityMeasurementManifestV49F | None = None,
) -> bytes:
    normalized = validate_capacity_measurement_samples_v49f(samples, manifest=manifest)
    if len(normalized) > A2M_MAXIMUM_TOTAL_TRIALS_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "sample stream exceeds its record-count bound"
        )
    lines: list[bytes] = []
    total_bytes = 0
    for item in normalized:
        line = canonical_json_bytes(item.as_dict()) + b"\n"
        if len(line) > A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F:
            raise CapacityMeasurementArtifactErrorV49F(
                "sample JSONL record exceeds its byte bound"
            )
        total_bytes += len(line)
        if total_bytes > A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F:
            raise CapacityMeasurementArtifactErrorV49F(
                "samples JSONL exceeds its artifact byte bound"
            )
        lines.append(line)
    return b"".join(lines)


def decode_capacity_measurement_samples_jsonl_v49f(
    payload: bytes,
    *,
    manifest: CapacityMeasurementManifestV49F | None = None,
) -> tuple[CapacityMeasurementSampleV49F, ...]:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F
        or not payload.endswith(b"\n")
        or b"\r" in payload
    ):
        raise CapacityMeasurementArtifactErrorV49F(
            "samples JSONL must be bounded non-empty LF-terminated bytes"
        )
    if payload.count(b"\n") > A2M_MAXIMUM_TOTAL_TRIALS_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "sample stream exceeds its record-count bound"
        )
    samples: list[CapacityMeasurementSampleV49F] = []
    offset = 0
    while offset < len(payload):
        newline = payload.find(b"\n", offset)
        if newline < 0:  # Defensive: LF termination was checked above.
            raise CapacityMeasurementArtifactErrorV49F(
                "samples JSONL record is unterminated"
            )
        line_size = newline - offset
        if line_size == 0:
            raise CapacityMeasurementArtifactErrorV49F(
                "samples JSONL cannot contain blank records"
            )
        if line_size + 1 > A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F:
            raise CapacityMeasurementArtifactErrorV49F(
                "sample JSONL record exceeds its byte bound"
            )
        if len(samples) >= A2M_MAXIMUM_TOTAL_TRIALS_V49F:
            raise CapacityMeasurementArtifactErrorV49F(
                "sample stream exceeds its record-count bound"
            )
        line = payload[offset:newline]
        parsed = strict_json_loads(line)
        if not isinstance(parsed, Mapping):
            raise CapacityMeasurementArtifactErrorV49F(
                "sample JSONL record must be an object"
            )
        sample = CapacityMeasurementSampleV49F.from_mapping(parsed)
        if canonical_json_bytes(sample.as_dict()) != line:
            raise CapacityMeasurementArtifactErrorV49F(
                "sample JSONL record is not canonical"
            )
        samples.append(sample)
        offset = newline + 1
    return validate_capacity_measurement_samples_v49f(samples, manifest=manifest)


def capacity_measurement_sample_stream_sha256_v49f(
    samples: Sequence[CapacityMeasurementSampleV49F],
    *,
    manifest: CapacityMeasurementManifestV49F | None = None,
) -> str:
    return hashlib.sha256(
        encode_capacity_measurement_samples_jsonl_v49f(samples, manifest=manifest)
    ).hexdigest()


_A2M_CORRECTNESS_BOOLEAN_FIELDS_V49F = (
    "no_loss",
    "no_duplication",
    "no_reordering",
    "control_output_causal",
    "projection_verified",
    "observations_complete",
    "cleanup_complete",
)
_A2M_UNFINALIZED_CORRECTNESS_ASSERTION_FIELDS_V49F = (
    "no_loss",
    "no_duplication",
    "no_reordering",
    "control_output_causal",
    "projection_verified",
    "cleanup_complete",
)


def _require_unfinalized_correctness_v49f(
    correctness: CapacityMeasurementCorrectnessV49F,
) -> None:
    """Keep V4.9F correctness provisional until evidence can be finalized."""

    if type(correctness) is not CapacityMeasurementCorrectnessV49F:
        raise CanonicalizationError("correctness record must be exact")
    try:
        for name in _A2M_CORRECTNESS_BOOLEAN_FIELDS_V49F:
            if type(getattr(correctness, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        failure_codes = correctness.failure_codes
    except AttributeError as exc:
        raise CanonicalizationError("correctness record is incomplete") from exc
    if type(failure_codes) is not tuple:
        raise CanonicalizationError("failure_codes must be an exact tuple")
    canonical_failures = canonical_reason_codes(failure_codes, field="failure_codes")
    if failure_codes != canonical_failures:
        raise CanonicalizationError("failure_codes must be canonical")
    if A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F not in failure_codes:
        raise CanonicalizationError(
            "correctness record must include "
            "CORRECTNESS_FINALIZER_NOT_IMPLEMENTED until an evidence-derived "
            "finalizer is implemented"
        )
    asserted = tuple(
        name
        for name in _A2M_UNFINALIZED_CORRECTNESS_ASSERTION_FIELDS_V49F
        if getattr(correctness, name)
    )
    if asserted:
        raise CanonicalizationError(
            "unfinalized correctness cannot assert verified checks: "
            + ", ".join(asserted)
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCorrectnessV49F:
    campaign_manifest_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    sample_stream_sha256: str
    sample_count: int
    first_sample_id: str
    last_sample_id: str
    raw_ingress_root_sha256: str
    actor_event_root_sha256: str
    projection_root_sha256: str
    no_loss: bool
    no_duplication: bool
    no_reordering: bool
    control_output_causal: bool
    projection_verified: bool
    observations_complete: bool
    cleanup_complete: bool
    failure_codes: tuple[str, ...]
    correctness_id: str | None = None

    _BOOLEAN_FIELDS: ClassVar[tuple[str, ...]] = _A2M_CORRECTNESS_BOOLEAN_FIELDS_V49F

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "sample_stream_sha256",
            "first_sample_id",
            "last_sample_id",
            "raw_ingress_root_sha256",
            "actor_event_root_sha256",
            "projection_root_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "sample_count",
            canonical_safe_int(
                self.sample_count,
                field="sample_count",
                minimum=1,
                maximum=A2M_MAXIMUM_TOTAL_TRIALS_V49F,
            ),
        )
        for name in self._BOOLEAN_FIELDS:
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        failures = canonical_reason_codes(self.failure_codes, field="failure_codes")
        object.__setattr__(self, "failure_codes", failures)
        _require_unfinalized_correctness_v49f(self)
        if bool(failures) == all(getattr(self, name) for name in self._BOOLEAN_FIELDS):
            raise CanonicalizationError(
                "failure_codes must be empty exactly when all correctness checks pass"
            )
        identity = _semantic_identity_v49f(
            domain=A2M_CORRECTNESS_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if self.correctness_id is not None and self.correctness_id != identity:
            raise CanonicalizationError(
                "correctness_id differs from canonical correctness record"
            )
        object.__setattr__(self, "correctness_id", identity)

    @property
    def passed(self) -> bool:
        _require_unfinalized_correctness_v49f(self)
        return not self.failure_codes and all(
            getattr(self, name) for name in self._BOOLEAN_FIELDS
        )

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"correctness_id"}
        }
        result["failure_codes"] = list(self.failure_codes)
        return result

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementCorrectnessV49F,
            context="measurement correctness",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementCorrectnessV49F,
            context="measurement correctness",
        )
        _require_unfinalized_correctness_v49f(self)
        return _semantic_record_v49f(
            domain=A2M_CORRECTNESS_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="correctness_id",
            identity=self.correctness_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCorrectnessV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_CORRECTNESS_DOMAIN_V49F,
            context="measurement correctness",
        )
        if type(item["failure_codes"]) is not list:
            raise CanonicalizationError("failure_codes must be a JSON array")
        return cls(**{**item, "failure_codes": tuple(item["failure_codes"])})


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementArtifactMemberV49F:
    artifact_name: str
    media_type: str
    byte_count: int
    record_count: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_name",
            canonical_identifier(self.artifact_name, field="artifact_name"),
        )
        if self.artifact_name not in _RAW_ARTIFACT_NAMES:
            raise CanonicalizationError(
                "integrity member is not a supported raw artifact"
            )
        expected_media = (
            "application/x-ndjson"
            if self.artifact_name == SAMPLES_ARTIFACT_NAME_V49F
            else "application/json"
        )
        if self.media_type != expected_media:
            raise CanonicalizationError(
                "integrity member media_type differs from artifact"
            )
        object.__setattr__(
            self,
            "byte_count",
            canonical_safe_int(
                self.byte_count,
                field="byte_count",
                minimum=1,
                maximum=_ARTIFACT_BYTE_LIMITS_V49F[self.artifact_name],
            ),
        )
        expected_records = (
            A2M_MAXIMUM_TOTAL_TRIALS_V49F
            if self.artifact_name == SAMPLES_ARTIFACT_NAME_V49F
            else 1
        )
        object.__setattr__(
            self,
            "record_count",
            canonical_safe_int(
                self.record_count,
                field="record_count",
                minimum=1,
                maximum=expected_records,
            ),
        )
        object.__setattr__(self, "sha256", canonical_hash(self.sha256, field="sha256"))

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementArtifactMemberV49F,
            context="measurement artifact member",
        )
        return {name: getattr(self, name) for name in _record_keys(type(self))}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementArtifactMemberV49F:
        return cls(
            **_mapping(payload, expected=_record_keys(cls), context="integrity member")
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIntegrityV49F:
    campaign_manifest_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    members: tuple[CapacityMeasurementArtifactMemberV49F, ...]
    integrity_id: str | None = None
    evidence_bundle_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        if type(self.members) is not tuple or any(
            type(item) is not CapacityMeasurementArtifactMemberV49F
            for item in self.members
        ):
            raise CanonicalizationError("integrity members must be an exact tuple")
        names = tuple(item.artifact_name for item in self.members)
        if names != tuple(sorted(_RAW_ARTIFACT_NAMES)):
            raise CanonicalizationError(
                "integrity members do not close exactly the three raw artifacts"
            )
        identity = _semantic_identity_v49f(
            domain=A2M_INTEGRITY_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        for name in ("integrity_id", "evidence_bundle_id"):
            supplied = getattr(self, name)
            if supplied is not None and supplied != identity:
                raise CanonicalizationError(
                    f"{name} differs from canonical integrity closure"
                )
            object.__setattr__(self, name, identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "campaign_manifest_id": self.campaign_manifest_id,
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "kernel_socket_identity": self.kernel_socket_identity,
            "members": [item.as_dict() for item in self.members],
            "transport_session_id": self.transport_session_id,
        }

    def identity_payload(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIntegrityV49F,
            context="measurement integrity",
        )
        return self._identity_payload_unchecked()

    def as_dict(self) -> dict[str, Any]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementIntegrityV49F,
            context="measurement integrity",
        )
        return {
            **_semantic_record_v49f(
                domain=A2M_INTEGRITY_DOMAIN_V49F,
                payload=self._identity_payload_unchecked(),
                identity_field="integrity_id",
                identity=self.integrity_id,
            ),
            "evidence_bundle_id": self.evidence_bundle_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIntegrityV49F:
        item = _decode_semantic_record_v49f(
            payload,
            record_type=cls,
            domain=A2M_INTEGRITY_DOMAIN_V49F,
            context="measurement integrity",
        )
        members = item["members"]
        if type(members) is not list:
            raise CanonicalizationError("integrity members must be a JSON array")
        return cls(
            **{
                **item,
                "members": tuple(
                    CapacityMeasurementArtifactMemberV49F.from_mapping(value)
                    for value in members
                ),
            }
        )


class _MeasurementRecord(Protocol):
    def as_dict(self) -> dict[str, Any]: ...


_RecordT = TypeVar("_RecordT", bound=_MeasurementRecord)
_SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F = (
    CapacityMeasurementEnvironmentV49F,
    CapacityMeasurementDesignV49F,
    CapacityMeasurementWorkloadV49F,
    CapacityMeasurementManifestV49F,
    CapacityMeasurementAdapterSpanV49F,
    CapacityMeasurementLayerSnapshotV49F,
    CapacityMeasurementLogicalOutputFrameV49F,
    CapacityMeasurementRuntimeBoundaryEvidenceV49F,
    CapacityMeasurementIngressProgressEvidenceV49F,
    CapacityMeasurementSampleV49F,
    CapacityMeasurementCorrectnessV49F,
    CapacityMeasurementArtifactMemberV49F,
    CapacityMeasurementIntegrityV49F,
)


def _measurement_json_record_limit_v49f(record_type: type[Any]) -> int:
    if record_type is CapacityMeasurementManifestV49F:
        return A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F
    if record_type is CapacityMeasurementSampleV49F:
        return A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F
    if record_type is CapacityMeasurementCorrectnessV49F:
        return A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F
    if record_type is CapacityMeasurementIntegrityV49F:
        return A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F
    return A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F


def encode_capacity_measurement_json_v49f(record: _MeasurementRecord) -> bytes:
    if type(record) not in _SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F:
        raise CanonicalizationError("measurement JSON record is unsupported")
    encoded = canonical_json_bytes(record.as_dict()) + b"\n"
    if len(encoded) > _measurement_json_record_limit_v49f(type(record)):
        raise CapacityMeasurementArtifactErrorV49F(
            "measurement JSON exceeds its record-type byte bound"
        )
    return encoded


def decode_capacity_measurement_json_v49f(
    payload: bytes,
    *,
    record_type: type[_RecordT],
) -> _RecordT:
    if record_type not in _SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "measurement JSON record type is unsupported"
        )
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _measurement_json_record_limit_v49f(record_type)
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
    ):
        raise CapacityMeasurementArtifactErrorV49F(
            "measurement JSON must be one bounded LF-terminated record"
        )
    parsed = strict_json_loads(payload[:-1])
    if not isinstance(parsed, Mapping):
        raise CapacityMeasurementArtifactErrorV49F(
            "measurement JSON record type is unsupported"
        )
    record = record_type.from_mapping(parsed)  # type: ignore[attr-defined]
    if encode_capacity_measurement_json_v49f(record) != payload:
        raise CapacityMeasurementArtifactErrorV49F(
            "measurement JSON does not replay canonically"
        )
    return record


def _raw_member_bytes(
    manifest: CapacityMeasurementManifestV49F,
    samples: Sequence[CapacityMeasurementSampleV49F],
    correctness: CapacityMeasurementCorrectnessV49F,
) -> dict[str, bytes]:
    return {
        MANIFEST_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f(manifest),
        SAMPLES_ARTIFACT_NAME_V49F: encode_capacity_measurement_samples_jsonl_v49f(
            samples, manifest=manifest
        ),
        CORRECTNESS_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f(
            correctness
        ),
    }


def _integrity_for_raw(
    manifest: CapacityMeasurementManifestV49F,
    raw: Mapping[str, bytes],
    *,
    sample_count: int,
) -> CapacityMeasurementIntegrityV49F:
    members = tuple(
        CapacityMeasurementArtifactMemberV49F(
            artifact_name=name,
            media_type="application/x-ndjson"
            if name == SAMPLES_ARTIFACT_NAME_V49F
            else "application/json",
            byte_count=len(raw[name]),
            record_count=sample_count if name == SAMPLES_ARTIFACT_NAME_V49F else 1,
            sha256=hashlib.sha256(raw[name]).hexdigest(),
        )
        for name in sorted(_RAW_ARTIFACT_NAMES)
    )
    return CapacityMeasurementIntegrityV49F(
        campaign_manifest_id=manifest.campaign_manifest_id,
        transport_session_id=manifest.transport_session_id,
        driver_evidence_nonce_sha256=manifest.driver_evidence_nonce_sha256,
        kernel_socket_identity=manifest.kernel_socket_identity,
        members=members,
    )


def _validate_correctness_links(
    manifest: CapacityMeasurementManifestV49F,
    samples: tuple[CapacityMeasurementSampleV49F, ...],
    correctness: CapacityMeasurementCorrectnessV49F,
) -> None:
    _require_unfinalized_correctness_v49f(correctness)
    expected = (
        manifest.campaign_manifest_id,
        manifest.transport_session_id,
        manifest.driver_evidence_nonce_sha256,
        manifest.kernel_socket_identity,
    )
    actual = (
        correctness.campaign_manifest_id,
        correctness.transport_session_id,
        correctness.driver_evidence_nonce_sha256,
        correctness.kernel_socket_identity,
    )
    if actual != expected:
        raise CanonicalizationError(
            "correctness record differs from exact manifest/session"
        )
    if (
        correctness.sample_count != len(samples)
        or correctness.sample_stream_sha256
        != capacity_measurement_sample_stream_sha256_v49f(samples, manifest=manifest)
        or correctness.first_sample_id != samples[0].sample_id
        or correctness.last_sample_id != samples[-1].sample_id
    ):
        raise CanonicalizationError(
            "correctness record differs from exact sample stream"
        )
    observations_complete = all(
        sample.measurement_outcome is CapacityMeasurementOutcomeV49F.PASS
        and sample.admission_attribution == "EXACT_RETURNED_GRANT"
        and not sample.before_snapshot.unavailable_fields
        and not sample.in_operation_snapshot.unavailable_fields
        and not sample.after_snapshot.unavailable_fields
        for sample in samples
    )
    if correctness.observations_complete is not observations_complete:
        raise CanonicalizationError(
            "correctness observations_complete differs from exact sample coverage"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementArtifactBundleV49F:
    manifest: CapacityMeasurementManifestV49F
    samples: tuple[CapacityMeasurementSampleV49F, ...]
    correctness: CapacityMeasurementCorrectnessV49F
    integrity: CapacityMeasurementIntegrityV49F

    def __post_init__(self) -> None:
        if type(self.manifest) is not CapacityMeasurementManifestV49F:
            raise CanonicalizationError("bundle manifest must be exact")
        normalized = validate_capacity_measurement_samples_v49f(
            self.samples, manifest=self.manifest
        )
        object.__setattr__(self, "samples", normalized)
        if type(self.correctness) is not CapacityMeasurementCorrectnessV49F:
            raise CanonicalizationError("bundle correctness must be exact")
        _validate_correctness_links(self.manifest, normalized, self.correctness)
        if type(self.integrity) is not CapacityMeasurementIntegrityV49F:
            raise CanonicalizationError("bundle integrity must be exact")
        raw = _raw_member_bytes(self.manifest, normalized, self.correctness)
        expected_integrity = _integrity_for_raw(
            self.manifest, raw, sample_count=len(normalized)
        )
        if self.integrity != expected_integrity:
            raise CanonicalizationError(
                "integrity metadata differs from exact raw artifact bytes"
            )

    @property
    def evidence_bundle_id(self) -> str:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementArtifactBundleV49F,
            context="measurement artifact bundle",
        )
        return self.integrity.evidence_bundle_id

    @classmethod
    def build(
        cls,
        *,
        manifest: CapacityMeasurementManifestV49F,
        samples: Sequence[CapacityMeasurementSampleV49F],
        correctness: CapacityMeasurementCorrectnessV49F,
    ) -> CapacityMeasurementArtifactBundleV49F:
        normalized = validate_capacity_measurement_samples_v49f(
            samples, manifest=manifest
        )
        _validate_correctness_links(manifest, normalized, correctness)
        raw = _raw_member_bytes(manifest, normalized, correctness)
        return cls(
            manifest=manifest,
            samples=normalized,
            correctness=correctness,
            integrity=_integrity_for_raw(manifest, raw, sample_count=len(normalized)),
        )

    def artifact_bytes(self) -> dict[str, bytes]:
        _revalidate_exact_dataclass_v49f(
            self,
            record_type=CapacityMeasurementArtifactBundleV49F,
            context="measurement artifact bundle",
        )
        raw = _raw_member_bytes(self.manifest, self.samples, self.correctness)
        return {
            **raw,
            INTEGRITY_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f(
                self.integrity
            ),
        }

    @classmethod
    def from_artifact_bytes(
        cls,
        artifacts: Mapping[str, bytes],
    ) -> CapacityMeasurementArtifactBundleV49F:
        if (
            not isinstance(artifacts, Mapping)
            or set(artifacts) != _BUNDLE_ARTIFACT_NAMES
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "artifact closure must contain exactly manifest, samples, correctness, and integrity"
            )
        if any(
            type(name) is not str or type(value) is not bytes
            for name, value in artifacts.items()
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "artifact names and bytes must be exact"
            )
        if any(
            not value or len(value) > _ARTIFACT_BYTE_LIMITS_V49F[name]
            for name, value in artifacts.items()
        ) or sum(len(value) for value in artifacts.values()) > (
            A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "artifact closure exceeds its frozen member or total byte bounds"
            )
        integrity = decode_capacity_measurement_json_v49f(
            artifacts[INTEGRITY_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementIntegrityV49F,
        )
        members = {item.artifact_name: item for item in integrity.members}
        for name in _RAW_ARTIFACT_NAMES:
            raw = artifacts[name]
            member = members[name]
            if (
                member.byte_count != len(raw)
                or member.sha256 != hashlib.sha256(raw).hexdigest()
            ):
                raise CapacityMeasurementArtifactErrorV49F(
                    "raw artifact bytes differ from integrity metadata"
                )
        manifest = decode_capacity_measurement_json_v49f(
            artifacts[MANIFEST_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementManifestV49F,
        )
        samples = decode_capacity_measurement_samples_jsonl_v49f(
            artifacts[SAMPLES_ARTIFACT_NAME_V49F], manifest=manifest
        )
        correctness = decode_capacity_measurement_json_v49f(
            artifacts[CORRECTNESS_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementCorrectnessV49F,
        )
        if members[SAMPLES_ARTIFACT_NAME_V49F].record_count != len(samples):
            raise CapacityMeasurementArtifactErrorV49F(
                "samples record_count differs from JSONL"
            )
        if any(
            members[name].record_count != 1
            for name in (MANIFEST_ARTIFACT_NAME_V49F, CORRECTNESS_ARTIFACT_NAME_V49F)
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "singleton artifact record_count differs"
            )
        return cls(
            manifest=manifest,
            samples=samples,
            correctness=correctness,
            integrity=integrity,
        )


# Guard against accidentally widening relative offsets into unsafe JSON integers.
assert MAX_IJSON_INTEGER == (1 << 53) - 1


# Raw V7 artifact contracts.  V6 remains unchanged above and is used only as
# the explicitly typed, self-contained predecessor of a V7 manifest.
A2M_MEASUREMENT_SCHEMA_VERSION_V49F_V7 = A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7
A2M_MANIFEST_DOMAIN_V49F_V7 = "RiskYieldMMA2MManifestV4_9F_RawV7"
A2M_SAMPLE_DOMAIN_V49F_V7 = "RiskYieldMMA2MLifecycleSampleV4_9F_RawV7"
A2M_OBSERVATION_DOMAIN_V49F_V7 = "RiskYieldMMA2MObservationV4_9F_RawV7"
A2M_RECOVERED_PREFIX_DOMAIN_V49F_V7 = (
    "RiskYieldMMA2MRecoveredOperationPrefixV4_9F_RawV7"
)
A2M_CLOSED_PREFIX_DOMAIN_V49F_V7 = "RiskYieldMMA2MClosedOperationPrefixV4_9F_RawV7"
A2M_CORRECTNESS_DOMAIN_V49F_V7 = "RiskYieldMMA2MCorrectnessV4_9F_RawV7"
A2M_INTEGRITY_DOMAIN_V49F_V7 = "RiskYieldMMA2MIntegrityV4_9F_RawV7"
A2M_PROJECTION_RECEIPT_DOMAIN_V49F_V7 = (
    "RiskYieldMMA2MProjectionReceiptEvidenceV4_9F_RawV7"
)
A2M_COMMITTED_LIFECYCLE_DOMAIN_V49F_V7 = (
    "RiskYieldMMA2MCommittedLifecycleRecordV4_9F_RawV7"
)
A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7 = (
    A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F
)
A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7 = (
    "POST_RUN_SUFFIX_PROVENANCE_UNATTESTED"
)
A2M_PROJECTION_RECEIPT_HASH_DOMAIN_V49F_V7 = "RiskYieldMMPhysicalProjectionReceiptV4"
A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7 = (
    "CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V7"
)
A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7 = (
    "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7"
)
A2M_RAW_INGRESS_RECORD_KIND_V49F_V7 = "RAW_INGRESS_COMMIT_V4"
A2M_ACTOR_EVENT_RECORD_KIND_V49F_V7 = "TRANSPORT_ACTOR_EVENT_V49C"
A2M_MAXIMUM_OPERATION_ATTEMPT_BYTES_V49F_V7 = 256 * 1024
A2M_MAXIMUM_OPERATION_TERMINAL_BYTES_V49F_V7 = 256 * 1024


class CapacityMeasurementScheduleCoverageV49FV7(str, Enum):
    COMPLETE = "COMPLETE"
    RUN_ENDING_PREFIX = "RUN_ENDING_PREFIX"


def _semantic_identity_v49f_v7(*, domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": A2M_MEASUREMENT_SCHEMA_VERSION_V49F_V7,
        }
    )


def _semantic_record_v49f_v7(
    *,
    domain: str,
    payload: Mapping[str, Any],
    identity_field: str,
    identity: str,
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": A2M_MEASUREMENT_SCHEMA_VERSION_V49F_V7,
        "record_domain": domain,
        **dict(payload),
        identity_field: identity,
    }


def _decode_semantic_record_v49f_v7(
    payload: Mapping[str, Any],
    *,
    record_type: type[Any],
    domain: str,
    context: str,
) -> dict[str, Any]:
    item = _mapping(
        payload,
        expected=_record_keys(record_type) | set(_SEMANTIC_RECORD_KEYS_V49F),
        context=context,
    )
    if item["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError(f"{context} canonicalization version differs")
    if item["measurement_schema_version"] != A2M_MEASUREMENT_SCHEMA_VERSION_V49F_V7:
        raise CanonicalizationError(f"{context} Raw V7 schema version differs")
    if item["record_domain"] != domain:
        raise CanonicalizationError(f"{context} Raw V7 record domain differs")
    return {name: item[name] for name in _record_keys(record_type)}


def _source_role_modules_v49f_v7(
    snapshot: SourceObservationSnapshotV49F, *, role_prefix: str
) -> tuple[str, ...]:
    if type(snapshot) is not SourceObservationSnapshotV49F:
        raise CanonicalizationError("Raw V7 source observation must be exact")
    allowed_prefixes = ("CRITICAL_MODULE:", "LOADED_MODULE:")
    if role_prefix not in allowed_prefixes:
        raise CanonicalizationError("Raw V7 source role prefix is unsupported")
    if any(
        not role.startswith(allowed_prefixes)
        for member in snapshot.members
        for role in member.roles
    ):
        raise CanonicalizationError("Raw V7 source observation has an unknown role")
    modules = tuple(
        sorted(
            role.removeprefix(role_prefix)
            for member in snapshot.members
            for role in member.roles
            if role.startswith(role_prefix)
        )
    )
    if len(modules) != len(set(modules)):
        raise CanonicalizationError(
            "Raw V7 source observation duplicates a module role"
        )
    return modules


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementManifestV49FV7:
    predecessor_manifest_v6: CapacityMeasurementManifestV49F
    source_inventory: CapacityMeasurementSourceInventoryV49FV7
    lifecycle_contract: CapacityMeasurementLifecycleContractV49FV7
    projection_authority: CapacityMeasurementProjectionAuthorityV49FV7
    actor_baseline: CapacityMeasurementActorBaselineV49FV7
    manifest_authority_v7: CapacityMeasurementManifestAuthorityV49FV7
    campaign_manifest_id: str | None = None

    def __post_init__(self) -> None:
        for name, record_type in (
            ("predecessor_manifest_v6", CapacityMeasurementManifestV49F),
            ("source_inventory", CapacityMeasurementSourceInventoryV49FV7),
            ("lifecycle_contract", CapacityMeasurementLifecycleContractV49FV7),
            (
                "projection_authority",
                CapacityMeasurementProjectionAuthorityV49FV7,
            ),
            ("actor_baseline", CapacityMeasurementActorBaselineV49FV7),
            (
                "manifest_authority_v7",
                CapacityMeasurementManifestAuthorityV49FV7,
            ),
        ):
            record = getattr(self, name)
            if type(record) is not record_type:
                raise CanonicalizationError(f"Raw V7 {name} must be exact")
            replay = record_type.from_mapping(
                strict_json_loads(canonical_json_bytes(record.as_dict()))
            )
            if replay != record:
                raise CanonicalizationError(f"Raw V7 {name} differs from exact replay")
        predecessor = self.predecessor_manifest_v6
        source = predecessor.source_observation
        if (
            _source_role_modules_v49f_v7(source, role_prefix="CRITICAL_MODULE:")
            != RAW_V7_CRITICAL_SOURCE_MODULES_V49F
            or _source_role_modules_v49f_v7(source, role_prefix="LOADED_MODULE:")
            != RAW_V7_CRITICAL_SOURCE_MODULES_V49F
            or self.source_inventory.source_inventory_id
            != RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F
            or not source.deployment_source_tree_matches
            or source.source_tree_sha256 != source.deployment_source_tree_sha256
            or source.source_tree_sha256
            != predecessor.runtime_observation.declared_source_tree_sha256
        ):
            raise CanonicalizationError(
                "Raw V7 predecessor is not the current exact 41-module source closure"
            )
        projection = self.projection_authority
        actor = self.actor_baseline
        runtime = predecessor.runtime_observation
        if (
            actor.projection_receipt_sequence,
            actor.projection_receipt_hash,
        ) != (
            projection.baseline_receipt_sequence,
            projection.baseline_receipt_hash,
        ) or (
            actor.transport_session_id,
            actor.driver_evidence_nonce_sha256,
            actor.kernel_socket_identity,
            actor.transport_capacity_policy_id,
            actor.deployment_bundle_id,
            actor.monotonic_clock_domain_id,
            actor.driver_policy_id,
        ) != (
            predecessor.transport_session_id,
            predecessor.driver_evidence_nonce_sha256,
            predecessor.kernel_socket_identity,
            predecessor.transport_capacity_policy_id,
            runtime.deployment_bundle_id,
            runtime.monotonic_clock_domain_id,
            runtime.tls_websocket_driver_policy_id,
        ):
            raise CanonicalizationError(
                "Raw V7 actor/projection baseline leaves predecessor authority"
            )
        authority = self.manifest_authority_v7
        base = predecessor.manifest_authority
        expected_authority = (
            base.manifest_authority_id,
            predecessor.campaign_manifest_id,
            base.manifest_authority_id,
            self.source_inventory.source_inventory_id,
            self.source_inventory.source_inventory_record_id,
            source.source_observation_id,
            source.source_tree_sha256,
            source.deployment_source_tree_sha256,
            self.lifecycle_contract.lifecycle_schema_id,
            self.lifecycle_contract.lifecycle_contract_id,
            projection.projection_authority_id,
            projection.projection_ledger_id,
            projection.projection_schema_version,
            projection.projection_validation_version,
            projection.projection_schema_fingerprint,
            actor.actor_baseline_id,
            base.collector_attestation_key_id,
            runtime.deployment_bundle_id,
            runtime.deployment_trust_root_id,
            runtime.collector_release_manifest_id,
            runtime.runtime_environment_manifest_id,
            predecessor.transport_session_id,
            predecessor.driver_evidence_nonce_sha256,
            predecessor.kernel_socket_identity,
            predecessor.transport_capacity_policy_id,
            predecessor.started_at_utc,
            predecessor.monotonic_origin_nanoseconds,
            predecessor.boottime_origin_nanoseconds,
            predecessor.loop_time_origin_nanoseconds,
            self.lifecycle_contract.operation_lifecycle_profile,
            self.lifecycle_contract.failed_prefix_profile,
            self.lifecycle_contract.cancellation_profile,
            self.lifecycle_contract.orphan_recovery_profile,
            False,
            base.collector_attestation_public_key_hex,
        )
        actual_authority = (
            authority.base_observed_authority_id,
            authority.predecessor_manifest_id,
            authority.predecessor_manifest_authority_id,
            authority.v7_source_inventory_id,
            authority.source_inventory_record_id,
            authority.v7_source_observation_id,
            authority.v7_source_tree_sha256,
            authority.v7_release_source_tree_sha256,
            authority.lifecycle_schema_id,
            authority.lifecycle_contract_id,
            authority.projection_authority_id,
            authority.projection_ledger_id,
            authority.projection_schema_version,
            authority.projection_validation_version,
            authority.projection_schema_fingerprint,
            authority.actor_baseline_id,
            authority.collector_attestation_key_id,
            authority.deployment_bundle_id,
            authority.deployment_trust_root_id,
            authority.collector_release_manifest_id,
            authority.runtime_environment_manifest_id,
            authority.transport_session_id,
            authority.driver_evidence_nonce_sha256,
            authority.kernel_socket_identity,
            authority.transport_capacity_policy_id,
            authority.started_at_utc,
            authority.monotonic_origin_nanoseconds,
            authority.boottime_origin_nanoseconds,
            authority.loop_time_origin_nanoseconds,
            authority.operation_lifecycle_profile,
            authority.failed_prefix_profile,
            authority.cancellation_profile,
            authority.orphan_recovery_profile,
            authority.promotion_eligible,
            authority.collector_attestation_public_key_hex,
        )
        if actual_authority != expected_authority:
            raise CanonicalizationError(
                "Raw V7 signed authority differs from exact predecessor and baselines"
            )
        identity = _semantic_identity_v49f_v7(
            domain=A2M_MANIFEST_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.campaign_manifest_id is not None
            and canonical_hash(self.campaign_manifest_id, field="campaign_manifest_id")
            != identity
        ):
            raise CanonicalizationError(
                "Raw V7 campaign_manifest_id differs from canonical manifest"
            )
        object.__setattr__(self, "campaign_manifest_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "actor_baseline": self.actor_baseline.as_dict(),
            "lifecycle_contract": self.lifecycle_contract.as_dict(),
            "manifest_authority_v7": self.manifest_authority_v7.as_dict(),
            "predecessor_manifest_v6": self.predecessor_manifest_v6.as_dict(),
            "projection_authority": self.projection_authority.as_dict(),
            "source_inventory": self.source_inventory.as_dict(),
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 manifest was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_MANIFEST_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="campaign_manifest_id",
            identity=self.campaign_manifest_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementManifestV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_MANIFEST_DOMAIN_V49F_V7,
            context="Raw V7 manifest",
        )
        predecessor_payload = item["predecessor_manifest_v6"]
        if isinstance(predecessor_payload, Mapping):
            workloads = predecessor_payload.get("workloads")
            if isinstance(workloads, Sequence) and not isinstance(
                workloads, (str, bytes, bytearray)
            ):
                for workload in workloads:
                    if not isinstance(workload, Mapping):
                        continue
                    embedded = workload.get("workload_manifest_json")
                    if isinstance(embedded, str):
                        validate_capacity_measurement_json_structure_before_parse_v49f_v7(
                            embedded.encode("utf-8", errors="strict")
                        )
        return cls(
            predecessor_manifest_v6=CapacityMeasurementManifestV49F.from_mapping(
                predecessor_payload
            ),
            source_inventory=CapacityMeasurementSourceInventoryV49FV7.from_mapping(
                item["source_inventory"]
            ),
            lifecycle_contract=CapacityMeasurementLifecycleContractV49FV7.from_mapping(
                item["lifecycle_contract"]
            ),
            projection_authority=(
                CapacityMeasurementProjectionAuthorityV49FV7.from_mapping(
                    item["projection_authority"]
                )
            ),
            actor_baseline=CapacityMeasurementActorBaselineV49FV7.from_mapping(
                item["actor_baseline"]
            ),
            manifest_authority_v7=(
                CapacityMeasurementManifestAuthorityV49FV7.from_mapping(
                    item["manifest_authority_v7"]
                )
            ),
            campaign_manifest_id=item["campaign_manifest_id"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCommittedLifecycleRecordV49FV7:
    record: (
        CapacityMeasurementOperationAttemptV49F
        | CapacityMeasurementOperationTerminalV49F
    )
    projection_receipt: CapacityMeasurementProjectionReceiptEvidenceV49F
    committed_record_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.record) is CapacityMeasurementOperationAttemptV49F:
            record_kind = A2M_OPERATION_ATTEMPT_RECORD_KIND_V49F_V7
            identity = self.record.attempt_id
            maximum = A2M_MAXIMUM_OPERATION_ATTEMPT_BYTES_V49F_V7
        elif type(self.record) is CapacityMeasurementOperationTerminalV49F:
            record_kind = A2M_OPERATION_TERMINAL_RECORD_KIND_V49F_V7
            identity = self.record.terminal_id
            maximum = A2M_MAXIMUM_OPERATION_TERMINAL_BYTES_V49F_V7
        else:
            raise CanonicalizationError(
                "committed lifecycle record type is unsupported"
            )
        assert identity is not None
        receipt = self.projection_receipt
        if type(receipt) is not CapacityMeasurementProjectionReceiptEvidenceV49F:
            raise CanonicalizationError("committed lifecycle receipt must be exact")
        canonical_blob = canonical_json_bytes(self.record.as_dict())
        if len(canonical_blob) > maximum:
            raise CanonicalizationError("committed lifecycle record exceeds byte bound")
        if (
            receipt.record_kind != record_kind
            or receipt.identity_id != identity
            or receipt.content_hash != hashlib.sha256(canonical_blob).hexdigest()
        ):
            raise CanonicalizationError(
                "committed lifecycle receipt differs from canonical record"
            )
        committed_id = _semantic_identity_v49f_v7(
            domain=A2M_COMMITTED_LIFECYCLE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.committed_record_id is not None
            and canonical_hash(self.committed_record_id, field="committed_record_id")
            != committed_id
        ):
            raise CanonicalizationError(
                "committed_record_id differs from record and receipt"
            )
        object.__setattr__(self, "committed_record_id", committed_id)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "projection_receipt": self.projection_receipt.as_dict(),
            "record": self.record.as_dict(),
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            record=self.record,
            projection_receipt=self.projection_receipt,
            committed_record_id=self.committed_record_id,
        )
        if replay != self:
            raise CanonicalizationError("committed lifecycle record was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_COMMITTED_LIFECYCLE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="committed_record_id",
            identity=self.committed_record_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCommittedLifecycleRecordV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_COMMITTED_LIFECYCLE_DOMAIN_V49F_V7,
            context="Raw V7 committed lifecycle record",
        )
        record_payload = item["record"]
        if not isinstance(record_payload, Mapping):
            raise CanonicalizationError("committed lifecycle record must be a mapping")
        domain = record_payload.get("record_domain")
        if domain == "RiskYieldMMA2MOperationAttemptV4_9F_RawV7":
            record = CapacityMeasurementOperationAttemptV49F.from_mapping(
                record_payload
            )
        elif domain == "RiskYieldMMA2MOperationTerminalV4_9F_RawV7":
            record = CapacityMeasurementOperationTerminalV49F.from_mapping(
                record_payload
            )
        else:
            raise CanonicalizationError("committed lifecycle domain is unsupported")
        return cls(
            record=record,
            projection_receipt=CapacityMeasurementProjectionReceiptEvidenceV49F.from_mapping(
                item["projection_receipt"]
            ),
            committed_record_id=item["committed_record_id"],
        )


def _optional_observation_reason_v49f_v7(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return canonical_identifier(value, field=field, maximum=128)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementObservationV49FV7:
    initial_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F | None
    initial_runtime_boundary_unavailable_reason: str | None
    before_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F | None
    before_runtime_boundary_unavailable_reason: str | None
    after_runtime_boundary: CapacityMeasurementRuntimeBoundaryEvidenceV49F | None
    after_runtime_boundary_unavailable_reason: str | None
    before_snapshot: CapacityMeasurementLayerSnapshotV49F | None
    before_snapshot_unavailable_reason: str | None
    in_operation_snapshot: CapacityMeasurementLayerSnapshotV49F | None
    in_operation_snapshot_unavailable_reason: str | None
    after_snapshot: CapacityMeasurementLayerSnapshotV49F | None
    after_snapshot_unavailable_reason: str | None
    returned_ingress_progress: CapacityMeasurementIngressProgressEvidenceV49F | None
    returned_ingress_progress_unavailable_reason: str | None
    observation_id: str | None = None

    _COMPONENTS: ClassVar[tuple[tuple[str, type[Any]], ...]] = (
        ("initial_runtime_boundary", CapacityMeasurementRuntimeBoundaryEvidenceV49F),
        ("before_runtime_boundary", CapacityMeasurementRuntimeBoundaryEvidenceV49F),
        ("after_runtime_boundary", CapacityMeasurementRuntimeBoundaryEvidenceV49F),
        ("before_snapshot", CapacityMeasurementLayerSnapshotV49F),
        ("in_operation_snapshot", CapacityMeasurementLayerSnapshotV49F),
        ("after_snapshot", CapacityMeasurementLayerSnapshotV49F),
        ("returned_ingress_progress", CapacityMeasurementIngressProgressEvidenceV49F),
    )

    def __post_init__(self) -> None:
        for name, record_type in self._COMPONENTS:
            value = getattr(self, name)
            reason_name = f"{name}_unavailable_reason"
            reason = _optional_observation_reason_v49f_v7(
                getattr(self, reason_name), field=reason_name
            )
            object.__setattr__(self, reason_name, reason)
            if (value is None) != (reason is not None):
                raise CanonicalizationError(
                    f"{name} and its unavailable reason must be exactly complementary"
                )
            if value is not None:
                if type(value) is not record_type:
                    raise CanonicalizationError(f"{name} must be exact")
                replay = record_type.from_mapping(
                    strict_json_loads(canonical_json_bytes(value.as_dict()))
                )
                if replay != value:
                    raise CanonicalizationError(f"{name} differs from exact replay")
        expected_roles = (
            ("initial_runtime_boundary", "INITIAL"),
            ("before_runtime_boundary", "BEFORE_OPERATION"),
            ("after_runtime_boundary", "AFTER_OPERATION"),
        )
        for name, expected_role in expected_roles:
            boundary = getattr(self, name)
            if boundary is not None and boundary.boundary_role != expected_role:
                raise CanonicalizationError(f"{name} has the wrong boundary role")
        identity = _semantic_identity_v49f_v7(
            domain=A2M_OBSERVATION_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.observation_id is not None
            and canonical_hash(self.observation_id, field="observation_id") != identity
        ):
            raise CanonicalizationError("observation_id differs from exact components")
        object.__setattr__(self, "observation_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, _ in self._COMPONENTS:
            value = getattr(self, name)
            result[name] = None if value is None else value.as_dict()
            result[f"{name}_unavailable_reason"] = getattr(
                self, f"{name}_unavailable_reason"
            )
        return result

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 observation was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_OBSERVATION_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="observation_id",
            identity=self.observation_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementObservationV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_OBSERVATION_DOMAIN_V49F_V7,
            context="Raw V7 observation",
        )
        parsers: dict[str, type[Any]] = dict(cls._COMPONENTS)
        for name, record_type in parsers.items():
            value = item[name]
            if value is not None:
                if not isinstance(value, Mapping):
                    raise CanonicalizationError(f"{name} must be a mapping or null")
                item[name] = record_type.from_mapping(value)
        return cls(**item)


def _verify_projection_record_span_v49f_v7(
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> None:
    """Replay every span member through the authoritative projection registry."""

    from .physical_projection_v4 import (
        PhysicalRecordKindV4,
        _parse_record,
        _record_identity,
    )

    for evidence in prefix.projection_records:
        try:
            kind = PhysicalRecordKindV4(evidence.record_kind)
            record = _parse_record(kind, evidence.canonical_record_bytes)
            identity = _record_identity(record)
        except (CanonicalizationError, ValueError) as exc:
            raise CanonicalizationError(
                "Raw V7 projection span contains an unsupported canonical record"
            ) from exc
        if (
            canonical_json_bytes(record.as_dict()) != evidence.canonical_record_bytes
            or identity != evidence.identity_id
            or hashlib.sha256(evidence.canonical_record_bytes).hexdigest()
            != evidence.content_hash
        ):
            raise CanonicalizationError(
                "Raw V7 projection span record fails semantic registry replay"
            )


def derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7(
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> CapacityMeasurementIngressProgressEvidenceV49F:
    """Reconstruct returned ingress progress solely from one durable prefix."""

    from .physical_transport_actor_v49c import (
        OutboundDispatchCompletedPayloadV49C,
        OutboundWireOriginV49C,
        OutboundWirePreparedPayloadV49C,
        ParserTransitionPayloadV49C,
        RawIngressCommittedPayloadV49C,
        TransportActorEventKindV49C,
        _decode_single_automatic_protocol_output_v49c,
    )

    if type(prefix) is not CapacityMeasurementOperationPrefixV49F:
        raise CanonicalizationError("returned progress requires an exact prefix")
    # Reconstructing the exact type also replays the receipt span, RAW union,
    # parser cursor chain, two-domain prefix fixed point, and terminal aliases.
    replay = CapacityMeasurementOperationPrefixV49F.from_mapping(prefix.as_dict())
    if replay != prefix:
        raise CanonicalizationError("returned progress prefix differs from replay")
    attempt = prefix.attempt
    terminal = prefix.terminal
    if (
        terminal is not None
        and terminal.terminal_trigger
        is not CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
    ) or len(prefix.new_raw_ingress_commits) != 1:
        raise CanonicalizationError(
            "returned progress requires one completed ingress RAW prefix"
        )
    raw = prefix.new_raw_ingress_commits[0]
    raw_events = tuple(
        event
        for event in prefix.actor_events
        if event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
        and type(event.payload) is RawIngressCommittedPayloadV49C
        and event.payload.raw_ingress_commit_id == raw.raw_ingress_commit_id
    )
    if len(raw_events) != 1:
        raise CanonicalizationError(
            "returned progress cannot resolve one exact RAW actor event"
        )
    raw_payload = raw_events[0].payload
    assert type(raw_payload) is RawIngressCommittedPayloadV49C

    parser_events = tuple(
        event
        for event in prefix.actor_events
        if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
    )
    if any(
        type(event.payload) is not ParserTransitionPayloadV49C
        for event in parser_events
    ):
        raise CanonicalizationError(
            "returned progress contains a non-exact parser transition"
        )
    cursor = attempt.parser_cursor_before
    output_sources: list[Any] = []
    for event in parser_events:
        payload = event.payload
        assert type(payload) is ParserTransitionPayloadV49C
        if payload.cursor_before != cursor:
            raise CanonicalizationError(
                "returned progress parser transition is not cursor-contiguous"
            )
        cursor = payload.cursor_after
        if payload.ordered_protocol_output_chunks_base64:
            output_sources.append(event)

    automatic_wires = tuple(
        event
        for event in prefix.actor_events
        if event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
        and type(event.payload) is OutboundWirePreparedPayloadV49C
        and event.payload.wire_origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
    )
    wire_by_source: dict[str, Any] = {}
    for event in automatic_wires:
        source_id = event.payload.source_parser_event_id
        assert source_id is not None
        if source_id in wire_by_source:
            raise CanonicalizationError(
                "returned progress contains duplicate automatic wire sources"
            )
        wire_by_source[source_id] = event
    expected_source_ids = tuple(
        event.transport_actor_event_id for event in output_sources
    )
    if tuple(wire_by_source) != expected_source_ids:
        raise CanonicalizationError(
            "returned progress automatic wire order differs from parser output"
        )

    dispatch_by_wire: dict[str, Any] = {}
    for event in prefix.actor_events:
        if event.event_kind is not (
            TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
        ):
            continue
        payload = event.payload
        if type(payload) is not OutboundDispatchCompletedPayloadV49C:
            raise CanonicalizationError(
                "returned progress contains a non-exact dispatch completion"
            )
        wire_id = payload.outbound_wire_prepared_event_id
        if wire_id not in {item.transport_actor_event_id for item in automatic_wires}:
            continue
        if wire_id in dispatch_by_wire:
            raise CanonicalizationError(
                "returned progress contains duplicate automatic dispatch completions"
            )
        dispatch_by_wire[wire_id] = event
    if set(dispatch_by_wire) != {
        item.transport_actor_event_id for item in automatic_wires
    }:
        raise CanonicalizationError(
            "returned progress lacks one exact automatic dispatch completion"
        )

    output_chunks: list[bytes] = []
    output_wire_chunk_counts: list[int] = []
    output_frames: list[CapacityMeasurementLogicalOutputFrameV49F] = []
    completion_ids: list[str] = []
    for source in output_sources:
        source_payload = source.payload
        assert type(source_payload) is ParserTransitionPayloadV49C
        chunks = tuple(
            base64.b64decode(value, validate=True)
            for value in source_payload.ordered_protocol_output_chunks_base64
        )
        wire_event = wire_by_source[source.transport_actor_event_id]
        wire_payload = wire_event.payload
        assert type(wire_payload) is OutboundWirePreparedPayloadV49C
        if (
            wire_payload.ordered_wire_chunks_base64
            != source_payload.ordered_protocol_output_chunks_base64
            or wire_event.actor_sequence <= source.actor_sequence
        ):
            raise CanonicalizationError(
                "returned progress automatic wire differs from parser bytes or order"
            )
        dispatch_event = dispatch_by_wire[wire_event.transport_actor_event_id]
        if dispatch_event.actor_sequence <= wire_event.actor_sequence:
            raise CanonicalizationError(
                "returned progress automatic dispatch precedes its wire"
            )
        opcode, payload = _decode_single_automatic_protocol_output_v49c(chunks)
        if (
            wire_payload.logical_opcode is not opcode
            or wire_payload.logical_payload_octets != len(payload)
            or wire_payload.logical_payload_sha256
            != hashlib.sha256(payload).hexdigest()
        ):
            raise CanonicalizationError(
                "returned progress logical output differs from automatic wire"
            )
        output_chunks.extend(chunks)
        output_wire_chunk_counts.append(len(chunks))
        output_frames.append(
            CapacityMeasurementLogicalOutputFrameV49F(
                opcode=opcode.value,
                payload_base64=base64.b64encode(payload).decode("ascii"),
            )
        )
        completion_ids.append(dispatch_event.transport_actor_event_id)

    retained_octets = raw_payload.stream_end_octet - cursor.next_stream_octet
    if retained_octets < 0:
        raise CanonicalizationError(
            "returned progress parser cursor exceeds the committed RAW stream"
        )

    def loop_offset(value: str, *, field: str) -> int:
        offset = int(value) - int(attempt.loop_time_origin_nanoseconds)
        return canonical_safe_int(
            offset,
            field=field,
            minimum=0,
            maximum=MAX_IJSON_INTEGER,
        )

    return CapacityMeasurementIngressProgressEvidenceV49F(
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        ingress_sequence=raw.ingress_sequence,
        committed_raw_octets=len(raw.raw_bytes),
        raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
        parser_event_ids=tuple(
            event.transport_actor_event_id for event in parser_events
        ),
        automatic_output_source_parser_event_ids=expected_source_ids,
        automatic_dispatch_completion_event_ids=tuple(completion_ids),
        automatic_protocol_output_base64=base64.b64encode(
            b"".join(output_chunks)
        ).decode("ascii"),
        automatic_protocol_output_chunk_octet_counts=tuple(
            len(chunk) for chunk in output_chunks
        ),
        automatic_output_wire_chunk_counts=tuple(output_wire_chunk_counts),
        automatic_protocol_output_frames=tuple(output_frames),
        actor_event_count_before=attempt.baseline_actor_event_count,
        actor_tail_event_id_before=attempt.baseline_actor_tail_event_id,
        actor_event_count_after=(
            attempt.baseline_actor_event_count + len(prefix.actor_events)
        ),
        actor_tail_event_id_after=(
            attempt.baseline_actor_tail_event_id
            if not prefix.actor_events
            else prefix.actor_events[-1].transport_actor_event_id
        ),
        retained_incomplete_octets=retained_octets,
        used_initial_pending_ingress=(attempt.initial_pending_ingress_present_before),
        websocket_parser_state=cursor.websocket_state.value,
        admission_policy_id=attempt.admission_policy_id,
        admission_epoch=attempt.admission_epoch,
        admission_sequence=attempt.admission_sequence,
        admission_command_kind=attempt.admission_command_kind.value,
        admission_reservation_work_units=attempt.admission_reservation_work_units,
        admission_admitted_loop_time_offset_nanoseconds=loop_offset(
            attempt.admission_admitted_loop_time_ns,
            field="admission_admitted_loop_time_offset_nanoseconds",
        ),
        admission_started_loop_time_offset_nanoseconds=loop_offset(
            attempt.admission_started_loop_time_ns,
            field="admission_started_loop_time_offset_nanoseconds",
        ),
        admission_start_deadline_loop_time_offset_nanoseconds=loop_offset(
            attempt.admission_start_deadline_loop_time_ns,
            field="admission_start_deadline_loop_time_offset_nanoseconds",
        ),
        admission_queue_wait_nanoseconds=attempt.admission_queue_wait_nanoseconds,
    )


def verify_capacity_measurement_ingress_progress_against_prefix_v49f_v7(
    progress: CapacityMeasurementIngressProgressEvidenceV49F,
    *,
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> None:
    """Reject any returned-progress claim not derived by offline prefix replay."""

    if type(progress) is not CapacityMeasurementIngressProgressEvidenceV49F:
        raise CanonicalizationError("returned progress evidence must be exact")
    replay = CapacityMeasurementIngressProgressEvidenceV49F.from_mapping(
        progress.as_dict()
    )
    if replay != progress:
        raise CanonicalizationError("returned progress differs from exact replay")
    expected = derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7(prefix)
    if progress != expected:
        raise CanonicalizationError(
            "returned progress differs from durable prefix reconstruction"
        )


def _validate_capacity_measurement_terminal_derivations_from_prefix_v49f_v7(
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> None:
    """Re-derive terminal aliases from the serialized durable prefix.

    Store-time construction already owns these choices.  Raw-V7 replay must
    repeat the derivation independently, however, because the post-run suffix
    is unsigned and an offline caller can otherwise recompute a self-consistent
    terminal record and receipt after selecting a more favourable alias.
    """

    if type(prefix) is not CapacityMeasurementOperationPrefixV49F:
        raise CanonicalizationError("Raw V7 derived terminal prefix must be exact")
    terminal = prefix.terminal
    if terminal is None:
        raise CanonicalizationError("Raw V7 derived terminal prefix is open")
    ordinary_attempts = {
        event.transport_actor_event_id
        for event in prefix.actor_events
        if event.event_kind.value == "KERNEL_SEND_ATTEMPT"
    }
    control_attempts = {
        event.transport_actor_event_id
        for event in prefix.actor_events
        if event.event_kind.value == "TLS_CONTROL_KERNEL_SEND_ATTEMPT"
    }
    ordinary_resolved = {
        value
        for event in prefix.actor_events
        for value in (getattr(event.payload, "kernel_send_attempt_event_id", None),)
        if value is not None
    }
    control_resolved = {
        value
        for event in prefix.actor_events
        for value in (
            getattr(
                event.payload,
                "tls_control_kernel_send_attempt_event_id",
                None,
            ),
        )
        if value is not None
    }
    unresolved = bool(
        ordinary_attempts - ordinary_resolved or control_attempts - control_resolved
    )
    returned = terminal.terminal_trigger is (
        CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
    )
    recovery = terminal.terminal_trigger is (
        CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
    )
    if returned:
        if unresolved:
            raise CanonicalizationError(
                "Raw V7 RETURN cannot contain an unresolved durable send attempt"
            )
        expected_effect = CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE
        expected_progress = (
            CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_RETURNED_PROGRESS
        )
    else:
        no_durable_delta = (
            not prefix.new_raw_ingress_commits and not prefix.actor_events
        )
        expected_effect = (
            CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
            if recovery or unresolved
            else CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
            if no_durable_delta
            else CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
        )
        expected_progress = (
            CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_DURABLE_PREFIX
        )
    if (
        terminal.effect_certainty is not expected_effect
        or terminal.progress_availability is not expected_progress
        or terminal.progress_unavailable_reason is not None
    ):
        raise CanonicalizationError(
            "Raw V7 terminal aliases differ from derived durable prefix"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSampleV49FV7:
    committed_attempt: CapacityMeasurementCommittedLifecycleRecordV49FV7
    committed_terminal: CapacityMeasurementCommittedLifecycleRecordV49FV7
    recovered_prefix: CapacityMeasurementOperationPrefixV49F
    observation: CapacityMeasurementObservationV49FV7
    sample_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.committed_attempt) is not (
            CapacityMeasurementCommittedLifecycleRecordV49FV7
        ) or type(self.committed_attempt.record) is not (
            CapacityMeasurementOperationAttemptV49F
        ):
            raise CanonicalizationError("Raw V7 sample attempt must be exact")
        if type(self.committed_terminal) is not (
            CapacityMeasurementCommittedLifecycleRecordV49FV7
        ) or type(self.committed_terminal.record) is not (
            CapacityMeasurementOperationTerminalV49F
        ):
            raise CanonicalizationError("Raw V7 sample terminal must be exact")
        if type(self.recovered_prefix) is not CapacityMeasurementOperationPrefixV49F:
            raise CanonicalizationError("Raw V7 sample prefix must be exact")
        if type(self.observation) is not CapacityMeasurementObservationV49FV7:
            raise CanonicalizationError("Raw V7 sample observation must be exact")
        _verify_projection_record_span_v49f_v7(self.recovered_prefix)
        attempt = self.committed_attempt.record
        terminal = self.committed_terminal.record
        prefix = self.recovered_prefix
        if (
            prefix.terminal is None
            or prefix.attempt != attempt
            or prefix.terminal != terminal
            or prefix.recovered_prefix_id != terminal.recovered_prefix_id
            or prefix.projection_receipts[0].as_dict()
            != self.committed_attempt.projection_receipt.as_dict()
            or prefix.projection_receipts[-1].as_dict()
            != self.committed_terminal.projection_receipt.as_dict()
        ):
            raise CanonicalizationError(
                "Raw V7 sample lifecycle wrappers differ from the exact closed prefix"
            )
        _validate_capacity_measurement_terminal_derivations_from_prefix_v49f_v7(prefix)
        boundary_authority = (
            attempt.transport_session_id,
            attempt.driver_evidence_nonce_sha256,
            attempt.kernel_socket_identity,
            attempt.transport_capacity_policy_id,
        )
        for name in (
            "initial_runtime_boundary",
            "before_runtime_boundary",
            "after_runtime_boundary",
        ):
            boundary = getattr(self.observation, name)
            if (
                boundary is not None
                and (
                    boundary.transport_session_id,
                    boundary.driver_evidence_nonce_sha256,
                    boundary.kernel_socket_identity,
                    boundary.transport_capacity_policy_id,
                )
                != boundary_authority
            ):
                raise CanonicalizationError(
                    f"{name} leaves the measured operation authority"
                )
        for name in ("before_snapshot", "in_operation_snapshot", "after_snapshot"):
            snapshot = getattr(self.observation, name)
            if (
                snapshot is not None
                and snapshot.kernel_socket_identity is not None
                and snapshot.kernel_socket_identity != attempt.kernel_socket_identity
            ):
                raise CanonicalizationError(f"{name} has a foreign socket identity")
        progress = self.observation.returned_ingress_progress
        if (progress is None) != (terminal.returned_progress_evidence_id is None) or (
            progress is not None
            and progress.ingress_progress_evidence_id
            != terminal.returned_progress_evidence_id
        ):
            raise CanonicalizationError(
                "Raw V7 returned progress differs from terminal availability"
            )
        if progress is not None:
            verify_capacity_measurement_ingress_progress_against_prefix_v49f_v7(
                progress,
                prefix=prefix,
            )
        identity = _semantic_identity_v49f_v7(
            domain=A2M_SAMPLE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.sample_id is not None
            and canonical_hash(self.sample_id, field="sample_id") != identity
        ):
            raise CanonicalizationError("Raw V7 sample_id differs from exact evidence")
        object.__setattr__(self, "sample_id", identity)

    @property
    def attempt(self) -> CapacityMeasurementOperationAttemptV49F:
        record = self.committed_attempt.record
        assert type(record) is CapacityMeasurementOperationAttemptV49F
        return record

    @property
    def terminal(self) -> CapacityMeasurementOperationTerminalV49F:
        record = self.committed_terminal.record
        assert type(record) is CapacityMeasurementOperationTerminalV49F
        return record

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "committed_attempt": self.committed_attempt.as_dict(),
            "committed_terminal": self.committed_terminal.as_dict(),
            "observation": self.observation.as_dict(),
            "recovered_prefix": self.recovered_prefix.as_dict(),
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 sample was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_SAMPLE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="sample_id",
            identity=self.sample_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSampleV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_SAMPLE_DOMAIN_V49F_V7,
            context="Raw V7 sample",
        )
        return cls(
            committed_attempt=(
                CapacityMeasurementCommittedLifecycleRecordV49FV7.from_mapping(
                    item["committed_attempt"]
                )
            ),
            committed_terminal=(
                CapacityMeasurementCommittedLifecycleRecordV49FV7.from_mapping(
                    item["committed_terminal"]
                )
            ),
            recovered_prefix=CapacityMeasurementOperationPrefixV49F.from_mapping(
                item["recovered_prefix"]
            ),
            observation=CapacityMeasurementObservationV49FV7.from_mapping(
                item["observation"]
            ),
            sample_id=item["sample_id"],
        )


def _expected_schedule_v49f_v7(
    manifest: CapacityMeasurementManifestV49FV7,
) -> tuple[tuple[str, bool, int], ...]:
    predecessor = manifest.predecessor_manifest_v6
    warmups = [
        (workload.workload_id, True, repetition)
        for workload in predecessor.workloads
        for repetition in range(predecessor.design.warmup_repetitions)
    ]
    measured = [
        (workload.workload_id, False, repetition)
        for workload in predecessor.workloads
        for repetition in range(predecessor.design.measured_repetitions)
    ]
    measured.sort(
        key=lambda item: sha256_digest(
            {
                "domain": "RiskYieldMMA2MSeededMeasuredTrialOrderV4_9F",
                "is_warmup": item[1],
                "random_seed": predecessor.design.random_seed,
                "repetition_index": item[2],
                "workload_id": item[0],
            }
        )
    )
    return tuple(warmups + measured)


def _terminal_is_run_ending_v49f_v7(
    terminal: CapacityMeasurementOperationTerminalV49F,
    *,
    lifecycle_contract: CapacityMeasurementLifecycleContractV49FV7,
) -> bool:
    trigger = terminal.terminal_trigger
    if trigger in {
        CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED,
        CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED,
        CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN,
    }:
        return True
    return (
        trigger is CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION
        and terminal.operation_error_code is not None
        and terminal.surfaced_exception_class is not None
        and (
            terminal.operation_error_code,
            terminal.surfaced_exception_class,
        )
        in lifecycle_contract.fatal_operation_exceptions
    )


def validate_capacity_measurement_samples_v49f_v7(
    samples: Sequence[CapacityMeasurementSampleV49FV7],
    *,
    manifest: CapacityMeasurementManifestV49FV7,
) -> tuple[CapacityMeasurementSampleV49FV7, ...]:
    if type(manifest) is not CapacityMeasurementManifestV49FV7:
        raise CanonicalizationError("Raw V7 manifest must be exact")
    if (
        type(samples) not in {list, tuple}
        or not samples
        or len(samples) > A2M_MAXIMUM_TOTAL_TRIALS_V49F
    ):
        raise CanonicalizationError("Raw V7 samples must be a bounded non-empty set")
    normalized = tuple(samples)
    if any(type(item) is not CapacityMeasurementSampleV49FV7 for item in normalized):
        raise CanonicalizationError("Raw V7 sample stream contains a foreign record")
    predecessor = manifest.predecessor_manifest_v6
    expected_schedule = _expected_schedule_v49f_v7(manifest)
    actual_schedule: list[tuple[str, bool, int]] = []
    previous_terminal_id: str | None = None
    previous_receipt_sequence = manifest.projection_authority.baseline_receipt_sequence
    previous_receipt_hash = manifest.projection_authority.baseline_receipt_hash
    previous_terminal: CapacityMeasurementOperationTerminalV49F | None = None
    previous_parser_cursor = manifest.actor_baseline.parser_cursor
    seen_attempts: set[str] = set()
    seen_terminals: set[str] = set()
    for index, sample in enumerate(normalized, start=1):
        replay = CapacityMeasurementSampleV49FV7.from_mapping(sample.as_dict())
        if replay != sample:
            raise CanonicalizationError("Raw V7 sample differs from exact replay")
        attempt = sample.attempt
        terminal = sample.terminal
        if (
            attempt.campaign_manifest_id != manifest.campaign_manifest_id
            or attempt.manifest_authority_id
            != manifest.manifest_authority_v7.manifest_authority_id
            or attempt.measurement_design_id != predecessor.design.measurement_design_id
            or attempt.transport_session_id != predecessor.transport_session_id
            or attempt.driver_evidence_nonce_sha256
            != predecessor.driver_evidence_nonce_sha256
            or attempt.kernel_socket_identity != predecessor.kernel_socket_identity
            or attempt.transport_capacity_policy_id
            != predecessor.transport_capacity_policy_id
            or attempt.sample_sequence != index
            or attempt.operation_sequence != index
            or attempt.trial_index != index - 1
            or attempt.previous_operation_terminal_id != previous_terminal_id
            or terminal.previous_operation_terminal_id != previous_terminal_id
            or terminal.attempt_id != attempt.attempt_id
        ):
            raise CanonicalizationError(
                "Raw V7 sample leaves its manifest or contiguous lifecycle chain"
            )
        actor_authority = manifest.actor_baseline
        expected_raw_baseline = (
            (
                actor_authority.raw_ingress_sequence,
                actor_authority.raw_ingress_commit_id,
            )
            if previous_terminal is None
            else (
                previous_terminal.terminal_raw_ingress_sequence,
                previous_terminal.terminal_raw_ingress_commit_id,
            )
        )
        expected_actor_baseline = (
            (
                actor_authority.actor_event_count,
                actor_authority.actor_tail_event_id,
            )
            if previous_terminal is None
            else (
                previous_terminal.terminal_actor_event_count,
                previous_terminal.terminal_actor_tail_event_id,
            )
        )
        expected_parser_runtime = (
            (
                previous_parser_cursor,
                actor_authority.parser_cursor_id,
                actor_authority.runtime_state,
            )
            if previous_terminal is None
            else (
                previous_parser_cursor,
                previous_terminal.parser_cursor_id_after,
                previous_terminal.runtime_state_after,
            )
        )
        if (
            attempt.projection_ledger_id
            != manifest.projection_authority.projection_ledger_id
            or attempt.projection_schema_version
            != manifest.projection_authority.projection_schema_version
            or attempt.projection_validation_version
            != manifest.projection_authority.projection_validation_version
            or attempt.projection_schema_fingerprint
            != manifest.projection_authority.projection_schema_fingerprint
            or (
                attempt.writer_fence_token_sha256,
                attempt.writer_fence_generation,
                attempt.monotonic_clock_domain_id,
            )
            != (
                actor_authority.writer_fence_token_sha256,
                actor_authority.writer_fence_generation,
                actor_authority.monotonic_clock_domain_id,
            )
            or (
                attempt.baseline_raw_ingress_sequence,
                attempt.baseline_raw_ingress_commit_id,
            )
            != expected_raw_baseline
            or (
                attempt.baseline_actor_event_count,
                attempt.baseline_actor_tail_event_id,
            )
            != expected_actor_baseline
            or (
                attempt.parser_cursor_before,
                attempt.parser_cursor_id_before,
                attempt.runtime_state_before,
            )
            != expected_parser_runtime
        ):
            raise CanonicalizationError(
                "Raw V7 attempt baseline differs from signed projection/actor state"
            )
        event_authority = (
            actor_authority.transport_subscription_policy_id,
            actor_authority.transport_session_id,
            actor_authority.physical_scope_manifest_id,
            actor_authority.adapter_policy_id,
            actor_authority.capture_partition_id,
            actor_authority.socket_lease_id,
            actor_authority.connection_generation,
            actor_authority.deployment_bundle_id,
            actor_authority.writer_fence_token_sha256,
            actor_authority.writer_fence_generation,
            actor_authority.monotonic_clock_domain_id,
            actor_authority.driver_policy_id,
        )
        for event in sample.recovered_prefix.actor_events:
            if (
                event.transport_subscription_policy_id,
                event.transport_session_id,
                event.physical_scope_manifest_id,
                event.adapter_policy_id,
                event.capture_partition_id,
                event.socket_lease_id,
                event.connection_generation,
                event.deployment_bundle_id,
                event.writer_fence_token_sha256,
                event.writer_fence_generation,
                event.monotonic_clock_domain_id,
                event.driver_policy_id,
            ) != event_authority:
                raise CanonicalizationError(
                    "Raw V7 actor event leaves the signed actor authority"
                )
        raw_authority = event_authority[:-1]
        for raw in sample.recovered_prefix.raw_dependencies:
            if (
                raw.transport_subscription_policy_id,
                raw.transport_session_id,
                raw.physical_scope_manifest_id,
                raw.adapter_policy_id,
                raw.capture_partition_id,
                raw.socket_lease_id,
                raw.connection_generation,
                raw.deployment_bundle_id,
                raw.writer_fence_token_sha256,
                raw.writer_fence_generation,
                raw.monotonic_clock_domain_id,
            ) != raw_authority:
                raise CanonicalizationError(
                    "Raw V7 RAW dependency leaves the signed actor authority"
                )
        workload = next(
            (
                item
                for item in predecessor.workloads
                if item.workload_id == attempt.workload_id
            ),
            None,
        )
        if workload is None or workload.workload_sha256 != attempt.workload_sha256:
            raise CanonicalizationError("Raw V7 sample workload is undeclared")
        workload_spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
            workload.workload_manifest_json
        )
        input_bytes = b"".join(workload_spec.input_chunks)
        expected_declaration = (
            predecessor.design.measurement_design_id,
            workload.workload_id,
            workload.workload_sha256,
            index,
            index,
            index - 1,
            expected_schedule[index - 1][2],
            expected_schedule[index - 1][1],
            workload_spec.stage,
            CapacityMeasurementLifecycleOperationV49F.INGRESS,
            len(workload_spec.input_chunks),
            len(input_bytes),
            hashlib.sha256(input_bytes).hexdigest(),
            workload_spec.raw_ingress_batch_sha256,
            workload_spec.timeout_seconds,
            len(workload_spec.expected_output_frames),
            workload_spec.expected_output_frames_sha256,
        )
        actual_declaration = (
            attempt.measurement_design_id,
            attempt.workload_id,
            attempt.workload_sha256,
            attempt.sample_sequence,
            attempt.operation_sequence,
            attempt.trial_index,
            attempt.repetition_index,
            attempt.is_warmup,
            attempt.stage,
            attempt.operation,
            attempt.input_chunk_count,
            attempt.input_octet_count,
            attempt.input_sha256,
            attempt.raw_ingress_batch_sha256,
            attempt.timeout_seconds,
            attempt.expected_output_frame_count,
            attempt.expected_output_frames_sha256,
        )
        if actual_declaration != expected_declaration:
            raise CanonicalizationError(
                "Raw V7 attempt differs from the signed workload declaration"
            )
        if (
            attempt.attempt_id in seen_attempts
            or terminal.terminal_id in seen_terminals
        ):
            raise CanonicalizationError("Raw V7 lifecycle record is duplicated")
        seen_attempts.add(attempt.attempt_id)
        seen_terminals.add(terminal.terminal_id)
        first_receipt = sample.recovered_prefix.projection_receipts[0]
        if (
            first_receipt.global_sequence != previous_receipt_sequence + 1
            or first_receipt.previous_receipt_hash != previous_receipt_hash
            or first_receipt.ledger_id
            != manifest.projection_authority.projection_ledger_id
        ):
            raise CanonicalizationError(
                "Raw V7 samples do not extend one contiguous projection ledger"
            )
        last_receipt = sample.recovered_prefix.projection_receipts[-1]
        previous_receipt_sequence = last_receipt.global_sequence
        previous_receipt_hash = last_receipt.receipt_hash
        actual_schedule.append(
            (attempt.workload_id, attempt.is_warmup, attempt.repetition_index)
        )
        previous_terminal_id = terminal.terminal_id
        previous_terminal = terminal
        previous_parser_cursor = attempt.parser_cursor_before
        for event in sample.recovered_prefix.actor_events:
            if event.event_kind.value == "PARSER_TRANSITION":
                previous_parser_cursor = event.payload.cursor_after
        if index < len(normalized) and _terminal_is_run_ending_v49f_v7(
            terminal, lifecycle_contract=manifest.lifecycle_contract
        ):
            raise CanonicalizationError(
                "Raw V7 sample appears after a run-ending terminal"
            )
    if tuple(actual_schedule) != expected_schedule[: len(normalized)]:
        raise CanonicalizationError("Raw V7 schedule prefix is missing or reordered")
    if len(normalized) < len(expected_schedule) and not _terminal_is_run_ending_v49f_v7(
        normalized[-1].terminal,
        lifecycle_contract=manifest.lifecycle_contract,
    ):
        raise CanonicalizationError(
            "short Raw V7 schedule must end in a structurally valid run-ending terminal"
        )
    return normalized


def _validate_capacity_measurement_samples_length_v49f_v7(
    byte_length: int,
) -> None:
    if type(byte_length) is not int or byte_length < 0:
        raise TypeError("Raw V7 samples byte length must be a nonnegative exact int")
    if byte_length > A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 samples artifact exceeds its bounded byte limit"
        )


def _accumulate_capacity_measurement_samples_length_v49f_v7(
    *,
    prior_length: int,
    sample_record_length: int,
) -> int:
    if type(prior_length) is not int or prior_length < 0:
        raise TypeError(
            "Raw V7 prior samples byte length must be a nonnegative exact int"
        )
    if type(sample_record_length) is not int or sample_record_length < 0:
        raise TypeError("Raw V7 sample byte length must be a nonnegative exact int")
    if sample_record_length > A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 sample record exceeds its byte bound"
        )
    total = prior_length + sample_record_length
    _validate_capacity_measurement_samples_length_v49f_v7(total)
    return total


def encode_capacity_measurement_samples_jsonl_v49f_v7(
    samples: Sequence[CapacityMeasurementSampleV49FV7],
    *,
    manifest: CapacityMeasurementManifestV49FV7,
) -> bytes:
    normalized = validate_capacity_measurement_samples_v49f_v7(
        samples, manifest=manifest
    )
    lines: list[bytes] = []
    total = 0
    for sample in normalized:
        line = canonical_json_bytes(sample.as_dict()) + b"\n"
        total = _accumulate_capacity_measurement_samples_length_v49f_v7(
            prior_length=total,
            sample_record_length=len(line),
        )
        lines.append(line)
    return b"".join(lines)


def decode_capacity_measurement_samples_jsonl_v49f_v7(
    payload: bytes,
    *,
    manifest: CapacityMeasurementManifestV49FV7,
) -> tuple[CapacityMeasurementSampleV49FV7, ...]:
    if type(payload) is not bytes or not payload:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 samples must be bounded non-empty LF-terminated JSONL"
        )
    _validate_capacity_measurement_samples_length_v49f_v7(len(payload))
    if (
        not payload.endswith(b"\n")
        or b"\r" in payload
        or payload.count(b"\n") > A2M_MAXIMUM_TOTAL_TRIALS_V49F
    ):
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 samples must be bounded non-empty LF-terminated JSONL"
        )
    samples: list[CapacityMeasurementSampleV49FV7] = []
    total = 0
    for line in payload.splitlines(keepends=True):
        if len(line) <= 1:
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 sample JSONL record is empty or oversized"
            )
        total = _accumulate_capacity_measurement_samples_length_v49f_v7(
            prior_length=total,
            sample_record_length=len(line),
        )
        validate_capacity_measurement_json_structure_before_parse_v49f_v7(line[:-1])
        parsed = strict_json_loads(line[:-1])
        if not isinstance(parsed, Mapping):
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 sample JSONL record must be an object"
            )
        sample = CapacityMeasurementSampleV49FV7.from_mapping(parsed)
        if canonical_json_bytes(sample.as_dict()) + b"\n" != line:
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 sample JSONL record is not canonical"
            )
        samples.append(sample)
    return validate_capacity_measurement_samples_v49f_v7(samples, manifest=manifest)


def capacity_measurement_sample_stream_sha256_v49f_v7(
    samples: Sequence[CapacityMeasurementSampleV49FV7],
    *,
    manifest: CapacityMeasurementManifestV49FV7,
) -> str:
    return hashlib.sha256(
        encode_capacity_measurement_samples_jsonl_v49f_v7(samples, manifest=manifest)
    ).hexdigest()


def _sample_roots_v49f_v7(
    samples: Sequence[CapacityMeasurementSampleV49FV7],
) -> tuple[str, str, str]:
    raw = [
        [
            item.raw_ingress_commit_id
            for item in sample.recovered_prefix.raw_dependencies
        ]
        for sample in samples
    ]
    actor = [
        [item.transport_actor_event_id for item in sample.recovered_prefix.actor_events]
        for sample in samples
    ]
    projection = [
        [
            {
                "global_sequence": item.global_sequence,
                "receipt_hash": item.receipt_hash,
            }
            for item in sample.recovered_prefix.projection_receipts
        ]
        for sample in samples
    ]
    return (
        sha256_digest({"domain": "RiskYieldMMA2MV7RawIngressRoot", "samples": raw}),
        sha256_digest({"domain": "RiskYieldMMA2MV7ActorEventRoot", "samples": actor}),
        sha256_digest(
            {"domain": "RiskYieldMMA2MV7ProjectionReceiptRoot", "samples": projection}
        ),
    )


_A2M_CORRECTNESS_BOOLEAN_FIELDS_V49F_V7 = (
    "no_loss",
    "no_duplication",
    "no_reordering",
    "control_output_causal",
    "projection_verified",
    "observations_complete",
    "cleanup_complete",
)
_A2M_FINALIZER_OWNED_FIELDS_V49F_V7 = (
    "no_loss",
    "no_duplication",
    "no_reordering",
    "control_output_causal",
    "projection_verified",
    "cleanup_complete",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementCorrectnessV49FV7:
    campaign_manifest_id: str
    manifest_authority_id: str
    sample_stream_sha256: str
    sample_count: int
    first_sample_id: str
    last_sample_id: str
    schedule_coverage: CapacityMeasurementScheduleCoverageV49FV7
    expected_sample_count: int
    last_operation_sequence: int
    last_terminal_id: str
    raw_ingress_root_sha256: str
    actor_event_root_sha256: str
    projection_root_sha256: str
    no_loss: bool
    no_duplication: bool
    no_reordering: bool
    control_output_causal: bool
    projection_verified: bool
    observations_complete: bool
    cleanup_complete: bool
    failure_codes: tuple[str, ...]
    correctness_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "sample_stream_sha256",
            "first_sample_id",
            "last_sample_id",
            "last_terminal_id",
            "raw_ingress_root_sha256",
            "actor_event_root_sha256",
            "projection_root_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in (
            "sample_count",
            "expected_sample_count",
            "last_operation_sequence",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(
                    getattr(self, name),
                    field=name,
                    minimum=1,
                    maximum=A2M_MAXIMUM_TOTAL_TRIALS_V49F,
                ),
            )
        _exact_enum(
            self.schedule_coverage,
            CapacityMeasurementScheduleCoverageV49FV7,
            field="schedule_coverage",
        )
        if (
            self.sample_count > self.expected_sample_count
            or self.last_operation_sequence != self.sample_count
            or (
                self.schedule_coverage
                is CapacityMeasurementScheduleCoverageV49FV7.COMPLETE
            )
            != (self.sample_count == self.expected_sample_count)
        ):
            raise CanonicalizationError("Raw V7 correctness schedule coverage differs")
        for name in _A2M_CORRECTNESS_BOOLEAN_FIELDS_V49F_V7:
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        failures = canonical_reason_codes(self.failure_codes, field="failure_codes")
        if A2M_CORRECTNESS_FINALIZER_NOT_IMPLEMENTED_V49F_V7 not in failures:
            raise CanonicalizationError(
                "Raw V7 correctness must remain explicitly unfinalized"
            )
        if A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7 not in failures:
            raise CanonicalizationError(
                "Raw V7 correctness must disclose unattested post-run provenance"
            )
        if any(getattr(self, name) for name in _A2M_FINALIZER_OWNED_FIELDS_V49F_V7):
            raise CanonicalizationError(
                "Raw V7 provisional correctness cannot assert finalizer-owned claims"
            )
        object.__setattr__(self, "failure_codes", failures)
        identity = _semantic_identity_v49f_v7(
            domain=A2M_CORRECTNESS_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.correctness_id is not None
            and canonical_hash(self.correctness_id, field="correctness_id") != identity
        ):
            raise CanonicalizationError("Raw V7 correctness_id differs")
        object.__setattr__(self, "correctness_id", identity)

    @property
    def passed(self) -> bool:
        return False

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for item in fields(type(self)):
            if item.name == "correctness_id":
                continue
            value = getattr(self, item.name)
            if isinstance(value, Enum):
                value = value.value
            elif isinstance(value, tuple):
                value = list(value)
            result[item.name] = value
        return result

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 correctness was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_CORRECTNESS_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="correctness_id",
            identity=self.correctness_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementCorrectnessV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_CORRECTNESS_DOMAIN_V49F_V7,
            context="Raw V7 correctness",
        )
        if type(item["failure_codes"]) is not list:
            raise CanonicalizationError("Raw V7 failure_codes must be a JSON array")
        try:
            coverage = CapacityMeasurementScheduleCoverageV49FV7(
                item["schedule_coverage"]
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError(
                "Raw V7 schedule coverage is unsupported"
            ) from exc
        return cls(
            **{
                **item,
                "schedule_coverage": coverage,
                "failure_codes": tuple(item["failure_codes"]),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementArtifactMemberV49FV7:
    artifact_name: str
    media_type: str
    byte_count: int
    record_count: int
    sha256: str

    def __post_init__(self) -> None:
        name = canonical_identifier(self.artifact_name, field="artifact_name")
        if name not in _RAW_ARTIFACT_NAMES:
            raise CanonicalizationError("Raw V7 integrity member name is unsupported")
        expected_media = (
            "application/x-ndjson"
            if name == SAMPLES_ARTIFACT_NAME_V49F
            else "application/json"
        )
        if self.media_type != expected_media:
            raise CanonicalizationError("Raw V7 integrity member media type differs")
        object.__setattr__(self, "artifact_name", name)
        object.__setattr__(
            self,
            "byte_count",
            canonical_safe_int(
                self.byte_count,
                field="byte_count",
                minimum=1,
                maximum=_ARTIFACT_BYTE_LIMITS_V49F[name],
            ),
        )
        object.__setattr__(
            self,
            "record_count",
            canonical_safe_int(
                self.record_count,
                field="record_count",
                minimum=1,
                maximum=(
                    A2M_MAXIMUM_TOTAL_TRIALS_V49F
                    if name == SAMPLES_ARTIFACT_NAME_V49F
                    else 1
                ),
            ),
        )
        object.__setattr__(self, "sha256", canonical_hash(self.sha256, field="sha256"))
        if name != SAMPLES_ARTIFACT_NAME_V49F and self.record_count != 1:
            raise CanonicalizationError("Raw V7 singleton record count differs")

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 integrity member was mutated")
        return {item.name: getattr(self, item.name) for item in fields(type(self))}

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementArtifactMemberV49FV7:
        return cls(
            **_mapping(
                payload,
                expected=_record_keys(cls),
                context="Raw V7 integrity member",
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIntegrityV49FV7:
    campaign_manifest_id: str
    manifest_authority_id: str
    projection_ledger_id: str
    members: tuple[CapacityMeasurementArtifactMemberV49FV7, ...]
    integrity_id: str | None = None
    evidence_bundle_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "campaign_manifest_id",
            "manifest_authority_id",
            "projection_ledger_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        if type(self.members) is not tuple or any(
            type(item) is not CapacityMeasurementArtifactMemberV49FV7
            for item in self.members
        ):
            raise CanonicalizationError("Raw V7 integrity members must be exact")
        if tuple(item.artifact_name for item in self.members) != tuple(
            sorted(_RAW_ARTIFACT_NAMES)
        ):
            raise CanonicalizationError(
                "Raw V7 integrity must close exactly three raw artifacts"
            )
        identity = _semantic_identity_v49f_v7(
            domain=A2M_INTEGRITY_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        for name in ("integrity_id", "evidence_bundle_id"):
            supplied = getattr(self, name)
            if (
                supplied is not None
                and canonical_hash(supplied, field=name) != identity
            ):
                raise CanonicalizationError(f"Raw V7 {name} differs")
            object.__setattr__(self, name, identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "campaign_manifest_id": self.campaign_manifest_id,
            "manifest_authority_id": self.manifest_authority_id,
            "members": [item.as_dict() for item in self.members],
            "projection_ledger_id": self.projection_ledger_id,
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 integrity was mutated")
        return {
            **_semantic_record_v49f_v7(
                domain=A2M_INTEGRITY_DOMAIN_V49F_V7,
                payload=self._identity_payload_unchecked(),
                identity_field="integrity_id",
                identity=self.integrity_id,
            ),
            "evidence_bundle_id": self.evidence_bundle_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementIntegrityV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_INTEGRITY_DOMAIN_V49F_V7,
            context="Raw V7 integrity",
        )
        if type(item["members"]) is not list:
            raise CanonicalizationError("Raw V7 integrity members must be a JSON array")
        return cls(
            **{
                **item,
                "members": tuple(
                    CapacityMeasurementArtifactMemberV49FV7.from_mapping(value)
                    for value in item["members"]
                ),
            }
        )


_SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F_V7 = (
    CapacityMeasurementManifestV49FV7,
    CapacityMeasurementObservationV49FV7,
    CapacityMeasurementSampleV49FV7,
    CapacityMeasurementCorrectnessV49FV7,
    CapacityMeasurementArtifactMemberV49FV7,
    CapacityMeasurementIntegrityV49FV7,
)


def _measurement_json_record_limit_v49f_v7(record_type: type[Any]) -> int:
    if record_type is CapacityMeasurementManifestV49FV7:
        return A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F
    if record_type is CapacityMeasurementSampleV49FV7:
        return A2M_MAXIMUM_SAMPLE_RECORD_BYTES_V49F
    if record_type is CapacityMeasurementCorrectnessV49FV7:
        return A2M_MAXIMUM_CORRECTNESS_ARTIFACT_BYTES_V49F
    if record_type is CapacityMeasurementIntegrityV49FV7:
        return A2M_MAXIMUM_INTEGRITY_ARTIFACT_BYTES_V49F
    return A2M_MAXIMUM_MANIFEST_ARTIFACT_BYTES_V49F


def encode_capacity_measurement_json_v49f_v7(record: _MeasurementRecord) -> bytes:
    if type(record) not in _SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F_V7:
        raise CanonicalizationError("Raw V7 measurement JSON record is unsupported")
    encoded = canonical_json_bytes(record.as_dict()) + b"\n"
    if len(encoded) > _measurement_json_record_limit_v49f_v7(type(record)):
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 measurement JSON exceeds its record byte bound"
        )
    return encoded


def decode_capacity_measurement_json_v49f_v7(
    payload: bytes,
    *,
    record_type: type[_RecordT],
) -> _RecordT:
    if record_type not in _SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F_V7:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 measurement JSON record type is unsupported"
        )
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > _measurement_json_record_limit_v49f_v7(record_type)
        or not payload.endswith(b"\n")
        or payload.count(b"\n") != 1
    ):
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 measurement JSON must be one bounded LF-terminated record"
        )
    validate_capacity_measurement_json_structure_before_parse_v49f_v7(payload[:-1])
    parsed = strict_json_loads(payload[:-1])
    if not isinstance(parsed, Mapping):
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 measurement JSON must be an object"
        )
    record = record_type.from_mapping(parsed)  # type: ignore[attr-defined]
    if encode_capacity_measurement_json_v49f_v7(record) != payload:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 measurement JSON does not replay canonically"
        )
    return record


def capacity_measurement_observation_is_complete_v49f_v7(
    observation: CapacityMeasurementObservationV49FV7,
) -> bool:
    """Derive completeness from every component and nested availability marker."""

    if type(observation) is not CapacityMeasurementObservationV49FV7:
        raise TypeError("Raw V7 observation completeness requires an exact record")
    if any(
        getattr(observation, name) is None
        or getattr(observation, f"{name}_unavailable_reason") is not None
        for name, _ in observation._COMPONENTS
    ):
        return False
    for name in ("before_snapshot", "in_operation_snapshot", "after_snapshot"):
        snapshot = getattr(observation, name)
        assert type(snapshot) is CapacityMeasurementLayerSnapshotV49F
        if (
            snapshot.unavailable_fields
            or snapshot.unavailable_reason_codes
            or any(
                span.unavailable_fields or span.unavailable_reason_codes
                for span in snapshot.adapter_spans
            )
        ):
            return False
    return True


def _validate_correctness_links_v49f_v7(
    manifest: CapacityMeasurementManifestV49FV7,
    samples: tuple[CapacityMeasurementSampleV49FV7, ...],
    correctness: CapacityMeasurementCorrectnessV49FV7,
) -> None:
    if type(correctness) is not CapacityMeasurementCorrectnessV49FV7:
        raise CanonicalizationError("Raw V7 correctness must be exact")
    expected_total = len(_expected_schedule_v49f_v7(manifest))
    coverage = (
        CapacityMeasurementScheduleCoverageV49FV7.COMPLETE
        if len(samples) == expected_total
        else CapacityMeasurementScheduleCoverageV49FV7.RUN_ENDING_PREFIX
    )
    roots = _sample_roots_v49f_v7(samples)
    expected = (
        manifest.campaign_manifest_id,
        manifest.manifest_authority_v7.manifest_authority_id,
        capacity_measurement_sample_stream_sha256_v49f_v7(samples, manifest=manifest),
        len(samples),
        samples[0].sample_id,
        samples[-1].sample_id,
        coverage,
        expected_total,
        samples[-1].attempt.operation_sequence,
        samples[-1].terminal.terminal_id,
        *roots,
        all(
            capacity_measurement_observation_is_complete_v49f_v7(sample.observation)
            for sample in samples
        ),
    )
    actual = (
        correctness.campaign_manifest_id,
        correctness.manifest_authority_id,
        correctness.sample_stream_sha256,
        correctness.sample_count,
        correctness.first_sample_id,
        correctness.last_sample_id,
        correctness.schedule_coverage,
        correctness.expected_sample_count,
        correctness.last_operation_sequence,
        correctness.last_terminal_id,
        correctness.raw_ingress_root_sha256,
        correctness.actor_event_root_sha256,
        correctness.projection_root_sha256,
        correctness.observations_complete,
    )
    if actual != expected:
        raise CanonicalizationError(
            "Raw V7 correctness differs from exact manifest and sample stream"
        )


def _raw_member_bytes_v49f_v7(
    manifest: CapacityMeasurementManifestV49FV7,
    samples: tuple[CapacityMeasurementSampleV49FV7, ...],
    correctness: CapacityMeasurementCorrectnessV49FV7,
) -> dict[str, bytes]:
    return {
        MANIFEST_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f_v7(manifest),
        SAMPLES_ARTIFACT_NAME_V49F: encode_capacity_measurement_samples_jsonl_v49f_v7(
            samples, manifest=manifest
        ),
        CORRECTNESS_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f_v7(
            correctness
        ),
    }


def _integrity_for_raw_v49f_v7(
    manifest: CapacityMeasurementManifestV49FV7,
    raw: Mapping[str, bytes],
    *,
    sample_count: int,
) -> CapacityMeasurementIntegrityV49FV7:
    return CapacityMeasurementIntegrityV49FV7(
        campaign_manifest_id=manifest.campaign_manifest_id,
        manifest_authority_id=manifest.manifest_authority_v7.manifest_authority_id,
        projection_ledger_id=manifest.projection_authority.projection_ledger_id,
        members=tuple(
            CapacityMeasurementArtifactMemberV49FV7(
                artifact_name=name,
                media_type=(
                    "application/x-ndjson"
                    if name == SAMPLES_ARTIFACT_NAME_V49F
                    else "application/json"
                ),
                byte_count=len(raw[name]),
                record_count=(
                    sample_count if name == SAMPLES_ARTIFACT_NAME_V49F else 1
                ),
                sha256=hashlib.sha256(raw[name]).hexdigest(),
            )
            for name in sorted(_RAW_ARTIFACT_NAMES)
        ),
    )


def _validate_capacity_measurement_artifact_closure_length_v49f_v7(
    byte_length: int,
) -> None:
    if type(byte_length) is not int or byte_length < 0:
        raise TypeError("Raw V7 closure byte length must be a nonnegative exact int")
    if byte_length > A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F:
        raise CapacityMeasurementArtifactErrorV49F(
            "Raw V7 artifact closure exceeds its frozen total byte bound"
        )


def _validate_capacity_measurement_artifact_member_lengths_v49f_v7(
    member_lengths: Mapping[str, int],
) -> None:
    if (
        not isinstance(member_lengths, Mapping)
        or set(member_lengths) != _BUNDLE_ARTIFACT_NAMES
        or any(
            type(name) is not str or type(byte_length) is not int or byte_length < 0
            for name, byte_length in member_lengths.items()
        )
    ):
        raise TypeError("Raw V7 member lengths must be an exact four-member mapping")
    for name in sorted(_BUNDLE_ARTIFACT_NAMES):
        if member_lengths[name] > _ARTIFACT_BYTE_LIMITS_V49F[name]:
            raise CapacityMeasurementArtifactErrorV49F(
                f"Raw V7 artifact member {name} exceeds its frozen byte bound"
            )
    _validate_capacity_measurement_artifact_closure_length_v49f_v7(
        sum(member_lengths.values())
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementArtifactBundleV49FV7:
    manifest: CapacityMeasurementManifestV49FV7
    samples: tuple[CapacityMeasurementSampleV49FV7, ...]
    correctness: CapacityMeasurementCorrectnessV49FV7
    integrity: CapacityMeasurementIntegrityV49FV7

    def __post_init__(self) -> None:
        if type(self.manifest) is not CapacityMeasurementManifestV49FV7:
            raise CanonicalizationError("Raw V7 bundle manifest must be exact")
        normalized = validate_capacity_measurement_samples_v49f_v7(
            self.samples, manifest=self.manifest
        )
        object.__setattr__(self, "samples", normalized)
        _validate_correctness_links_v49f_v7(self.manifest, normalized, self.correctness)
        if type(self.integrity) is not CapacityMeasurementIntegrityV49FV7:
            raise CanonicalizationError("Raw V7 bundle integrity must be exact")
        raw = _raw_member_bytes_v49f_v7(self.manifest, normalized, self.correctness)
        expected_integrity = _integrity_for_raw_v49f_v7(
            self.manifest, raw, sample_count=len(normalized)
        )
        if self.integrity != expected_integrity:
            raise CanonicalizationError(
                "Raw V7 integrity differs from exact raw artifact bytes"
            )

    @property
    def evidence_bundle_id(self) -> str:
        assert self.integrity.evidence_bundle_id is not None
        return self.integrity.evidence_bundle_id

    @classmethod
    def build(
        cls,
        *,
        manifest: CapacityMeasurementManifestV49FV7,
        samples: Sequence[CapacityMeasurementSampleV49FV7],
        correctness: CapacityMeasurementCorrectnessV49FV7,
    ) -> CapacityMeasurementArtifactBundleV49FV7:
        normalized = validate_capacity_measurement_samples_v49f_v7(
            samples, manifest=manifest
        )
        _validate_correctness_links_v49f_v7(manifest, normalized, correctness)
        raw = _raw_member_bytes_v49f_v7(manifest, normalized, correctness)
        return cls(
            manifest=manifest,
            samples=normalized,
            correctness=correctness,
            integrity=_integrity_for_raw_v49f_v7(
                manifest, raw, sample_count=len(normalized)
            ),
        )

    def artifact_bytes(self) -> dict[str, bytes]:
        raw = _raw_member_bytes_v49f_v7(self.manifest, self.samples, self.correctness)
        artifacts = {
            **raw,
            INTEGRITY_ARTIFACT_NAME_V49F: encode_capacity_measurement_json_v49f_v7(
                self.integrity
            ),
        }
        return artifacts

    @classmethod
    def from_artifact_bytes(
        cls,
        artifacts: Mapping[str, bytes],
        *,
        expectation: Any,
    ) -> CapacityMeasurementArtifactBundleV49FV7:
        from .physical_transport_capacity_manifest_authority_v49f import (
            AdmittedCapacityMeasurementAuthorityExpectationV49FV7,
            verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7,
        )

        if (
            type(expectation)
            is not AdmittedCapacityMeasurementAuthorityExpectationV49FV7
        ):
            raise TypeError(
                "Raw V7 artifact replay requires an exact admitted expectation"
            )
        if (
            not isinstance(artifacts, Mapping)
            or set(artifacts) != _BUNDLE_ARTIFACT_NAMES
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 closure must contain exactly four artifact members"
            )
        if any(
            type(name) is not str or type(value) is not bytes
            for name, value in artifacts.items()
        ):
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 artifact names and bytes must be exact"
            )
        if any(not value for value in artifacts.values()):
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 artifact closure exceeds its frozen bounds"
            )
        _validate_capacity_measurement_artifact_member_lengths_v49f_v7(
            {name: len(value) for name, value in artifacts.items()}
        )
        integrity = decode_capacity_measurement_json_v49f_v7(
            artifacts[INTEGRITY_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementIntegrityV49FV7,
        )
        members = {item.artifact_name: item for item in integrity.members}
        for name in _RAW_ARTIFACT_NAMES:
            member = members[name]
            raw = artifacts[name]
            if (
                member.byte_count != len(raw)
                or member.sha256 != hashlib.sha256(raw).hexdigest()
            ):
                raise CapacityMeasurementArtifactErrorV49F(
                    "Raw V7 bytes differ from integrity metadata"
                )
        manifest = decode_capacity_measurement_json_v49f_v7(
            artifacts[MANIFEST_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementManifestV49FV7,
        )
        verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7(
            manifest=manifest, expectation=expectation
        )
        samples = decode_capacity_measurement_samples_jsonl_v49f_v7(
            artifacts[SAMPLES_ARTIFACT_NAME_V49F], manifest=manifest
        )
        correctness = decode_capacity_measurement_json_v49f_v7(
            artifacts[CORRECTNESS_ARTIFACT_NAME_V49F],
            record_type=CapacityMeasurementCorrectnessV49FV7,
        )
        if members[SAMPLES_ARTIFACT_NAME_V49F].record_count != len(samples):
            raise CapacityMeasurementArtifactErrorV49F(
                "Raw V7 sample count differs from integrity metadata"
            )
        return cls(
            manifest=manifest,
            samples=samples,
            correctness=correctness,
            integrity=integrity,
        )

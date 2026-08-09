"""Observed-local manifest authority for V4.9F A2-M raw schema V6.

This module deliberately distinguishes an observation from an attestation.
The embedded collector can bind exact local source, runtime, and process facts
to the collector key authorized by the admitted deployment.  It cannot prove
that its own process is uncompromised and it is not SLSA provenance, a VSA,
verified boot, IMA, fs-verity, or remote host attestation.

The serialized records live inside ``manifest.json``.  Runtime-only retained
authority is represented by :class:`CollectedCapacityMeasurementCampaignV49F`
and is never serialized or exposed as a transport capability.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import re
import sqlite3
import ssl
import sys
import sysconfig
import threading
import time
import weakref
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, ClassVar, Final

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
    utc_iso,
)
from .ledger_signing import Ed25519CheckpointVerifier, ed25519_public_key_is_valid
from .physical_transport_actor_v49c import WebSocketParserCursorV49C
from .physical_transport_capacity_lifecycle_v49f import (
    CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
)
from .physical_transport_capacity_source_observation_v49f import (
    RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F,
    RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
)
from .physical_transport_owner_v4 import derive_linux_namespace_id
from .physical_transport_v4 import derive_transport_attestation_key_id

A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F: Final = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v6"
)
A2M_MANIFEST_REQUEST_DOMAIN_V49F: Final = "RiskYieldMMA2MManifestRequestV4_9F_RawV6"
A2M_RUNTIME_OBSERVATION_DOMAIN_V49F: Final = (
    "RiskYieldMMA2MRuntimeObservationV4_9F_RawV6"
)
A2M_PROCESS_ENVIRONMENT_OBSERVATION_DOMAIN_V49F: Final = (
    "RiskYieldMMA2MProcessEnvironmentObservationV4_9F_RawV6"
)
A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F: Final = (
    "RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV6"
)
A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F: Final = (
    "RiskYieldMMA2MManifestAuthorityAttestationV4_9F_RawV6"
)
A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F: Final = (
    "OBSERVED_LOCAL_SIGNED_DEPLOYMENT_BOUND_V49F_V6"
)
A2M_EXTERNAL_ATTESTATION_STATUS_V49F: Final = "NOT_EXTERNALLY_ATTESTED"
A2M_ENVIRONMENT_VALUE_PROFILE_V49F: Final = (
    "REVIEWED_NON_SECRET_VALUES_AND_AGGREGATE_SENSITIVE_VALUE_DIGEST_V2"
)
A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F: Final = "ED25519"
A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F: Final = 256

_MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F: Final = (
    "authority_profile",
    "external_attestation_status",
    "manifest_request_id",
    "source_observation_id",
    "runtime_observation_id",
    "environment_observation_id",
    "deployment_bundle_id",
    "deployment_trust_root_id",
    "collector_release_manifest_id",
    "runtime_environment_manifest_id",
    "transport_session_id",
    "driver_evidence_nonce_sha256",
    "kernel_socket_identity",
    "transport_capacity_policy_id",
    "started_at_utc",
    "monotonic_origin_nanoseconds",
    "boottime_origin_nanoseconds",
    "loop_time_origin_nanoseconds",
    "promotion_eligible",
)

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")
_MAX_ENVIRONMENT_VARIABLES = 4096
_MAX_ENVIRONMENT_CANONICAL_BYTES = 1 << 20
_MAX_UINT128_DECIMAL_DIGITS = 39
_SAFE_ENVIRONMENT_VALUES: Final = frozenset(
    {
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PYTHONHASHSEED",
        "PYTHONNOUSERSITE",
        "TZ",
    }
)
_LOADER_INJECTION_VARIABLES: Final = frozenset(
    {
        "LD_AUDIT",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "PYTHONPATH",
        "PYTHONSTARTUP",
    }
)

_MANIFEST_AUTHORITY_FORK_GUARDS: weakref.WeakSet[Any] = weakref.WeakSet()


def _invalidate_manifest_authorities_in_fork_child() -> None:
    for item in tuple(_MANIFEST_AUTHORITY_FORK_GUARDS):
        item._fork_invalid = True  # noqa: SLF001


os.register_at_fork(after_in_child=_invalidate_manifest_authorities_in_fork_child)


def _record_keys(record_type: type[Any]) -> set[str]:
    return {item.name for item in fields(record_type)}


def _strict_mapping(
    payload: Mapping[str, Any], *, expected: set[str], context: str
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CanonicalizationError(f"{context} must be a mapping")
    require_exact_keys(payload, expected=expected, context=context)
    return payload


def _exact_tuple_of_identifiers(
    value: Any, *, field: str, maximum_items: int = 4096
) -> tuple[str, ...]:
    if type(value) is not tuple or len(value) > maximum_items:
        raise CanonicalizationError(f"{field} must be a bounded exact tuple")
    result = tuple(
        canonical_identifier(item, field=field, maximum=4096) for item in value
    )
    return result


def _exact_tuple_of_pairs(
    value: Any, *, field: str, maximum_items: int = 4096
) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) > maximum_items:
        raise CanonicalizationError(f"{field} must be a bounded exact tuple")
    pairs: list[tuple[str, str]] = []
    for raw in value:
        if type(raw) is not tuple or len(raw) != 2:
            raise CanonicalizationError(f"{field} must contain exact pairs")
        pairs.append(
            (
                canonical_identifier(raw[0], field=f"{field}_name", maximum=4096),
                canonical_identifier(raw[1], field=f"{field}_value", maximum=16384),
            )
        )
    result = tuple(pairs)
    if result != tuple(sorted(result)) or len({item[0] for item in result}) != len(
        result
    ):
        raise CanonicalizationError(f"{field} must be uniquely name-sorted")
    return result


def _semantic_identity(*, domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F,
        }
    )


def _semantic_record(
    *,
    domain: str,
    payload: Mapping[str, Any],
    identity_field: str,
    identity: str,
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "record_domain": domain,
        "measurement_schema_version": A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F,
        **dict(payload),
        identity_field: identity,
    }


def _decode_semantic_record(
    payload: Mapping[str, Any],
    *,
    record_type: type[Any],
    domain: str,
    context: str,
) -> dict[str, Any]:
    item = _strict_mapping(
        payload,
        expected=_record_keys(record_type)
        | {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
        },
        context=context,
    )
    if item["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError(f"{context} canonicalization version differs")
    if item["measurement_schema_version"] != A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F:
        raise CanonicalizationError(f"{context} schema version differs")
    if item["record_domain"] != domain:
        raise CanonicalizationError(f"{context} record domain differs")
    return {name: item[name] for name in _record_keys(record_type)}


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementManifestRequestV49F:
    """The small governed campaign-plan input; never runtime provenance."""

    campaign_label: str
    phase: str
    measurement_design_id: str
    workload_corpus_sha256: str
    workload_ids: tuple[str, ...]
    workload_sha256s: tuple[str, ...]
    manifest_request_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "campaign_label",
            canonical_identifier(self.campaign_label, field="campaign_label"),
        )
        phase = canonical_identifier(self.phase, field="phase")
        if phase != "EXPLORATORY":
            raise CanonicalizationError("manifest request phase must be EXPLORATORY")
        object.__setattr__(self, "phase", phase)
        for name in ("measurement_design_id", "workload_corpus_sha256"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ids = _exact_tuple_of_identifiers(
            self.workload_ids,
            field="workload_ids",
            maximum_items=A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F,
        )
        if (
            type(self.workload_sha256s) is not tuple
            or len(self.workload_sha256s) > A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F
        ):
            raise CanonicalizationError(
                "workload_sha256s must be a bounded exact tuple"
            )
        hashes = tuple(
            canonical_hash(value, field="workload_sha256s")
            for value in self.workload_sha256s
        )
        if (
            not ids
            or len(ids) != len(hashes)
            or ids != tuple(sorted(ids))
            or len(set(ids)) != len(ids)
        ):
            raise CanonicalizationError(
                "manifest request workloads must be non-empty, aligned, unique, and sorted"
            )
        object.__setattr__(self, "workload_ids", ids)
        object.__setattr__(self, "workload_sha256s", hashes)
        identity = _semantic_identity(
            domain=A2M_MANIFEST_REQUEST_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.manifest_request_id is not None
            and self.manifest_request_id != identity
        ):
            raise CanonicalizationError(
                "manifest_request_id differs from canonical campaign request"
            )
        object.__setattr__(self, "manifest_request_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "campaign_label": self.campaign_label,
            "measurement_design_id": self.measurement_design_id,
            "phase": self.phase,
            "workload_corpus_sha256": self.workload_corpus_sha256,
            "workload_ids": list(self.workload_ids),
            "workload_sha256s": list(self.workload_sha256s),
        }

    def as_dict(self) -> dict[str, Any]:
        return _semantic_record(
            domain=A2M_MANIFEST_REQUEST_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="manifest_request_id",
            identity=self.manifest_request_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementManifestRequestV49F:
        item = _decode_semantic_record(
            payload,
            record_type=cls,
            domain=A2M_MANIFEST_REQUEST_DOMAIN_V49F,
            context="measurement manifest request",
        )
        raw_ids = item["workload_ids"]
        raw_hashes = item["workload_sha256s"]
        if type(raw_ids) is not list or type(raw_hashes) is not list:
            raise CanonicalizationError(
                "manifest request workloads must be JSON arrays"
            )
        return cls(
            **{
                **item,
                "workload_ids": tuple(raw_ids),
                "workload_sha256s": tuple(raw_hashes),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementRuntimeObservationV49F:
    """Exact deployment/runtime identities returned by the runtime authority."""

    authority_profile: str
    transport_runtime_schema_version: str
    deployment_bundle_id: str
    deployment_sequence: int
    deployment_trust_root_id: str
    environment_id: str
    collector_release_manifest_id: str
    collector_key_authorization_manifest_id: str
    collector_attestation_key_id: str
    collector_release_name: str
    collector_release_version: str
    collector_release_entrypoint: str
    declared_source_tree_sha256: str
    declared_build_artifact_sha256: str
    runtime_environment_manifest_id: str
    tls_websocket_driver_policy_id: str
    retained_runtime_observation_sha256: str
    transport_capacity_policy_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    monotonic_clock_domain_id: str
    clock_source_manifest_id: str
    chronyd_launch_id: str | None
    chronyd_runtime_observation_sha256: str | None
    runtime_observation_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "authority_profile",
            "transport_runtime_schema_version",
            "environment_id",
            "collector_release_name",
            "collector_release_version",
            "collector_release_entrypoint",
            "kernel_boot_id",
        ):
            object.__setattr__(
                self,
                name,
                canonical_identifier(getattr(self, name), field=name, maximum=4096),
            )
        for name in (
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "collector_key_authorization_manifest_id",
            "collector_attestation_key_id",
            "declared_source_tree_sha256",
            "declared_build_artifact_sha256",
            "runtime_environment_manifest_id",
            "tls_websocket_driver_policy_id",
            "retained_runtime_observation_sha256",
            "transport_capacity_policy_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "time_namespace_id",
            "network_namespace_id",
            "monotonic_clock_domain_id",
            "clock_source_manifest_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "deployment_sequence",
            canonical_safe_int(
                self.deployment_sequence, field="deployment_sequence", minimum=1
            ),
        )
        launch = (self.chronyd_launch_id, self.chronyd_runtime_observation_sha256)
        if (launch[0] is None) != (launch[1] is None):
            raise CanonicalizationError(
                "chronyd launch and observation identities must be paired"
            )
        if launch[0] is not None:
            object.__setattr__(
                self,
                "chronyd_launch_id",
                canonical_hash(launch[0], field="chronyd_launch_id"),
            )
            object.__setattr__(
                self,
                "chronyd_runtime_observation_sha256",
                canonical_hash(launch[1], field="chronyd_runtime_observation_sha256"),
            )
        identity = _semantic_identity(
            domain=A2M_RUNTIME_OBSERVATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.runtime_observation_id is not None
            and self.runtime_observation_id != identity
        ):
            raise CanonicalizationError(
                "runtime_observation_id differs from canonical observation"
            )
        object.__setattr__(self, "runtime_observation_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"runtime_observation_id"}
        }

    @property
    def runtime_identity_sha256(self) -> str:
        return self.runtime_observation_id

    def as_dict(self) -> dict[str, Any]:
        return _semantic_record(
            domain=A2M_RUNTIME_OBSERVATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="runtime_observation_id",
            identity=self.runtime_observation_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementRuntimeObservationV49F:
        return cls(
            **_decode_semantic_record(
                payload,
                record_type=cls,
                domain=A2M_RUNTIME_OBSERVATION_DOMAIN_V49F,
                context="measurement runtime observation",
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementProcessEnvironmentObservationV49F:
    """Bounded behavior-relevant facts observed from the current process."""

    observation_profile: str
    captured_at_utc: str
    capture_started_monotonic_nanoseconds: str
    capture_completed_monotonic_nanoseconds: str
    kernel_release: str
    kernel_version: str
    machine_architecture: str
    cpu_model: str
    logical_cpu_count: int
    cpu_affinity: tuple[int, ...]
    python_implementation: str
    python_version: str
    python_full_version: str
    python_cache_tag: str
    python_abi_flags: str
    python_executable_path: str
    python_executable_sha256: str
    platform_tag: str
    sys_flags: tuple[tuple[str, str], ...]
    sys_path_sha256: str
    meta_path_profile_sha256: str
    event_loop_implementation: str
    event_loop_policy_implementation: str
    openssl_version: str
    websockets_version: str
    sqlite_version: str
    filesystem_type: str
    filesystem_mount_identity_sha256: str
    database_path: str
    database_device: int
    database_inode: int
    storage_identity_sha256: str
    sqlite_pragmas: tuple[tuple[str, str], ...]
    sqlite_pragmas_sha256: str
    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    mount_namespace_id: str
    pid_namespace_id: str
    cgroup_namespace_id: str
    cgroup_membership_sha256: str
    environment_value_profile: str
    safe_environment_values: tuple[tuple[str, str], ...]
    sensitive_environment_presence: tuple[str, ...]
    sensitive_environment_values_sha256: str
    environment_sha256: str
    loader_injection_present: bool
    environment_observation_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "observation_profile",
            "kernel_release",
            "kernel_version",
            "machine_architecture",
            "cpu_model",
            "python_implementation",
            "python_version",
            "python_full_version",
            "python_cache_tag",
            "python_abi_flags",
            "python_executable_path",
            "platform_tag",
            "event_loop_implementation",
            "event_loop_policy_implementation",
            "openssl_version",
            "websockets_version",
            "sqlite_version",
            "filesystem_type",
            "database_path",
            "kernel_boot_id",
            "environment_value_profile",
        ):
            object.__setattr__(
                self,
                name,
                canonical_identifier(getattr(self, name), field=name, maximum=16384),
            )
        object.__setattr__(
            self,
            "captured_at_utc",
            utc_iso(self.captured_at_utc, field="captured_at_utc"),
        )
        for name in (
            "capture_started_monotonic_nanoseconds",
            "capture_completed_monotonic_nanoseconds",
        ):
            value = getattr(self, name)
            if (
                type(value) is not str
                or len(value) > _MAX_UINT128_DECIMAL_DIGITS
                or not value.isascii()
                or not value.isdecimal()
            ):
                raise CanonicalizationError(f"{name} must be unsigned integer text")
            if len(value) > 1 and value.startswith("0"):
                raise CanonicalizationError(f"{name} must be canonical")
        if int(self.capture_completed_monotonic_nanoseconds) < int(
            self.capture_started_monotonic_nanoseconds
        ):
            raise CanonicalizationError("environment capture bracket regresses")
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
        if affinity != tuple(sorted(set(affinity))):
            raise CanonicalizationError("cpu_affinity must be unique and sorted")
        object.__setattr__(self, "cpu_affinity", affinity)
        for name in ("database_device", "database_inode"):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=0),
            )
        for name in (
            "python_executable_sha256",
            "sys_path_sha256",
            "meta_path_profile_sha256",
            "filesystem_mount_identity_sha256",
            "storage_identity_sha256",
            "sqlite_pragmas_sha256",
            "time_namespace_id",
            "network_namespace_id",
            "mount_namespace_id",
            "pid_namespace_id",
            "cgroup_namespace_id",
            "cgroup_membership_sha256",
            "environment_sha256",
            "sensitive_environment_values_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self, "sys_flags", _exact_tuple_of_pairs(self.sys_flags, field="sys_flags")
        )
        pragmas = _exact_tuple_of_pairs(
            self.sqlite_pragmas, field="sqlite_pragmas", maximum_items=64
        )
        if self.sqlite_pragmas_sha256 != sha256_digest(
            {"domain": "RiskYieldMMA2MSqlitePragmasV4_9F", "pragmas": list(pragmas)}
        ):
            raise CanonicalizationError(
                "sqlite_pragmas_sha256 differs from observed pragma mapping"
            )
        object.__setattr__(self, "sqlite_pragmas", pragmas)
        safe_values = _exact_tuple_of_pairs(
            self.safe_environment_values,
            field="safe_environment_values",
            maximum_items=_MAX_ENVIRONMENT_VARIABLES,
        )
        sensitive = _exact_tuple_of_identifiers(
            self.sensitive_environment_presence,
            field="sensitive_environment_presence",
            maximum_items=_MAX_ENVIRONMENT_VARIABLES,
        )
        if sensitive != tuple(sorted(set(sensitive))):
            raise CanonicalizationError(
                "sensitive environment names must be unique and sorted"
            )
        object.__setattr__(self, "safe_environment_values", safe_values)
        object.__setattr__(self, "sensitive_environment_presence", sensitive)
        if type(self.loader_injection_present) is not bool:
            raise CanonicalizationError("loader_injection_present must be boolean")
        expected_environment_sha256 = sha256_digest(
            {
                "domain": "RiskYieldMMA2MProcessEnvironmentVariablesV4_9F",
                "profile": self.environment_value_profile,
                "safe_values": list(safe_values),
                "sensitive_presence": list(sensitive),
                "sensitive_values_sha256": (self.sensitive_environment_values_sha256),
            }
        )
        if self.environment_sha256 != expected_environment_sha256:
            raise CanonicalizationError(
                "environment_sha256 differs from safe values and sensitive presence"
            )
        identity = _semantic_identity(
            domain=A2M_PROCESS_ENVIRONMENT_OBSERVATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.environment_observation_id is not None
            and self.environment_observation_id != identity
        ):
            raise CanonicalizationError(
                "environment_observation_id differs from canonical observation"
            )
        object.__setattr__(self, "environment_observation_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in _record_keys(type(self)) - {"environment_observation_id"}:
            value = getattr(self, name)
            payload[name] = (
                [list(item) for item in value]
                if name
                in {
                    "sys_flags",
                    "sqlite_pragmas",
                    "safe_environment_values",
                }
                else list(value)
                if name
                in {
                    "cpu_affinity",
                    "sensitive_environment_presence",
                }
                else value
            )
        return payload

    def as_dict(self) -> dict[str, Any]:
        return _semantic_record(
            domain=A2M_PROCESS_ENVIRONMENT_OBSERVATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="environment_observation_id",
            identity=self.environment_observation_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementProcessEnvironmentObservationV49F:
        item = _decode_semantic_record(
            payload,
            record_type=cls,
            domain=A2M_PROCESS_ENVIRONMENT_OBSERVATION_DOMAIN_V49F,
            context="measurement process environment observation",
        )
        for name in (
            "cpu_affinity",
            "sensitive_environment_presence",
        ):
            if type(item[name]) is not list:
                raise CanonicalizationError(f"{name} must be a JSON array")
            item[name] = tuple(item[name])
        for name in ("sys_flags", "sqlite_pragmas", "safe_environment_values"):
            if type(item[name]) is not list or any(
                type(pair) is not list or len(pair) != 2 for pair in item[name]
            ):
                raise CanonicalizationError(f"{name} must be an array of pairs")
            item[name] = tuple(tuple(pair) for pair in item[name])
        return cls(**item)


def capacity_measurement_authority_subject_signing_payload_v49f(
    *,
    authority_subject_id: str,
    deployment_bundle_id: str,
    collector_attestation_key_id: str,
    transport_session_id: str,
) -> dict[str, Any]:
    """Return the sole payload the runtime collector key may sign for this gate."""

    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F,
        "payload": {
            "authority_subject_id": canonical_hash(
                authority_subject_id, field="authority_subject_id"
            ),
            "collector_attestation_key_id": canonical_hash(
                collector_attestation_key_id,
                field="collector_attestation_key_id",
            ),
            "deployment_bundle_id": canonical_hash(
                deployment_bundle_id, field="deployment_bundle_id"
            ),
            "transport_session_id": canonical_hash(
                transport_session_id, field="transport_session_id"
            ),
        },
        "schema_version": A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F,
    }


def derive_capacity_measurement_manifest_authority_subject_id_v49f(
    subject_payload: Mapping[str, Any],
) -> str:
    """Validate and identify the complete unsigned local-authority subject."""

    item = _strict_mapping(
        subject_payload,
        expected=set(_MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F),
        context="measurement manifest authority subject",
    )
    normalized = dict(item)
    if normalized["authority_profile"] != A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F:
        raise CanonicalizationError("manifest authority profile is unsupported")
    if normalized["external_attestation_status"] != (
        A2M_EXTERNAL_ATTESTATION_STATUS_V49F
    ):
        raise CanonicalizationError("manifest authority external status is unsupported")
    for name in (
        "manifest_request_id",
        "source_observation_id",
        "runtime_observation_id",
        "environment_observation_id",
        "deployment_bundle_id",
        "deployment_trust_root_id",
        "collector_release_manifest_id",
        "runtime_environment_manifest_id",
        "transport_session_id",
        "driver_evidence_nonce_sha256",
        "kernel_socket_identity",
        "transport_capacity_policy_id",
    ):
        if normalized[name] != canonical_hash(normalized[name], field=name):
            raise CanonicalizationError(f"{name} is not canonical")
    if normalized["started_at_utc"] != utc_iso(
        normalized["started_at_utc"], field="started_at_utc"
    ):
        raise CanonicalizationError("started_at_utc is not canonical")
    for name in (
        "monotonic_origin_nanoseconds",
        "boottime_origin_nanoseconds",
        "loop_time_origin_nanoseconds",
    ):
        value = normalized[name]
        if (
            type(value) is not str
            or len(value) > _MAX_UINT128_DECIMAL_DIGITS
            or not value.isascii()
            or not value.isdecimal()
        ):
            raise CanonicalizationError(f"{name} must be canonical unsigned text")
        if len(value) > 1 and value.startswith("0"):
            raise CanonicalizationError(f"{name} must not contain leading zeroes")
    if (
        type(normalized["promotion_eligible"]) is not bool
        or normalized["promotion_eligible"]
    ):
        raise CanonicalizationError(
            "observed-local authority must not be promotion eligible"
        )
    return _semantic_identity(
        domain=A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F,
        payload=normalized,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementManifestAuthorityV49F:
    """Signed observed-local subject; not an external build/host attestation."""

    authority_profile: str
    external_attestation_status: str
    manifest_request_id: str
    source_observation_id: str
    runtime_observation_id: str
    environment_observation_id: str
    deployment_bundle_id: str
    deployment_trust_root_id: str
    collector_release_manifest_id: str
    runtime_environment_manifest_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    started_at_utc: str
    monotonic_origin_nanoseconds: str
    boottime_origin_nanoseconds: str
    loop_time_origin_nanoseconds: str
    promotion_eligible: bool
    authority_subject_id: str | None
    signature_algorithm: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    signature_hex: str
    manifest_authority_id: str | None = None

    _SUBJECT_FIELDS: ClassVar[tuple[str, ...]] = _MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F

    def __post_init__(self) -> None:
        profile = canonical_identifier(
            self.authority_profile, field="authority_profile"
        )
        if profile != A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F:
            raise CanonicalizationError("manifest authority profile is unsupported")
        object.__setattr__(self, "authority_profile", profile)
        external = canonical_identifier(
            self.external_attestation_status, field="external_attestation_status"
        )
        if external != A2M_EXTERNAL_ATTESTATION_STATUS_V49F:
            raise CanonicalizationError(
                "local manifest authority cannot claim external attestation"
            )
        object.__setattr__(self, "external_attestation_status", external)
        for name in (
            "manifest_request_id",
            "source_observation_id",
            "runtime_observation_id",
            "environment_observation_id",
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "runtime_environment_manifest_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self, "started_at_utc", utc_iso(self.started_at_utc, field="started_at_utc")
        )
        for name in (
            "monotonic_origin_nanoseconds",
            "boottime_origin_nanoseconds",
            "loop_time_origin_nanoseconds",
        ):
            value = getattr(self, name)
            if (
                type(value) is not str
                or len(value) > _MAX_UINT128_DECIMAL_DIGITS
                or not value.isascii()
                or not value.isdecimal()
            ):
                raise CanonicalizationError(f"{name} must be unsigned integer text")
            if len(value) > 1 and value.startswith("0"):
                raise CanonicalizationError(f"{name} must be canonical")
        if type(self.promotion_eligible) is not bool or self.promotion_eligible:
            raise CanonicalizationError(
                "observed-local exploratory authority must not be promotion eligible"
            )
        subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f(
            self._subject_payload_unchecked()
        )
        if (
            self.authority_subject_id is not None
            and self.authority_subject_id != subject_id
        ):
            raise CanonicalizationError(
                "authority_subject_id differs from the exact observed subject"
            )
        object.__setattr__(self, "authority_subject_id", subject_id)
        algorithm = canonical_identifier(
            self.signature_algorithm, field="signature_algorithm"
        )
        if algorithm != A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F:
            raise CanonicalizationError("manifest authority signature is unsupported")
        object.__setattr__(self, "signature_algorithm", algorithm)
        key_id = canonical_hash(
            self.collector_attestation_key_id,
            field="collector_attestation_key_id",
        )
        if type(
            self.collector_attestation_public_key_hex
        ) is not str or not re.fullmatch(
            r"[0-9a-f]{64}", self.collector_attestation_public_key_hex
        ):
            raise CanonicalizationError(
                "collector attestation public key must be lowercase hex"
            )
        public_key = bytes.fromhex(self.collector_attestation_public_key_hex)
        if (
            not ed25519_public_key_is_valid(public_key)
            or derive_transport_attestation_key_id(public_key) != key_id
        ):
            raise CanonicalizationError(
                "collector attestation key differs from its public key"
            )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        if (
            type(self.signature_hex) is not str
            or _SIGNATURE_RE.fullmatch(self.signature_hex) is None
        ):
            raise CanonicalizationError("manifest authority signature is malformed")
        signing_payload = capacity_measurement_authority_subject_signing_payload_v49f(
            authority_subject_id=subject_id,
            deployment_bundle_id=self.deployment_bundle_id,
            collector_attestation_key_id=key_id,
            transport_session_id=self.transport_session_id,
        )
        try:
            Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
                canonical_json_bytes(signing_payload), bytes.fromhex(self.signature_hex)
            )
        except Exception as exc:
            raise CanonicalizationError(
                "manifest authority signature is invalid"
            ) from exc
        authority_id = _semantic_identity(
            domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.manifest_authority_id is not None
            and self.manifest_authority_id != authority_id
        ):
            raise CanonicalizationError(
                "manifest_authority_id differs from the signed authority record"
            )
        object.__setattr__(self, "manifest_authority_id", authority_id)

    def _subject_payload_unchecked(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._SUBJECT_FIELDS}

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            **self._subject_payload_unchecked(),
            "authority_subject_id": self.authority_subject_id,
            "collector_attestation_key_id": self.collector_attestation_key_id,
            "collector_attestation_public_key_hex": (
                self.collector_attestation_public_key_hex
            ),
            "signature_algorithm": self.signature_algorithm,
            "signature_hex": self.signature_hex,
        }

    def as_dict(self) -> dict[str, Any]:
        return _semantic_record(
            domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F,
            payload=self._identity_payload_unchecked(),
            identity_field="manifest_authority_id",
            identity=self.manifest_authority_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementManifestAuthorityV49F:
        return cls(
            **_decode_semantic_record(
                payload,
                record_type=cls,
                domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F,
                context="measurement manifest authority",
            )
        )


class CapacityMeasurementManifestSigningAuthorizationV49F:
    """One-shot retained authorization for the runtime collector signer."""

    _TOKEN = object()
    _MAX_COLLECTION_NANOSECONDS = 120_000_000_000
    _MAX_MONOTONIC_LOOP_DISAGREEMENT_NANOSECONDS = 1_000_000_000

    def __init__(
        self,
        *,
        _token: object,
        subject_payload: Mapping[str, Any],
        collection_started_snapshot: Any,
        runtime_snapshot: Any,
        sqlite_environment_observation: Any,
        source_authority: Any,
        runtime_observation: CapacityMeasurementRuntimeObservationV49F,
        process_environment_observation: (
            CapacityMeasurementProcessEnvironmentObservationV49F
        ),
    ) -> None:
        if (
            _token is not self._TOKEN
            or type(self) is not CapacityMeasurementManifestSigningAuthorizationV49F
        ):
            raise TypeError("signing authorization is collector-owned")
        from .physical_projection_v4 import (
            PhysicalProjectionSqliteEnvironmentObservationV49F,
        )
        from .physical_transport_capacity_source_observation_v49f import (
            PinnedSourceObservationV49F,
        )
        from .physical_transport_runtime_v4 import (
            PhysicalTransportManifestAuthoritySnapshotV49F,
        )

        if (
            type(collection_started_snapshot)
            is not PhysicalTransportManifestAuthoritySnapshotV49F
            or type(runtime_snapshot)
            is not PhysicalTransportManifestAuthoritySnapshotV49F
            or type(sqlite_environment_observation)
            is not PhysicalProjectionSqliteEnvironmentObservationV49F
            or type(source_authority) is not PinnedSourceObservationV49F
            or type(runtime_observation)
            is not CapacityMeasurementRuntimeObservationV49F
            or type(process_environment_observation)
            is not CapacityMeasurementProcessEnvironmentObservationV49F
        ):
            raise TypeError("signing authorization inputs must be exact authorities")
        payload = dict(subject_payload)
        subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f(
            payload
        )
        source_authority.assert_current()
        if (
            collection_started_snapshot.authority_binding_payload()
            != runtime_snapshot.authority_binding_payload()
            or utc_iso(collection_started_snapshot.captured_at_utc)
            != payload["started_at_utc"]
            or source_authority.snapshot.source_observation_id
            != payload["source_observation_id"]
            or runtime_observation.runtime_observation_id
            != payload["runtime_observation_id"]
            or process_environment_observation.environment_observation_id
            != payload["environment_observation_id"]
            or runtime_observation.deployment_bundle_id
            != payload["deployment_bundle_id"]
            or runtime_observation.deployment_trust_root_id
            != payload["deployment_trust_root_id"]
            or runtime_observation.collector_release_manifest_id
            != payload["collector_release_manifest_id"]
            or runtime_observation.runtime_environment_manifest_id
            != payload["runtime_environment_manifest_id"]
            or runtime_observation.transport_session_id
            != payload["transport_session_id"]
            or runtime_observation.driver_evidence_nonce_sha256
            != payload["driver_evidence_nonce_sha256"]
            or runtime_observation.kernel_socket_identity
            != payload["kernel_socket_identity"]
            or runtime_observation.transport_capacity_policy_id
            != payload["transport_capacity_policy_id"]
            or capacity_measurement_runtime_observation_from_snapshot_v49f(
                runtime_snapshot
            )
            != runtime_observation
            or source_authority.snapshot.deployment_source_tree_sha256
            != runtime_observation.declared_source_tree_sha256
            or sqlite_environment_observation.database_path
            != process_environment_observation.database_path
            or sqlite_environment_observation.database_device
            != process_environment_observation.database_device
            or sqlite_environment_observation.database_inode
            != process_environment_observation.database_inode
            or tuple(sqlite_environment_observation.sqlite_pragmas)
            != process_environment_observation.sqlite_pragmas
        ):
            raise CanonicalizationError(
                "signing authorization is not one observed authority closure"
            )
        try:
            import asyncio

            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "signing authorization requires an active event loop"
            ) from exc
        self._subject_payload = payload
        self._authority_subject_id = subject_id
        self._runtime_snapshot = runtime_snapshot
        self._sqlite_environment_observation = sqlite_environment_observation
        self._source_authority = source_authority
        self._runtime_observation = runtime_observation
        self._process_environment_observation = process_environment_observation
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._creator_loop = loop
        self._consumed = False
        self._fork_invalid = False
        _MANIFEST_AUTHORITY_FORK_GUARDS.add(self)

    @classmethod
    def _create(
        cls,
        *,
        subject_payload: Mapping[str, Any],
        collection_started_snapshot: Any,
        runtime_snapshot: Any,
        sqlite_environment_observation: Any,
        source_authority: Any,
        runtime_observation: CapacityMeasurementRuntimeObservationV49F,
        process_environment_observation: (
            CapacityMeasurementProcessEnvironmentObservationV49F
        ),
    ) -> CapacityMeasurementManifestSigningAuthorizationV49F:
        return cls(
            _token=cls._TOKEN,
            subject_payload=subject_payload,
            collection_started_snapshot=collection_started_snapshot,
            runtime_snapshot=runtime_snapshot,
            sqlite_environment_observation=sqlite_environment_observation,
            source_authority=source_authority,
            runtime_observation=runtime_observation,
            process_environment_observation=process_environment_observation,
        )

    @property
    def authority_subject_id(self) -> str:
        return self._authority_subject_id

    def _assert_context(self) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "signing authorization left its event loop"
            ) from exc
        if (
            self._consumed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
            or loop is not self._creator_loop
        ):
            raise CanonicalizationError(
                "signing authorization is consumed or left its creation context"
            )

    def consume(self, *, runtime_snapshot: Any, sqlite_observation: Any) -> str:
        """Validate currentness once and return the sole authorized subject ID."""

        self._assert_context()
        self._source_authority.assert_current()
        if (
            type(runtime_snapshot) is not type(self._runtime_snapshot)
            or runtime_snapshot.authority_binding_payload()
            != self._runtime_snapshot.authority_binding_payload()
            or sqlite_observation != self._sqlite_environment_observation
            or capacity_measurement_runtime_observation_from_snapshot_v49f(
                runtime_snapshot
            )
            != self._runtime_observation
        ):
            raise CanonicalizationError(
                "signing authorization runtime or SQLite authority changed"
            )
        current_process = observe_capacity_measurement_process_environment_v49f(
            runtime_snapshot=runtime_snapshot,
            sqlite_environment_observation=sqlite_observation,
            event_loop=self._creator_loop,
        )
        stable_fields = _record_keys(
            CapacityMeasurementProcessEnvironmentObservationV49F
        ) - {
            "captured_at_utc",
            "capture_started_monotonic_nanoseconds",
            "capture_completed_monotonic_nanoseconds",
            "environment_observation_id",
        }
        if any(
            getattr(current_process, name)
            != getattr(self._process_environment_observation, name)
            for name in stable_fields
        ):
            raise CanonicalizationError(
                "signing authorization process environment changed"
            )
        now_monotonic = time.monotonic_ns()
        now_boottime = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        now_loop = int(self._creator_loop.time() * 1_000_000_000)
        origins = tuple(
            int(self._subject_payload[name])
            for name in (
                "monotonic_origin_nanoseconds",
                "boottime_origin_nanoseconds",
                "loop_time_origin_nanoseconds",
            )
        )
        elapsed = tuple(
            now - origin
            for now, origin in zip(
                (now_monotonic, now_boottime, now_loop), origins, strict=True
            )
        )
        if any(
            value < 0 or value > self._MAX_COLLECTION_NANOSECONDS for value in elapsed
        ) or abs(elapsed[0] - elapsed[2]) > (
            self._MAX_MONOTONIC_LOOP_DISAGREEMENT_NANOSECONDS
        ):
            raise CanonicalizationError(
                "signing authorization clock origins are stale or inconsistent"
            )
        self._consumed = True
        return self._authority_subject_id


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmittedCapacityMeasurementAuthorityExpectationV49F:
    """Independent trust expectations supplied by admitted deployment replay."""

    authority_profile: str
    transport_runtime_schema_version: str
    deployment_bundle_id: str
    deployment_sequence: int
    deployment_trust_root_id: str
    environment_id: str
    collector_release_manifest_id: str
    collector_key_authorization_manifest_id: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    runtime_environment_manifest_id: str
    collector_release_name: str
    collector_release_version: str
    collector_release_entrypoint: str
    release_source_tree_sha256: str
    release_build_artifact_sha256: str
    tls_websocket_driver_policy_id: str
    transport_capacity_policy_id: str
    clock_source_manifest_id: str

    def __post_init__(self) -> None:
        for name in (
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "collector_key_authorization_manifest_id",
            "collector_attestation_key_id",
            "runtime_environment_manifest_id",
            "release_source_tree_sha256",
            "release_build_artifact_sha256",
            "tls_websocket_driver_policy_id",
            "transport_capacity_policy_id",
            "clock_source_manifest_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "environment_id",
            canonical_identifier(self.environment_id, field="environment_id"),
        )
        for name in (
            "authority_profile",
            "transport_runtime_schema_version",
            "collector_release_name",
            "collector_release_version",
            "collector_release_entrypoint",
        ):
            object.__setattr__(
                self,
                name,
                canonical_identifier(getattr(self, name), field=name, maximum=4096),
            )
        if self.authority_profile not in {"LIVE_LINUX", "EXACT_TEST"}:
            raise CanonicalizationError("trusted authority profile is unsupported")
        object.__setattr__(
            self,
            "deployment_sequence",
            canonical_safe_int(
                self.deployment_sequence,
                field="deployment_sequence",
                minimum=1,
            ),
        )
        public_hex = self.collector_attestation_public_key_hex
        if (
            type(public_hex) is not str
            or re.fullmatch(r"[0-9a-f]{64}", public_hex) is None
        ):
            raise CanonicalizationError(
                "trusted collector public key must be 32-byte lowercase hex"
            )
        public_key = bytes.fromhex(public_hex)
        if (
            not ed25519_public_key_is_valid(public_key)
            or derive_transport_attestation_key_id(public_key)
            != self.collector_attestation_key_id
        ):
            raise CanonicalizationError(
                "trusted collector key ID differs from its public key"
            )

    @classmethod
    def from_verified_deployment(
        cls,
        *,
        capability: Any,
        collector_release: Any,
        authority_profile: str,
    ) -> AdmittedCapacityMeasurementAuthorityExpectationV49F:
        """Derive the static expectation from independently verified authorities."""

        from .operational_manifests_v4 import (
            CollectorReleaseManifestV4,
            VerifiedDeploymentCapabilityV4,
        )
        from .physical_transport_runtime_v4 import (
            PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION,
        )

        if type(capability) is not VerifiedDeploymentCapabilityV4:
            raise TypeError("capability must be an exact verified deployment")
        if type(collector_release) is not CollectorReleaseManifestV4:
            raise TypeError("collector_release must be an exact release manifest")
        if collector_release.manifest_id != capability.collector_release_manifest_id:
            raise CanonicalizationError(
                "collector release differs from the verified deployment"
            )
        return cls(
            authority_profile=authority_profile,
            transport_runtime_schema_version=(
                PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION
            ),
            deployment_bundle_id=capability.deployment_bundle_id,
            deployment_sequence=capability.deployment_sequence,
            deployment_trust_root_id=capability.deployment_trust_root_id,
            environment_id=capability.environment_id,
            collector_release_manifest_id=capability.collector_release_manifest_id,
            collector_key_authorization_manifest_id=(
                capability.collector_key_authorization_manifest_id
            ),
            collector_attestation_key_id=capability.collector_attestation_key_id,
            collector_attestation_public_key_hex=(
                capability.collector_attestation_public_key_hex
            ),
            runtime_environment_manifest_id=(
                capability.runtime_environment_manifest_id
            ),
            collector_release_name=collector_release.release_name,
            collector_release_version=collector_release.release_version,
            collector_release_entrypoint=collector_release.entrypoint,
            release_source_tree_sha256=collector_release.source_tree_sha256,
            release_build_artifact_sha256=collector_release.build_artifact_sha256,
            tls_websocket_driver_policy_id=(
                capability.require_tls_websocket_driver_policy_id_v49b()
            ),
            transport_capacity_policy_id=(
                capability.require_transport_capacity_policy_id_v49f()
            ),
            clock_source_manifest_id=capability.clock_source_manifest_id,
        )


def verify_capacity_measurement_manifest_against_admitted_authority_v49f(
    *,
    manifest: Any,
    expectation: AdmittedCapacityMeasurementAuthorityExpectationV49F,
) -> None:
    """Authenticate Raw V6 against an independently admitted deployment view."""

    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementManifestV49F,
    )

    if type(manifest) is not CapacityMeasurementManifestV49F:
        raise TypeError("manifest must be an exact Raw V6 manifest")
    if type(expectation) is not AdmittedCapacityMeasurementAuthorityExpectationV49F:
        raise TypeError("expectation must be exact admitted authority")
    reconstructed = CapacityMeasurementManifestV49F.from_mapping(
        strict_json_loads(canonical_json_bytes(manifest.as_dict()))
    )
    if reconstructed != manifest:
        raise CanonicalizationError("manifest differs from exact Raw V6 replay")
    runtime = manifest.runtime_observation
    authority = manifest.manifest_authority
    expected = (
        expectation.authority_profile,
        expectation.transport_runtime_schema_version,
        expectation.deployment_bundle_id,
        expectation.deployment_sequence,
        expectation.deployment_trust_root_id,
        expectation.environment_id,
        expectation.collector_release_manifest_id,
        expectation.collector_key_authorization_manifest_id,
        expectation.collector_attestation_key_id,
        expectation.collector_attestation_public_key_hex,
        expectation.runtime_environment_manifest_id,
        expectation.collector_release_name,
        expectation.collector_release_version,
        expectation.collector_release_entrypoint,
        expectation.release_source_tree_sha256,
        expectation.release_build_artifact_sha256,
        expectation.tls_websocket_driver_policy_id,
        expectation.transport_capacity_policy_id,
        expectation.clock_source_manifest_id,
    )
    actual = (
        runtime.authority_profile,
        runtime.transport_runtime_schema_version,
        runtime.deployment_bundle_id,
        runtime.deployment_sequence,
        runtime.deployment_trust_root_id,
        runtime.environment_id,
        runtime.collector_release_manifest_id,
        runtime.collector_key_authorization_manifest_id,
        authority.collector_attestation_key_id,
        authority.collector_attestation_public_key_hex,
        runtime.runtime_environment_manifest_id,
        runtime.collector_release_name,
        runtime.collector_release_version,
        runtime.collector_release_entrypoint,
        runtime.declared_source_tree_sha256,
        runtime.declared_build_artifact_sha256,
        runtime.tls_websocket_driver_policy_id,
        runtime.transport_capacity_policy_id,
        runtime.clock_source_manifest_id,
    )
    if actual != expected:
        raise CanonicalizationError(
            "manifest authority differs from independently admitted deployment"
        )


def _namespace_identity(kind: str) -> str:
    path = Path("/proc/self/ns") / kind
    try:
        link = os.readlink(path)
        observed = path.stat()
    except OSError as exc:
        raise CanonicalizationError(f"{kind} namespace is unavailable") from exc
    if kind in {"time", "net"}:
        return derive_linux_namespace_id(
            namespace_kind=kind,
            stat_device_u64=observed.st_dev,
            stat_inode_u64=observed.st_ino,
        )
    return sha256_digest(
        {
            "device": observed.st_dev,
            "domain": "RiskYieldMMLinuxNamespaceIdentityV4_9F",
            "inode": observed.st_ino,
            "kind": kind,
            "link": link,
        }
    )


def _bounded_proc_bytes(path: str, *, maximum: int = 1 << 20) -> bytes:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError as exc:
        raise CanonicalizationError(
            f"required process file is unavailable: {path}"
        ) from exc
    try:
        os.set_inheritable(descriptor, False)
        data = bytearray()
        offset = 0
        while len(data) <= maximum:
            chunk = os.pread(descriptor, min(65536, maximum + 1 - len(data)), offset)
            if not chunk:
                break
            data.extend(chunk)
            offset += len(chunk)
        if len(data) > maximum:
            raise CanonicalizationError(f"required process file exceeds bound: {path}")
        return bytes(data)
    finally:
        os.close(descriptor)


def _cpu_model() -> str:
    raw = _bounded_proc_bytes("/proc/cpuinfo", maximum=4 << 20)
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("/proc/cpuinfo is not UTF-8") from exc
    values = {
        line.split(":", 1)[1].strip()
        for line in lines
        if ":" in line
        and line.split(":", 1)[0].strip() in {"model name", "Hardware", "Processor"}
        and line.split(":", 1)[1].strip()
    }
    if not values:
        raise CanonicalizationError("CPU model is unavailable")
    return " | ".join(sorted(values))


def _mountinfo_for_path(path: Path) -> tuple[str, str]:
    raw = _bounded_proc_bytes("/proc/self/mountinfo", maximum=4 << 20)
    try:
        lines = raw.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("mountinfo is not UTF-8") from exc

    def unescape(value: str) -> str:
        for encoded, decoded in (
            ("\\040", " "),
            ("\\011", "\t"),
            ("\\012", "\n"),
            ("\\134", "\\"),
        ):
            value = value.replace(encoded, decoded)
        return value

    target = str(path)
    candidates: list[tuple[int, list[str], list[str]]] = []
    for line in lines:
        left, separator, right = line.partition(" - ")
        if not separator:
            raise CanonicalizationError("mountinfo row is malformed")
        left_fields = left.split(" ")
        right_fields = right.split(" ")
        if len(left_fields) < 6 or len(right_fields) < 3:
            raise CanonicalizationError("mountinfo row is truncated")
        mount_point = unescape(left_fields[4])
        if target == mount_point or target.startswith(mount_point.rstrip("/") + "/"):
            candidates.append((len(mount_point), left_fields, right_fields))
    if not candidates:
        raise CanonicalizationError("database mount is absent from mountinfo")
    _, left, right = max(candidates, key=lambda item: item[0])
    fs_type = canonical_identifier(right[0], field="filesystem_type", maximum=256)
    identity = sha256_digest(
        {
            "device": left[2],
            "domain": "RiskYieldMMA2MFilesystemMountIdentityV4_9F",
            "filesystem_type": fs_type,
            "mount_id": left[0],
            "mount_options": left[5],
            "mount_point": left[4],
            "mount_root": left[3],
            "source": right[1],
            "super_options": right[2],
        }
    )
    return fs_type, identity


def _executable_stat_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _hash_executable_descriptor(
    descriptor: int, *, maximum: int = 1 << 30
) -> tuple[str, tuple[int, ...]]:
    os.set_inheritable(descriptor, False)
    before = os.fstat(descriptor)
    if before.st_size < 0 or before.st_size > maximum:
        raise CanonicalizationError("executable is outside its byte bound")
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(descriptor, min(131072, before.st_size - offset), offset)
        if not chunk:
            raise CanonicalizationError("executable was truncated while hashing")
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    identity = _executable_stat_identity(before)
    if identity != _executable_stat_identity(after):
        raise CanonicalizationError("executable changed while hashing")
    return digest.hexdigest(), identity


def _hash_file(path: str, *, maximum: int = 1 << 30) -> str:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        digest, _ = _hash_executable_descriptor(descriptor, maximum=maximum)
        return digest
    finally:
        os.close(descriptor)


def _process_executable() -> tuple[str, str]:
    try:
        process_descriptor = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        raise CanonicalizationError("/proc/self/exe cannot be retained") from exc
    try:
        try:
            target = os.readlink("/proc/self/exe")
        except OSError as exc:
            raise CanonicalizationError("/proc/self/exe is unavailable") from exc
        if target.endswith(" (deleted)"):
            raise CanonicalizationError("running interpreter executable is deleted")
        actual = os.path.realpath(target)
        declared = os.path.realpath(sys.executable)
        if actual != declared:
            raise CanonicalizationError(
                "sys.executable differs from the running process executable"
            )
        process_digest, process_identity = _hash_executable_descriptor(
            process_descriptor
        )
        try:
            path_descriptor = os.open(
                actual,
                os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            )
        except OSError as exc:
            raise CanonicalizationError(
                "running interpreter pathname cannot be retained"
            ) from exc
        try:
            path_digest, path_identity = _hash_executable_descriptor(path_descriptor)
        finally:
            os.close(path_descriptor)
        if process_identity != path_identity or process_digest != path_digest:
            raise CanonicalizationError(
                "running interpreter differs from the executable pathname"
            )
        if os.readlink("/proc/self/exe") != target:
            raise CanonicalizationError(
                "running interpreter pathname changed during observation"
            )
        return actual, process_digest
    finally:
        os.close(process_descriptor)


def _sys_flags() -> tuple[tuple[str, str], ...]:
    names = tuple(
        name
        for name in dir(sys.flags)
        if not name.startswith("_") and type(getattr(sys.flags, name)) in {int, bool}
    )
    return tuple(sorted((name, str(int(getattr(sys.flags, name)))) for name in names))


def _environment_observation() -> tuple[
    tuple[tuple[str, str], ...], tuple[str, ...], str, str, bool
]:
    if len(os.environ) > _MAX_ENVIRONMENT_VARIABLES:
        raise CanonicalizationError("process environment has too many variables")
    safe = tuple(
        sorted(
            (name, os.environ[name])
            for name in _SAFE_ENVIRONMENT_VALUES
            if name in os.environ
        )
    )
    sensitive_pairs = tuple(
        sorted(
            (name, os.environ[name])
            for name in os.environ
            if name not in _SAFE_ENVIRONMENT_VALUES
        )
    )
    sensitive = tuple(name for name, _ in sensitive_pairs)
    sensitive_payload = canonical_json_bytes(
        {
            "domain": "RiskYieldMMA2MSensitiveEnvironmentValuesV4_9F",
            "pairs": [list(item) for item in sensitive_pairs],
        }
    )
    if len(sensitive_payload) > _MAX_ENVIRONMENT_CANONICAL_BYTES:
        raise CanonicalizationError("process environment observation exceeds its bound")
    sensitive_values_sha256 = hashlib.sha256(sensitive_payload).hexdigest()
    encoded = canonical_json_bytes(
        {
            "domain": "RiskYieldMMA2MProcessEnvironmentVariablesV4_9F",
            "profile": A2M_ENVIRONMENT_VALUE_PROFILE_V49F,
            "safe_values": [list(item) for item in safe],
            "sensitive_presence": list(sensitive),
            "sensitive_values_sha256": sensitive_values_sha256,
        }
    )
    if len(encoded) > _MAX_ENVIRONMENT_CANONICAL_BYTES:
        raise CanonicalizationError("process environment observation exceeds its bound")
    return (
        safe,
        sensitive,
        sensitive_values_sha256,
        sha256_digest(
            {
                "domain": "RiskYieldMMA2MProcessEnvironmentVariablesV4_9F",
                "profile": A2M_ENVIRONMENT_VALUE_PROFILE_V49F,
                "safe_values": [list(item) for item in safe],
                "sensitive_presence": list(sensitive),
                "sensitive_values_sha256": sensitive_values_sha256,
            }
        ),
        any(name in os.environ for name in _LOADER_INJECTION_VARIABLES),
    )


def observe_capacity_measurement_process_environment_v49f(
    *,
    runtime_snapshot: Any,
    sqlite_environment_observation: Any,
    event_loop: Any,
) -> CapacityMeasurementProcessEnvironmentObservationV49F:
    """Collect process facts and owner-derived SQLite facts without fallbacks.

    ``runtime_snapshot`` is intentionally validated by exact field projection
    instead of structural authority.  The caller must still bind the resulting
    record to the sealed runtime context before sampling.
    """

    started = time.monotonic_ns()
    uname = os.uname()
    affinity = tuple(sorted(os.sched_getaffinity(0)))
    logical = os.cpu_count()
    if logical is None or not affinity or any(value >= logical for value in affinity):
        raise CanonicalizationError("CPU topology or affinity is inconsistent")
    executable_path, executable_sha = _process_executable()
    database_path = Path(sqlite_environment_observation.database_path)
    if not database_path.is_absolute():
        raise CanonicalizationError("runtime database path is not absolute")
    resolved_database = database_path.resolve(strict=True)
    database_stat = resolved_database.stat()
    if (database_stat.st_dev, database_stat.st_ino) != (
        sqlite_environment_observation.database_device,
        sqlite_environment_observation.database_inode,
    ):
        raise CanonicalizationError("database path differs from runtime-owned identity")
    filesystem_type, mount_identity = _mountinfo_for_path(resolved_database)
    pragmas = tuple(sqlite_environment_observation.sqlite_pragmas)
    pragma_hash = sha256_digest(
        {"domain": "RiskYieldMMA2MSqlitePragmasV4_9F", "pragmas": list(pragmas)}
    )
    (
        safe_env,
        sensitive_env,
        sensitive_values_sha256,
        environment_sha,
        injection,
    ) = _environment_observation()
    cgroup_bytes = _bounded_proc_bytes("/proc/self/cgroup")
    try:
        boot_id = (
            _bounded_proc_bytes("/proc/sys/kernel/random/boot_id", maximum=256)
            .decode("ascii", errors="strict")
            .strip()
        )
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("kernel boot ID is not ASCII") from exc
    if boot_id != runtime_snapshot.kernel_boot_id:
        raise CanonicalizationError("kernel boot ID differs from runtime authority")
    time_namespace = _namespace_identity("time")
    network_namespace = _namespace_identity("net")
    if (
        time_namespace != runtime_snapshot.time_namespace_id
        or network_namespace != runtime_snapshot.network_namespace_id
    ):
        raise CanonicalizationError("process namespaces differ from runtime authority")
    loop_type = type(event_loop)
    loop_identity = f"{loop_type.__module__}.{loop_type.__qualname__}"
    policy = asyncio_event_loop_policy_type()
    completed = time.monotonic_ns()
    captured_at = runtime_snapshot.captured_at_utc
    sys_path_hash = sha256_digest(
        {"domain": "RiskYieldMMA2MSysPathV4_9F", "ordered_paths": list(sys.path)}
    )
    meta_path_hash = sha256_digest(
        {
            "domain": "RiskYieldMMA2MMetaPathV4_9F",
            "ordered_types": [
                f"{type(item).__module__}.{type(item).__qualname__}"
                for item in sys.meta_path
            ],
        }
    )
    python_cache_tag = sys.implementation.cache_tag
    if type(python_cache_tag) is not str or not python_cache_tag:
        raise CanonicalizationError("Python cache tag is unavailable")
    try:
        websockets_version = importlib.metadata.version("websockets")
    except importlib.metadata.PackageNotFoundError as exc:
        raise CanonicalizationError("websockets distribution is unavailable") from exc
    storage_identity = sha256_digest(
        {
            "device": database_stat.st_dev,
            "domain": "RiskYieldMMA2MProjectionStorageIdentityV4_9F",
            "inode": database_stat.st_ino,
            "resolved_path": str(resolved_database),
        }
    )
    return CapacityMeasurementProcessEnvironmentObservationV49F(
        observation_profile="LINUX_PROCESS_AND_OWNER_SQLITE_OBSERVED_LOCAL_V49F_V6",
        captured_at_utc=captured_at,
        capture_started_monotonic_nanoseconds=str(started),
        capture_completed_monotonic_nanoseconds=str(completed),
        kernel_release=uname.release,
        kernel_version=uname.version,
        machine_architecture=uname.machine,
        cpu_model=_cpu_model(),
        logical_cpu_count=logical,
        cpu_affinity=affinity,
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        python_full_version=sys.version,
        python_cache_tag=python_cache_tag,
        python_abi_flags=getattr(sys, "abiflags", "") or "NONE",
        python_executable_path=executable_path,
        python_executable_sha256=executable_sha,
        platform_tag=sysconfig.get_platform(),
        sys_flags=_sys_flags(),
        sys_path_sha256=sys_path_hash,
        meta_path_profile_sha256=meta_path_hash,
        event_loop_implementation=loop_identity,
        event_loop_policy_implementation=policy,
        openssl_version=ssl.OPENSSL_VERSION,
        websockets_version=websockets_version,
        sqlite_version=sqlite3.sqlite_version,
        filesystem_type=filesystem_type,
        filesystem_mount_identity_sha256=mount_identity,
        database_path=str(resolved_database),
        database_device=database_stat.st_dev,
        database_inode=database_stat.st_ino,
        storage_identity_sha256=storage_identity,
        sqlite_pragmas=pragmas,
        sqlite_pragmas_sha256=pragma_hash,
        kernel_boot_id=boot_id,
        time_namespace_id=time_namespace,
        network_namespace_id=network_namespace,
        mount_namespace_id=_namespace_identity("mnt"),
        pid_namespace_id=_namespace_identity("pid"),
        cgroup_namespace_id=_namespace_identity("cgroup"),
        cgroup_membership_sha256=hashlib.sha256(cgroup_bytes).hexdigest(),
        environment_value_profile=A2M_ENVIRONMENT_VALUE_PROFILE_V49F,
        safe_environment_values=safe_env,
        sensitive_environment_presence=sensitive_env,
        sensitive_environment_values_sha256=sensitive_values_sha256,
        environment_sha256=environment_sha,
        loader_injection_present=injection,
    )


def asyncio_event_loop_policy_type() -> str:
    """Return the active event-loop policy type without accepting a declaration."""

    import asyncio

    policy = asyncio.get_event_loop_policy()
    return f"{type(policy).__module__}.{type(policy).__qualname__}"


class CollectedCapacityMeasurementCampaignV49F:
    """Sealed local observation context retained for one exploratory campaign."""

    _TOKEN = object()

    def __init__(
        self,
        *,
        _token: object,
        manifest: Any,
        runtime: Any,
        source_authority: Any,
        runtime_snapshot: Any,
        sqlite_environment_observation: Any,
        runtime_observation: CapacityMeasurementRuntimeObservationV49F,
        environment_observation: CapacityMeasurementProcessEnvironmentObservationV49F,
    ) -> None:
        if (
            _token is not self._TOKEN
            or type(self) is not CollectedCapacityMeasurementCampaignV49F
        ):
            raise TypeError("collected campaigns must be created by the V6 collector")
        self._manifest = manifest
        self._runtime = runtime
        self._source_authority = source_authority
        self._runtime_snapshot = runtime_snapshot
        self._sqlite_environment_observation = sqlite_environment_observation
        self._runtime_observation = runtime_observation
        self._environment_observation = environment_observation
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._closed = False
        self._fork_invalid = False
        try:
            import asyncio

            self._creator_loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "collected campaign requires the active sampling event loop"
            ) from exc
        _MANIFEST_AUTHORITY_FORK_GUARDS.add(self)

    @classmethod
    def _create(
        cls,
        *,
        manifest: Any,
        runtime: Any,
        source_authority: Any,
        runtime_snapshot: Any,
        sqlite_environment_observation: Any,
        runtime_observation: CapacityMeasurementRuntimeObservationV49F,
        environment_observation: CapacityMeasurementProcessEnvironmentObservationV49F,
    ) -> CollectedCapacityMeasurementCampaignV49F:
        from .physical_projection_v4 import (
            PhysicalProjectionSqliteEnvironmentObservationV49F,
        )
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementManifestV49F,
        )
        from .physical_transport_capacity_source_observation_v49f import (
            PinnedSourceObservationV49F,
        )
        from .physical_transport_runtime_v4 import (
            PhysicalTransportManifestAuthoritySnapshotV49F,
            PhysicalTransportRuntimeV4,
        )

        if (
            type(manifest) is not CapacityMeasurementManifestV49F
            or type(runtime) is not PhysicalTransportRuntimeV4
            or type(source_authority) is not PinnedSourceObservationV49F
            or type(runtime_snapshot)
            is not PhysicalTransportManifestAuthoritySnapshotV49F
            or type(sqlite_environment_observation)
            is not PhysicalProjectionSqliteEnvironmentObservationV49F
            or type(runtime_observation)
            is not CapacityMeasurementRuntimeObservationV49F
            or type(environment_observation)
            is not CapacityMeasurementProcessEnvironmentObservationV49F
        ):
            raise TypeError("collected campaign inputs must be exact authorities")
        if (
            source_authority.snapshot != manifest.source_observation
            or runtime_observation != manifest.runtime_observation
            or environment_observation != manifest.process_environment_observation
            or capacity_measurement_runtime_observation_from_snapshot_v49f(
                runtime_snapshot
            )
            != runtime_observation
            or runtime_snapshot.release_source_tree_sha256
            != source_authority.snapshot.deployment_source_tree_sha256
            or runtime_snapshot.collector_attestation_key_id
            != manifest.manifest_authority.collector_attestation_key_id
            or sqlite_environment_observation.database_path
            != environment_observation.database_path
            or sqlite_environment_observation.database_device
            != environment_observation.database_device
            or sqlite_environment_observation.database_inode
            != environment_observation.database_inode
            or tuple(sqlite_environment_observation.sqlite_pragmas)
            != environment_observation.sqlite_pragmas
        ):
            raise CanonicalizationError(
                "collected campaign inputs are not one exact authority closure"
            )
        result = cls(
            _token=cls._TOKEN,
            manifest=manifest,
            runtime=runtime,
            source_authority=source_authority,
            runtime_snapshot=runtime_snapshot,
            sqlite_environment_observation=sqlite_environment_observation,
            runtime_observation=runtime_observation,
            environment_observation=environment_observation,
        )
        result.assert_local_current()
        return result

    @property
    def manifest(self) -> Any:
        self._assert_context()
        return self._manifest

    @property
    def runtime(self) -> Any:
        self._assert_context()
        return self._runtime

    @property
    def manifest_authority_id(self) -> str:
        self._assert_context()
        return self._manifest.manifest_authority.manifest_authority_id

    def _assert_context(self) -> None:
        try:
            import asyncio

            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "collected campaign left its event loop"
            ) from exc
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
            or loop is not self._creator_loop
        ):
            raise CanonicalizationError(
                "collected campaign left its creating process/thread/event loop"
            )

    def assert_local_current(self) -> None:
        """Check retained local capabilities without awaiting runtime orchestration."""

        self._assert_context()
        try:
            reconstructed = type(self._manifest).from_mapping(
                strict_json_loads(canonical_json_bytes(self._manifest.as_dict()))
            )
        except (AttributeError, TypeError) as exc:
            raise CanonicalizationError(
                "collected campaign manifest is not reconstructable"
            ) from exc
        if (
            reconstructed != self._manifest
            or self._manifest.runtime_observation != self._runtime_observation
            or self._manifest.process_environment_observation
            != self._environment_observation
            or self._manifest.source_observation != self._source_authority.snapshot
        ):
            raise CanonicalizationError(
                "collected campaign manifest changed after collection"
            )
        self._source_authority.assert_current()
        current_environment = observe_capacity_measurement_process_environment_v49f(
            runtime_snapshot=self._runtime_snapshot,
            sqlite_environment_observation=self._sqlite_environment_observation,
            event_loop=self._creator_loop,
        )
        # Capture timestamps are evidence brackets, not stable environment identity.
        stable_fields = _record_keys(
            CapacityMeasurementProcessEnvironmentObservationV49F
        ) - {
            "captured_at_utc",
            "capture_started_monotonic_nanoseconds",
            "capture_completed_monotonic_nanoseconds",
            "environment_observation_id",
        }
        if any(
            getattr(current_environment, name)
            != getattr(self._environment_observation, name)
            for name in stable_fields
        ):
            raise CanonicalizationError(
                "process environment changed after manifest collection"
            )

    async def assert_current(self) -> None:
        """Recapture runtime/store authority and recheck retained local context."""

        self.assert_local_current()
        capture = getattr(self._runtime, "capture_manifest_authority_inputs_v49f", None)
        if not callable(capture):
            raise CanonicalizationError(
                "runtime no longer exposes authoritative manifest recapture"
            )
        snapshot, sqlite_observation = await capture()
        binding = getattr(snapshot, "authority_binding_payload", None)
        expected_binding = getattr(
            self._runtime_snapshot, "authority_binding_payload", None
        )
        if (
            not callable(binding)
            or not callable(expected_binding)
            or binding() != expected_binding()
            or sqlite_observation != self._sqlite_environment_observation
        ):
            raise CanonicalizationError(
                "runtime or SQLite authority changed after manifest collection"
            )
        current = capacity_measurement_runtime_observation_from_snapshot_v49f(snapshot)
        if current != self._runtime_observation:
            raise CanonicalizationError(
                "runtime authority changed after manifest collection"
            )
        current_environment = observe_capacity_measurement_process_environment_v49f(
            runtime_snapshot=snapshot,
            sqlite_environment_observation=sqlite_observation,
            event_loop=self._creator_loop,
        )
        stable_fields = _record_keys(
            CapacityMeasurementProcessEnvironmentObservationV49F
        ) - {
            "captured_at_utc",
            "capture_started_monotonic_nanoseconds",
            "capture_completed_monotonic_nanoseconds",
            "environment_observation_id",
        }
        if any(
            getattr(current_environment, name)
            != getattr(self._environment_observation, name)
            for name in stable_fields
        ):
            raise CanonicalizationError(
                "process environment changed after manifest collection"
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self._source_authority, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> CollectedCapacityMeasurementCampaignV49F:
        self.assert_local_current()
        return self

    async def __aenter__(self) -> CollectedCapacityMeasurementCampaignV49F:
        await self.assert_current()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aexit__(self, *_: object) -> None:
        self.close()


def capacity_measurement_runtime_observation_from_snapshot_v49f(
    snapshot: Any,
) -> CapacityMeasurementRuntimeObservationV49F:
    """Project only reviewed immutable fields from the runtime-owned snapshot."""

    return CapacityMeasurementRuntimeObservationV49F(
        authority_profile=snapshot.authority_profile,
        transport_runtime_schema_version=snapshot.transport_runtime_schema_version,
        deployment_bundle_id=snapshot.deployment_bundle_id,
        deployment_sequence=snapshot.deployment_sequence,
        deployment_trust_root_id=snapshot.deployment_trust_root_id,
        environment_id=snapshot.environment_id,
        collector_release_manifest_id=snapshot.collector_release_manifest_id,
        collector_key_authorization_manifest_id=(
            snapshot.collector_key_authorization_manifest_id
        ),
        collector_attestation_key_id=snapshot.collector_attestation_key_id,
        collector_release_name=snapshot.release_name,
        collector_release_version=snapshot.release_version,
        collector_release_entrypoint=snapshot.release_entrypoint,
        declared_source_tree_sha256=snapshot.release_source_tree_sha256,
        declared_build_artifact_sha256=snapshot.release_build_artifact_sha256,
        runtime_environment_manifest_id=snapshot.runtime_environment_manifest_id,
        tls_websocket_driver_policy_id=snapshot.tls_websocket_driver_policy_id,
        retained_runtime_observation_sha256=(
            snapshot.retained_driver_runtime_observation_sha256
        ),
        transport_capacity_policy_id=snapshot.transport_capacity_policy_id,
        transport_session_id=snapshot.transport_session_id,
        driver_evidence_nonce_sha256=snapshot.driver_evidence_nonce_sha256,
        kernel_socket_identity=snapshot.kernel_socket_identity,
        kernel_boot_id=snapshot.kernel_boot_id,
        time_namespace_id=snapshot.time_namespace_id,
        network_namespace_id=snapshot.network_namespace_id,
        monotonic_clock_domain_id=snapshot.monotonic_clock_domain_id,
        clock_source_manifest_id=snapshot.clock_source_manifest_id,
        chronyd_launch_id=snapshot.chronyd_launch_id,
        chronyd_runtime_observation_sha256=(
            snapshot.chronyd_runtime_observation_sha256
        ),
    )


def _capture_capacity_measurement_clock_origins_v49f(
    event_loop: Any,
) -> tuple[int, int, int]:
    """Capture distinct MONOTONIC, BOOTTIME, and event-loop origins."""

    monotonic_origin = time.monotonic_ns()
    boottime_origin = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    loop_origin = int(event_loop.time() * 1_000_000_000)
    if any(
        type(value) is not int or value < 0
        for value in (monotonic_origin, boottime_origin, loop_origin)
    ):
        raise CanonicalizationError(
            "campaign clock origins must be non-negative integers"
        )
    return monotonic_origin, boottime_origin, loop_origin


async def _collect_capacity_measurement_campaign_v49f(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
    required_authority_profile: str,
) -> CollectedCapacityMeasurementCampaignV49F:
    """Collect, sign, and retain one authoritative exploratory Raw-V6 campaign.

    Only the campaign plan is caller supplied.  Source, runtime, process,
    storage, clock-origin, deployment, session, and signature fields are
    observed through retained authorities and cannot be substituted here.
    """

    import asyncio

    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementCampaignPhaseV49F,
        CapacityMeasurementDesignV49F,
        CapacityMeasurementEnvironmentV49F,
        CapacityMeasurementManifestV49F,
        CapacityMeasurementWorkloadV49F,
        capacity_measurement_workload_corpus_sha256_v49f,
    )
    from .physical_transport_capacity_source_observation_v49f import (
        observe_current_source_v49f,
    )
    from .physical_transport_runtime_v4 import PhysicalTransportRuntimeV4

    if type(runtime) is not PhysicalTransportRuntimeV4:
        raise TypeError("runtime must be exact PhysicalTransportRuntimeV4")
    required_profile = canonical_identifier(
        required_authority_profile,
        field="required_authority_profile",
        maximum=32,
    )
    if required_profile not in {"LIVE_LINUX", "EXACT_TEST"}:
        raise CanonicalizationError("collector authority profile is unsupported")
    if runtime.is_live_profile != (required_profile == "LIVE_LINUX"):
        raise TypeError(
            f"collector requires an exact {required_profile} runtime profile"
        )
    if type(design) is not CapacityMeasurementDesignV49F:
        raise TypeError("design must be an exact capacity measurement design")
    if design.observer_clock != "CLOCK_MONOTONIC":
        raise CanonicalizationError(
            "the production sampler requires the CLOCK_MONOTONIC design"
        )
    if (
        type(workloads) is not tuple
        or not workloads
        or any(type(item) is not CapacityMeasurementWorkloadV49F for item in workloads)
    ):
        raise TypeError("workloads must be a non-empty exact workload tuple")
    workload_ids = tuple(item.workload_id for item in workloads)
    if workload_ids != tuple(sorted(set(workload_ids))):
        raise CanonicalizationError("workloads must be uniquely ID-sorted")

    loop = asyncio.get_running_loop()
    source_authority: Any | None = None
    try:
        monotonic_origin, boottime_origin, loop_origin = (
            _capture_capacity_measurement_clock_origins_v49f(loop)
        )
        (
            first_snapshot,
            first_sqlite,
        ) = await runtime.capture_manifest_authority_inputs_v49f()
        if first_snapshot.authority_profile != required_profile:
            raise CanonicalizationError(
                "runtime snapshot differs from the required collector profile"
            )
        started_at = utc_iso(first_snapshot.captured_at_utc)

        source_authority = observe_current_source_v49f(
            repository_root=repository_root,
            deployment_source_tree_sha256=(first_snapshot.release_source_tree_sha256),
        )
        source = source_authority.snapshot
        if not source.deployment_source_tree_matches:
            raise CanonicalizationError(
                "observed source differs from the signed deployment release"
            )

        (
            runtime_snapshot,
            sqlite_observation,
        ) = await runtime.capture_manifest_authority_inputs_v49f()
        if (
            runtime_snapshot.authority_binding_payload()
            != first_snapshot.authority_binding_payload()
            or sqlite_observation != first_sqlite
        ):
            raise CanonicalizationError(
                "runtime or SQLite authority changed during manifest collection"
            )
        runtime_observation = (
            capacity_measurement_runtime_observation_from_snapshot_v49f(
                runtime_snapshot
            )
        )
        process_observation = observe_capacity_measurement_process_environment_v49f(
            runtime_snapshot=runtime_snapshot,
            sqlite_environment_observation=sqlite_observation,
            event_loop=loop,
        )
        source_authority.assert_current()

        corpus_sha256 = capacity_measurement_workload_corpus_sha256_v49f(workloads)
        request = CapacityMeasurementManifestRequestV49F(
            campaign_label=campaign_label,
            phase=CapacityMeasurementCampaignPhaseV49F.EXPLORATORY.value,
            measurement_design_id=design.measurement_design_id,
            workload_corpus_sha256=corpus_sha256,
            workload_ids=workload_ids,
            workload_sha256s=tuple(item.workload_sha256 for item in workloads),
        )
        subject_payload = {
            "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F,
            "external_attestation_status": A2M_EXTERNAL_ATTESTATION_STATUS_V49F,
            "manifest_request_id": request.manifest_request_id,
            "source_observation_id": source.source_observation_id,
            "runtime_observation_id": runtime_observation.runtime_observation_id,
            "environment_observation_id": (
                process_observation.environment_observation_id
            ),
            "deployment_bundle_id": runtime_observation.deployment_bundle_id,
            "deployment_trust_root_id": (runtime_observation.deployment_trust_root_id),
            "collector_release_manifest_id": (
                runtime_observation.collector_release_manifest_id
            ),
            "runtime_environment_manifest_id": (
                runtime_observation.runtime_environment_manifest_id
            ),
            "transport_session_id": runtime_observation.transport_session_id,
            "driver_evidence_nonce_sha256": (
                runtime_observation.driver_evidence_nonce_sha256
            ),
            "kernel_socket_identity": runtime_observation.kernel_socket_identity,
            "transport_capacity_policy_id": (
                runtime_observation.transport_capacity_policy_id
            ),
            "started_at_utc": started_at,
            "monotonic_origin_nanoseconds": str(monotonic_origin),
            "boottime_origin_nanoseconds": str(boottime_origin),
            "loop_time_origin_nanoseconds": str(loop_origin),
            "promotion_eligible": False,
        }
        authority_subject_id = (
            derive_capacity_measurement_manifest_authority_subject_id_v49f(
                subject_payload
            )
        )
        signing_authorization = (
            CapacityMeasurementManifestSigningAuthorizationV49F._create(
                subject_payload=subject_payload,
                collection_started_snapshot=first_snapshot,
                runtime_snapshot=runtime_snapshot,
                sqlite_environment_observation=sqlite_observation,
                source_authority=source_authority,
                runtime_observation=runtime_observation,
                process_environment_observation=process_observation,
            )
        )
        signature = await runtime.sign_manifest_authority_subject_v49f(
            authorization=signing_authorization,
        )
        if (
            signature.authority_subject_id != authority_subject_id
            or signature.deployment_bundle_id
            != runtime_observation.deployment_bundle_id
            or signature.collector_attestation_key_id
            != runtime_observation.collector_attestation_key_id
            or signature.transport_session_id
            != runtime_observation.transport_session_id
        ):
            raise CanonicalizationError(
                "runtime signature differs from the observed authority subject"
            )
        authority = CapacityMeasurementManifestAuthorityV49F(
            **subject_payload,
            authority_subject_id=authority_subject_id,
            signature_algorithm=A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F,
            collector_attestation_key_id=(signature.collector_attestation_key_id),
            collector_attestation_public_key_hex=(
                signature.collector_attestation_public_key_hex
            ),
            signature_hex=signature.signature_hex,
        )
        environment = CapacityMeasurementEnvironmentV49F(
            kernel_release=process_observation.kernel_release,
            machine_architecture=process_observation.machine_architecture,
            cpu_model=process_observation.cpu_model,
            logical_cpu_count=process_observation.logical_cpu_count,
            cpu_affinity=process_observation.cpu_affinity,
            python_version=process_observation.python_version,
            event_loop_implementation=(process_observation.event_loop_implementation),
            openssl_version=process_observation.openssl_version,
            websockets_version=process_observation.websockets_version,
            sqlite_version=process_observation.sqlite_version,
            filesystem_type=process_observation.filesystem_type,
            storage_identity_sha256=(process_observation.storage_identity_sha256),
            sqlite_pragmas_sha256=process_observation.sqlite_pragmas_sha256,
        )
        manifest = CapacityMeasurementManifestV49F(
            campaign_label=request.campaign_label,
            phase=CapacityMeasurementCampaignPhaseV49F.EXPLORATORY,
            started_at_utc=started_at,
            source_revision=source.git_state.head_commit,
            source_identity_sha256=source.source_tree_sha256,
            source_tree_clean=source.git_state.source_tree_clean,
            runtime_identity_sha256=runtime_observation.runtime_observation_id,
            workload_corpus_sha256=corpus_sha256,
            transport_capacity_policy_id=(
                runtime_observation.transport_capacity_policy_id
            ),
            transport_runtime_version=(
                runtime_observation.transport_runtime_schema_version
            ),
            transport_session_id=runtime_observation.transport_session_id,
            driver_evidence_nonce_sha256=(
                runtime_observation.driver_evidence_nonce_sha256
            ),
            kernel_socket_identity=runtime_observation.kernel_socket_identity,
            monotonic_origin_nanoseconds=str(monotonic_origin),
            boottime_origin_nanoseconds=str(boottime_origin),
            loop_time_origin_nanoseconds=str(loop_origin),
            workloads=workloads,
            environment=environment,
            design=design,
            manifest_request=request,
            source_observation=source,
            runtime_observation=runtime_observation,
            process_environment_observation=process_observation,
            manifest_authority=authority,
        )
        campaign = CollectedCapacityMeasurementCampaignV49F._create(
            manifest=manifest,
            runtime=runtime,
            source_authority=source_authority,
            runtime_snapshot=runtime_snapshot,
            sqlite_environment_observation=sqlite_observation,
            runtime_observation=runtime_observation,
            environment_observation=process_observation,
        )
        await campaign.assert_current()
        source_authority = None
        return campaign
    except BaseException:
        if source_authority is not None:
            source_authority.close()
        raise


async def collect_capacity_measurement_campaign_v49f(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
) -> CollectedCapacityMeasurementCampaignV49F:
    """Collect one live-Linux campaign; test runtimes are rejected."""

    return await _collect_capacity_measurement_campaign_v49f(
        runtime=runtime,
        repository_root=repository_root,
        campaign_label=campaign_label,
        workloads=workloads,
        design=design,
        required_authority_profile="LIVE_LINUX",
    )


async def _collect_capacity_measurement_campaign_for_test_v49f(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
) -> CollectedCapacityMeasurementCampaignV49F:
    """Exercise the exact collector with the explicit non-live test profile."""

    return await _collect_capacity_measurement_campaign_v49f(
        runtime=runtime,
        repository_root=repository_root,
        campaign_label=campaign_label,
        workloads=workloads,
        design=design,
        required_authority_profile="EXACT_TEST",
    )


# Raw V7 is a separate evidence and signature domain.  Historical V6 bytes are
# never reinterpreted or upgraded: the V7 collector embeds one newly collected
# current V6 predecessor and adds a separately signed lifecycle authority.
A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7: Final = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v7"
)
A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F_V7: Final = (
    "RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV7"
)
A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F_V7: Final = (
    "RiskYieldMMA2MManifestAuthorityAttestationV4_9F_RawV7"
)
A2M_SOURCE_INVENTORY_DOMAIN_V49F_V7: Final = "RiskYieldMMA2MSourceInventoryV4_9F_RawV7"
A2M_LIFECYCLE_CONTRACT_DOMAIN_V49F_V7: Final = (
    "RiskYieldMMA2MLifecycleContractV4_9F_RawV7"
)
A2M_PROJECTION_AUTHORITY_DOMAIN_V49F_V7: Final = (
    "RiskYieldMMA2MProjectionAuthorityV4_9F_RawV7"
)
A2M_ACTOR_BASELINE_DOMAIN_V49F_V7: Final = "RiskYieldMMA2MActorBaselineV4_9F_RawV7"
A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7: Final = (
    "DURABLE_PRE_EFFECT_ATTEMPT_EXACTLY_ONE_TERMINAL_V1"
)
A2M_FAILED_PREFIX_PROFILE_V49F_V7: Final = "EXACT_ACTOR_DELTA_WITH_RAW_DEPENDENCIES_V1"
A2M_CANCELLATION_PROFILE_V49F_V7: Final = "PROPAGATE_AFTER_SYNCHRONOUS_TERMINAL_V1"
A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7: Final = "RECONCILE_BEFORE_NEXT_RUNTIME_COMMAND_V1"
A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F_V7: Final = "ED25519"
A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7: Final = (
    "OBSERVED_LOCAL_SIGNED_DEPLOYMENT_BOUND_V49F_V7"
)
A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7: Final = "NOT_EXTERNALLY_ATTESTED"
# Kept local to avoid the projection -> measurement -> authority import cycle.
# The outer manifest still compares these exact strings with the retained
# projection authority supplied by the caller.
A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7: Final = (
    "riskyieldmm_physical_projection_v4_9f_raw_v7"
)
A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7: Final = (
    "riskyieldmm_physical_projection_validation_v4_9f_raw_v7"
)
_A2M_RUNTIME_STATE_VALUES_V49F_V7: Final = frozenset(
    {
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
)


def _semantic_identity_v49f_v7(*, domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7,
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
        "record_domain": domain,
        "measurement_schema_version": (A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7),
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
    item = _strict_mapping(
        payload,
        expected=_record_keys(record_type)
        | {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
        },
        context=context,
    )
    if item["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError(f"{context} canonicalization version differs")
    if (
        item["measurement_schema_version"]
        != A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7
    ):
        raise CanonicalizationError(f"{context} Raw V7 schema version differs")
    if item["record_domain"] != domain:
        raise CanonicalizationError(f"{context} Raw V7 record domain differs")
    return {name: item[name] for name in _record_keys(record_type)}


def _replay_exact_v49f_v7(record: Any, *, record_type: type[Any], field: str) -> None:
    if type(record) is not record_type:
        raise CanonicalizationError(f"{field} must be exact")
    replay = record_type.from_mapping(record.as_dict())
    if replay != record:
        raise CanonicalizationError(f"{field} differs from exact replay")


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementSourceInventoryV49FV7:
    """Versioned module-name closure; it is not a source-byte attestation."""

    predecessor_source_inventory_id: str
    module_names: tuple[str, ...]
    source_inventory_id: str
    source_inventory_record_id: str | None = None

    def __post_init__(self) -> None:
        predecessor = canonical_hash(
            self.predecessor_source_inventory_id,
            field="predecessor_source_inventory_id",
        )
        if predecessor != RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F:
            raise CanonicalizationError(
                "Raw V7 source inventory does not extend the frozen Raw V6 inventory"
            )
        modules = _exact_tuple_of_identifiers(
            self.module_names,
            field="module_names",
            maximum_items=len(RAW_V7_CRITICAL_SOURCE_MODULES_V49F),
        )
        if (
            modules != RAW_V7_CRITICAL_SOURCE_MODULES_V49F
            or len(modules) != 41
            or tuple(
                name
                for name in modules
                if name not in RAW_V6_ACCEPTED_CRITICAL_SOURCE_MODULES_V49F
            )
            != ("riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f",)
        ):
            raise CanonicalizationError(
                "Raw V7 source inventory must be the exact frozen 41-module closure"
            )
        inventory_id = canonical_hash(
            self.source_inventory_id, field="source_inventory_id"
        )
        if inventory_id != RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F:
            raise CanonicalizationError("Raw V7 source inventory ID differs")
        object.__setattr__(self, "predecessor_source_inventory_id", predecessor)
        object.__setattr__(self, "module_names", modules)
        object.__setattr__(self, "source_inventory_id", inventory_id)
        identity = _semantic_identity_v49f_v7(
            domain=A2M_SOURCE_INVENTORY_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.source_inventory_record_id is not None
            and canonical_hash(
                self.source_inventory_record_id,
                field="source_inventory_record_id",
            )
            != identity
        ):
            raise CanonicalizationError(
                "source_inventory_record_id differs from canonical members"
            )
        object.__setattr__(self, "source_inventory_record_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "module_names": list(self.module_names),
            "predecessor_source_inventory_id": (self.predecessor_source_inventory_id),
            "source_inventory_id": self.source_inventory_id,
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            predecessor_source_inventory_id=self.predecessor_source_inventory_id,
            module_names=self.module_names,
            source_inventory_id=self.source_inventory_id,
            source_inventory_record_id=self.source_inventory_record_id,
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 source inventory was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_SOURCE_INVENTORY_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="source_inventory_record_id",
            identity=self.source_inventory_record_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementSourceInventoryV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_SOURCE_INVENTORY_DOMAIN_V49F_V7,
            context="Raw V7 source inventory",
        )
        if type(item["module_names"]) is not list:
            raise CanonicalizationError("Raw V7 module_names must be a JSON array")
        return cls(**{**item, "module_names": tuple(item["module_names"])})


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementLifecycleContractV49FV7:
    lifecycle_schema_id: str
    operation_lifecycle_profile: str
    failed_prefix_profile: str
    cancellation_profile: str
    orphan_recovery_profile: str
    fatal_operation_exceptions: tuple[tuple[str, str], ...]
    lifecycle_contract_id: str | None = None

    def __post_init__(self) -> None:
        schema = canonical_identifier(
            self.lifecycle_schema_id, field="lifecycle_schema_id", maximum=256
        )
        if schema != CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F:
            raise CanonicalizationError("Raw V7 lifecycle schema differs")
        expected_profiles = {
            "operation_lifecycle_profile": (A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7),
            "failed_prefix_profile": A2M_FAILED_PREFIX_PROFILE_V49F_V7,
            "cancellation_profile": A2M_CANCELLATION_PROFILE_V49F_V7,
            "orphan_recovery_profile": A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
        }
        for name, expected in expected_profiles.items():
            value = canonical_identifier(getattr(self, name), field=name, maximum=256)
            if value != expected:
                raise CanonicalizationError(f"Raw V7 {name} differs")
            object.__setattr__(self, name, value)
        if type(self.fatal_operation_exceptions) is not tuple:
            raise CanonicalizationError(
                "fatal_operation_exceptions must be an exact tuple"
            )
        fatal_pairs: list[tuple[str, str]] = []
        for value in self.fatal_operation_exceptions:
            if type(value) is not tuple or len(value) != 2:
                raise CanonicalizationError(
                    "fatal_operation_exceptions must contain exact pairs"
                )
            fatal_pairs.append(
                (
                    canonical_identifier(
                        value[0], field="fatal_operation_error_code", maximum=128
                    ),
                    canonical_identifier(
                        value[1], field="fatal_operation_exception_class", maximum=256
                    ),
                )
            )
        failures = tuple(fatal_pairs)
        if failures != tuple(sorted(set(failures))):
            raise CanonicalizationError(
                "fatal_operation_exceptions must be sorted and unique"
            )
        object.__setattr__(self, "lifecycle_schema_id", schema)
        object.__setattr__(self, "fatal_operation_exceptions", failures)
        identity = _semantic_identity_v49f_v7(
            domain=A2M_LIFECYCLE_CONTRACT_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.lifecycle_contract_id is not None
            and canonical_hash(
                self.lifecycle_contract_id, field="lifecycle_contract_id"
            )
            != identity
        ):
            raise CanonicalizationError(
                "lifecycle_contract_id differs from canonical members"
            )
        object.__setattr__(self, "lifecycle_contract_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            "cancellation_profile": self.cancellation_profile,
            "failed_prefix_profile": self.failed_prefix_profile,
            "fatal_operation_exceptions": [
                list(item) for item in self.fatal_operation_exceptions
            ],
            "lifecycle_schema_id": self.lifecycle_schema_id,
            "operation_lifecycle_profile": self.operation_lifecycle_profile,
            "orphan_recovery_profile": self.orphan_recovery_profile,
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            lifecycle_schema_id=self.lifecycle_schema_id,
            operation_lifecycle_profile=self.operation_lifecycle_profile,
            failed_prefix_profile=self.failed_prefix_profile,
            cancellation_profile=self.cancellation_profile,
            orphan_recovery_profile=self.orphan_recovery_profile,
            fatal_operation_exceptions=self.fatal_operation_exceptions,
            lifecycle_contract_id=self.lifecycle_contract_id,
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 lifecycle contract was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_LIFECYCLE_CONTRACT_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="lifecycle_contract_id",
            identity=self.lifecycle_contract_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementLifecycleContractV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_LIFECYCLE_CONTRACT_DOMAIN_V49F_V7,
            context="Raw V7 lifecycle contract",
        )
        if type(item["fatal_operation_exceptions"]) is not list or any(
            type(value) is not list or len(value) != 2
            for value in item["fatal_operation_exceptions"]
        ):
            raise CanonicalizationError(
                "fatal_operation_exceptions must be a JSON array of pairs"
            )
        return cls(
            **{
                **item,
                "fatal_operation_exceptions": tuple(
                    tuple(value) for value in item["fatal_operation_exceptions"]
                ),
            }
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementProjectionAuthorityV49FV7:
    projection_ledger_id: str
    projection_schema_version: str
    projection_validation_version: str
    projection_schema_fingerprint: str
    baseline_receipt_sequence: int
    baseline_receipt_hash: str
    projection_authority_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "projection_ledger_id",
            "projection_schema_fingerprint",
            "baseline_receipt_hash",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name, expected in (
            (
                "projection_schema_version",
                A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7,
            ),
            (
                "projection_validation_version",
                A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7,
            ),
        ):
            value = canonical_identifier(getattr(self, name), field=name, maximum=256)
            if value != expected:
                raise CanonicalizationError(f"Raw V7 {name} differs")
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "baseline_receipt_sequence",
            canonical_safe_int(
                self.baseline_receipt_sequence,
                field="baseline_receipt_sequence",
                minimum=0,
            ),
        )
        if (self.baseline_receipt_sequence == 0) != (
            self.baseline_receipt_hash == "0" * 64
        ):
            raise CanonicalizationError(
                "projection baseline sequence and genesis hash are inconsistent"
            )
        identity = _semantic_identity_v49f_v7(
            domain=A2M_PROJECTION_AUTHORITY_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.projection_authority_id is not None
            and canonical_hash(
                self.projection_authority_id, field="projection_authority_id"
            )
            != identity
        ):
            raise CanonicalizationError(
                "projection_authority_id differs from canonical members"
            )
        object.__setattr__(self, "projection_authority_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"projection_authority_id"}
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 projection authority was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_PROJECTION_AUTHORITY_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="projection_authority_id",
            identity=self.projection_authority_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementProjectionAuthorityV49FV7:
        return cls(
            **_decode_semantic_record_v49f_v7(
                payload,
                record_type=cls,
                domain=A2M_PROJECTION_AUTHORITY_DOMAIN_V49F_V7,
                context="Raw V7 projection authority",
            )
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementActorBaselineV49FV7:
    transport_subscription_policy_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    monotonic_clock_domain_id: str
    driver_policy_id: str
    raw_ingress_sequence: int
    raw_ingress_commit_id: str | None
    actor_event_count: int
    actor_tail_event_id: str | None
    parser_cursor: WebSocketParserCursorV49C
    parser_cursor_id: str
    runtime_state: str
    projection_receipt_sequence: int
    projection_receipt_hash: str
    actor_baseline_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "monotonic_clock_domain_id",
            "driver_policy_id",
            "projection_receipt_hash",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in (
            "raw_ingress_sequence",
            "actor_event_count",
            "projection_receipt_sequence",
            "connection_generation",
            "writer_fence_generation",
        ):
            minimum = (
                1 if name in {"connection_generation", "writer_fence_generation"} else 0
            )
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=minimum),
            )
        for name in ("raw_ingress_commit_id", "actor_tail_event_id"):
            value = getattr(self, name)
            if value is not None:
                value = canonical_hash(value, field=name)
            object.__setattr__(self, name, value)
        if (self.raw_ingress_sequence == 0) != (self.raw_ingress_commit_id is None):
            raise CanonicalizationError("Raw V7 RAW baseline is inconsistent")
        if (self.actor_event_count == 0) != (self.actor_tail_event_id is None):
            raise CanonicalizationError("Raw V7 actor baseline is inconsistent")
        if (self.projection_receipt_sequence == 0) != (
            self.projection_receipt_hash == "0" * 64
        ):
            raise CanonicalizationError(
                "Raw V7 projection baseline sequence and hash are inconsistent"
            )
        if type(self.parser_cursor) is not WebSocketParserCursorV49C:
            raise CanonicalizationError(
                "Raw V7 parser baseline must be an exact WebSocket cursor"
            )
        object.__setattr__(
            self,
            "parser_cursor_id",
            canonical_hash(self.parser_cursor_id, field="parser_cursor_id"),
        )
        if self.parser_cursor_id != self.parser_cursor.parser_cursor_id:
            raise CanonicalizationError(
                "Raw V7 parser cursor ID differs from its exact cursor state"
            )
        object.__setattr__(
            self,
            "runtime_state",
            canonical_identifier(self.runtime_state, field="runtime_state", maximum=64),
        )
        if self.runtime_state not in _A2M_RUNTIME_STATE_VALUES_V49F_V7:
            raise CanonicalizationError("Raw V7 actor runtime state is unsupported")
        identity = _semantic_identity_v49f_v7(
            domain=A2M_ACTOR_BASELINE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.actor_baseline_id is not None
            and canonical_hash(self.actor_baseline_id, field="actor_baseline_id")
            != identity
        ):
            raise CanonicalizationError(
                "actor_baseline_id differs from canonical members"
            )
        object.__setattr__(self, "actor_baseline_id", identity)

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name)
            for name in _record_keys(type(self)) - {"actor_baseline_id"}
        }
        result["parser_cursor"] = self.parser_cursor.as_dict()
        return result

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 actor baseline was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_ACTOR_BASELINE_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="actor_baseline_id",
            identity=self.actor_baseline_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementActorBaselineV49FV7:
        item = _decode_semantic_record_v49f_v7(
            payload,
            record_type=cls,
            domain=A2M_ACTOR_BASELINE_DOMAIN_V49F_V7,
            context="Raw V7 actor baseline",
        )
        raw_cursor = item["parser_cursor"]
        if not isinstance(raw_cursor, Mapping):
            raise CanonicalizationError("Raw V7 parser baseline must be a mapping")
        return cls(
            **{
                **item,
                "parser_cursor": WebSocketParserCursorV49C.from_mapping(raw_cursor),
            }
        )


_MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F_V7: Final = (
    "authority_profile",
    "external_attestation_status",
    "base_observed_authority_id",
    "predecessor_manifest_id",
    "predecessor_manifest_authority_id",
    "v7_source_inventory_id",
    "source_inventory_record_id",
    "v7_source_observation_id",
    "v7_source_tree_sha256",
    "v7_release_source_tree_sha256",
    "lifecycle_schema_id",
    "lifecycle_contract_id",
    "projection_authority_id",
    "projection_ledger_id",
    "projection_schema_version",
    "projection_validation_version",
    "projection_schema_fingerprint",
    "actor_baseline_id",
    "collector_attestation_key_id",
    "deployment_bundle_id",
    "deployment_trust_root_id",
    "collector_release_manifest_id",
    "runtime_environment_manifest_id",
    "transport_session_id",
    "driver_evidence_nonce_sha256",
    "kernel_socket_identity",
    "transport_capacity_policy_id",
    "started_at_utc",
    "monotonic_origin_nanoseconds",
    "boottime_origin_nanoseconds",
    "loop_time_origin_nanoseconds",
    "operation_lifecycle_profile",
    "failed_prefix_profile",
    "cancellation_profile",
    "orphan_recovery_profile",
    "promotion_eligible",
)


def derive_capacity_measurement_manifest_authority_subject_id_v49f_v7(
    subject: Mapping[str, Any],
) -> str:
    if not isinstance(subject, Mapping):
        raise CanonicalizationError("Raw V7 authority subject must be a mapping")
    require_exact_keys(
        subject,
        expected=set(_MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F_V7),
        context="Raw V7 manifest authority subject",
    )
    normalized = dict(subject)
    for name in (
        "base_observed_authority_id",
        "predecessor_manifest_id",
        "predecessor_manifest_authority_id",
        "v7_source_inventory_id",
        "source_inventory_record_id",
        "v7_source_observation_id",
        "v7_source_tree_sha256",
        "v7_release_source_tree_sha256",
        "lifecycle_contract_id",
        "projection_authority_id",
        "projection_ledger_id",
        "projection_schema_fingerprint",
        "actor_baseline_id",
        "collector_attestation_key_id",
        "deployment_bundle_id",
        "deployment_trust_root_id",
        "collector_release_manifest_id",
        "runtime_environment_manifest_id",
        "transport_session_id",
        "driver_evidence_nonce_sha256",
        "kernel_socket_identity",
        "transport_capacity_policy_id",
    ):
        normalized[name] = canonical_hash(normalized[name], field=name)
    normalized["started_at_utc"] = utc_iso(
        normalized["started_at_utc"], field="started_at_utc"
    )
    expected_identifiers = {
        "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7,
        "external_attestation_status": A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7,
        "lifecycle_schema_id": CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
        "projection_schema_version": (A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7),
        "projection_validation_version": (
            A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7
        ),
        "operation_lifecycle_profile": A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
        "failed_prefix_profile": A2M_FAILED_PREFIX_PROFILE_V49F_V7,
        "cancellation_profile": A2M_CANCELLATION_PROFILE_V49F_V7,
        "orphan_recovery_profile": A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
    }
    for name, expected in expected_identifiers.items():
        value = canonical_identifier(normalized[name], field=name, maximum=256)
        if value != expected:
            raise CanonicalizationError(f"Raw V7 authority {name} differs")
        normalized[name] = value
    for name in (
        "monotonic_origin_nanoseconds",
        "boottime_origin_nanoseconds",
        "loop_time_origin_nanoseconds",
    ):
        value = normalized[name]
        if (
            type(value) is not str
            or len(value) > _MAX_UINT128_DECIMAL_DIGITS
            or not value.isascii()
            or not value.isdecimal()
            or (len(value) > 1 and value.startswith("0"))
            or int(value) >= 1 << 128
        ):
            raise CanonicalizationError(
                f"{name} must be canonical uint128 decimal text"
            )
    if (
        type(normalized["promotion_eligible"]) is not bool
        or normalized["promotion_eligible"]
    ):
        raise CanonicalizationError("Raw V7 authority cannot be promotion eligible")
    return _semantic_identity_v49f_v7(
        domain=A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F_V7,
        payload=normalized,
    )


def capacity_measurement_authority_subject_signing_payload_v49f_v7(
    *,
    authority_subject_id: str,
    base_observed_authority_id: str,
    predecessor_manifest_id: str,
    predecessor_manifest_authority_id: str,
    v7_source_inventory_id: str,
    v7_source_observation_id: str,
    v7_source_tree_sha256: str,
    v7_release_source_tree_sha256: str,
    lifecycle_schema_id: str,
    projection_ledger_id: str,
    projection_schema_version: str,
    projection_validation_version: str,
    projection_schema_fingerprint: str,
    actor_baseline_id: str,
    collector_attestation_key_id: str,
    deployment_bundle_id: str,
    transport_session_id: str,
    operation_lifecycle_profile: str,
    failed_prefix_profile: str,
    cancellation_profile: str,
    orphan_recovery_profile: str,
) -> dict[str, Any]:
    payload = {
        "actor_baseline_id": canonical_hash(
            actor_baseline_id, field="actor_baseline_id"
        ),
        "authority_subject_id": canonical_hash(
            authority_subject_id, field="authority_subject_id"
        ),
        "base_observed_authority_id": canonical_hash(
            base_observed_authority_id, field="base_observed_authority_id"
        ),
        "cancellation_profile": canonical_identifier(
            cancellation_profile, field="cancellation_profile", maximum=256
        ),
        "collector_attestation_key_id": canonical_hash(
            collector_attestation_key_id, field="collector_attestation_key_id"
        ),
        "deployment_bundle_id": canonical_hash(
            deployment_bundle_id, field="deployment_bundle_id"
        ),
        "failed_prefix_profile": canonical_identifier(
            failed_prefix_profile, field="failed_prefix_profile", maximum=256
        ),
        "lifecycle_schema_id": canonical_identifier(
            lifecycle_schema_id, field="lifecycle_schema_id", maximum=256
        ),
        "operation_lifecycle_profile": canonical_identifier(
            operation_lifecycle_profile,
            field="operation_lifecycle_profile",
            maximum=256,
        ),
        "orphan_recovery_profile": canonical_identifier(
            orphan_recovery_profile, field="orphan_recovery_profile", maximum=256
        ),
        "predecessor_manifest_authority_id": canonical_hash(
            predecessor_manifest_authority_id,
            field="predecessor_manifest_authority_id",
        ),
        "predecessor_manifest_id": canonical_hash(
            predecessor_manifest_id, field="predecessor_manifest_id"
        ),
        "projection_ledger_id": canonical_hash(
            projection_ledger_id, field="projection_ledger_id"
        ),
        "projection_schema_fingerprint": canonical_hash(
            projection_schema_fingerprint,
            field="projection_schema_fingerprint",
        ),
        "projection_schema_version": canonical_identifier(
            projection_schema_version,
            field="projection_schema_version",
            maximum=256,
        ),
        "projection_validation_version": canonical_identifier(
            projection_validation_version,
            field="projection_validation_version",
            maximum=256,
        ),
        "transport_session_id": canonical_hash(
            transport_session_id, field="transport_session_id"
        ),
        "v7_source_inventory_id": canonical_hash(
            v7_source_inventory_id, field="v7_source_inventory_id"
        ),
        "v7_source_observation_id": canonical_hash(
            v7_source_observation_id, field="v7_source_observation_id"
        ),
        "v7_source_tree_sha256": canonical_hash(
            v7_source_tree_sha256, field="v7_source_tree_sha256"
        ),
        "v7_release_source_tree_sha256": canonical_hash(
            v7_release_source_tree_sha256,
            field="v7_release_source_tree_sha256",
        ),
    }
    expected = {
        "cancellation_profile": A2M_CANCELLATION_PROFILE_V49F_V7,
        "failed_prefix_profile": A2M_FAILED_PREFIX_PROFILE_V49F_V7,
        "lifecycle_schema_id": CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
        "operation_lifecycle_profile": A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
        "orphan_recovery_profile": A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
        "projection_schema_version": (A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7),
        "projection_validation_version": (
            A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7
        ),
        "v7_source_inventory_id": RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
    }
    if any(payload[name] != value for name, value in expected.items()):
        raise CanonicalizationError("Raw V7 signing payload profile differs")
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F_V7,
        "payload": payload,
        "schema_version": A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7,
    }


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementManifestAuthorityV49FV7:
    authority_profile: str
    external_attestation_status: str
    base_observed_authority_id: str
    predecessor_manifest_id: str
    predecessor_manifest_authority_id: str
    v7_source_inventory_id: str
    source_inventory_record_id: str
    v7_source_observation_id: str
    v7_source_tree_sha256: str
    v7_release_source_tree_sha256: str
    lifecycle_schema_id: str
    lifecycle_contract_id: str
    projection_authority_id: str
    projection_ledger_id: str
    projection_schema_version: str
    projection_validation_version: str
    projection_schema_fingerprint: str
    actor_baseline_id: str
    collector_attestation_key_id: str
    deployment_bundle_id: str
    deployment_trust_root_id: str
    collector_release_manifest_id: str
    runtime_environment_manifest_id: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    started_at_utc: str
    monotonic_origin_nanoseconds: str
    boottime_origin_nanoseconds: str
    loop_time_origin_nanoseconds: str
    operation_lifecycle_profile: str
    failed_prefix_profile: str
    cancellation_profile: str
    orphan_recovery_profile: str
    promotion_eligible: bool
    authority_subject_id: str | None
    signature_algorithm: str
    collector_attestation_public_key_hex: str
    signature_hex: str
    manifest_authority_id: str | None = None

    _SUBJECT_FIELDS: ClassVar[tuple[str, ...]] = (
        _MANIFEST_AUTHORITY_SUBJECT_FIELDS_V49F_V7
    )

    def __post_init__(self) -> None:
        subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f_v7(
            self._subject_payload_unchecked()
        )
        if (
            self.authority_subject_id is not None
            and canonical_hash(self.authority_subject_id, field="authority_subject_id")
            != subject_id
        ):
            raise CanonicalizationError(
                "Raw V7 authority_subject_id differs from the exact subject"
            )
        object.__setattr__(self, "authority_subject_id", subject_id)
        # Normalize through the same strict subject function's primitive rules.
        for name in (
            "base_observed_authority_id",
            "predecessor_manifest_id",
            "predecessor_manifest_authority_id",
            "v7_source_inventory_id",
            "source_inventory_record_id",
            "v7_source_observation_id",
            "v7_source_tree_sha256",
            "v7_release_source_tree_sha256",
            "lifecycle_contract_id",
            "projection_authority_id",
            "projection_ledger_id",
            "projection_schema_fingerprint",
            "actor_baseline_id",
            "collector_attestation_key_id",
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "runtime_environment_manifest_id",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self, "started_at_utc", utc_iso(self.started_at_utc, field="started_at_utc")
        )
        algorithm = canonical_identifier(
            self.signature_algorithm, field="signature_algorithm"
        )
        if algorithm != A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F_V7:
            raise CanonicalizationError("Raw V7 signature algorithm is unsupported")
        object.__setattr__(self, "signature_algorithm", algorithm)
        public_hex = self.collector_attestation_public_key_hex
        if (
            type(public_hex) is not str
            or re.fullmatch(r"[0-9a-f]{64}", public_hex) is None
        ):
            raise CanonicalizationError(
                "Raw V7 public key must be 32-byte lowercase hex"
            )
        public_key = bytes.fromhex(public_hex)
        if (
            not ed25519_public_key_is_valid(public_key)
            or derive_transport_attestation_key_id(public_key)
            != self.collector_attestation_key_id
        ):
            raise CanonicalizationError("Raw V7 collector key differs from public key")
        if (
            type(self.signature_hex) is not str
            or _SIGNATURE_RE.fullmatch(self.signature_hex) is None
        ):
            raise CanonicalizationError("Raw V7 signature is malformed")
        signing_payload = capacity_measurement_authority_subject_signing_payload_v49f_v7(
            authority_subject_id=subject_id,
            base_observed_authority_id=self.base_observed_authority_id,
            predecessor_manifest_id=self.predecessor_manifest_id,
            predecessor_manifest_authority_id=self.predecessor_manifest_authority_id,
            v7_source_inventory_id=self.v7_source_inventory_id,
            v7_source_observation_id=self.v7_source_observation_id,
            v7_source_tree_sha256=self.v7_source_tree_sha256,
            v7_release_source_tree_sha256=self.v7_release_source_tree_sha256,
            lifecycle_schema_id=self.lifecycle_schema_id,
            projection_ledger_id=self.projection_ledger_id,
            projection_schema_version=self.projection_schema_version,
            projection_validation_version=self.projection_validation_version,
            projection_schema_fingerprint=self.projection_schema_fingerprint,
            actor_baseline_id=self.actor_baseline_id,
            collector_attestation_key_id=self.collector_attestation_key_id,
            deployment_bundle_id=self.deployment_bundle_id,
            transport_session_id=self.transport_session_id,
            operation_lifecycle_profile=self.operation_lifecycle_profile,
            failed_prefix_profile=self.failed_prefix_profile,
            cancellation_profile=self.cancellation_profile,
            orphan_recovery_profile=self.orphan_recovery_profile,
        )
        try:
            Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
                canonical_json_bytes(signing_payload), bytes.fromhex(self.signature_hex)
            )
        except Exception as exc:
            raise CanonicalizationError("Raw V7 manifest signature is invalid") from exc
        authority_id = _semantic_identity_v49f_v7(
            domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
        )
        if (
            self.manifest_authority_id is not None
            and canonical_hash(
                self.manifest_authority_id, field="manifest_authority_id"
            )
            != authority_id
        ):
            raise CanonicalizationError(
                "Raw V7 manifest_authority_id differs from signed content"
            )
        object.__setattr__(self, "manifest_authority_id", authority_id)

    def _subject_payload_unchecked(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._SUBJECT_FIELDS}

    def _identity_payload_unchecked(self) -> dict[str, Any]:
        return {
            **self._subject_payload_unchecked(),
            "authority_subject_id": self.authority_subject_id,
            "collector_attestation_public_key_hex": (
                self.collector_attestation_public_key_hex
            ),
            "signature_algorithm": self.signature_algorithm,
            "signature_hex": self.signature_hex,
        }

    def as_dict(self) -> dict[str, Any]:
        replay = type(self)(
            **{item.name: getattr(self, item.name) for item in fields(type(self))}
        )
        if replay != self:
            raise CanonicalizationError("Raw V7 manifest authority was mutated")
        return _semantic_record_v49f_v7(
            domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F_V7,
            payload=self._identity_payload_unchecked(),
            identity_field="manifest_authority_id",
            identity=self.manifest_authority_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CapacityMeasurementManifestAuthorityV49FV7:
        return cls(
            **_decode_semantic_record_v49f_v7(
                payload,
                record_type=cls,
                domain=A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F_V7,
                context="Raw V7 manifest authority",
            )
        )


class CapacityMeasurementManifestSigningAuthorizationV49FV7:
    """One-shot same-task authorization for the admitted Raw-V7 signer."""

    _TOKEN = object()
    _MAX_COLLECTION_NANOSECONDS = 120_000_000_000
    _MAX_MONOTONIC_LOOP_DISAGREEMENT_NANOSECONDS = 1_000_000_000

    def __init__(
        self,
        *,
        _token: object,
        subject_payload: Mapping[str, Any],
        predecessor_campaign: CollectedCapacityMeasurementCampaignV49F,
        runtime: Any,
        runtime_snapshot: Any,
        sqlite_environment_observation: Any,
        source_inventory: CapacityMeasurementSourceInventoryV49FV7,
        lifecycle_contract: CapacityMeasurementLifecycleContractV49FV7,
        projection_authority: CapacityMeasurementProjectionAuthorityV49FV7,
        actor_baseline: CapacityMeasurementActorBaselineV49FV7,
    ) -> None:
        from .physical_projection_v4 import (
            PhysicalProjectionSqliteEnvironmentObservationV49F,
        )
        from .physical_transport_runtime_v4 import (
            PhysicalTransportManifestAuthoritySnapshotV49F,
            PhysicalTransportRuntimeV4,
        )

        if (
            _token is not self._TOKEN
            or type(self) is not CapacityMeasurementManifestSigningAuthorizationV49FV7
        ):
            raise TypeError("Raw-V7 signing authorization is collector-owned")
        if (
            type(predecessor_campaign) is not CollectedCapacityMeasurementCampaignV49F
            or type(runtime) is not PhysicalTransportRuntimeV4
            or predecessor_campaign.runtime is not runtime
            or type(runtime_snapshot)
            is not PhysicalTransportManifestAuthoritySnapshotV49F
            or type(sqlite_environment_observation)
            is not PhysicalProjectionSqliteEnvironmentObservationV49F
            or type(source_inventory) is not CapacityMeasurementSourceInventoryV49FV7
            or type(lifecycle_contract)
            is not CapacityMeasurementLifecycleContractV49FV7
            or type(projection_authority)
            is not CapacityMeasurementProjectionAuthorityV49FV7
            or type(actor_baseline) is not CapacityMeasurementActorBaselineV49FV7
        ):
            raise TypeError("Raw-V7 signing inputs must be exact retained authorities")
        predecessor_campaign.assert_local_current()
        predecessor = predecessor_campaign.manifest
        source = predecessor.source_observation
        base = predecessor.manifest_authority
        payload = dict(subject_payload)
        subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f_v7(
            payload
        )
        expected = {
            "base_observed_authority_id": base.manifest_authority_id,
            "predecessor_manifest_id": predecessor.campaign_manifest_id,
            "predecessor_manifest_authority_id": base.manifest_authority_id,
            "v7_source_inventory_id": source_inventory.source_inventory_id,
            "source_inventory_record_id": source_inventory.source_inventory_record_id,
            "v7_source_observation_id": source.source_observation_id,
            "v7_source_tree_sha256": source.source_tree_sha256,
            "v7_release_source_tree_sha256": source.deployment_source_tree_sha256,
            "lifecycle_schema_id": lifecycle_contract.lifecycle_schema_id,
            "lifecycle_contract_id": lifecycle_contract.lifecycle_contract_id,
            "projection_authority_id": projection_authority.projection_authority_id,
            "projection_ledger_id": projection_authority.projection_ledger_id,
            "projection_schema_version": projection_authority.projection_schema_version,
            "projection_validation_version": (
                projection_authority.projection_validation_version
            ),
            "projection_schema_fingerprint": (
                projection_authority.projection_schema_fingerprint
            ),
            "actor_baseline_id": actor_baseline.actor_baseline_id,
            "collector_attestation_key_id": base.collector_attestation_key_id,
            "deployment_bundle_id": predecessor.runtime_observation.deployment_bundle_id,
            "deployment_trust_root_id": (
                predecessor.runtime_observation.deployment_trust_root_id
            ),
            "collector_release_manifest_id": (
                predecessor.runtime_observation.collector_release_manifest_id
            ),
            "runtime_environment_manifest_id": (
                predecessor.runtime_observation.runtime_environment_manifest_id
            ),
            "transport_session_id": predecessor.transport_session_id,
            "driver_evidence_nonce_sha256": predecessor.driver_evidence_nonce_sha256,
            "kernel_socket_identity": predecessor.kernel_socket_identity,
            "transport_capacity_policy_id": predecessor.transport_capacity_policy_id,
            "started_at_utc": predecessor.started_at_utc,
            "monotonic_origin_nanoseconds": predecessor.monotonic_origin_nanoseconds,
            "boottime_origin_nanoseconds": predecessor.boottime_origin_nanoseconds,
            "loop_time_origin_nanoseconds": predecessor.loop_time_origin_nanoseconds,
            "operation_lifecycle_profile": (
                lifecycle_contract.operation_lifecycle_profile
            ),
            "failed_prefix_profile": lifecycle_contract.failed_prefix_profile,
            "cancellation_profile": lifecycle_contract.cancellation_profile,
            "orphan_recovery_profile": lifecycle_contract.orphan_recovery_profile,
            "promotion_eligible": False,
        }
        if (
            any(payload.get(name) != value for name, value in expected.items())
            or (
                payload.get("authority_profile")
                != A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7
            )
            or (
                payload.get("external_attestation_status")
                != A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7
            )
        ):
            raise CanonicalizationError(
                "Raw-V7 signing authorization is not the exact retained closure"
            )
        if (
            runtime_snapshot.authority_binding_payload()
            != predecessor_campaign._runtime_snapshot.authority_binding_payload()  # noqa: SLF001
            or sqlite_environment_observation
            != predecessor_campaign._sqlite_environment_observation  # noqa: SLF001
            or capacity_measurement_runtime_observation_from_snapshot_v49f(
                runtime_snapshot
            )
            != predecessor.runtime_observation
            or actor_baseline.transport_session_id
            != runtime_snapshot.transport_session_id
            or actor_baseline.driver_evidence_nonce_sha256
            != runtime_snapshot.driver_evidence_nonce_sha256
            or actor_baseline.kernel_socket_identity
            != runtime_snapshot.kernel_socket_identity
            or actor_baseline.transport_capacity_policy_id
            != runtime_snapshot.transport_capacity_policy_id
            or actor_baseline.deployment_bundle_id
            != runtime_snapshot.deployment_bundle_id
            or actor_baseline.monotonic_clock_domain_id
            != runtime_snapshot.monotonic_clock_domain_id
            or (
                actor_baseline.projection_receipt_sequence,
                actor_baseline.projection_receipt_hash,
            )
            != (
                projection_authority.baseline_receipt_sequence,
                projection_authority.baseline_receipt_hash,
            )
        ):
            raise CanonicalizationError(
                "Raw-V7 signing runtime/projection authority is not one closure"
            )
        signing_payload = (
            capacity_measurement_authority_subject_signing_payload_v49f_v7(
                authority_subject_id=subject_id,
                base_observed_authority_id=payload["base_observed_authority_id"],
                predecessor_manifest_id=payload["predecessor_manifest_id"],
                predecessor_manifest_authority_id=payload[
                    "predecessor_manifest_authority_id"
                ],
                v7_source_inventory_id=payload["v7_source_inventory_id"],
                v7_source_observation_id=payload["v7_source_observation_id"],
                v7_source_tree_sha256=payload["v7_source_tree_sha256"],
                v7_release_source_tree_sha256=payload["v7_release_source_tree_sha256"],
                lifecycle_schema_id=payload["lifecycle_schema_id"],
                projection_ledger_id=payload["projection_ledger_id"],
                projection_schema_version=payload["projection_schema_version"],
                projection_validation_version=payload["projection_validation_version"],
                projection_schema_fingerprint=payload["projection_schema_fingerprint"],
                actor_baseline_id=payload["actor_baseline_id"],
                collector_attestation_key_id=payload["collector_attestation_key_id"],
                deployment_bundle_id=payload["deployment_bundle_id"],
                transport_session_id=payload["transport_session_id"],
                operation_lifecycle_profile=payload["operation_lifecycle_profile"],
                failed_prefix_profile=payload["failed_prefix_profile"],
                cancellation_profile=payload["cancellation_profile"],
                orphan_recovery_profile=payload["orphan_recovery_profile"],
            )
        )
        try:
            import asyncio

            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "Raw-V7 signing authorization requires an active event loop"
            ) from exc
        task = asyncio.current_task()
        if task is None:
            raise CanonicalizationError(
                "Raw-V7 signing authorization requires one current task"
            )
        self._subject_payload = payload
        self._authority_subject_id = subject_id
        self._signing_payload = signing_payload
        self._predecessor_campaign = predecessor_campaign
        self._runtime = runtime
        self._runtime_snapshot = runtime_snapshot
        self._sqlite_environment_observation = sqlite_environment_observation
        self._projection_authority = projection_authority
        self._actor_baseline = actor_baseline
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._creator_loop = loop
        self._creator_task = task
        self._consumed = False
        self._fork_invalid = False
        _MANIFEST_AUTHORITY_FORK_GUARDS.add(self)

    @classmethod
    def _create(
        cls, **values: Any
    ) -> CapacityMeasurementManifestSigningAuthorizationV49FV7:
        return cls(_token=cls._TOKEN, **values)

    @property
    def authority_subject_id(self) -> str:
        return self._authority_subject_id

    def consume(
        self,
        *,
        runtime: Any,
        runtime_snapshot: Any,
        sqlite_observation: Any,
        projection_authority: Any,
        actor_baseline: Any,
    ) -> tuple[str, dict[str, Any]]:
        """Consume once after exact runtime/store/baseline recapture."""

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "Raw-V7 signing authorization left its event loop"
            ) from exc
        if (
            self._consumed
            or self._fork_invalid
            or runtime is not self._runtime
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
            or loop is not self._creator_loop
            or asyncio.current_task() is not self._creator_task
            or type(projection_authority)
            is not CapacityMeasurementProjectionAuthorityV49FV7
            or type(actor_baseline) is not CapacityMeasurementActorBaselineV49FV7
        ):
            raise CanonicalizationError(
                "Raw-V7 signing authorization is consumed or left its owner"
            )
        self._predecessor_campaign.assert_local_current()
        if (
            type(runtime_snapshot) is not type(self._runtime_snapshot)
            or runtime_snapshot.authority_binding_payload()
            != self._runtime_snapshot.authority_binding_payload()
            or sqlite_observation != self._sqlite_environment_observation
            or projection_authority != self._projection_authority
            or actor_baseline != self._actor_baseline
        ):
            raise CanonicalizationError(
                "Raw-V7 signing authority changed before key use"
            )
        now_monotonic = time.monotonic_ns()
        now_boottime = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        now_loop = int(self._creator_loop.time() * 1_000_000_000)
        origins = tuple(
            int(self._subject_payload[name])
            for name in (
                "monotonic_origin_nanoseconds",
                "boottime_origin_nanoseconds",
                "loop_time_origin_nanoseconds",
            )
        )
        elapsed = tuple(
            now - origin
            for now, origin in zip(
                (now_monotonic, now_boottime, now_loop), origins, strict=True
            )
        )
        if any(
            value < 0 or value > self._MAX_COLLECTION_NANOSECONDS for value in elapsed
        ) or abs(elapsed[0] - elapsed[2]) > (
            self._MAX_MONOTONIC_LOOP_DISAGREEMENT_NANOSECONDS
        ):
            raise CanonicalizationError(
                "Raw-V7 signing clock origins are stale or inconsistent"
            )
        self._consumed = True
        return self._authority_subject_id, dict(self._signing_payload)


@dataclass(frozen=True, slots=True, kw_only=True)
class AdmittedCapacityMeasurementAuthorityExpectationV49FV7:
    """Independent V6 trust plus frozen V7 ledger/profile expectations."""

    predecessor_expectation_v6: AdmittedCapacityMeasurementAuthorityExpectationV49F
    v7_source_inventory_id: str
    source_inventory_record_id: str
    v7_source_observation_id: str
    v7_source_tree_sha256: str
    v7_release_source_tree_sha256: str
    lifecycle_contract_id: str
    projection_authority_id: str
    projection_ledger_id: str
    projection_schema_version: str
    projection_validation_version: str
    projection_schema_fingerprint: str
    baseline_receipt_sequence: int
    baseline_receipt_hash: str
    actor_baseline_id: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str

    def __post_init__(self) -> None:
        if type(self.predecessor_expectation_v6) is not (
            AdmittedCapacityMeasurementAuthorityExpectationV49F
        ):
            raise CanonicalizationError("Raw V7 predecessor expectation must be exact")
        for name in (
            "v7_source_inventory_id",
            "source_inventory_record_id",
            "v7_source_observation_id",
            "v7_source_tree_sha256",
            "v7_release_source_tree_sha256",
            "lifecycle_contract_id",
            "projection_authority_id",
            "projection_ledger_id",
            "projection_schema_fingerprint",
            "baseline_receipt_hash",
            "actor_baseline_id",
            "collector_attestation_key_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        if self.v7_source_inventory_id != RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F:
            raise CanonicalizationError("trusted Raw V7 source inventory differs")
        if self.v7_source_tree_sha256 != self.v7_release_source_tree_sha256:
            raise CanonicalizationError(
                "trusted Raw V7 observed and release source trees differ"
            )
        version = canonical_identifier(
            self.projection_schema_version,
            field="projection_schema_version",
            maximum=256,
        )
        if version != A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7:
            raise CanonicalizationError("trusted Raw V7 projection schema differs")
        object.__setattr__(self, "projection_schema_version", version)
        validation = canonical_identifier(
            self.projection_validation_version,
            field="projection_validation_version",
            maximum=256,
        )
        if validation != A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7:
            raise CanonicalizationError("trusted Raw V7 projection validation differs")
        object.__setattr__(self, "projection_validation_version", validation)
        object.__setattr__(
            self,
            "baseline_receipt_sequence",
            canonical_safe_int(
                self.baseline_receipt_sequence,
                field="baseline_receipt_sequence",
                minimum=0,
            ),
        )
        if (self.baseline_receipt_sequence == 0) != (
            self.baseline_receipt_hash == "0" * 64
        ):
            raise CanonicalizationError(
                "trusted Raw V7 projection baseline sequence and hash differ"
            )
        public_hex = self.collector_attestation_public_key_hex
        if (
            type(public_hex) is not str
            or re.fullmatch(r"[0-9a-f]{64}", public_hex) is None
        ):
            raise CanonicalizationError("trusted Raw V7 public key is malformed")
        public_key = bytes.fromhex(public_hex)
        if (
            not ed25519_public_key_is_valid(public_key)
            or derive_transport_attestation_key_id(public_key)
            != self.collector_attestation_key_id
            or self.collector_attestation_key_id
            != self.predecessor_expectation_v6.collector_attestation_key_id
            or public_hex
            != self.predecessor_expectation_v6.collector_attestation_public_key_hex
        ):
            raise CanonicalizationError(
                "trusted Raw V7 key differs from admitted predecessor key"
            )


def verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7(
    *,
    manifest: Any,
    expectation: AdmittedCapacityMeasurementAuthorityExpectationV49FV7,
) -> None:
    """Authenticate V7 only after independently authenticating embedded V6."""

    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementManifestV49FV7,
    )

    if type(manifest) is not CapacityMeasurementManifestV49FV7:
        raise TypeError("manifest must be an exact Raw V7 manifest")
    if type(expectation) is not AdmittedCapacityMeasurementAuthorityExpectationV49FV7:
        raise TypeError("expectation must be exact admitted Raw V7 authority")
    replay = CapacityMeasurementManifestV49FV7.from_mapping(
        strict_json_loads(canonical_json_bytes(manifest.as_dict()))
    )
    if replay != manifest:
        raise CanonicalizationError("manifest differs from exact Raw V7 replay")
    verify_capacity_measurement_manifest_against_admitted_authority_v49f(
        manifest=manifest.predecessor_manifest_v6,
        expectation=expectation.predecessor_expectation_v6,
    )
    predecessor = manifest.predecessor_manifest_v6
    source = predecessor.source_observation
    role_values = tuple(role for member in source.members for role in member.roles)
    if any(
        not role.startswith(("CRITICAL_MODULE:", "LOADED_MODULE:"))
        for role in role_values
    ):
        raise CanonicalizationError(
            "Raw V7 predecessor source observation contains an unknown module role"
        )
    critical_roles = tuple(
        sorted(
            role.removeprefix("CRITICAL_MODULE:")
            for role in role_values
            if role.startswith("CRITICAL_MODULE:")
        )
    )
    loaded_roles = tuple(
        sorted(
            role.removeprefix("LOADED_MODULE:")
            for role in role_values
            if role.startswith("LOADED_MODULE:")
        )
    )
    if (
        critical_roles != RAW_V7_CRITICAL_SOURCE_MODULES_V49F
        or loaded_roles != RAW_V7_CRITICAL_SOURCE_MODULES_V49F
    ):
        raise CanonicalizationError(
            "Raw V7 predecessor source observation is not the exact 41-module closure"
        )
    if (
        not source.deployment_source_tree_matches
        or source.source_tree_sha256 != source.deployment_source_tree_sha256
        or source.source_tree_sha256 != expectation.v7_release_source_tree_sha256
        or source.source_observation_id != expectation.v7_source_observation_id
    ):
        raise CanonicalizationError(
            "Raw V7 predecessor source observation differs from the admitted release"
        )
    authority = manifest.manifest_authority_v7
    expected = (
        expectation.v7_source_inventory_id,
        expectation.source_inventory_record_id,
        expectation.v7_source_observation_id,
        expectation.v7_source_tree_sha256,
        expectation.v7_release_source_tree_sha256,
        expectation.lifecycle_contract_id,
        expectation.projection_authority_id,
        expectation.projection_ledger_id,
        expectation.projection_schema_version,
        expectation.projection_validation_version,
        expectation.projection_schema_fingerprint,
        expectation.baseline_receipt_sequence,
        expectation.baseline_receipt_hash,
        expectation.actor_baseline_id,
        expectation.collector_attestation_key_id,
        expectation.collector_attestation_public_key_hex,
    )
    actual = (
        manifest.source_inventory.source_inventory_id,
        manifest.source_inventory.source_inventory_record_id,
        manifest.predecessor_manifest_v6.source_observation.source_observation_id,
        manifest.predecessor_manifest_v6.source_observation.source_tree_sha256,
        manifest.predecessor_manifest_v6.source_observation.deployment_source_tree_sha256,
        manifest.lifecycle_contract.lifecycle_contract_id,
        manifest.projection_authority.projection_authority_id,
        manifest.projection_authority.projection_ledger_id,
        manifest.projection_authority.projection_schema_version,
        manifest.projection_authority.projection_validation_version,
        manifest.projection_authority.projection_schema_fingerprint,
        manifest.projection_authority.baseline_receipt_sequence,
        manifest.projection_authority.baseline_receipt_hash,
        manifest.actor_baseline.actor_baseline_id,
        authority.collector_attestation_key_id,
        authority.collector_attestation_public_key_hex,
    )
    if actual != expected:
        raise CanonicalizationError(
            "Raw V7 manifest differs from independently admitted authority"
        )
    runtime = predecessor.runtime_observation
    actor = manifest.actor_baseline
    projection = manifest.projection_authority
    if (
        actor.transport_session_id,
        actor.driver_evidence_nonce_sha256,
        actor.kernel_socket_identity,
        actor.transport_capacity_policy_id,
        actor.deployment_bundle_id,
        actor.monotonic_clock_domain_id,
    ) != (
        runtime.transport_session_id,
        runtime.driver_evidence_nonce_sha256,
        runtime.kernel_socket_identity,
        runtime.transport_capacity_policy_id,
        runtime.deployment_bundle_id,
        runtime.monotonic_clock_domain_id,
    ) or (
        actor.projection_receipt_sequence,
        actor.projection_receipt_hash,
    ) != (
        projection.baseline_receipt_sequence,
        projection.baseline_receipt_hash,
    ):
        raise CanonicalizationError(
            "Raw V7 actor/projection baseline differs from current session authority"
        )


class CollectedCapacityMeasurementCampaignV49FV7:
    """Sealed live context for one newly collected and signed Raw-V7 campaign."""

    _TOKEN = object()

    def __init__(
        self,
        *,
        _token: object,
        manifest: Any,
        expectation: AdmittedCapacityMeasurementAuthorityExpectationV49FV7,
        predecessor_campaign: CollectedCapacityMeasurementCampaignV49F,
        runtime: Any,
    ) -> None:
        import asyncio

        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementManifestV49FV7,
        )
        from .physical_transport_runtime_v4 import PhysicalTransportRuntimeV4

        if (
            _token is not self._TOKEN
            or type(self) is not CollectedCapacityMeasurementCampaignV49FV7
        ):
            raise TypeError("Raw-V7 campaigns must be created by the V7 collector")
        if (
            type(manifest) is not CapacityMeasurementManifestV49FV7
            or type(expectation)
            is not AdmittedCapacityMeasurementAuthorityExpectationV49FV7
            or type(predecessor_campaign)
            is not CollectedCapacityMeasurementCampaignV49F
            or type(runtime) is not PhysicalTransportRuntimeV4
            or predecessor_campaign.runtime is not runtime
            or manifest.predecessor_manifest_v6 is not predecessor_campaign.manifest
        ):
            raise TypeError("Raw-V7 campaign inputs must be exact retained authorities")
        verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7(
            manifest=manifest,
            expectation=expectation,
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError(
                "Raw-V7 campaign requires the active sampling event loop"
            ) from exc
        self._manifest = manifest
        self._expectation = expectation
        self._predecessor_campaign = predecessor_campaign
        self._runtime = runtime
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._creator_loop = loop
        self._closed = False
        self._fork_invalid = False
        self._next_operation_sequence = 1
        self._previous_operation_terminal_id: str | None = None
        self._active_declaration: Any | None = None
        self._run_ended = False
        self._artifact_eligible = True
        self._runner_authority: Any | None = None
        self._completed_prefixes: list[Any] = []
        self._completed_samples: list[Any] = []
        _MANIFEST_AUTHORITY_FORK_GUARDS.add(self)

    @classmethod
    def _create(cls, **values: Any) -> CollectedCapacityMeasurementCampaignV49FV7:
        result = cls(_token=cls._TOKEN, **values)
        result.assert_local_current()
        return result

    def _assert_context(self) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError("Raw-V7 campaign left its event loop") from exc
        if (
            self._closed
            or self._fork_invalid
            or os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
            or loop is not self._creator_loop
        ):
            raise CanonicalizationError(
                "Raw-V7 campaign left its creating process/thread/event loop"
            )

    @property
    def manifest(self) -> Any:
        self._assert_context()
        return self._manifest

    @property
    def runtime(self) -> Any:
        self._assert_context()
        return self._runtime

    @property
    def admitted_expectation(
        self,
    ) -> AdmittedCapacityMeasurementAuthorityExpectationV49FV7:
        self._assert_context()
        return self._expectation

    @property
    def next_operation_sequence(self) -> int:
        self._assert_context()
        return self._next_operation_sequence

    @property
    def artifact_eligible(self) -> bool:
        self._assert_context()
        return self._artifact_eligible

    def assert_local_current(self) -> None:
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementManifestV49FV7,
        )

        self._assert_context()
        self._predecessor_campaign.assert_local_current()
        replay = CapacityMeasurementManifestV49FV7.from_mapping(
            strict_json_loads(canonical_json_bytes(self._manifest.as_dict()))
        )
        if replay != self._manifest:
            raise CanonicalizationError("retained Raw-V7 manifest was mutated")
        verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7(
            manifest=self._manifest,
            expectation=self._expectation,
        )

    async def assert_current(self) -> None:
        self.assert_local_current()
        await self._predecessor_campaign.assert_current()

    def assert_operation_context_v49f(
        self,
        *,
        runtime: Any,
        runner_authority: Any,
    ) -> None:
        """Perform only constant-cost owner checks at a target-operation boundary."""

        self._assert_context()
        if (
            runtime is not self._runtime
            or runner_authority is not self._runner_authority
            or not self._artifact_eligible
            or self._run_ended
        ):
            raise CanonicalizationError(
                "Raw-V7 operation left its retained runner/campaign authority"
            )

    def has_next_operation_v49f(
        self,
        *,
        runtime: Any,
        runner_authority: Any,
    ) -> bool:
        """Return schedule availability without invalidating an admissible end."""

        from .physical_transport_capacity_measurement_v49f import (
            _expected_schedule_v49f_v7,
        )

        self._assert_context()
        if (
            runtime is not self._runtime
            or runner_authority is not self._runner_authority
        ):
            raise CanonicalizationError(
                "Raw-V7 next-operation query lacks its runner authority"
            )
        return (
            self._artifact_eligible
            and not self._run_ended
            and self._active_declaration is None
            and self._next_operation_sequence
            <= len(_expected_schedule_v49f_v7(self._manifest))
        )

    def _begin_next_operation_v49f(
        self,
        *,
        runtime: Any,
        runner_authority: Any,
    ) -> tuple[Any, str | None]:
        """Derive the sole next declaration from the signed schedule."""

        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleOperationV49F,
            CapacityMeasurementOperationDeclarationV49F,
        )
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementIngressWorkloadSpecV49F,
            _expected_schedule_v49f_v7,
        )

        self.assert_operation_context_v49f(
            runtime=runtime,
            runner_authority=runner_authority,
        )
        if self._active_declaration is not None:
            raise CanonicalizationError(
                "Raw-V7 campaign is ended, active, or bound to a foreign runtime"
            )
        schedule = _expected_schedule_v49f_v7(self._manifest)
        sequence = self._next_operation_sequence
        if sequence > len(schedule):
            raise CanonicalizationError("Raw-V7 campaign schedule is complete")
        workload_id, is_warmup, repetition_index = schedule[sequence - 1]
        predecessor = self._manifest.predecessor_manifest_v6
        workload = next(
            item for item in predecessor.workloads if item.workload_id == workload_id
        )
        spec = CapacityMeasurementIngressWorkloadSpecV49F.from_manifest_json(
            workload.workload_manifest_json
        )
        input_bytes = b"".join(spec.input_chunks)
        declaration = CapacityMeasurementOperationDeclarationV49F(
            campaign_manifest_id=self._manifest.campaign_manifest_id,
            manifest_authority_id=(
                self._manifest.manifest_authority_v7.manifest_authority_id
            ),
            measurement_design_id=predecessor.design.measurement_design_id,
            workload_id=workload.workload_id,
            workload_sha256=workload.workload_sha256,
            sample_sequence=sequence,
            operation_sequence=sequence,
            trial_index=sequence - 1,
            repetition_index=repetition_index,
            is_warmup=is_warmup,
            stage=spec.stage,
            operation=CapacityMeasurementLifecycleOperationV49F.INGRESS,
            input_chunk_count=len(spec.input_chunks),
            input_octet_count=len(input_bytes),
            input_sha256=hashlib.sha256(input_bytes).hexdigest(),
            raw_ingress_batch_sha256=spec.raw_ingress_batch_sha256,
            timeout_seconds=spec.timeout_seconds,
            expected_output_frame_count=len(spec.expected_output_frames),
            expected_output_frames_sha256=spec.expected_output_frames_sha256,
        )
        self._active_declaration = declaration
        return declaration, self._previous_operation_terminal_id

    def _abandon_uncommitted_operation_v49f(self, *, declaration: Any) -> None:
        self._assert_context()
        if declaration is not self._active_declaration:
            raise CanonicalizationError("Raw-V7 abandoned a foreign declaration")
        self._active_declaration = None

    def _mark_unenveloped_run_termination_v49f(
        self,
        *,
        runner_authority: Any,
        declaration: Any | None = None,
    ) -> None:
        """Latch an interruption with no runner-recorded durable terminal."""

        self._assert_context()
        if runner_authority is not self._runner_authority or (
            declaration is not None and declaration is not self._active_declaration
        ):
            raise CanonicalizationError(
                "Raw-V7 unenveloped termination lacks its runner authority"
            )
        self._active_declaration = None
        self._artifact_eligible = False
        self._run_ended = True

    def _mark_unpublishable_v49f(
        self,
        *,
        runner_authority: Any,
        declaration: Any | None = None,
    ) -> None:
        """Permanently refuse publication after a local runner invariant fails."""

        self._assert_context()
        if runner_authority is not self._runner_authority or (
            declaration is not None and declaration is not self._active_declaration
        ):
            raise CanonicalizationError(
                "Raw-V7 unpublishable latch lacks its runner authority"
            )
        self._active_declaration = None
        self._artifact_eligible = False
        self._run_ended = True

    def _mark_artifact_finalization_failure_v49f(self) -> None:
        """Permanently reject retry after a failed final campaign boundary."""

        self._assert_context()
        if self._active_declaration is not None:
            raise CanonicalizationError(
                "Raw-V7 artifact finalization cannot overtake an active operation"
            )
        self._artifact_eligible = False
        self._run_ended = True

    def _complete_operation_v49f(
        self,
        *,
        declaration: Any,
        prefix: Any,
        sample: Any | None,
        runner_authority: Any,
    ) -> None:
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationDeclarationV49F,
            CapacityMeasurementOperationPrefixV49F,
        )
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementSampleV49FV7,
            _terminal_is_run_ending_v49f_v7,
        )

        self._assert_context()
        if (
            runner_authority is not self._runner_authority
            or type(declaration) is not CapacityMeasurementOperationDeclarationV49F
            or declaration is not self._active_declaration
            or type(prefix) is not CapacityMeasurementOperationPrefixV49F
            or prefix.terminal is None
            or (
                sample is not None
                and (
                    type(sample) is not CapacityMeasurementSampleV49FV7
                    or sample.recovered_prefix is not prefix
                    or sample.attempt is not prefix.attempt
                    or sample.terminal is not prefix.terminal
                )
            )
            or prefix.attempt.declaration_id != declaration.declaration_id
            or prefix.attempt.operation_sequence != self._next_operation_sequence
            or prefix.attempt.previous_operation_terminal_id
            != self._previous_operation_terminal_id
            or prefix.terminal.previous_operation_terminal_id
            != self._previous_operation_terminal_id
            or prefix.attempt.campaign_manifest_id
            != self._manifest.campaign_manifest_id
            or prefix.attempt.manifest_authority_id
            != self._manifest.manifest_authority_v7.manifest_authority_id
        ):
            raise CanonicalizationError(
                "Raw-V7 terminal prefix differs from its retained schedule authority"
            )
        self._previous_operation_terminal_id = prefix.terminal.terminal_id
        self._next_operation_sequence += 1
        self._active_declaration = None
        self._completed_prefixes.append(prefix)
        if sample is not None:
            self._completed_samples.append(sample)
        self._run_ended = _terminal_is_run_ending_v49f_v7(
            prefix.terminal,
            lifecycle_contract=self._manifest.lifecycle_contract,
        )

    def _assert_artifact_candidate_v49f(
        self,
        *,
        runtime: Any,
        runner_authority: Any,
        runner: Any,
        samples: Any,
    ) -> tuple[Any, ...]:
        """Bind candidate bytes to exact runner-recorded local issuance effects."""

        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementSampleV49FV7,
            _expected_schedule_v49f_v7,
        )

        self._assert_context()
        if (
            runtime is not self._runtime
            or runner_authority is not self._runner_authority
            or not self._artifact_eligible
            or self._active_declaration is not None
        ):
            raise CanonicalizationError(
                "Raw-V7 artifact candidate lacks its eligible quiescent campaign"
            )
        runner_authority.assert_owner(
            campaign=self,
            runtime=runtime,
            runner=runner,
        )
        normalized = tuple(samples)
        retained = tuple(self._completed_samples)
        retained_prefixes = tuple(self._completed_prefixes)
        if (
            not retained
            or len(retained_prefixes) != len(retained)
            or len(normalized) != len(retained)
            or any(
                type(actual) is not CapacityMeasurementSampleV49FV7
                or actual is not recorded
                or (
                    actual.sample_id,
                    actual.attempt.attempt_id,
                    actual.terminal.terminal_id,
                    actual.recovered_prefix.recovered_prefix_id,
                )
                != (
                    recorded.sample_id,
                    recorded.attempt.attempt_id,
                    recorded.terminal.terminal_id,
                    recorded.recovered_prefix.recovered_prefix_id,
                )
                for actual, recorded in zip(normalized, retained)
            )
            or any(
                sample.recovered_prefix is not prefix
                for sample, prefix in zip(retained, retained_prefixes)
            )
            or tuple(runner.completed_samples) != retained
        ):
            raise CanonicalizationError(
                "Raw-V7 artifact samples differ from runner-recorded issuance"
            )
        expected_count = len(_expected_schedule_v49f_v7(self._manifest))
        if len(retained) != expected_count and not self._run_ended:
            raise CanonicalizationError(
                "Raw-V7 artifact is neither complete nor a run-ending prefix"
            )
        return normalized

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._predecessor_campaign.close()

    def __enter__(self) -> CollectedCapacityMeasurementCampaignV49FV7:
        self.assert_local_current()
        return self

    async def __aenter__(self) -> CollectedCapacityMeasurementCampaignV49FV7:
        await self.assert_current()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aexit__(self, *_: object) -> None:
        self.close()


class CapacityMeasurementCampaignRunnerAuthorizationV49FV7:
    """Process-local reusable authority for one campaign runner and task."""

    _TOKEN = object()

    def __init__(
        self,
        *,
        _token: object,
        campaign: CollectedCapacityMeasurementCampaignV49FV7,
        runner: object,
    ) -> None:
        import asyncio

        if (
            _token is not self._TOKEN
            or type(self) is not CapacityMeasurementCampaignRunnerAuthorizationV49FV7
            or type(campaign) is not CollectedCapacityMeasurementCampaignV49FV7
            or runner is None
        ):
            raise TypeError("Raw-V7 runner authority is campaign-owned")
        campaign._assert_context()  # noqa: SLF001
        if campaign._runner_authority is not None:  # noqa: SLF001
            raise CanonicalizationError("Raw-V7 campaign already has a runner")
        task = asyncio.current_task()
        if task is None:
            raise CanonicalizationError("Raw-V7 runner requires one current task")
        self._campaign = campaign
        self._runner = runner
        self._pid = os.getpid()
        self._thread_id = threading.get_ident()
        self._loop = asyncio.get_running_loop()
        self._task = task
        self._fork_invalid = False
        campaign._runner_authority = self  # noqa: SLF001
        _MANIFEST_AUTHORITY_FORK_GUARDS.add(self)

    @classmethod
    def _create(
        cls,
        *,
        campaign: CollectedCapacityMeasurementCampaignV49FV7,
        runner: object,
    ) -> CapacityMeasurementCampaignRunnerAuthorizationV49FV7:
        from .physical_transport_capacity_sampler_v49f import (
            CapacityMeasurementSessionRunnerV49FV7,
        )

        if type(runner) is not CapacityMeasurementSessionRunnerV49FV7:
            raise TypeError("Raw-V7 runner authority requires the exact runner")
        return cls(_token=cls._TOKEN, campaign=campaign, runner=runner)

    def assert_owner(
        self,
        *,
        campaign: CollectedCapacityMeasurementCampaignV49FV7,
        runtime: Any,
        runner: object,
    ) -> None:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CanonicalizationError("Raw-V7 runner left its event loop") from exc
        if (
            self._fork_invalid
            or campaign is not self._campaign
            or runtime is not campaign.runtime
            or runner is not self._runner
            or os.getpid() != self._pid
            or threading.get_ident() != self._thread_id
            or loop is not self._loop
            or asyncio.current_task() is not self._task
        ):
            raise CanonicalizationError(
                "Raw-V7 runner authorization left its exact owner"
            )


def _capacity_measurement_v7_subject_payload(
    *,
    predecessor: Any,
    source_inventory: CapacityMeasurementSourceInventoryV49FV7,
    lifecycle_contract: CapacityMeasurementLifecycleContractV49FV7,
    projection_authority: CapacityMeasurementProjectionAuthorityV49FV7,
    actor_baseline: CapacityMeasurementActorBaselineV49FV7,
) -> dict[str, Any]:
    source = predecessor.source_observation
    runtime = predecessor.runtime_observation
    base = predecessor.manifest_authority
    return {
        "authority_profile": A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7,
        "external_attestation_status": A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7,
        "base_observed_authority_id": base.manifest_authority_id,
        "predecessor_manifest_id": predecessor.campaign_manifest_id,
        "predecessor_manifest_authority_id": base.manifest_authority_id,
        "v7_source_inventory_id": source_inventory.source_inventory_id,
        "source_inventory_record_id": source_inventory.source_inventory_record_id,
        "v7_source_observation_id": source.source_observation_id,
        "v7_source_tree_sha256": source.source_tree_sha256,
        "v7_release_source_tree_sha256": source.deployment_source_tree_sha256,
        "lifecycle_schema_id": lifecycle_contract.lifecycle_schema_id,
        "lifecycle_contract_id": lifecycle_contract.lifecycle_contract_id,
        "projection_authority_id": projection_authority.projection_authority_id,
        "projection_ledger_id": projection_authority.projection_ledger_id,
        "projection_schema_version": projection_authority.projection_schema_version,
        "projection_validation_version": (
            projection_authority.projection_validation_version
        ),
        "projection_schema_fingerprint": (
            projection_authority.projection_schema_fingerprint
        ),
        "actor_baseline_id": actor_baseline.actor_baseline_id,
        "collector_attestation_key_id": base.collector_attestation_key_id,
        "deployment_bundle_id": runtime.deployment_bundle_id,
        "deployment_trust_root_id": runtime.deployment_trust_root_id,
        "collector_release_manifest_id": runtime.collector_release_manifest_id,
        "runtime_environment_manifest_id": runtime.runtime_environment_manifest_id,
        "transport_session_id": predecessor.transport_session_id,
        "driver_evidence_nonce_sha256": predecessor.driver_evidence_nonce_sha256,
        "kernel_socket_identity": predecessor.kernel_socket_identity,
        "transport_capacity_policy_id": predecessor.transport_capacity_policy_id,
        "started_at_utc": predecessor.started_at_utc,
        "monotonic_origin_nanoseconds": predecessor.monotonic_origin_nanoseconds,
        "boottime_origin_nanoseconds": predecessor.boottime_origin_nanoseconds,
        "loop_time_origin_nanoseconds": predecessor.loop_time_origin_nanoseconds,
        "operation_lifecycle_profile": lifecycle_contract.operation_lifecycle_profile,
        "failed_prefix_profile": lifecycle_contract.failed_prefix_profile,
        "cancellation_profile": lifecycle_contract.cancellation_profile,
        "orphan_recovery_profile": lifecycle_contract.orphan_recovery_profile,
        "promotion_eligible": False,
    }


async def _collect_capacity_measurement_campaign_v49f_v7(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
    fatal_operation_exceptions: tuple[tuple[str, str], ...],
    required_authority_profile: str,
) -> CollectedCapacityMeasurementCampaignV49FV7:
    """Collect a fresh current V6 predecessor, then sign its exact V7 closure."""

    from .physical_transport_capacity_measurement_v49f import (
        CapacityMeasurementManifestV49FV7,
    )

    profile = canonical_identifier(
        required_authority_profile,
        field="required_authority_profile",
        maximum=32,
    )
    predecessor_campaign: CollectedCapacityMeasurementCampaignV49F | None = None
    try:
        predecessor_campaign = await _collect_capacity_measurement_campaign_v49f(
            runtime=runtime,
            repository_root=repository_root,
            campaign_label=campaign_label,
            workloads=workloads,
            design=design,
            required_authority_profile=profile,
        )
        await predecessor_campaign.assert_current()
        predecessor = predecessor_campaign.manifest
        source_inventory = CapacityMeasurementSourceInventoryV49FV7(
            predecessor_source_inventory_id=(
                RAW_V6_ACCEPTED_CRITICAL_SOURCE_INVENTORY_ID_V49F
            ),
            module_names=RAW_V7_CRITICAL_SOURCE_MODULES_V49F,
            source_inventory_id=RAW_V7_CRITICAL_SOURCE_INVENTORY_ID_V49F,
        )
        lifecycle_contract = CapacityMeasurementLifecycleContractV49FV7(
            lifecycle_schema_id=CAPACITY_MEASUREMENT_LIFECYCLE_SCHEMA_VERSION_V49F,
            operation_lifecycle_profile=A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7,
            failed_prefix_profile=A2M_FAILED_PREFIX_PROFILE_V49F_V7,
            cancellation_profile=A2M_CANCELLATION_PROFILE_V49F_V7,
            orphan_recovery_profile=A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7,
            fatal_operation_exceptions=fatal_operation_exceptions,
        )
        (
            projection_authority,
            actor_baseline,
        ) = await runtime.capture_capacity_measurement_v7_baselines_v49f()
        (
            runtime_snapshot,
            sqlite_observation,
        ) = await runtime.capture_manifest_authority_inputs_v49f()
        subject = _capacity_measurement_v7_subject_payload(
            predecessor=predecessor,
            source_inventory=source_inventory,
            lifecycle_contract=lifecycle_contract,
            projection_authority=projection_authority,
            actor_baseline=actor_baseline,
        )
        subject_id = derive_capacity_measurement_manifest_authority_subject_id_v49f_v7(
            subject
        )
        signing_authorization = (
            CapacityMeasurementManifestSigningAuthorizationV49FV7._create(
                subject_payload=subject,
                predecessor_campaign=predecessor_campaign,
                runtime=runtime,
                runtime_snapshot=runtime_snapshot,
                sqlite_environment_observation=sqlite_observation,
                source_inventory=source_inventory,
                lifecycle_contract=lifecycle_contract,
                projection_authority=projection_authority,
                actor_baseline=actor_baseline,
            )
        )
        signature = await runtime.sign_manifest_authority_subject_v49f_v7(
            authorization=signing_authorization
        )
        expected_signing_payload = (
            capacity_measurement_authority_subject_signing_payload_v49f_v7(
                authority_subject_id=subject_id,
                base_observed_authority_id=subject["base_observed_authority_id"],
                predecessor_manifest_id=subject["predecessor_manifest_id"],
                predecessor_manifest_authority_id=subject[
                    "predecessor_manifest_authority_id"
                ],
                v7_source_inventory_id=subject["v7_source_inventory_id"],
                v7_source_observation_id=subject["v7_source_observation_id"],
                v7_source_tree_sha256=subject["v7_source_tree_sha256"],
                v7_release_source_tree_sha256=subject["v7_release_source_tree_sha256"],
                lifecycle_schema_id=subject["lifecycle_schema_id"],
                projection_ledger_id=subject["projection_ledger_id"],
                projection_schema_version=subject["projection_schema_version"],
                projection_validation_version=subject["projection_validation_version"],
                projection_schema_fingerprint=subject["projection_schema_fingerprint"],
                actor_baseline_id=subject["actor_baseline_id"],
                collector_attestation_key_id=subject["collector_attestation_key_id"],
                deployment_bundle_id=subject["deployment_bundle_id"],
                transport_session_id=subject["transport_session_id"],
                operation_lifecycle_profile=subject["operation_lifecycle_profile"],
                failed_prefix_profile=subject["failed_prefix_profile"],
                cancellation_profile=subject["cancellation_profile"],
                orphan_recovery_profile=subject["orphan_recovery_profile"],
            )
        )
        if (
            signature.authority_subject_id != subject_id
            or signature.deployment_bundle_id != subject["deployment_bundle_id"]
            or signature.collector_attestation_key_id
            != subject["collector_attestation_key_id"]
            or signature.transport_session_id != subject["transport_session_id"]
            or signature.signed_payload_sha256
            != hashlib.sha256(
                canonical_json_bytes(expected_signing_payload)
            ).hexdigest()
            or signature.collector_attestation_public_key_hex
            != predecessor.manifest_authority.collector_attestation_public_key_hex
        ):
            raise CanonicalizationError(
                "Raw-V7 runtime signature differs from its retained subject"
            )
        authority = CapacityMeasurementManifestAuthorityV49FV7(
            **subject,
            authority_subject_id=subject_id,
            signature_algorithm=(A2M_MANIFEST_AUTHORITY_SIGNATURE_ALGORITHM_V49F_V7),
            collector_attestation_public_key_hex=(
                signature.collector_attestation_public_key_hex
            ),
            signature_hex=signature.signature_hex,
        )
        manifest = CapacityMeasurementManifestV49FV7(
            predecessor_manifest_v6=predecessor,
            source_inventory=source_inventory,
            lifecycle_contract=lifecycle_contract,
            projection_authority=projection_authority,
            actor_baseline=actor_baseline,
            manifest_authority_v7=authority,
        )
        predecessor_expectation = (
            runtime.capacity_measurement_admitted_expectation_v49f()
        )
        expectation = AdmittedCapacityMeasurementAuthorityExpectationV49FV7(
            predecessor_expectation_v6=predecessor_expectation,
            v7_source_inventory_id=source_inventory.source_inventory_id,
            source_inventory_record_id=source_inventory.source_inventory_record_id,
            v7_source_observation_id=predecessor.source_observation.source_observation_id,
            v7_source_tree_sha256=predecessor.source_observation.source_tree_sha256,
            v7_release_source_tree_sha256=(
                predecessor.source_observation.deployment_source_tree_sha256
            ),
            lifecycle_contract_id=lifecycle_contract.lifecycle_contract_id,
            projection_authority_id=projection_authority.projection_authority_id,
            projection_ledger_id=projection_authority.projection_ledger_id,
            projection_schema_version=projection_authority.projection_schema_version,
            projection_validation_version=(
                projection_authority.projection_validation_version
            ),
            projection_schema_fingerprint=(
                projection_authority.projection_schema_fingerprint
            ),
            baseline_receipt_sequence=(projection_authority.baseline_receipt_sequence),
            baseline_receipt_hash=projection_authority.baseline_receipt_hash,
            actor_baseline_id=actor_baseline.actor_baseline_id,
            collector_attestation_key_id=authority.collector_attestation_key_id,
            collector_attestation_public_key_hex=(
                authority.collector_attestation_public_key_hex
            ),
        )
        campaign = CollectedCapacityMeasurementCampaignV49FV7._create(
            manifest=manifest,
            expectation=expectation,
            predecessor_campaign=predecessor_campaign,
            runtime=runtime,
        )
        await campaign.assert_current()
        predecessor_campaign = None
        return campaign
    except BaseException:
        if predecessor_campaign is not None:
            predecessor_campaign.close()
        raise


async def collect_capacity_measurement_campaign_v49f_v7(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
    fatal_operation_exceptions: tuple[tuple[str, str], ...] = (),
) -> CollectedCapacityMeasurementCampaignV49FV7:
    """Collect one production Raw-V7 campaign from an exact LIVE_LINUX runtime."""

    return await _collect_capacity_measurement_campaign_v49f_v7(
        runtime=runtime,
        repository_root=repository_root,
        campaign_label=campaign_label,
        workloads=workloads,
        design=design,
        fatal_operation_exceptions=fatal_operation_exceptions,
        required_authority_profile="LIVE_LINUX",
    )


async def _collect_capacity_measurement_campaign_for_test_v49f_v7(
    *,
    runtime: Any,
    repository_root: Path,
    campaign_label: str,
    workloads: tuple[Any, ...],
    design: Any,
    fatal_operation_exceptions: tuple[tuple[str, str], ...] = (),
) -> CollectedCapacityMeasurementCampaignV49FV7:
    """Exercise the production V7 collector with the explicit exact-test profile."""

    return await _collect_capacity_measurement_campaign_v49f_v7(
        runtime=runtime,
        repository_root=repository_root,
        campaign_label=campaign_label,
        workloads=workloads,
        design=design,
        fatal_operation_exceptions=fatal_operation_exceptions,
        required_authority_profile="EXACT_TEST",
    )


__all__ = [
    "A2M_EXTERNAL_ATTESTATION_STATUS_V49F",
    "A2M_EXTERNAL_ATTESTATION_STATUS_V49F_V7",
    "A2M_ACTOR_BASELINE_DOMAIN_V49F_V7",
    "A2M_CANCELLATION_PROFILE_V49F_V7",
    "A2M_FAILED_PREFIX_PROFILE_V49F_V7",
    "A2M_LIFECYCLE_CONTRACT_DOMAIN_V49F_V7",
    "A2M_MANIFEST_AUTHORITY_ATTESTATION_DOMAIN_V49F_V7",
    "A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F",
    "A2M_MANIFEST_AUTHORITY_SCHEMA_VERSION_V49F_V7",
    "A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F",
    "A2M_MANIFEST_AUTHORITY_SUBJECT_DOMAIN_V49F_V7",
    "A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F_V7",
    "A2M_OPERATION_LIFECYCLE_PROFILE_V49F_V7",
    "A2M_ORPHAN_RECOVERY_PROFILE_V49F_V7",
    "A2M_PROJECTION_AUTHORITY_DOMAIN_V49F_V7",
    "A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7",
    "A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7",
    "A2M_SOURCE_INVENTORY_DOMAIN_V49F_V7",
    "A2M_MAXIMUM_MANIFEST_REQUEST_WORKLOADS_V49F",
    "A2M_OBSERVED_LOCAL_AUTHORITY_PROFILE_V49F",
    "AdmittedCapacityMeasurementAuthorityExpectationV49F",
    "AdmittedCapacityMeasurementAuthorityExpectationV49FV7",
    "CapacityMeasurementActorBaselineV49FV7",
    "CapacityMeasurementLifecycleContractV49FV7",
    "CapacityMeasurementManifestAuthorityV49F",
    "CapacityMeasurementManifestAuthorityV49FV7",
    "CapacityMeasurementManifestRequestV49F",
    "CapacityMeasurementManifestSigningAuthorizationV49F",
    "CapacityMeasurementManifestSigningAuthorizationV49FV7",
    "CapacityMeasurementProjectionAuthorityV49FV7",
    "CapacityMeasurementProcessEnvironmentObservationV49F",
    "CapacityMeasurementRuntimeObservationV49F",
    "CapacityMeasurementSourceInventoryV49FV7",
    "CollectedCapacityMeasurementCampaignV49F",
    "CollectedCapacityMeasurementCampaignV49FV7",
    "capacity_measurement_authority_subject_signing_payload_v49f",
    "capacity_measurement_authority_subject_signing_payload_v49f_v7",
    "collect_capacity_measurement_campaign_v49f",
    "collect_capacity_measurement_campaign_v49f_v7",
    "derive_capacity_measurement_manifest_authority_subject_id_v49f",
    "derive_capacity_measurement_manifest_authority_subject_id_v49f_v7",
    "capacity_measurement_runtime_observation_from_snapshot_v49f",
    "observe_capacity_measurement_process_environment_v49f",
    "verify_capacity_measurement_manifest_against_admitted_authority_v49f",
    "verify_capacity_measurement_manifest_against_admitted_authority_v49f_v7",
]

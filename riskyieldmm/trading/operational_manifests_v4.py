"""Offline operational deployment authority contracts for transport V4.5.

This module intentionally solves a narrow local admission problem.  A caller
pins one deployment trust-root identity out of band, verifies a DSSE-wrapped
deployment bundle under that root, verifies the exact content-addressed child
closure, and receives an immutable capability describing what was admitted.

The contracts do not establish build provenance, remote attestation, host
integrity, key non-compromise, TUF compliance, or profitable trading.  The
deployment-root private keys are never required by the runtime.  A separate,
strictly scoped collector key is authorized only to sign transport evidence.
"""

from __future__ import annotations

import base64
import binascii
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Protocol, TypeAlias, runtime_checkable

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
from .ledger_signing import Ed25519CheckpointVerifier, ed25519_public_key_is_valid
from .physical_transport_capacity_v49f import TransportCapacityPolicyV49F
from .physical_transport_v4 import derive_transport_attestation_key_id

OPERATIONAL_MANIFEST_SCHEMA_VERSION = "riskyieldmm_operational_manifest_v4_9f"
DEPLOYMENT_TRUST_ROOT_SCHEMA_VERSION = (
    "riskyieldmm_operational_deployment_trust_root_v4_5"
)
DEPLOYMENT_BUNDLE_SCHEMA_VERSION = "riskyieldmm_operational_deployment_bundle_v4_5"
DEPLOYMENT_DSSE_PAYLOAD_TYPE = (
    "application/vnd.riskyieldmm.operational-deployment-bundle.v4_5+json"
)
DEPLOYMENT_SIGNATURE_ALGORITHM = "ED25519"
DEPLOYMENT_ROLE_NAME = "DEPLOYMENT"

DEPENDENCY_LOCK_FORMAT = "PIP_REQUIREMENTS_HASHES_V1"
TLS_TRUST_STORE_FORMAT = "PEM_CA_BUNDLE_V1"
TLS_VERIFY_PURPOSE = "SERVER_AUTH"
CLOCK_SOURCE_KIND = "CHRONY_TRACKING_V1"
MONOTONIC_DOMAIN_PROFILE = "LINUX_BOOT_ID_TIME_NAMESPACE_CLOCK_BOOTTIME_V1"
CHRONYD_LAUNCH_PROFILE = "LINUX_CHRONYD_4_8_SEALED_MEMFD_SUPERVISED_V1"
CHRONYD_SUPERVISOR_PROFILE = "SYSTEMD_TYPE_NOTIFY_MAIN_EXACT_UNIT_V1"
CHRONYD_COMMAND_PROXY_PROFILE = "CHRONY_4_8_READ_ONLY_DATAGRAM_CREDENTIAL_PROXY_V1"
# ``/query-`` + 16 lowercase hex characters + ``/upstream.sock``.
CHRONYD_QUERY_SOCKET_PATH_SUFFIX_BYTES = 37
CHRONYD_FIXED_ENVIRONMENT_SHA256 = sha256_digest(
    {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
)
COLLECTOR_KEY_USAGE = "TRANSPORT_ATTESTATION_ONLY"
TLS_WEBSOCKET_DRIVER_PROFILE_V49B = "PYTHON_SSL_MEMORY_BIO_WEBSOCKETS_16_SANS_IO_V49B"
TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B = frozenset(
    {
        "OPENSSL_LIBCRYPTO",
        "OPENSSL_LIBSSL",
        "PYTHON_EXECUTABLE",
        "PYTHON_SSL_EXTENSION",
        "PYTHON_STDLIB_SSL",
        "RISKYIELDMM_TLS_DRIVER",
        "RISKYIELDMM_TLS_TRUST_STORE",
    }
)
TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B = frozenset(
    {
        "PYTHON_STDLIB_SSL_BYTECODE_CACHE",
        "RISKYIELDMM_TLS_DRIVER_BYTECODE_CACHE",
        "RISKYIELDMM_TLS_TRUST_STORE_BYTECODE_CACHE",
    }
)
TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B = frozenset({"cryptography", "websockets"})

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")
_POSIX_USER_NAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class OperationalManifestVerificationError(ValueError):
    """Raised when a deployment authority graph cannot be admitted."""


class OperationalManifestKindV4(str, Enum):
    COLLECTOR_RELEASE = "COLLECTOR_RELEASE"
    DEPENDENCY_LOCK = "DEPENDENCY_LOCK"
    TLS_TRUST_STORE = "TLS_TRUST_STORE"
    CLOCK_SOURCE_POLICY = "CLOCK_SOURCE_POLICY"
    RUNTIME_ENVIRONMENT = "RUNTIME_ENVIRONMENT"
    COLLECTOR_KEY_AUTHORIZATION = "COLLECTOR_KEY_AUTHORIZATION"


class DeploymentAuthorityCeilingV4(str, Enum):
    """Maximum side-effect class authorized by this initial bundle."""

    PUBLIC_MARKET_DATA_CAPTURE_ONLY = "PUBLIC_MARKET_DATA_CAPTURE_ONLY"


def _strict_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _required_true(value: Any, *, field: str) -> bool:
    result = _strict_bool(value, field=field)
    if not result:
        raise CanonicalizationError(f"{field} must be true")
    return result


def _canonical_absolute_posix_path(value: Any, *, field: str) -> str:
    path = canonical_identifier(value, field=field, maximum=4096)
    if not path.startswith("/") or posixpath.normpath(path) != path:
        raise CanonicalizationError(f"{field} must be a normalized absolute POSIX path")
    return path


def _required_false(value: Any, *, field: str) -> bool:
    result = _strict_bool(value, field=field)
    if result:
        raise CanonicalizationError(f"{field} must be false")
    return result


def _lower_hex(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise CanonicalizationError(
            f"{field} must use exact lowercase hexadecimal encoding"
        )
    return value


def _public_key_bytes(value: Any, *, field: str) -> bytes:
    encoded = _lower_hex(value, field=field, pattern=_HASH_RE)
    public_key = bytes.fromhex(encoded)
    if not ed25519_public_key_is_valid(public_key):
        raise CanonicalizationError(
            f"{field} is not a canonical Ed25519 main-subgroup public key"
        )
    return public_key


def _optional_hash(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return canonical_hash(value, field=field)


def _manifest_identity(
    kind: OperationalManifestKindV4, payload: Mapping[str, Any]
) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": f"RiskYieldMMOperational{kind.value}ManifestIdentityV4_5",
            "payload": dict(payload),
            "schema_version": OPERATIONAL_MANIFEST_SCHEMA_VERSION,
        }
    )


def _manifest_mapping(
    *, kind: OperationalManifestKindV4, manifest_id: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "manifest_id": manifest_id,
        "manifest_type": kind.value,
        **dict(payload),
        "schema_version": OPERATIONAL_MANIFEST_SCHEMA_VERSION,
    }


def _require_manifest_envelope(
    payload: Mapping[str, Any],
    *,
    kind: OperationalManifestKindV4,
    fields: frozenset[str],
    context: str,
) -> None:
    require_exact_keys(
        payload,
        expected=fields
        | {
            "canonicalization_version",
            "manifest_id",
            "manifest_type",
            "schema_version",
        },
        context=context,
    )
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError(f"{context} canonicalization version differs")
    if payload["schema_version"] != OPERATIONAL_MANIFEST_SCHEMA_VERSION:
        raise CanonicalizationError(f"{context} schema version differs")
    if payload["manifest_type"] != kind.value:
        raise CanonicalizationError(f"{context} manifest type differs")


def _require_manifest_identity(payload: Mapping[str, Any], actual: str) -> None:
    expected = canonical_hash(payload["manifest_id"], field="manifest_id")
    if expected != actual:
        raise CanonicalizationError("manifest_id differs from canonical content")


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectorReleaseManifestV4:
    release_name: str
    release_version: str
    source_tree_sha256: str
    build_artifact_sha256: str
    entrypoint: str
    parser_policy_root_sha256: str

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.COLLECTOR_RELEASE
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "release_name",
            "release_version",
            "source_tree_sha256",
            "build_artifact_sha256",
            "entrypoint",
            "parser_policy_root_sha256",
        }
    )

    def __post_init__(self) -> None:
        for field_name in ("release_name", "release_version", "entrypoint"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_tree_sha256",
            "build_artifact_sha256",
            "parser_policy_root_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )

    def identity_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CollectorReleaseManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(**{name: payload[name] for name in cls._FIELDS})
        _require_manifest_identity(payload, item.manifest_id)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class DependencyLockManifestV4:
    lock_format: str
    lock_file_sha256: str
    wheelhouse_root_sha256: str
    distribution_count: int
    require_hashes: bool
    only_binary: bool
    fully_pinned: bool

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.DEPENDENCY_LOCK
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "lock_format",
            "lock_file_sha256",
            "wheelhouse_root_sha256",
            "distribution_count",
            "require_hashes",
            "only_binary",
            "fully_pinned",
        }
    )

    def __post_init__(self) -> None:
        lock_format = canonical_identifier(self.lock_format, field="lock_format")
        if lock_format != DEPENDENCY_LOCK_FORMAT:
            raise CanonicalizationError("dependency lock format is not reviewed")
        object.__setattr__(self, "lock_format", lock_format)
        for field_name in ("lock_file_sha256", "wheelhouse_root_sha256"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "distribution_count",
            canonical_safe_int(
                self.distribution_count, field="distribution_count", minimum=1
            ),
        )
        for field_name in ("require_hashes", "only_binary", "fully_pinned"):
            object.__setattr__(
                self,
                field_name,
                _required_true(getattr(self, field_name), field=field_name),
            )

    def identity_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DependencyLockManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(**{name: payload[name] for name in cls._FIELDS})
        _require_manifest_identity(payload, item.manifest_id)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsTrustStoreManifestV4:
    bundle_format: str
    ca_bundle_sha256: str
    ca_bundle_size_bytes: int
    ca_certificate_count: int
    ca_der_set_root_sha256: str
    openssl_verify_purpose: str

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.TLS_TRUST_STORE
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "bundle_format",
            "ca_bundle_sha256",
            "ca_bundle_size_bytes",
            "ca_certificate_count",
            "ca_der_set_root_sha256",
            "openssl_verify_purpose",
        }
    )

    def __post_init__(self) -> None:
        bundle_format = canonical_identifier(self.bundle_format, field="bundle_format")
        if bundle_format != TLS_TRUST_STORE_FORMAT:
            raise CanonicalizationError("TLS trust-store format is not reviewed")
        object.__setattr__(self, "bundle_format", bundle_format)
        purpose = canonical_identifier(
            self.openssl_verify_purpose, field="openssl_verify_purpose"
        )
        if purpose != TLS_VERIFY_PURPOSE:
            raise CanonicalizationError("TLS verification purpose is not SERVER_AUTH")
        object.__setattr__(self, "openssl_verify_purpose", purpose)
        for field_name in ("ca_bundle_sha256", "ca_der_set_root_sha256"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "ca_bundle_size_bytes",
            canonical_safe_int(
                self.ca_bundle_size_bytes,
                field="ca_bundle_size_bytes",
                minimum=1,
                maximum=64 * 1024 * 1024,
            ),
        )
        object.__setattr__(
            self,
            "ca_certificate_count",
            canonical_safe_int(
                self.ca_certificate_count,
                field="ca_certificate_count",
                minimum=1,
                maximum=100_000,
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TlsTrustStoreManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(**{name: payload[name] for name in cls._FIELDS})
        _require_manifest_identity(payload, item.manifest_id)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ChronydLaunchPolicyV48B:
    """Exact launch-time closure required for the governed chronyd process."""

    launch_profile: str
    supervisor_profile: str
    command_proxy_profile: str
    systemd_unit_name: str
    systemd_unit_path: str
    systemd_unit_sha256: str
    chronyd_executable_path: str
    chronyd_executable_sha256: str
    effective_config_sha256: str
    printed_config_sha256: str
    fixed_environment_sha256: str
    runtime_directory_path: str
    chronyd_socket_directory_path: str
    supervisor_socket_directory_path: str
    real_command_socket_path: str
    notify_socket_path: str
    read_only_api_socket_path: str
    post_drop_user_name: str
    post_drop_uid: int
    post_drop_gid: int
    lsm_profile: str
    ready_timeout_milliseconds: int
    maximum_datagram_bytes: int

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "launch_profile",
            "supervisor_profile",
            "command_proxy_profile",
            "systemd_unit_name",
            "systemd_unit_path",
            "systemd_unit_sha256",
            "chronyd_executable_path",
            "chronyd_executable_sha256",
            "effective_config_sha256",
            "printed_config_sha256",
            "fixed_environment_sha256",
            "runtime_directory_path",
            "chronyd_socket_directory_path",
            "supervisor_socket_directory_path",
            "real_command_socket_path",
            "notify_socket_path",
            "read_only_api_socket_path",
            "post_drop_user_name",
            "post_drop_uid",
            "post_drop_gid",
            "lsm_profile",
            "ready_timeout_milliseconds",
            "maximum_datagram_bytes",
        }
    )

    def __post_init__(self) -> None:
        reviewed_profiles = (
            ("launch_profile", CHRONYD_LAUNCH_PROFILE),
            ("supervisor_profile", CHRONYD_SUPERVISOR_PROFILE),
            ("command_proxy_profile", CHRONYD_COMMAND_PROXY_PROFILE),
        )
        for field_name, required_profile in reviewed_profiles:
            profile = canonical_identifier(getattr(self, field_name), field=field_name)
            if profile != required_profile:
                raise CanonicalizationError(
                    f"{field_name} is not the reviewed chronyd profile"
                )
            object.__setattr__(self, field_name, profile)

        unit_name = canonical_identifier(
            self.systemd_unit_name, field="systemd_unit_name", maximum=256
        )
        if (
            "/" in unit_name
            or not unit_name.endswith(".service")
            or unit_name == ".service"
        ):
            raise CanonicalizationError(
                "systemd_unit_name must be a slash-free .service basename"
            )
        object.__setattr__(self, "systemd_unit_name", unit_name)

        path_fields = (
            "systemd_unit_path",
            "chronyd_executable_path",
            "runtime_directory_path",
            "chronyd_socket_directory_path",
            "supervisor_socket_directory_path",
            "real_command_socket_path",
            "notify_socket_path",
            "read_only_api_socket_path",
        )
        for field_name in path_fields:
            object.__setattr__(
                self,
                field_name,
                _canonical_absolute_posix_path(
                    getattr(self, field_name), field=field_name
                ),
            )
        if posixpath.basename(self.systemd_unit_path) != self.systemd_unit_name:
            raise CanonicalizationError(
                "systemd_unit_name must equal the systemd unit path basename"
            )
        if self.runtime_directory_path == "/":
            raise CanonicalizationError(
                "runtime_directory_path must be a dedicated non-root directory"
            )
        runtime_prefix = f"{self.runtime_directory_path}/"
        for field_name in (
            "chronyd_socket_directory_path",
            "supervisor_socket_directory_path",
        ):
            directory_path = getattr(self, field_name)
            if posixpath.dirname(
                directory_path
            ) != self.runtime_directory_path or not directory_path.startswith(
                runtime_prefix
            ):
                raise CanonicalizationError(
                    f"{field_name} must be a direct child of runtime_directory_path"
                )
        expected_socket_parents = {
            "real_command_socket_path": self.chronyd_socket_directory_path,
            "notify_socket_path": self.supervisor_socket_directory_path,
            "read_only_api_socket_path": self.supervisor_socket_directory_path,
        }
        for field_name in (
            "real_command_socket_path",
            "notify_socket_path",
            "read_only_api_socket_path",
        ):
            socket_path = getattr(self, field_name)
            if posixpath.dirname(socket_path) != expected_socket_parents[field_name]:
                raise CanonicalizationError(
                    f"{field_name} must be directly contained by its reviewed owner directory"
                )
            if len(socket_path.encode("utf-8")) >= 108:
                raise CanonicalizationError(
                    f"{field_name} exceeds Linux sockaddr_un capacity"
                )
        if (
            len(self.supervisor_socket_directory_path.encode("utf-8"))
            + CHRONYD_QUERY_SOCKET_PATH_SUFFIX_BYTES
            >= 108
        ):
            raise CanonicalizationError(
                "supervisor_socket_directory_path leaves insufficient query-socket headroom"
            )
        if len({getattr(self, field_name) for field_name in path_fields}) != len(
            path_fields
        ):
            raise CanonicalizationError("chronyd launch-policy paths must be distinct")

        for field_name in (
            "systemd_unit_sha256",
            "chronyd_executable_sha256",
            "effective_config_sha256",
            "printed_config_sha256",
            "fixed_environment_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.fixed_environment_sha256 != CHRONYD_FIXED_ENVIRONMENT_SHA256:
            raise CanonicalizationError(
                "fixed_environment_sha256 does not identify the reviewed environment"
            )

        user_name = canonical_identifier(
            self.post_drop_user_name, field="post_drop_user_name", maximum=32
        )
        if _POSIX_USER_NAME_RE.fullmatch(user_name) is None:
            raise CanonicalizationError(
                "post_drop_user_name must be a strict POSIX account name"
            )
        object.__setattr__(self, "post_drop_user_name", user_name)

        for field_name in ("post_drop_uid", "post_drop_gid"):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=1,
                    maximum=2_147_483_647,
                ),
            )
        object.__setattr__(
            self,
            "lsm_profile",
            canonical_identifier(self.lsm_profile, field="lsm_profile", maximum=512),
        )
        object.__setattr__(
            self,
            "ready_timeout_milliseconds",
            canonical_safe_int(
                self.ready_timeout_milliseconds,
                field="ready_timeout_milliseconds",
                minimum=250,
                maximum=30_000,
            ),
        )
        object.__setattr__(
            self,
            "maximum_datagram_bytes",
            canonical_safe_int(
                self.maximum_datagram_bytes,
                field="maximum_datagram_bytes",
                minimum=256,
                maximum=65_536,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ChronydLaunchPolicyV48B:
        require_exact_keys(payload, expected=cls._FIELDS, context=cls.__name__)
        return cls(**{name: payload[name] for name in cls._FIELDS})


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockSourcePolicyManifestV4:
    source_kind: str
    chrony_version: str
    chronyc_executable_path: str
    chronyc_executable_sha256: str
    chrony_config_path: str
    chrony_config_sha256: str
    chronyc_command_socket_path: str
    chronyc_command_timeout_milliseconds: int
    chronyc_max_output_bytes: int
    configured_source_set_root_sha256: str
    min_selectable_sources: int
    max_uncertainty_milliseconds: int
    max_sample_age_milliseconds: int
    require_synchronized: bool
    require_normal_leap: bool
    monotonic_domain_profile: str
    chronyd_launch_policy: ChronydLaunchPolicyV48B

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.CLOCK_SOURCE_POLICY
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "source_kind",
            "chrony_version",
            "chronyc_executable_path",
            "chronyc_executable_sha256",
            "chrony_config_path",
            "chrony_config_sha256",
            "chronyc_command_socket_path",
            "chronyc_command_timeout_milliseconds",
            "chronyc_max_output_bytes",
            "configured_source_set_root_sha256",
            "min_selectable_sources",
            "max_uncertainty_milliseconds",
            "max_sample_age_milliseconds",
            "require_synchronized",
            "require_normal_leap",
            "monotonic_domain_profile",
            "chronyd_launch_policy",
        }
    )

    def __post_init__(self) -> None:
        source_kind = canonical_identifier(self.source_kind, field="source_kind")
        if source_kind != CLOCK_SOURCE_KIND:
            raise CanonicalizationError("clock source kind is not reviewed")
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(
            self,
            "chrony_version",
            canonical_identifier(self.chrony_version, field="chrony_version"),
        )
        for field_name in (
            "chronyc_executable_path",
            "chrony_config_path",
            "chronyc_command_socket_path",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonical_absolute_posix_path(
                    getattr(self, field_name), field=field_name
                ),
            )
        domain_profile = canonical_identifier(
            self.monotonic_domain_profile, field="monotonic_domain_profile"
        )
        if domain_profile != MONOTONIC_DOMAIN_PROFILE:
            raise CanonicalizationError("monotonic-domain profile is not reviewed")
        object.__setattr__(self, "monotonic_domain_profile", domain_profile)
        for field_name in (
            "chronyc_executable_sha256",
            "chrony_config_sha256",
            "configured_source_set_root_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "chronyc_command_timeout_milliseconds",
            canonical_safe_int(
                self.chronyc_command_timeout_milliseconds,
                field="chronyc_command_timeout_milliseconds",
                minimum=250,
                maximum=30_000,
            ),
        )
        object.__setattr__(
            self,
            "chronyc_max_output_bytes",
            canonical_safe_int(
                self.chronyc_max_output_bytes,
                field="chronyc_max_output_bytes",
                minimum=1_024,
                maximum=1_048_576,
            ),
        )
        object.__setattr__(
            self,
            "min_selectable_sources",
            canonical_safe_int(
                self.min_selectable_sources,
                field="min_selectable_sources",
                minimum=1,
                maximum=64,
            ),
        )
        object.__setattr__(
            self,
            "max_uncertainty_milliseconds",
            canonical_safe_int(
                self.max_uncertainty_milliseconds,
                field="max_uncertainty_milliseconds",
                minimum=1,
                maximum=60_000,
            ),
        )
        object.__setattr__(
            self,
            "max_sample_age_milliseconds",
            canonical_safe_int(
                self.max_sample_age_milliseconds,
                field="max_sample_age_milliseconds",
                minimum=1,
                maximum=3_600_000,
            ),
        )
        object.__setattr__(
            self,
            "require_synchronized",
            _required_true(self.require_synchronized, field="require_synchronized"),
        )
        object.__setattr__(
            self,
            "require_normal_leap",
            _required_true(self.require_normal_leap, field="require_normal_leap"),
        )
        if type(self.chronyd_launch_policy) is not ChronydLaunchPolicyV48B:
            raise CanonicalizationError(
                "chronyd_launch_policy accepts exact ChronydLaunchPolicyV48B values only"
            )
        if (
            self.chronyc_command_socket_path
            != self.chronyd_launch_policy.read_only_api_socket_path
        ):
            raise CanonicalizationError(
                "chronyc command socket must equal the governed read-only API socket"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: (
                self.chronyd_launch_policy.as_dict()
                if name == "chronyd_launch_policy"
                else getattr(self, name)
            )
            for name in self._FIELDS
        }

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ClockSourcePolicyManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(
            **{
                name: (
                    ChronydLaunchPolicyV48B.from_mapping(payload[name])
                    if name == "chronyd_launch_policy"
                    else payload[name]
                )
                for name in cls._FIELDS
            }
        )
        _require_manifest_identity(payload, item.manifest_id)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeArtifactMemberV49B:
    """One exact signed member of the V4.9B loaded runtime closure."""

    role: str
    path: str
    size_bytes: int
    sha256: str
    require_executable: bool

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"role", "path", "size_bytes", "sha256", "require_executable"}
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "role",
            canonical_identifier(self.role, field="artifact_role", maximum=256),
        )
        object.__setattr__(
            self,
            "path",
            _canonical_absolute_posix_path(self.path, field="artifact_path"),
        )
        object.__setattr__(
            self,
            "size_bytes",
            canonical_safe_int(
                self.size_bytes,
                field="artifact_size_bytes",
                minimum=0,
                maximum=1 << 30,
            ),
        )
        object.__setattr__(
            self,
            "sha256",
            canonical_hash(self.sha256, field="artifact_sha256"),
        )
        if type(self.require_executable) is not bool:
            raise CanonicalizationError("require_executable must be a boolean")

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeArtifactMemberV49B:
        require_exact_keys(payload, expected=cls._FIELDS, context=cls.__name__)
        return cls(**{name: payload[name] for name in cls._FIELDS})


@dataclass(frozen=True, slots=True, kw_only=True)
class InstalledDistributionClosureV49B:
    """Exact installed files, version, root, and import origin for one dependency."""

    distribution_name: str
    distribution_version: str
    distribution_origin: str
    module_origin: str
    members: tuple[RuntimeArtifactMemberV49B, ...]

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "distribution_name",
            "distribution_version",
            "distribution_origin",
            "module_origin",
            "members",
        }
    )

    def __post_init__(self) -> None:
        name = canonical_identifier(
            self.distribution_name,
            field="distribution_name",
            maximum=128,
        )
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        if (
            name != normalized_name
            or name not in TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B
        ):
            raise CanonicalizationError(
                "distribution_name is not an exact reviewed V4.9B dependency"
            )
        object.__setattr__(self, "distribution_name", name)
        object.__setattr__(
            self,
            "distribution_version",
            canonical_identifier(
                self.distribution_version,
                field="distribution_version",
                maximum=128,
            ),
        )
        for field_name in ("distribution_origin", "module_origin"):
            object.__setattr__(
                self,
                field_name,
                _canonical_absolute_posix_path(
                    getattr(self, field_name), field=field_name
                ),
            )
        if (
            type(self.members) is not tuple
            or not self.members
            or any(
                type(member) is not RuntimeArtifactMemberV49B for member in self.members
            )
        ):
            raise CanonicalizationError(
                "installed distribution requires exact non-empty artifact members"
            )
        ordered = tuple(sorted(self.members, key=lambda member: member.path))
        if ordered != self.members:
            raise CanonicalizationError(
                "installed distribution members must be sorted by absolute path"
            )
        paths = tuple(member.path for member in self.members)
        if len(paths) != len(set(paths)):
            raise CanonicalizationError(
                "installed distribution member paths must be unique"
            )
        if self.module_origin not in set(paths):
            raise CanonicalizationError(
                "installed distribution module origin is not a signed member"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "distribution_name": self.distribution_name,
            "distribution_version": self.distribution_version,
            "distribution_origin": self.distribution_origin,
            "module_origin": self.module_origin,
            "members": [member.as_dict() for member in self.members],
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> InstalledDistributionClosureV49B:
        require_exact_keys(payload, expected=cls._FIELDS, context=cls.__name__)
        raw_members = payload["members"]
        if isinstance(raw_members, (str, bytes, bytearray)) or not isinstance(
            raw_members, Sequence
        ):
            raise CanonicalizationError("distribution members must be a sequence")
        return cls(
            distribution_name=payload["distribution_name"],
            distribution_version=payload["distribution_version"],
            distribution_origin=payload["distribution_origin"],
            module_origin=payload["module_origin"],
            members=tuple(
                RuntimeArtifactMemberV49B.from_mapping(member) for member in raw_members
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsWebSocketDriverPolicyV49B:
    """Signed member-by-member runtime closure for the exact V4.9 driver."""

    driver_profile: str
    python_implementation: str
    python_version: str
    openssl_version: str
    runtime_artifacts: tuple[RuntimeArtifactMemberV49B, ...]
    python_bytecode_cache_artifacts: tuple[RuntimeArtifactMemberV49B, ...]
    installed_distributions: tuple[InstalledDistributionClosureV49B, ...]

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "driver_profile",
            "python_implementation",
            "python_version",
            "openssl_version",
            "runtime_artifacts",
            "python_bytecode_cache_artifacts",
            "installed_distributions",
        }
    )

    def __post_init__(self) -> None:
        profile = canonical_identifier(self.driver_profile, field="driver_profile")
        if profile != TLS_WEBSOCKET_DRIVER_PROFILE_V49B:
            raise CanonicalizationError("TLS/WebSocket driver profile is not reviewed")
        object.__setattr__(self, "driver_profile", profile)
        for field_name in (
            "python_implementation",
            "python_version",
            "openssl_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        if type(self.runtime_artifacts) is not tuple or any(
            type(member) is not RuntimeArtifactMemberV49B
            for member in self.runtime_artifacts
        ):
            raise CanonicalizationError(
                "driver runtime artifacts must be an exact tuple"
            )
        artifacts = tuple(sorted(self.runtime_artifacts, key=lambda item: item.role))
        if artifacts != self.runtime_artifacts:
            raise CanonicalizationError("driver runtime artifacts must be role-sorted")
        roles = tuple(member.role for member in artifacts)
        paths = tuple(member.path for member in artifacts)
        if frozenset(roles) != TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B or len(
            roles
        ) != len(TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B):
            raise CanonicalizationError(
                "driver runtime artifacts do not contain the exact required roles"
            )
        if len(paths) != len(set(paths)):
            raise CanonicalizationError("driver runtime artifact paths must be unique")
        if not next(
            member for member in artifacts if member.role == "PYTHON_EXECUTABLE"
        ).require_executable:
            raise CanonicalizationError("Python executable must require execute access")
        object.__setattr__(self, "runtime_artifacts", artifacts)

        if type(self.python_bytecode_cache_artifacts) is not tuple or any(
            type(member) is not RuntimeArtifactMemberV49B
            for member in self.python_bytecode_cache_artifacts
        ):
            raise CanonicalizationError(
                "Python bytecode-cache artifacts must be an exact tuple"
            )
        bytecode_artifacts = tuple(
            sorted(
                self.python_bytecode_cache_artifacts,
                key=lambda item: item.role,
            )
        )
        if bytecode_artifacts != self.python_bytecode_cache_artifacts:
            raise CanonicalizationError(
                "Python bytecode-cache artifacts must be role-sorted"
            )
        bytecode_roles = tuple(member.role for member in bytecode_artifacts)
        bytecode_paths = tuple(member.path for member in bytecode_artifacts)
        if frozenset(
            bytecode_roles
        ) != TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B or len(
            bytecode_roles
        ) != len(TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B):
            raise CanonicalizationError(
                "Python bytecode-cache closure does not contain the exact three roles"
            )
        if any(member.require_executable for member in bytecode_artifacts):
            raise CanonicalizationError(
                "Python bytecode-cache artifacts must not require execute access"
            )
        if len(bytecode_paths) != len(set(bytecode_paths)):
            raise CanonicalizationError(
                "Python bytecode-cache artifact paths must be unique"
            )
        object.__setattr__(
            self,
            "python_bytecode_cache_artifacts",
            bytecode_artifacts,
        )

        if type(self.installed_distributions) is not tuple or any(
            type(item) is not InstalledDistributionClosureV49B
            for item in self.installed_distributions
        ):
            raise CanonicalizationError(
                "installed driver distributions must be an exact tuple"
            )
        distributions = tuple(
            sorted(
                self.installed_distributions,
                key=lambda item: item.distribution_name,
            )
        )
        if distributions != self.installed_distributions:
            raise CanonicalizationError(
                "installed driver distributions must be name-sorted"
            )
        names = tuple(item.distribution_name for item in distributions)
        if frozenset(names) != TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B or len(
            names
        ) != len(TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B):
            raise CanonicalizationError(
                "installed distributions do not contain the exact driver dependencies"
            )
        all_paths = (
            paths
            + bytecode_paths
            + tuple(
                member.path
                for distribution in distributions
                for member in distribution.members
            )
        )
        if len(all_paths) != len(set(all_paths)):
            raise CanonicalizationError(
                "TLS/WebSocket policy contains duplicate artifact paths"
            )
        object.__setattr__(self, "installed_distributions", distributions)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "driver_profile": self.driver_profile,
            "python_implementation": self.python_implementation,
            "python_version": self.python_version,
            "openssl_version": self.openssl_version,
            "runtime_artifacts": [
                member.as_dict() for member in self.runtime_artifacts
            ],
            "python_bytecode_cache_artifacts": [
                member.as_dict() for member in self.python_bytecode_cache_artifacts
            ],
            "installed_distributions": [
                distribution.as_dict() for distribution in self.installed_distributions
            ],
        }

    @property
    def policy_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": "RiskYieldMMTlsWebSocketDriverPolicyIdentityV49B",
                "payload": self.identity_payload(),
                "schema_version": OPERATIONAL_MANIFEST_SCHEMA_VERSION,
            }
        )

    @property
    def installed_distribution_root_sha256(self) -> str:
        """Derive the signed distribution root from every explicit file member."""

        return sha256_digest(
            {
                "distributions": [
                    distribution.as_dict()
                    for distribution in self.installed_distributions
                ],
                "domain": "RiskYieldMMInstalledDriverDistributionClosureV49B",
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "policy_id": self.policy_id}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TlsWebSocketDriverPolicyV49B:
        require_exact_keys(
            payload,
            expected=cls._FIELDS | {"policy_id"},
            context=cls.__name__,
        )
        raw_artifacts = payload["runtime_artifacts"]
        raw_bytecode_artifacts = payload["python_bytecode_cache_artifacts"]
        raw_distributions = payload["installed_distributions"]
        if isinstance(raw_artifacts, (str, bytes, bytearray)) or not isinstance(
            raw_artifacts, Sequence
        ):
            raise CanonicalizationError("runtime artifacts must be a sequence")
        if isinstance(
            raw_bytecode_artifacts, (str, bytes, bytearray)
        ) or not isinstance(raw_bytecode_artifacts, Sequence):
            raise CanonicalizationError(
                "Python bytecode-cache artifacts must be a sequence"
            )
        if isinstance(raw_distributions, (str, bytes, bytearray)) or not isinstance(
            raw_distributions, Sequence
        ):
            raise CanonicalizationError("installed distributions must be a sequence")
        item = cls(
            driver_profile=payload["driver_profile"],
            python_implementation=payload["python_implementation"],
            python_version=payload["python_version"],
            openssl_version=payload["openssl_version"],
            runtime_artifacts=tuple(
                RuntimeArtifactMemberV49B.from_mapping(member)
                for member in raw_artifacts
            ),
            python_bytecode_cache_artifacts=tuple(
                RuntimeArtifactMemberV49B.from_mapping(member)
                for member in raw_bytecode_artifacts
            ),
            installed_distributions=tuple(
                InstalledDistributionClosureV49B.from_mapping(distribution)
                for distribution in raw_distributions
            ),
        )
        if (
            canonical_hash(payload["policy_id"], field="driver_policy_id")
            != item.policy_id
        ):
            raise CanonicalizationError(
                "TLS/WebSocket driver policy ID differs from canonical members"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeEnvironmentManifestV4:
    python_implementation: str
    python_version: str
    python_executable_sha256: str
    platform_tag: str
    openssl_version: str
    installed_distribution_root_sha256: str
    dependency_lock_manifest_id: str
    collector_release_manifest_id: str
    tls_trust_store_manifest_id: str
    clock_source_policy_manifest_id: str
    isolated_mode: bool
    user_site_enabled: bool
    tls_websocket_driver_policy: TlsWebSocketDriverPolicyV49B | None = None
    transport_capacity_policy_v49f: TransportCapacityPolicyV49F | None = None

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.RUNTIME_ENVIRONMENT
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "python_implementation",
            "python_version",
            "python_executable_sha256",
            "platform_tag",
            "openssl_version",
            "installed_distribution_root_sha256",
            "dependency_lock_manifest_id",
            "collector_release_manifest_id",
            "tls_trust_store_manifest_id",
            "clock_source_policy_manifest_id",
            "isolated_mode",
            "user_site_enabled",
            "tls_websocket_driver_policy",
            "transport_capacity_policy_v49f",
        }
    )

    def __post_init__(self) -> None:
        for field_name in (
            "python_implementation",
            "python_version",
            "platform_tag",
            "openssl_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "python_executable_sha256",
            "installed_distribution_root_sha256",
            "dependency_lock_manifest_id",
            "collector_release_manifest_id",
            "tls_trust_store_manifest_id",
            "clock_source_policy_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "isolated_mode",
            _required_true(self.isolated_mode, field="isolated_mode"),
        )
        object.__setattr__(
            self,
            "user_site_enabled",
            _required_false(self.user_site_enabled, field="user_site_enabled"),
        )
        if (
            self.tls_websocket_driver_policy is not None
            and type(self.tls_websocket_driver_policy)
            is not TlsWebSocketDriverPolicyV49B
        ):
            raise CanonicalizationError(
                "tls_websocket_driver_policy must be exact V4.9B policy or null"
            )
        if self.tls_websocket_driver_policy is not None:
            driver = self.tls_websocket_driver_policy
            python_artifact = next(
                member
                for member in driver.runtime_artifacts
                if member.role == "PYTHON_EXECUTABLE"
            )
            if (
                self.python_implementation != driver.python_implementation
                or self.python_version != driver.python_version
                or self.python_executable_sha256 != python_artifact.sha256
                or self.openssl_version != driver.openssl_version
                or self.installed_distribution_root_sha256
                != driver.installed_distribution_root_sha256
            ):
                raise CanonicalizationError(
                    "runtime environment differs from its nested V4.9B driver closure"
                )
        if (
            self.transport_capacity_policy_v49f is not None
            and type(self.transport_capacity_policy_v49f)
            is not TransportCapacityPolicyV49F
        ):
            raise CanonicalizationError(
                "transport_capacity_policy_v49f must be exact V4.9F policy or null"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: (
                self.tls_websocket_driver_policy.as_dict()
                if name == "tls_websocket_driver_policy"
                and self.tls_websocket_driver_policy is not None
                else self.transport_capacity_policy_v49f.as_dict()
                if name == "transport_capacity_policy_v49f"
                and self.transport_capacity_policy_v49f is not None
                else getattr(self, name)
            )
            for name in self._FIELDS
        }

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RuntimeEnvironmentManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(
            **{
                name: (
                    TlsWebSocketDriverPolicyV49B.from_mapping(payload[name])
                    if name == "tls_websocket_driver_policy"
                    and payload[name] is not None
                    else TransportCapacityPolicyV49F.from_mapping(payload[name])
                    if name == "transport_capacity_policy_v49f"
                    and payload[name] is not None
                    else payload[name]
                )
                for name in cls._FIELDS
            }
        )
        _require_manifest_identity(payload, item.manifest_id)
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class CollectorKeyAuthorizationManifestV4:
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    usage: str
    collector_release_manifest_id: str
    valid_from: datetime
    valid_until: datetime

    KIND: ClassVar[OperationalManifestKindV4] = (
        OperationalManifestKindV4.COLLECTOR_KEY_AUTHORIZATION
    )
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "collector_attestation_key_id",
            "collector_attestation_public_key_hex",
            "usage",
            "collector_release_manifest_id",
            "valid_from",
            "valid_until",
        }
    )

    def __post_init__(self) -> None:
        public_key = _public_key_bytes(
            self.collector_attestation_public_key_hex,
            field="collector_attestation_public_key_hex",
        )
        object.__setattr__(
            self, "collector_attestation_public_key_hex", public_key.hex()
        )
        derived = derive_transport_attestation_key_id(public_key)
        supplied = canonical_hash(
            self.collector_attestation_key_id, field="collector_attestation_key_id"
        )
        if supplied != derived:
            raise CanonicalizationError(
                "collector attestation key ID differs from its transport public key"
            )
        object.__setattr__(self, "collector_attestation_key_id", supplied)
        usage = canonical_identifier(self.usage, field="usage")
        if usage != COLLECTOR_KEY_USAGE:
            raise CanonicalizationError("collector key usage is not transport-only")
        object.__setattr__(self, "usage", usage)
        object.__setattr__(
            self,
            "collector_release_manifest_id",
            canonical_hash(
                self.collector_release_manifest_id,
                field="collector_release_manifest_id",
            ),
        )
        valid_from = utc_datetime(self.valid_from, field="valid_from")
        valid_until = utc_datetime(self.valid_until, field="valid_until")
        if valid_until <= valid_from:
            raise CanonicalizationError(
                "collector key authorization must have a positive validity interval"
            )
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "valid_until", valid_until)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "collector_attestation_key_id": self.collector_attestation_key_id,
            "collector_attestation_public_key_hex": (
                self.collector_attestation_public_key_hex
            ),
            "collector_release_manifest_id": self.collector_release_manifest_id,
            "usage": self.usage,
            "valid_from": utc_iso(self.valid_from),
            "valid_until": utc_iso(self.valid_until),
        }

    @property
    def manifest_id(self) -> str:
        return _manifest_identity(self.KIND, self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _manifest_mapping(
            kind=self.KIND,
            manifest_id=self.manifest_id,
            payload=self.identity_payload(),
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> CollectorKeyAuthorizationManifestV4:
        _require_manifest_envelope(
            payload, kind=cls.KIND, fields=cls._FIELDS, context=cls.__name__
        )
        item = cls(**{name: payload[name] for name in cls._FIELDS})
        _require_manifest_identity(payload, item.manifest_id)
        return item


OperationalChildManifestV4: TypeAlias = (
    CollectorReleaseManifestV4
    | DependencyLockManifestV4
    | TlsTrustStoreManifestV4
    | ClockSourcePolicyManifestV4
    | RuntimeEnvironmentManifestV4
    | CollectorKeyAuthorizationManifestV4
)


def derive_deployment_signing_key_id(public_key_bytes: bytes) -> str:
    """Derive a deployment-role key ID, distinct from all other key domains."""

    if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
        raise CanonicalizationError(
            "deployment Ed25519 public key must contain exactly 32 bytes"
        )
    if not ed25519_public_key_is_valid(public_key_bytes):
        raise CanonicalizationError(
            "deployment Ed25519 public key is not a valid main-subgroup point"
        )
    return sha256_digest(
        {
            "algorithm": DEPLOYMENT_SIGNATURE_ALGORITHM,
            "domain": "RiskYieldMMOperationalDeploymentSigningPublicKeyV4_5",
            "public_key_hex": public_key_bytes.hex(),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class DeploymentRoleKeyV4:
    key_id: str
    public_key_hex: str
    algorithm: str = DEPLOYMENT_SIGNATURE_ALGORITHM

    def __post_init__(self) -> None:
        algorithm = canonical_identifier(self.algorithm, field="algorithm")
        if algorithm != DEPLOYMENT_SIGNATURE_ALGORITHM:
            raise CanonicalizationError("deployment signing algorithm is not ED25519")
        object.__setattr__(self, "algorithm", algorithm)
        public_key = _public_key_bytes(self.public_key_hex, field="public_key_hex")
        object.__setattr__(self, "public_key_hex", public_key.hex())
        supplied = canonical_hash(self.key_id, field="key_id")
        derived = derive_deployment_signing_key_id(public_key)
        if supplied != derived:
            raise CanonicalizationError("deployment key ID differs from its public key")
        object.__setattr__(self, "key_id", supplied)

    @property
    def public_key_bytes(self) -> bytes:
        return bytes.fromhex(self.public_key_hex)

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "public_key_hex": self.public_key_hex,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DeploymentRoleKeyV4:
        require_exact_keys(
            payload,
            expected={"algorithm", "key_id", "public_key_hex"},
            context=cls.__name__,
        )
        return cls(
            algorithm=payload["algorithm"],
            key_id=payload["key_id"],
            public_key_hex=payload["public_key_hex"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class DeploymentTrustRootV4:
    root_version: int
    deployment_role_threshold: int
    deployment_keys: tuple[DeploymentRoleKeyV4, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "root_version",
            canonical_safe_int(self.root_version, field="root_version", minimum=1),
        )
        if not isinstance(self.deployment_keys, tuple) or not self.deployment_keys:
            raise CanonicalizationError(
                "deployment_keys must be a non-empty exact tuple"
            )
        if any(type(item) is not DeploymentRoleKeyV4 for item in self.deployment_keys):
            raise CanonicalizationError(
                "deployment_keys accepts exact DeploymentRoleKeyV4 values only"
            )
        ordered = tuple(sorted(self.deployment_keys, key=lambda item: item.key_id))
        if len({item.key_id for item in ordered}) != len(ordered):
            raise CanonicalizationError("deployment trust root contains duplicate keys")
        object.__setattr__(self, "deployment_keys", ordered)
        object.__setattr__(
            self,
            "deployment_role_threshold",
            canonical_safe_int(
                self.deployment_role_threshold,
                field="deployment_role_threshold",
                minimum=1,
                maximum=len(ordered),
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "deployment_role": {
                "key_ids": [item.key_id for item in self.deployment_keys],
                "name": DEPLOYMENT_ROLE_NAME,
                "threshold": self.deployment_role_threshold,
            },
            "keys": [item.as_dict() for item in self.deployment_keys],
            "root_version": self.root_version,
        }

    @property
    def trust_root_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": "RiskYieldMMOperationalDeploymentTrustRootIdentityV4_5",
                "payload": self.identity_payload(),
                "schema_version": DEPLOYMENT_TRUST_ROOT_SCHEMA_VERSION,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": DEPLOYMENT_TRUST_ROOT_SCHEMA_VERSION,
            "trust_root_id": self.trust_root_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DeploymentTrustRootV4:
        require_exact_keys(
            payload,
            expected={
                "canonicalization_version",
                "deployment_role",
                "keys",
                "root_version",
                "schema_version",
                "trust_root_id",
            },
            context=cls.__name__,
        )
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError(
                "deployment trust-root canonicalization differs"
            )
        if payload["schema_version"] != DEPLOYMENT_TRUST_ROOT_SCHEMA_VERSION:
            raise CanonicalizationError("deployment trust-root schema differs")
        role = payload["deployment_role"]
        require_exact_keys(
            role,
            expected={"key_ids", "name", "threshold"},
            context="deployment_role",
        )
        if role["name"] != DEPLOYMENT_ROLE_NAME:
            raise CanonicalizationError("deployment trust-root role name differs")
        keys_value = payload["keys"]
        if not isinstance(keys_value, list):
            raise CanonicalizationError("deployment trust-root keys must be a list")
        keys = tuple(DeploymentRoleKeyV4.from_mapping(item) for item in keys_value)
        item = cls(
            root_version=payload["root_version"],
            deployment_role_threshold=role["threshold"],
            deployment_keys=keys,
        )
        if payload["keys"] != [key.as_dict() for key in item.deployment_keys]:
            raise CanonicalizationError(
                "deployment trust-root keys are not in canonical key-ID order"
            )
        if role["key_ids"] != [key.key_id for key in item.deployment_keys]:
            raise CanonicalizationError(
                "deployment role key IDs differ from key objects"
            )
        expected = canonical_hash(payload["trust_root_id"], field="trust_root_id")
        if expected != item.trust_root_id:
            raise CanonicalizationError(
                "trust_root_id differs from canonical trust-root content"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class DeploymentBundleV4:
    deployment_trust_root_id: str
    deployment_sequence: int
    parent_deployment_bundle_id: str | None
    valid_from: datetime
    valid_until: datetime
    environment_id: str
    authority_ceiling: DeploymentAuthorityCeilingV4
    collector_release_manifest_id: str
    dependency_lock_manifest_id: str
    tls_trust_store_manifest_id: str
    clock_source_policy_manifest_id: str
    runtime_environment_manifest_id: str
    collector_key_authorization_manifest_id: str

    _IDENTITY_FIELDS: ClassVar[tuple[str, ...]] = (
        "deployment_trust_root_id",
        "deployment_sequence",
        "parent_deployment_bundle_id",
        "valid_from",
        "valid_until",
        "environment_id",
        "authority_ceiling",
        "collector_release_manifest_id",
        "dependency_lock_manifest_id",
        "tls_trust_store_manifest_id",
        "clock_source_policy_manifest_id",
        "runtime_environment_manifest_id",
        "collector_key_authorization_manifest_id",
    )

    def __post_init__(self) -> None:
        for field_name in (
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "dependency_lock_manifest_id",
            "tls_trust_store_manifest_id",
            "clock_source_policy_manifest_id",
            "runtime_environment_manifest_id",
            "collector_key_authorization_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "deployment_sequence",
            canonical_safe_int(
                self.deployment_sequence, field="deployment_sequence", minimum=1
            ),
        )
        parent = _optional_hash(
            self.parent_deployment_bundle_id,
            field="parent_deployment_bundle_id",
        )
        if self.deployment_sequence == 1 and parent is not None:
            raise CanonicalizationError("deployment genesis cannot have a parent")
        if self.deployment_sequence > 1 and parent is None:
            raise CanonicalizationError("deployment successor requires a parent")
        object.__setattr__(self, "parent_deployment_bundle_id", parent)
        valid_from = utc_datetime(self.valid_from, field="valid_from")
        valid_until = utc_datetime(self.valid_until, field="valid_until")
        if valid_until <= valid_from:
            raise CanonicalizationError(
                "deployment bundle must have a positive validity interval"
            )
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(
            self,
            "environment_id",
            canonical_identifier(self.environment_id, field="environment_id"),
        )
        try:
            ceiling = DeploymentAuthorityCeilingV4(self.authority_ceiling)
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError(
                "deployment authority ceiling is unsupported"
            ) from exc
        if ceiling is not DeploymentAuthorityCeilingV4.PUBLIC_MARKET_DATA_CAPTURE_ONLY:
            raise CanonicalizationError("deployment exceeds the V4.5 authority ceiling")
        object.__setattr__(self, "authority_ceiling", ceiling)
        child_ids = (
            self.collector_release_manifest_id,
            self.dependency_lock_manifest_id,
            self.tls_trust_store_manifest_id,
            self.clock_source_policy_manifest_id,
            self.runtime_environment_manifest_id,
            self.collector_key_authorization_manifest_id,
        )
        if len(set(child_ids)) != len(child_ids):
            raise CanonicalizationError("deployment child manifest IDs must be unique")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "authority_ceiling": self.authority_ceiling.value,
            "clock_source_policy_manifest_id": self.clock_source_policy_manifest_id,
            "collector_key_authorization_manifest_id": (
                self.collector_key_authorization_manifest_id
            ),
            "collector_release_manifest_id": self.collector_release_manifest_id,
            "dependency_lock_manifest_id": self.dependency_lock_manifest_id,
            "deployment_sequence": self.deployment_sequence,
            "deployment_trust_root_id": self.deployment_trust_root_id,
            "environment_id": self.environment_id,
            "parent_deployment_bundle_id": self.parent_deployment_bundle_id,
            "runtime_environment_manifest_id": self.runtime_environment_manifest_id,
            "tls_trust_store_manifest_id": self.tls_trust_store_manifest_id,
            "valid_from": utc_iso(self.valid_from),
            "valid_until": utc_iso(self.valid_until),
        }

    @property
    def deployment_bundle_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": "RiskYieldMMOperationalDeploymentBundleIdentityV4_5",
                "payload": self.identity_payload(),
                "schema_version": DEPLOYMENT_BUNDLE_SCHEMA_VERSION,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "deployment_bundle_id": self.deployment_bundle_id,
            **self.identity_payload(),
            "schema_version": DEPLOYMENT_BUNDLE_SCHEMA_VERSION,
        }

    def child_manifest_ids_by_kind(
        self,
    ) -> dict[OperationalManifestKindV4, str]:
        """Return the bundle's exact, closed child-manifest mapping."""

        return {
            OperationalManifestKindV4.COLLECTOR_RELEASE: (
                self.collector_release_manifest_id
            ),
            OperationalManifestKindV4.DEPENDENCY_LOCK: (
                self.dependency_lock_manifest_id
            ),
            OperationalManifestKindV4.TLS_TRUST_STORE: (
                self.tls_trust_store_manifest_id
            ),
            OperationalManifestKindV4.CLOCK_SOURCE_POLICY: (
                self.clock_source_policy_manifest_id
            ),
            OperationalManifestKindV4.RUNTIME_ENVIRONMENT: (
                self.runtime_environment_manifest_id
            ),
            OperationalManifestKindV4.COLLECTOR_KEY_AUTHORIZATION: (
                self.collector_key_authorization_manifest_id
            ),
        }

    def child_manifest_id(self, kind: OperationalManifestKindV4) -> str:
        """Return the referenced child ID for one exact manifest kind."""

        if type(kind) is not OperationalManifestKindV4:
            raise TypeError("kind must be an exact OperationalManifestKindV4")
        return self.child_manifest_ids_by_kind()[kind]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DeploymentBundleV4:
        require_exact_keys(
            payload,
            expected=set(cls._IDENTITY_FIELDS)
            | {
                "canonicalization_version",
                "deployment_bundle_id",
                "schema_version",
            },
            context=cls.__name__,
        )
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("deployment canonicalization version differs")
        if payload["schema_version"] != DEPLOYMENT_BUNDLE_SCHEMA_VERSION:
            raise CanonicalizationError("deployment schema version differs")
        item = cls(**{name: payload[name] for name in cls._IDENTITY_FIELDS})
        expected = canonical_hash(
            payload["deployment_bundle_id"], field="deployment_bundle_id"
        )
        if expected != item.deployment_bundle_id:
            raise CanonicalizationError(
                "deployment_bundle_id differs from canonical bundle content"
            )
        return item


def dsse_pae_v1(payload_type: str, payload: bytes) -> bytes:
    """Return the exact DSSE v1 pre-authentication encoding."""

    normalized_type = canonical_identifier(
        payload_type, field="payload_type", maximum=512
    )
    if not isinstance(payload, bytes):
        raise TypeError("DSSE payload must be bytes")
    type_bytes = normalized_type.encode("utf-8")
    return b" ".join(
        (
            b"DSSEv1",
            str(len(type_bytes)).encode("ascii"),
            type_bytes,
            str(len(payload)).encode("ascii"),
            payload,
        )
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class DsseSignatureV4:
    key_id: str
    signature_base64: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", canonical_hash(self.key_id, field="key_id"))
        if (
            not isinstance(self.signature_base64, str)
            or len(self.signature_base64) > 128
            or _BASE64_RE.fullmatch(self.signature_base64) is None
        ):
            raise CanonicalizationError("DSSE signature has invalid base64 encoding")
        try:
            decoded = base64.b64decode(self.signature_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise CanonicalizationError(
                "DSSE signature has invalid base64 encoding"
            ) from exc
        if len(decoded) != 64:
            raise CanonicalizationError(
                "DSSE Ed25519 signature must contain exactly 64 bytes"
            )
        if base64.b64encode(decoded).decode("ascii") != self.signature_base64:
            raise CanonicalizationError("DSSE signature base64 is not canonical")

    @property
    def signature_bytes(self) -> bytes:
        return base64.b64decode(self.signature_base64, validate=True)

    def as_dict(self) -> dict[str, Any]:
        return {"keyid": self.key_id, "sig": self.signature_base64}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DsseSignatureV4:
        require_exact_keys(payload, expected={"keyid", "sig"}, context=cls.__name__)
        return cls(key_id=payload["keyid"], signature_base64=payload["sig"])


@dataclass(frozen=True, slots=True, kw_only=True)
class DeploymentBundleApprovalV4:
    payload_type: str
    payload_base64: str
    signatures: tuple[DsseSignatureV4, ...]

    def __post_init__(self) -> None:
        payload_type = canonical_identifier(
            self.payload_type, field="payload_type", maximum=512
        )
        if payload_type != DEPLOYMENT_DSSE_PAYLOAD_TYPE:
            raise CanonicalizationError("DSSE deployment payload type differs")
        object.__setattr__(self, "payload_type", payload_type)
        if (
            not isinstance(self.payload_base64, str)
            or len(self.payload_base64) > 4 * 1024 * 1024
            or _BASE64_RE.fullmatch(self.payload_base64) is None
        ):
            raise CanonicalizationError("DSSE payload has invalid base64 encoding")
        try:
            decoded = base64.b64decode(self.payload_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise CanonicalizationError(
                "DSSE payload has invalid base64 encoding"
            ) from exc
        if base64.b64encode(decoded).decode("ascii") != self.payload_base64:
            raise CanonicalizationError("DSSE payload base64 is not canonical")
        if not decoded or len(decoded) > 3 * 1024 * 1024:
            raise CanonicalizationError("DSSE payload size is outside reviewed bounds")
        if not isinstance(self.signatures, tuple) or not self.signatures:
            raise CanonicalizationError("DSSE signatures must be a non-empty tuple")
        if any(type(item) is not DsseSignatureV4 for item in self.signatures):
            raise CanonicalizationError(
                "DSSE signatures accepts exact DsseSignatureV4 values only"
            )
        ordered = tuple(sorted(self.signatures, key=lambda item: item.key_id))
        if len({item.key_id for item in ordered}) != len(ordered):
            raise CanonicalizationError("DSSE envelope contains duplicate key IDs")
        object.__setattr__(self, "signatures", ordered)

    @property
    def payload_bytes(self) -> bytes:
        return base64.b64decode(self.payload_base64, validate=True)

    @property
    def deployment_bundle(self) -> DeploymentBundleV4:
        """Parse exact canonical bundle bytes without granting authority.

        This is a syntax and identity accessor only.  Callers must still use
        :func:`verify_deployment_bundle_approval_v4` before treating the
        bundle or its identity as authorized by a trust root.
        """

        return _parse_deployment_bundle_payload(self.payload_bytes)

    @property
    def deployment_bundle_id(self) -> str:
        """Return the syntax-validated bundle identity; it is not authority."""

        return self.deployment_bundle.deployment_bundle_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload_base64,
            "payloadType": self.payload_type,
            "signatures": [item.as_dict() for item in self.signatures],
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DeploymentBundleApprovalV4:
        require_exact_keys(
            payload,
            expected={"payload", "payloadType", "signatures"},
            context=cls.__name__,
        )
        signatures = payload["signatures"]
        if not isinstance(signatures, list):
            raise CanonicalizationError("DSSE signatures must be a list")
        return cls(
            payload_type=payload["payloadType"],
            payload_base64=payload["payload"],
            signatures=tuple(DsseSignatureV4.from_mapping(item) for item in signatures),
        )


@runtime_checkable
class DeploymentBundleSignerV4(Protocol):
    public_key_bytes: bytes

    def sign(self, payload: bytes) -> bytes:
        """Return an Ed25519 signature over exact DSSE PAE bytes."""


def _parse_deployment_bundle_payload(payload: bytes) -> DeploymentBundleV4:
    """Parse the exact byte object passed by the DSSE verification path."""

    parsed = strict_json_loads(payload)
    if not isinstance(parsed, Mapping):
        raise CanonicalizationError("DSSE deployment payload must be an object")
    bundle = DeploymentBundleV4.from_mapping(parsed)
    if canonical_json_bytes(bundle.as_dict()) != payload:
        raise CanonicalizationError(
            "DSSE deployment payload is not exact canonical JSON"
        )
    return bundle


def approve_deployment_bundle_v4(
    bundle: DeploymentBundleV4,
    *,
    signers: Sequence[DeploymentBundleSignerV4],
) -> DeploymentBundleApprovalV4:
    """Create and self-check a DSSE approval for one canonical bundle."""

    if type(bundle) is not DeploymentBundleV4:
        raise TypeError("bundle must be an exact DeploymentBundleV4")
    if isinstance(signers, (str, bytes, bytearray)) or not isinstance(
        signers, Sequence
    ):
        raise TypeError("signers must be a sequence")
    if not signers:
        raise CanonicalizationError("at least one deployment signer is required")
    payload = canonical_json_bytes(bundle.as_dict())
    pae = dsse_pae_v1(DEPLOYMENT_DSSE_PAYLOAD_TYPE, payload)
    signatures: list[DsseSignatureV4] = []
    seen: set[str] = set()
    for signer in signers:
        public_key = getattr(signer, "public_key_bytes", None)
        if not isinstance(public_key, bytes):
            raise CanonicalizationError(
                "deployment signer must expose exact public_key_bytes"
            )
        key_id = derive_deployment_signing_key_id(public_key)
        if key_id in seen:
            raise CanonicalizationError("duplicate deployment signer key")
        seen.add(key_id)
        signature = signer.sign(pae)
        if not isinstance(signature, bytes) or len(signature) != 64:
            raise CanonicalizationError(
                "deployment signer must return exactly 64 signature bytes"
            )
        try:
            Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
                pae, signature
            )
        except Exception as exc:
            raise CanonicalizationError(
                "deployment signer returned an invalid Ed25519 signature"
            ) from exc
        signatures.append(
            DsseSignatureV4(
                key_id=key_id,
                signature_base64=base64.b64encode(signature).decode("ascii"),
            )
        )
    return DeploymentBundleApprovalV4(
        payload_type=DEPLOYMENT_DSSE_PAYLOAD_TYPE,
        payload_base64=base64.b64encode(payload).decode("ascii"),
        signatures=tuple(signatures),
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifiedDeploymentCapabilityV4:
    """Immutable result of exact local deployment admission.

    This object is evidence of verification by this function, not an
    unforgeable OS capability.  A later runtime slice must bind its identity
    into transport sessions and persist sequence/parent acceptance under the
    writer fence.
    """

    deployment_bundle_id: str
    deployment_sequence: int
    deployment_trust_root_id: str
    authority_ceiling: DeploymentAuthorityCeilingV4
    environment_id: str
    verified_at: datetime
    valid_from: datetime
    valid_until: datetime
    parent_deployment_bundle_id: str | None
    child_manifest_ids: tuple[str, ...]
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    dependency_lock_manifest_id: str
    tls_trust_store_manifest_id: str
    clock_source_policy_manifest_id: str
    collector_release_manifest_id: str
    runtime_environment_manifest_id: str
    collector_key_authorization_manifest_id: str
    tls_websocket_driver_policy_id: str | None
    max_uncertainty_milliseconds: int
    max_sample_age_milliseconds: int
    transport_capacity_policy_id_v49f: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_attestation_key_id",
            "dependency_lock_manifest_id",
            "tls_trust_store_manifest_id",
            "clock_source_policy_manifest_id",
            "collector_release_manifest_id",
            "runtime_environment_manifest_id",
            "collector_key_authorization_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "deployment_sequence",
            canonical_safe_int(
                self.deployment_sequence, field="deployment_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "authority_ceiling",
            DeploymentAuthorityCeilingV4(self.authority_ceiling),
        )
        object.__setattr__(
            self,
            "environment_id",
            canonical_identifier(self.environment_id, field="environment_id"),
        )
        object.__setattr__(
            self, "verified_at", utc_datetime(self.verified_at, field="verified_at")
        )
        valid_from = utc_datetime(self.valid_from, field="valid_from")
        valid_until = utc_datetime(self.valid_until, field="valid_until")
        if valid_until <= valid_from:
            raise CanonicalizationError(
                "capability must have a positive deployment validity interval"
            )
        if self.verified_at < valid_from or self.verified_at >= valid_until:
            raise CanonicalizationError(
                "capability verification time is outside deployment validity"
            )
        object.__setattr__(self, "valid_from", valid_from)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(
            self,
            "parent_deployment_bundle_id",
            _optional_hash(
                self.parent_deployment_bundle_id,
                field="parent_deployment_bundle_id",
            ),
        )
        if not isinstance(self.child_manifest_ids, tuple) or len(
            self.child_manifest_ids
        ) != len(OperationalManifestKindV4):
            raise CanonicalizationError(
                "capability must contain the exact child-manifest closure"
            )
        normalized_ids = tuple(
            canonical_hash(value, field="child_manifest_id")
            for value in self.child_manifest_ids
        )
        if len(set(normalized_ids)) != len(normalized_ids):
            raise CanonicalizationError("capability child-manifest IDs are not unique")
        object.__setattr__(self, "child_manifest_ids", normalized_ids)
        public_key = _public_key_bytes(
            self.collector_attestation_public_key_hex,
            field="collector_attestation_public_key_hex",
        )
        if (
            derive_transport_attestation_key_id(public_key)
            != self.collector_attestation_key_id
        ):
            raise CanonicalizationError("capability collector key binding differs")
        object.__setattr__(
            self, "collector_attestation_public_key_hex", public_key.hex()
        )
        object.__setattr__(
            self,
            "tls_websocket_driver_policy_id",
            _optional_hash(
                self.tls_websocket_driver_policy_id,
                field="tls_websocket_driver_policy_id",
            ),
        )
        object.__setattr__(
            self,
            "transport_capacity_policy_id_v49f",
            _optional_hash(
                self.transport_capacity_policy_id_v49f,
                field="transport_capacity_policy_id_v49f",
            ),
        )
        object.__setattr__(
            self,
            "max_uncertainty_milliseconds",
            canonical_safe_int(
                self.max_uncertainty_milliseconds,
                field="max_uncertainty_milliseconds",
                minimum=1,
                maximum=60_000,
            ),
        )
        object.__setattr__(
            self,
            "max_sample_age_milliseconds",
            canonical_safe_int(
                self.max_sample_age_milliseconds,
                field="max_sample_age_milliseconds",
                minimum=1,
                maximum=3_600_000,
            ),
        )

    @property
    def collector_release_hash(self) -> str:
        """Return the V4.5 session value for ``collector_release_hash``."""

        return self.collector_release_manifest_id

    @property
    def collector_runtime_id(self) -> str:
        """Return the V4.5 session value for ``collector_runtime_id``."""

        return self.runtime_environment_manifest_id

    @property
    def trust_store_manifest_id(self) -> str:
        """Return the V4.5 session value for ``trust_store_manifest_id``."""

        return self.tls_trust_store_manifest_id

    @property
    def clock_source_manifest_id(self) -> str:
        """Return the signed clock-policy identity consumed by clock evidence."""

        return self.clock_source_policy_manifest_id

    def require_tls_websocket_driver_policy_id_v49b(self) -> str:
        """Return the signed driver-policy identity or reject live admission."""

        if self.tls_websocket_driver_policy_id is None:
            raise OperationalManifestVerificationError(
                "live TLS/WebSocket admission requires a signed V4.9B driver policy"
            )
        return self.tls_websocket_driver_policy_id

    def require_transport_capacity_policy_id_v49f(self) -> str:
        """Return the signed A1 policy identity or reject bounded admission."""

        if self.transport_capacity_policy_id_v49f is None:
            raise OperationalManifestVerificationError(
                "bounded transport admission requires a signed V4.9F policy"
            )
        return self.transport_capacity_policy_id_v49f

    def transport_session_bindings(self) -> dict[str, str]:
        """Return the exact manifest identities a V4.5 session must carry."""

        return {
            "clock_source_manifest_id": self.clock_source_manifest_id,
            "collector_key_authorization_manifest_id": (
                self.collector_key_authorization_manifest_id
            ),
            "collector_release_hash": self.collector_release_hash,
            "collector_runtime_id": self.collector_runtime_id,
            "deployment_bundle_id": self.deployment_bundle_id,
            "trust_store_manifest_id": self.trust_store_manifest_id,
        }


_EXPECTED_CHILD_TYPES: dict[
    type[OperationalChildManifestV4], tuple[OperationalManifestKindV4, str]
] = {
    CollectorReleaseManifestV4: (
        OperationalManifestKindV4.COLLECTOR_RELEASE,
        "collector_release_manifest_id",
    ),
    DependencyLockManifestV4: (
        OperationalManifestKindV4.DEPENDENCY_LOCK,
        "dependency_lock_manifest_id",
    ),
    TlsTrustStoreManifestV4: (
        OperationalManifestKindV4.TLS_TRUST_STORE,
        "tls_trust_store_manifest_id",
    ),
    ClockSourcePolicyManifestV4: (
        OperationalManifestKindV4.CLOCK_SOURCE_POLICY,
        "clock_source_policy_manifest_id",
    ),
    RuntimeEnvironmentManifestV4: (
        OperationalManifestKindV4.RUNTIME_ENVIRONMENT,
        "runtime_environment_manifest_id",
    ),
    CollectorKeyAuthorizationManifestV4: (
        OperationalManifestKindV4.COLLECTOR_KEY_AUTHORIZATION,
        "collector_key_authorization_manifest_id",
    ),
}


def _verify_child_closure(
    bundle: DeploymentBundleV4,
    children: Sequence[OperationalChildManifestV4],
) -> dict[type[OperationalChildManifestV4], OperationalChildManifestV4]:
    if isinstance(children, (str, bytes, bytearray)) or not isinstance(
        children, Sequence
    ):
        raise OperationalManifestVerificationError("children must be a sequence")
    if len(children) != len(_EXPECTED_CHILD_TYPES):
        raise OperationalManifestVerificationError(
            "deployment bundle requires the exact six-child closure"
        )
    by_type: dict[type[OperationalChildManifestV4], OperationalChildManifestV4] = {}
    ids: set[str] = set()
    for child in children:
        child_type = type(child)
        specification = _EXPECTED_CHILD_TYPES.get(child_type)
        if specification is None:
            raise OperationalManifestVerificationError(
                "deployment closure contains an unsupported child type"
            )
        if child_type in by_type:
            raise OperationalManifestVerificationError(
                "deployment closure contains a duplicate child role"
            )
        manifest_id = child.manifest_id
        if manifest_id in ids:
            raise OperationalManifestVerificationError(
                "deployment closure contains a duplicate child identity"
            )
        ids.add(manifest_id)
        _, bundle_field = specification
        if manifest_id != getattr(bundle, bundle_field):
            raise OperationalManifestVerificationError(
                f"{bundle_field} differs from the supplied child"
            )
        by_type[child_type] = child
    if set(by_type) != set(_EXPECTED_CHILD_TYPES):
        raise OperationalManifestVerificationError(
            "deployment closure does not contain every required child role"
        )
    return by_type


def _verify_cross_manifest_bindings(
    bundle: DeploymentBundleV4,
    by_type: Mapping[type[OperationalChildManifestV4], OperationalChildManifestV4],
) -> CollectorKeyAuthorizationManifestV4:
    release = by_type[CollectorReleaseManifestV4]
    dependency = by_type[DependencyLockManifestV4]
    trust_store = by_type[TlsTrustStoreManifestV4]
    clock = by_type[ClockSourcePolicyManifestV4]
    runtime = by_type[RuntimeEnvironmentManifestV4]
    key_authorization = by_type[CollectorKeyAuthorizationManifestV4]
    if type(runtime) is not RuntimeEnvironmentManifestV4:
        raise OperationalManifestVerificationError("runtime child type is ambiguous")
    if type(key_authorization) is not CollectorKeyAuthorizationManifestV4:
        raise OperationalManifestVerificationError(
            "collector key child type is ambiguous"
        )
    mismatches = (
        runtime.collector_release_manifest_id != release.manifest_id,
        runtime.dependency_lock_manifest_id != dependency.manifest_id,
        runtime.tls_trust_store_manifest_id != trust_store.manifest_id,
        runtime.clock_source_policy_manifest_id != clock.manifest_id,
        key_authorization.collector_release_manifest_id != release.manifest_id,
    )
    if any(mismatches):
        raise OperationalManifestVerificationError(
            "deployment child manifests do not form one exact composition"
        )
    if (
        key_authorization.valid_from > bundle.valid_from
        or key_authorization.valid_until < bundle.valid_until
    ):
        raise OperationalManifestVerificationError(
            "collector key authorization does not cover the deployment interval"
        )
    return key_authorization


def verify_deployment_bundle_approval_v4(
    approval: DeploymentBundleApprovalV4,
    *,
    trust_root: DeploymentTrustRootV4,
    expected_trust_root_id: str,
    children: Sequence[OperationalChildManifestV4],
    verified_at: datetime,
    expected_collector_attestation_key_id: str | None = None,
) -> VerifiedDeploymentCapabilityV4:
    """Verify one DSSE approval and return its narrow admission capability.

    ``expected_trust_root_id`` is mandatory out-of-band input.  Supplying a
    self-created root next to a self-signed bundle is therefore insufficient.
    This function deliberately performs signature verification before parsing
    the signed deployment payload.
    """

    if type(approval) is not DeploymentBundleApprovalV4:
        raise TypeError("approval must be an exact DeploymentBundleApprovalV4")
    if type(trust_root) is not DeploymentTrustRootV4:
        raise TypeError("trust_root must be an exact DeploymentTrustRootV4")
    expected_root = canonical_hash(
        expected_trust_root_id, field="expected_trust_root_id"
    )
    if trust_root.trust_root_id != expected_root:
        raise OperationalManifestVerificationError(
            "deployment trust root is not the out-of-band pinned root"
        )

    payload = approval.payload_bytes
    pae = dsse_pae_v1(approval.payload_type, payload)
    trusted_keys = {item.key_id: item for item in trust_root.deployment_keys}
    verified_key_ids: set[str] = set()
    for signature in approval.signatures:
        trusted_key = trusted_keys.get(signature.key_id)
        if trusted_key is None:
            raise OperationalManifestVerificationError(
                "DSSE approval contains an untrusted deployment key"
            )
        try:
            Ed25519CheckpointVerifier.from_public_bytes(
                trusted_key.public_key_bytes
            ).verify(pae, signature.signature_bytes)
        except Exception as exc:
            raise OperationalManifestVerificationError(
                "DSSE deployment signature is invalid"
            ) from exc
        verified_key_ids.add(signature.key_id)
    if len(verified_key_ids) < trust_root.deployment_role_threshold:
        raise OperationalManifestVerificationError(
            "DSSE deployment approval does not meet the trusted role threshold"
        )

    try:
        # Parse the exact immutable byte object verified above.  Do not decode
        # or re-read the DSSE envelope a second time on the authority path.
        bundle = _parse_deployment_bundle_payload(payload)
    except (CanonicalizationError, TypeError, ValueError) as exc:
        raise OperationalManifestVerificationError(
            f"signed deployment payload is not a valid V4.5 bundle: {exc}"
        ) from exc
    if bundle.deployment_trust_root_id != trust_root.trust_root_id:
        raise OperationalManifestVerificationError(
            "deployment bundle names a different trust root"
        )
    now = utc_datetime(verified_at, field="verified_at")
    if now < bundle.valid_from or now >= bundle.valid_until:
        raise OperationalManifestVerificationError(
            "deployment bundle is not valid at the governed verification time"
        )

    by_type = _verify_child_closure(bundle, children)
    key_authorization = _verify_cross_manifest_bindings(bundle, by_type)
    clock_policy = by_type[ClockSourcePolicyManifestV4]
    runtime_environment = by_type[RuntimeEnvironmentManifestV4]
    if type(clock_policy) is not ClockSourcePolicyManifestV4:
        raise OperationalManifestVerificationError("clock-policy child is ambiguous")
    if type(runtime_environment) is not RuntimeEnvironmentManifestV4:
        raise OperationalManifestVerificationError(
            "runtime-environment child is ambiguous"
        )
    if expected_collector_attestation_key_id is not None:
        expected_key = canonical_hash(
            expected_collector_attestation_key_id,
            field="expected_collector_attestation_key_id",
        )
        if key_authorization.collector_attestation_key_id != expected_key:
            raise OperationalManifestVerificationError(
                "loaded collector key is not authorized by the deployment bundle"
            )

    child_ids = tuple(
        child.manifest_id
        for child in sorted(children, key=lambda item: item.KIND.value)
    )
    return VerifiedDeploymentCapabilityV4(
        deployment_bundle_id=bundle.deployment_bundle_id,
        deployment_sequence=bundle.deployment_sequence,
        deployment_trust_root_id=trust_root.trust_root_id,
        authority_ceiling=bundle.authority_ceiling,
        environment_id=bundle.environment_id,
        verified_at=now,
        valid_from=bundle.valid_from,
        valid_until=bundle.valid_until,
        parent_deployment_bundle_id=bundle.parent_deployment_bundle_id,
        child_manifest_ids=child_ids,
        collector_attestation_key_id=(key_authorization.collector_attestation_key_id),
        collector_attestation_public_key_hex=(
            key_authorization.collector_attestation_public_key_hex
        ),
        dependency_lock_manifest_id=bundle.dependency_lock_manifest_id,
        tls_trust_store_manifest_id=bundle.tls_trust_store_manifest_id,
        clock_source_policy_manifest_id=bundle.clock_source_policy_manifest_id,
        collector_release_manifest_id=bundle.collector_release_manifest_id,
        runtime_environment_manifest_id=bundle.runtime_environment_manifest_id,
        collector_key_authorization_manifest_id=(
            bundle.collector_key_authorization_manifest_id
        ),
        tls_websocket_driver_policy_id=(
            None
            if runtime_environment.tls_websocket_driver_policy is None
            else runtime_environment.tls_websocket_driver_policy.policy_id
        ),
        max_uncertainty_milliseconds=(clock_policy.max_uncertainty_milliseconds),
        max_sample_age_milliseconds=clock_policy.max_sample_age_milliseconds,
        transport_capacity_policy_id_v49f=(
            None
            if runtime_environment.transport_capacity_policy_v49f is None
            else runtime_environment.transport_capacity_policy_v49f.policy_id
        ),
    )


__all__ = [
    "CHRONYD_COMMAND_PROXY_PROFILE",
    "CHRONYD_FIXED_ENVIRONMENT_SHA256",
    "CHRONYD_LAUNCH_PROFILE",
    "CHRONYD_QUERY_SOCKET_PATH_SUFFIX_BYTES",
    "CHRONYD_SUPERVISOR_PROFILE",
    "CLOCK_SOURCE_KIND",
    "COLLECTOR_KEY_USAGE",
    "DEPENDENCY_LOCK_FORMAT",
    "DEPLOYMENT_BUNDLE_SCHEMA_VERSION",
    "DEPLOYMENT_DSSE_PAYLOAD_TYPE",
    "DEPLOYMENT_ROLE_NAME",
    "DEPLOYMENT_SIGNATURE_ALGORITHM",
    "DEPLOYMENT_TRUST_ROOT_SCHEMA_VERSION",
    "MONOTONIC_DOMAIN_PROFILE",
    "OPERATIONAL_MANIFEST_SCHEMA_VERSION",
    "TLS_TRUST_STORE_FORMAT",
    "TLS_WEBSOCKET_DRIVER_ARTIFACT_ROLES_V49B",
    "TLS_WEBSOCKET_DRIVER_BYTECODE_CACHE_ROLES_V49B",
    "TLS_WEBSOCKET_DRIVER_DISTRIBUTIONS_V49B",
    "TLS_WEBSOCKET_DRIVER_PROFILE_V49B",
    "TLS_VERIFY_PURPOSE",
    "ChronydLaunchPolicyV48B",
    "ClockSourcePolicyManifestV4",
    "CollectorKeyAuthorizationManifestV4",
    "CollectorReleaseManifestV4",
    "DependencyLockManifestV4",
    "DeploymentAuthorityCeilingV4",
    "DeploymentBundleApprovalV4",
    "DeploymentBundleSignerV4",
    "DeploymentBundleV4",
    "DeploymentRoleKeyV4",
    "DeploymentTrustRootV4",
    "DsseSignatureV4",
    "OperationalChildManifestV4",
    "OperationalManifestKindV4",
    "OperationalManifestVerificationError",
    "InstalledDistributionClosureV49B",
    "RuntimeArtifactMemberV49B",
    "RuntimeEnvironmentManifestV4",
    "TlsWebSocketDriverPolicyV49B",
    "TlsTrustStoreManifestV4",
    "TransportCapacityPolicyV49F",
    "VerifiedDeploymentCapabilityV4",
    "approve_deployment_bundle_v4",
    "derive_deployment_signing_key_id",
    "dsse_pae_v1",
    "verify_deployment_bundle_approval_v4",
]

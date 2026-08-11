"""Signed V4.7 cooperative transport socket-owner binding.

The binding is intentionally separate from the V4.5 transport-session
identity.  It commits one existing session to one Linux socket identity, one
writer fence, and one boot/time-namespace-scoped ``CLOCK_BOOTTIME`` domain at
the instant the runtime accepts ownership.

This is evidence of the collector's cooperative writer-ownership claim.  A
Linux socket can have duplicated or inherited descriptors, so the record does
not claim kernel-enforced descriptor exclusivity, peer receipt, or remote
exchange participation.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .ledger_signing import Ed25519CheckpointVerifier, ed25519_public_key_is_valid
from .physical_transport_v4 import (
    TransportSessionAttestationV4,
    derive_transport_attestation_key_id,
)

PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION = "riskyieldmm_physical_transport_owner_v4_7"

LINUX_SOCKET_IDENTITY_PROFILE_V4 = "LINUX_SO_COOKIE_BOOT_NETNS_V1"
LINUX_BOOTTIME_CLOCK_PROFILE_V4 = "LINUX_BOOT_ID_TIME_NAMESPACE_CLOCK_BOOTTIME_V1"

_OWNER_BINDING_IDENTITY_DOMAIN = "TransportSocketOwnerBindingV4_7"
_OWNER_BINDING_SIGNING_DOMAIN = "RiskYieldMMTransportSocketOwnerBindingSignatureV4_7"
_LINUX_NAMESPACE_IDENTITY_DOMAIN = "RiskYieldMMLinuxNamespaceIdentityV4_7"
_LINUX_SOCKET_IDENTITY_DOMAIN = "RiskYieldMMLinuxKernelSocketIdentityV4_7"
_LINUX_CLOCK_DOMAIN_IDENTITY_DOMAIN = "RiskYieldMMLinuxBoottimeClockDomainIdentityV4_7"
_SOCKET_LEASE_IDENTITY_DOMAIN = "RiskYieldMMTransportSocketLeaseIdentityV4_7"

_PUBLIC_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")
_U64_HEX_RE = re.compile(r"^[0-9a-f]{16}$")
_NAMESPACE_KINDS = frozenset({"net", "time"})


def _canonical_u64(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CanonicalizationError(f"{field} must be an integer")
    if value < 0 or value > (1 << 64) - 1:
        raise CanonicalizationError(f"{field} must be an unsigned 64-bit integer")
    return value


def _canonical_socket_cookie_u64_hex(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or _U64_HEX_RE.fullmatch(value) is None:
        raise CanonicalizationError(
            f"{field} must be exactly 16 lowercase hexadecimal characters"
        )
    if value == "0000000000000000":
        raise CanonicalizationError(f"{field} must identify a nonzero Linux socket")
    return value


def format_linux_socket_cookie_u64(value: int) -> str:
    """Encode a Linux ``SO_COOKIE`` value without entering the I-JSON int domain."""

    encoded = f"{_canonical_u64(value, field='socket_cookie_u64'):016x}"
    return _canonical_socket_cookie_u64_hex(encoded, field="socket_cookie_u64")


def derive_linux_namespace_id(
    *, namespace_kind: str, stat_device_u64: int, stat_inode_u64: int
) -> str:
    """Derive a stable process-visible namespace ID from an opened namespace FD.

    Callers should obtain ``st_dev`` and ``st_ino`` from ``fstat()`` on a
    retained ``/proc/self/ns/time`` or ``/proc/self/ns/net`` descriptor.  The
    integers are encoded as fixed-width hex before hashing so full-width Linux
    values never enter canonical JSON as unsafe numbers.
    """

    kind = canonical_identifier(namespace_kind, field="namespace_kind")
    if kind not in _NAMESPACE_KINDS:
        raise CanonicalizationError("namespace_kind must be 'time' or 'net'")
    device = _canonical_u64(stat_device_u64, field="stat_device_u64")
    inode = _canonical_u64(stat_inode_u64, field="stat_inode_u64")
    return sha256_digest(
        {
            "domain": _LINUX_NAMESPACE_IDENTITY_DOMAIN,
            "namespace_kind": kind,
            "stat_device_u64_hex": f"{device:016x}",
            "stat_inode_u64_hex": f"{inode:016x}",
        }
    )


def derive_linux_boottime_clock_domain_id(
    *,
    kernel_boot_id: str,
    time_namespace_id: str,
    clock_profile: str = LINUX_BOOTTIME_CLOCK_PROFILE_V4,
) -> str:
    """Bind the BOOTTIME clock domain to one kernel boot and time namespace."""

    boot_id = canonical_identifier(kernel_boot_id, field="kernel_boot_id")
    namespace_id = canonical_hash(time_namespace_id, field="time_namespace_id")
    profile = canonical_identifier(clock_profile, field="clock_profile")
    if profile != LINUX_BOOTTIME_CLOCK_PROFILE_V4:
        raise CanonicalizationError(
            "clock_profile differs from the reviewed Linux BOOTTIME profile"
        )
    return sha256_digest(
        {
            "clock_profile": profile,
            "domain": _LINUX_CLOCK_DOMAIN_IDENTITY_DOMAIN,
            "kernel_boot_id": boot_id,
            "time_namespace_id": namespace_id,
        }
    )


def derive_linux_kernel_socket_identity(
    *,
    kernel_boot_id: str,
    network_namespace_id: str,
    socket_cookie_u64: str,
    socket_identity_profile: str = LINUX_SOCKET_IDENTITY_PROFILE_V4,
) -> str:
    """Derive the scoped Linux kernel-socket identity used by the binding."""

    boot_id = canonical_identifier(kernel_boot_id, field="kernel_boot_id")
    namespace_id = canonical_hash(network_namespace_id, field="network_namespace_id")
    cookie = _canonical_socket_cookie_u64_hex(
        socket_cookie_u64, field="socket_cookie_u64"
    )
    profile = canonical_identifier(
        socket_identity_profile, field="socket_identity_profile"
    )
    if profile != LINUX_SOCKET_IDENTITY_PROFILE_V4:
        raise CanonicalizationError(
            "socket_identity_profile differs from the reviewed Linux SO_COOKIE profile"
        )
    return sha256_digest(
        {
            "domain": _LINUX_SOCKET_IDENTITY_DOMAIN,
            "kernel_boot_id": boot_id,
            "network_namespace_id": namespace_id,
            "socket_cookie_u64": cookie,
            "socket_identity_profile": profile,
        }
    )


def derive_transport_socket_lease_nonce_sha256(lease_nonce: bytes) -> str:
    """Commit caller-owned lease capability entropy without persisting the secret."""

    if not isinstance(lease_nonce, bytes) or len(lease_nonce) < 16:
        raise CanonicalizationError(
            "lease_nonce must contain at least 16 bytes of caller-owned entropy"
        )
    return hashlib.sha256(lease_nonce).hexdigest()


def derive_transport_socket_lease_id(
    *,
    transport_session_id: str,
    kernel_socket_identity: str,
    socket_lease_nonce_sha256: str,
    writer_fence_token_sha256: str,
    writer_fence_generation: int,
    socket_identity_profile: str = LINUX_SOCKET_IDENTITY_PROFILE_V4,
) -> str:
    """Derive a per-session lease from capability and writer-fence evidence.

    The raw nonce remains runtime capability material.  Only its SHA-256
    commitment enters this derivation and the signed record.
    """

    session_id = canonical_hash(transport_session_id, field="transport_session_id")
    socket_identity = canonical_hash(
        kernel_socket_identity, field="kernel_socket_identity"
    )
    nonce_digest = canonical_hash(
        socket_lease_nonce_sha256, field="socket_lease_nonce_sha256"
    )
    fence_token = canonical_hash(
        writer_fence_token_sha256, field="writer_fence_token_sha256"
    )
    fence_generation = canonical_safe_int(
        writer_fence_generation, field="writer_fence_generation", minimum=1
    )
    profile = canonical_identifier(
        socket_identity_profile, field="socket_identity_profile"
    )
    if profile != LINUX_SOCKET_IDENTITY_PROFILE_V4:
        raise CanonicalizationError(
            "socket_identity_profile differs from the reviewed Linux SO_COOKIE profile"
        )
    return sha256_digest(
        {
            "domain": _SOCKET_LEASE_IDENTITY_DOMAIN,
            "kernel_socket_identity": socket_identity,
            "socket_identity_profile": profile,
            "socket_lease_nonce_sha256": nonce_digest,
            "transport_session_id": session_id,
            "writer_fence_generation": fence_generation,
            "writer_fence_token_sha256": fence_token,
        }
    )


def _public_key_bytes(value: Any) -> bytes:
    if not isinstance(value, str) or _PUBLIC_KEY_RE.fullmatch(value) is None:
        raise CanonicalizationError(
            "collector_attestation_public_key_hex has invalid lowercase hexadecimal encoding"
        )
    public_key = bytes.fromhex(value)
    if not ed25519_public_key_is_valid(public_key):
        raise CanonicalizationError(
            "collector_attestation_public_key_hex is not a canonical Ed25519 main-subgroup public key"
        )
    return public_key


def _key_pair(key_id: Any, public_key_hex: Any) -> tuple[str, str, bytes]:
    public_key = _public_key_bytes(public_key_hex)
    supplied = canonical_hash(key_id, field="collector_attestation_key_id")
    derived = derive_transport_attestation_key_id(public_key)
    if supplied != derived:
        raise CanonicalizationError(
            "collector_attestation_key_id differs from its transport public key"
        )
    return supplied, public_key.hex(), public_key


def _signer_key(signer: Any) -> tuple[str, str]:
    public_key = getattr(signer, "public_key_bytes", None)
    if not isinstance(public_key, bytes):
        raise CanonicalizationError("transport signer must expose public_key_bytes")
    return derive_transport_attestation_key_id(public_key), public_key.hex()


def _signature_payload(identity_payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": _OWNER_BINDING_SIGNING_DOMAIN,
        "payload": dict(identity_payload),
        "schema_version": PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION,
    }


def _sign(signer: Any, payload: Mapping[str, Any]) -> str:
    sign = getattr(signer, "sign", None)
    if not callable(sign):
        raise CanonicalizationError("transport signer must provide sign(payload)")
    signature = sign(canonical_json_bytes(payload))
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise CanonicalizationError(
            "transport signer must return exactly 64 Ed25519 signature bytes"
        )
    return signature.hex()


def _verify_signature(
    *, public_key: bytes, signature_hex: Any, payload: Mapping[str, Any]
) -> str:
    if (
        not isinstance(signature_hex, str)
        or _SIGNATURE_RE.fullmatch(signature_hex) is None
    ):
        raise CanonicalizationError(
            "signature_hex has invalid lowercase hexadecimal encoding"
        )
    try:
        Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
            canonical_json_bytes(payload), bytes.fromhex(signature_hex)
        )
    except Exception as exc:
        raise CanonicalizationError(
            "transport socket-owner Ed25519 signature is invalid"
        ) from exc
    return signature_hex


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportSocketOwnerSnapshotV4:
    """One noncanonical live snapshot returned by the private socket owner port."""

    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    socket_cookie_u64: str
    clock_resolution_ns: int
    socket_identity_profile: str = LINUX_SOCKET_IDENTITY_PROFILE_V4
    clock_profile: str = LINUX_BOOTTIME_CLOCK_PROFILE_V4
    chronyd_launch_id: str | None = None
    chronyd_runtime_observation_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kernel_boot_id",
            canonical_identifier(self.kernel_boot_id, field="kernel_boot_id"),
        )
        for field_name in ("time_namespace_id", "network_namespace_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "socket_cookie_u64",
            _canonical_socket_cookie_u64_hex(
                self.socket_cookie_u64,
                field="socket_cookie_u64",
            ),
        )
        object.__setattr__(
            self,
            "clock_resolution_ns",
            canonical_safe_int(
                self.clock_resolution_ns,
                field="clock_resolution_ns",
                minimum=1,
            ),
        )
        for field_name, expected in (
            ("socket_identity_profile", LINUX_SOCKET_IDENTITY_PROFILE_V4),
            ("clock_profile", LINUX_BOOTTIME_CLOCK_PROFILE_V4),
        ):
            value = canonical_identifier(getattr(self, field_name), field=field_name)
            if value != expected:
                raise CanonicalizationError(
                    f"{field_name} differs from the reviewed V4.7 profile"
                )
            object.__setattr__(self, field_name, value)
        launch_values = (
            self.chronyd_launch_id,
            self.chronyd_runtime_observation_sha256,
        )
        if (launch_values[0] is None) != (launch_values[1] is None):
            raise CanonicalizationError(
                "chronyd launch and runtime-observation identities must be paired"
            )
        if launch_values[0] is not None:
            object.__setattr__(
                self,
                "chronyd_launch_id",
                canonical_hash(launch_values[0], field="chronyd_launch_id"),
            )
            object.__setattr__(
                self,
                "chronyd_runtime_observation_sha256",
                canonical_hash(
                    launch_values[1],
                    field="chronyd_runtime_observation_sha256",
                ),
            )

    @property
    def kernel_socket_identity(self) -> str:
        return derive_linux_kernel_socket_identity(
            kernel_boot_id=self.kernel_boot_id,
            network_namespace_id=self.network_namespace_id,
            socket_cookie_u64=self.socket_cookie_u64,
            socket_identity_profile=self.socket_identity_profile,
        )

    @property
    def monotonic_clock_domain_id(self) -> str:
        return derive_linux_boottime_clock_domain_id(
            kernel_boot_id=self.kernel_boot_id,
            time_namespace_id=self.time_namespace_id,
            clock_profile=self.clock_profile,
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportSocketOwnerBindingV4:
    """Immutable signed cooperative ownership binding for one V4.5 session."""

    transport_session_id: str
    deployment_bundle_id: str
    transport_subscription_policy_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    socket_lease_nonce_sha256: str
    kernel_socket_identity: str
    socket_identity_profile: str
    socket_cookie_u64: str
    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    clock_source_manifest_id: str
    monotonic_clock_domain_id: str
    clock_profile: str
    clock_resolution_ns: int
    connection_generation: int
    writer_fence_token_sha256: str
    writer_fence_generation: int
    bound_at: datetime
    bound_monotonic_before_ns: int
    bound_monotonic_after_ns: int
    clock_uncertainty_milliseconds: int
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    signature_hex: str

    def __post_init__(self) -> None:
        for field_name in (
            "transport_session_id",
            "deployment_bundle_id",
            "transport_subscription_policy_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "socket_lease_nonce_sha256",
            "kernel_socket_identity",
            "time_namespace_id",
            "network_namespace_id",
            "clock_source_manifest_id",
            "monotonic_clock_domain_id",
            "writer_fence_token_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "kernel_boot_id",
            canonical_identifier(self.kernel_boot_id, field="kernel_boot_id"),
        )
        for field_name, expected in (
            ("socket_identity_profile", LINUX_SOCKET_IDENTITY_PROFILE_V4),
            ("clock_profile", LINUX_BOOTTIME_CLOCK_PROFILE_V4),
        ):
            value = canonical_identifier(getattr(self, field_name), field=field_name)
            if value != expected:
                raise CanonicalizationError(
                    f"{field_name} differs from the reviewed V4.7 profile"
                )
            object.__setattr__(self, field_name, value)
        object.__setattr__(
            self,
            "socket_cookie_u64",
            _canonical_socket_cookie_u64_hex(
                self.socket_cookie_u64, field="socket_cookie_u64"
            ),
        )
        for field_name in (
            "clock_resolution_ns",
            "connection_generation",
            "writer_fence_generation",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        for field_name in (
            "bound_monotonic_before_ns",
            "bound_monotonic_after_ns",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        object.__setattr__(
            self,
            "clock_uncertainty_milliseconds",
            canonical_safe_int(
                self.clock_uncertainty_milliseconds,
                field="clock_uncertainty_milliseconds",
                minimum=0,
                maximum=3_600_000,
            ),
        )
        if self.bound_monotonic_after_ns < self.bound_monotonic_before_ns:
            raise CanonicalizationError(
                "bound_monotonic_after_ns must not precede bound_monotonic_before_ns"
            )
        object.__setattr__(
            self, "bound_at", utc_datetime(self.bound_at, field="bound_at")
        )

        expected_socket_identity = derive_linux_kernel_socket_identity(
            kernel_boot_id=self.kernel_boot_id,
            network_namespace_id=self.network_namespace_id,
            socket_cookie_u64=self.socket_cookie_u64,
            socket_identity_profile=self.socket_identity_profile,
        )
        if self.kernel_socket_identity != expected_socket_identity:
            raise CanonicalizationError(
                "kernel_socket_identity differs from boot, network namespace, and SO_COOKIE evidence"
            )
        expected_clock_domain = derive_linux_boottime_clock_domain_id(
            kernel_boot_id=self.kernel_boot_id,
            time_namespace_id=self.time_namespace_id,
            clock_profile=self.clock_profile,
        )
        if self.monotonic_clock_domain_id != expected_clock_domain:
            raise CanonicalizationError(
                "monotonic_clock_domain_id differs from boot, time namespace, and clock profile"
            )
        expected_lease_id = derive_transport_socket_lease_id(
            transport_session_id=self.transport_session_id,
            kernel_socket_identity=self.kernel_socket_identity,
            socket_lease_nonce_sha256=self.socket_lease_nonce_sha256,
            writer_fence_token_sha256=self.writer_fence_token_sha256,
            writer_fence_generation=self.writer_fence_generation,
            socket_identity_profile=self.socket_identity_profile,
        )
        if self.socket_lease_id != expected_lease_id:
            raise CanonicalizationError(
                "socket_lease_id differs from session, socket, capability, and writer-fence evidence"
            )

        key_id, public_hex, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        object.__setattr__(
            self,
            "signature_hex",
            _verify_signature(
                public_key=public_key,
                signature_hex=self.signature_hex,
                payload=self.signing_payload(),
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: utc_iso(value) if name == "bound_at" else value
            for name, value in (
                (name, getattr(self, name)) for name in self.__dataclass_fields__
            )
            if name != "signature_hex"
        }

    def signing_payload(self) -> dict[str, Any]:
        return _signature_payload(self.identity_payload())

    @property
    def transport_socket_owner_binding_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": _OWNER_BINDING_IDENTITY_DOMAIN,
                "payload": self.identity_payload(),
                "schema_version": PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION,
            }
        )

    def verify_signature(self) -> None:
        _, _, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        _verify_signature(
            public_key=public_key,
            signature_hex=self.signature_hex,
            payload=self.signing_payload(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "signature_hex": self.signature_hex,
            "transport_socket_owner_binding_id": (
                self.transport_socket_owner_binding_id
            ),
            "schema_version": PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION,
        }

    @classmethod
    def create_signed(
        cls, *, signer: Any, **fields: Any
    ) -> TransportSocketOwnerBindingV4:
        if any(
            name in fields
            for name in (
                "collector_attestation_key_id",
                "collector_attestation_public_key_hex",
                "signature_hex",
            )
        ):
            raise CanonicalizationError(
                "signed owner-binding key/signature fields are derived"
            )
        key_id, public_hex = _signer_key(signer)
        unsigned = _owner_binding_identity_payload(
            {
                **fields,
                "collector_attestation_key_id": key_id,
                "collector_attestation_public_key_hex": public_hex,
            }
        )
        signature = _sign(signer, _signature_payload(unsigned))
        return cls(
            **fields,
            collector_attestation_key_id=key_id,
            collector_attestation_public_key_hex=public_hex,
            signature_hex=signature,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportSocketOwnerBindingV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "transport_socket_owner_binding_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported canonicalization_version")
        if payload["schema_version"] != PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION:
            raise CanonicalizationError(
                "unsupported physical-transport owner V4.7 schema_version"
            )
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        supplied = canonical_hash(
            payload["transport_socket_owner_binding_id"],
            field="transport_socket_owner_binding_id",
        )
        if supplied != item.transport_socket_owner_binding_id:
            raise CanonicalizationError(
                "transport_socket_owner_binding_id does not match canonical content"
            )
        return item


def _owner_binding_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical unsigned binding payload used before signing."""

    result: dict[str, Any] = {}
    hash_fields = {
        "transport_session_id",
        "deployment_bundle_id",
        "transport_subscription_policy_id",
        "physical_scope_manifest_id",
        "adapter_policy_id",
        "capture_partition_id",
        "socket_lease_id",
        "socket_lease_nonce_sha256",
        "kernel_socket_identity",
        "time_namespace_id",
        "network_namespace_id",
        "clock_source_manifest_id",
        "monotonic_clock_domain_id",
        "writer_fence_token_sha256",
        "collector_attestation_key_id",
    }
    positive_int_fields = {
        "clock_resolution_ns",
        "connection_generation",
        "writer_fence_generation",
    }
    nonnegative_int_fields = {
        "bound_monotonic_before_ns",
        "bound_monotonic_after_ns",
        "clock_uncertainty_milliseconds",
    }
    for name in TransportSocketOwnerBindingV4.__dataclass_fields__:
        if name == "signature_hex":
            continue
        if name not in values:
            raise CanonicalizationError(f"signed owner binding is missing {name}")
        value = values[name]
        if name in hash_fields:
            result[name] = canonical_hash(value, field=name)
        elif name == "collector_attestation_public_key_hex":
            result[name] = _public_key_bytes(value).hex()
        elif name == "bound_at":
            result[name] = utc_iso(value, field=name)
        elif name == "socket_cookie_u64":
            result[name] = _canonical_socket_cookie_u64_hex(value, field=name)
        elif name in positive_int_fields:
            result[name] = canonical_safe_int(value, field=name, minimum=1)
        elif name in nonnegative_int_fields:
            result[name] = canonical_safe_int(value, field=name, minimum=0)
        else:
            result[name] = canonical_identifier(value, field=name)
    return result


@dataclass(frozen=True, slots=True, kw_only=True)
class CommittedBoundTransportSessionV4:
    """Noncanonical in-process pair returned after one atomic journal commit."""

    session: TransportSessionAttestationV4
    binding: TransportSocketOwnerBindingV4

    def __post_init__(self) -> None:
        if type(self.session) is not TransportSessionAttestationV4:
            raise TypeError("session must be an exact TransportSessionAttestationV4")
        if type(self.binding) is not TransportSocketOwnerBindingV4:
            raise TypeError("binding must be an exact TransportSocketOwnerBindingV4")
        shared_fields = (
            ("transport_session_id", self.session.transport_session_id),
            ("deployment_bundle_id", self.session.deployment_bundle_id),
            (
                "transport_subscription_policy_id",
                self.session.transport_subscription_policy_id,
            ),
            ("physical_scope_manifest_id", self.session.physical_scope_manifest_id),
            ("adapter_policy_id", self.session.adapter_policy_id),
            ("capture_partition_id", self.session.capture_partition_id),
            ("clock_source_manifest_id", self.session.clock_source_manifest_id),
            ("monotonic_clock_domain_id", self.session.monotonic_clock_domain_id),
            ("connection_generation", self.session.connection_generation),
            (
                "collector_attestation_key_id",
                self.session.collector_attestation_key_id,
            ),
            (
                "collector_attestation_public_key_hex",
                self.session.collector_attestation_public_key_hex,
            ),
        )
        mismatches = tuple(
            name
            for name, session_value in shared_fields
            if getattr(self.binding, name) != session_value
        )
        if mismatches:
            raise CanonicalizationError(
                "committed session/binding pair differs in shared fields: "
                + ", ".join(mismatches)
            )


__all__ = [
    "LINUX_BOOTTIME_CLOCK_PROFILE_V4",
    "LINUX_SOCKET_IDENTITY_PROFILE_V4",
    "PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION",
    "CommittedBoundTransportSessionV4",
    "TransportSocketOwnerBindingV4",
    "TransportSocketOwnerSnapshotV4",
    "derive_linux_boottime_clock_domain_id",
    "derive_linux_kernel_socket_identity",
    "derive_linux_namespace_id",
    "derive_transport_socket_lease_id",
    "derive_transport_socket_lease_nonce_sha256",
    "format_linux_socket_cookie_u64",
]

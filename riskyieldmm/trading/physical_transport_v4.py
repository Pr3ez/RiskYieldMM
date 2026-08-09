"""Immutable V4.5 transport-session and subscription evidence contracts.

These records authenticate a narrow local claim: a reviewed collector key
attested one verified WebSocket session, one exact outbound subscription
command, its provider acknowledgement, or a terminal session event.  They do
not enable order execution and do not make the remote exchange a participant
in the local transaction.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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
from .ledger_signing import (
    Ed25519CheckpointVerifier,
    ed25519_public_key_is_valid,
)

PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION = "riskyieldmm_physical_transport_v4_5"

BYBIT_V5_LINEAR_ENDPOINT_V4 = "wss://stream.bybit.com/v5/public/linear"
BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4 = "stream.bybit.com"
BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4 = "/v5/public/linear"
BYBIT_V5_LINEAR_PORT_V4 = 443
V4_TRANSPORT_MINIMUM_TLS_VERSION = "TLSv1.3"
V4_TRANSPORT_WEBSOCKET_HTTP_STATUS = 101
V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH = 36
V4_TRANSPORT_SEND_DEADLINE_SECONDS = 5
V4_TRANSPORT_ACK_DEADLINE_SECONDS = 10
V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE = (
    "EXACT_DECRYPTED_HTTP1_OPENING_HANDSHAKE_OCTETS_V1"
)

_PUBLIC_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _strict_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _optional_identifier(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return canonical_identifier(value, field=field)


def _optional_hash(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return canonical_hash(value, field=field)


def _identifiers(
    values: Sequence[Any], *, field: str, maximum_items: int = 32
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum_items:
        raise CanonicalizationError(f"{field} exceeds {maximum_items} values")
    result = tuple(canonical_identifier(value, field=field) for value in values)
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return result


def _lower_hex(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise CanonicalizationError(
            f"{field} has invalid lowercase hexadecimal encoding"
        )
    return value


def _public_key_bytes(value: Any, *, field: str) -> bytes:
    encoded = _lower_hex(value, field=field, pattern=_PUBLIC_KEY_RE)
    public_key = bytes.fromhex(encoded)
    if not ed25519_public_key_is_valid(public_key):
        raise CanonicalizationError(
            f"{field} is not a canonical Ed25519 main-subgroup public key"
        )
    return public_key


def derive_transport_attestation_key_id(public_key_bytes: bytes) -> str:
    """Derive a transport-only key ID; never a checkpoint-key identity."""

    if not isinstance(public_key_bytes, bytes) or len(public_key_bytes) != 32:
        raise CanonicalizationError(
            "transport Ed25519 public key must contain exactly 32 bytes"
        )
    if not ed25519_public_key_is_valid(public_key_bytes):
        raise CanonicalizationError(
            "transport Ed25519 public key is not a valid main-subgroup point"
        )
    return sha256_digest(
        {
            "algorithm": "ED25519",
            "domain": "RiskYieldMMTransportCollectorAttestationPublicKeyV4_4",
            "public_key_hex": public_key_bytes.hex(),
        }
    )


def _key_pair(key_id: Any, public_key_hex: Any) -> tuple[str, str, bytes]:
    public_key = _public_key_bytes(
        public_key_hex, field="collector_attestation_public_key_hex"
    )
    derived = derive_transport_attestation_key_id(public_key)
    supplied = canonical_hash(key_id, field="collector_attestation_key_id")
    if supplied != derived:
        raise CanonicalizationError(
            "collector_attestation_key_id differs from its transport public key"
        )
    return supplied, public_key.hex(), public_key


def _signer_key(signer: Any) -> tuple[str, str, bytes]:
    public_key = getattr(signer, "public_key_bytes", None)
    if not isinstance(public_key, bytes):
        raise CanonicalizationError("transport signer must expose public_key_bytes")
    key_id = derive_transport_attestation_key_id(public_key)
    return key_id, public_key.hex(), public_key


def _signature_payload(
    domain: str, identity_payload: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": dict(identity_payload),
        "schema_version": PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION,
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
    encoded = _lower_hex(signature_hex, field="signature_hex", pattern=_SIGNATURE_RE)
    try:
        Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
            canonical_json_bytes(payload), bytes.fromhex(encoded)
        )
    except Exception as exc:
        raise CanonicalizationError("transport Ed25519 signature is invalid") from exc
    return encoded


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION,
        }
    )


def _record_mapping(
    record: Any, *, identity_field: str, identity: str
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        **record.identity_payload(),
        identity_field: identity,
        "schema_version": PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION,
    }


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION:
        raise CanonicalizationError(
            "unsupported physical-transport V4.5 schema_version"
        )


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportSubscriptionPolicyV4:
    deployment_bundle_id: str
    collector_key_authorization_manifest_id: str
    policy_name: str
    provider_id: str
    venue_id: str
    environment_id: str
    authoritative_endpoint: str
    tls_server_name: str
    port: int
    websocket_path: str
    direct_connection_only: bool
    minimum_tls_version: str
    certificate_verification_required: bool
    hostname_verification_required: bool
    websocket_http_status_required: int
    websocket_accept_validation_required: bool
    allowed_websocket_extensions: tuple[str, ...]
    allowed_subprotocols: tuple[str, ...]
    single_topic_per_session: bool
    maximum_inflight_subscriptions: int
    require_nonempty_echoed_request_id: bool
    maximum_request_id_length: int
    send_deadline_seconds: int
    ack_deadline_seconds: int
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    frozen_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "deployment_bundle_id",
            "collector_key_authorization_manifest_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in ("policy_name", "provider_id", "venue_id", "environment_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "authoritative_endpoint",
            "tls_server_name",
            "websocket_path",
            "minimum_tls_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "direct_connection_only",
            "certificate_verification_required",
            "hostname_verification_required",
            "websocket_accept_validation_required",
            "single_topic_per_session",
            "require_nonempty_echoed_request_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_bool(getattr(self, field_name), field=field_name),
            )
        for field_name, minimum, maximum in (
            ("port", 1, 65535),
            ("websocket_http_status_required", 100, 599),
            ("maximum_inflight_subscriptions", 1, 1024),
            ("maximum_request_id_length", 1, 256),
            ("send_deadline_seconds", 1, 3600),
            ("ack_deadline_seconds", 1, 3600),
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=minimum,
                    maximum=maximum,
                ),
            )
        object.__setattr__(
            self,
            "allowed_websocket_extensions",
            _identifiers(
                self.allowed_websocket_extensions,
                field="allowed_websocket_extensions",
            ),
        )
        object.__setattr__(
            self,
            "allowed_subprotocols",
            _identifiers(self.allowed_subprotocols, field="allowed_subprotocols"),
        )
        key_id, public_hex, _ = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )
        exact = (
            self.provider_id == "BYBIT"
            and self.venue_id == "BYBIT"
            and self.environment_id == "MAINNET"
            and self.authoritative_endpoint == BYBIT_V5_LINEAR_ENDPOINT_V4
            and self.tls_server_name == BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4
            and self.port == BYBIT_V5_LINEAR_PORT_V4
            and self.websocket_path == BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4
            and self.direct_connection_only
            and self.minimum_tls_version == V4_TRANSPORT_MINIMUM_TLS_VERSION
            and self.certificate_verification_required
            and self.hostname_verification_required
            and self.websocket_http_status_required
            == V4_TRANSPORT_WEBSOCKET_HTTP_STATUS
            and self.websocket_accept_validation_required
            and not self.allowed_websocket_extensions
            and not self.allowed_subprotocols
            and self.single_topic_per_session
            and self.maximum_inflight_subscriptions == 1
            and self.require_nonempty_echoed_request_id
            and self.maximum_request_id_length == V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH
            and self.send_deadline_seconds == V4_TRANSPORT_SEND_DEADLINE_SECONDS
            and self.ack_deadline_seconds == V4_TRANSPORT_ACK_DEADLINE_SECONDS
        )
        if not exact:
            raise CanonicalizationError(
                "transport subscription policy differs from the reviewed Bybit V4.5 profile"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: (
                utc_iso(value)
                if name == "frozen_at"
                else list(value)
                if name in {"allowed_websocket_extensions", "allowed_subprotocols"}
                else value
            )
            for name, value in (
                (name, getattr(self, name)) for name in self.__dataclass_fields__
            )
        }

    @property
    def transport_subscription_policy_id(self) -> str:
        return _identity("TransportSubscriptionPolicyV4_5", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="transport_subscription_policy_id",
            identity=self.transport_subscription_policy_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportSubscriptionPolicyV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "transport_subscription_policy_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["transport_subscription_policy_id"],
            item.transport_subscription_policy_id,
            field="transport_subscription_policy_id",
        )
        return item


_SESSION_SIGNING_DOMAIN = "RiskYieldMMTransportSessionAttestationSignatureV4_5"


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportSessionAttestationV4:
    deployment_bundle_id: str
    clock_source_manifest_id: str
    collector_key_authorization_manifest_id: str
    transport_subscription_policy_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    collector_instance_id: str
    collector_boot_id: str
    connection_generation: int
    session_nonce: str
    parent_transport_session_id: str | None
    authoritative_endpoint: str
    tls_server_name: str
    remote_address: str
    tls_version: str
    tls_cipher: str
    alpn_protocol: str | None
    websocket_extensions: tuple[str, ...]
    peer_certificate_sha256: str
    peer_spki_sha256: str
    trust_store_manifest_id: str
    certificate_verified: bool
    hostname_verified: bool
    websocket_http_status: int
    websocket_accept_verified: bool
    handshake_commitment_profile: str
    handshake_request_sha256: str
    handshake_response_sha256: str
    handshake_started_at: datetime
    handshake_completed_at: datetime
    monotonic_clock_domain_id: str
    handshake_started_monotonic_ns: int
    handshake_completed_monotonic_ns: int
    clock_uncertainty_milliseconds: int
    collector_release_hash: str
    collector_runtime_id: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    signature_hex: str

    def __post_init__(self) -> None:
        for field_name in (
            "deployment_bundle_id",
            "clock_source_manifest_id",
            "collector_key_authorization_manifest_id",
            "transport_subscription_policy_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "session_nonce",
            "peer_certificate_sha256",
            "peer_spki_sha256",
            "trust_store_manifest_id",
            "monotonic_clock_domain_id",
            "handshake_request_sha256",
            "handshake_response_sha256",
            "collector_release_hash",
            "collector_runtime_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "parent_transport_session_id",
            _optional_hash(
                self.parent_transport_session_id, field="parent_transport_session_id"
            ),
        )
        for field_name in (
            "collector_instance_id",
            "collector_boot_id",
            "authoritative_endpoint",
            "tls_server_name",
            "remote_address",
            "tls_version",
            "tls_cipher",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "alpn_protocol",
            _optional_identifier(self.alpn_protocol, field="alpn_protocol"),
        )
        object.__setattr__(
            self,
            "websocket_extensions",
            _identifiers(self.websocket_extensions, field="websocket_extensions"),
        )
        object.__setattr__(
            self,
            "handshake_commitment_profile",
            canonical_identifier(
                self.handshake_commitment_profile,
                field="handshake_commitment_profile",
            ),
        )
        if (
            self.handshake_commitment_profile
            != V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE
        ):
            raise CanonicalizationError(
                "handshake_commitment_profile differs from the reviewed V4.5 profile"
            )
        for field_name in (
            "certificate_verified",
            "hostname_verified",
            "websocket_accept_verified",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_bool(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation, field="connection_generation", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "websocket_http_status",
            canonical_safe_int(
                self.websocket_http_status,
                field="websocket_http_status",
                minimum=100,
                maximum=599,
            ),
        )
        for field_name in (
            "handshake_started_monotonic_ns",
            "handshake_completed_monotonic_ns",
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
        started = utc_datetime(self.handshake_started_at, field="handshake_started_at")
        completed = utc_datetime(
            self.handshake_completed_at, field="handshake_completed_at"
        )
        object.__setattr__(self, "handshake_started_at", started)
        object.__setattr__(self, "handshake_completed_at", completed)
        key_id, public_hex, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        if (
            self.authoritative_endpoint != BYBIT_V5_LINEAR_ENDPOINT_V4
            or self.tls_server_name != BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4
            or self.tls_version != V4_TRANSPORT_MINIMUM_TLS_VERSION
            or not self.certificate_verified
            or not self.hostname_verified
            or self.websocket_http_status != V4_TRANSPORT_WEBSOCKET_HTTP_STATUS
            or not self.websocket_accept_verified
            or self.websocket_extensions
            or self.alpn_protocol is not None
        ):
            raise CanonicalizationError(
                "transport session differs from the reviewed Bybit TLS/WebSocket profile"
            )
        if completed <= started:
            raise CanonicalizationError(
                "handshake completion must follow handshake start"
            )
        if self.handshake_completed_monotonic_ns <= self.handshake_started_monotonic_ns:
            raise CanonicalizationError(
                "handshake monotonic completion must follow handshake start"
            )
        signature = _verify_signature(
            public_key=public_key,
            signature_hex=self.signature_hex,
            payload=self.signing_payload(),
        )
        object.__setattr__(self, "signature_hex", signature)

    def identity_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            if name == "signature_hex":
                continue
            value = getattr(self, name)
            if name in {"handshake_started_at", "handshake_completed_at"}:
                payload[name] = utc_iso(value)
            elif name == "websocket_extensions":
                payload[name] = list(value)
            else:
                payload[name] = value
        return payload

    def signing_payload(self) -> dict[str, Any]:
        return _signature_payload(_SESSION_SIGNING_DOMAIN, self.identity_payload())

    @property
    def transport_session_id(self) -> str:
        return _identity("TransportSessionAttestationV4_5", self.identity_payload())

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
            **_record_mapping(
                self,
                identity_field="transport_session_id",
                identity=self.transport_session_id,
            ),
            "signature_hex": self.signature_hex,
        }

    @classmethod
    def create_signed(
        cls, *, signer: Any, **fields: Any
    ) -> TransportSessionAttestationV4:
        key_id, public_hex, _ = _signer_key(signer)
        if any(
            name in fields
            for name in (
                "collector_attestation_key_id",
                "collector_attestation_public_key_hex",
                "signature_hex",
            )
        ):
            raise CanonicalizationError(
                "signed session key/signature fields are derived"
            )
        unsigned = _session_identity_payload(
            {
                **fields,
                "collector_attestation_key_id": key_id,
                "collector_attestation_public_key_hex": public_hex,
            }
        )
        signature = _sign(signer, _signature_payload(_SESSION_SIGNING_DOMAIN, unsigned))
        return cls(
            **fields,
            collector_attestation_key_id=key_id,
            collector_attestation_public_key_hex=public_hex,
            signature_hex=signature,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportSessionAttestationV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "transport_session_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["transport_session_id"],
            item.transport_session_id,
            field="transport_session_id",
        )
        return item


def _session_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical unsigned session payload used before constructing a signed record."""

    result: dict[str, Any] = {}
    for name in TransportSessionAttestationV4.__dataclass_fields__:
        if name == "signature_hex":
            continue
        if name not in values:
            raise CanonicalizationError(f"signed session is missing {name}")
        value = values[name]
        if name in {"handshake_started_at", "handshake_completed_at"}:
            result[name] = utc_iso(value, field=name)
        elif name == "websocket_extensions":
            result[name] = list(_identifiers(value, field=name))
        elif name in {
            "deployment_bundle_id",
            "clock_source_manifest_id",
            "collector_key_authorization_manifest_id",
            "transport_subscription_policy_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "session_nonce",
            "peer_certificate_sha256",
            "peer_spki_sha256",
            "trust_store_manifest_id",
            "monotonic_clock_domain_id",
            "handshake_request_sha256",
            "handshake_response_sha256",
            "collector_release_hash",
            "collector_runtime_id",
            "collector_attestation_key_id",
        }:
            result[name] = canonical_hash(value, field=name)
        elif name == "parent_transport_session_id":
            result[name] = _optional_hash(value, field=name)
        elif name == "alpn_protocol":
            result[name] = _optional_identifier(value, field=name)
        elif name == "collector_attestation_public_key_hex":
            result[name] = _public_key_bytes(value, field=name).hex()
        elif name in {
            "certificate_verified",
            "hostname_verified",
            "websocket_accept_verified",
        }:
            result[name] = _strict_bool(value, field=name)
        elif name in {
            "connection_generation",
            "websocket_http_status",
            "handshake_started_monotonic_ns",
            "handshake_completed_monotonic_ns",
            "clock_uncertainty_milliseconds",
        }:
            result[name] = canonical_safe_int(value, field=name, minimum=0)
        else:
            result[name] = canonical_identifier(value, field=name)
    return result


def subscription_manifest_hash_v4(topics: Sequence[str]) -> str:
    checked = _identifiers(topics, field="topics", maximum_items=1)
    if len(checked) != 1:
        raise CanonicalizationError("V4.5 subscription manifest requires one topic")
    return sha256_digest(
        {
            "domain": "RiskYieldMMSubscriptionManifestV4_5",
            "ordered_topics": list(checked),
        }
    )


def _request_id(
    value: Any, *, maximum: int = V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH
) -> str:
    checked = canonical_identifier(value, field="request_id", maximum=maximum)
    if _REQUEST_ID_RE.fullmatch(checked) is None:
        raise CanonicalizationError(
            "request_id must contain only ASCII letters, digits, underscore, or hyphen"
        )
    return checked


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundSubscriptionIntentV4:
    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    connection_generation: int
    intent_nonce: str
    request_id: str
    operation: str
    topics: tuple[str, ...]
    subscription_manifest_hash: str
    websocket_opcode: str
    command_base64: str
    command_sha256: str
    authorized_at: datetime
    send_not_after: datetime
    ack_not_after: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "intent_nonce",
            "subscription_manifest_hash",
            "command_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation, field="connection_generation", minimum=1
            ),
        )
        object.__setattr__(self, "request_id", _request_id(self.request_id))
        object.__setattr__(
            self, "operation", canonical_identifier(self.operation, field="operation")
        )
        topics = _identifiers(self.topics, field="topics", maximum_items=1)
        if len(topics) != 1:
            raise CanonicalizationError("V4.5 subscription intent requires one topic")
        object.__setattr__(self, "topics", topics)
        object.__setattr__(
            self,
            "websocket_opcode",
            canonical_identifier(self.websocket_opcode, field="websocket_opcode"),
        )
        if not isinstance(self.command_base64, str):
            raise CanonicalizationError("command_base64 must be a string")
        try:
            command = base64.b64decode(self.command_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise CanonicalizationError(
                "command_base64 is not canonical base64"
            ) from exc
        if base64.b64encode(command).decode("ascii") != self.command_base64:
            raise CanonicalizationError("command_base64 is not canonical base64")
        expected_command = canonical_json_bytes(
            {"args": list(topics), "op": "subscribe", "req_id": self.request_id}
        )
        expected_manifest = subscription_manifest_hash_v4(topics)
        expected_hash = hashlib.sha256(expected_command).hexdigest()
        if (
            self.operation != "subscribe"
            or self.websocket_opcode != "TEXT"
            or command != expected_command
            or self.command_sha256 != expected_hash
            or self.subscription_manifest_hash != expected_manifest
        ):
            raise CanonicalizationError(
                "subscription intent command or derived commitment differs from V4.5"
            )
        authorized = utc_datetime(self.authorized_at, field="authorized_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        ack_by = utc_datetime(self.ack_not_after, field="ack_not_after")
        if not authorized < send_by < ack_by:
            raise CanonicalizationError(
                "subscription deadlines must satisfy authorized_at < send_not_after < ack_not_after"
            )
        object.__setattr__(self, "authorized_at", authorized)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(self, "ack_not_after", ack_by)

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: (
                utc_iso(value)
                if name in {"authorized_at", "send_not_after", "ack_not_after"}
                else list(value)
                if name == "topics"
                else value
            )
            for name, value in (
                (name, getattr(self, name)) for name in self.__dataclass_fields__
            )
        }

    @property
    def outbound_subscription_intent_id(self) -> str:
        return _identity("OutboundSubscriptionIntentV4_5", self.identity_payload())

    @property
    def command_bytes(self) -> bytes:
        return base64.b64decode(self.command_base64, validate=True)

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="outbound_subscription_intent_id",
            identity=self.outbound_subscription_intent_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> OutboundSubscriptionIntentV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "outbound_subscription_intent_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["outbound_subscription_intent_id"],
            item.outbound_subscription_intent_id,
            field="outbound_subscription_intent_id",
        )
        return item


def build_outbound_subscription_intent_v4(
    *,
    transport_subscription_policy_id: str,
    transport_session_id: str,
    physical_scope_manifest_id: str,
    adapter_policy_id: str,
    capture_partition_id: str,
    connection_generation: int,
    intent_nonce: str,
    request_id: str,
    topic: str,
    authorized_at: datetime | str,
    send_not_after: datetime | str,
    ack_not_after: datetime | str,
) -> OutboundSubscriptionIntentV4:
    checked_topic = canonical_identifier(topic, field="topic")
    checked_request = _request_id(request_id)
    command = canonical_json_bytes(
        {"args": [checked_topic], "op": "subscribe", "req_id": checked_request}
    )
    return OutboundSubscriptionIntentV4(
        transport_subscription_policy_id=transport_subscription_policy_id,
        transport_session_id=transport_session_id,
        physical_scope_manifest_id=physical_scope_manifest_id,
        adapter_policy_id=adapter_policy_id,
        capture_partition_id=capture_partition_id,
        connection_generation=connection_generation,
        intent_nonce=intent_nonce,
        request_id=checked_request,
        operation="subscribe",
        topics=(checked_topic,),
        subscription_manifest_hash=subscription_manifest_hash_v4((checked_topic,)),
        websocket_opcode="TEXT",
        command_base64=base64.b64encode(command).decode("ascii"),
        command_sha256=hashlib.sha256(command).hexdigest(),
        authorized_at=authorized_at,
        send_not_after=send_not_after,
        ack_not_after=ack_not_after,
    )


_DISPATCH_SIGNING_DOMAIN = "RiskYieldMMSubscriptionDispatchAttestationV4_5"


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionAckBindingV4:
    transport_subscription_policy_id: str
    transport_session_id: str
    outbound_subscription_intent_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    connection_generation: int
    capture_segment_id: str
    physical_message_id: str
    message_receipt_id: str
    scope_message_sequence: int
    provider_message_disposition_id: str
    message_disposition_id: str
    raw_ack_sha256: str
    echoed_request_id: str
    provider_connection_id: str
    request_command_sha256: str
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    dispatch_started_monotonic_ns: int
    dispatch_completed_monotonic_ns: int
    ack_received_at: datetime
    ack_received_monotonic_ns: int
    bound_at: datetime
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    dispatch_attestation_signature_hex: str

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "outbound_subscription_intent_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "capture_segment_id",
            "physical_message_id",
            "message_receipt_id",
            "provider_message_disposition_id",
            "message_disposition_id",
            "raw_ack_sha256",
            "request_command_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation, field="connection_generation", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "scope_message_sequence",
            canonical_safe_int(
                self.scope_message_sequence, field="scope_message_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self, "echoed_request_id", _request_id(self.echoed_request_id)
        )
        object.__setattr__(
            self,
            "provider_connection_id",
            canonical_identifier(
                self.provider_connection_id, field="provider_connection_id"
            ),
        )
        for field_name in (
            "dispatch_started_monotonic_ns",
            "dispatch_completed_monotonic_ns",
            "ack_received_monotonic_ns",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        started = utc_datetime(self.dispatch_started_at, field="dispatch_started_at")
        completed = utc_datetime(
            self.dispatch_completed_at, field="dispatch_completed_at"
        )
        received = utc_datetime(self.ack_received_at, field="ack_received_at")
        bound = utc_datetime(self.bound_at, field="bound_at")
        object.__setattr__(self, "dispatch_started_at", started)
        object.__setattr__(self, "dispatch_completed_at", completed)
        object.__setattr__(self, "ack_received_at", received)
        object.__setattr__(self, "bound_at", bound)
        if not started <= completed < received <= bound:
            raise CanonicalizationError(
                "dispatch/ACK/binding wall clocks are not causally ordered"
            )
        if not (
            self.dispatch_started_monotonic_ns
            <= self.dispatch_completed_monotonic_ns
            < self.ack_received_monotonic_ns
        ):
            raise CanonicalizationError(
                "dispatch/ACK monotonic clocks are not causally ordered"
            )
        key_id, public_hex, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        signature = _verify_signature(
            public_key=public_key,
            signature_hex=self.dispatch_attestation_signature_hex,
            payload=self.signing_payload(),
        )
        object.__setattr__(self, "dispatch_attestation_signature_hex", signature)

    def identity_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            if name == "dispatch_attestation_signature_hex":
                continue
            value = getattr(self, name)
            payload[name] = (
                utc_iso(value)
                if name
                in {
                    "dispatch_started_at",
                    "dispatch_completed_at",
                    "ack_received_at",
                    "bound_at",
                }
                else value
            )
        return payload

    def signing_payload(self) -> dict[str, Any]:
        return _signature_payload(_DISPATCH_SIGNING_DOMAIN, self.identity_payload())

    @property
    def subscription_ack_binding_id(self) -> str:
        return _identity("SubscriptionAckBindingV4_5", self.identity_payload())

    def verify_signature(self) -> None:
        _, _, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        _verify_signature(
            public_key=public_key,
            signature_hex=self.dispatch_attestation_signature_hex,
            payload=self.signing_payload(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **_record_mapping(
                self,
                identity_field="subscription_ack_binding_id",
                identity=self.subscription_ack_binding_id,
            ),
            "dispatch_attestation_signature_hex": self.dispatch_attestation_signature_hex,
        }

    @classmethod
    def create_signed(cls, *, signer: Any, **fields: Any) -> SubscriptionAckBindingV4:
        key_id, public_hex, _ = _signer_key(signer)
        if any(
            name in fields
            for name in (
                "collector_attestation_key_id",
                "collector_attestation_public_key_hex",
                "dispatch_attestation_signature_hex",
            )
        ):
            raise CanonicalizationError(
                "signed binding key/signature fields are derived"
            )
        unsigned = _binding_identity_payload(
            {
                **fields,
                "collector_attestation_key_id": key_id,
                "collector_attestation_public_key_hex": public_hex,
            }
        )
        signature = _sign(
            signer, _signature_payload(_DISPATCH_SIGNING_DOMAIN, unsigned)
        )
        return cls(
            **fields,
            collector_attestation_key_id=key_id,
            collector_attestation_public_key_hex=public_hex,
            dispatch_attestation_signature_hex=signature,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SubscriptionAckBindingV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "subscription_ack_binding_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["subscription_ack_binding_id"],
            item.subscription_ack_binding_id,
            field="subscription_ack_binding_id",
        )
        return item


def _binding_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    hash_fields = {
        "transport_subscription_policy_id",
        "transport_session_id",
        "outbound_subscription_intent_id",
        "physical_scope_manifest_id",
        "adapter_policy_id",
        "capture_partition_id",
        "capture_segment_id",
        "physical_message_id",
        "message_receipt_id",
        "provider_message_disposition_id",
        "message_disposition_id",
        "raw_ack_sha256",
        "request_command_sha256",
        "collector_attestation_key_id",
    }
    timestamp_fields = {
        "dispatch_started_at",
        "dispatch_completed_at",
        "ack_received_at",
        "bound_at",
    }
    integer_fields = {
        "connection_generation",
        "scope_message_sequence",
        "dispatch_started_monotonic_ns",
        "dispatch_completed_monotonic_ns",
        "ack_received_monotonic_ns",
    }
    for name in SubscriptionAckBindingV4.__dataclass_fields__:
        if name == "dispatch_attestation_signature_hex":
            continue
        if name not in values:
            raise CanonicalizationError(f"signed binding is missing {name}")
        value = values[name]
        if name in hash_fields:
            result[name] = canonical_hash(value, field=name)
        elif name in timestamp_fields:
            result[name] = utc_iso(value, field=name)
        elif name in integer_fields:
            result[name] = canonical_safe_int(value, field=name, minimum=0)
        elif name == "echoed_request_id":
            result[name] = _request_id(value)
        elif name == "collector_attestation_public_key_hex":
            result[name] = _public_key_bytes(value, field=name).hex()
        else:
            result[name] = canonical_identifier(value, field=name)
    return result


class TransportSessionTerminationReasonV4(str, Enum):
    LOCAL_CLOSE = "LOCAL_CLOSE"
    REMOTE_CLOSE = "REMOTE_CLOSE"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    BACKPRESSURE = "BACKPRESSURE"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    ACK_TIMEOUT = "ACK_TIMEOUT"
    PROCESS_RESTART = "PROCESS_RESTART"
    SUPERSEDED = "SUPERSEDED"


_TERMINATION_SIGNING_DOMAIN = "RiskYieldMMTransportSessionTerminationSignatureV4_5"


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportSessionTerminationV4:
    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    capture_partition_id: str
    connection_generation: int
    reason: TransportSessionTerminationReasonV4
    close_code: int | None
    close_reason_digest: str | None
    detected_at: datetime
    detected_monotonic_clock_domain_id: str
    detected_monotonic_ns: int
    recorded_at: datetime
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    signature_hex: str

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "capture_partition_id",
            "detected_monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation, field="connection_generation", minimum=1
            ),
        )
        try:
            reason = (
                self.reason
                if isinstance(self.reason, TransportSessionTerminationReasonV4)
                else TransportSessionTerminationReasonV4(self.reason)
            )
        except (TypeError, ValueError) as exc:
            raise CanonicalizationError(
                "unsupported transport termination reason"
            ) from exc
        object.__setattr__(self, "reason", reason)
        if self.close_code is None:
            close_code = None
        else:
            close_code = canonical_safe_int(
                self.close_code, field="close_code", minimum=0, maximum=65535
            )
        object.__setattr__(self, "close_code", close_code)
        close_digest = _optional_hash(
            self.close_reason_digest, field="close_reason_digest"
        )
        if close_digest is not None and close_code is None:
            raise CanonicalizationError("close_reason_digest requires close_code")
        object.__setattr__(self, "close_reason_digest", close_digest)
        detected = utc_datetime(self.detected_at, field="detected_at")
        recorded = utc_datetime(self.recorded_at, field="recorded_at")
        if recorded < detected:
            raise CanonicalizationError("termination recorded_at precedes detected_at")
        object.__setattr__(self, "detected_at", detected)
        object.__setattr__(self, "recorded_at", recorded)
        object.__setattr__(
            self,
            "detected_monotonic_ns",
            canonical_safe_int(
                self.detected_monotonic_ns,
                field="detected_monotonic_ns",
                minimum=0,
            ),
        )
        key_id, public_hex, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        signature = _verify_signature(
            public_key=public_key,
            signature_hex=self.signature_hex,
            payload=self.signing_payload(),
        )
        object.__setattr__(self, "signature_hex", signature)

    def identity_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            if name == "signature_hex":
                continue
            value = getattr(self, name)
            if name in {"detected_at", "recorded_at"}:
                payload[name] = utc_iso(value)
            elif name == "reason":
                payload[name] = value.value
            else:
                payload[name] = value
        return payload

    def signing_payload(self) -> dict[str, Any]:
        return _signature_payload(_TERMINATION_SIGNING_DOMAIN, self.identity_payload())

    @property
    def transport_session_termination_id(self) -> str:
        return _identity("TransportSessionTerminationV4_5", self.identity_payload())

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
            **_record_mapping(
                self,
                identity_field="transport_session_termination_id",
                identity=self.transport_session_termination_id,
            ),
            "signature_hex": self.signature_hex,
        }

    @classmethod
    def create_signed(
        cls, *, signer: Any, **fields: Any
    ) -> TransportSessionTerminationV4:
        key_id, public_hex, _ = _signer_key(signer)
        if any(
            name in fields
            for name in (
                "collector_attestation_key_id",
                "collector_attestation_public_key_hex",
                "signature_hex",
            )
        ):
            raise CanonicalizationError(
                "signed termination key/signature fields are derived"
            )
        unsigned = _termination_identity_payload(
            {
                **fields,
                "collector_attestation_key_id": key_id,
                "collector_attestation_public_key_hex": public_hex,
            }
        )
        signature = _sign(
            signer, _signature_payload(_TERMINATION_SIGNING_DOMAIN, unsigned)
        )
        return cls(
            **fields,
            collector_attestation_key_id=key_id,
            collector_attestation_public_key_hex=public_hex,
            signature_hex=signature,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportSessionTerminationV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "transport_session_termination_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["transport_session_termination_id"],
            item.transport_session_termination_id,
            field="transport_session_termination_id",
        )
        return item


def _termination_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in TransportSessionTerminationV4.__dataclass_fields__:
        if name == "signature_hex":
            continue
        if name not in values:
            raise CanonicalizationError(f"signed termination is missing {name}")
        value = values[name]
        if name in {
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "capture_partition_id",
            "detected_monotonic_clock_domain_id",
            "collector_attestation_key_id",
        }:
            result[name] = canonical_hash(value, field=name)
        elif name in {"detected_at", "recorded_at"}:
            result[name] = utc_iso(value, field=name)
        elif name in {"connection_generation", "detected_monotonic_ns"}:
            result[name] = canonical_safe_int(value, field=name, minimum=0)
        elif name == "reason":
            try:
                result[name] = TransportSessionTerminationReasonV4(value).value
            except (TypeError, ValueError) as exc:
                raise CanonicalizationError(
                    "unsupported transport termination reason"
                ) from exc
        elif name == "close_code":
            result[name] = (
                None
                if value is None
                else canonical_safe_int(value, field=name, minimum=0, maximum=65535)
            )
        elif name == "close_reason_digest":
            result[name] = _optional_hash(value, field=name)
        elif name == "collector_attestation_public_key_hex":
            result[name] = _public_key_bytes(value, field=name).hex()
        else:  # pragma: no cover - frozen field manifest guards this branch
            raise CanonicalizationError(f"unsupported termination field {name}")
    return result


__all__ = [
    "BYBIT_V5_LINEAR_ENDPOINT_V4",
    "BYBIT_V5_LINEAR_PORT_V4",
    "BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4",
    "BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4",
    "OutboundSubscriptionIntentV4",
    "PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION",
    "SubscriptionAckBindingV4",
    "TransportSessionAttestationV4",
    "TransportSessionTerminationReasonV4",
    "TransportSessionTerminationV4",
    "TransportSubscriptionPolicyV4",
    "V4_TRANSPORT_ACK_DEADLINE_SECONDS",
    "V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE",
    "V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH",
    "V4_TRANSPORT_MINIMUM_TLS_VERSION",
    "V4_TRANSPORT_SEND_DEADLINE_SECONDS",
    "V4_TRANSPORT_WEBSOCKET_HTTP_STATUS",
    "build_outbound_subscription_intent_v4",
    "derive_transport_attestation_key_id",
    "subscription_manifest_hash_v4",
]

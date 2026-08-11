from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import (
    CANONICALIZATION_VERSION,
    MAX_IJSON_INTEGER,
    CanonicalizationError,
    sha256_digest,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_owner_v4 import (
    LINUX_BOOTTIME_CLOCK_PROFILE_V4,
    LINUX_SOCKET_IDENTITY_PROFILE_V4,
    PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION,
    CommittedBoundTransportSessionV4,
    TransportSocketOwnerBindingV4,
    TransportSocketOwnerSnapshotV4,
    derive_linux_boottime_clock_domain_id,
    derive_linux_kernel_socket_identity,
    derive_linux_namespace_id,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
    format_linux_socket_cookie_u64,
)
from riskyieldmm.trading.physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    TransportSessionAttestationV4,
    derive_transport_attestation_key_id,
)

T0 = datetime(2026, 7, 15, 3, 0, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def binding_fields() -> dict[str, object]:
    kernel_boot_id = "1090d9f9-fc63-4bae-a9aa-a8236b5a9ea5"
    time_namespace_id = derive_linux_namespace_id(
        namespace_kind="time",
        stat_device_u64=4,
        stat_inode_u64=4_026_531_834,
    )
    network_namespace_id = derive_linux_namespace_id(
        namespace_kind="net",
        stat_device_u64=4,
        stat_inode_u64=4_026_531_833,
    )
    socket_cookie = format_linux_socket_cookie_u64((1 << 64) - 2)
    kernel_socket_identity = derive_linux_kernel_socket_identity(
        kernel_boot_id=kernel_boot_id,
        network_namespace_id=network_namespace_id,
        socket_cookie_u64=socket_cookie,
    )
    transport_session_id = digest("transport-session")
    writer_fence_token_sha256 = digest("writer-fence-token")
    writer_fence_generation = 7
    socket_lease_nonce_sha256 = derive_transport_socket_lease_nonce_sha256(
        b"runtime-owned-capability-nonce-v47"
    )
    return {
        "transport_session_id": transport_session_id,
        "deployment_bundle_id": digest("deployment-bundle"),
        "transport_subscription_policy_id": digest("transport-policy"),
        "physical_scope_manifest_id": digest("scope"),
        "adapter_policy_id": digest("adapter"),
        "capture_partition_id": digest("partition"),
        "socket_lease_id": derive_transport_socket_lease_id(
            transport_session_id=transport_session_id,
            kernel_socket_identity=kernel_socket_identity,
            socket_lease_nonce_sha256=socket_lease_nonce_sha256,
            writer_fence_token_sha256=writer_fence_token_sha256,
            writer_fence_generation=writer_fence_generation,
        ),
        "socket_lease_nonce_sha256": socket_lease_nonce_sha256,
        "kernel_socket_identity": kernel_socket_identity,
        "socket_identity_profile": LINUX_SOCKET_IDENTITY_PROFILE_V4,
        "socket_cookie_u64": socket_cookie,
        "kernel_boot_id": kernel_boot_id,
        "time_namespace_id": time_namespace_id,
        "network_namespace_id": network_namespace_id,
        "clock_source_manifest_id": digest("clock-source-manifest"),
        "monotonic_clock_domain_id": derive_linux_boottime_clock_domain_id(
            kernel_boot_id=kernel_boot_id,
            time_namespace_id=time_namespace_id,
        ),
        "clock_profile": LINUX_BOOTTIME_CLOCK_PROFILE_V4,
        "clock_resolution_ns": 1,
        "connection_generation": 3,
        "writer_fence_token_sha256": writer_fence_token_sha256,
        "writer_fence_generation": writer_fence_generation,
        "bound_at": T0,
        "bound_monotonic_before_ns": 8_000_000_000,
        "bound_monotonic_after_ns": 8_000_000_123,
        "clock_uncertainty_milliseconds": 2,
    }


def binding(
    signer: Ed25519CheckpointSigner | None = None,
) -> TransportSocketOwnerBindingV4:
    return TransportSocketOwnerBindingV4.create_signed(
        signer=signer or Ed25519CheckpointSigner.generate(),
        **binding_fields(),
    )


def test_socket_owner_snapshot_requires_complete_loaded_chronyd_identity_pair() -> None:
    fields = binding_fields()
    arguments = {
        "kernel_boot_id": fields["kernel_boot_id"],
        "time_namespace_id": fields["time_namespace_id"],
        "network_namespace_id": fields["network_namespace_id"],
        "socket_cookie_u64": fields["socket_cookie_u64"],
        "clock_resolution_ns": 1,
    }
    with pytest.raises(CanonicalizationError, match="must be paired"):
        TransportSocketOwnerSnapshotV4(
            **arguments,
            chronyd_launch_id=digest("launch"),
        )

    snapshot = TransportSocketOwnerSnapshotV4(
        **arguments,
        chronyd_launch_id=digest("launch"),
        chronyd_runtime_observation_sha256=digest("runtime-observation"),
    )
    assert snapshot.chronyd_runtime_observation_sha256 == digest("runtime-observation")


def matching_session_and_binding(
    signer: Ed25519CheckpointSigner,
) -> tuple[TransportSessionAttestationV4, TransportSocketOwnerBindingV4]:
    fields = binding_fields()
    session = TransportSessionAttestationV4.create_signed(
        signer=signer,
        deployment_bundle_id=fields["deployment_bundle_id"],
        clock_source_manifest_id=fields["clock_source_manifest_id"],
        collector_key_authorization_manifest_id=digest("collector-key-authorization"),
        transport_subscription_policy_id=fields["transport_subscription_policy_id"],
        physical_scope_manifest_id=fields["physical_scope_manifest_id"],
        adapter_policy_id=fields["adapter_policy_id"],
        capture_partition_id=fields["capture_partition_id"],
        collector_instance_id="collector-v47",
        collector_boot_id=fields["kernel_boot_id"],
        connection_generation=fields["connection_generation"],
        session_nonce=digest("session-nonce"),
        parent_transport_session_id=None,
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        remote_address="203.0.113.10:443",
        tls_version="TLSv1.3",
        tls_cipher="TLS_AES_128_GCM_SHA256",
        alpn_protocol=None,
        websocket_extensions=(),
        peer_certificate_sha256=digest("peer-certificate"),
        peer_spki_sha256=digest("peer-spki"),
        trust_store_manifest_id=digest("trust-store"),
        certificate_verified=True,
        hostname_verified=True,
        websocket_http_status=101,
        websocket_accept_verified=True,
        handshake_commitment_profile=V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
        handshake_request_sha256=digest("handshake-request"),
        handshake_response_sha256=digest("handshake-response"),
        handshake_started_at=T0 - timedelta(milliseconds=2),
        handshake_completed_at=T0 - timedelta(milliseconds=1),
        monotonic_clock_domain_id=fields["monotonic_clock_domain_id"],
        handshake_started_monotonic_ns=7_999_000_000,
        handshake_completed_monotonic_ns=7_999_500_000,
        clock_uncertainty_milliseconds=fields["clock_uncertainty_milliseconds"],
        collector_release_hash=digest("collector-release"),
        collector_runtime_id=digest("collector-runtime"),
    )
    for name in (
        "transport_session_id",
        "deployment_bundle_id",
        "transport_subscription_policy_id",
        "physical_scope_manifest_id",
        "adapter_policy_id",
        "capture_partition_id",
        "clock_source_manifest_id",
        "monotonic_clock_domain_id",
        "connection_generation",
    ):
        fields[name] = getattr(session, name)
    fields["socket_lease_id"] = derive_transport_socket_lease_id(
        transport_session_id=session.transport_session_id,
        kernel_socket_identity=fields["kernel_socket_identity"],  # type: ignore[arg-type]
        socket_lease_nonce_sha256=fields["socket_lease_nonce_sha256"],  # type: ignore[arg-type]
        writer_fence_token_sha256=fields["writer_fence_token_sha256"],  # type: ignore[arg-type]
        writer_fence_generation=fields["writer_fence_generation"],  # type: ignore[arg-type]
    )
    owner_binding = TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)
    return session, owner_binding


def test_v47_owner_binding_schema_and_linux_profiles_are_exact() -> None:
    assert PHYSICAL_TRANSPORT_OWNER_V4_SCHEMA_VERSION == (
        "riskyieldmm_physical_transport_owner_v4_7"
    )
    assert LINUX_SOCKET_IDENTITY_PROFILE_V4 == "LINUX_SO_COOKIE_BOOT_NETNS_V1"
    assert LINUX_BOOTTIME_CLOCK_PROFILE_V4 == (
        "LINUX_BOOT_ID_TIME_NAMESPACE_CLOCK_BOOTTIME_V1"
    )


def test_owner_binding_round_trips_and_signature_verifies() -> None:
    signer = Ed25519CheckpointSigner.generate()
    item = binding(signer)

    restored = TransportSocketOwnerBindingV4.from_mapping(item.as_dict())

    assert restored == item
    assert len(item.transport_socket_owner_binding_id) == 64
    assert item.collector_attestation_key_id == derive_transport_attestation_key_id(
        signer.public_key_bytes
    )
    item.verify_signature()


def test_owner_binding_has_a_separate_identity_from_transport_session() -> None:
    item = binding()

    assert item.transport_socket_owner_binding_id != item.transport_session_id
    assert item.as_dict()["transport_session_id"] == item.transport_session_id
    assert item.as_dict()["schema_version"] != ("riskyieldmm_physical_transport_v4_5")


def test_committed_bound_session_requires_exact_matching_signed_halves() -> None:
    signer = Ed25519CheckpointSigner.generate()
    session, owner_binding = matching_session_and_binding(signer)

    committed = CommittedBoundTransportSessionV4(session=session, binding=owner_binding)

    assert committed.session is session
    assert committed.binding is owner_binding
    with pytest.raises(TypeError, match="exact TransportSessionAttestationV4"):
        CommittedBoundTransportSessionV4(  # type: ignore[arg-type]
            session=owner_binding, binding=owner_binding
        )
    other_session, _ = matching_session_and_binding(Ed25519CheckpointSigner.generate())
    with pytest.raises(CanonicalizationError, match="transport_session_id"):
        CommittedBoundTransportSessionV4(session=other_session, binding=owner_binding)


def test_owner_binding_signature_rejects_field_mutation_and_key_substitution() -> None:
    signer = Ed25519CheckpointSigner.generate()
    other = Ed25519CheckpointSigner.generate()
    item = binding(signer)

    with pytest.raises(CanonicalizationError, match="signature"):
        replace(item, clock_resolution_ns=item.clock_resolution_ns + 1)
    with pytest.raises(CanonicalizationError, match="signature"):
        replace(item, bound_at="2026-07-15T03:00:01Z")
    with pytest.raises(CanonicalizationError, match="signature"):
        replace(
            item,
            collector_attestation_key_id=derive_transport_attestation_key_id(
                other.public_key_bytes
            ),
            collector_attestation_public_key_hex=other.public_key_bytes.hex(),
        )


def test_create_signed_rejects_caller_supplied_signature_or_key_fields() -> None:
    signer = Ed25519CheckpointSigner.generate()
    for forbidden, value in (
        ("signature_hex", "00" * 64),
        ("collector_attestation_key_id", digest("key")),
        ("collector_attestation_public_key_hex", signer.public_key_bytes.hex()),
    ):
        with pytest.raises(CanonicalizationError, match="derived"):
            TransportSocketOwnerBindingV4.create_signed(
                signer=signer,
                **binding_fields(),
                **{forbidden: value},
            )


def test_mapping_rejects_unknown_versions_fields_and_identity_substitution() -> None:
    item = binding()

    for field_name, value in (
        ("canonicalization_version", "future-canonicalization"),
        ("schema_version", "future-schema"),
        ("transport_socket_owner_binding_id", digest("substituted-binding")),
    ):
        payload = item.as_dict()
        payload[field_name] = value
        with pytest.raises(CanonicalizationError):
            TransportSocketOwnerBindingV4.from_mapping(payload)

    payload = item.as_dict()
    payload["unknown"] = "field"
    with pytest.raises(CanonicalizationError, match="unknown"):
        TransportSocketOwnerBindingV4.from_mapping(payload)
    payload = item.as_dict()
    del payload["clock_profile"]
    with pytest.raises(CanonicalizationError, match="missing"):
        TransportSocketOwnerBindingV4.from_mapping(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("socket_identity_profile", "LINUX_FD_NUMBER_V1"),
        ("clock_profile", "LINUX_BOOT_ID_CLOCK_MONOTONIC_V1"),
    ),
)
def test_owner_binding_rejects_unreviewed_profiles(
    field_name: str, value: object
) -> None:
    fields = binding_fields()
    fields[field_name] = value

    with pytest.raises(CanonicalizationError, match=field_name):
        TransportSocketOwnerBindingV4.create_signed(
            signer=Ed25519CheckpointSigner.generate(), **fields
        )


@pytest.mark.parametrize(
    "value",
    (
        "1",
        "00000000000000001",
        "00000000000000GG",
        "FFFFFFFFFFFFFFFF",
        4097,
        True,
    ),
)
def test_socket_cookie_field_requires_fixed_lowercase_u64_hex(value: object) -> None:
    fields = binding_fields()
    fields["socket_cookie_u64"] = value

    with pytest.raises(CanonicalizationError, match="socket_cookie_u64"):
        TransportSocketOwnerBindingV4.create_signed(
            signer=Ed25519CheckpointSigner.generate(), **fields
        )


def test_socket_cookie_formatter_supports_full_u64_without_ijson_integer() -> None:
    assert format_linux_socket_cookie_u64((1 << 64) - 1) == "ffffffffffffffff"
    with pytest.raises(CanonicalizationError, match="nonzero"):
        format_linux_socket_cookie_u64(0)
    with pytest.raises(CanonicalizationError):
        format_linux_socket_cookie_u64(1 << 64)
    with pytest.raises(CanonicalizationError):
        format_linux_socket_cookie_u64(True)


def test_kernel_socket_identity_is_bound_to_boot_netns_cookie_and_profile() -> None:
    fields = binding_fields()
    baseline = fields["kernel_socket_identity"]

    variants = (
        derive_linux_kernel_socket_identity(
            kernel_boot_id="different-boot",
            network_namespace_id=fields["network_namespace_id"],  # type: ignore[arg-type]
            socket_cookie_u64=fields["socket_cookie_u64"],  # type: ignore[arg-type]
        ),
        derive_linux_kernel_socket_identity(
            kernel_boot_id=fields["kernel_boot_id"],  # type: ignore[arg-type]
            network_namespace_id=digest("different-netns"),
            socket_cookie_u64=fields["socket_cookie_u64"],  # type: ignore[arg-type]
        ),
        derive_linux_kernel_socket_identity(
            kernel_boot_id=fields["kernel_boot_id"],  # type: ignore[arg-type]
            network_namespace_id=fields["network_namespace_id"],  # type: ignore[arg-type]
            socket_cookie_u64="0000000000000001",
        ),
    )

    assert all(identity != baseline for identity in variants)
    fields["kernel_socket_identity"] = digest("unbound-socket")
    with pytest.raises(CanonicalizationError, match="kernel_socket_identity"):
        TransportSocketOwnerBindingV4.create_signed(
            signer=Ed25519CheckpointSigner.generate(), **fields
        )


def test_boottime_clock_domain_is_bound_to_boot_time_namespace_and_profile() -> None:
    fields = binding_fields()
    baseline = fields["monotonic_clock_domain_id"]

    assert (
        derive_linux_boottime_clock_domain_id(
            kernel_boot_id="different-boot",
            time_namespace_id=fields["time_namespace_id"],  # type: ignore[arg-type]
        )
        != baseline
    )
    assert (
        derive_linux_boottime_clock_domain_id(
            kernel_boot_id=fields["kernel_boot_id"],  # type: ignore[arg-type]
            time_namespace_id=digest("different-time-namespace"),
        )
        != baseline
    )
    fields["monotonic_clock_domain_id"] = digest("unbound-clock")
    with pytest.raises(CanonicalizationError, match="monotonic_clock_domain_id"):
        TransportSocketOwnerBindingV4.create_signed(
            signer=Ed25519CheckpointSigner.generate(), **fields
        )


def test_namespace_identity_is_deterministic_domain_separated_and_u64_safe() -> None:
    maximum = (1 << 64) - 1
    time_id = derive_linux_namespace_id(
        namespace_kind="time",
        stat_device_u64=maximum,
        stat_inode_u64=maximum,
    )
    assert time_id == derive_linux_namespace_id(
        namespace_kind="time",
        stat_device_u64=maximum,
        stat_inode_u64=maximum,
    )
    assert time_id != derive_linux_namespace_id(
        namespace_kind="net",
        stat_device_u64=maximum,
        stat_inode_u64=maximum,
    )
    with pytest.raises(CanonicalizationError, match="namespace_kind"):
        derive_linux_namespace_id(
            namespace_kind="mnt", stat_device_u64=1, stat_inode_u64=2
        )
    with pytest.raises(CanonicalizationError, match="unsigned 64-bit"):
        derive_linux_namespace_id(
            namespace_kind="time", stat_device_u64=-1, stat_inode_u64=2
        )
    with pytest.raises(CanonicalizationError, match="integer"):
        derive_linux_namespace_id(
            namespace_kind="time", stat_device_u64=True, stat_inode_u64=2
        )


def test_lease_id_is_deterministic_and_bound_to_session_socket_and_secret_nonce() -> (
    None
):
    fields = binding_fields()
    arguments = {
        "transport_session_id": fields["transport_session_id"],
        "kernel_socket_identity": fields["kernel_socket_identity"],
        "socket_lease_nonce_sha256": derive_transport_socket_lease_nonce_sha256(
            b"0123456789abcdef"
        ),
        "writer_fence_token_sha256": fields["writer_fence_token_sha256"],
        "writer_fence_generation": fields["writer_fence_generation"],
    }
    lease_id = derive_transport_socket_lease_id(**arguments)  # type: ignore[arg-type]

    assert lease_id == derive_transport_socket_lease_id(  # type: ignore[arg-type]
        **arguments
    )
    assert lease_id != derive_transport_socket_lease_id(
        transport_session_id=digest("other-session"),
        kernel_socket_identity=fields["kernel_socket_identity"],  # type: ignore[arg-type]
        socket_lease_nonce_sha256=arguments["socket_lease_nonce_sha256"],  # type: ignore[arg-type]
        writer_fence_token_sha256=arguments["writer_fence_token_sha256"],  # type: ignore[arg-type]
        writer_fence_generation=arguments["writer_fence_generation"],  # type: ignore[arg-type]
    )
    assert lease_id != derive_transport_socket_lease_id(
        transport_session_id=fields["transport_session_id"],  # type: ignore[arg-type]
        kernel_socket_identity=digest("other-socket"),
        socket_lease_nonce_sha256=arguments["socket_lease_nonce_sha256"],  # type: ignore[arg-type]
        writer_fence_token_sha256=arguments["writer_fence_token_sha256"],  # type: ignore[arg-type]
        writer_fence_generation=arguments["writer_fence_generation"],  # type: ignore[arg-type]
    )
    assert lease_id != derive_transport_socket_lease_id(
        transport_session_id=fields["transport_session_id"],  # type: ignore[arg-type]
        kernel_socket_identity=fields["kernel_socket_identity"],  # type: ignore[arg-type]
        socket_lease_nonce_sha256=derive_transport_socket_lease_nonce_sha256(
            b"fedcba9876543210"
        ),
        writer_fence_token_sha256=arguments["writer_fence_token_sha256"],  # type: ignore[arg-type]
        writer_fence_generation=arguments["writer_fence_generation"],  # type: ignore[arg-type]
    )
    assert lease_id != derive_transport_socket_lease_id(
        transport_session_id=fields["transport_session_id"],  # type: ignore[arg-type]
        kernel_socket_identity=fields["kernel_socket_identity"],  # type: ignore[arg-type]
        socket_lease_nonce_sha256=arguments["socket_lease_nonce_sha256"],  # type: ignore[arg-type]
        writer_fence_token_sha256=digest("other-writer-fence"),
        writer_fence_generation=arguments["writer_fence_generation"],  # type: ignore[arg-type]
    )
    assert lease_id != derive_transport_socket_lease_id(
        transport_session_id=fields["transport_session_id"],  # type: ignore[arg-type]
        kernel_socket_identity=fields["kernel_socket_identity"],  # type: ignore[arg-type]
        socket_lease_nonce_sha256=arguments["socket_lease_nonce_sha256"],  # type: ignore[arg-type]
        writer_fence_token_sha256=arguments["writer_fence_token_sha256"],  # type: ignore[arg-type]
        writer_fence_generation=8,
    )
    with pytest.raises(CanonicalizationError, match="at least 16 bytes"):
        derive_transport_socket_lease_nonce_sha256(b"short")


def test_binding_rejects_zero_socket_cookie_and_caller_selected_lease_id() -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = binding_fields()
    fields["socket_cookie_u64"] = "0000000000000000"
    with pytest.raises(CanonicalizationError, match="nonzero"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)

    fields = binding_fields()
    fields["socket_lease_id"] = digest("caller-selected-lease")
    with pytest.raises(CanonicalizationError, match="socket_lease_id differs"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)


@pytest.mark.parametrize(
    "field_name",
    (
        "socket_lease_nonce_sha256",
        "writer_fence_token_sha256",
        "writer_fence_generation",
    ),
)
def test_binding_rejects_lease_input_substitution(field_name: str) -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = binding_fields()
    fields[field_name] = (
        8 if field_name == "writer_fence_generation" else digest(f"other-{field_name}")
    )
    with pytest.raises(CanonicalizationError, match="socket_lease_id differs"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)


def test_binding_accepts_zero_width_bracket_but_rejects_reversed_or_invalid_clock() -> (
    None
):
    signer = Ed25519CheckpointSigner.generate()
    fields = binding_fields()
    fields["bound_monotonic_after_ns"] = fields["bound_monotonic_before_ns"]
    item = TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)
    assert item.bound_monotonic_after_ns == item.bound_monotonic_before_ns

    fields = binding_fields()
    fields["bound_monotonic_after_ns"] = (
        fields["bound_monotonic_before_ns"] - 1  # type: ignore[operator]
    )
    with pytest.raises(CanonicalizationError, match="must not precede"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)

    for field_name, value in (
        ("clock_resolution_ns", 0),
        ("connection_generation", 0),
        ("writer_fence_generation", 0),
        ("clock_uncertainty_milliseconds", -1),
        ("bound_monotonic_before_ns", MAX_IJSON_INTEGER + 1),
    ):
        fields = binding_fields()
        fields[field_name] = value
        with pytest.raises(CanonicalizationError, match=field_name):
            TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)


def test_binding_hash_fields_and_timestamp_are_strictly_canonical() -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = binding_fields()
    fields["socket_lease_id"] = digest("socket").upper()
    with pytest.raises(CanonicalizationError, match="socket_lease_id"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)

    fields = binding_fields()
    fields["bound_at"] = "2026-07-15T03:00:00"
    with pytest.raises(CanonicalizationError, match="bound_at"):
        TransportSocketOwnerBindingV4.create_signed(signer=signer, **fields)


def test_binding_mapping_uses_canonical_utc_and_json_safe_cookie_string() -> None:
    item = binding()
    payload = item.as_dict()

    assert payload["canonicalization_version"] == CANONICALIZATION_VERSION
    assert payload["bound_at"] == "2026-07-15T03:00:00Z"
    assert payload["socket_cookie_u64"] == "fffffffffffffffe"
    assert isinstance(payload["socket_cookie_u64"], str)

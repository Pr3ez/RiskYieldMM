from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_json_bytes,
    sha256_digest,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    CHRONYD_COMMAND_PROXY_PROFILE,
    CHRONYD_FIXED_ENVIRONMENT_SHA256,
    CHRONYD_LAUNCH_PROFILE,
    CHRONYD_SUPERVISOR_PROFILE,
    CLOCK_SOURCE_KIND,
    COLLECTOR_KEY_USAGE,
    DEPENDENCY_LOCK_FORMAT,
    DEPLOYMENT_BUNDLE_SCHEMA_VERSION,
    DEPLOYMENT_DSSE_PAYLOAD_TYPE,
    MONOTONIC_DOMAIN_PROFILE,
    OPERATIONAL_MANIFEST_SCHEMA_VERSION,
    TLS_TRUST_STORE_FORMAT,
    TLS_VERIFY_PURPOSE,
    ChronydLaunchPolicyV48B,
    ClockSourcePolicyManifestV4,
    CollectorKeyAuthorizationManifestV4,
    CollectorReleaseManifestV4,
    DependencyLockManifestV4,
    DeploymentAuthorityCeilingV4,
    DeploymentBundleApprovalV4,
    DeploymentBundleV4,
    DeploymentRoleKeyV4,
    DeploymentTrustRootV4,
    DsseSignatureV4,
    OperationalManifestKindV4,
    OperationalManifestVerificationError,
    RuntimeEnvironmentManifestV4,
    TlsTrustStoreManifestV4,
    approve_deployment_bundle_v4,
    derive_deployment_signing_key_id,
    dsse_pae_v1,
    verify_deployment_bundle_approval_v4,
)
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportCapacityPolicyV49F,
)
from riskyieldmm.trading.physical_transport_v4 import (
    derive_transport_attestation_key_id,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)

UTC = timezone.utc
VALID_FROM = datetime(2026, 1, 1, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 7, 15, tzinfo=UTC)
VALID_UNTIL = datetime(2027, 1, 1, tzinfo=UTC)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def role_key(signer: Ed25519CheckpointSigner) -> DeploymentRoleKeyV4:
    return DeploymentRoleKeyV4(
        key_id=derive_deployment_signing_key_id(signer.public_key_bytes),
        public_key_hex=signer.public_key_bytes.hex(),
    )


@dataclass(frozen=True)
class Graph:
    signers: tuple[Ed25519CheckpointSigner, ...]
    trust_root: DeploymentTrustRootV4
    release: CollectorReleaseManifestV4
    dependency: DependencyLockManifestV4
    trust_store: TlsTrustStoreManifestV4
    clock: ClockSourcePolicyManifestV4
    runtime: RuntimeEnvironmentManifestV4
    key_authorization: CollectorKeyAuthorizationManifestV4
    bundle: DeploymentBundleV4
    approval: DeploymentBundleApprovalV4

    @property
    def children(self) -> tuple[Any, ...]:
        return (
            self.release,
            self.dependency,
            self.trust_store,
            self.clock,
            self.runtime,
            self.key_authorization,
        )


def make_graph(
    *,
    deployment_signer_count: int = 1,
    threshold: int = 1,
    approved_signer_count: int | None = None,
    valid_from: datetime = VALID_FROM,
    valid_until: datetime = VALID_UNTIL,
    key_valid_from: datetime = VALID_FROM,
    key_valid_until: datetime = VALID_UNTIL,
    transport_capacity_policy_v49f: TransportCapacityPolicyV49F | None = None,
) -> Graph:
    signers = tuple(
        Ed25519CheckpointSigner.generate() for _ in range(deployment_signer_count)
    )
    trust_root = DeploymentTrustRootV4(
        root_version=1,
        deployment_role_threshold=threshold,
        deployment_keys=tuple(role_key(signer) for signer in signers),
    )
    release = CollectorReleaseManifestV4(
        release_name="riskyieldmm-collector",
        release_version="0.1.0+transport-v4.5",
        source_tree_sha256=digest("source-tree"),
        build_artifact_sha256=digest("collector-wheel"),
        entrypoint="riskyieldmm.collector:main",
        parser_policy_root_sha256=digest("parser-policy-root"),
    )
    dependency = DependencyLockManifestV4(
        lock_format=DEPENDENCY_LOCK_FORMAT,
        lock_file_sha256=digest("requirements.lock"),
        wheelhouse_root_sha256=digest("wheelhouse"),
        distribution_count=17,
        require_hashes=True,
        only_binary=True,
        fully_pinned=True,
    )
    trust_store = TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=digest("ca-bundle-bytes"),
        ca_bundle_size_bytes=220_000,
        ca_certificate_count=141,
        ca_der_set_root_sha256=digest("sorted-ca-der-set"),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )
    clock = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256=digest("chronyc-executable"),
        chrony_config_path="/etc/chrony/chrony.conf",
        chrony_config_sha256=digest("chrony-config"),
        chronyc_command_socket_path="/run/chrony/chronyd.sock",
        chronyc_command_timeout_milliseconds=2_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=digest("clock-sources"),
        min_selectable_sources=3,
        max_uncertainty_milliseconds=250,
        max_sample_age_milliseconds=2_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path="/run/chrony/chronyd.sock"
        ),
    )
    runtime = RuntimeEnvironmentManifestV4(
        python_implementation="CPython",
        python_version="3.12.11",
        python_executable_sha256=digest("python-executable"),
        platform_tag="manylinux_2_39_x86_64",
        openssl_version="OpenSSL 3.2.4",
        installed_distribution_root_sha256=digest("installed-distributions"),
        dependency_lock_manifest_id=dependency.manifest_id,
        collector_release_manifest_id=release.manifest_id,
        tls_trust_store_manifest_id=trust_store.manifest_id,
        clock_source_policy_manifest_id=clock.manifest_id,
        isolated_mode=True,
        user_site_enabled=False,
        transport_capacity_policy_v49f=transport_capacity_policy_v49f,
    )
    collector_signer = Ed25519CheckpointSigner.generate()
    key_authorization = CollectorKeyAuthorizationManifestV4(
        collector_attestation_key_id=derive_transport_attestation_key_id(
            collector_signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=collector_signer.public_key_bytes.hex(),
        usage=COLLECTOR_KEY_USAGE,
        collector_release_manifest_id=release.manifest_id,
        valid_from=key_valid_from,
        valid_until=key_valid_until,
    )
    bundle = DeploymentBundleV4(
        deployment_trust_root_id=trust_root.trust_root_id,
        deployment_sequence=1,
        parent_deployment_bundle_id=None,
        valid_from=valid_from,
        valid_until=valid_until,
        environment_id="BYBIT_MAINNET_PUBLIC_DATA",
        authority_ceiling=(
            DeploymentAuthorityCeilingV4.PUBLIC_MARKET_DATA_CAPTURE_ONLY
        ),
        collector_release_manifest_id=release.manifest_id,
        dependency_lock_manifest_id=dependency.manifest_id,
        tls_trust_store_manifest_id=trust_store.manifest_id,
        clock_source_policy_manifest_id=clock.manifest_id,
        runtime_environment_manifest_id=runtime.manifest_id,
        collector_key_authorization_manifest_id=key_authorization.manifest_id,
    )
    count = approved_signer_count
    if count is None:
        count = deployment_signer_count
    approval = approve_deployment_bundle_v4(bundle, signers=signers[:count])
    return Graph(
        signers=signers,
        trust_root=trust_root,
        release=release,
        dependency=dependency,
        trust_store=trust_store,
        clock=clock,
        runtime=runtime,
        key_authorization=key_authorization,
        bundle=bundle,
        approval=approval,
    )


def verify(graph: Graph, **overrides: Any):
    arguments = {
        "trust_root": graph.trust_root,
        "expected_trust_root_id": graph.trust_root.trust_root_id,
        "children": graph.children,
        "verified_at": VERIFIED_AT,
    }
    arguments.update(overrides)
    return verify_deployment_bundle_approval_v4(graph.approval, **arguments)


def approval_for_payload(
    payload: bytes, signer: Ed25519CheckpointSigner
) -> DeploymentBundleApprovalV4:
    signature = signer.sign(dsse_pae_v1(DEPLOYMENT_DSSE_PAYLOAD_TYPE, payload))
    return DeploymentBundleApprovalV4(
        payload_type=DEPLOYMENT_DSSE_PAYLOAD_TYPE,
        payload_base64=base64.b64encode(payload).decode("ascii"),
        signatures=(
            DsseSignatureV4(
                key_id=derive_deployment_signing_key_id(signer.public_key_bytes),
                signature_base64=base64.b64encode(signature).decode("ascii"),
            ),
        ),
    )


def test_dsse_pae_matches_official_length_prefixed_shape() -> None:
    assert dsse_pae_v1("text/plain", b"hello") == (b"DSSEv1 10 text/plain 5 hello")


def test_exact_graph_verifies_and_exposes_transport_bindings() -> None:
    graph = make_graph(deployment_signer_count=2, threshold=2)

    capability = verify(graph)

    assert capability.deployment_bundle_id == graph.bundle.deployment_bundle_id
    assert capability.authority_ceiling is (
        DeploymentAuthorityCeilingV4.PUBLIC_MARKET_DATA_CAPTURE_ONLY
    )
    assert set(capability.child_manifest_ids) == {
        child.manifest_id for child in graph.children
    }
    assert capability.valid_from == graph.bundle.valid_from
    assert capability.valid_until == graph.bundle.valid_until
    assert capability.parent_deployment_bundle_id is None
    assert capability.max_uncertainty_milliseconds == 250
    assert capability.max_sample_age_milliseconds == 2_000
    assert capability.transport_session_bindings() == {
        "clock_source_manifest_id": graph.clock.manifest_id,
        "collector_key_authorization_manifest_id": graph.key_authorization.manifest_id,
        "collector_release_hash": graph.release.manifest_id,
        "collector_runtime_id": graph.runtime.manifest_id,
        "deployment_bundle_id": graph.bundle.deployment_bundle_id,
        "trust_store_manifest_id": graph.trust_store.manifest_id,
    }
    assert (
        graph.bundle.child_manifest_id(OperationalManifestKindV4.CLOCK_SOURCE_POLICY)
        == graph.clock.manifest_id
    )
    assert set(graph.bundle.child_manifest_ids_by_kind()) == set(
        OperationalManifestKindV4
    )


def test_signed_runtime_environment_binds_exact_v49f_capacity_policy() -> None:
    policy = TransportCapacityPolicyV49F(
        maximum_active_and_waiting_commands=4,
        maximum_reserved_work_units=89,
        maximum_queue_wait_milliseconds=2_000,
        ingress_reservation_work_units=64,
        subscription_dispatch_reservation_work_units=16,
        ack_deadline_expiry_reservation_work_units=1,
        local_shutdown_reservation_work_units=8,
    )
    graph = make_graph(transport_capacity_policy_v49f=policy)

    capability = verify(graph)

    assert graph.runtime.transport_capacity_policy_v49f == policy
    assert (
        RuntimeEnvironmentManifestV4.from_mapping(
            graph.runtime.as_dict()
        ).transport_capacity_policy_v49f
        == policy
    )
    assert capability.transport_capacity_policy_id_v49f == policy.policy_id
    assert capability.require_transport_capacity_policy_id_v49f() == policy.policy_id

    unsigned = verify(make_graph())
    with pytest.raises(
        OperationalManifestVerificationError, match="signed V4.9F policy"
    ):
        unsigned.require_transport_capacity_policy_id_v49f()


def test_v49f_policy_change_propagates_to_runtime_and_bundle_identity() -> None:
    policy = TransportCapacityPolicyV49F(
        maximum_active_and_waiting_commands=4,
        maximum_reserved_work_units=89,
        maximum_queue_wait_milliseconds=2_000,
        ingress_reservation_work_units=64,
        subscription_dispatch_reservation_work_units=16,
        ack_deadline_expiry_reservation_work_units=1,
        local_shutdown_reservation_work_units=8,
    )
    graph = make_graph(transport_capacity_policy_v49f=policy)
    changed_policy = replace(policy, maximum_queue_wait_milliseconds=1_999)
    changed_runtime = replace(
        graph.runtime,
        transport_capacity_policy_v49f=changed_policy,
    )
    changed_bundle = replace(
        graph.bundle,
        runtime_environment_manifest_id=changed_runtime.manifest_id,
    )

    assert changed_policy.policy_id != policy.policy_id
    assert changed_runtime.manifest_id != graph.runtime.manifest_id
    assert changed_bundle.deployment_bundle_id != graph.bundle.deployment_bundle_id

    substituted_graph = replace(
        graph,
        runtime=changed_runtime,
        bundle=changed_bundle,
    )
    with pytest.raises(OperationalManifestVerificationError):
        verify(substituted_graph)


@pytest.mark.parametrize(
    "attribute",
    [
        "release",
        "dependency",
        "trust_store",
        "clock",
        "runtime",
        "key_authorization",
    ],
)
def test_child_manifest_round_trip_is_exact(attribute: str) -> None:
    graph = make_graph()
    manifest = getattr(graph, attribute)

    restored = type(manifest).from_mapping(manifest.as_dict())

    assert restored == manifest
    assert restored.manifest_id == manifest.manifest_id


def test_chronyd_launch_policy_round_trip_and_parent_schema_are_exact() -> None:
    graph = make_graph()
    policy = graph.clock.chronyd_launch_policy

    assert ChronydLaunchPolicyV48B.from_mapping(policy.as_dict()) == policy
    assert graph.clock.as_dict()["chronyd_launch_policy"] == policy.as_dict()
    assert OPERATIONAL_MANIFEST_SCHEMA_VERSION == (
        "riskyieldmm_operational_manifest_v4_9f"
    )
    assert graph.clock.as_dict()["schema_version"] == (
        "riskyieldmm_operational_manifest_v4_9f"
    )
    assert CHRONYD_FIXED_ENVIRONMENT_SHA256 == sha256_digest(
        {
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "TZ": "UTC",
        }
    )


def test_chronyd_launch_policy_rejects_unknown_nested_field() -> None:
    graph = make_graph()
    payload = graph.clock.as_dict()
    launch_policy = dict(payload["chronyd_launch_policy"])
    launch_policy["surprise"] = "unsigned"
    payload["chronyd_launch_policy"] = launch_policy

    with pytest.raises(CanonicalizationError, match="keys do not match"):
        ClockSourcePolicyManifestV4.from_mapping(payload)


@pytest.mark.parametrize(
    ("field_name", "expected_profile"),
    [
        ("launch_profile", CHRONYD_LAUNCH_PROFILE),
        ("supervisor_profile", CHRONYD_SUPERVISOR_PROFILE),
        ("command_proxy_profile", CHRONYD_COMMAND_PROXY_PROFILE),
    ],
)
def test_chronyd_launch_policy_rejects_unreviewed_constant_profile(
    field_name: str, expected_profile: str
) -> None:
    policy = make_graph().clock.chronyd_launch_policy
    assert getattr(policy, field_name) == expected_profile

    with pytest.raises(CanonicalizationError, match="not the reviewed chronyd"):
        replace(policy, **{field_name: "UNREVIEWED_PROFILE"})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"real_command_socket_path": "/run/outside/chronyd.sock"},
            "directly contained",
        ),
        (
            {"notify_socket_path": "/run/outside/notify.sock"},
            "directly contained",
        ),
        (
            {"read_only_api_socket_path": "/run/outside/api.sock"},
            "directly contained",
        ),
        ({"runtime_directory_path": "/"}, "dedicated non-root"),
    ],
)
def test_chronyd_launch_policy_rejects_ambiguous_path_topology(
    changes: dict[str, Any], message: str
) -> None:
    policy = make_graph().clock.chronyd_launch_policy

    with pytest.raises(CanonicalizationError, match=message):
        replace(policy, **changes)


def test_chronyd_launch_policy_rejects_duplicate_socket_paths() -> None:
    policy = make_graph().clock.chronyd_launch_policy

    with pytest.raises(CanonicalizationError, match="paths must be distinct"):
        replace(policy, notify_socket_path=policy.read_only_api_socket_path)


def test_chronyd_launch_policy_reserves_ephemeral_query_socket_headroom() -> None:
    policy = make_graph().clock.chronyd_launch_policy
    target_directory_bytes = 80
    component = "s" * (
        target_directory_bytes - len(policy.runtime_directory_path.encode("utf-8")) - 1
    )
    supervisor_directory = f"{policy.runtime_directory_path}/{component}"
    assert len(supervisor_directory.encode("utf-8")) == target_directory_bytes
    assert len(f"{supervisor_directory}/readonly.sock".encode()) < 108

    with pytest.raises(CanonicalizationError, match="query-socket headroom"):
        replace(
            policy,
            supervisor_socket_directory_path=supervisor_directory,
            notify_socket_path=f"{supervisor_directory}/notify.sock",
            read_only_api_socket_path=f"{supervisor_directory}/readonly.sock",
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"systemd_unit_name": "../chronyd.service"}, "slash-free"),
        ({"systemd_unit_name": "other.service"}, "unit path basename"),
        ({"systemd_unit_name": "chronyd.socket"}, "slash-free"),
        ({"post_drop_user_name": "Chrony"}, "POSIX account name"),
        ({"post_drop_user_name": "chrony.user"}, "POSIX account name"),
        ({"post_drop_uid": 0}, "post_drop_uid must be at least 1"),
        ({"post_drop_gid": 0}, "post_drop_gid must be at least 1"),
        (
            {"ready_timeout_milliseconds": 249},
            "ready_timeout_milliseconds must be at least 250",
        ),
        (
            {"ready_timeout_milliseconds": 30_001},
            "ready_timeout_milliseconds must be at most 30000",
        ),
        (
            {"maximum_datagram_bytes": 65_537},
            "maximum_datagram_bytes must be at most 65536",
        ),
    ],
)
def test_chronyd_launch_policy_rejects_unsealed_identity_or_bound(
    changes: dict[str, Any], message: str
) -> None:
    policy = make_graph().clock.chronyd_launch_policy

    with pytest.raises(CanonicalizationError, match=message):
        replace(policy, **changes)


def test_chronyd_launch_policy_rejects_wrong_fixed_environment() -> None:
    policy = make_graph().clock.chronyd_launch_policy

    with pytest.raises(CanonicalizationError, match="reviewed environment"):
        replace(policy, fixed_environment_sha256=digest("different-environment"))


def test_clock_policy_binds_chronyc_to_governed_read_only_api() -> None:
    clock = make_graph().clock

    with pytest.raises(CanonicalizationError, match="read-only API socket"):
        replace(clock, chronyc_command_socket_path="/run/chrony/other.sock")


def test_root_bundle_and_dsse_round_trip_are_exact() -> None:
    graph = make_graph(deployment_signer_count=2, threshold=2)

    assert DeploymentTrustRootV4.from_mapping(graph.trust_root.as_dict()) == (
        graph.trust_root
    )
    assert DeploymentBundleV4.from_mapping(graph.bundle.as_dict()) == graph.bundle
    assert DeploymentBundleApprovalV4.from_mapping(graph.approval.as_dict()) == (
        graph.approval
    )
    assert graph.approval.deployment_bundle == graph.bundle
    assert graph.approval.deployment_bundle_id == graph.bundle.deployment_bundle_id


def test_trust_root_rejects_noncanonical_key_order() -> None:
    graph = make_graph(deployment_signer_count=2, threshold=2)
    payload = graph.trust_root.as_dict()
    payload["keys"] = list(reversed(payload["keys"]))

    with pytest.raises(CanonicalizationError, match="canonical key-ID order"):
        DeploymentTrustRootV4.from_mapping(payload)


def test_child_unknown_field_is_rejected() -> None:
    graph = make_graph()
    payload = {**graph.release.as_dict(), "surprise": "value"}

    with pytest.raises(CanonicalizationError, match="keys do not match"):
        CollectorReleaseManifestV4.from_mapping(payload)


def test_child_identity_detects_content_substitution() -> None:
    graph = make_graph()
    payload = {
        **graph.release.as_dict(),
        "build_artifact_sha256": digest("substituted-wheel"),
    }

    with pytest.raises(CanonicalizationError, match="manifest_id differs"):
        CollectorReleaseManifestV4.from_mapping(payload)


def test_false_dependency_security_claim_is_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="require_hashes must be true"):
        DependencyLockManifestV4(
            lock_format=DEPENDENCY_LOCK_FORMAT,
            lock_file_sha256=digest("lock"),
            wheelhouse_root_sha256=digest("wheelhouse"),
            distribution_count=1,
            require_hashes=False,
            only_binary=True,
            fully_pinned=True,
        )


def test_root_key_identifier_is_bound_to_public_key() -> None:
    signer = Ed25519CheckpointSigner.generate()

    with pytest.raises(CanonicalizationError, match="differs from its public key"):
        DeploymentRoleKeyV4(
            key_id=digest("invented-key-id"),
            public_key_hex=signer.public_key_bytes.hex(),
        )


def test_root_threshold_cannot_exceed_distinct_keys() -> None:
    signer = Ed25519CheckpointSigner.generate()

    with pytest.raises(CanonicalizationError, match="at most 1"):
        DeploymentTrustRootV4(
            root_version=1,
            deployment_role_threshold=2,
            deployment_keys=(role_key(signer),),
        )


def test_out_of_band_root_pin_rejects_self_authorized_bundle() -> None:
    pinned = make_graph()
    attacker = make_graph()

    with pytest.raises(
        OperationalManifestVerificationError, match="out-of-band pinned root"
    ):
        verify(
            attacker,
            expected_trust_root_id=pinned.trust_root.trust_root_id,
        )


def test_threshold_requires_distinct_valid_approvals() -> None:
    graph = make_graph(
        deployment_signer_count=2,
        threshold=2,
        approved_signer_count=1,
    )

    with pytest.raises(
        OperationalManifestVerificationError, match="does not meet.*threshold"
    ):
        verify(graph)


def test_untrusted_signature_key_is_rejected() -> None:
    trusted = make_graph()
    untrusted_signer = Ed25519CheckpointSigner.generate()
    approval = approve_deployment_bundle_v4(trusted.bundle, signers=(untrusted_signer,))

    with pytest.raises(
        OperationalManifestVerificationError, match="untrusted deployment key"
    ):
        verify_deployment_bundle_approval_v4(
            approval,
            trust_root=trusted.trust_root,
            expected_trust_root_id=trusted.trust_root.trust_root_id,
            children=trusted.children,
            verified_at=VERIFIED_AT,
        )


def test_invalid_dsse_signature_is_rejected() -> None:
    graph = make_graph()
    original = graph.approval.signatures[0]
    replacement = base64.b64encode(b"\x00" * 64).decode("ascii")
    assert replacement != original.signature_base64
    approval = replace(
        graph.approval,
        signatures=(replace(original, signature_base64=replacement),),
    )

    with pytest.raises(
        OperationalManifestVerificationError, match="signature is invalid"
    ):
        verify_deployment_bundle_approval_v4(
            approval,
            trust_root=graph.trust_root,
            expected_trust_root_id=graph.trust_root.trust_root_id,
            children=graph.children,
            verified_at=VERIFIED_AT,
        )


def test_duplicate_dsse_key_id_is_rejected_before_threshold_counting() -> None:
    graph = make_graph()
    signature = graph.approval.signatures[0]

    with pytest.raises(CanonicalizationError, match="duplicate key IDs"):
        DeploymentBundleApprovalV4(
            payload_type=graph.approval.payload_type,
            payload_base64=graph.approval.payload_base64,
            signatures=(signature, signature),
        )


def test_wrong_dsse_payload_type_is_rejected() -> None:
    graph = make_graph()

    with pytest.raises(CanonicalizationError, match="payload type differs"):
        replace(graph.approval, payload_type="application/json")


def test_valid_signature_over_noncanonical_json_is_still_rejected() -> None:
    graph = make_graph()
    canonical = graph.bundle.as_dict()
    noncanonical = (
        "  " + canonical_json_bytes(canonical).decode("utf-8") + "\n"
    ).encode("utf-8")
    approval = approval_for_payload(noncanonical, graph.signers[0])

    with pytest.raises(
        OperationalManifestVerificationError, match="not exact canonical JSON"
    ):
        verify_deployment_bundle_approval_v4(
            approval,
            trust_root=graph.trust_root,
            expected_trust_root_id=graph.trust_root.trust_root_id,
            children=graph.children,
            verified_at=VERIFIED_AT,
        )


def test_valid_signature_over_wrong_bundle_schema_is_rejected() -> None:
    graph = make_graph()
    payload = {
        **graph.bundle.as_dict(),
        "schema_version": "riskyieldmm_operational_deployment_bundle_v999",
    }
    approval = approval_for_payload(canonical_json_bytes(payload), graph.signers[0])

    with pytest.raises(
        OperationalManifestVerificationError, match="not a valid V4.5 bundle"
    ):
        verify_deployment_bundle_approval_v4(
            approval,
            trust_root=graph.trust_root,
            expected_trust_root_id=graph.trust_root.trust_root_id,
            children=graph.children,
            verified_at=VERIFIED_AT,
        )


def test_missing_child_is_rejected() -> None:
    graph = make_graph()

    with pytest.raises(
        OperationalManifestVerificationError, match="exact six-child closure"
    ):
        verify(graph, children=graph.children[:-1])


def test_duplicate_child_role_is_rejected() -> None:
    graph = make_graph()
    children = (*graph.children[:-1], graph.release)

    with pytest.raises(
        OperationalManifestVerificationError, match="duplicate child role"
    ):
        verify(graph, children=children)


def test_top_level_child_id_substitution_is_rejected() -> None:
    graph = make_graph()
    substituted_release = replace(
        graph.release, build_artifact_sha256=digest("different-release")
    )
    children = (substituted_release, *graph.children[1:])

    with pytest.raises(
        OperationalManifestVerificationError,
        match="collector_release_manifest_id differs",
    ):
        verify(graph, children=children)


def test_cross_manifest_runtime_binding_is_rechecked() -> None:
    graph = make_graph()
    substituted_dependency = replace(
        graph.dependency, lock_file_sha256=digest("different-lock")
    )
    substituted_bundle = replace(
        graph.bundle,
        dependency_lock_manifest_id=substituted_dependency.manifest_id,
    )
    approval = approve_deployment_bundle_v4(substituted_bundle, signers=graph.signers)
    children = (
        graph.release,
        substituted_dependency,
        graph.trust_store,
        graph.clock,
        graph.runtime,
        graph.key_authorization,
    )

    with pytest.raises(
        OperationalManifestVerificationError, match="one exact composition"
    ):
        verify_deployment_bundle_approval_v4(
            approval,
            trust_root=graph.trust_root,
            expected_trust_root_id=graph.trust_root.trust_root_id,
            children=children,
            verified_at=VERIFIED_AT,
        )


@pytest.mark.parametrize(
    "verified_at",
    [VALID_FROM.replace(year=2025), VALID_UNTIL],
)
def test_bundle_outside_half_open_validity_interval_is_rejected(
    verified_at: datetime,
) -> None:
    graph = make_graph()

    with pytest.raises(
        OperationalManifestVerificationError, match="not valid.*governed.*time"
    ):
        verify(graph, verified_at=verified_at)


def test_collector_key_authorization_must_cover_bundle_interval() -> None:
    graph = make_graph(key_valid_until=datetime(2026, 12, 1, tzinfo=UTC))

    with pytest.raises(
        OperationalManifestVerificationError,
        match="key authorization does not cover",
    ):
        verify(graph)


def test_collector_key_id_uses_transport_domain_not_deployment_domain() -> None:
    signer = Ed25519CheckpointSigner.generate()

    with pytest.raises(CanonicalizationError, match="transport public key"):
        CollectorKeyAuthorizationManifestV4(
            collector_attestation_key_id=derive_deployment_signing_key_id(
                signer.public_key_bytes
            ),
            collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
            usage=COLLECTOR_KEY_USAGE,
            collector_release_manifest_id=digest("release"),
            valid_from=VALID_FROM,
            valid_until=VALID_UNTIL,
        )


def test_expected_loaded_collector_key_must_match_authorization() -> None:
    graph = make_graph()

    with pytest.raises(
        OperationalManifestVerificationError, match="loaded collector key"
    ):
        verify(
            graph,
            expected_collector_attestation_key_id=digest("different-key"),
        )


def test_bundle_cannot_claim_trading_authority() -> None:
    graph = make_graph()
    payload = graph.bundle.as_dict()
    payload["authority_ceiling"] = "ORDER_EXECUTION"
    payload["deployment_bundle_id"] = sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": "RiskYieldMMOperationalDeploymentBundleIdentityV4_5",
            "payload": {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "canonicalization_version",
                    "deployment_bundle_id",
                    "schema_version",
                }
            },
            "schema_version": DEPLOYMENT_BUNDLE_SCHEMA_VERSION,
        }
    )

    with pytest.raises(CanonicalizationError, match="authority ceiling"):
        DeploymentBundleV4.from_mapping(payload)


def test_successor_requires_parent_and_genesis_rejects_parent() -> None:
    graph = make_graph()

    with pytest.raises(CanonicalizationError, match="successor requires a parent"):
        replace(graph.bundle, deployment_sequence=2)
    with pytest.raises(CanonicalizationError, match="genesis cannot have a parent"):
        replace(
            graph.bundle,
            parent_deployment_bundle_id=digest("unexpected-parent"),
        )


def test_bundle_approval_signs_exact_canonical_bundle_bytes() -> None:
    graph = make_graph()

    assert graph.approval.payload_bytes == canonical_json_bytes(graph.bundle.as_dict())
    assert graph.approval.payload_type == DEPLOYMENT_DSSE_PAYLOAD_TYPE

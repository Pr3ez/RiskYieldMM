from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    CLOCK_SOURCE_KIND,
    COLLECTOR_KEY_USAGE,
    DEPENDENCY_LOCK_FORMAT,
    MONOTONIC_DOMAIN_PROFILE,
    TLS_TRUST_STORE_FORMAT,
    TLS_VERIFY_PURPOSE,
    ClockSourcePolicyManifestV4,
    CollectorKeyAuthorizationManifestV4,
    CollectorReleaseManifestV4,
    DependencyLockManifestV4,
    DeploymentAuthorityCeilingV4,
    DeploymentBundleApprovalV4,
    DeploymentBundleV4,
    DeploymentRoleKeyV4,
    DeploymentTrustRootV4,
    RuntimeEnvironmentManifestV4,
    TlsTrustStoreManifestV4,
    approve_deployment_bundle_v4,
    derive_deployment_signing_key_id,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4IdempotencyError,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    derive_linux_boottime_clock_domain_id,
)
from riskyieldmm.trading.physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_PORT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
    V4_TRANSPORT_ACK_DEADLINE_SECONDS,
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH,
    V4_TRANSPORT_MINIMUM_TLS_VERSION,
    V4_TRANSPORT_SEND_DEADLINE_SECONDS,
    V4_TRANSPORT_WEBSOCKET_HTTP_STATUS,
    TransportSessionAttestationV4,
    TransportSubscriptionPolicyV4,
    derive_transport_attestation_key_id,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)
from tests.test_trading_physical_authority_v4_projection import (
    FixedClock,
    authority_scope,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    segment,
    status_policy,
)
from tests.test_trading_physical_transport_v4_projection import (
    append_test_bound_session,
)

VALID_FROM = T0 - timedelta(hours=2)
VERIFIED_AT = T0 - timedelta(minutes=30)
VALID_UNTIL = T0 + timedelta(days=2)


def digest(label: str) -> str:
    return sha256_digest({"operational-projection-test": label})


@dataclass(frozen=True, slots=True)
class DeploymentGraph:
    deployment_signer: Ed25519CheckpointSigner
    collector_signer: Ed25519CheckpointSigner
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
    def children(self):
        return (
            self.release,
            self.dependency,
            self.trust_store,
            self.clock,
            self.runtime,
            self.key_authorization,
        )


def deployment_graph(*, environment_id: str = "MAINNET") -> DeploymentGraph:
    deployment_signer = Ed25519CheckpointSigner.generate()
    collector_signer = Ed25519CheckpointSigner.generate()
    role_key = DeploymentRoleKeyV4(
        key_id=derive_deployment_signing_key_id(deployment_signer.public_key_bytes),
        public_key_hex=deployment_signer.public_key_bytes.hex(),
    )
    root = DeploymentTrustRootV4(
        root_version=1,
        deployment_role_threshold=1,
        deployment_keys=(role_key,),
    )
    release = CollectorReleaseManifestV4(
        release_name="riskyieldmm-collector",
        release_version="0.1.0+projection-v4.5",
        source_tree_sha256=digest("source-tree"),
        build_artifact_sha256=digest("collector-wheel"),
        entrypoint="riskyieldmm.collector:main",
        parser_policy_root_sha256=digest("parser-policy-root"),
    )
    dependency = DependencyLockManifestV4(
        lock_format=DEPENDENCY_LOCK_FORMAT,
        lock_file_sha256=digest("requirements-lock"),
        wheelhouse_root_sha256=digest("wheelhouse"),
        distribution_count=17,
        require_hashes=True,
        only_binary=True,
        fully_pinned=True,
    )
    trust_store = TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=digest("ca-bundle"),
        ca_bundle_size_bytes=220_000,
        ca_certificate_count=141,
        ca_der_set_root_sha256=digest("ca-der-set"),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )
    clock = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256=digest("chronyc"),
        chrony_config_path="/etc/chrony/chrony.conf",
        chrony_config_sha256=digest("chrony-config"),
        chronyc_command_socket_path="/run/chrony/chronyd.sock",
        chronyc_command_timeout_milliseconds=2_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=digest("clock-sources"),
        min_selectable_sources=3,
        max_uncertainty_milliseconds=100,
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
        python_executable_sha256=digest("python"),
        platform_tag="manylinux_2_39_x86_64",
        openssl_version="OpenSSL 3.2.4",
        installed_distribution_root_sha256=digest("installed-distributions"),
        dependency_lock_manifest_id=dependency.manifest_id,
        collector_release_manifest_id=release.manifest_id,
        tls_trust_store_manifest_id=trust_store.manifest_id,
        clock_source_policy_manifest_id=clock.manifest_id,
        isolated_mode=True,
        user_site_enabled=False,
    )
    key_authorization = CollectorKeyAuthorizationManifestV4(
        collector_attestation_key_id=derive_transport_attestation_key_id(
            collector_signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=collector_signer.public_key_bytes.hex(),
        usage=COLLECTOR_KEY_USAGE,
        collector_release_manifest_id=release.manifest_id,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
    )
    bundle = DeploymentBundleV4(
        deployment_trust_root_id=root.trust_root_id,
        deployment_sequence=1,
        parent_deployment_bundle_id=None,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        environment_id=environment_id,
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
    approval = approve_deployment_bundle_v4(
        bundle,
        signers=(deployment_signer,),
    )
    return DeploymentGraph(
        deployment_signer=deployment_signer,
        collector_signer=collector_signer,
        trust_root=root,
        release=release,
        dependency=dependency,
        trust_store=trust_store,
        clock=clock,
        runtime=runtime,
        key_authorization=key_authorization,
        bundle=bundle,
        approval=approval,
    )


def append_graph(
    store: PhysicalProjectionStoreV4,
    graph: DeploymentGraph,
) -> None:
    store.append_deployment_trust_root(
        graph.trust_root,
        idempotency_key="deployment-root",
    )
    for child in graph.children:
        store.append_operational_child_manifest(
            child,
            idempotency_key=f"deployment-child-{child.KIND.value.lower()}",
        )
    store.append_deployment_bundle_approval(
        graph.approval,
        verified_at=VERIFIED_AT,
        idempotency_key="deployment-approval-1",
    )


def successor_approval(
    graph: DeploymentGraph,
    *,
    deployment_sequence: int = 2,
    parent_deployment_bundle_id: str | None = None,
    key_authorization: CollectorKeyAuthorizationManifestV4 | None = None,
) -> tuple[DeploymentBundleV4, DeploymentBundleApprovalV4]:
    authorization = key_authorization or graph.key_authorization
    parent = (
        graph.bundle.deployment_bundle_id
        if parent_deployment_bundle_id is None
        else parent_deployment_bundle_id
    )
    bundle = DeploymentBundleV4(
        deployment_trust_root_id=graph.trust_root.trust_root_id,
        deployment_sequence=deployment_sequence,
        parent_deployment_bundle_id=parent,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        environment_id=graph.bundle.environment_id,
        authority_ceiling=graph.bundle.authority_ceiling,
        collector_release_manifest_id=graph.release.manifest_id,
        dependency_lock_manifest_id=graph.dependency.manifest_id,
        tls_trust_store_manifest_id=graph.trust_store.manifest_id,
        clock_source_policy_manifest_id=graph.clock.manifest_id,
        runtime_environment_manifest_id=graph.runtime.manifest_id,
        collector_key_authorization_manifest_id=authorization.manifest_id,
    )
    return bundle, approve_deployment_bundle_v4(
        bundle,
        signers=(graph.deployment_signer,),
    )


def transport_policy(
    graph: DeploymentGraph,
    *,
    frozen_at: datetime,
) -> TransportSubscriptionPolicyV4:
    return TransportSubscriptionPolicyV4(
        deployment_bundle_id=graph.bundle.deployment_bundle_id,
        collector_key_authorization_manifest_id=(graph.key_authorization.manifest_id),
        policy_name="bybit-linear-v45-transport",
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        port=BYBIT_V5_LINEAR_PORT_V4,
        websocket_path=BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
        direct_connection_only=True,
        minimum_tls_version=V4_TRANSPORT_MINIMUM_TLS_VERSION,
        certificate_verification_required=True,
        hostname_verification_required=True,
        websocket_http_status_required=V4_TRANSPORT_WEBSOCKET_HTTP_STATUS,
        websocket_accept_validation_required=True,
        allowed_websocket_extensions=(),
        allowed_subprotocols=(),
        single_topic_per_session=True,
        maximum_inflight_subscriptions=1,
        require_nonempty_echoed_request_id=True,
        maximum_request_id_length=V4_TRANSPORT_MAXIMUM_REQUEST_ID_LENGTH,
        send_deadline_seconds=V4_TRANSPORT_SEND_DEADLINE_SECONDS,
        ack_deadline_seconds=V4_TRANSPORT_ACK_DEADLINE_SECONDS,
        collector_attestation_key_id=(
            graph.key_authorization.collector_attestation_key_id
        ),
        collector_attestation_public_key_hex=(
            graph.key_authorization.collector_attestation_public_key_hex
        ),
        frozen_at=frozen_at,
    )


def prepare_transport_authority(
    store: PhysicalProjectionStoreV4,
    graph: DeploymentGraph,
):
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    store.append_health_policy(idempotency_key="health-policy")
    store.append_adapter_policy(primary, idempotency_key="primary-adapter")
    store.append_adapter_policy(required_status, idempotency_key="status-adapter")
    store.append_scope(scope, idempotency_key="physical-scope")
    policy = transport_policy(graph, frozen_at=scope.frozen_at)
    store.append_transport_subscription_policy(
        policy,
        idempotency_key="transport-policy",
    )
    return primary, scope, policy


def signed_session(
    graph: DeploymentGraph,
    *,
    primary,
    scope,
    policy: TransportSubscriptionPolicyV4,
    clock_uncertainty_milliseconds: int = 50,
    trust_store_manifest_id: str | None = None,
    session_nonce: str | None = None,
) -> TransportSessionAttestationV4:
    partition_probe = replace(
        segment(primary, b"{}", received_at=T0),
        collector_instance_id="collector-a",
        collector_boot_id="boot-a",
    )
    return TransportSessionAttestationV4.create_signed(
        signer=graph.collector_signer,
        deployment_bundle_id=graph.bundle.deployment_bundle_id,
        clock_source_manifest_id=graph.clock.manifest_id,
        collector_key_authorization_manifest_id=(graph.key_authorization.manifest_id),
        transport_subscription_policy_id=policy.transport_subscription_policy_id,
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        adapter_policy_id=primary.adapter_policy_id,
        capture_partition_id=partition_probe.capture_partition_id,
        collector_instance_id="collector-a",
        collector_boot_id="boot-a",
        connection_generation=1,
        session_nonce=session_nonce or digest("session-nonce"),
        parent_transport_session_id=None,
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        remote_address="bybit-edge-diagnostic",
        tls_version=V4_TRANSPORT_MINIMUM_TLS_VERSION,
        tls_cipher="TLS_AES_128_GCM_SHA256",
        alpn_protocol=None,
        websocket_extensions=(),
        peer_certificate_sha256=digest("leaf-certificate"),
        peer_spki_sha256=digest("leaf-spki"),
        trust_store_manifest_id=(
            graph.trust_store.manifest_id
            if trust_store_manifest_id is None
            else trust_store_manifest_id
        ),
        certificate_verified=True,
        hostname_verified=True,
        websocket_http_status=V4_TRANSPORT_WEBSOCKET_HTTP_STATUS,
        websocket_accept_verified=True,
        handshake_commitment_profile=V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
        handshake_request_sha256=digest("handshake-request"),
        handshake_response_sha256=digest("handshake-response"),
        handshake_started_at=T0 - timedelta(seconds=2),
        handshake_completed_at=T0 - timedelta(seconds=1),
        handshake_started_monotonic_ns=100_000_000,
        handshake_completed_monotonic_ns=200_000_000,
        monotonic_clock_domain_id=derive_linux_boottime_clock_domain_id(
            kernel_boot_id="boot-a",
            time_namespace_id=digest("test-time-namespace"),
        ),
        clock_uncertainty_milliseconds=clock_uncertainty_milliseconds,
        collector_release_hash=graph.release.manifest_id,
        collector_runtime_id=graph.runtime.manifest_id,
    )


def receipt_count(store: PhysicalProjectionStoreV4) -> int:
    row = store._connection.execute("SELECT count(*) FROM receipts").fetchone()
    assert row is not None
    return int(row[0])


def test_root_children_and_approval_are_exact_receipt_typed_bijections(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    clock = FixedClock(T0)
    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite", clock=clock
    ) as store:
        append_graph(store, graph)

        kinds = [store.get_receipt(index).record_kind for index in range(1, 9)]
        assert kinds == [
            PhysicalRecordKindV4.DEPLOYMENT_TRUST_ROOT,
            PhysicalRecordKindV4.COLLECTOR_RELEASE_MANIFEST,
            PhysicalRecordKindV4.DEPENDENCY_LOCK_MANIFEST,
            PhysicalRecordKindV4.TLS_TRUST_STORE_MANIFEST,
            PhysicalRecordKindV4.CLOCK_SOURCE_POLICY_MANIFEST,
            PhysicalRecordKindV4.RUNTIME_ENVIRONMENT_MANIFEST,
            PhysicalRecordKindV4.COLLECTOR_KEY_AUTHORIZATION_MANIFEST,
            PhysicalRecordKindV4.DEPLOYMENT_BUNDLE_APPROVAL,
        ]
        assert store.get_receipt(8).identity_id != graph.bundle.deployment_bundle_id
        report = store.verify()
        assert report.receipt_count == report.canonical_record_count == 8
        assert report.deployment_trust_root_count == 1
        assert report.operational_child_manifest_count == 6
        assert report.deployment_bundle_approval_count == 1
        assert report.batch_count == 8
        strict_tables = {
            row[1]: row[5] for row in store._connection.execute("PRAGMA table_list")
        }
        assert strict_tables["deployment_trust_roots"] == 1
        assert strict_tables["operational_child_manifests"] == 1
        assert strict_tables["deployment_bundle_approvals"] == 1


def test_deployment_appends_are_idempotent_and_tables_are_immutable(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        append_graph(store, graph)
        before = receipt_count(store)

        store.append_deployment_trust_root(
            graph.trust_root,
            idempotency_key="deployment-root",
        )
        store.append_operational_child_manifest(
            graph.release,
            idempotency_key="deployment-child-collector_release",
        )
        capability = store.append_deployment_bundle_approval(
            graph.approval,
            verified_at=VERIFIED_AT,
            idempotency_key="deployment-approval-1",
        )

        assert capability.deployment_bundle_id == graph.bundle.deployment_bundle_id
        assert receipt_count(store) == before
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store._connection.execute(
                "UPDATE deployment_bundle_approvals SET deployment_sequence = 2"
            )
        with pytest.raises(PhysicalProjectionV4IdempotencyError):
            store.append_operational_child_manifest(
                graph.dependency,
                idempotency_key="deployment-child-collector_release",
            )


def test_approval_requires_prior_exact_closure_and_trusted_signature(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="operator-installed deployment trust root",
        ):
            store.append_operational_child_manifest(
                graph.release,
                idempotency_key="child-before-root",
            )
        assert receipt_count(store) == 0
        store.append_deployment_trust_root(
            graph.trust_root,
            idempotency_key="root",
        )
        for child in graph.children[:-1]:
            store.append_operational_child_manifest(
                child,
                idempotency_key=f"child-{child.KIND.value.lower()}",
            )
        before = receipt_count(store)
        with pytest.raises(PhysicalProjectionV4ConflictError, match="missing"):
            store.append_deployment_bundle_approval(
                graph.approval,
                verified_at=VERIFIED_AT,
                idempotency_key="missing-child-approval",
            )
        assert receipt_count(store) == before

        store.append_operational_child_manifest(
            graph.key_authorization,
            idempotency_key="child-key-authorization",
        )
        untrusted = approve_deployment_bundle_v4(
            graph.bundle,
            signers=(Ed25519CheckpointSigner.generate(),),
        )
        before = receipt_count(store)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="signature or exact closure",
        ):
            store.append_deployment_bundle_approval(
                untrusted,
                verified_at=VERIFIED_AT,
                idempotency_key="untrusted-approval",
            )
        assert receipt_count(store) == before


@pytest.mark.parametrize(
    ("sequence", "parent"),
    [
        (3, None),
        (2, digest("not-current-parent")),
    ],
)
def test_successor_requires_current_plus_one_and_exact_parent(
    tmp_path: Path,
    sequence: int,
    parent: str | None,
) -> None:
    graph = deployment_graph()
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        append_graph(store, graph)
        _, approval = successor_approval(
            graph,
            deployment_sequence=sequence,
            parent_deployment_bundle_id=parent,
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="successor"):
            store.append_deployment_bundle_approval(
                approval,
                verified_at=VERIFIED_AT + timedelta(minutes=1),
                idempotency_key="invalid-successor",
            )
        assert store.verify().deployment_bundle_approval_count == 1


def test_successor_reuses_children_and_becomes_assertable_current_head(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    bundle, approval = successor_approval(graph)
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        append_graph(store, graph)
        capability = store.append_deployment_bundle_approval(
            approval,
            verified_at=VERIFIED_AT + timedelta(minutes=1),
            idempotency_key="deployment-approval-2",
        )

        asserted = store.assert_current_operational_deployment(
            deployment_bundle_id=bundle.deployment_bundle_id,
            deployment_trust_root_id=graph.trust_root.trust_root_id,
            deployment_sequence=2,
        )
        assert asserted is None
        assert capability.deployment_bundle_id == bundle.deployment_bundle_id
        report = store.verify()
        assert report.operational_child_manifest_count == 6
        assert report.deployment_bundle_approval_count == 2
        assert report.receipt_count == 9
        with pytest.raises(PhysicalProjectionV4ConflictError, match="current"):
            store.assert_current_operational_deployment(
                deployment_bundle_id=graph.bundle.deployment_bundle_id,
                deployment_trust_root_id=graph.trust_root.trust_root_id,
                deployment_sequence=1,
            )


def test_v45_successor_forbids_collector_key_authorization_rotation(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    rotated_signer = Ed25519CheckpointSigner.generate()
    rotated_authorization = CollectorKeyAuthorizationManifestV4(
        collector_attestation_key_id=derive_transport_attestation_key_id(
            rotated_signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=rotated_signer.public_key_bytes.hex(),
        usage=COLLECTOR_KEY_USAGE,
        collector_release_manifest_id=graph.release.manifest_id,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
    )
    _, approval = successor_approval(
        graph,
        key_authorization=rotated_authorization,
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        append_graph(store, graph)
        store.append_operational_child_manifest(
            rotated_authorization,
            idempotency_key="rotated-key-authorization",
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="key rotation"):
            store.append_deployment_bundle_approval(
                approval,
                verified_at=VERIFIED_AT + timedelta(minutes=1),
                idempotency_key="rotated-key-successor",
            )
        assert store.verify().deployment_bundle_approval_count == 1


def test_transport_policy_requires_current_exact_deployment_and_key(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    clock = FixedClock(T0)
    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite", clock=clock
    ) as store:
        primary = bar_policy(requires_status=True)
        required_status = status_policy()
        scope = authority_scope(primary, required_status)
        store.append_health_policy(idempotency_key="health")
        store.append_adapter_policy(primary, idempotency_key="primary")
        store.append_adapter_policy(required_status, idempotency_key="status")
        store.append_scope(scope, idempotency_key="scope")
        policy = transport_policy(graph, frozen_at=scope.frozen_at)

        with pytest.raises(PhysicalProjectionV4ConflictError, match="deployment"):
            store.append_transport_subscription_policy(
                policy,
                idempotency_key="policy-before-deployment",
            )
        append_graph(store, graph)
        wrong = replace(policy, deployment_bundle_id=digest("wrong-bundle"))
        with pytest.raises(PhysicalProjectionV4ConflictError, match="current"):
            store.append_transport_subscription_policy(
                wrong,
                idempotency_key="wrong-deployment-policy",
            )
        store.append_transport_subscription_policy(
            policy,
            idempotency_key="exact-policy",
        )
        assert store.verify().transport_subscription_policy_count == 1


def test_transport_policy_rejects_deployment_environment_substitution(
    tmp_path: Path,
) -> None:
    graph = deployment_graph(environment_id="TESTNET")
    clock = FixedClock(T0)
    with PhysicalProjectionStoreV4(
        tmp_path / "environment-substitution.sqlite", clock=clock
    ) as store:
        append_graph(store, graph)
        primary = bar_policy(requires_status=True)
        required_status = status_policy()
        scope = authority_scope(primary, required_status)
        store.append_health_policy(idempotency_key="environment-health")
        store.append_adapter_policy(primary, idempotency_key="environment-primary")
        store.append_adapter_policy(
            required_status,
            idempotency_key="environment-status",
        )
        store.append_scope(scope, idempotency_key="environment-scope")

        with pytest.raises(PhysicalProjectionV4ConflictError, match="deployment"):
            store.append_transport_subscription_policy(
                transport_policy(graph, frozen_at=scope.frozen_at),
                idempotency_key="environment-policy",
            )


def test_session_requires_all_bundle_children_and_both_uncertainty_limits(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    clock = FixedClock(T0)
    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite", clock=clock
    ) as store:
        append_graph(store, graph)
        primary, scope, policy = prepare_transport_authority(store, graph)
        writer_token = digest("session-validation-writer")
        writer_generation = store.claim_transport_runtime_writer_fence(
            lease_token_sha256=writer_token,
            holder_id="session-validation-writer",
        )

        wrong_trust = signed_session(
            graph,
            primary=primary,
            scope=scope,
            policy=policy,
            trust_store_manifest_id=digest("wrong-trust-store"),
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="policy"):
            append_test_bound_session(
                store,
                session=wrong_trust,
                signer=graph.collector_signer,
                writer_fence_token_sha256=writer_token,
                writer_fence_generation=writer_generation,
                idempotency_key="wrong-trust-session",
                label="wrong-trust-session",
                time_namespace_id=digest("test-time-namespace"),
            )
        uncertain = signed_session(
            graph,
            primary=primary,
            scope=scope,
            policy=policy,
            clock_uncertainty_milliseconds=101,
            session_nonce=digest("uncertain-session"),
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="policy"):
            append_test_bound_session(
                store,
                session=uncertain,
                signer=graph.collector_signer,
                writer_fence_token_sha256=writer_token,
                writer_fence_generation=writer_generation,
                idempotency_key="uncertain-session",
                label="uncertain-session",
                time_namespace_id=digest("test-time-namespace"),
            )
        exact = signed_session(
            graph,
            primary=primary,
            scope=scope,
            policy=policy,
        )
        append_test_bound_session(
            store,
            session=exact,
            signer=graph.collector_signer,
            writer_fence_token_sha256=writer_token,
            writer_fence_generation=writer_generation,
            idempotency_key="exact-session",
            label="exact-session",
            time_namespace_id=digest("test-time-namespace"),
        )
        assert store.verify().transport_session_attestation_count == 1


def test_successor_requires_every_prior_session_terminal(tmp_path: Path) -> None:
    graph = deployment_graph()
    _, successor = successor_approval(graph)
    clock = FixedClock(T0)
    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite", clock=clock
    ) as store:
        append_graph(store, graph)
        primary, scope, policy = prepare_transport_authority(store, graph)
        writer_token = digest("successor-open-session-writer")
        writer_generation = store.claim_transport_runtime_writer_fence(
            lease_token_sha256=writer_token,
            holder_id="successor-open-session-writer",
        )
        session = signed_session(
            graph,
            primary=primary,
            scope=scope,
            policy=policy,
        )
        append_test_bound_session(
            store,
            session=session,
            signer=graph.collector_signer,
            writer_fence_token_sha256=writer_token,
            writer_fence_generation=writer_generation,
            idempotency_key="open-session",
            label="open-session",
            time_namespace_id=digest("test-time-namespace"),
        )

        with pytest.raises(PhysicalProjectionV4ConflictError, match="terminal"):
            store.append_deployment_bundle_approval(
                successor,
                verified_at=VERIFIED_AT + timedelta(minutes=1),
                idempotency_key="successor-with-open-session",
            )
        assert store.verify().deployment_bundle_approval_count == 1


def test_approval_batch_fault_rolls_back_all_canonical_and_typed_state(
    tmp_path: Path,
) -> None:
    graph = deployment_graph()
    fail = {"enabled": True}

    def fault(stage: str) -> None:
        if fail["enabled"] and stage == "after_deployment_bundle_approval_insert":
            raise RuntimeError("injected approval failure")

    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite",
        fault_injector=fault,
    ) as store:
        store.append_deployment_trust_root(graph.trust_root, idempotency_key="root")
        for child in graph.children:
            store.append_operational_child_manifest(
                child,
                idempotency_key=f"child-{child.KIND.value.lower()}",
            )
        before = receipt_count(store)
        with pytest.raises(RuntimeError, match="injected approval failure"):
            store.append_deployment_bundle_approval(
                graph.approval,
                verified_at=VERIFIED_AT,
                idempotency_key="approval",
            )
        assert receipt_count(store) == before
        assert store.verify().deployment_bundle_approval_count == 0

        fail["enabled"] = False
        store.append_deployment_bundle_approval(
            graph.approval,
            verified_at=VERIFIED_AT,
            idempotency_key="approval",
        )
        assert store.verify().deployment_bundle_approval_count == 1

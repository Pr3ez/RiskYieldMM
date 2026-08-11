from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import riskyieldmm.trading.physical_projection_v4 as physical_projection_module
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    VerifiedDeploymentCapabilityV4,
)
from riskyieldmm.trading.physical_evidence_v4 import (
    PhysicalScopeManifestV4,
    message_disposition_from_v3,
)
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    MessageDispositionKind,
    PhysicalGateStage,
    PhysicalGateVerdict,
    PrefixHealth,
    ProviderAdapterPolicyV3,
    ProviderMessageDispositionV3,
    ProviderMessageTypeV3,
)
from riskyieldmm.trading.physical_projection_v4 import (
    ClassificationAppendV4,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4VerificationError,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    LINUX_BOOTTIME_CLOCK_PROFILE_V4,
    LINUX_SOCKET_IDENTITY_PROFILE_V4,
    TransportSocketOwnerBindingV4,
    derive_linux_boottime_clock_domain_id,
    derive_linux_kernel_socket_identity,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    OperationalDeploymentAdmissionV4,
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
    OutboundSubscriptionIntentV4,
    SubscriptionAckBindingV4,
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
    TransportSubscriptionPolicyV4,
    derive_transport_attestation_key_id,
)
from tests.test_trading_physical_authority_v4_projection import (
    FixedClock,
    append_one_message,
    authority_scope,
    exact_event_binding,
    fresh_status_bytes,
    live_information_set,
    project_classification,
    receipt_count,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    kline_bytes,
    segment,
    status_policy,
)
from tests.test_trading_physical_transport_runtime_v4 import deployment_admission


@dataclass(frozen=True, slots=True)
class TransportFixture:
    primary: ProviderAdapterPolicyV3
    required_status: ProviderAdapterPolicyV3
    scope: PhysicalScopeManifestV4
    signer: Ed25519CheckpointSigner
    deployment_capability: VerifiedDeploymentCapabilityV4
    policy: TransportSubscriptionPolicyV4
    session: TransportSessionAttestationV4
    socket_owner_binding: TransportSocketOwnerBindingV4
    writer_fence_token_sha256: str
    writer_fence_generation: int
    intent: OutboundSubscriptionIntentV4 | None


@dataclass(frozen=True, slots=True)
class AckOccurrence:
    capture: CaptureSegmentV3
    classification: ClassificationAppendV4


class InjectedTransportProjectionFailure(RuntimeError):
    pass


def append_test_operational_deployment(
    store: PhysicalProjectionStoreV4,
    *,
    signer: Ed25519CheckpointSigner,
    verified_at: datetime,
    valid_until: datetime,
    idempotency_prefix: str,
) -> tuple[OperationalDeploymentAdmissionV4, VerifiedDeploymentCapabilityV4]:
    admission = deployment_admission(
        signer,
        valid_from=verified_at - timedelta(days=1),
        valid_until=valid_until,
    )
    store.append_deployment_trust_root(
        admission.trust_root,
        idempotency_key=f"{idempotency_prefix}-root",
    )
    for index, child in enumerate(admission.children):
        store.append_operational_child_manifest(
            child,
            idempotency_key=f"{idempotency_prefix}-child-{index}",
        )
    capability = store.append_deployment_bundle_approval(
        admission.approval,
        verified_at=verified_at,
        idempotency_key=f"{idempotency_prefix}-approval",
    )
    return admission, capability


def transport_policy(
    *,
    signer: Ed25519CheckpointSigner,
    frozen_at: datetime,
    deployment_capability: VerifiedDeploymentCapabilityV4,
) -> TransportSubscriptionPolicyV4:
    return TransportSubscriptionPolicyV4(
        deployment_bundle_id=deployment_capability.deployment_bundle_id,
        collector_key_authorization_manifest_id=(
            deployment_capability.collector_key_authorization_manifest_id
        ),
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
        collector_attestation_key_id=derive_transport_attestation_key_id(
            signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
        frozen_at=frozen_at,
    )


def signed_session(
    *,
    fixture_policy: TransportSubscriptionPolicyV4,
    scope: PhysicalScopeManifestV4,
    primary: ProviderAdapterPolicyV3,
    signer: Ed25519CheckpointSigner,
    deployment_capability: VerifiedDeploymentCapabilityV4,
    session_nonce_label: str = "session-one",
    collector_instance_id: str = "collector-a",
    collector_boot_id: str = "boot-a",
    connection_generation: int = 1,
    parent_transport_session_id: str | None = None,
    handshake_started_at: datetime = T0 - timedelta(seconds=2),
    handshake_completed_at: datetime = T0 - timedelta(seconds=1),
    handshake_started_monotonic_ns: int = 100_000_000,
    handshake_completed_monotonic_ns: int = 200_000_000,
    monotonic_clock_domain_id: str | None = None,
) -> TransportSessionAttestationV4:
    partition_probe = replace(
        segment(primary, b"{}", received_at=T0),
        collector_instance_id=collector_instance_id,
        collector_boot_id=collector_boot_id,
    )
    return TransportSessionAttestationV4.create_signed(
        signer=signer,
        deployment_bundle_id=fixture_policy.deployment_bundle_id,
        clock_source_manifest_id=deployment_capability.clock_source_manifest_id,
        collector_key_authorization_manifest_id=(
            fixture_policy.collector_key_authorization_manifest_id
        ),
        transport_subscription_policy_id=(
            fixture_policy.transport_subscription_policy_id
        ),
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        adapter_policy_id=primary.adapter_policy_id,
        capture_partition_id=partition_probe.capture_partition_id,
        collector_instance_id=collector_instance_id,
        collector_boot_id=collector_boot_id,
        connection_generation=connection_generation,
        session_nonce=digest(session_nonce_label),
        parent_transport_session_id=parent_transport_session_id,
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        remote_address="bybit-edge-diagnostic",
        tls_version=V4_TRANSPORT_MINIMUM_TLS_VERSION,
        tls_cipher="TLS_AES_128_GCM_SHA256",
        alpn_protocol=None,
        websocket_extensions=(),
        peer_certificate_sha256=digest(f"{session_nonce_label}-leaf"),
        peer_spki_sha256=digest(f"{session_nonce_label}-spki"),
        trust_store_manifest_id=deployment_capability.trust_store_manifest_id,
        certificate_verified=True,
        hostname_verified=True,
        websocket_http_status=V4_TRANSPORT_WEBSOCKET_HTTP_STATUS,
        websocket_accept_verified=True,
        handshake_commitment_profile=V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
        handshake_request_sha256=digest(f"{session_nonce_label}-request"),
        handshake_response_sha256=digest(f"{session_nonce_label}-response"),
        handshake_started_at=handshake_started_at,
        handshake_completed_at=handshake_completed_at,
        handshake_started_monotonic_ns=handshake_started_monotonic_ns,
        handshake_completed_monotonic_ns=handshake_completed_monotonic_ns,
        monotonic_clock_domain_id=(
            derive_linux_boottime_clock_domain_id(
                kernel_boot_id=collector_boot_id,
                time_namespace_id=digest("test-time-namespace"),
            )
            if monotonic_clock_domain_id is None
            else monotonic_clock_domain_id
        ),
        clock_uncertainty_milliseconds=20,
        collector_release_hash=deployment_capability.collector_release_hash,
        collector_runtime_id=deployment_capability.collector_runtime_id,
    )


def signed_test_socket_owner_binding(
    *,
    session: TransportSessionAttestationV4,
    signer: Ed25519CheckpointSigner,
    writer_fence_token_sha256: str,
    writer_fence_generation: int,
    label: str,
    bound_at: datetime | None = None,
    bound_monotonic_before_ns: int | None = None,
    time_namespace_id: str | None = None,
    network_namespace_id: str | None = None,
) -> TransportSocketOwnerBindingV4:
    """Build deterministic synthetic owner evidence for projection tests only."""

    time_namespace = (
        digest("test-time-namespace")
        if time_namespace_id is None
        else time_namespace_id
    )
    network_namespace = (
        digest("test-network-namespace")
        if network_namespace_id is None
        else network_namespace_id
    )
    cookie = digest(f"{label}-socket-cookie")[:16]
    if cookie == "0000000000000000":
        cookie = "0000000000000001"
    kernel_socket_identity = derive_linux_kernel_socket_identity(
        kernel_boot_id=session.collector_boot_id,
        network_namespace_id=network_namespace,
        socket_cookie_u64=cookie,
    )
    nonce_digest = derive_transport_socket_lease_nonce_sha256(
        hashlib.sha256(f"{label}-lease-capability".encode()).digest()
    )
    socket_lease_id = derive_transport_socket_lease_id(
        transport_session_id=session.transport_session_id,
        kernel_socket_identity=kernel_socket_identity,
        socket_lease_nonce_sha256=nonce_digest,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
    )
    before_ns = (
        session.handshake_completed_monotonic_ns + 1_000_000
        if bound_monotonic_before_ns is None
        else bound_monotonic_before_ns
    )
    return TransportSocketOwnerBindingV4.create_signed(
        signer=signer,
        transport_session_id=session.transport_session_id,
        deployment_bundle_id=session.deployment_bundle_id,
        transport_subscription_policy_id=(session.transport_subscription_policy_id),
        physical_scope_manifest_id=session.physical_scope_manifest_id,
        adapter_policy_id=session.adapter_policy_id,
        capture_partition_id=session.capture_partition_id,
        socket_lease_id=socket_lease_id,
        socket_lease_nonce_sha256=nonce_digest,
        kernel_socket_identity=kernel_socket_identity,
        socket_identity_profile=LINUX_SOCKET_IDENTITY_PROFILE_V4,
        socket_cookie_u64=cookie,
        kernel_boot_id=session.collector_boot_id,
        time_namespace_id=time_namespace,
        network_namespace_id=network_namespace,
        clock_source_manifest_id=session.clock_source_manifest_id,
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        clock_profile=LINUX_BOOTTIME_CLOCK_PROFILE_V4,
        clock_resolution_ns=1,
        connection_generation=session.connection_generation,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        bound_at=(
            session.handshake_completed_at + timedelta(milliseconds=1)
            if bound_at is None
            else bound_at
        ),
        bound_monotonic_before_ns=before_ns,
        bound_monotonic_after_ns=before_ns + 1,
        clock_uncertainty_milliseconds=session.clock_uncertainty_milliseconds,
    )


def append_test_bound_session(
    store: PhysicalProjectionStoreV4,
    *,
    session: TransportSessionAttestationV4,
    signer: Ed25519CheckpointSigner,
    writer_fence_token_sha256: str,
    writer_fence_generation: int,
    idempotency_key: str,
    label: str,
    bound_at: datetime | None = None,
    bound_monotonic_before_ns: int | None = None,
    time_namespace_id: str | None = None,
) -> object:
    binding = signed_test_socket_owner_binding(
        session=session,
        signer=signer,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        label=label,
        bound_at=bound_at,
        bound_monotonic_before_ns=bound_monotonic_before_ns,
        time_namespace_id=time_namespace_id,
    )
    return store.append_transport_session_attestation(
        session,
        socket_owner_binding=binding,
        idempotency_key=idempotency_key,
    )


def prepare_transport_fixture(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    authorize: bool = True,
) -> TransportFixture:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    signer = Ed25519CheckpointSigner.generate()
    clock.value = scope.frozen_at
    _, deployment_capability = append_test_operational_deployment(
        store,
        signer=signer,
        verified_at=scope.frozen_at,
        valid_until=T0 + timedelta(days=1),
        idempotency_prefix="transport-deployment",
    )
    policy = transport_policy(
        signer=signer,
        frozen_at=scope.frozen_at,
        deployment_capability=deployment_capability,
    )
    store.append_health_policy(idempotency_key="transport-health-policy")
    store.append_adapter_policy(primary, idempotency_key="transport-primary-policy")
    store.append_adapter_policy(
        required_status,
        idempotency_key="transport-status-policy",
    )
    store.append_scope(scope, idempotency_key="transport-scope")
    store.append_transport_subscription_policy(
        policy,
        idempotency_key="transport-policy",
    )
    session = signed_session(
        fixture_policy=policy,
        scope=scope,
        primary=primary,
        signer=signer,
        deployment_capability=deployment_capability,
    )
    writer_fence_token_sha256 = digest("transport-fixture-writer-fence")
    writer_fence_generation = store.claim_transport_runtime_writer_fence(
        lease_token_sha256=writer_fence_token_sha256,
        holder_id="transport-fixture-writer",
    )
    socket_owner_binding = signed_test_socket_owner_binding(
        session=session,
        signer=signer,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        label="transport-fixture",
    )
    clock.value = T0 - timedelta(milliseconds=500)
    store.append_transport_session_attestation(
        session,
        socket_owner_binding=socket_owner_binding,
        idempotency_key="transport-session",
    )
    intent = (
        store.authorize_outbound_subscription_intent(
            session.transport_session_id,
            idempotency_key="transport-intent",
        )
        if authorize
        else None
    )
    return TransportFixture(
        primary=primary,
        required_status=required_status,
        scope=scope,
        signer=signer,
        deployment_capability=deployment_capability,
        policy=policy,
        session=session,
        socket_owner_binding=socket_owner_binding,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        intent=intent,
    )


def ack_payload(
    *,
    request_id: str,
    provider_connection_id: str,
) -> dict[str, Any]:
    return {
        "success": True,
        "ret_msg": "",
        "conn_id": provider_connection_id,
        "req_id": request_id,
        "op": "subscribe",
    }


def append_ack_occurrence(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    fixture: TransportFixture,
    intent: OutboundSubscriptionIntentV4,
    payload: dict[str, Any],
    sequence: int,
    received_at: datetime,
    parent: CaptureSegmentV3 | None = None,
    session: TransportSessionAttestationV4 | None = None,
    idempotency_suffix: str,
    message_type: ProviderMessageTypeV3 = ProviderMessageTypeV3.TEXT,
) -> AckOccurrence:
    effective_session = session or fixture.session
    raw = json.dumps(payload, separators=(",", ":")).encode()
    capture = replace(
        segment(
            fixture.primary,
            raw,
            sequence=sequence,
            received_at=received_at,
            parent=parent,
            connection_id=effective_session.transport_session_id,
            connection_generation=effective_session.connection_generation,
            message_type=message_type,
        ),
        subscription_manifest_hash=intent.subscription_manifest_hash,
        collector_instance_id=effective_session.collector_instance_id,
        collector_boot_id=effective_session.collector_boot_id,
    )
    clock.value = received_at + timedelta(milliseconds=100)
    message = append_one_message(
        store,
        scope=fixture.scope,
        capture=capture,
        idempotency_key=f"{idempotency_suffix}-message",
    )
    classification = project_classification(
        store=store,
        policy=fixture.primary,
        scope=fixture.scope,
        capture=capture,
        message=message,
    )
    clock.value = classification.provider_disposition.classified_at
    store.append_classification_batch(
        (classification,),
        idempotency_key=f"{idempotency_suffix}-classification",
    )
    return AckOccurrence(capture=capture, classification=classification)


def bind_ack(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    fixture: TransportFixture,
    intent: OutboundSubscriptionIntentV4,
    occurrence: AckOccurrence,
    idempotency_key: str,
) -> SubscriptionAckBindingV4:
    received = occurrence.capture.envelopes[0].collector_received_wall_ts
    monotonic = occurrence.capture.envelopes[0].collector_received_monotonic_ns
    clock.value = max(clock.value, received + timedelta(milliseconds=500))
    return store.bind_subscription_ack(
        outbound_subscription_intent_id=intent.outbound_subscription_intent_id,
        message_disposition_id=(
            occurrence.classification.disposition.message_disposition_id
        ),
        dispatch_started_at=intent.authorized_at + timedelta(milliseconds=100),
        dispatch_completed_at=intent.authorized_at + timedelta(milliseconds=200),
        dispatch_started_monotonic_ns=monotonic - 300_000_000,
        dispatch_completed_monotonic_ns=monotonic - 200_000_000,
        signer=fixture.signer,
        idempotency_key=idempotency_key,
    )


def append_classified_capture(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    fixture: TransportFixture,
    policy: ProviderAdapterPolicyV3,
    capture: CaptureSegmentV3,
    idempotency_suffix: str,
) -> ClassificationAppendV4:
    received = capture.envelopes[0].collector_received_wall_ts
    clock.value = received + timedelta(milliseconds=100)
    message = append_one_message(
        store,
        scope=fixture.scope,
        capture=capture,
        idempotency_key=f"{idempotency_suffix}-message",
    )
    classification = project_classification(
        store=store,
        policy=policy,
        scope=fixture.scope,
        capture=capture,
        message=message,
    )
    clock.value = classification.provider_disposition.classified_at
    store.append_classification_batch(
        (classification,),
        idempotency_key=f"{idempotency_suffix}-classification",
    )
    return classification


def primary_bar_capture(
    *,
    fixture: TransportFixture,
    intent: OutboundSubscriptionIntentV4,
    sequence: int,
    bar_start: datetime,
    received_at: datetime,
    parent: CaptureSegmentV3 | None,
) -> CaptureSegmentV3:
    return replace(
        segment(
            fixture.primary,
            kline_bytes(bar_start=bar_start),
            sequence=sequence,
            received_at=received_at,
            parent=parent,
            connection_id=fixture.session.transport_session_id,
        ),
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )


def test_generation_two_can_supply_first_capture_after_empty_generation_one(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "empty-generation-reconnect.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        assert fixture.intent is None
        assert store.verify().message_count == 0

        generation_one_terminated_at = T0 - timedelta(milliseconds=400)
        clock.value = generation_one_terminated_at + timedelta(milliseconds=50)
        store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            detected_at=generation_one_terminated_at,
            detected_monotonic_ns=300_000_000,
            detected_monotonic_clock_domain_id=(
                fixture.session.monotonic_clock_domain_id
            ),
            signer=fixture.signer,
            idempotency_key="empty-generation-one-termination",
            close_code=1000,
        )

        generation_two = signed_session(
            fixture_policy=fixture.policy,
            scope=fixture.scope,
            primary=fixture.primary,
            signer=fixture.signer,
            deployment_capability=fixture.deployment_capability,
            session_nonce_label="session-two-after-empty-one",
            connection_generation=2,
            parent_transport_session_id=fixture.session.transport_session_id,
            handshake_started_at=T0 - timedelta(milliseconds=300),
            handshake_completed_at=T0 - timedelta(milliseconds=200),
            handshake_started_monotonic_ns=400_000_000,
            handshake_completed_monotonic_ns=500_000_000,
        )
        clock.value = T0 - timedelta(milliseconds=100)
        append_test_bound_session(
            store,
            session=generation_two,
            signer=fixture.signer,
            writer_fence_token_sha256=fixture.writer_fence_token_sha256,
            writer_fence_generation=fixture.writer_fence_generation,
            idempotency_key="generation-two-session",
            label="generation-two",
        )
        generation_two_intent = store.authorize_outbound_subscription_intent(
            generation_two.transport_session_id,
            idempotency_key="generation-two-intent",
        )

        first_capture = replace(
            segment(
                fixture.primary,
                kline_bytes(),
                sequence=1,
                received_at=T0 + timedelta(minutes=1, milliseconds=200),
                connection_generation=2,
                connection_id=generation_two.transport_session_id,
            ),
            subscription_manifest_hash=(
                generation_two_intent.subscription_manifest_hash
            ),
        )
        clock.value = first_capture.closed_at + timedelta(milliseconds=50)
        messages = store.append_messages(
            physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
            segment=first_capture,
            idempotency_key="generation-two-first-capture",
        )
        assert len(messages) == 1
        assert messages[0].capture_segment_id == first_capture.capture_segment_id
        assert first_capture.envelopes[0].collector_sequence == 1

        second_parentless_capture = replace(
            segment(
                fixture.primary,
                kline_bytes(close="100.75"),
                sequence=1,
                received_at=T0 + timedelta(minutes=2, milliseconds=200),
                connection_generation=2,
                connection_id=generation_two.transport_session_id,
            ),
            subscription_manifest_hash=(
                generation_two_intent.subscription_manifest_hash
            ),
        )
        before = receipt_count(store)
        clock.value = second_parentless_capture.closed_at + timedelta(milliseconds=50)
        with pytest.raises(PhysicalProjectionV4ConflictError) as exc_info:
            store.append_messages(
                physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
                segment=second_parentless_capture,
                idempotency_key="generation-two-second-parentless-capture",
            )
        assert "capture segment lineage is invalid" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None
        assert "capture partition already has a root segment" in str(
            exc_info.value.__cause__
        )
        assert receipt_count(store) == before
        assert store.verify().message_count == 1


def test_cross_domain_process_restart_termination_is_admitted(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "cross-domain-process-restart.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        restarted_domain = digest("monotonic-clock-domain-after-restart")
        clock.value = T0 + timedelta(seconds=1)

        termination = store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.PROCESS_RESTART,
            detected_at=T0,
            detected_monotonic_ns=1,
            detected_monotonic_clock_domain_id=restarted_domain,
            signer=fixture.signer,
            idempotency_key="cross-domain-process-restart",
        )

        assert termination.detected_monotonic_clock_domain_id == restarted_domain
        assert termination.detected_monotonic_ns == 1
        store.verify()


def test_startup_reconciliation_terminates_each_open_session_once(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "startup-reconciliation.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        restarted_domain = digest("startup-reconciliation-clock-domain")
        clock.value = T0 + timedelta(seconds=1)

        reconciled = store.reconcile_unterminated_transport_sessions(
            detected_at=T0,
            detected_monotonic_ns=1,
            detected_monotonic_clock_domain_id=restarted_domain,
            signer=fixture.signer,
            idempotency_prefix="runtime-startup",
        )

        assert len(reconciled) == 1
        assert reconciled[0].transport_session_id == (
            fixture.session.transport_session_id
        )
        assert (
            reconciled[0].reason is TransportSessionTerminationReasonV4.PROCESS_RESTART
        )
        assert reconciled[0].detected_monotonic_clock_domain_id == restarted_domain
        assert (
            store.reconcile_unterminated_transport_sessions(
                detected_at=T0 + timedelta(milliseconds=1),
                detected_monotonic_ns=2,
                detected_monotonic_clock_domain_id=restarted_domain,
                signer=fixture.signer,
                idempotency_prefix="runtime-startup-retry",
            )
            == ()
        )
        report = store.verify()
        assert report.transport_session_termination_count == 1


def test_same_boot_successor_cannot_change_monotonic_clock_domain(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "same-boot-domain-change.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        clock.value = T0 - timedelta(milliseconds=350)
        store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            detected_at=T0 - timedelta(milliseconds=400),
            detected_monotonic_ns=300_000_000,
            detected_monotonic_clock_domain_id=(
                fixture.session.monotonic_clock_domain_id
            ),
            signer=fixture.signer,
            idempotency_key="same-domain-parent-termination",
            close_code=1000,
        )
        changed_time_namespace_id = digest("changed-time-namespace")
        successor = signed_session(
            fixture_policy=fixture.policy,
            scope=fixture.scope,
            primary=fixture.primary,
            signer=fixture.signer,
            deployment_capability=fixture.deployment_capability,
            session_nonce_label="same-boot-domain-change",
            connection_generation=2,
            parent_transport_session_id=fixture.session.transport_session_id,
            handshake_started_at=T0 - timedelta(milliseconds=300),
            handshake_completed_at=T0 - timedelta(milliseconds=200),
            handshake_started_monotonic_ns=400_000_000,
            handshake_completed_monotonic_ns=500_000_000,
            monotonic_clock_domain_id=derive_linux_boottime_clock_domain_id(
                kernel_boot_id=fixture.session.collector_boot_id,
                time_namespace_id=changed_time_namespace_id,
            ),
        )
        clock.value = T0 - timedelta(milliseconds=100)

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="transport session does not exactly extend its parent lineage",
        ):
            append_test_bound_session(
                store,
                session=successor,
                signer=fixture.signer,
                writer_fence_token_sha256=fixture.writer_fence_token_sha256,
                writer_fence_generation=fixture.writer_fence_generation,
                idempotency_key="same-boot-domain-change",
                label="same-boot-domain-change",
                time_namespace_id=changed_time_namespace_id,
            )

        store.verify()


@pytest.mark.parametrize(
    ("reason", "detected_domain", "detected_monotonic", "expected"),
    [
        (
            TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            digest("monotonic-clock-domain-after-restart"),
            1,
            "cross-domain transport termination requires PROCESS_RESTART",
        ),
        (
            TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            None,
            100_000_000,
            "transport termination predates its completed handshake",
        ),
    ],
    ids=("cross-domain-non-restart", "same-domain-reversed-monotonic"),
)
def test_transport_termination_rejects_incomparable_or_reversed_clock_evidence(
    tmp_path: Path,
    reason: TransportSessionTerminationReasonV4,
    detected_domain: str | None,
    detected_monotonic: int,
    expected: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"invalid-termination-{reason.value}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        clock.value = T0 + timedelta(seconds=1)
        domain = (
            fixture.session.monotonic_clock_domain_id
            if detected_domain is None
            else detected_domain
        )

        with pytest.raises(PhysicalProjectionV4ConflictError, match=expected):
            store.append_transport_session_termination(
                transport_session_id=fixture.session.transport_session_id,
                reason=reason,
                detected_at=T0,
                detected_monotonic_ns=detected_monotonic,
                detected_monotonic_clock_domain_id=domain,
                signer=fixture.signer,
                idempotency_key=f"invalid-termination-{detected_monotonic}",
            )

        assert store.verify().canonical_record_count > 0


@pytest.mark.parametrize(
    ("mutate", "expected_disposition"),
    [
        (
            lambda payload, _intent: {**payload, "unexpected": "field"},
            MessageDispositionKind.UNSUPPORTED_SCHEMA,
        ),
        (
            lambda payload, _intent: {
                key: value for key, value in payload.items() if key != "req_id"
            },
            MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        ),
        (
            lambda payload, _intent: {**payload, "req_id": ""},
            MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        ),
        (
            lambda payload, _intent: {**payload, "req_id": "copied-request-id"},
            MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        ),
    ],
    ids=("extra-key", "missing-request-id", "empty-request-id", "wrong-request-id"),
)
def test_ack_binding_requires_exact_schema_and_exact_echoed_request_id(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any], OutboundSubscriptionIntentV4], dict[str, Any]],
    expected_disposition: MessageDispositionKind,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "invalid-ack.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        payload = mutate(
            ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            fixture.intent,
        )
        occurrence = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=payload,
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix="invalid-ack",
        )
        assert (
            occurrence.classification.disposition.disposition_kind
            is expected_disposition
        )
        before = receipt_count(store)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="exact bindable schema|exactly echo",
        ):
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=occurrence,
                idempotency_key="invalid-ack-binding",
            )
        assert receipt_count(store) == before
        assert store.verify().subscription_ack_binding_count == 0


@pytest.mark.parametrize(
    "message_type",
    (ProviderMessageTypeV3.BINARY, ProviderMessageTypeV3.UNKNOWN),
)
def test_non_text_exact_ack_json_is_captured_but_cannot_bind(
    tmp_path: Path,
    message_type: ProviderMessageTypeV3,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"non-text-ack-{message_type.value}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        occurrence = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix=f"non-text-ack-{message_type.value}",
            message_type=message_type,
        )
        assert occurrence.capture.envelopes[0].message_type is message_type
        assert (
            occurrence.classification.disposition.disposition_kind
            is MessageDispositionKind.UNSUPPORTED_SCHEMA
        )
        before = receipt_count(store)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="exact TEXT provider frame",
        ):
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=occurrence,
                idempotency_key=f"non-text-binding-{message_type.value}",
            )
        assert receipt_count(store) == before
        assert store.verify().subscription_ack_binding_count == 0


def test_full_replay_independently_rejects_persisted_binary_ack_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model a compromised append path; genesis replay must still reject it."""

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "forged-binary-ack-replay.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        received_at = T0 + timedelta(milliseconds=10)
        raw = json.dumps(
            ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            separators=(",", ":"),
        ).encode()
        capture = replace(
            segment(
                fixture.primary,
                raw,
                sequence=1,
                received_at=received_at,
                connection_id=fixture.session.transport_session_id,
                connection_generation=fixture.session.connection_generation,
                message_type=ProviderMessageTypeV3.BINARY,
            ),
            subscription_manifest_hash=fixture.intent.subscription_manifest_hash,
            collector_instance_id=fixture.session.collector_instance_id,
            collector_boot_id=fixture.session.collector_boot_id,
        )
        clock.value = received_at + timedelta(milliseconds=100)
        message = append_one_message(
            store,
            scope=fixture.scope,
            capture=capture,
            idempotency_key="forged-binary-ack-message",
        )
        classified_at = clock.value + timedelta(milliseconds=300)
        provider = ProviderMessageDispositionV3(
            adapter_policy_id=fixture.primary.adapter_policy_id,
            capture_segment_id=capture.capture_segment_id,
            message_receipt_id=message.message_receipt_id,
            raw_payload_sha256=message.raw_payload_sha256,
            disposition_kind=MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
            classifier_release_hash=(fixture.primary.message_classifier_release_hash),
            classified_at=classified_at,
        )
        classification = ClassificationAppendV4(
            disposition=message_disposition_from_v3(
                message=message,
                disposition=provider,
            ),
            provider_disposition=provider,
        )
        clock.value = classified_at

        with monkeypatch.context() as compromised:
            compromised.setattr(
                physical_projection_module,
                "build_bybit_v5_message_disposition",
                lambda **_: (provider, None, None),
            )
            compromised.setattr(
                physical_projection_module,
                "_is_exact_text_provider_message",
                lambda _: True,
            )
            store.append_classification_batch(
                (classification,),
                idempotency_key="forged-binary-ack-classification",
            )
            occurrence = AckOccurrence(
                capture=capture,
                classification=classification,
            )
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=occurrence,
                idempotency_key="forged-binary-ack-binding",
            )

        with pytest.raises(
            PhysicalProjectionV4VerificationError,
            match="does not use an exact TEXT frame",
        ):
            store.verify()


def test_provider_connection_id_is_opaque_distinct_and_stable_within_session(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "provider-connection-stability.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        first = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix="first-ack",
        )
        first_binding = bind_ack(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            occurrence=first,
            idempotency_key="first-binding",
        )
        assert first_binding.provider_connection_id == "provider-opaque-a"
        assert (
            first_binding.provider_connection_id != fixture.session.transport_session_id
        )

        second_intent = store.authorize_outbound_subscription_intent(
            fixture.session.transport_session_id,
            idempotency_key="second-intent",
        )
        second_received = second_intent.authorized_at + timedelta(milliseconds=500)
        second = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=second_intent,
            payload=ack_payload(
                request_id=second_intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            sequence=2,
            received_at=second_received,
            parent=first.capture,
            idempotency_suffix="second-ack",
        )
        second_binding = bind_ack(
            store,
            clock=clock,
            fixture=fixture,
            intent=second_intent,
            occurrence=second,
            idempotency_key="second-binding",
        )
        assert (
            second_binding.provider_connection_id
            == first_binding.provider_connection_id
        )

        third_intent = store.authorize_outbound_subscription_intent(
            fixture.session.transport_session_id,
            idempotency_key="third-intent",
        )
        third = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=third_intent,
            payload=ack_payload(
                request_id=third_intent.request_id,
                provider_connection_id="provider-opaque-copied-from-another-session",
            ),
            sequence=3,
            received_at=third_intent.authorized_at + timedelta(milliseconds=500),
            parent=second.capture,
            idempotency_suffix="third-ack",
        )
        before = receipt_count(store)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="provider connection identity changed within one local session",
        ):
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=third_intent,
                occurrence=third,
                idempotency_key="third-binding",
            )
        assert receipt_count(store) == before
        report = store.verify()
        assert report.outbound_subscription_intent_count == 3
        assert report.subscription_ack_binding_count == 2


@pytest.mark.parametrize(
    "attack",
    ("unknown-session", "generation", "partition", "manifest"),
)
def test_copied_ack_capture_cannot_cross_transport_authority_dimensions(
    tmp_path: Path,
    attack: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"copied-ack-{attack}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        candidate = replace(
            segment(
                fixture.primary,
                json.dumps(
                    ack_payload(
                        request_id=fixture.intent.request_id,
                        provider_connection_id="provider-opaque-a",
                    ),
                    separators=(",", ":"),
                ).encode(),
                sequence=1,
                received_at=T0 + timedelta(milliseconds=10),
                connection_id=fixture.session.transport_session_id,
            ),
            subscription_manifest_hash=fixture.intent.subscription_manifest_hash,
        )
        if attack == "unknown-session":
            candidate = replace(candidate, connection_id=digest("foreign-session"))
        elif attack == "generation":
            candidate = replace(candidate, connection_generation=2)
        elif attack == "partition":
            candidate = replace(candidate, collector_boot_id="foreign-boot")
        else:
            candidate = replace(
                candidate,
                subscription_manifest_hash=digest("foreign-subscription-manifest"),
            )

        before = receipt_count(store)
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_messages(
                physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
                segment=candidate,
                idempotency_key=f"copied-{attack}",
            )
        assert receipt_count(store) == before
        assert store.verify().message_count == 0


def test_ack_from_another_attested_session_cannot_bind_the_original_intent(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "cross-session-copy.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        foreign_session = signed_session(
            fixture_policy=fixture.policy,
            scope=fixture.scope,
            primary=fixture.primary,
            signer=fixture.signer,
            deployment_capability=fixture.deployment_capability,
            session_nonce_label="foreign-session",
            collector_boot_id="boot-foreign",
        )
        clock.value = T0 - timedelta(milliseconds=400)
        append_test_bound_session(
            store,
            session=foreign_session,
            signer=fixture.signer,
            writer_fence_token_sha256=fixture.writer_fence_token_sha256,
            writer_fence_generation=fixture.writer_fence_generation,
            idempotency_key="foreign-session",
            label="foreign-session",
        )
        foreign_intent = store.authorize_outbound_subscription_intent(
            foreign_session.transport_session_id,
            idempotency_key="foreign-intent",
        )
        occurrence = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=foreign_intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-foreign",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            session=foreign_session,
            idempotency_suffix="foreign-ack",
        )
        before = receipt_count(store)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="capture/classifier chain differs",
        ):
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=occurrence,
                idempotency_key="cross-session-binding",
            )
        assert receipt_count(store) == before
        assert store.verify().subscription_ack_binding_count == 0


def test_completed_bar_captured_before_ack_binding_is_excluded_from_recovery(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "pre-binding-bar.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        pre_binding_capture = primary_bar_capture(
            fixture=fixture,
            intent=fixture.intent,
            sequence=1,
            bar_start=T0 - timedelta(minutes=1),
            received_at=T0 + timedelta(milliseconds=5),
            parent=None,
        )
        pre_binding = append_classified_capture(
            store,
            clock=clock,
            fixture=fixture,
            policy=fixture.primary,
            capture=pre_binding_capture,
            idempotency_suffix="pre-binding-bar",
        )
        assert pre_binding.revision is not None

        ack = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            sequence=2,
            received_at=T0 + timedelta(milliseconds=500),
            parent=pre_binding_capture,
            idempotency_suffix="post-data-ack",
        )
        bind_ack(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            occurrence=ack,
            idempotency_key="post-data-binding",
        )

        post_binding_capture = primary_bar_capture(
            fixture=fixture,
            intent=fixture.intent,
            sequence=3,
            bar_start=T0,
            received_at=T0 + timedelta(minutes=1, milliseconds=200),
            parent=ack.capture,
        )
        append_classified_capture(
            store,
            clock=clock,
            fixture=fixture,
            policy=fixture.primary,
            capture=post_binding_capture,
            idempotency_suffix="post-binding-bar",
        )
        status_published = T0 + timedelta(minutes=1, milliseconds=700)
        status_capture = segment(
            fixture.required_status,
            fresh_status_bytes(published_at=status_published),
            received_at=status_published + timedelta(milliseconds=100),
        )
        append_classified_capture(
            store,
            clock=clock,
            fixture=fixture,
            policy=fixture.required_status,
            capture=status_capture,
            idempotency_suffix="pre-binding-status",
        )

        cutoff_ts = T0 + timedelta(minutes=1, seconds=4)
        clock.value = cutoff_ts
        cutoff, transition = store.append_derived_health_cutoff(
            physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=cutoff_ts,
            idempotency_key="pre-binding-health",
        )
        assert cutoff.health is PrefixHealth.RECOVERING
        assert transition.current_health is PrefixHealth.RECOVERING
        assert transition.recovery_consecutive_completed_bars == 1
        assert "RECOVERY_STREAK_INCOMPLETE" in transition.health_reason_codes


def test_transport_termination_invalidates_health_stales_gate_and_h2_abstains(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "termination-gate.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock)
        assert fixture.intent is not None
        ack = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-opaque-a",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix="healthy-ack",
        )
        bind_ack(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            occurrence=ack,
            idempotency_key="healthy-binding",
        )

        parent = ack.capture
        bar_classifications: list[ClassificationAppendV4] = []
        for index in range(2):
            capture = primary_bar_capture(
                fixture=fixture,
                intent=fixture.intent,
                sequence=index + 2,
                bar_start=T0 + timedelta(minutes=index),
                received_at=T0 + timedelta(minutes=index + 1, milliseconds=200),
                parent=parent,
            )
            bar_classifications.append(
                append_classified_capture(
                    store,
                    clock=clock,
                    fixture=fixture,
                    policy=fixture.primary,
                    capture=capture,
                    idempotency_suffix=f"healthy-bar-{index}",
                )
            )
            parent = capture
        status_published = T0 + timedelta(minutes=2, milliseconds=700)
        append_classified_capture(
            store,
            clock=clock,
            fixture=fixture,
            policy=fixture.required_status,
            capture=segment(
                fixture.required_status,
                fresh_status_bytes(published_at=status_published),
                received_at=status_published + timedelta(milliseconds=100),
            ),
            idempotency_suffix="healthy-status",
        )

        healthy_at = T0 + timedelta(minutes=2, seconds=4)
        clock.value = healthy_at
        cutoff, transition = store.append_derived_health_cutoff(
            physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=healthy_at,
            idempotency_key="healthy-cutoff",
        )
        assert cutoff.health is PrefixHealth.HEALTHY
        assert transition.current_health is PrefixHealth.HEALTHY

        protocol_binding = exact_event_binding(fixture.scope)
        store.append_protocol_binding(
            protocol_binding,
            idempotency_key="termination-protocol-binding",
        )
        proof_at = healthy_at + timedelta(milliseconds=100)
        clock.value = proof_at
        proof, chunk = store.select_observations(
            physical_protocol_binding_id=(
                protocol_binding.physical_protocol_binding_id
            ),
            evidence_cutoff_id=cutoff.evidence_cutoff_id,
            observation_cutoff_ts=healthy_at,
            computed_at=proof_at,
            idempotency_key="termination-selection",
        )
        assert chunk is not None
        selected_revision = bar_classifications[-1].revision
        assert selected_revision is not None
        assert chunk.ordered_observation_revision_ids == (
            selected_revision.observation_revision_id,
        )
        assembled_at = healthy_at + timedelta(milliseconds=200)
        information_set = live_information_set(
            scope=fixture.scope,
            binding=protocol_binding,
            revision=selected_revision,
            observation_cutoff_ts=healthy_at,
            assembled_at=assembled_at,
        )
        clock.value = assembled_at
        store.append_information_set(
            information_set,
            idempotency_key="termination-information-set",
        )

        detected_at = healthy_at + timedelta(milliseconds=250)
        clock.value = healthy_at + timedelta(milliseconds=300)
        termination = store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            detected_at=detected_at,
            detected_monotonic_ns=4_000_000_000,
            detected_monotonic_clock_domain_id=(
                fixture.session.monotonic_clock_domain_id
            ),
            signer=fixture.signer,
            idempotency_key="transport-termination",
            close_code=1000,
        )

        clock.value = healthy_at + timedelta(milliseconds=400)
        decision_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="stale-decision-gate",
        )
        assert decision_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert (
            "CURRENT_HEALTH_LAGS_PROVIDER_EVIDENCE"
            in decision_gate.abstention_reason_codes
        )
        h2_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.EXECUTION_BAR,
            idempotency_key="stale-execution-gate",
        )
        assert h2_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "EXECUTION_GATE_BRIDGE_NOT_IMPLEMENTED" in (
            h2_gate.abstention_reason_codes
        )

        disconnected_at = healthy_at + timedelta(milliseconds=350)
        clock.value = healthy_at + timedelta(milliseconds=500)
        _, disconnected = store.append_derived_health_cutoff(
            physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=disconnected_at,
            idempotency_key="terminated-health-cutoff",
        )
        assert disconnected.current_health is PrefixHealth.DISCONNECTED
        assert disconnected.current_transport_session_id == (
            termination.transport_session_id
        )
        assert (
            "CURRENT_TRANSPORT_SESSION_TERMINATED" in disconnected.health_reason_codes
        )


@pytest.mark.parametrize(
    ("target", "fault_stage", "typed_table"),
    (
        (
            "policy",
            "after_transport_subscription_policy_insert",
            "transport_subscription_policies",
        ),
        (
            "session",
            "after_transport_session_attestation_insert",
            "transport_session_attestations",
        ),
    ),
)
def test_early_transport_projection_faults_roll_back_all_rows(
    tmp_path: Path,
    target: str,
    fault_stage: str,
    typed_table: str,
) -> None:
    def fail_target(stage: str) -> None:
        if stage == fault_stage:
            raise InjectedTransportProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"rollback-{target}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        primary = bar_policy(requires_status=True)
        required_status = status_policy()
        scope = authority_scope(primary, required_status)
        signer = Ed25519CheckpointSigner.generate()
        clock.value = scope.frozen_at
        _, deployment_capability = append_test_operational_deployment(
            store,
            signer=signer,
            verified_at=scope.frozen_at,
            valid_until=T0 + timedelta(days=1),
            idempotency_prefix=f"{target}-deployment",
        )
        policy = transport_policy(
            signer=signer,
            frozen_at=scope.frozen_at,
            deployment_capability=deployment_capability,
        )
        store.append_health_policy(idempotency_key=f"{target}-health-policy")
        store.append_adapter_policy(primary, idempotency_key=f"{target}-primary")
        store.append_adapter_policy(
            required_status,
            idempotency_key=f"{target}-status",
        )
        store.append_scope(scope, idempotency_key=f"{target}-scope")
        session: TransportSessionAttestationV4 | None = None
        socket_owner_binding: TransportSocketOwnerBindingV4 | None = None
        if target == "session":
            store.append_transport_subscription_policy(
                policy,
                idempotency_key="session-policy",
            )
            session = signed_session(
                fixture_policy=policy,
                scope=scope,
                primary=primary,
                signer=signer,
                deployment_capability=deployment_capability,
            )
            writer_token = digest("faulted-session-writer-fence")
            writer_generation = store.claim_transport_runtime_writer_fence(
                lease_token_sha256=writer_token,
                holder_id="faulted-session-writer",
            )
            socket_owner_binding = signed_test_socket_owner_binding(
                session=session,
                signer=signer,
                writer_fence_token_sha256=writer_token,
                writer_fence_generation=writer_generation,
                label="faulted-session",
            )
            clock.value = T0 - timedelta(milliseconds=500)

        before_receipts = receipt_count(store)
        before_canonical = store.verify().canonical_record_count
        idempotency_key = f"faulted-{target}"
        with pytest.raises(InjectedTransportProjectionFailure, match=fault_stage):
            if target == "policy":
                store.append_transport_subscription_policy(
                    policy,
                    idempotency_key=idempotency_key,
                )
            else:
                assert session is not None
                assert socket_owner_binding is not None
                store.append_transport_session_attestation(
                    session,
                    socket_owner_binding=socket_owner_binding,
                    idempotency_key=idempotency_key,
                )

        report = store.verify()
        assert receipt_count(store) == before_receipts
        assert report.canonical_record_count == before_canonical
        assert store._connection.execute(  # noqa: SLF001
            f"SELECT count(*) FROM {typed_table}"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone() == (0,)


@pytest.mark.parametrize(
    ("target", "fault_stage", "typed_table"),
    (
        (
            "intent",
            "after_outbound_subscription_intent_insert",
            "outbound_subscription_intents",
        ),
        (
            "binding",
            "after_subscription_ack_binding_insert",
            "subscription_ack_bindings",
        ),
        (
            "termination",
            "after_transport_session_termination_insert",
            "transport_session_terminations",
        ),
    ),
)
def test_transport_projection_faults_roll_back_canonical_typed_and_batch_rows(
    tmp_path: Path,
    target: str,
    fault_stage: str,
    typed_table: str,
) -> None:
    def fail_target(stage: str) -> None:
        if stage == fault_stage:
            raise InjectedTransportProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"rollback-{target}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        fixture = prepare_transport_fixture(
            store,
            clock=clock,
            authorize=target != "intent",
        )
        occurrence: AckOccurrence | None = None
        if target in {"binding", "termination"}:
            assert fixture.intent is not None
            occurrence = append_ack_occurrence(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                payload=ack_payload(
                    request_id=fixture.intent.request_id,
                    provider_connection_id="provider-opaque-a",
                ),
                sequence=1,
                received_at=T0 + timedelta(milliseconds=10),
                idempotency_suffix=f"rollback-{target}-ack",
            )
        if target == "termination":
            assert fixture.intent is not None and occurrence is not None
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=occurrence,
                idempotency_key="pre-termination-binding",
            )

        before_receipts = receipt_count(store)
        before_canonical = store.verify().canonical_record_count
        before_typed = int(
            store._connection.execute(  # noqa: SLF001
                f"SELECT count(*) FROM {typed_table}"
            ).fetchone()[0]
        )
        idempotency_key = f"faulted-{target}"
        with pytest.raises(InjectedTransportProjectionFailure, match=fault_stage):
            if target == "intent":
                store.authorize_outbound_subscription_intent(
                    fixture.session.transport_session_id,
                    idempotency_key=idempotency_key,
                )
            elif target == "binding":
                assert fixture.intent is not None and occurrence is not None
                bind_ack(
                    store,
                    clock=clock,
                    fixture=fixture,
                    intent=fixture.intent,
                    occurrence=occurrence,
                    idempotency_key=idempotency_key,
                )
            else:
                clock.value = T0 + timedelta(seconds=2)
                store.append_transport_session_termination(
                    transport_session_id=fixture.session.transport_session_id,
                    reason=TransportSessionTerminationReasonV4.REMOTE_CLOSE,
                    detected_at=T0 + timedelta(seconds=1),
                    detected_monotonic_ns=3_000_000_000,
                    detected_monotonic_clock_domain_id=(
                        fixture.session.monotonic_clock_domain_id
                    ),
                    signer=fixture.signer,
                    idempotency_key=idempotency_key,
                    close_code=1000,
                )

        report = store.verify()
        assert receipt_count(store) == before_receipts
        assert report.canonical_record_count == before_canonical
        assert (
            store._connection.execute(  # noqa: SLF001
                f"SELECT count(*) FROM {typed_table}"
            ).fetchone()[0]
            == before_typed
        )
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone() == (0,)

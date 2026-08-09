from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.contracts import (
    InformationDependencyV3,
    InformationSetV3,
    StateCheckpointDependencyV3,
    VintageClass,
)
from riskyieldmm.trading.evidence import DependencySelectionMode
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_evidence_v4 import (
    PhysicalMessageV4,
    PhysicalScopeManifestV4,
    message_disposition_from_v3,
)
from riskyieldmm.trading.physical_health_v4 import (
    REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
    REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
)
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    ContinuityPolicy,
    MessageDispositionKind,
    ObservationRevisionV3,
    PhysicalGateStage,
    PhysicalGateVerdict,
    PhysicalVintage,
    PrefixHealth,
    ProviderAdapterPolicyV3,
    SelectionStatus,
    build_bybit_v5_message_disposition,
    observation_value_digest,
)
from riskyieldmm.trading.physical_projection_v4 import (
    ClassificationAppendV4,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_selection_v4 import PhysicalProtocolBindingV4
from riskyieldmm.trading.physical_transport_owner_v4 import (
    LINUX_BOOTTIME_CLOCK_PROFILE_V4,
    LINUX_SOCKET_IDENTITY_PROFILE_V4,
    TransportSocketOwnerBindingV4,
    derive_linux_boottime_clock_domain_id,
    derive_linux_kernel_socket_identity,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
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
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    epoch_milliseconds,
    kline_bytes,
    segment,
    source_member_placeholder,
    status_bytes,
    status_policy,
)
from tests.test_trading_physical_transport_runtime_v4 import deployment_admission


@dataclass
class FixedClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


def authority_scope(
    primary: ProviderAdapterPolicyV3,
    required_status: ProviderAdapterPolicyV3,
) -> PhysicalScopeManifestV4:
    member = source_member_placeholder(primary)
    return PhysicalScopeManifestV4(
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        provider_id=primary.provider_id,
        venue_id=primary.venue_id,
        environment_id=primary.environment_id,
        asset_id=primary.asset_id,
        concrete_contract_id=primary.concrete_contract_id,
        timeframe_id=primary.timeframe_id,
        primary_adapter_policy_id=primary.adapter_policy_id,
        primary_classifier_release_hash=primary.message_classifier_release_hash,
        required_status_adapter_policy_id=required_status.adapter_policy_id,
        required_status_classifier_release_hash=(
            required_status.message_classifier_release_hash
        ),
        calendar_manifest_id=primary.calendar_manifest_id,
        protocol_lineage_id=digest("physical-authority-v4-projection-tests"),
        health_policy_id=REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
        frozen_at=primary.frozen_at,
    )


def subscription_ack_bytes(*, request_id: str) -> bytes:
    return json.dumps(
        {
            "success": True,
            "ret_msg": "",
            "conn_id": "provider-connection-opaque-1",
            "req_id": request_id,
            "op": "subscribe",
        },
        separators=(",", ":"),
    ).encode()


def fresh_status_bytes(*, published_at: datetime) -> bytes:
    payload = json.loads(status_bytes().decode())
    payload["time"] = epoch_milliseconds(published_at)
    return json.dumps(payload, separators=(",", ":")).encode()


def append_one_message(
    store: PhysicalProjectionStoreV4,
    *,
    scope: PhysicalScopeManifestV4,
    capture: CaptureSegmentV3,
    idempotency_key: str,
) -> PhysicalMessageV4:
    messages = store.append_messages(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        segment=capture,
        idempotency_key=idempotency_key,
    )
    assert len(messages) == 1
    return messages[0]


def receipt_count(store: PhysicalProjectionStoreV4) -> int:
    row = store._connection.execute("SELECT count(*) FROM receipts").fetchone()  # noqa: SLF001
    assert row is not None
    return int(row[0])


def project_classification(
    *,
    store: PhysicalProjectionStoreV4,
    policy: ProviderAdapterPolicyV3,
    scope: PhysicalScopeManifestV4,
    capture: CaptureSegmentV3,
    message: PhysicalMessageV4,
) -> ClassificationAppendV4:
    durable_at = store.get_receipt(message.raw_capture_receipt_sequence).committed_at
    provider, derivation, revision = build_bybit_v5_message_disposition(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=message.message_receipt_id,
        source_member_key=scope.source_member_key,
        instrument_mapping_id=scope.instrument_mapping_id,
        durably_appended_ts=durable_at,
        normalized_at=durable_at + timedelta(milliseconds=100),
        available_at=durable_at + timedelta(milliseconds=200),
        classified_at=durable_at + timedelta(milliseconds=300),
    )
    projected = message_disposition_from_v3(
        message=message,
        disposition=provider,
    )
    return ClassificationAppendV4(
        disposition=projected,
        provider_disposition=provider,
        derivation=derivation,
        revision=revision,
    )


def append_live_authority_prefix(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    scope: PhysicalScopeManifestV4,
    primary: ProviderAdapterPolicyV3,
    required_status: ProviderAdapterPolicyV3,
) -> tuple[tuple[ClassificationAppendV4, ...], CaptureSegmentV3]:
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission(
        signer,
        valid_from=scope.frozen_at - timedelta(days=1),
        valid_until=T0 + timedelta(days=1),
    )
    clock.value = scope.frozen_at
    store.append_deployment_trust_root(
        admission.trust_root,
        idempotency_key="authority-deployment-root",
    )
    for index, child in enumerate(admission.children):
        store.append_operational_child_manifest(
            child,
            idempotency_key=f"authority-deployment-child-{index}",
        )
    deployment_capability = store.append_deployment_bundle_approval(
        admission.approval,
        verified_at=scope.frozen_at,
        idempotency_key="authority-deployment-approval",
    )
    transport_policy = TransportSubscriptionPolicyV4(
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
        frozen_at=scope.frozen_at,
    )
    clock.value = scope.frozen_at
    store.append_transport_subscription_policy(
        transport_policy,
        idempotency_key="authority-transport-policy",
    )

    ack_received = T0 + timedelta(milliseconds=10)
    partition_probe = segment(
        primary,
        b"{}",
        sequence=1,
        received_at=ack_received,
    )
    handshake_started = T0 - timedelta(seconds=2)
    handshake_completed = T0 - timedelta(seconds=1)
    session = TransportSessionAttestationV4.create_signed(
        signer=signer,
        deployment_bundle_id=transport_policy.deployment_bundle_id,
        clock_source_manifest_id=deployment_capability.clock_source_manifest_id,
        collector_key_authorization_manifest_id=(
            transport_policy.collector_key_authorization_manifest_id
        ),
        transport_subscription_policy_id=(
            transport_policy.transport_subscription_policy_id
        ),
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        adapter_policy_id=primary.adapter_policy_id,
        capture_partition_id=partition_probe.capture_partition_id,
        collector_instance_id=partition_probe.collector_instance_id,
        collector_boot_id=partition_probe.collector_boot_id,
        connection_generation=1,
        session_nonce=digest("authority-v45-session-nonce"),
        parent_transport_session_id=None,
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        remote_address="bybit-edge-diagnostic",
        tls_version=V4_TRANSPORT_MINIMUM_TLS_VERSION,
        tls_cipher="TLS_AES_128_GCM_SHA256",
        alpn_protocol=None,
        websocket_extensions=(),
        peer_certificate_sha256=digest("bybit-leaf-certificate"),
        peer_spki_sha256=digest("bybit-leaf-spki"),
        trust_store_manifest_id=deployment_capability.trust_store_manifest_id,
        certificate_verified=True,
        hostname_verified=True,
        websocket_http_status=V4_TRANSPORT_WEBSOCKET_HTTP_STATUS,
        websocket_accept_verified=True,
        handshake_commitment_profile=V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
        handshake_request_sha256=digest("websocket-handshake-request"),
        handshake_response_sha256=digest("websocket-handshake-response"),
        handshake_started_at=handshake_started,
        handshake_completed_at=handshake_completed,
        handshake_started_monotonic_ns=100_000_000,
        handshake_completed_monotonic_ns=200_000_000,
        monotonic_clock_domain_id=derive_linux_boottime_clock_domain_id(
            kernel_boot_id=partition_probe.collector_boot_id,
            time_namespace_id=digest("test-time-namespace"),
        ),
        clock_uncertainty_milliseconds=20,
        collector_release_hash=deployment_capability.collector_release_hash,
        collector_runtime_id=deployment_capability.collector_runtime_id,
    )
    writer_token = digest("authority-owner-writer-fence")
    writer_generation = store.claim_transport_runtime_writer_fence(
        lease_token_sha256=writer_token,
        holder_id="authority-owner-writer",
    )
    cookie = digest("authority-owner-socket-cookie")[:16]
    kernel_socket_identity = derive_linux_kernel_socket_identity(
        kernel_boot_id=session.collector_boot_id,
        network_namespace_id=digest("test-network-namespace"),
        socket_cookie_u64=cookie,
    )
    nonce_digest = derive_transport_socket_lease_nonce_sha256(
        bytes.fromhex(digest("authority-owner-capability"))
    )
    socket_lease_id = derive_transport_socket_lease_id(
        transport_session_id=session.transport_session_id,
        kernel_socket_identity=kernel_socket_identity,
        socket_lease_nonce_sha256=nonce_digest,
        writer_fence_token_sha256=writer_token,
        writer_fence_generation=writer_generation,
    )
    socket_owner_binding = TransportSocketOwnerBindingV4.create_signed(
        signer=signer,
        transport_session_id=session.transport_session_id,
        deployment_bundle_id=session.deployment_bundle_id,
        transport_subscription_policy_id=session.transport_subscription_policy_id,
        physical_scope_manifest_id=session.physical_scope_manifest_id,
        adapter_policy_id=session.adapter_policy_id,
        capture_partition_id=session.capture_partition_id,
        socket_lease_id=socket_lease_id,
        socket_lease_nonce_sha256=nonce_digest,
        kernel_socket_identity=kernel_socket_identity,
        socket_identity_profile=LINUX_SOCKET_IDENTITY_PROFILE_V4,
        socket_cookie_u64=cookie,
        kernel_boot_id=session.collector_boot_id,
        time_namespace_id=digest("test-time-namespace"),
        network_namespace_id=digest("test-network-namespace"),
        clock_source_manifest_id=session.clock_source_manifest_id,
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        clock_profile=LINUX_BOOTTIME_CLOCK_PROFILE_V4,
        clock_resolution_ns=1,
        connection_generation=session.connection_generation,
        writer_fence_token_sha256=writer_token,
        writer_fence_generation=writer_generation,
        bound_at=session.handshake_completed_at + timedelta(milliseconds=1),
        bound_monotonic_before_ns=(
            session.handshake_completed_monotonic_ns + 1_000_000
        ),
        bound_monotonic_after_ns=(session.handshake_completed_monotonic_ns + 1_000_001),
        clock_uncertainty_milliseconds=session.clock_uncertainty_milliseconds,
    )
    clock.value = T0 - timedelta(milliseconds=500)
    store.append_transport_session_attestation(
        session,
        socket_owner_binding=socket_owner_binding,
        idempotency_key="authority-transport-session",
    )
    intent = store.authorize_outbound_subscription_intent(
        session.transport_session_id,
        idempotency_key="authority-subscription-intent",
    )
    ack_capture = replace(
        segment(
            primary,
            subscription_ack_bytes(request_id=intent.request_id),
            sequence=1,
            received_at=ack_received,
            connection_id=session.transport_session_id,
        ),
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )

    clock.value = ack_received + timedelta(milliseconds=100)
    ack_message = append_one_message(
        store,
        scope=scope,
        capture=ack_capture,
        idempotency_key="authority-message-1",
    )
    ack_classification = project_classification(
        store=store,
        policy=primary,
        scope=scope,
        capture=ack_capture,
        message=ack_message,
    )
    clock.value = ack_classification.provider_disposition.classified_at
    store.append_classification_batch(
        (ack_classification,),
        idempotency_key="authority-ack-classification",
    )
    store.bind_subscription_ack(
        outbound_subscription_intent_id=intent.outbound_subscription_intent_id,
        message_disposition_id=(ack_classification.disposition.message_disposition_id),
        dispatch_started_at=T0 - timedelta(milliseconds=250),
        dispatch_completed_at=T0 - timedelta(milliseconds=100),
        dispatch_started_monotonic_ns=300_000_000,
        dispatch_completed_monotonic_ns=400_000_000,
        signer=signer,
        idempotency_key="authority-subscription-ack-binding",
    )

    first_bar_received = T0 + timedelta(minutes=1, milliseconds=200)
    first_bar_capture = replace(
        segment(
            primary,
            kline_bytes(bar_start=T0, close="100.5"),
            sequence=2,
            received_at=first_bar_received,
            parent=ack_capture,
            connection_id=session.transport_session_id,
        ),
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )
    second_bar_received = T0 + timedelta(minutes=2, milliseconds=200)
    second_bar_capture = replace(
        segment(
            primary,
            kline_bytes(
                bar_start=T0 + timedelta(minutes=1),
                close="101.0",
            ),
            sequence=3,
            received_at=second_bar_received,
            parent=first_bar_capture,
            connection_id=session.transport_session_id,
        ),
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )

    status_published = T0 + timedelta(minutes=2, milliseconds=700)
    status_received = status_published + timedelta(milliseconds=100)
    status_capture = segment(
        required_status,
        fresh_status_bytes(published_at=status_published),
        sequence=1,
        received_at=status_received,
    )

    captures = (
        (
            primary,
            first_bar_capture,
            first_bar_received + timedelta(milliseconds=100),
        ),
        (
            primary,
            second_bar_capture,
            second_bar_received + timedelta(milliseconds=100),
        ),
        (
            required_status,
            status_capture,
            status_received + timedelta(milliseconds=100),
        ),
    )
    classifications: list[ClassificationAppendV4] = [ack_classification]
    for index, (policy, capture, durable_at) in enumerate(captures, start=2):
        clock.value = durable_at
        message = append_one_message(
            store,
            scope=scope,
            capture=capture,
            idempotency_key=f"authority-message-{index}",
        )
        classifications.append(
            project_classification(
                store=store,
                policy=policy,
                scope=scope,
                capture=capture,
                message=message,
            )
        )

    assert [item.disposition.disposition_kind for item in classifications] == [
        MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        MessageDispositionKind.NORMALIZED_OBSERVATION,
        MessageDispositionKind.NORMALIZED_OBSERVATION,
        MessageDispositionKind.NORMALIZED_OBSERVATION,
    ]
    clock.value = max(
        item.provider_disposition.classified_at for item in classifications[1:]
    )
    store.append_classification_batch(
        classifications[1:],
        idempotency_key="authority-post-binding-classifications",
    )
    return tuple(classifications), second_bar_capture


def exact_event_binding(scope: PhysicalScopeManifestV4) -> PhysicalProtocolBindingV4:
    return PhysicalProtocolBindingV4(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        protocol_manifest_id=digest("authority-protocol-manifest"),
        source_manifest_id=digest("authority-source-manifest"),
        calendar_manifest_id=scope.calendar_manifest_id,
        feature_schema_id=digest("authority-feature-schema"),
        dependency_slot_id=digest("authority-primary-bar-slot"),
        source_member_id=digest("authority-primary-source-member"),
        source_member_key=scope.source_member_key,
        observation_selection_policy_id=digest("authority-exact-event-policy"),
        selection_mode=DependencySelectionMode.EXACT_EVENT,
        anchor_lag_intervals=0,
        requested_count=1,
        maximum_age_seconds=300,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        frozen_at=scope.frozen_at,
    )


def dependency_for_revision(
    *,
    binding: PhysicalProtocolBindingV4,
    revision: ObservationRevisionV3,
) -> InformationDependencyV3:
    assert revision.bar_open_ts is not None
    assert revision.bar_close_ts is not None
    return InformationDependencyV3(
        dependency_slot_id=binding.dependency_slot_id,
        source_member_id=binding.source_member_id,
        name="primary-ohlcv",
        source_id=revision.source_id,
        source_manifest_id=binding.source_manifest_id,
        source_field_ids=revision.field_ids,
        observation_revision_id=revision.observation_revision_id,
        source_event_ts=revision.source_event_ts,
        bar_open_ts=revision.bar_open_ts,
        bar_close_ts=revision.bar_close_ts,
        source_publish_ts=revision.source_publish_ts,
        ingested_first_seen_ts=revision.durably_appended_ts,
        revision_received_ts=revision.durably_appended_ts,
        feature_available_ts=revision.available_at,
        value_digest=observation_value_digest(
            revision.field_ids,
            revision.field_values,
        ),
    )


def live_information_set(
    *,
    scope: PhysicalScopeManifestV4,
    binding: PhysicalProtocolBindingV4,
    revision: ObservationRevisionV3,
    observation_cutoff_ts: datetime,
    assembled_at: datetime,
) -> InformationSetV3:
    return InformationSetV3(
        asset_id=scope.asset_id,
        venue_id=scope.venue_id,
        contract_id=scope.concrete_contract_id,
        timeframe_id=scope.timeframe_id,
        observation_cutoff_ts=observation_cutoff_ts,
        assembled_at=assembled_at,
        source_manifest_id=binding.source_manifest_id,
        protocol_manifest_id=binding.protocol_manifest_id,
        calendar_manifest_id=binding.calendar_manifest_id,
        feature_schema_id=binding.feature_schema_id,
        dependencies=(dependency_for_revision(binding=binding, revision=revision),),
        state_dependencies=(),
        vintage_class=VintageClass.LIVE_FIRST_SEEN_CERTIFIED,
        point_in_time_certified=True,
        certification_blockers=(),
    )


def append_newer_primary_pong(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    scope: PhysicalScopeManifestV4,
    primary: ProviderAdapterPolicyV3,
    parent_capture: CaptureSegmentV3,
    received_at: datetime,
) -> ClassificationAppendV4:
    capture = replace(
        segment(
            primary,
            b'{"success":true,"ret_msg":"pong","conn_id":"provider-connection-opaque-1","op":"ping"}',
            sequence=4,
            received_at=received_at,
            parent=parent_capture,
            connection_id=parent_capture.connection_id,
        ),
        subscription_manifest_hash=parent_capture.subscription_manifest_hash,
    )
    clock.value = received_at + timedelta(milliseconds=100)
    message = append_one_message(
        store,
        scope=scope,
        capture=capture,
        idempotency_key="newer-provider-message",
    )
    classification = project_classification(
        store=store,
        policy=primary,
        scope=scope,
        capture=capture,
        message=message,
    )
    assert (
        classification.disposition.disposition_kind
        is MessageDispositionKind.CONTROL_PONG
    )
    clock.value = classification.provider_disposition.classified_at
    store.append_classification_batch(
        (classification,),
        idempotency_key="newer-provider-classification",
    )
    return classification


def test_projection_derives_healthy_authority_then_expires_it_to_stale(
    tmp_path: Path,
) -> None:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    database = tmp_path / "physical-authority-v4.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))

    with PhysicalProjectionStoreV4(database, clock=clock) as store:
        policy = store.append_health_policy(idempotency_key="health-policy")
        assert policy == REVIEWED_PHYSICAL_HEALTH_POLICY_V4
        policy_receipt_count = receipt_count(store)
        assert (
            store.append_health_policy(idempotency_key="health-policy")
            == REVIEWED_PHYSICAL_HEALTH_POLICY_V4
        )
        assert receipt_count(store) == policy_receipt_count

        assert (
            store.append_adapter_policy(
                primary, idempotency_key="authority-primary-adapter"
            )
            == primary
        )
        assert (
            store.append_adapter_policy(
                required_status, idempotency_key="authority-status-adapter"
            )
            == required_status
        )
        adapter_receipt_count = receipt_count(store)
        assert (
            store.append_adapter_policy(
                primary, idempotency_key="authority-primary-adapter"
            )
            == primary
        )
        assert receipt_count(store) == adapter_receipt_count
        assert store.append_scope(scope, idempotency_key="authority-scope") == scope
        classifications, latest_primary_capture = append_live_authority_prefix(
            store,
            clock=clock,
            scope=scope,
            primary=primary,
            required_status=required_status,
        )
        first_bar_revision = classifications[1].revision
        selected_revision = classifications[2].revision
        status_revision = classifications[-1].revision
        assert first_bar_revision is not None
        assert selected_revision is not None
        assert status_revision is not None

        healthy_knowledge = T0 + timedelta(minutes=2, seconds=4)
        clock.value = healthy_knowledge
        healthy_cutoff, healthy_transition = store.append_derived_health_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=healthy_knowledge,
            idempotency_key="derived-health-healthy",
        )
        assert healthy_cutoff.vintage is PhysicalVintage.PROSPECTIVE_LIVE
        assert healthy_cutoff.health is PrefixHealth.HEALTHY
        assert healthy_cutoff.health_reason_codes == ()
        assert healthy_cutoff.tree_size == 4
        assert healthy_cutoff.event_time_watermark == T0 + timedelta(minutes=2)
        assert (
            healthy_cutoff.current_required_status_revision_id
            == status_revision.observation_revision_id
        )
        assert healthy_transition.prior_health is PrefixHealth.BOOTSTRAPPING
        assert healthy_transition.current_health is PrefixHealth.HEALTHY
        assert healthy_transition.health_reason_codes == ()
        assert (
            healthy_transition.evidence_cutoff_id == healthy_cutoff.evidence_cutoff_id
        )

        healthy_receipt_count = receipt_count(store)
        assert store.append_derived_health_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=healthy_knowledge,
            idempotency_key="derived-health-healthy",
        ) == (healthy_cutoff, healthy_transition)
        assert receipt_count(store) == healthy_receipt_count

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="caller-selected HEALTHY is forbidden",
        ):
            store.append_cutoff(
                physical_scope_manifest_id=scope.physical_scope_manifest_id,
                knowledge_cutoff_ts=healthy_knowledge,
                vintage=PhysicalVintage.PROSPECTIVE_LIVE,
                health=PrefixHealth.HEALTHY,
                health_reason_codes=(),
                health_valid_until=healthy_cutoff.health_valid_until,
                current_required_status_revision_id=(
                    status_revision.observation_revision_id
                ),
                event_time_watermark=T0 + timedelta(minutes=2),
                idempotency_key="caller-selected-healthy",
            )
        assert receipt_count(store) == healthy_receipt_count

        binding = exact_event_binding(scope)
        assert (
            store.append_protocol_binding(
                binding,
                idempotency_key="authority-protocol-binding",
            )
            == binding
        )
        proof_computed_at = healthy_knowledge + timedelta(milliseconds=100)
        clock.value = proof_computed_at
        selection_proof, selection_chunk = store.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=healthy_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=healthy_knowledge,
            computed_at=proof_computed_at,
            idempotency_key="authority-selection",
        )
        assert selection_proof.status is SelectionStatus.SELECTED
        assert selection_chunk is not None
        assert selection_chunk.ordered_observation_revision_ids == (
            selected_revision.observation_revision_id,
        )

        information_assembled_at = healthy_knowledge + timedelta(milliseconds=200)
        information_set = live_information_set(
            scope=scope,
            binding=binding,
            revision=selected_revision,
            observation_cutoff_ts=healthy_knowledge,
            assembled_at=information_assembled_at,
        )
        clock.value = information_assembled_at
        assert (
            store.append_information_set(
                information_set,
                idempotency_key="authority-information-set",
            )
            == information_set
        )

        pass_evaluated_at = healthy_knowledge + timedelta(milliseconds=300)
        clock.value = pass_evaluated_at
        passing_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-pass",
        )
        assert passing_gate.evaluated_at == pass_evaluated_at
        assert passing_gate.verdict is PhysicalGateVerdict.PASS
        assert passing_gate.abstention_reason_codes == ()
        assert passing_gate.proof_link_count == 1
        assert passing_gate.health_link_count == 1
        assert passing_gate.valid_until == healthy_cutoff.health_valid_until
        passing_gate_receipt_count = receipt_count(store)
        assert (
            store.evaluate_physical_gate(
                information_set_id=information_set.information_set_id,
                gate_stage=PhysicalGateStage.DECISION_INPUT,
                idempotency_key="authority-gate-pass",
            )
            == passing_gate
        )
        assert receipt_count(store) == passing_gate_receipt_count

        state_dependency = StateCheckpointDependencyV3(
            dependency_slot_id=digest("authority-state-slot"),
            state_schema_id=digest("authority-state-schema"),
            state_cutoff_ts=healthy_knowledge - timedelta(seconds=1),
            state_available_ts=healthy_knowledge - timedelta(milliseconds=500),
            value_digest=digest("authority-state-value"),
        )
        state_information_set = replace(
            information_set,
            assembled_at=healthy_knowledge + timedelta(milliseconds=350),
            state_dependencies=(state_dependency,),
        )
        clock.value = state_information_set.assembled_at
        store.append_information_set(
            state_information_set,
            idempotency_key="authority-information-set-state",
        )
        state_gate_evaluated_at = healthy_knowledge + timedelta(milliseconds=400)
        clock.value = state_gate_evaluated_at
        state_gate = store.evaluate_physical_gate(
            information_set_id=state_information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-state-abstain",
        )
        assert state_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "STATE_DEPENDENCIES_NOT_PHYSICALLY_PROVED" in (
            state_gate.abstention_reason_codes
        )

        mismatched_information_set = replace(
            information_set,
            assembled_at=healthy_knowledge + timedelta(milliseconds=450),
            dependencies=(
                dependency_for_revision(
                    binding=binding,
                    revision=first_bar_revision,
                ),
            ),
        )
        clock.value = mismatched_information_set.assembled_at
        store.append_information_set(
            mismatched_information_set,
            idempotency_key="authority-information-set-mismatched",
        )
        mismatch_gate_evaluated_at = healthy_knowledge + timedelta(milliseconds=500)
        clock.value = mismatch_gate_evaluated_at
        mismatch_gate = store.evaluate_physical_gate(
            information_set_id=mismatched_information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-mismatch-abstain",
        )
        assert mismatch_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "SELECTED_DEPENDENCY_SET_MISMATCH" in (
            mismatch_gate.abstention_reason_codes
        )

        append_newer_primary_pong(
            store,
            clock=clock,
            scope=scope,
            primary=primary,
            parent_capture=latest_primary_capture,
            received_at=healthy_knowledge + timedelta(seconds=1),
        )
        lagging_gate_evaluated_at = healthy_knowledge + timedelta(seconds=2)
        clock.value = lagging_gate_evaluated_at
        lagging_health_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-lagging-health-abstain",
        )
        assert lagging_health_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "CURRENT_HEALTH_LAGS_PROVIDER_EVIDENCE" in (
            lagging_health_gate.abstention_reason_codes
        )

        stale_knowledge = healthy_cutoff.health_valid_until + timedelta(microseconds=1)
        clock.value = stale_knowledge
        stale_cutoff, stale_transition = store.append_derived_health_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=stale_knowledge,
            idempotency_key="derived-health-stale-tick",
        )
        assert stale_cutoff.health is PrefixHealth.STALE
        assert stale_cutoff.tree_size == healthy_cutoff.tree_size + 1
        assert stale_cutoff.tree_root != healthy_cutoff.tree_root
        assert "PRIMARY_BAR_STALE" in stale_cutoff.health_reason_codes
        assert stale_transition.prior_health is PrefixHealth.HEALTHY
        assert stale_transition.current_health is PrefixHealth.STALE
        assert (
            stale_transition.parent_physical_health_transition_id
            == healthy_transition.physical_health_transition_id
        )
        assert stale_transition.evidence_cutoff_id == stale_cutoff.evidence_cutoff_id

        stale_gate_evaluated_at = stale_knowledge + timedelta(microseconds=10)
        clock.value = stale_gate_evaluated_at
        stale_health_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-stale-health-abstain",
        )
        assert stale_health_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "CURRENT_HEALTH_NOT_ELIGIBLE" in (
            stale_health_gate.abstention_reason_codes
        )

        report = store.verify()
        assert report.adapter_policy_count == 2
        assert report.physical_health_policy_count == 1
        assert report.physical_health_transition_count == 2
        assert report.cutoff_count == 2
        assert report.scope_count == 1
        assert report.message_count == report.disposition_count == 5
        assert report.protocol_binding_count == 1
        assert report.selection_result_chunk_count == 1
        assert report.observation_selection_proof_count == 1
        assert report.information_set_count == 3
        assert report.physical_evidence_gate_count == 5

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
    PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION,
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    V4_TRANSPORT_SEND_DEADLINE_SECONDS,
    OutboundSubscriptionIntentV4,
    SubscriptionAckBindingV4,
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
    TransportSessionTerminationV4,
    TransportSubscriptionPolicyV4,
    build_outbound_subscription_intent_v4,
    derive_transport_attestation_key_id,
)

T0 = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def policy(signer: Ed25519CheckpointSigner) -> TransportSubscriptionPolicyV4:
    return TransportSubscriptionPolicyV4(
        deployment_bundle_id=digest("deployment-bundle"),
        collector_key_authorization_manifest_id=digest("collector-key-authorization"),
        policy_name="RiskYieldMMBybitLinearSubscriptionV4_5",
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        port=443,
        websocket_path=BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
        direct_connection_only=True,
        minimum_tls_version="TLSv1.3",
        certificate_verification_required=True,
        hostname_verification_required=True,
        websocket_http_status_required=101,
        websocket_accept_validation_required=True,
        allowed_websocket_extensions=(),
        allowed_subprotocols=(),
        single_topic_per_session=True,
        maximum_inflight_subscriptions=1,
        require_nonempty_echoed_request_id=True,
        maximum_request_id_length=36,
        send_deadline_seconds=V4_TRANSPORT_SEND_DEADLINE_SECONDS,
        ack_deadline_seconds=10,
        collector_attestation_key_id=derive_transport_attestation_key_id(
            signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
        frozen_at=T0,
    )


def session_fields(policy_record: TransportSubscriptionPolicyV4) -> dict[str, object]:
    return {
        "deployment_bundle_id": policy_record.deployment_bundle_id,
        "clock_source_manifest_id": digest("clock-source-manifest"),
        "collector_key_authorization_manifest_id": (
            policy_record.collector_key_authorization_manifest_id
        ),
        "transport_subscription_policy_id": (
            policy_record.transport_subscription_policy_id
        ),
        "physical_scope_manifest_id": digest("scope"),
        "adapter_policy_id": digest("adapter"),
        "capture_partition_id": digest("partition"),
        "collector_instance_id": "collector-1",
        "collector_boot_id": "boot-1",
        "connection_generation": 1,
        "session_nonce": digest("session-nonce"),
        "parent_transport_session_id": None,
        "authoritative_endpoint": BYBIT_V5_LINEAR_ENDPOINT_V4,
        "tls_server_name": BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        "remote_address": "203.0.113.10:443",
        "tls_version": "TLSv1.3",
        "tls_cipher": "TLS_AES_128_GCM_SHA256",
        "alpn_protocol": None,
        "websocket_extensions": (),
        "peer_certificate_sha256": digest("leaf-certificate"),
        "peer_spki_sha256": digest("leaf-spki"),
        "trust_store_manifest_id": digest("trust-store"),
        "certificate_verified": True,
        "hostname_verified": True,
        "websocket_http_status": 101,
        "websocket_accept_verified": True,
        "handshake_commitment_profile": (V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE),
        "handshake_request_sha256": digest("handshake-request"),
        "handshake_response_sha256": digest("handshake-response"),
        "handshake_started_at": T0 + timedelta(milliseconds=1),
        "handshake_completed_at": T0 + timedelta(milliseconds=2),
        "monotonic_clock_domain_id": digest("monotonic-clock-domain"),
        "handshake_started_monotonic_ns": 1_000,
        "handshake_completed_monotonic_ns": 2_000,
        "clock_uncertainty_milliseconds": 1,
        "collector_release_hash": digest("collector-release"),
        "collector_runtime_id": digest("collector-runtime"),
    }


def session(
    signer: Ed25519CheckpointSigner,
    policy_record: TransportSubscriptionPolicyV4,
) -> TransportSessionAttestationV4:
    return TransportSessionAttestationV4.create_signed(
        signer=signer, **session_fields(policy_record)
    )


def intent(
    policy_record: TransportSubscriptionPolicyV4,
    session_record: TransportSessionAttestationV4,
) -> OutboundSubscriptionIntentV4:
    return build_outbound_subscription_intent_v4(
        transport_subscription_policy_id=(
            policy_record.transport_subscription_policy_id
        ),
        transport_session_id=session_record.transport_session_id,
        physical_scope_manifest_id=session_record.physical_scope_manifest_id,
        adapter_policy_id=session_record.adapter_policy_id,
        capture_partition_id=session_record.capture_partition_id,
        connection_generation=session_record.connection_generation,
        intent_nonce=digest("intent-nonce"),
        request_id="riskyieldmm-v45-request-1",
        topic="kline.1.BTCUSDT",
        authorized_at=T0 + timedelta(milliseconds=3),
        send_not_after=T0 + timedelta(seconds=V4_TRANSPORT_SEND_DEADLINE_SECONDS),
        ack_not_after=T0 + timedelta(seconds=10),
    )


def binding_fields(
    policy_record: TransportSubscriptionPolicyV4,
    session_record: TransportSessionAttestationV4,
    intent_record: OutboundSubscriptionIntentV4,
) -> dict[str, object]:
    return {
        "transport_subscription_policy_id": (
            policy_record.transport_subscription_policy_id
        ),
        "transport_session_id": session_record.transport_session_id,
        "outbound_subscription_intent_id": (
            intent_record.outbound_subscription_intent_id
        ),
        "physical_scope_manifest_id": session_record.physical_scope_manifest_id,
        "adapter_policy_id": session_record.adapter_policy_id,
        "capture_partition_id": session_record.capture_partition_id,
        "connection_generation": session_record.connection_generation,
        "capture_segment_id": digest("capture-segment"),
        "physical_message_id": digest("physical-message"),
        "message_receipt_id": digest("message-receipt"),
        "scope_message_sequence": 1,
        "provider_message_disposition_id": digest("provider-disposition"),
        "message_disposition_id": digest("v4-disposition"),
        "raw_ack_sha256": digest("raw-ack"),
        "echoed_request_id": intent_record.request_id,
        "provider_connection_id": "bybit-connection-1",
        "request_command_sha256": intent_record.command_sha256,
        "dispatch_started_at": T0 + timedelta(milliseconds=4),
        "dispatch_completed_at": T0 + timedelta(milliseconds=5),
        "dispatch_started_monotonic_ns": 3_000,
        "dispatch_completed_monotonic_ns": 4_000,
        "ack_received_at": T0 + timedelta(milliseconds=6),
        "ack_received_monotonic_ns": 5_000,
        "bound_at": T0 + timedelta(milliseconds=7),
    }


def termination_fields(
    policy_record: TransportSubscriptionPolicyV4,
    session_record: TransportSessionAttestationV4,
) -> dict[str, object]:
    return {
        "transport_subscription_policy_id": (
            policy_record.transport_subscription_policy_id
        ),
        "transport_session_id": session_record.transport_session_id,
        "physical_scope_manifest_id": session_record.physical_scope_manifest_id,
        "capture_partition_id": session_record.capture_partition_id,
        "connection_generation": session_record.connection_generation,
        "reason": TransportSessionTerminationReasonV4.REMOTE_CLOSE,
        "close_code": 1000,
        "close_reason_digest": digest("normal-close"),
        "detected_at": T0 + timedelta(seconds=11),
        "detected_monotonic_clock_domain_id": (
            session_record.monotonic_clock_domain_id
        ),
        "detected_monotonic_ns": 11_000,
        "recorded_at": T0 + timedelta(seconds=11, milliseconds=1),
    }


def test_all_five_records_round_trip_and_verify_signatures() -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    intent_record = intent(policy_record, session_record)
    binding_record = SubscriptionAckBindingV4.create_signed(
        signer=signer,
        **binding_fields(policy_record, session_record, intent_record),
    )
    termination_record = TransportSessionTerminationV4.create_signed(
        signer=signer,
        **termination_fields(policy_record, session_record),
    )

    assert (
        TransportSubscriptionPolicyV4.from_mapping(policy_record.as_dict())
        == policy_record
    )
    assert (
        TransportSessionAttestationV4.from_mapping(session_record.as_dict())
        == session_record
    )
    assert (
        OutboundSubscriptionIntentV4.from_mapping(intent_record.as_dict())
        == intent_record
    )
    assert (
        SubscriptionAckBindingV4.from_mapping(binding_record.as_dict())
        == binding_record
    )
    assert (
        TransportSessionTerminationV4.from_mapping(termination_record.as_dict())
        == termination_record
    )
    session_record.verify_signature()
    binding_record.verify_signature()
    termination_record.verify_signature()


def test_v45_schema_and_exact_handshake_commitment_profile_are_frozen() -> None:
    assert PHYSICAL_TRANSPORT_V4_SCHEMA_VERSION == (
        "riskyieldmm_physical_transport_v4_5"
    )
    assert V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE == (
        "EXACT_DECRYPTED_HTTP1_OPENING_HANDSHAKE_OCTETS_V1"
    )


def test_policy_rejects_any_relaxation_of_reviewed_transport_profile() -> None:
    signer = Ed25519CheckpointSigner.generate()
    item = policy(signer)
    mutations = {
        "direct_connection_only": False,
        "minimum_tls_version": "TLSv1.2",
        "certificate_verification_required": False,
        "hostname_verification_required": False,
        "websocket_http_status_required": 200,
        "websocket_accept_validation_required": False,
        "allowed_websocket_extensions": ("permessage-deflate",),
        "allowed_subprotocols": ("unexpected",),
        "single_topic_per_session": False,
        "maximum_inflight_subscriptions": 2,
        "require_nonempty_echoed_request_id": False,
        "send_deadline_seconds": 1,
        "ack_deadline_seconds": 11,
    }
    for field_name, value in mutations.items():
        with pytest.raises(CanonicalizationError):
            replace(item, **{field_name: value})


def test_session_signature_rejects_content_mutation_and_key_substitution() -> None:
    signer = Ed25519CheckpointSigner.generate()
    other = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    item = session(signer, policy_record)

    with pytest.raises(CanonicalizationError, match="signature"):
        replace(item, remote_address="203.0.113.11:443")
    with pytest.raises(CanonicalizationError, match="signature"):
        replace(
            item,
            collector_attestation_key_id=derive_transport_attestation_key_id(
                other.public_key_bytes
            ),
            collector_attestation_public_key_hex=other.public_key_bytes.hex(),
        )
    with pytest.raises(CanonicalizationError, match="public key"):
        replace(
            item,
            collector_attestation_key_id=digest("forged-key"),
            collector_attestation_public_key_hex="00" * 32,
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("certificate_verified", False),
        ("hostname_verified", False),
        ("websocket_http_status", 200),
        ("websocket_accept_verified", False),
        ("tls_version", "TLSv1.2"),
        ("alpn_protocol", "http/1.1"),
        ("websocket_extensions", ("permessage-deflate",)),
    ),
)
def test_signed_session_fails_closed_on_unreviewed_tls_or_ws_fact(
    field_name: str, value: object
) -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = session_fields(policy(signer))
    fields[field_name] = value
    with pytest.raises(CanonicalizationError, match="reviewed Bybit"):
        TransportSessionAttestationV4.create_signed(signer=signer, **fields)


def test_session_rejects_wrong_handshake_commitment_profile() -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = session_fields(policy(signer))
    fields["handshake_commitment_profile"] = "PARSED_HTTP_FIELDS_V1"

    with pytest.raises(CanonicalizationError, match="handshake_commitment_profile"):
        TransportSessionAttestationV4.create_signed(signer=signer, **fields)


def test_monotonic_clock_domain_ids_require_canonical_hashes() -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    fields = session_fields(policy_record)
    fields["monotonic_clock_domain_id"] = digest("clock-domain").upper()
    with pytest.raises(CanonicalizationError, match="monotonic_clock_domain_id"):
        TransportSessionAttestationV4.create_signed(signer=signer, **fields)

    session_record = session(signer, policy_record)
    termination = termination_fields(policy_record, session_record)
    termination["detected_monotonic_clock_domain_id"] = digest("clock-domain").upper()
    with pytest.raises(
        CanonicalizationError,
        match="detected_monotonic_clock_domain_id",
    ):
        TransportSessionTerminationV4.create_signed(signer=signer, **termination)


def test_session_rejects_reversed_wall_or_monotonic_handshake_clocks() -> None:
    signer = Ed25519CheckpointSigner.generate()
    fields = session_fields(policy(signer))
    fields["handshake_completed_at"] = fields["handshake_started_at"]
    with pytest.raises(CanonicalizationError, match="completion"):
        TransportSessionAttestationV4.create_signed(signer=signer, **fields)

    fields = session_fields(policy(signer))
    fields["handshake_completed_monotonic_ns"] = fields[
        "handshake_started_monotonic_ns"
    ]
    with pytest.raises(CanonicalizationError, match="monotonic"):
        TransportSessionAttestationV4.create_signed(signer=signer, **fields)


def test_intent_builder_freezes_canonical_text_command_and_one_topic() -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    item = intent(policy_record, session_record)

    assert item.command_bytes == (
        b'{"args":["kline.1.BTCUSDT"],"op":"subscribe",'
        b'"req_id":"riskyieldmm-v45-request-1"}'
    )
    with pytest.raises(CanonicalizationError, match="topics|one topic"):
        replace(item, topics=("kline.1.BTCUSDT", "kline.1.ETHUSDT"))
    with pytest.raises(CanonicalizationError, match="request_id"):
        replace(item, request_id="")
    with pytest.raises(CanonicalizationError, match="request_id"):
        replace(item, request_id="contains spaces")
    with pytest.raises(CanonicalizationError, match="command"):
        replace(item, command_base64="e30=")


def test_intent_rejects_noncausal_deadlines() -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    item = intent(policy_record, session_record)

    with pytest.raises(CanonicalizationError, match="deadlines"):
        replace(item, send_not_after=item.authorized_at)
    with pytest.raises(CanonicalizationError, match="deadlines"):
        replace(item, ack_not_after=item.send_not_after)


def test_binding_rejects_mutation_wrong_key_and_reversed_clocks() -> None:
    signer = Ed25519CheckpointSigner.generate()
    other = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    intent_record = intent(policy_record, session_record)
    fields = binding_fields(policy_record, session_record, intent_record)
    item = SubscriptionAckBindingV4.create_signed(signer=signer, **fields)

    with pytest.raises(CanonicalizationError, match="signature"):
        replace(item, provider_connection_id="substituted")
    with pytest.raises(CanonicalizationError, match="signature"):
        replace(
            item,
            collector_attestation_key_id=derive_transport_attestation_key_id(
                other.public_key_bytes
            ),
            collector_attestation_public_key_hex=other.public_key_bytes.hex(),
        )

    fields["ack_received_at"] = fields["dispatch_completed_at"]
    with pytest.raises(CanonicalizationError, match="causally ordered"):
        SubscriptionAckBindingV4.create_signed(signer=signer, **fields)
    fields = binding_fields(policy_record, session_record, intent_record)
    fields["ack_received_monotonic_ns"] = fields["dispatch_completed_monotonic_ns"]
    with pytest.raises(CanonicalizationError, match="monotonic"):
        SubscriptionAckBindingV4.create_signed(signer=signer, **fields)


def test_termination_rejects_invalid_reason_shape_time_and_signature() -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    fields = termination_fields(policy_record, session_record)
    item = TransportSessionTerminationV4.create_signed(signer=signer, **fields)

    with pytest.raises(CanonicalizationError, match="signature"):
        replace(item, close_code=1001)
    fields["reason"] = "UNKNOWN"
    with pytest.raises(CanonicalizationError, match="reason"):
        TransportSessionTerminationV4.create_signed(signer=signer, **fields)
    fields = termination_fields(policy_record, session_record)
    fields["recorded_at"] = T0
    with pytest.raises(CanonicalizationError, match="precedes"):
        TransportSessionTerminationV4.create_signed(signer=signer, **fields)
    fields = termination_fields(policy_record, session_record)
    fields["close_code"] = None
    with pytest.raises(CanonicalizationError, match="requires close_code"):
        TransportSessionTerminationV4.create_signed(signer=signer, **fields)


@pytest.mark.parametrize(
    "reason",
    (
        TransportSessionTerminationReasonV4.BACKPRESSURE,
        TransportSessionTerminationReasonV4.STORAGE_FAILURE,
    ),
)
def test_termination_supports_fail_closed_operational_reasons(
    reason: TransportSessionTerminationReasonV4,
) -> None:
    signer = Ed25519CheckpointSigner.generate()
    policy_record = policy(signer)
    session_record = session(signer, policy_record)
    fields = termination_fields(policy_record, session_record)
    fields.update(reason=reason, close_code=None, close_reason_digest=None)

    item = TransportSessionTerminationV4.create_signed(signer=signer, **fields)

    assert item.reason is reason
    assert TransportSessionTerminationV4.from_mapping(item.as_dict()) == item


def test_persisted_mapping_rejects_unknown_fields_and_identity_mutation() -> None:
    signer = Ed25519CheckpointSigner.generate()
    item = policy(signer)
    payload = item.as_dict()
    payload["unknown"] = "value"
    with pytest.raises(CanonicalizationError, match="unknown"):
        TransportSubscriptionPolicyV4.from_mapping(payload)

    payload = item.as_dict()
    payload["transport_subscription_policy_id"] = digest("wrong")
    with pytest.raises(CanonicalizationError, match="does not match"):
        TransportSubscriptionPolicyV4.from_mapping(payload)

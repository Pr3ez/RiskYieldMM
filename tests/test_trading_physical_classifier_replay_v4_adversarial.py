from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_evidence_v4 import (
    PhysicalMessageV4,
    PhysicalScopeManifestV4,
    message_disposition_from_v3,
)
from riskyieldmm.trading.physical_health_v4 import (
    REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
)
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    CompletionBasis,
    CompletionState,
    MessageDispositionKind,
    ObservationDerivationV3,
    ObservationRevisionV3,
    ProviderAdapterPolicyV3,
    ProviderMessageDispositionV3,
    build_bybit_v5_message_disposition,
)
from riskyieldmm.trading.physical_projection_v4 import (
    ClassificationAppendV4,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_transport_v4 import (
    OutboundSubscriptionIntentV4,
    TransportSessionAttestationV4,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    kline_bytes,
    segment,
    source_member_placeholder,
    status_bytes,
    status_policy,
)
from tests.test_trading_physical_transport_v4_projection import (
    append_test_bound_session,
    append_test_operational_deployment,
    signed_session,
    transport_policy,
)


@dataclass
class MutableClock:
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
        instrument_mapping_id=digest("classifier-replay-mapping"),
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
        protocol_lineage_id=digest("classifier-replay-v4-adversarial"),
        health_policy_id=REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
        frozen_at=primary.frozen_at,
    )


def prepared_store(
    database: Path,
) -> tuple[
    PhysicalProjectionStoreV4,
    MutableClock,
    ProviderAdapterPolicyV3,
    ProviderAdapterPolicyV3,
    PhysicalScopeManifestV4,
    TransportSessionAttestationV4,
    OutboundSubscriptionIntentV4,
]:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    clock = MutableClock(T0 - timedelta(hours=2))
    store = PhysicalProjectionStoreV4(database, clock=clock)
    clock.value = primary.frozen_at
    store.append_adapter_policy(primary, idempotency_key="primary-policy")
    store.append_adapter_policy(required_status, idempotency_key="status-policy")
    store.append_scope(scope, idempotency_key="authority-scope")
    signer = Ed25519CheckpointSigner.generate()
    _, deployment_capability = append_test_operational_deployment(
        store,
        signer=signer,
        verified_at=scope.frozen_at,
        valid_until=T0 + timedelta(days=1),
        idempotency_prefix="classifier-replay-deployment",
    )
    subscription_policy = transport_policy(
        signer=signer,
        frozen_at=scope.frozen_at,
        deployment_capability=deployment_capability,
    )
    store.append_transport_subscription_policy(
        subscription_policy,
        idempotency_key="classifier-replay-transport-policy",
    )
    session = signed_session(
        fixture_policy=subscription_policy,
        scope=scope,
        primary=primary,
        signer=signer,
        deployment_capability=deployment_capability,
        session_nonce_label="classifier-replay-session",
    )
    clock.value = T0 - timedelta(milliseconds=500)
    writer_token = digest("classifier-replay-writer-fence")
    writer_generation = store.claim_transport_runtime_writer_fence(
        lease_token_sha256=writer_token,
        holder_id="classifier-replay-writer",
    )
    append_test_bound_session(
        store,
        session=session,
        signer=signer,
        writer_fence_token_sha256=writer_token,
        writer_fence_generation=writer_generation,
        idempotency_key="classifier-replay-transport-session",
        label="classifier-replay-session",
    )
    intent = store.authorize_outbound_subscription_intent(
        session.transport_session_id,
        idempotency_key="classifier-replay-subscription-intent",
    )
    return store, clock, primary, required_status, scope, session, intent


def authorized_primary_capture(
    policy: ProviderAdapterPolicyV3,
    raw: bytes,
    *,
    session: TransportSessionAttestationV4,
    intent: OutboundSubscriptionIntentV4,
    sequence: int,
    received_at: datetime,
) -> CaptureSegmentV3:
    return replace(
        segment(
            policy,
            raw,
            sequence=sequence,
            received_at=received_at,
            connection_generation=session.connection_generation,
            connection_id=session.transport_session_id,
        ),
        collector_instance_id=session.collector_instance_id,
        collector_boot_id=session.collector_boot_id,
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )


def captured_classification(
    store: PhysicalProjectionStoreV4,
    clock: MutableClock,
    *,
    scope: PhysicalScopeManifestV4,
    policy: ProviderAdapterPolicyV3,
    capture: CaptureSegmentV3,
) -> tuple[
    PhysicalMessageV4,
    ProviderMessageDispositionV3,
    ObservationDerivationV3 | None,
    ObservationRevisionV3 | None,
]:
    durable_at = capture.closed_at + timedelta(milliseconds=50)
    normalized_at = durable_at + timedelta(milliseconds=10)
    available_at = durable_at + timedelta(milliseconds=20)
    classified_at = durable_at + timedelta(milliseconds=30)
    clock.value = durable_at
    messages = store.append_messages(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        segment=capture,
        idempotency_key="captured-message",
    )
    assert len(messages) == 1
    message = messages[0]
    provider, derivation, revision = build_bybit_v5_message_disposition(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=message.message_receipt_id,
        source_member_key=scope.source_member_key,
        instrument_mapping_id=scope.instrument_mapping_id,
        durably_appended_ts=durable_at,
        normalized_at=normalized_at,
        available_at=available_at,
        classified_at=classified_at,
    )
    clock.value = classified_at
    return message, provider, derivation, revision


def assert_rejected_without_classification_writes(
    store: PhysicalProjectionStoreV4,
    classification: ClassificationAppendV4,
    *,
    match: str,
) -> None:
    before = store._connection.execute("SELECT count(*) FROM receipts").fetchone()[0]  # noqa: SLF001
    with pytest.raises(PhysicalProjectionV4ConflictError, match=match):
        store.append_classification_batch(
            (classification,),
            idempotency_key="forged-classification",
        )
    after = store._connection.execute("SELECT count(*) FROM receipts").fetchone()[0]  # noqa: SLF001
    assert after == before
    assert (
        store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM message_dispositions"
        ).fetchone()[0]
        == 0
    )
    assert (
        store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM observation_revisions"
        ).fetchone()[0]
        == 0
    )
    report = store.verify()
    assert report.adapter_policy_count == 2
    assert report.message_count == 1
    assert report.disposition_count == 0


def test_provisional_bar_cannot_be_relabelled_provider_final(
    tmp_path: Path,
) -> None:
    store, clock, primary, _required_status, scope, session, intent = prepared_store(
        tmp_path / "provisional-forgery.sqlite3"
    )
    try:
        capture = authorized_primary_capture(
            primary,
            kline_bytes(confirm=False),
            session=session,
            intent=intent,
            sequence=1,
            received_at=T0 + timedelta(minutes=1, milliseconds=200),
        )
        message, provider, derivation, revision = captured_classification(
            store,
            clock,
            scope=scope,
            policy=primary,
            capture=capture,
        )
        assert (
            provider.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION
        )
        assert derivation is not None
        assert revision is not None
        assert revision.completion_state is CompletionState.PROVISIONAL
        assert revision.completion_basis is CompletionBasis.NONE

        forged_revision = replace(
            revision,
            completion_state=CompletionState.COMPLETE,
            completion_basis=CompletionBasis.PROVIDER_FINAL_FLAG,
        )
        forged_provider = replace(
            provider,
            observation_revision_id=forged_revision.observation_revision_id,
        )
        forged = ClassificationAppendV4(
            disposition=message_disposition_from_v3(
                message=message,
                disposition=forged_provider,
            ),
            provider_disposition=forged_provider,
            derivation=derivation,
            revision=forged_revision,
        )
        assert_rejected_without_classification_writes(
            store,
            forged,
            match="raw normalization differs|normalized outputs differ",
        )
    finally:
        store.close()


def test_halted_status_cannot_be_relabelled_trading(tmp_path: Path) -> None:
    (
        store,
        clock,
        _primary,
        required_status,
        scope,
        _session,
        _intent,
    ) = prepared_store(tmp_path / "status-forgery.sqlite3")
    try:
        capture = segment(
            required_status,
            status_bytes(status="Halted"),
            sequence=1,
            received_at=T0 + timedelta(seconds=30, milliseconds=100),
        )
        message, provider, derivation, revision = captured_classification(
            store,
            clock,
            scope=scope,
            policy=required_status,
            capture=capture,
        )
        assert (
            provider.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION
        )
        assert derivation is not None
        assert revision is not None
        assert revision.field_values == ("Halted", "LinearPerpetual")

        forged_values = ("Trading", "LinearPerpetual")
        forged_derivation = replace(
            derivation,
            output_field_values=forged_values,
        )
        forged_revision = replace(
            revision,
            observation_derivation_id=(forged_derivation.observation_derivation_id),
            field_values=forged_values,
        )
        forged_provider = replace(
            provider,
            observation_derivation_id=(forged_derivation.observation_derivation_id),
            observation_revision_id=forged_revision.observation_revision_id,
        )
        forged = ClassificationAppendV4(
            disposition=message_disposition_from_v3(
                message=message,
                disposition=forged_provider,
            ),
            provider_disposition=forged_provider,
            derivation=forged_derivation,
            revision=forged_revision,
        )
        assert_rejected_without_classification_writes(
            store,
            forged,
            match="raw normalization differs|normalized outputs differ",
        )
    finally:
        store.close()


def test_provider_error_cannot_be_relabelled_subscription_ack(
    tmp_path: Path,
) -> None:
    store, clock, primary, _required_status, scope, session, intent = prepared_store(
        tmp_path / "provider-error-forgery.sqlite3"
    )
    try:
        raw_error = json.dumps(
            {
                "success": False,
                "ret_msg": "subscription failed",
                "conn_id": "conn-1",
                "req_id": "request-1",
                "op": "subscribe",
            },
            separators=(",", ":"),
        ).encode()
        capture = authorized_primary_capture(
            primary,
            raw_error,
            session=session,
            intent=intent,
            sequence=1,
            received_at=T0 + timedelta(seconds=1),
        )
        message, provider, derivation, revision = captured_classification(
            store,
            clock,
            scope=scope,
            policy=primary,
            capture=capture,
        )
        assert provider.disposition_kind is MessageDispositionKind.PROVIDER_ERROR
        assert provider.provider_diagnostic_code == "WS_SUBSCRIBE_FAILED"
        assert derivation is None
        assert revision is None

        forged_provider = replace(
            provider,
            disposition_kind=MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
            provider_diagnostic_code=None,
            provider_diagnostic_digest=None,
        )
        forged = ClassificationAppendV4(
            disposition=message_disposition_from_v3(
                message=message,
                disposition=forged_provider,
            ),
            provider_disposition=forged_provider,
        )
        assert_rejected_without_classification_writes(
            store,
            forged,
            match="provider disposition differs from deterministic classifier replay",
        )
    finally:
        store.close()

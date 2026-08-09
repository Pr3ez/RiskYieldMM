from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_evidence_v4 import (
    PhysicalMessageV4,
    PhysicalScopeManifestV4,
)
from riskyieldmm.trading.physical_health_v4 import (
    REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
)
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    ProviderAdapterPolicyV3,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4VerificationError,
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
    *,
    reviewed: bool,
) -> PhysicalScopeManifestV4:
    member = source_member_placeholder(primary)
    return PhysicalScopeManifestV4(
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("capture-lineage-v4-mapping"),
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
        protocol_lineage_id=digest("capture-lineage-v4-adversarial"),
        health_policy_id=(
            REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4
            if reviewed
            else digest("capture-lineage-storage-only-health-policy")
        ),
        frozen_at=primary.frozen_at,
    )


def prepared_store(
    database: Path,
    *,
    reviewed: bool = False,
) -> tuple[
    PhysicalProjectionStoreV4,
    MutableClock,
    ProviderAdapterPolicyV3,
    PhysicalScopeManifestV4,
]:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status, reviewed=reviewed)
    clock = MutableClock(T0)
    store = PhysicalProjectionStoreV4(database, clock=clock)
    store.append_adapter_policy(primary, idempotency_key="primary-policy")
    store.append_adapter_policy(required_status, idempotency_key="status-policy")
    store.append_scope(scope, idempotency_key="authority-scope")
    return store, clock, primary, scope


def establish_reviewed_transport(
    store: PhysicalProjectionStoreV4,
    *,
    scope: PhysicalScopeManifestV4,
    primary: ProviderAdapterPolicyV3,
) -> tuple[TransportSessionAttestationV4, OutboundSubscriptionIntentV4]:
    signer = Ed25519CheckpointSigner.generate()
    _, deployment_capability = append_test_operational_deployment(
        store,
        signer=signer,
        verified_at=scope.frozen_at,
        valid_until=T0 + timedelta(days=1),
        idempotency_prefix="lineage-deployment",
    )
    policy = transport_policy(
        signer=signer,
        frozen_at=scope.frozen_at,
        deployment_capability=deployment_capability,
    )
    store.append_transport_subscription_policy(
        policy,
        idempotency_key="lineage-transport-policy",
    )
    session = signed_session(
        fixture_policy=policy,
        scope=scope,
        primary=primary,
        signer=signer,
        deployment_capability=deployment_capability,
        session_nonce_label="capture-lineage-session",
    )
    writer_token = digest("capture-lineage-writer-fence")
    writer_generation = store.claim_transport_runtime_writer_fence(
        lease_token_sha256=writer_token,
        holder_id="capture-lineage-writer",
    )
    append_test_bound_session(
        store,
        session=session,
        signer=signer,
        writer_fence_token_sha256=writer_token,
        writer_fence_generation=writer_generation,
        idempotency_key="lineage-transport-session",
        label="capture-lineage-session",
    )
    intent = store.authorize_outbound_subscription_intent(
        session.transport_session_id,
        idempotency_key="lineage-transport-intent",
    )
    return session, intent


def bind_capture_to_transport(
    capture: CaptureSegmentV3,
    *,
    session: TransportSessionAttestationV4,
    intent: OutboundSubscriptionIntentV4,
) -> CaptureSegmentV3:
    return replace(
        capture,
        collector_instance_id=session.collector_instance_id,
        collector_boot_id=session.collector_boot_id,
        connection_id=session.transport_session_id,
        connection_generation=session.connection_generation,
        subscription_manifest_hash=intent.subscription_manifest_hash,
    )


def append_capture(
    store: PhysicalProjectionStoreV4,
    clock: MutableClock,
    *,
    scope: PhysicalScopeManifestV4,
    capture: CaptureSegmentV3,
    idempotency_key: str,
) -> None:
    clock.value = max(clock.value, capture.closed_at + timedelta(milliseconds=50))
    messages = store.append_messages(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        segment=capture,
        idempotency_key=idempotency_key,
    )
    assert len(messages) == len(capture.envelopes)


def assert_capture_rejected_without_writes(
    store: PhysicalProjectionStoreV4,
    clock: MutableClock,
    *,
    scope: PhysicalScopeManifestV4,
    capture: CaptureSegmentV3,
    match: str,
    idempotency_key: str,
) -> None:
    before = store._connection.execute(  # noqa: SLF001
        "SELECT count(*) FROM receipts"
    ).fetchone()[0]
    clock.value = max(clock.value, capture.closed_at + timedelta(milliseconds=50))
    with pytest.raises(PhysicalProjectionV4ConflictError) as exc_info:
        store.append_messages(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            segment=capture,
            idempotency_key=idempotency_key,
        )
    cause = exc_info.value.__cause__
    assert match in str(exc_info.value) or (cause is not None and match in str(cause))
    after = store._connection.execute(  # noqa: SLF001
        "SELECT count(*) FROM receipts"
    ).fetchone()[0]
    assert after == before
    report = store.verify()
    assert report.receipt_count == before


def test_second_capture_root_for_one_partition_is_rejected(tmp_path: Path) -> None:
    store, clock, primary, scope = prepared_store(tmp_path / "second-root.sqlite3")
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        second_root = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=1,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=second_root,
            match="already has a root segment",
            idempotency_key="second-root",
        )
    finally:
        store.close()


def test_capture_successor_cannot_fork_a_superseded_parent(tmp_path: Path) -> None:
    store, clock, primary, scope = prepared_store(tmp_path / "fork.sqlite3")
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        first_child = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=2,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
            parent=root,
        )
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        append_capture(
            store,
            clock,
            scope=scope,
            capture=first_child,
            idempotency_key="first-child",
        )
        fork = segment(
            primary,
            kline_bytes(close="100.9"),
            sequence=2,
            received_at=T0 + timedelta(minutes=2, milliseconds=400),
            parent=root,
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=fork,
            match="forks a superseded parent",
            idempotency_key="fork",
        )
    finally:
        store.close()


def test_capture_successor_cannot_skip_collector_sequence(tmp_path: Path) -> None:
    store, clock, primary, scope = prepared_store(tmp_path / "skip-sequence.sqlite3")
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        skipped = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=3,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
            parent=root,
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=skipped,
            match="skips collector sequence",
            idempotency_key="skip-sequence",
        )
    finally:
        store.close()


def test_connection_id_change_requires_new_generation(tmp_path: Path) -> None:
    store, clock, primary, scope = prepared_store(
        tmp_path / "connection-without-generation.sqlite3"
    )
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        hidden_reconnect = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=2,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
            parent=root,
            connection_id="conn-hidden",
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=hidden_reconnect,
            match="connection ID changed without a new generation",
            idempotency_key="hidden-reconnect",
        )
    finally:
        store.close()


def test_subscription_change_inside_one_generation_is_rejected(
    tmp_path: Path,
) -> None:
    store, clock, primary, scope = prepared_store(
        tmp_path / "subscription-change.sqlite3"
    )
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        child = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=2,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
            parent=root,
        )
        changed_subscription = replace(
            child,
            subscription_manifest_hash=digest("changed-subscription"),
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=changed_subscription,
            match="subscription manifest changed inside one connection generation",
            idempotency_key="changed-subscription",
        )
    finally:
        store.close()


def test_capture_successor_cannot_skip_connection_generation(tmp_path: Path) -> None:
    store, clock, primary, scope = prepared_store(tmp_path / "skip-generation.sqlite3")
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        skipped = segment(
            primary,
            kline_bytes(close="100.75"),
            sequence=2,
            received_at=T0 + timedelta(minutes=2, milliseconds=200),
            parent=root,
            connection_generation=3,
            connection_id="conn-3",
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=skipped,
            match="connection generation skips an epoch",
            idempotency_key="skip-generation",
        )
    finally:
        store.close()


def test_provider_message_occurrence_cannot_be_registered_twice(
    tmp_path: Path,
) -> None:
    store, clock, primary, scope = prepared_store(
        tmp_path / "duplicate-occurrence.sqlite3"
    )
    try:
        root = segment(primary, kline_bytes(), sequence=1)
        append_capture(
            store,
            clock,
            scope=scope,
            capture=root,
            idempotency_key="root",
        )
        another_partition = replace(root, collector_instance_id="collector-b")
        assert another_partition.capture_partition_id != root.capture_partition_id
        assert another_partition.message_receipt_ids == root.message_receipt_ids
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=scope,
            capture=another_partition,
            match="provider message occurrence is already registered",
            idempotency_key="duplicate-occurrence",
        )
    finally:
        store.close()


def test_partition_and_authoritative_adapter_stream_cannot_cross_scopes(
    tmp_path: Path,
) -> None:
    store, clock, primary, authority = prepared_store(
        tmp_path / "cross-scope.sqlite3",
        reviewed=True,
    )
    try:
        session, intent = establish_reviewed_transport(
            store,
            scope=authority,
            primary=primary,
        )
        secondary = replace(
            authority,
            source_member_key=digest("secondary-source-member"),
            protocol_lineage_id=digest("secondary-protocol-lineage"),
            health_policy_id=digest("non-authoritative-health-policy"),
        )
        store.append_scope(secondary, idempotency_key="secondary-scope")
        root = bind_capture_to_transport(
            segment(primary, kline_bytes(), sequence=1),
            session=session,
            intent=intent,
        )
        append_capture(
            store,
            clock,
            scope=authority,
            capture=root,
            idempotency_key="authority-root",
        )

        cross_scope_successor = bind_capture_to_transport(
            segment(
                primary,
                kline_bytes(close="100.75"),
                sequence=2,
                received_at=T0 + timedelta(minutes=2, milliseconds=200),
                parent=root,
            ),
            session=session,
            intent=intent,
        )
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=secondary,
            capture=cross_scope_successor,
            match="capture partition lineage cannot cross physical scopes",
            idempotency_key="cross-scope-partition",
        )

        second_partition = replace(
            segment(
                primary,
                kline_bytes(close="100.9"),
                sequence=1,
                received_at=T0 + timedelta(minutes=2, milliseconds=400),
            ),
            collector_instance_id="collector-b",
        )
        assert second_partition.capture_partition_id != root.capture_partition_id
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=secondary,
            capture=second_partition,
            match="authoritative adapter stream cannot be split across scopes",
            idempotency_key="cross-scope-adapter",
        )
    finally:
        store.close()


def test_reviewed_adapter_policy_cannot_seed_parallel_fresh_scope(
    tmp_path: Path,
) -> None:
    store, _clock, _primary, authority = prepared_store(
        tmp_path / "parallel-reviewed-scope.sqlite3",
        reviewed=True,
    )
    try:
        parallel = replace(
            authority,
            source_member_key=digest("parallel-authority-member"),
            protocol_lineage_id=digest("parallel-authority-lineage"),
        )
        before = store.verify().receipt_count
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="reviewed primary adapter policy already belongs to a scope",
        ):
            store.append_scope(parallel, idempotency_key="parallel-authority")
        report = store.verify()
        assert report.receipt_count == before
        assert report.scope_count == 1
    finally:
        store.close()


def test_registered_same_instrument_adapter_outside_scope_is_rejected(
    tmp_path: Path,
) -> None:
    store, clock, _primary, authority = prepared_store(
        tmp_path / "outside-scope-adapter.sqlite3"
    )
    try:
        outsider = bar_policy(requires_status=False)
        store.append_adapter_policy(outsider, idempotency_key="outsider-policy")
        capture = segment(outsider, kline_bytes(), sequence=1)
        before = store.verify().receipt_count
        assert_capture_rejected_without_writes(
            store,
            clock,
            scope=authority,
            capture=capture,
            match="capture segment adapter policy is outside the physical scope",
            idempotency_key="outside-scope-capture",
        )
        assert store.verify().receipt_count == before
    finally:
        store.close()


def test_canonical_replay_rejects_outside_scope_capture_adapter(
    tmp_path: Path,
) -> None:
    store, clock, _primary, authority = prepared_store(
        tmp_path / "outside-scope-canonical-replay.sqlite3"
    )
    try:
        outsider = bar_policy(requires_status=False)
        store.append_adapter_policy(outsider, idempotency_key="outsider-policy")
        capture = segment(outsider, kline_bytes(), sequence=1)
        clock.value = max(clock.value, capture.closed_at + timedelta(milliseconds=50))
        with pytest.raises(
            PhysicalProjectionV4VerificationError,
            match="canonical capture adapter policy is outside its physical scope",
        ):
            with store._transaction():  # noqa: SLF001
                capture_receipt = store._append_record(capture)  # noqa: SLF001
                envelope = capture.envelopes[0]
                forged_message = PhysicalMessageV4(
                    physical_scope_manifest_id=(authority.physical_scope_manifest_id),
                    scope_message_sequence=1,
                    capture_segment_id=capture.capture_segment_id,
                    envelope_ordinal=0,
                    message_receipt_id=envelope.message_receipt_id,
                    raw_payload_sha256=envelope.raw_payload_sha256,
                    adapter_policy_id=outsider.adapter_policy_id,
                    raw_capture_receipt_sequence=capture_receipt.global_sequence,
                )
                store._append_record(forged_message)  # noqa: SLF001
                store._verify_capture_and_classifier_replay()  # noqa: SLF001
        report = store.verify()
        assert report.adapter_policy_count == 3
        assert report.message_count == 0
    finally:
        store.close()

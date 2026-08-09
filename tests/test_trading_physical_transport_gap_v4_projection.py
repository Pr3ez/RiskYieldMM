from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    validate_capture_segment_lineage,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    _capture_lineage_validation_proxy_v4,
)
from riskyieldmm.trading.physical_transport_v4 import (
    OutboundSubscriptionIntentV4,
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_authority_v4_projection import (
    FixedClock,
    receipt_count,
)
from tests.test_trading_physical_market_data_v3 import T0, kline_bytes, segment
from tests.test_trading_physical_transport_v4_projection import (
    TransportFixture,
    append_test_bound_session,
    prepare_transport_fixture,
    signed_session,
)


@dataclass(frozen=True, slots=True)
class CaptureGapFixture:
    transport: TransportFixture
    root_capture: CaptureSegmentV3
    intermediate_capture: CaptureSegmentV3 | None
    generation_two: TransportSessionAttestationV4
    generation_three: TransportSessionAttestationV4
    generation_three_intent: OutboundSubscriptionIntentV4
    candidate: CaptureSegmentV3


def append_capture(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
    fixture: TransportFixture,
    capture: CaptureSegmentV3,
    *,
    idempotency_key: str,
) -> None:
    clock.value = capture.closed_at + timedelta(milliseconds=50)
    messages = store.append_messages(
        physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
        segment=capture,
        idempotency_key=idempotency_key,
    )
    assert len(messages) == 1


def terminate_session(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
    fixture: TransportFixture,
    session: TransportSessionAttestationV4,
    *,
    detected_at,
    detected_monotonic_ns: int,
    label: str,
) -> None:
    clock.value = detected_at + timedelta(milliseconds=50)
    store.append_transport_session_termination(
        transport_session_id=session.transport_session_id,
        reason=TransportSessionTerminationReasonV4.REMOTE_CLOSE,
        detected_at=detected_at,
        detected_monotonic_ns=detected_monotonic_ns,
        detected_monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        signer=fixture.signer,
        idempotency_key=f"{label}-termination",
        close_code=1000,
    )


def prepare_capture_gap(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
    *,
    capture_intermediate: bool,
) -> CaptureGapFixture:
    fixture = prepare_transport_fixture(store, clock=clock)
    assert fixture.intent is not None
    root_capture = replace(
        segment(
            fixture.primary,
            kline_bytes(),
            sequence=1,
            received_at=T0 + timedelta(minutes=1, milliseconds=200),
            connection_id=fixture.session.transport_session_id,
        ),
        subscription_manifest_hash=fixture.intent.subscription_manifest_hash,
    )
    append_capture(
        store,
        clock,
        fixture,
        root_capture,
        idempotency_key="gap-generation-one-capture",
    )
    terminate_session(
        store,
        clock,
        fixture,
        fixture.session,
        detected_at=T0 + timedelta(minutes=1, milliseconds=400),
        detected_monotonic_ns=1_100_000_000,
        label="gap-generation-one",
    )

    generation_two = signed_session(
        fixture_policy=fixture.policy,
        scope=fixture.scope,
        primary=fixture.primary,
        signer=fixture.signer,
        deployment_capability=fixture.deployment_capability,
        session_nonce_label="gap-generation-two",
        connection_generation=2,
        parent_transport_session_id=fixture.session.transport_session_id,
        handshake_started_at=T0 + timedelta(minutes=1, milliseconds=500),
        handshake_completed_at=T0 + timedelta(minutes=1, milliseconds=600),
        handshake_started_monotonic_ns=1_200_000_000,
        handshake_completed_monotonic_ns=1_300_000_000,
    )
    clock.value = T0 + timedelta(minutes=1, milliseconds=700)
    append_test_bound_session(
        store,
        session=generation_two,
        signer=fixture.signer,
        writer_fence_token_sha256=fixture.writer_fence_token_sha256,
        writer_fence_generation=fixture.writer_fence_generation,
        idempotency_key="gap-generation-two-session",
        label="gap-generation-two",
    )

    intermediate_capture: CaptureSegmentV3 | None = None
    if capture_intermediate:
        generation_two_intent = store.authorize_outbound_subscription_intent(
            generation_two.transport_session_id,
            idempotency_key="gap-generation-two-intent",
        )
        intermediate_capture = replace(
            segment(
                fixture.primary,
                kline_bytes(close="100.75", bar_start=T0 + timedelta(minutes=1)),
                sequence=2,
                received_at=T0 + timedelta(minutes=2, milliseconds=200),
                parent=root_capture,
                connection_generation=2,
                connection_id=generation_two.transport_session_id,
            ),
            subscription_manifest_hash=(
                generation_two_intent.subscription_manifest_hash
            ),
        )
        append_capture(
            store,
            clock,
            fixture,
            intermediate_capture,
            idempotency_key="gap-generation-two-capture",
        )
        generation_two_terminated_at = T0 + timedelta(
            minutes=2,
            milliseconds=400,
        )
        generation_two_terminated_monotonic_ns = 2_100_000_000
        generation_three_started_at = T0 + timedelta(
            minutes=2,
            milliseconds=500,
        )
        generation_three_completed_at = T0 + timedelta(
            minutes=2,
            milliseconds=600,
        )
        generation_three_started_monotonic_ns = 2_200_000_000
        generation_three_completed_monotonic_ns = 2_300_000_000
        candidate_sequence = 3
        candidate_received_at = T0 + timedelta(minutes=3, milliseconds=200)
        candidate_bar_start = T0 + timedelta(minutes=2)
    else:
        generation_two_terminated_at = T0 + timedelta(
            minutes=1,
            milliseconds=800,
        )
        generation_two_terminated_monotonic_ns = 1_400_000_000
        generation_three_started_at = T0 + timedelta(
            minutes=1,
            milliseconds=900,
        )
        generation_three_completed_at = T0 + timedelta(minutes=2)
        generation_three_started_monotonic_ns = 1_500_000_000
        generation_three_completed_monotonic_ns = 1_600_000_000
        candidate_sequence = 2
        candidate_received_at = T0 + timedelta(minutes=2, milliseconds=300)
        candidate_bar_start = T0 + timedelta(minutes=1)

    terminate_session(
        store,
        clock,
        fixture,
        generation_two,
        detected_at=generation_two_terminated_at,
        detected_monotonic_ns=generation_two_terminated_monotonic_ns,
        label="gap-generation-two",
    )
    generation_three = signed_session(
        fixture_policy=fixture.policy,
        scope=fixture.scope,
        primary=fixture.primary,
        signer=fixture.signer,
        deployment_capability=fixture.deployment_capability,
        session_nonce_label="gap-generation-three",
        connection_generation=3,
        parent_transport_session_id=generation_two.transport_session_id,
        handshake_started_at=generation_three_started_at,
        handshake_completed_at=generation_three_completed_at,
        handshake_started_monotonic_ns=generation_three_started_monotonic_ns,
        handshake_completed_monotonic_ns=generation_three_completed_monotonic_ns,
    )
    clock.value = generation_three_completed_at + timedelta(milliseconds=50)
    append_test_bound_session(
        store,
        session=generation_three,
        signer=fixture.signer,
        writer_fence_token_sha256=fixture.writer_fence_token_sha256,
        writer_fence_generation=fixture.writer_fence_generation,
        idempotency_key="gap-generation-three-session",
        label="gap-generation-three",
    )
    generation_three_intent = store.authorize_outbound_subscription_intent(
        generation_three.transport_session_id,
        idempotency_key="gap-generation-three-intent",
    )
    candidate = replace(
        segment(
            fixture.primary,
            kline_bytes(close="101.00", bar_start=candidate_bar_start),
            sequence=candidate_sequence,
            received_at=candidate_received_at,
            parent=root_capture,
            connection_generation=3,
            connection_id=generation_three.transport_session_id,
        ),
        subscription_manifest_hash=(generation_three_intent.subscription_manifest_hash),
    )
    return CaptureGapFixture(
        transport=fixture,
        root_capture=root_capture,
        intermediate_capture=intermediate_capture,
        generation_two=generation_two,
        generation_three=generation_three,
        generation_three_intent=generation_three_intent,
        candidate=candidate,
    )


def test_projection_admits_gap_only_for_terminal_empty_intermediate_and_replays(
    tmp_path: Path,
) -> None:
    database = tmp_path / "empty-intermediate-capture-gap.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(database, clock=clock) as store:
        gap = prepare_capture_gap(store, clock, capture_intermediate=False)
        with pytest.raises(CanonicalizationError, match="skips an epoch"):
            validate_capture_segment_lineage(
                gap.candidate,
                {gap.root_capture.capture_segment_id: gap.root_capture},
            )

        append_capture(
            store,
            clock,
            gap.transport,
            gap.candidate,
            idempotency_key="gap-generation-three-capture",
        )
        report = store.verify()
        assert report.message_count == 2

    with PhysicalProjectionStoreV4(database, clock=clock) as replayed:
        assert replayed.verify().message_count == 2


@pytest.mark.parametrize(
    ("attack", "expected"),
    (
        ("missing", "is missing"),
        ("nonterminal", "is not terminal"),
    ),
)
def test_gap_proof_rejects_missing_or_nonterminal_intermediate_session(
    tmp_path: Path,
    attack: str,
    expected: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"{attack}-intermediate.sqlite3",
        clock=clock,
    ) as store:
        gap = prepare_capture_gap(store, clock, capture_intermediate=False)
        sessions = {
            gap.transport.session.transport_session_id: gap.transport.session,
            gap.generation_two.transport_session_id: gap.generation_two,
            gap.generation_three.transport_session_id: gap.generation_three,
        }
        terminal_session_ids = {
            gap.transport.session.transport_session_id,
            gap.generation_two.transport_session_id,
        }
        if attack == "missing":
            sessions.pop(gap.generation_two.transport_session_id)
        else:
            terminal_session_ids.remove(gap.generation_two.transport_session_id)

        with pytest.raises(CanonicalizationError, match=expected):
            _capture_lineage_validation_proxy_v4(
                gap.candidate,
                {gap.root_capture.capture_segment_id: gap.root_capture},
                transport_sessions=sessions,
                terminal_transport_session_ids=terminal_session_ids,
                captured_transport_session_ids={
                    gap.root_capture.connection_id,
                    gap.candidate.connection_id,
                },
            )


def test_projection_rejects_gap_across_an_intermediate_session_with_capture(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "captured-intermediate.sqlite3",
        clock=clock,
    ) as store:
        gap = prepare_capture_gap(store, clock, capture_intermediate=True)
        assert gap.intermediate_capture is not None
        before = receipt_count(store)
        clock.value = gap.candidate.closed_at + timedelta(milliseconds=50)

        with pytest.raises(PhysicalProjectionV4ConflictError) as exc_info:
            store.append_messages(
                physical_scope_manifest_id=(
                    gap.transport.scope.physical_scope_manifest_id
                ),
                segment=gap.candidate,
                idempotency_key="captured-intermediate-gap",
            )
        assert exc_info.value.__cause__ is not None
        assert "has captured segments" in str(exc_info.value.__cause__)
        assert receipt_count(store) == before
        assert store.verify().message_count == 2


def test_reconciliation_uses_full_session_id_in_idempotency_key(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "reconcile-full-session-id.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        prefix = "startup-reconcile"
        clock.value = T0 + timedelta(seconds=1)
        store.reconcile_unterminated_transport_sessions(
            detected_at=T0,
            detected_monotonic_ns=300_000_000,
            detected_monotonic_clock_domain_id=(
                fixture.session.monotonic_clock_domain_id
            ),
            signer=fixture.signer,
            idempotency_prefix=prefix,
        )

        expected_key = f"{prefix}-{fixture.session.transport_session_id}"
        row = store._connection.execute(  # noqa: SLF001
            "SELECT operation FROM operation_batches WHERE idempotency_key = ?",
            (expected_key,),
        ).fetchone()
        assert row == ("APPEND_TRANSPORT_SESSION_TERMINATION_V4_5",)

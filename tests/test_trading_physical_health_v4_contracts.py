from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
from riskyieldmm.trading.physical_evidence_v4 import PhysicalScopeManifestV4
from riskyieldmm.trading.physical_health_v4 import (
    PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
    PHYSICAL_HEALTH_BLOCKER_LEAF_DOMAIN_V4,
    REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
    REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
    V4_BLOCKER_RECOVERY_RULES,
    V4_HEALTH_STATE_PRECEDENCE,
    V4_MAX_HEALTH_BLOCKERS,
    V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS,
    BlockerRecoveryModeV4,
    HealthEvidenceItemV4,
    PhysicalHealthPolicyV4,
    PhysicalHealthTransitionV4,
    TransportAuthorityContextV4,
    health_blocker_leaf_input_v4,
    health_blocker_root_v4,
    validate_health_transition_successor_v4,
)
from riskyieldmm.trading.physical_health_v4 import (
    reduce_physical_health_v4 as reduce_physical_health_contract_v4,
)
from riskyieldmm.trading.physical_market_data import (
    CaptureSegmentV3,
    CompletionBasis,
    CompletionState,
    MessageDispositionKind,
    ObservationKind,
    ObservationRevisionV3,
    PhysicalVintage,
    PrefixHealth,
    ProviderMessageEnvelopeV3,
    ProviderMessageTypeV3,
)
from riskyieldmm.trading.transparency_log import (
    rfc9162_empty_root,
    rfc9162_tree_hash,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)
PRIMARY_ADAPTER_POLICY_ID = hashlib.sha256(b"primary-adapter-policy").hexdigest()
STATUS_ADAPTER_POLICY_ID = hashlib.sha256(b"status-adapter-policy").hexdigest()
SOURCE_MEMBER_KEY = hashlib.sha256(b"source-member-key").hexdigest()
INSTRUMENT_MAPPING_ID = hashlib.sha256(b"instrument-mapping").hexdigest()


def digest(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


def health_scope(*, requires_status: bool = True) -> PhysicalScopeManifestV4:
    return PhysicalScopeManifestV4(
        source_member_key=SOURCE_MEMBER_KEY,
        instrument_mapping_id=INSTRUMENT_MAPPING_ID,
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        asset_id="BTC",
        concrete_contract_id="BTCUSDT.LINEAR.PERP",
        timeframe_id="1m",
        primary_adapter_policy_id=PRIMARY_ADAPTER_POLICY_ID,
        primary_classifier_release_hash=digest("primary-classifier-release"),
        required_status_adapter_policy_id=(
            STATUS_ADAPTER_POLICY_ID if requires_status else None
        ),
        required_status_classifier_release_hash=(
            digest("status-classifier-release") if requires_status else None
        ),
        calendar_manifest_id=digest("continuous-calendar"),
        protocol_lineage_id=digest("physical-health-reducer-tests"),
        health_policy_id=REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
        frozen_at=T0 - timedelta(hours=1),
    )


def capture_segment(
    *,
    adapter_policy_id: str = PRIMARY_ADAPTER_POLICY_ID,
    sequence: int,
    received_at: datetime,
    vintage: PhysicalVintage = PhysicalVintage.PROSPECTIVE_LIVE,
    collector_instance_id: str = "health-test-collector",
    collector_boot_id: str = "boot-1",
    connection_generation: int = 1,
    connection_id: str | None = None,
    clock_uncertainty_milliseconds: int = 20,
) -> CaptureSegmentV3:
    connection_id = connection_id or digest("connection-1")
    envelope = ProviderMessageEnvelopeV3.from_raw(
        collector_sequence=sequence,
        collector_received_wall_ts=received_at,
        collector_received_monotonic_ns=sequence * 1_000_000_000,
        message_type=ProviderMessageTypeV3.UNKNOWN,
        raw_payload=(
            f"{adapter_policy_id}:{collector_boot_id}:{connection_generation}:"
            f"{connection_id}:{sequence}:{received_at.isoformat()}"
        ).encode(),
    )
    return CaptureSegmentV3(
        adapter_policy_id=adapter_policy_id,
        provider_native_key="BTCUSDT",
        collector_instance_id=collector_instance_id,
        collector_boot_id=collector_boot_id,
        connection_id=connection_id,
        connection_generation=connection_generation,
        subscription_manifest_hash=digest("primary-subscription"),
        vintage=vintage,
        envelopes=(envelope,),
        closed_at=received_at + timedelta(milliseconds=1),
        clock_uncertainty_milliseconds=clock_uncertainty_milliseconds,
    )


def complete_bar(
    *,
    bar_open_ts: datetime,
    label: str,
    parent_observation_revision_id: str | None = None,
    correction_reason: str | None = None,
    close: str = "101",
) -> ObservationRevisionV3:
    bar_close_ts = bar_open_ts + timedelta(minutes=1)
    durable = bar_close_ts + timedelta(milliseconds=100)
    return ObservationRevisionV3(
        adapter_policy_id=PRIMARY_ADAPTER_POLICY_ID,
        source_member_key=SOURCE_MEMBER_KEY,
        instrument_mapping_id=INSTRUMENT_MAPPING_ID,
        source_id="bybit.linear.BTCUSDT.1m.confirmed",
        asset_id="BTC",
        venue_id="BYBIT",
        concrete_contract_id="BTCUSDT.LINEAR.PERP",
        timeframe_id="1m",
        observation_name="ohlcv",
        observation_kind=ObservationKind.BAR,
        bar_open_ts=bar_open_ts,
        bar_close_ts=bar_close_ts,
        source_event_ts=bar_close_ts - timedelta(milliseconds=1),
        source_publish_ts=bar_close_ts + timedelta(milliseconds=50),
        durably_appended_ts=durable,
        normalized_at=durable + timedelta(milliseconds=100),
        available_at=durable + timedelta(milliseconds=200),
        completion_state=CompletionState.COMPLETE,
        completion_basis=CompletionBasis.PROVIDER_FINAL_FLAG,
        observation_derivation_id=digest(f"bar-derivation:{label}"),
        field_ids=("open", "high", "low", "close", "volume"),
        field_values=("100", "102", "99", close, "10"),
        parent_observation_revision_id=parent_observation_revision_id,
        correction_reason=correction_reason,
    )


def complete_trading_status(*, published_at: datetime) -> ObservationRevisionV3:
    durable = published_at + timedelta(milliseconds=100)
    return ObservationRevisionV3(
        adapter_policy_id=STATUS_ADAPTER_POLICY_ID,
        source_member_key=SOURCE_MEMBER_KEY,
        instrument_mapping_id=INSTRUMENT_MAPPING_ID,
        source_id="bybit.linear.BTCUSDT.instrument-status",
        asset_id="BTC",
        venue_id="BYBIT",
        concrete_contract_id="BTCUSDT.LINEAR.PERP",
        timeframe_id="1m",
        observation_name="instrument-status",
        observation_kind=ObservationKind.INSTRUMENT_STATUS,
        bar_open_ts=None,
        bar_close_ts=None,
        source_event_ts=published_at,
        source_publish_ts=published_at,
        durably_appended_ts=durable,
        normalized_at=durable + timedelta(milliseconds=100),
        available_at=durable + timedelta(milliseconds=200),
        completion_state=CompletionState.COMPLETE,
        completion_basis=CompletionBasis.PROVIDER_FINAL_RECORD,
        observation_derivation_id=digest("status-derivation"),
        field_ids=("status", "contract_type"),
        field_values=("Trading", "LinearPerpetual"),
    )


def health_evidence(
    *,
    sequence: int,
    disposition_kind: MessageDispositionKind,
    segment: CaptureSegmentV3,
    revision: ObservationRevisionV3 | None = None,
    label: str | None = None,
) -> HealthEvidenceItemV4:
    return HealthEvidenceItemV4(
        scope_message_sequence=sequence,
        disposition_receipt_sequence=sequence * 10,
        message_disposition_id=digest(label or f"disposition-{sequence}"),
        disposition_kind=disposition_kind,
        adapter_policy_id=segment.adapter_policy_id,
        classified_at=segment.closed_at + timedelta(milliseconds=1),
        capture_segment=segment,
        observation_revision=revision,
        observation_admission_receipt_sequence=(
            sequence * 10
            if disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION
            else None
        ),
    )


def live_ack_and_bars(
    *,
    vintage: PhysicalVintage = PhysicalVintage.PROSPECTIVE_LIVE,
    connection_generation: int = 1,
    connection_id: str | None = None,
    first_sequence: int = 1,
    first_bar_open_ts: datetime = T0,
    bar_count: int = 2,
) -> tuple[HealthEvidenceItemV4, ...]:
    connection_id = connection_id or digest("connection-1")
    ack = health_evidence(
        sequence=first_sequence,
        disposition_kind=MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        segment=capture_segment(
            sequence=first_sequence,
            received_at=first_bar_open_ts + timedelta(milliseconds=10),
            vintage=vintage,
            connection_generation=connection_generation,
            connection_id=connection_id,
        ),
        label=f"ack-{first_sequence}-{connection_generation}",
    )
    bars = tuple(
        health_evidence(
            sequence=first_sequence + index + 1,
            disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
            segment=capture_segment(
                sequence=first_sequence + index + 1,
                received_at=(
                    first_bar_open_ts + timedelta(minutes=index + 1, milliseconds=350)
                ),
                vintage=vintage,
                connection_generation=connection_generation,
                connection_id=connection_id,
            ),
            revision=complete_bar(
                bar_open_ts=first_bar_open_ts + timedelta(minutes=index),
                label=f"bar-{first_sequence}-{index}-{connection_generation}",
            ),
            label=f"bar-disposition-{first_sequence}-{index}-{connection_generation}",
        )
        for index in range(bar_count)
    )
    return (ack, *bars)


def live_authoritative_prefix(
    *,
    vintage: PhysicalVintage = PhysicalVintage.PROSPECTIVE_LIVE,
    connection_generation: int = 1,
    connection_id: str | None = None,
    first_sequence: int = 1,
    first_bar_open_ts: datetime = T0,
    bar_count: int = 2,
) -> tuple[HealthEvidenceItemV4, ...]:
    if bar_count < 1:
        raise ValueError("authoritative health fixture requires at least one bar")
    ack_and_bars = live_ack_and_bars(
        vintage=vintage,
        connection_generation=connection_generation,
        connection_id=connection_id,
        first_sequence=first_sequence,
        first_bar_open_ts=first_bar_open_ts,
        bar_count=bar_count,
    )
    status_sequence = first_sequence + bar_count + 1
    status_revision = complete_trading_status(
        published_at=(
            first_bar_open_ts + timedelta(minutes=bar_count, milliseconds=500)
        )
    )
    status = health_evidence(
        sequence=status_sequence,
        disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
        segment=capture_segment(
            adapter_policy_id=STATUS_ADAPTER_POLICY_ID,
            sequence=status_sequence,
            received_at=status_revision.available_at,
            vintage=vintage,
            connection_generation=connection_generation,
            connection_id=connection_id,
        ),
        revision=status_revision,
        label=f"status-{status_sequence}-{connection_generation}",
    )
    return (*ack_and_bars, status)


def transport_authority_for(
    *,
    scope: PhysicalScopeManifestV4,
    evidence: tuple[HealthEvidenceItemV4, ...],
) -> TransportAuthorityContextV4 | None:
    """Build explicit synthetic transport authority for pure-reducer tests."""

    primary = tuple(
        item
        for item in evidence
        if item.adapter_policy_id == scope.primary_adapter_policy_id
    )
    current = next(
        (
            item
            for item in reversed(primary)
            if item.observation_revision is not None
            and item.observation_revision.observation_kind is ObservationKind.BAR
        ),
        None,
    )
    if current is None:
        return None
    segment = current.capture_segment
    acknowledgements = tuple(
        item
        for item in primary
        if item.disposition_kind is MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
        and item.capture_segment.capture_partition_id == segment.capture_partition_id
        and item.capture_segment.collector_boot_id == segment.collector_boot_id
        and item.capture_segment.connection_generation == segment.connection_generation
        and item.capture_segment.connection_id == segment.connection_id
        and item.capture_segment.subscription_manifest_hash
        == segment.subscription_manifest_hash
    )
    if not acknowledgements:
        return None
    ack = acknowledgements[-1]
    session_receipt = ack.disposition_receipt_sequence - 3
    intent_receipt = ack.disposition_receipt_sequence - 2
    binding_receipt = ack.disposition_receipt_sequence + 1
    return TransportAuthorityContextV4(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        adapter_policy_id=scope.primary_adapter_policy_id,
        transport_subscription_policy_id=digest("transport-policy"),
        transport_session_id=segment.connection_id,
        transport_session_receipt_sequence=session_receipt,
        capture_partition_id=segment.capture_partition_id,
        collector_boot_id=segment.collector_boot_id,
        connection_generation=segment.connection_generation,
        subscription_manifest_hash=segment.subscription_manifest_hash,
        outbound_subscription_intent_id=digest(
            f"intent:{segment.connection_id}:{segment.connection_generation}"
        ),
        outbound_subscription_intent_receipt_sequence=intent_receipt,
        subscription_ack_binding_id=digest(f"binding:{ack.message_disposition_id}"),
        bound_message_disposition_id=ack.message_disposition_id,
        subscription_ack_binding_receipt_sequence=binding_receipt,
    )


def reduce_physical_health_v4(
    *,
    policy: PhysicalHealthPolicyV4,
    scope: PhysicalScopeManifestV4,
    evidence: object,
    covered_message_count: int,
    knowledge_cutoff_ts: datetime | str,
):
    items = tuple(evidence)  # type: ignore[arg-type]
    return reduce_physical_health_contract_v4(
        policy=policy,
        scope=scope,
        evidence=items,
        transport_authority=transport_authority_for(
            scope=scope,
            evidence=items,
        ),
        covered_message_count=covered_message_count,
        knowledge_cutoff_ts=knowledge_cutoff_ts,
    )


def transition(**overrides: object) -> PhysicalHealthTransitionV4:
    values: dict[str, object] = {
        "physical_scope_manifest_id": digest("scope"),
        "ledger_id": digest("ledger"),
        "physical_health_policy_id": REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4,
        "evidence_cutoff_id": digest("cutoff"),
        "cutoff_global_sequence": 10,
        "cutoff_receipt_hash": digest("cutoff-receipt"),
        "knowledge_cutoff_ts": T0 + timedelta(minutes=2),
        "tree_size": 2,
        "tree_root": digest("tree-root"),
        "parent_physical_health_transition_id": None,
        "prior_health": PrefixHealth.BOOTSTRAPPING,
        "current_health": PrefixHealth.HEALTHY,
        "health_reason_codes": (),
        "unresolved_blocker_count": 0,
        "unresolved_blocker_root": rfc9162_empty_root().hex(),
        "recovery_consecutive_completed_bars": (V4_RECOVERY_CONSECUTIVE_COMPLETED_BARS),
        "current_required_status_revision_id": digest("status"),
        "current_transport_session_id": digest("transport-session"),
        "current_outbound_subscription_intent_id": digest("subscription-intent"),
        "current_subscription_ack_binding_id": digest("ack-binding"),
        "event_time_watermark": T0 + timedelta(minutes=2),
        "health_valid_until": T0 + timedelta(minutes=3, seconds=30),
        "evaluated_at": T0 + timedelta(minutes=2),
    }
    values.update(overrides)
    return PhysicalHealthTransitionV4(**values)


def test_reviewed_health_policy_is_self_hashed_and_round_trips() -> None:
    policy = REVIEWED_PHYSICAL_HEALTH_POLICY_V4
    payload = policy.as_dict()

    assert policy == PhysicalHealthPolicyV4()
    assert policy.physical_health_policy_id == (REVIEWED_PHYSICAL_HEALTH_POLICY_ID_V4)
    assert payload["schema_version"] == PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION
    assert PhysicalHealthPolicyV4.from_mapping(payload) == policy
    assert policy.interval_seconds == 60
    assert policy.primary_freshness_seconds == 90
    assert policy.status_freshness_seconds == 90
    assert policy.max_clock_uncertainty_milliseconds == 250
    assert policy.recovery_consecutive_completed_bars == 2
    assert policy.required_vintage is PhysicalVintage.PROSPECTIVE_LIVE
    assert policy.bound_subscription_ack_required is True
    assert policy.required_status_value == "Trading"
    assert policy.required_contract_type_value == "LinearPerpetual"


def test_health_precedence_and_blocker_recovery_matrix_are_exact() -> None:
    assert REVIEWED_PHYSICAL_HEALTH_POLICY_V4.state_precedence == (
        V4_HEALTH_STATE_PRECEDENCE
    )
    assert REVIEWED_PHYSICAL_HEALTH_POLICY_V4.blocker_recovery_rules == (
        V4_BLOCKER_RECOVERY_RULES
    )
    matrix = {
        rule.disposition_kind: rule.recovery_mode for rule in V4_BLOCKER_RECOVERY_RULES
    }
    assert set(matrix) == {
        MessageDispositionKind.PROVIDER_ERROR,
        MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT,
        MessageDispositionKind.MALFORMED_PAYLOAD,
        MessageDispositionKind.UNSUPPORTED_SCHEMA,
        MessageDispositionKind.OUT_OF_SCOPE,
        MessageDispositionKind.RECEIPT_LAG_REJECTED,
        MessageDispositionKind.CLOCK_ORDERING_REJECTED,
        MessageDispositionKind.CONTENT_CONFLICT,
    }
    assert matrix[MessageDispositionKind.CONTENT_CONFLICT] is (
        BlockerRecoveryModeV4.SCOPE_ROTATION_ONLY
    )
    assert matrix[MessageDispositionKind.UNSUPPORTED_SCHEMA] is (
        BlockerRecoveryModeV4.SCOPE_ROTATION_ONLY
    )

    with pytest.raises(CanonicalizationError, match="precedence"):
        replace(
            REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
            state_precedence=tuple(reversed(V4_HEALTH_STATE_PRECEDENCE)),
        )
    with pytest.raises(CanonicalizationError, match="recovery matrix"):
        replace(
            REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
            blocker_recovery_rules=tuple(reversed(V4_BLOCKER_RECOVERY_RULES)),
        )
    with pytest.raises(CanonicalizationError, match="prospective-live"):
        replace(
            REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
            required_vintage=PhysicalVintage.REPLAY,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("interval_seconds", 61),
        ("primary_freshness_seconds", 91),
        ("status_freshness_seconds", 91),
        ("max_clock_uncertainty_milliseconds", 251),
        ("recovery_consecutive_completed_bars", 1),
        ("bound_subscription_ack_required", False),
        ("required_status_value", "Halted"),
        ("required_contract_type_value", "InversePerpetual"),
    ],
)
def test_unreviewed_health_policy_parameters_fail_closed(
    field: str, value: object
) -> None:
    with pytest.raises(CanonicalizationError):
        replace(REVIEWED_PHYSICAL_HEALTH_POLICY_V4, **{field: value})


def test_health_blocker_root_is_an_independent_ordered_rfc9162_commitment() -> None:
    blocker_ids = tuple(digest(f"blocker-{index}") for index in range(3))
    leaves = tuple(
        canonical_json_bytes(
            {
                "domain": PHYSICAL_HEALTH_BLOCKER_LEAF_DOMAIN_V4,
                "message_disposition_id": blocker_id,
                "ordinal": ordinal,
            }
        )
        for ordinal, blocker_id in enumerate(blocker_ids)
    )

    assert (
        health_blocker_leaf_input_v4(ordinal=0, message_disposition_id=blocker_ids[0])
        == leaves[0]
    )
    assert health_blocker_root_v4(blocker_ids) == rfc9162_tree_hash(leaves).hex()
    assert health_blocker_root_v4(blocker_ids) != health_blocker_root_v4(
        blocker_ids[::-1]
    )
    assert health_blocker_root_v4(()) == rfc9162_empty_root().hex()


def test_health_blocker_root_zero_one_4096_4097_and_duplicate_boundaries() -> None:
    blocker_ids = tuple(
        digest(f"blocker-{index}") for index in range(V4_MAX_HEALTH_BLOCKERS + 1)
    )

    assert health_blocker_root_v4(()) == rfc9162_empty_root().hex()
    assert health_blocker_root_v4(blocker_ids[:1]) != rfc9162_empty_root().hex()
    assert (
        health_blocker_root_v4(blocker_ids[:V4_MAX_HEALTH_BLOCKERS])
        != rfc9162_empty_root().hex()
    )
    with pytest.raises(CanonicalizationError, match="exceeds 4096"):
        health_blocker_root_v4(blocker_ids)
    with pytest.raises(CanonicalizationError, match="duplicate"):
        health_blocker_root_v4((blocker_ids[0], blocker_ids[0]))


def test_health_transition_healthy_bootstrap_and_recovering_round_trip() -> None:
    healthy = transition()
    bootstrapping = transition(
        evidence_cutoff_id=digest("empty-cutoff"),
        cutoff_global_sequence=1,
        cutoff_receipt_hash=digest("empty-receipt"),
        knowledge_cutoff_ts=T0,
        tree_size=0,
        tree_root=rfc9162_empty_root().hex(),
        current_health=PrefixHealth.BOOTSTRAPPING,
        health_reason_codes=("EMPTY_EVIDENCE_PREFIX",),
        recovery_consecutive_completed_bars=0,
        current_required_status_revision_id=None,
        event_time_watermark=None,
        health_valid_until=T0 + timedelta(seconds=30),
        evaluated_at=T0,
    )
    recovering = transition(
        parent_physical_health_transition_id=digest("parent"),
        prior_health=PrefixHealth.DISCONNECTED,
        current_health=PrefixHealth.RECOVERING,
        health_reason_codes=("RECOVERY_STREAK_INCOMPLETE",),
        recovery_consecutive_completed_bars=1,
    )

    for item in (healthy, bootstrapping, recovering):
        assert PhysicalHealthTransitionV4.from_mapping(item.as_dict()) == item
    assert healthy.current_health is PrefixHealth.HEALTHY
    assert bootstrapping.tree_root == rfc9162_empty_root().hex()
    assert recovering.recovery_consecutive_completed_bars == 1


def test_health_transition_shape_and_timestamp_attacks_fail_closed() -> None:
    blocker_id = digest("blocker")
    blocker_root = health_blocker_root_v4((blocker_id,))

    with pytest.raises(CanonicalizationError, match="HEALTHY transition"):
        transition(health_reason_codes=("FORGED_REASON",))
    with pytest.raises(CanonicalizationError, match="non-healthy requires reasons"):
        transition(
            current_health=PrefixHealth.STALE,
            health_reason_codes=(),
            recovery_consecutive_completed_bars=0,
        )
    with pytest.raises(CanonicalizationError, match="count and RFC9162 root"):
        transition(
            current_health=PrefixHealth.DISCONNECTED,
            health_reason_codes=("UNRESOLVED_PROVIDER_ERROR",),
            unresolved_blocker_count=1,
            unresolved_blocker_root=rfc9162_empty_root().hex(),
            recovery_consecutive_completed_bars=0,
        )
    with pytest.raises(CanonicalizationError, match="unblocked evidence"):
        transition(
            unresolved_blocker_count=1,
            unresolved_blocker_root=blocker_root,
        )
    with pytest.raises(CanonicalizationError, match="complete recovery streak"):
        transition(recovery_consecutive_completed_bars=1)
    with pytest.raises(CanonicalizationError, match="evaluated before"):
        transition(evaluated_at=T0 + timedelta(minutes=1, seconds=59))
    with pytest.raises(CanonicalizationError, match="follow evaluated_at"):
        transition(health_valid_until=T0 + timedelta(minutes=2))
    with pytest.raises(CanonicalizationError, match="cannot follow"):
        transition(event_time_watermark=T0 + timedelta(minutes=2, microseconds=1))


def test_health_transition_successor_enforces_chain_and_monotonicity() -> None:
    parent = transition()
    successor = transition(
        evidence_cutoff_id=digest("next-cutoff"),
        cutoff_global_sequence=11,
        cutoff_receipt_hash=digest("next-receipt"),
        knowledge_cutoff_ts=T0 + timedelta(minutes=3),
        tree_size=3,
        tree_root=digest("next-tree"),
        parent_physical_health_transition_id=parent.physical_health_transition_id,
        prior_health=PrefixHealth.HEALTHY,
        event_time_watermark=T0 + timedelta(minutes=3),
        evaluated_at=T0 + timedelta(minutes=3),
        health_valid_until=T0 + timedelta(minutes=4, seconds=30),
    )
    validate_health_transition_successor_v4(parent, successor)

    with pytest.raises(CanonicalizationError, match="parent identity"):
        validate_health_transition_successor_v4(
            parent,
            replace(
                successor,
                parent_physical_health_transition_id=digest("wrong-parent"),
            ),
        )
    with pytest.raises(CanonicalizationError, match="prior state"):
        validate_health_transition_successor_v4(
            parent,
            replace(successor, prior_health=PrefixHealth.BOOTSTRAPPING),
        )
    with pytest.raises(CanonicalizationError, match="sequence regresses"):
        validate_health_transition_successor_v4(
            parent,
            replace(successor, cutoff_global_sequence=9),
        )


def test_health_policy_and_transition_identity_tampering_is_rejected() -> None:
    policy_payload = REVIEWED_PHYSICAL_HEALTH_POLICY_V4.as_dict()
    policy_payload["physical_health_policy_id"] = digest("tampered-policy")
    with pytest.raises(CanonicalizationError, match="canonical content"):
        PhysicalHealthPolicyV4.from_mapping(policy_payload)

    item = transition()
    transition_payload = item.as_dict()
    transition_payload["physical_health_transition_id"] = digest("tampered-transition")
    with pytest.raises(CanonicalizationError, match="canonical content"):
        PhysicalHealthTransitionV4.from_mapping(transition_payload)


def test_health_reducer_is_deterministic_for_the_same_causal_prefix() -> None:
    scope = health_scope()
    evidence = live_authoritative_prefix()
    knowledge = T0 + timedelta(minutes=2, seconds=1)

    first = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=knowledge,
    )
    replayed = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=list(evidence),
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=knowledge.isoformat(),
    )

    assert first == replayed
    assert first.health is PrefixHealth.HEALTHY
    assert first.reason_codes == ()
    assert first.vintage is PhysicalVintage.PROSPECTIVE_LIVE


def test_health_reducer_empty_prefix_is_exact_bootstrap_state() -> None:
    knowledge = T0 + timedelta(seconds=10)

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=(),
        covered_message_count=0,
        knowledge_cutoff_ts=knowledge,
    )

    assert result.health is PrefixHealth.BOOTSTRAPPING
    assert result.reason_codes == ("EMPTY_EVIDENCE_PREFIX",)
    assert result.unresolved_blocker_ids == ()
    assert result.recovery_consecutive_completed_bars == 0
    assert result.current_required_status_revision_id is None
    assert result.event_time_watermark is None
    assert result.health_valid_until == knowledge + timedelta(microseconds=1)
    assert result.vintage is PhysicalVintage.REPLAY


def test_health_reducer_replay_prefix_can_never_be_healthy() -> None:
    evidence = live_authoritative_prefix(vintage=PhysicalVintage.REPLAY)

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.SCHEMA_UNSUPPORTED
    assert result.reason_codes == ("NON_PROSPECTIVE_OR_MIXED_VINTAGE",)
    assert result.recovery_consecutive_completed_bars == 0
    assert result.vintage is PhysicalVintage.REPLAY


def test_health_reducer_rejects_replay_status_in_otherwise_live_prefix() -> None:
    evidence = live_authoritative_prefix()
    status = evidence[-1]
    replay_status = replace(
        status,
        message_disposition_id=digest("replay-status-disposition"),
        capture_segment=replace(
            status.capture_segment,
            vintage=PhysicalVintage.REPLAY,
        ),
    )

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=(*evidence[:-1], replay_status),
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.SCHEMA_UNSUPPORTED
    assert result.reason_codes == ("NON_PROSPECTIVE_OR_MIXED_VINTAGE",)
    assert result.vintage is PhysicalVintage.REPLAY


def test_health_reducer_missing_current_connection_ack_is_disconnected() -> None:
    with_ack = live_authoritative_prefix()
    evidence = tuple(
        replace(
            item,
            scope_message_sequence=index,
            disposition_receipt_sequence=index,
            message_disposition_id=digest(f"no-ack-bar-{index}"),
            observation_admission_receipt_sequence=index,
        )
        for index, item in enumerate(with_ack[1:], start=1)
    )

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.DISCONNECTED
    assert result.reason_codes == ("CURRENT_TRANSPORT_SESSION_ATTESTATION_MISSING",)
    assert result.recovery_consecutive_completed_bars == 0


def test_raw_subscription_ack_without_transport_binding_is_not_authority() -> None:
    scope = health_scope()
    evidence = live_authoritative_prefix()

    result = reduce_physical_health_contract_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        transport_authority=None,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert evidence[0].disposition_kind is (
        MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
    )
    assert result.health is PrefixHealth.DISCONNECTED
    assert result.reason_codes == ("CURRENT_TRANSPORT_SESSION_ATTESTATION_MISSING",)
    assert result.current_subscription_ack_binding_id is None


def test_only_bars_admitted_after_ack_binding_enter_recovery_suffix() -> None:
    scope = health_scope()
    evidence = live_authoritative_prefix()
    authority = transport_authority_for(scope=scope, evidence=evidence)
    assert authority is not None
    after_first_bar = replace(
        authority,
        subscription_ack_binding_receipt_sequence=25,
    )

    result = reduce_physical_health_contract_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        transport_authority=after_first_bar,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.RECOVERING
    assert result.reason_codes == ("RECOVERY_STREAK_INCOMPLETE",)
    assert result.recovery_consecutive_completed_bars == 1


def test_terminal_transport_event_immediately_invalidates_bound_health() -> None:
    scope = health_scope()
    evidence = live_authoritative_prefix()
    authority = transport_authority_for(scope=scope, evidence=evidence)
    assert authority is not None
    terminated = replace(
        authority,
        transport_session_termination_id=digest("transport-termination"),
        transport_session_termination_receipt_sequence=35,
    )

    result = reduce_physical_health_contract_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        transport_authority=terminated,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.DISCONNECTED
    assert result.reason_codes == (
        "CURRENT_TRANSPORT_SESSION_TERMINATED",
        "RECOVERY_STREAK_INCOMPLETE",
    )
    assert result.recovery_consecutive_completed_bars == 0


def test_health_reducer_does_not_mix_ack_across_capture_partitions() -> None:
    evidence = live_authoritative_prefix()
    foreign_ack = replace(
        evidence[0],
        capture_segment=replace(
            evidence[0].capture_segment,
            collector_instance_id="foreign-health-test-collector",
        ),
    )

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=(foreign_ack, *evidence[1:]),
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert (
        foreign_ack.capture_segment.connection_id
        == evidence[1].capture_segment.connection_id
    )
    assert (
        foreign_ack.capture_segment.capture_partition_id
        != evidence[1].capture_segment.capture_partition_id
    )
    assert result.health is PrefixHealth.DISCONNECTED
    assert result.reason_codes == ("CURRENT_TRANSPORT_SESSION_ATTESTATION_MISSING",)
    assert result.recovery_consecutive_completed_bars == 0


def test_health_reducer_requires_two_contiguous_post_ack_bars() -> None:
    one_bar = live_authoritative_prefix(bar_count=1)
    recovering = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=one_bar,
        covered_message_count=len(one_bar),
        knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
    )

    two_bars = live_authoritative_prefix(bar_count=2)
    healthy = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=two_bars,
        covered_message_count=len(two_bars),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert recovering.health is PrefixHealth.RECOVERING
    assert recovering.reason_codes == ("RECOVERY_STREAK_INCOMPLETE",)
    assert recovering.recovery_consecutive_completed_bars == 1
    assert healthy.health is PrefixHealth.HEALTHY
    assert healthy.reason_codes == ()
    assert healthy.recovery_consecutive_completed_bars == 2
    assert healthy.event_time_watermark == T0 + timedelta(minutes=2)


def test_health_reducer_time_tick_expires_an_unchanged_healthy_prefix() -> None:
    evidence = live_authoritative_prefix()
    scope = health_scope()
    initially_healthy = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )
    expired = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=scope,
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=3, seconds=30),
    )

    assert initially_healthy.health is PrefixHealth.HEALTHY
    assert initially_healthy.health_valid_until == T0 + timedelta(minutes=3, seconds=30)
    assert expired.health is PrefixHealth.STALE
    assert expired.reason_codes == ("PRIMARY_BAR_STALE",)
    assert expired.recovery_consecutive_completed_bars == 0


def test_health_reducer_requires_fresh_unambiguous_trading_status() -> None:
    bars_only = live_ack_and_bars()
    blocked = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(requires_status=True),
        evidence=bars_only,
        covered_message_count=len(bars_only),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    complete_evidence = live_authoritative_prefix()
    status_revision = complete_evidence[-1].observation_revision
    assert status_revision is not None
    healthy = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(requires_status=True),
        evidence=complete_evidence,
        covered_message_count=len(complete_evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert blocked.health is PrefixHealth.STATUS_BLOCKED
    assert blocked.reason_codes == ("REQUIRED_STATUS_MISSING_OR_AMBIGUOUS",)
    assert blocked.current_required_status_revision_id is None
    assert healthy.health is PrefixHealth.HEALTHY
    assert healthy.current_required_status_revision_id == (
        status_revision.observation_revision_id
    )


def test_health_reducer_resolves_transient_blocker_only_after_new_authority() -> None:
    blocker = health_evidence(
        sequence=1,
        disposition_kind=MessageDispositionKind.PROVIDER_ERROR,
        segment=capture_segment(
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            connection_generation=1,
            connection_id=digest("connection-1"),
        ),
        label="provider-error-blocker",
    )
    recovered_connection = live_authoritative_prefix(
        connection_generation=2,
        connection_id=digest("connection-2"),
        first_sequence=2,
    )
    evidence = (blocker, *recovered_connection)

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.HEALTHY
    assert result.reason_codes == ()
    assert result.unresolved_blocker_ids == ()
    assert result.recovery_consecutive_completed_bars == 2


def test_health_reducer_never_resolves_scope_rotation_only_blocker() -> None:
    blocker = health_evidence(
        sequence=1,
        disposition_kind=MessageDispositionKind.CONTENT_CONFLICT,
        segment=capture_segment(
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            connection_generation=1,
            connection_id=digest("connection-1"),
        ),
        label="terminal-content-conflict",
    )
    replacement_connection = live_authoritative_prefix(
        connection_generation=2,
        connection_id=digest("connection-2"),
        first_sequence=2,
    )
    evidence = (blocker, *replacement_connection)

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.INTEGRITY_CONFLICT
    assert result.reason_codes == ("UNRESOLVED_CONTENT_CONFLICT",)
    assert result.unresolved_blocker_ids == (blocker.message_disposition_id,)
    assert result.recovery_consecutive_completed_bars == 0


def test_health_reducer_rejects_an_active_revision_fork() -> None:
    ack = live_ack_and_bars(bar_count=0)[0]
    root = complete_bar(bar_open_ts=T0, label="fork-root")
    first_child = replace(
        root,
        observation_derivation_id=digest("fork-first-child"),
        field_values=("100", "102", "99", "100.5", "10"),
        parent_observation_revision_id=root.observation_revision_id,
        correction_reason="provider-correction-a",
    )
    second_child = replace(
        root,
        observation_derivation_id=digest("fork-second-child"),
        field_values=("100", "102", "99", "100.75", "10"),
        parent_observation_revision_id=root.observation_revision_id,
        correction_reason="provider-correction-b",
    )
    revisions = (root, first_child, second_child)
    fork_items = tuple(
        health_evidence(
            sequence=index,
            disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
            segment=capture_segment(
                sequence=index,
                received_at=revision.available_at + timedelta(milliseconds=index),
            ),
            revision=revision,
            label=f"fork-revision-{index}",
        )
        for index, revision in enumerate(revisions, start=2)
    )
    next_bar = complete_bar(
        bar_open_ts=T0 + timedelta(minutes=1), label="post-fork-bar"
    )
    next_bar_item = health_evidence(
        sequence=5,
        disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
        segment=capture_segment(
            sequence=5,
            received_at=next_bar.available_at + timedelta(milliseconds=5),
        ),
        revision=next_bar,
        label="post-fork-bar",
    )
    status_revision = complete_trading_status(
        published_at=T0 + timedelta(minutes=2, milliseconds=500)
    )
    status_item = health_evidence(
        sequence=6,
        disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
        segment=capture_segment(
            adapter_policy_id=STATUS_ADAPTER_POLICY_ID,
            sequence=6,
            received_at=status_revision.available_at,
        ),
        revision=status_revision,
        label="post-fork-status",
    )
    evidence = (ack, *fork_items, next_bar_item, status_item)

    result = reduce_physical_health_v4(
        policy=REVIEWED_PHYSICAL_HEALTH_POLICY_V4,
        scope=health_scope(),
        evidence=evidence,
        covered_message_count=len(evidence),
        knowledge_cutoff_ts=T0 + timedelta(minutes=2, seconds=1),
    )

    assert result.health is PrefixHealth.INTEGRITY_CONFLICT
    assert "ACTIVE_REVISION_FORK" in result.reason_codes
    assert result.recovery_consecutive_completed_bars == 0

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
from riskyieldmm.trading.contracts import (
    InformationDependencyV3,
    InformationSetV3,
    VintageClass,
)
from riskyieldmm.trading.evidence import (
    CardinalityScope,
    DependencySelectionMode,
    EvidenceKind,
    FeatureDependencySlotV3,
    MissingInputPolicy,
    SourceBundleMemberV3,
    SourceRole,
)
from riskyieldmm.trading.physical_market_data import (
    BYBIT_V5_FEED_HEALTH_POLICY_ID,
    BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH,
    BYBIT_V5_INSTRUMENT_INFO_PARSER_RELEASE_HASH,
    BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION,
    BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
    BYBIT_V5_KLINE_PARSER_RELEASE_HASH,
    BYBIT_V5_KLINE_PARSER_VERSION,
    MAX_CAPTURE_CANONICAL_BYTES,
    MAX_PREFIX_CANONICAL_BYTES,
    CaptureSegmentV3,
    CompletionBasis,
    CompletionState,
    ContinuityPolicy,
    DependencySelectionProofV3,
    EvidencePrefixV3,
    MessageDispositionKind,
    ObservationDerivationV3,
    ObservationRevisionV3,
    ObservationSelectionPolicyV3,
    PhysicalEvidenceGateV3,
    PhysicalGateVerdict,
    PhysicalVintage,
    PrefixHealth,
    ProviderAdapterKind,
    ProviderAdapterPolicyV3,
    ProviderDataUse,
    ProviderMessageDispositionV3,
    ProviderMessageEnvelopeV3,
    ProviderMessageTypeV3,
    ProviderTransport,
    SelectionAnchor,
    SelectionStatus,
    build_bybit_v5_message_disposition,
    build_physical_evidence_gate_v3,
    normalize_bybit_v5_instrument_info,
    normalize_bybit_v5_kline_message,
    observation_value_digest,
    select_observation_revisions_v3,
    validate_capture_segment_lineage,
    validate_dependency_against_observation,
    validate_evidence_prefix_graph,
    validate_observation_revision_lineage,
    validate_raw_normalization_v3,
    validate_source_member_physical_prefix,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 14, 9, 0, tzinfo=UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def epoch_milliseconds(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def bar_policy(*, requires_status: bool = True) -> ProviderAdapterPolicyV3:
    return ProviderAdapterPolicyV3(
        policy_name="bybit-linear-btcusdt-confirmed-1m",
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        adapter_kind=ProviderAdapterKind.BYBIT_V5_PUBLIC_KLINE,
        transport=ProviderTransport.WEBSOCKET,
        data_use=(
            ProviderDataUse.TRADING_AUTHORITY
            if requires_status
            else ProviderDataUse.RESEARCH_ONLY
        ),
        authoritative_endpoint="wss://stream.bybit.com/v5/public/linear",
        channel_or_schema="kline.1.BTCUSDT",
        source_id="bybit.linear.BTCUSDT.1m.confirmed",
        asset_id="BTC",
        concrete_contract_id="BTCUSDT.LINEAR.PERP",
        provider_native_key="BTCUSDT",
        timeframe_id="1m",
        base_interval_seconds=60,
        source_schema_id=digest("bybit-confirmed-ohlcv-schema"),
        parser_code_hash=BYBIT_V5_KLINE_PARSER_RELEASE_HASH,
        parser_version=BYBIT_V5_KLINE_PARSER_VERSION,
        message_classifier_release_hash=BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
        feed_health_policy_id=BYBIT_V5_FEED_HEALTH_POLICY_ID,
        availability_policy_id=digest("ledger-first-receipt-policy"),
        revision_policy_id=digest("append-only-revision-policy"),
        calendar_manifest_id=digest("bybit-247-calendar"),
        completion_basis=CompletionBasis.PROVIDER_FINAL_FLAG,
        max_receipt_lag_milliseconds=2_000,
        stale_after_seconds=90,
        max_clock_uncertainty_milliseconds=250,
        requires_instrument_status=requires_status,
        frozen_at=T0 - timedelta(hours=1),
    )


def status_policy() -> ProviderAdapterPolicyV3:
    return ProviderAdapterPolicyV3(
        policy_name="bybit-linear-btcusdt-instrument-status",
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        adapter_kind=ProviderAdapterKind.BYBIT_V5_INSTRUMENT_INFO,
        transport=ProviderTransport.HTTP_REST,
        data_use=ProviderDataUse.RECONCILIATION_ONLY,
        authoritative_endpoint="https://api.bybit.com/v5/market/instruments-info",
        channel_or_schema="category=linear&symbol=BTCUSDT",
        source_id="bybit.linear.BTCUSDT.instrument-status",
        asset_id="BTC",
        concrete_contract_id="BTCUSDT.LINEAR.PERP",
        provider_native_key="BTCUSDT",
        timeframe_id="1m",
        base_interval_seconds=60,
        source_schema_id=digest("bybit-instrument-schema"),
        parser_code_hash=BYBIT_V5_INSTRUMENT_INFO_PARSER_RELEASE_HASH,
        parser_version=BYBIT_V5_INSTRUMENT_INFO_PARSER_VERSION,
        message_classifier_release_hash=(
            BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH
        ),
        feed_health_policy_id=BYBIT_V5_FEED_HEALTH_POLICY_ID,
        availability_policy_id=digest("ledger-first-receipt-policy"),
        revision_policy_id=digest("append-only-revision-policy"),
        calendar_manifest_id=digest("bybit-247-calendar"),
        completion_basis=CompletionBasis.PROVIDER_FINAL_RECORD,
        max_receipt_lag_milliseconds=2_000,
        stale_after_seconds=90,
        max_clock_uncertainty_milliseconds=250,
        requires_instrument_status=False,
        frozen_at=T0 - timedelta(hours=1),
    )


def source_member_placeholder(policy: ProviderAdapterPolicyV3) -> SourceBundleMemberV3:
    return SourceBundleMemberV3(
        source_id=policy.source_id,
        source_role=SourceRole.DECISION_INPUT,
        asset_id=policy.asset_id,
        venue_id=policy.venue_id,
        contract_id=policy.concrete_contract_id,
        timeframe_id=policy.timeframe_id,
        source_schema_id=policy.source_schema_id,
        source_field_ids=("open", "high", "low", "close", "volume", "turnover"),
        availability_policy_id=policy.availability_policy_id,
        revision_policy_id=policy.revision_policy_id,
        calendar_manifest_id=policy.calendar_manifest_id,
        semantic_content_root=digest("physical-prefix-placeholder"),
        artifact_hash=digest("raw-root-placeholder"),
        row_count=1,
        event_start_ts=T0 + timedelta(seconds=55),
        event_end_ts=T0 + timedelta(seconds=55),
        knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
    )


def kline_bytes(
    *,
    confirm: bool = True,
    close: str = "100.5",
    topic: str = "kline.1.BTCUSDT",
    bar_start: datetime = T0,
) -> bytes:
    payload = {
        "topic": topic,
        "type": "snapshot",
        "ts": epoch_milliseconds(bar_start + timedelta(minutes=1, milliseconds=100)),
        "data": [
            {
                "start": epoch_milliseconds(bar_start),
                "end": epoch_milliseconds(bar_start + timedelta(minutes=1)) - 1,
                "interval": "1",
                "open": "100",
                "close": close,
                "high": "101",
                "low": "99",
                "volume": "12.25",
                "turnover": "1230.5",
                "confirm": confirm,
                "timestamp": epoch_milliseconds(bar_start + timedelta(seconds=55)),
            }
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def status_bytes(*, status: str = "Trading") -> bytes:
    payload = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "category": "linear",
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "contractType": "LinearPerpetual",
                    "status": status,
                }
            ],
            "nextPageCursor": "",
        },
        "retExtInfo": {},
        "time": epoch_milliseconds(T0 + timedelta(seconds=30)),
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def segment(
    policy: ProviderAdapterPolicyV3,
    raw: bytes,
    *,
    sequence: int = 1,
    received_at: datetime | None = None,
    parent: CaptureSegmentV3 | None = None,
    connection_generation: int = 1,
    connection_id: str = "conn-1",
    vintage: PhysicalVintage = PhysicalVintage.PROSPECTIVE_LIVE,
    message_type: ProviderMessageTypeV3 = ProviderMessageTypeV3.TEXT,
) -> CaptureSegmentV3:
    received = received_at or T0 + timedelta(minutes=1, milliseconds=200)
    envelope = ProviderMessageEnvelopeV3.from_raw(
        collector_sequence=sequence,
        collector_received_wall_ts=received,
        collector_received_monotonic_ns=sequence * 1_000_000_000,
        message_type=message_type,
        raw_payload=raw,
    )
    return CaptureSegmentV3(
        adapter_policy_id=policy.adapter_policy_id,
        provider_native_key=policy.provider_native_key,
        collector_instance_id="collector-a",
        collector_boot_id="boot-a",
        connection_id=connection_id,
        connection_generation=connection_generation,
        subscription_manifest_hash=digest("subscription"),
        vintage=vintage,
        envelopes=(envelope,),
        closed_at=received + timedelta(milliseconds=50),
        clock_uncertainty_milliseconds=20,
        parent_capture_segment_id=(
            None if parent is None else parent.capture_segment_id
        ),
    )


def normalized_bar(
    policy: ProviderAdapterPolicyV3,
    member: SourceBundleMemberV3,
    *,
    confirm: bool = True,
    close: str = "100.5",
    capture: CaptureSegmentV3 | None = None,
    bar_start: datetime = T0,
) -> tuple[CaptureSegmentV3, ObservationDerivationV3, ObservationRevisionV3]:
    capture = capture or segment(
        policy,
        kline_bytes(confirm=confirm, close=close, bar_start=bar_start),
        received_at=bar_start + timedelta(minutes=1, milliseconds=200),
    )
    durable = bar_start + timedelta(minutes=1, milliseconds=400)
    derivation, revision = normalize_bybit_v5_kline_message(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        durably_appended_ts=durable,
        normalized_at=durable + timedelta(milliseconds=100),
        available_at=durable + timedelta(milliseconds=200),
    )
    return capture, derivation, revision


def normalized_status(
    policy: ProviderAdapterPolicyV3,
    member: SourceBundleMemberV3,
    *,
    status: str = "Trading",
) -> tuple[CaptureSegmentV3, ObservationDerivationV3, ObservationRevisionV3]:
    capture = segment(
        policy,
        status_bytes(status=status),
        received_at=T0 + timedelta(seconds=30, milliseconds=100),
    )
    durable = T0 + timedelta(seconds=30, milliseconds=200)
    derivation, revision = normalize_bybit_v5_instrument_info(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        durably_appended_ts=durable,
        normalized_at=durable + timedelta(milliseconds=50),
        available_at=durable + timedelta(milliseconds=100),
    )
    return capture, derivation, revision


def classify_message(
    policy: ProviderAdapterPolicyV3,
    capture: CaptureSegmentV3,
    member: SourceBundleMemberV3,
    *,
    durable: datetime | None = None,
    normalized_at: datetime | None = None,
    available_at: datetime | None = None,
    classified_at: datetime | None = None,
    prior: tuple[tuple[CaptureSegmentV3, ProviderMessageDispositionV3], ...] = (),
):
    durable = durable or (
        capture.envelopes[0].collector_received_wall_ts + timedelta(milliseconds=200)
    )
    normalized_at = normalized_at or durable + timedelta(milliseconds=50)
    available_at = available_at or durable + timedelta(milliseconds=100)
    classified_at = classified_at or durable + timedelta(milliseconds=150)
    return build_bybit_v5_message_disposition(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        durably_appended_ts=durable,
        normalized_at=normalized_at,
        available_at=available_at,
        classified_at=classified_at,
        prior_normalized_occurrences=prior,
    )


def healthy_prefix(
    policy: ProviderAdapterPolicyV3,
    member: SourceBundleMemberV3,
    bar_segment: CaptureSegmentV3,
    status_segment: CaptureSegmentV3 | None,
    bar: ObservationRevisionV3,
    status: ObservationRevisionV3 | None,
    bar_disposition: ProviderMessageDispositionV3,
    status_disposition: ProviderMessageDispositionV3 | None,
) -> EvidencePrefixV3:
    revisions = (bar,) if status is None else (bar, status)
    dispositions = (
        (bar_disposition,)
        if status_disposition is None
        else (bar_disposition, status_disposition)
    )
    return EvidencePrefixV3(
        adapter_policy_id=policy.adapter_policy_id,
        supporting_adapter_policy_ids=(
            () if status is None else (status.adapter_policy_id,)
        ),
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        ledger_id=digest("physical-ledger"),
        cutoff_global_sequence=7,
        cutoff_receipt_hash=digest("physical-ledger-prefix-receipt"),
        knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
        capture_segment_ids=(
            (bar_segment.capture_segment_id,)
            if status_segment is None
            else (
                bar_segment.capture_segment_id,
                status_segment.capture_segment_id,
            )
        ),
        message_disposition_ids=tuple(
            item.provider_message_disposition_id for item in dispositions
        ),
        observation_revision_ids=tuple(
            item.observation_revision_id for item in revisions
        ),
        active_observation_revision_ids=tuple(
            item.observation_revision_id for item in revisions
        ),
        status_observation_revision_ids=(
            () if status is None else (status.observation_revision_id,)
        ),
        unresolved_disposition_ids=(),
        vintage=PhysicalVintage.PROSPECTIVE_LIVE,
        health=PrefixHealth.HEALTHY,
        health_reason_codes=(),
        event_time_watermark=T0 + timedelta(minutes=1),
        health_valid_until=T0 + timedelta(minutes=2),
        assembled_at=T0 + timedelta(minutes=1, seconds=1),
    )


def exact_slot(member: SourceBundleMemberV3) -> FeatureDependencySlotV3:
    return FeatureDependencySlotV3(
        dependency_slot_name="exact-completed-close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.EXACT_EVENT,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=60,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=member.availability_policy_id,
        revision_policy_id=member.revision_policy_id,
    )


def exact_policy(slot: FeatureDependencySlotV3) -> ObservationSelectionPolicyV3:
    return ObservationSelectionPolicyV3(
        dependency_slot_id=slot.dependency_slot_id,
        selection_mode=DependencySelectionMode.EXACT_EVENT,
        anchor=SelectionAnchor.CUTOFF_COMPLETED_INTERVAL,
        interval_seconds=60,
        anchor_lag_intervals=0,
        requested_count=1,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        maximum_age_seconds=slot.maximum_age_seconds,
        maximum_prefix_age_seconds=90,
        tie_break_policy="AVAILABLE_AT_THEN_REVISION_ID",
        frozen_at=T0 - timedelta(minutes=1),
    )


def physical_graph():
    price_policy = bar_policy()
    instrument_policy = status_policy()
    placeholder = source_member_placeholder(price_policy)
    bar_segment, bar_derivation, bar = normalized_bar(price_policy, placeholder)
    status_segment, status_derivation, status = normalized_status(
        instrument_policy, placeholder
    )
    bar_disposition, classified_bar_derivation, classified_bar = classify_message(
        price_policy,
        bar_segment,
        placeholder,
        durable=bar.durably_appended_ts,
        normalized_at=bar.normalized_at,
        available_at=bar.available_at,
        classified_at=bar.available_at + timedelta(milliseconds=50),
    )
    status_disposition, classified_status_derivation, classified_status = (
        classify_message(
            instrument_policy,
            status_segment,
            placeholder,
            durable=status.durably_appended_ts,
            normalized_at=status.normalized_at,
            available_at=status.available_at,
            classified_at=status.available_at + timedelta(milliseconds=50),
        )
    )
    assert (classified_bar_derivation, classified_bar) == (bar_derivation, bar)
    assert (classified_status_derivation, classified_status) == (
        status_derivation,
        status,
    )
    prefix = healthy_prefix(
        price_policy,
        placeholder,
        bar_segment,
        status_segment,
        bar,
        status,
        bar_disposition,
        status_disposition,
    )
    revisions = {
        bar.observation_revision_id: bar,
        status.observation_revision_id: status,
    }
    dispositions = {
        bar_disposition.provider_message_disposition_id: bar_disposition,
        status_disposition.provider_message_disposition_id: status_disposition,
    }
    validate_evidence_prefix_graph(
        prefix,
        adapter_policy=price_policy,
        adapter_policies={
            price_policy.adapter_policy_id: price_policy,
            instrument_policy.adapter_policy_id: instrument_policy,
        },
        segments={
            bar_segment.capture_segment_id: bar_segment,
            status_segment.capture_segment_id: status_segment,
        },
        dispositions=dispositions,
        revisions=revisions,
        parent_prefixes={},
    )
    member = replace(
        placeholder,
        semantic_content_root=prefix.evidence_prefix_id,
        artifact_hash=prefix.raw_receipt_root,
    )
    validate_source_member_physical_prefix(member, prefix, revisions)
    slot = exact_slot(member)
    selection_policy = exact_policy(slot)
    proof = select_observation_revisions_v3(
        policy=selection_policy,
        slot=slot,
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        computed_at=prefix.assembled_at,
    )
    dependency = InformationDependencyV3(
        dependency_slot_id=slot.dependency_slot_id,
        source_member_id=member.source_member_id,
        name="completed-close",
        source_id=bar.source_id,
        source_manifest_id=digest("physical-source-manifest"),
        source_field_ids=("close",),
        observation_revision_id=bar.observation_revision_id,
        source_event_ts=bar.source_event_ts,
        bar_open_ts=bar.bar_open_ts,
        bar_close_ts=bar.bar_close_ts,
        source_publish_ts=bar.source_publish_ts,
        ingested_first_seen_ts=bar.durably_appended_ts,
        revision_received_ts=bar.durably_appended_ts,
        feature_available_ts=bar.available_at,
        value_digest=observation_value_digest(("close",), ("100.5",)),
    )
    information = InformationSetV3(
        asset_id=price_policy.asset_id,
        venue_id=price_policy.venue_id,
        contract_id=price_policy.concrete_contract_id,
        timeframe_id=price_policy.timeframe_id,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        assembled_at=prefix.assembled_at,
        source_manifest_id=dependency.source_manifest_id,
        protocol_manifest_id=digest("physical-protocol"),
        calendar_manifest_id=price_policy.calendar_manifest_id,
        feature_schema_id=digest("physical-feature-schema"),
        dependencies=(dependency,),
        state_dependencies=(),
        vintage_class=VintageClass.LIVE_FIRST_SEEN_CERTIFIED,
        point_in_time_certified=True,
        certification_blockers=(),
    )
    gate = build_physical_evidence_gate_v3(
        information_set=information,
        proofs=(proof,),
        prefixes={prefix.evidence_prefix_id: prefix},
        revisions=revisions,
        evaluated_at=prefix.assembled_at,
    )
    return {
        "bar_policy": price_policy,
        "status_policy": instrument_policy,
        "member": member,
        "bar_segment": bar_segment,
        "status_segment": status_segment,
        "bar_derivation": bar_derivation,
        "status_derivation": status_derivation,
        "bar": bar,
        "status": status,
        "bar_disposition": bar_disposition,
        "status_disposition": status_disposition,
        "dispositions": dispositions,
        "prefix": prefix,
        "slot": slot,
        "selection_policy": selection_policy,
        "proof": proof,
        "dependency": dependency,
        "information": information,
        "gate": gate,
        "revisions": revisions,
    }


def test_physical_contracts_round_trip_and_tamper_detection() -> None:
    graph = physical_graph()
    records = (
        (graph["bar_policy"], ProviderAdapterPolicyV3),
        (graph["bar_segment"], CaptureSegmentV3),
        (graph["bar_derivation"], ObservationDerivationV3),
        (graph["bar"], ObservationRevisionV3),
        (graph["bar_disposition"], ProviderMessageDispositionV3),
        (graph["selection_policy"], ObservationSelectionPolicyV3),
        (graph["prefix"], EvidencePrefixV3),
        (graph["proof"], DependencySelectionProofV3),
        (graph["gate"], PhysicalEvidenceGateV3),
    )
    for record, parser in records:
        payload = record.as_dict()
        assert parser.from_mapping(payload) == record
        unknown = dict(payload)
        unknown["unexpected"] = True
        with pytest.raises(CanonicalizationError, match="keys do not match"):
            parser.from_mapping(unknown)


def test_evidence_prefix_requires_exactly_one_disposition_per_message() -> None:
    graph = physical_graph()
    arguments = {
        "adapter_policy": graph["bar_policy"],
        "adapter_policies": {
            graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
            graph["status_policy"].adapter_policy_id: graph["status_policy"],
        },
        "segments": {
            graph["bar_segment"].capture_segment_id: graph["bar_segment"],
            graph["status_segment"].capture_segment_id: graph["status_segment"],
        },
        "revisions": graph["revisions"],
        "parent_prefixes": {},
    }
    with pytest.raises(CanonicalizationError, match="exactly once"):
        validate_evidence_prefix_graph(
            replace(
                graph["prefix"],
                message_disposition_ids=(
                    graph["bar_disposition"].provider_message_disposition_id,
                ),
            ),
            dispositions=graph["dispositions"],
            **arguments,
        )

    second_bar_disposition = replace(
        graph["bar_disposition"],
        classified_at=graph["bar_disposition"].classified_at
        + timedelta(microseconds=1),
    )
    with pytest.raises(CanonicalizationError, match="exactly once"):
        validate_evidence_prefix_graph(
            replace(
                graph["prefix"],
                message_disposition_ids=(
                    *graph["prefix"].message_disposition_ids,
                    second_bar_disposition.provider_message_disposition_id,
                ),
            ),
            dispositions={
                **graph["dispositions"],
                second_bar_disposition.provider_message_disposition_id: (
                    second_bar_disposition
                ),
            },
            **arguments,
        )


def test_neutral_control_disposition_preserves_healthy_prefix() -> None:
    graph = physical_graph()
    control_segment = segment(
        graph["bar_policy"],
        json.dumps(
            {
                "success": True,
                "ret_msg": "pong",
                "conn_id": "conn-1",
                "op": "ping",
            },
            separators=(",", ":"),
        ).encode(),
        sequence=2,
        received_at=T0 + timedelta(minutes=1, milliseconds=300),
        parent=graph["bar_segment"],
    )
    control, derivation, revision = classify_message(
        graph["bar_policy"],
        control_segment,
        graph["member"],
    )
    assert control.disposition_kind is MessageDispositionKind.CONTROL_PONG
    assert derivation is None
    assert revision is None
    dispositions = {
        **graph["dispositions"],
        control.provider_message_disposition_id: control,
    }
    prefix = replace(
        graph["prefix"],
        capture_segment_ids=(
            *graph["prefix"].capture_segment_ids,
            control_segment.capture_segment_id,
        ),
        message_disposition_ids=(
            *graph["prefix"].message_disposition_ids,
            control.provider_message_disposition_id,
        ),
    )
    validate_evidence_prefix_graph(
        prefix,
        adapter_policy=graph["bar_policy"],
        adapter_policies={
            graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
            graph["status_policy"].adapter_policy_id: graph["status_policy"],
        },
        segments={
            graph["bar_segment"].capture_segment_id: graph["bar_segment"],
            graph["status_segment"].capture_segment_id: graph["status_segment"],
            control_segment.capture_segment_id: control_segment,
        },
        dispositions=dispositions,
        revisions=graph["revisions"],
        parent_prefixes={},
    )
    assert prefix.health is PrefixHealth.HEALTHY
    assert prefix.unresolved_disposition_ids == ()


def test_blocking_disposition_health_and_reconnect_recovery_are_deterministic() -> None:
    graph = physical_graph()
    blocker_segment = segment(
        graph["bar_policy"],
        b"not-json",
        sequence=2,
        received_at=T0 + timedelta(minutes=1, milliseconds=300),
        parent=graph["bar_segment"],
    )
    blocker, derivation, revision = classify_message(
        graph["bar_policy"],
        blocker_segment,
        graph["member"],
    )
    assert blocker.disposition_kind is MessageDispositionKind.MALFORMED_PAYLOAD
    assert derivation is None
    assert revision is None
    blocked_dispositions = {
        **graph["dispositions"],
        blocker.provider_message_disposition_id: blocker,
    }
    blocked = replace(
        graph["prefix"],
        cutoff_global_sequence=8,
        cutoff_receipt_hash=digest("blocked-prefix-receipt"),
        knowledge_cutoff_ts=blocker.classified_at,
        capture_segment_ids=(
            *graph["prefix"].capture_segment_ids,
            blocker_segment.capture_segment_id,
        ),
        message_disposition_ids=(
            *graph["prefix"].message_disposition_ids,
            blocker.provider_message_disposition_id,
        ),
        unresolved_disposition_ids=(blocker.provider_message_disposition_id,),
        health=PrefixHealth.INTEGRITY_CONFLICT,
        health_reason_codes=("unresolved-malformed-payload",),
        assembled_at=blocker.classified_at,
    )
    common_segments = {
        graph["bar_segment"].capture_segment_id: graph["bar_segment"],
        graph["status_segment"].capture_segment_id: graph["status_segment"],
        blocker_segment.capture_segment_id: blocker_segment,
    }
    policies = {
        graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
        graph["status_policy"].adapter_policy_id: graph["status_policy"],
    }
    validate_evidence_prefix_graph(
        blocked,
        adapter_policy=graph["bar_policy"],
        adapter_policies=policies,
        segments=common_segments,
        dispositions=blocked_dispositions,
        revisions=graph["revisions"],
        parent_prefixes={},
    )

    recovery_segment = segment(
        graph["bar_policy"],
        kline_bytes(close="100.6"),
        sequence=3,
        received_at=T0 + timedelta(minutes=1, milliseconds=700),
        parent=blocker_segment,
        connection_generation=2,
        connection_id="conn-2",
    )
    recovery_disposition, recovery_derivation, parsed_recovery = classify_message(
        graph["bar_policy"],
        recovery_segment,
        graph["member"],
    )
    assert recovery_derivation is not None
    assert parsed_recovery is not None
    recovery = replace(
        parsed_recovery,
        parent_observation_revision_id=graph["bar"].observation_revision_id,
        correction_reason="provider-correction-after-reconnect",
    )
    recovery_disposition = replace(
        recovery_disposition,
        observation_revision_id=recovery.observation_revision_id,
    )
    recovered_dispositions = {
        **blocked_dispositions,
        recovery_disposition.provider_message_disposition_id: recovery_disposition,
    }
    recovered_revisions = {
        **graph["revisions"],
        recovery.observation_revision_id: recovery,
    }
    recovered = replace(
        blocked,
        cutoff_global_sequence=9,
        cutoff_receipt_hash=digest("recovered-prefix-receipt"),
        knowledge_cutoff_ts=recovery_disposition.classified_at,
        capture_segment_ids=(
            *blocked.capture_segment_ids,
            recovery_segment.capture_segment_id,
        ),
        message_disposition_ids=(
            *blocked.message_disposition_ids,
            recovery_disposition.provider_message_disposition_id,
        ),
        observation_revision_ids=(
            *blocked.observation_revision_ids,
            recovery.observation_revision_id,
        ),
        active_observation_revision_ids=(
            graph["status"].observation_revision_id,
            recovery.observation_revision_id,
        ),
        unresolved_disposition_ids=(),
        health=PrefixHealth.HEALTHY,
        health_reason_codes=(),
        assembled_at=recovery_disposition.classified_at,
        parent_evidence_prefix_id=blocked.evidence_prefix_id,
    )
    validate_evidence_prefix_graph(
        recovered,
        adapter_policy=graph["bar_policy"],
        adapter_policies=policies,
        segments={
            **common_segments,
            recovery_segment.capture_segment_id: recovery_segment,
        },
        dispositions=recovered_dispositions,
        revisions=recovered_revisions,
        parent_prefixes={blocked.evidence_prefix_id: blocked},
    )
    assert recovered.health is PrefixHealth.HEALTHY
    assert recovered.unresolved_disposition_ids == ()


def test_capture_preserves_duplicate_occurrences_and_rejects_gaps() -> None:
    raw = kline_bytes()
    first = ProviderMessageEnvelopeV3.from_raw(
        collector_sequence=1,
        collector_received_wall_ts=T0,
        collector_received_monotonic_ns=1,
        message_type=ProviderMessageTypeV3.TEXT,
        raw_payload=raw,
    )
    duplicate = ProviderMessageEnvelopeV3.from_raw(
        collector_sequence=2,
        collector_received_wall_ts=T0 + timedelta(microseconds=1),
        collector_received_monotonic_ns=2,
        message_type=ProviderMessageTypeV3.TEXT,
        raw_payload=raw,
    )
    assert first.raw_payload_sha256 == duplicate.raw_payload_sha256
    assert first.message_receipt_id != duplicate.message_receipt_id
    with pytest.raises(CanonicalizationError, match="contiguous"):
        CaptureSegmentV3(
            adapter_policy_id=bar_policy().adapter_policy_id,
            provider_native_key="BTCUSDT",
            collector_instance_id="collector-a",
            collector_boot_id="boot-a",
            connection_id="conn-1",
            connection_generation=1,
            subscription_manifest_hash=digest("subscription"),
            vintage=PhysicalVintage.PROSPECTIVE_LIVE,
            envelopes=(first, replace(duplicate, collector_sequence=3)),
            closed_at=T0 + timedelta(seconds=1),
            clock_uncertainty_milliseconds=1,
        )


def test_capture_rejects_untyped_provider_message_kinds() -> None:
    with pytest.raises(CanonicalizationError, match="TEXT, BINARY, UNKNOWN"):
        ProviderMessageEnvelopeV3.from_raw(
            collector_sequence=1,
            collector_received_wall_ts=T0,
            collector_received_monotonic_ns=1,
            message_type="provider-data",
            raw_payload=b"{}",
        )


def test_capture_enforces_actual_canonical_object_budget() -> None:
    policy = bar_policy(requires_status=False)
    near_limit = segment(policy, b"x" * 500_000)
    assert len(canonical_json_bytes(near_limit.as_dict())) < MAX_CAPTURE_CANONICAL_BYTES

    many_small = tuple(
        ProviderMessageEnvelopeV3.from_raw(
            collector_sequence=sequence,
            collector_received_wall_ts=T0 + timedelta(microseconds=sequence),
            collector_received_monotonic_ns=sequence,
            message_type=ProviderMessageTypeV3.TEXT,
            raw_payload=b"x",
        )
        for sequence in range(1, 4097)
    )
    with pytest.raises(CanonicalizationError, match="canonical ledger-object budget"):
        CaptureSegmentV3(
            adapter_policy_id=policy.adapter_policy_id,
            provider_native_key=policy.provider_native_key,
            collector_instance_id="collector-a",
            collector_boot_id="boot-a",
            connection_id="conn-1",
            connection_generation=1,
            subscription_manifest_hash=digest("subscription"),
            vintage=PhysicalVintage.PROSPECTIVE_LIVE,
            envelopes=many_small,
            closed_at=T0 + timedelta(seconds=1),
            clock_uncertainty_milliseconds=1,
        )


def test_capture_lineage_rejects_sequence_and_connection_epoch_attacks() -> None:
    policy = bar_policy(requires_status=False)
    parent = segment(policy, kline_bytes(), sequence=1)
    child = segment(
        policy,
        kline_bytes(),
        sequence=2,
        parent=parent,
        received_at=T0 + timedelta(minutes=2),
    )
    validate_capture_segment_lineage(
        child,
        {parent.capture_segment_id: parent},
    )
    with pytest.raises(CanonicalizationError, match="connection ID"):
        validate_capture_segment_lineage(
            replace(child, connection_id="hidden-reconnect"),
            {parent.capture_segment_id: parent},
        )
    with pytest.raises(CanonicalizationError, match="skips an epoch"):
        validate_capture_segment_lineage(
            replace(child, connection_id="conn-3", connection_generation=3),
            {parent.capture_segment_id: parent},
        )
    with pytest.raises(CanonicalizationError, match="sequence 1"):
        validate_capture_segment_lineage(
            segment(policy, kline_bytes(), sequence=999),
            {},
        )


def test_capture_lineage_allows_later_generation_only_as_partition_first_capture() -> (
    None
):
    policy = bar_policy(requires_status=False)
    first_capture = segment(
        policy,
        kline_bytes(),
        sequence=1,
        connection_generation=2,
        connection_id="conn-2",
    )

    validate_capture_segment_lineage(first_capture, {})

    second_parentless_capture = segment(
        policy,
        kline_bytes(close="100.75"),
        sequence=1,
        received_at=T0 + timedelta(minutes=2),
        connection_generation=2,
        connection_id="conn-2",
    )
    with pytest.raises(CanonicalizationError, match="already has a root segment"):
        validate_capture_segment_lineage(
            second_parentless_capture,
            {first_capture.capture_segment_id: first_capture},
        )


def test_adapter_policy_rejects_unapproved_parser_identity() -> None:
    with pytest.raises(CanonicalizationError, match="approved parser/classifier"):
        replace(bar_policy(), parser_code_hash=digest("unreviewed-parser"))
    with pytest.raises(CanonicalizationError, match="approved parser/classifier"):
        replace(status_policy(), parser_version="bybit_v5_instrument_info_v3")
    with pytest.raises(CanonicalizationError, match="approved feed-health policy"):
        replace(bar_policy(), feed_health_policy_id=digest("unreviewed-health-policy"))


@pytest.mark.parametrize(
    "changes",
    (
        {"environment_id": "TESTNET"},
        {"authoritative_endpoint": "wss://example.invalid/v5/public/linear"},
        {"provider_native_key": "SOLUSDT"},
        {"max_receipt_lag_milliseconds": 2_001},
        {"stale_after_seconds": 91},
        {"max_clock_uncertainty_milliseconds": 251},
        {"requires_instrument_status": False},
    ),
)
def test_trading_authority_rejects_unreviewed_deployment_or_thresholds(
    changes: dict[str, object],
) -> None:
    with pytest.raises(CanonicalizationError, match="deployment allowlist"):
        replace(bar_policy(), **changes)


def test_status_authority_rejects_recursive_requirement() -> None:
    with pytest.raises(CanonicalizationError, match="deployment allowlist"):
        replace(status_policy(), requires_instrument_status=True)


def test_bybit_confirm_flag_is_authoritative_and_raw_parser_is_replayed() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    complete_segment, complete_derivation, complete = normalized_bar(policy, member)
    provisional_segment, provisional_derivation, provisional = normalized_bar(
        policy, member, confirm=False
    )
    assert complete.completion_state is CompletionState.COMPLETE
    assert complete.completion_basis is CompletionBasis.PROVIDER_FINAL_FLAG
    assert provisional.completion_state is CompletionState.PROVISIONAL
    assert provisional.completion_basis is CompletionBasis.NONE
    validate_raw_normalization_v3(
        policy=policy,
        segment=complete_segment,
        derivation=complete_derivation,
        revision=complete,
    )
    validate_raw_normalization_v3(
        policy=policy,
        segment=provisional_segment,
        derivation=provisional_derivation,
        revision=provisional,
    )
    forged = replace(
        provisional,
        completion_state=CompletionState.COMPLETE,
        completion_basis=CompletionBasis.PROVIDER_FINAL_FLAG,
    )
    with pytest.raises(CanonicalizationError, match="frozen parser output"):
        validate_raw_normalization_v3(
            policy=policy,
            segment=provisional_segment,
            derivation=provisional_derivation,
            revision=forged,
        )


def test_healthy_prefix_permits_only_current_provisional_tail_and_never_selects_it() -> (
    None
):
    graph = physical_graph()
    tail_start = T0 + timedelta(minutes=1)
    tail_payload = json.loads(
        kline_bytes(confirm=False, bar_start=tail_start).decode("utf-8")
    )
    tail_payload["ts"] = epoch_milliseconds(tail_start + timedelta(seconds=20))
    tail_payload["data"][0]["timestamp"] = epoch_milliseconds(
        tail_start + timedelta(seconds=20)
    )
    tail_segment = segment(
        graph["bar_policy"],
        json.dumps(tail_payload, separators=(",", ":")).encode(),
        sequence=2,
        received_at=tail_start + timedelta(seconds=20, milliseconds=100),
        parent=graph["bar_segment"],
    )
    tail_disposition, tail_derivation, tail = classify_message(
        graph["bar_policy"],
        tail_segment,
        graph["member"],
        durable=tail_start + timedelta(seconds=20, milliseconds=200),
        normalized_at=tail_start + timedelta(seconds=20, milliseconds=300),
        available_at=tail_start + timedelta(seconds=20, milliseconds=400),
        classified_at=tail_start + timedelta(seconds=20, milliseconds=500),
    )
    assert tail_derivation is not None
    assert tail is not None
    assert tail.completion_state is CompletionState.PROVISIONAL
    cutoff = tail_start + timedelta(seconds=30)
    prefix = replace(
        graph["prefix"],
        knowledge_cutoff_ts=cutoff,
        capture_segment_ids=(
            *graph["prefix"].capture_segment_ids,
            tail_segment.capture_segment_id,
        ),
        message_disposition_ids=(
            *graph["prefix"].message_disposition_ids,
            tail_disposition.provider_message_disposition_id,
        ),
        observation_revision_ids=(
            *graph["prefix"].observation_revision_ids,
            tail.observation_revision_id,
        ),
        active_observation_revision_ids=(
            *graph["prefix"].active_observation_revision_ids,
            tail.observation_revision_id,
        ),
        assembled_at=cutoff,
    )
    revisions = {**graph["revisions"], tail.observation_revision_id: tail}
    dispositions = {
        **graph["dispositions"],
        tail_disposition.provider_message_disposition_id: tail_disposition,
    }
    validate_evidence_prefix_graph(
        prefix,
        adapter_policy=graph["bar_policy"],
        adapter_policies={
            graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
            graph["status_policy"].adapter_policy_id: graph["status_policy"],
        },
        segments={
            graph["bar_segment"].capture_segment_id: graph["bar_segment"],
            graph["status_segment"].capture_segment_id: graph["status_segment"],
            tail_segment.capture_segment_id: tail_segment,
        },
        dispositions=dispositions,
        revisions=revisions,
        parent_prefixes={},
    )
    member = replace(
        graph["member"],
        semantic_content_root=prefix.evidence_prefix_id,
        artifact_hash=prefix.raw_receipt_root,
        knowledge_cutoff_ts=cutoff,
    )
    proof = select_observation_revisions_v3(
        policy=graph["selection_policy"],
        slot=graph["slot"],
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=cutoff,
        computed_at=cutoff,
    )
    assert proof.status is SelectionStatus.SELECTED
    assert proof.selected_observation_revision_ids == (
        graph["bar"].observation_revision_id,
    )
    assert tail.observation_revision_id not in proof.selected_observation_revision_ids


def test_raw_provider_lag_cannot_be_bypassed_by_omitting_envelope_metadata() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    delayed_receipt = T0 + timedelta(minutes=10)
    capture = segment(
        policy,
        kline_bytes(),
        received_at=delayed_receipt,
    )
    assert capture.envelopes[0].provider_generated_ts is None
    derivation, revision = normalize_bybit_v5_kline_message(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("mapping"),
        durably_appended_ts=delayed_receipt + timedelta(milliseconds=100),
        normalized_at=delayed_receipt + timedelta(milliseconds=200),
        available_at=delayed_receipt + timedelta(milliseconds=300),
    )
    with pytest.raises(CanonicalizationError, match="receipt-lag limit"):
        validate_raw_normalization_v3(
            policy=policy,
            segment=capture,
            derivation=derivation,
            revision=revision,
        )


def test_bybit_parser_rejects_wrong_topic_and_duplicate_json_keys() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    wrong = segment(policy, kline_bytes(topic="kline.1.ETHUSDT"))
    with pytest.raises(CanonicalizationError, match="wrong topic"):
        normalize_bybit_v5_kline_message(
            adapter_policy=policy,
            segment=wrong,
            message_receipt_id=wrong.message_receipt_ids[0],
            source_member_key=member.source_member_key,
            instrument_mapping_id=digest("mapping"),
            durably_appended_ts=T0 + timedelta(minutes=1, seconds=1),
            normalized_at=T0 + timedelta(minutes=1, seconds=1),
            available_at=T0 + timedelta(minutes=1, seconds=1),
        )
    duplicate_key = kline_bytes().replace(b'{"topic":', b'{"topic":"x","topic":', 1)
    malformed = segment(policy, duplicate_key)
    with pytest.raises(CanonicalizationError, match="duplicate JSON object key"):
        normalize_bybit_v5_kline_message(
            adapter_policy=policy,
            segment=malformed,
            message_receipt_id=malformed.message_receipt_ids[0],
            source_member_key=member.source_member_key,
            instrument_mapping_id=digest("mapping"),
            durably_appended_ts=T0 + timedelta(minutes=1, seconds=1),
            normalized_at=T0 + timedelta(minutes=1, seconds=1),
            available_at=T0 + timedelta(minutes=1, seconds=1),
        )


def test_revision_chain_rejects_forks_and_coordinate_mutation() -> None:
    graph = physical_graph()
    root = graph["bar"]
    child = replace(
        root,
        field_values=("100", "101", "99", "100.75", "12.25", "1230.5"),
        parent_observation_revision_id=root.observation_revision_id,
        correction_reason="provider-correction",
        durably_appended_ts=root.durably_appended_ts + timedelta(seconds=1),
        normalized_at=root.normalized_at + timedelta(seconds=1),
        available_at=root.available_at + timedelta(seconds=1),
    )
    validate_observation_revision_lineage(
        child,
        {root.observation_revision_id: root},
    )
    sibling = replace(
        child,
        field_values=("100", "101", "99", "100.8", "12.25", "1230.5"),
    )
    with pytest.raises(CanonicalizationError, match="forks"):
        validate_observation_revision_lineage(
            sibling,
            {
                root.observation_revision_id: root,
                child.observation_revision_id: child,
            },
        )
    with pytest.raises(CanonicalizationError, match="changes coordinates"):
        validate_observation_revision_lineage(
            replace(child, bar_open_ts=root.bar_open_ts - timedelta(minutes=1)),
            {root.observation_revision_id: root},
        )
    with pytest.raises(CanonicalizationError, match="instrument mapping"):
        validate_observation_revision_lineage(
            replace(child, instrument_mapping_id=digest("substituted-mapping")),
            {root.observation_revision_id: root},
        )


def test_healthy_prefix_requires_prospective_final_fresh_status() -> None:
    graph = physical_graph()
    arguments = {
        "adapter_policy": graph["bar_policy"],
        "adapter_policies": {
            graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
            graph["status_policy"].adapter_policy_id: graph["status_policy"],
        },
        "segments": {
            graph["bar_segment"].capture_segment_id: graph["bar_segment"],
            graph["status_segment"].capture_segment_id: graph["status_segment"],
        },
        "dispositions": graph["dispositions"],
        "revisions": graph["revisions"],
        "parent_prefixes": {},
    }
    validate_evidence_prefix_graph(graph["prefix"], **arguments)
    with pytest.raises(CanonicalizationError, match="prospective"):
        validate_evidence_prefix_graph(
            replace(graph["prefix"], vintage=PhysicalVintage.HISTORICAL_IMPORT),
            **arguments,
        )
    with pytest.raises(CanonicalizationError, match="instrument is not Trading"):
        halted = replace(graph["status"], field_values=("Halted", "LinearPerpetual"))
        halted_disposition = replace(
            graph["status_disposition"],
            observation_revision_id=halted.observation_revision_id,
        )
        revisions = dict(graph["revisions"])
        revisions.pop(graph["status"].observation_revision_id)
        revisions[halted.observation_revision_id] = halted
        validate_evidence_prefix_graph(
            replace(
                graph["prefix"],
                observation_revision_ids=(
                    graph["bar"].observation_revision_id,
                    halted.observation_revision_id,
                ),
                active_observation_revision_ids=(
                    graph["bar"].observation_revision_id,
                    halted.observation_revision_id,
                ),
                status_observation_revision_ids=(halted.observation_revision_id,),
                message_disposition_ids=(
                    graph["bar_disposition"].provider_message_disposition_id,
                    halted_disposition.provider_message_disposition_id,
                ),
            ),
            adapter_policy=graph["bar_policy"],
            adapter_policies=arguments["adapter_policies"],
            segments=arguments["segments"],
            dispositions={
                graph["bar_disposition"].provider_message_disposition_id: graph[
                    "bar_disposition"
                ],
                halted_disposition.provider_message_disposition_id: halted_disposition,
            },
            revisions=revisions,
            parent_prefixes={},
        )


def test_evidence_prefix_enforces_actual_canonical_object_budget() -> None:
    graph = physical_graph()
    record_count = 4_096
    capture_ids = tuple(digest(f"capture-{index}") for index in range(record_count))
    disposition_ids = tuple(
        digest(f"disposition-{index}") for index in range(record_count)
    )
    revision_ids = tuple(digest(f"revision-{index}") for index in range(record_count))
    with pytest.raises(CanonicalizationError, match="canonical ledger-object budget"):
        replace(
            graph["prefix"],
            capture_segment_ids=capture_ids,
            message_disposition_ids=disposition_ids,
            observation_revision_ids=revision_ids,
            active_observation_revision_ids=revision_ids,
            status_observation_revision_ids=(),
        )
    assert MAX_PREFIX_CANONICAL_BYTES < 1_048_576


def test_evidence_prefix_current_serialization_boundary_is_reproducible() -> None:
    graph = physical_graph()
    boundary = 3_352
    capture_ids = tuple(digest(f"boundary-capture-{i}") for i in range(boundary + 1))
    disposition_ids = tuple(
        digest(f"boundary-disposition-{i}") for i in range(boundary + 1)
    )
    revision_ids = tuple(digest(f"boundary-revision-{i}") for i in range(boundary + 1))
    status_ids = graph["prefix"].status_observation_revision_ids

    accepted_revisions = revision_ids[:boundary] + status_ids
    accepted = replace(
        graph["prefix"],
        capture_segment_ids=capture_ids[:boundary],
        message_disposition_ids=disposition_ids[:boundary],
        observation_revision_ids=accepted_revisions,
        active_observation_revision_ids=accepted_revisions,
    )
    assert len(canonical_json_bytes(accepted.as_dict())) == 899_945

    rejected_revisions = revision_ids + status_ids
    with pytest.raises(CanonicalizationError, match="canonical ledger-object budget"):
        replace(
            graph["prefix"],
            capture_segment_ids=capture_ids,
            message_disposition_ids=disposition_ids,
            observation_revision_ids=rejected_revisions,
            active_observation_revision_ids=rejected_revisions,
        )


def test_prefix_health_uses_only_active_status_and_rejects_cross_scope_support() -> (
    None
):
    graph = physical_graph()
    halted_segment = segment(
        graph["status_policy"],
        status_bytes(status="Halted"),
        sequence=2,
        received_at=T0 + timedelta(seconds=30, milliseconds=150),
        parent=graph["status_segment"],
    )
    halted_disposition, halted_derivation, parsed_halt = classify_message(
        graph["status_policy"],
        halted_segment,
        graph["member"],
        durable=T0 + timedelta(seconds=30, milliseconds=250),
        normalized_at=T0 + timedelta(seconds=30, milliseconds=300),
        available_at=T0 + timedelta(seconds=30, milliseconds=350),
        classified_at=T0 + timedelta(seconds=30, milliseconds=400),
    )
    assert halted_derivation is not None
    assert parsed_halt is not None
    active_halt = replace(
        parsed_halt,
        parent_observation_revision_id=graph["status"].observation_revision_id,
        correction_reason="provider-correction",
    )
    halted_disposition = replace(
        halted_disposition,
        observation_revision_id=active_halt.observation_revision_id,
    )
    revisions = dict(graph["revisions"])
    revisions[active_halt.observation_revision_id] = active_halt
    dispositions = {
        **graph["dispositions"],
        halted_disposition.provider_message_disposition_id: halted_disposition,
    }
    attacked = replace(
        graph["prefix"],
        capture_segment_ids=(
            *graph["prefix"].capture_segment_ids,
            halted_segment.capture_segment_id,
        ),
        message_disposition_ids=(
            *graph["prefix"].message_disposition_ids,
            halted_disposition.provider_message_disposition_id,
        ),
        observation_revision_ids=(
            *graph["prefix"].observation_revision_ids,
            active_halt.observation_revision_id,
        ),
        active_observation_revision_ids=(
            graph["bar"].observation_revision_id,
            active_halt.observation_revision_id,
        ),
        status_observation_revision_ids=(
            graph["status"].observation_revision_id,
            active_halt.observation_revision_id,
        ),
    )
    policies = {
        graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
        graph["status_policy"].adapter_policy_id: graph["status_policy"],
    }
    segments = {
        graph["bar_segment"].capture_segment_id: graph["bar_segment"],
        graph["status_segment"].capture_segment_id: graph["status_segment"],
        halted_segment.capture_segment_id: halted_segment,
    }
    with pytest.raises(CanonicalizationError, match="instrument is not Trading"):
        validate_evidence_prefix_graph(
            attacked,
            adapter_policy=graph["bar_policy"],
            adapter_policies=policies,
            segments=segments,
            dispositions=dispositions,
            revisions=revisions,
            parent_prefixes={},
        )

    foreign_status = replace(graph["status_policy"], timeframe_id="5m")
    with pytest.raises(CanonicalizationError, match="concrete market scope"):
        validate_evidence_prefix_graph(
            replace(
                graph["prefix"],
                supporting_adapter_policy_ids=(foreign_status.adapter_policy_id,),
            ),
            adapter_policy=graph["bar_policy"],
            adapter_policies={
                graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
                foreign_status.adapter_policy_id: foreign_status,
            },
            segments=segments,
            dispositions=graph["dispositions"],
            revisions=graph["revisions"],
            parent_prefixes={},
        )


def test_healthy_prefix_requires_reviewed_perpetual_contract_type() -> None:
    graph = physical_graph()
    wrong_contract_type = replace(
        graph["status"],
        field_values=("Trading", "LinearFutures"),
    )
    wrong_contract_disposition = replace(
        graph["status_disposition"],
        observation_revision_id=wrong_contract_type.observation_revision_id,
    )
    revisions = dict(graph["revisions"])
    revisions.pop(graph["status"].observation_revision_id)
    revisions[wrong_contract_type.observation_revision_id] = wrong_contract_type
    prefix = replace(
        graph["prefix"],
        observation_revision_ids=(
            graph["bar"].observation_revision_id,
            wrong_contract_type.observation_revision_id,
        ),
        active_observation_revision_ids=(
            graph["bar"].observation_revision_id,
            wrong_contract_type.observation_revision_id,
        ),
        status_observation_revision_ids=(wrong_contract_type.observation_revision_id,),
        message_disposition_ids=(
            graph["bar_disposition"].provider_message_disposition_id,
            wrong_contract_disposition.provider_message_disposition_id,
        ),
    )
    with pytest.raises(CanonicalizationError, match="reviewed perpetual contract"):
        validate_evidence_prefix_graph(
            prefix,
            adapter_policy=graph["bar_policy"],
            adapter_policies={
                graph["bar_policy"].adapter_policy_id: graph["bar_policy"],
                graph["status_policy"].adapter_policy_id: graph["status_policy"],
            },
            segments={
                graph["bar_segment"].capture_segment_id: graph["bar_segment"],
                graph["status_segment"].capture_segment_id: graph["status_segment"],
            },
            dispositions={
                graph["bar_disposition"].provider_message_disposition_id: graph[
                    "bar_disposition"
                ],
                wrong_contract_disposition.provider_message_disposition_id: (
                    wrong_contract_disposition
                ),
            },
            revisions=revisions,
            parent_prefixes={},
        )


def test_source_member_is_bound_to_raw_and_normalized_prefix() -> None:
    graph = physical_graph()
    validate_source_member_physical_prefix(
        graph["member"], graph["prefix"], graph["revisions"]
    )
    with pytest.raises(CanonicalizationError, match="artifact hash"):
        validate_source_member_physical_prefix(
            replace(graph["member"], artifact_hash=digest("substituted-raw-root")),
            graph["prefix"],
            graph["revisions"],
        )


def test_exact_selection_and_gate_recompute_logical_dependency() -> None:
    graph = physical_graph()
    assert graph["proof"].status is SelectionStatus.SELECTED
    assert graph["proof"].selected_observation_revision_ids == (
        graph["bar"].observation_revision_id,
    )
    assert graph["gate"].verdict is PhysicalGateVerdict.PASS
    validate_dependency_against_observation(graph["dependency"], graph["bar"])
    poisoned = replace(
        graph["dependency"],
        value_digest=digest("future-poisoned-value"),
    )
    with pytest.raises(CanonicalizationError, match="value_digest"):
        validate_dependency_against_observation(poisoned, graph["bar"])
    poisoned_information = replace(graph["information"], dependencies=(poisoned,))
    gate = build_physical_evidence_gate_v3(
        information_set=poisoned_information,
        proofs=(graph["proof"],),
        prefixes={graph["prefix"].evidence_prefix_id: graph["prefix"]},
        revisions=graph["revisions"],
        evaluated_at=graph["prefix"].assembled_at,
    )
    assert gate.verdict is PhysicalGateVerdict.ABSTAIN
    assert "physical-dependency-content-mismatch" in gate.abstention_reason_codes


def test_selection_abstains_for_future_prefix_and_missing_exact_bar() -> None:
    graph = physical_graph()
    proof = select_observation_revisions_v3(
        policy=graph["selection_policy"],
        slot=graph["slot"],
        member=graph["member"],
        prefix=replace(
            graph["prefix"],
            knowledge_cutoff_ts=T0 + timedelta(minutes=2),
            assembled_at=T0 + timedelta(minutes=2),
        ),
        revisions=graph["revisions"],
        observation_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
        computed_at=T0 + timedelta(minutes=2),
    )
    assert proof.status is SelectionStatus.ABSTAIN
    assert "prefix-known-after-selection-cutoff" in proof.abstention_reason_codes
    missing = select_observation_revisions_v3(
        policy=graph["selection_policy"],
        slot=graph["slot"],
        member=graph["member"],
        prefix=graph["prefix"],
        revisions=graph["revisions"],
        observation_cutoff_ts=T0 + timedelta(minutes=2),
        computed_at=T0 + timedelta(minutes=2),
    )
    assert missing.status is SelectionStatus.ABSTAIN
    assert "exact-event-missing-or-ambiguous" in missing.abstention_reason_codes
    expired = select_observation_revisions_v3(
        policy=graph["selection_policy"],
        slot=graph["slot"],
        member=graph["member"],
        prefix=graph["prefix"],
        revisions=graph["revisions"],
        observation_cutoff_ts=graph["prefix"].health_valid_until
        + timedelta(microseconds=1),
        computed_at=graph["prefix"].health_valid_until + timedelta(microseconds=1),
    )
    assert expired.status is SelectionStatus.ABSTAIN
    assert "physical-prefix-health-expired" in expired.abstention_reason_codes


def test_latest_and_trailing_selection_use_available_completed_revision_suffix() -> (
    None
):
    price_policy = bar_policy()
    instrument_policy = status_policy()
    placeholder = source_member_placeholder(price_policy)
    earlier_start = T0 - timedelta(minutes=1)
    earlier_segment = segment(
        price_policy,
        kline_bytes(bar_start=earlier_start, close="99.75"),
        sequence=1,
        received_at=T0 + timedelta(milliseconds=200),
    )
    later_segment = segment(
        price_policy,
        kline_bytes(bar_start=T0, close="100.5"),
        sequence=2,
        received_at=T0 + timedelta(minutes=1, milliseconds=200),
        parent=earlier_segment,
    )
    _, earlier_derivation, earlier = normalized_bar(
        price_policy,
        placeholder,
        close="99.75",
        capture=earlier_segment,
        bar_start=earlier_start,
    )
    _, later_derivation, later = normalized_bar(
        price_policy,
        placeholder,
        capture=later_segment,
        bar_start=T0,
    )
    status_segment, status_derivation, status = normalized_status(
        instrument_policy, placeholder
    )
    earlier_disposition, replayed_earlier_derivation, replayed_earlier = (
        classify_message(
            price_policy,
            earlier_segment,
            placeholder,
            durable=earlier.durably_appended_ts,
            normalized_at=earlier.normalized_at,
            available_at=earlier.available_at,
            classified_at=earlier.available_at + timedelta(milliseconds=50),
        )
    )
    later_disposition, replayed_later_derivation, replayed_later = classify_message(
        price_policy,
        later_segment,
        placeholder,
        durable=later.durably_appended_ts,
        normalized_at=later.normalized_at,
        available_at=later.available_at,
        classified_at=later.available_at + timedelta(milliseconds=50),
    )
    status_disposition, replayed_status_derivation, replayed_status = classify_message(
        instrument_policy,
        status_segment,
        placeholder,
        durable=status.durably_appended_ts,
        normalized_at=status.normalized_at,
        available_at=status.available_at,
        classified_at=status.available_at + timedelta(milliseconds=50),
    )
    assert (replayed_earlier_derivation, replayed_earlier) == (
        earlier_derivation,
        earlier,
    )
    assert (replayed_later_derivation, replayed_later) == (
        later_derivation,
        later,
    )
    assert (replayed_status_derivation, replayed_status) == (
        status_derivation,
        status,
    )
    revisions = {
        earlier.observation_revision_id: earlier,
        later.observation_revision_id: later,
        status.observation_revision_id: status,
    }
    dispositions = {
        item.provider_message_disposition_id: item
        for item in (earlier_disposition, later_disposition, status_disposition)
    }
    prefix = EvidencePrefixV3(
        adapter_policy_id=price_policy.adapter_policy_id,
        supporting_adapter_policy_ids=(instrument_policy.adapter_policy_id,),
        source_member_key=placeholder.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        ledger_id=digest("physical-ledger"),
        cutoff_global_sequence=11,
        cutoff_receipt_hash=digest("two-bar-prefix"),
        knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
        capture_segment_ids=(
            earlier_segment.capture_segment_id,
            later_segment.capture_segment_id,
            status_segment.capture_segment_id,
        ),
        message_disposition_ids=tuple(dispositions),
        observation_revision_ids=tuple(revisions),
        active_observation_revision_ids=tuple(revisions),
        status_observation_revision_ids=(status.observation_revision_id,),
        unresolved_disposition_ids=(),
        vintage=PhysicalVintage.PROSPECTIVE_LIVE,
        health=PrefixHealth.HEALTHY,
        health_reason_codes=(),
        event_time_watermark=T0 + timedelta(minutes=1),
        health_valid_until=T0 + timedelta(minutes=2),
        assembled_at=T0 + timedelta(minutes=1, seconds=1),
    )
    validate_evidence_prefix_graph(
        prefix,
        adapter_policy=price_policy,
        adapter_policies={
            price_policy.adapter_policy_id: price_policy,
            instrument_policy.adapter_policy_id: instrument_policy,
        },
        segments={
            earlier_segment.capture_segment_id: earlier_segment,
            later_segment.capture_segment_id: later_segment,
            status_segment.capture_segment_id: status_segment,
        },
        dispositions=dispositions,
        revisions=revisions,
        parent_prefixes={},
    )
    member = replace(
        placeholder,
        semantic_content_root=prefix.evidence_prefix_id,
        artifact_hash=prefix.raw_receipt_root,
        row_count=2,
        event_start_ts=earlier.source_event_ts,
        event_end_ts=later.source_event_ts,
    )
    trailing_slot = replace(
        exact_slot(member),
        dependency_slot_name="two-completed-closes",
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        minimum_count=2,
        maximum_count=2,
        maximum_age_seconds=120,
    )
    trailing_policy = ObservationSelectionPolicyV3(
        dependency_slot_id=trailing_slot.dependency_slot_id,
        selection_mode=trailing_slot.selection_mode,
        anchor=SelectionAnchor.LATEST_COMPLETED_ASOF,
        interval_seconds=60,
        anchor_lag_intervals=0,
        requested_count=2,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        maximum_age_seconds=120,
        maximum_prefix_age_seconds=90,
        tie_break_policy="AVAILABLE_AT_THEN_REVISION_ID",
        frozen_at=T0 - timedelta(minutes=2),
    )
    trailing = select_observation_revisions_v3(
        policy=trailing_policy,
        slot=trailing_slot,
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        computed_at=prefix.assembled_at,
    )
    assert trailing.status is SelectionStatus.SELECTED
    assert trailing.selected_observation_revision_ids == (
        earlier.observation_revision_id,
        later.observation_revision_id,
    )

    latest_slot = replace(
        trailing_slot,
        dependency_slot_name="latest-completed-close",
        selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
        minimum_count=1,
        maximum_count=1,
    )
    latest_policy = ObservationSelectionPolicyV3(
        dependency_slot_id=latest_slot.dependency_slot_id,
        selection_mode=latest_slot.selection_mode,
        anchor=SelectionAnchor.LATEST_COMPLETED_ASOF,
        interval_seconds=60,
        anchor_lag_intervals=0,
        requested_count=1,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        maximum_age_seconds=120,
        maximum_prefix_age_seconds=90,
        tie_break_policy="AVAILABLE_AT_THEN_REVISION_ID",
        frozen_at=T0 - timedelta(minutes=2),
    )
    latest = select_observation_revisions_v3(
        policy=latest_policy,
        slot=latest_slot,
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        computed_at=prefix.assembled_at,
    )
    assert latest.selected_observation_revision_ids == (later.observation_revision_id,)

    lagged_latest = select_observation_revisions_v3(
        policy=replace(latest_policy, anchor_lag_intervals=1),
        slot=latest_slot,
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        computed_at=prefix.assembled_at,
    )
    assert lagged_latest.selected_observation_revision_ids == (
        earlier.observation_revision_id,
    )

    gapped = replace(
        prefix,
        active_observation_revision_ids=(
            later.observation_revision_id,
            status.observation_revision_id,
        ),
    )
    short = select_observation_revisions_v3(
        policy=trailing_policy,
        slot=trailing_slot,
        member=member,
        prefix=gapped,
        revisions=revisions,
        observation_cutoff_ts=prefix.knowledge_cutoff_ts,
        computed_at=prefix.assembled_at,
    )
    assert short.status is SelectionStatus.ABSTAIN
    assert "trailing-window-short" in short.abstention_reason_codes


def test_live_and_replay_parser_outputs_are_content_identical() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    capture = segment(policy, kline_bytes())
    first = normalize_bybit_v5_kline_message(
        adapter_policy=policy,
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("mapping"),
        durably_appended_ts=T0 + timedelta(minutes=1, milliseconds=400),
        normalized_at=T0 + timedelta(minutes=1, milliseconds=500),
        available_at=T0 + timedelta(minutes=1, milliseconds=600),
    )
    replay_capture = replace(capture, vintage=PhysicalVintage.REPLAY)
    second = normalize_bybit_v5_kline_message(
        adapter_policy=policy,
        segment=replay_capture,
        message_receipt_id=replay_capture.message_receipt_ids[0],
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("mapping"),
        durably_appended_ts=T0 + timedelta(minutes=1, milliseconds=400),
        normalized_at=T0 + timedelta(minutes=1, milliseconds=500),
        available_at=T0 + timedelta(minutes=1, milliseconds=600),
    )
    assert first == second


def test_message_classifier_normalizes_kline_and_status_and_round_trips() -> None:
    price_policy = bar_policy(requires_status=False)
    member = source_member_placeholder(price_policy)
    price_capture = segment(price_policy, kline_bytes())
    price_disposition, price_derivation, price_revision = classify_message(
        price_policy, price_capture, member
    )
    assert (
        price_disposition.disposition_kind
        is MessageDispositionKind.NORMALIZED_OBSERVATION
    )
    assert price_disposition.classifier_release_hash == (
        BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH
    )
    assert price_derivation is not None
    assert price_revision is not None
    assert (
        price_disposition.observation_derivation_id
        == price_derivation.observation_derivation_id
    )
    assert (
        price_disposition.observation_revision_id
        == price_revision.observation_revision_id
    )
    assert (
        ProviderMessageDispositionV3.from_mapping(price_disposition.as_dict())
        == price_disposition
    )

    instrument_policy = status_policy()
    status_capture = segment(
        instrument_policy,
        status_bytes(),
        received_at=T0 + timedelta(seconds=30, milliseconds=100),
    )
    status_disposition, status_derivation, status_revision = classify_message(
        instrument_policy, status_capture, member
    )
    assert (
        status_disposition.disposition_kind
        is MessageDispositionKind.NORMALIZED_OBSERVATION
    )
    assert status_disposition.classifier_release_hash == (
        BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH
    )
    assert status_derivation is not None
    assert status_revision is not None
    assert status_revision.field_values == ("Trading", "LinearPerpetual")


@pytest.mark.parametrize(
    ("payload", "expected"),
    (
        (
            {
                "success": True,
                "ret_msg": "",
                "conn_id": "linear-connection",
                "req_id": "",
                "op": "subscribe",
            },
            MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        ),
        (
            {
                "success": True,
                "ret_msg": "pong",
                "conn_id": "linear-connection",
                "req_id": "",
                "op": "ping",
            },
            MessageDispositionKind.CONTROL_PONG,
        ),
    ),
)
def test_message_classifier_accepts_only_reviewed_bybit_controls(
    payload: dict[str, object], expected: MessageDispositionKind
) -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    capture = segment(
        policy,
        json.dumps(payload, separators=(",", ":")).encode(),
    )
    disposition, derivation, revision = classify_message(policy, capture, member)
    assert disposition.disposition_kind is expected
    assert derivation is None
    assert revision is None

    additive = dict(payload)
    additive["unreviewed"] = True
    unsupported = segment(
        policy,
        json.dumps(additive, separators=(",", ":")).encode(),
    )
    classified, _, _ = classify_message(policy, unsupported, member)
    assert classified.disposition_kind is MessageDispositionKind.UNSUPPORTED_SCHEMA


def test_message_classifier_records_provider_error_and_missing_status() -> None:
    price_policy = bar_policy(requires_status=False)
    member = source_member_placeholder(price_policy)
    error_payload = {
        "success": False,
        "ret_msg": "subscription failed",
        "conn_id": "linear-connection",
        "req_id": "request-1",
        "op": "subscribe",
    }
    error_capture = segment(
        price_policy,
        json.dumps(error_payload, separators=(",", ":")).encode(),
    )
    error, derivation, revision = classify_message(price_policy, error_capture, member)
    assert error.disposition_kind is MessageDispositionKind.PROVIDER_ERROR
    assert error.provider_diagnostic_code == "WS_SUBSCRIBE_FAILED"
    assert error.provider_diagnostic_digest is not None
    assert derivation is None
    assert revision is None

    instrument_policy = status_policy()
    absent_payload = json.loads(status_bytes().decode())
    absent_payload["result"]["list"] = []
    absent_capture = segment(
        instrument_policy,
        json.dumps(absent_payload, separators=(",", ":")).encode(),
        received_at=T0 + timedelta(seconds=30, milliseconds=100),
    )
    absent, derivation, revision = classify_message(
        instrument_policy, absent_capture, member
    )
    assert (
        absent.disposition_kind
        is MessageDispositionKind.EXPECTED_INSTRUMENT_STATUS_ABSENT
    )
    assert derivation is None
    assert revision is None

    rest_error_payload = json.loads(status_bytes().decode())
    rest_error_payload["retCode"] = 10001
    rest_error_payload["retMsg"] = "parameter error"
    rest_error_capture = segment(
        instrument_policy,
        json.dumps(rest_error_payload, separators=(",", ":")).encode(),
        received_at=T0 + timedelta(seconds=30, milliseconds=100),
    )
    rest_error, _, _ = classify_message(instrument_policy, rest_error_capture, member)
    assert rest_error.disposition_kind is MessageDispositionKind.PROVIDER_ERROR
    assert rest_error.provider_diagnostic_code == "REST_10001"


def test_message_classifier_exhaustively_rejects_bad_or_foreign_payloads() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    cases = (
        (b"\xff-not-json", MessageDispositionKind.MALFORMED_PAYLOAD),
        (
            b'{"notice":"provider-maintenance"}',
            MessageDispositionKind.UNSUPPORTED_SCHEMA,
        ),
        (
            kline_bytes(topic="kline.1.ETHUSDT"),
            MessageDispositionKind.OUT_OF_SCOPE,
        ),
    )
    for raw, expected in cases:
        capture = segment(policy, raw)
        disposition, derivation, revision = classify_message(policy, capture, member)
        assert disposition.disposition_kind is expected
        assert derivation is None
        assert revision is None

    conflict_payload = json.loads(kline_bytes().decode())
    conflict_payload["data"][0]["high"] = "98"
    conflict_capture = segment(
        policy,
        json.dumps(conflict_payload, separators=(",", ":")).encode(),
    )
    conflict, _, _ = classify_message(policy, conflict_capture, member)
    assert conflict.disposition_kind is MessageDispositionKind.CONTENT_CONFLICT


@pytest.mark.parametrize(
    "message_type",
    (ProviderMessageTypeV3.BINARY, ProviderMessageTypeV3.UNKNOWN),
)
@pytest.mark.parametrize(
    "raw",
    (
        kline_bytes(),
        json.dumps(
            {
                "success": True,
                "ret_msg": "",
                "conn_id": "linear-connection",
                "req_id": "request-1",
                "op": "subscribe",
            },
            separators=(",", ":"),
        ).encode(),
        b"\xff\xfe-not-text",
    ),
)
def test_non_text_provider_frames_are_preserved_but_never_decoded_or_normalized(
    message_type: ProviderMessageTypeV3,
    raw: bytes,
) -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    capture = segment(policy, raw, message_type=message_type)

    disposition, derivation, revision = classify_message(policy, capture, member)

    assert capture.envelopes[0].message_type is message_type
    assert capture.envelopes[0].raw_payload == raw
    assert disposition.disposition_kind is MessageDispositionKind.UNSUPPORTED_SCHEMA
    assert derivation is None
    assert revision is None
    with pytest.raises(CanonicalizationError, match="exact TEXT provider frame"):
        normalize_bybit_v5_kline_message(
            adapter_policy=policy,
            segment=capture,
            message_receipt_id=capture.envelopes[0].message_receipt_id,
            source_member_key=member.source_member_key,
            instrument_mapping_id=digest("binary-frame-instrument-mapping"),
            durably_appended_ts=T0 + timedelta(minutes=1, milliseconds=300),
            normalized_at=T0 + timedelta(minutes=1, milliseconds=400),
            available_at=T0 + timedelta(minutes=1, milliseconds=500),
        )


def test_message_classifier_distinguishes_lag_and_clock_rejection() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    late_capture = segment(
        policy,
        kline_bytes(),
        received_at=T0 + timedelta(minutes=10),
    )
    late, _, _ = classify_message(
        policy,
        late_capture,
        member,
        durable=T0 + timedelta(minutes=10, milliseconds=100),
    )
    assert late.disposition_kind is MessageDispositionKind.RECEIPT_LAG_REJECTED

    future_publish_capture = segment(
        policy,
        kline_bytes(),
        received_at=T0 + timedelta(seconds=59),
    )
    uncertain, _, _ = classify_message(
        policy,
        future_publish_capture,
        member,
        durable=T0 + timedelta(seconds=59, milliseconds=100),
    )
    assert uncertain.disposition_kind is MessageDispositionKind.CLOCK_ORDERING_REJECTED


def test_message_classifier_uses_earliest_exact_normalized_occurrence() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    raw = kline_bytes()
    first_capture = segment(policy, raw)
    first, first_derivation, first_revision = classify_message(
        policy, first_capture, member
    )
    assert first_derivation is not None
    assert first_revision is not None

    second_capture = segment(
        policy,
        raw,
        sequence=2,
        received_at=T0 + timedelta(minutes=1, milliseconds=300),
        parent=first_capture,
    )
    second_normal, _, _ = classify_message(policy, second_capture, member)
    assert (
        second_normal.disposition_kind is MessageDispositionKind.NORMALIZED_OBSERVATION
    )

    third_capture = segment(
        policy,
        raw,
        sequence=3,
        received_at=T0 + timedelta(minutes=1, milliseconds=400),
        parent=second_capture,
    )
    duplicate, derivation, revision = classify_message(
        policy,
        third_capture,
        member,
        prior=(
            (first_capture, first),
            (second_capture, second_normal),
        ),
    )
    assert duplicate.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE
    assert duplicate.duplicate_of_message_receipt_id == first.message_receipt_id
    assert (
        duplicate.duplicate_of_disposition_id == first.provider_message_disposition_id
    )
    assert derivation is None
    assert revision is None

    with pytest.raises(CanonicalizationError, match="current message"):
        classify_message(
            policy,
            first_capture,
            member,
            prior=((first_capture, first),),
        )


def test_message_disposition_field_matrix_is_fail_closed() -> None:
    policy = bar_policy(requires_status=False)
    member = source_member_placeholder(policy)
    capture = segment(policy, kline_bytes())
    normalized, _, _ = classify_message(policy, capture, member)
    with pytest.raises(CanonicalizationError, match="requires derivation"):
        replace(normalized, observation_derivation_id=None)
    with pytest.raises(CanonicalizationError, match="reference fields"):
        replace(
            normalized,
            disposition_kind=MessageDispositionKind.CONTROL_PONG,
        )
    with pytest.raises(CanonicalizationError, match="approved classifier"):
        replace(normalized, classifier_release_hash=digest("unknown-classifier"))

    error_payload = {
        "success": False,
        "ret_msg": "subscription failed",
        "conn_id": "linear-connection",
        "op": "subscribe",
    }
    error_capture = segment(
        policy,
        json.dumps(error_payload, separators=(",", ":")).encode(),
    )
    error, _, _ = classify_message(policy, error_capture, member)
    with pytest.raises(CanonicalizationError, match="diagnostic evidence"):
        replace(error, provider_diagnostic_digest=None)

    tampered = normalized.as_dict()
    tampered["disposition_kind"] = MessageDispositionKind.CONTROL_PONG.value
    with pytest.raises(CanonicalizationError):
        ProviderMessageDispositionV3.from_mapping(tampered)

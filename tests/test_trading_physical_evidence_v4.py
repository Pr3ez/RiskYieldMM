from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
)
from riskyieldmm.trading.physical_evidence_v4 import (
    V4_CUTOFF_MAX_CANONICAL_BYTES,
    DispositionHealthSeverity,
    EvidenceCutoffV4,
    EvidenceTreeHeadV4,
    MessageDispositionV4,
    PhysicalMessageV4,
    PhysicalScopeManifestV4,
    append_disposition_tree_head_v4,
    classifier_result_id_v4,
    disposition_leaf_input_v4,
    message_disposition_from_v3,
)
from riskyieldmm.trading.physical_market_data import (
    BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
    MessageDispositionKind,
    PhysicalVintage,
    PrefixHealth,
    ProviderMessageDispositionV3,
)
from riskyieldmm.trading.transparency_log import (
    RFC9162Frontier,
    rfc9162_empty_root,
    rfc9162_tree_hash,
)

UTC = timezone.utc
T0 = datetime(2025, 1, 1, tzinfo=UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scope(*, suffix: str = "base") -> PhysicalScopeManifestV4:
    return PhysicalScopeManifestV4(
        source_member_key=digest(f"BTCUSDT-1m-{suffix}"),
        instrument_mapping_id=digest(f"mapping-{suffix}"),
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        asset_id="BTCUSDT",
        concrete_contract_id="BTCUSDT-LINEAR",
        timeframe_id="1m",
        primary_adapter_policy_id=digest(f"adapter-{suffix}"),
        primary_classifier_release_hash=(BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH),
        required_status_adapter_policy_id=None,
        required_status_classifier_release_hash=None,
        calendar_manifest_id=digest(f"calendar-{suffix}"),
        protocol_lineage_id=digest(f"protocol-{suffix}"),
        health_policy_id=digest(f"health-{suffix}"),
        frozen_at=T0,
    )


def message(item_scope: PhysicalScopeManifestV4, sequence: int) -> PhysicalMessageV4:
    return PhysicalMessageV4(
        physical_scope_manifest_id=item_scope.physical_scope_manifest_id,
        scope_message_sequence=sequence,
        capture_segment_id=digest(f"segment-{sequence}"),
        envelope_ordinal=0,
        message_receipt_id=digest(f"message-{sequence}"),
        raw_payload_sha256=digest(f"raw-{sequence}"),
        adapter_policy_id=item_scope.primary_adapter_policy_id,
        raw_capture_receipt_sequence=sequence + 10,
    )


def control_disposition(
    item_scope: PhysicalScopeManifestV4, sequence: int
) -> MessageDispositionV4:
    item_message = message(item_scope, sequence)
    return MessageDispositionV4(
        physical_scope_manifest_id=item_scope.physical_scope_manifest_id,
        scope_message_sequence=sequence,
        physical_message_id=item_message.physical_message_id,
        message_receipt_id=item_message.message_receipt_id,
        capture_segment_id=item_message.capture_segment_id,
        raw_payload_sha256=item_message.raw_payload_sha256,
        adapter_policy_id=item_message.adapter_policy_id,
        classifier_release_hash=BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
        disposition_kind=MessageDispositionKind.CONTROL_PONG,
        health_severity=DispositionHealthSeverity.NEUTRAL,
        reason_codes=("DISPOSITION_CONTROL_PONG",),
    )


def test_v4_scope_message_and_disposition_round_trip() -> None:
    item_scope = scope()
    item_message = message(item_scope, 1)
    disposition = control_disposition(item_scope, 1)

    assert PhysicalScopeManifestV4.from_mapping(item_scope.as_dict()) == item_scope
    assert PhysicalMessageV4.from_mapping(item_message.as_dict()) == item_message
    assert MessageDispositionV4.from_mapping(disposition.as_dict()) == disposition

    unknown = disposition.as_dict()
    unknown["unknown"] = True
    with pytest.raises(CanonicalizationError, match="keys do not match schema"):
        MessageDispositionV4.from_mapping(unknown)


def test_v4_scope_rotation_changes_identity_and_boot_is_not_in_scope() -> None:
    original = scope()
    rotated = PhysicalScopeManifestV4(
        **{
            **{
                field: getattr(original, field)
                for field in original.__dataclass_fields__
            },
            "primary_adapter_policy_id": digest("rotated-adapter"),
        }
    )
    assert original.physical_scope_manifest_id != rotated.physical_scope_manifest_id
    assert "collector_boot" not in original.as_dict()
    assert "connection" not in original.as_dict()

    unsupported = {
        field: getattr(original, field) for field in original.__dataclass_fields__
    }
    unsupported["timeframe_id"] = "5m"
    with pytest.raises(CanonicalizationError, match="completed 1m evidence only"):
        PhysicalScopeManifestV4(**unsupported)


def test_scope_binds_classifier_releases_to_adapter_slots() -> None:
    original = scope()
    payload = {
        field: getattr(original, field) for field in original.__dataclass_fields__
    }
    payload["required_status_adapter_policy_id"] = digest("status-policy")
    with pytest.raises(CanonicalizationError, match="supplied together"):
        PhysicalScopeManifestV4(**payload)

    payload["required_status_classifier_release_hash"] = digest("status-classifier")
    with_status = PhysicalScopeManifestV4(**payload)
    assert with_status.physical_scope_manifest_id != (
        original.physical_scope_manifest_id
    )


def test_v4_preserves_all_v3_disposition_outcomes_and_severity() -> None:
    item_scope = scope()
    neutral = {
        MessageDispositionKind.NORMALIZED_OBSERVATION,
        MessageDispositionKind.EXACT_DUPLICATE,
        MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
        MessageDispositionKind.CONTROL_PONG,
    }
    assert len(tuple(MessageDispositionKind)) == 12
    for kind in MessageDispositionKind:
        expected = (
            DispositionHealthSeverity.NEUTRAL
            if kind in neutral
            else DispositionHealthSeverity.HALT
        )
        item_message = message(item_scope, 1)
        base = {
            "physical_scope_manifest_id": item_scope.physical_scope_manifest_id,
            "scope_message_sequence": 1,
            "physical_message_id": item_message.physical_message_id,
            "message_receipt_id": item_message.message_receipt_id,
            "capture_segment_id": item_message.capture_segment_id,
            "raw_payload_sha256": item_message.raw_payload_sha256,
            "adapter_policy_id": item_message.adapter_policy_id,
            "classifier_release_hash": BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
            "disposition_kind": kind,
            "health_severity": expected,
            "reason_codes": (f"DISPOSITION_{kind.value}",),
        }
        if kind is MessageDispositionKind.NORMALIZED_OBSERVATION:
            base["observation_derivation_ids"] = (digest("derivation"),)
            base["observation_revision_ids"] = (digest("revision"),)
        elif kind is MessageDispositionKind.EXACT_DUPLICATE:
            base["duplicate_of_message_receipt_id"] = digest("first-message")
            base["duplicate_of_disposition_id"] = digest("first-disposition")
        elif kind is MessageDispositionKind.PROVIDER_ERROR:
            base["provider_diagnostic_code"] = "10001"
            base["provider_diagnostic_digest"] = digest("diagnostic")
        disposition = MessageDispositionV4(**base)
        assert disposition.disposition_kind is kind
        assert disposition.health_severity is expected


def test_v4_rejects_outcome_shape_and_severity_substitution() -> None:
    item_scope = scope()
    item_message = message(item_scope, 1)
    base = {
        "physical_scope_manifest_id": item_scope.physical_scope_manifest_id,
        "scope_message_sequence": 1,
        "physical_message_id": item_message.physical_message_id,
        "message_receipt_id": item_message.message_receipt_id,
        "capture_segment_id": item_message.capture_segment_id,
        "raw_payload_sha256": item_message.raw_payload_sha256,
        "adapter_policy_id": item_message.adapter_policy_id,
        "classifier_release_hash": BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
        "disposition_kind": MessageDispositionKind.MALFORMED_PAYLOAD,
        "reason_codes": ("DISPOSITION_MALFORMED_PAYLOAD",),
    }
    with pytest.raises(CanonicalizationError, match="severity"):
        MessageDispositionV4(**base, health_severity=DispositionHealthSeverity.NEUTRAL)
    with pytest.raises(CanonicalizationError, match="foreign references"):
        MessageDispositionV4(
            **base,
            health_severity=DispositionHealthSeverity.HALT,
            observation_revision_ids=(digest("revision"),),
        )


def test_classifier_result_is_derived_and_duplicate_cannot_self_reference() -> None:
    item_scope = scope()
    disposition = control_disposition(item_scope, 1)
    expected = classifier_result_id_v4(
        adapter_policy_id=disposition.adapter_policy_id,
        capture_segment_id=disposition.capture_segment_id,
        classifier_release_hash=disposition.classifier_release_hash,
        disposition_kind=disposition.disposition_kind,
        message_receipt_id=disposition.message_receipt_id,
        raw_payload_sha256=disposition.raw_payload_sha256,
    )
    assert disposition.classifier_result_id == expected

    tampered = disposition.as_dict()
    tampered["classifier_result_id"] = digest("attacker-selected-result")
    with pytest.raises(CanonicalizationError, match="classifier_result_id"):
        MessageDispositionV4.from_mapping(tampered)

    item_message = message(item_scope, 2)
    with pytest.raises(CanonicalizationError, match="own message"):
        MessageDispositionV4(
            physical_scope_manifest_id=item_scope.physical_scope_manifest_id,
            scope_message_sequence=2,
            physical_message_id=item_message.physical_message_id,
            message_receipt_id=item_message.message_receipt_id,
            capture_segment_id=item_message.capture_segment_id,
            raw_payload_sha256=item_message.raw_payload_sha256,
            adapter_policy_id=item_message.adapter_policy_id,
            classifier_release_hash=BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
            disposition_kind=MessageDispositionKind.EXACT_DUPLICATE,
            health_severity=DispositionHealthSeverity.NEUTRAL,
            reason_codes=("DISPOSITION_EXACT_DUPLICATE",),
            duplicate_of_message_receipt_id=item_message.message_receipt_id,
            duplicate_of_disposition_id=digest("first-disposition"),
        )


def test_v3_mapping_excludes_operational_classification_clock() -> None:
    item_scope = scope()
    item_message = message(item_scope, 1)
    common = {
        "adapter_policy_id": item_message.adapter_policy_id,
        "capture_segment_id": item_message.capture_segment_id,
        "message_receipt_id": item_message.message_receipt_id,
        "raw_payload_sha256": item_message.raw_payload_sha256,
        "disposition_kind": MessageDispositionKind.CONTROL_PONG,
        "classifier_release_hash": BYBIT_V5_KLINE_CLASSIFIER_RELEASE_HASH,
    }
    early = ProviderMessageDispositionV3(classified_at=T0, **common)
    late = ProviderMessageDispositionV3(
        classified_at=T0 + timedelta(seconds=30), **common
    )
    assert early.provider_message_disposition_id != late.provider_message_disposition_id

    mapped_early = message_disposition_from_v3(message=item_message, disposition=early)
    mapped_late = message_disposition_from_v3(message=item_message, disposition=late)
    assert mapped_early.classifier_result_id == mapped_late.classifier_result_id
    assert mapped_early.message_disposition_id == mapped_late.message_disposition_id
    assert disposition_leaf_input_v4(mapped_early) == disposition_leaf_input_v4(
        mapped_late
    )


def test_continuous_tree_heads_match_slow_reference_and_bind_scope() -> None:
    item_scope = scope()
    frontier = RFC9162Frontier()
    parent: EvidenceTreeHeadV4 | None = None
    dispositions = []
    stored = {}
    for sequence in range(1, 34):
        disposition = control_disposition(item_scope, sequence)
        dispositions.append(disposition)
        parent, frontier, created = append_disposition_tree_head_v4(
            disposition=disposition,
            frontier=frontier,
            cutoff_global_sequence=sequence * 2,
            cutoff_receipt_hash=digest(f"receipt-{sequence}"),
            parent=parent,
        )
        for node in created:
            stored[(node.level, node.subtree_index)] = node.value
        assert parent.tree_size == sequence
        assert parent.tree_root == frontier.root_hash.hex()
    assert parent is not None
    assert frontier.root_hash == rfc9162_tree_hash(
        [disposition_leaf_input_v4(item) for item in dispositions]
    )
    assert len(stored) < 2 * len(dispositions)

    foreign = control_disposition(scope(suffix="foreign"), 34)
    with pytest.raises(CanonicalizationError, match="scope"):
        append_disposition_tree_head_v4(
            disposition=foreign,
            frontier=frontier,
            cutoff_global_sequence=100,
            cutoff_receipt_hash=digest("receipt-foreign"),
            parent=parent,
        )
    with pytest.raises(CanonicalizationError, match="advance beyond"):
        append_disposition_tree_head_v4(
            disposition=control_disposition(item_scope, 34),
            frontier=frontier,
            cutoff_global_sequence=parent.cutoff_global_sequence,
            cutoff_receipt_hash=digest("receipt-backward"),
            parent=parent,
        )


def test_v4_cutoff_is_bounded_and_healthy_requires_exact_coverage() -> None:
    item_scope = scope()

    def cutoff(size: int) -> EvidenceCutoffV4:
        return EvidenceCutoffV4(
            physical_scope_manifest_id=item_scope.physical_scope_manifest_id,
            ledger_id=digest("ledger"),
            evidence_tree_head_id=digest(f"head-{size}"),
            tree_size=size,
            tree_root=digest(f"root-{size}"),
            cutoff_global_sequence=size * 3,
            cutoff_receipt_hash=digest(f"receipt-{size}"),
            knowledge_cutoff_ts=T0,
            raw_message_count=size,
            raw_message_high_water_sequence=size,
            disposition_count=size,
            disposition_high_water_sequence=size,
            current_required_status_revision_id=None,
            vintage=PhysicalVintage.REPLAY,
            health=PrefixHealth.HEALTHY,
            health_reason_codes=(),
            event_time_watermark=T0 - timedelta(minutes=1),
            health_valid_until=T0 + timedelta(minutes=1),
        )

    small = cutoff(1)
    large = cutoff(1_000_000)
    assert EvidenceCutoffV4.from_mapping(small.as_dict()) == small
    assert EvidenceCutoffV4.from_mapping(large.as_dict()) == large
    small_size = len(canonical_json_bytes(small.as_dict()))
    large_size = len(canonical_json_bytes(large.as_dict()))
    assert small_size < V4_CUTOFF_MAX_CANONICAL_BYTES
    assert large_size < V4_CUTOFF_MAX_CANONICAL_BYTES
    assert large_size - small_size < 128

    payload = {field: getattr(small, field) for field in small.__dataclass_fields__}
    payload["disposition_count"] = 0
    with pytest.raises(CanonicalizationError, match="exact contiguous coverage"):
        EvidenceCutoffV4(**payload)
    payload["disposition_count"] = 1
    payload["raw_message_count"] = 2
    with pytest.raises(CanonicalizationError, match="exact contiguous coverage"):
        EvidenceCutoffV4(**payload)


def test_empty_cutoff_is_bootstrapping_only() -> None:
    item_scope = scope()
    base = {
        "physical_scope_manifest_id": item_scope.physical_scope_manifest_id,
        "ledger_id": digest("ledger"),
        "evidence_tree_head_id": None,
        "tree_size": 0,
        "tree_root": rfc9162_empty_root().hex(),
        "cutoff_global_sequence": 1,
        "cutoff_receipt_hash": digest("receipt-empty"),
        "knowledge_cutoff_ts": T0,
        "raw_message_count": 0,
        "raw_message_high_water_sequence": 0,
        "disposition_count": 0,
        "disposition_high_water_sequence": 0,
        "current_required_status_revision_id": None,
        "vintage": PhysicalVintage.REPLAY,
        "health_reason_codes": ("EMPTY_EVIDENCE_PREFIX",),
        "event_time_watermark": None,
        "health_valid_until": T0 + timedelta(seconds=30),
    }
    cutoff = EvidenceCutoffV4(**base, health=PrefixHealth.BOOTSTRAPPING)
    assert EvidenceCutoffV4.from_mapping(cutoff.as_dict()) == cutoff

    with pytest.raises(CanonicalizationError, match="non-empty evidence prefix"):
        EvidenceCutoffV4(
            **{
                **base,
                "health": PrefixHealth.HEALTHY,
                "health_reason_codes": (),
            }
        )

    with pytest.raises(CanonicalizationError, match="cannot reference a tree head"):
        EvidenceCutoffV4(
            **{
                **base,
                "evidence_tree_head_id": digest("impossible-empty-head"),
                "health": PrefixHealth.BOOTSTRAPPING,
            }
        )


def test_nonhealthy_cutoff_requires_a_reason() -> None:
    item_scope = scope()
    base = {
        "physical_scope_manifest_id": item_scope.physical_scope_manifest_id,
        "ledger_id": digest("ledger"),
        "evidence_tree_head_id": digest("head"),
        "tree_size": 1,
        "tree_root": digest("root"),
        "cutoff_global_sequence": 3,
        "cutoff_receipt_hash": digest("receipt"),
        "knowledge_cutoff_ts": T0,
        "raw_message_count": 1,
        "raw_message_high_water_sequence": 1,
        "disposition_count": 1,
        "disposition_high_water_sequence": 1,
        "current_required_status_revision_id": None,
        "vintage": PhysicalVintage.REPLAY,
        "health": PrefixHealth.INTEGRITY_CONFLICT,
        "event_time_watermark": None,
        "health_valid_until": T0 + timedelta(seconds=30),
    }
    with pytest.raises(CanonicalizationError, match="requires health reason"):
        EvidenceCutoffV4(**base, health_reason_codes=())
    cutoff = EvidenceCutoffV4(
        **base, health_reason_codes=("UNRESOLVED_MALFORMED_PAYLOAD",)
    )
    assert cutoff.health is PrefixHealth.INTEGRITY_CONFLICT


def test_cutoff_rejects_future_or_missing_healthy_event_watermark() -> None:
    item_scope = scope()
    base = {
        "physical_scope_manifest_id": item_scope.physical_scope_manifest_id,
        "ledger_id": digest("ledger-watermark"),
        "evidence_tree_head_id": digest("head-watermark"),
        "tree_size": 1,
        "tree_root": digest("root-watermark"),
        "cutoff_global_sequence": 3,
        "cutoff_receipt_hash": digest("receipt-watermark"),
        "knowledge_cutoff_ts": T0,
        "raw_message_count": 1,
        "raw_message_high_water_sequence": 1,
        "disposition_count": 1,
        "disposition_high_water_sequence": 1,
        "current_required_status_revision_id": None,
        "vintage": PhysicalVintage.REPLAY,
        "health": PrefixHealth.HEALTHY,
        "health_reason_codes": (),
        "health_valid_until": T0 + timedelta(seconds=30),
    }
    with pytest.raises(CanonicalizationError, match="event-time watermark"):
        EvidenceCutoffV4(**base, event_time_watermark=None)
    with pytest.raises(CanonicalizationError, match="cannot follow"):
        EvidenceCutoffV4(**base, event_time_watermark=T0 + timedelta(microseconds=1))

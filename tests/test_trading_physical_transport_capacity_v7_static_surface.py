from __future__ import annotations

import inspect
from pathlib import Path

import riskyieldmm.trading as public_trading
import riskyieldmm.trading.physical_transport_capacity_measurement_v49f as measurement
from riskyieldmm.trading.physical_transport_actor_journal_v49c import (
    PhysicalTransportActorProjectionJournalV49C,
)
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    CapacityMeasurementSessionRunnerV49FV7,
)
from riskyieldmm.trading.physical_transport_linux_v4 import LinuxSocketOwnerV4
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeV4,
)

EXPECTED_PUBLIC_V7_EXPORTS = frozenset(
    {
        "PHYSICAL_TRANSPORT_A2M_RAW_V49F_V7_SCHEMA_VERSION",
        "CapacityMeasurementArtifactBundleV49FV7",
        "CapacityMeasurementManifestV49FV7",
        "CapacityMeasurementSampleV49FV7",
        "CapacityMeasurementSessionRunnerV49FV7",
        "CollectedCapacityMeasurementCampaignV49FV7",
        "collect_capacity_measurement_campaign_v49f_v7",
    }
)
INTERNAL_V7_SYMBOLS = frozenset(
    {
        "CapacityMeasurementActorBaselineV49FV7",
        "CapacityMeasurementArtifactMemberV49FV7",
        "CapacityMeasurementCommittedLifecycleRecordV49FV7",
        "CapacityMeasurementCorrectnessV49FV7",
        "CapacityMeasurementIntegrityV49FV7",
        "CapacityMeasurementLifecycleContractV49FV7",
        "CapacityMeasurementLiteralNeutralityTraceV49F",
        "CapacityMeasurementNeutralityArmV49FV7",
        "CapacityMeasurementNeutralityReportV49F",
        "CapacityMeasurementObservationV49FV7",
        "CapacityMeasurementOperationAttemptV49F",
        "CapacityMeasurementOperationPrefixV49F",
        "CapacityMeasurementOperationTerminalV49F",
        "CapacityMeasurementPhysicalNeutralityTraceV49F",
        "CapacityMeasurementProjectionAuthorityV49FV7",
        "CapacityMeasurementSourceInventoryV49FV7",
    }
)


def test_raw_v7_public_export_surface_is_exact_and_measurement_only() -> None:
    actual = {
        name
        for name in public_trading.__all__
        if "V49FV7" in name or "RAW_V49F_V7" in name or name.endswith("_v49f_v7")
    }
    assert actual == EXPECTED_PUBLIC_V7_EXPORTS
    assert EXPECTED_PUBLIC_V7_EXPORTS <= set(public_trading.__all__)
    assert INTERNAL_V7_SYMBOLS.isdisjoint(public_trading.__all__)
    assert all(not hasattr(public_trading, name) for name in INTERNAL_V7_SYMBOLS)


def test_raw_v7_top_level_serialization_surface_is_exact_and_disjoint_from_v6() -> None:
    supported_v7 = measurement._SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F_V7  # noqa: SLF001
    assert supported_v7 == (
        measurement.CapacityMeasurementManifestV49FV7,
        measurement.CapacityMeasurementObservationV49FV7,
        measurement.CapacityMeasurementSampleV49FV7,
        measurement.CapacityMeasurementCorrectnessV49FV7,
        measurement.CapacityMeasurementArtifactMemberV49FV7,
        measurement.CapacityMeasurementIntegrityV49FV7,
    )
    assert set(supported_v7).isdisjoint(
        measurement._SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F  # noqa: SLF001
    )
    assert len(supported_v7) == len(set(supported_v7))


def test_raw_v7_runtime_paths_have_no_task_migration_or_cancellation_suppression() -> (
    None
):
    targets = (
        PhysicalTransportRuntimeV4.process_next_ingress_for_capacity_measurement_v49f,
        CapacityMeasurementSessionRunnerV49FV7.run_next_ingress,
    )
    forbidden = ("create_task(", "shield(", ".uncancel(")
    for target in targets:
        source = inspect.getsource(target)
        assert all(token not in source for token in forbidden)


def test_legacy_ingress_signature_remains_separate_from_v7_measurement_authority() -> (
    None
):
    signature = inspect.signature(PhysicalTransportRuntimeV4.process_next_ingress_v49d)
    assert tuple(signature.parameters) == ("self", "timeout_seconds")
    timeout = signature.parameters["timeout_seconds"]
    assert timeout.kind is inspect.Parameter.KEYWORD_ONLY
    assert timeout.default == 10
    assert "campaign" not in signature.parameters
    assert "authorization" not in signature.parameters


def test_owned_raw_v7_modules_have_no_unresolved_placeholder_markers() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    paths = (
        "riskyieldmm/trading/physical_transport_capacity_lifecycle_v49f.py",
        "riskyieldmm/trading/physical_transport_capacity_manifest_authority_v49f.py",
        "riskyieldmm/trading/physical_transport_capacity_measurement_v49f.py",
        "riskyieldmm/trading/physical_transport_capacity_sampler_v49f.py",
    )
    forbidden = ("TODO", "FIXME", "HACK", "XXX", "NotImplementedError")
    for relative in paths:
        source = (repository_root / relative).read_text(encoding="utf-8")
        assert all(token not in source for token in forbidden)


def test_post_fin_terminal_journal_fallback_is_exact_and_non_effect_capable() -> None:
    single = inspect.getsource(
        PhysicalTransportActorProjectionJournalV49C.append_transport_actor_event_v49c
    )
    batch = inspect.getsource(
        PhysicalTransportActorProjectionJournalV49C.append_transport_actor_events_v49c
    )
    convergence = inspect.getsource(
        PhysicalTransportActorProjectionJournalV49C.converge_actor_terminal_v49e
    )
    owner = inspect.getsource(
        LinuxSocketOwnerV4.assert_same_terminal_journal_owner_v49e
    )

    assert "TLS_PROTOCOL_OPERATION_STARTED" in single
    assert "LOCAL_CLOSE_NOTIFY" in single
    assert "PEER_SHUTDOWN_POLL" in single
    assert "TLS_PROTOCOL_OPERATION_FAILED" in single
    assert "OPAQUE_POST_HANDSHAKE_RESPONSE" not in single
    assert "terminal_operation_start or terminal_operation_failure" in single
    assert "events[-1].event_kind" in batch
    assert "TERMINAL_TRANSITION" in batch
    assert "terminal_eligible=True" in convergence
    assert "_v49e_terminal_actor_clock_authorized" in owner
    assert "_assert_terminal_actor_clock_base_v49e" in owner

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

import riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f as authority_contract
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.operational_manifests_v4 import CollectorReleaseManifestV4
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    AdmittedCapacityMeasurementAuthorityExpectationV49F,
    CollectedCapacityMeasurementCampaignV49F,
    _collect_capacity_measurement_campaign_for_test_v49f,
    collect_capacity_measurement_campaign_v49f,
    verify_capacity_measurement_manifest_against_admitted_authority_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementDesignV49F,
    CapacityMeasurementManifestV49F,
    CapacityMeasurementWorkloadV49F,
    decode_capacity_measurement_json_v49f,
    encode_capacity_measurement_json_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    CapacityMeasurementSessionRunnerV49F,
    CapacityMeasurementTrialV49F,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    measure_current_release_source_tree_v49f,
)
from tests.test_trading_physical_transport_capacity_measurement_v49f import (
    _hash,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    not hasattr(time, "CLOCK_BOOTTIME"),
    reason="Linux-only retained manifest-authority integration",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_sensitive_environment_value_drift_changes_aggregate_commitment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENSSL_CONF", "/tmp/riskyieldmm-a.cnf")
    first = authority_contract._environment_observation()  # noqa: SLF001
    monkeypatch.setenv("OPENSSL_CONF", "/tmp/riskyieldmm-b.cnf")
    second = authority_contract._environment_observation()  # noqa: SLF001

    assert first[1] == second[1]
    assert first[2] != second[2]
    assert first[3] != second[3]


def _design() -> CapacityMeasurementDesignV49F:
    resolution = max(1, int(time.get_clock_info("monotonic").resolution * 1e9))
    return CapacityMeasurementDesignV49F(
        observer_clock="CLOCK_MONOTONIC",
        observer_clock_resolution_nanoseconds=resolution,
        observer_overhead_subtracted=False,
        instrumentation_overhead_method="PAIRED_EMPTY_SPAN_UNSUBTRACTED",
        warmup_repetitions=0,
        measured_repetitions=1,
        trial_order="WARMUPS_DECLARED_THEN_SHA256_SEEDED_MEASURED_V49F",
        random_seed=49_006,
        analysis_plan_sha256=_hash("1"),
        exclusion_policy_sha256=_hash("2"),
    )


def _trial(input_bytes: bytes) -> CapacityMeasurementTrialV49F:
    return CapacityMeasurementTrialV49F(
        workload_id="AUTHORITATIVE_EMPTY_PONG",
        workload_family="COALESCED_INGRESS_BURST",
        repetition_index=0,
        is_warmup=False,
        stage="INTEGRATED_INGRESS_BOUNDARY",
        input_chunks=(input_bytes,),
        expected_output_frames=(),
        timeout_seconds=2,
    )


def _workload(trial: CapacityMeasurementTrialV49F) -> CapacityMeasurementWorkloadV49F:
    return CapacityMeasurementWorkloadV49F(
        workload_id=trial.workload_id,
        workload_sha256=trial.workload_spec.workload_sha256,
        workload_manifest_json=trial.workload_spec.workload_manifest_json,
    )


def test_clock_origins_do_not_alias_boottime_to_monotonic_after_suspend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Loop:
        @staticmethod
        def time() -> float:
            return 0.0000003

    monkeypatch.setattr(authority_contract.time, "monotonic_ns", lambda: 100)
    monkeypatch.setattr(
        authority_contract.time,
        "clock_gettime_ns",
        lambda clock: 10_000 if clock == time.CLOCK_BOOTTIME else 0,
    )
    assert authority_contract._capture_capacity_measurement_clock_origins_v49f(  # noqa: SLF001
        _Loop()
    ) == (100, 10_000, 300)


def test_collector_rejects_a_caller_signed_source_declaration_that_was_not_observed(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(Frame(Opcode.PONG, b"").serialize(mask=False))
            with pytest.raises(TypeError, match="LIVE_LINUX runtime profile"):
                await collect_capacity_measurement_campaign_v49f(
                    runtime=harness.runtime,
                    repository_root=_repository_root(),
                    campaign_label="v49f-a2m-test-runtime-rejected",
                    workloads=(_workload(trial),),
                    design=_design(),
                )
            with pytest.raises(
                CanonicalizationError,
                match="observed source differs from the signed deployment release",
            ):
                await _collect_capacity_measurement_campaign_for_test_v49f(
                    runtime=harness.runtime,
                    repository_root=_repository_root(),
                    campaign_label="v49f-a2m-source-mismatch",
                    workloads=(_workload(trial),),
                    design=_design(),
                )
            assert harness.store.verify().raw_ingress_commit_count == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_collector_builds_one_signed_retained_v6_campaign_and_binds_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        repository_root = _repository_root()
        release_source_tree_sha256 = measure_current_release_source_tree_v49f(
            repository_root=repository_root
        )

        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path.parent / "m6-campaign",
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
            release_source_tree_sha256=release_source_tree_sha256,
        )
        campaign: CollectedCapacityMeasurementCampaignV49F | None = None
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            runtime_type = type(harness.runtime)
            original_sign = runtime_type.sign_manifest_authority_subject_v49f
            authorizations: list[object] = []

            async def record_authorization(
                runtime: object, *, authorization: object
            ) -> object:
                authorizations.append(authorization)
                return await original_sign(runtime, authorization=authorization)

            monkeypatch.setattr(
                runtime_type,
                "sign_manifest_authority_subject_v49f",
                record_authorization,
            )
            campaign = await _collect_capacity_measurement_campaign_for_test_v49f(
                runtime=harness.runtime,
                repository_root=repository_root,
                campaign_label="v49f-a2m-authoritative-v6",
                workloads=(_workload(trial),),
                design=_design(),
            )
            assert type(campaign) is CollectedCapacityMeasurementCampaignV49F
            manifest = campaign.manifest
            assert type(manifest) is CapacityMeasurementManifestV49F
            assert manifest.source_observation.deployment_source_tree_matches
            assert manifest.source_observation.deployment_source_tree_sha256 == (
                manifest.runtime_observation.declared_source_tree_sha256
            )
            assert manifest.manifest_authority.promotion_eligible is False
            assert manifest.manifest_authority.external_attestation_status == (
                "NOT_EXTERNALLY_ATTESTED"
            )
            capability = harness.runtime._deployment_capability  # noqa: SLF001
            assert capability is not None
            collector_release = next(
                child
                for child in harness.runtime._deployment_admission.children  # noqa: SLF001
                if type(child) is CollectorReleaseManifestV4
            )
            trusted_expectation = AdmittedCapacityMeasurementAuthorityExpectationV49F.from_verified_deployment(
                capability=capability,
                collector_release=collector_release,
                authority_profile="EXACT_TEST",
            )
            verify_capacity_measurement_manifest_against_admitted_authority_v49f(
                manifest=manifest,
                expectation=trusted_expectation,
            )
            assert (
                decode_capacity_measurement_json_v49f(
                    encode_capacity_measurement_json_v49f(manifest),
                    record_type=CapacityMeasurementManifestV49F,
                )
                == manifest
            )
            await campaign.assert_current()
            assert len(authorizations) == 1
            with pytest.raises(CanonicalizationError, match="consumed"):
                await original_sign(
                    harness.runtime,
                    authorization=authorizations[0],
                )

            run = await CapacityMeasurementSessionRunnerV49F(
                campaign=campaign
            ).run_ingress(trial, sample_sequence=1, parent_sample_id=None)
            assert run.sample.manifest_authority_id == (
                manifest.manifest_authority.manifest_authority_id
            )
            assert run.sample.input_sha256 == hashlib.sha256(ingress).hexdigest()
        finally:
            if campaign is not None:
                campaign.close()
            await harness.close()

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading import (
    physical_transport_capacity_measurement_v49f as measurement,
)
from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    CollectedCapacityMeasurementCampaignV49FV7,
    _collect_capacity_measurement_campaign_for_test_v49f_v7,
    collect_capacity_measurement_campaign_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7,
    CapacityMeasurementArtifactBundleV49FV7,
    CapacityMeasurementManifestV49FV7,
    CapacityMeasurementSampleV49FV7,
    CapacityMeasurementScheduleCoverageV49FV7,
)
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    CapacityMeasurementSamplerErrorV49F,
    CapacityMeasurementSessionRunnerV49FV7,
    build_provisional_capacity_measurement_bundle_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_source_observation_v49f import (
    measure_current_release_source_tree_v49f,
)
from tests.test_trading_physical_transport_capacity_manifest_collector_v49f import (
    _design,
    _trial,
    _workload,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    not hasattr(time, "CLOCK_BOOTTIME"),
    reason="Linux-only production Raw-V7 campaign integration",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_retained_v7_collector_signer_runner_and_four_member_replay(
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
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
            release_source_tree_sha256=release_source_tree_sha256,
        )
        campaign: CollectedCapacityMeasurementCampaignV49FV7 | None = None
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            workload = _workload(trial)
            design = replace(
                _design(),
                measured_repetitions=5,
                measurement_design_id=None,
            )
            with pytest.raises(TypeError, match="LIVE_LINUX runtime profile"):
                await collect_capacity_measurement_campaign_v49f_v7(
                    runtime=harness.runtime,
                    repository_root=repository_root,
                    campaign_label="v49f-v7-live-profile-denied",
                    workloads=(workload,),
                    design=design,
                )

            runtime_type = type(harness.runtime)
            original_sign = runtime_type.sign_manifest_authority_subject_v49f_v7
            authorizations: list[object] = []

            async def record_authorization(
                runtime: object, *, authorization: object
            ) -> object:
                authorizations.append(authorization)
                return await original_sign(runtime, authorization=authorization)

            monkeypatch.setattr(
                runtime_type,
                "sign_manifest_authority_subject_v49f_v7",
                record_authorization,
            )
            campaign = await _collect_capacity_measurement_campaign_for_test_v49f_v7(
                runtime=harness.runtime,
                repository_root=repository_root,
                campaign_label="v49f-v7-production-path",
                workloads=(workload,),
                design=design,
            )
            assert type(campaign) is CollectedCapacityMeasurementCampaignV49FV7
            assert type(campaign.manifest) is CapacityMeasurementManifestV49FV7
            assert len(authorizations) == 1
            with pytest.raises(CanonicalizationError, match="consumed"):
                await original_sign(
                    harness.runtime,
                    authorization=authorizations[0],
                )

            campaign_type = type(campaign)
            original_assert_current = campaign_type.assert_current
            currentness_checks = 0

            async def count_currentness(retained_campaign: object) -> None:
                nonlocal currentness_checks
                currentness_checks += 1
                await original_assert_current(retained_campaign)

            monkeypatch.setattr(
                campaign_type,
                "assert_current",
                count_currentness,
            )
            runner = CapacityMeasurementSessionRunnerV49FV7(campaign=campaign)
            with pytest.raises(
                CanonicalizationError,
                match="runner-recorded issuance",
            ):
                campaign._assert_artifact_candidate_v49f(  # noqa: SLF001
                    runtime=harness.runtime,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=runner,
                    samples=(),
                )
            with pytest.raises(CanonicalizationError, match="exact owner"):
                campaign._assert_artifact_candidate_v49f(  # noqa: SLF001
                    runtime=harness.runtime,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=object(),
                    samples=(),
                )
            for _ in range(5):
                await _push_server_bytes(harness, ingress)
                await runner.run_next_ingress()
            with pytest.raises(
                CanonicalizationError,
                match="runner-recorded issuance",
            ):
                campaign._assert_artifact_candidate_v49f(  # noqa: SLF001
                    runtime=harness.runtime,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=runner,
                    samples=runner.completed_samples[:-1],
                )
            substituted = (
                CapacityMeasurementSampleV49FV7.from_mapping(
                    runner.completed_samples[0].as_dict()
                ),
                *runner.completed_samples[1:],
            )
            with pytest.raises(
                CanonicalizationError,
                match="runner-recorded issuance",
            ):
                campaign._assert_artifact_candidate_v49f(  # noqa: SLF001
                    runtime=harness.runtime,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=runner,
                    samples=substituted,
                )
            bundle = await runner.run_campaign()
            assert type(bundle) is CapacityMeasurementArtifactBundleV49FV7
            assert len(bundle.samples) == 5
            # One full recapture opens the runner and one closes the campaign;
            # the retained source tree is not rehashed per target operation.
            assert currentness_checks == 2
            assert bundle.correctness.schedule_coverage is (
                CapacityMeasurementScheduleCoverageV49FV7.COMPLETE
            )
            assert bundle.correctness.passed is False
            assert (
                A2M_POST_RUN_SUFFIX_PROVENANCE_UNATTESTED_V49F_V7
                in bundle.correctness.failure_codes
            )
            assert bundle.correctness.observations_complete is False
            assert "POST_RUN_SUFFIX_PROVENANCE_UNATTESTED" in (
                bundle.correctness.failure_codes
            )
            artifacts = bundle.artifact_bytes()
            assert set(artifacts) == {
                "correctness.json",
                "integrity.json",
                "manifest.json",
                "samples.jsonl",
            }
            expected_samples_bytes = sum(
                len(canonical_json_bytes(sample.as_dict())) + 1
                for sample in bundle.samples
            )
            assert len(artifacts["samples.jsonl"]) == expected_samples_bytes
            assert runner._samples_artifact_byte_count == expected_samples_bytes  # noqa: SLF001
            assert (
                CapacityMeasurementArtifactBundleV49FV7.from_artifact_bytes(
                    artifacts,
                    expectation=campaign.admitted_expectation,
                )
                == bundle
            )
            assert await runner.run_campaign() is bundle
            with pytest.raises(
                CapacityMeasurementSamplerErrorV49F,
                match="no admissible next operation",
            ):
                await runner.run_next_ingress()
            assert campaign.artifact_eligible is True

            # Finalization uses actual correctness/integrity bytes, and a
            # failed closure boundary permanently denies a restored-state retry.
            original_closure_bound = measurement.A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F
            monkeypatch.setattr(
                measurement,
                "A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F",
                sum(len(value) for value in artifacts.values()) - 1,
            )
            with pytest.raises(
                CapacityMeasurementSamplerErrorV49F,
                match="final artifact closure",
            ):
                build_provisional_capacity_measurement_bundle_v49f_v7(
                    campaign=campaign,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=runner,
                    samples=runner.completed_samples,
                )
            monkeypatch.setattr(
                measurement,
                "A2M_MAXIMUM_ARTIFACT_CLOSURE_BYTES_V49F",
                original_closure_bound,
            )
            assert campaign.artifact_eligible is False
            with pytest.raises(
                CapacityMeasurementSamplerErrorV49F,
                match="permanently made ineligible",
            ):
                build_provisional_capacity_measurement_bundle_v49f_v7(
                    campaign=campaign,
                    runner_authority=runner._runner_authority,  # noqa: SLF001
                    runner=runner,
                    samples=runner.completed_samples,
                )
        finally:
            if campaign is not None:
                campaign.close()
            await harness.close()

    asyncio.run(scenario())

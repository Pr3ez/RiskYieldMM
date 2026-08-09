from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import replace
from pathlib import Path

import pytest
import websockets.frames as websocket_frames
from websockets.frames import Frame, Opcode

import riskyieldmm.trading.physical_transport_capacity_sampler_v49f as capacity_sampler
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementOutcomeV49F,
    CapacityMeasurementWorkloadV49F,
)
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    CapacityMeasurementCorrectnessInputsV49F,
    CapacityMeasurementLiteralNeutralityTraceV49F,
    CapacityMeasurementNeutralityArmV49FV7,
    CapacityMeasurementPhysicalNeutralityTraceV49F,
    CapacityMeasurementSamplerErrorV49F,
    CapacityMeasurementSessionRunnerV49F,
    CapacityMeasurementTrialV49F,
    _build_capacity_measurement_bundle_for_test_v49f,
    assert_capacity_measurement_neutrality_v49f,
    capacity_measurement_storage_identity_sha256_v49f,
    compare_capacity_measurement_neutrality_v49f,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4StateError,
)
from tests.test_trading_physical_transport_capacity_measurement_v49f import (
    _design,
    _environment,
    _manifest,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _actor_events,
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import (
    _policy,
    _wait_until,
)


def _campaign_manifest(
    runtime: PhysicalTransportRuntimeV4,
    trial: CapacityMeasurementTrialV49F,
):
    boundary = runtime.capacity_measurement_boundary_v49f()
    loop = asyncio.get_running_loop()
    workload = CapacityMeasurementWorkloadV49F(
        workload_id=trial.workload_id,
        workload_sha256=trial.workload_spec.workload_sha256,
        workload_manifest_json=trial.workload_spec.workload_manifest_json,
    )
    design = replace(
        _design(),
        observer_clock="CLOCK_MONOTONIC",
        warmup_repetitions=0,
        measured_repetitions=1,
        measurement_design_id=None,
    )
    database_path = runtime.capacity_measurement_database_path_v49f()
    environment = replace(
        _environment(),
        storage_identity_sha256=capacity_measurement_storage_identity_sha256_v49f(
            database_path
        ),
        environment_id=None,
    )
    return _manifest(
        transport_session_id=boundary.transport_session_id,
        driver_evidence_nonce_sha256=boundary.driver_evidence_nonce_sha256,
        kernel_socket_identity=boundary.kernel_socket_identity,
        transport_capacity_policy_id=boundary.transport_capacity_policy_id,
        monotonic_origin_nanoseconds=str(time.monotonic_ns()),
        boottime_origin_nanoseconds=str(time.clock_gettime_ns(time.CLOCK_BOOTTIME)),
        loop_time_origin_nanoseconds=str(int(loop.time() * 1_000_000_000)),
        workloads=(workload,),
        environment=environment,
        design=design,
    )


def _trial(input_bytes: bytes) -> CapacityMeasurementTrialV49F:
    return CapacityMeasurementTrialV49F(
        workload_id="COALESCED_EMPTY_PONG",
        workload_family="COALESCED_INGRESS_BURST",
        repetition_index=0,
        is_warmup=False,
        stage="INTEGRATED_INGRESS_BOUNDARY",
        input_chunks=(input_bytes,),
        expected_output_frames=(),
        timeout_seconds=2,
    )


def _correctness_inputs(*, cleanup_complete: bool = False):
    return CapacityMeasurementCorrectnessInputsV49F(
        raw_ingress_root_sha256="1" * 64,
        actor_event_root_sha256="2" * 64,
        projection_root_sha256="3" * 64,
        no_loss=True,
        no_duplication=True,
        no_reordering=True,
        control_output_causal=True,
        projection_verified=True,
        cleanup_complete=cleanup_complete,
    )


def test_boundary_sampler_runs_exact_ingress_once_and_keeps_missing_hook_explicit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            manifest = _campaign_manifest(harness.runtime, trial)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )

            run = await runner.run_ingress(
                trial, sample_sequence=1, parent_sample_id=None
            )
            sample = run.sample

            assert sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
            assert sample.operation_error_code is None
            assert sample.measurement_outcome is (CapacityMeasurementOutcomeV49F.ERROR)
            assert sample.measurement_error_code == "MEASUREMENT_INCOMPLETE"
            assert sample.admission_attribution == "EXACT_RETURNED_GRANT"
            assert sample.admission_policy_id == _policy().policy_id
            assert sample.admission_sequence == 1
            assert sample.raw_ingress_sequence == 1
            assert sample.input_octet_count == len(ingress)
            assert sample.input_sha256 == hashlib.sha256(ingress).hexdigest()
            assert sample.returned_ingress_progress is not None
            assert sample.returned_ingress_progress.admission_command_kind == "INGRESS"
            assert (
                sample.returned_ingress_progress.admission_reservation_work_units
                == _policy().ingress_reservation_work_units
            )
            assert (
                sample.returned_ingress_progress.admission_queue_wait_nanoseconds
                == (
                    sample.returned_ingress_progress.admission_started_loop_time_offset_nanoseconds
                    - sample.returned_ingress_progress.admission_admitted_loop_time_offset_nanoseconds
                )
            )
            assert sample.initial_runtime_boundary.actor_event_count == (
                run.initial_boundary.actor_event_count
            )
            assert sample.before_runtime_boundary.actor_event_count == (
                run.boundary_before.actor_event_count
            )
            assert sample.after_runtime_boundary.actor_event_count == (
                run.boundary_after.actor_event_count
            )
            assert run.boundary_before.actor_event_count == 0
            assert run.boundary_before.actor_wire_queue_events == 0
            assert run.boundary_before.actor_wire_queue_octets == 0
            assert run.boundary_after.actor_event_count == 2
            assert run.boundary_after.actor_wire_queue_events == 0
            assert run.boundary_after.actor_wire_queue_octets == 0
            assert run.boundary_after.admission_released_commands == (
                run.boundary_before.admission_released_commands + 1
            )
            assert len(sample.parser_event_ids) == 1
            assert sample.automatic_output_source_parser_event_ids == ()
            assert sample.automatic_dispatch_completion_event_ids == ()
            assert sample.automatic_output_wire_chunk_counts == ()
            assert sample.before_snapshot.actor_wire_queue_octets == 0
            assert sample.after_snapshot.actor_wire_queue_octets == 0
            assert set(sample.in_operation_snapshot.unavailable_fields) == set(
                sample.in_operation_snapshot.as_dict().keys()
            ) - {
                "adapter_spans",
                "observation_method",
                "observed_offset_nanoseconds",
                "unavailable_fields",
                "unavailable_reason_codes",
            }

            bundle = _build_capacity_measurement_bundle_for_test_v49f(
                manifest=manifest,
                runs=(run,),
                correctness_inputs=_correctness_inputs(),
            )
            assert not bundle.correctness.observations_complete
            assert "OBSERVATIONS_INCOMPLETE" in bundle.correctness.failure_codes
            assert "CLEANUP_INCOMPLETE" in bundle.correctness.failure_codes
            assert "CORRECTNESS_FINALIZER_NOT_IMPLEMENTED" in (
                bundle.correctness.failure_codes
            )
            assert not bundle.correctness.passed
            assert not bundle.correctness.no_loss
            assert not bundle.correctness.no_duplication
            assert not bundle.correctness.no_reordering
            assert not bundle.correctness.control_output_causal
            assert not bundle.correctness.projection_verified
            assert bundle.artifact_bytes() == (
                type(bundle)
                .from_artifact_bytes(bundle.artifact_bytes())
                .artifact_bytes()
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_sampler_logical_pong_oracle_is_independent_of_client_mask_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_token_bytes = websocket_frames.secrets.token_bytes

    async def scenario() -> None:
        payload = b"logical-oracle"
        ingress = Frame(Opcode.PING, payload).serialize(mask=False)
        samples = []
        exact_outputs = []
        for index, mask in enumerate((b"\x01\x02\x03\x04", b"\x05\x06\x07\x08")):
            harness = await _build_harness(
                tmp_path.parent / f"a2m-mask-{index}",
                first_frame=ingress,
                transport_capacity_policy_v49f=_policy(),
            )
            try:
                await _establish_and_activate(harness)

                def fixed_mask(size: int, *, value: bytes = mask) -> bytes:
                    return value if size == 4 else original_token_bytes(size)

                monkeypatch.setattr(websocket_frames.secrets, "token_bytes", fixed_mask)
                trial = replace(
                    _trial(ingress),
                    workload_id="COALESCED_PING_PONG",
                    expected_output_frames=(("PONG", payload),),
                )
                runner = CapacityMeasurementSessionRunnerV49F._for_test(
                    runtime=harness.runtime,
                    manifest=_campaign_manifest(harness.runtime, trial),
                )
                run = await runner.run_ingress(
                    trial,
                    sample_sequence=1,
                    parent_sample_id=None,
                )
                sample = run.sample
                assert sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
                assert sample.output_frame_count == 1
                assert sample.expected_output_frame_count == 1
                assert sample.observed_output_frames_sha256 == (
                    sample.expected_output_frames_sha256
                )
                assert sample.automatic_output_source_parser_event_ids == (
                    sample.parser_event_ids[0],
                )
                assert len(sample.automatic_dispatch_completion_event_ids) == 1
                assert sample.automatic_output_wire_chunk_counts == (1,)
                assert sample.returned_ingress_progress is not None
                assert sample.returned_ingress_progress.logical_output_frames == (
                    ("PONG", payload),
                )
                exact_outputs.append(
                    sample.returned_ingress_progress.automatic_protocol_output_chunks
                )
                assert type(sample).from_mapping(sample.as_dict()) == sample
                samples.append(sample)
            finally:
                await harness.close()

        assert samples[0].observed_output_batch_sha256 != (
            samples[1].observed_output_batch_sha256
        )
        assert samples[0].observed_output_frames_sha256 == (
            samples[1].observed_output_frames_sha256
        )
        assert exact_outputs[0] != exact_outputs[1]
        assert b"".join(exact_outputs[0]) != b"".join(exact_outputs[1])

    asyncio.run(scenario())


def test_boundary_sampler_rejects_same_length_declared_input_substitution(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        actual = Frame(Opcode.PONG, b"").serialize(mask=False)
        substituted = Frame(Opcode.PING, b"").serialize(mask=False)
        assert len(actual) == len(substituted) and actual != substituted
        harness = await _build_harness(
            tmp_path,
            first_frame=actual,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(substituted)
            manifest = _campaign_manifest(harness.runtime, trial)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )

            run = await runner.run_ingress(
                trial, sample_sequence=1, parent_sample_id=None
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.FAIL
            assert (
                run.sample.operation_error_code == "COMMITTED_RAW_BATCH_SHA256_MISMATCH"
            )
            assert run.sample.input_sha256 == hashlib.sha256(substituted).hexdigest()
            assert run.sample.raw_ingress_batch_sha256 != (
                trial.workload_spec.raw_ingress_batch_sha256
            )
            assert harness.store.verify().raw_ingress_commit_count == 1
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_sampler_fails_wrong_preregistered_logical_output_after_real_pong(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        payload = b"actual"
        ingress = Frame(Opcode.PING, payload).serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = replace(
                _trial(ingress),
                workload_id="WRONG_EXPECTED_PONG",
                expected_output_frames=(("PONG", b"different"),),
            )
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=_campaign_manifest(harness.runtime, trial),
            )

            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.FAIL
            assert run.sample.operation_error_code == "EXPECTED_LOGICAL_OUTPUT_MISMATCH"
            assert run.sample.output_frame_count == 1
            assert run.sample.observed_output_frames_sha256 != (
                run.sample.expected_output_frames_sha256
            )
            assert harness.store.verify().raw_ingress_commit_count == 1
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_sampler_persists_more_than_one_staged_dispatch_limit_of_outputs(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ingress = b"".join(
            Frame(Opcode.PING, b"").serialize(mask=False) for _ in range(33)
        )
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = replace(_trial(ingress), workload_id="THIRTY_THREE_PINGS")
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=_campaign_manifest(harness.runtime, trial),
            )

            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.FAIL
            assert run.sample.operation_error_code == "EXPECTED_LOGICAL_OUTPUT_MISMATCH"
            assert run.sample.output_frame_count == 33
            assert len(run.sample.automatic_output_source_parser_event_ids) == 33
            assert len(run.sample.automatic_dispatch_completion_event_ids) == 33
            assert sum(run.sample.automatic_output_wire_chunk_counts) == (
                run.sample.output_chunk_count
            )
            assert run.sample.returned_ingress_progress is not None
            assert len(run.sample.returned_ingress_progress.logical_output_frames) == 33
            assert (
                len(
                    run.sample.returned_ingress_progress.automatic_protocol_output_chunks
                )
                == run.sample.output_chunk_count
            )
            assert type(run.sample).from_mapping(run.sample.as_dict()) == run.sample
            assert harness.store.verify().raw_ingress_commit_count == 1
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_runner_rejects_chunk_stage_and_timeout_manifest_substitution_before_ingress(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            declared = _trial(ingress)
            manifest = _campaign_manifest(harness.runtime, declared)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )
            substitutions = (
                replace(
                    declared,
                    input_chunks=(ingress[:1], ingress[1:]),
                ),
                replace(declared, stage="SUBSTITUTED_STAGE"),
                replace(declared, timeout_seconds=3),
            )

            for substituted in substitutions:
                with pytest.raises(
                    CapacityMeasurementSamplerErrorV49F,
                    match="exact executable workload manifest",
                ):
                    await runner.run_ingress(
                        substituted,
                        sample_sequence=1,
                        parent_sample_id=None,
                    )
            assert harness.store.verify().raw_ingress_commit_count == 0
            assert _actor_events(harness) == ()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_transport_observer_failure_does_not_suppress_or_duplicate_ingress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable_flow(self: PhysicalTransportRuntimeV4):
        raise OSError("injected observer-only failure")

    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            manifest = _campaign_manifest(harness.runtime, trial)
            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "capacity_measurement_transport_flow_v49f",
                unavailable_flow,
            )
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )

            run = await runner.run_ingress(
                trial, sample_sequence=1, parent_sample_id=None
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
            assert run.sample.measurement_outcome is (
                CapacityMeasurementOutcomeV49F.ERROR
            )
            assert set(_actor_events(harness))
            assert harness.store.verify().raw_ingress_commit_count == 1
            assert "TRANSPORT_FLOW_OBSERVER_ERROR" in (
                run.sample.before_snapshot.unavailable_reason_codes
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_operation_exception_class_is_persisted_in_raw_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def injected_failure(
        self: PhysicalTransportRuntimeV4, *, timeout_seconds: int = 10
    ):
        del self, timeout_seconds
        raise OSError("injected ingress failure before effects")

    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=_campaign_manifest(harness.runtime, trial),
            )
            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "process_next_ingress_v49d",
                injected_failure,
            )

            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.ERROR
            assert run.sample.operation_error_code == "INGRESS_OPERATION_EXCEPTION"
            assert run.sample.operation_exception_class == "OSError"
            assert run.operation_exception_class == "OSError"
            assert run.sample.raw_ingress_commit_id is None
            assert run.sample.returned_ingress_progress is None
            assert run.sample.returned_ingress_progress_unavailable_reason == (
                "RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION"
            )
            assert run.sample.output_chunk_count is None
            assert run.sample.output_octet_count is None
            assert run.sample.observed_output_sha256 is None
            assert run.sample.observed_output_batch_sha256 is None
            assert run.sample.output_frame_count is None
            assert run.sample.observed_output_frames_sha256 is None
            assert run.sample.after_runtime_boundary.actor_event_count == (
                run.boundary_after.actor_event_count
            )
            assert harness.store.verify().raw_ingress_commit_count == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_exception_after_completed_pong_never_becomes_exact_empty_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        first_payload = b"completed-before-failure"
        second_payload = b"must-not-be-claimed"
        ingress = Frame(Opcode.PING, first_payload).serialize(mask=False) + Frame(
            Opcode.PING, second_payload
        ).serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = replace(
                _trial(ingress),
                workload_id="PARTIAL_PONG_THEN_PARSER_FAILURE",
                expected_output_frames=(
                    ("PONG", first_payload),
                    ("PONG", second_payload),
                ),
            )
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=_campaign_manifest(harness.runtime, trial),
            )
            original_parse = harness.owner.parse_next_durable_unit_v49d
            parse_calls = 0

            async def fail_second_parser_unit():
                nonlocal parse_calls
                parse_calls += 1
                if parse_calls == 2:
                    raise RuntimeError("injected second parser unit failure")
                return await original_parse()

            monkeypatch.setattr(
                harness.owner,
                "parse_next_durable_unit_v49d",
                fail_second_parser_unit,
            )
            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.ERROR
            assert run.sample.operation_error_code == "INGRESS_OPERATION_EXCEPTION"
            assert run.sample.returned_ingress_progress is None
            assert run.sample.returned_ingress_progress_unavailable_reason == (
                "RETURNED_PROGRESS_UNAVAILABLE_AFTER_EXCEPTION"
            )
            assert run.sample.output_chunk_count is None
            assert run.sample.output_octet_count is None
            assert run.sample.observed_output_sha256 is None
            assert run.sample.after_runtime_boundary.runtime_state == "FAULT_LATCHED"
            assert run.sample.after_runtime_boundary.actor_event_count > (
                run.sample.before_runtime_boundary.actor_event_count
            )
            assert await _read_client_frames(harness, count=1) == (
                (int(Opcode.PONG), first_payload),
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("interleave_after_observation", [1, 2])
def test_foreign_runtime_command_around_target_operation_is_detected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interleave_after_observation: int,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=_campaign_manifest(harness.runtime, trial),
            )
            await _push_server_bytes(harness, ingress)
            adapter_type = type(runner._adapter)  # noqa: SLF001
            original_observe = adapter_type.observe
            calls = 0

            async def interleaving_observe(self, *, event_loop_lag_nanoseconds):
                nonlocal calls
                snapshot = await original_observe(
                    self,
                    event_loop_lag_nanoseconds=event_loop_lag_nanoseconds,
                )
                calls += 1
                if calls == interleave_after_observation:
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key=(f"a2m-foreign-{interleave_after_observation}")
                    )
                return snapshot

            monkeypatch.setattr(adapter_type, "observe", interleaving_observe)
            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
            assert (
                run.sample.measurement_outcome is CapacityMeasurementOutcomeV49F.ERROR
            )
            assert (
                run.sample.measurement_error_code
                == "NON_TARGET_RUNTIME_ACTIVITY_DETECTED"
            )
            if interleave_after_observation == 1:
                assert run.sample.before_snapshot.actor_event_count == 0
                assert run.boundary_before.actor_event_count > 0
            else:
                assert run.sample.after_snapshot.actor_event_count == (
                    run.boundary_before.actor_event_count + 2
                )
                assert run.boundary_after.actor_event_count > (
                    run.sample.after_snapshot.actor_event_count
                )
            assert run.sample.initial_runtime_boundary.actor_event_count == (
                run.initial_boundary.actor_event_count
            )
            assert run.sample.before_runtime_boundary.actor_event_count == (
                run.boundary_before.actor_event_count
            )
            assert run.sample.after_runtime_boundary.actor_event_count == (
                run.boundary_after.actor_event_count
            )
            assert harness.store.verify().raw_ingress_commit_count == 1
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("failing_observation", "failed_snapshot_name"),
    [(1, "before_snapshot"), (2, "after_snapshot")],
)
def test_process_observer_failure_before_or_after_does_not_change_ingress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_observation: int,
    failed_snapshot_name: str,
) -> None:
    original_observer = capacity_sampler.observe_linux_process_point_v49f
    call_count = 0

    def flaky_process_observer():
        nonlocal call_count
        call_count += 1
        if call_count == failing_observation:
            raise OSError("injected process observer failure")
        return original_observer()

    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            manifest = _campaign_manifest(harness.runtime, trial)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )
            monkeypatch.setattr(
                capacity_sampler,
                "observe_linux_process_point_v49f",
                flaky_process_observer,
            )

            run = await runner.run_ingress(
                trial,
                sample_sequence=1,
                parent_sample_id=None,
            )

            assert call_count == 2
            assert run.sample.operation_outcome is CapacityMeasurementOutcomeV49F.PASS
            assert run.sample.measurement_outcome is (
                CapacityMeasurementOutcomeV49F.ERROR
            )
            assert harness.store.verify().raw_ingress_commit_count == 1
            assert set(_actor_events(harness))
            failed_snapshot = getattr(run.sample, failed_snapshot_name)
            assert "PROCESS_OBSERVER_ERROR" in (
                failed_snapshot.unavailable_reason_codes
            )
            other_snapshot_name = (
                "after_snapshot"
                if failed_snapshot_name == "before_snapshot"
                else "before_snapshot"
            )
            assert (
                "PROCESS_OBSERVER_ERROR"
                not in getattr(run.sample, other_snapshot_name).unavailable_reason_codes
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_runner_rejects_manifest_storage_identity_mismatch(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(ingress)
            manifest = _campaign_manifest(harness.runtime, trial)
            foreign_environment = replace(
                manifest.environment,
                storage_identity_sha256="0" * 64,
                environment_id=None,
            )
            with pytest.raises(
                CanonicalizationError,
                match="environment aliases differ from the process observation",
            ):
                replace(
                    manifest,
                    environment=foreign_environment,
                    campaign_manifest_id=None,
                )
            assert harness.store.verify().raw_ingress_commit_count == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_sampler_propagates_cancellation_without_post_observation_or_stale_admission(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            trial = _trial(b"not-delivered")
            manifest = _campaign_manifest(harness.runtime, trial)
            runner = CapacityMeasurementSessionRunnerV49F._for_test(
                runtime=harness.runtime,
                manifest=manifest,
            )
            task = asyncio.create_task(
                runner.run_ingress(
                    trial,
                    sample_sequence=1,
                    parent_sample_id=None,
                )
            )
            await _wait_until(
                lambda: (
                    (snapshot := harness.runtime.transport_admission_snapshot_v49f())
                    is not None
                    and snapshot.active_and_waiting_commands == 1
                )
            )
            with pytest.raises(PhysicalTransportRuntimeV4StateError, match="quiescent"):
                harness.runtime.capacity_measurement_boundary_v49f()
            with pytest.raises(PhysicalTransportRuntimeV4StateError, match="quiescent"):
                await harness.runtime.capture_capacity_measurement_boundary_v49f()

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.active_and_waiting_commands == 0
            assert snapshot.reserved_work_units == 0
            assert snapshot.cancelled_before_entry_commands in {0, 1}
            assert _actor_events(harness) == ()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_literal_and_physical_neutrality_profiles_are_strict_and_separate() -> None:
    literal = CapacityMeasurementLiteralNeutralityTraceV49F(
        neutrality_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
        raw_prefix_bytes=b"raw",
        actor_prefix_bytes=b"actor",
        projection_prefix_bytes=b"projection",
        logical_output_bytes=b"output",
        outcome_classes=("PASS",),
    )
    probes_on = replace(
        literal,
        neutrality_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_ON),
    )
    assert compare_capacity_measurement_neutrality_v49f(literal, probes_on).passed
    assert_capacity_measurement_neutrality_v49f(literal, probes_on)

    changed = replace(literal, actor_prefix_bytes=b"changed")
    report = compare_capacity_measurement_neutrality_v49f(literal, changed)
    assert report.mismatch_fields == ("actor_prefix_bytes",)
    with pytest.raises(CapacityMeasurementSamplerErrorV49F, match="actor_prefix"):
        assert_capacity_measurement_neutrality_v49f(literal, changed)

    physical = CapacityMeasurementPhysicalNeutralityTraceV49F(
        neutrality_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
        actor_event_kinds=("RAW_INGRESS_COMMITTED", "PARSER_TRANSITION"),
        causal_parent_ordinals=((), (0,)),
        logical_frames=(("PONG", hashlib.sha256(b"").hexdigest()),),
        admission_decisions=("ADMITTED",),
        operation_outcomes=("PASS",),
        runtime_states=("SESSION_COMMITTED",),
        chain_verified=True,
        projection_verified=True,
    )
    assert compare_capacity_measurement_neutrality_v49f(physical, physical).passed
    with pytest.raises(TypeError, match="one exact comparison profile"):
        compare_capacity_measurement_neutrality_v49f(literal, physical)  # type: ignore[arg-type]


@pytest.mark.parametrize("input_chunks", [(), (b"",)])
def test_trial_rejects_empty_input_tuple_or_empty_chunk(
    input_chunks: tuple[bytes, ...],
) -> None:
    with pytest.raises(CanonicalizationError, match="non-empty byte chunks"):
        CapacityMeasurementTrialV49F(
            workload_id="X",
            workload_family="X",
            repetition_index=0,
            is_warmup=False,
            stage="INGRESS",
            input_chunks=input_chunks,
            expected_output_frames=(),
        )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"logical_frames": []}, "logical_frames must be an exact tuple"),
        (
            {"causal_parent_ordinals": [(), (0,)]},
            "causal_parent_ordinals must align exactly",
        ),
        (
            {"causal_parent_ordinals": ((),)},
            "causal_parent_ordinals must align exactly",
        ),
        (
            {"causal_parent_ordinals": ((0,), (0,))},
            "exact earlier event ordinals",
        ),
        (
            {"causal_parent_ordinals": ((), (1,))},
            "exact earlier event ordinals",
        ),
        (
            {"causal_parent_ordinals": ((), (0, 0))},
            "unique and canonically ordered",
        ),
    ],
)
def test_physical_neutrality_trace_rejects_invalid_causal_shapes(
    changes: dict[str, object], message: str
) -> None:
    physical = CapacityMeasurementPhysicalNeutralityTraceV49F(
        neutrality_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
        actor_event_kinds=("RAW_INGRESS_COMMITTED", "PARSER_TRANSITION"),
        causal_parent_ordinals=((), (0,)),
        logical_frames=(("PONG", hashlib.sha256(b"").hexdigest()),),
        admission_decisions=("ADMITTED",),
        operation_outcomes=("PASS",),
        runtime_states=("SESSION_COMMITTED",),
        chain_verified=True,
        projection_verified=True,
    )

    with pytest.raises(CanonicalizationError, match=message):
        replace(physical, **changes)


def test_physical_neutrality_cannot_pass_with_unverified_chains() -> None:
    physical = CapacityMeasurementPhysicalNeutralityTraceV49F(
        neutrality_arm=(CapacityMeasurementNeutralityArmV49FV7.RESOURCE_PROBES_OFF),
        actor_event_kinds=("RAW_INGRESS_COMMITTED", "PARSER_TRANSITION"),
        causal_parent_ordinals=((), (0,)),
        logical_frames=(("PONG", hashlib.sha256(b"").hexdigest()),),
        admission_decisions=("ADMITTED",),
        operation_outcomes=("PASS",),
        runtime_states=("SESSION_COMMITTED",),
        chain_verified=False,
        projection_verified=False,
    )

    report = compare_capacity_measurement_neutrality_v49f(physical, physical)
    assert not report.passed
    assert report.mismatch_fields == ("chain_verified", "projection_verified")
    with pytest.raises(
        CapacityMeasurementSamplerErrorV49F,
        match="chain_verified, projection_verified",
    ):
        assert_capacity_measurement_neutrality_v49f(physical, physical)

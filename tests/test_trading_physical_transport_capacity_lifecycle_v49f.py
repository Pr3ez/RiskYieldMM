from __future__ import annotations

import asyncio
import base64
import hashlib
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PHYSICAL_PROJECTION_V4_SCHEMA_VERSION,
    PHYSICAL_PROJECTION_V4_VALIDATION_VERSION,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    validate_capacity_measurement_operation_prefix_records_v49f,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CapacityMeasurementLifecycleOperationV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationAttemptV49F,
    CapacityMeasurementOperationDeclarationV49F,
    CapacityMeasurementRetainedRawDependencyV49F,
    CapacityMeasurementSameTaskTerminalObservationV49F,
)
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportCommandKindV49F,
)
from tests.test_trading_physical_transport_runtime_v49b import T0, _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact transport authority tests"
)


def _ingress_batch_sha256(chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _declaration(input_chunks: tuple[bytes, ...]):
    joined = b"".join(input_chunks)
    return CapacityMeasurementOperationDeclarationV49F(
        campaign_manifest_id="1" * 64,
        manifest_authority_id="2" * 64,
        measurement_design_id="3" * 64,
        workload_id="CANCEL_AFTER_ADMISSION",
        workload_sha256="4" * 64,
        sample_sequence=1,
        operation_sequence=1,
        trial_index=0,
        repetition_index=0,
        is_warmup=False,
        stage="INTEGRATED_INGRESS_BOUNDARY",
        operation=CapacityMeasurementLifecycleOperationV49F.INGRESS,
        input_chunk_count=len(input_chunks),
        input_octet_count=len(joined),
        input_sha256=hashlib.sha256(joined).hexdigest(),
        raw_ingress_batch_sha256=_ingress_batch_sha256(input_chunks),
        timeout_seconds=2,
        expected_output_frame_count=0,
        expected_output_frames_sha256="5" * 64,
    )


def _attempt(harness, declaration, *, initial_pending: bool = False):
    boundary = harness.runtime.capacity_measurement_boundary_v49f()
    cursor = harness.runtime._parser_cursor_v49d  # noqa: SLF001
    assert cursor is not None
    raw_sequence, raw_tail, actor_count, actor_tail = (
        harness.store._capacity_measurement_projection_coordinates_v49f(  # noqa: SLF001
            boundary.transport_session_id
        )
    )
    authority = harness.store._capacity_measurement_attempt_authority_v49f(  # noqa: SLF001
        transport_session_id=boundary.transport_session_id,
        baseline_actor_event_count=actor_count,
    )
    origin = (1 << 53) + 10_000
    admitted = origin + 100
    started = admitted + 10
    return CapacityMeasurementOperationAttemptV49F(
        **{
            name: getattr(declaration, name)
            for name in (
                "campaign_manifest_id",
                "manifest_authority_id",
                "measurement_design_id",
                "declaration_id",
                "workload_id",
                "workload_sha256",
                "sample_sequence",
                "operation_sequence",
                "trial_index",
                "repetition_index",
                "is_warmup",
                "stage",
                "operation",
                "input_chunk_count",
                "input_octet_count",
                "input_sha256",
                "raw_ingress_batch_sha256",
                "timeout_seconds",
                "expected_output_frame_count",
                "expected_output_frames_sha256",
            )
        },
        previous_operation_terminal_id=None,
        transport_session_id=boundary.transport_session_id,
        driver_evidence_nonce_sha256=boundary.driver_evidence_nonce_sha256,
        kernel_socket_identity=boundary.kernel_socket_identity,
        transport_capacity_policy_id=boundary.transport_capacity_policy_id,
        transport_capacity_policy=_policy(),
        projection_ledger_id=authority.projection_ledger_id,
        projection_schema_version=authority.projection_schema_version,
        projection_validation_version=authority.projection_validation_version,
        projection_schema_fingerprint=authority.projection_schema_fingerprint,
        projection_store_observation_id=authority.projection_store_observation_id,
        writer_fence_token_sha256=authority.writer_fence_token_sha256,
        writer_fence_generation=authority.writer_fence_generation,
        pre_attempt_receipt_sequence=authority.pre_attempt_receipt_sequence,
        pre_attempt_receipt_hash=authority.pre_attempt_receipt_hash,
        retained_raw_dependencies=authority.retained_raw_dependencies,
        initial_pending_ingress_present_before=initial_pending,
        observer_start_offset_nanoseconds=10,
        boottime_start_offset_nanoseconds=20,
        loop_time_start_offset_nanoseconds=120,
        loop_time_origin_nanoseconds=str(origin),
        admission_policy_id=boundary.transport_capacity_policy_id,
        admission_epoch=boundary.admission_epoch,
        admission_sequence=1,
        admission_command_kind=CapacityMeasurementLifecycleOperationV49F.INGRESS,
        admission_reservation_work_units=_policy().ingress_reservation_work_units,
        admission_admitted_loop_time_ns=str(admitted),
        admission_started_loop_time_ns=str(started),
        admission_start_deadline_loop_time_ns=str(started + 1_000),
        admission_queue_wait_nanoseconds=10,
        baseline_raw_ingress_sequence=raw_sequence,
        baseline_raw_ingress_commit_id=raw_tail,
        baseline_actor_event_count=actor_count,
        baseline_actor_tail_event_id=actor_tail,
        parser_cursor_before=cursor,
        parser_cursor_id_before=cursor.parser_cursor_id,
        runtime_state_before=boundary.runtime_state,
        started_at=T0,
        started_monotonic_ns=str((1 << 53) + 20_000),
        monotonic_clock_domain_id=(
            harness.owner.governed_clock.monotonic_clock_domain_id
        ),
    )


def _cancel_observation(attempt: CapacityMeasurementOperationAttemptV49F):
    return CapacityMeasurementSameTaskTerminalObservationV49F(
        terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED,
        surfaced_exception_class="asyncio.exceptions.CancelledError",
        exception_class_chain=("asyncio.exceptions.CancelledError",),
        exception_message_sha256_chain=(hashlib.sha256(b"").hexdigest(),),
        runtime_state_after=attempt.runtime_state_before,
        observer_end_offset_nanoseconds=(attempt.observer_start_offset_nanoseconds + 1),
        boottime_end_offset_nanoseconds=(attempt.boottime_start_offset_nanoseconds + 1),
        loop_time_end_offset_nanoseconds=(
            attempt.loop_time_start_offset_nanoseconds + 1
        ),
    )


def test_declaration_is_exact_versioned_non_effect_contract() -> None:
    declaration = _declaration((b"one", b"two"))
    assert type(declaration).from_mapping(declaration.as_dict()) == declaration
    with pytest.raises(CanonicalizationError, match="exact boolean"):
        replace(declaration, is_warmup=1, declaration_id=None)
    with pytest.raises(CanonicalizationError, match="keys do not match"):
        type(declaration).from_mapping({**declaration.as_dict(), "future": True})


def test_attempt_uint128_clock_text_round_trip_and_origin_rejection(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            assert int(attempt.loop_time_origin_nanoseconds) > 1 << 53
            assert type(attempt).from_mapping(attempt.as_dict()) == attempt
            assert (
                attempt.projection_schema_version
                == PHYSICAL_PROJECTION_V4_SCHEMA_VERSION
            )
            assert (
                attempt.projection_validation_version
                == PHYSICAL_PROJECTION_V4_VALIDATION_VERSION
            )
            for invalid in ("-1", "01", str(1 << 128)):
                with pytest.raises(CanonicalizationError, match="128-bit"):
                    replace(
                        attempt,
                        loop_time_origin_nanoseconds=invalid,
                        attempt_id=None,
                    )
            with pytest.raises(CanonicalizationError, match="origin/offset"):
                replace(
                    attempt,
                    loop_time_origin_nanoseconds=str(
                        int(attempt.admission_admitted_loop_time_ns) + 1
                    ),
                    attempt_id=None,
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_initial_pending_and_retained_raw_witness_are_independent(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            witness = CapacityMeasurementRetainedRawDependencyV49F(
                raw_ingress_commit_id="a" * 64,
                content_hash="b" * 64,
                original_receipt_sequence=1,
                original_receipt_hash="c" * 64,
            )
            for pending in (False, True):
                for retained in ((), (witness,)):
                    candidate = replace(
                        attempt,
                        retained_raw_dependencies=retained,
                        initial_pending_ingress_present_before=pending,
                        attempt_id=None,
                    )
                    assert candidate.initial_pending_ingress_present_before is pending
                    assert candidate.retained_raw_dependencies == retained
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_attempt_terminal_are_atomic_reopen_safe_and_receipt_complete(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            committed = (
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-attempt",
                )
            )
            assert (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                == (attempt,)
            )
            harness.owner.abort()
            observation = _cancel_observation(attempt)
            prefix = harness.store.append_capacity_measurement_operation_terminal_v49f(
                committed,
                observation,
                idempotency_key="raw-v7-terminal",
            )
            assert prefix.terminal is not None
            assert (
                prefix.terminal.completed_at
                == prefix.projection_receipts[-1].committed_at
            )
            assert (
                prefix.projection_receipts[-1].identity_id
                == prefix.terminal.terminal_id
            )
            assert (
                validate_capacity_measurement_operation_prefix_records_v49f(prefix)
                == prefix
            )
            assert not harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            harness.store.verify()
            with pytest.raises(PhysicalProjectionV4ConflictError):
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-attempt",
                )
        finally:
            await harness.close()

        reopened = PhysicalProjectionStoreV4(
            tmp_path / "v49b-runtime.sqlite3",
            clock=lambda: T0 + timedelta(seconds=10),
        )
        try:
            assert reopened.verify().receipt_count > 0
            assert not reopened.list_open_capacity_measurement_operation_attempts_v49f()
        finally:
            reopened.close()

    asyncio.run(scenario())


def test_terminal_observation_freezes_trigger_exception_mapping() -> None:
    with pytest.raises(CanonicalizationError, match="CancelledError"):
        CapacityMeasurementSameTaskTerminalObservationV49F(
            terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED,
            surfaced_exception_class="builtins.KeyboardInterrupt",
            exception_class_chain=("builtins.KeyboardInterrupt",),
            exception_message_sha256_chain=("2" * 64,),
            runtime_state_after="FAULT_LATCHED",
            observer_end_offset_nanoseconds=1,
            boottime_end_offset_nanoseconds=1,
            loop_time_end_offset_nanoseconds=1,
        )
    with pytest.raises(CanonicalizationError, match="unsupported"):
        CapacityMeasurementSameTaskTerminalObservationV49F(
            terminal_trigger=CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED,
            surfaced_exception_class=None,
            exception_class_chain=(),
            exception_message_sha256_chain=(),
            runtime_state_after="INVENTED_STATE",
            observer_end_offset_nanoseconds=1,
            boottime_end_offset_nanoseconds=1,
            loop_time_end_offset_nanoseconds=1,
        )


def test_startup_recovery_is_store_owned_sealed_and_barriered(tmp_path: Path) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        attempt = None
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                attempt,
                idempotency_key="raw-v7-orphan-attempt",
            )
            harness.store.close()
            harness.owner.abort()
            await harness.server.close()
        finally:
            if not harness.store._closed:  # noqa: SLF001
                await harness.close()
        assert attempt is not None

        reopened = PhysicalProjectionStoreV4(
            tmp_path / "v49b-runtime.sqlite3",
            clock=lambda: T0 + timedelta(seconds=10),
        )
        try:
            reopened.claim_transport_runtime_writer_fence(
                lease_token_sha256="f" * 64,
                holder_id="raw-v7-startup-recovery",
            )
            with pytest.raises(PhysicalProjectionV4ConflictError, match="reconciled"):
                with reopened._transaction():  # noqa: SLF001
                    pass
            capability = (
                reopened._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001
            )
            assert capability.open_attempt_ids == (attempt.attempt_id,)
            with pytest.raises(AttributeError, match="no setter|immutable"):
                capability.open_attempt_ids = ()
            with pytest.raises(PhysicalProjectionV4ConflictError, match="reconciled"):
                with reopened._transaction():  # noqa: SLF001
                    pass
            prefix = reopened.recover_capacity_measurement_operation_terminal_v49f(
                capability,
                str(attempt.attempt_id),
                idempotency_key="raw-v7-recover-orphan",
            )
            assert prefix.terminal is not None
            assert prefix.terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
            )
            assert prefix.terminal.operation_error_code == "PROCESS_LOSS_UNKNOWN"
            assert prefix.terminal.runtime_state_after is None
            assert prefix.terminal.completed_monotonic_ns is None
            with pytest.raises(PhysicalProjectionV4ConflictError):
                reopened.recover_capacity_measurement_operation_terminal_v49f(
                    capability,
                    str(attempt.attempt_id),
                    idempotency_key="raw-v7-recover-orphan",
                )
            reopened.complete_capacity_measurement_startup_recovery_v49f(capability)
            with reopened._transaction():  # noqa: SLF001
                pass
            assert reopened.verify().receipt_count > 0
        finally:
            reopened.close()

    asyncio.run(scenario())


assert TransportCommandKindV49F.INGRESS.value == (
    CapacityMeasurementLifecycleOperationV49F.INGRESS.value
)

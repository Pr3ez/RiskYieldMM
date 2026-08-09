from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_projection_v4 import PhysicalProjectionStoreV4
from riskyieldmm.trading.physical_transport_actor_journal_v49c import (
    PhysicalTransportActorJournalV49COwnerError,
    PhysicalTransportActorProjectionJournalV49C,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleOperationV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationDeclarationV49F,
    CapacityMeasurementSessionTerminalAuthorityV49F,
)
from riskyieldmm.trading.physical_transport_capacity_sampler_v49f import (
    _measurement_ingress_progress_evidence_v49f,
)
from riskyieldmm.trading.physical_transport_linux_v4 import LinuxSocketOwnerV4
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    CapacityMeasurementIngressAuthorizationV49FError,
    CapacityMeasurementTerminalPersistenceV49FError,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
    _capacity_measurement_exception_chain_v49f,
)
from tests.test_trading_physical_transport_runtime_integration_v4 import private_lease
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only Raw-V7 runtime lifecycle tests"
)


class _InjectedIngressError(RuntimeError):
    pass


class _InjectedOperationError(RuntimeError):
    pass


class _InjectedPersistenceError(RuntimeError):
    pass


class _HostileStrError(RuntimeError):
    str_call_count = 0

    def __str__(self) -> str:
        type(self).str_call_count += 1
        raise AssertionError("Raw-V7 must not execute exception __str__")


def test_exception_chain_rejects_depth_overflow_and_cycles_without_truncation() -> None:
    head = RuntimeError("depth-0")
    cursor: BaseException = head
    for depth in range(1, 9):
        next_exception = RuntimeError(f"depth-{depth}")
        cursor.__cause__ = next_exception
        cursor = next_exception
    with pytest.raises(
        CapacityMeasurementTerminalPersistenceV49FError,
        match="depth bound",
    ):
        _capacity_measurement_exception_chain_v49f(head)

    first = RuntimeError("cycle-a")
    second = RuntimeError("cycle-b")
    first.__cause__ = second
    second.__cause__ = first
    with pytest.raises(
        CapacityMeasurementTerminalPersistenceV49FError,
        match="cycle",
    ):
        _capacity_measurement_exception_chain_v49f(first)


def test_exception_chain_never_formats_hostile_or_oversized_messages() -> None:
    _HostileStrError.str_call_count = 0
    hostile = _HostileStrError("hostile")
    with pytest.raises(
        CapacityMeasurementTerminalPersistenceV49FError,
        match="unsupported message formatter",
    ):
        _capacity_measurement_exception_chain_v49f(hostile)
    assert _HostileStrError.str_call_count == 0

    oversized = RuntimeError("x" * 4_097)
    with pytest.raises(
        CapacityMeasurementTerminalPersistenceV49FError,
        match="message exceeds",
    ):
        _capacity_measurement_exception_chain_v49f(oversized)


def _ingress_batch_sha256(chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _declaration(
    input_chunks: tuple[bytes, ...],
) -> CapacityMeasurementOperationDeclarationV49F:
    joined = b"".join(input_chunks)
    return CapacityMeasurementOperationDeclarationV49F(
        campaign_manifest_id="1" * 64,
        manifest_authority_id="2" * 64,
        measurement_design_id="3" * 64,
        workload_id="RAW_V7_RUNTIME_INGRESS",
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


def _boottime_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


def _issue_authorization(
    runtime: PhysicalTransportRuntimeV4,
    *,
    campaign: object,
    declaration: CapacityMeasurementOperationDeclarationV49F,
) -> tuple[Any, int, int]:
    """Issue test authority with deliberately different clock origins."""

    loop = asyncio.get_running_loop()
    base = _boottime_ns()

    def observer_monotonic_ns() -> int:
        # Keep the test observer comparable with the governed BOOTTIME sample,
        # but intentionally distinguish both clock readings and both origins.
        return _boottime_ns() + 5_000_000

    observer_origin = base + 4_000_000
    boottime_origin = base - 2_000_000
    assert observer_origin != boottime_origin
    authorization = (
        runtime._issue_capacity_measurement_ingress_authorization_v49f_for_test(  # noqa: SLF001
            campaign=campaign,
            declaration=declaration,
            previous_operation_terminal_id=None,
            observer_monotonic_ns=observer_monotonic_ns,
            boottime_ns=_boottime_ns,
            observer_origin_ns=observer_origin,
            boottime_origin_ns=boottime_origin,
            loop_origin_ns=int(loop.time() * 1_000_000_000) - 1_000_000,
        )
    )
    return authorization, observer_origin, boottime_origin


async def _wait_for_open_attempt(harness: Any) -> None:
    for _ in range(2_000):
        if harness.store.list_open_capacity_measurement_operation_attempts_v49f():
            return
        await asyncio.sleep(0)
    raise AssertionError("Raw-V7 attempt did not become durable")


def test_raw_v7_success_commits_attempt_before_effect_and_closes_same_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
            campaign = object()
            declaration = _declaration((ingress,))
            authorization, observer_origin, boottime_origin = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            events: list[str] = []
            original_commit = PhysicalTransportActorProjectionJournalV49C.commit_capacity_measurement_operation_attempt_v49f
            original_read = LinuxSocketOwnerV4.read_decrypted_ingress_v49d

            def observed_commit(self: Any, **kwargs: Any) -> Any:
                committed = original_commit(self, **kwargs)
                events.append("ATTEMPT_COMMITTED")
                return committed

            async def observed_read(self: Any, **kwargs: Any) -> Any:
                assert (
                    len(
                        harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                    )
                    == 1
                )
                events.append("TARGET_EFFECT_ENTERED")
                return await original_read(self, **kwargs)

            monkeypatch.setattr(
                PhysicalTransportActorProjectionJournalV49C,
                "commit_capacity_measurement_operation_attempt_v49f",
                observed_commit,
            )
            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                observed_read,
            )
            tasks_before = asyncio.all_tasks()
            closure = await harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                campaign=campaign,
                declaration=declaration,
                authorization=authorization,
            )
            await asyncio.sleep(0)
            assert asyncio.all_tasks() == tasks_before
            assert events == ["ATTEMPT_COMMITTED", "TARGET_EFFECT_ENTERED"]
            attempt = closure.committed_attempt.attempt
            terminal = closure.terminalized_prefix.terminal
            assert terminal is not None
            gate = harness.runtime._transport_admission_gate_v49f  # noqa: SLF001
            assert gate is not None
            assert attempt.transport_capacity_policy is gate.policy
            assert attempt.declaration_id == declaration.declaration_id
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
            )
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE
            )
            assert terminal.progress_availability is (
                CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_RETURNED_PROGRESS
            )
            assert terminal.session_terminal_authority is (
                CapacityMeasurementSessionTerminalAuthorityV49F.NONTERMINAL_RUNTIME
            )
            assert terminal.completed_monotonic_ns == str(
                int(attempt.started_monotonic_ns)
                + max(
                    0,
                    terminal.boottime_end_offset_nanoseconds
                    - attempt.boottime_start_offset_nanoseconds,
                )
            )
            assert observer_origin + terminal.observer_end_offset_nanoseconds != (
                boottime_origin + terminal.boottime_end_offset_nanoseconds
            )
            assert closure.returned_progress_evidence == (
                _measurement_ingress_progress_evidence_v49f(
                    closure.returned_progress,
                    loop_time_origin_nanoseconds=int(
                        attempt.loop_time_origin_nanoseconds
                    ),
                )
            )
            assert not harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_legacy_ingress_has_no_raw_v7_lifecycle_side_effect(tmp_path: Path) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            progress = await harness.runtime.process_next_ingress_v49d(
                timeout_seconds=2
            )
            assert progress.committed_raw_octets == len(ingress)
            assert not harness.store.list_open_capacity_measurement_operation_attempts_v49f()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_raw_v7_cancellation_closes_zero_effect_prefix_and_bare_rethrows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            declaration = _declaration((b"x",))
            campaign = object()
            observed_cancellations: list[asyncio.CancelledError] = []
            original_read = LinuxSocketOwnerV4.read_decrypted_ingress_v49d

            async def observe_cancel(self: Any, **kwargs: Any) -> Any:
                try:
                    return await original_read(self, **kwargs)
                except asyncio.CancelledError as exc:
                    observed_cancellations.append(exc)
                    raise

            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                observe_cancel,
            )

            async def measured() -> None:
                authorization, _, _ = _issue_authorization(
                    harness.runtime,
                    campaign=campaign,
                    declaration=declaration,
                )
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )

            task = asyncio.create_task(measured())
            await _wait_for_open_attempt(harness)
            task.cancel("raw-v7-cancel")
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert observed_cancellations == [caught.value]
            assert str(caught.value) == "raw-v7-cancel"
            attempts = (
                harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                    declaration.campaign_manifest_id, 1
                ),
            )
            prefix = harness.store.load_capacity_measurement_operation_prefix_v49f(
                attempts[0].attempt_id
            )
            terminal = prefix.terminal
            assert terminal is not None, repr(caught.value.__cause__)
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
            )
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
            )
            assert terminal.session_terminal_authority is (
                CapacityMeasurementSessionTerminalAuthorityV49F.VOLATILE_RUNTIME_FAULT_LATCHED
            )
            assert prefix.new_raw_ingress_commits == ()
            assert prefix.actor_events == ()
            journal = harness.runtime._transport_actor_journal_v49c  # noqa: SLF001
            actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
            assert journal is not None and actor is not None
            with pytest.raises(PhysicalTransportActorJournalV49COwnerError):
                await journal.read_transport_actor_prefix_v49c(
                    transport_session_id=actor.authority.transport_session_id
                )
            assert (
                journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                    attempt_id=attempts[0].attempt_id
                )
                == prefix
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("exception_type", "argument"),
    ((KeyboardInterrupt, "keyboard-stop"), (SystemExit, 23)),
)
def test_raw_v7_interrupts_close_then_rethrow_exact_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
    argument: Any,
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
            primary = exception_type(argument)

            async def interrupt(*args: Any, **kwargs: Any) -> Any:
                raise primary

            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "_process_next_ingress_v49d_locked",
                interrupt,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            try:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            except BaseException as caught:
                assert caught is primary
            else:
                raise AssertionError("interrupt was not rethrown")
            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id, 1
            )
            terminal = harness.store.load_capacity_measurement_operation_prefix_v49f(
                attempt.attempt_id
            ).terminal
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED
            )
            assert terminal.surfaced_exception_class == (
                f"{exception_type.__module__}.{exception_type.__qualname__}"
            )
            assert terminal.exception_class_chain == (
                terminal.surfaced_exception_class,
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_raw_v7_failure_records_exact_cause_chain_after_owner_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            original = _InjectedIngressError("injected read failure")

            async def fail_read(*args: Any, **kwargs: Any) -> Any:
                raise original

            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                fail_read,
            )
            declaration = _declaration((b"x",))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched) as caught:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            assert caught.value.__cause__ is original
            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id, 1
            )
            terminal = harness.store.load_capacity_measurement_operation_prefix_v49f(
                attempt.attempt_id
            ).terminal
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION
            )
            expected_classes = (
                "riskyieldmm.trading.physical_transport_runtime_v4."
                "PhysicalTransportRuntimeV4FaultLatched",
                f"{_InjectedIngressError.__module__}.{_InjectedIngressError.__qualname__}",
            )
            assert terminal.exception_class_chain == expected_classes
            assert terminal.surfaced_exception_class == expected_classes[0]
            assert terminal.exception_message_sha256_chain == (
                hashlib.sha256(str(caught.value).encode()).hexdigest(),
                hashlib.sha256(str(original).encode()).hexdigest(),
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_raw_v7_terminal_persistence_failure_preserves_primary_and_open_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
            primary = _InjectedOperationError("primary operation failure")
            persistence = _InjectedPersistenceError("terminal append failure")

            async def fail_operation(*args: Any, **kwargs: Any) -> Any:
                raise primary

            def fail_close(*args: Any, **kwargs: Any) -> Any:
                raise persistence

            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "_process_next_ingress_v49d_locked",
                fail_operation,
            )
            monkeypatch.setattr(
                PhysicalTransportActorProjectionJournalV49C,
                "close_capacity_measurement_operation_v49f",
                fail_close,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            try:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            except _InjectedOperationError as caught:
                assert caught is primary
                assert caught.__cause__ is persistence
                assert any("startup recovery" in note for note in caught.__notes__)
            else:
                raise AssertionError("primary operation exception was not rethrown")
            assert (
                len(
                    harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                )
                == 1
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_unsupported_exception_evidence_preserves_primary_and_open_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
            primary = _HostileStrError("must-not-format")
            _HostileStrError.str_call_count = 0

            async def fail_operation(*args: Any, **kwargs: Any) -> Any:
                raise primary

            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "_process_next_ingress_v49d_locked",
                fail_operation,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            try:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            except _HostileStrError as caught:
                assert caught is primary
                assert type(caught.__cause__) is (
                    CapacityMeasurementTerminalPersistenceV49FError
                )
                assert any("startup recovery" in note for note in caught.__notes__)
            else:
                raise AssertionError("hostile exception was not rethrown")
            assert _HostileStrError.str_call_count == 0
            assert (
                len(
                    harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                )
                == 1
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_raw_v7_authority_is_task_bound_one_shot_and_uses_no_shield(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            declaration = _declaration((b"x",))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )

            async def migrated() -> None:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )

            with pytest.raises(
                CapacityMeasurementIngressAuthorizationV49FError,
                match="migrated",
            ):
                await asyncio.create_task(migrated())
            assert not harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            source = inspect.getsource(
                PhysicalTransportRuntimeV4.process_next_ingress_for_capacity_measurement_v49f
            )
            assert "create_task" not in source
            assert "shield" not in source
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_empty_startup_snapshot_needs_no_capability_before_session_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        order: list[str] = []
        reports: list[Any] = []
        original_claim = (
            PhysicalProjectionStoreV4._claim_capacity_measurement_startup_recovery_v49f
        )
        original_complete = PhysicalProjectionStoreV4.complete_capacity_measurement_startup_recovery_v49f
        original_reconcile = (
            PhysicalProjectionStoreV4.reconcile_unterminated_transport_sessions
        )
        original_start = PhysicalTransportRuntimeV4.start
        original_admit = PhysicalTransportRuntimeV4._admit_actor_command_v49f
        original_read = LinuxSocketOwnerV4.read_decrypted_ingress_v49d

        def observed_claim(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("CAPACITY_SNAPSHOT_CLAIMED")
            return original_claim(self, *args, **kwargs)

        def observed_complete(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("CAPACITY_SNAPSHOT_COMPLETED")
            return original_complete(self, *args, **kwargs)

        def observed_reconcile(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("SESSION_RECONCILIATION")
            return original_reconcile(self, *args, **kwargs)

        def observed_start(self: Any) -> Any:
            report = original_start(self)
            reports.append(report)
            return report

        def observed_admit(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("TRANSPORT_ADMISSION")
            return original_admit(self, *args, **kwargs)

        async def observed_read(self: Any, *args: Any, **kwargs: Any) -> Any:
            order.append("TARGET_EFFECT")
            return await original_read(self, *args, **kwargs)

        monkeypatch.setattr(
            PhysicalProjectionStoreV4,
            "_claim_capacity_measurement_startup_recovery_v49f",
            observed_claim,
        )
        monkeypatch.setattr(
            PhysicalProjectionStoreV4,
            "complete_capacity_measurement_startup_recovery_v49f",
            observed_complete,
        )
        monkeypatch.setattr(
            PhysicalProjectionStoreV4,
            "reconcile_unterminated_transport_sessions",
            observed_reconcile,
        )
        monkeypatch.setattr(PhysicalTransportRuntimeV4, "start", observed_start)
        monkeypatch.setattr(
            PhysicalTransportRuntimeV4,
            "_admit_actor_command_v49f",
            observed_admit,
        )
        monkeypatch.setattr(
            LinuxSocketOwnerV4,
            "read_decrypted_ingress_v49d",
            observed_read,
        )
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            assert order == [
                "CAPACITY_SNAPSHOT_CLAIMED",
                "SESSION_RECONCILIATION",
            ]
            assert len(reports) == 1
            assert reports[0].recovered_capacity_measurement_attempt_ids == ()
            assert not harness.store._capacity_startup_recovery_capability_issued_v49f  # noqa: SLF001
            assert harness.store._capacity_startup_recovery_capability_v49f is None  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_runtime_restart_recovers_capacity_orphan_before_session_reconciliation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        old_runtime = harness.runtime
        reopened: PhysicalProjectionStoreV4 | None = None
        restart_runtime: PhysicalTransportRuntimeV4 | None = None
        try:
            await _establish_and_activate(harness)
            declaration = _declaration((ingress,))
            campaign = object()
            primary = _InjectedOperationError("process lost after attempt commit")
            persistence = _InjectedPersistenceError("simulated process loss")

            async def fail_operation(*args: Any, **kwargs: Any) -> Any:
                raise primary

            def fail_close(*args: Any, **kwargs: Any) -> Any:
                raise persistence

            monkeypatch.setattr(
                PhysicalTransportRuntimeV4,
                "_process_next_ingress_v49d_locked",
                fail_operation,
            )
            monkeypatch.setattr(
                PhysicalTransportActorProjectionJournalV49C,
                "close_capacity_measurement_operation_v49f",
                fail_close,
            )
            authorization, _, _ = _issue_authorization(
                old_runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(_InjectedOperationError) as caught:
                await old_runtime.process_next_ingress_for_capacity_measurement_v49f(
                    campaign=campaign,
                    declaration=declaration,
                    authorization=authorization,
                )
            assert caught.value is primary
            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id, 1
            )
            assert (
                harness.store.load_capacity_measurement_operation_terminal_v49f(
                    attempt.attempt_id
                )
                is None
            )
            assert old_runtime._writer_fence_token_sha256 is not None  # noqa: SLF001
            harness.store.release_transport_runtime_writer_fence(
                lease_token_sha256=old_runtime._writer_fence_token_sha256  # noqa: SLF001
            )
            old_runtime._writer_fence_token_sha256 = None  # noqa: SLF001
            old_runtime._writer_fence_generation = None  # noqa: SLF001
            old_runtime._writer_lease.release()  # noqa: SLF001
            old_runtime._state = PhysicalTransportRuntimeStateV4.CLOSED  # noqa: SLF001

            store_path = harness.store.path
            store_clock = harness.store._clock  # noqa: SLF001
            harness.store.close()
            reopened = PhysicalProjectionStoreV4(store_path, clock=store_clock)
            order: list[str] = []
            original_recover = PhysicalProjectionStoreV4.recover_capacity_measurement_operation_terminal_v49f
            original_session_reconcile = (
                PhysicalProjectionStoreV4.reconcile_unterminated_transport_sessions
            )

            def observed_recover(self: Any, *args: Any, **kwargs: Any) -> Any:
                order.append("CAPACITY_ORPHAN_TERMINAL")
                return original_recover(self, *args, **kwargs)

            def observed_session_reconcile(self: Any, *args: Any, **kwargs: Any) -> Any:
                order.append("SESSION_RECONCILIATION")
                return original_session_reconcile(self, *args, **kwargs)

            async def forbidden_network_effect(*args: Any, **kwargs: Any) -> Any:
                raise AssertionError("startup recovery attempted target network I/O")

            monkeypatch.setattr(
                PhysicalProjectionStoreV4,
                "recover_capacity_measurement_operation_terminal_v49f",
                observed_recover,
            )
            monkeypatch.setattr(
                PhysicalProjectionStoreV4,
                "reconcile_unterminated_transport_sessions",
                observed_session_reconcile,
            )
            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                forbidden_network_effect,
            )
            restart_runtime = PhysicalTransportRuntimeV4.for_test(
                journal=reopened,
                writer_lease=private_lease(tmp_path, holder_id="v49f-capacity-restart"),
                clock_source=harness.owner,
                signer=old_runtime._signer,  # noqa: SLF001
                deployment_admission=old_runtime._deployment_admission,  # noqa: SLF001
                idempotency_prefix="v49f-capacity-restart",
                wall_clock=store_clock,
                random_bytes=lambda length: bytes([0x4A]) * length,
            )
            report = restart_runtime.start()
            assert order == [
                "CAPACITY_ORPHAN_TERMINAL",
                "SESSION_RECONCILIATION",
            ]
            assert report.recovered_capacity_measurement_attempt_ids == (
                attempt.attempt_id,
            )
            assert report.reconciled_transport_session_ids == (
                attempt.transport_session_id,
            )
            prefix = reopened.load_capacity_measurement_operation_prefix_v49f(
                attempt.attempt_id
            )
            terminal = prefix.terminal
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
            )
            assert terminal.session_terminal_authority is (
                CapacityMeasurementSessionTerminalAuthorityV49F.UNAVAILABLE_AFTER_ORPHAN
            )
            assert terminal.parser_cursor_id_after == attempt.parser_cursor_id_before
            assert terminal.runtime_state_after is None
            assert terminal.completed_monotonic_ns is None
            assert not reopened.list_open_capacity_measurement_operation_attempts_v49f()
        finally:
            if restart_runtime is not None:
                restart_runtime.close()
            harness.owner.abort()
            await harness.server.close()
            if reopened is not None:
                reopened.close()
            else:
                harness.store.close()

    asyncio.run(scenario())

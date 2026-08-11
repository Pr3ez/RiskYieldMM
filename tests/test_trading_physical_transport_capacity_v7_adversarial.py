from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading import physical_transport_capacity_lifecycle_v49f as lifecycle
from riskyieldmm.trading import (
    physical_transport_capacity_measurement_v49f as measurement,
)
from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ClockError,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4VerificationError,
)
from riskyieldmm.trading.physical_transport_actor_journal_v49c import (
    PhysicalTransportActorJournalV49CCapabilityError,
    PhysicalTransportActorJournalV49COwnerError,
    PhysicalTransportActorProjectionJournalV49C,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    TransportActorEventKindV49C,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F,
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F,
    CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F,
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationAttemptV49F,
    CapacityMeasurementOperationPrefixV49F,
    CapacityMeasurementOperationTerminalV49F,
    CapacityMeasurementProjectionReceiptEvidenceV49F,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementArtifactErrorV49F,
    CapacityMeasurementManifestV49FV7,
    CapacityMeasurementSampleV49FV7,
    decode_capacity_measurement_json_v49f_v7,
    decode_capacity_measurement_samples_jsonl_v49f_v7,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
)
from tests.test_trading_physical_transport_capacity_lifecycle_v49f import (
    _attempt,
    _cancel_observation,
    _declaration,
)
from tests.test_trading_physical_transport_capacity_measurement_v7_v49f import (
    _returned_sample,
    _v7_manifest_and_expectation,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy
from tests.test_trading_physical_transport_runtime_v49f_lifecycle import (
    _issue_authorization,
    _wait_for_open_attempt,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only Raw-V7 adversarial tests"
)


class _InjectedLifecycleFault(RuntimeError):
    pass


class _InjectedRollbackFault(RuntimeError):
    pass


def _arm_exact_fault(store: PhysicalProjectionStoreV4, target: str) -> list[str]:
    observed: list[str] = []

    def inject(stage: str) -> None:
        observed.append(stage)
        if stage == target:
            raise _InjectedLifecycleFault(stage)

    store._fault_injector = inject  # noqa: SLF001
    return observed


def _capacity_identity_counts(
    store: PhysicalProjectionStoreV4,
    *,
    attempt_id: str,
    terminal_id: str | None = None,
) -> tuple[int, int, int, int, int]:
    connection = store._connection  # noqa: SLF001
    attempt_blob = bytes.fromhex(attempt_id)
    terminal_blob = None if terminal_id is None else bytes.fromhex(terminal_id)
    canonical_ids = (
        (attempt_blob,)
        if terminal_blob is None
        else (
            attempt_blob,
            terminal_blob,
        )
    )
    placeholders = ",".join("?" for _ in canonical_ids)
    canonical = int(
        connection.execute(
            f"SELECT count(*) FROM canonical_records "  # noqa: S608
            f"WHERE identity_id IN ({placeholders})",
            canonical_ids,
        ).fetchone()[0]
    )
    receipts = int(
        connection.execute(
            f"SELECT count(*) FROM receipts "  # noqa: S608
            f"WHERE identity_id IN ({placeholders})",
            canonical_ids,
        ).fetchone()[0]
    )
    attempts = int(
        connection.execute(
            "SELECT count(*) FROM capacity_measurement_operation_attempts_v49f "
            "WHERE attempt_id = ?",
            (attempt_blob,),
        ).fetchone()[0]
    )
    terminals = int(
        connection.execute(
            "SELECT count(*) FROM capacity_measurement_operation_terminals_v49f "
            "WHERE attempt_id = ?",
            (attempt_blob,),
        ).fetchone()[0]
    )
    locators = int(
        connection.execute(
            "SELECT count(*) FROM capacity_measurement_open_attempts_v49f "
            "WHERE attempt_id = ?",
            (attempt_blob,),
        ).fetchone()[0]
    )
    return canonical, receipts, attempts, terminals, locators


def test_attempt_transaction_faults_leave_only_rollback_or_complete_commit(
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
            receipt_anchor = harness.store._last_receipt()  # noqa: SLF001
            stages = (
                "capacity_attempt_before_canonical_append",
                "after_canonical_record_insert",
                "after_receipt_insert",
                "capacity_attempt_after_canonical_append",
                "capacity_attempt_after_typed_insert",
                "capacity_attempt_after_locator_insert",
                "after_operation_batch_insert",
                "capacity_attempt_after_batch_finish",
                "capacity_attempt_before_commit",
                "before_commit",
            )
            for stage in stages:
                observed = _arm_exact_fault(harness.store, stage)
                with pytest.raises(_InjectedLifecycleFault, match=stage):
                    harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                        attempt,
                        idempotency_key="raw-v7-fault-attempt",
                    )
                assert stage in observed
                assert not harness.store._connection.in_transaction  # noqa: SLF001
                assert harness.store._last_receipt() == receipt_anchor  # noqa: SLF001
                assert _capacity_identity_counts(
                    harness.store, attempt_id=str(attempt.attempt_id)
                ) == (0, 0, 0, 0, 0)
                assert (
                    harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                    == ()
                )
                harness.store.verify()

            def fail_rollback_boundary(stage: str) -> None:
                if stage == "capacity_attempt_before_commit":
                    raise _InjectedLifecycleFault(stage)
                if stage == "capacity_attempt_after_rollback":
                    raise _InjectedRollbackFault(stage)

            harness.store._fault_injector = fail_rollback_boundary  # noqa: SLF001
            with pytest.raises(
                _InjectedRollbackFault, match="capacity_attempt_after_rollback"
            ):
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-fault-attempt",
                )
            assert harness.store._last_receipt() == receipt_anchor  # noqa: SLF001
            assert _capacity_identity_counts(
                harness.store, attempt_id=str(attempt.attempt_id)
            ) == (0, 0, 0, 0, 0)

            harness.store._fault_injector = None  # noqa: SLF001
            committed = (
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-fault-attempt",
                )
            )
            assert committed.attempt == attempt
            assert _capacity_identity_counts(
                harness.store, attempt_id=str(attempt.attempt_id)
            ) == (1, 1, 1, 0, 1)
            harness.store.verify()
        finally:
            harness.store._fault_injector = None  # noqa: SLF001
            await harness.close()

    asyncio.run(scenario())


def test_attempt_after_commit_fault_exposes_one_complete_recoverable_orphan(
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
            _arm_exact_fault(harness.store, "capacity_attempt_after_commit")
            with pytest.raises(
                _InjectedLifecycleFault, match="capacity_attempt_after_commit"
            ):
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-after-commit-attempt",
                )
            harness.store._fault_injector = None  # noqa: SLF001
            assert _capacity_identity_counts(
                harness.store, attempt_id=str(attempt.attempt_id)
            ) == (1, 1, 1, 0, 1)
            assert (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                == (attempt,)
            )
            harness.store.verify()
        finally:
            harness.store._fault_injector = None  # noqa: SLF001
            await harness.close()

    asyncio.run(scenario())


def test_terminal_faults_task_binding_and_one_shot_capability_are_closed(
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
                    idempotency_key="raw-v7-terminal-fault-attempt",
                )
            )
            observation = _cancel_observation(attempt)
            receipt_anchor = harness.store._last_receipt()  # noqa: SLF001
            stages = (
                "capacity_terminal_before_canonical_append",
                "after_canonical_record_insert",
                "after_receipt_insert",
                "capacity_terminal_after_canonical_append",
                "capacity_terminal_after_typed_insert",
                "capacity_terminal_after_locator_delete",
                "after_operation_batch_insert",
                "capacity_terminal_after_batch_finish",
                "capacity_terminal_before_commit",
                "before_commit",
            )
            for stage in stages:
                observed = _arm_exact_fault(harness.store, stage)
                with pytest.raises(_InjectedLifecycleFault, match=stage):
                    harness.store.append_capacity_measurement_operation_terminal_v49f(
                        committed,
                        observation,
                        idempotency_key="raw-v7-terminal-fault",
                    )
                assert stage in observed
                assert harness.store._last_receipt() == receipt_anchor  # noqa: SLF001
                assert _capacity_identity_counts(
                    harness.store,
                    attempt_id=str(attempt.attempt_id),
                ) == (1, 1, 1, 0, 1)
                assert (
                    harness.store.load_capacity_measurement_operation_terminal_v49f(
                        str(attempt.attempt_id)
                    )
                    is None
                )
                harness.store.verify()

            async def migrated_terminal() -> None:
                harness.store.append_capacity_measurement_operation_terminal_v49f(
                    committed,
                    observation,
                    idempotency_key="raw-v7-terminal-fault",
                )

            harness.store._fault_injector = None  # noqa: SLF001
            with pytest.raises(PhysicalProjectionV4ClockError, match="same-task"):
                await asyncio.create_task(migrated_terminal())
            assert _capacity_identity_counts(
                harness.store, attempt_id=str(attempt.attempt_id)
            ) == (1, 1, 1, 0, 1)

            _arm_exact_fault(harness.store, "capacity_terminal_after_commit")
            with pytest.raises(
                _InjectedLifecycleFault, match="capacity_terminal_after_commit"
            ):
                harness.store.append_capacity_measurement_operation_terminal_v49f(
                    committed,
                    observation,
                    idempotency_key="raw-v7-terminal-fault",
                )
            harness.store._fault_injector = None  # noqa: SLF001
            terminal = harness.store.load_capacity_measurement_operation_terminal_v49f(
                str(attempt.attempt_id)
            )
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
            )
            assert _capacity_identity_counts(
                harness.store,
                attempt_id=str(attempt.attempt_id),
                terminal_id=str(terminal.terminal_id),
            ) == (2, 2, 1, 1, 0)

            prefix = harness.store.append_capacity_measurement_operation_terminal_v49f(
                committed,
                observation,
                idempotency_key="raw-v7-terminal-fault",
            )
            assert prefix.terminal == terminal
            assert not (
                harness.store._active_capacity_lifecycle_attempt_capabilities_v49f  # noqa: SLF001
            )
            with pytest.raises(PhysicalProjectionV4ConflictError, match="same-task"):
                harness.store.append_capacity_measurement_operation_terminal_v49f(
                    committed,
                    observation,
                    idempotency_key="raw-v7-terminal-fault",
                )
            conflicting = replace(
                observation,
                observer_end_offset_nanoseconds=(
                    observation.observer_end_offset_nanoseconds + 1
                ),
            )
            with pytest.raises(PhysicalProjectionV4ConflictError, match="same-task"):
                harness.store.append_capacity_measurement_operation_terminal_v49f(
                    committed,
                    conflicting,
                    idempotency_key="raw-v7-terminal-fault",
                )
            harness.store.verify()
        finally:
            harness.store._fault_injector = None  # noqa: SLF001
            await harness.close()

    asyncio.run(scenario())


def test_locator_and_duplicate_terminal_contradictions_fail_closed(
    tmp_path: Path,
) -> None:
    async def missing_locator() -> None:
        harness = await _build_harness(
            tmp_path / "a",
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                attempt,
                idempotency_key="raw-v7-missing-locator",
            )
            harness.store._connection.execute(  # noqa: SLF001
                "DELETE FROM capacity_measurement_open_attempts_v49f "
                "WHERE attempt_id = ?",
                (bytes.fromhex(str(attempt.attempt_id)),),
            )
            harness.store._connection.commit()  # noqa: SLF001
            with pytest.raises(
                PhysicalProjectionV4VerificationError, match="open|locator|terminal"
            ):
                harness.store.verify()
        finally:
            await harness.close()

    async def terminal_with_locator_and_duplicate() -> None:
        harness = await _build_harness(
            tmp_path / "b",
            first_frame=Frame(Opcode.PONG, b"").serialize(mask=False),
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            committed = (
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-terminal-locator-attempt",
                )
            )
            prefix = harness.store.append_capacity_measurement_operation_terminal_v49f(
                committed,
                _cancel_observation(attempt),
                idempotency_key="raw-v7-terminal-locator",
            )
            terminal = prefix.terminal
            assert terminal is not None
            row = harness.store._connection.execute(  # noqa: SLF001
                "SELECT * FROM capacity_measurement_operation_terminals_v49f "
                "WHERE attempt_id = ?",
                (bytes.fromhex(str(attempt.attempt_id)),),
            ).fetchone()
            columns = tuple(
                str(item[1])
                for item in harness.store._connection.execute(  # noqa: SLF001
                    "PRAGMA table_info(capacity_measurement_operation_terminals_v49f)"
                )
            )
            assert row is not None
            duplicate = list(row)
            duplicate[columns.index("terminal_id")] = bytes.fromhex("f" * 64)
            with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
                harness.store._connection.execute(  # noqa: SLF001
                    "INSERT INTO capacity_measurement_operation_terminals_v49f "
                    f"({','.join(columns)}) VALUES "  # noqa: S608
                    f"({','.join('?' for _ in columns)})",
                    tuple(duplicate),
                )
            harness.store._connection.rollback()  # noqa: SLF001

            harness.store._connection.execute(  # noqa: SLF001
                "INSERT INTO capacity_measurement_open_attempts_v49f("
                "transport_session_id, attempt_id, campaign_manifest_id, "
                "operation_sequence, attempt_receipt_sequence) VALUES(?, ?, ?, ?, ?)",
                (
                    bytes.fromhex(attempt.transport_session_id),
                    bytes.fromhex(str(attempt.attempt_id)),
                    bytes.fromhex(attempt.campaign_manifest_id),
                    attempt.operation_sequence,
                    committed.receipt.global_sequence,
                ),
            )
            harness.store._connection.commit()  # noqa: SLF001
            with pytest.raises(
                PhysicalProjectionV4VerificationError, match="open|locator|terminal"
            ):
                harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(missing_locator())
    asyncio.run(terminal_with_locator_and_duplicate())


def test_postmortem_prefix_revalidates_store_session_and_writer_anchors(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            attempt = _attempt(harness, _declaration((b"x",)))
            committed = (
                harness.store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
                    attempt,
                    idempotency_key="raw-v7-postmortem-attempt",
                )
            )
            prefix = harness.store.append_capacity_measurement_operation_terminal_v49f(
                committed,
                _cancel_observation(attempt),
                idempotency_key="raw-v7-postmortem-terminal",
            )
            journal = harness.runtime._transport_actor_journal_v49c  # noqa: SLF001
            assert journal is not None
            harness.owner.abort()
            assert (
                journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                    attempt_id=str(attempt.attempt_id)
                )
                == prefix
            )

            identity = journal._capacity_measurement_store_identity_v49f  # noqa: SLF001
            for index in range(len(identity)):
                changed = list(identity)
                changed[index] = (
                    int(changed[index]) + 1
                    if type(changed[index]) is int
                    else f"{changed[index]}-foreign"
                )
                journal._capacity_measurement_store_identity_v49f = tuple(changed)  # noqa: SLF001
                with pytest.raises(
                    PhysicalTransportActorJournalV49COwnerError,
                    match="identity changed",
                ):
                    journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                        attempt_id=str(attempt.attempt_id)
                    )
                journal._capacity_measurement_store_identity_v49f = identity  # noqa: SLF001

            authority = journal.authority
            for field_name in ("transport_session_id", "writer_fence_token_sha256"):
                original = getattr(authority, field_name)
                object.__setattr__(authority, field_name, "f" * 64)
                try:
                    with pytest.raises(
                        PhysicalTransportActorJournalV49CCapabilityError,
                        match="authority|session",
                    ):
                        journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                            attempt_id=str(attempt.attempt_id)
                        )
                finally:
                    object.__setattr__(authority, field_name, original)
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_repeated_racing_cancellation_commits_one_terminal_and_releases_once(
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
            gate = harness.runtime._transport_admission_gate_v49f  # noqa: SLF001
            assert gate is not None
            before = gate.snapshot()

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
            assert task.cancel("raw-v7-first-cancel")
            assert task.cancel("raw-v7-racing-cancel")
            with pytest.raises(asyncio.CancelledError):
                await task
            assert task.cancelled()
            assert task.cancelling() >= 2

            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id,
                declaration.operation_sequence,
            )
            prefix = harness.store.load_capacity_measurement_operation_prefix_v49f(
                str(attempt.attempt_id)
            )
            assert prefix.terminal is not None
            assert prefix.terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
            )
            assert _capacity_identity_counts(
                harness.store,
                attempt_id=str(attempt.attempt_id),
                terminal_id=str(prefix.terminal.terminal_id),
            ) == (2, 2, 1, 1, 0)
            assert not (
                harness.store._active_capacity_lifecycle_attempt_capabilities_v49f  # noqa: SLF001
            )
            after = gate.snapshot()
            assert after.released_commands == before.released_commands + 1
            assert (
                after.cancelled_before_entry_commands
                == before.cancelled_before_entry_commands
            )
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("fail_after_completed_pong", (False, True))
def test_failure_after_raw_or_completed_output_retains_exact_durable_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_after_completed_pong: bool,
) -> None:
    async def scenario() -> None:
        first_payload = b"first-durable-pong"
        ingress = (
            Frame(Opcode.PING, first_payload).serialize(mask=False)
            + Frame(Opcode.PING, b"second-fails").serialize(mask=False)
            if fail_after_completed_pong
            else Frame(Opcode.PONG, b"").serialize(mask=False)
        )
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            original_parse = harness.owner.parse_next_durable_unit_v49d
            calls = 0

            async def fail_selected_parser_unit() -> Any:
                nonlocal calls
                calls += 1
                if calls == (2 if fail_after_completed_pong else 1):
                    raise RuntimeError("injected Raw-V7 parser boundary failure")
                return await original_parse()

            monkeypatch.setattr(
                harness.owner,
                "parse_next_durable_unit_v49d",
                fail_selected_parser_unit,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id,
                declaration.operation_sequence,
            )
            prefix = harness.store.load_capacity_measurement_operation_prefix_v49f(
                str(attempt.attempt_id)
            )
            terminal = prefix.terminal
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION
            )
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
            )
            assert len(prefix.new_raw_ingress_commits) == 1
            assert prefix.new_raw_ingress_commits[0].raw_ingress_commit_id in {
                raw.raw_ingress_commit_id for raw in prefix.raw_dependencies
            }
            kinds = tuple(event.event_kind for event in prefix.actor_events)
            assert kinds[0] is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            if fail_after_completed_pong:
                assert kinds.count(TransportActorEventKindV49C.PARSER_TRANSITION) == 1
                assert kinds.count(TransportActorEventKindV49C.KERNEL_SEND_RESULT) >= 1
                assert (
                    kinds.count(TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED)
                    == 1
                )
            else:
                assert TransportActorEventKindV49C.PARSER_TRANSITION not in kinds
                assert TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT not in kinds
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_prepared_output_failure_retains_obligation_without_false_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PING, b"prepared-only").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)

            async def fail_before_kernel_attempt(
                self: PhysicalTransportSessionActorV49C,
                **kwargs: Any,
            ) -> Any:
                del self, kwargs
                raise RuntimeError("injected failure after output preparation")

            monkeypatch.setattr(
                PhysicalTransportSessionActorV49C,
                "send_oldest_ciphertext",
                fail_before_kernel_attempt,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            attempt = harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
                declaration.campaign_manifest_id,
                declaration.operation_sequence,
            )
            prefix = harness.store.load_capacity_measurement_operation_prefix_v49f(
                str(attempt.attempt_id)
            )
            terminal = prefix.terminal
            assert terminal is not None
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
            )
            kinds = tuple(event.event_kind for event in prefix.actor_events)
            assert TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED in kinds
            assert TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED in kinds
            assert TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT not in kinds
            assert TransportActorEventKindV49C.KERNEL_SEND_RESULT not in kinds
            assert TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED not in kinds
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def _rehashed_receipt(
    receipt: CapacityMeasurementProjectionReceiptEvidenceV49F,
    **changes: Any,
) -> CapacityMeasurementProjectionReceiptEvidenceV49F:
    values = {
        "ledger_id": receipt.ledger_id,
        "global_sequence": receipt.global_sequence,
        "previous_receipt_hash": receipt.previous_receipt_hash,
        "record_kind": receipt.record_kind,
        "identity_id": receipt.identity_id,
        "content_hash": receipt.content_hash,
        "committed_at": receipt.committed_at,
    }
    values.update(changes)
    values["receipt_hash"] = hashlib.sha256(
        canonical_json_bytes(
            {
                "content_hash": values["content_hash"],
                "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
                "global_sequence": values["global_sequence"],
                "identity_id": values["identity_id"],
                "ledger_id": values["ledger_id"],
                "previous_receipt_hash": values["previous_receipt_hash"],
                "record_kind": values["record_kind"],
            }
        )
    ).hexdigest()
    return CapacityMeasurementProjectionReceiptEvidenceV49F(**values)


@pytest.mark.parametrize(
    "mutation",
    (
        "reordered_actor",
        "dropped_actor",
        "dropped_receipt",
        "reordered_receipt",
        "receipt_sequence_gap",
        "broken_receipt_predecessor",
        "wrong_ledger",
        "foreign_record_splice",
        "raw_substitution",
        "false_prefix_id",
    ),
)
def test_offline_prefix_adversary_cannot_relabel_receipt_complete_evidence(
    mutation: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    prefix = _returned_sample(manifest).recovered_prefix
    changes: dict[str, Any] = {
        "recovered_prefix_id": None,
        "prefix_id": None,
    }
    if mutation == "reordered_actor":
        changes["actor_events"] = tuple(reversed(prefix.actor_events))
    elif mutation == "dropped_actor":
        changes["actor_events"] = prefix.actor_events[:-1]
    elif mutation == "dropped_receipt":
        changes["projection_receipts"] = (
            *prefix.projection_receipts[:2],
            *prefix.projection_receipts[3:],
        )
    elif mutation == "reordered_receipt":
        changes["projection_receipts"] = (
            prefix.projection_receipts[1],
            prefix.projection_receipts[0],
            *prefix.projection_receipts[2:],
        )
    elif mutation == "receipt_sequence_gap":
        receipts = list(prefix.projection_receipts)
        receipts[1] = _rehashed_receipt(
            receipts[1], global_sequence=receipts[1].global_sequence + 1
        )
        changes["projection_receipts"] = tuple(receipts)
    elif mutation == "broken_receipt_predecessor":
        receipts = list(prefix.projection_receipts)
        receipts[1] = _rehashed_receipt(receipts[1], previous_receipt_hash="f" * 64)
        changes["projection_receipts"] = tuple(receipts)
    elif mutation == "wrong_ledger":
        receipts = list(prefix.projection_receipts)
        receipts[0] = _rehashed_receipt(receipts[0], ledger_id="f" * 64)
        changes["projection_receipts"] = tuple(receipts)
    elif mutation == "foreign_record_splice":
        records = list(prefix.projection_records)
        records[1] = records[0]
        changes["projection_records"] = tuple(records)
    elif mutation == "raw_substitution":
        raw = prefix.new_raw_ingress_commits[0]
        substituted = replace(
            raw,
            received_monotonic_ns=raw.received_monotonic_ns + 1,
        )
        changes["new_raw_ingress_commits"] = (substituted,)
        changes["raw_dependencies"] = (substituted,)
    elif mutation == "false_prefix_id":
        changes["prefix_id"] = "f" * 64
    else:  # pragma: no cover - frozen parameter inventory above.
        raise AssertionError(mutation)

    with pytest.raises(CanonicalizationError):
        replace(prefix, **changes)


@pytest.mark.parametrize(
    ("record_type", "array_name", "maximum"),
    (
        (
            CapacityMeasurementOperationAttemptV49F,
            "retained_raw_dependencies",
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_RAW_DEPENDENCIES_V49F,
        ),
        (
            CapacityMeasurementOperationTerminalV49F,
            "exception_class_chain",
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_EXCEPTION_CHAIN_DEPTH_V49F,
        ),
        (
            CapacityMeasurementOperationPrefixV49F,
            "actor_events",
            CAPACITY_MEASUREMENT_LIFECYCLE_MAXIMUM_ACTOR_EVENTS_V49F,
        ),
    ),
)
def test_lifecycle_array_bounds_reject_before_canonical_nested_walk(
    monkeypatch: pytest.MonkeyPatch,
    record_type: type[Any],
    array_name: str,
    maximum: int,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    prefix = _returned_sample(manifest).recovered_prefix
    source = {
        CapacityMeasurementOperationAttemptV49F: prefix.attempt,
        CapacityMeasurementOperationTerminalV49F: prefix.terminal,
        CapacityMeasurementOperationPrefixV49F: prefix,
    }[record_type]
    assert source is not None
    payload = source.as_dict()
    payload[array_name] = [None] * (maximum + 1)
    canonical_walk_started = False
    original = lifecycle._bounded_canonical_bytes  # noqa: SLF001

    def observed_walk(*args: Any, **kwargs: Any) -> bytes:
        nonlocal canonical_walk_started
        canonical_walk_started = True
        return original(*args, **kwargs)

    monkeypatch.setattr(lifecycle, "_bounded_canonical_bytes", observed_walk)
    with pytest.raises(CanonicalizationError, match="bounded JSON array"):
        record_type.from_mapping(payload)
    assert not canonical_walk_started


def test_lifecycle_record_byte_bound_precedes_nested_contract_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    payload = _returned_sample(manifest).attempt.as_dict()
    payload["transport_capacity_policy"] = {"untrusted": "x" * (256 * 1024)}
    nested_policy_parse_started = False
    original = lifecycle.TransportCapacityPolicyV49F.from_mapping

    def observed_policy_parse(raw: Any) -> Any:
        nonlocal nested_policy_parse_started
        nested_policy_parse_started = True
        return original(raw)

    monkeypatch.setattr(
        lifecycle.TransportCapacityPolicyV49F,
        "from_mapping",
        observed_policy_parse,
    )
    with pytest.raises(CanonicalizationError, match="canonical bound"):
        CapacityMeasurementOperationAttemptV49F.from_mapping(payload)
    assert not nested_policy_parse_started


def test_v7_record_and_jsonl_byte_limits_reject_before_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    parse_started = False

    def forbidden_parse(payload: bytes) -> Any:
        nonlocal parse_started
        parse_started = True
        raise AssertionError(payload)

    monkeypatch.setattr(measurement, "strict_json_loads", forbidden_parse)
    monkeypatch.setattr(
        measurement,
        "_measurement_json_record_limit_v49f_v7",
        lambda record_type: 8,
    )
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="bounded"):
        decode_capacity_measurement_json_v49f_v7(
            b"12345678\n",
            record_type=CapacityMeasurementManifestV49FV7,
        )
    assert not parse_started

    monkeypatch.setattr(measurement, "A2M_MAXIMUM_SAMPLES_ARTIFACT_BYTES_V49F", 8)
    with pytest.raises(CapacityMeasurementArtifactErrorV49F, match="bounded"):
        decode_capacity_measurement_samples_jsonl_v49f_v7(
            b"12345678\n",
            manifest=manifest,
        )
    assert not parse_started


def test_v7_serialization_surface_inventory_is_exact_and_versioned() -> None:
    supported = measurement._SUPPORTED_MEASUREMENT_JSON_RECORD_TYPES_V49F_V7  # noqa: SLF001
    assert supported == (
        measurement.CapacityMeasurementManifestV49FV7,
        measurement.CapacityMeasurementObservationV49FV7,
        measurement.CapacityMeasurementSampleV49FV7,
        measurement.CapacityMeasurementCorrectnessV49FV7,
        measurement.CapacityMeasurementArtifactMemberV49FV7,
        measurement.CapacityMeasurementIntegrityV49FV7,
    )
    assert len(supported) == len(set(supported))
    assert all(
        record_type.__module__ == measurement.__name__ for record_type in supported
    )
    assert CapacityMeasurementSampleV49FV7 in supported


@pytest.mark.parametrize(
    "loss_point", ("AFTER_RAW", "AFTER_PREPARED", "AFTER_COMPLETED")
)
def test_startup_recovery_preserves_each_durable_process_loss_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loss_point: str,
) -> None:
    async def scenario() -> None:
        first_payload = b"completed-before-process-loss"
        ingress = (
            Frame(Opcode.PING, first_payload).serialize(mask=False)
            + Frame(Opcode.PING, b"later-parser-fails").serialize(mask=False)
            if loss_point == "AFTER_COMPLETED"
            else Frame(
                Opcode.PING if loss_point == "AFTER_PREPARED" else Opcode.PONG,
                b"prepared" if loss_point == "AFTER_PREPARED" else b"",
            ).serialize(mask=False)
        )
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        reopened: PhysicalProjectionStoreV4 | None = None
        try:
            await _establish_and_activate(harness)
            if loss_point in {"AFTER_RAW", "AFTER_COMPLETED"}:
                original_parse = harness.owner.parse_next_durable_unit_v49d
                calls = 0

                async def fail_parser() -> Any:
                    nonlocal calls
                    calls += 1
                    if calls == (2 if loss_point == "AFTER_COMPLETED" else 1):
                        raise RuntimeError(f"process loss {loss_point}")
                    return await original_parse()

                monkeypatch.setattr(
                    harness.owner,
                    "parse_next_durable_unit_v49d",
                    fail_parser,
                )
            else:

                async def fail_send_before_attempt(
                    self: PhysicalTransportSessionActorV49C,
                    **kwargs: Any,
                ) -> Any:
                    del self, kwargs
                    raise RuntimeError("process loss AFTER_PREPARED")

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "send_oldest_ciphertext",
                    fail_send_before_attempt,
                )

            def lose_terminal(*args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                raise OSError("process lost before same-task terminal persistence")

            monkeypatch.setattr(
                PhysicalTransportActorProjectionJournalV49C,
                "close_capacity_measurement_operation_v49f",
                lose_terminal,
            )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            (attempt,) = (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            )
            open_prefix = harness.store.load_capacity_measurement_operation_prefix_v49f(
                str(attempt.attempt_id)
            )
            assert open_prefix.terminal is None
            open_kinds = tuple(event.event_kind for event in open_prefix.actor_events)
            assert open_kinds[0] is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            if loss_point == "AFTER_RAW":
                assert TransportActorEventKindV49C.PARSER_TRANSITION not in open_kinds
            elif loss_point == "AFTER_PREPARED":
                assert TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED in open_kinds
                assert TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED in open_kinds
                assert TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT not in open_kinds
            else:
                assert (
                    TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                    in open_kinds
                )

            runtime = harness.runtime
            assert runtime._writer_fence_token_sha256 is not None  # noqa: SLF001
            harness.store.release_transport_runtime_writer_fence(
                lease_token_sha256=runtime._writer_fence_token_sha256  # noqa: SLF001
            )
            runtime._writer_fence_token_sha256 = None  # noqa: SLF001
            runtime._writer_fence_generation = None  # noqa: SLF001
            runtime._writer_lease.release()  # noqa: SLF001
            runtime._state = PhysicalTransportRuntimeStateV4.CLOSED  # noqa: SLF001
            store_path = harness.store.path
            store_clock = harness.store._clock  # noqa: SLF001
            harness.store.close()

            reopened = PhysicalProjectionStoreV4(store_path, clock=store_clock)
            reopened.claim_transport_runtime_writer_fence(
                lease_token_sha256="f" * 64,
                holder_id=f"raw-v7-recovery-{loss_point.lower()}",
            )
            capability = reopened._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001
            assert capability.open_attempt_ids == (str(attempt.attempt_id),)
            _arm_exact_fault(reopened, "capacity_terminal_after_commit")
            with pytest.raises(
                _InjectedLifecycleFault, match="capacity_terminal_after_commit"
            ):
                reopened.recover_capacity_measurement_operation_terminal_v49f(
                    capability,
                    str(attempt.attempt_id),
                    idempotency_key=f"raw-v7-recover-{loss_point.lower()}",
                )
            reopened._fault_injector = None  # noqa: SLF001
            recovered = reopened.recover_capacity_measurement_operation_terminal_v49f(
                capability,
                str(attempt.attempt_id),
                idempotency_key=f"raw-v7-recover-{loss_point.lower()}",
            )
            terminal = recovered.terminal
            assert terminal is not None
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
            )
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
            )
            assert (
                recovered.new_raw_ingress_commits == open_prefix.new_raw_ingress_commits
            )
            assert recovered.raw_dependencies == open_prefix.raw_dependencies
            assert recovered.actor_events == open_prefix.actor_events
            with pytest.raises(PhysicalProjectionV4ConflictError, match="snapshot"):
                reopened.recover_capacity_measurement_operation_terminal_v49f(
                    capability,
                    str(attempt.attempt_id),
                    idempotency_key=f"raw-v7-recover-{loss_point.lower()}",
                )
            reopened.complete_capacity_measurement_startup_recovery_v49f(capability)
            assert not reopened.list_open_capacity_measurement_operation_attempts_v49f()
            reopened.verify()
        finally:
            harness.owner.abort()
            await harness.server.close()
            if reopened is not None:
                reopened.close()
            elif not harness.store._closed:  # noqa: SLF001
                harness.store.close()

    asyncio.run(scenario())

from __future__ import annotations

import asyncio
import random
import time
from contextvars import Context
from dataclasses import replace
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    BoundedTransportAdmissionGateV49F,
    TransportAdmissionClosedV49F,
    TransportAdmissionDeadlineExceededV49F,
    TransportAdmissionRejectedV49F,
    TransportAdmissionStateErrorV49F,
    TransportAdmissionTerminalBarrierV49F,
    TransportCapacityPolicyV49F,
    TransportCommandKindV49F,
)


def _policy(*, maximum_queue_wait_milliseconds: int = 1_000):
    reservations = {
        "ingress_reservation_work_units": 64,
        "subscription_dispatch_reservation_work_units": 16,
        "ack_deadline_expiry_reservation_work_units": 1,
        "local_shutdown_reservation_work_units": 8,
    }
    return TransportCapacityPolicyV49F(
        maximum_active_and_waiting_commands=4,
        maximum_reserved_work_units=sum(reservations.values()),
        maximum_queue_wait_milliseconds=maximum_queue_wait_milliseconds,
        **reservations,
    )


async def _wait_until(predicate: Any) -> None:
    for _ in range(1_000):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("asynchronous admission condition did not become true")


def _independent_task(coroutine: Any) -> asyncio.Task[Any]:
    """Model a caller task created outside another command's lease context."""

    return Context().run(asyncio.create_task, coroutine)


def test_capacity_policy_roundtrips_and_closes_exact_singleton_budget() -> None:
    policy = _policy()

    assert TransportCapacityPolicyV49F.from_mapping(policy.as_dict()) == policy
    assert policy.reservation_work_units(TransportCommandKindV49F.INGRESS) == 64
    assert policy.reservation_work_units(TransportCommandKindV49F.LOCAL_SHUTDOWN) == 8

    changed = replace(policy, maximum_queue_wait_milliseconds=999)
    assert changed.policy_id != policy.policy_id

    with pytest.raises(CanonicalizationError, match="exactly one slot"):
        replace(policy, maximum_active_and_waiting_commands=5)
    with pytest.raises(CanonicalizationError, match="every command kind"):
        replace(
            policy, maximum_reserved_work_units=policy.maximum_reserved_work_units + 1
        )

    tampered = policy.as_dict()
    tampered["ingress_reservation_work_units"] += 1
    with pytest.raises(CanonicalizationError, match="work capacity"):
        TransportCapacityPolicyV49F.from_mapping(tampered)

    for field, value, match in (
        ("canonicalization_version", "foreign", "canonicalization version"),
        ("schema_version", "foreign", "schema version"),
        ("policy_id", "0" * 64, "policy ID"),
    ):
        malformed = policy.as_dict()
        malformed[field] = value
        with pytest.raises(CanonicalizationError, match=match):
            TransportCapacityPolicyV49F.from_mapping(malformed)


def test_queue_wait_uses_grant_timestamp_difference_without_float_rounding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        loop = asyncio.get_running_loop()
        admitted_loop_time = 1.0000000009
        started_loop_time = 1.0000000021
        time_calls = 0

        def controlled_loop_time() -> float:
            nonlocal time_calls
            time_calls += 1
            return admitted_loop_time if time_calls == 1 else started_loop_time

        # These exactly controlled values expose the former one-nanosecond
        # disagreement between truncating a float duration and subtracting the
        # two truncated timestamps carried by the grant.
        assert int((started_loop_time - admitted_loop_time) * 1_000_000_000) == 1
        assert (
            int(started_loop_time * 1_000_000_000)
            - int(admitted_loop_time * 1_000_000_000)
            == 2
        )

        with monkeypatch.context() as controlled:
            controlled.setattr(loop, "time", controlled_loop_time)
            async with gate.admit(TransportCommandKindV49F.INGRESS) as grant:
                snapshot = gate.snapshot()
                assert grant.queue_wait_nanoseconds == 2
                assert (
                    snapshot.last_started_queue_wait_nanoseconds
                    == grant.queue_wait_nanoseconds
                )
                assert (
                    snapshot.maximum_observed_queue_wait_nanoseconds
                    == grant.queue_wait_nanoseconds
                )

    asyncio.run(scenario())


def test_fifo_singletons_preserve_order_and_shutdown_closes_epoch() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        entered: list[tuple[int, TransportCommandKindV49F]] = []
        releases = {kind: asyncio.Event() for kind in TransportCommandKindV49F}

        async def worker(kind: TransportCommandKindV49F) -> None:
            async with gate.admit(kind) as grant:
                entered.append((grant.admission_sequence, kind))
                if kind is TransportCommandKindV49F.LOCAL_SHUTDOWN:
                    gate.commit_terminal_barrier(grant)
                await releases[kind].wait()

        tasks: list[asyncio.Task[None]] = []
        for index, kind in enumerate(
            (
                TransportCommandKindV49F.INGRESS,
                TransportCommandKindV49F.SUBSCRIPTION_DISPATCH,
                TransportCommandKindV49F.ACK_DEADLINE_EXPIRY,
                TransportCommandKindV49F.LOCAL_SHUTDOWN,
            )
        ):
            tasks.append(asyncio.create_task(worker(kind)))
            await _wait_until(
                lambda index=index: (
                    gate.snapshot().active_and_waiting_commands == index + 1
                )
            )

        snapshot = gate.snapshot()
        assert snapshot.active_admission_sequence == 1
        assert snapshot.waiting_admission_sequences == (2, 3, 4)
        assert snapshot.terminal_barrier_admission_sequence == 4
        assert not snapshot.terminal_barrier_committed
        assert snapshot.maximum_observed_admitted_commands == 4
        assert (
            snapshot.maximum_observed_reserved_work_units
            == gate.policy.maximum_reserved_work_units
        )

        effects: list[str] = []
        with pytest.raises(TransportAdmissionTerminalBarrierV49F):
            async with gate.admit(TransportCommandKindV49F.INGRESS):
                effects.append("forbidden")
        assert effects == []

        expected = (
            TransportCommandKindV49F.INGRESS,
            TransportCommandKindV49F.SUBSCRIPTION_DISPATCH,
            TransportCommandKindV49F.ACK_DEADLINE_EXPIRY,
            TransportCommandKindV49F.LOCAL_SHUTDOWN,
        )
        for position, kind in enumerate(expected, start=1):
            await _wait_until(lambda position=position: len(entered) == position)
            assert entered[-1] == (position, kind)
            releases[kind].set()

        await asyncio.gather(*tasks)
        snapshot = gate.snapshot()
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        assert snapshot.released_commands == 4
        assert snapshot.terminal_barrier_admission_sequence == 4
        assert snapshot.terminal_barrier_committed

        assert gate.advance_epoch() == 2
        assert gate.snapshot().terminal_barrier_admission_sequence is None

    asyncio.run(scenario())


def test_shutdown_body_failure_before_durable_commit_clears_terminal_barrier() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())

        with pytest.raises(RuntimeError, match="pre-durable validation"):
            async with gate.admit(TransportCommandKindV49F.LOCAL_SHUTDOWN):
                raise RuntimeError("pre-durable validation failed")

        snapshot = gate.snapshot()
        assert snapshot.terminal_barrier_admission_sequence is None
        assert not snapshot.terminal_barrier_committed
        async with gate.admit(TransportCommandKindV49F.INGRESS):
            pass

    asyncio.run(scenario())


def test_duplicate_kind_rejects_without_effect_or_disturbing_active_ticket() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        effects: list[str] = []

        async with gate.admit(TransportCommandKindV49F.INGRESS) as active:

            async def duplicate() -> None:
                async with gate.admit(TransportCommandKindV49F.INGRESS):
                    effects.append("forbidden")

            duplicate_task = _independent_task(duplicate())
            with pytest.raises(TransportAdmissionRejectedV49F, match="one outstanding"):
                await duplicate_task
            snapshot = gate.snapshot()
            assert snapshot.active_admission_sequence == active.admission_sequence
            assert snapshot.active_and_waiting_commands == 1
            assert snapshot.rejected_commands == 1
            assert effects == []

        assert gate.snapshot().released_commands == 1

    asyncio.run(scenario())


def test_waiting_cancellation_removes_only_that_ticket_and_preserves_fifo() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        entered: list[tuple[int, TransportCommandKindV49F]] = []
        release_dispatch = asyncio.Event()

        async def dispatch() -> None:
            async with gate.admit(
                TransportCommandKindV49F.SUBSCRIPTION_DISPATCH
            ) as grant:
                entered.append((grant.admission_sequence, grant.command_kind))
                await release_dispatch.wait()

        async def deadline() -> None:
            async with gate.admit(
                TransportCommandKindV49F.ACK_DEADLINE_EXPIRY
            ) as grant:
                entered.append((grant.admission_sequence, grant.command_kind))

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            dispatch_task = _independent_task(dispatch())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2,)
            )
            deadline_task = _independent_task(deadline())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2, 3)
            )
            deadline_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await deadline_task
            assert gate.snapshot().waiting_admission_sequences == (2,)

        await _wait_until(
            lambda: entered == [(2, TransportCommandKindV49F.SUBSCRIPTION_DISPATCH)]
        )
        release_dispatch.set()
        await dispatch_task
        snapshot = gate.snapshot()
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.cancelled_before_entry_commands == 1
        assert snapshot.released_commands == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_position", [0, 1, 2])
def test_head_middle_and_tail_cancellation_preserve_survivor_sequence(
    cancel_position: int,
) -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        entered: list[int] = []
        kinds = (
            TransportCommandKindV49F.SUBSCRIPTION_DISPATCH,
            TransportCommandKindV49F.ACK_DEADLINE_EXPIRY,
            TransportCommandKindV49F.LOCAL_SHUTDOWN,
        )

        async def worker(kind: TransportCommandKindV49F) -> None:
            async with gate.admit(kind) as grant:
                entered.append(grant.admission_sequence)
                if kind is TransportCommandKindV49F.LOCAL_SHUTDOWN:
                    gate.commit_terminal_barrier(grant)

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            tasks = [_independent_task(worker(kind)) for kind in kinds]
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2, 3, 4)
            )
            tasks[cancel_position].cancel()
            with pytest.raises(asyncio.CancelledError):
                await tasks[cancel_position]

        survivors = [
            task for index, task in enumerate(tasks) if index != cancel_position
        ]
        await asyncio.gather(*survivors)
        expected = [
            sequence
            for index, sequence in enumerate((2, 3, 4))
            if index != cancel_position
        ]
        assert entered == expected
        snapshot = gate.snapshot()
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        assert snapshot.cancelled_before_entry_commands == 1

    asyncio.run(scenario())


def test_cancellation_after_grant_before_context_entry_revokes_grant_once() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        effects: list[str] = []

        async def dispatch() -> None:
            async with gate.admit(TransportCommandKindV49F.SUBSCRIPTION_DISPATCH):
                effects.append("entered")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            task = _independent_task(dispatch())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2,)
            )

        # Releasing INGRESS grants sequence 2 synchronously.  Cancel it before
        # the task is allowed another event-loop turn and enters caller code.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        snapshot = gate.snapshot()
        assert effects == []
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        assert snapshot.cancelled_before_entry_commands == 1

    asyncio.run(scenario())


def test_absolute_queue_deadline_expires_without_caller_effect() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(
            _policy(maximum_queue_wait_milliseconds=10)
        )
        effects: list[str] = []

        async def dispatch() -> None:
            async with gate.admit(TransportCommandKindV49F.SUBSCRIPTION_DISPATCH):
                effects.append("entered")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            task = _independent_task(dispatch())
            with pytest.raises(TransportAdmissionDeadlineExceededV49F):
                await task

        snapshot = gate.snapshot()
        assert effects == []
        assert snapshot.timed_out_commands == 1
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0

    asyncio.run(scenario())


def test_granted_ticket_must_resume_before_absolute_effect_entry_deadline() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(
            _policy(maximum_queue_wait_milliseconds=50)
        )
        effects: list[str] = []

        async def dispatch() -> None:
            async with gate.admit(TransportCommandKindV49F.SUBSCRIPTION_DISPATCH):
                effects.append("forbidden-late-entry")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            task = _independent_task(dispatch())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2,)
            )

        # Releasing INGRESS grants sequence 2 synchronously. Keep this caller
        # on the event-loop thread until the already-granted task's absolute
        # entry deadline is in the past.
        assert gate.snapshot().active_admission_sequence == 2
        time.sleep(0.08)
        with pytest.raises(
            TransportAdmissionDeadlineExceededV49F, match="resumed after"
        ):
            await task

        snapshot = gate.snapshot()
        assert effects == []
        assert snapshot.timed_out_commands == 1
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0

    asyncio.run(scenario())


def test_same_task_and_inherited_context_reentrancy_fail_without_waiting() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        effects: list[str] = []

        async def inherited_child() -> None:
            async with gate.admit(TransportCommandKindV49F.ACK_DEADLINE_EXPIRY):
                effects.append("child-entered")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            with pytest.raises(TransportAdmissionStateErrorV49F, match="reentrant"):
                async with gate.admit(TransportCommandKindV49F.SUBSCRIPTION_DISPATCH):
                    effects.append("same-task-entered")
            child = asyncio.create_task(inherited_child())
            with pytest.raises(TransportAdmissionStateErrorV49F, match="inherited"):
                await child

        assert effects == []
        assert gate.snapshot().active_and_waiting_commands == 0

    asyncio.run(scenario())


def test_close_settles_waiters_but_does_not_cancel_started_work() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        effects: list[str] = []

        async def dispatch() -> None:
            async with gate.admit(TransportCommandKindV49F.SUBSCRIPTION_DISPATCH):
                effects.append("entered")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            queued = _independent_task(dispatch())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2,)
            )
            gate.close()
            with pytest.raises(TransportAdmissionClosedV49F):
                await queued

            async def after_close() -> None:
                async with gate.admit(TransportCommandKindV49F.ACK_DEADLINE_EXPIRY):
                    effects.append("forbidden")

            after_close_task = _independent_task(after_close())
            with pytest.raises(TransportAdmissionClosedV49F):
                await after_close_task

        snapshot = gate.snapshot()
        assert effects == []
        assert snapshot.closed
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        with pytest.raises(TransportAdmissionClosedV49F):
            gate.advance_epoch()

    asyncio.run(scenario())


def test_close_clears_reversible_queued_shutdown_without_false_commit() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())

        async def shutdown() -> None:
            async with gate.admit(TransportCommandKindV49F.LOCAL_SHUTDOWN):
                raise AssertionError("closed shutdown entered caller effects")

        async with gate.admit(TransportCommandKindV49F.INGRESS):
            queued = _independent_task(shutdown())
            await _wait_until(
                lambda: gate.snapshot().waiting_admission_sequences == (2,)
            )
            assert gate.snapshot().terminal_barrier_admission_sequence == 2
            gate.close()
            with pytest.raises(TransportAdmissionClosedV49F):
                await queued
            snapshot = gate.snapshot()
            assert snapshot.terminal_barrier_admission_sequence is None
            assert not snapshot.terminal_barrier_committed

        snapshot = gate.snapshot()
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        assert snapshot.closed_before_entry_commands == 1
        assert snapshot.cancelled_before_entry_commands == 0
        assert snapshot.terminal_barrier_admission_sequence is None
        assert not snapshot.terminal_barrier_committed

    asyncio.run(scenario())


def test_forged_cloned_wrong_task_and_stale_grants_cannot_authorize_effects() -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        retained_grant = None

        async with gate.admit(TransportCommandKindV49F.LOCAL_SHUTDOWN) as grant:
            retained_grant = grant
            forged = replace(
                grant,
                policy_id="0" * 64,
                reservation_work_units=-1,
                started_loop_time_ns=-1,
            )

            with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
                gate.assert_active_grant(
                    replace(grant),
                    expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
                )

            async def cross_task_assert_genuine_grant() -> None:
                gate.assert_active_grant(
                    grant,
                    expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
                )

            task = _independent_task(cross_task_assert_genuine_grant())
            with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
                await task

            async def cross_task_commit_genuine_grant() -> None:
                gate.commit_terminal_barrier(grant)

            task = _independent_task(cross_task_commit_genuine_grant())
            with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
                await task

            async def cross_task_commit_forged_grant() -> None:
                gate.commit_terminal_barrier(forged)

            task = _independent_task(cross_task_commit_forged_grant())
            with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
                await task
            with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
                gate.assert_active_grant(
                    replace(grant, reservation_work_units=-1),
                    expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
                )
            assert not gate.snapshot().terminal_barrier_committed
            gate.commit_terminal_barrier(grant)

        assert retained_grant is not None
        assert gate.snapshot().terminal_barrier_committed
        assert gate.advance_epoch() == 2
        with pytest.raises(TransportAdmissionStateErrorV49F, match="not active"):
            gate.assert_active_grant(
                retained_grant,
                expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", list(TransportCommandKindV49F))
def test_entered_exception_releases_exact_capacity_for_every_kind(
    kind: TransportCommandKindV49F,
) -> None:
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())

        with pytest.raises(RuntimeError, match="caller failed"):
            async with gate.admit(kind):
                raise RuntimeError("caller failed after entry")

        snapshot = gate.snapshot()
        assert snapshot.active_and_waiting_commands == 0
        assert snapshot.reserved_work_units == 0
        assert snapshot.released_commands == 1
        assert snapshot.terminal_barrier_admission_sequence is None
        assert not snapshot.terminal_barrier_committed
        async with gate.admit(TransportCommandKindV49F.INGRESS):
            pass

    asyncio.run(scenario())


def test_fixed_seed_cancellation_stress_preserves_monotonic_entry_and_capacity() -> (
    None
):
    async def scenario() -> None:
        gate = BoundedTransportAdmissionGateV49F(_policy())
        rng = random.Random(49_001)
        entered_sequences: list[int] = []

        async def worker(kind: TransportCommandKindV49F) -> None:
            async with gate.admit(kind) as grant:
                entered_sequences.append(grant.admission_sequence)

        for _ in range(32):
            async with gate.admit(TransportCommandKindV49F.INGRESS) as grant:
                entered_sequences.append(grant.admission_sequence)
                tasks: list[asyncio.Task[None]] = []
                for index, kind in enumerate(
                    (
                        TransportCommandKindV49F.SUBSCRIPTION_DISPATCH,
                        TransportCommandKindV49F.ACK_DEADLINE_EXPIRY,
                        TransportCommandKindV49F.LOCAL_SHUTDOWN,
                    ),
                    start=1,
                ):
                    tasks.append(_independent_task(worker(kind)))
                    await _wait_until(
                        lambda index=index: (
                            len(gate.snapshot().waiting_admission_sequences) == index
                        )
                    )
                cancelled = {index for index in range(len(tasks)) if rng.random() < 0.5}
                for index in cancelled:
                    tasks[index].cancel()
                for index in sorted(cancelled):
                    with pytest.raises(asyncio.CancelledError):
                        await tasks[index]

            await asyncio.gather(
                *(task for index, task in enumerate(tasks) if index not in cancelled)
            )
            snapshot = gate.snapshot()
            assert snapshot.active_and_waiting_commands == 0
            assert snapshot.reserved_work_units == 0
            assert snapshot.terminal_barrier_admission_sequence is None
            assert not snapshot.terminal_barrier_committed

        assert entered_sequences == sorted(entered_sequences)
        assert len(entered_sequences) == len(set(entered_sequences))
        snapshot = gate.snapshot()
        assert snapshot.maximum_observed_admitted_commands == 4
        assert (
            snapshot.maximum_observed_reserved_work_units
            == gate.policy.maximum_reserved_work_units
        )

    asyncio.run(scenario())


def test_gate_rejects_use_from_a_different_event_loop() -> None:
    gate = BoundedTransportAdmissionGateV49F(_policy())

    async def first_loop() -> None:
        async with gate.admit(TransportCommandKindV49F.INGRESS):
            pass

    asyncio.run(first_loop())

    async def second_loop() -> None:
        async with gate.admit(TransportCommandKindV49F.INGRESS):
            pass

    with pytest.raises(TransportAdmissionStateErrorV49F, match="event loops"):
        asyncio.run(second_loop())

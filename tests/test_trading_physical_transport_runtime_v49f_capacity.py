from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportAdmissionRejectedV49F,
    TransportCapacityPolicyV49F,
    TransportCommandKindV49F,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4StateError,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
)
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only V4.9F admission integration tests"
)


def _policy() -> TransportCapacityPolicyV49F:
    return TransportCapacityPolicyV49F(
        maximum_active_and_waiting_commands=4,
        maximum_reserved_work_units=89,
        maximum_queue_wait_milliseconds=2_000,
        ingress_reservation_work_units=64,
        subscription_dispatch_reservation_work_units=16,
        ack_deadline_expiry_reservation_work_units=1,
        local_shutdown_reservation_work_units=8,
    )


async def _wait_until(predicate) -> None:
    for _ in range(2_000):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("runtime admission condition did not become true")


def test_signed_policy_activates_gate_and_predurable_shutdown_failure_does_not_poison(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.policy_id == _policy().policy_id
            assert snapshot.admission_epoch == 1

            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="requires state"
            ):
                await harness.runtime.shutdown_current_v49e(timeout_seconds=2)

            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.terminal_barrier_admission_sequence is None
            assert snapshot.active_and_waiting_commands == 0
            assert snapshot.reserved_work_units == 0
            assert harness.runtime.state is PhysicalTransportRuntimeStateV4.READY

            await _establish_and_activate(harness)
            await harness.runtime.dispatch_subscription_v49c(
                idempotency_key="v49f-after-predurable-shutdown-rejection"
            )
            intent = harness.runtime._intent  # noqa: SLF001
            assert intent is not None
            assert await _read_client_frames(harness, count=1) == (
                (int(Opcode.TEXT), intent.command_bytes),
            )
            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.active_and_waiting_commands == 0
            assert snapshot.released_commands == 2
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_effect_capable_locked_helpers_reject_missing_grant_before_mutation(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
            assert actor is not None
            events_before = actor.events
            tail_before = harness.runtime._retained_ingress_tail_v49d  # noqa: SLF001
            cursor_before = harness.runtime._parser_cursor_v49d  # noqa: SLF001
            snapshot_before = harness.runtime.transport_admission_snapshot_v49f()

            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="cannot bypass"
            ):
                await harness.runtime._process_next_ingress_v49d_locked(  # noqa: SLF001
                    timeout_seconds=1
                )
            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="cannot bypass"
            ):
                await harness.runtime._dispatch_subscription_v49c_locked(  # noqa: SLF001
                    idempotency_key="v49f-direct-bypass"
                )
            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="cannot bypass"
            ):
                await harness.runtime._commit_completed_application_message_v49e_locked(  # noqa: SLF001
                    actor=actor,
                    message=None,
                    parser_event=None,
                    admission_grant_v49f=None,
                    admission_kind_v49f=TransportCommandKindV49F.INGRESS,
                )
            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="cannot bypass"
            ):
                await harness.runtime._dispatch_automatic_protocol_output_v49d_locked(  # noqa: SLF001
                    actor=actor,
                    owner=None,
                    parser_event=None,
                    admission_grant_v49f=None,
                    admission_kind_v49f=TransportCommandKindV49F.INGRESS,
                )
            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="cannot bypass"
            ):
                await harness.runtime._send_local_websocket_close_v49e_locked(  # noqa: SLF001
                    actor=actor,
                    owner=None,
                    command_event=None,
                    driver_evidence_nonce_sha256="0" * 64,
                    admission_grant_v49f=None,
                )

            assert actor.events == events_before
            assert harness.runtime._retained_ingress_tail_v49d is tail_before  # noqa: SLF001
            assert harness.runtime._parser_cursor_v49d is cursor_before  # noqa: SLF001
            assert (
                harness.runtime.transport_admission_snapshot_v49f() == snapshot_before
            )
            assert (
                harness.runtime.state
                is PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
            )

            await harness.runtime.dispatch_subscription_v49c(
                idempotency_key="v49f-authorized-dispatch"
            )
            intent = harness.runtime._intent  # noqa: SLF001
            assert intent is not None
            assert await _read_client_frames(harness, count=1) == (
                (int(Opcode.TEXT), intent.command_bytes),
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_duplicate_ingress_rejects_while_first_ticket_finishes_normally(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
            assert actor is not None

            first = asyncio.create_task(
                harness.runtime.process_next_ingress_v49d(timeout_seconds=5)
            )
            await _wait_until(
                lambda: (
                    (snapshot := harness.runtime.transport_admission_snapshot_v49f())
                    is not None
                    and snapshot.active_command_kind is TransportCommandKindV49F.INGRESS
                )
            )
            events_before_duplicate = actor.events
            tail_before_duplicate = harness.runtime._retained_ingress_tail_v49d  # noqa: SLF001

            with pytest.raises(TransportAdmissionRejectedV49F, match="one outstanding"):
                await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

            assert actor.events == events_before_duplicate
            assert (
                harness.runtime._retained_ingress_tail_v49d  # noqa: SLF001
                is tail_before_duplicate
            )
            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.rejected_commands == 1
            assert snapshot.active_and_waiting_commands == 1

            ping = Frame(Opcode.PING, b"v49f-ping").serialize(mask=False)
            await _push_server_bytes(harness, ping)
            progress = await first
            assert progress.committed_raw_octets == len(ping)
            assert len(progress.raw_ingress_batch_sha256) == 64
            assert progress.admission_policy_id_v49f == _policy().policy_id
            assert progress.admission_epoch_v49f == 1
            assert progress.admission_sequence_v49f == 1
            assert progress.admission_queue_wait_nanoseconds_v49f is not None
            assert progress.admission_command_kind_v49f == "INGRESS"
            assert progress.admission_reservation_work_units_v49f == 64
            assert progress.admission_admitted_loop_time_ns_v49f is not None
            assert progress.admission_started_loop_time_ns_v49f is not None
            assert progress.admission_start_deadline_loop_time_ns_v49f is not None
            assert (
                progress.admission_admitted_loop_time_ns_v49f
                <= progress.admission_started_loop_time_ns_v49f
                <= progress.admission_start_deadline_loop_time_ns_v49f
            )
            assert progress.admission_queue_wait_nanoseconds_v49f == (
                progress.admission_started_loop_time_ns_v49f
                - progress.admission_admitted_loop_time_ns_v49f
            )
            with pytest.raises(CanonicalizationError, match="present together"):
                replace(progress, admission_started_loop_time_ns_v49f=None)
            with pytest.raises(CanonicalizationError, match="requires an INGRESS"):
                replace(progress, admission_command_kind_v49f="LOCAL_SHUTDOWN")
            with pytest.raises(CanonicalizationError, match="queue wait differs"):
                replace(
                    progress,
                    admission_queue_wait_nanoseconds_v49f=(
                        progress.admission_queue_wait_nanoseconds_v49f + 1
                    ),
                )
            with pytest.raises(CanonicalizationError, match="admitted <= started"):
                replace(
                    progress,
                    admission_start_deadline_loop_time_ns_v49f=(
                        progress.admission_started_loop_time_ns_v49f - 1
                    ),
                )
            assert await _read_client_frames(harness, count=1) == (
                (int(Opcode.PONG), b"v49f-ping"),
            )
            snapshot = harness.runtime.transport_admission_snapshot_v49f()
            assert snapshot is not None
            assert snapshot.active_and_waiting_commands == 0
            assert snapshot.reserved_work_units == 0
            boundary = harness.runtime.capacity_measurement_boundary_v49f()
            assert boundary.admission_closed is snapshot.closed
            assert (
                boundary.admission_terminal_barrier_admission_sequence
                == snapshot.terminal_barrier_admission_sequence
            )
            assert (
                boundary.admission_terminal_barrier_committed
                is snapshot.terminal_barrier_committed
            )
            assert (
                boundary.admission_active_admission_sequence
                == snapshot.active_admission_sequence
            )
            assert boundary.admission_active_command_kind is None
            assert (
                boundary.admission_waiting_admission_sequences
                == snapshot.waiting_admission_sequences
            )
            assert boundary.admission_waiting_command_kinds == tuple(
                value.value for value in snapshot.waiting_command_kinds
            )
            assert (
                boundary.admission_oldest_waiting_age_nanoseconds
                == snapshot.oldest_waiting_age_nanoseconds
            )
            assert (
                boundary.admission_reserved_work_units == snapshot.reserved_work_units
            )
            assert (
                boundary.admission_maximum_observed_admitted_commands
                == snapshot.maximum_observed_admitted_commands
            )
            assert (
                boundary.admission_maximum_observed_reserved_work_units
                == snapshot.maximum_observed_reserved_work_units
            )
            assert (
                boundary.admission_last_started_queue_wait_nanoseconds
                == snapshot.last_started_queue_wait_nanoseconds
            )
            assert (
                boundary.admission_maximum_observed_queue_wait_nanoseconds
                == snapshot.maximum_observed_queue_wait_nanoseconds
            )
            assert boundary.admission_released_commands == snapshot.released_commands
            assert boundary.admission_rejected_commands == snapshot.rejected_commands
            assert (
                boundary.admission_duplicate_kind_rejections
                == snapshot.duplicate_kind_rejections
            )
            assert (
                boundary.admission_terminal_barrier_rejections
                == snapshot.terminal_barrier_rejections
            )
            assert (
                boundary.admission_capacity_rejections == snapshot.capacity_rejections
            )
            assert boundary.admission_closed_rejections == snapshot.closed_rejections
            assert boundary.admission_timed_out_commands == snapshot.timed_out_commands
            assert (
                boundary.admission_cancelled_before_entry_commands
                == snapshot.cancelled_before_entry_commands
            )
            assert (
                boundary.admission_closed_before_entry_commands
                == snapshot.closed_before_entry_commands
            )
            with pytest.raises(CanonicalizationError, match="exact boolean"):
                replace(boundary, admission_closed=1)
            with pytest.raises(CanonicalizationError, match="quiescent"):
                replace(
                    boundary,
                    admission_active_admission_sequence=2,
                    admission_active_command_kind="INGRESS",
                )
            with pytest.raises(CanonicalizationError, match="rejection total"):
                replace(
                    boundary,
                    admission_rejected_commands=(
                        boundary.admission_rejected_commands + 1
                    ),
                )
            with pytest.raises(CanonicalizationError, match="last admission queue"):
                replace(
                    boundary,
                    admission_last_started_queue_wait_nanoseconds=(
                        boundary.admission_maximum_observed_queue_wait_nanoseconds + 1
                    ),
                )
            with pytest.raises(
                CanonicalizationError, match="released admissions require"
            ):
                replace(
                    boundary,
                    admission_maximum_observed_admitted_commands=0,
                    admission_maximum_observed_reserved_work_units=0,
                )
        finally:
            await harness.close()

    asyncio.run(scenario())

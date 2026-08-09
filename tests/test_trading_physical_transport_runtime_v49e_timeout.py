from __future__ import annotations

import asyncio
import inspect
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

import riskyieldmm.trading.physical_transport_linux_v4 as linux_transport
from riskyieldmm.trading.physical_projection_v4 import PhysicalRecordKindV4
from riskyieldmm.trading.physical_transport_actor_v49c import (
    AckDeadlineExpiredPayloadV49E,
    TransportActorEventKindV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    TlsWebSocketDriverStateV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
    TransportSessionTerminationV4,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _typed_count,
)
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9E timeout tests"
)


async def _dispatch_subscription(harness: object) -> tuple[object, object, object]:
    await _establish_and_activate(harness)
    window = await harness.runtime.dispatch_subscription_v49c(  # type: ignore[attr-defined]
        idempotency_key="v49e-timeout-subscription"
    )
    intent = harness.runtime._intent  # type: ignore[attr-defined]  # noqa: SLF001
    actor = harness.runtime._transport_session_actor_v49c  # type: ignore[attr-defined]  # noqa: SLF001
    assert intent is not None
    assert type(actor) is PhysicalTransportSessionActorV49C
    assert await _read_client_frames(harness, count=1) == (  # type: ignore[arg-type]
        (int(Opcode.TEXT), intent.command_bytes),
    )
    return window, intent, actor


def _duration_nanoseconds(value: timedelta) -> int:
    return (
        value.days * 86_400 + value.seconds
    ) * 1_000_000_000 + value.microseconds * 1_000


def _deadline_monotonic_ns(window: object, intent: object) -> int:
    return window.dispatch_completed_monotonic_ns + _duration_nanoseconds(  # type: ignore[attr-defined]
        intent.ack_not_after - window.dispatch_completed_at  # type: ignore[attr-defined]
    )


def _install_governed_bracket(
    monkeypatch: pytest.MonkeyPatch,
    harness: object,
    *,
    wall_before: datetime,
    monotonic_before_ns: int,
) -> None:
    """Install one exact 1 us wall/BOOTTIME bracket without sleeping."""

    wall_after = wall_before + timedelta(microseconds=1)
    wall_values: Iterator[datetime] = iter((wall_before, wall_after))
    boottime_values: Iterator[int] = iter(
        (monotonic_before_ns, monotonic_before_ns + 1_000)
    )
    clock = harness.owner._clock  # type: ignore[attr-defined]  # noqa: SLF001
    original_runner = clock._runner  # noqa: SLF001

    def fresh_chrony_runner(argv, **kwargs):
        result = original_runner(argv, **kwargs)
        if argv[-1] == "--version":
            return result
        lines = result.stdout.decode("ascii").splitlines()
        tracking = lines[2].split(",")
        tracking[3] = f"{wall_before.timestamp():.6f}"
        lines[2] = ",".join(tracking)
        return linux_transport.BoundedCommandResultV4(
            returncode=result.returncode,
            stdout=("\n".join(lines) + "\n").encode("ascii"),
            stderr=result.stderr,
        )

    clock._runner = fresh_chrony_runner  # noqa: SLF001
    clock._wall_clock = lambda: next(wall_values)  # noqa: SLF001
    harness.runtime._wall_clock = lambda: wall_after  # type: ignore[attr-defined]  # noqa: SLF001
    harness.store._clock = lambda: wall_after  # type: ignore[attr-defined]  # noqa: SLF001
    monkeypatch.setattr(
        linux_transport,
        "_boottime_ns",
        lambda: next(boottime_values),
    )


def _termination(harness: object) -> TransportSessionTerminationV4:
    row = harness.store._connection.execute(  # type: ignore[attr-defined]  # noqa: SLF001
        """
        SELECT hex(transport_session_termination_id)
        FROM transport_session_terminations
        """
    ).fetchone()
    assert row is not None
    loaded = harness.store._load_record(  # type: ignore[attr-defined]  # noqa: SLF001
        PhysicalRecordKindV4.TRANSPORT_SESSION_TERMINATION,
        str(row[0]).lower(),
    )
    assert type(loaded) is TransportSessionTerminationV4
    return loaded


def test_v49e_timeout_signature_has_no_caller_evidence_seams() -> None:
    assert tuple(
        inspect.signature(PhysicalTransportRuntimeV4.expire_ack_if_due_v49e).parameters
    ) == ("self",)


@pytest.mark.parametrize(
    ("wall_begin_due", "monotonic_begin_due"),
    ((False, True), (True, False)),
)
def test_v49e_timeout_requires_both_governed_bracket_beginnings_due(
    monkeypatch: pytest.MonkeyPatch,
    *,
    wall_begin_due: bool,
    monotonic_begin_due: bool,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-timeout-early-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                window, intent, actor = await _dispatch_subscription(harness)
                deadline_ns = _deadline_monotonic_ns(window, intent)
                events_before = actor.events
                _install_governed_bracket(
                    monkeypatch,
                    harness,
                    wall_before=(
                        intent.ack_not_after
                        if wall_begin_due
                        else intent.ack_not_after - timedelta(microseconds=1)
                    ),
                    monotonic_before_ns=(
                        deadline_ns if monotonic_begin_due else deadline_ns - 1
                    ),
                )

                assert not await harness.runtime.expire_ack_if_due_v49e()

                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )
                assert actor.events == events_before
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
                assert all(
                    event.event_kind
                    is not TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED
                    for event in actor.events
                )
                validate_transport_actor_chain_v49c(actor.events)
                assert harness.store.verify().transport_actor_event_count == len(
                    actor.events
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49e_due_timeout_commits_one_exact_terminal_order_and_aborts_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-timeout-due-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                window, intent, actor = await _dispatch_subscription(harness)
                deadline_ns = _deadline_monotonic_ns(window, intent)
                old_count = len(actor.events)
                _install_governed_bracket(
                    monkeypatch,
                    harness,
                    wall_before=intent.ack_not_after,
                    monotonic_before_ns=deadline_ns,
                )

                assert await harness.runtime.expire_ack_if_due_v49e()

                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                assert harness.runtime.fault_cause == "ACK_DEADLINE_EXPIRED"
                assert harness.owner._closed  # type: ignore[attr-defined]  # noqa: SLF001
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
                assert len(actor.events) == old_count + 2
                deadline_event, terminal_event = actor.events[-2:]
                assert deadline_event.event_kind is (
                    TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED
                )
                assert type(deadline_event.payload) is AckDeadlineExpiredPayloadV49E
                assert deadline_event.payload.outbound_subscription_intent_id == (
                    intent.outbound_subscription_intent_id
                )
                assert deadline_event.payload.ack_not_after == intent.ack_not_after
                assert deadline_event.payload.ack_not_after_monotonic_ns == deadline_ns
                assert terminal_event.event_kind is (
                    TransportActorEventKindV49C.TERMINAL_TRANSITION
                )
                assert type(terminal_event.payload) is TerminalTransitionPayloadV49C
                assert terminal_event.payload.kind is TerminalTransitionKindV49C.TIMEOUT
                assert terminal_event.payload.cause_code == "ACK_DEADLINE_EXPIRED"

                termination = _termination(harness)
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.ACK_TIMEOUT
                )
                assert termination.transport_session_id == (
                    harness.runtime.current_transport_session_id
                )
                termination.verify_signature()
                deadline_sequence = harness.store._connection.execute(  # noqa: SLF001
                    """
                    SELECT source_receipt_sequence
                    FROM transport_actor_events_v49c
                    WHERE transport_actor_event_id = ?
                    """,
                    (bytes.fromhex(deadline_event.transport_actor_event_id),),
                ).fetchone()[0]
                terminal_sequence = harness.store._connection.execute(  # noqa: SLF001
                    """
                    SELECT source_receipt_sequence
                    FROM transport_actor_events_v49c
                    WHERE transport_actor_event_id = ?
                    """,
                    (bytes.fromhex(terminal_event.transport_actor_event_id),),
                ).fetchone()[0]
                termination_sequence = harness.store._connection.execute(  # noqa: SLF001
                    """
                    SELECT source_receipt_sequence
                    FROM transport_session_terminations
                    """
                ).fetchone()[0]
                assert deadline_sequence < terminal_sequence < termination_sequence
                validate_transport_actor_chain_v49c(actor.events)
                report = harness.store.verify()
                assert report.transport_actor_event_count == len(actor.events)
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 1
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49e_actor_bound_sync_timeout_bypass_is_rejected() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-timeout-sync-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                _, _, actor = await _dispatch_subscription(harness)
                events_before = actor.events

                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="cannot bypass the V4.9E actor order",
                ):
                    harness.runtime.expire_ack_if_due()

                assert actor.events == events_before
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49e_lock_admitted_raw_ack_wins_race_and_timeout_cannot_revive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-timeout-race-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                _, intent, actor = await _dispatch_subscription(harness)
                entered_commit = asyncio.Event()
                release_commit = asyncio.Event()
                original = PhysicalTransportSessionActorV49C.commit_completed_application_message_v49e

                async def controlled_commit(self, **kwargs):
                    entered_commit.set()
                    await release_commit.wait()
                    return await original(self, **kwargs)

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "commit_completed_application_message_v49e",
                    controlled_commit,
                )
                raw_ack = json.dumps(
                    {
                        "success": True,
                        "ret_msg": "",
                        "conn_id": "v49e-timeout-race",
                        "req_id": intent.request_id,
                        "op": "subscribe",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                await _push_server_bytes(
                    harness,
                    Frame(Opcode.TEXT, raw_ack).serialize(mask=False),
                )

                ingress_task = asyncio.create_task(
                    harness.runtime.process_next_ingress_v49d(timeout_seconds=1)
                )
                await asyncio.wait_for(entered_commit.wait(), timeout=2)
                timeout_task = asyncio.create_task(
                    harness.runtime.expire_ack_if_due_v49e()
                )
                await asyncio.sleep(0)
                assert not timeout_task.done()
                release_commit.set()
                await ingress_task
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="current state is ACK_BOUND",
                ):
                    await timeout_task

                assert (
                    harness.runtime.state is PhysicalTransportRuntimeStateV4.ACK_BOUND
                )
                assert any(
                    event.event_kind
                    is TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND
                    for event in actor.events
                )
                assert all(
                    event.event_kind
                    is not TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED
                    for event in actor.events
                )
                assert _typed_count(harness.store, "subscription_ack_bindings") == 1
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
                validate_transport_actor_chain_v49c(actor.events)
                assert harness.store.verify().transport_actor_event_count == len(
                    actor.events
                )
            finally:
                await harness.close()

    asyncio.run(scenario())

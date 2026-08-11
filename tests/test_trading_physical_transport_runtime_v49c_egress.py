from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    TransportActorEventKindV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportDispatchUnknownV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    T0,
    _build_harness,
    _establish,
    _typed_count,
)
from tests.test_trading_physical_transport_tls_v49 import _decode_client_frame


def _bind_projection_clock_to_owner(harness: object) -> None:
    store = harness.store  # type: ignore[attr-defined]
    owner = harness.owner  # type: ignore[attr-defined]
    runtime = harness.runtime  # type: ignore[attr-defined]
    cursor = 0

    def causal_wall_clock() -> datetime:
        nonlocal cursor
        cursor += 1
        return T0 + timedelta(seconds=2, microseconds=cursor)

    owner._clock._wall_clock = causal_wall_clock  # noqa: SLF001
    runtime._wall_clock = lambda: T0 + timedelta(seconds=3)  # noqa: SLF001
    store._clock = causal_wall_clock  # noqa: SLF001


def test_v49c_dispatch_signature_exposes_only_intent_idempotency() -> None:
    assert tuple(
        inspect.signature(
            PhysicalTransportRuntimeV4.dispatch_subscription_v49c
        ).parameters
    ) == ("self", "idempotency_key")


def test_v49c_runtime_drives_exact_durable_subscription_over_real_tls13() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-egress-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                assert not harness.runtime.has_initial_pending_raw_ingress_v49c
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()

                window = await harness.runtime.dispatch_subscription_v49c(
                    idempotency_key="v49c-exact-subscription"
                )
                intent = harness.runtime._intent  # noqa: SLF001
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert intent is not None
                assert actor is not None

                frame = await asyncio.wait_for(
                    harness.server.application_reads.get(), timeout=1
                )
                opcode, decoded = _decode_client_frame(frame)
                assert opcode == int(Opcode.TEXT)
                assert decoded == intent.command_bytes
                assert window.outbound_subscription_intent_id == (
                    intent.outbound_subscription_intent_id
                )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )
                assert tuple(event.event_kind for event in actor.events) == (
                    TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                    TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                    TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                    TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                    TransportActorEventKindV49C.TERMINAL_TRANSITION,
                    TransportActorEventKindV49C.KERNEL_SEND_RESULT,
                    TransportActorEventKindV49C.TERMINAL_TRANSITION,
                    TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED,
                )
                validate_transport_actor_chain_v49c(actor.events)
                assert harness.store.verify().transport_actor_event_count == 8
                assert _typed_count(harness.store, "outbound_subscription_intents") == 1
                assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND

                permit = harness.runtime._permit  # noqa: SLF001
                assert permit is not None
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="legacy TEXT dispatch is fenced",
                ):
                    await harness.runtime.dispatch_text(
                        permit,
                        socket_lease_id=permit.socket_lease_id,
                        sender=harness.owner,
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_retained_post_upgrade_ping_blocks_application_before_intent() -> None:
    async def scenario() -> None:
        ping = Frame(Opcode.PING, b"must-answer-first").serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49c-pending-") as directory:
            harness = await _build_harness(Path(directory), first_frame=ping)
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="post-upgrade ingress",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="must-not-authorize-before-pong"
                    )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
                )
                assert _typed_count(harness.store, "outbound_subscription_intents") == 0
                assert harness.store.verify().transport_actor_event_count == 0
                assert harness.server.application_reads.empty()
                assert harness.driver.state is (
                    TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_tls_never_advances_before_atomic_wire_permit_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        actor_insert_count = 0

        def fault(stage: str) -> None:
            nonlocal actor_insert_count
            if stage != "after_transport_actor_event_v49c_insert":
                return
            actor_insert_count += 1
            if actor_insert_count == 2:
                raise RuntimeError("injected wire-permit batch failure")

        with TemporaryDirectory(prefix="ry-v49c-wire-permit-fault-") as directory:
            harness = await _build_harness(
                Path(directory),
                fault_injector=fault,
            )
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                owner_type = type(harness.owner)
                original = owner_type.prepare_tls_ciphertext_v49c
                tls_calls = 0

                async def observed_tls_prepare(self, prepared_wire):
                    nonlocal tls_calls
                    tls_calls += 1
                    return await original(self, prepared_wire)

                monkeypatch.setattr(
                    owner_type,
                    "prepare_tls_ciphertext_v49c",
                    observed_tls_prepare,
                )
                with pytest.raises(
                    PhysicalTransportDispatchUnknownV4,
                    match="no kernel attempt is durable",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-wire-permit-fault"
                    )

                assert actor_insert_count == 2
                assert tls_calls == 0
                assert harness.store.verify().transport_actor_event_count == 0
                assert _typed_count(harness.store, "outbound_subscription_intents") == 1
                assert harness.server.application_reads.empty()
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_tls_journal_failure_retains_only_prior_wire_permit_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        actor_insert_count = 0

        def fault(stage: str) -> None:
            nonlocal actor_insert_count
            if stage != "after_transport_actor_event_v49c_insert":
                return
            actor_insert_count += 1
            if actor_insert_count == 3:
                raise RuntimeError("injected TLS event failure")

        with TemporaryDirectory(prefix="ry-v49c-tls-journal-fault-") as directory:
            harness = await _build_harness(
                Path(directory),
                fault_injector=fault,
            )
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                owner_type = type(harness.owner)
                original = owner_type.prepare_tls_ciphertext_v49c
                tls_calls = 0

                async def observed_tls_prepare(self, prepared_wire):
                    nonlocal tls_calls
                    tls_calls += 1
                    return await original(self, prepared_wire)

                monkeypatch.setattr(
                    owner_type,
                    "prepare_tls_ciphertext_v49c",
                    observed_tls_prepare,
                )
                with pytest.raises(
                    PhysicalTransportDispatchUnknownV4,
                    match="no kernel attempt is durable",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-tls-journal-fault"
                    )

                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                assert tls_calls == 1
                assert actor_insert_count == 3
                assert tuple(event.event_kind for event in actor.events) == (
                    TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                    TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                )
                assert harness.store.verify().transport_actor_event_count == 2
                assert harness.server.application_reads.empty()
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_expired_preflight_durably_fences_and_never_prepares_wire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-expired-preflight-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                runtime = harness.runtime
                original_authorize = runtime._authorize_send_permit_core  # noqa: SLF001

                def authorize_then_jump(*, idempotency_key: str):
                    permit = original_authorize(idempotency_key=idempotency_key)
                    # Collapse only the retained test permit's monotonic
                    # budget; the next governed sample must be outside it.
                    object.__setattr__(
                        permit,
                        "send_not_after_monotonic_ns",
                        permit.issued_monotonic_ns + 1,
                    )
                    return permit

                monkeypatch.setattr(
                    runtime,
                    "_authorize_send_permit_core",
                    authorize_then_jump,
                )
                with pytest.raises(
                    PhysicalTransportDispatchUnknownV4,
                    match="no kernel attempt is durable",
                ):
                    await runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-expired-preflight"
                    )

                assert runtime.state is PhysicalTransportRuntimeStateV4.FENCED, (
                    runtime._fault_cause  # noqa: SLF001
                )
                assert harness.owner._closed  # noqa: SLF001
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
                assert harness.server.application_reads.empty()
                assert harness.store.verify().transport_actor_event_count == 0
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 1
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_concurrent_backpressure_bypass_rejects_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-backpressure-race-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                owner_type = type(harness.owner)
                original_send = owner_type.send_prepared_tls_ciphertext_once_v49c
                entered = asyncio.Event()
                release = asyncio.Event()

                async def blocked_send(self, exact_slice, *, prepared, deadline_ns):
                    entered.set()
                    await release.wait()
                    return await original_send(
                        self,
                        exact_slice,
                        prepared=prepared,
                        deadline_ns=deadline_ns,
                    )

                monkeypatch.setattr(
                    owner_type,
                    "send_prepared_tls_ciphertext_once_v49c",
                    blocked_send,
                )
                task = asyncio.create_task(
                    harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-backpressure-race"
                    )
                )
                await asyncio.wait_for(entered.wait(), timeout=5)
                socket_lease_id = harness.runtime._socket_lease_id  # noqa: SLF001
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                lease = harness.runtime._writer_lease  # noqa: SLF001
                assert socket_lease_id is not None
                assert actor is not None
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.DISPATCHING
                )
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held
                state_before = harness.runtime.state
                actor_events_before = actor.events
                actor_rows_before = _typed_count(
                    harness.store, "transport_actor_events_v49c"
                )
                termination_rows_before = _typed_count(
                    harness.store, "transport_session_terminations"
                )
                fence_before = harness.runtime._writer_fence_token_sha256  # noqa: SLF001

                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="legacy fence_backpressure is fenced.*causal transport actor",
                ):
                    harness.runtime.fence_backpressure(socket_lease_id=socket_lease_id)
                assert harness.runtime.state is state_before
                assert actor.events == actor_events_before
                assert (
                    _typed_count(harness.store, "transport_actor_events_v49c")
                    == actor_rows_before
                )
                assert (
                    _typed_count(harness.store, "transport_session_terminations")
                    == termination_rows_before
                )
                assert (  # noqa: SLF001
                    harness.runtime._writer_fence_token_sha256 == fence_before
                )
                assert harness.runtime._socket_owner is harness.owner  # noqa: SLF001
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held

                release.set()
                window = await task

                assert window.socket_lease_id == socket_lease_id
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held
                assert (
                    _typed_count(harness.store, "transport_session_terminations")
                    == termination_rows_before
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_synchronous_close_bypass_rejects_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-close-race-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                owner_type = type(harness.owner)
                original_send = owner_type.send_prepared_tls_ciphertext_once_v49c
                entered = asyncio.Event()
                release = asyncio.Event()

                async def blocked_send(self, exact_slice, *, prepared, deadline_ns):
                    entered.set()
                    await release.wait()
                    return await original_send(
                        self,
                        exact_slice,
                        prepared=prepared,
                        deadline_ns=deadline_ns,
                    )

                monkeypatch.setattr(
                    owner_type,
                    "send_prepared_tls_ciphertext_once_v49c",
                    blocked_send,
                )
                task = asyncio.create_task(
                    harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-close-race"
                    )
                )
                await asyncio.wait_for(entered.wait(), timeout=5)
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                lease = harness.runtime._writer_lease  # noqa: SLF001
                socket_lease_id = harness.runtime._socket_lease_id  # noqa: SLF001
                assert actor is not None
                assert socket_lease_id is not None
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.DISPATCHING
                )
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held
                state_before = harness.runtime.state
                actor_events_before = actor.events
                actor_rows_before = _typed_count(
                    harness.store, "transport_actor_events_v49c"
                )
                termination_rows_before = _typed_count(
                    harness.store, "transport_session_terminations"
                )
                fence_before = harness.runtime._writer_fence_token_sha256  # noqa: SLF001

                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="legacy close is fenced.*causal transport actor",
                ):
                    harness.runtime.close()
                assert harness.runtime.state is state_before
                assert actor.events == actor_events_before
                assert (
                    _typed_count(harness.store, "transport_actor_events_v49c")
                    == actor_rows_before
                )
                assert (
                    _typed_count(harness.store, "transport_session_terminations")
                    == termination_rows_before
                )
                assert (  # noqa: SLF001
                    harness.runtime._writer_fence_token_sha256 == fence_before
                )
                assert harness.runtime._socket_owner is harness.owner  # noqa: SLF001
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held

                release.set()
                window = await task

                assert window.socket_lease_id == socket_lease_id
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )
                assert not harness.owner._closed  # noqa: SLF001
                assert lease.is_held
                assert (
                    _typed_count(harness.store, "transport_session_terminations")
                    == termination_rows_before
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_activation_failure_clears_in_progress_and_aborts_owner() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-activation-fault-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                harness.runtime._committed_bound_session_v49c = None  # noqa: SLF001
                with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                    await harness.runtime.activate_causal_transport_actor_v49c()

                assert not harness.runtime._transport_actor_activation_v49c_in_progress  # noqa: SLF001
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.owner._closed  # noqa: SLF001
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49c_positive_send_result_storage_failure_aborts_without_replay() -> None:
    async def scenario() -> None:
        actor_insert_count = 0

        def fault(stage: str) -> None:
            nonlocal actor_insert_count
            if stage != "after_transport_actor_event_v49c_insert":
                return
            actor_insert_count += 1
            if actor_insert_count == 6:
                raise RuntimeError("injected positive-result persistence failure")

        with TemporaryDirectory(prefix="ry-v49c-result-fault-") as directory:
            harness = await _build_harness(
                Path(directory),
                fault_injector=fault,
            )
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                with pytest.raises(
                    PhysicalTransportDispatchUnknownV4,
                    match="peer delivery is unknown",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49c-result-fault"
                    )
                intent = harness.runtime._intent  # noqa: SLF001
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert intent is not None
                assert actor is not None
                frame = await asyncio.wait_for(
                    harness.server.application_reads.get(), timeout=1
                )
                opcode, decoded = _decode_client_frame(frame)
                assert opcode == int(Opcode.TEXT)
                assert decoded == intent.command_bytes
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        harness.server.application_reads.get(), timeout=0.1
                    )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
                assert actor.is_fault_latched
                assert tuple(event.event_kind for event in actor.events) == (
                    TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                    TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                    TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                    TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                    TransportActorEventKindV49C.TERMINAL_TRANSITION,
                )
                validate_transport_actor_chain_v49c(actor.events)
                assert actor_insert_count == 6
                assert harness.store.verify().transport_actor_event_count == 5
            finally:
                await harness.close()

    asyncio.run(scenario())

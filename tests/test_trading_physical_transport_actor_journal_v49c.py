from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from riskyieldmm.trading.physical_transport_actor_journal_v49c import (
    PhysicalTransportActorJournalV49CCapabilityError,
    PhysicalTransportActorProjectionJournalV49C,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    TransportActorEventV49C,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
    TransportActorAuthorityV49C,
)
from tests.test_trading_physical_transport_actor_v49c_projection import (
    _parser_event,
    _raw_record,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
)


def test_v49d_actor_raw_api_consumes_real_bridge_capability_without_return() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49d-actor-raw-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                transition = harness.owner._v49b_transition  # noqa: SLF001
                authority = TransportActorAuthorityV49C.from_committed_bound_session(
                    committed_session=committed,
                    handshake_transition=transition,
                )
                bridge = PhysicalTransportActorProjectionJournalV49C.for_test(
                    store=harness.store,
                    authority=authority,
                )
                clock_monotonic_ns = committed.session.handshake_completed_monotonic_ns

                def observation_clock():
                    nonlocal clock_monotonic_ns
                    clock_monotonic_ns += 1
                    return committed.session.handshake_completed_at, clock_monotonic_ns

                actor = await PhysicalTransportSessionActorV49C._restore(  # noqa: SLF001
                    journal=bridge,
                    authority=authority,
                    observation_clock=observation_clock,
                )
                raw = _raw_record(committed)

                assert await actor.commit_and_adopt_raw_ingress_v49d(raw) is None

                assert len(actor.events) == 1
                adopted = actor.events[0]
                assert (
                    adopted.payload.raw_ingress_commit_id == raw.raw_ingress_commit_id
                )
                with pytest.raises(
                    PhysicalTransportActorJournalV49CCapabilityError,
                    match="exact commit capability",
                ):
                    await bridge.resolve_exact_committed_raw_actor_event_v49c(
                        event=adopted
                    )
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_projection_bridge_preserves_exact_raw_capability_and_actor_tail() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-journal-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                transition = harness.owner._v49b_transition  # noqa: SLF001
                authority = TransportActorAuthorityV49C.from_committed_bound_session(
                    committed_session=committed,
                    handshake_transition=transition,
                )
                bridge = PhysicalTransportActorProjectionJournalV49C.for_test(
                    store=harness.store,
                    authority=authority,
                )
                clock_wall = committed.session.handshake_completed_at
                clock_monotonic_ns = committed.session.handshake_completed_monotonic_ns

                def observation_clock():
                    nonlocal clock_wall, clock_monotonic_ns
                    clock_monotonic_ns += 1
                    return clock_wall, clock_monotonic_ns

                actor = await PhysicalTransportSessionActorV49C._restore(  # noqa: SLF001
                    journal=bridge,
                    authority=authority,
                    observation_clock=observation_clock,
                )

                committed_raw = await bridge.append_actor_raw_ingress_v49c(
                    raw=_raw_record(committed)
                )
                clock_wall = committed_raw.receipt.committed_at
                clock_monotonic_ns = committed_raw.event.recorded_monotonic_ns
                copied_event = TransportActorEventV49C.from_mapping(
                    committed_raw.event.as_dict()
                )
                with pytest.raises(
                    PhysicalTransportActorJournalV49CCapabilityError,
                    match="exact commit capability",
                ):
                    await bridge.resolve_exact_committed_raw_actor_event_v49c(
                        event=copied_event
                    )
                assert (
                    await actor.adopt_committed_raw_event(committed_raw.event)
                    is committed_raw.event
                )
                with pytest.raises(
                    PhysicalTransportActorJournalV49CCapabilityError,
                    match="exact commit capability",
                ):
                    await bridge.resolve_exact_committed_raw_actor_event_v49c(
                        event=committed_raw.event
                    )

                parser_event = await actor.append_parser_transition(
                    _parser_event(committed_raw).payload
                )
                prefix = await bridge.read_transport_actor_prefix_v49c(
                    transport_session_id=committed.session.transport_session_id
                )
                assert tuple(item.transport_actor_event_id for item in prefix) == (
                    committed_raw.event.transport_actor_event_id,
                    parser_event.transport_actor_event_id,
                )
                assert harness.store.verify().transport_actor_event_count == 2

                replay_bridge = PhysicalTransportActorProjectionJournalV49C.for_test(
                    store=harness.store,
                    authority=authority,
                )
                replay = await replay_bridge.append_actor_raw_ingress_v49c(
                    raw=_raw_record(committed)
                )
                assert not replay.receipt.is_store_minted
                with pytest.raises(
                    PhysicalTransportActorJournalV49CCapabilityError,
                    match="exact commit capability",
                ):
                    await replay_bridge.resolve_exact_committed_raw_actor_event_v49c(
                        event=replay.event
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())

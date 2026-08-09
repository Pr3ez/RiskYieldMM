from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
)


def test_v49c_activation_binds_one_actor_and_fences_legacy_writers() -> None:
    async def scenario() -> None:
        ping = Frame(Opcode.PING, b"actor-ping").serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49c-runtime-") as directory:
            harness = await _build_harness(
                Path(directory),
                first_frame=ping,
            )
            try:
                committed = await _establish(harness)
                assert harness.runtime.has_initial_pending_raw_ingress_v49c

                result = await harness.runtime.activate_causal_transport_actor_v49c()
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001

                assert result is None
                assert type(actor) is PhysicalTransportSessionActorV49C
                assert actor.authority.transport_session_id == (
                    committed.session.transport_session_id
                )
                assert actor.events == ()
                assert harness.runtime.causal_transport_actor_v49c_active
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="already active",
                ):
                    await harness.runtime.activate_causal_transport_actor_v49c()
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="fenced",
                ):
                    harness.runtime.create_control_mediator()
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="fenced",
                ):
                    harness.runtime.authorize_send_permit(
                        idempotency_key="legacy-must-not-authorize"
                    )
                assert harness.store.verify().transport_actor_event_count == 0
            finally:
                await harness.close()

    asyncio.run(scenario())

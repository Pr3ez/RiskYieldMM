from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
    _typed_count,
)
from tests.test_trading_physical_transport_runtime_v49c_egress import (
    _bind_projection_clock_to_owner,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9E runtime tests"
)


@pytest.mark.parametrize(
    "operation",
    ("terminate_current", "fence_backpressure", "close"),
)
def test_actor_active_legacy_terminal_api_rejects_without_side_effects(
    operation: str,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix=f"ry-v49e-{operation}-seal-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()

                runtime = harness.runtime
                owner = harness.owner
                store = harness.store
                actor = runtime._transport_session_actor_v49c  # noqa: SLF001
                lease = runtime._writer_lease  # noqa: SLF001
                assert actor is not None
                assert (
                    runtime.state is PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
                )
                assert lease.is_held
                assert not owner._closed  # noqa: SLF001

                state_before = runtime.state
                fault_before = runtime.fault_cause
                session_before = runtime._session  # noqa: SLF001
                owner_before = runtime._socket_owner  # noqa: SLF001
                binding_before = runtime._socket_owner_binding  # noqa: SLF001
                lease_id_before = runtime._socket_lease_id  # noqa: SLF001
                fence_token_before = runtime._writer_fence_token_sha256  # noqa: SLF001
                fence_generation_before = runtime._writer_fence_generation  # noqa: SLF001
                actor_events_before = actor.events
                owner_snapshot_before = owner.snapshot()
                terminations_before = _typed_count(
                    store, "transport_session_terminations"
                )
                actor_rows_before = _typed_count(store, "transport_actor_events_v49c")

                def forbidden(*_args: Any, **_kwargs: Any) -> None:
                    raise AssertionError(
                        f"legacy {operation} crossed a sealed side-effect boundary"
                    )

                with pytest.MonkeyPatch.context() as sealed:
                    sealed.setattr(
                        type(store), "append_transport_session_termination", forbidden
                    )
                    sealed.setattr(
                        type(store), "release_transport_runtime_writer_fence", forbidden
                    )
                    sealed.setattr(type(owner), "abort", forbidden)
                    sealed.setattr(type(lease), "release", forbidden)

                    with pytest.raises(
                        PhysicalTransportRuntimeV4StateError,
                        match=rf"legacy {operation} is fenced.*causal transport actor",
                    ):
                        if operation == "terminate_current":
                            runtime.terminate_current(
                                TransportSessionTerminationReasonV4.LOCAL_CLOSE
                            )
                        elif operation == "fence_backpressure":
                            assert lease_id_before is not None
                            runtime.fence_backpressure(socket_lease_id=lease_id_before)
                        else:
                            runtime.close()

                assert runtime.state is state_before
                assert runtime.fault_cause == fault_before
                assert runtime._session is session_before  # noqa: SLF001
                assert runtime._socket_owner is owner_before  # noqa: SLF001
                assert runtime._socket_owner_binding is binding_before  # noqa: SLF001
                assert runtime._socket_lease_id == lease_id_before  # noqa: SLF001
                assert (  # noqa: SLF001
                    runtime._writer_fence_token_sha256 == fence_token_before
                )
                assert (  # noqa: SLF001
                    runtime._writer_fence_generation == fence_generation_before
                )
                assert runtime._transport_session_actor_v49c is actor  # noqa: SLF001
                assert actor.events == actor_events_before
                assert owner.snapshot() == owner_snapshot_before
                assert not owner._closed  # noqa: SLF001
                assert lease.is_held
                assert (
                    _typed_count(store, "transport_session_terminations")
                    == terminations_before
                )
                assert (
                    _typed_count(store, "transport_actor_events_v49c")
                    == actor_rows_before
                )
            finally:
                # The positive actor-owned asynchronous shutdown is deliberately
                # outside this bounded E3 test.  Remove only the test's actor
                # references so the legacy harness can release its private lease.
                harness.runtime._transport_session_actor_v49c = None  # noqa: SLF001
                harness.runtime._transport_actor_journal_v49c = None  # noqa: SLF001
                await harness.close()

    asyncio.run(scenario())

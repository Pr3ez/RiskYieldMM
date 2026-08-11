from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    TransportActorEventKindV49C,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportProviderIntegrityFailureV49E,
    PhysicalTransportRuntimeStateV4,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    TerminalTransitionKindV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    TlsWebSocketDriverStateV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _actor_events,
    _establish_and_activate,
    _push_server_bytes,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9E provider runtime tests"
)


def test_pending_subscribe_near_miss_fences_from_one_atomic_actor_result() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-provider-integrity-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                await harness.runtime.dispatch_subscription_v49c(
                    idempotency_key="v49e-provider-integrity-subscription"
                )
                session = harness.runtime._session  # noqa: SLF001
                intent = harness.runtime._intent  # noqa: SLF001
                assert session is not None and intent is not None

                payload = json.dumps(
                    {
                        "success": True,
                        "ret_msg": "",
                        "conn_id": "runtime-v49e",
                        "req_id": "wrong-request-id",
                        "op": "subscribe",
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                await _push_server_bytes(
                    harness,
                    Frame(Opcode.TEXT, payload).serialize(mask=False),
                )

                with pytest.raises(
                    PhysicalTransportProviderIntegrityFailureV49E,
                    match="non-bindable subscribe response",
                ):
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                assert harness.runtime.fault_cause == (
                    "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
                )
                assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
                events = _actor_events(harness)
                assert events[-2].event_kind is (
                    TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED
                )
                assert events[-1].event_kind is (
                    TransportActorEventKindV49C.TERMINAL_TRANSITION
                )
                assert events[-1].payload.kind is TerminalTransitionKindV49C.FATAL
                assert events[-1].payload.cause_code == (
                    "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
                )

                rows = harness.store._connection.execute(  # noqa: SLF001
                    """
                    SELECT reason, close_code, close_reason_digest
                    FROM transport_session_terminations
                    WHERE transport_session_id = ?
                    """,
                    (bytes.fromhex(session.transport_session_id),),
                ).fetchall()
                assert rows == [
                    (
                        TransportSessionTerminationReasonV4.TRANSPORT_ERROR.value,
                        None,
                        None,
                    )
                ]
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT COUNT(*) FROM subscription_ack_bindings"
                    ).fetchone()[0]
                    == 0
                )
                report = harness.store.verify()
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())

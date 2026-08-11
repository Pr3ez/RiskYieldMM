from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4Error,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    DurableIngressAdoptionV49D,
    ParsedDurableUnitV49D,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _decode_client_frame,
    _raw_record,
)


def _owner_raw(harness, pending):
    session_id = harness.owner._v49b_bound_session_id  # noqa: SLF001
    assert type(session_id) is str
    return replace(
        _raw_record(pending),
        transport_subscription_policy_id=(
            harness.driver.transport_policy.transport_subscription_policy_id
        ),
        transport_session_id=session_id,
    )


def test_v49d_owner_retains_initial_raw_identity_and_hides_capabilities(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        frame = Frame(Opcode.TEXT, b"owner-frame").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=frame)
        try:
            owner = harness.owner
            assert list(
                inspect.signature(owner.read_decrypted_ingress_v49d).parameters
            ) == ["timeout_seconds"]
            assert list(
                inspect.signature(owner.adopt_durable_ingress_v49d).parameters
            ) == ["raw"]
            assert (
                list(inspect.signature(owner.parse_next_durable_unit_v49d).parameters)
                == []
            )

            pending = await owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            assert pending is harness.pending_raw
            assert await owner.read_decrypted_ingress_v49d(timeout_seconds=1) is pending
            assert owner.has_pending_raw_ingress_v49d
            assert owner.durable_ingress_buffer_octets_v49d == 0
            assert harness.fake.application_reads.empty()

            raw = _owner_raw(harness, pending)
            adopted = await owner.adopt_durable_ingress_v49d(raw)
            assert type(adopted) is DurableIngressAdoptionV49D
            assert adopted.raw_ingress_commit_id == raw.raw_ingress_commit_id
            assert adopted.ingress_sequence == pending.ingress_sequence
            assert adopted.adopted_octets == pending.total_octets
            assert adopted.durable_buffer_octets == len(frame)
            assert not owner.has_pending_raw_ingress_v49d

            parsed = await owner.parse_next_durable_unit_v49d()
            assert type(parsed) is ParsedDurableUnitV49D
            assert parsed.consumed_unit == frame
            assert parsed.frame_event is not None
            assert parsed.frame_event.opcode == int(Opcode.TEXT)
            assert parsed.frame_event.payload == b"owner-frame"
            assert parsed.protocol_output_chunks == ()
            assert parsed.remaining_durable_octets == 0
            assert owner.durable_ingress_buffer_octets_v49d == 0
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_owner_preserves_cross_raw_tail_and_holds_automatic_pong(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ping = Frame(Opcode.PING, b"owner-cross-raw").serialize(mask=False)
        split_at = 4
        harness = await _bound_owner(tmp_path, first_frame=ping[:split_at])
        try:
            owner = harness.owner
            first_pending = await owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            await owner.adopt_durable_ingress_v49d(_owner_raw(harness, first_pending))
            assert await owner.parse_next_durable_unit_v49d() is None
            assert owner.durable_ingress_buffer_octets_v49d == split_at

            writer = harness.fake.writers[0]
            writer.write(ping[split_at:])
            await writer.drain()
            second_pending = await owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            assert second_pending is not first_pending
            assert second_pending.ingress_sequence == first_pending.ingress_sequence + 1
            await owner.adopt_durable_ingress_v49d(_owner_raw(harness, second_pending))

            parsed = await owner.parse_next_durable_unit_v49d()
            assert type(parsed) is ParsedDurableUnitV49D
            assert parsed.consumed_unit == ping
            assert parsed.frame_event is not None
            assert parsed.frame_event.opcode == int(Opcode.PING)
            assert parsed.frame_event.payload == b"owner-cross-raw"
            assert len(parsed.protocol_output_chunks) == 1
            opcode, payload = _decode_client_frame(parsed.protocol_output_chunks[0])
            assert opcode == int(Opcode.PONG)
            assert payload == b"owner-cross-raw"
            assert parsed.remaining_durable_octets == 0
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            )
            await asyncio.sleep(0.02)
            assert harness.fake.application_reads.empty()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_owner_rejects_raw_from_another_session_and_fences_authority(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        frame = Frame(Opcode.BINARY, b"wrong-session").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=frame)
        try:
            pending = await harness.owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            wrong_session_raw = _raw_record(pending)
            assert (
                wrong_session_raw.transport_session_id
                != harness.owner._v49b_bound_session_id  # noqa: SLF001
            )
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="retained RAW/session authority",
            ):
                await harness.owner.adopt_durable_ingress_v49d(wrong_session_raw)
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            with pytest.raises(LinuxSocketOwnerV4Error):
                harness.owner.snapshot()
        finally:
            await harness.close()

    asyncio.run(scenario())

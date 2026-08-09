from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4Error,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PreparedTlsCiphertextV49C,
    PreparedWebSocketWireV49C,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v4 import (
    T0,
    _driver_session,
    clock_fixture,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _certificates,
    _connected_socket,
    _decode_client_frame,
    _measured_runtime_artifacts,
    _policy,
    _raw_record,
    _server_context,
    _start_fake_server,
    _trust_store,
    _write_certificates,
)


@dataclass(slots=True)
class _BoundOwnerHarness:
    owner: LinuxSocketOwnerV4
    driver: ExactTlsWebSocketDriverV49
    fake: Any
    pending_raw: Any

    async def close(self) -> None:
        self.owner.abort()
        await self.fake.close()


async def _bound_owner(
    tmp_path: Path,
    *,
    first_frame: bytes = b"",
    bind_evidence: bool = True,
) -> _BoundOwnerHarness:
    clock, _ = clock_fixture(tmp_path)
    wall_values = iter(T0 + timedelta(milliseconds=index) for index in range(256))
    clock._wall_clock = lambda: next(wall_values)  # noqa: SLF001
    material = _certificates()
    ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
    fake = await _start_fake_server(
        _server_context(cert_path, key_path), first_frame=first_frame
    )
    store = _trust_store(ca_path, material)
    runtime_artifacts = _measured_runtime_artifacts(
        tls_trust_store_manifest_id=store.manifest.manifest_id,
        clock_source_policy_manifest_id=clock.policy.manifest_id,
    )
    driver = ExactTlsWebSocketDriverV49.from_measured_authority(
        trust_store=store,
        transport_policy=_policy(),
        runtime_artifacts=runtime_artifacts,
    )
    sock = await _connected_socket(fake.address)
    owner = LinuxSocketOwnerV4._from_v49b_exact_profile_for_test(
        owned_socket=sock,
        governed_clock=clock,
        driver=driver,
    )
    try:
        transition = await owner.establish_v49b_handshake()
        pending = None
        if bind_evidence:
            session = _driver_session(
                owner=owner,
                transition=transition,
                signer=Ed25519CheckpointSigner.generate(),
            )
            pending = owner.bind_committed_v49b_handshake(transition, session)
        return _BoundOwnerHarness(
            owner=owner,
            driver=driver,
            fake=fake,
            pending_raw=pending,
        )
    except BaseException:
        owner.abort()
        await fake.close()
        raise


def _deadline(owner: LinuxSocketOwnerV4) -> int:
    return owner.monotonic_now_ns() + 2_000_000_000


async def _send_all(
    owner: LinuxSocketOwnerV4, prepared: PreparedTlsCiphertextV49C
) -> None:
    offset = 0
    while offset < prepared.ciphertext_octets:
        accepted = await owner.send_prepared_tls_ciphertext_once_v49c(
            prepared.exact_ciphertext[offset:],
            prepared=prepared,
            deadline_ns=_deadline(owner),
        )
        assert 0 < accepted <= prepared.ciphertext_octets - offset
        offset += accepted


def test_owner_staged_text_is_sealed_bound_and_drives_real_tls13(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        payload = b'{"args":["kline.1.BTCUSDT"],"op":"subscribe","req_id":"owner"}'
        try:
            owner = harness.owner
            assert list(
                inspect.signature(owner.prepare_exact_text_wire_v49c).parameters
            ) == ["payload"]
            assert list(
                inspect.signature(
                    owner.send_prepared_tls_ciphertext_once_v49c
                ).parameters
            ) == ["exact_ciphertext_slice", "prepared", "deadline_ns"]

            wire = await owner.prepare_exact_text_wire_v49c(payload)
            assert type(wire) is PreparedWebSocketWireV49C
            assert harness.fake.application_reads.empty()
            prepared = await owner.prepare_tls_ciphertext_v49c(wire)
            assert type(prepared) is PreparedTlsCiphertextV49C
            assert prepared.prepared_wire is wire
            assert harness.fake.application_reads.empty()

            await _send_all(owner, prepared)
            frame = await asyncio.wait_for(
                harness.fake.application_reads.get(), timeout=1
            )
            opcode, decoded = _decode_client_frame(frame)
            assert opcode == int(Opcode.TEXT)
            assert decoded == payload
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            assert owner._v49c_active_prepared_wire is None  # noqa: SLF001
            assert owner._v49c_active_prepared_tls is None  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_owner_automatic_pong_uses_same_sealed_staged_fifo(tmp_path: Path) -> None:
    async def scenario() -> None:
        ping = Frame(Opcode.PING, b"owner-ping").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=ping)
        try:
            assert harness.pending_raw is not None
            parsed = harness.driver.parse_durable_ingress(
                _raw_record(harness.pending_raw)
            )
            assert len(parsed.protocol_output_chunks) == 1
            wire = await harness.owner.prepare_pending_protocol_output_wire_v49c(
                parsed.protocol_output_chunks
            )
            assert wire.logical_opcode == int(Opcode.PONG)
            prepared = await harness.owner.prepare_tls_ciphertext_v49c(wire)
            await _send_all(harness.owner, prepared)

            frame = await asyncio.wait_for(
                harness.fake.application_reads.get(), timeout=1
            )
            opcode, decoded = _decode_client_frame(frame)
            assert opcode == int(Opcode.PONG)
            assert decoded == b"owner-ping"
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_staged_owner_rejects_use_before_committed_v49b_binding(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path, bind_evidence=False)
        try:
            with pytest.raises(LinuxSocketOwnerV4Error, match="committed V4.9B"):
                await harness.owner.prepare_exact_text_wire_v49c(b"subscribe")
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            with pytest.raises(LinuxSocketOwnerV4Error):
                harness.owner.snapshot()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_owner_rejects_copied_wire_identity_and_fences_connection(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            wire = await harness.owner.prepare_exact_text_wire_v49c(b"subscribe")
            copied = object.__new__(PreparedWebSocketWireV49C)
            for field in PreparedWebSocketWireV49C.__dataclass_fields__:
                object.__setattr__(copied, field, getattr(wire, field))
            with pytest.raises(LinuxSocketOwnerV4Error, match="owner-retained"):
                await harness.owner.prepare_tls_ciphertext_v49c(copied)
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            with pytest.raises(LinuxSocketOwnerV4Error):
                harness.owner.snapshot()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_send_cancellation_while_waiting_for_owner_lock_aborts_authority(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        owner = harness.owner
        try:
            wire = await owner.prepare_exact_text_wire_v49c(b"subscribe")
            prepared = await owner.prepare_tls_ciphertext_v49c(wire)
            await owner._io_lock.acquire()  # noqa: SLF001 - adversarial contention
            try:
                task = asyncio.create_task(
                    owner.send_prepared_tls_ciphertext_once_v49c(
                        prepared.exact_ciphertext,
                        prepared=prepared,
                        deadline_ns=_deadline(owner),
                    )
                )
                await asyncio.sleep(0)
                assert not task.done()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                owner._io_lock.release()  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            with pytest.raises(LinuxSocketOwnerV4Error):
                owner.snapshot()
        finally:
            await harness.close()

    asyncio.run(scenario())

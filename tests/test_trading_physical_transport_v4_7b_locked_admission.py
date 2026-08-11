from __future__ import annotations

import asyncio
import socket
import sys
from dataclasses import replace
from datetime import timedelta
from functools import wraps
from itertools import count
from pathlib import Path
from typing import Any

import pytest

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
    PhysicalTransportControlRuntimeStateV4,
    PhysicalTransportControlRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    OutboundControlWritePermitConsumedV4,
)
from riskyieldmm.trading.physical_transport_linux_v4 import LinuxSocketOwnerV4
from tests.test_trading_physical_transport_control_runtime_v4 import (
    FakeJournal as ControlJournal,
)
from tests.test_trading_physical_transport_control_runtime_v4 import wire_prepared
from tests.test_trading_physical_transport_linux_owner_v4 import (
    T0,
    binding_for_owner,
    clock_fixture,
    connected_tcp_pair,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only V4.7B tests"
)


def run_async(function: Any) -> Any:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


class LockedAdmissionRejected(RuntimeError):
    pass


class BlockingRecordingDriver:
    def __init__(self, *, blocked_path: str) -> None:
        self.blocked_path = blocked_path
        self.calls: list[str] = []
        self.entered = {
            "subscription": asyncio.Event(),
            "control": asyncio.Event(),
        }
        self.release = asyncio.Event()

    async def _enter(self, path: str) -> None:
        self.calls.append(path)
        self.entered[path].set()
        if path == self.blocked_path:
            await self.release.wait()

    async def send_exact_text_frame(
        self, owned_socket: socket.socket, payload: bytes
    ) -> None:
        assert owned_socket.fileno() >= 0
        assert payload
        await self._enter("subscription")

    async def submit_permitted_chunks(
        self,
        owned_socket: socket.socket,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        assert owned_socket.fileno() >= 0
        assert permit is not None
        await self._enter("control")
        return sum(len(item) for item in ordered_chunks)


def locked_owner(
    tmp_path: Path, *, blocked_path: str
) -> tuple[LinuxSocketOwnerV4, socket.socket, BlockingRecordingDriver]:
    clock, _ = clock_fixture(tmp_path)
    client, peer = connected_tcp_pair()
    driver = BlockingRecordingDriver(blocked_path=blocked_path)
    owner = LinuxSocketOwnerV4(
        owned_socket=client,
        governed_clock=clock,
        driver=driver,
    )
    return owner, peer, driver


async def invoke_path(
    owner: LinuxSocketOwnerV4,
    path: str,
    *,
    before_driver: Any,
) -> int | None:
    if path == "subscription":
        await owner.send_exact_text_frame(
            b'{"op":"subscribe"}', before_driver=before_driver
        )
        return None
    return await owner.submit_permitted_chunks(
        permit=object(),
        ordered_chunks=(b"masked-control-frame",),
        before_driver=before_driver,
    )


@pytest.mark.parametrize(
    ("first_path", "queued_path", "rejection"),
    (
        ("subscription", "control", "writer fence superseded"),
        ("control", "subscription", "send deadline expired"),
    ),
)
@run_async
async def test_opposite_paths_recheck_admission_only_after_shared_lock(
    tmp_path: Path,
    first_path: str,
    queued_path: str,
    rejection: str,
) -> None:
    owner, peer, driver = locked_owner(tmp_path, blocked_path=first_path)
    first_guard_calls: list[str] = []
    queued_guard_calls: list[str] = []

    def reject_queued_admission() -> None:
        queued_guard_calls.append(rejection)
        raise LockedAdmissionRejected(rejection)

    try:
        first = asyncio.create_task(
            invoke_path(
                owner,
                first_path,
                before_driver=lambda: first_guard_calls.append(first_path),
            )
        )
        await driver.entered[first_path].wait()

        queued = asyncio.create_task(
            invoke_path(
                owner,
                queued_path,
                before_driver=reject_queued_admission,
            )
        )
        await asyncio.sleep(0)

        assert first_guard_calls == [first_path]
        assert queued_guard_calls == []
        assert driver.calls == [first_path]
        assert not queued.done()

        driver.release.set()
        await first
        with pytest.raises(LockedAdmissionRejected, match=rejection):
            await queued

        assert queued_guard_calls == [rejection]
        assert driver.calls == [first_path]
        assert not driver.entered[queued_path].is_set()
    finally:
        owner.abort()
        peer.close()


class FenceAwareControlJournal(ControlJournal):
    def __init__(
        self, *args: Any, expected_fence: tuple[str, int], **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self.expected_fence = expected_fence
        self.reject_fence = False
        self.fence_checks = 0
        self.permit_consumed = asyncio.Event()

    def assert_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, generation: int
    ) -> None:
        assert (lease_token_sha256, generation) == self.expected_fence
        self.fence_checks += 1
        if self.reject_fence:
            raise RuntimeError("writer fence superseded while waiting for I/O lock")

    def consume_outbound_control_write_permit(
        self,
        outbound_control_wire_prepared_id: str,
        *,
        permit_consumed_at: Any,
        permit_consumed_monotonic_ns: int,
        idempotency_key: str,
    ) -> OutboundControlWritePermitConsumedV4:
        permit = super().consume_outbound_control_write_permit(
            outbound_control_wire_prepared_id,
            permit_consumed_at=permit_consumed_at,
            permit_consumed_monotonic_ns=permit_consumed_monotonic_ns,
            idempotency_key=idempotency_key,
        )
        self.permit_consumed.set()
        return permit


@run_async
async def test_bound_control_rechecks_superseded_fence_after_subscription_lock(
    tmp_path: Path,
) -> None:
    owner, peer, driver = locked_owner(tmp_path, blocked_path="subscription")
    clock = owner.governed_clock
    wall_tick = count()
    clock._wall_clock = lambda: (
        T0
        + timedelta(  # noqa: SLF001
            milliseconds=next(wall_tick)
        )
    )
    signer = Ed25519CheckpointSigner.generate()
    binding = binding_for_owner(owner, signer=signer)
    preparation = owner.sample()
    template = wire_prepared("locked-bound-control")
    wire = replace(
        template,
        transport_session_id=binding.transport_session_id,
        socket_lease_id=binding.socket_lease_id,
        connection_generation=binding.connection_generation,
        deployment_bundle_id=binding.deployment_bundle_id,
        writer_fence_token_sha256=binding.writer_fence_token_sha256,
        writer_fence_generation=binding.writer_fence_generation,
        prepared_at=preparation.sampled_at,
        monotonic_clock_domain_id=binding.monotonic_clock_domain_id,
        prepared_monotonic_ns=preparation.monotonic_after_ns,
        send_not_after=preparation.sampled_at + timedelta(seconds=5),
        send_not_after_monotonic_ns=(preparation.monotonic_after_ns + 5_000_000_000),
    )
    events: list[str] = []
    journal = FenceAwareControlJournal(
        (wire,),
        events=events,
        expected_fence=(
            binding.writer_fence_token_sha256,
            binding.writer_fence_generation,
        ),
    )
    mediator = PhysicalTransportControlMediatorV4.from_bound_transport_authority(
        journal=journal,  # type: ignore[arg-type]
        authority=owner,
        binding=binding,
        signer=signer,
    )

    try:
        subscription = asyncio.create_task(
            owner.send_exact_text_frame(
                b'{"op":"subscribe"}', before_driver=lambda: None
            )
        )
        await driver.entered["subscription"].wait()

        control = asyncio.create_task(
            mediator.dispatch_prepared(
                wire,
                socket_lease_id=binding.socket_lease_id,
                connection_generation=binding.connection_generation,
                idempotency_prefix="locked-bound-control",
            )
        )
        await journal.permit_consumed.wait()
        await asyncio.sleep(0)

        assert events == ["permit"]
        assert driver.calls == ["subscription"]
        assert journal.fence_checks == 1
        assert not control.done()

        journal.reject_fence = True
        driver.release.set()
        await subscription
        with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
            await control

        assert journal.fence_checks == 2
        assert events == ["permit"]
        assert driver.calls == ["subscription"]
        assert not driver.entered["control"].is_set()
        assert journal.results == []
        assert mediator.state is (PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED)
    finally:
        owner.abort()
        peer.close()

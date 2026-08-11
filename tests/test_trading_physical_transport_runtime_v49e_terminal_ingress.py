from __future__ import annotations

import asyncio
import hashlib
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownCommandStartedPayloadV49E,
    TerminalIngressFailureKindV49E,
    TerminalIngressFailurePayloadV49E,
    TransportActorEventKindV49C,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
    LinuxSocketOwnerV4Error,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)
from tests.test_trading_physical_transport_runtime_v49e_negative_pair import (
    _assert_one_terminal_pair,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Linux-only exact V4.9E terminal-ingress integration test",
)


def test_terminal_ingress_partial_progress_preserves_exact_owner_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live partial ingress must authorize clocks before durable convergence."""

    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            (1000).to_bytes(2, "big") + b"partial-terminal-ingress",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-terminal-ingress-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                admitted_socket_identity = (
                    harness.owner._initial_snapshot.kernel_socket_identity  # noqa: SLF001
                )

                effect_order: list[tuple[str, Any]] = []
                owner_evidence: list[
                    LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E
                ] = []
                restore_checks: list[str] = []
                force_both_due = False

                original_bind = (
                    LinuxSocketOwnerV4._bind_deadline_expired_after_progress_v49e
                )

                def track_owner_binding(
                    current: LinuxSocketOwnerV4,
                    **kwargs: Any,
                ) -> LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E:
                    evidence = original_bind(current, **kwargs)
                    if current is harness.owner:
                        owner_evidence.append(evidence)
                        effect_order.append(("owner-bound", evidence))
                    return evidence

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "_bind_deadline_expired_after_progress_v49e",
                    track_owner_binding,
                )

                original_authorizer = actor._terminal_clock_authorizer  # noqa: SLF001
                original_terminal_clock = (
                    actor._terminal_observation_batch_clock  # noqa: SLF001
                )
                assert original_authorizer is not None
                assert original_terminal_clock is not None

                def track_exact_authorization(evidence: Any) -> None:
                    effect_order.append(("actor-authorized", evidence))
                    original_authorizer(evidence)

                def terminal_clock(
                    count: int,
                ) -> tuple[tuple[Any, int], ...]:
                    observations = original_terminal_clock(count)
                    effect_order.append(("post-effect-sample", observations))
                    if (
                        any(
                            event.event_kind
                            is TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE
                            for event in actor.events
                        )
                        and not restore_checks
                    ):
                        retained_authorized = (
                            harness.owner._v49e_terminal_actor_clock_authorized  # noqa: SLF001
                        )
                        retained_evidence_ids = set(
                            harness.owner._v49e_terminal_actor_clock_evidence_ids  # noqa: SLF001
                        )
                        assert retained_authorized
                        assert len(retained_evidence_ids) == 1

                        harness.owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
                            events=actor.events
                        )
                        restore_checks.append("same-owner-prefix")

                        harness.owner._v49e_terminal_actor_clock_evidence_ids = {  # noqa: SLF001
                            "0" * 64
                        }
                        with pytest.raises(
                            LinuxSocketOwnerV4Error,
                            match="prior live owner authorization",
                        ):
                            harness.owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
                                events=actor.events
                            )
                        restore_checks.append("wrong-evidence-rejected")

                        harness.owner._v49e_terminal_actor_clock_authorized = False  # noqa: SLF001
                        harness.owner._v49e_terminal_actor_clock_evidence_ids = set()  # noqa: SLF001
                        with pytest.raises(
                            LinuxSocketOwnerV4Error,
                            match="prior live owner authorization",
                        ):
                            harness.owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
                                events=actor.events
                            )
                        restore_checks.append("fresh-owner-state-rejected")

                        harness.owner._v49e_terminal_actor_clock_authorized = (  # noqa: SLF001
                            retained_authorized
                        )
                        harness.owner._v49e_terminal_actor_clock_evidence_ids = (  # noqa: SLF001
                            retained_evidence_ids
                        )

                    if not force_both_due:
                        return observations
                    command_event = actor.local_shutdown_command_event_v49e
                    assert command_event is not None
                    command = command_event.payload
                    assert type(command) is LocalShutdownCommandStartedPayloadV49E
                    return tuple(
                        (command.shutdown_deadline_at, monotonic_ns)
                        for _, monotonic_ns in observations
                    )

                actor._terminal_clock_authorizer = track_exact_authorization  # noqa: SLF001
                actor._terminal_observation_batch_clock = terminal_clock  # noqa: SLF001

                original_recv = ExactTlsWebSocketDriverV49._recv_after_readiness_v49e
                captured_ciphertext_prefixes: list[bytes] = []
                terminal_recv_calls = 0

                async def receive_prefix_then_expire(
                    current: ExactTlsWebSocketDriverV49,
                    owned_socket: Any,
                    *,
                    deadline_ns: int,
                    shutdown_socket_v49e: bool = False,
                ) -> bytes:
                    nonlocal force_both_due, terminal_recv_calls
                    if current is not harness.driver or shutdown_socket_v49e:
                        return await original_recv(
                            current,
                            owned_socket,
                            deadline_ns=deadline_ns,
                            shutdown_socket_v49e=shutdown_socket_v49e,
                        )
                    terminal_recv_calls += 1
                    if terminal_recv_calls == 1:
                        ciphertext = await original_recv(
                            current,
                            owned_socket,
                            deadline_ns=deadline_ns,
                        )
                        assert len(ciphertext) > 1
                        prefix = ciphertext[:1]
                        captured_ciphertext_prefixes.append(prefix)
                        return prefix

                    remaining_seconds = max(
                        0.0,
                        (deadline_ns - time.clock_gettime_ns(time.CLOCK_BOOTTIME))
                        / 1_000_000_000,
                    )
                    await asyncio.sleep(remaining_seconds + 0.01)
                    force_both_due = True
                    command_event = actor.local_shutdown_command_event_v49e
                    assert command_event is not None
                    command = command_event.payload
                    assert type(command) is LocalShutdownCommandStartedPayloadV49E
                    harness.store._clock = (  # noqa: SLF001
                        lambda: command.shutdown_deadline_at
                    )
                    raise TimeoutError("scripted expiry after one ciphertext octet")

                monkeypatch.setattr(
                    ExactTlsWebSocketDriverV49,
                    "_recv_after_readiness_v49e",
                    receive_prefix_then_expire,
                )

                async def send_peer_close_after_local_close() -> tuple[
                    tuple[int, bytes], ...
                ]:
                    frames = await _read_client_frames(harness, count=1)
                    await _push_server_bytes(harness, peer_close)
                    return frames

                peer = asyncio.create_task(send_peer_close_after_local_close())
                termination = await harness.runtime.shutdown_current_v49e(
                    # Projection and authority validation occur under this same
                    # command budget; shorter fixtures can expire before the
                    # retained owner reaches the terminal recv boundary.
                    timeout_seconds=20
                )

                assert await peer == ((int(Opcode.CLOSE), (1000).to_bytes(2, "big")),)
                assert terminal_recv_calls == 2
                assert captured_ciphertext_prefixes == [captured_ciphertext_prefixes[0]]
                assert len(captured_ciphertext_prefixes[0]) == 1
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED

                events = _assert_one_terminal_pair(harness)
                failures = tuple(
                    event
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE
                )
                assert len(failures) == 1
                failure = failures[0].payload
                assert type(failure) is TerminalIngressFailurePayloadV49E
                assert failure.failure_kind is (
                    TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                )
                assert failure.operation == "TERMINAL_CLOSE_INGRESS"
                assert failure.kernel_socket_identity == admitted_socket_identity
                assert failure.ciphertext_octets_received == 1
                assert (
                    failure.ciphertext_sha256
                    == hashlib.sha256(captured_ciphertext_prefixes[0]).hexdigest()
                )

                assert len(owner_evidence) == 1
                exact_evidence = owner_evidence[0]
                assert effect_order[0] == ("owner-bound", exact_evidence)
                assert effect_order[1] == ("actor-authorized", exact_evidence)
                assert effect_order[2][0] == "post-effect-sample"
                assert failure.owner_evidence_id == exact_evidence.owner_evidence_id
                assert failure.driver_evidence_id == exact_evidence.driver_evidence_id
                assert failure.kernel_socket_identity == (
                    exact_evidence.kernel_socket_identity
                )

                expected_driver_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
                        "driver_evidence_nonce_sha256": (
                            failure.driver_evidence_nonce_sha256
                        ),
                        "operation": failure.operation,
                        "deadline_ns": failure.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": (
                            failure.ciphertext_octets_received
                        ),
                        "ciphertext_sha256": failure.ciphertext_sha256,
                    }
                )
                expected_owner_id = sha256_digest(
                    {
                        "domain": ("RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E"),
                        "transport_session_id": actor.authority.transport_session_id,
                        "kernel_socket_identity": admitted_socket_identity,
                        "driver_evidence_nonce_sha256": (
                            failure.driver_evidence_nonce_sha256
                        ),
                        "operation": failure.operation,
                        "deadline_ns": failure.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": (
                            failure.ciphertext_octets_received
                        ),
                        "ciphertext_sha256": failure.ciphertext_sha256,
                        "driver_evidence_id": expected_driver_id,
                    }
                )
                assert failure.driver_evidence_id == expected_driver_id
                assert failure.owner_evidence_id == expected_owner_id
                assert failure.owner_evidence_id != failure.driver_evidence_id
                assert restore_checks == [
                    "same-owner-prefix",
                    "wrong-evidence-rejected",
                    "fresh-owner-state-rejected",
                ]

                terminal = events[-1].payload
                assert type(terminal) is TerminalTransitionPayloadV49C
                assert terminal.kind is TerminalTransitionKindV49C.TIMEOUT
                assert terminal.cause_code == (
                    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                )
            finally:
                await harness.close()

    asyncio.run(scenario())

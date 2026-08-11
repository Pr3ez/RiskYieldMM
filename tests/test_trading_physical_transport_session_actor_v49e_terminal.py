from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    ActorTerminalConvergenceResultV49E,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
    OutboundWireOriginV49C,
    TcpHalfCloseAttemptPayloadV49E,
    TcpHalfCloseResultPayloadV49E,
    TlsCiphertextPreparedPayloadV49C,
    TlsControlCiphertextPreparedPayloadV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TlsShutdownObservationKindV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    derive_local_terminal_command_operation_id_v49e,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4Error,
    OwnerTlsShutdownObservationV49E,
    OwnerUnsendableTlsPostHandshakeOutputV49E,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
    PhysicalTransportSessionActorV49CJournalError,
    PhysicalTransportSessionActorV49CQueueError,
    TransportActorAuthorityV49C,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE,
    OutboundObligationLayerV49C,
    TerminalOutcomeV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    PreparedTlsCiphertextV49C,
    PreparedTlsControlCiphertextV49E,
    PreparedWebSocketWireV49C,
    TlsControlOutputKindV49E,
    TlsShutdownObservationV49E,
    UnsendableTlsPostHandshakeOutputV49E,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    TlsShutdownObservationKindV49E as DriverTlsShutdownObservationKindV49E,
)
from tests.test_trading_physical_transport_actor_v49c_contracts import (
    _automatic_output_prefix,
    _local_terminal_wire_payload,
)
from tests.test_trading_physical_transport_actor_v49e_terminal_contract import (
    AUTHORITY,
    T0,
    _append_control_attempt,
    _append_half_close_attempt,
    _local_control_prepared_prefix,
    _local_tls_accepted_prefix,
    _local_tls_and_half_close_prefix,
    _observe_shutdown,
    _start_tls_operation,
    _terminal,
    _websocket_close_prefix,
)
from tests.test_trading_physical_transport_session_actor_v49c import (
    _raw_event,
    _run_async,
)


def _batch_hash(domain: str, chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": domain,
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _sealed(exact_type: type[Any], **values: Any) -> Any:
    value = object.__new__(exact_type)
    for field in exact_type.__dataclass_fields__:
        object.__setattr__(value, field, values[field])
    return value


class _Clock:
    def __init__(self, events: list[TransportActorEventV49C]) -> None:
        self.wall = (T0 if not events else events[-1].recorded_at) + timedelta(
            seconds=10
        )
        self.monotonic_ns = max(
            1_000,
            0 if not events else events[-1].recorded_monotonic_ns,
        )

    def observation(self) -> tuple[datetime, int]:
        self.wall += timedelta(microseconds=1)
        self.monotonic_ns += 1
        return self.wall, self.monotonic_ns

    def batch(self, count: int) -> tuple[tuple[datetime, int], ...]:
        return tuple(self.observation() for _ in range(count))


class _ScriptedTerminalClock:
    def __init__(self, samples: tuple[tuple[datetime, int], ...]) -> None:
        self.samples = samples
        self.offset = 0
        self.batch_calls: list[int] = []

    def batch(self, count: int) -> tuple[tuple[datetime, int], ...]:
        self.batch_calls.append(count)
        result = self.samples[self.offset : self.offset + count]
        if len(result) != count:
            raise RuntimeError("scripted terminal clock is exhausted")
        self.offset += count
        return result


class _Journal:
    def __init__(self, events: list[TransportActorEventV49C]) -> None:
        self.events = list(events)
        self.fail_next_single = False
        self.fail_next_batch = False
        self.fail_batch_first_kind: TransportActorEventKindV49C | None = None
        self.effect_append_calls = 0
        self.terminal_convergence_calls = 0

    async def read_transport_actor_prefix_v49c(
        self, *, transport_session_id: str
    ) -> tuple[TransportActorEventV49C, ...]:
        expected_session_id = (
            AUTHORITY["transport_session_id"]
            if not self.events
            else self.events[0].transport_session_id
        )
        assert transport_session_id == expected_session_id
        return tuple(self.events)

    async def append_transport_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        self.effect_append_calls += 1
        if self.fail_next_single:
            self.fail_next_single = False
            raise RuntimeError("injected single persistence failure")
        self.events.append(event)
        return event

    async def append_transport_actor_events_v49c(
        self, *, events: tuple[TransportActorEventV49C, ...]
    ) -> tuple[TransportActorEventV49C, ...]:
        self.effect_append_calls += 1
        if self.fail_next_batch:
            self.fail_next_batch = False
            raise RuntimeError("injected batch persistence failure")
        if events[0].event_kind is self.fail_batch_first_kind:
            raise RuntimeError("injected typed batch persistence failure")
        self.events.extend(events)
        return events

    async def converge_actor_terminal_v49e(
        self,
        *,
        terminal_event: TransportActorEventV49C,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        assert signer is not None
        self.terminal_convergence_calls += 1
        self.events.append(terminal_event)
        result = object.__new__(ActorTerminalConvergenceResultV49E)
        object.__setattr__(result, "terminal_event", terminal_event)
        object.__setattr__(
            result,
            "termination",
            SimpleNamespace(transport_session_id=terminal_event.transport_session_id),
        )
        return result


async def _actor(
    events: list[TransportActorEventV49C],
    *,
    clock: _Clock | None = None,
) -> tuple[PhysicalTransportSessionActorV49C, _Journal]:
    journal = _Journal(events)
    retained_clock = _Clock(events) if clock is None else clock
    authority = TransportActorAuthorityV49C._from_event(
        _websocket_close_prefix()[0][0] if not events else events[0]
    )
    actor = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=authority,
        observation_clock=retained_clock.observation,
        observation_batch_clock=retained_clock.batch,
    )
    return actor, journal


def _clean_ready_shutdown_prefix(
    *, include_eof_marker: bool
) -> list[TransportActorEventV49C]:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    _observe_shutdown(
        events,
        state,
        operation_sequence=3,
        observation_sequence=2,
        kind=TlsShutdownObservationKindV49E.TCP_EOF,
        cause_event_id=peer_marker.transport_actor_event_id,
        peer_received=True,
        ciphertext_octets_received=0,
    )
    return events if include_eof_marker else events[:-1]


async def _restored_actor_with_terminal_clock(
    events: list[TransportActorEventV49C],
    terminal_clock: _ScriptedTerminalClock,
) -> tuple[PhysicalTransportSessionActorV49C, _Journal, list[str]]:
    journal = _Journal(events)
    authority = TransportActorAuthorityV49C._from_event(events[0])
    strict_clock_calls: list[str] = []

    def strict_clock() -> tuple[datetime, int]:
        strict_clock_calls.append("single")
        raise AssertionError("strict connected-peer clock must not be sampled")

    def strict_batch(_count: int) -> tuple[tuple[datetime, int], ...]:
        strict_clock_calls.append("batch")
        raise AssertionError("strict connected-peer batch clock must not be sampled")

    actor = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=authority,
        observation_clock=strict_clock,
        observation_batch_clock=strict_batch,
        terminal_observation_batch_clock=terminal_clock.batch,
        terminal_clock_authorizer=lambda _evidence: None,
        terminal_clock_restore_authorizer=lambda _events: None,
    )
    return actor, journal, strict_clock_calls


async def _close_actor_with_tls() -> tuple[
    PhysicalTransportSessionActorV49C,
    _Journal,
]:
    actor, journal = await _actor([_raw_event()])
    command, wire, _, permit = await _authorize_local_close(
        actor,
        _prepared_normal_close(),
    )
    prepared_wire = _prepared_normal_close()
    ciphertext = (b"0123456789",)
    prepared_tls = _sealed(
        PreparedTlsCiphertextV49C,
        outbound_sequence=prepared_wire.outbound_sequence,
        prepared_wire=prepared_wire,
        plaintext_batch_sha256=prepared_wire.wire_batch_sha256,
        plaintext_octets=prepared_wire.wire_octets,
        ordered_ciphertext_chunks=ciphertext,
        ordered_ciphertext_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in ciphertext
        ),
        ciphertext_batch_sha256=_batch_hash(
            "RiskYieldMMActorOrderedTlsCiphertextV4_9C", ciphertext
        ),
        ciphertext_octets=sum(map(len, ciphertext)),
    )
    await actor.prepare_local_close_tls_ciphertext_v49e(
        command,
        wire,
        permit,
        driver_evidence_nonce_sha256=hashlib.sha256(b"test-driver").hexdigest(),
        prepare_effect=lambda **_values: prepared_tls,
        signer=object(),
    )
    return actor, journal


async def _authorize_local_close(
    actor: PhysicalTransportSessionActorV49C,
    prepared: PreparedWebSocketWireV49C,
    *,
    timeout_seconds: int = 60,
) -> tuple[
    TransportActorEventV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    command = await actor.start_local_shutdown_command_v49e(
        timeout_seconds=timeout_seconds
    )
    wire, marker, permit = await actor.authorize_local_websocket_close_v49e(
        command,
        driver_evidence_nonce_sha256=hashlib.sha256(b"test-driver").hexdigest(),
        prepare_effect=lambda **_values: prepared,
        signer=object(),
    )
    return command, wire, marker, permit


async def _start_actor_tls_operation(
    actor: PhysicalTransportSessionActorV49C,
    *,
    purpose: TlsProtocolOperationPurposeV49E,
    cause_event: TransportActorEventV49C,
    driver_evidence_nonce_sha256: str,
) -> TransportActorEventV49C:
    command = actor.local_shutdown_command_event_v49e
    assert type(command) is TransportActorEventV49C
    return await actor.start_tls_protocol_operation_v49e(
        command,
        purpose=purpose,
        cause_event=cause_event,
        driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
    )


def _prepared_normal_close(*, outbound_sequence: int = 1) -> PreparedWebSocketWireV49C:
    payload = (1000).to_bytes(2, "big")
    mask = b"\x01\x02\x03\x04"
    frame = (
        b"\x88\x82"
        + mask
        + bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    )
    return _sealed(
        PreparedWebSocketWireV49C,
        outbound_sequence=outbound_sequence,
        logical_opcode=0x8,
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        logical_payload_octets=len(payload),
        ordered_wire_chunks=(frame,),
        ordered_wire_chunks_sha256=(hashlib.sha256(frame).hexdigest(),),
        wire_batch_sha256=_batch_hash(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", (frame,)
        ),
        wire_octets=len(frame),
    )


def _tls_payload_after_permit(
    wire_event: TransportActorEventV49C,
    permit_event: TransportActorEventV49C,
) -> TlsCiphertextPreparedPayloadV49C:
    wire = wire_event.payload
    permit = permit_event.payload
    ciphertext = (b"0123456789",)
    return TlsCiphertextPreparedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        write_permit_consumed_event_id=permit_event.transport_actor_event_id,
        plaintext_batch_sha256=wire.wire_batch_sha256,
        plaintext_octets=wire.wire_octets,
        ordered_ciphertext_chunks_base64=tuple(
            base64.b64encode(chunk).decode("ascii") for chunk in ciphertext
        ),
        ordered_ciphertext_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in ciphertext
        ),
        ciphertext_batch_sha256=_batch_hash(
            "RiskYieldMMActorOrderedTlsCiphertextV4_9C", ciphertext
        ),
        ciphertext_octets=sum(map(len, ciphertext)),
        prepared_at=permit.consumed_at + timedelta(microseconds=1),
        prepared_monotonic_ns=permit.consumed_monotonic_ns + 1,
    )


def _prepared_tls_control(
    *,
    nonce: str,
    control_sequence: int = 1,
    chunks: tuple[bytes, ...] = (b"local-close-notify",),
) -> PreparedTlsControlCiphertextV49E:
    return _sealed(
        PreparedTlsControlCiphertextV49E,
        control_sequence=control_sequence,
        control_kind=TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY,
        driver_evidence_nonce_sha256=nonce,
        ordered_ciphertext_chunks=chunks,
        ordered_ciphertext_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in chunks
        ),
        ciphertext_batch_sha256=_batch_hash(
            "RiskYieldMMActorOrderedTlsControlCiphertextV4_9E", chunks
        ),
        ciphertext_octets=sum(map(len, chunks)),
        peer_close_notify_received_during_preparation=False,
    )


def _prepared_from_event(
    control_event: TransportActorEventV49C,
) -> PreparedTlsControlCiphertextV49E:
    payload = control_event.payload
    assert type(payload) is TlsControlCiphertextPreparedPayloadV49E
    return _sealed(
        PreparedTlsControlCiphertextV49E,
        control_sequence=payload.control_sequence,
        control_kind=TlsControlOutputKindV49E(payload.control_kind.value),
        driver_evidence_nonce_sha256=payload.driver_evidence_nonce_sha256,
        ordered_ciphertext_chunks=tuple(
            base64.b64decode(chunk, validate=True)
            for chunk in payload.ordered_ciphertext_chunks_base64
        ),
        ordered_ciphertext_chunks_sha256=(payload.ordered_ciphertext_chunks_sha256),
        ciphertext_batch_sha256=payload.ciphertext_batch_sha256,
        ciphertext_octets=payload.ciphertext_octets,
        peer_close_notify_received_during_preparation=(
            payload.peer_close_notify_received_during_preparation
        ),
    )


def _owner_observation(
    *,
    nonce: str,
    kind: TlsShutdownObservationKindV49E,
    sequence: int = 1,
    peer_received: bool | None = None,
) -> OwnerTlsShutdownObservationV49E:
    peer = (
        kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
        if peer_received is None
        else peer_received
    )
    tcp_eof = kind is TlsShutdownObservationKindV49E.TCP_EOF
    driver_kind = DriverTlsShutdownObservationKindV49E(kind.value)
    values = {
        "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
        "observation_sequence": sequence,
        "observation_kind": kind.value,
        "driver_evidence_nonce_sha256": nonce,
        "peer_close_notify_received": peer,
        "tcp_eof_received": tcp_eof,
        "truncated": tcp_eof and not peer,
        "ciphertext_octets_received": 0,
    }
    driver = _sealed(
        TlsShutdownObservationV49E,
        observation_sequence=sequence,
        observation_kind=driver_kind,
        driver_evidence_nonce_sha256=nonce,
        peer_close_notify_received=peer,
        tcp_eof_received=tcp_eof,
        truncated=tcp_eof and not peer,
        ciphertext_octets_received=0,
        observation_id=sha256_digest(values),
    )
    kernel_identity = hashlib.sha256(b"owner-kernel-socket").hexdigest()
    owner_values = {
        "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
        "transport_session_id": AUTHORITY["transport_session_id"],
        "kernel_socket_identity": kernel_identity,
        "driver_observation_id": driver.observation_id,
        "driver_observation_sequence": sequence,
        "driver_observation_kind": driver.observation_kind.value,
    }
    return _sealed(
        OwnerTlsShutdownObservationV49E,
        transport_session_id=AUTHORITY["transport_session_id"],
        kernel_socket_identity=kernel_identity,
        driver_observation=driver,
        owner_observation_id=sha256_digest(owner_values),
    )


def _owner_unsendable_evidence(
    *, nonce: str, ciphertext: bytes
) -> OwnerUnsendableTlsPostHandshakeOutputV49E:
    ciphertext_sha = hashlib.sha256(ciphertext).hexdigest()
    driver_values = {
        "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
        "output_sequence": 1,
        "driver_evidence_nonce_sha256": nonce,
        "ciphertext_sha256": ciphertext_sha,
        "ciphertext_octets": len(ciphertext),
    }
    driver_evidence = _sealed(
        UnsendableTlsPostHandshakeOutputV49E,
        output_sequence=1,
        driver_evidence_nonce_sha256=nonce,
        ciphertext_sha256=ciphertext_sha,
        ciphertext_octets=len(ciphertext),
        unsendable_output_id=sha256_digest(driver_values),
    )
    kernel_identity = hashlib.sha256(b"kernel-socket").hexdigest()
    owner_values = {
        "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
        "transport_session_id": AUTHORITY["transport_session_id"],
        "kernel_socket_identity": kernel_identity,
        "driver_unsendable_output_id": driver_evidence.unsendable_output_id,
        "driver_output_sequence": driver_evidence.output_sequence,
        "driver_evidence_nonce_sha256": nonce,
        "ciphertext_sha256": ciphertext_sha,
        "ciphertext_octets": len(ciphertext),
    }
    return _sealed(
        OwnerUnsendableTlsPostHandshakeOutputV49E,
        transport_session_id=AUTHORITY["transport_session_id"],
        kernel_socket_identity=kernel_identity,
        driver_evidence=driver_evidence,
        owner_unsendable_output_id=sha256_digest(owner_values),
    )


@_run_async
async def test_fixed_local_close_authorization_commits_one_atomic_three_event_batch() -> (
    None
):
    actor, journal = await _actor([])
    prepared = _prepared_normal_close()
    command = await actor.start_local_shutdown_command_v49e(timeout_seconds=60)
    before_authorization = journal.effect_append_calls
    wire, close, permit = await actor.authorize_local_websocket_close_v49e(
        command,
        driver_evidence_nonce_sha256=hashlib.sha256(b"test-driver").hexdigest(),
        prepare_effect=lambda **_values: prepared,
        signer=object(),
    )

    assert journal.effect_append_calls == before_authorization + 1
    assert tuple(event.event_kind for event in (wire, close, permit)) == (
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
    )
    assert type(close.payload) is TerminalTransitionPayloadV49C
    assert close.payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT
    assert wire.payload.wire_origin is (OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND)
    assert wire.payload.source_parser_event_id is None
    assert wire.payload.outbound_operation_id == (
        derive_local_terminal_command_operation_id_v49e(
            transport_session_id=wire.transport_session_id,
            actor_predecessor_event_id=wire.previous_event_id,
            logical_payload_sha256=wire.payload.logical_payload_sha256,
            logical_payload_octets=wire.payload.logical_payload_octets,
            ordered_wire_chunks_sha256=wire.payload.ordered_wire_chunks_sha256,
            wire_batch_sha256=wire.payload.wire_batch_sha256,
            wire_octets=wire.payload.wire_octets,
        )
    )


@_run_async
async def test_local_close_operation_identity_ignores_unpersisted_driver_sequence() -> (
    None
):
    first_actor, _ = await _actor([])
    second_actor, _ = await _actor([])

    _, first_wire, _, _ = await _authorize_local_close(
        first_actor,
        _prepared_normal_close(outbound_sequence=1),
    )
    _, second_wire, _, _ = await _authorize_local_close(
        second_actor,
        _prepared_normal_close(outbound_sequence=999),
    )

    assert first_wire.payload.outbound_operation_id == (
        second_wire.payload.outbound_operation_id
    )


@_run_async
async def test_local_close_cannot_bypass_pending_automatic_output() -> None:
    events, _, _ = _automatic_output_prefix()
    actor, journal = await _actor(events)
    before = tuple(journal.events)

    with pytest.raises(
        PhysicalTransportSessionActorV49CQueueError,
        match="quiescent OPEN",
    ):
        await _authorize_local_close(
            actor,
            _prepared_normal_close(),
        )

    assert tuple(journal.events) == before


@_run_async
async def test_generic_wire_append_rejects_local_terminal_command() -> None:
    actor, journal = await _actor([])

    with pytest.raises(
        PhysicalTransportSessionActorV49CQueueError,
        match="requires atomic V4.9E authorization",
    ):
        await actor.prepare_outbound_wire(_local_terminal_wire_payload([]))

    assert journal.events == []


@_run_async
async def test_local_close_deadline_expiry_requires_due_owner_clock_and_typed_api() -> (
    None
):
    clock = _Clock([])
    actor, journal = await _actor([], clock=clock)
    command, _, _, _ = await _authorize_local_close(
        actor,
        _prepared_normal_close(),
    )
    command_payload = command.payload
    clock.wall = command_payload.shutdown_deadline_at - timedelta(microseconds=2)
    clock.monotonic_ns = command_payload.shutdown_deadline_monotonic_ns - 2
    before = tuple(journal.events)

    with pytest.raises(
        PhysicalTransportSessionActorV49CQueueError,
        match="dedicated owner-clock API",
    ):
        await actor.converge_terminal_v49e(
            TerminalTransitionKindV49C.TIMEOUT,
            cause_code=V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
            signer=object(),
        )
    with pytest.raises(
        PhysicalTransportSessionActorV49CQueueError,
        match="wall and BOOTTIME deadlines are not due",
    ):
        await actor.expire_local_websocket_close_deadline_v49e(signer=object())
    assert tuple(journal.events) == before

    result = await actor.expire_local_websocket_close_deadline_v49e(signer=object())

    assert result.terminal_event.recorded_monotonic_ns >= (
        command_payload.shutdown_deadline_monotonic_ns
    )
    assert result.terminal_event.payload.kind is TerminalTransitionKindV49C.TIMEOUT
    assert result.terminal_event.payload.cause_code == (
        V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
    )
    assert actor.terminal_state.terminal_outcome is TerminalOutcomeV49C.TIMEOUT


@_run_async
async def test_close_send_effect_failure_converges_signed_unknown_pair() -> None:
    actor, journal = await _close_actor_with_tls()
    effect_calls = 0

    def fail_after_attempt(_ciphertext: bytes, **_values: Any) -> int:
        nonlocal effect_calls
        effect_calls += 1
        raise RuntimeError("injected Close send failure")

    with pytest.raises(RuntimeError, match="Close send failure"):
        await actor.send_oldest_ciphertext(
            send_effect=fail_after_attempt,
            terminal_signer=object(),
        )

    assert effect_calls == 1
    assert journal.terminal_convergence_calls == 1
    final = journal.events[-1].payload
    assert type(final) is TerminalTransitionPayloadV49C
    assert final.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
    assert actor.terminal_state.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND


@_run_async
async def test_close_result_persistence_failure_is_storage_uncertainty_not_final() -> (
    None
):
    actor, journal = await _close_actor_with_tls()
    journal.fail_batch_first_kind = TransportActorEventKindV49C.KERNEL_SEND_RESULT
    effect_calls = 0

    def accept_once(ciphertext: bytes, **_values: Any) -> int:
        nonlocal effect_calls
        effect_calls += 1
        return len(ciphertext)

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.send_oldest_ciphertext(
            send_effect=accept_once,
            terminal_signer=object(),
        )

    assert effect_calls == 1
    assert journal.terminal_convergence_calls == 0
    tail = journal.events[-1].payload
    assert type(tail) is TerminalTransitionPayloadV49C
    assert tail.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED
    assert not actor.terminal_state.is_terminal
    assert actor.is_fault_latched


@_run_async
async def test_close_send_without_terminal_signer_is_rejected_before_attempt() -> None:
    actor, journal = await _close_actor_with_tls()
    before = len(journal.events)

    with pytest.raises(PhysicalTransportSessionActorV49CQueueError, match="signer"):
        await actor.send_oldest_ciphertext(
            send_effect=lambda ciphertext, **_values: len(ciphertext)
        )

    assert len(journal.events) == before


@_run_async
async def test_prepared_artifact_persistence_failure_is_not_driver_failure() -> None:
    events, _state, ws_accepted = _websocket_close_prefix()
    actor, journal = await _actor(events)
    nonce = hashlib.sha256(b"prep-storage-boundary").hexdigest()
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event=actor.events[ws_accepted.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )
    prepared = _prepared_tls_control(nonce=nonce)
    journal.fail_next_batch = True

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.complete_tls_control_preparation_v49e(
            operation,
            prepare_effect=lambda **_values: prepared,
            signer=object(),
        )

    assert journal.events[-1] is operation
    assert not any(
        type(event.payload) is TlsProtocolOperationFailedPayloadV49E
        for event in journal.events
    )
    assert journal.terminal_convergence_calls == 0


@_run_async
async def test_observation_persistence_failure_is_not_driver_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, _state, fin_marker, _control = _local_tls_and_half_close_prefix()
    actor, journal = await _actor(events)
    nonce = next(
        event.payload.driver_evidence_nonce_sha256
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
    )
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event=actor.events[fin_marker.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )
    observation = _owner_observation(
        nonce=nonce,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
    )
    monkeypatch.setattr(
        OwnerTlsShutdownObservationV49E,
        "consume_for_actor_v49e",
        lambda self, **_values: self,
    )
    journal.fail_next_batch = True

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.observe_tls_shutdown_v49e(
            operation,
            observation_effect=lambda **_values: observation,
            signer=object(),
        )

    assert journal.events[-1] is operation
    assert not any(
        type(event.payload) is TlsProtocolOperationFailedPayloadV49E
        for event in journal.events
    )
    assert journal.terminal_convergence_calls == 0


@_run_async
async def test_driver_exception_exposes_exact_signed_convergence_on_actor() -> None:
    events, _state, fin_marker, _control = _local_tls_and_half_close_prefix()
    actor, _journal = await _actor(events)
    nonce = next(
        event.payload.driver_evidence_nonce_sha256
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
    )
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event=actor.events[fin_marker.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )

    with pytest.raises(RuntimeError, match="driver poll failed"):
        await actor.observe_tls_shutdown_v49e(
            operation,
            observation_effect=lambda **_values: (_ for _ in ()).throw(
                RuntimeError("driver poll failed")
            ),
            signer=object(),
        )

    convergence = actor.last_terminal_convergence_v49e
    assert type(convergence) is ActorTerminalConvergenceResultV49E
    assert convergence.terminal_event is actor.events[-1]
    assert (
        convergence.termination.transport_session_id
        == actor.authority.transport_session_id
    )


@_run_async
async def test_token_preparation_failure_has_fixed_final_without_syscall_claim() -> (
    None
):
    events, _state, _tls_marker, control_event = _local_tls_accepted_prefix()
    actor, journal = await _actor(events)
    retained_control = actor.events[control_event.actor_sequence - 1]
    prepared = _prepared_from_event(retained_control)
    actor._v49e_prepared_control_capabilities[  # noqa: SLF001
        retained_control.transport_actor_event_id
    ] = prepared
    shutdown_called = False

    def fail_token(**_values: Any) -> Any:
        raise RuntimeError("token mint failed before syscall")

    def shutdown_effect(_token: Any, **_values: Any) -> Any:
        nonlocal shutdown_called
        shutdown_called = True
        raise AssertionError("shutdown must not run")

    with pytest.raises(RuntimeError, match="token mint failed"):
        command = actor.local_shutdown_command_event_v49e
        assert type(command) is TransportActorEventV49C
        await actor.half_close_tcp_write_v49e(
            command,
            retained_control,
            prepared,
            prepare_token_effect=fail_token,
            shutdown_effect=shutdown_effect,
            signer=object(),
        )

    assert not shutdown_called
    assert not any(
        type(event.payload) is TcpHalfCloseAttemptPayloadV49E
        for event in journal.events
    )
    final = journal.events[-1].payload
    assert type(final) is TerminalTransitionPayloadV49C
    assert final.kind is TerminalTransitionKindV49C.FATAL
    assert final.cause_code == "TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR"
    assert actor.terminal_state.terminal_outcome is TerminalOutcomeV49C.FATAL
    assert journal.terminal_convergence_calls == 1


@_run_async
async def test_owner_unsendable_output_retains_exact_summary_and_fixed_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, _state, fin_marker, _control = _local_tls_and_half_close_prefix()
    actor, journal = await _actor(events)
    nonce = next(
        event.payload.driver_evidence_nonce_sha256
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
    )
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event=actor.events[fin_marker.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )
    ciphertext_sha = hashlib.sha256(b"post-shut-wr-output").hexdigest()
    driver_values = {
        "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
        "output_sequence": 1,
        "driver_evidence_nonce_sha256": nonce,
        "ciphertext_sha256": ciphertext_sha,
        "ciphertext_octets": 19,
    }
    driver_evidence = _sealed(
        UnsendableTlsPostHandshakeOutputV49E,
        output_sequence=1,
        driver_evidence_nonce_sha256=nonce,
        ciphertext_sha256=ciphertext_sha,
        ciphertext_octets=19,
        unsendable_output_id=sha256_digest(driver_values),
    )
    kernel_identity = hashlib.sha256(b"kernel-socket").hexdigest()
    owner_values = {
        "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
        "transport_session_id": AUTHORITY["transport_session_id"],
        "kernel_socket_identity": kernel_identity,
        "driver_unsendable_output_id": driver_evidence.unsendable_output_id,
        "driver_output_sequence": driver_evidence.output_sequence,
        "driver_evidence_nonce_sha256": nonce,
        "ciphertext_sha256": ciphertext_sha,
        "ciphertext_octets": 19,
    }
    owner_evidence = _sealed(
        OwnerUnsendableTlsPostHandshakeOutputV49E,
        transport_session_id=AUTHORITY["transport_session_id"],
        kernel_socket_identity=kernel_identity,
        driver_evidence=driver_evidence,
        owner_unsendable_output_id=sha256_digest(owner_values),
    )
    monkeypatch.setattr(
        OwnerUnsendableTlsPostHandshakeOutputV49E,
        "consume_for_actor_v49e",
        lambda self, **_values: self,
    )

    await actor.record_unsendable_tls_output_v49e(
        operation,
        owner_evidence,
        signer=object(),
    )

    failure = journal.events[-2].payload
    final = journal.events[-1].payload
    assert type(failure) is TlsProtocolOperationFailedPayloadV49E
    assert failure.failure_kind is (
        TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
    )
    assert failure.unsendable_ciphertext_sha256 == ciphertext_sha
    assert failure.unsendable_ciphertext_octets == 19
    assert type(final) is TerminalTransitionPayloadV49C
    assert final.cause_code == V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE


@_run_async
async def test_unregistered_unsendable_copy_maps_driver_error_without_summary() -> None:
    events, _state, fin_marker, _control = _local_tls_and_half_close_prefix()
    actor, journal = await _actor(events)
    nonce = next(
        event.payload.driver_evidence_nonce_sha256
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
    )
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event=actor.events[fin_marker.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )
    copied_evidence = _owner_unsendable_evidence(
        nonce=nonce,
        ciphertext=b"unregistered-copy",
    )

    with pytest.raises(LinuxSocketOwnerV4Error, match="copied|consumed|expired"):
        await actor.record_unsendable_tls_output_v49e(
            operation,
            copied_evidence,
            signer=object(),
        )

    failure = journal.events[-2].payload
    assert type(failure) is TlsProtocolOperationFailedPayloadV49E
    assert failure.failure_kind is TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
    assert failure.unsendable_ciphertext_sha256 is None
    assert failure.unsendable_ciphertext_octets is None
    assert actor.terminal_state.terminal_outcome is TerminalOutcomeV49C.FATAL


@_run_async
async def test_clean_shutdown_outcome_carries_exact_signed_terminal_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, state, fin_marker, _control = _local_tls_and_half_close_prefix()
    state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    assert not state.is_terminal
    actor, journal = await _actor(events)
    nonce = next(
        event.payload.driver_evidence_nonce_sha256
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
    )
    operation = await _start_actor_tls_operation(
        actor,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event=actor.events[peer_marker.actor_sequence - 1],
        driver_evidence_nonce_sha256=nonce,
    )
    observation = _owner_observation(
        nonce=nonce,
        kind=TlsShutdownObservationKindV49E.TCP_EOF,
        sequence=2,
        peer_received=True,
    )
    monkeypatch.setattr(
        OwnerTlsShutdownObservationV49E,
        "consume_for_actor_v49e",
        lambda self, **_values: self,
    )

    outcome = await actor.observe_tls_shutdown_v49e(
        operation,
        observation_effect=lambda **_values: observation,
        signer=object(),
    )

    assert outcome.observation_event is journal.events[-3]
    assert outcome.marker_event is journal.events[-2]
    assert outcome.terminal_convergence is not None
    assert outcome.terminal_convergence.terminal_event is journal.events[-1]
    assert outcome.terminal_event is journal.events[-1]
    assert outcome.termination is outcome.terminal_convergence.termination
    assert actor.last_terminal_convergence_v49e is outcome.terminal_convergence
    assert actor.terminal_state.terminal_outcome is (
        TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    )


@_run_async
async def test_recovery_of_tcp_eof_observation_uses_terminal_governed_clocks() -> None:
    events = _clean_ready_shutdown_prefix(include_eof_marker=False)
    first = (
        events[-1].recorded_at + timedelta(seconds=1),
        events[-1].recorded_monotonic_ns + 100,
    )
    second = (first[0] + timedelta(microseconds=1), first[1] + 1)
    terminal_clock = _ScriptedTerminalClock((first, second))
    actor, journal, strict_clock_calls = await _restored_actor_with_terminal_clock(
        events,
        terminal_clock,
    )

    await actor.recover_terminal_prefix_v49e(signer=object())

    assert terminal_clock.batch_calls == [2]
    assert strict_clock_calls == []
    assert (
        journal.events[-2].recorded_at,
        journal.events[-2].recorded_monotonic_ns,
    ) == first
    assert (
        journal.events[-1].recorded_at,
        journal.events[-1].recorded_monotonic_ns,
    ) == second
    assert journal.events[-2].payload.kind is (
        TerminalTransitionKindV49C.TCP_EOF_RECEIVED
    )
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.CLEAN_ALL_LAYERS
    )
    assert actor.terminal_state.terminal_outcome is (
        TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    )


@_run_async
async def test_recovery_of_tcp_eof_marker_uses_terminal_governed_clock() -> None:
    events = _clean_ready_shutdown_prefix(include_eof_marker=True)
    recovered = (
        events[-1].recorded_at + timedelta(seconds=1),
        events[-1].recorded_monotonic_ns + 100,
    )
    terminal_clock = _ScriptedTerminalClock((recovered,))
    actor, journal, strict_clock_calls = await _restored_actor_with_terminal_clock(
        events,
        terminal_clock,
    )

    await actor.recover_terminal_prefix_v49e(signer=object())

    assert terminal_clock.batch_calls == [1]
    assert strict_clock_calls == []
    assert (
        journal.events[-1].recorded_at,
        journal.events[-1].recorded_monotonic_ns,
    ) == recovered
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.CLEAN_ALL_LAYERS
    )


@_run_async
async def test_recovery_fails_closed_when_terminal_clock_is_unavailable() -> None:
    events = _clean_ready_shutdown_prefix(include_eof_marker=False)
    terminal_clock = _ScriptedTerminalClock(())
    actor, journal, strict_clock_calls = await _restored_actor_with_terminal_clock(
        events,
        terminal_clock,
    )
    before = tuple(journal.events)

    with pytest.raises(RuntimeError, match="terminal clock is exhausted"):
        await actor.recover_terminal_prefix_v49e(signer=object())

    assert tuple(journal.events) == before
    assert terminal_clock.batch_calls == [2]
    assert strict_clock_calls == []


@_run_async
async def test_replace_prefix_rejects_non_extension_after_terminal_authorization() -> (
    None
):
    events = _clean_ready_shutdown_prefix(include_eof_marker=True)
    terminal_clock = _ScriptedTerminalClock(
        (
            (
                events[-1].recorded_at + timedelta(seconds=1),
                events[-1].recorded_monotonic_ns + 100,
            ),
        )
    )
    actor, _journal, _strict_clock_calls = await _restored_actor_with_terminal_clock(
        events, terminal_clock
    )
    before = actor.events
    assert actor._terminal_evidence_clock_authorized_v49e  # noqa: SLF001

    with pytest.raises(
        PhysicalTransportSessionActorV49CJournalError,
        match="append-only extension",
    ):
        actor._replace_prefix(tuple(events[:-1]))  # noqa: SLF001

    assert actor.events == before
    assert actor._terminal_evidence_clock_authorized_v49e  # noqa: SLF001


@_run_async
async def test_recovery_closes_every_unresolved_e2_prefix_without_effect_replay() -> (
    None
):
    signer = object()

    operation_events, _state, ws_accepted = _websocket_close_prefix()
    pending_operation = _start_tls_operation(
        operation_events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    operation_actor, operation_journal = await _actor(operation_events)
    await operation_actor.recover_terminal_prefix_v49e(signer=signer)
    operation_failure = operation_journal.events[-2].payload
    operation_final = operation_journal.events[-1].payload
    assert type(operation_failure) is TlsProtocolOperationFailedPayloadV49E
    assert operation_failure.tls_protocol_operation_started_event_id == (
        pending_operation.transport_actor_event_id
    )
    assert operation_failure.failure_kind is (
        TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
    )
    assert type(operation_final) is TerminalTransitionPayloadV49C
    assert operation_final.cause_code == V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE
    assert operation_journal.terminal_convergence_calls == 1

    attempt_events, attempt_state, control_event = _local_control_prepared_prefix()
    pending_attempt = _append_control_attempt(attempt_events, control_event)
    attempt_state, _ = _terminal(
        attempt_events,
        attempt_state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=pending_attempt.transport_actor_event_id,
    )
    assert attempt_state.has_pending_send_attempt
    attempt_actor, attempt_journal = await _actor(attempt_events)
    await attempt_actor.recover_terminal_prefix_v49e(signer=signer)
    attempt_final = attempt_journal.events[-1].payload
    assert type(attempt_final) is TerminalTransitionPayloadV49C
    assert attempt_final.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
    assert attempt_final.cause_code == V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE
    assert attempt_journal.terminal_convergence_calls == 1

    half_events, _state, tls_marker, control_event = _local_tls_accepted_prefix()
    pending_half_close = _append_half_close_attempt(
        half_events,
        tls_marker,
        control_event,
    )
    half_actor, half_journal = await _actor(half_events)
    await half_actor.recover_terminal_prefix_v49e(signer=signer)
    half_final = half_journal.events[-1].payload
    assert type(half_final) is TerminalTransitionPayloadV49C
    assert half_final.kind is TerminalTransitionKindV49C.FATAL
    assert half_final.cause_code == V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE
    assert half_journal.terminal_convergence_calls == 1
    assert not any(
        type(event.payload) is TcpHalfCloseResultPayloadV49E
        and event.payload.tcp_half_close_attempt_event_id
        == pending_half_close.transport_actor_event_id
        for event in half_journal.events[len(half_events) :]
    )

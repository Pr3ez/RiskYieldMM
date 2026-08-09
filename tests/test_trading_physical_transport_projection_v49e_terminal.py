from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4VerificationError,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    LocalShutdownDeadlineEvidencePayloadV49E,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    ParserTransitionPayloadV49C,
    TerminalIngressFailureKindV49E,
    TerminalIngressFailurePayloadV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TlsShutdownObservedPayloadV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketOpcodeV49C,
    WebSocketParserStateV49C,
    derive_local_shutdown_command_id_v49e,
    derive_local_terminal_command_operation_id_v49e,
    reduce_transport_actor_chain_v49e,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    OutboundObligationLayerV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests import (
    test_trading_physical_transport_actor_v49e_terminal_contract as actor_contract,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    T0,
    _build_harness,
    _establish,
)


def _close_raw(committed: Any) -> RawIngressCommitV4:
    session = committed.session
    binding = committed.binding
    frame = b"\x88\x00"
    encoded = (base64.b64encode(frame).decode("ascii"),)
    return RawIngressCommitV4(
        transport_subscription_policy_id=session.transport_subscription_policy_id,
        transport_session_id=session.transport_session_id,
        physical_scope_manifest_id=session.physical_scope_manifest_id,
        adapter_policy_id=session.adapter_policy_id,
        capture_partition_id=session.capture_partition_id,
        socket_lease_id=binding.socket_lease_id,
        connection_generation=session.connection_generation,
        deployment_bundle_id=session.deployment_bundle_id,
        writer_fence_token_sha256=binding.writer_fence_token_sha256,
        writer_fence_generation=binding.writer_fence_generation,
        ingress_sequence=1,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=(hashlib.sha256(frame).hexdigest(),),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=T0 + timedelta(milliseconds=900),
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        received_monotonic_ns=session.handshake_completed_monotonic_ns + 1_000_000,
    )


def _authority(event: TransportActorEventV49C) -> dict[str, Any]:
    return {
        name: getattr(event, name)
        for name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "connection_generation",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "writer_fence_generation",
            "monotonic_clock_domain_id",
            "driver_policy_id",
        )
    }


def _event_with_payload(
    prior: TransportActorEventV49C,
    payload: Any,
) -> TransportActorEventV49C:
    return TransportActorEventV49C.create(
        **_authority(prior),
        recorded_at=prior.recorded_at + timedelta(microseconds=1),
        recorded_monotonic_ns=prior.recorded_monotonic_ns + 1,
        actor_sequence=prior.actor_sequence + 1,
        previous_event_id=prior.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.TERMINAL_TRANSITION,
        payload=payload,
    )


def _recreate_event(
    event: TransportActorEventV49C,
    *,
    payload: Any | None = None,
    previous_event_id: str | None = None,
) -> TransportActorEventV49C:
    return TransportActorEventV49C.create(
        **_authority(event),
        recorded_at=event.recorded_at,
        recorded_monotonic_ns=event.recorded_monotonic_ns,
        actor_sequence=event.actor_sequence,
        previous_event_id=(
            event.previous_event_id if previous_event_id is None else previous_event_id
        ),
        event_kind=event.event_kind,
        payload=event.payload if payload is None else payload,
    )


def _prepare_clean_chain(
    harness: Any,
    committed: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[tuple[TransportActorEventV49C, ...], TransportActorEventV49C]:
    raw, raw_event = _bind_actor_contract_harness(
        harness,
        committed,
        monkeypatch,
        idempotency_key="v49e-terminal-raw",
    )
    events, state, fin_marker, _ = actor_contract._local_tls_and_half_close_prefix()
    state, peer_shutdown_marker = actor_contract._observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=actor_contract.TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    state, _ = actor_contract._observe_shutdown(
        events,
        state,
        operation_sequence=3,
        observation_sequence=2,
        kind=actor_contract.TlsShutdownObservationKindV49E.TCP_EOF,
        cause_event_id=peer_shutdown_marker.transport_actor_event_id,
        peer_received=True,
    )
    state, final_event = actor_contract._terminal(
        events,
        state,
        TerminalTransitionKindV49C.CLEAN_ALL_LAYERS,
    )
    assert events[0] == raw_event
    assert reduce_transport_actor_chain_v49e(events) == state
    for index, event in enumerate(events[1:-1], start=1):
        harness.store.append_transport_actor_event_v49c_for_test(
            event,
            idempotency_key=f"v49e-terminal-prefix-{index}",
        )
    assert raw.transport_session_id == committed.session.transport_session_id
    return tuple(events), final_event


def _bind_actor_contract_harness(
    harness: Any,
    committed: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    idempotency_key: str,
) -> tuple[RawIngressCommitV4, TransportActorEventV49C]:
    raw = _close_raw(committed)
    committed_raw = harness.store.append_actor_raw_ingress_v49c_for_test(
        raw,
        driver_policy_id=harness.driver.driver_policy_id,
        idempotency_key=idempotency_key,
    )
    raw_event = committed_raw.event
    session = committed.session
    original_digest = actor_contract._digest
    harness.store._clock = lambda: raw.received_at + timedelta(seconds=10)  # noqa: SLF001

    def evidence_digest(label: str) -> str:
        if label == "driver-evidence-nonce":
            return session.session_nonce
        if label == "owner-kernel-socket":
            return committed.binding.kernel_socket_identity
        return original_digest(label)

    def append_with_session_clock(
        events: list[TransportActorEventV49C],
        kind: TransportActorEventKindV49C,
        payload: Any,
    ) -> TransportActorEventV49C:
        if not events and kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED:
            events.append(raw_event)
            return raw_event
        clock = actor_contract._payload_clock(payload)
        if (
            events
            and clock is not None
            and clock[1] <= events[-1].recorded_monotonic_ns
        ):
            for ns_name in (
                "received_monotonic_ns",
                "processed_monotonic_ns",
                "prepared_monotonic_ns",
                "consumed_monotonic_ns",
                "attempted_monotonic_ns",
                "observed_monotonic_ns",
                "completed_monotonic_ns",
                "started_monotonic_ns",
            ):
                if hasattr(payload, ns_name):
                    payload = replace(
                        payload,
                        **{ns_name: events[-1].recorded_monotonic_ns + 10},
                    )
                    clock = actor_contract._payload_clock(payload)
                    break
        prior_at, prior_ns = actor_contract._next_clock(events)
        if clock is None:
            recorded_at, recorded_ns = prior_at, prior_ns
        elif type(payload) is LocalShutdownCommandStartedPayloadV49E:
            recorded_at, recorded_ns = clock
        else:
            recorded_at = max(prior_at, clock[0] + timedelta(microseconds=1))
            recorded_ns = max(prior_ns, clock[1] + 1)
        event = TransportActorEventV49C.create(
            **actor_contract.AUTHORITY,
            recorded_at=recorded_at,
            recorded_monotonic_ns=recorded_ns,
            actor_sequence=len(events) + 1,
            previous_event_id=(
                None if not events else events[-1].transport_actor_event_id
            ),
            event_kind=kind,
            payload=payload,
        )
        events.append(event)
        return event

    monkeypatch.setattr(actor_contract, "AUTHORITY", _authority(raw_event))
    monkeypatch.setattr(
        actor_contract,
        "T0",
        raw_event.payload.receipt.committed_at - timedelta(milliseconds=2),
    )
    monkeypatch.setattr(actor_contract, "_digest", evidence_digest)
    monkeypatch.setattr(actor_contract, "_append", append_with_session_clock)
    monkeypatch.setattr(
        actor_contract,
        "_raw_close_payload",
        lambda: (raw_event.payload, raw.raw_bytes),
    )
    monkeypatch.setattr(
        actor_contract,
        "_start_tls_operation",
        _current_start_tls_operation,
    )
    monkeypatch.setattr(
        actor_contract,
        "_fail_tls_operation",
        _current_fail_tls_operation,
    )
    monkeypatch.setattr(
        actor_contract,
        "_append_control_attempt",
        _current_append_control_attempt,
    )
    monkeypatch.setattr(
        actor_contract,
        "_append_half_close_attempt",
        _current_append_half_close_attempt,
    )
    return raw, raw_event


def _append_actor_contract_prefix(
    harness: Any,
    events: list[TransportActorEventV49C],
    *,
    key_prefix: str,
    include_tail: bool = True,
) -> None:
    suffix = events[1:] if include_tail else events[1:-1]
    for index, event in enumerate(suffix, start=1):
        harness.store.append_transport_actor_event_v49c_for_test(
            event,
            idempotency_key=f"{key_prefix}-{index}",
        )


def _masked_client_frame(opcode: int, payload: bytes) -> bytes:
    assert len(payload) <= 125
    mask = b"\x01\x02\x03\x04"
    masked = bytes(
        value ^ mask[index % len(mask)] for index, value in enumerate(payload)
    )
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + masked


def _shutdown_command_event_after(
    prior: TransportActorEventV49C,
    *,
    timeout_seconds: int = 60,
) -> TransportActorEventV49C:
    started_at = prior.recorded_at + timedelta(milliseconds=1)
    started_ns = prior.recorded_monotonic_ns + 10
    deadline_at = started_at + timedelta(seconds=timeout_seconds)
    deadline_ns = started_ns + timeout_seconds * 1_000_000_000
    payload = LocalShutdownCommandStartedPayloadV49E(
        local_shutdown_command_id=derive_local_shutdown_command_id_v49e(
            transport_session_id=prior.transport_session_id,
            actor_predecessor_event_id=prior.transport_actor_event_id,
            timeout_seconds=timeout_seconds,
            started_at=started_at,
            started_monotonic_ns=started_ns,
            deadline_at=deadline_at,
            deadline_monotonic_ns=deadline_ns,
        ),
        websocket_close_code=1000,
        websocket_close_reason_sha256=hashlib.sha256(b"").hexdigest(),
        websocket_close_reason_octets=0,
        websocket_close_payload_sha256=hashlib.sha256(b"\x03\xe8").hexdigest(),
        websocket_close_payload_octets=2,
        timeout_seconds=timeout_seconds,
        started_at=started_at,
        started_monotonic_ns=started_ns,
        shutdown_deadline_at=deadline_at,
        shutdown_deadline_monotonic_ns=deadline_ns,
    )
    return TransportActorEventV49C.create(
        **_authority(prior),
        recorded_at=started_at,
        recorded_monotonic_ns=started_ns,
        actor_sequence=prior.actor_sequence + 1,
        previous_event_id=prior.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
        payload=payload,
    )


def _wire_event_after(
    prior: TransportActorEventV49C,
    *,
    wire_origin: OutboundWireOriginV49C,
    logical_opcode: WebSocketOpcodeV49C,
    logical_payload: bytes,
    outbound_operation_id: str | None = None,
) -> TransportActorEventV49C:
    opcode = {
        WebSocketOpcodeV49C.TEXT: 0x1,
        WebSocketOpcodeV49C.CLOSE: 0x8,
    }[logical_opcode]
    frame = _masked_client_frame(opcode, logical_payload)
    encoded = (base64.b64encode(frame).decode("ascii"),)
    chunk_hashes = (hashlib.sha256(frame).hexdigest(),)
    batch_hash = sha256_digest(
        {
            "domain": "RiskYieldMMActorOrderedProtocolOutputV4_9C",
            "ordered_chunks_base64": list(encoded),
        }
    )
    operation_id = outbound_operation_id
    if operation_id is None:
        operation_id = derive_local_terminal_command_operation_id_v49e(
            transport_session_id=prior.transport_session_id,
            actor_predecessor_event_id=prior.transport_actor_event_id,
            logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
            logical_payload_octets=len(logical_payload),
            ordered_wire_chunks_sha256=chunk_hashes,
            wire_batch_sha256=batch_hash,
            wire_octets=len(frame),
        )
    command = (
        prior.payload
        if wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
        else None
    )
    if wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND:
        assert type(command) is LocalShutdownCommandStartedPayloadV49E
    prepared_at = prior.recorded_at + timedelta(milliseconds=1)
    prepared_ns = prior.recorded_monotonic_ns + 10
    payload = OutboundWirePreparedPayloadV49C(
        outbound_operation_id=operation_id,
        wire_origin=wire_origin,
        source_parser_event_id=None,
        logical_opcode=logical_opcode,
        logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
        logical_payload_octets=len(logical_payload),
        ordered_wire_chunks_base64=encoded,
        ordered_wire_chunks_sha256=chunk_hashes,
        wire_batch_sha256=batch_hash,
        wire_octets=len(frame),
        prepared_at=prepared_at,
        prepared_monotonic_ns=prepared_ns,
        send_not_after=(
            command.shutdown_deadline_at
            if type(command) is LocalShutdownCommandStartedPayloadV49E
            else prepared_at + timedelta(minutes=1)
        ),
        send_not_after_monotonic_ns=(
            command.shutdown_deadline_monotonic_ns
            if type(command) is LocalShutdownCommandStartedPayloadV49E
            else prepared_ns + 100_000
        ),
    )
    return TransportActorEventV49C.create(
        **_authority(prior),
        recorded_at=prepared_at + timedelta(microseconds=1),
        recorded_monotonic_ns=prepared_ns + 1,
        actor_sequence=prior.actor_sequence + 1,
        previous_event_id=prior.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        payload=payload,
    )


def _current_shutdown_command(
    events: list[TransportActorEventV49C],
) -> TransportActorEventV49C:
    commands = [
        event
        for event in events
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    ]
    if commands:
        assert len(commands) == 1
        return commands[0]
    command = _shutdown_command_event_after(events[-1])
    events.append(command)
    return command


def _current_start_tls_operation(
    events: list[TransportActorEventV49C],
    *,
    sequence: int,
    purpose: TlsProtocolOperationPurposeV49E,
    cause_event_id: str,
) -> TransportActorEventV49C:
    command_event = _current_shutdown_command(events)
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    started_at, started_ns = actor_contract._next_clock(events)
    nonce = actor_contract._digest("driver-evidence-nonce")
    operation_id = sha256_digest(
        {
            "domain": "RiskYieldMMTlsProtocolOperationV4_9E",
            "transport_session_id": actor_contract.AUTHORITY["transport_session_id"],
            "operation_sequence": sequence,
            "local_shutdown_command_started_event_id": (
                command_event.transport_actor_event_id
            ),
            "purpose": purpose.value,
            "cause_actor_event_id": cause_event_id,
            "driver_evidence_nonce_sha256": nonce,
        }
    )
    return actor_contract._append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
        TlsProtocolOperationStartedPayloadV49E(
            operation_sequence=sequence,
            tls_operation_id=operation_id,
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            purpose=purpose,
            cause_actor_event_id=cause_event_id,
            driver_evidence_nonce_sha256=nonce,
            started_at=started_at,
            started_monotonic_ns=started_ns,
        ),
    )


def _current_fail_tls_operation(
    events: list[TransportActorEventV49C],
    operation_event: TransportActorEventV49C,
    failure_kind: TlsProtocolOperationFailureKindV49E,
) -> TransportActorEventV49C:
    operation = operation_event.payload
    assert type(operation) is TlsProtocolOperationStartedPayloadV49E
    command_event = _current_shutdown_command(events)
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    unsendable = (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
    )
    unsendable_digest = actor_contract._digest("unsendable-post-handshake-output")
    unsendable_sequence = 1
    unsendable_driver_id = (
        sha256_digest(
            {
                "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
                "output_sequence": unsendable_sequence,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "ciphertext_sha256": unsendable_digest,
                "ciphertext_octets": 17,
            }
        )
        if unsendable
        else None
    )
    unsendable_socket = actor_contract._digest("unsendable-owner-socket")
    unsendable_owner_id = (
        sha256_digest(
            {
                "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
                "transport_session_id": events[0].transport_session_id,
                "kernel_socket_identity": unsendable_socket,
                "driver_unsendable_output_id": unsendable_driver_id,
                "driver_output_sequence": unsendable_sequence,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "ciphertext_sha256": unsendable_digest,
                "ciphertext_octets": 17,
            }
        )
        if unsendable
        else None
    )
    if failure_kind not in {
        TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
        TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR,
    }:
        raise AssertionError("projection fixture requires explicit deadline evidence")
    observed_at, observed_ns = actor_contract._next_clock(events)
    return actor_contract._append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
        TlsProtocolOperationFailedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation_event.transport_actor_event_id
            ),
            tls_operation_id=operation.tls_operation_id,
            purpose=operation.purpose,
            driver_evidence_nonce_sha256=operation.driver_evidence_nonce_sha256,
            failure_kind=failure_kind,
            deadline_classification=None,
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            unsendable_driver_output_sequence=(
                unsendable_sequence if unsendable else None
            ),
            unsendable_driver_evidence_id=unsendable_driver_id,
            unsendable_owner_evidence_id=unsendable_owner_id,
            unsendable_kernel_socket_identity=(
                unsendable_socket if unsendable else None
            ),
            unsendable_ciphertext_sha256=(unsendable_digest if unsendable else None),
            unsendable_ciphertext_octets=17 if unsendable else None,
            deadline_no_observation_owner_evidence_id=None,
            deadline_no_observation_kernel_socket_identity=None,
            deadline_no_observation_operation=None,
            deadline_after_progress_owner_evidence_id=None,
            deadline_after_progress_driver_evidence_id=None,
            deadline_after_progress_kernel_socket_identity=None,
            deadline_after_progress_operation=None,
            deadline_after_progress_ciphertext_sha256=None,
            deadline_after_progress_ciphertext_octets=None,
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )


def _current_append_control_attempt(
    events: list[TransportActorEventV49C],
    control_event: TransportActorEventV49C,
    *,
    start_octet: int = 0,
    attempt_ordinal: int = 1,
    requested_octets: int | None = None,
) -> TransportActorEventV49C:
    control = control_event.payload
    assert type(control) is actor_contract.TlsControlCiphertextPreparedPayloadV49E
    command_event = _current_shutdown_command(events)
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    requested = (
        control.ciphertext_octets - start_octet
        if requested_octets is None
        else requested_octets
    )
    attempted_at, attempted_ns = actor_contract._next_clock(events)
    return actor_contract._append(
        events,
        TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT,
        actor_contract.TlsControlKernelSendAttemptPayloadV49E(
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            kernel_attempt_ordinal=attempt_ordinal,
            ciphertext_batch_sha256=control.ciphertext_batch_sha256,
            ciphertext_octets=control.ciphertext_octets,
            ciphertext_start_octet=start_octet,
            requested_octets=requested,
            attempted_at=attempted_at,
            attempted_monotonic_ns=attempted_ns,
        ),
    )


def _current_append_half_close_attempt(
    events: list[TransportActorEventV49C],
    tls_marker: TransportActorEventV49C,
    control_event: TransportActorEventV49C,
    *,
    shutdown_token_id_override: str | None = None,
) -> TransportActorEventV49C:
    control = control_event.payload
    assert type(control) is actor_contract.TlsControlCiphertextPreparedPayloadV49E
    command_event = _current_shutdown_command(events)
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    shutdown_token_id = sha256_digest(
        {
            "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
            "token_sequence": 1,
            "transport_session_id": actor_contract.AUTHORITY["transport_session_id"],
            "tls_control_sequence": control.control_sequence,
            "tls_ciphertext_batch_sha256": control.ciphertext_batch_sha256,
            "tls_ciphertext_octets": control.ciphertext_octets,
            "shutdown_deadline_monotonic_ns": (command.shutdown_deadline_monotonic_ns),
        }
    )
    attempted_at, attempted_ns = actor_contract._next_clock(events)
    return actor_contract._append(
        events,
        TransportActorEventKindV49C.TCP_HALF_CLOSE_ATTEMPT,
        actor_contract.TcpHalfCloseAttemptPayloadV49E(
            tls_close_notify_sent_event_id=tls_marker.transport_actor_event_id,
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_token_id=(
                shutdown_token_id
                if shutdown_token_id_override is None
                else shutdown_token_id_override
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            token_sequence=1,
            tls_control_sequence=control.control_sequence,
            tls_ciphertext_batch_sha256=control.ciphertext_batch_sha256,
            tls_ciphertext_octets=control.ciphertext_octets,
            shutdown_how="SHUT_WR",
            attempted_at=attempted_at,
            attempted_monotonic_ns=attempted_ns,
        ),
    )


def _recovery_detected_at(
    harness: Any,
    tail: TransportActorEventV49C,
) -> datetime:
    return max(tail.recorded_at, harness.store._now()) + timedelta(  # noqa: SLF001
        seconds=1
    )


def _prepare_tls_failure_prefix(
    harness: Any,
    committed: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    append_failure: bool = True,
) -> tuple[
    list[TransportActorEventV49C],
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    _, raw_event = _bind_actor_contract_harness(
        harness,
        committed,
        monkeypatch,
        idempotency_key="v49e-failure-raw",
    )
    events, state, cause_event = actor_contract._websocket_close_prefix()
    operation = actor_contract._start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=cause_event.transport_actor_event_id,
    )
    failure = actor_contract._fail_tls_operation(
        events,
        operation,
        TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
    )
    _, terminal = actor_contract._terminal(
        events,
        state,
        TerminalTransitionKindV49C.FATAL,
        cause_code=actor_contract.V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    )
    assert events[0] == raw_event
    suffix = events[1:-1] if append_failure else events[1:-2]
    for index, event in enumerate(suffix, start=1):
        harness.store.append_transport_actor_event_v49c_for_test(
            event,
            idempotency_key=f"v49e-failure-prefix-{index}",
        )
    return events, failure, terminal


def _prepare_pending_tls_control_prefix(
    harness: Any,
    committed: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> list[TransportActorEventV49C]:
    _, raw_event = _bind_actor_contract_harness(
        harness,
        committed,
        monkeypatch,
        idempotency_key="v49e-pending-control-raw",
    )
    events, _, _ = actor_contract._local_control_prepared_prefix()
    assert events[0] == raw_event
    _append_actor_contract_prefix(
        harness,
        events,
        key_prefix="v49e-pending-control-prefix",
    )
    return events


def test_clean_terminal_convergence_is_one_derived_pair_and_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-pair-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events, final_event = _prepare_clean_chain(
                    harness, committed, monkeypatch
                )
                result = harness.store.converge_actor_terminal_v49e_for_test(
                    final_event,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-clean-convergence",
                )
                assert result.terminal_event == final_event
                assert (
                    result.termination.reason
                    is TransportSessionTerminationReasonV4.REMOTE_CLOSE
                )
                assert result.termination.close_code is None
                assert result.termination.close_reason_digest is None
                assert (
                    harness.store._source_metadata(  # noqa: SLF001
                        result.termination.transport_session_termination_id
                    )[0]
                    == harness.store._source_metadata(  # noqa: SLF001
                        result.terminal_event.transport_actor_event_id
                    )[0]
                    + 1
                )
                replay = harness.store.converge_actor_terminal_v49e_for_test(
                    final_event,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-clean-convergence",
                )
                assert replay == result
                assert harness.store.verify().transport_session_termination_count == 1
                assert events[-1] == final_event
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_negative_terminal_mapping_and_legacy_bypasses_are_sealed() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-negative-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                raw = harness.store.append_actor_raw_ingress_v49c_for_test(
                    _close_raw(committed),
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="v49e-negative-raw",
                )
                harness.store._clock = lambda: (
                    raw.event.recorded_at
                    + timedelta(  # noqa: SLF001
                        seconds=10
                    )
                )
                state = reduce_transport_actor_chain_v49e((raw.event,))
                terminal = _event_with_payload(
                    raw.event,
                    TerminalTransitionPayloadV49C(
                        transport_session_id=committed.session.transport_session_id,
                        transition_sequence=state.transition_sequence + 1,
                        parent_terminal_state_id=state.terminal_state_id,
                        kind=TerminalTransitionKindV49C.FATAL,
                        cause_code="BACKPRESSURE_POLICY_FENCE",
                    ),
                )
                bridge = harness.store._derive_actor_terminal_bridge_v49e(  # noqa: SLF001
                    (raw.event, terminal)
                )
                assert bridge.reason is TransportSessionTerminationReasonV4.BACKPRESSURE

                with pytest.raises(
                    PhysicalProjectionV4ConflictError, match="atomic V4.9E"
                ):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        terminal,
                        idempotency_key="v49e-negative-final-bypass",
                    )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError, match="actor-owned"
                ):
                    harness.store.append_transport_session_termination(
                        transport_session_id=committed.session.transport_session_id,
                        reason=TransportSessionTerminationReasonV4.LOCAL_CLOSE,
                        detected_at=terminal.recorded_at,
                        detected_monotonic_ns=terminal.recorded_monotonic_ns,
                        detected_monotonic_clock_domain_id=(
                            committed.session.monotonic_clock_domain_id
                        ),
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_key="v49e-negative-legacy-bypass",
                    )

                result = harness.store.converge_actor_terminal_v49e_for_test(
                    terminal,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-negative-convergence",
                )
                assert (
                    result.termination.reason
                    is TransportSessionTerminationReasonV4.BACKPRESSURE
                )
                assert harness.store.verify().transport_session_termination_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_terminal_predecessor_and_layer_forgeries_fail_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-forge-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events, final_event = _prepare_clean_chain(
                    harness, committed, monkeypatch
                )
                prefix = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert prefix[-1] == events[-2]

                reordered = _recreate_event(
                    final_event,
                    previous_event_id=events[-3].transport_actor_event_id,
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError, match="exact actor chain"
                ):
                    harness.store.converge_actor_terminal_v49e_for_test(
                        reordered,
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_key="v49e-reordered-final",
                    )

                state_without_eof = reduce_transport_actor_chain_v49e(events[:-3])
                missing_layer_payload = TerminalTransitionPayloadV49C(
                    transport_session_id=committed.session.transport_session_id,
                    transition_sequence=state_without_eof.transition_sequence + 1,
                    parent_terminal_state_id=state_without_eof.terminal_state_id,
                    kind=TerminalTransitionKindV49C.CLEAN_ALL_LAYERS,
                )
                missing_layer = _event_with_payload(events[-4], missing_layer_payload)
                with pytest.raises(
                    PhysicalProjectionV4ConflictError, match="exact actor chain"
                ):
                    harness.store.converge_actor_terminal_v49e_for_test(
                        missing_layer,
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_key="v49e-missing-layer-final",
                    )

                assert harness.store.verify().transport_session_termination_count == 0
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_tls_nonce_cross_link_is_rejected_by_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-nonce-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events, _ = _prepare_clean_chain(harness, committed, monkeypatch)
                tls_index = next(
                    index
                    for index, event in enumerate(events)
                    if type(event.payload) is TlsProtocolOperationStartedPayloadV49E
                )
                # `_prepare_clean_chain` appended the valid TLS event already, so a
                # same-position forge is tested in the dedicated actor suite. Here
                # the projection-specific handshake binding is exercised directly.
                tls_event = events[tls_index]
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="attested session nonce|exact durable chain",
                ):
                    harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                        _recreate_event(
                            tls_event,
                            payload=replace(
                                tls_event.payload,
                                driver_evidence_nonce_sha256=hashlib.sha256(
                                    b"cross-session-nonce"
                                ).hexdigest(),
                            ),
                        )
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_tls_shutdown_owner_evidence_replays_for_close_notify_and_eof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-shutdown-owner-replay-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events, _ = _prepare_clean_chain(harness, committed, monkeypatch)
                observations = tuple(
                    event
                    for event in events
                    if type(event.payload) is TlsShutdownObservedPayloadV49E
                )
                assert tuple(
                    event.payload.observation_kind for event in observations
                ) == (
                    actor_contract.TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
                    actor_contract.TlsShutdownObservationKindV49E.TCP_EOF,
                )
                for event in observations:
                    payload = event.payload
                    assert type(payload) is TlsShutdownObservedPayloadV49E
                    assert payload.owner_kernel_socket_identity == (
                        committed.binding.kernel_socket_identity
                    )
                    harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                        event
                    )

                    missing_owner = payload.as_dict()
                    missing_owner.pop("owner_observation_id")
                    with pytest.raises(
                        CanonicalizationError, match="keys do not match schema"
                    ):
                        TlsShutdownObservedPayloadV49E.from_mapping(missing_owner)

                    forged_driver_id = hashlib.sha256(
                        f"forged-driver-{payload.observation_kind.value}".encode()
                    ).hexdigest()
                    forged_driver_owner_id = sha256_digest(
                        {
                            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
                            "transport_session_id": event.transport_session_id,
                            "kernel_socket_identity": (
                                payload.owner_kernel_socket_identity
                            ),
                            "driver_observation_id": forged_driver_id,
                            "driver_observation_sequence": (
                                payload.observation_sequence
                            ),
                            "driver_observation_kind": payload.observation_kind.value,
                        }
                    )
                    forged_driver = _recreate_event(
                        event,
                        payload=replace(
                            payload,
                            observation_id=forged_driver_id,
                            owner_observation_id=forged_driver_owner_id,
                        ),
                    )
                    with pytest.raises(
                        PhysicalProjectionV4ConflictError,
                        match="driver-derived identity",
                    ):
                        harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                            forged_driver
                        )

                    forged_owner = _recreate_event(
                        event,
                        payload=replace(
                            payload,
                            owner_observation_id=hashlib.sha256(
                                f"forged-owner-{payload.observation_kind.value}".encode()
                            ).hexdigest(),
                        ),
                    )
                    with pytest.raises(
                        PhysicalProjectionV4ConflictError,
                        match="owner-derived identity",
                    ):
                        harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                            forged_owner
                        )

                    forged_socket = hashlib.sha256(
                        f"forged-socket-{payload.observation_kind.value}".encode()
                    ).hexdigest()
                    forged_socket_owner_id = sha256_digest(
                        {
                            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
                            "transport_session_id": event.transport_session_id,
                            "kernel_socket_identity": forged_socket,
                            "driver_observation_id": payload.observation_id,
                            "driver_observation_sequence": (
                                payload.observation_sequence
                            ),
                            "driver_observation_kind": payload.observation_kind.value,
                        }
                    )
                    foreign_socket = _recreate_event(
                        event,
                        payload=replace(
                            payload,
                            owner_kernel_socket_identity=forged_socket,
                            owner_observation_id=forged_socket_owner_id,
                        ),
                    )
                    with pytest.raises(
                        PhysicalProjectionV4ConflictError,
                        match="admitted kernel socket",
                    ):
                        harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                            foreign_socket
                        )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_terminal_convergence_fault_rolls_back_event_and_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_transport_session_termination_insert":
            raise RuntimeError("terminal-pair-storage-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49e-terminal-rollback-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                committed = await _establish(harness)
                _, final_event = _prepare_clean_chain(harness, committed, monkeypatch)
                before = harness.store._last_receipt()[0]  # noqa: SLF001
                armed = True
                with pytest.raises(RuntimeError, match="terminal-pair-storage-failure"):
                    harness.store.converge_actor_terminal_v49e_for_test(
                        final_event,
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_key="v49e-terminal-fault",
                    )
                assert harness.store._last_receipt()[0] == before  # noqa: SLF001
                assert (
                    harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                        committed.session.transport_session_id
                    )[-1]
                    != final_event
                )
                assert harness.store.verify().transport_session_termination_count == 0
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_verify_rejects_terminal_pair_typed_row_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-verify-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, final_event = _prepare_clean_chain(harness, committed, monkeypatch)
                harness.store.converge_actor_terminal_v49e_for_test(
                    final_event,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-terminal-verify",
                )
                connection = harness.store._connection  # noqa: SLF001
                trigger = connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'trigger'
                      AND tbl_name = 'transport_session_terminations'
                      AND sql LIKE '%UPDATE%'
                    ORDER BY name LIMIT 1
                    """
                ).fetchone()
                assert trigger is not None
                connection.execute(f'DROP TRIGGER "{trigger[0]}"')
                connection.execute(
                    """
                    UPDATE transport_session_terminations
                    SET reason = 'LOCAL_CLOSE'
                    WHERE transport_session_id = ?
                    """,
                    (bytes.fromhex(committed.session.transport_session_id),),
                )
                connection.commit()
                with pytest.raises(PhysicalProjectionV4VerificationError):
                    harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_tls_operation_failure_roundtrips_converges_and_rejects_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-failure-roundtrip-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events, failure_event, terminal_event = _prepare_tls_failure_prefix(
                    harness,
                    committed,
                    monkeypatch,
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[-1] == failure_event
                assert type(chain[-1].payload) is TlsProtocolOperationFailedPayloadV49E

                malformed = failure_event.as_dict()
                malformed["payload"]["failure_kind"] = "NOT_A_FAILURE_KIND"
                with pytest.raises(CanonicalizationError):
                    TransportActorEventV49C.from_mapping(malformed)

                forged_failure = _recreate_event(
                    failure_event,
                    payload=replace(
                        failure_event.payload,
                        tls_operation_id=hashlib.sha256(
                            b"substituted-tls-operation"
                        ).hexdigest(),
                    ),
                )
                with pytest.raises(
                    CanonicalizationError, match="exact started operation"
                ):
                    validate_transport_actor_chain_v49c((*events[:-2], forged_failure))

                result = harness.store.converge_actor_terminal_v49e_for_test(
                    terminal_event,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-failure-convergence",
                )
                failure = failure_event.payload
                assert type(failure) is TlsProtocolOperationFailedPayloadV49E
                assert (
                    result.termination.reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert result.termination.detected_at == failure.observed_at
                assert (
                    result.termination.detected_monotonic_ns
                    == failure.observed_monotonic_ns
                )
                harness.store.verify()

                connection = harness.store._connection  # noqa: SLF001
                trigger = connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'trigger'
                      AND tbl_name = 'transport_actor_events_v49c'
                      AND sql LIKE '%UPDATE%'
                    ORDER BY name LIMIT 1
                    """
                ).fetchone()
                assert trigger is not None
                connection.execute(f'DROP TRIGGER "{trigger[0]}"')
                mutated_payload = failure.as_dict()
                mutated_payload["failure_kind"] = "NOT_A_FAILURE_KIND"
                connection.execute(
                    """
                    UPDATE transport_actor_events_v49c
                    SET payload_blob = ?
                    WHERE transport_actor_event_id = ?
                    """,
                    (
                        json.dumps(
                            mutated_payload,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8"),
                        bytes.fromhex(failure_event.transport_actor_event_id),
                    ),
                )
                connection.commit()
                with pytest.raises(PhysicalProjectionV4VerificationError):
                    harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_actor_startup_reconciliation_appends_one_atomic_restart_pair() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-actor-restart-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                raw = _close_raw(committed)
                raw_result = harness.store.append_actor_raw_ingress_v49c_for_test(
                    raw,
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="v49e-restart-raw",
                )
                detected_at = raw.received_at + timedelta(seconds=1)
                restarted_domain = sha256_digest(
                    {"domain": "v49e-restarted-monotonic-domain"}
                )
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )
                before = harness.store._last_receipt()[0]  # noqa: SLF001

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=1,
                    detected_monotonic_clock_domain_id=restarted_domain,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-actor-startup",
                )
                assert len(reconciled) == 1
                termination = reconciled[0]
                assert (
                    termination.reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[0] == raw_result.event
                assert len(chain) == 2
                terminal = chain[-1]
                assert type(terminal.payload) is TerminalTransitionPayloadV49C
                assert terminal.payload.kind is TerminalTransitionKindV49C.FATAL
                assert terminal.payload.cause_code == "PROCESS_RESTART"
                assert (
                    harness.store._source_metadata(  # noqa: SLF001
                        termination.transport_session_termination_id
                    )[0]
                    == harness.store._source_metadata(  # noqa: SLF001
                        terminal.transport_actor_event_id
                    )[0]
                    + 1
                )
                assert harness.store._last_receipt()[0] == before + 2  # noqa: SLF001

                replay = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at + timedelta(seconds=1),
                    detected_monotonic_ns=2,
                    detected_monotonic_clock_domain_id=restarted_domain,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-actor-startup-retry",
                )
                assert replay == ()
                assert harness.store._last_receipt()[0] == before + 2  # noqa: SLF001
                assert harness.store.verify().transport_session_termination_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_started_tls_operation_records_typed_failure_then_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-recover-tls-operation-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, _, _ = _prepare_tls_failure_prefix(
                    harness,
                    committed,
                    monkeypatch,
                    append_failure=False,
                )
                chain_before = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert type(chain_before[-1].payload) is (
                    TlsProtocolOperationStartedPayloadV49E
                )
                detected_at = _recovery_detected_at(harness, chain_before[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(
                        chain_before[-1].recorded_monotonic_ns + 1_000
                    ),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-started-tls-recovery",
                )
                assert len(reconciled) == 1
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert type(chain[-2].payload) is TlsProtocolOperationFailedPayloadV49E
                assert (
                    chain[-2].payload.failure_kind
                    is TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
                )
                assert type(chain[-1].payload) is TerminalTransitionPayloadV49C
                assert chain[-1].payload.cause_code == (
                    actor_contract.V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE
                )
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_pending_tls_control_uses_fixed_failure_not_generic_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-block-pending-control-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                events = _prepare_pending_tls_control_prefix(
                    harness,
                    committed,
                    monkeypatch,
                )
                detected_at = _recovery_detected_at(harness, events[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )
                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(events[-1].recorded_monotonic_ns + 1_000),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-block-pending-control",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert (
                    chain[-1].payload.cause_code
                    == actor_contract.V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE
                )
                assert chain[-1].payload.cause_code != "PROCESS_RESTART"
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_unresolved_tls_control_send_blocks_generic_restart_with_unknown_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-unknown-tls-send-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-unknown-tls-send-raw",
                )
                events, _, control_event = (
                    actor_contract._local_control_prepared_prefix()
                )
                actor_contract._append_control_attempt(events, control_event)
                assert events[0] == raw_event
                _append_actor_contract_prefix(
                    harness,
                    events,
                    key_prefix="v49e-unknown-tls-send-prefix",
                )
                detected_at = _recovery_detected_at(harness, events[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(events[-1].recorded_monotonic_ns + 1_000),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-unknown-tls-send",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert type(chain[-1].payload) is TerminalTransitionPayloadV49C
                assert chain[-1].payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
                assert chain[-1].payload.cause_code == (
                    actor_contract.V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE
                )
                assert chain[-1].payload.cause_code != "PROCESS_RESTART"
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_conclusive_tls_control_result_repairs_markers_before_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-control-result-markers-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-control-result-raw",
                )
                events, state, control_event = (
                    actor_contract._local_control_prepared_prefix()
                )
                attempt = actor_contract._append_control_attempt(
                    events,
                    control_event,
                )
                state, _ = actor_contract._terminal(
                    events,
                    state,
                    TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                    layer=actor_contract.OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                    obligation_id=control_event.transport_actor_event_id,
                    send_attempt_id=attempt.transport_actor_event_id,
                )
                actor_contract._append_control_result(
                    events,
                    control_event,
                    attempt,
                )
                assert state.has_pending_send_attempt
                assert events[0] == raw_event
                _append_actor_contract_prefix(
                    harness,
                    events,
                    key_prefix="v49e-control-result-prefix",
                )
                detected_at = _recovery_detected_at(harness, events[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(events[-1].recorded_monotonic_ns + 1_000),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-control-result-recovery",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                suffix_kinds = tuple(
                    event.payload.kind
                    for event in chain[-4:]
                    if type(event.payload) is TerminalTransitionPayloadV49C
                )
                assert suffix_kinds == (
                    TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                    TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
                    TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
                    TerminalTransitionKindV49C.FATAL,
                )
                assert chain[-1].payload.cause_code == "PROCESS_RESTART"
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_repairs_parser_close_marker_without_synthesizing_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(
            prefix="ry-v49e-parser-marker-quarantine-"
        ) as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-parser-marker-raw",
                )
                complete_events, _, _ = actor_contract._websocket_close_prefix()
                interrupted = complete_events[:2]
                assert interrupted[0] == raw_event
                _append_actor_contract_prefix(
                    harness,
                    interrupted,
                    key_prefix="v49e-parser-marker-prefix",
                )
                detected_at = _recovery_detected_at(harness, interrupted[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(
                        interrupted[-1].recorded_monotonic_ns + 1_000
                    ),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-parser-marker-recovery",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert len(chain) == 4
                assert type(chain[-2].payload) is TerminalTransitionPayloadV49C
                assert (
                    chain[-2].payload.kind
                    is TerminalTransitionKindV49C.WS_CLOSE_RECEIVED
                )
                assert chain[-1].payload.cause_code == "PROCESS_RESTART"
                assert all(
                    event.event_kind
                    is not TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
                    for event in chain
                )
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_successful_half_close_repairs_fin_marker_before_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-half-close-marker-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-half-close-marker-raw",
                )
                events, _, tls_marker, control_event = (
                    actor_contract._local_tls_accepted_prefix()
                )
                half_attempt = actor_contract._append_half_close_attempt(
                    events,
                    tls_marker,
                    control_event,
                )
                actor_contract._append_half_close_result(
                    events,
                    half_attempt,
                    result_kind=actor_contract.TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED,
                )
                assert events[0] == raw_event
                _append_actor_contract_prefix(
                    harness,
                    events,
                    key_prefix="v49e-half-close-marker-prefix",
                )
                detected_at = _recovery_detected_at(harness, events[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(events[-1].recorded_monotonic_ns + 1_000),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-half-close-marker-recovery",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[-2].payload.kind is (
                    TerminalTransitionKindV49C.TCP_FIN_SENT
                )
                assert chain[-1].payload.cause_code == "PROCESS_RESTART"
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_shutdown_observation_repairs_exact_marker_before_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-shutdown-marker-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-shutdown-marker-raw",
                )
                events, state, fin_marker, _ = (
                    actor_contract._local_tls_and_half_close_prefix()
                )
                actor_contract._observe_shutdown(
                    events,
                    state,
                    operation_sequence=2,
                    observation_sequence=1,
                    kind=(
                        actor_contract.TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                    ),
                    cause_event_id=fin_marker.transport_actor_event_id,
                    peer_received=True,
                )
                interrupted = events[:-1]
                assert interrupted[0] == raw_event
                _append_actor_contract_prefix(
                    harness,
                    interrupted,
                    key_prefix="v49e-shutdown-marker-prefix",
                )
                detected_at = _recovery_detected_at(harness, interrupted[-1])
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )

                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(
                        interrupted[-1].recorded_monotonic_ns + 1_000
                    ),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-shutdown-marker-recovery",
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[-2].payload.kind is (
                    TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED
                )
                assert chain[-1].payload.cause_code == "PROCESS_RESTART"
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_reconcile_rejects_terminal_actor_tail_without_legacy_pair() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-terminal-without-pair-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                raw = _close_raw(committed)
                raw_event = harness.store.append_actor_raw_ingress_v49c_for_test(
                    raw,
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="v49e-corrupt-terminal-raw",
                ).event
                state = reduce_transport_actor_chain_v49e((raw_event,))
                terminal = _event_with_payload(
                    raw_event,
                    TerminalTransitionPayloadV49C(
                        transport_session_id=committed.session.transport_session_id,
                        transition_sequence=state.transition_sequence + 1,
                        parent_terminal_state_id=state.terminal_state_id,
                        kind=TerminalTransitionKindV49C.FATAL,
                        cause_code="PROCESS_RESTART",
                    ),
                )
                harness.store._clock = lambda: (
                    terminal.recorded_at
                    + timedelta(  # noqa: SLF001
                        seconds=2
                    )
                )
                with harness.store._v49e_composite_transaction():  # noqa: SLF001
                    harness.store._append_transport_actor_event_record_core(  # noqa: SLF001
                        terminal,
                        operation_now=harness.store._now(),  # noqa: SLF001
                        allow_raw_event=False,
                    )
                before = harness.store._last_receipt()[0]  # noqa: SLF001

                with pytest.raises(
                    PhysicalProjectionV4VerificationError,
                    match="exactly one legacy termination",
                ):
                    harness.store.reconcile_unterminated_transport_sessions(
                        detected_at=terminal.recorded_at + timedelta(seconds=1),
                        detected_monotonic_ns=1,
                        detected_monotonic_clock_domain_id=sha256_digest(
                            {"domain": "v49e-corrupt-restart-domain"}
                        ),
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_prefix="v49e-corrupt-terminal",
                    )
                assert harness.store._last_receipt()[0] == before  # noqa: SLF001
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM transport_session_terminations"
                    ).fetchone()[0]
                    == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_actor_reconciliation_fault_rolls_back_restart_pair() -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_transport_session_termination_insert":
            raise RuntimeError("startup-restart-pair-storage-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49e-restart-rollback-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                committed = await _establish(harness)
                raw = _close_raw(committed)
                raw_event = harness.store.append_actor_raw_ingress_v49c_for_test(
                    raw,
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="v49e-restart-rollback-raw",
                ).event
                detected_at = raw.received_at + timedelta(seconds=1)
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )
                before = harness.store._last_receipt()[0]  # noqa: SLF001
                armed = True
                with pytest.raises(
                    RuntimeError, match="startup-restart-pair-storage-failure"
                ):
                    harness.store.reconcile_unterminated_transport_sessions(
                        detected_at=detected_at,
                        detected_monotonic_ns=1,
                        detected_monotonic_clock_domain_id=sha256_digest(
                            {"domain": "v49e-rollback-restart-domain"}
                        ),
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_prefix="v49e-restart-rollback",
                    )
                assert harness.store._last_receipt()[0] == before  # noqa: SLF001
                assert harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                ) == (raw_event,)
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM transport_session_terminations"
                    ).fetchone()[0]
                    == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_projection_raw_close_cursor_requires_exact_local_marker_and_no_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-local-close-cursor-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-local-cursor-raw",
                )
                shutdown_command = _shutdown_command_event_after(raw_event)
                harness.store.append_transport_actor_event_v49c_for_test(
                    shutdown_command,
                    idempotency_key="v49e-local-cursor-shutdown-command",
                )
                local_command = _wire_event_after(
                    shutdown_command,
                    wire_origin=OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND,
                    logical_opcode=WebSocketOpcodeV49C.CLOSE,
                    logical_payload=b"\x03\xe8",
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    local_command,
                    idempotency_key="v49e-local-cursor-command",
                )
                state = reduce_transport_actor_chain_v49e(
                    (raw_event, shutdown_command, local_command)
                )
                sent_marker = _event_with_payload(
                    local_command,
                    TerminalTransitionPayloadV49C(
                        transport_session_id=committed.session.transport_session_id,
                        transition_sequence=state.transition_sequence + 1,
                        parent_terminal_state_id=state.terminal_state_id,
                        kind=TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                        obligation_id=local_command.payload.outbound_operation_id,
                    ),
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    sent_marker,
                    idempotency_key="v49e-local-cursor-sent-marker",
                )

                peer_first, _, _ = actor_contract._websocket_close_prefix()
                assert peer_first[0] == raw_event
                peer_parser = next(
                    event
                    for event in peer_first
                    if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                )
                assert type(peer_parser.payload) is ParserTransitionPayloadV49C
                local_parser_payload = replace(
                    peer_parser.payload,
                    cursor_before=replace(
                        peer_parser.payload.cursor_before,
                        websocket_state=WebSocketParserStateV49C.CLOSING,
                    ),
                    ordered_protocol_output_chunks_base64=(),
                    ordered_protocol_output_chunks_sha256=(),
                    protocol_output_batch_sha256=None,
                )
                recorded_at = max(
                    sent_marker.recorded_at + timedelta(microseconds=1),
                    local_parser_payload.processed_at + timedelta(microseconds=1),
                )
                recorded_ns = max(
                    sent_marker.recorded_monotonic_ns + 1,
                    local_parser_payload.processed_monotonic_ns + 1,
                )
                local_parser = TransportActorEventV49C.create(
                    **_authority(sent_marker),
                    recorded_at=recorded_at,
                    recorded_monotonic_ns=recorded_ns,
                    actor_sequence=sent_marker.actor_sequence + 1,
                    previous_event_id=sent_marker.transport_actor_event_id,
                    event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
                    payload=local_parser_payload,
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    local_parser,
                    idempotency_key="v49e-local-cursor-peer-close",
                )
                assert (
                    harness.store._assert_actor_parser_raw_bytes_v49d(  # noqa: SLF001
                        local_parser
                    )
                    == b""
                )
                assert local_parser_payload.cursor_after.websocket_state is (
                    WebSocketParserStateV49C.CLOSING
                )
                assert not local_parser_payload.ordered_protocol_output_chunks_base64
                harness.store.verify()

                automatic_close = _masked_client_frame(0x8, b"")
                automatic_encoded = (base64.b64encode(automatic_close).decode("ascii"),)
                automatic_hashes = (hashlib.sha256(automatic_close).hexdigest(),)
                automatic_batch = sha256_digest(
                    {
                        "domain": "RiskYieldMMActorOrderedProtocolOutputV4_9C",
                        "ordered_chunks_base64": list(automatic_encoded),
                    }
                )
                open_after_local = _recreate_event(
                    local_parser,
                    payload=replace(
                        local_parser_payload,
                        cursor_before=replace(
                            local_parser_payload.cursor_before,
                            websocket_state=WebSocketParserStateV49C.OPEN,
                        ),
                        ordered_protocol_output_chunks_base64=automatic_encoded,
                        ordered_protocol_output_chunks_sha256=automatic_hashes,
                        protocol_output_batch_sha256=automatic_batch,
                    ),
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="contradicts its prior local WS_CLOSE_SENT",
                ):
                    harness.store._assert_actor_parser_raw_bytes_v49d(  # noqa: SLF001
                        open_after_local
                    )

                repeated_reply = _recreate_event(
                    local_parser,
                    payload=replace(
                        local_parser_payload,
                        ordered_protocol_output_chunks_base64=automatic_encoded,
                        ordered_protocol_output_chunks_sha256=automatic_hashes,
                        protocol_output_batch_sha256=automatic_batch,
                    ),
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="repeats the local automatic response",
                ):
                    harness.store._assert_actor_parser_raw_bytes_v49d(  # noqa: SLF001
                        repeated_reply
                    )

                before_marker = TransportActorEventV49C.create(
                    **_authority(local_parser),
                    recorded_at=local_parser.recorded_at,
                    recorded_monotonic_ns=local_parser.recorded_monotonic_ns,
                    actor_sequence=sent_marker.actor_sequence,
                    previous_event_id=local_command.transport_actor_event_id,
                    event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
                    payload=local_parser_payload,
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="lacks its exact WS_CLOSE_SENT marker",
                ):
                    harness.store._assert_actor_parser_raw_bytes_v49d(  # noqa: SLF001
                        before_marker
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_command_timeout_uses_sealed_dual_clock_evidence_and_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-close-timeout-bridge-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-timeout-bridge-raw",
                )
                shutdown_command = _shutdown_command_event_after(raw_event)
                harness.store.append_transport_actor_event_v49c_for_test(
                    shutdown_command,
                    idempotency_key="v49e-local-terminal-shutdown-command",
                )
                local_command = _wire_event_after(
                    shutdown_command,
                    wire_origin=OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND,
                    logical_opcode=WebSocketOpcodeV49C.CLOSE,
                    logical_payload=b"\x03\xe8",
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    local_command,
                    idempotency_key="v49e-timeout-bridge-local-command",
                )
                state = reduce_transport_actor_chain_v49e(
                    (raw_event, shutdown_command, local_command)
                )
                sent_marker = _event_with_payload(
                    local_command,
                    TerminalTransitionPayloadV49C(
                        transport_session_id=committed.session.transport_session_id,
                        transition_sequence=state.transition_sequence + 1,
                        parent_terminal_state_id=state.terminal_state_id,
                        kind=TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                        obligation_id=local_command.payload.outbound_operation_id,
                    ),
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    sent_marker,
                    idempotency_key="v49e-timeout-bridge-sent-marker",
                )
                state = reduce_transport_actor_chain_v49e(
                    (raw_event, shutdown_command, local_command, sent_marker)
                )
                command = shutdown_command.payload
                assert type(command) is LocalShutdownCommandStartedPayloadV49E
                owner = committed.binding
                operation = "LOCAL_WEBSOCKET_CLOSE_PREPARATION"
                owner_evidence_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
                        "transport_session_id": (
                            committed.session.transport_session_id
                        ),
                        "kernel_socket_identity": owner.kernel_socket_identity,
                        "driver_evidence_nonce_sha256": (
                            committed.session.session_nonce
                        ),
                        "operation": operation,
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                    }
                )
                harness.store._clock = lambda: (  # noqa: SLF001
                    command.shutdown_deadline_at + timedelta(seconds=1)
                )

                def deadline_evidence_event(
                    *,
                    observed_at: datetime,
                    observed_monotonic_ns: int,
                ) -> TransportActorEventV49C:
                    evidence = LocalShutdownDeadlineEvidencePayloadV49E(
                        local_shutdown_command_started_event_id=(
                            shutdown_command.transport_actor_event_id
                        ),
                        shutdown_deadline_monotonic_ns=(
                            command.shutdown_deadline_monotonic_ns
                        ),
                        operation=operation,
                        classification=(
                            LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                        ),
                        owner_evidence_id=owner_evidence_id,
                        kernel_socket_identity=owner.kernel_socket_identity,
                        driver_evidence_nonce_sha256=(committed.session.session_nonce),
                        observed_at=observed_at,
                        observed_monotonic_ns=observed_monotonic_ns,
                    )
                    return TransportActorEventV49C.create(
                        **_authority(sent_marker),
                        recorded_at=observed_at,
                        recorded_monotonic_ns=observed_monotonic_ns,
                        actor_sequence=sent_marker.actor_sequence + 1,
                        previous_event_id=sent_marker.transport_actor_event_id,
                        event_kind=(
                            TransportActorEventKindV49C.LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
                        ),
                        payload=evidence,
                    )

                early_evidence = deadline_evidence_event(
                    observed_at=command.shutdown_deadline_at
                    - timedelta(microseconds=1),
                    observed_monotonic_ns=(command.shutdown_deadline_monotonic_ns - 1),
                )
                before = harness.store._last_receipt()[0]  # noqa: SLF001
                with pytest.raises(PhysicalProjectionV4ConflictError):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        early_evidence,
                        idempotency_key="v49e-timeout-bridge-early",
                    )
                assert harness.store._last_receipt()[0] == before  # noqa: SLF001

                deadline_evidence = deadline_evidence_event(
                    observed_at=command.shutdown_deadline_at,
                    observed_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    deadline_evidence,
                    idempotency_key="v49e-timeout-bridge-evidence",
                )
                state = reduce_transport_actor_chain_v49e(
                    (
                        raw_event,
                        shutdown_command,
                        local_command,
                        sent_marker,
                        deadline_evidence,
                    )
                )
                timeout_payload = TerminalTransitionPayloadV49C(
                    transport_session_id=committed.session.transport_session_id,
                    transition_sequence=state.transition_sequence + 1,
                    parent_terminal_state_id=state.terminal_state_id,
                    kind=TerminalTransitionKindV49C.TIMEOUT,
                    cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                )
                terminal = TransportActorEventV49C.create(
                    **_authority(deadline_evidence),
                    recorded_at=(
                        deadline_evidence.recorded_at + timedelta(microseconds=1)
                    ),
                    recorded_monotonic_ns=(deadline_evidence.recorded_monotonic_ns + 1),
                    actor_sequence=deadline_evidence.actor_sequence + 1,
                    previous_event_id=deadline_evidence.transport_actor_event_id,
                    event_kind=TransportActorEventKindV49C.TERMINAL_TRANSITION,
                    payload=timeout_payload,
                )
                exact_chain = (
                    raw_event,
                    shutdown_command,
                    local_command,
                    sent_marker,
                    deadline_evidence,
                    terminal,
                )
                bridge = harness.store._derive_actor_terminal_bridge_v49e(  # noqa: SLF001
                    exact_chain
                )
                assert bridge.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert bridge.detected_at == deadline_evidence.payload.observed_at
                assert bridge.detected_monotonic_ns == (
                    deadline_evidence.payload.observed_monotonic_ns
                )

                result = harness.store.converge_actor_terminal_v49e_for_test(
                    terminal,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-timeout-bridge-convergence",
                )
                assert result.termination.detected_at == (
                    deadline_evidence.payload.observed_at
                )
                assert result.termination.detected_monotonic_ns == (
                    deadline_evidence.payload.observed_monotonic_ns
                )
                after = harness.store._last_receipt()[0]  # noqa: SLF001
                assert after == before + 3

                replay = harness.store.converge_actor_terminal_v49e_for_test(
                    terminal,
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_key="v49e-timeout-bridge-convergence",
                )
                assert replay == result
                assert harness.store._last_receipt()[0] == after  # noqa: SLF001
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_terminal_ingress_after_progress_recomputes_evidence_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(
            prefix="ry-v49e-ingress-progress-recovery-"
        ) as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-ingress-progress-raw",
                )
                shutdown_command = _shutdown_command_event_after(raw_event)
                harness.store.append_transport_actor_event_v49c_for_test(
                    shutdown_command,
                    idempotency_key="v49e-ingress-progress-command",
                )
                local_command = _wire_event_after(
                    shutdown_command,
                    wire_origin=OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND,
                    logical_opcode=WebSocketOpcodeV49C.CLOSE,
                    logical_payload=b"\x03\xe8",
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    local_command,
                    idempotency_key="v49e-ingress-progress-wire",
                )
                state = reduce_transport_actor_chain_v49e(
                    (raw_event, shutdown_command, local_command)
                )
                sent_marker = _event_with_payload(
                    local_command,
                    TerminalTransitionPayloadV49C(
                        transport_session_id=committed.session.transport_session_id,
                        transition_sequence=state.transition_sequence + 1,
                        parent_terminal_state_id=state.terminal_state_id,
                        kind=TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                        obligation_id=local_command.payload.outbound_operation_id,
                    ),
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    sent_marker,
                    idempotency_key="v49e-ingress-progress-marker",
                )
                command = shutdown_command.payload
                assert type(command) is LocalShutdownCommandStartedPayloadV49E
                ciphertext = b"authenticated-partial-terminal-ingress"
                ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
                driver_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
                        "driver_evidence_nonce_sha256": (
                            committed.session.session_nonce
                        ),
                        "operation": "TERMINAL_CLOSE_INGRESS",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                    }
                )
                owner_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
                        "transport_session_id": (
                            committed.session.transport_session_id
                        ),
                        "kernel_socket_identity": (
                            committed.binding.kernel_socket_identity
                        ),
                        "driver_evidence_nonce_sha256": (
                            committed.session.session_nonce
                        ),
                        "operation": "TERMINAL_CLOSE_INGRESS",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                        "driver_evidence_id": driver_id,
                    }
                )
                failure_payload = TerminalIngressFailurePayloadV49E(
                    local_shutdown_command_started_event_id=(
                        shutdown_command.transport_actor_event_id
                    ),
                    shutdown_deadline_monotonic_ns=(
                        command.shutdown_deadline_monotonic_ns
                    ),
                    failure_kind=(
                        TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                    ),
                    operation="TERMINAL_CLOSE_INGRESS",
                    owner_evidence_id=owner_id,
                    driver_evidence_id=driver_id,
                    kernel_socket_identity=(committed.binding.kernel_socket_identity),
                    driver_evidence_nonce_sha256=committed.session.session_nonce,
                    ciphertext_sha256=ciphertext_sha256,
                    ciphertext_octets_received=len(ciphertext),
                    observed_at=command.shutdown_deadline_at,
                    observed_monotonic_ns=command.shutdown_deadline_monotonic_ns,
                )
                failure_event = TransportActorEventV49C.create(
                    **_authority(sent_marker),
                    recorded_at=failure_payload.observed_at,
                    recorded_monotonic_ns=failure_payload.observed_monotonic_ns,
                    actor_sequence=sent_marker.actor_sequence + 1,
                    previous_event_id=sent_marker.transport_actor_event_id,
                    event_kind=TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE,
                    payload=failure_payload,
                )
                harness.store._clock = lambda: (  # noqa: SLF001
                    command.shutdown_deadline_at + timedelta(seconds=2)
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    failure_event,
                    idempotency_key="v49e-ingress-progress-failure",
                )

                forged_driver_id = hashlib.sha256(b"forged-progress-driver").hexdigest()
                forged_owner_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
                        "transport_session_id": (
                            committed.session.transport_session_id
                        ),
                        "kernel_socket_identity": (
                            committed.binding.kernel_socket_identity
                        ),
                        "driver_evidence_nonce_sha256": (
                            committed.session.session_nonce
                        ),
                        "operation": "TERMINAL_CLOSE_INGRESS",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                        "driver_evidence_id": forged_driver_id,
                    }
                )
                forged_payload = object.__new__(TerminalIngressFailurePayloadV49E)
                for field_name in failure_payload.__dataclass_fields__:
                    object.__setattr__(
                        forged_payload,
                        field_name,
                        getattr(failure_payload, field_name),
                    )
                object.__setattr__(
                    forged_payload,
                    "driver_evidence_id",
                    forged_driver_id,
                )
                object.__setattr__(
                    forged_payload,
                    "owner_evidence_id",
                    forged_owner_id,
                )
                forged_event = _recreate_event(
                    failure_event,
                    payload=forged_payload,
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="driver/owner evidence",
                ):
                    harness.store._assert_actor_shutdown_evidence_projection_v49e(  # noqa: SLF001
                        forged_event
                    )

                detected_at = failure_payload.observed_at + timedelta(seconds=1)
                before = harness.store._last_receipt()[0]  # noqa: SLF001
                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(
                        failure_payload.observed_monotonic_ns + 1_000
                    ),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-ingress-progress-recovery",
                )
                assert len(reconciled) == 1
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert reconciled[0].detected_at == failure_payload.observed_at
                assert reconciled[0].detected_monotonic_ns == (
                    failure_payload.observed_monotonic_ns
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[-1].payload.kind is TerminalTransitionKindV49C.TIMEOUT
                assert chain[-1].payload.cause_code == (
                    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                )
                after = harness.store._last_receipt()[0]  # noqa: SLF001
                assert after == before + 2
                replay = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=(
                        failure_payload.observed_monotonic_ns + 1_000
                    ),
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-ingress-progress-recovery",
                )
                assert replay == ()
                assert harness.store._last_receipt()[0] == after  # noqa: SLF001
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_tls_poll_after_progress_recomputes_evidence_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-tls-progress-recovery-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-tls-progress-raw",
                )
                events, _, fin_marker, _ = (
                    actor_contract._local_tls_and_half_close_prefix()
                )
                operation_event = actor_contract._start_tls_operation(
                    events,
                    sequence=2,
                    purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
                    cause_event_id=fin_marker.transport_actor_event_id,
                )
                operation = operation_event.payload
                assert type(operation) is TlsProtocolOperationStartedPayloadV49E
                command_event = _current_shutdown_command(events)
                command = command_event.payload
                assert type(command) is LocalShutdownCommandStartedPayloadV49E
                ciphertext = b"authenticated-partial-tls-shutdown"
                ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
                driver_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
                        "driver_evidence_nonce_sha256": (
                            operation.driver_evidence_nonce_sha256
                        ),
                        "operation": "TLS_SHUTDOWN_POLL",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                    }
                )
                owner_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
                        "transport_session_id": (
                            committed.session.transport_session_id
                        ),
                        "kernel_socket_identity": (
                            committed.binding.kernel_socket_identity
                        ),
                        "driver_evidence_nonce_sha256": (
                            operation.driver_evidence_nonce_sha256
                        ),
                        "operation": "TLS_SHUTDOWN_POLL",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                        "driver_evidence_id": driver_id,
                    }
                )
                failure_event = actor_contract._append(
                    events,
                    TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
                    TlsProtocolOperationFailedPayloadV49E(
                        tls_protocol_operation_started_event_id=(
                            operation_event.transport_actor_event_id
                        ),
                        tls_operation_id=operation.tls_operation_id,
                        purpose=operation.purpose,
                        driver_evidence_nonce_sha256=(
                            operation.driver_evidence_nonce_sha256
                        ),
                        failure_kind=(
                            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                        ),
                        deadline_classification=(
                            LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                        ),
                        shutdown_deadline_monotonic_ns=(
                            command.shutdown_deadline_monotonic_ns
                        ),
                        unsendable_driver_output_sequence=None,
                        unsendable_driver_evidence_id=None,
                        unsendable_owner_evidence_id=None,
                        unsendable_kernel_socket_identity=None,
                        unsendable_ciphertext_sha256=None,
                        unsendable_ciphertext_octets=None,
                        deadline_no_observation_owner_evidence_id=None,
                        deadline_no_observation_kernel_socket_identity=None,
                        deadline_no_observation_operation=None,
                        deadline_after_progress_owner_evidence_id=owner_id,
                        deadline_after_progress_driver_evidence_id=driver_id,
                        deadline_after_progress_kernel_socket_identity=(
                            committed.binding.kernel_socket_identity
                        ),
                        deadline_after_progress_operation="TLS_SHUTDOWN_POLL",
                        deadline_after_progress_ciphertext_sha256=(ciphertext_sha256),
                        deadline_after_progress_ciphertext_octets=len(ciphertext),
                        observed_at=command.shutdown_deadline_at,
                        observed_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
                    ),
                )
                assert events[0] == raw_event
                validate_transport_actor_chain_v49c(events)
                for index, event in enumerate(events[1:-1], start=1):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        event,
                        idempotency_key=f"v49e-tls-progress-prefix-{index}",
                    )
                harness.store._clock = lambda: (  # noqa: SLF001
                    command.shutdown_deadline_at + timedelta(seconds=2)
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    failure_event,
                    idempotency_key="v49e-tls-progress-failure",
                )

                failure = failure_event.payload
                assert type(failure) is TlsProtocolOperationFailedPayloadV49E
                forged_driver_id = hashlib.sha256(
                    b"forged-tls-progress-driver"
                ).hexdigest()
                forged_owner_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
                        "transport_session_id": (
                            committed.session.transport_session_id
                        ),
                        "kernel_socket_identity": (
                            committed.binding.kernel_socket_identity
                        ),
                        "driver_evidence_nonce_sha256": (
                            operation.driver_evidence_nonce_sha256
                        ),
                        "operation": "TLS_SHUTDOWN_POLL",
                        "deadline_ns": command.shutdown_deadline_monotonic_ns,
                        "ciphertext_octets_received": len(ciphertext),
                        "ciphertext_sha256": ciphertext_sha256,
                        "driver_evidence_id": forged_driver_id,
                    }
                )
                forged_payload = object.__new__(TlsProtocolOperationFailedPayloadV49E)
                for field_name in failure.__dataclass_fields__:
                    object.__setattr__(
                        forged_payload,
                        field_name,
                        getattr(failure, field_name),
                    )
                object.__setattr__(
                    forged_payload,
                    "deadline_after_progress_driver_evidence_id",
                    forged_driver_id,
                )
                object.__setattr__(
                    forged_payload,
                    "deadline_after_progress_owner_evidence_id",
                    forged_owner_id,
                )
                forged_event = _recreate_event(
                    failure_event,
                    payload=forged_payload,
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="driver/owner evidence",
                ):
                    harness.store._assert_actor_shutdown_evidence_projection_v49e(  # noqa: SLF001
                        forged_event
                    )

                detected_at = failure.observed_at + timedelta(seconds=1)
                before = harness.store._last_receipt()[0]  # noqa: SLF001
                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=failure.observed_monotonic_ns + 1_000,
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-tls-progress-recovery",
                )
                assert len(reconciled) == 1
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert reconciled[0].detected_at == failure.observed_at
                assert reconciled[0].detected_monotonic_ns == (
                    failure.observed_monotonic_ns
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[-1].payload.kind is TerminalTransitionKindV49C.TIMEOUT
                assert chain[-1].payload.cause_code == (
                    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                )
                after = harness.store._last_receipt()[0]  # noqa: SLF001
                assert after == before + 2
                assert (
                    harness.store.reconcile_unterminated_transport_sessions(
                        detected_at=detected_at,
                        detected_monotonic_ns=(failure.observed_monotonic_ns + 1_000),
                        detected_monotonic_clock_domain_id=(
                            committed.session.monotonic_clock_domain_id
                        ),
                        signer=harness.runtime._signer,  # noqa: SLF001
                        idempotency_prefix="v49e-tls-progress-recovery",
                    )
                    == ()
                )
                assert harness.store._last_receipt()[0] == after  # noqa: SLF001
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_local_terminal_command_roundtrips_recovers_and_rejects_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-local-terminal-wire-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                _, raw_event = _bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-local-terminal-raw",
                )

                application_without_intent = _wire_event_after(
                    raw_event,
                    wire_origin=OutboundWireOriginV49C.APPLICATION_INTENT,
                    logical_opcode=WebSocketOpcodeV49C.TEXT,
                    logical_payload=b"{}",
                    outbound_operation_id=sha256_digest(
                        {"domain": "v49e-missing-application-intent"}
                    ),
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="lacks its durable subscription intent",
                ):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        application_without_intent,
                        idempotency_key="v49e-local-terminal-missing-intent",
                    )
                assert harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                ) == (raw_event,)

                shutdown_command = _shutdown_command_event_after(raw_event)
                harness.store.append_transport_actor_event_v49c_for_test(
                    shutdown_command,
                    idempotency_key="v49e-local-terminal-shutdown-command",
                )
                local_command = _wire_event_after(
                    shutdown_command,
                    wire_origin=OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND,
                    logical_opcode=WebSocketOpcodeV49C.CLOSE,
                    logical_payload=b"\x03\xe8",
                )
                harness.store.append_transport_actor_event_v49c_for_test(
                    local_command,
                    idempotency_key="v49e-local-terminal-command",
                )
                assert harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                ) == (raw_event, shutdown_command, local_command)

                detected_at = _recovery_detected_at(harness, local_command)
                harness.store._clock = lambda: (
                    detected_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )
                reconciled = harness.store.reconcile_unterminated_transport_sessions(
                    detected_at=detected_at,
                    detected_monotonic_ns=local_command.recorded_monotonic_ns + 1_000,
                    detected_monotonic_clock_domain_id=(
                        committed.session.monotonic_clock_domain_id
                    ),
                    signer=harness.runtime._signer,  # noqa: SLF001
                    idempotency_prefix="v49e-local-terminal-recovery",
                )
                assert len(reconciled) == 1
                assert (
                    reconciled[0].reason
                    is TransportSessionTerminationReasonV4.PROCESS_RESTART
                )
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain[1] == shutdown_command
                assert chain[2] == local_command
                assert type(chain[3].payload) is TerminalTransitionPayloadV49C
                assert chain[3].payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT
                assert chain[3].payload.obligation_id == (
                    local_command.payload.outbound_operation_id
                )
                assert type(chain[-1].payload) is TerminalTransitionPayloadV49C
                assert chain[-1].payload.kind is TerminalTransitionKindV49C.FATAL
                assert chain[-1].payload.cause_code == "PROCESS_RESTART"
                harness.store.verify()

                connection = harness.store._connection  # noqa: SLF001
                trigger = connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'trigger'
                      AND tbl_name = 'transport_actor_events_v49c'
                      AND sql LIKE '%UPDATE%'
                    ORDER BY name LIMIT 1
                    """
                ).fetchone()
                assert trigger is not None
                connection.execute(f'DROP TRIGGER "{trigger[0]}"')
                mutated_payload = local_command.payload.as_dict()
                mutated_payload["wire_origin"] = (
                    OutboundWireOriginV49C.APPLICATION_INTENT.value
                )
                connection.execute(
                    """
                    UPDATE transport_actor_events_v49c
                    SET payload_blob = ?
                    WHERE transport_actor_event_id = ?
                    """,
                    (
                        json.dumps(
                            mutated_payload,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8"),
                        bytes.fromhex(local_command.transport_actor_event_id),
                    ),
                )
                connection.commit()
                with pytest.raises(PhysicalProjectionV4VerificationError):
                    harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())

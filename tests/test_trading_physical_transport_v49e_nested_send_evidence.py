from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
    KernelSendAttemptPayloadV49C,
    KernelSendFailureKindV49E,
    KernelSendFailurePayloadV49E,
    LocalShutdownCommandStartedPayloadV49E,
    OutboundWirePreparedPayloadV49C,
    TlsCiphertextPreparedPayloadV49C,
    TlsControlCiphertextPreparedPayloadV49E,
    TlsControlKernelSendAttemptPayloadV49E,
    TlsControlKernelSendFailurePayloadV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    reduce_transport_actor_chain_v49e,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
    TransportActorAuthorityV49C,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    OutboundObligationLayerV49C,
    TerminalTransitionKindV49C,
)
from tests import (
    test_trading_physical_transport_actor_v49e_terminal_contract as actor_contract,
)
from tests import (
    test_trading_physical_transport_projection_v49e_terminal as projection_contract,
)
from tests import (
    test_trading_physical_transport_session_actor_v49e_terminal as session_contract,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
)

UTC = timezone.utc
DEADLINE_AT = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)
DEADLINE_NS = 9_000_000_000
SendType = Literal["ordinary", "tls_control"]


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _driver_send_evidence_id(values: dict[str, Any]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "driver_evidence_nonce_sha256": (values["driver_evidence_nonce_sha256"]),
            "send_kind": values["send_kind"],
            "transport_sequence": values["transport_sequence"],
            "ciphertext_batch_sha256": values["ciphertext_batch_sha256"],
            "ciphertext_octets": values["ciphertext_octets"],
            "ciphertext_start_octet": values["ciphertext_start_octet"],
            "requested_octets": values["requested_octets"],
            "exact_slice_sha256": values["exact_slice_sha256"],
            "deadline_ns": values["shutdown_deadline_monotonic_ns"],
            "would_block_count": values["would_block_count"],
        }
    )


def _owner_send_evidence_id(
    values: dict[str, Any],
    *,
    driver_evidence_id: str,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMOwnerTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "transport_session_id": actor_contract.AUTHORITY["transport_session_id"],
            "kernel_socket_identity": values["kernel_socket_identity"],
            "driver_evidence_nonce_sha256": (values["driver_evidence_nonce_sha256"]),
            "send_kind": values["send_kind"],
            "transport_sequence": values["transport_sequence"],
            "ciphertext_batch_sha256": values["ciphertext_batch_sha256"],
            "ciphertext_octets": values["ciphertext_octets"],
            "ciphertext_start_octet": values["ciphertext_start_octet"],
            "requested_octets": values["requested_octets"],
            "exact_slice_sha256": values["exact_slice_sha256"],
            "deadline_ns": values["shutdown_deadline_monotonic_ns"],
            "would_block_count": values["would_block_count"],
            "driver_evidence_id": driver_evidence_id,
        }
    )


def _send_failure_values(
    send_type: SendType,
    *,
    driver_evidence_id: str | None = None,
) -> tuple[type[Any], dict[str, Any], tuple[str, ...], str]:
    ciphertext = f"{send_type}-ciphertext".encode()
    encoded = (base64.b64encode(ciphertext).decode("ascii"),)
    send_kind = "LOCAL_WEBSOCKET_CLOSE" if send_type == "ordinary" else "TLS_CONTROL"
    values: dict[str, Any] = {
        "local_shutdown_command_started_event_id": _digest("shutdown-command"),
        "shutdown_deadline_monotonic_ns": DEADLINE_NS,
        "kernel_attempt_ordinal": 1,
        "ciphertext_batch_sha256": _digest(f"{send_type}-ciphertext-batch"),
        "ciphertext_octets": len(ciphertext),
        "ciphertext_start_octet": 0,
        "requested_octets": len(ciphertext),
        "failure_kind": (
            KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
        ),
        "owner_evidence_id": None,
        "kernel_socket_identity": _digest("admitted-kernel-socket"),
        "driver_evidence_nonce_sha256": _digest("driver-evidence-nonce"),
        "owner_deadline_operation": None,
        "send_kind": send_kind,
        "transport_sequence": 1,
        "exact_slice_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "would_block_count": 1,
        "driver_evidence_id": None,
        "observed_at": DEADLINE_AT,
        "observed_monotonic_ns": DEADLINE_NS,
    }
    if send_type == "ordinary":
        payload_type: type[Any] = KernelSendFailurePayloadV49E
        values.update(
            kernel_send_attempt_event_id=_digest("ordinary-send-attempt"),
            tls_ciphertext_prepared_event_id=_digest("ordinary-tls-ciphertext"),
        )
    else:
        payload_type = TlsControlKernelSendFailurePayloadV49E
        values.update(
            tls_control_kernel_send_attempt_event_id=(
                _digest("tls-control-send-attempt")
            ),
            tls_control_ciphertext_prepared_event_id=(
                _digest("tls-control-ciphertext")
            ),
        )
    exact_driver_id = _driver_send_evidence_id(values)
    selected_driver_id = (
        exact_driver_id if driver_evidence_id is None else driver_evidence_id
    )
    values["driver_evidence_id"] = selected_driver_id
    values["owner_evidence_id"] = _owner_send_evidence_id(
        values,
        driver_evidence_id=selected_driver_id,
    )
    return payload_type, values, encoded, send_kind


def _event_for_send_failure(
    send_type: SendType,
    payload: KernelSendFailurePayloadV49E | TlsControlKernelSendFailurePayloadV49E,
) -> TransportActorEventV49C:
    event_kind = (
        TransportActorEventKindV49C.KERNEL_SEND_FAILURE
        if send_type == "ordinary"
        else TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE
    )
    return TransportActorEventV49C.create(
        **actor_contract.AUTHORITY,
        recorded_at=DEADLINE_AT + timedelta(microseconds=1),
        recorded_monotonic_ns=DEADLINE_NS + 1,
        actor_sequence=1,
        previous_event_id=None,
        event_kind=event_kind,
        payload=payload,
    )


def _rehash_actor_event_mapping(mapping: dict[str, Any]) -> None:
    mapping["transport_actor_event_id"] = sha256_digest(
        {
            "canonicalization_version": mapping["canonicalization_version"],
            "domain": "RiskYieldMMTransportActorEventV4_9C",
            "payload": {
                key: value
                for key, value in mapping.items()
                if key
                not in {
                    "canonicalization_version",
                    "schema_version",
                    "transport_actor_event_id",
                }
            },
            "schema_version": mapping["schema_version"],
        }
    )


def _actor_send_failure_chain(
    send_type: SendType,
    *,
    coordinated_forgery: bool,
) -> tuple[list[TransportActorEventV49C], Any]:
    if send_type == "ordinary":
        completed, _, _ = actor_contract._websocket_close_prefix()
        attempt_index = next(
            index
            for index, event in enumerate(completed)
            if type(event.payload) is KernelSendAttemptPayloadV49C
        )
        events = list(completed[: attempt_index + 2])
        attempt_event = events[attempt_index]
        attempt = attempt_event.payload
        assert type(attempt) is KernelSendAttemptPayloadV49C
        tls_event = next(
            event
            for event in events
            if event.transport_actor_event_id
            == attempt.tls_ciphertext_prepared_event_id
        )
        tls = tls_event.payload
        assert type(tls) is TlsCiphertextPreparedPayloadV49C
        wire_event = next(
            event
            for event in events
            if event.transport_actor_event_id == tls.outbound_wire_prepared_event_id
        )
        wire = wire_event.payload
        assert type(wire) is OutboundWirePreparedPayloadV49C
        ciphertext = b"".join(
            base64.b64decode(chunk, validate=True)
            for chunk in tls.ordered_ciphertext_chunks_base64
        )
        values: dict[str, Any] = {
            "kernel_send_attempt_event_id": attempt_event.transport_actor_event_id,
            "tls_ciphertext_prepared_event_id": tls_event.transport_actor_event_id,
            "kernel_attempt_ordinal": attempt.kernel_attempt_ordinal,
            "ciphertext_batch_sha256": attempt.ciphertext_batch_sha256,
            "ciphertext_octets": attempt.ciphertext_octets,
            "ciphertext_start_octet": attempt.ciphertext_start_octet,
            "requested_octets": attempt.requested_octets,
            "local_shutdown_command_started_event_id": None,
            "shutdown_deadline_monotonic_ns": wire.send_not_after_monotonic_ns,
            "failure_kind": (
                KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
            ),
            "owner_evidence_id": None,
            "kernel_socket_identity": _digest("actor-ordinary-kernel-socket"),
            "driver_evidence_nonce_sha256": _digest("actor-ordinary-driver-nonce"),
            "owner_deadline_operation": None,
            "send_kind": "AUTOMATIC_WEBSOCKET_CLOSE",
            "transport_sequence": 1,
            "exact_slice_sha256": hashlib.sha256(
                ciphertext[
                    attempt.ciphertext_start_octet : attempt.ciphertext_start_octet
                    + attempt.requested_octets
                ]
            ).hexdigest(),
            "would_block_count": 1,
            "driver_evidence_id": None,
            "observed_at": wire.send_not_after,
            "observed_monotonic_ns": wire.send_not_after_monotonic_ns,
        }
        payload_type: type[Any] = KernelSendFailurePayloadV49E
        event_kind = TransportActorEventKindV49C.KERNEL_SEND_FAILURE
        layer = OutboundObligationLayerV49C.WEBSOCKET_CLOSE
        obligation_id = wire.outbound_operation_id
        terminal_cause = V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
        state = reduce_transport_actor_chain_v49e(events)
    else:
        events, state, control_event = actor_contract._local_control_prepared_prefix()
        control = control_event.payload
        assert type(control) is TlsControlCiphertextPreparedPayloadV49E
        attempt_event = actor_contract._append_control_attempt(events, control_event)
        attempt = attempt_event.payload
        assert type(attempt) is TlsControlKernelSendAttemptPayloadV49E
        state, _ = actor_contract._terminal(
            events,
            state,
            TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            obligation_id=control_event.transport_actor_event_id,
            send_attempt_id=attempt_event.transport_actor_event_id,
        )
        command_event = next(
            event
            for event in events
            if type(event.payload) is LocalShutdownCommandStartedPayloadV49E
        )
        command = command_event.payload
        assert type(command) is LocalShutdownCommandStartedPayloadV49E
        ciphertext = b"".join(
            base64.b64decode(chunk, validate=True)
            for chunk in control.ordered_ciphertext_chunks_base64
        )
        values = {
            "tls_control_kernel_send_attempt_event_id": (
                attempt_event.transport_actor_event_id
            ),
            "tls_control_ciphertext_prepared_event_id": (
                control_event.transport_actor_event_id
            ),
            "local_shutdown_command_started_event_id": (
                command_event.transport_actor_event_id
            ),
            "shutdown_deadline_monotonic_ns": (command.shutdown_deadline_monotonic_ns),
            "kernel_attempt_ordinal": attempt.kernel_attempt_ordinal,
            "ciphertext_batch_sha256": attempt.ciphertext_batch_sha256,
            "ciphertext_octets": attempt.ciphertext_octets,
            "ciphertext_start_octet": attempt.ciphertext_start_octet,
            "requested_octets": attempt.requested_octets,
            "failure_kind": (
                KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
            ),
            "owner_evidence_id": None,
            "kernel_socket_identity": _digest("actor-control-kernel-socket"),
            "driver_evidence_nonce_sha256": control.driver_evidence_nonce_sha256,
            "owner_deadline_operation": None,
            "send_kind": "TLS_CONTROL",
            "transport_sequence": control.control_sequence,
            "exact_slice_sha256": hashlib.sha256(
                ciphertext[
                    attempt.ciphertext_start_octet : attempt.ciphertext_start_octet
                    + attempt.requested_octets
                ]
            ).hexdigest(),
            "would_block_count": 1,
            "driver_evidence_id": None,
            "observed_at": command.shutdown_deadline_at,
            "observed_monotonic_ns": command.shutdown_deadline_monotonic_ns,
        }
        payload_type = TlsControlKernelSendFailurePayloadV49E
        event_kind = TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE
        layer = OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
        obligation_id = control_event.transport_actor_event_id
        terminal_cause = V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE

    exact_driver_id = _driver_send_evidence_id(values)
    values["driver_evidence_id"] = exact_driver_id
    values["owner_evidence_id"] = _owner_send_evidence_id(
        values,
        driver_evidence_id=exact_driver_id,
    )
    failure = payload_type(**values)
    if coordinated_forgery:
        forged_driver_id = _digest(f"actor-{send_type}-coordinated-driver")
        object.__setattr__(failure, "driver_evidence_id", forged_driver_id)
        object.__setattr__(
            failure,
            "owner_evidence_id",
            _owner_send_evidence_id(
                values,
                driver_evidence_id=forged_driver_id,
            ),
        )
    actor_contract._append(events, event_kind, failure)
    state, _ = actor_contract._terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        layer=layer,
        obligation_id=obligation_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    state, _ = actor_contract._terminal(
        events,
        state,
        TerminalTransitionKindV49C.TIMEOUT,
        cause_code=terminal_cause,
    )
    return events, state


@pytest.mark.parametrize("send_type", ("ordinary", "tls_control"))
def test_actor_payload_rejects_coordinated_forged_send_evidence_ids(
    send_type: SendType,
) -> None:
    forged_driver_id = _digest(f"{send_type}-coordinated-forged-driver")
    payload_type, forged_values, _, _ = _send_failure_values(
        send_type,
        driver_evidence_id=forged_driver_id,
    )

    with pytest.raises(
        CanonicalizationError,
        match="driver evidence ID differs from exact fields",
    ):
        payload_type(**forged_values)

    exact_payload_type, exact_values, _, _ = _send_failure_values(send_type)
    exact_payload = exact_payload_type(**exact_values)
    mapping = copy.deepcopy(_event_for_send_failure(send_type, exact_payload).as_dict())
    mapping["payload"]["driver_evidence_id"] = forged_driver_id
    mapping["payload"]["owner_evidence_id"] = forged_values["owner_evidence_id"]
    _rehash_actor_event_mapping(mapping)
    with pytest.raises(
        CanonicalizationError,
        match="driver evidence ID differs from exact fields",
    ):
        TransportActorEventV49C.from_mapping(mapping)


@pytest.mark.parametrize("send_type", ("ordinary", "tls_control"))
def test_actor_chain_rejects_coordinated_forged_send_evidence_ids(
    send_type: SendType,
) -> None:
    exact_events, exact_state = _actor_send_failure_chain(
        send_type,
        coordinated_forgery=False,
    )
    assert validate_transport_actor_chain_v49c(exact_events) == exact_state

    forged_events, _ = _actor_send_failure_chain(
        send_type,
        coordinated_forgery=True,
    )
    with pytest.raises(
        CanonicalizationError,
        match="send failure differs from exact",
    ):
        validate_transport_actor_chain_v49c(forged_events)


@pytest.mark.parametrize("send_type", ("ordinary", "tls_control"))
def test_projection_rejects_coordinated_forged_send_evidence_ids(
    send_type: SendType,
) -> None:
    payload_type, values, encoded, send_kind = _send_failure_values(send_type)
    payload = payload_type(**values)
    forged_driver_id = _digest(f"{send_type}-projection-forged-driver")
    forged_owner_id = _owner_send_evidence_id(
        values,
        driver_evidence_id=forged_driver_id,
    )
    object.__setattr__(payload, "driver_evidence_id", forged_driver_id)
    object.__setattr__(payload, "owner_evidence_id", forged_owner_id)
    event = _event_for_send_failure(send_type, payload)
    projection = object.__new__(PhysicalProjectionStoreV4)

    with pytest.raises(
        PhysicalProjectionV4ConflictError,
        match="changes exact ciphertext evidence",
    ):
        projection._assert_send_failure_evidence_v49e(  # noqa: SLF001
            event=event,
            payload=payload,
            encoded_chunks=encoded,
            deadline_at=DEADLINE_AT,
            deadline_ns=DEADLINE_NS,
            expected_send_kind=send_kind,
        )


def test_projection_rejects_publicly_consistent_unsendable_tls_foreign_socket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-unsendable-socket-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                projection_contract._bind_actor_contract_harness(
                    harness,
                    committed,
                    monkeypatch,
                    idempotency_key="v49e-unsendable-foreign-socket-raw",
                )
                events, state, fin_marker, _ = (
                    actor_contract._local_tls_and_half_close_prefix()
                )
                operation = actor_contract._start_tls_operation(
                    events,
                    sequence=2,
                    purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
                    cause_event_id=fin_marker.transport_actor_event_id,
                )
                failure_event = actor_contract._fail_tls_operation(
                    events,
                    operation,
                    TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR,
                )
                state, _ = actor_contract._terminal(
                    events,
                    state,
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=(
                        actor_contract.V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE
                    ),
                )
                assert validate_transport_actor_chain_v49c(events) == state

                payload = failure_event.payload
                assert type(payload) is TlsProtocolOperationFailedPayloadV49E
                assert payload.unsendable_kernel_socket_identity != (
                    committed.binding.kernel_socket_identity
                )
                expected_driver_id = sha256_digest(
                    {
                        "domain": ("RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E"),
                        "output_sequence": (payload.unsendable_driver_output_sequence),
                        "driver_evidence_nonce_sha256": (
                            payload.driver_evidence_nonce_sha256
                        ),
                        "ciphertext_sha256": payload.unsendable_ciphertext_sha256,
                        "ciphertext_octets": payload.unsendable_ciphertext_octets,
                    }
                )
                expected_owner_id = sha256_digest(
                    {
                        "domain": (
                            "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E"
                        ),
                        "transport_session_id": failure_event.transport_session_id,
                        "kernel_socket_identity": (
                            payload.unsendable_kernel_socket_identity
                        ),
                        "driver_unsendable_output_id": expected_driver_id,
                        "driver_output_sequence": (
                            payload.unsendable_driver_output_sequence
                        ),
                        "driver_evidence_nonce_sha256": (
                            payload.driver_evidence_nonce_sha256
                        ),
                        "ciphertext_sha256": payload.unsendable_ciphertext_sha256,
                        "ciphertext_octets": payload.unsendable_ciphertext_octets,
                    }
                )
                assert payload.unsendable_driver_evidence_id == expected_driver_id
                assert payload.unsendable_owner_evidence_id == expected_owner_id

                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="changes the admitted kernel socket",
                ):
                    harness.store._assert_actor_tls_driver_projection_v49e(  # noqa: SLF001
                        failure_event
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_removed_tls_failure_api_and_partial_terminal_owner_seams_are_closed() -> None:
    assert not hasattr(
        PhysicalTransportSessionActorV49C,
        "record_tls_operation_failure_v49e",
    )

    async def scenario() -> None:
        events = [session_contract._raw_event()]
        authority = TransportActorAuthorityV49C._from_event(events[0])
        clock = session_contract._Clock(events)
        complete_seams: dict[str, Any] = {
            "terminal_observation_batch_clock": lambda count: tuple(
                (DEADLINE_AT, DEADLINE_NS + index) for index in range(count)
            ),
            "terminal_clock_authorizer": lambda _evidence: None,
            "terminal_clock_restore_authorizer": lambda _events: None,
        }
        seam_names = tuple(complete_seams)
        for selection in range(1, 2 ** len(seam_names) - 1):
            partial = {
                name: complete_seams[name]
                for index, name in enumerate(seam_names)
                if selection & (1 << index)
            }
            with pytest.raises(TypeError, match="one closed capability set"):
                PhysicalTransportSessionActorV49C(
                    journal=session_contract._Journal(events),
                    authority=authority,
                    events=events,
                    observation_clock=clock.observation,
                    **partial,
                )

    asyncio.run(scenario())

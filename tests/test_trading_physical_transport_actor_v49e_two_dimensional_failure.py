from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    TerminalIngressFailureKindV49E,
    TerminalIngressFailurePayloadV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TransportActorEventKindV49C,
    classify_tls_protocol_operation_failure_v49e,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    TerminalTransitionKindV49C,
)
from tests import (
    test_trading_physical_transport_actor_v49e_terminal_contract as contract,
)

UTC = timezone.utc
OBSERVED_AT = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _after_progress_evidence(
    *,
    transport_session_id: str,
    driver_evidence_nonce_sha256: str,
    shutdown_deadline_monotonic_ns: int,
    operation: str = "TLS_SHUTDOWN_POLL",
    driver_evidence_id: str | None = None,
) -> dict[str, Any]:
    kernel_socket_identity = _digest("after-progress-kernel-socket")
    ciphertext_sha256 = _digest("after-progress-ciphertext")
    ciphertext_octets = 17
    exact_driver_evidence_id = sha256_digest(
        {
            "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": ciphertext_octets,
            "ciphertext_sha256": ciphertext_sha256,
        }
    )
    selected_driver_evidence_id = (
        exact_driver_evidence_id if driver_evidence_id is None else driver_evidence_id
    )
    owner_evidence_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": transport_session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": ciphertext_octets,
            "ciphertext_sha256": ciphertext_sha256,
            "driver_evidence_id": selected_driver_evidence_id,
        }
    )
    return {
        "deadline_after_progress_owner_evidence_id": owner_evidence_id,
        "deadline_after_progress_driver_evidence_id": (selected_driver_evidence_id),
        "deadline_after_progress_kernel_socket_identity": (kernel_socket_identity),
        "deadline_after_progress_operation": operation,
        "deadline_after_progress_ciphertext_sha256": ciphertext_sha256,
        "deadline_after_progress_ciphertext_octets": ciphertext_octets,
    }


def _tls_failure_payload(
    *,
    failure_kind: TlsProtocolOperationFailureKindV49E,
    deadline_classification: LocalShutdownDeadlineClassificationV49E | None,
    shutdown_deadline_monotonic_ns: int = 1_000_000_000,
    observed_at: datetime = OBSERVED_AT,
    observed_monotonic_ns: int = 1_000_000_001,
    operation_event: Any | None = None,
    transport_session_id: str = contract.AUTHORITY["transport_session_id"],
    forged_driver_evidence_id: str | None = None,
) -> TlsProtocolOperationFailedPayloadV49E:
    if operation_event is None:
        operation_started_event_id = _digest("tls-operation-started-event")
        tls_operation_id = _digest("tls-operation")
        purpose = TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
        driver_nonce = _digest("driver-evidence-nonce")
    else:
        operation = operation_event.payload
        assert type(operation) is TlsProtocolOperationStartedPayloadV49E
        operation_started_event_id = operation_event.transport_actor_event_id
        tls_operation_id = operation.tls_operation_id
        purpose = operation.purpose
        driver_nonce = operation.driver_evidence_nonce_sha256

    after_progress = (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
    )
    no_observation = (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
    )
    progress_fields = (
        _after_progress_evidence(
            transport_session_id=transport_session_id,
            driver_evidence_nonce_sha256=driver_nonce,
            shutdown_deadline_monotonic_ns=shutdown_deadline_monotonic_ns,
            driver_evidence_id=forged_driver_evidence_id,
        )
        if after_progress
        else {
            "deadline_after_progress_owner_evidence_id": None,
            "deadline_after_progress_driver_evidence_id": None,
            "deadline_after_progress_kernel_socket_identity": None,
            "deadline_after_progress_operation": None,
            "deadline_after_progress_ciphertext_sha256": None,
            "deadline_after_progress_ciphertext_octets": None,
        }
    )
    no_observation_operation = (
        "TLS_SHUTDOWN_POLL"
        if purpose is TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
        else "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION"
    )
    no_observation_socket = _digest("no-observation-kernel-socket")
    no_observation_owner_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
            "transport_session_id": transport_session_id,
            "kernel_socket_identity": no_observation_socket,
            "driver_evidence_nonce_sha256": driver_nonce,
            "operation": no_observation_operation,
            "deadline_ns": shutdown_deadline_monotonic_ns,
        }
    )
    return TlsProtocolOperationFailedPayloadV49E(
        tls_protocol_operation_started_event_id=operation_started_event_id,
        tls_operation_id=tls_operation_id,
        purpose=purpose,
        driver_evidence_nonce_sha256=driver_nonce,
        failure_kind=failure_kind,
        deadline_classification=deadline_classification,
        shutdown_deadline_monotonic_ns=shutdown_deadline_monotonic_ns,
        unsendable_driver_output_sequence=None,
        unsendable_driver_evidence_id=None,
        unsendable_owner_evidence_id=None,
        unsendable_kernel_socket_identity=None,
        unsendable_ciphertext_sha256=None,
        unsendable_ciphertext_octets=None,
        deadline_no_observation_owner_evidence_id=(
            no_observation_owner_id if no_observation else None
        ),
        deadline_no_observation_kernel_socket_identity=(
            no_observation_socket if no_observation else None
        ),
        deadline_no_observation_operation=(
            no_observation_operation if no_observation else None
        ),
        **progress_fields,
        observed_at=observed_at,
        observed_monotonic_ns=observed_monotonic_ns,
    )


def _command(events: list[Any]) -> LocalShutdownCommandStartedPayloadV49E:
    command = next(
        event.payload
        for event in reversed(events)
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    )
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    return command


def test_physical_tls_deadline_failure_requires_actor_clock_classification() -> None:
    with pytest.raises(
        CanonicalizationError,
        match="only physical TLS deadline failures carry actor clock classification",
    ):
        _tls_failure_payload(
            failure_kind=(
                TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
            ),
            deadline_classification=None,
        )


def test_nondeadline_tls_failure_rejects_actor_clock_classification() -> None:
    with pytest.raises(
        CanonicalizationError,
        match="only physical TLS deadline failures carry actor clock classification",
    ):
        _tls_failure_payload(
            failure_kind=TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
            deadline_classification=(LocalShutdownDeadlineClassificationV49E.BOTH_DUE),
        )


@pytest.mark.parametrize(
    ("classification", "expected_terminal_kind", "expected_cause"),
    (
        (
            LocalShutdownDeadlineClassificationV49E.BOTH_DUE,
            TerminalTransitionKindV49C.TIMEOUT,
            V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
        ),
        (
            LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT,
            TerminalTransitionKindV49C.FATAL,
            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
        ),
        (
            LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS,
            TerminalTransitionKindV49C.FATAL,
            V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
        ),
    ),
)
def test_clock_classification_selects_terminal_outcome_without_erasing_evidence(
    classification: LocalShutdownDeadlineClassificationV49E,
    expected_terminal_kind: TerminalTransitionKindV49C,
    expected_cause: str,
) -> None:
    failure = _tls_failure_payload(
        failure_kind=(
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
        ),
        deadline_classification=classification,
    )
    physical_evidence = {
        name: getattr(failure, name)
        for name in (
            "deadline_after_progress_owner_evidence_id",
            "deadline_after_progress_driver_evidence_id",
            "deadline_after_progress_kernel_socket_identity",
            "deadline_after_progress_operation",
            "deadline_after_progress_ciphertext_sha256",
            "deadline_after_progress_ciphertext_octets",
        )
    }
    assert all(value is not None for value in physical_evidence.values())

    assert classify_tls_protocol_operation_failure_v49e(failure) == (
        expected_terminal_kind,
        expected_cause,
    )
    assert failure.failure_kind is (
        TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
    )
    assert {
        name: getattr(failure, name) for name in physical_evidence
    } == physical_evidence


@pytest.mark.parametrize(
    ("declared_classification", "wall_delta", "monotonic_delta"),
    (
        (
            LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT,
            timedelta(0),
            0,
        ),
        (
            LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS,
            timedelta(0),
            -1,
        ),
        (
            LocalShutdownDeadlineClassificationV49E.BOTH_DUE,
            -timedelta(microseconds=1),
            -1,
        ),
    ),
)
def test_actor_recomputes_tls_deadline_classification_from_command_clocks(
    declared_classification: LocalShutdownDeadlineClassificationV49E,
    wall_delta: timedelta,
    monotonic_delta: int,
) -> None:
    events, _, fin_marker, _ = contract._local_tls_and_half_close_prefix()
    operation_event = contract._start_tls_operation(
        events,
        sequence=2,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=fin_marker.transport_actor_event_id,
    )
    command = _command(events)
    failure = _tls_failure_payload(
        failure_kind=(
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
        ),
        deadline_classification=declared_classification,
        shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
        observed_at=command.shutdown_deadline_at + wall_delta,
        observed_monotonic_ns=(
            command.shutdown_deadline_monotonic_ns + monotonic_delta
        ),
        operation_event=operation_event,
    )
    contract._append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
        failure,
    )

    with pytest.raises(
        CanonicalizationError,
        match="TLS operation failure differs from its exact started operation",
    ):
        validate_transport_actor_chain_v49c(events)


def test_actor_rejects_coordinated_after_progress_driver_and_owner_forgery() -> None:
    events, _, fin_marker, _ = contract._local_tls_and_half_close_prefix()
    operation_event = contract._start_tls_operation(
        events,
        sequence=2,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=fin_marker.transport_actor_event_id,
    )
    command = _command(events)
    failure = _tls_failure_payload(
        failure_kind=(
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
        ),
        deadline_classification=LocalShutdownDeadlineClassificationV49E.BOTH_DUE,
        shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
        observed_at=command.shutdown_deadline_at,
        observed_monotonic_ns=command.shutdown_deadline_monotonic_ns,
        operation_event=operation_event,
    )
    forged_driver_evidence_id = _digest("coordinated-forged-driver-evidence")
    forged_owner_evidence_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": contract.AUTHORITY["transport_session_id"],
            "kernel_socket_identity": (
                failure.deadline_after_progress_kernel_socket_identity
            ),
            "driver_evidence_nonce_sha256": (failure.driver_evidence_nonce_sha256),
            "operation": failure.deadline_after_progress_operation,
            "deadline_ns": failure.shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": (
                failure.deadline_after_progress_ciphertext_octets
            ),
            "ciphertext_sha256": (failure.deadline_after_progress_ciphertext_sha256),
            "driver_evidence_id": forged_driver_evidence_id,
        }
    )
    object.__setattr__(
        failure,
        "deadline_after_progress_driver_evidence_id",
        forged_driver_evidence_id,
    )
    object.__setattr__(
        failure,
        "deadline_after_progress_owner_evidence_id",
        forged_owner_evidence_id,
    )
    contract._append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
        failure,
    )

    with pytest.raises(
        CanonicalizationError,
        match="TLS operation failure differs from its exact started operation",
    ):
        validate_transport_actor_chain_v49c(events)


def test_terminal_ingress_rejects_coordinated_driver_and_owner_forgery() -> None:
    events: list[Any] = []
    command_event = contract._append_local_shutdown_command(events)
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    driver_nonce = _digest("terminal-ingress-driver-nonce")
    evidence = _after_progress_evidence(
        transport_session_id=contract.AUTHORITY["transport_session_id"],
        driver_evidence_nonce_sha256=driver_nonce,
        shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
        operation="TERMINAL_CLOSE_INGRESS",
    )
    failure = TerminalIngressFailurePayloadV49E(
        local_shutdown_command_started_event_id=(
            command_event.transport_actor_event_id
        ),
        shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
        failure_kind=(TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS),
        operation="TERMINAL_CLOSE_INGRESS",
        owner_evidence_id=evidence["deadline_after_progress_owner_evidence_id"],
        driver_evidence_id=evidence["deadline_after_progress_driver_evidence_id"],
        kernel_socket_identity=evidence[
            "deadline_after_progress_kernel_socket_identity"
        ],
        driver_evidence_nonce_sha256=driver_nonce,
        ciphertext_sha256=evidence["deadline_after_progress_ciphertext_sha256"],
        ciphertext_octets_received=evidence[
            "deadline_after_progress_ciphertext_octets"
        ],
        observed_at=command.shutdown_deadline_at,
        observed_monotonic_ns=command.shutdown_deadline_monotonic_ns,
    )
    forged_driver_id = _digest("terminal-ingress-forged-driver-evidence")
    forged_owner_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": contract.AUTHORITY["transport_session_id"],
            "kernel_socket_identity": failure.kernel_socket_identity,
            "driver_evidence_nonce_sha256": (failure.driver_evidence_nonce_sha256),
            "operation": failure.operation,
            "deadline_ns": failure.shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": failure.ciphertext_octets_received,
            "ciphertext_sha256": failure.ciphertext_sha256,
            "driver_evidence_id": forged_driver_id,
        }
    )
    object.__setattr__(failure, "driver_evidence_id", forged_driver_id)
    object.__setattr__(failure, "owner_evidence_id", forged_owner_id)
    contract._append(
        events,
        TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE,
        failure,
    )

    with pytest.raises(
        CanonicalizationError,
        match="terminal-ingress failure differs from command/owner evidence",
    ):
        validate_transport_actor_chain_v49c(events)

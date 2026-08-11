from __future__ import annotations

from dataclasses import replace

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49C_RECOVERY_UNKNOWN_SEND_CAUSE,
    V49C_TLS_TRUNCATION_CAUSE,
    V49C_WEBSOCKET_TRUNCATION_CAUSE,
    OutboundObligationLayerV49C,
    PhysicalTransportTerminalV49CStateError,
    TerminalOutcomeV49C,
    TerminalStateV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
    advance_terminal_state_v49c,
    initial_terminal_state_v49c,
    reduce_terminal_transitions_v49c,
    terminalize_pending_send_v49c,
    validate_application_output_allowed_v49c,
    validate_terminal_transition_v49c,
)


def _digest(label: str) -> str:
    return sha256_digest({"label": label})


SESSION_ID = _digest("terminal-session")
WS_OBLIGATION_ID = _digest("ws-close-obligation")
TLS_OBLIGATION_ID = _digest("tls-close-notify-obligation")
APP_OBLIGATION_ID = _digest("application-obligation")


def _transition(
    state: TerminalStateV49C,
    kind: TerminalTransitionKindV49C,
    **overrides: object,
) -> TerminalTransitionPayloadV49C:
    values: dict[str, object] = {
        "transport_session_id": state.transport_session_id,
        "transition_sequence": state.transition_sequence + 1,
        "parent_terminal_state_id": state.terminal_state_id,
        "kind": kind,
    }
    values.update(overrides)
    return TerminalTransitionPayloadV49C(**values)


def _advance(
    state: TerminalStateV49C,
    kind: TerminalTransitionKindV49C,
    **overrides: object,
) -> TerminalStateV49C:
    return advance_terminal_state_v49c(state, _transition(state, kind, **overrides))


def _send_attempt(
    state: TerminalStateV49C,
    *,
    layer: OutboundObligationLayerV49C,
    obligation_id: str,
    label: str,
) -> TerminalStateV49C:
    attempt_id = _digest(f"attempt-{label}")
    state = _advance(
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        obligation_layer=layer,
        obligation_id=obligation_id,
        send_attempt_id=attempt_id,
    )
    return _advance(
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        obligation_layer=layer,
        obligation_id=obligation_id,
        send_attempt_id=attempt_id,
    )


def _send_ws_close(state: TerminalStateV49C, *, attempts: int = 1) -> TerminalStateV49C:
    state = _advance(
        state,
        TerminalTransitionKindV49C.WS_CLOSE_SENT,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
    )
    for index in range(attempts):
        state = _send_attempt(
            state,
            layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
            obligation_id=WS_OBLIGATION_ID,
            label=f"ws-{index}",
        )
    return _advance(
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
    )


def _send_tls_notify(
    state: TerminalStateV49C, *, attempts: int = 1
) -> TerminalStateV49C:
    state = _advance(
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    for index in range(attempts):
        state = _send_attempt(
            state,
            layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            obligation_id=TLS_OBLIGATION_ID,
            label=f"tls-{index}",
        )
    return _advance(
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )


def _state_with_complete_ws_close() -> TerminalStateV49C:
    state = _send_ws_close(initial_terminal_state_v49c(SESSION_ID))
    return _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)


def test_local_initiated_close_reaches_clean_only_after_every_layer() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    assert not state.is_terminal
    assert state.send_retry_allowed

    state = _send_ws_close(state, attempts=2)
    assert state.ws_close_sent
    assert state.ws_output_fully_kernel_accepted
    assert state.ws_send_attempts_resolved == 2
    state = _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    state = _send_tls_notify(state, attempts=2)
    assert state.tls_close_notify_sent
    assert state.tls_close_notify_fully_kernel_accepted
    assert state.tls_send_attempts_resolved == 2
    state = _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)
    state = _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)
    state = _advance(state, TerminalTransitionKindV49C.TCP_EOF_RECEIVED)

    assert not state.is_terminal
    state = _advance(state, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)
    assert state.terminal_outcome is TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    assert state.terminal_cause_code is None
    assert not state.send_retry_allowed


def test_peer_initiated_half_close_can_finish_local_layers_cleanly() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    state = _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    state = _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)
    state = _advance(state, TerminalTransitionKindV49C.TCP_EOF_RECEIVED)
    assert not state.is_terminal

    state = _send_ws_close(state)
    state = _send_tls_notify(state)
    state = _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)
    state = _advance(state, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)

    assert state.terminal_outcome is TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    assert state.ws_close_received and state.ws_close_sent
    assert state.tls_close_notify_received and state.tls_close_notify_sent
    assert state.tcp_eof_received and state.tcp_fin_sent


@pytest.mark.parametrize(
    ("kind", "outcome"),
    (
        (TerminalTransitionKindV49C.TIMEOUT, TerminalOutcomeV49C.TIMEOUT),
        (TerminalTransitionKindV49C.FATAL, TerminalOutcomeV49C.FATAL),
        (
            TerminalTransitionKindV49C.STORAGE_FAILURE,
            TerminalOutcomeV49C.STORAGE_FAILURE,
        ),
    ),
)
def test_explicit_failure_outcomes_are_distinct_and_terminal(
    kind: TerminalTransitionKindV49C, outcome: TerminalOutcomeV49C
) -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    state = _advance(state, kind, cause_code=f"TEST_{kind.value}")

    assert state.terminal_outcome is outcome
    assert state.terminal_cause_code == f"TEST_{kind.value}"
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="terminal"):
        _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)


def test_tcp_eof_before_peer_close_notify_is_immediate_truncation() -> None:
    state = _advance(
        initial_terminal_state_v49c(SESSION_ID),
        TerminalTransitionKindV49C.TCP_EOF_RECEIVED,
    )

    assert state.terminal_outcome is TerminalOutcomeV49C.TRUNCATED
    assert state.terminal_cause_code == V49C_TLS_TRUNCATION_CAUSE
    assert state.tcp_eof_received
    assert not state.tls_close_notify_received
    with pytest.raises(PhysicalTransportTerminalV49CStateError):
        _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)


def test_peer_close_notify_without_websocket_close_is_immediate_truncation() -> None:
    state = _advance(
        initial_terminal_state_v49c(SESSION_ID),
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED,
    )

    assert state.terminal_outcome is TerminalOutcomeV49C.TRUNCATED
    assert state.terminal_cause_code == V49C_WEBSOCKET_TRUNCATION_CAUSE
    assert state.tls_close_notify_received
    assert not state.ws_close_received


def test_application_output_is_forbidden_after_either_websocket_close() -> None:
    initial = initial_terminal_state_v49c(SESSION_ID)
    validate_application_output_allowed_v49c(initial)
    state = _send_attempt(
        initial,
        layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=APP_OBLIGATION_ID,
        label="application-before-close",
    )
    validate_application_output_allowed_v49c(state)

    after_sent = _advance(
        state,
        TerminalTransitionKindV49C.WS_CLOSE_SENT,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="sent"):
        validate_application_output_allowed_v49c(after_sent)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="sent"):
        _advance(
            after_sent,
            TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
            obligation_id=APP_OBLIGATION_ID,
            send_attempt_id=_digest("late-application-after-sent"),
        )

    after_received = _advance(initial, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="received"):
        validate_application_output_allowed_v49c(after_received)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="received"):
        _advance(
            after_received,
            TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
            obligation_id=APP_OBLIGATION_ID,
            send_attempt_id=_digest("late-application-after-received"),
        )


def test_tls_notify_requires_both_ws_closes_and_kernel_accepted_close() -> None:
    states: list[TerminalStateV49C] = [initial_terminal_state_v49c(SESSION_ID)]
    states.append(
        _advance(
            states[-1],
            TerminalTransitionKindV49C.WS_CLOSE_SENT,
            obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
            obligation_id=WS_OBLIGATION_ID,
        )
    )
    states.append(_advance(states[-1], TerminalTransitionKindV49C.WS_CLOSE_RECEIVED))
    states.append(
        _send_attempt(
            states[-1],
            layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
            obligation_id=WS_OBLIGATION_ID,
            label="ws-prerequisite",
        )
    )

    for state in states:
        with pytest.raises(PhysicalTransportTerminalV49CStateError, match="WebSocket"):
            _advance(
                state,
                TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
                obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                obligation_id=TLS_OBLIGATION_ID,
            )

    ready = _advance(
        states[-1],
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
    )
    sent = _advance(
        ready,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    assert sent.tls_close_notify_sent


def test_prepared_tls_notify_supports_causal_send_before_sent_marker() -> None:
    ready = _state_with_complete_ws_close()
    prepared = _advance(
        ready,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    assert prepared.tls_close_notify_obligation_id == TLS_OBLIGATION_ID
    assert not prepared.tls_close_notify_sent

    resolved = _send_attempt(
        prepared,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
        label="prepared-tls",
    )
    assert resolved.tls_send_attempts_resolved == 1
    sent = _advance(
        resolved,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    accepted = _advance(
        sent,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    assert accepted.tls_close_notify_sent
    assert accepted.tls_close_notify_fully_kernel_accepted

    with pytest.raises(
        PhysicalTransportTerminalV49CStateError, match="already prepared"
    ):
        _advance(
            prepared,
            TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
            obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            obligation_id=_digest("duplicate-tls-obligation"),
        )


def test_fin_requires_tls_ciphertext_fully_kernel_accepted() -> None:
    state = _state_with_complete_ws_close()
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="accepted"):
        _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)

    state = _advance(
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    state = _send_attempt(
        state,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
        label="tls-before-acceptance",
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="accepted"):
        _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)

    state = _advance(
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=TLS_OBLIGATION_ID,
    )
    state = _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)
    assert state.tcp_fin_sent


def test_full_acceptance_requires_matching_resolved_send_evidence() -> None:
    state = _advance(
        initial_terminal_state_v49c(SESSION_ID),
        TerminalTransitionKindV49C.WS_CLOSE_SENT,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="resolved"):
        _advance(
            state,
            TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
            obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
            obligation_id=WS_OBLIGATION_ID,
        )

    state = _send_attempt(
        state,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=WS_OBLIGATION_ID,
        label="ws-matching",
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="matching"):
        _advance(
            state,
            TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
            obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
            obligation_id=_digest("wrong-ws-obligation"),
        )


def test_pending_send_only_accepts_exact_outcome_and_recovers_unknown() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    attempt_id = _digest("unresolved-application-send")
    state = _advance(
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=APP_OBLIGATION_ID,
        send_attempt_id=attempt_id,
    )
    assert state.has_pending_send_attempt
    assert not state.send_retry_allowed

    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="permits only"):
        _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="match"):
        _advance(
            state,
            TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
            obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
            obligation_id=APP_OBLIGATION_ID,
            send_attempt_id=_digest("different-attempt"),
        )

    transition, terminal = terminalize_pending_send_v49c(state)
    assert transition.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
    assert transition.send_attempt_id == attempt_id
    assert transition.cause_code == V49C_RECOVERY_UNKNOWN_SEND_CAUSE
    assert terminal.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND
    assert terminal.pending_send_attempt_id == attempt_id
    assert not terminal.send_retry_allowed
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="terminal"):
        terminalize_pending_send_v49c(terminal)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="terminal"):
        _advance(
            terminal,
            TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
            obligation_id=APP_OBLIGATION_ID,
            send_attempt_id=_digest("forbidden-retry"),
        )


@pytest.mark.parametrize(
    "kind",
    (
        TerminalTransitionKindV49C.TIMEOUT,
        TerminalTransitionKindV49C.FATAL,
        TerminalTransitionKindV49C.STORAGE_FAILURE,
    ),
)
def test_unresolved_send_dominates_other_failure_classifications(
    kind: TerminalTransitionKindV49C,
) -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    state = _advance(
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=APP_OBLIGATION_ID,
        send_attempt_id=_digest(f"pending-before-{kind.value}"),
    )

    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="permits only"):
        _advance(state, kind, cause_code=f"ALSO_{kind.value}")
    _, state = terminalize_pending_send_v49c(
        state, cause_code=f"{kind.value}_LEFT_SEND_OUTCOME_UNKNOWN"
    )
    assert state.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND


def test_unknown_send_cannot_be_declared_without_pending_attempt() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    transition = _transition(
        state,
        TerminalTransitionKindV49C.UNKNOWN_SEND,
        obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=APP_OBLIGATION_ID,
        send_attempt_id=_digest("not-started"),
        cause_code="NO_OUTCOME",
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="unresolved"):
        advance_terminal_state_v49c(state, transition)


@pytest.mark.parametrize(
    "override",
    (
        {"transition_sequence": 2},
        {"parent_terminal_state_id": _digest("wrong-parent")},
        {"transport_session_id": _digest("wrong-session")},
    ),
)
def test_append_only_sequence_parent_and_session_are_strict(
    override: dict[str, object],
) -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    transition = _transition(
        state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED, **override
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError):
        advance_terminal_state_v49c(state, transition)


def test_duplicate_layer_observations_and_terminal_successors_are_rejected() -> None:
    state = _advance(
        initial_terminal_state_v49c(SESSION_ID),
        TerminalTransitionKindV49C.WS_CLOSE_RECEIVED,
    )
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="already"):
        _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)

    state = _send_ws_close(state)
    state = _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)
    with pytest.raises(PhysicalTransportTerminalV49CStateError, match="already"):
        _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)


def test_clean_transition_rejects_every_incomplete_prefix() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    prefixes = [state]
    state = _send_ws_close(state)
    prefixes.append(state)
    state = _advance(state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    prefixes.append(state)
    state = _send_tls_notify(state)
    prefixes.append(state)
    state = _advance(state, TerminalTransitionKindV49C.TCP_FIN_SENT)
    prefixes.append(state)
    state = _advance(state, TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)
    prefixes.append(state)

    for prefix in prefixes:
        with pytest.raises(PhysicalTransportTerminalV49CStateError, match="requires"):
            _advance(prefix, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)

    state = _advance(state, TerminalTransitionKindV49C.TCP_EOF_RECEIVED)
    validate_terminal_transition_v49c(
        state, _transition(state, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)
    )


def test_transition_and_state_payloads_round_trip_and_reject_tampering() -> None:
    initial = initial_terminal_state_v49c(SESSION_ID)
    transition = _transition(
        initial,
        TerminalTransitionKindV49C.TIMEOUT,
        cause_code="CLOSE_DEADLINE_EXPIRED",
    )
    terminal = advance_terminal_state_v49c(initial, transition)

    assert (
        TerminalTransitionPayloadV49C.from_mapping(transition.as_dict()) == transition
    )
    assert TerminalStateV49C.from_mapping(initial.as_dict()) == initial
    assert TerminalStateV49C.from_mapping(terminal.as_dict()) == terminal

    tampered = transition.as_dict()
    tampered["cause_code"] = "DIFFERENT_CAUSE"
    with pytest.raises(CanonicalizationError, match="does not match"):
        TerminalTransitionPayloadV49C.from_mapping(tampered)
    extra = terminal.as_dict()
    extra["actor_event_id"] = _digest("top-level-event-not-owned-here")
    with pytest.raises(CanonicalizationError, match="keys"):
        TerminalStateV49C.from_mapping(extra)


@pytest.mark.parametrize(
    "values",
    (
        {
            "kind": TerminalTransitionKindV49C.WS_CLOSE_SENT,
            "obligation_layer": None,
            "obligation_id": WS_OBLIGATION_ID,
        },
        {
            "kind": TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            "obligation_layer": OutboundObligationLayerV49C.APPLICATION_DATA,
            "obligation_id": APP_OBLIGATION_ID,
            "send_attempt_id": None,
        },
        {
            "kind": TerminalTransitionKindV49C.TIMEOUT,
            "cause_code": None,
        },
        {
            "kind": TerminalTransitionKindV49C.TCP_FIN_SENT,
            "cause_code": "NOT_ALLOWED",
        },
        {
            "kind": (
                TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
            ),
            "obligation_layer": OutboundObligationLayerV49C.APPLICATION_DATA,
            "obligation_id": APP_OBLIGATION_ID,
        },
    ),
)
def test_transition_payload_shape_is_closed(values: dict[str, object]) -> None:
    initial = initial_terminal_state_v49c(SESSION_ID)
    payload: dict[str, object] = {
        "transport_session_id": SESSION_ID,
        "transition_sequence": 1,
        "parent_terminal_state_id": initial.terminal_state_id,
    }
    payload.update(values)
    with pytest.raises(CanonicalizationError):
        TerminalTransitionPayloadV49C(**payload)


def test_state_constructor_rejects_noncanonical_or_impossible_snapshots() -> None:
    state = initial_terminal_state_v49c(SESSION_ID)
    with pytest.raises(CanonicalizationError, match="boolean"):
        replace(state, ws_close_sent=1)
    with pytest.raises(CanonicalizationError, match="empty state|obligation"):
        replace(state, ws_close_sent=True)
    with pytest.raises(
        CanonicalizationError, match="empty state|all present or absent"
    ):
        replace(state, pending_send_attempt_id=_digest("incomplete-pending"))
    with pytest.raises(CanonicalizationError, match="empty state|UNKNOWN_SEND"):
        replace(
            state,
            terminal_outcome=TerminalOutcomeV49C.UNKNOWN_SEND,
            terminal_cause_code="NO_OUTCOME",
        )


def test_reducer_replays_exact_order_and_rejects_reordering() -> None:
    initial = initial_terminal_state_v49c(SESSION_ID)
    state = initial
    transitions: list[TerminalTransitionPayloadV49C] = []
    for kind in (
        TerminalTransitionKindV49C.WS_CLOSE_RECEIVED,
        TerminalTransitionKindV49C.TIMEOUT,
    ):
        transition = _transition(
            state,
            kind,
            **(
                {"cause_code": "PEER_CLOSE_TIMEOUT"}
                if kind is TerminalTransitionKindV49C.TIMEOUT
                else {}
            ),
        )
        transitions.append(transition)
        state = advance_terminal_state_v49c(state, transition)

    assert reduce_terminal_transitions_v49c(initial, transitions) == state
    with pytest.raises(PhysicalTransportTerminalV49CStateError):
        reduce_terminal_transitions_v49c(initial, tuple(reversed(transitions)))

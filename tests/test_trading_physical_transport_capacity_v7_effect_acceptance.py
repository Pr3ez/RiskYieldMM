from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_actor_journal_v49c import (
    PhysicalTransportActorProjectionJournalV49C,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    KernelSendFailurePayloadV49E,
    KernelSendResultPayloadV49C,
    OutboundDispatchCompletedPayloadV49C,
    OutboundWirePreparedPayloadV49C,
    ParserTransitionPayloadV49C,
    TlsCiphertextPreparedPayloadV49C,
    TransportActorEventKindV49C,
    WebSocketOpcodeV49C,
    _decode_single_automatic_protocol_output_v49c,
)
from riskyieldmm.trading.physical_transport_capacity_lifecycle_v49f import (
    CapacityMeasurementLifecycleCancellationV49F,
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
    CapacityMeasurementLifecycleTerminalTriggerV49F,
    CapacityMeasurementOperationPrefixV49F,
)
from riskyieldmm.trading.physical_transport_capacity_manifest_authority_v49f import (
    collect_capacity_measurement_campaign_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_measurement_v49f import (
    CapacityMeasurementCommittedLifecycleRecordV49FV7,
    CapacityMeasurementSampleV49FV7,
    derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7,
)
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportAdmissionLifecycleV49F,
    TransportAdmissionStateErrorV49F,
    TransportCommandKindV49F,
)
from riskyieldmm.trading.physical_transport_linux_v4 import LinuxSocketOwnerV4
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    CapacityMeasurementIngressAuthorizationV49FError,
    PhysicalTransportAutomaticCloseTerminalFailureV49E,
    PhysicalTransportDispatchUnknownV4,
    PhysicalTransportIngressProgressV49D,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
)
from tests.test_trading_physical_transport_capacity_manifest_collector_v49f import (
    _design,
    _trial,
    _workload,
)
from tests.test_trading_physical_transport_capacity_measurement_v7_v49f import (
    _cancelled_sample,
    _projection_commit,
    _unavailable_observation,
    _v7_manifest_and_expectation,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy
from tests.test_trading_physical_transport_runtime_v49f_lifecycle import (
    _declaration,
    _issue_authorization,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only Raw-V7 effect acceptance tests"
)


def _operation_prefix(harness: Any, *, operation_sequence: int = 1) -> Any:
    declaration_campaign_id = "1" * 64
    attempt = (
        harness.store.load_capacity_measurement_operation_attempt_by_sequence_v49f(
            declaration_campaign_id,
            operation_sequence,
        )
    )
    return harness.store.load_capacity_measurement_operation_prefix_v49f(
        str(attempt.attempt_id)
    )


def _event_kinds(prefix: Any) -> tuple[TransportActorEventKindV49C, ...]:
    return tuple(event.event_kind for event in prefix.actor_events)


def _derive_nonreturn_prefix_aliases_for_test(
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> tuple[
    CapacityMeasurementLifecycleEffectCertaintyV49F,
    CapacityMeasurementLifecycleProgressAvailabilityV49F,
]:
    """Independently classify a closed non-return prefix from durable facts."""

    terminal = prefix.terminal
    assert terminal is not None
    assert terminal.terminal_trigger is not (
        CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
    )
    attempt_ids = {
        event.transport_actor_event_id
        for event in prefix.actor_events
        if event.event_kind
        in {
            TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
            TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT,
        }
    }
    resolved_ids = {
        attempt_id
        for event in prefix.actor_events
        for attempt_id in (
            getattr(event.payload, "kernel_send_attempt_event_id", None),
            getattr(
                event.payload,
                "tls_control_kernel_send_attempt_event_id",
                None,
            ),
        )
        if attempt_id is not None
    }
    if attempt_ids - resolved_ids:
        effect = CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
    elif not prefix.new_raw_ingress_commits and not prefix.actor_events:
        effect = CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
    else:
        effect = CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
    return (
        effect,
        CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_DURABLE_PREFIX,
    )


def _terminal_receipt_replacement(
    prefix: CapacityMeasurementOperationPrefixV49F,
    *,
    terminal: Any,
) -> CapacityMeasurementOperationPrefixV49F:
    """Recompute the complete unsigned terminal suffix for an alias attack."""

    previous = prefix.projection_receipts[-2]
    terminal_receipt, terminal_record = _projection_commit(
        terminal,
        record_kind="CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7",
        identity_id=terminal.terminal_id,
        ledger_id=prefix.attempt.projection_ledger_id,
        global_sequence=prefix.projection_receipts[-1].global_sequence,
        previous_receipt_hash=previous.receipt_hash,
    )
    return CapacityMeasurementOperationPrefixV49F(
        attempt=prefix.attempt,
        terminal=terminal,
        new_raw_ingress_commits=prefix.new_raw_ingress_commits,
        raw_dependencies=prefix.raw_dependencies,
        actor_events=prefix.actor_events,
        projection_receipts=(*prefix.projection_receipts[:-1], terminal_receipt),
        projection_records=(*prefix.projection_records[:-1], terminal_record),
        recovered_prefix_id=prefix.recovered_prefix_id,
    )


def _sample_from_nonreturn_prefix(
    prefix: CapacityMeasurementOperationPrefixV49F,
) -> CapacityMeasurementSampleV49FV7:
    terminal = prefix.terminal
    assert terminal is not None
    return CapacityMeasurementSampleV49FV7(
        committed_attempt=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=prefix.attempt,
            projection_receipt=prefix.projection_receipts[0],
        ),
        committed_terminal=CapacityMeasurementCommittedLifecycleRecordV49FV7(
            record=terminal,
            projection_receipt=prefix.projection_receipts[-1],
        ),
        recovered_prefix=prefix,
        observation=_unavailable_observation(),
    )


@pytest.mark.parametrize(
    "forgery",
    ("operation_sequence", "previous_terminal", "grant_coordinates", "policy"),
)
def test_forged_sequence_grant_or_policy_is_denied_before_target_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    forgery: str,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        policy_restore: tuple[Any, int] | None = None
        try:
            await _establish_and_activate(harness)
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            target_effect_count = 0

            async def forbidden_effect(*args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                nonlocal target_effect_count
                target_effect_count += 1
                raise AssertionError("forged authority reached target ingress")

            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                forbidden_effect,
            )
            if forgery == "operation_sequence":
                object.__setattr__(declaration, "operation_sequence", 2)
            elif forgery == "previous_terminal":
                object.__setattr__(
                    authorization,
                    "_previous_operation_terminal_id",
                    "f" * 64,
                )
            else:
                original_attempt = PhysicalTransportRuntimeV4._capacity_measurement_operation_attempt_v49f

                def forge_after_grant(
                    runtime: PhysicalTransportRuntimeV4,
                    **kwargs: Any,
                ) -> Any:
                    nonlocal policy_restore
                    if forgery == "grant_coordinates":
                        grant = kwargs["admission_grant"]
                        object.__setattr__(
                            grant,
                            "admission_sequence",
                            grant.admission_sequence + 1,
                        )
                    else:
                        gate = runtime._transport_admission_gate_v49f  # noqa: SLF001
                        assert gate is not None
                        old_value = gate.policy.ingress_reservation_work_units
                        policy_restore = (gate.policy, old_value)
                        object.__setattr__(
                            gate.policy,
                            "ingress_reservation_work_units",
                            old_value + 1,
                        )
                    return original_attempt(runtime, **kwargs)

                monkeypatch.setattr(
                    PhysicalTransportRuntimeV4,
                    "_capacity_measurement_operation_attempt_v49f",
                    forge_after_grant,
                )

            expected_error: tuple[type[BaseException], str] = {
                "operation_sequence": (
                    CanonicalizationError,
                    "only the first campaign operation",
                ),
                "previous_terminal": (
                    CanonicalizationError,
                    "only the first campaign operation",
                ),
                "grant_coordinates": (
                    TransportAdmissionStateErrorV49F,
                    "grant is not active",
                ),
                "policy": (
                    TransportAdmissionStateErrorV49F,
                    "grant is not active",
                ),
            }[forgery]
            with pytest.raises(expected_error[0], match=expected_error[1]) as caught:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            assert not isinstance(caught.value, AssertionError)
            assert target_effect_count == 0
            assert not (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            )
            attempt_count = harness.store._connection.execute(  # noqa: SLF001
                "SELECT count(*) FROM capacity_measurement_operation_attempts_v49f"
            ).fetchone()[0]
            assert attempt_count == 0
        finally:
            if policy_restore is not None:
                policy, old_value = policy_restore
                object.__setattr__(
                    policy,
                    "ingress_reservation_work_units",
                    old_value,
                )
            await harness.close()

    asyncio.run(scenario())


def test_ping_success_reconstructs_every_wire_grant_and_retained_byte_field(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        payload = b"v7-independent-ping-replay"
        ingress = Frame(Opcode.PING, payload).serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            declaration = _declaration((ingress,))
            # The declaration intentionally predicts no output.  Physical evidence
            # must still close and retain the observed Pong as correctness evidence.
            assert declaration.expected_output_frame_count == 0
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            closure = await harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                campaign=campaign,
                declaration=declaration,
                authorization=authorization,
            )
            prefix = closure.terminalized_prefix
            replay = derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7(
                prefix
            )
            terminal = prefix.terminal
            assert terminal is not None
            assert replay == closure.returned_progress_evidence
            assert prefix.new_raw_ingress_commits[0].raw_bytes == ingress
            assert replay.committed_raw_octets == len(ingress)
            assert replay.retained_incomplete_octets == 0
            assert replay.websocket_parser_state == "OPEN"
            assert len(replay.parser_event_ids) == 1
            assert len(replay.automatic_output_source_parser_event_ids) == 1
            assert len(replay.automatic_dispatch_completion_event_ids) == 1
            assert replay.logical_output_frames[0] == ("PONG", payload)
            assert replay.admission_policy_id == prefix.attempt.admission_policy_id
            assert replay.admission_epoch == prefix.attempt.admission_epoch
            assert replay.admission_sequence == prefix.attempt.admission_sequence
            assert replay.admission_queue_wait_nanoseconds == (
                prefix.attempt.admission_queue_wait_nanoseconds
            )
            assert replay.actor_event_count_before == (
                prefix.attempt.baseline_actor_event_count
            )
            assert replay.actor_event_count_after == (
                terminal.terminal_actor_event_count
            )
            assert replay.actor_tail_event_id_after == (
                terminal.terminal_actor_tail_event_id
            )
            assert terminal.runtime_state_after == harness.runtime.state.value
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE
            )
            assert declaration.expected_output_frame_count != len(
                replay.logical_output_frames
            )
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_exception_before_raw_derives_exact_empty_prefix_from_durable_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        primary = RuntimeError("exception before Raw ingress")
        try:
            await _establish_and_activate(harness)

            async def fail_before_raw(*args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                raise primary

            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                fail_before_raw,
            )
            declaration = _declaration((b"x",))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(
                PhysicalTransportRuntimeV4FaultLatched,
                match="before any durable kernel attempt",
            ) as caught:
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            assert caught.value.__cause__ is primary
            prefix = _operation_prefix(harness)
            terminal = prefix.terminal
            assert terminal is not None
            assert prefix.new_raw_ingress_commits == ()
            assert prefix.raw_dependencies == ()
            assert prefix.actor_events == ()
            assert terminal.terminal_raw_ingress_sequence == (
                prefix.attempt.baseline_raw_ingress_sequence
            )
            assert terminal.terminal_actor_event_count == (
                prefix.attempt.baseline_actor_event_count
            )
            assert terminal.effect_certainty is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
            )
            assert terminal.progress_availability is (
                CapacityMeasurementLifecycleProgressAvailabilityV49F.EXACT_DURABLE_PREFIX
            )
            assert terminal.runtime_state_after == (
                PhysicalTransportRuntimeStateV4.FAULT_LATCHED.value
            )
            assert terminal.exception_class_chain[-1] == ("builtins.RuntimeError")
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("mode", "expected_completed"),
    (
        ("zero", 0),
        ("prepared_only", 0),
        ("one", 1),
        ("one_then_failure", 1),
        ("multiple", 2),
    ),
)
def test_completed_logical_output_count_uses_only_durable_dispatch_completions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_completed: int,
) -> None:
    async def scenario() -> None:
        first_payload = b"first"
        first_ping = Frame(Opcode.PING, first_payload).serialize(mask=False)
        second_ping = Frame(Opcode.PING, b"second").serialize(mask=False)
        ingress = {
            "zero": Frame(Opcode.PONG, b"").serialize(mask=False),
            "prepared_only": first_ping,
            "one": first_ping,
            "one_then_failure": first_ping + second_ping,
            "multiple": first_ping + second_ping,
        }[mode]
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            failure_expected = mode in {"prepared_only", "one_then_failure"}
            if mode == "prepared_only":

                async def fail_after_prepared(
                    self: PhysicalTransportSessionActorV49C,
                    **kwargs: Any,
                ) -> Any:
                    del self, kwargs
                    raise RuntimeError("prepared output is not completed output")

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "send_oldest_ciphertext",
                    fail_after_prepared,
                )
            elif mode == "one_then_failure":
                original_parse = harness.owner.parse_next_durable_unit_v49d
                calls = 0

                async def fail_second_parser() -> Any:
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise RuntimeError("second parser unit failed")
                    return await original_parse()

                monkeypatch.setattr(
                    harness.owner,
                    "parse_next_durable_unit_v49d",
                    fail_second_parser,
                )
            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            if failure_expected:
                with pytest.raises(
                    PhysicalTransportRuntimeV4FaultLatched,
                    match="before any durable kernel attempt",
                ):
                    await harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                prefix = _operation_prefix(harness)
            else:
                closure = await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
                prefix = closure.terminalized_prefix
                replay = (
                    derive_capacity_measurement_ingress_progress_from_prefix_v49f_v7(
                        prefix
                    )
                )
                assert len(replay.logical_output_frames) == expected_completed
            kinds = _event_kinds(prefix)
            assert (
                kinds.count(TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED)
                == expected_completed
            )
            if mode == "prepared_only":
                assert TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED in kinds
                assert TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED in kinds
            if mode == "one_then_failure":
                assert kinds.count(TransportActorEventKindV49C.PARSER_TRANSITION) == 1
                events_by_id = {
                    event.transport_actor_event_id: event
                    for event in prefix.actor_events
                }
                completion_events = tuple(
                    event
                    for event in prefix.actor_events
                    if event.event_kind
                    is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                )
                assert len(completion_events) == 1
                completion = completion_events[0].payload
                assert type(completion) is OutboundDispatchCompletedPayloadV49C
                wire_event = events_by_id[completion.outbound_wire_prepared_event_id]
                assert wire_event.event_kind is (
                    TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
                )
                wire = wire_event.payload
                assert type(wire) is OutboundWirePreparedPayloadV49C
                assert wire.source_parser_event_id is not None
                parser_event = events_by_id[wire.source_parser_event_id]
                assert parser_event.event_kind is (
                    TransportActorEventKindV49C.PARSER_TRANSITION
                )
                parser = parser_event.payload
                assert type(parser) is ParserTransitionPayloadV49C
                output_chunks = tuple(
                    base64.b64decode(value, validate=True)
                    for value in parser.ordered_protocol_output_chunks_base64
                )
                output_opcode, output_payload = (
                    _decode_single_automatic_protocol_output_v49c(output_chunks)
                )
                first_payload_sha256 = hashlib.sha256(first_payload).hexdigest()
                assert output_opcode is WebSocketOpcodeV49C.PONG
                assert output_payload == first_payload
                assert parser.frame is not None
                assert parser.frame.opcode is WebSocketOpcodeV49C.PING
                assert (
                    parser.frame.frame_sha256 == hashlib.sha256(first_ping).hexdigest()
                )
                assert parser.frame.payload_octets == len(first_payload)
                assert parser.frame.payload_sha256 == first_payload_sha256
                assert parser.ordered_protocol_output_chunks_sha256 == tuple(
                    hashlib.sha256(chunk).hexdigest() for chunk in output_chunks
                )
                assert wire.logical_opcode is WebSocketOpcodeV49C.PONG
                assert wire.logical_payload_octets == len(first_payload)
                assert wire.logical_payload_sha256 == first_payload_sha256
                assert wire.ordered_wire_chunks_sha256 == (
                    parser.ordered_protocol_output_chunks_sha256
                )
                assert wire.wire_batch_sha256 == (parser.protocol_output_batch_sha256)
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "send_state",
    (
        "unresolved_attempt",
        "conclusive_zero",
        "partial_positive",
        "full_without_dispatch",
        "dispatch_complete",
    ),
)
def test_five_send_lifecycle_states_remain_distinct_in_raw_v7_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    send_state: str,
) -> None:
    async def scenario() -> None:
        opcode = Opcode.CLOSE if send_state == "conclusive_zero" else Opcode.PING
        payload = b"" if opcode is Opcode.CLOSE else b"send-lifecycle"
        ingress = Frame(opcode, payload).serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            if send_state == "unresolved_attempt":

                async def fail_send(*args: Any, **kwargs: Any) -> Any:
                    del args, kwargs
                    raise RuntimeError("kernel result unavailable")

                async def fail_unknown_append(*args: Any, **kwargs: Any) -> Any:
                    del args, kwargs
                    raise RuntimeError("failure before UNKNOWN append")

                monkeypatch.setattr(
                    harness.owner,
                    "send_prepared_tls_ciphertext_once_v49c",
                    fail_send,
                )
                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "_append_unknown_send_locked",
                    fail_unknown_append,
                )
            elif send_state == "conclusive_zero":
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                original_clock = actor._observation_clock  # noqa: SLF001
                forced_ns = None

                def expire_after_write_ahead() -> Any:
                    nonlocal forced_ns
                    kinds = tuple(event.event_kind for event in actor.events)
                    unresolved = (
                        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT in kinds
                        and TransportActorEventKindV49C.KERNEL_SEND_RESULT not in kinds
                        and TransportActorEventKindV49C.KERNEL_SEND_FAILURE not in kinds
                    )
                    if unresolved or forced_ns is not None:
                        wire = next(
                            event.payload
                            for event in reversed(actor.events)
                            if type(event.payload) is OutboundWirePreparedPayloadV49C
                        )
                        prior = actor.events[-1]
                        # Keep the real wall clock inside projection receipt
                        # chronology while forcing the monotonic deadline due.
                        # This exercises the actor's conclusive, zero-kernel-
                        # acceptance CLOCK_DISAGREEMENT branch without forging
                        # a future wall-clock event.
                        observed_wall, _ = original_clock()
                        forced_ns = max(
                            wire.send_not_after_monotonic_ns,
                            prior.recorded_monotonic_ns + 1,
                            0 if forced_ns is None else forced_ns + 1,
                        )
                        return max(observed_wall, prior.recorded_at), forced_ns
                    return original_clock()

                monkeypatch.setattr(
                    actor, "_observation_clock", expire_after_write_ahead
                )
                monkeypatch.setattr(
                    actor,
                    "_observation_batch_clock",
                    lambda count: tuple(
                        expire_after_write_ahead() for _ in range(count)
                    ),
                )
            elif send_state == "partial_positive":
                original_send = PhysicalTransportSessionActorV49C.send_oldest_ciphertext

                async def stop_after_positive_partial(
                    actor: PhysicalTransportSessionActorV49C,
                    **kwargs: Any,
                ) -> Any:
                    outcome = await original_send(
                        actor,
                        requested_octets=1,
                        **kwargs,
                    )
                    assert outcome.accepted_octets == 1
                    raise RuntimeError("stop after positive partial result")

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "send_oldest_ciphertext",
                    stop_after_positive_partial,
                )
            elif send_state == "full_without_dispatch":

                async def fail_completion(*args: Any, **kwargs: Any) -> Any:
                    del args, kwargs
                    raise RuntimeError("full result persisted before dispatch")

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "complete_oldest_dispatch_from_chain",
                    fail_completion,
                )

            declaration = _declaration((ingress,))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            if send_state == "dispatch_complete":
                closure = await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
                prefix = closure.terminalized_prefix
            else:
                expected_error: tuple[type[BaseException], str] = {
                    "unresolved_attempt": (
                        PhysicalTransportDispatchUnknownV4,
                        "unresolved durable kernel attempt",
                    ),
                    "conclusive_zero": (
                        PhysicalTransportAutomaticCloseTerminalFailureV49E,
                        "ended conclusively",
                    ),
                    "partial_positive": (
                        PhysicalTransportRuntimeV4FaultLatched,
                        "after a conclusive kernel send result",
                    ),
                    "full_without_dispatch": (
                        PhysicalTransportRuntimeV4FaultLatched,
                        "after a conclusive kernel send result",
                    ),
                }[send_state]
                with pytest.raises(
                    expected_error[0], match=expected_error[1]
                ) as caught_error:
                    await harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                prefix = _operation_prefix(harness)
            terminal = prefix.terminal
            assert terminal is not None, (
                None
                if send_state == "dispatch_complete"
                else caught_error.value.__cause__,
                None
                if send_state == "dispatch_complete"
                else getattr(caught_error.value, "__notes__", ()),
            )
            attempts = tuple(
                event
                for event in prefix.actor_events
                if event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
            )
            results = tuple(
                event.payload
                for event in prefix.actor_events
                if type(event.payload) is KernelSendResultPayloadV49C
            )
            failures = tuple(
                event.payload
                for event in prefix.actor_events
                if type(event.payload) is KernelSendFailurePayloadV49E
            )
            completions = tuple(
                event.payload
                for event in prefix.actor_events
                if type(event.payload) is OutboundDispatchCompletedPayloadV49C
            )
            tls = next(
                event.payload
                for event in prefix.actor_events
                if type(event.payload) is TlsCiphertextPreparedPayloadV49C
            )
            assert len(attempts) == 1
            if send_state == "unresolved_attempt":
                assert not results and not failures and not completions
                assert terminal.effect_certainty is (
                    CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
                )
                relabelled = replace(
                    terminal,
                    effect_certainty=(
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                    terminal_id=None,
                )
                forged_prefix = _terminal_receipt_replacement(
                    prefix,
                    terminal=relabelled,
                )
                with pytest.raises(CanonicalizationError, match="derived"):
                    _sample_from_nonreturn_prefix(forged_prefix)
            elif send_state == "conclusive_zero":
                assert not results and len(failures) == 1 and not completions
                assert terminal.effect_certainty is (
                    CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                )
            elif send_state == "partial_positive":
                assert len(results) == 1 and not failures and not completions
                assert results[0].accepted_octets == 1
                assert results[0].resulting_ciphertext_offset < tls.ciphertext_octets
            elif send_state == "full_without_dispatch":
                assert results and not failures and not completions
                assert sum(item.accepted_octets for item in results) == (
                    tls.ciphertext_octets
                )
            else:
                assert results and not failures and len(completions) == 1
                assert sum(item.accepted_octets for item in results) == (
                    tls.ciphertext_octets
                )
                assert terminal.effect_certainty is (
                    CapacityMeasurementLifecycleEffectCertaintyV49F.COMPLETE
                )
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "alias",
    ("effect_nonempty", "progress_availability"),
)
def test_recomputed_unsigned_terminal_aliases_are_rejected_by_prefix_replay(
    alias: str,
) -> None:
    manifest, _ = _v7_manifest_and_expectation()
    sample = _cancelled_sample(manifest)
    terminal = sample.terminal
    changes: dict[str, Any]
    if alias == "effect_nonempty":
        changes = {
            "effect_certainty": (
                CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
            ),
        }
    else:
        changes = {
            "progress_availability": (
                CapacityMeasurementLifecycleProgressAvailabilityV49F.UNAVAILABLE
            ),
            "progress_unavailable_reason": "CALLER_SELECTED_ALIAS",
        }
    forged_terminal = replace(terminal, **changes, terminal_id=None)
    forged_prefix = _terminal_receipt_replacement(
        sample.recovered_prefix,
        terminal=forged_terminal,
    )
    with pytest.raises(CanonicalizationError, match="derived"):
        _sample_from_nonreturn_prefix(forged_prefix)


def test_postmortem_load_is_read_only_and_mints_no_effect_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)

            async def fail_read(*args: Any, **kwargs: Any) -> Any:
                del args, kwargs
                raise RuntimeError("abort owner before postmortem read")

            monkeypatch.setattr(
                LinuxSocketOwnerV4,
                "read_decrypted_ingress_v49d",
                fail_read,
            )
            declaration = _declaration((b"x",))
            campaign = object()
            authorization, _, _ = _issue_authorization(
                harness.runtime,
                campaign=campaign,
                declaration=declaration,
            )
            with pytest.raises(
                PhysicalTransportRuntimeV4FaultLatched,
                match="before any durable kernel attempt",
            ):
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )
            prefix = _operation_prefix(harness)
            terminal = prefix.terminal
            assert terminal is not None
            journal = harness.runtime._transport_actor_journal_v49c  # noqa: SLF001
            assert type(journal) is PhysicalTransportActorProjectionJournalV49C
            before_report = harness.store.verify()
            before_changes = harness.store._connection.total_changes  # noqa: SLF001
            before_capabilities = dict(
                harness.store._active_capacity_lifecycle_attempt_capabilities_v49f  # noqa: SLF001
            )
            first = journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                attempt_id=str(prefix.attempt.attempt_id)
            )
            second = journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
                attempt_id=str(prefix.attempt.attempt_id)
            )
            after_capabilities = dict(
                harness.store._active_capacity_lifecycle_attempt_capabilities_v49f  # noqa: SLF001
            )
            assert first == second == prefix
            assert harness.store._connection.total_changes == before_changes  # noqa: SLF001
            assert harness.store.verify() == before_report
            assert before_capabilities == after_capabilities == {}
            assert harness.owner._closed is True  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "barrier",
    (
        "before_admission",
        "grant_to_orchestration",
        "after_attempt",
        "after_raw",
        "after_parser",
        "after_prepared",
        "after_kernel_attempt",
        "after_kernel_result",
        "after_dispatch",
    ),
)
def test_cancellation_at_every_reachable_v7_barrier_preserves_exact_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    barrier: str,
) -> None:
    async def scenario() -> None:
        ingress = Frame(
            Opcode.PING
            if barrier
            not in {
                "before_admission",
                "grant_to_orchestration",
                "after_attempt",
                "after_raw",
            }
            else Opcode.PONG,
            b"cancel-barrier"
            if barrier
            not in {
                "before_admission",
                "grant_to_orchestration",
                "after_attempt",
                "after_raw",
            }
            else b"",
        ).serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress if barrier != "after_attempt" else b"",
            transport_capacity_policy_v49f=_policy(),
        )
        reached = asyncio.Event()
        observed: list[asyncio.CancelledError] = []
        lock_held = False
        try:
            await _establish_and_activate(harness)
            gate = harness.runtime._transport_admission_gate_v49f  # noqa: SLF001
            assert gate is not None
            before = gate.snapshot()

            async def wait_barrier() -> None:
                reached.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError as exc:
                    observed.append(exc)
                    raise

            if barrier == "before_admission":
                original_acquire = type(gate)._acquire

                async def block_before_admission(self: Any, *args: Any, **kwargs: Any):
                    await wait_barrier()
                    return await original_acquire(self, *args, **kwargs)

                monkeypatch.setattr(type(gate), "_acquire", block_before_admission)
            elif barrier == "grant_to_orchestration":
                await harness.runtime._transport_orchestration_lock_v49c.acquire()  # noqa: SLF001
                lock_held = True
            elif barrier == "after_attempt":
                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "read_decrypted_ingress_v49d",
                    lambda *args, **kwargs: wait_barrier(),
                )
            elif barrier == "after_raw":
                original_adopt = LinuxSocketOwnerV4.adopt_durable_ingress_v49d

                async def block_after_raw(self: Any, *args: Any, **kwargs: Any):
                    await wait_barrier()
                    return await original_adopt(self, *args, **kwargs)

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "adopt_durable_ingress_v49d",
                    block_after_raw,
                )
            elif barrier == "after_parser":
                original_parser = (
                    PhysicalTransportSessionActorV49C.append_parser_transition_v49d
                )

                async def block_after_parser(self: Any, *args: Any, **kwargs: Any):
                    result = await original_parser(self, *args, **kwargs)
                    await wait_barrier()
                    return result

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "append_parser_transition_v49d",
                    block_after_parser,
                )
            elif barrier == "after_prepared":
                original_send = PhysicalTransportSessionActorV49C.send_oldest_ciphertext

                async def block_after_prepared(self: Any, *args: Any, **kwargs: Any):
                    await wait_barrier()
                    return await original_send(self, *args, **kwargs)

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "send_oldest_ciphertext",
                    block_after_prepared,
                )
            elif barrier == "after_kernel_attempt":
                original_append_batch = (
                    PhysicalTransportSessionActorV49C._append_candidate_batch_locked
                )

                async def block_after_attempt(
                    self: Any,
                    events: tuple[Any, ...],
                ) -> Any:
                    result = await original_append_batch(self, events)
                    if any(
                        event.event_kind
                        is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
                        for event in events
                    ):
                        await wait_barrier()
                    return result

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "_append_candidate_batch_locked",
                    block_after_attempt,
                )
            elif barrier == "after_kernel_result":
                original_complete = PhysicalTransportSessionActorV49C.complete_oldest_dispatch_from_chain

                async def block_after_result(self: Any, *args: Any, **kwargs: Any):
                    await wait_barrier()
                    return await original_complete(self, *args, **kwargs)

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "complete_oldest_dispatch_from_chain",
                    block_after_result,
                )
            elif barrier == "after_dispatch":
                original_dispatch = PhysicalTransportRuntimeV4._dispatch_automatic_protocol_output_v49d_locked

                async def block_after_dispatch(self: Any, *args: Any, **kwargs: Any):
                    result = await original_dispatch(self, *args, **kwargs)
                    await wait_barrier()
                    return result

                monkeypatch.setattr(
                    PhysicalTransportRuntimeV4,
                    "_dispatch_automatic_protocol_output_v49d_locked",
                    block_after_dispatch,
                )

            declaration = _declaration((ingress,))
            campaign = object()

            async def measured() -> None:
                authorization, _, _ = _issue_authorization(
                    harness.runtime,
                    campaign=campaign,
                    declaration=declaration,
                )
                await (
                    harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )
                )

            task = asyncio.create_task(measured())
            if barrier == "grant_to_orchestration":
                for _ in range(2_000):
                    active = gate._active  # noqa: SLF001
                    if (
                        active is not None
                        and active.lifecycle is TransportAdmissionLifecycleV49F.ENTERED
                    ):
                        reached.set()
                        break
                    await asyncio.sleep(0)
                else:
                    raise AssertionError("grant did not reach orchestration wait")
            await asyncio.wait_for(reached.wait(), timeout=2)
            task.cancel(f"Raw-V7 cancellation at {barrier}")
            if lock_held:
                harness.runtime._transport_orchestration_lock_v49c.release()  # noqa: SLF001
                lock_held = False
            with pytest.raises(asyncio.CancelledError) as caught:
                await task
            assert task.cancelled()
            if observed:
                assert observed == [caught.value]
            after = gate.snapshot()
            attempts = (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            )
            if barrier in {"before_admission", "grant_to_orchestration"}:
                assert attempts == ()
                attempt_count = harness.store._connection.execute(  # noqa: SLF001
                    "SELECT count(*) FROM capacity_measurement_operation_attempts_v49f"
                ).fetchone()[0]
                assert attempt_count == 0
                if barrier == "before_admission":
                    assert after.cancelled_before_entry_commands == (
                        before.cancelled_before_entry_commands
                    )
                else:
                    assert after.released_commands == before.released_commands + 1
            else:
                prefix = _operation_prefix(harness)
                terminal = prefix.terminal
                assert terminal is not None
                expected_kinds = {
                    "after_attempt": (),
                    "after_raw": (TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,),
                    "after_parser": (
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                    ),
                    "after_prepared": (
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                    ),
                    "after_kernel_attempt": (
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                        TransportActorEventKindV49C.TERMINAL_TRANSITION,
                    ),
                    "after_kernel_result": (
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                        TransportActorEventKindV49C.TERMINAL_TRANSITION,
                        TransportActorEventKindV49C.KERNEL_SEND_RESULT,
                        TransportActorEventKindV49C.TERMINAL_TRANSITION,
                    ),
                    "after_dispatch": (
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                        TransportActorEventKindV49C.TERMINAL_TRANSITION,
                        TransportActorEventKindV49C.KERNEL_SEND_RESULT,
                        TransportActorEventKindV49C.TERMINAL_TRANSITION,
                        TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED,
                    ),
                }[barrier]
                assert _event_kinds(prefix) == expected_kinds
                expected_raw_count = 0 if barrier == "after_attempt" else 1
                assert len(prefix.new_raw_ingress_commits) == expected_raw_count
                assert len(prefix.raw_dependencies) == expected_raw_count
                assert {
                    raw.raw_ingress_commit_id for raw in prefix.new_raw_ingress_commits
                } == {raw.raw_ingress_commit_id for raw in prefix.raw_dependencies}
                expected_effect = {
                    "after_attempt": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.NO_DURABLE_EFFECT
                    ),
                    "after_raw": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                    "after_parser": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                    "after_prepared": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                    "after_kernel_attempt": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
                    ),
                    "after_kernel_result": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                    "after_dispatch": (
                        CapacityMeasurementLifecycleEffectCertaintyV49F.EXACT_COMPLETED_PREFIX
                    ),
                }[barrier]
                derived_effect, derived_progress = (
                    _derive_nonreturn_prefix_aliases_for_test(prefix)
                )
                assert derived_effect is expected_effect
                assert terminal.effect_certainty is derived_effect
                assert terminal.progress_availability is derived_progress
                assert terminal.progress_unavailable_reason is None
                assert terminal.terminal_trigger is (
                    CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
                )
                assert terminal.cancellation_classification is (
                    CapacityMeasurementLifecycleCancellationV49F.ASYNCIO_CANCELLED_ERROR
                )
                assert terminal.operation_error_code == "ASYNCIO_CANCELLED_ERROR"
                assert terminal.operation_error_code != "APPLICATION_TIMEOUT"
                assert after.released_commands == before.released_commands + 1
                assert not (
                    harness.store.list_open_capacity_measurement_operation_attempts_v49f()
                )
        finally:
            if lock_held:
                harness.runtime._transport_orchestration_lock_v49c.release()  # noqa: SLF001
            await harness.close()

    asyncio.run(scenario())


def test_repeated_racing_cancellation_has_one_terminal_no_uncancel_and_no_relabel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def one_run(run_index: int, base_path: Path) -> tuple[Any, ...]:
        ingress = Frame(Opcode.PING, b"repeated-cancel").serialize(mask=False)
        run_path = base_path / f"r{run_index}"
        run_path.mkdir()
        harness = await _build_harness(
            run_path,
            first_frame=ingress,
            transport_capacity_policy_v49f=_policy(),
        )
        reached = asyncio.Event()
        observed: list[asyncio.CancelledError] = []
        try:
            await _establish_and_activate(harness)
            with monkeypatch.context() as run_patch:
                original_append_batch = (
                    PhysicalTransportSessionActorV49C._append_candidate_batch_locked
                )

                async def block_at_attempt(
                    self: Any,
                    events: tuple[Any, ...],
                ) -> Any:
                    result = await original_append_batch(self, events)
                    if any(
                        event.event_kind
                        is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
                        for event in events
                    ):
                        reached.set()
                        try:
                            await asyncio.Event().wait()
                        except asyncio.CancelledError as exc:
                            observed.append(exc)
                            raise
                    return result

                run_patch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "_append_candidate_batch_locked",
                    block_at_attempt,
                )
                declaration = _declaration((ingress,))
                campaign = object()

                async def measured() -> None:
                    authorization, _, _ = _issue_authorization(
                        harness.runtime,
                        campaign=campaign,
                        declaration=declaration,
                    )
                    await harness.runtime.process_next_ingress_for_capacity_measurement_v49f(
                        campaign=campaign,
                        declaration=declaration,
                        authorization=authorization,
                    )

                task = asyncio.create_task(measured())
                await asyncio.wait_for(reached.wait(), timeout=2)
                assert task.cancel("race-one")
                assert task.cancel("race-two")
                assert task.cancel("race-three")
                with pytest.raises(asyncio.CancelledError) as caught:
                    await task
                assert observed == [caught.value]
                assert task.cancelled()
                assert task.cancelling() >= 3
            prefix = _operation_prefix(harness)
            terminal = prefix.terminal
            assert terminal is not None
            expected_kinds = (
                TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                TransportActorEventKindV49C.PARSER_TRANSITION,
                TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
                TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
                TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
                TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
                TransportActorEventKindV49C.TERMINAL_TRANSITION,
            )
            assert _event_kinds(prefix) == expected_kinds
            assert len(prefix.new_raw_ingress_commits) == 1
            assert len(prefix.raw_dependencies) == 1
            derived_effect, derived_progress = (
                _derive_nonreturn_prefix_aliases_for_test(prefix)
            )
            assert derived_effect is (
                CapacityMeasurementLifecycleEffectCertaintyV49F.UNKNOWN
            )
            assert terminal.effect_certainty is derived_effect
            assert terminal.progress_availability is derived_progress
            assert terminal.terminal_trigger is (
                CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
            )
            assert terminal.cancellation_classification is (
                CapacityMeasurementLifecycleCancellationV49F.ASYNCIO_CANCELLED_ERROR
            )
            assert terminal.operation_error_code == "ASYNCIO_CANCELLED_ERROR"
            assert (
                sum(
                    receipt.record_kind
                    == "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7"
                    for receipt in prefix.projection_receipts
                )
                == 1
            )
            await asyncio.sleep(0)
            assert not harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            harness.store.verify()
            return (
                _event_kinds(prefix),
                len(prefix.new_raw_ingress_commits),
                len(prefix.raw_dependencies),
                derived_effect,
                derived_progress,
                terminal.terminal_trigger,
                terminal.cancellation_classification,
                terminal.operation_error_code,
            )
        finally:
            await harness.close()

    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v7-cancel-") as directory:
            oracle_runs: list[tuple[Any, ...]] = []
            for index in range(3):
                oracle_runs.append(await one_run(index, Path(directory)))
            oracles = tuple(oracle_runs)
            assert oracles == (oracles[0],) * 3
        source = inspect.getsource(
            PhysicalTransportRuntimeV4.process_next_ingress_for_capacity_measurement_v49f
        )
        assert ".uncancel(" not in source
        assert "shield(" not in source

    asyncio.run(scenario())


@pytest.mark.parametrize("legacy_mode", ("return", "error", "cancel"))
def test_public_legacy_ingress_preserves_exact_return_error_and_cancellation_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    legacy_mode: str,
) -> None:
    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            first_frame=ingress if legacy_mode == "return" else b"",
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            if legacy_mode == "return":
                result = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=2
                )
                assert type(result) is PhysicalTransportIngressProgressV49D
                assert result.committed_raw_octets == len(ingress)
            elif legacy_mode == "error":
                primary = RuntimeError("legacy read error")

                async def fail_read(*args: Any, **kwargs: Any) -> Any:
                    del args, kwargs
                    raise primary

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "read_decrypted_ingress_v49d",
                    fail_read,
                )
                with pytest.raises(
                    PhysicalTransportRuntimeV4FaultLatched,
                    match="before any durable kernel attempt",
                ) as caught:
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=2)
                assert caught.value.__cause__ is primary
            else:
                reached = asyncio.Event()
                observed: list[asyncio.CancelledError] = []

                async def block_read(*args: Any, **kwargs: Any) -> Any:
                    del args, kwargs
                    reached.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError as exc:
                        observed.append(exc)
                        raise

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "read_decrypted_ingress_v49d",
                    block_read,
                )
                task = asyncio.create_task(
                    harness.runtime.process_next_ingress_v49d(timeout_seconds=2)
                )
                await asyncio.wait_for(reached.wait(), timeout=2)
                task.cancel("legacy-cancel")
                with pytest.raises(asyncio.CancelledError) as caught:
                    await task
                assert observed == [caught.value]
                assert task.cancelled()
            assert not (
                harness.store.list_open_capacity_measurement_operation_attempts_v49f()
            )
            count = harness.store._connection.execute(  # noqa: SLF001
                "SELECT count(*) FROM capacity_measurement_operation_attempts_v49f"
            ).fetchone()[0]
            assert count == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_public_legacy_signature_and_live_collector_denial_are_unchanged(
    tmp_path: Path,
) -> None:
    assert tuple(
        inspect.signature(
            PhysicalTransportRuntimeV4.process_next_ingress_v49d
        ).parameters
    ) == ("self", "timeout_seconds")

    async def scenario() -> None:
        ingress = Frame(Opcode.PONG, b"").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            with pytest.raises(TypeError, match="LIVE_LINUX runtime profile"):
                await collect_capacity_measurement_campaign_v49f_v7(
                    runtime=harness.runtime,
                    repository_root=Path(__file__).resolve().parents[1],
                    campaign_label="public-live-denial",
                    workloads=(_workload(_trial(ingress)),),
                    design=_design(),
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_capacity_authorization_type_remains_measurement_only() -> None:
    assert not issubclass(
        CapacityMeasurementIngressAuthorizationV49FError,
        PhysicalTransportRuntimeV4FaultLatched,
    )
    assert TransportCommandKindV49F.INGRESS.value == "INGRESS"
    assert hashlib.sha256(b"").hexdigest() == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )

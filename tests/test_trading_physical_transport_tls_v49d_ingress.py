from __future__ import annotations

import asyncio
import hashlib
import inspect
import socket
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_tls_v49 import (
    DurableIngressAdoptionV49D,
    ExactTlsWebSocketDriverV49,
    ParsedDurableUnitV49D,
    PhysicalTlsWebSocketV49PostHandshakeOutputRequired,
    PhysicalTlsWebSocketV49StateError,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _certificates,
    _connected_socket,
    _decode_client_frame,
    _policy,
    _raw_record,
    _server_context,
    _start_fake_server,
    _trust_store,
    _write_certificates,
)


@dataclass(slots=True)
class _BoundDriverV49D:
    driver: ExactTlsWebSocketDriverV49
    socket: socket.socket
    fake: Any
    pending_raw: Any

    async def close(self) -> None:
        self.driver.abort()
        self.socket.close()
        await self.fake.close()


async def _bound_driver_v49d(
    tmp_path: Path, *, first_frame: bytes = b""
) -> _BoundDriverV49D:
    material = _certificates()
    ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
    fake = await _start_fake_server(
        _server_context(cert_path, key_path), first_frame=first_frame
    )
    driver = ExactTlsWebSocketDriverV49(
        trust_store=_trust_store(ca_path, material),
        transport_policy=_policy(),
    )
    owned_socket = await _connected_socket(fake.address)
    try:
        evidence = await driver.handshake(owned_socket)
        pending = driver.bind_handshake_evidence(evidence)
        return _BoundDriverV49D(
            driver=driver,
            socket=owned_socket,
            fake=fake,
            pending_raw=pending,
        )
    except BaseException:
        driver.abort()
        owned_socket.close()
        await fake.close()
        raise


def _driver_raw(harness: _BoundDriverV49D, pending):
    return replace(
        _raw_record(pending),
        transport_subscription_policy_id=(
            harness.driver.transport_policy.transport_subscription_policy_id
        ),
    )


def test_v49d_results_are_driver_constructed_tokens() -> None:
    with pytest.raises(TypeError, match="driver-constructed"):
        DurableIngressAdoptionV49D(_token=object())
    with pytest.raises(TypeError, match="driver-constructed"):
        ParsedDurableUnitV49D(_token=object())


def test_v49d_parses_exactly_one_oldest_frame_per_transition(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        first = Frame(Opcode.TEXT, b"first").serialize(mask=False)
        second = Frame(Opcode.BINARY, b"second").serialize(mask=False)
        harness = await _bound_driver_v49d(tmp_path, first_frame=first + second)
        try:
            pending = harness.pending_raw
            assert pending is not None
            raw = _driver_raw(harness, pending)
            adopted = harness.driver.adopt_durable_ingress_v49d(raw)
            assert adopted.raw_ingress_commit_id == raw.raw_ingress_commit_id
            assert adopted.ingress_sequence == pending.ingress_sequence
            assert adopted.adopted_octets == len(first) + len(second)
            assert adopted.durable_buffer_octets == len(first) + len(second)

            parsed_first = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_first) is ParsedDurableUnitV49D
            assert parsed_first.parser_unit_sequence == 1
            assert parsed_first.consumed_unit == first
            assert (
                parsed_first.consumed_unit_sha256 == hashlib.sha256(first).hexdigest()
            )
            assert parsed_first.consumed_octets == len(first)
            assert parsed_first.frame_event is not None
            assert parsed_first.frame_event.opcode == int(Opcode.TEXT)
            assert parsed_first.frame_event.payload == b"first"
            assert parsed_first.protocol_output_chunks == ()
            assert parsed_first.remaining_durable_octets == len(second)
            assert harness.driver.durable_ingress_buffer_octets_v49d == len(second)
            assert harness.driver.has_complete_durable_unit_v49d

            parsed_second = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_second) is ParsedDurableUnitV49D
            assert parsed_second.parser_unit_sequence == 2
            assert parsed_second.consumed_unit == second
            assert parsed_second.frame_event is not None
            assert parsed_second.frame_event.opcode == int(Opcode.BINARY)
            assert parsed_second.frame_event.payload == b"second"
            assert parsed_second.remaining_durable_octets == 0
            assert harness.driver.durable_ingress_buffer_octets_v49d == 0
            assert not harness.driver.has_complete_durable_unit_v49d
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            assert harness.fake.application_reads.empty()
            with pytest.raises(
                PhysicalTlsWebSocketV49StateError,
                match="cannot bypass active V4.9D ordering",
            ):
                await harness.driver.read_decrypted_ingress(
                    harness.socket, timeout_seconds=1
                )
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_invalid_unfragmented_text_fails_with_close_1007(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        invalid_text = Frame(Opcode.TEXT, b"invalid:\xff").serialize(mask=False)
        harness = await _bound_driver_v49d(tmp_path, first_frame=invalid_text)
        try:
            pending = harness.pending_raw
            assert pending is not None
            harness.driver.adopt_durable_ingress_v49d(_driver_raw(harness, pending))
            parsed = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed) is ParsedDurableUnitV49D
            assert parsed.consumed_unit == invalid_text
            assert parsed.frame_event is None
            assert parsed.parser_exception_class == "builtins.UnicodeDecodeError"
            assert parsed.parser_exception_message is not None
            assert len(parsed.protocol_output_chunks) == 1
            opcode, payload = _decode_client_frame(parsed.protocol_output_chunks[0])
            assert opcode == int(Opcode.CLOSE)
            assert int.from_bytes(payload[:2], "big") == 1007
            assert parsed.remaining_durable_octets == 0
            assert harness.driver._fragmented_text_decoder_v49d is None  # noqa: SLF001
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            )
            assert harness.fake.application_reads.empty()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_incrementally_validates_fragmented_text_without_reassembly(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        first = Frame(Opcode.TEXT, b"emoji:\xf0\x9f", fin=False).serialize(mask=False)
        final = Frame(Opcode.CONT, b"\x98\x80", fin=True).serialize(mask=False)
        harness = await _bound_driver_v49d(tmp_path, first_frame=first + final)
        try:
            pending = harness.pending_raw
            assert pending is not None
            harness.driver.adopt_durable_ingress_v49d(_driver_raw(harness, pending))
            parsed_first = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_first) is ParsedDurableUnitV49D
            assert parsed_first.frame_event is not None
            assert parsed_first.frame_event.opcode == int(Opcode.TEXT)
            assert parsed_first.parser_exception_class is None
            assert harness.driver._fragmented_text_decoder_v49d is not None  # noqa: SLF001

            parsed_final = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_final) is ParsedDurableUnitV49D
            assert parsed_final.frame_event is not None
            assert parsed_final.frame_event.opcode == int(Opcode.CONT)
            assert parsed_final.parser_exception_class is None
            assert parsed_final.protocol_output_chunks == ()
            assert parsed_final.remaining_durable_octets == 0
            assert harness.driver._fragmented_text_decoder_v49d is None  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_invalid_utf8_across_fragments_fails_only_the_final_unit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        first = Frame(Opcode.TEXT, b"prefix:\xf0\x9f", fin=False).serialize(mask=False)
        invalid_final = Frame(Opcode.CONT, b"\x28\x80", fin=True).serialize(mask=False)
        harness = await _bound_driver_v49d(tmp_path, first_frame=first + invalid_final)
        try:
            pending = harness.pending_raw
            assert pending is not None
            harness.driver.adopt_durable_ingress_v49d(_driver_raw(harness, pending))
            parsed_first = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_first) is ParsedDurableUnitV49D
            assert parsed_first.frame_event is not None
            assert parsed_first.parser_exception_class is None
            assert parsed_first.remaining_durable_octets == len(invalid_final)

            parsed_final = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed_final) is ParsedDurableUnitV49D
            assert parsed_final.consumed_unit == invalid_final
            assert parsed_final.frame_event is None
            assert parsed_final.parser_exception_class == (
                "builtins.UnicodeDecodeError"
            )
            assert len(parsed_final.protocol_output_chunks) == 1
            opcode, payload = _decode_client_frame(
                parsed_final.protocol_output_chunks[0]
            )
            assert opcode == int(Opcode.CLOSE)
            assert int.from_bytes(payload[:2], "big") == 1007
            assert parsed_final.remaining_durable_octets == 0
            assert harness.driver._fragmented_text_decoder_v49d is None  # noqa: SLF001
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_incomplete_frame_spans_two_durable_raw_batches(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        ping = Frame(Opcode.PING, b"cross-raw").serialize(mask=False)
        split_at = 5
        harness = await _bound_driver_v49d(tmp_path, first_frame=ping[:split_at])
        try:
            first_pending = harness.pending_raw
            assert first_pending is not None
            first_adoption = harness.driver.adopt_durable_ingress_v49d(
                _driver_raw(harness, first_pending)
            )
            assert first_adoption.durable_buffer_octets == split_at
            assert harness.driver.parse_next_durable_unit_v49d() is None
            assert harness.driver.durable_ingress_buffer_octets_v49d == split_at
            assert not harness.driver.has_complete_durable_unit_v49d

            writer = harness.fake.writers[0]
            writer.write(ping[split_at:])
            await writer.drain()
            second_pending = await harness.driver.read_decrypted_ingress_v49d(
                harness.socket, timeout_seconds=1
            )
            assert second_pending.ingress_sequence == first_pending.ingress_sequence + 1
            second_adoption = harness.driver.adopt_durable_ingress_v49d(
                _driver_raw(harness, second_pending)
            )
            assert second_adoption.durable_buffer_octets == len(ping)

            parsed = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed) is ParsedDurableUnitV49D
            assert parsed.consumed_unit == ping
            assert parsed.frame_event is not None
            assert parsed.frame_event.opcode == int(Opcode.PING)
            assert parsed.frame_event.payload == b"cross-raw"
            assert parsed.remaining_durable_octets == 0
            assert len(parsed.protocol_output_chunks) == 1
            opcode, payload = _decode_client_frame(parsed.protocol_output_chunks[0])
            assert opcode == int(Opcode.PONG)
            assert payload == b"cross-raw"
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            )
            await asyncio.sleep(0.02)
            assert harness.fake.application_reads.empty()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_structural_error_consumes_only_the_proven_prefix(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        masked_server_ping = Frame(Opcode.PING, b"bad").serialize(mask=True)
        harness = await _bound_driver_v49d(tmp_path, first_frame=masked_server_ping)
        try:
            pending = harness.pending_raw
            assert pending is not None
            harness.driver.adopt_durable_ingress_v49d(_driver_raw(harness, pending))
            parsed = harness.driver.parse_next_durable_unit_v49d()
            assert type(parsed) is ParsedDurableUnitV49D
            assert parsed.consumed_unit == masked_server_ping[:2]
            assert parsed.consumed_octets == 2
            assert parsed.frame_event is None
            assert parsed.parser_exception_class is not None
            assert parsed.remaining_durable_octets == len(masked_server_ping) - 2
            assert len(parsed.protocol_output_chunks) == 1
            opcode, _ = _decode_client_frame(parsed.protocol_output_chunks[0])
            assert opcode == int(Opcode.CLOSE)
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            )
            assert harness.fake.application_reads.empty()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_rejects_unrepresented_tls_output_before_any_socket_write(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_driver_v49d(tmp_path)
        try:
            assert harness.pending_raw is None
            harness.driver._outgoing.write(b"unrepresented-tls-control")  # noqa: SLF001
            with pytest.raises(
                PhysicalTlsWebSocketV49PostHandshakeOutputRequired,
                match="actor-ordered",
            ):
                await harness.driver.read_decrypted_ingress_v49d(
                    harness.socket, timeout_seconds=1
                )
            assert harness.driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            await asyncio.sleep(0.02)
            assert harness.fake.application_reads.empty()
        finally:
            await harness.close()

    source = inspect.getsource(
        ExactTlsWebSocketDriverV49.read_decrypted_ingress_v49d
    ) + inspect.getsource(ExactTlsWebSocketDriverV49._read_plaintext_chunk_v49d)
    assert "_flush_tls_output" not in source
    assert "_send_raw_ciphertext" not in source
    asyncio.run(scenario())

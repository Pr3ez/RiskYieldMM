from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49PostHandshakeOutputRequired,
    PhysicalTlsWebSocketV49ProtocolError,
    PreparedTlsControlCiphertextV49E,
    TlsControlOutputKindV49E,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
)


def test_explicit_opaque_tls_output_is_exactly_retained_without_socket_io(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            exact_chunks = (b"opaque-post-handshake-one", b"opaque-two")
            for chunk in exact_chunks:
                harness.driver._outgoing.write(chunk)  # noqa: SLF001
            prepared = (
                await harness.driver.prepare_opaque_post_handshake_response_v49e()
            )
            assert type(prepared) is PreparedTlsControlCiphertextV49E
            assert prepared.control_kind is (
                TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
            )
            # MemoryBIO may coalesce adjacent writes, so the artifact promises
            # exact bytes and retained drain order, not caller write boundaries.
            assert prepared.exact_ciphertext == b"".join(exact_chunks)
            assert prepared.ciphertext_octets == len(prepared.exact_ciphertext)
            assert prepared.ciphertext_batch_sha256 == sha256_digest(
                {
                    "domain": "RiskYieldMMActorOrderedTlsControlCiphertextV4_9E",
                    "ordered_chunks_base64": [
                        base64.b64encode(chunk).decode("ascii")
                        for chunk in prepared.ordered_ciphertext_chunks
                    ],
                }
            )
            assert harness.fake.application_reads.empty()
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_CONTROL_CIPHERTEXT_PREPARED_V49E
            )

            forged = object.__new__(PreparedTlsControlCiphertextV49E)
            for field in PreparedTlsControlCiphertextV49E.__dataclass_fields__:
                object.__setattr__(forged, field, getattr(prepared, field))
            object.__setattr__(
                forged, "ciphertext_octets", prepared.ciphertext_octets + 1
            )
            with pytest.raises(
                PhysicalTlsWebSocketV49ProtocolError, match="exact kind"
            ):
                ExactTlsWebSocketDriverV49._assert_prepared_tls_control_integrity_v49e(
                    forged
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49d_still_faults_on_unrepresented_post_handshake_output(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            harness.driver._outgoing.write(b"unrepresented-output")  # noqa: SLF001
            with pytest.raises(
                PhysicalTlsWebSocketV49PostHandshakeOutputRequired,
                match="actor-ordered",
            ):
                await harness.owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
        finally:
            await harness.close()

    asyncio.run(scenario())

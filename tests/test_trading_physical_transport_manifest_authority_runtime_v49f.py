from __future__ import annotations

import asyncio
import inspect
import sys
from dataclasses import fields
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import (
    sha256_digest,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionSqliteEnvironmentObservationV49F,
    PhysicalProjectionV4ConfigurationError,
)
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportCommandKindV49F,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION,
    PhysicalTransportManifestAuthoritySnapshotV49F,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    PhysicalTlsWebSocketV49StateError,
)
from tests.test_trading_physical_transport_runtime_v49b import _build_harness
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
)
from tests.test_trading_physical_transport_runtime_v49f_capacity import _policy

pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Linux-only V4.9F manifest-authority integration tests",
)


def _subject_id(
    snapshot: PhysicalTransportManifestAuthoritySnapshotV49F,
    sqlite_observation: PhysicalProjectionSqliteEnvironmentObservationV49F,
) -> str:
    return sha256_digest(
        {
            "manifest_authority_snapshot_id": snapshot.snapshot_id,
            "sqlite_environment_observation_id": sqlite_observation.observation_id,
        }
    )


def test_authoritative_inputs_are_owner_observed_immutable_and_complete(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            (
                snapshot,
                sqlite_observation,
            ) = await harness.runtime.capture_manifest_authority_inputs_v49f()

            assert type(snapshot) is PhysicalTransportManifestAuthoritySnapshotV49F
            assert (
                type(sqlite_observation)
                is PhysicalProjectionSqliteEnvironmentObservationV49F
            )
            assert snapshot.authority_profile == "EXACT_TEST"
            assert snapshot.transport_runtime_schema_version == (
                PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION
            )
            assert snapshot.transport_session_id == (
                harness.runtime.current_transport_session_id
            )
            assert snapshot.tls_websocket_driver_policy_id == (
                harness.owner.driver_policy_id
            )
            assert snapshot.retained_driver_runtime_observation_sha256 == (
                harness.driver.runtime_observation_sha256
            )
            assert snapshot.release_name == "riskyieldmm-collector"
            assert snapshot.release_version == "0.1.0-v49b-runtime-test"
            assert snapshot.release_entrypoint == "riskyieldmm.transport.collector"
            assert snapshot.captured_at_utc.tzinfo is not None
            assert snapshot.captured_monotonic_ns >= 0
            assert snapshot.chronyd_launch_id is None
            assert snapshot.chronyd_runtime_observation_sha256 is None

            assert sqlite_observation.database_path == str(harness.store.path)
            path_stat = harness.store.path.stat()
            assert sqlite_observation.database_device == path_stat.st_dev
            assert sqlite_observation.database_inode == path_stat.st_ino
            assert sqlite_observation.busy_timeout_milliseconds == 5_000
            assert sqlite_observation.foreign_keys_enabled is True
            assert sqlite_observation.trusted_schema_enabled is False
            assert sqlite_observation.cell_size_check_enabled is True
            assert sqlite_observation.mmap_size_bytes == 0
            assert sqlite_observation.journal_mode == "DELETE"
            assert sqlite_observation.synchronous_level == 3
            assert sqlite_observation.page_size_bytes in {
                512,
                1024,
                2048,
                4096,
                8192,
                16384,
                32768,
                65536,
            }

            for record in (snapshot, sqlite_observation):
                field_names = {field.name for field in fields(record)}
                assert {
                    "socket",
                    "owned_socket",
                    "socket_fd",
                    "socket_cookie_u64",
                    "connection",
                }.isdisjoint(field_names)
                assert not any(
                    name in field.name
                    for field in fields(record)
                    for name in ("descriptor", "capability", "private_key", "signer")
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_signing_rejects_opaque_subject_ids_and_requires_one_shot_authorization(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            (
                snapshot,
                sqlite_observation,
            ) = await harness.runtime.capture_manifest_authority_inputs_v49f()
            subject_id = _subject_id(snapshot, sqlite_observation)
            with pytest.raises(TypeError, match="one-shot manifest signing"):
                await harness.runtime.sign_manifest_authority_subject_v49f(
                    authorization=subject_id,
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_manifest_authority_requires_quiescent_orchestration_and_a1(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            lock = harness.runtime._transport_orchestration_lock_v49c  # noqa: SLF001
            async with lock:
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="quiescent orchestration",
                ):
                    await harness.runtime.capture_manifest_authority_inputs_v49f()

            gate = harness.runtime._transport_admission_gate_v49f  # noqa: SLF001
            assert gate is not None
            async with gate.admit(TransportCommandKindV49F.INGRESS):
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="quiescent A1",
                ):
                    await harness.runtime.capture_manifest_authority_inputs_v49f()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_sqlite_pragmas_are_recaptured_and_path_replacement_is_rejected(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            (
                snapshot,
                first,
            ) = await harness.runtime.capture_manifest_authority_inputs_v49f()
            harness.store._connection.execute("PRAGMA busy_timeout = 1234")  # noqa: SLF001
            _, changed = await harness.runtime.capture_manifest_authority_inputs_v49f()
            assert changed.busy_timeout_milliseconds == 1234
            assert changed.observation_id != first.observation_id
            harness.store._connection.execute("PRAGMA busy_timeout = 5000")  # noqa: SLF001

            original_path = harness.store.path
            retained_path = original_path.with_suffix(".retained.sqlite3")
            original_path.rename(retained_path)
            original_path.write_bytes(b"replacement")
            try:
                with pytest.raises(
                    PhysicalProjectionV4ConfigurationError,
                    match="device/inode changed",
                ):
                    await harness.runtime.capture_manifest_authority_inputs_v49f()
            finally:
                original_path.unlink()
                retained_path.rename(original_path)
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_driver_currentness_is_revalidated_and_public_factory_stays_closed(
    tmp_path: Path,
) -> None:
    signature = inspect.signature(
        PhysicalTransportRuntimeV4.sign_manifest_authority_subject_v49f
    )
    assert tuple(signature.parameters) == (
        "self",
        "authorization",
    )
    assert {
        "payload",
        "signer",
        "private_key",
        "socket_owner",
        "connection",
        "descriptor",
    }.isdisjoint(signature.parameters)
    with pytest.raises(TypeError, match="use for_test"):
        PhysicalTransportRuntimeV4(
            journal=None,  # type: ignore[arg-type]
            writer_lease=None,  # type: ignore[arg-type]
            clock_source=None,  # type: ignore[arg-type]
            signer=None,
            deployment_admission=None,  # type: ignore[arg-type]
            idempotency_prefix="closed",
        )

    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            transport_capacity_policy_v49f=_policy(),
        )
        try:
            await _establish_and_activate(harness)
            retained = harness.driver._runtime_observation_sha256  # noqa: SLF001
            harness.driver._runtime_observation_sha256 = sha256_digest(  # noqa: SLF001
                {"substitution": "runtime"}
            )
            try:
                with pytest.raises(
                    PhysicalTlsWebSocketV49StateError,
                    match="measured runtime authority changed",
                ):
                    await harness.runtime.capture_manifest_authority_inputs_v49f()
            finally:
                harness.driver._runtime_observation_sha256 = retained  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())

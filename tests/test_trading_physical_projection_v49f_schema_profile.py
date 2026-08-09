from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace

import pytest

from riskyieldmm.trading import physical_projection_v4


def test_raw_v7_projection_schema_sql_and_fingerprint_are_frozen() -> None:
    schema_core_bytes = physical_projection_v4._SCHEMA_SQL.encode("utf-8")  # noqa: SLF001
    schema_sql = physical_projection_v4._FULL_SCHEMA_SQL  # noqa: SLF001
    schema_bytes = schema_sql.encode("utf-8")

    assert len(schema_core_bytes) == 121_640
    assert hashlib.sha256(schema_core_bytes).hexdigest() == (
        "d288f934fba970b1e7240a62ada0e5a11e9901aa25d7e43351a473e4fd3192b7"
    )
    assert len(schema_bytes) == 136_483
    assert hashlib.sha256(schema_bytes).hexdigest() == (
        "d4b311050f20f03159cd7d121421535e36f45a1d56d42022345ab9fdfcf088e5"
    )
    assert physical_projection_v4._expected_schema_fingerprint().hex() == (  # noqa: SLF001
        "7aefd863c3c6773d357d2ec638bf1c212055fcacfbec406e10030e184f599d98"
    )


def test_physical_projection_store_pins_raw_v7_profile_without_caller_mode() -> None:
    profile = physical_projection_v4._RAW_V7_SCHEMA_PROFILE_V4  # noqa: SLF001
    store_type = physical_projection_v4.PhysicalProjectionStoreV4

    assert store_type._projection_schema_profile_v4() is profile  # noqa: SLF001
    assert profile.schema_sql is physical_projection_v4._FULL_SCHEMA_SQL  # noqa: SLF001
    assert (
        profile.schema_version
        == physical_projection_v4.PHYSICAL_PROJECTION_V4_SCHEMA_VERSION
    )
    assert (
        profile.validation_version
        == physical_projection_v4.PHYSICAL_PROJECTION_V4_VALIDATION_VERSION
    )
    assert physical_projection_v4._expected_schema_fingerprint_for_profile(  # noqa: SLF001
        profile
    ).hex() == ("7aefd863c3c6773d357d2ec638bf1c212055fcacfbec406e10030e184f599d98")
    assert tuple(inspect.signature(store_type).parameters) == (
        "path",
        "clock",
        "fault_injector",
        "max_object_bytes",
    )


def test_raw_v7_projection_ledger_identity_derivation_is_frozen() -> None:
    assert (
        physical_projection_v4._derive_ledger_id(  # noqa: SLF001
            nonce=bytes(range(32)),
            created_at="2026-07-25T00:00:00.000000Z",
            schema_fingerprint=bytes.fromhex(
                "7aefd863c3c6773d357d2ec638bf1c212055fcacfbec406e10030e184f599d98"
            ),
        ).hex()
        == "98b1fe20e726e77e82ea320d3b962941b3d292931ac845f37929747c261208e3"
    )


def test_raw_v7_projection_request_and_receipt_identities_are_frozen() -> None:
    ledger_id = bytes.fromhex(
        "98b1fe20e726e77e82ea320d3b962941b3d292931ac845f37929747c261208e3"
    )

    assert (
        physical_projection_v4._request_hash(  # noqa: SLF001
            "PROFILE_GOLDEN_V1",
            {"alpha": 1, "beta": "x"},
        ).hex()
        == "1d1f951bf801624e9176b158f2cd2db9c95aa82c24217cd1c036ea0552b3e466"
    )
    assert (
        physical_projection_v4._receipt_hash(  # noqa: SLF001
            ledger_id=ledger_id,
            sequence=1,
            previous_receipt_hash=(
                physical_projection_v4.PHYSICAL_PROJECTION_V4_GENESIS_HASH
            ),
            record_kind=physical_projection_v4.PhysicalRecordKindV4.RAW_INGRESS_COMMIT,
            identity_id=bytes.fromhex("11" * 32),
            content_hash=bytes.fromhex("22" * 32),
        ).hex()
        == "3fc924daec4c3e0f97176209633ffe5f8d3aefeb26b1ccfd28b2b54187825127"
    )


def test_raw_v7_capacity_entry_points_reject_another_schema_profile() -> None:
    alternate_profile = replace(
        physical_projection_v4._RAW_V7_SCHEMA_PROFILE_V4,  # noqa: SLF001
        schema_version="non_raw_v7_test_profile",
    )

    class NonRawV7ProjectionStore(physical_projection_v4.PhysicalProjectionStoreV4):
        _PINNED_SCHEMA_PROFILE_V4 = alternate_profile

    store = object.__new__(NonRawV7ProjectionStore)
    expected = pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="exact Raw V7 schema profile",
    )
    with expected:
        store._capacity_measurement_attempt_authority_v49f(  # noqa: SLF001
            transport_session_id="0" * 64,
            baseline_actor_event_count=0,
        )
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="exact Raw V7 schema profile",
    ):
        store._append_capacity_measurement_operation_attempt_core_v49f(  # noqa: SLF001
            None,  # type: ignore[arg-type]
            idempotency_key="profile-guard-attempt",
        )
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="exact Raw V7 schema profile",
    ):
        store._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="exact Raw V7 schema profile",
    ):
        store._append_capacity_measurement_operation_terminal_core_v49f(  # noqa: SLF001
            None,
            idempotency_key="profile-guard-terminal",
            returned_progress_evidence=None,
        )

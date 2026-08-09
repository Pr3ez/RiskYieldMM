from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4WriterFenceError,
)
from tests.test_trading_physical_market_data_v3 import bar_policy


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fence_row(path: Path) -> tuple[int, int, bytes, str, str, str | None]:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT generation, active, lease_token_sha256, holder_id,
                   claimed_at, released_at
            FROM operational_transport_writer_fence
            WHERE singleton = 1
            """
        ).fetchone()
    assert row is not None
    return (
        int(row[0]),
        int(row[1]),
        bytes(row[2]),
        str(row[3]),
        str(row[4]),
        None if row[5] is None else str(row[5]),
    )


def receipt_count(path: Path) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute("SELECT count(*) FROM receipts").fetchone()[0])


def test_claim_is_atomic_and_exact_active_replay_is_idempotent(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection.sqlite3"
    token = digest("writer-token-1")

    with PhysicalProjectionStoreV4(path) as store:
        assert (
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=token,
                holder_id="collector-main",
            )
            == 1
        )
        assert (
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=token,
                holder_id="collector-main",
            )
            == 1
        )
        store.assert_transport_runtime_writer_fence(
            lease_token_sha256=token,
            generation=1,
        )
        store.verify()

    generation, active, stored_token, holder, _, released_at = fence_row(path)
    assert generation == 1
    assert active == 1
    assert stored_token.hex() == token
    assert holder == "collector-main"
    assert released_at is None


def test_new_claim_supersedes_old_instance_and_fences_mutation_and_verify(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection.sqlite3"
    first_token = digest("writer-token-1")
    second_token = digest("writer-token-2")
    first = PhysicalProjectionStoreV4(path)
    second: PhysicalProjectionStoreV4 | None = None
    try:
        assert (
            first.claim_transport_runtime_writer_fence(
                lease_token_sha256=first_token,
                holder_id="collector-first",
            )
            == 1
        )
        second = PhysicalProjectionStoreV4(path)
        assert (
            second.claim_transport_runtime_writer_fence(
                lease_token_sha256=second_token,
                holder_id="collector-second",
            )
            == 2
        )

        before = receipt_count(path)
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="released or superseded",
        ):
            first.append_adapter_policy(
                bar_policy(requires_status=False),
                idempotency_key="stale-writer-append",
            )
        assert receipt_count(path) == before
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="released or superseded",
        ):
            first.verify()
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="released or superseded",
        ):
            first.assert_transport_runtime_writer_fence(
                lease_token_sha256=first_token,
                generation=1,
            )
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="released or superseded",
        ):
            first.release_transport_runtime_writer_fence(lease_token_sha256=first_token)
        assert receipt_count(path) == before

        assert second.verify().receipt_count == before
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="asserted writer fence epoch",
        ):
            second.assert_transport_runtime_writer_fence(
                lease_token_sha256=second_token,
                generation=1,
            )
    finally:
        first.close()
        if second is not None:
            second.close()


def test_release_requires_exact_bound_token_and_generation(tmp_path: Path) -> None:
    path = tmp_path / "projection.sqlite3"
    token = digest("writer-token")
    wrong_token = digest("wrong-token")

    with PhysicalProjectionStoreV4(path) as store:
        assert (
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=token,
                holder_id="collector-main",
            )
            == 1
        )
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="differs from the bound token",
        ):
            store.release_transport_runtime_writer_fence(lease_token_sha256=wrong_token)
        assert fence_row(path)[1] == 1

        store.release_transport_runtime_writer_fence(lease_token_sha256=token)
        generation, active, stored_token, holder, _, released_at = fence_row(path)
        assert (generation, active, stored_token.hex(), holder) == (
            1,
            0,
            token,
            "collector-main",
        )
        assert released_at is not None

        # An inactive fence leaves ordinary reference-projection behavior intact.
        store.append_adapter_policy(
            bar_policy(requires_status=False),
            idempotency_key="reference-after-release",
        )


def test_close_leaves_stale_active_row_and_fresh_claim_advances_generation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection.sqlite3"
    stale_token = digest("stale-token")
    fresh_token = digest("fresh-token")

    first = PhysicalProjectionStoreV4(path)
    assert (
        first.claim_transport_runtime_writer_fence(
            lease_token_sha256=stale_token,
            holder_id="collector-before-crash",
        )
        == 1
    )
    first.close()
    assert fence_row(path)[0:2] == (1, 1)

    with PhysicalProjectionStoreV4(path) as recovered:
        # Opening and verifying stale diagnostic state is safe; mutation remains
        # unavailable until the new OS-lease holder claims its application epoch.
        assert recovered.verify().receipt_count == 0
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="unbound store cannot mutate",
        ):
            recovered.append_adapter_policy(
                bar_policy(requires_status=False),
                idempotency_key="unbound-stale-append",
            )
        assert (
            recovered.claim_transport_runtime_writer_fence(
                lease_token_sha256=fresh_token,
                holder_id="collector-after-restart",
            )
            == 2
        )
        recovered.append_adapter_policy(
            bar_policy(requires_status=False),
            idempotency_key="recovered-append",
        )

    assert fence_row(path)[0:4] == (
        2,
        1,
        bytes.fromhex(fresh_token),
        "collector-after-restart",
    )
    assert receipt_count(path) == 1


def test_active_token_replay_with_different_holder_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "projection.sqlite3"
    token = digest("shared-token")

    with PhysicalProjectionStoreV4(path) as first:
        assert (
            first.claim_transport_runtime_writer_fence(
                lease_token_sha256=token,
                holder_id="collector-first",
            )
            == 1
        )
        second = PhysicalProjectionStoreV4(path)
        try:
            with pytest.raises(
                PhysicalProjectionV4WriterFenceError,
                match="bound to another holder",
            ):
                second.claim_transport_runtime_writer_fence(
                    lease_token_sha256=token,
                    holder_id="collector-second",
                )
        finally:
            second.close()

    assert fence_row(path)[0:4] == (
        1,
        1,
        bytes.fromhex(token),
        "collector-first",
    )

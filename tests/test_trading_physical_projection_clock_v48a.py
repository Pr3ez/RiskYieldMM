from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, utc_iso
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    DeploymentRoleKeyV4,
    DeploymentTrustRootV4,
    derive_deployment_signing_key_id,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ClockError,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import ClockEvidenceV4

T0 = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
SOURCE_ID = hashlib.sha256(b"v48a-clock-source").hexdigest()
DOMAIN_ID = hashlib.sha256(b"v48a-monotonic-domain").hexdigest()
LEASE_TOKEN_SHA256 = hashlib.sha256(b"v48a-writer-lease").hexdigest()
CHRONYD_LAUNCH_ID = hashlib.sha256(b"v48b-chronyd-launch").hexdigest()
CHRONYD_RUNTIME_OBSERVATION = hashlib.sha256(
    b"v48b-chronyd-runtime-observation"
).hexdigest()


def clock_evidence(
    *,
    sampled_at: datetime,
    monotonic_before_ns: int,
    monotonic_after_ns: int,
    source_id: str = SOURCE_ID,
    domain_id: str = DOMAIN_ID,
    uncertainty_milliseconds: int = 2,
    synchronized: bool = True,
    lifetime_milliseconds: int = 1_000,
    chronyd_launch_id: str | None = None,
    chronyd_runtime_observation_sha256: str | None = None,
) -> ClockEvidenceV4:
    return ClockEvidenceV4(
        clock_source_manifest_id=source_id,
        monotonic_clock_domain_id=domain_id,
        sampled_at=sampled_at,
        monotonic_ns=monotonic_after_ns,
        uncertainty_milliseconds=uncertainty_milliseconds,
        synchronized=synchronized,
        valid_until=sampled_at + timedelta(milliseconds=lifetime_milliseconds),
        monotonic_before_ns=monotonic_before_ns,
        monotonic_after_ns=monotonic_after_ns,
        wall_before_at=sampled_at - timedelta(microseconds=1),
        wall_after_at=sampled_at,
        clock_resolution_ns=1,
        observation_sha256=hashlib.sha256(
            f"{sampled_at.isoformat()}-{monotonic_after_ns}".encode()
        ).hexdigest(),
        selectable_source_count=3,
        chronyd_launch_id=chronyd_launch_id,
        chronyd_runtime_observation_sha256=(chronyd_runtime_observation_sha256),
    )


class QueuedClock:
    def __init__(
        self,
        values: list[ClockEvidenceV4 | BaseException],
        *,
        monotonic_values: list[int | BaseException] | None = None,
    ) -> None:
        self.values = values
        self.monotonic_values = monotonic_values or []
        self.calls = 0
        self.monotonic_calls = 0
        self._last_sample: ClockEvidenceV4 | None = None

    def sample(self) -> ClockEvidenceV4:
        self.calls += 1
        value = self.values.pop(0)
        if isinstance(value, BaseException):
            raise value
        self._last_sample = value
        return value

    def monotonic_now_ns(self) -> int:
        self.monotonic_calls += 1
        if self.monotonic_values:
            value = self.monotonic_values.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        assert self._last_sample is not None
        return self._last_sample.monotonic_after_ns


def bind_for_test(store: PhysicalProjectionStoreV4, clock: QueuedClock) -> None:
    store.bind_governed_clock_for_test(
        clock,
        clock_source_manifest_id=SOURCE_ID,
        monotonic_clock_domain_id=DOMAIN_ID,
        maximum_uncertainty_milliseconds=100,
        maximum_lifetime_milliseconds=5_000,
    )


def bind_loaded_chronyd_profile_for_test(
    store: PhysicalProjectionStoreV4,
    clock: QueuedClock,
) -> None:
    """Exercise post-binding live checks while V4.9 keeps construction sealed."""

    bind_for_test(store, clock)
    store._governed_clock_live_profile = True  # noqa: SLF001


def trust_root() -> DeploymentTrustRootV4:
    signer = Ed25519CheckpointSigner.generate()
    key = DeploymentRoleKeyV4(
        key_id=derive_deployment_signing_key_id(signer.public_key_bytes),
        public_key_hex=signer.public_key_bytes.hex(),
    )
    return DeploymentTrustRootV4(
        root_version=1,
        deployment_role_threshold=1,
        deployment_keys=(key,),
    )


def test_one_governed_sample_supplies_all_generated_transaction_times(
    tmp_path: Path,
) -> None:
    claim_at = T0
    append_at = T0 + timedelta(seconds=1)
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=claim_at,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
            ),
            clock_evidence(
                sampled_at=append_at,
                monotonic_before_ns=200,
                monotonic_after_ns=210,
            ),
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        assert store.is_governed_clock_bound
        assert not store.is_live_clock_profile
        assert store.governed_clock_identity == (SOURCE_ID, DOMAIN_ID)

        generation = store.claim_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256,
            holder_id="v48a-test-writer",
        )
        assert generation == 1
        stored_claim = store._connection.execute(  # noqa: SLF001
            "SELECT claimed_at FROM operational_transport_writer_fence"
        ).fetchone()
        assert stored_claim == (utc_iso(claim_at),)

        store.append_deployment_trust_root(
            trust_root(), idempotency_key="v48a-clock-root"
        )
        receipt_at = store._connection.execute(  # noqa: SLF001
            "SELECT committed_at FROM receipts ORDER BY global_sequence DESC LIMIT 1"
        ).fetchone()
        batch_at = store._connection.execute(  # noqa: SLF001
            "SELECT committed_at FROM operation_batches "
            "ORDER BY last_receipt_sequence DESC LIMIT 1"
        ).fetchone()
        assert receipt_at == (utc_iso(append_at),)
        assert batch_at == receipt_at
        assert clock.calls == 2


def test_live_projection_accepts_one_stable_loaded_chronyd_pair(
    tmp_path: Path,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
                chronyd_launch_id=CHRONYD_LAUNCH_ID,
                chronyd_runtime_observation_sha256=(CHRONYD_RUNTIME_OBSERVATION),
            ),
            clock_evidence(
                sampled_at=T0 + timedelta(seconds=1),
                monotonic_before_ns=200,
                monotonic_after_ns=210,
                chronyd_launch_id=CHRONYD_LAUNCH_ID,
                chronyd_runtime_observation_sha256=(CHRONYD_RUNTIME_OBSERVATION),
            ),
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_loaded_chronyd_profile_for_test(store, clock)

        generation = store.claim_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256,
            holder_id="v48b-paired-writer",
        )
        store.release_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256
        )

        assert generation == 1
        assert clock.calls == 2
        assert store._connection.execute(  # noqa: SLF001
            "SELECT active, released_at IS NOT NULL "
            "FROM operational_transport_writer_fence"
        ).fetchone() == (0, 1)


def test_live_projection_rejects_missing_loaded_chronyd_pair_before_sql(
    tmp_path: Path,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
            )
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_loaded_chronyd_profile_for_test(store, clock)

        with pytest.raises(
            PhysicalProjectionV4ClockError,
            match="synthetic or incomplete",
        ):
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256,
                holder_id="v48b-missing-pair-writer",
            )

        assert store._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM operational_transport_writer_fence"
        ).fetchone() == (0,)


def test_live_projection_rejects_changed_loaded_chronyd_pair_and_rolls_back(
    tmp_path: Path,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
                chronyd_launch_id=CHRONYD_LAUNCH_ID,
                chronyd_runtime_observation_sha256=(CHRONYD_RUNTIME_OBSERVATION),
            ),
            clock_evidence(
                sampled_at=T0 + timedelta(seconds=1),
                monotonic_before_ns=200,
                monotonic_after_ns=210,
                chronyd_launch_id=hashlib.sha256(
                    b"v48b-replacement-launch"
                ).hexdigest(),
                chronyd_runtime_observation_sha256=hashlib.sha256(
                    b"v48b-replacement-runtime-observation"
                ).hexdigest(),
            ),
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_loaded_chronyd_profile_for_test(store, clock)
        store.claim_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256,
            holder_id="v48b-changed-pair-writer",
        )

        with pytest.raises(PhysicalProjectionV4ClockError, match="regresses"):
            store.release_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256
            )

        assert store._connection.execute(  # noqa: SLF001
            "SELECT active, released_at FROM operational_transport_writer_fence"
        ).fetchone() == (1, None)


@pytest.mark.parametrize(
    "second",
    [
        clock_evidence(
            sampled_at=T0 + timedelta(seconds=1),
            monotonic_before_ns=110,
            monotonic_after_ns=120,
        ),
        clock_evidence(
            sampled_at=T0 - timedelta(seconds=1),
            monotonic_before_ns=200,
            monotonic_after_ns=210,
        ),
    ],
    ids=("overlap", "wall-regression"),
)
def test_regressing_or_overlapping_clock_rolls_back_without_releasing_fence(
    tmp_path: Path,
    second: ClockEvidenceV4,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
            ),
            second,
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        store.claim_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256,
            holder_id="v48a-test-writer",
        )

        with pytest.raises(PhysicalProjectionV4ClockError, match="overlaps|regresses"):
            store.release_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256
            )

        row = store._connection.execute(  # noqa: SLF001
            "SELECT active, released_at FROM operational_transport_writer_fence"
        ).fetchone()
        assert row == (1, None)
        assert clock.calls == 2


@pytest.mark.parametrize(
    "mutate, match",
    [
        (
            lambda value: replace(
                value,
                clock_source_manifest_id=hashlib.sha256(b"wrong-source").hexdigest(),
            ),
            "source",
        ),
        (
            lambda value: replace(
                value,
                monotonic_clock_domain_id=hashlib.sha256(b"wrong-domain").hexdigest(),
            ),
            "domain",
        ),
        (lambda value: replace(value, uncertainty_milliseconds=101), "uncertainty"),
        (lambda value: replace(value, synchronized=False), "synchronization"),
        (
            lambda value: replace(value, valid_until=value.sampled_at),
            "lifetime",
        ),
        (
            lambda value: replace(
                value,
                valid_until=value.sampled_at + timedelta(milliseconds=5_001),
            ),
            "lifetime",
        ),
    ],
)
def test_invalid_governed_sample_prevents_any_sql_mutation(
    tmp_path: Path,
    mutate: Callable[[ClockEvidenceV4], ClockEvidenceV4],
    match: str,
) -> None:
    clock = QueuedClock(
        [
            mutate(
                clock_evidence(
                    sampled_at=T0,
                    monotonic_before_ns=100,
                    monotonic_after_ns=110,
                )
            )
        ]
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        with pytest.raises(PhysicalProjectionV4ClockError, match=match):
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256,
                holder_id="v48a-test-writer",
            )
        assert store._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM operational_transport_writer_fence"
        ).fetchone() == (0,)


def test_clock_failure_is_wrapped_and_precedes_sql_mutation(tmp_path: Path) -> None:
    clock = QueuedClock([RuntimeError("clock unavailable")])
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        with pytest.raises(PhysicalProjectionV4ClockError, match="sampling failed"):
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256,
                holder_id="v48a-test-writer",
            )
        assert not store._connection.in_transaction  # noqa: SLF001


def test_clock_expiry_during_transaction_rolls_back_before_commit(
    tmp_path: Path,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
                lifetime_milliseconds=1,
            )
        ],
        monotonic_values=[111, 1_000_111],
    )
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        with pytest.raises(PhysicalProjectionV4ClockError, match="expired"):
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256,
                holder_id="v48a-test-writer",
            )
        assert not store._connection.in_transaction  # noqa: SLF001
        assert store._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM operational_transport_writer_fence"
        ).fetchone() == (0,)
        assert clock.calls == 1
        assert clock.monotonic_calls == 2


def test_base_exception_rolls_back_complete_governed_transaction(
    tmp_path: Path,
) -> None:
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
            ),
            clock_evidence(
                sampled_at=T0 + timedelta(seconds=1),
                monotonic_before_ns=200,
                monotonic_after_ns=210,
            ),
        ]
    )

    def interrupt_before_commit(stage: str) -> None:
        if stage == "before_commit":
            raise KeyboardInterrupt

    with PhysicalProjectionStoreV4(
        tmp_path / "projection.sqlite",
        fault_injector=interrupt_before_commit,
    ) as store:
        bind_for_test(store, clock)
        store.claim_transport_runtime_writer_fence(
            lease_token_sha256=LEASE_TOKEN_SHA256,
            holder_id="v48a-test-writer",
        )

        with pytest.raises(KeyboardInterrupt):
            store.append_deployment_trust_root(
                trust_root(), idempotency_key="v48a-interrupted-root"
            )

        assert not store._connection.in_transaction  # noqa: SLF001
        assert store._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM receipts"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT COUNT(*) FROM operation_batches"
        ).fetchone() == (0,)


def test_invalid_binding_arguments_do_not_half_bind_store(tmp_path: Path) -> None:
    clock = QueuedClock([])
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        with pytest.raises(CanonicalizationError):
            store.bind_governed_clock_for_test(
                clock,
                clock_source_manifest_id="not-a-sha256",
                monotonic_clock_domain_id=DOMAIN_ID,
                maximum_uncertainty_milliseconds=100,
                maximum_lifetime_milliseconds=5_000,
            )
        assert not store.is_governed_clock_bound

        bind_for_test(store, clock)
        assert store.is_governed_clock_bound


def test_binding_is_one_shot_thread_bound_and_not_restored_on_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection.sqlite"
    clock = QueuedClock(
        [
            clock_evidence(
                sampled_at=T0,
                monotonic_before_ns=100,
                monotonic_after_ns=110,
            )
        ]
    )
    store = PhysicalProjectionStoreV4(path)
    bind_for_test(store, clock)
    with pytest.raises(PhysicalProjectionV4ClockError, match="already bound"):
        bind_for_test(store, clock)
    with pytest.raises(PhysicalProjectionV4ClockError, match="only available"):
        store._now()  # noqa: SLF001

    errors: list[BaseException] = []

    def wrong_thread() -> None:
        try:
            store.claim_transport_runtime_writer_fence(
                lease_token_sha256=LEASE_TOKEN_SHA256,
                holder_id="v48a-test-writer",
            )
        except BaseException as exc:  # test captures the exact fail-closed error
            errors.append(exc)

    thread = threading.Thread(target=wrong_thread)
    thread.start()
    thread.join()
    assert len(errors) == 1
    assert isinstance(errors[0], PhysicalProjectionV4ClockError)
    assert "process/thread" in str(errors[0])
    store.close()

    with PhysicalProjectionStoreV4(path) as reopened:
        assert not reopened.is_governed_clock_bound
        assert reopened.governed_clock_identity is None


def test_arbitrary_clock_source_cannot_enter_live_binding(tmp_path: Path) -> None:
    clock = QueuedClock([])
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        with pytest.raises(TypeError, match="promotion-eligible"):
            store._bind_live_linux_clock(  # noqa: SLF001
                clock,
                maximum_lifetime_milliseconds=5_000,
            )
        assert not store.is_governed_clock_bound

        with pytest.raises(TypeError, match="promotion-eligible"):
            store._bind_governed_clock(  # noqa: SLF001
                clock,
                clock_source_manifest_id=SOURCE_ID,
                monotonic_clock_domain_id=DOMAIN_ID,
                maximum_uncertainty_milliseconds=100,
                maximum_lifetime_milliseconds=5_000,
                live_profile=True,
            )
        assert not store.is_governed_clock_bound


def test_live_bound_projection_rejects_direct_caller_session_facts(
    tmp_path: Path,
) -> None:
    clock = QueuedClock([])
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        bind_for_test(store, clock)
        store._governed_clock_live_profile = True  # noqa: SLF001

        with pytest.raises(PhysicalProjectionV4ClockError, match="caller-authored"):
            store.append_transport_session_attestation(
                object(),  # type: ignore[arg-type]
                socket_owner_binding=object(),  # type: ignore[arg-type]
                idempotency_key="v48a-direct-live-session-bypass",
            )


def test_test_binding_rejects_non_clock_objects(tmp_path: Path) -> None:
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        with pytest.raises(TypeError, match=r"sample\(\)"):
            store.bind_governed_clock_for_test(
                object(),
                clock_source_manifest_id=SOURCE_ID,
                monotonic_clock_domain_id=DOMAIN_ID,
                maximum_uncertainty_milliseconds=100,
                maximum_lifetime_milliseconds=5_000,
            )

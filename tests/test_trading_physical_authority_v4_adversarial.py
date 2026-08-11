from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.contracts import InformationSetV3
from riskyieldmm.trading.physical_evidence_v4 import (
    EvidenceCutoffV4,
    PhysicalScopeManifestV4,
)
from riskyieldmm.trading.physical_health_v4 import PhysicalHealthTransitionV4
from riskyieldmm.trading.physical_market_data import (
    PhysicalGateStage,
    PhysicalGateVerdict,
    PrefixHealth,
    SelectionStatus,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4IdempotencyError,
)
from tests.test_trading_physical_authority_v4_projection import (
    FixedClock,
    append_live_authority_prefix,
    authority_scope,
    exact_event_binding,
    live_information_set,
    receipt_count,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    status_policy,
)

HEALTH_KNOWLEDGE = T0 + timedelta(minutes=2, seconds=4)
PROOF_COMPUTED_AT = HEALTH_KNOWLEDGE + timedelta(milliseconds=100)
INFORMATION_ASSEMBLED_AT = HEALTH_KNOWLEDGE + timedelta(milliseconds=200)
GATE_EVALUATED_AT = HEALTH_KNOWLEDGE + timedelta(milliseconds=300)


class InjectedProjectionFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedGateInputs:
    scope: PhysicalScopeManifestV4
    cutoff: EvidenceCutoffV4
    transition: PhysicalHealthTransitionV4
    information_set: InformationSetV3


def append_live_evidence(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
) -> tuple[PhysicalScopeManifestV4, object]:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    store.append_health_policy(idempotency_key="health-policy")
    store.append_adapter_policy(primary, idempotency_key="primary-adapter-policy")
    store.append_adapter_policy(
        required_status, idempotency_key="status-adapter-policy"
    )
    store.append_scope(scope, idempotency_key="authority-scope")
    classifications, _ = append_live_authority_prefix(
        store,
        clock=clock,
        scope=scope,
        primary=primary,
        required_status=required_status,
    )
    selected_revision = classifications[2].revision
    assert selected_revision is not None
    return scope, selected_revision


def prepare_gate_inputs(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
) -> PreparedGateInputs:
    scope, selected_revision = append_live_evidence(store, clock)
    clock.value = HEALTH_KNOWLEDGE
    cutoff, transition = store.append_derived_health_cutoff(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        knowledge_cutoff_ts=HEALTH_KNOWLEDGE,
        idempotency_key="derived-health-healthy",
    )
    assert cutoff.health is PrefixHealth.HEALTHY

    binding = exact_event_binding(scope)
    store.append_protocol_binding(
        binding,
        idempotency_key="authority-protocol-binding",
    )
    clock.value = PROOF_COMPUTED_AT
    proof, chunk = store.select_observations(
        physical_protocol_binding_id=binding.physical_protocol_binding_id,
        evidence_cutoff_id=cutoff.evidence_cutoff_id,
        observation_cutoff_ts=HEALTH_KNOWLEDGE,
        computed_at=PROOF_COMPUTED_AT,
        idempotency_key="authority-selection",
    )
    assert proof.status is SelectionStatus.SELECTED
    assert chunk is not None
    assert chunk.ordered_observation_revision_ids == (
        selected_revision.observation_revision_id,
    )
    information_set = live_information_set(
        scope=scope,
        binding=binding,
        revision=selected_revision,
        observation_cutoff_ts=HEALTH_KNOWLEDGE,
        assembled_at=INFORMATION_ASSEMBLED_AT,
    )
    clock.value = INFORMATION_ASSEMBLED_AT
    store.append_information_set(
        information_set,
        idempotency_key="authority-information-set",
    )
    return PreparedGateInputs(
        scope=scope,
        cutoff=cutoff,
        transition=transition,
        information_set=information_set,
    )


def test_health_transition_fault_rolls_back_cutoff_and_transition_atomically(
    tmp_path: Path,
) -> None:
    database = tmp_path / "health-transition-rollback.sqlite3"

    def fail_after_transition(stage: str) -> None:
        if stage == "after_physical_health_transition_insert":
            raise InjectedProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        database,
        clock=clock,
        fault_injector=fail_after_transition,
    ) as store:
        scope, _ = append_live_evidence(store, clock)
        before = receipt_count(store)
        clock.value = HEALTH_KNOWLEDGE
        with pytest.raises(
            InjectedProjectionFailure,
            match="after_physical_health_transition_insert",
        ):
            store.append_derived_health_cutoff(
                physical_scope_manifest_id=scope.physical_scope_manifest_id,
                knowledge_cutoff_ts=HEALTH_KNOWLEDGE,
                idempotency_key="derived-health-healthy",
            )
        assert receipt_count(store) == before
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM evidence_cutoffs"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM physical_health_transitions"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            ("derived-health-healthy",),
        ).fetchone() == (0,)
        report = store.verify()
        assert report.cutoff_count == 0
        assert report.physical_health_transition_count == 0
        store.release_transport_runtime_writer_fence(
            lease_token_sha256=digest("authority-owner-writer-fence")
        )

    reopened_clock = FixedClock(HEALTH_KNOWLEDGE)
    with PhysicalProjectionStoreV4(
        database,
        clock=reopened_clock,
    ) as reopened:
        cutoff, transition = reopened.append_derived_health_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=HEALTH_KNOWLEDGE,
            idempotency_key="derived-health-healthy",
        )
        assert cutoff.health is PrefixHealth.HEALTHY
        assert transition.current_health is PrefixHealth.HEALTHY
        report = reopened.verify()
        assert report.cutoff_count == 1
        assert report.physical_health_transition_count == 1


def test_gate_fault_rolls_back_then_reopen_retries_and_blocks_tampering(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gate-rollback-reopen.sqlite3"

    def fail_after_gate(stage: str) -> None:
        if stage == "after_physical_evidence_gate_insert":
            raise InjectedProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        database,
        clock=clock,
        fault_injector=fail_after_gate,
    ) as store:
        prepared = prepare_gate_inputs(store, clock)
        before = receipt_count(store)
        clock.value = GATE_EVALUATED_AT
        with pytest.raises(
            InjectedProjectionFailure,
            match="after_physical_evidence_gate_insert",
        ):
            store.evaluate_physical_gate(
                information_set_id=prepared.information_set.information_set_id,
                gate_stage=PhysicalGateStage.DECISION_INPUT,
                idempotency_key="authority-gate-pass",
            )
        assert receipt_count(store) == before
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM physical_evidence_gates"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM physical_gate_proof_links"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM physical_gate_health_links"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            ("authority-gate-pass",),
        ).fetchone() == (0,)
        assert store.verify().physical_evidence_gate_count == 0
        store.release_transport_runtime_writer_fence(
            lease_token_sha256=digest("authority-owner-writer-fence")
        )

    reopened_clock = FixedClock(GATE_EVALUATED_AT)
    with PhysicalProjectionStoreV4(
        database,
        clock=reopened_clock,
    ) as reopened:
        gate = reopened.evaluate_physical_gate(
            information_set_id=prepared.information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-pass",
        )
        assert gate.verdict is PhysicalGateVerdict.PASS
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            reopened._connection.execute(  # noqa: SLF001
                """
                UPDATE physical_evidence_gates SET verdict = 'ABSTAIN'
                WHERE physical_evidence_gate_id = ?
                """,
                (bytes.fromhex(gate.physical_evidence_gate_id),),
            )
        report = reopened.verify()
        assert report.physical_evidence_gate_count == 1
        receipt_root = report.global_receipt_root
        receipt_total = report.receipt_count

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(T0 + timedelta(days=2)),
    ) as reopened_again:
        report = reopened_again.verify()
        assert report.global_receipt_root == receipt_root
        assert report.receipt_count == receipt_total
        assert report.physical_evidence_gate_count == 1
        replayed = reopened_again.evaluate_physical_gate(
            information_set_id=prepared.information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-pass",
        )
        assert replayed == gate
        assert receipt_count(reopened_again) == receipt_total


def test_gate_uses_authority_clock_and_rejects_forged_idempotency_reuse(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gate-adversarial-inputs.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        database,
        clock=clock,
    ) as store:
        prepared = prepare_gate_inputs(store, clock)
        before = receipt_count(store)
        clock.value = HEALTH_KNOWLEDGE - timedelta(microseconds=1)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="evaluation precedes the information cutoff",
        ):
            store.evaluate_physical_gate(
                information_set_id=prepared.information_set.information_set_id,
                gate_stage=PhysicalGateStage.DECISION_INPUT,
                idempotency_key="early-gate",
            )
        assert receipt_count(store) == before
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            ("early-gate",),
        ).fetchone() == (0,)

        clock.value = GATE_EVALUATED_AT
        gate = store.evaluate_physical_gate(
            information_set_id=prepared.information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="authority-gate-pass",
        )
        assert gate.evaluated_at == GATE_EVALUATED_AT
        assert gate.verdict is PhysicalGateVerdict.PASS
        after_gate = receipt_count(store)

        with pytest.raises(
            PhysicalProjectionV4IdempotencyError,
            match="another request",
        ):
            store.evaluate_physical_gate(
                information_set_id=prepared.information_set.information_set_id,
                gate_stage=PhysicalGateStage.EXECUTION_BAR,
                idempotency_key="authority-gate-pass",
            )
        with pytest.raises(
            PhysicalProjectionV4IdempotencyError,
            match="another request",
        ):
            store.append_derived_health_cutoff(
                physical_scope_manifest_id=prepared.scope.physical_scope_manifest_id,
                knowledge_cutoff_ts=HEALTH_KNOWLEDGE + timedelta(microseconds=1),
                idempotency_key="derived-health-healthy",
            )
        assert receipt_count(store) == after_gate
        assert store.verify().physical_evidence_gate_count == 1


def test_gate_rolls_back_when_receipt_clock_falls_behind_evaluation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "gate-clock-regression.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(database, clock=clock) as store:
        prepared = prepare_gate_inputs(store, clock)
        before = receipt_count(store)
        clock.value = GATE_EVALUATED_AT
        append_record = store._append_record  # noqa: SLF001

        def append_with_regressing_receipt(record: object, **values: object) -> object:
            receipt = append_record(record, **values)
            return replace(
                receipt,
                committed_at=GATE_EVALUATED_AT - timedelta(microseconds=1),
            )

        # Transactions now freeze one clock sample, so a second injected wall
        # reading cannot split evaluation from receipt time.  Corrupt the
        # append result itself to retain direct coverage of the defensive
        # receipt/evaluation guard and its all-or-nothing rollback.
        store._append_record = append_with_regressing_receipt  # type: ignore[method-assign]  # noqa: SLF001

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="receipt clock precedes its authority evaluation",
        ):
            store.evaluate_physical_gate(
                information_set_id=prepared.information_set.information_set_id,
                gate_stage=PhysicalGateStage.DECISION_INPUT,
                idempotency_key="regressing-gate-clock",
            )

        assert receipt_count(store) == before
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM physical_evidence_gates"
        ).fetchone() == (0,)


def test_reviewed_scope_requires_registered_exact_role_adapter_policies(
    tmp_path: Path,
) -> None:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    clock = FixedClock(primary.frozen_at)
    with PhysicalProjectionStoreV4(
        tmp_path / "unregistered-adapters.sqlite3", clock=clock
    ) as store:
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="primary adapter policy is not registered",
        ):
            store.append_scope(scope, idempotency_key="scope-without-adapters")
        store.append_adapter_policy(primary, idempotency_key="primary-adapter")
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="required status adapter policy is not registered",
        ):
            store.append_scope(scope, idempotency_key="scope-without-status")
        assert store.verify().scope_count == 0

    research_primary = bar_policy(requires_status=False)
    research_scope = authority_scope(research_primary, required_status)
    with PhysicalProjectionStoreV4(
        tmp_path / "wrong-primary-role.sqlite3",
        clock=FixedClock(research_primary.frozen_at),
    ) as store:
        store.append_adapter_policy(
            research_primary, idempotency_key="research-primary"
        )
        store.append_adapter_policy(required_status, idempotency_key="status")
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="primary adapter policy differs",
        ):
            store.append_scope(research_scope, idempotency_key="reviewed-scope")
        assert store.verify().scope_count == 0

    mismatched_scope = replace(
        scope,
        asset_id="ETH",
        primary_classifier_release_hash=digest("wrong-classifier-release"),
    )
    with PhysicalProjectionStoreV4(
        tmp_path / "wrong-scope-binding.sqlite3",
        clock=FixedClock(primary.frozen_at),
    ) as store:
        store.append_adapter_policy(primary, idempotency_key="primary")
        store.append_adapter_policy(required_status, idempotency_key="status")
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="primary adapter policy differs",
        ):
            store.append_scope(mismatched_scope, idempotency_key="mismatched-scope")
        assert store.verify().scope_count == 0


def test_execution_bar_gate_is_explicitly_non_activating(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "execution-bar-abstain.sqlite3", clock=clock
    ) as store:
        prepared = prepare_gate_inputs(store, clock)
        clock.value = GATE_EVALUATED_AT
        gate = store.evaluate_physical_gate(
            information_set_id=prepared.information_set.information_set_id,
            gate_stage=PhysicalGateStage.EXECUTION_BAR,
            idempotency_key="execution-bar-gate",
        )
        assert gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "EXECUTION_GATE_BRIDGE_NOT_IMPLEMENTED" in (gate.abstention_reason_codes)
        assert store.verify().physical_evidence_gate_count == 1

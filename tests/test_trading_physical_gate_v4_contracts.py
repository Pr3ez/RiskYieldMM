from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
from riskyieldmm.trading.physical_gate_v4 import (
    PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4,
    PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4,
    V4_EXECUTION_BAR_PASS_ENABLED,
    V4_MAX_GATE_HEALTH_LINKS,
    V4_MAX_GATE_PROOF_LINKS,
    V4_PHYSICAL_GATE_POLICY_ID,
    PhysicalEvidenceGateV4,
    gate_health_link_leaf_input_v4,
    gate_health_link_root_v4,
    gate_proof_link_leaf_input_v4,
    gate_proof_link_root_v4,
)
from riskyieldmm.trading.physical_health_v4 import (
    PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
)
from riskyieldmm.trading.physical_market_data import (
    PhysicalGateStage,
    PhysicalGateVerdict,
)
from riskyieldmm.trading.transparency_log import (
    rfc9162_empty_root,
    rfc9162_tree_hash,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def digest(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


def passing_gate(
    *,
    proof_ids: tuple[str, ...] | None = None,
    health_ids: tuple[str, ...] | None = None,
    **overrides: object,
) -> PhysicalEvidenceGateV4:
    proofs = (digest("proof"),) if proof_ids is None else proof_ids
    health = (digest("health"),) if health_ids is None else health_ids
    values: dict[str, object] = {
        "physical_gate_policy_id": V4_PHYSICAL_GATE_POLICY_ID,
        "gate_stage": PhysicalGateStage.DECISION_INPUT,
        "ledger_id": digest("ledger"),
        "information_set_id": digest("information-set"),
        "information_set_record_hash": digest("information-record"),
        "observation_cutoff_ts": T0,
        "evaluation_receipt_sequence": 100,
        "evaluation_receipt_hash": digest("evaluation-receipt"),
        "proof_link_count": len(proofs),
        "proof_link_root": gate_proof_link_root_v4(proofs),
        "health_link_count": len(health),
        "health_link_root": gate_health_link_root_v4(health),
        "verdict": PhysicalGateVerdict.PASS,
        "abstention_reason_codes": (),
        "evaluated_at": T0 + timedelta(seconds=1),
        "valid_until": T0 + timedelta(seconds=30),
    }
    values.update(overrides)
    return PhysicalEvidenceGateV4(**values)


def abstaining_gate() -> PhysicalEvidenceGateV4:
    return PhysicalEvidenceGateV4(
        physical_gate_policy_id=V4_PHYSICAL_GATE_POLICY_ID,
        gate_stage=PhysicalGateStage.DECISION_INPUT,
        ledger_id=digest("ledger"),
        information_set_id=digest("information-set"),
        information_set_record_hash=digest("information-record"),
        observation_cutoff_ts=T0,
        evaluation_receipt_sequence=100,
        evaluation_receipt_hash=digest("evaluation-receipt"),
        proof_link_count=0,
        proof_link_root=rfc9162_empty_root().hex(),
        health_link_count=0,
        health_link_root=rfc9162_empty_root().hex(),
        verdict=PhysicalGateVerdict.ABSTAIN,
        abstention_reason_codes=("PHYSICAL_SELECTION_PROOFS_MISSING",),
        evaluated_at=T0 + timedelta(seconds=1),
        valid_until=T0 + timedelta(seconds=30),
    )


def test_gate_contract_pass_and_abstain_round_trip() -> None:
    passed = passing_gate()
    abstained = abstaining_gate()

    assert passed.verdict is PhysicalGateVerdict.PASS
    assert abstained.verdict is PhysicalGateVerdict.ABSTAIN
    assert passed.as_dict()["schema_version"] == (PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION)
    assert PhysicalEvidenceGateV4.from_mapping(passed.as_dict()) == passed
    assert PhysicalEvidenceGateV4.from_mapping(abstained.as_dict()) == abstained


def test_gate_proof_link_root_is_independent_ordered_rfc9162_commitment() -> None:
    proof_ids = tuple(digest(f"proof-{index}") for index in range(3))
    leaves = tuple(
        canonical_json_bytes(
            {
                "domain": PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4,
                "observation_selection_proof_id": proof_id,
                "ordinal": ordinal,
            }
        )
        for ordinal, proof_id in enumerate(proof_ids)
    )

    assert (
        gate_proof_link_leaf_input_v4(
            ordinal=0, observation_selection_proof_id=proof_ids[0]
        )
        == leaves[0]
    )
    assert gate_proof_link_root_v4(proof_ids) == rfc9162_tree_hash(leaves).hex()
    assert gate_proof_link_root_v4(proof_ids) != gate_proof_link_root_v4(
        proof_ids[::-1]
    )
    assert gate_proof_link_root_v4(()) == rfc9162_empty_root().hex()


def test_gate_health_link_root_is_independent_ordered_rfc9162_commitment() -> None:
    health_ids = tuple(digest(f"health-{index}") for index in range(3))
    leaves = tuple(
        canonical_json_bytes(
            {
                "domain": PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4,
                "ordinal": ordinal,
                "physical_health_transition_id": transition_id,
            }
        )
        for ordinal, transition_id in enumerate(health_ids)
    )

    assert (
        gate_health_link_leaf_input_v4(
            ordinal=0, physical_health_transition_id=health_ids[0]
        )
        == leaves[0]
    )
    assert gate_health_link_root_v4(health_ids) == rfc9162_tree_hash(leaves).hex()
    assert gate_health_link_root_v4(health_ids) != gate_health_link_root_v4(
        health_ids[::-1]
    )
    assert gate_health_link_root_v4(()) == rfc9162_empty_root().hex()


@pytest.mark.parametrize(
    ("root_function", "maximum", "prefix"),
    [
        (gate_proof_link_root_v4, V4_MAX_GATE_PROOF_LINKS, "proof"),
        (gate_health_link_root_v4, V4_MAX_GATE_HEALTH_LINKS, "health"),
    ],
)
def test_gate_link_zero_one_4096_4097_duplicate_boundaries(
    root_function: object, maximum: int, prefix: str
) -> None:
    assert callable(root_function)
    links = tuple(digest(f"{prefix}-{index}") for index in range(maximum + 1))

    assert root_function(()) == rfc9162_empty_root().hex()
    assert root_function(links[:1]) != rfc9162_empty_root().hex()
    assert root_function(links[:maximum]) != rfc9162_empty_root().hex()
    with pytest.raises(CanonicalizationError, match="exceeds 4096"):
        root_function(links)
    with pytest.raises(CanonicalizationError, match="duplicate"):
        root_function((links[0], links[0]))


def test_gate_reordering_changes_roots_and_identity() -> None:
    proof_ids = tuple(digest(f"proof-{index}") for index in range(3))
    health_ids = tuple(digest(f"health-{index}") for index in range(2))
    original = passing_gate(proof_ids=proof_ids, health_ids=health_ids)
    reordered_proofs = passing_gate(proof_ids=proof_ids[::-1], health_ids=health_ids)
    reordered_health = passing_gate(proof_ids=proof_ids, health_ids=health_ids[::-1])

    assert original.proof_link_root != reordered_proofs.proof_link_root
    assert original.health_link_root != reordered_health.health_link_root
    assert original.physical_evidence_gate_id != (
        reordered_proofs.physical_evidence_gate_id
    )
    assert original.physical_evidence_gate_id != (
        reordered_health.physical_evidence_gate_id
    )


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"physical_gate_policy_id": hashlib.sha256(b"other").hexdigest()}, "policy"),
        ({"proof_link_count": 0}, "proof link count"),
        ({"health_link_count": 0}, "health link count"),
        (
            {
                "proof_link_count": 0,
                "proof_link_root": rfc9162_empty_root().hex(),
            },
            "requires proof and health links",
        ),
        ({"abstention_reason_codes": ("FORGED_REASON",)}, "cannot have reasons"),
        ({"evaluated_at": T0 - timedelta(microseconds=1)}, "evaluated before"),
        ({"valid_until": T0 + timedelta(seconds=1)}, "must follow"),
    ],
)
def test_pass_gate_shape_cutoff_and_policy_attacks_fail_closed(
    overrides: dict[str, object], match: str
) -> None:
    with pytest.raises(CanonicalizationError, match=match):
        passing_gate(**overrides)


def test_abstain_gate_requires_reasons_and_consistent_empty_roots() -> None:
    abstained = abstaining_gate()

    with pytest.raises(CanonicalizationError, match="requires reasons"):
        replace(abstained, abstention_reason_codes=())
    with pytest.raises(CanonicalizationError, match="proof link count"):
        replace(abstained, proof_link_root=digest("forged-root"))
    with pytest.raises(CanonicalizationError, match="health link count"):
        replace(abstained, health_link_root=digest("forged-root"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("information_set_record_hash", hashlib.sha256(b"tampered-info").hexdigest()),
        ("evaluation_receipt_hash", hashlib.sha256(b"tampered-receipt").hexdigest()),
        ("proof_link_root", hashlib.sha256(b"tampered-proof-root").hexdigest()),
        ("health_link_root", hashlib.sha256(b"tampered-health-root").hexdigest()),
        ("physical_evidence_gate_id", hashlib.sha256(b"tampered-gate").hexdigest()),
    ],
)
def test_serialized_gate_tampering_is_rejected(field: str, value: object) -> None:
    payload = passing_gate().as_dict()
    payload[field] = value

    with pytest.raises(CanonicalizationError):
        PhysicalEvidenceGateV4.from_mapping(payload)


def test_gate_identity_binds_stage_information_cutoff_receipt_and_validity() -> None:
    original = passing_gate()
    execution_abstention = replace(
        abstaining_gate(),
        gate_stage=PhysicalGateStage.EXECUTION_BAR,
        abstention_reason_codes=("EXECUTION_GATE_BRIDGE_NOT_IMPLEMENTED",),
    )
    substitutions = (
        execution_abstention,
        replace(original, information_set_id=digest("other-information")),
        replace(original, information_set_record_hash=digest("other-record")),
        replace(
            original,
            observation_cutoff_ts=original.observation_cutoff_ts
            + timedelta(microseconds=1),
        ),
        replace(original, evaluation_receipt_sequence=101),
        replace(original, evaluation_receipt_hash=digest("other-receipt")),
        replace(original, valid_until=original.valid_until + timedelta(seconds=1)),
    )

    assert all(
        item.physical_evidence_gate_id != original.physical_evidence_gate_id
        for item in substitutions
    )


def test_execution_bar_cannot_claim_pass_before_atomic_intent_bridge() -> None:
    assert not V4_EXECUTION_BAR_PASS_ENABLED
    with pytest.raises(CanonicalizationError, match="atomic order-intent bridge"):
        passing_gate(gate_stage=PhysicalGateStage.EXECUTION_BAR)

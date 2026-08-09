"""Constant-size V4.3 physical trading-gate contracts.

The gate commits ordered proof and health-transition links without embedding
their cumulative lists.  This module intentionally exposes no PASS builder:
only the projection evaluator may derive a verdict from registered records.
Constructing a PASS-shaped value is representation, not trading authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_json_bytes,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .physical_evidence_v4 import V4_MAX_REASON_CODES
from .physical_health_v4 import PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION
from .physical_market_data import PhysicalGateStage, PhysicalGateVerdict
from .transparency_log import rfc9162_empty_root, rfc9162_tree_hash

PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4 = "RiskYieldMMPhysicalGateProofLinkLeafV4_3"
PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4 = "RiskYieldMMPhysicalGateHealthLinkLeafV4_3"
V4_MAX_GATE_PROOF_LINKS = 4096
V4_MAX_GATE_HEALTH_LINKS = 4096
V4_EXECUTION_BAR_PASS_ENABLED = False


def _gate_policy_payload() -> dict[str, Any]:
    return {
        "authority_schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        "domain": "RiskYieldMMPhysicalGatePolicyV4_3",
        "health_link_leaf_domain": PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4,
        "health_link_maximum": V4_MAX_GATE_HEALTH_LINKS,
        "proof_link_leaf_domain": PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4,
        "proof_link_maximum": V4_MAX_GATE_PROOF_LINKS,
        "requires_current_health": True,
        "requires_bound_subscription_ack": True,
        "requires_exact_information_set_record": True,
        "requires_v4_selection_proofs": True,
        "execution_bar_pass_enabled": V4_EXECUTION_BAR_PASS_ENABLED,
        "supported_gate_stages": [item.value for item in PhysicalGateStage],
    }


V4_PHYSICAL_GATE_POLICY_ID = sha256_digest(_gate_policy_payload())


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        }
    )


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION:
        raise CanonicalizationError(
            "unsupported physical-authority V4.3 schema_version"
        )


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _gate_stage(value: Any) -> PhysicalGateStage:
    try:
        return (
            value if isinstance(value, PhysicalGateStage) else PhysicalGateStage(value)
        )
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in PhysicalGateStage)
        raise CanonicalizationError(f"gate_stage must be one of: {choices}") from exc


def _gate_verdict(value: Any) -> PhysicalGateVerdict:
    try:
        return (
            value
            if isinstance(value, PhysicalGateVerdict)
            else PhysicalGateVerdict(value)
        )
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in PhysicalGateVerdict)
        raise CanonicalizationError(f"verdict must be one of: {choices}") from exc


def _ordered_link_ids(
    values: Sequence[Any], *, field: str, maximum: int
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    checked = tuple(canonical_hash(value, field=field) for value in values)
    if len(set(checked)) != len(checked):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return checked


def gate_proof_link_leaf_input_v4(
    *, ordinal: int, observation_selection_proof_id: str
) -> bytes:
    """Return one ordered V4 selection-proof link leaf input."""

    checked_ordinal = canonical_safe_int(
        ordinal,
        field="ordinal",
        minimum=0,
        maximum=V4_MAX_GATE_PROOF_LINKS - 1,
    )
    proof_id = canonical_hash(
        observation_selection_proof_id,
        field="observation_selection_proof_id",
    )
    return canonical_json_bytes(
        {
            "domain": PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4,
            "observation_selection_proof_id": proof_id,
            "ordinal": checked_ordinal,
        }
    )


def gate_proof_link_root_v4(
    ordered_observation_selection_proof_ids: Sequence[str],
) -> str:
    """Commit the ordered V4 selection-proof links."""

    checked = _ordered_link_ids(
        ordered_observation_selection_proof_ids,
        field="ordered_observation_selection_proof_ids",
        maximum=V4_MAX_GATE_PROOF_LINKS,
    )
    return rfc9162_tree_hash(
        tuple(
            gate_proof_link_leaf_input_v4(
                ordinal=ordinal, observation_selection_proof_id=proof_id
            )
            for ordinal, proof_id in enumerate(checked)
        )
    ).hex()


def gate_health_link_leaf_input_v4(
    *, ordinal: int, physical_health_transition_id: str
) -> bytes:
    """Return one ordered V4 physical-health link leaf input."""

    checked_ordinal = canonical_safe_int(
        ordinal,
        field="ordinal",
        minimum=0,
        maximum=V4_MAX_GATE_HEALTH_LINKS - 1,
    )
    transition_id = canonical_hash(
        physical_health_transition_id,
        field="physical_health_transition_id",
    )
    return canonical_json_bytes(
        {
            "domain": PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4,
            "ordinal": checked_ordinal,
            "physical_health_transition_id": transition_id,
        }
    )


def gate_health_link_root_v4(
    ordered_physical_health_transition_ids: Sequence[str],
) -> str:
    """Commit the ordered V4 physical-health transition links."""

    checked = _ordered_link_ids(
        ordered_physical_health_transition_ids,
        field="ordered_physical_health_transition_ids",
        maximum=V4_MAX_GATE_HEALTH_LINKS,
    )
    return rfc9162_tree_hash(
        tuple(
            gate_health_link_leaf_input_v4(
                ordinal=ordinal, physical_health_transition_id=transition_id
            )
            for ordinal, transition_id in enumerate(checked)
        )
    ).hex()


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalEvidenceGateV4:
    """A constant-size derived verdict over exact proof and health link roots."""

    physical_gate_policy_id: str
    gate_stage: PhysicalGateStage
    ledger_id: str
    information_set_id: str
    information_set_record_hash: str
    observation_cutoff_ts: datetime
    evaluation_receipt_sequence: int
    evaluation_receipt_hash: str
    proof_link_count: int
    proof_link_root: str
    health_link_count: int
    health_link_root: str
    verdict: PhysicalGateVerdict
    abstention_reason_codes: tuple[str, ...]
    evaluated_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "physical_gate_policy_id",
            "ledger_id",
            "information_set_id",
            "information_set_record_hash",
            "evaluation_receipt_hash",
            "proof_link_root",
            "health_link_root",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.physical_gate_policy_id != V4_PHYSICAL_GATE_POLICY_ID:
            raise CanonicalizationError("gate uses an unreviewed V4.3 gate policy")
        object.__setattr__(self, "gate_stage", _gate_stage(self.gate_stage))
        object.__setattr__(self, "verdict", _gate_verdict(self.verdict))
        object.__setattr__(
            self,
            "evaluation_receipt_sequence",
            canonical_safe_int(
                self.evaluation_receipt_sequence,
                field="evaluation_receipt_sequence",
                minimum=1,
            ),
        )
        proof_count = canonical_safe_int(
            self.proof_link_count,
            field="proof_link_count",
            minimum=0,
            maximum=V4_MAX_GATE_PROOF_LINKS,
        )
        health_count = canonical_safe_int(
            self.health_link_count,
            field="health_link_count",
            minimum=0,
            maximum=V4_MAX_GATE_HEALTH_LINKS,
        )
        object.__setattr__(self, "proof_link_count", proof_count)
        object.__setattr__(self, "health_link_count", health_count)
        empty_root = rfc9162_empty_root().hex()
        if (proof_count == 0) != (self.proof_link_root == empty_root):
            raise CanonicalizationError("proof link count and RFC9162 root disagree")
        if (health_count == 0) != (self.health_link_root == empty_root):
            raise CanonicalizationError("health link count and RFC9162 root disagree")
        reasons = canonical_reason_codes(
            self.abstention_reason_codes, field="abstention_reason_codes"
        )
        if len(reasons) > V4_MAX_REASON_CODES:
            raise CanonicalizationError(
                f"abstention_reason_codes exceeds {V4_MAX_REASON_CODES} values"
            )
        if self.verdict is PhysicalGateVerdict.PASS:
            if (
                self.gate_stage is PhysicalGateStage.EXECUTION_BAR
                and not V4_EXECUTION_BAR_PASS_ENABLED
            ):
                raise CanonicalizationError(
                    "EXECUTION_BAR PASS requires the atomic order-intent bridge"
                )
            if reasons:
                raise CanonicalizationError("PASS physical gate cannot have reasons")
            if proof_count == 0 or health_count == 0:
                raise CanonicalizationError(
                    "PASS physical gate requires proof and health links"
                )
        elif not reasons:
            raise CanonicalizationError("ABSTAIN physical gate requires reasons")
        object.__setattr__(self, "abstention_reason_codes", reasons)
        observation_cutoff = utc_datetime(
            self.observation_cutoff_ts, field="observation_cutoff_ts"
        )
        evaluated = utc_datetime(self.evaluated_at, field="evaluated_at")
        valid_until = utc_datetime(self.valid_until, field="valid_until")
        if evaluated < observation_cutoff:
            raise CanonicalizationError(
                "physical gate evaluated before observation cutoff"
            )
        if valid_until <= evaluated:
            raise CanonicalizationError(
                "physical gate valid_until must follow evaluation"
            )
        object.__setattr__(self, "observation_cutoff_ts", observation_cutoff)
        object.__setattr__(self, "evaluated_at", evaluated)
        object.__setattr__(self, "valid_until", valid_until)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "abstention_reason_codes": list(self.abstention_reason_codes),
            "evaluated_at": utc_iso(self.evaluated_at),
            "evaluation_receipt_hash": self.evaluation_receipt_hash,
            "evaluation_receipt_sequence": self.evaluation_receipt_sequence,
            "gate_stage": self.gate_stage.value,
            "health_link_count": self.health_link_count,
            "health_link_root": self.health_link_root,
            "information_set_id": self.information_set_id,
            "information_set_record_hash": self.information_set_record_hash,
            "ledger_id": self.ledger_id,
            "observation_cutoff_ts": utc_iso(self.observation_cutoff_ts),
            "physical_gate_policy_id": self.physical_gate_policy_id,
            "proof_link_count": self.proof_link_count,
            "proof_link_root": self.proof_link_root,
            "valid_until": utc_iso(self.valid_until),
            "verdict": self.verdict.value,
        }

    @property
    def physical_evidence_gate_id(self) -> str:
        return _identity("PhysicalEvidenceGateV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_evidence_gate_id": self.physical_evidence_gate_id,
            "schema_version": PHYSICAL_AUTHORITY_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalEvidenceGateV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_evidence_gate_id",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="PhysicalEvidenceGateV4")
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["physical_evidence_gate_id"],
            item.physical_evidence_gate_id,
            field="physical_evidence_gate_id",
        )
        return item


__all__ = [
    "PHYSICAL_GATE_HEALTH_LINK_LEAF_DOMAIN_V4",
    "PHYSICAL_GATE_PROOF_LINK_LEAF_DOMAIN_V4",
    "PhysicalEvidenceGateV4",
    "V4_EXECUTION_BAR_PASS_ENABLED",
    "V4_MAX_GATE_HEALTH_LINKS",
    "V4_MAX_GATE_PROOF_LINKS",
    "V4_PHYSICAL_GATE_POLICY_ID",
    "gate_health_link_leaf_input_v4",
    "gate_health_link_root_v4",
    "gate_proof_link_leaf_input_v4",
    "gate_proof_link_root_v4",
]

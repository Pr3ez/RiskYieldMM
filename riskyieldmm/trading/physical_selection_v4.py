"""Bounded, causal V4 physical-observation selection contracts.

The contracts in this module bind one selector invocation to an exact physical
scope, ledger cutoff, protocol/feature configuration, dependency slot, and
source member.  They deliberately do not authorize trading or restate feed
health: those checks belong to the later V4 physical gate.

V4.1 permits one non-empty result chunk containing at most 256 ordered
observation-revision identifiers.  Its result root is an RFC 9162 tree over
application leaves that bind the zero-based result ordinal and the raw
revision identifier.  This commitment authenticates the returned ordering;
it is not an authenticated SQL range proof.
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
    canonical_identifier,
    canonical_json_bytes,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .evidence import DependencySelectionMode
from .physical_evidence_v4 import (
    PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
    PHYSICAL_RESULT_LEAF_DOMAIN_V4,
    V4_MAX_REASON_CODES,
    V4_MAX_SELECTION_RESULTS,
    V4_SELECTION_QUERY_SPEC_ID,
)
from .physical_market_data import ContinuityPolicy, SelectionStatus
from .transparency_log import rfc9162_empty_root, rfc9162_tree_hash

V4_SELECTION_INTERVAL_SECONDS = 60
V4_SELECTION_TIE_BREAK_POLICY = "BAR_CLOSE_AVAILABLE_RECEIPT_REVISION_ID"
V4_TRAILING_SELECTION_MODE = "TRAILING_WINDOW"
V4_SELECTION_RESULT_CHUNK_ORDINAL = 0

_SUPPORTED_SELECTION_MODES = frozenset(
    {
        DependencySelectionMode.EXACT_EVENT,
        DependencySelectionMode.LATEST_AVAILABLE_ASOF,
        DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
    }
)


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }
    )


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported physical-evidence V4 schema_version")


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _selection_mode(value: Any, *, persisted: bool = False) -> DependencySelectionMode:
    if value == V4_TRAILING_SELECTION_MODE:
        return DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS
    try:
        mode = (
            value
            if isinstance(value, DependencySelectionMode)
            else DependencySelectionMode(value)
        )
    except (TypeError, ValueError) as exc:
        raise CanonicalizationError(
            "selection_mode must be EXACT_EVENT, LATEST_AVAILABLE_ASOF, "
            "or TRAILING_WINDOW"
        ) from exc
    if mode not in _SUPPORTED_SELECTION_MODES:
        raise CanonicalizationError(
            "V4 physical selection supports exact/latest/trailing only"
        )
    if persisted and mode is DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS:
        raise CanonicalizationError(
            "persisted V4 trailing selection_mode must be TRAILING_WINDOW"
        )
    return mode


def selection_mode_name_v4(value: DependencySelectionMode | str) -> str:
    """Return the frozen V4 wire name for a supported V3 selection enum."""

    mode = _selection_mode(value)
    if mode is DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS:
        return V4_TRAILING_SELECTION_MODE
    return mode.value


def _continuity_policy(value: Any) -> ContinuityPolicy:
    try:
        return value if isinstance(value, ContinuityPolicy) else ContinuityPolicy(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in ContinuityPolicy)
        raise CanonicalizationError(
            f"continuity_policy must be one of: {choices}"
        ) from exc


def _selection_status(value: Any) -> SelectionStatus:
    try:
        return value if isinstance(value, SelectionStatus) else SelectionStatus(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in SelectionStatus)
        raise CanonicalizationError(f"status must be one of: {choices}") from exc


def _ordered_revision_ids(values: Sequence[Any]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(
            "ordered_observation_revision_ids must be a sequence"
        )
    if not values:
        raise CanonicalizationError("selection result chunk must not be empty")
    if len(values) > V4_MAX_SELECTION_RESULTS:
        raise CanonicalizationError(
            f"selection result chunk exceeds {V4_MAX_SELECTION_RESULTS} values"
        )
    result = tuple(
        canonical_hash(value, field="observation_revision_id") for value in values
    )
    if len(set(result)) != len(result):
        raise CanonicalizationError(
            "ordered_observation_revision_ids contains duplicate values"
        )
    return result


def selection_result_leaf_input_v4(
    *, ordinal: int, observation_revision_id: str
) -> bytes:
    """Return one frozen application leaf passed to RFC 9162 hashing."""

    checked_ordinal = canonical_safe_int(
        ordinal,
        field="ordinal",
        minimum=0,
        maximum=V4_MAX_SELECTION_RESULTS - 1,
    )
    revision_id = canonical_hash(
        observation_revision_id, field="observation_revision_id"
    )
    return canonical_json_bytes(
        {
            "domain": PHYSICAL_RESULT_LEAF_DOMAIN_V4,
            "observation_revision_id": revision_id,
            "ordinal": checked_ordinal,
        }
    )


def selection_result_root_v4(
    ordered_observation_revision_ids: Sequence[str],
) -> str:
    """Commit an ordered, bounded result; the empty result uses the RFC root."""

    if isinstance(
        ordered_observation_revision_ids, (str, bytes, bytearray)
    ) or not isinstance(ordered_observation_revision_ids, Sequence):
        raise CanonicalizationError(
            "ordered_observation_revision_ids must be a sequence"
        )
    if len(ordered_observation_revision_ids) > V4_MAX_SELECTION_RESULTS:
        raise CanonicalizationError(
            f"selection result exceeds {V4_MAX_SELECTION_RESULTS} values"
        )
    checked = tuple(
        canonical_hash(value, field="observation_revision_id")
        for value in ordered_observation_revision_ids
    )
    if len(set(checked)) != len(checked):
        raise CanonicalizationError("selection result contains duplicate values")
    leaves = tuple(
        selection_result_leaf_input_v4(
            ordinal=ordinal, observation_revision_id=revision_id
        )
        for ordinal, revision_id in enumerate(checked)
    )
    return rfc9162_tree_hash(leaves).hex()


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalProtocolBindingV4:
    """Exact manifest, schema, slot, member, and selector-policy binding."""

    physical_scope_manifest_id: str
    protocol_manifest_id: str
    source_manifest_id: str
    calendar_manifest_id: str
    feature_schema_id: str
    dependency_slot_id: str
    source_member_id: str
    source_member_key: str
    observation_selection_policy_id: str
    selection_mode: DependencySelectionMode
    anchor_lag_intervals: int
    requested_count: int
    maximum_age_seconds: int
    continuity_policy: ContinuityPolicy
    frozen_at: datetime
    selection_query_spec_id: str = V4_SELECTION_QUERY_SPEC_ID
    interval_seconds: int = V4_SELECTION_INTERVAL_SECONDS
    tie_break_policy: str = V4_SELECTION_TIE_BREAK_POLICY

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "protocol_manifest_id",
            "source_manifest_id",
            "calendar_manifest_id",
            "feature_schema_id",
            "dependency_slot_id",
            "source_member_id",
            "source_member_key",
            "observation_selection_policy_id",
            "selection_query_spec_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.selection_query_spec_id != V4_SELECTION_QUERY_SPEC_ID:
            raise CanonicalizationError(
                "protocol binding uses an unsupported V4 selection query"
            )
        mode = _selection_mode(self.selection_mode)
        object.__setattr__(self, "selection_mode", mode)
        object.__setattr__(
            self,
            "anchor_lag_intervals",
            canonical_safe_int(
                self.anchor_lag_intervals,
                field="anchor_lag_intervals",
                minimum=0,
                maximum=10_000,
            ),
        )
        count = canonical_safe_int(
            self.requested_count,
            field="requested_count",
            minimum=1,
            maximum=V4_MAX_SELECTION_RESULTS,
        )
        object.__setattr__(self, "requested_count", count)
        object.__setattr__(
            self,
            "maximum_age_seconds",
            canonical_safe_int(
                self.maximum_age_seconds,
                field="maximum_age_seconds",
                minimum=0,
                maximum=315_576_000,
            ),
        )
        continuity = _continuity_policy(self.continuity_policy)
        object.__setattr__(self, "continuity_policy", continuity)
        interval = canonical_safe_int(
            self.interval_seconds,
            field="interval_seconds",
            minimum=V4_SELECTION_INTERVAL_SECONDS,
            maximum=V4_SELECTION_INTERVAL_SECONDS,
        )
        object.__setattr__(self, "interval_seconds", interval)
        tie_break = canonical_identifier(
            self.tie_break_policy, field="tie_break_policy"
        )
        if tie_break != V4_SELECTION_TIE_BREAK_POLICY:
            raise CanonicalizationError(
                "protocol binding uses an unsupported V4 tie-break policy"
            )
        object.__setattr__(self, "tie_break_policy", tie_break)
        if (
            mode
            in {
                DependencySelectionMode.EXACT_EVENT,
                DependencySelectionMode.LATEST_AVAILABLE_ASOF,
            }
            and count != 1
        ):
            raise CanonicalizationError("exact/latest V4 selection requires one row")
        if (
            mode is DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS
            and continuity is not ContinuityPolicy.STRICT_INTERVAL_GRID
        ):
            raise CanonicalizationError(
                "trailing V4 selection requires STRICT_INTERVAL_GRID"
            )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "anchor_lag_intervals": self.anchor_lag_intervals,
            "calendar_manifest_id": self.calendar_manifest_id,
            "continuity_policy": self.continuity_policy.value,
            "dependency_slot_id": self.dependency_slot_id,
            "feature_schema_id": self.feature_schema_id,
            "frozen_at": utc_iso(self.frozen_at),
            "interval_seconds": self.interval_seconds,
            "maximum_age_seconds": self.maximum_age_seconds,
            "observation_selection_policy_id": (self.observation_selection_policy_id),
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "protocol_manifest_id": self.protocol_manifest_id,
            "requested_count": self.requested_count,
            "selection_mode": selection_mode_name_v4(self.selection_mode),
            "selection_query_spec_id": self.selection_query_spec_id,
            "source_manifest_id": self.source_manifest_id,
            "source_member_id": self.source_member_id,
            "source_member_key": self.source_member_key,
            "tie_break_policy": self.tie_break_policy,
        }

    @property
    def physical_protocol_binding_id(self) -> str:
        return _identity("PhysicalProtocolBindingV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "physical_protocol_binding_id": self.physical_protocol_binding_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> PhysicalProtocolBindingV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "physical_protocol_binding_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="PhysicalProtocolBindingV4"
        )
        _require_versions(payload)
        _selection_mode(payload["selection_mode"], persisted=True)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["physical_protocol_binding_id"],
            item.physical_protocol_binding_id,
            field="physical_protocol_binding_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class SelectionResultChunkV4:
    """The sole non-empty, ordered V4.1 selection-result chunk."""

    physical_scope_manifest_id: str
    physical_protocol_binding_id: str
    evidence_cutoff_id: str
    ordered_observation_revision_ids: tuple[str, ...]
    chunk_ordinal: int = V4_SELECTION_RESULT_CHUNK_ORDINAL

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "physical_protocol_binding_id",
            "evidence_cutoff_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "ordered_observation_revision_ids",
            _ordered_revision_ids(self.ordered_observation_revision_ids),
        )
        ordinal = canonical_safe_int(
            self.chunk_ordinal,
            field="chunk_ordinal",
            minimum=V4_SELECTION_RESULT_CHUNK_ORDINAL,
            maximum=V4_SELECTION_RESULT_CHUNK_ORDINAL,
        )
        object.__setattr__(self, "chunk_ordinal", ordinal)

    @property
    def selected_result_count(self) -> int:
        return len(self.ordered_observation_revision_ids)

    @property
    def selected_result_root(self) -> str:
        return selection_result_root_v4(self.ordered_observation_revision_ids)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "chunk_ordinal": self.chunk_ordinal,
            "evidence_cutoff_id": self.evidence_cutoff_id,
            "ordered_observation_revision_ids": list(
                self.ordered_observation_revision_ids
            ),
            "physical_protocol_binding_id": self.physical_protocol_binding_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
        }

    @property
    def selection_result_chunk_id(self) -> str:
        return _identity("SelectionResultChunkV4", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "selected_result_count": self.selected_result_count,
            "selected_result_root": self.selected_result_root,
            "selection_result_chunk_id": self.selection_result_chunk_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SelectionResultChunkV4:
        expected = {
            "canonicalization_version",
            "chunk_ordinal",
            "evidence_cutoff_id",
            "ordered_observation_revision_ids",
            "physical_protocol_binding_id",
            "physical_scope_manifest_id",
            "schema_version",
            "selected_result_count",
            "selected_result_root",
            "selection_result_chunk_id",
        }
        require_exact_keys(payload, expected=expected, context="SelectionResultChunkV4")
        _require_versions(payload)
        item = cls(
            chunk_ordinal=payload["chunk_ordinal"],
            evidence_cutoff_id=payload["evidence_cutoff_id"],
            ordered_observation_revision_ids=payload[
                "ordered_observation_revision_ids"
            ],
            physical_protocol_binding_id=payload["physical_protocol_binding_id"],
            physical_scope_manifest_id=payload["physical_scope_manifest_id"],
        )
        count = canonical_safe_int(
            payload["selected_result_count"],
            field="selected_result_count",
            minimum=1,
            maximum=V4_MAX_SELECTION_RESULTS,
        )
        if count != item.selected_result_count:
            raise CanonicalizationError(
                "selected_result_count does not match chunk content"
            )
        _require_identity(
            payload["selected_result_root"],
            item.selected_result_root,
            field="selected_result_root",
        )
        _require_identity(
            payload["selection_result_chunk_id"],
            item.selection_result_chunk_id,
            field="selection_result_chunk_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ObservationSelectionProofV4:
    """One bounded result committed against an exact causal ledger cutoff."""

    physical_scope_manifest_id: str
    ledger_id: str
    evidence_cutoff_id: str
    cutoff_global_sequence: int
    cutoff_receipt_hash: str
    knowledge_cutoff_ts: datetime
    physical_protocol_binding_id: str
    selection_query_spec_id: str
    observation_selection_policy_id: str
    dependency_slot_id: str
    source_member_id: str
    source_member_key: str
    observation_cutoff_ts: datetime
    status: SelectionStatus
    selected_result_count: int
    selected_result_root: str
    selection_result_chunk_id: str | None
    abstention_reason_codes: tuple[str, ...]
    computed_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "physical_scope_manifest_id",
            "ledger_id",
            "evidence_cutoff_id",
            "cutoff_receipt_hash",
            "physical_protocol_binding_id",
            "selection_query_spec_id",
            "observation_selection_policy_id",
            "dependency_slot_id",
            "source_member_id",
            "source_member_key",
            "selected_result_root",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        if self.selection_query_spec_id != V4_SELECTION_QUERY_SPEC_ID:
            raise CanonicalizationError(
                "selection proof uses an unsupported V4 selection query"
            )
        chunk_id = (
            None
            if self.selection_result_chunk_id is None
            else canonical_hash(
                self.selection_result_chunk_id,
                field="selection_result_chunk_id",
            )
        )
        object.__setattr__(self, "selection_result_chunk_id", chunk_id)
        object.__setattr__(
            self,
            "cutoff_global_sequence",
            canonical_safe_int(
                self.cutoff_global_sequence,
                field="cutoff_global_sequence",
                minimum=1,
            ),
        )
        count = canonical_safe_int(
            self.selected_result_count,
            field="selected_result_count",
            minimum=0,
            maximum=V4_MAX_SELECTION_RESULTS,
        )
        object.__setattr__(self, "selected_result_count", count)
        status = _selection_status(self.status)
        object.__setattr__(self, "status", status)
        reasons = canonical_reason_codes(
            self.abstention_reason_codes, field="abstention_reason_codes"
        )
        if len(reasons) > V4_MAX_REASON_CODES:
            raise CanonicalizationError(
                f"abstention_reason_codes exceeds {V4_MAX_REASON_CODES} values"
            )
        object.__setattr__(self, "abstention_reason_codes", reasons)
        empty_root = rfc9162_empty_root().hex()
        if status is SelectionStatus.SELECTED:
            if count == 0 or chunk_id is None or reasons:
                raise CanonicalizationError(
                    "SELECTED proof requires a non-empty chunk and no reasons"
                )
            if self.selected_result_root == empty_root:
                raise CanonicalizationError(
                    "SELECTED proof cannot use the RFC9162 empty root"
                )
        elif (
            count != 0
            or chunk_id is not None
            or self.selected_result_root != empty_root
            or not reasons
        ):
            raise CanonicalizationError(
                "ABSTAIN proof requires zero count, no chunk, empty root, and reasons"
            )
        knowledge_cutoff = utc_datetime(
            self.knowledge_cutoff_ts, field="knowledge_cutoff_ts"
        )
        observation_cutoff = utc_datetime(
            self.observation_cutoff_ts, field="observation_cutoff_ts"
        )
        computed = utc_datetime(self.computed_at, field="computed_at")
        if observation_cutoff != knowledge_cutoff:
            raise CanonicalizationError(
                "V4.1 selection requires an exact knowledge/observation cutoff"
            )
        if computed < knowledge_cutoff:
            raise CanonicalizationError(
                "selection proof computed before its knowledge cutoff"
            )
        object.__setattr__(self, "knowledge_cutoff_ts", knowledge_cutoff)
        object.__setattr__(self, "observation_cutoff_ts", observation_cutoff)
        object.__setattr__(self, "computed_at", computed)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "abstention_reason_codes": list(self.abstention_reason_codes),
            "computed_at": utc_iso(self.computed_at),
            "cutoff_global_sequence": self.cutoff_global_sequence,
            "cutoff_receipt_hash": self.cutoff_receipt_hash,
            "dependency_slot_id": self.dependency_slot_id,
            "evidence_cutoff_id": self.evidence_cutoff_id,
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "ledger_id": self.ledger_id,
            "observation_cutoff_ts": utc_iso(self.observation_cutoff_ts),
            "observation_selection_policy_id": (self.observation_selection_policy_id),
            "physical_protocol_binding_id": self.physical_protocol_binding_id,
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "selected_result_count": self.selected_result_count,
            "selected_result_root": self.selected_result_root,
            "selection_query_spec_id": self.selection_query_spec_id,
            "selection_result_chunk_id": self.selection_result_chunk_id,
            "source_member_id": self.source_member_id,
            "source_member_key": self.source_member_key,
            "status": self.status.value,
        }

    @property
    def observation_selection_proof_id(self) -> str:
        return _identity("ObservationSelectionProofV4", self.identity_payload())

    @property
    def dependency_selection_proof_id(self) -> str:
        """Compatibility spelling for consumers of the V3 contract name."""

        return self.observation_selection_proof_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "observation_selection_proof_id": self.observation_selection_proof_id,
            "schema_version": PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ObservationSelectionProofV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "observation_selection_proof_id",
            "schema_version",
        }
        require_exact_keys(
            payload, expected=expected, context="ObservationSelectionProofV4"
        )
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        _require_identity(
            payload["observation_selection_proof_id"],
            item.observation_selection_proof_id,
            field="observation_selection_proof_id",
        )
        return item


def validate_observation_selection_proof_v4(
    *,
    proof: ObservationSelectionProofV4,
    binding: PhysicalProtocolBindingV4,
    chunk: SelectionResultChunkV4 | None,
) -> None:
    """Validate all repeated policy fields and the optional result commitment."""

    if proof.physical_protocol_binding_id != binding.physical_protocol_binding_id:
        raise CanonicalizationError("selection proof differs from protocol binding")
    repeated = {
        "physical_scope_manifest_id": binding.physical_scope_manifest_id,
        "selection_query_spec_id": binding.selection_query_spec_id,
        "observation_selection_policy_id": binding.observation_selection_policy_id,
        "dependency_slot_id": binding.dependency_slot_id,
        "source_member_id": binding.source_member_id,
        "source_member_key": binding.source_member_key,
    }
    for field_name, expected in repeated.items():
        if getattr(proof, field_name) != expected:
            raise CanonicalizationError(
                f"selection proof {field_name} differs from protocol binding"
            )
    if proof.status is SelectionStatus.ABSTAIN:
        if chunk is not None:
            raise CanonicalizationError(
                "ABSTAIN selection proof cannot resolve a chunk"
            )
        return
    if chunk is None:
        raise CanonicalizationError("SELECTED selection proof requires its chunk")
    if proof.selection_result_chunk_id != chunk.selection_result_chunk_id:
        raise CanonicalizationError("selection proof resolves a different result chunk")
    if proof.selected_result_count != chunk.selected_result_count:
        raise CanonicalizationError("selection proof result count differs from chunk")
    if proof.selected_result_root != chunk.selected_result_root:
        raise CanonicalizationError("selection proof result root differs from chunk")
    if (
        chunk.physical_scope_manifest_id != proof.physical_scope_manifest_id
        or chunk.physical_protocol_binding_id != proof.physical_protocol_binding_id
        or chunk.evidence_cutoff_id != proof.evidence_cutoff_id
    ):
        raise CanonicalizationError("selection result chunk changes proof context")
    if proof.selected_result_count != binding.requested_count:
        raise CanonicalizationError(
            "selected result count differs from bound requested_count"
        )


# V3 called the equivalent record a dependency-selection proof.  Keep an alias
# while using the more precise V4 canonical class and identity domain.
DependencySelectionProofV4 = ObservationSelectionProofV4


__all__ = [
    "DependencySelectionProofV4",
    "ObservationSelectionProofV4",
    "PhysicalProtocolBindingV4",
    "SelectionResultChunkV4",
    "V4_SELECTION_INTERVAL_SECONDS",
    "V4_SELECTION_RESULT_CHUNK_ORDINAL",
    "V4_SELECTION_TIE_BREAK_POLICY",
    "V4_TRAILING_SELECTION_MODE",
    "selection_mode_name_v4",
    "selection_result_leaf_input_v4",
    "selection_result_root_v4",
    "validate_observation_selection_proof_v4",
]

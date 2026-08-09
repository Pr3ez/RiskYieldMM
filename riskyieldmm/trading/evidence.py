"""Content-addressed source bundles and causal feature-schema contracts.

The contracts in this module describe *which* evidence a feature is allowed to
consume.  They deliberately remain independent from storage formats and model
libraries: logical identity must survive an Arrow/Parquet migration and must be
validatable before any feature values are materialized.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)

EVIDENCE_SCHEMA_VERSION = "riskyieldmm_evidence_contract_v1"
MAX_SOURCE_FIELDS = 4096
MAX_SOURCE_MEMBERS = 4096
MAX_DEPENDENCY_SLOTS = 4096
MAX_SCHEMA_FEATURES = 8192
MAX_SLOT_CARDINALITY = 1_000_000
MAX_AGE_SECONDS = 315_576_000


class SourceRole(str, Enum):
    """The causal role of one physical/logical source in a bundle."""

    DECISION_INPUT = "DECISION_INPUT"
    CALENDAR = "CALENDAR"
    UNIVERSE = "UNIVERSE"
    PATH_EVIDENCE = "PATH_EVIDENCE"
    LABEL = "LABEL"
    OUTCOME = "OUTCOME"


class EvidenceKind(str, Enum):
    """The variant of evidence selected by a dependency slot."""

    OBSERVATION = "OBSERVATION"
    STATE_CHECKPOINT = "STATE_CHECKPOINT"
    PROTOCOL_CONSTANT = "PROTOCOL_CONSTANT"


class DependencySelectionMode(str, Enum):
    """Leakage-aware selection semantics for a dependency slot."""

    EXACT_EVENT = "EXACT_EVENT"
    LATEST_AVAILABLE_ASOF = "LATEST_AVAILABLE_ASOF"
    TRAILING_COMPLETED_OBSERVATIONS = "TRAILING_COMPLETED_OBSERVATIONS"
    PRIOR_STATE_CHECKPOINT = "PRIOR_STATE_CHECKPOINT"
    PROTOCOL_CONSTANT = "PROTOCOL_CONSTANT"


class MissingInputPolicy(str, Enum):
    """Closed-world behavior when a declared slot cannot be satisfied."""

    FAIL = "FAIL"
    ABSTAIN = "ABSTAIN"
    NULL_WITH_INDICATOR = "NULL_WITH_INDICATOR"


class CardinalityScope(str, Enum):
    """Whether observation cardinality applies globally or to every member."""

    TOTAL = "TOTAL"
    PER_SOURCE_MEMBER = "PER_SOURCE_MEMBER"


class FeatureRole(str, Enum):
    """Permitted uses of a materialized feature."""

    MODEL_INPUT = "MODEL_INPUT"
    DIAGNOSTIC = "DIAGNOSTIC"
    MISSINGNESS_INDICATOR = "MISSINGNESS_INDICATOR"


# Candidate-conditioned features may use only immutable economic fields from
# ``PrimarySignalCandidateV3``.  Keeping the allowlist here makes the declared
# dependency content-addressed without allowing record IDs, availability
# clocks, or certification metadata to become accidental model inputs.
CANDIDATE_FEATURE_FIELD_ALLOWLIST = frozenset(
    {
        "earliest_entry_ts",
        "earliest_order_submission_ts",
        "entry_expiry_ts",
        "entry_reference",
        "entry_scenario",
        "estimated_roundtrip_cost_bps",
        "max_holding_seconds",
        "risk_unit",
        "side",
        "stop_r_multiple",
        "target_r_multiple",
    }
)


_VINTAGE_CLASSES = frozenset(
    {
        "LIVE_FIRST_SEEN_CERTIFIED",
        "HISTORICAL_AS_WAS_CERTIFIED",
        "NOMINAL_CURRENT_REVISION",
    }
)


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        }
    )


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _optional_identifier(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_identifier(value, field=field)


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _tuple_of_identifiers(
    values: Sequence[Any],
    *,
    field: str,
    maximum: int,
    allow_empty: bool,
    sort: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    result = tuple(canonical_identifier(value, field=field) for value in values)
    if not allow_empty and not result:
        raise CanonicalizationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return tuple(sorted(result)) if sort else result


def _tuple_of_hashes(
    values: Sequence[Any],
    *,
    field: str,
    maximum: int,
    allow_empty: bool,
    sort: bool = False,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if len(values) > maximum:
        raise CanonicalizationError(f"{field} exceeds {maximum} values")
    result = tuple(canonical_hash(value, field=field) for value in values)
    if not allow_empty and not result:
        raise CanonicalizationError(f"{field} must not be empty")
    if len(set(result)) != len(result):
        raise CanonicalizationError(f"{field} contains duplicate values")
    return tuple(sorted(result)) if sort else result


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != EVIDENCE_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported evidence schema_version")


def _require_digest(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceBundleMemberV3:
    """One exact, content-addressed source slice in a source bundle."""

    source_id: str
    source_role: SourceRole
    asset_id: str | None = None
    venue_id: str | None = None
    contract_id: str | None = None
    timeframe_id: str | None = None
    source_schema_id: str
    source_field_ids: tuple[str, ...]
    availability_policy_id: str
    revision_policy_id: str
    calendar_manifest_id: str
    semantic_content_root: str
    artifact_hash: str
    row_count: int
    event_start_ts: datetime | None
    event_end_ts: datetime | None
    knowledge_cutoff_ts: datetime
    parent_source_member_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_id", canonical_identifier(self.source_id, field="source_id")
        )
        object.__setattr__(
            self,
            "source_role",
            _enum(self.source_role, SourceRole, field="source_role"),
        )
        for field_name in ("asset_id", "venue_id", "contract_id", "timeframe_id"):
            object.__setattr__(
                self,
                field_name,
                _optional_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_schema_id",
            "availability_policy_id",
            "revision_policy_id",
            "calendar_manifest_id",
            "semantic_content_root",
            "artifact_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "source_field_ids",
            _tuple_of_identifiers(
                self.source_field_ids,
                field="source_field_ids",
                maximum=MAX_SOURCE_FIELDS,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self,
            "row_count",
            canonical_safe_int(self.row_count, field="row_count", minimum=0),
        )
        start = (
            None
            if self.event_start_ts is None
            else utc_datetime(self.event_start_ts, field="event_start_ts")
        )
        end = (
            None
            if self.event_end_ts is None
            else utc_datetime(self.event_end_ts, field="event_end_ts")
        )
        cutoff = utc_datetime(self.knowledge_cutoff_ts, field="knowledge_cutoff_ts")
        object.__setattr__(self, "event_start_ts", start)
        object.__setattr__(self, "event_end_ts", end)
        object.__setattr__(self, "knowledge_cutoff_ts", cutoff)
        object.__setattr__(
            self,
            "parent_source_member_id",
            _optional_hash(
                self.parent_source_member_id, field="parent_source_member_id"
            ),
        )
        if self.row_count == 0:
            if start is not None or end is not None:
                raise CanonicalizationError(
                    "zero-row source member must not declare event coverage"
                )
        elif start is None or end is None:
            raise CanonicalizationError(
                "non-empty source member requires event_start_ts and event_end_ts"
            )
        elif start > end:
            raise CanonicalizationError("event_start_ts must not exceed event_end_ts")
        if end is not None and end > cutoff:
            raise CanonicalizationError(
                "event_end_ts must not exceed knowledge_cutoff_ts"
            )

    def member_key_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "availability_policy_id": self.availability_policy_id,
            "calendar_manifest_id": self.calendar_manifest_id,
            "contract_id": self.contract_id,
            "revision_policy_id": self.revision_policy_id,
            "source_field_ids": list(self.source_field_ids),
            "source_id": self.source_id,
            "source_role": self.source_role.value,
            "source_schema_id": self.source_schema_id,
            "timeframe_id": self.timeframe_id,
            "venue_id": self.venue_id,
        }

    @property
    def source_member_key(self) -> str:
        return _identity("SourceBundleMemberKeyV3", self.member_key_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            **self.member_key_payload(),
            "artifact_hash": self.artifact_hash,
            "event_end_ts": (
                None if self.event_end_ts is None else utc_iso(self.event_end_ts)
            ),
            "event_start_ts": (
                None if self.event_start_ts is None else utc_iso(self.event_start_ts)
            ),
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "parent_source_member_id": self.parent_source_member_id,
            "row_count": self.row_count,
            "semantic_content_root": self.semantic_content_root,
            "source_member_key": self.source_member_key,
        }

    @property
    def source_member_id(self) -> str:
        return _identity("SourceBundleMemberV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "source_member_id": self.source_member_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SourceBundleMemberV3:
        expected = {
            "artifact_hash",
            "asset_id",
            "availability_policy_id",
            "calendar_manifest_id",
            "canonicalization_version",
            "contract_id",
            "event_end_ts",
            "event_start_ts",
            "knowledge_cutoff_ts",
            "parent_source_member_id",
            "revision_policy_id",
            "row_count",
            "schema_version",
            "semantic_content_root",
            "source_field_ids",
            "source_id",
            "source_member_id",
            "source_member_key",
            "source_role",
            "source_schema_id",
            "timeframe_id",
            "venue_id",
        }
        require_exact_keys(payload, expected=expected, context="SourceBundleMemberV3")
        _require_versions(payload)
        item = cls(
            source_id=payload["source_id"],
            source_role=payload["source_role"],
            asset_id=payload["asset_id"],
            venue_id=payload["venue_id"],
            contract_id=payload["contract_id"],
            timeframe_id=payload["timeframe_id"],
            source_schema_id=payload["source_schema_id"],
            source_field_ids=payload["source_field_ids"],
            availability_policy_id=payload["availability_policy_id"],
            revision_policy_id=payload["revision_policy_id"],
            calendar_manifest_id=payload["calendar_manifest_id"],
            semantic_content_root=payload["semantic_content_root"],
            artifact_hash=payload["artifact_hash"],
            row_count=payload["row_count"],
            event_start_ts=payload["event_start_ts"],
            event_end_ts=payload["event_end_ts"],
            knowledge_cutoff_ts=payload["knowledge_cutoff_ts"],
            parent_source_member_id=payload["parent_source_member_id"],
        )
        _require_digest(
            payload["source_member_key"],
            item.source_member_key,
            field="source_member_key",
        )
        _require_digest(
            payload["source_member_id"], item.source_member_id, field="source_member_id"
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceBundleV3:
    """A source-manifest-compatible set of exact source members."""

    source_dataset_id: str
    source_contract_id: str
    source_schema_id: str
    calendar_manifest_id: str
    universe_manifest_id: str
    first_seen_policy_id: str
    revision_policy_id: str
    vintage_class: str
    knowledge_cutoff_ts: datetime
    source_member_ids: tuple[str, ...]
    parent_source_bundle_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_dataset_id",
            canonical_identifier(self.source_dataset_id, field="source_dataset_id"),
        )
        for field_name in (
            "source_contract_id",
            "source_schema_id",
            "calendar_manifest_id",
            "universe_manifest_id",
            "first_seen_policy_id",
            "revision_policy_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        vintage = canonical_identifier(self.vintage_class, field="vintage_class")
        if vintage not in _VINTAGE_CLASSES:
            choices = ", ".join(sorted(_VINTAGE_CLASSES))
            raise CanonicalizationError(f"vintage_class must be one of: {choices}")
        object.__setattr__(self, "vintage_class", vintage)
        object.__setattr__(
            self,
            "knowledge_cutoff_ts",
            utc_datetime(self.knowledge_cutoff_ts, field="knowledge_cutoff_ts"),
        )
        object.__setattr__(
            self,
            "source_member_ids",
            _tuple_of_hashes(
                self.source_member_ids,
                field="source_member_ids",
                maximum=MAX_SOURCE_MEMBERS,
                allow_empty=False,
                sort=True,
            ),
        )
        object.__setattr__(
            self,
            "parent_source_bundle_id",
            _optional_hash(
                self.parent_source_bundle_id, field="parent_source_bundle_id"
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "calendar_manifest_id": self.calendar_manifest_id,
            "first_seen_policy_id": self.first_seen_policy_id,
            "knowledge_cutoff_ts": utc_iso(self.knowledge_cutoff_ts),
            "parent_source_bundle_id": self.parent_source_bundle_id,
            "revision_policy_id": self.revision_policy_id,
            "source_contract_id": self.source_contract_id,
            "source_dataset_id": self.source_dataset_id,
            "source_member_ids": list(self.source_member_ids),
            "source_schema_id": self.source_schema_id,
            "universe_manifest_id": self.universe_manifest_id,
            "vintage_class": self.vintage_class,
        }

    @property
    def source_bundle_id(self) -> str:
        return _identity("SourceBundleV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "source_bundle_id": self.source_bundle_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> SourceBundleV3:
        expected = {
            "calendar_manifest_id",
            "canonicalization_version",
            "first_seen_policy_id",
            "knowledge_cutoff_ts",
            "parent_source_bundle_id",
            "revision_policy_id",
            "schema_version",
            "source_bundle_id",
            "source_contract_id",
            "source_dataset_id",
            "source_member_ids",
            "source_schema_id",
            "universe_manifest_id",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="SourceBundleV3")
        _require_versions(payload)
        item = cls(
            source_dataset_id=payload["source_dataset_id"],
            source_contract_id=payload["source_contract_id"],
            source_schema_id=payload["source_schema_id"],
            calendar_manifest_id=payload["calendar_manifest_id"],
            universe_manifest_id=payload["universe_manifest_id"],
            first_seen_policy_id=payload["first_seen_policy_id"],
            revision_policy_id=payload["revision_policy_id"],
            vintage_class=payload["vintage_class"],
            knowledge_cutoff_ts=payload["knowledge_cutoff_ts"],
            source_member_ids=payload["source_member_ids"],
            parent_source_bundle_id=payload["parent_source_bundle_id"],
        )
        _require_digest(
            payload["source_bundle_id"], item.source_bundle_id, field="source_bundle_id"
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureDependencySlotV3:
    """A finite, typed input slot used by one or more feature definitions."""

    dependency_slot_name: str
    evidence_kind: EvidenceKind
    selection_mode: DependencySelectionMode
    missing_input_policy: MissingInputPolicy
    cardinality_scope: CardinalityScope
    minimum_count: int
    maximum_count: int
    maximum_age_seconds: int | None
    source_member_keys: tuple[str, ...] = ()
    source_field_ids: tuple[str, ...] = ()
    availability_policy_id: str | None = None
    revision_policy_id: str | None = None
    state_schema_id: str | None = None
    protocol_field_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "dependency_slot_name",
            canonical_identifier(
                self.dependency_slot_name, field="dependency_slot_name"
            ),
        )
        object.__setattr__(
            self,
            "evidence_kind",
            _enum(self.evidence_kind, EvidenceKind, field="evidence_kind"),
        )
        object.__setattr__(
            self,
            "selection_mode",
            _enum(self.selection_mode, DependencySelectionMode, field="selection_mode"),
        )
        object.__setattr__(
            self,
            "missing_input_policy",
            _enum(
                self.missing_input_policy,
                MissingInputPolicy,
                field="missing_input_policy",
            ),
        )
        object.__setattr__(
            self,
            "cardinality_scope",
            _enum(
                self.cardinality_scope,
                CardinalityScope,
                field="cardinality_scope",
            ),
        )
        object.__setattr__(
            self,
            "minimum_count",
            canonical_safe_int(
                self.minimum_count,
                field="minimum_count",
                minimum=0,
                maximum=MAX_SLOT_CARDINALITY,
            ),
        )
        object.__setattr__(
            self,
            "maximum_count",
            canonical_safe_int(
                self.maximum_count,
                field="maximum_count",
                minimum=1,
                maximum=MAX_SLOT_CARDINALITY,
            ),
        )
        if self.minimum_count > self.maximum_count:
            raise CanonicalizationError("minimum_count must not exceed maximum_count")
        if self.maximum_age_seconds is None:
            age = None
        else:
            age = canonical_safe_int(
                self.maximum_age_seconds,
                field="maximum_age_seconds",
                minimum=0,
                maximum=MAX_AGE_SECONDS,
            )
        object.__setattr__(self, "maximum_age_seconds", age)
        object.__setattr__(
            self,
            "source_member_keys",
            _tuple_of_hashes(
                self.source_member_keys,
                field="source_member_keys",
                maximum=MAX_SOURCE_MEMBERS,
                allow_empty=True,
                sort=True,
            ),
        )
        object.__setattr__(
            self,
            "source_field_ids",
            _tuple_of_identifiers(
                self.source_field_ids,
                field="source_field_ids",
                maximum=MAX_SOURCE_FIELDS,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "availability_policy_id",
            _optional_hash(self.availability_policy_id, field="availability_policy_id"),
        )
        object.__setattr__(
            self,
            "revision_policy_id",
            _optional_hash(self.revision_policy_id, field="revision_policy_id"),
        )
        object.__setattr__(
            self,
            "state_schema_id",
            _optional_hash(self.state_schema_id, field="state_schema_id"),
        )
        object.__setattr__(
            self,
            "protocol_field_names",
            _tuple_of_identifiers(
                self.protocol_field_names,
                field="protocol_field_names",
                maximum=MAX_SOURCE_FIELDS,
                allow_empty=True,
                sort=True,
            ),
        )
        self._validate_variant()
        self._validate_missing_policy()

    def _validate_missing_policy(self) -> None:
        if self.evidence_kind is EvidenceKind.PROTOCOL_CONSTANT:
            if self.missing_input_policy is not MissingInputPolicy.FAIL:
                raise CanonicalizationError(
                    "PROTOCOL_CONSTANT requires FAIL missing-input policy"
                )
            return
        if self.minimum_count == 0:
            raise CanonicalizationError(
                "observation and state dependency slots require minimum_count "
                "greater than zero; missing_input_policy controls insufficiency"
            )

    def _validate_variant(self) -> None:
        observation_modes = {
            DependencySelectionMode.EXACT_EVENT,
            DependencySelectionMode.LATEST_AVAILABLE_ASOF,
            DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        }
        if self.evidence_kind is EvidenceKind.OBSERVATION:
            if self.selection_mode not in observation_modes:
                raise CanonicalizationError(
                    "OBSERVATION slot uses an incompatible selection_mode"
                )
            if not self.source_member_keys or not self.source_field_ids:
                raise CanonicalizationError(
                    "OBSERVATION slot requires source_member_keys and source_field_ids"
                )
            if (
                self.cardinality_scope is CardinalityScope.PER_SOURCE_MEMBER
                and self.maximum_count * len(self.source_member_keys)
                > MAX_SLOT_CARDINALITY
            ):
                raise CanonicalizationError(
                    "PER_SOURCE_MEMBER aggregate cardinality exceeds the safety ceiling"
                )
            if self.availability_policy_id is None or self.revision_policy_id is None:
                raise CanonicalizationError(
                    "OBSERVATION slot requires availability and revision policies"
                )
            if self.maximum_age_seconds is None:
                raise CanonicalizationError(
                    "OBSERVATION slot requires finite maximum_age_seconds"
                )
            if self.state_schema_id is not None or self.protocol_field_names:
                raise CanonicalizationError(
                    "OBSERVATION slot must not declare state/protocol fields"
                )
            if self.selection_mode is DependencySelectionMode.EXACT_EVENT and (
                self.minimum_count != 1 or self.maximum_count != 1
            ):
                raise CanonicalizationError("EXACT_EVENT requires cardinality 1..1")
            if (
                self.selection_mode is DependencySelectionMode.LATEST_AVAILABLE_ASOF
                and self.maximum_count != 1
            ):
                raise CanonicalizationError(
                    "LATEST_AVAILABLE_ASOF requires maximum cardinality 1"
                )
            return
        if self.evidence_kind is EvidenceKind.STATE_CHECKPOINT:
            if (
                self.selection_mode
                is not DependencySelectionMode.PRIOR_STATE_CHECKPOINT
            ):
                raise CanonicalizationError(
                    "STATE_CHECKPOINT requires PRIOR_STATE_CHECKPOINT selection"
                )
            if self.state_schema_id is None or self.maximum_age_seconds is None:
                raise CanonicalizationError(
                    "STATE_CHECKPOINT requires state_schema_id and finite maximum age"
                )
            if self.maximum_count != 1:
                raise CanonicalizationError(
                    "PRIOR_STATE_CHECKPOINT requires maximum cardinality 1"
                )
            if (
                self.cardinality_scope is not CardinalityScope.TOTAL
                or self.source_member_keys
                or self.source_field_ids
                or self.availability_policy_id is not None
                or self.revision_policy_id is not None
                or self.protocol_field_names
            ):
                raise CanonicalizationError(
                    "STATE_CHECKPOINT must not declare observation/protocol fields"
                )
            return
        if self.selection_mode is not DependencySelectionMode.PROTOCOL_CONSTANT:
            raise CanonicalizationError(
                "PROTOCOL_CONSTANT evidence requires matching selection mode"
            )
        if not self.protocol_field_names:
            raise CanonicalizationError(
                "PROTOCOL_CONSTANT slot requires protocol_field_names"
            )
        if self.minimum_count != len(
            self.protocol_field_names
        ) or self.maximum_count != len(self.protocol_field_names):
            raise CanonicalizationError(
                "PROTOCOL_CONSTANT cardinality must equal its declared constants"
            )
        if (
            self.cardinality_scope is not CardinalityScope.TOTAL
            or self.maximum_age_seconds is not None
            or self.source_member_keys
            or self.source_field_ids
            or self.availability_policy_id is not None
            or self.revision_policy_id is not None
            or self.state_schema_id is not None
        ):
            raise CanonicalizationError(
                "PROTOCOL_CONSTANT must not declare observation/state fields"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "availability_policy_id": self.availability_policy_id,
            "cardinality_scope": self.cardinality_scope.value,
            "dependency_slot_name": self.dependency_slot_name,
            "evidence_kind": self.evidence_kind.value,
            "maximum_age_seconds": self.maximum_age_seconds,
            "maximum_count": self.maximum_count,
            "minimum_count": self.minimum_count,
            "missing_input_policy": self.missing_input_policy.value,
            "protocol_field_names": list(self.protocol_field_names),
            "revision_policy_id": self.revision_policy_id,
            "selection_mode": self.selection_mode.value,
            "source_field_ids": list(self.source_field_ids),
            "source_member_keys": list(self.source_member_keys),
            "state_schema_id": self.state_schema_id,
        }

    @property
    def dependency_slot_id(self) -> str:
        return _identity("FeatureDependencySlotV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "dependency_slot_id": self.dependency_slot_id,
            **self.identity_payload(),
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FeatureDependencySlotV3:
        expected = {
            "availability_policy_id",
            "canonicalization_version",
            "cardinality_scope",
            "dependency_slot_id",
            "dependency_slot_name",
            "evidence_kind",
            "maximum_age_seconds",
            "maximum_count",
            "minimum_count",
            "missing_input_policy",
            "protocol_field_names",
            "revision_policy_id",
            "schema_version",
            "selection_mode",
            "source_field_ids",
            "source_member_keys",
            "state_schema_id",
        }
        require_exact_keys(
            payload, expected=expected, context="FeatureDependencySlotV3"
        )
        _require_versions(payload)
        item = cls(
            dependency_slot_name=payload["dependency_slot_name"],
            evidence_kind=payload["evidence_kind"],
            selection_mode=payload["selection_mode"],
            missing_input_policy=payload["missing_input_policy"],
            cardinality_scope=payload["cardinality_scope"],
            minimum_count=payload["minimum_count"],
            maximum_count=payload["maximum_count"],
            maximum_age_seconds=payload["maximum_age_seconds"],
            source_member_keys=payload["source_member_keys"],
            source_field_ids=payload["source_field_ids"],
            availability_policy_id=payload["availability_policy_id"],
            revision_policy_id=payload["revision_policy_id"],
            state_schema_id=payload["state_schema_id"],
            protocol_field_names=payload["protocol_field_names"],
        )
        _require_digest(
            payload["dependency_slot_id"],
            item.dependency_slot_id,
            field="dependency_slot_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureDefinitionV3:
    """One ordered, content-addressed feature definition."""

    feature_name: str
    feature_family: str
    feature_role: FeatureRole
    nullable: bool
    transform_hash: str
    transform_parameters_hash: str
    normalization_hash: str
    input_dependency_slot_ids: tuple[str, ...]
    derived_feature_ids: tuple[str, ...]
    candidate_conditioned: bool
    candidate_field_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("feature_name", "feature_family"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "feature_role",
            _enum(self.feature_role, FeatureRole, field="feature_role"),
        )
        object.__setattr__(
            self, "nullable", _strict_bool(self.nullable, field="nullable")
        )
        if self.feature_role is FeatureRole.MISSINGNESS_INDICATOR and self.nullable:
            raise CanonicalizationError(
                "MISSINGNESS_INDICATOR feature must be non-nullable"
            )
        object.__setattr__(
            self,
            "candidate_conditioned",
            _strict_bool(self.candidate_conditioned, field="candidate_conditioned"),
        )
        candidate_field_names = _tuple_of_identifiers(
            self.candidate_field_names,
            field="candidate_field_names",
            maximum=len(CANDIDATE_FEATURE_FIELD_ALLOWLIST),
            allow_empty=True,
            sort=True,
        )
        unknown_candidate_fields = sorted(
            set(candidate_field_names) - CANDIDATE_FEATURE_FIELD_ALLOWLIST
        )
        if unknown_candidate_fields:
            raise CanonicalizationError(
                "candidate_field_names contains fields outside the sealed allowlist: "
                f"{unknown_candidate_fields}"
            )
        if candidate_field_names and not self.candidate_conditioned:
            raise CanonicalizationError(
                "candidate-neutral feature must not declare candidate_field_names"
            )
        if (
            self.feature_role is FeatureRole.MISSINGNESS_INDICATOR
            and self.candidate_conditioned
        ):
            raise CanonicalizationError(
                "MISSINGNESS_INDICATOR must be candidate-neutral"
            )
        object.__setattr__(self, "candidate_field_names", candidate_field_names)
        for field_name in (
            "transform_hash",
            "transform_parameters_hash",
            "normalization_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "input_dependency_slot_ids",
            _tuple_of_hashes(
                self.input_dependency_slot_ids,
                field="input_dependency_slot_ids",
                maximum=MAX_DEPENDENCY_SLOTS,
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "derived_feature_ids",
            _tuple_of_hashes(
                self.derived_feature_ids,
                field="derived_feature_ids",
                maximum=MAX_SCHEMA_FEATURES,
                allow_empty=True,
            ),
        )
        if (
            not self.input_dependency_slot_ids
            and not self.derived_feature_ids
            and not self.candidate_field_names
        ):
            raise CanonicalizationError(
                "feature requires a dependency slot, earlier derived feature, or "
                "declared candidate field"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "candidate_conditioned": self.candidate_conditioned,
            "candidate_field_names": list(self.candidate_field_names),
            "derived_feature_ids": list(self.derived_feature_ids),
            "feature_family": self.feature_family,
            "feature_name": self.feature_name,
            "feature_role": self.feature_role.value,
            "input_dependency_slot_ids": list(self.input_dependency_slot_ids),
            "normalization_hash": self.normalization_hash,
            "nullable": self.nullable,
            "transform_hash": self.transform_hash,
            "transform_parameters_hash": self.transform_parameters_hash,
        }

    @property
    def feature_definition_id(self) -> str:
        return _identity("FeatureDefinitionV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "feature_definition_id": self.feature_definition_id,
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FeatureDefinitionV3:
        expected = {
            "candidate_conditioned",
            "candidate_field_names",
            "canonicalization_version",
            "derived_feature_ids",
            "feature_definition_id",
            "feature_family",
            "feature_name",
            "feature_role",
            "input_dependency_slot_ids",
            "normalization_hash",
            "nullable",
            "schema_version",
            "transform_hash",
            "transform_parameters_hash",
        }
        require_exact_keys(payload, expected=expected, context="FeatureDefinitionV3")
        _require_versions(payload)
        item = cls(
            feature_name=payload["feature_name"],
            feature_family=payload["feature_family"],
            feature_role=payload["feature_role"],
            nullable=payload["nullable"],
            transform_hash=payload["transform_hash"],
            transform_parameters_hash=payload["transform_parameters_hash"],
            normalization_hash=payload["normalization_hash"],
            input_dependency_slot_ids=payload["input_dependency_slot_ids"],
            derived_feature_ids=payload["derived_feature_ids"],
            candidate_conditioned=payload["candidate_conditioned"],
            candidate_field_names=payload["candidate_field_names"],
        )
        _require_digest(
            payload["feature_definition_id"],
            item.feature_definition_id,
            field="feature_definition_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class FeatureSchemaV3:
    """An ordered feature vector and the semantic set of its input slots."""

    feature_schema_name: str
    feature_schema_version: str
    source_contract_id: str
    source_schema_id: str
    dependency_slot_ids: tuple[str, ...]
    feature_definition_ids: tuple[str, ...]
    frozen_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("feature_schema_name", "feature_schema_version"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in ("source_contract_id", "source_schema_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "dependency_slot_ids",
            _tuple_of_hashes(
                self.dependency_slot_ids,
                field="dependency_slot_ids",
                maximum=MAX_DEPENDENCY_SLOTS,
                allow_empty=True,
                sort=True,
            ),
        )
        object.__setattr__(
            self,
            "feature_definition_ids",
            _tuple_of_hashes(
                self.feature_definition_ids,
                field="feature_definition_ids",
                maximum=MAX_SCHEMA_FEATURES,
                allow_empty=False,
            ),
        )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "dependency_slot_ids": list(self.dependency_slot_ids),
            "feature_definition_ids": list(self.feature_definition_ids),
            "feature_schema_name": self.feature_schema_name,
            "feature_schema_version": self.feature_schema_version,
            "frozen_at": utc_iso(self.frozen_at),
            "source_contract_id": self.source_contract_id,
            "source_schema_id": self.source_schema_id,
        }

    @property
    def feature_schema_id(self) -> str:
        return _identity("FeatureSchemaV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "feature_schema_id": self.feature_schema_id,
            "schema_version": EVIDENCE_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> FeatureSchemaV3:
        expected = {
            "canonicalization_version",
            "dependency_slot_ids",
            "feature_definition_ids",
            "feature_schema_id",
            "feature_schema_name",
            "feature_schema_version",
            "frozen_at",
            "schema_version",
            "source_contract_id",
            "source_schema_id",
        }
        require_exact_keys(payload, expected=expected, context="FeatureSchemaV3")
        _require_versions(payload)
        item = cls(
            feature_schema_name=payload["feature_schema_name"],
            feature_schema_version=payload["feature_schema_version"],
            source_contract_id=payload["source_contract_id"],
            source_schema_id=payload["source_schema_id"],
            dependency_slot_ids=payload["dependency_slot_ids"],
            feature_definition_ids=payload["feature_definition_ids"],
            frozen_at=payload["frozen_at"],
        )
        _require_digest(
            payload["feature_schema_id"],
            item.feature_schema_id,
            field="feature_schema_id",
        )
        return item


def validate_source_bundle_graph(
    bundle: SourceBundleV3,
    member_registry: Mapping[str, SourceBundleMemberV3],
    bundle_registry: Mapping[str, SourceBundleV3],
) -> None:
    """Validate membership, source clocks, and append-only bundle lineage."""

    if not isinstance(bundle, SourceBundleV3):
        raise CanonicalizationError("bundle must be SourceBundleV3")
    state: dict[str, int] = {}
    stack: list[tuple[SourceBundleV3, bool]] = [(bundle, False)]
    while stack:
        current, exiting = stack.pop()
        current_id = current.source_bundle_id
        if exiting:
            _validate_bundle_local(current, member_registry, bundle_registry)
            state[current_id] = 2
            continue
        marker = state.get(current_id, 0)
        if marker == 2:
            continue
        if marker == 1:
            raise CanonicalizationError("source bundle lineage contains a cycle")
        state[current_id] = 1
        stack.append((current, True))
        parent_id = current.parent_source_bundle_id
        if parent_id is not None:
            stack.append((_resolve_bundle(bundle_registry, parent_id), False))


def validate_source_member_lineage(
    member: SourceBundleMemberV3,
    member_registry: Mapping[str, SourceBundleMemberV3],
) -> None:
    """Validate one member's direct append-only predecessor, when declared."""

    if not isinstance(member, SourceBundleMemberV3):
        raise CanonicalizationError("member must be SourceBundleMemberV3")
    parent_id = member.parent_source_member_id
    if parent_id is None:
        return
    previous = _resolve_member(member_registry, parent_id)
    _validate_member_successor(member, previous)


def _validate_member_successor(
    member: SourceBundleMemberV3,
    previous: SourceBundleMemberV3,
) -> None:
    if member.source_member_key != previous.source_member_key:
        raise CanonicalizationError(
            "child source member changes its stable membership key"
        )
    if member.parent_source_member_id != previous.source_member_id:
        raise CanonicalizationError(
            "child source member must reference its exact predecessor"
        )
    if member.knowledge_cutoff_ts <= previous.knowledge_cutoff_ts:
        raise CanonicalizationError(
            "child source member knowledge cutoff must follow its parent"
        )
    if member.row_count < previous.row_count:
        raise CanonicalizationError("source member lineage reduces row_count")
    if previous.row_count > 0 and previous.event_start_ts != member.event_start_ts:
        raise CanonicalizationError("source member lineage changes event_start_ts")
    if previous.event_end_ts is not None and (
        member.event_end_ts is None or member.event_end_ts < previous.event_end_ts
    ):
        raise CanonicalizationError("source member lineage reduces event coverage")
    coverage_changed = (
        member.row_count != previous.row_count
        or member.event_start_ts != previous.event_start_ts
        or member.event_end_ts != previous.event_end_ts
    )
    if (
        coverage_changed
        and member.semantic_content_root == previous.semantic_content_root
    ):
        raise CanonicalizationError(
            "source member row/coverage change requires a new semantic content root"
        )
    if (
        member.semantic_content_root != previous.semantic_content_root
        and member.artifact_hash == previous.artifact_hash
    ):
        raise CanonicalizationError(
            "source member semantic content change requires a new artifact hash"
        )


def _resolve_member(
    registry: Mapping[str, SourceBundleMemberV3], source_member_id: str
) -> SourceBundleMemberV3:
    member = registry.get(source_member_id)
    if member is None:
        raise CanonicalizationError("missing referenced source bundle member")
    if not isinstance(member, SourceBundleMemberV3):
        raise CanonicalizationError("source member registry contains an invalid value")
    if member.source_member_id != source_member_id:
        raise CanonicalizationError(
            "source member registry key does not match content ID"
        )
    return member


def _resolve_bundle(
    registry: Mapping[str, SourceBundleV3], source_bundle_id: str
) -> SourceBundleV3:
    bundle = registry.get(source_bundle_id)
    if bundle is None:
        raise CanonicalizationError("missing referenced parent source bundle")
    if not isinstance(bundle, SourceBundleV3):
        raise CanonicalizationError("source bundle registry contains an invalid value")
    if bundle.source_bundle_id != source_bundle_id:
        raise CanonicalizationError(
            "source bundle registry key does not match content ID"
        )
    return bundle


def _members_by_key(
    bundle: SourceBundleV3, registry: Mapping[str, SourceBundleMemberV3]
) -> dict[str, SourceBundleMemberV3]:
    result: dict[str, SourceBundleMemberV3] = {}
    for member_id in bundle.source_member_ids:
        member = _resolve_member(registry, member_id)
        if member.source_member_key in result:
            raise CanonicalizationError("source bundle contains duplicate member keys")
        if member.calendar_manifest_id != bundle.calendar_manifest_id:
            raise CanonicalizationError(
                "source member calendar differs from source bundle"
            )
        if member.availability_policy_id != bundle.first_seen_policy_id:
            raise CanonicalizationError(
                "source member availability policy differs from source bundle"
            )
        if member.revision_policy_id != bundle.revision_policy_id:
            raise CanonicalizationError(
                "source member revision policy differs from source bundle"
            )
        if member.knowledge_cutoff_ts > bundle.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "source member knowledge cutoff exceeds source bundle cutoff"
            )
        result[member.source_member_key] = member
    return result


def _validate_bundle_local(
    bundle: SourceBundleV3,
    member_registry: Mapping[str, SourceBundleMemberV3],
    bundle_registry: Mapping[str, SourceBundleV3],
) -> None:
    members = _members_by_key(bundle, member_registry)
    parent_id = bundle.parent_source_bundle_id
    if parent_id is None:
        for member in members.values():
            if member.parent_source_member_id is not None:
                raise CanonicalizationError(
                    "root source bundle member must not declare a parent"
                )
        return
    parent = _resolve_bundle(bundle_registry, parent_id)
    for field_name in (
        "source_dataset_id",
        "source_contract_id",
        "source_schema_id",
        "calendar_manifest_id",
        "universe_manifest_id",
        "first_seen_policy_id",
        "revision_policy_id",
    ):
        if getattr(bundle, field_name) != getattr(parent, field_name):
            raise CanonicalizationError(f"source bundle lineage changes {field_name}")
    if bundle.knowledge_cutoff_ts <= parent.knowledge_cutoff_ts:
        raise CanonicalizationError(
            "child source bundle knowledge cutoff must follow its parent cutoff"
        )
    if bundle.vintage_class != parent.vintage_class:
        raise CanonicalizationError(
            "source bundle lineage cannot change vintage_class; prospective "
            "live evidence requires a separate root lineage"
        )

    parent_members = _members_by_key(parent, member_registry)
    missing_keys = sorted(set(parent_members) - set(members))
    if missing_keys:
        raise CanonicalizationError(
            f"source bundle lineage removes member keys: {missing_keys}"
        )
    parent_member_ids = set(parent.source_member_ids)
    for key, member in members.items():
        previous = parent_members.get(key)
        if previous is None:
            if member.parent_source_member_id is not None:
                raise CanonicalizationError(
                    "new source member key must not claim a parent in the prior bundle"
                )
            if member.knowledge_cutoff_ts <= parent.knowledge_cutoff_ts:
                raise CanonicalizationError(
                    "new source member knowledge cutoff must follow the parent bundle"
                )
            continue
        if member.source_member_id == previous.source_member_id:
            continue
        if member.knowledge_cutoff_ts <= parent.knowledge_cutoff_ts:
            raise CanonicalizationError(
                "changed source member knowledge cutoff must follow the parent bundle"
            )
        _validate_member_successor(member, previous)
        if member.parent_source_member_id not in parent_member_ids:
            raise CanonicalizationError("source member parent is outside parent bundle")


def validate_feature_schema_graph(
    schema: FeatureSchemaV3,
    slot_registry: Mapping[str, FeatureDependencySlotV3],
    feature_registry: Mapping[str, FeatureDefinitionV3],
    source_bundle: SourceBundleV3,
    member_registry: Mapping[str, SourceBundleMemberV3],
    bundle_registry: Mapping[str, SourceBundleV3],
) -> None:
    """Validate all feature, slot, and source references for one frozen schema."""

    if not isinstance(schema, FeatureSchemaV3):
        raise CanonicalizationError("schema must be FeatureSchemaV3")
    validate_source_bundle_graph(source_bundle, member_registry, bundle_registry)
    if schema.source_contract_id != source_bundle.source_contract_id:
        raise CanonicalizationError(
            "feature schema source_contract_id differs from bundle"
        )
    if schema.source_schema_id != source_bundle.source_schema_id:
        raise CanonicalizationError(
            "feature schema source_schema_id differs from bundle"
        )
    members = _members_by_key(source_bundle, member_registry)
    slots: dict[str, FeatureDependencySlotV3] = {}
    slot_names: set[str] = set()
    for slot_id in schema.dependency_slot_ids:
        slot = slot_registry.get(slot_id)
        if slot is None:
            raise CanonicalizationError("missing referenced feature dependency slot")
        if not isinstance(slot, FeatureDependencySlotV3):
            raise CanonicalizationError("slot registry contains an invalid value")
        if slot.dependency_slot_id != slot_id:
            raise CanonicalizationError("slot registry key does not match content ID")
        if slot.dependency_slot_name in slot_names:
            raise CanonicalizationError("feature schema contains duplicate slot names")
        slot_names.add(slot.dependency_slot_name)
        if slot.evidence_kind is EvidenceKind.OBSERVATION:
            for member_key in slot.source_member_keys:
                member = members.get(member_key)
                if member is None:
                    raise CanonicalizationError(
                        "observation slot references member outside source bundle"
                    )
                if member.source_role is not SourceRole.DECISION_INPUT:
                    raise CanonicalizationError(
                        "pre-decision observation slot requires DECISION_INPUT source role"
                    )
                missing_fields = sorted(
                    set(slot.source_field_ids) - set(member.source_field_ids)
                )
                if missing_fields:
                    raise CanonicalizationError(
                        f"observation slot references unknown source fields: {missing_fields}"
                    )
                if slot.availability_policy_id != member.availability_policy_id:
                    raise CanonicalizationError(
                        "observation slot availability policy differs from source member"
                    )
                if slot.revision_policy_id != member.revision_policy_id:
                    raise CanonicalizationError(
                        "observation slot revision policy differs from source member"
                    )
        slots[slot_id] = slot

    features: list[FeatureDefinitionV3] = []
    feature_names: set[str] = set()
    for feature_id in schema.feature_definition_ids:
        feature = feature_registry.get(feature_id)
        if feature is None:
            raise CanonicalizationError("missing referenced feature definition")
        if not isinstance(feature, FeatureDefinitionV3):
            raise CanonicalizationError("feature registry contains an invalid value")
        if feature.feature_definition_id != feature_id:
            raise CanonicalizationError(
                "feature registry key does not match content ID"
            )
        if feature.feature_name in feature_names:
            raise CanonicalizationError(
                "feature schema contains duplicate feature names"
            )
        feature_names.add(feature.feature_name)
        unknown_slots = sorted(set(feature.input_dependency_slot_ids) - set(slots))
        if unknown_slots:
            raise CanonicalizationError(
                f"feature references dependency slots outside schema: {unknown_slots}"
            )
        features.append(feature)

    all_feature_ids = set(schema.feature_definition_ids)
    prior_feature_ids: set[str] = set()
    candidate_conditioned_ids: set[str] = set()
    feature_slot_ancestry: dict[str, frozenset[str]] = {}
    used_slot_ids: set[str] = set()
    for feature in features:
        used_slot_ids.update(feature.input_dependency_slot_ids)
        unknown_derived = sorted(set(feature.derived_feature_ids) - all_feature_ids)
        if unknown_derived:
            raise CanonicalizationError(
                f"feature references derived features outside schema: {unknown_derived}"
            )
        forward = sorted(set(feature.derived_feature_ids) - prior_feature_ids)
        if forward:
            raise CanonicalizationError(
                f"derived feature references must point to earlier features: {forward}"
            )
        tainted_inputs = sorted(
            set(feature.derived_feature_ids).intersection(candidate_conditioned_ids)
        )
        if not feature.candidate_conditioned and tainted_inputs:
            raise CanonicalizationError(
                "candidate-neutral feature derives from candidate-conditioned "
                f"features: {tainted_inputs}"
            )
        if (
            feature.candidate_conditioned
            and not feature.candidate_field_names
            and not tainted_inputs
        ):
            raise CanonicalizationError(
                "candidate-conditioned feature requires declared candidate fields "
                "or a candidate-conditioned ancestor"
            )
        inherited_slots = set(feature.input_dependency_slot_ids)
        for parent_id in feature.derived_feature_ids:
            inherited_slots.update(feature_slot_ancestry[parent_id])
        feature_slot_ancestry[feature.feature_definition_id] = frozenset(
            inherited_slots
        )
        optional_ancestry = {
            slot_id
            for slot_id in inherited_slots
            if slots[slot_id].missing_input_policy is not MissingInputPolicy.FAIL
        }
        if (
            optional_ancestry
            and feature.feature_role is not FeatureRole.MISSINGNESS_INDICATOR
            and not feature.nullable
        ):
            raise CanonicalizationError(
                "feature with ABSTAIN or NULL_WITH_INDICATOR input ancestry must "
                "be nullable"
            )
        prior_feature_ids.add(feature.feature_definition_id)
        if feature.candidate_conditioned:
            candidate_conditioned_ids.add(feature.feature_definition_id)

    unused_slots = sorted(set(slots) - used_slot_ids)
    if unused_slots:
        raise CanonicalizationError(
            f"feature schema contains unused slots: {unused_slots}"
        )

    null_indicator_slots = {
        slot_id
        for slot_id, slot in slots.items()
        if slot.missing_input_policy is MissingInputPolicy.NULL_WITH_INDICATOR
    }
    covered_indicator_slots = {
        slot_id
        for feature in features
        if feature.feature_role is FeatureRole.MISSINGNESS_INDICATOR
        for slot_id in feature.input_dependency_slot_ids
        if slot_id in null_indicator_slots
    }
    missing_indicators = sorted(null_indicator_slots - covered_indicator_slots)
    if missing_indicators:
        raise CanonicalizationError(
            "NULL_WITH_INDICATOR slots require a directly bound "
            f"MISSINGNESS_INDICATOR feature: {missing_indicators}"
        )
    for feature in features:
        if feature.feature_role is not FeatureRole.MISSINGNESS_INDICATOR:
            continue
        if (
            len(feature.input_dependency_slot_ids) != 1
            or feature.derived_feature_ids
            or feature.input_dependency_slot_ids[0] not in null_indicator_slots
        ):
            raise CanonicalizationError(
                "MISSINGNESS_INDICATOR feature must bind exactly one "
                "NULL_WITH_INDICATOR slot directly"
            )


__all__ = [
    "CANDIDATE_FEATURE_FIELD_ALLOWLIST",
    "CardinalityScope",
    "DependencySelectionMode",
    "EVIDENCE_SCHEMA_VERSION",
    "EvidenceKind",
    "FeatureDefinitionV3",
    "FeatureDependencySlotV3",
    "FeatureRole",
    "FeatureSchemaV3",
    "MAX_SCHEMA_FEATURES",
    "MissingInputPolicy",
    "SourceBundleMemberV3",
    "SourceBundleV3",
    "SourceRole",
    "validate_feature_schema_graph",
    "validate_source_bundle_graph",
    "validate_source_member_lineage",
]

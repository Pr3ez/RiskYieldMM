"""Immutable V3 contracts for causal trading decisions and later outcomes.

The contract graph deliberately keeps future-dependent labels out of the
pre-outcome decision identity:

``InformationSetV3 -> EligibilityDecisionV3 -> DecisionEventV3``

``LabelOutcomeV3`` is appended later and links to the unchanged decision ID.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_decimal,
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

CONTRACT_SCHEMA_VERSION = "riskyieldmm_trade_event_v3"
MAX_HOLDING_SECONDS = 315_576_000
MAX_COST_COMPONENTS = 64
DECIMAL_ARITHMETIC_PRECISION = 100
RETURN_QUANTUM = Decimal("0.00000001")


class TradeSide(str, Enum):
    """One independently evaluated trade direction."""

    LONG = "LONG"
    SHORT = "SHORT"


class VintageClass(str, Enum):
    """How faithfully the source represents historical availability."""

    LIVE_FIRST_SEEN_CERTIFIED = "LIVE_FIRST_SEEN_CERTIFIED"
    HISTORICAL_AS_WAS_CERTIFIED = "HISTORICAL_AS_WAS_CERTIFIED"
    NOMINAL_CURRENT_REVISION = "NOMINAL_CURRENT_REVISION"


class EligibilityVerdict(str, Enum):
    """Static signal-cohort eligibility, separate from portfolio acceptance."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    ABSTAIN_DATA = "ABSTAIN_DATA"


class EntryScenario(str, Enum):
    """Predeclared order-entry interpretation."""

    NEXT_REAL_BASE_BAR_OPEN = "NEXT_REAL_BASE_BAR_OPEN"
    FORWARD_MARKET_ORDER = "FORWARD_MARKET_ORDER"
    LIVE_MARKET_ORDER = "LIVE_MARKET_ORDER"


class ExecutionMode(str, Enum):
    """Evidence class used to resolve a later outcome."""

    HISTORICAL_NOMINAL_SCENARIO = "HISTORICAL_NOMINAL_SCENARIO"
    FORWARD_PAPER = "FORWARD_PAPER"
    LIVE_ACTUAL = "LIVE_ACTUAL"


class BarrierOutcomeV3(str, Enum):
    """Terminal outcomes for an eligible decision event."""

    TP_FIRST = "TP_FIRST"
    SL_FIRST = "SL_FIRST"
    TIMEOUT = "TIMEOUT"
    AMBIGUOUS = "AMBIGUOUS"
    NO_FILL = "NO_FILL"
    CANCELLED = "CANCELLED"


class AmbiguityResolution(str, Enum):
    """How an unresolved same-observation TP/SL path is represented."""

    CONSERVATIVE_LOWER_BOUND = "CONSERVATIVE_LOWER_BOUND"


FILLED_OUTCOMES = frozenset(
    {
        BarrierOutcomeV3.TP_FIRST,
        BarrierOutcomeV3.SL_FIRST,
        BarrierOutcomeV3.TIMEOUT,
        BarrierOutcomeV3.AMBIGUOUS,
    }
)
UNFILLED_OUTCOMES = frozenset({BarrierOutcomeV3.NO_FILL, BarrierOutcomeV3.CANCELLED})


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "schema_version": CONTRACT_SCHEMA_VERSION,
            "payload": dict(payload),
        }
    )


def _record_hash(domain: str, payload: Mapping[str, Any]) -> str:
    return _identity(f"{domain}.record", payload)


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {allowed}") from exc


def _strict_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CanonicalizationError(f"{field} must be boolean")
    return value


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _optional_identifier(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_identifier(value, field=field)


def _optional_timestamp(value: Any, *, field: str) -> datetime | None:
    return None if value is None else utc_datetime(value, field=field)


def _optional_decimal(
    value: Any,
    *,
    field: str,
    minimum: Decimal | int | str | None = None,
    strictly_positive: bool = False,
) -> str | None:
    if value is None:
        return None
    return canonical_decimal(
        value,
        field=field,
        minimum=minimum,
        strictly_positive=strictly_positive,
    )


def _enum_value(value: Enum) -> str:
    return str(value.value)


@dataclass(frozen=True, slots=True, kw_only=True)
class InformationDependencyV3:
    """One exact source observation revision selected before a cutoff."""

    name: str
    source_id: str
    source_manifest_id: str
    observation_revision_id: str
    source_event_ts: datetime
    bar_open_ts: datetime
    bar_close_ts: datetime
    source_publish_ts: datetime | None
    ingested_first_seen_ts: datetime
    revision_received_ts: datetime
    feature_available_ts: datetime
    value_digest: str
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonical_identifier(self.name, field="name"))
        object.__setattr__(
            self, "source_id", canonical_identifier(self.source_id, field="source_id")
        )
        for field_name in (
            "source_manifest_id",
            "observation_revision_id",
            "value_digest",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "source_event_ts",
            utc_datetime(self.source_event_ts, field="source_event_ts"),
        )
        object.__setattr__(
            self,
            "bar_open_ts",
            utc_datetime(self.bar_open_ts, field="bar_open_ts"),
        )
        object.__setattr__(
            self,
            "bar_close_ts",
            utc_datetime(self.bar_close_ts, field="bar_close_ts"),
        )
        object.__setattr__(
            self,
            "source_publish_ts",
            _optional_timestamp(self.source_publish_ts, field="source_publish_ts"),
        )
        object.__setattr__(
            self,
            "ingested_first_seen_ts",
            utc_datetime(self.ingested_first_seen_ts, field="ingested_first_seen_ts"),
        )
        object.__setattr__(
            self,
            "revision_received_ts",
            utc_datetime(self.revision_received_ts, field="revision_received_ts"),
        )
        object.__setattr__(
            self,
            "feature_available_ts",
            utc_datetime(self.feature_available_ts, field="feature_available_ts"),
        )
        object.__setattr__(
            self, "required", _strict_bool(self.required, field="required")
        )
        if self.bar_open_ts >= self.bar_close_ts:
            raise CanonicalizationError("bar_open_ts must precede bar_close_ts")
        if not self.bar_open_ts <= self.source_event_ts <= self.bar_close_ts:
            raise CanonicalizationError(
                "source_event_ts must lie inside the completed bar interval"
            )
        if (
            self.source_publish_ts is not None
            and self.source_event_ts > self.source_publish_ts
        ):
            raise CanonicalizationError(
                "source_event_ts must not exceed source_publish_ts"
            )
        if (
            self.source_publish_ts is not None
            and self.source_publish_ts > self.ingested_first_seen_ts
        ):
            raise CanonicalizationError(
                "source_publish_ts must not exceed ingested_first_seen_ts"
            )
        if self.ingested_first_seen_ts > self.revision_received_ts:
            raise CanonicalizationError(
                "ingested_first_seen_ts must not exceed revision_received_ts"
            )
        if self.bar_close_ts > self.feature_available_ts:
            raise CanonicalizationError(
                "bar_close_ts must not exceed feature_available_ts"
            )
        if self.revision_received_ts > self.feature_available_ts:
            raise CanonicalizationError(
                "revision_received_ts must not exceed feature_available_ts"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "bar_open_ts": utc_iso(self.bar_open_ts),
            "bar_close_ts": utc_iso(self.bar_close_ts),
            "feature_available_ts": utc_iso(self.feature_available_ts),
            "ingested_first_seen_ts": utc_iso(self.ingested_first_seen_ts),
            "name": self.name,
            "observation_revision_id": self.observation_revision_id,
            "required": self.required,
            "revision_received_ts": utc_iso(self.revision_received_ts),
            "source_event_ts": utc_iso(self.source_event_ts),
            "source_id": self.source_id,
            "source_manifest_id": self.source_manifest_id,
            "source_publish_ts": (
                None
                if self.source_publish_ts is None
                else utc_iso(self.source_publish_ts)
            ),
            "value_digest": self.value_digest,
        }

    @property
    def dependency_id(self) -> str:
        return _identity("InformationDependencyV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "dependency_id": self.dependency_id,
            **self.identity_payload(),
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> InformationDependencyV3:
        expected = {
            "bar_open_ts",
            "bar_close_ts",
            "canonicalization_version",
            "dependency_id",
            "feature_available_ts",
            "ingested_first_seen_ts",
            "name",
            "observation_revision_id",
            "required",
            "revision_received_ts",
            "schema_version",
            "source_event_ts",
            "source_id",
            "source_manifest_id",
            "source_publish_ts",
            "value_digest",
        }
        require_exact_keys(
            payload, expected=expected, context="InformationDependencyV3"
        )
        _require_versions(payload)
        item = cls(
            name=payload["name"],
            source_id=payload["source_id"],
            source_manifest_id=payload["source_manifest_id"],
            observation_revision_id=payload["observation_revision_id"],
            source_event_ts=payload["source_event_ts"],
            bar_open_ts=payload["bar_open_ts"],
            bar_close_ts=payload["bar_close_ts"],
            source_publish_ts=payload["source_publish_ts"],
            ingested_first_seen_ts=payload["ingested_first_seen_ts"],
            revision_received_ts=payload["revision_received_ts"],
            feature_available_ts=payload["feature_available_ts"],
            value_digest=payload["value_digest"],
            required=payload["required"],
        )
        _require_digest(
            payload["dependency_id"], item.dependency_id, field="dependency_id"
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class InformationSetV3:
    """All observations and causal feature evidence available at one cutoff."""

    asset_id: str
    venue_id: str
    contract_id: str
    timeframe_id: str
    observation_cutoff_ts: datetime
    assembled_at: datetime
    source_manifest_id: str
    protocol_manifest_id: str
    calendar_manifest_id: str
    feature_schema_id: str
    feature_materialization_hash: str
    dependencies: tuple[InformationDependencyV3, ...]
    vintage_class: VintageClass
    point_in_time_certified: bool
    certification_blockers: tuple[str, ...]
    data_quality_flags: tuple[str, ...] = ()
    state_checkpoint_ids: tuple[str, ...] = ()
    universe_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("asset_id", "venue_id", "contract_id", "timeframe_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "source_manifest_id",
            "protocol_manifest_id",
            "calendar_manifest_id",
            "feature_schema_id",
            "feature_materialization_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "universe_snapshot_id",
            _optional_hash(self.universe_snapshot_id, field="universe_snapshot_id"),
        )
        object.__setattr__(
            self,
            "observation_cutoff_ts",
            utc_datetime(self.observation_cutoff_ts, field="observation_cutoff_ts"),
        )
        object.__setattr__(
            self, "assembled_at", utc_datetime(self.assembled_at, field="assembled_at")
        )
        if self.assembled_at < self.observation_cutoff_ts:
            raise CanonicalizationError(
                "assembled_at must not precede observation_cutoff_ts"
            )

        dependencies = tuple(self.dependencies)
        if not dependencies or not all(
            isinstance(item, InformationDependencyV3) for item in dependencies
        ):
            raise CanonicalizationError(
                "dependencies must contain InformationDependencyV3 records"
            )
        if len({item.dependency_id for item in dependencies}) != len(dependencies):
            raise CanonicalizationError("dependencies contain duplicate identities")
        dependencies = tuple(sorted(dependencies, key=lambda item: item.dependency_id))
        if any(
            item.source_manifest_id != self.source_manifest_id for item in dependencies
        ):
            raise CanonicalizationError(
                "every dependency must reference the information-set source manifest"
            )
        if any(
            item.feature_available_ts > self.observation_cutoff_ts
            for item in dependencies
        ):
            raise CanonicalizationError(
                "a dependency became available after observation_cutoff_ts"
            )
        object.__setattr__(self, "dependencies", dependencies)

        vintage = _enum(self.vintage_class, VintageClass, field="vintage_class")
        object.__setattr__(self, "vintage_class", vintage)
        certified = _strict_bool(
            self.point_in_time_certified, field="point_in_time_certified"
        )
        object.__setattr__(self, "point_in_time_certified", certified)
        blockers = canonical_reason_codes(
            self.certification_blockers, field="certification_blockers"
        )
        quality = canonical_reason_codes(
            self.data_quality_flags, field="data_quality_flags"
        )
        checkpoints = tuple(
            sorted(
                {
                    canonical_hash(value, field="state_checkpoint_ids")
                    for value in self.state_checkpoint_ids
                }
            )
        )
        if len(checkpoints) != len(tuple(self.state_checkpoint_ids)):
            raise CanonicalizationError("state_checkpoint_ids contain duplicates")
        object.__setattr__(self, "certification_blockers", blockers)
        object.__setattr__(self, "data_quality_flags", quality)
        object.__setattr__(self, "state_checkpoint_ids", checkpoints)
        _validate_certification(vintage, certified, blockers)

    def identity_payload(self) -> dict[str, Any]:
        """Semantic input identity, intentionally excluding derived feature floats."""

        return {
            "asset_id": self.asset_id,
            "calendar_manifest_id": self.calendar_manifest_id,
            "contract_id": self.contract_id,
            "data_quality_flags": list(self.data_quality_flags),
            "dependencies": [item.dependency_id for item in self.dependencies],
            "feature_schema_id": self.feature_schema_id,
            "observation_cutoff_ts": utc_iso(self.observation_cutoff_ts),
            "protocol_manifest_id": self.protocol_manifest_id,
            "source_manifest_id": self.source_manifest_id,
            "state_checkpoint_ids": list(self.state_checkpoint_ids),
            "timeframe_id": self.timeframe_id,
            "universe_snapshot_id": self.universe_snapshot_id,
            "venue_id": self.venue_id,
            "vintage_class": _enum_value(self.vintage_class),
        }

    @property
    def information_set_id(self) -> str:
        return _identity("InformationSetV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "assembled_at": utc_iso(self.assembled_at),
            "certification_blockers": list(self.certification_blockers),
            "dependencies": [item.as_dict() for item in self.dependencies],
            "feature_materialization_hash": self.feature_materialization_hash,
            "information_set_id": self.information_set_id,
            "point_in_time_certified": self.point_in_time_certified,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("InformationSetV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> InformationSetV3:
        expected = {
            "assembled_at",
            "asset_id",
            "calendar_manifest_id",
            "canonicalization_version",
            "certification_blockers",
            "contract_id",
            "data_quality_flags",
            "dependencies",
            "feature_materialization_hash",
            "feature_schema_id",
            "information_set_id",
            "observation_cutoff_ts",
            "point_in_time_certified",
            "protocol_manifest_id",
            "record_hash",
            "schema_version",
            "source_manifest_id",
            "state_checkpoint_ids",
            "timeframe_id",
            "universe_snapshot_id",
            "venue_id",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="InformationSetV3")
        _require_versions(payload)
        raw_dependencies = payload["dependencies"]
        if not isinstance(raw_dependencies, list):
            raise CanonicalizationError("dependencies must be a JSON array")
        item = cls(
            asset_id=payload["asset_id"],
            venue_id=payload["venue_id"],
            contract_id=payload["contract_id"],
            timeframe_id=payload["timeframe_id"],
            observation_cutoff_ts=payload["observation_cutoff_ts"],
            assembled_at=payload["assembled_at"],
            source_manifest_id=payload["source_manifest_id"],
            protocol_manifest_id=payload["protocol_manifest_id"],
            calendar_manifest_id=payload["calendar_manifest_id"],
            feature_schema_id=payload["feature_schema_id"],
            feature_materialization_hash=payload["feature_materialization_hash"],
            dependencies=tuple(
                InformationDependencyV3.from_mapping(value)
                for value in raw_dependencies
            ),
            vintage_class=payload["vintage_class"],
            point_in_time_certified=payload["point_in_time_certified"],
            certification_blockers=_string_sequence(
                payload["certification_blockers"], field="certification_blockers"
            ),
            data_quality_flags=_string_sequence(
                payload["data_quality_flags"], field="data_quality_flags"
            ),
            state_checkpoint_ids=_string_sequence(
                payload["state_checkpoint_ids"], field="state_checkpoint_ids"
            ),
            universe_snapshot_id=payload["universe_snapshot_id"],
        )
        _require_digest(
            payload["information_set_id"],
            item.information_set_id,
            field="information_set_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class EligibilityDecisionV3:
    """Deterministic primary-signal cohort decision, not a portfolio decision."""

    information_set_id: str
    information_set_record_hash: str
    primary_candidate_id: str
    eligibility_policy_id: str
    input_state_hash: str
    observation_cutoff_ts: datetime
    evaluated_at: datetime
    verdict: EligibilityVerdict
    reason_codes: tuple[str, ...]
    vintage_class: VintageClass
    point_in_time_certified: bool

    def __post_init__(self) -> None:
        for field_name in (
            "information_set_id",
            "information_set_record_hash",
            "eligibility_policy_id",
            "input_state_hash",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "primary_candidate_id",
            canonical_hash(self.primary_candidate_id, field="primary_candidate_id"),
        )
        object.__setattr__(
            self,
            "observation_cutoff_ts",
            utc_datetime(self.observation_cutoff_ts, field="observation_cutoff_ts"),
        )
        object.__setattr__(
            self, "evaluated_at", utc_datetime(self.evaluated_at, field="evaluated_at")
        )
        if self.evaluated_at < self.observation_cutoff_ts:
            raise CanonicalizationError(
                "evaluated_at must not precede observation_cutoff_ts"
            )
        verdict = _enum(self.verdict, EligibilityVerdict, field="verdict")
        reasons = canonical_reason_codes(self.reason_codes, field="reason_codes")
        if verdict is EligibilityVerdict.ELIGIBLE and reasons:
            raise CanonicalizationError("ELIGIBLE must not carry rejection reasons")
        if verdict is not EligibilityVerdict.ELIGIBLE and not reasons:
            raise CanonicalizationError(
                "INELIGIBLE and ABSTAIN_DATA require at least one reason"
            )
        object.__setattr__(self, "verdict", verdict)
        object.__setattr__(self, "reason_codes", reasons)
        vintage = _enum(self.vintage_class, VintageClass, field="vintage_class")
        certified = _strict_bool(
            self.point_in_time_certified, field="point_in_time_certified"
        )
        if vintage is VintageClass.NOMINAL_CURRENT_REVISION and certified:
            raise CanonicalizationError(
                "NOMINAL_CURRENT_REVISION cannot be point-in-time certified"
            )
        object.__setattr__(self, "vintage_class", vintage)
        object.__setattr__(self, "point_in_time_certified", certified)

    def eligibility_key_payload(self) -> dict[str, Any]:
        return {
            "eligibility_policy_id": self.eligibility_policy_id,
            "information_set_id": self.information_set_id,
            "information_set_record_hash": self.information_set_record_hash,
            "primary_candidate_id": self.primary_candidate_id,
        }

    @property
    def eligibility_key(self) -> str:
        return _identity("EligibilityKeyV3", self.eligibility_key_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            **self.eligibility_key_payload(),
            "input_state_hash": self.input_state_hash,
            "reason_codes": list(self.reason_codes),
            "verdict": _enum_value(self.verdict),
        }

    @property
    def eligibility_decision_id(self) -> str:
        return _identity("EligibilityDecisionV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "eligibility_decision_id": self.eligibility_decision_id,
            "eligibility_key": self.eligibility_key,
            "evaluated_at": utc_iso(self.evaluated_at),
            "observation_cutoff_ts": utc_iso(self.observation_cutoff_ts),
            "point_in_time_certified": self.point_in_time_certified,
            "vintage_class": _enum_value(self.vintage_class),
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("EligibilityDecisionV3", self.record_payload())

    @classmethod
    def create(
        cls,
        *,
        information_set: InformationSetV3,
        primary_candidate_id: str,
        eligibility_policy_id: str,
        input_state_hash: str,
        evaluated_at: datetime | str,
        verdict: EligibilityVerdict | str,
        reason_codes: Sequence[str],
    ) -> EligibilityDecisionV3:
        """Create eligibility with clocks and attestations inherited from its input."""

        item = cls(
            information_set_id=information_set.information_set_id,
            information_set_record_hash=information_set.record_hash,
            primary_candidate_id=primary_candidate_id,
            eligibility_policy_id=eligibility_policy_id,
            input_state_hash=input_state_hash,
            observation_cutoff_ts=information_set.observation_cutoff_ts,
            evaluated_at=evaluated_at,
            verdict=verdict,
            reason_codes=tuple(reason_codes),
            vintage_class=information_set.vintage_class,
            point_in_time_certified=information_set.point_in_time_certified,
        )
        item.validate_against(information_set)
        return item

    def validate_against(self, information_set: InformationSetV3) -> None:
        """Validate cross-record identity, causality, vintage, and certification."""

        if self.information_set_id != information_set.information_set_id:
            raise CanonicalizationError(
                "eligibility does not reference the supplied information set"
            )
        if self.information_set_record_hash != information_set.record_hash:
            raise CanonicalizationError(
                "eligibility does not bind the supplied information-set record"
            )
        if self.input_state_hash != information_set.feature_materialization_hash:
            raise CanonicalizationError(
                "eligibility input_state_hash must equal feature materialization hash"
            )
        if self.observation_cutoff_ts != information_set.observation_cutoff_ts:
            raise CanonicalizationError(
                "eligibility cutoff differs from the information-set cutoff"
            )
        if self.evaluated_at < information_set.assembled_at:
            raise CanonicalizationError(
                "eligibility was evaluated before the information set was assembled"
            )
        if self.vintage_class is not information_set.vintage_class:
            raise CanonicalizationError(
                "eligibility vintage differs from the information-set vintage"
            )
        if self.point_in_time_certified != information_set.point_in_time_certified:
            raise CanonicalizationError(
                "eligibility certification differs from the information set"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EligibilityDecisionV3:
        expected = {
            "canonicalization_version",
            "eligibility_decision_id",
            "eligibility_key",
            "eligibility_policy_id",
            "evaluated_at",
            "information_set_id",
            "information_set_record_hash",
            "input_state_hash",
            "observation_cutoff_ts",
            "point_in_time_certified",
            "primary_candidate_id",
            "reason_codes",
            "record_hash",
            "schema_version",
            "verdict",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="EligibilityDecisionV3")
        _require_versions(payload)
        item = cls(
            information_set_id=payload["information_set_id"],
            information_set_record_hash=payload["information_set_record_hash"],
            primary_candidate_id=payload["primary_candidate_id"],
            eligibility_policy_id=payload["eligibility_policy_id"],
            input_state_hash=payload["input_state_hash"],
            observation_cutoff_ts=payload["observation_cutoff_ts"],
            evaluated_at=payload["evaluated_at"],
            verdict=payload["verdict"],
            reason_codes=_string_sequence(
                payload["reason_codes"], field="reason_codes"
            ),
            vintage_class=payload["vintage_class"],
            point_in_time_certified=payload["point_in_time_certified"],
        )
        _require_digest(
            payload["eligibility_key"], item.eligibility_key, field="eligibility_key"
        )
        _require_digest(
            payload["eligibility_decision_id"],
            item.eligibility_decision_id,
            field="eligibility_decision_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionEventV3:
    """An eligible, immutable economic candidate sealed before its outcome."""

    information_set_id: str
    information_set_record_hash: str
    eligibility_decision_id: str
    eligibility_record_hash: str
    asset_id: str
    venue_id: str
    contract_id: str
    timeframe_id: str
    primary_signal_id: str
    primary_signal_version: str
    primary_signal_policy_id: str
    primary_signal_instance_id: str
    side: TradeSide
    decision_ts: datetime
    eligibility_evaluated_at: datetime
    earliest_order_submission_ts: datetime
    earliest_entry_ts: datetime
    entry_expiry_ts: datetime
    action_protocol_id: str
    label_protocol_id: str
    entry_scenario: EntryScenario
    barrier_policy_id: str
    cost_scenario_id: str
    risk_unit: str
    stop_r_multiple: str
    target_r_multiple: str
    max_holding_seconds: int
    vintage_class: VintageClass
    point_in_time_certified: bool
    certification_blockers: tuple[str, ...]
    eligibility_verdict: EligibilityVerdict = EligibilityVerdict.ELIGIBLE

    def __post_init__(self) -> None:
        for field_name in (
            "information_set_id",
            "information_set_record_hash",
            "eligibility_decision_id",
            "eligibility_record_hash",
            "primary_signal_policy_id",
            "action_protocol_id",
            "label_protocol_id",
            "barrier_policy_id",
            "cost_scenario_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "asset_id",
            "venue_id",
            "contract_id",
            "timeframe_id",
            "primary_signal_id",
            "primary_signal_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "primary_signal_instance_id",
            canonical_hash(
                self.primary_signal_instance_id,
                field="primary_signal_instance_id",
            ),
        )
        object.__setattr__(self, "side", _enum(self.side, TradeSide, field="side"))
        for field_name in (
            "decision_ts",
            "eligibility_evaluated_at",
            "earliest_order_submission_ts",
            "earliest_entry_ts",
            "entry_expiry_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.eligibility_evaluated_at > self.decision_ts:
            raise CanonicalizationError(
                "eligibility_evaluated_at must not exceed decision_ts"
            )
        if self.decision_ts > self.earliest_order_submission_ts:
            raise CanonicalizationError(
                "decision_ts must not exceed earliest_order_submission_ts"
            )
        if self.earliest_order_submission_ts >= self.earliest_entry_ts:
            raise CanonicalizationError(
                "earliest_order_submission_ts must precede earliest_entry_ts"
            )
        if self.earliest_entry_ts > self.entry_expiry_ts:
            raise CanonicalizationError(
                "earliest_entry_ts must not exceed entry_expiry_ts"
            )
        object.__setattr__(
            self,
            "entry_scenario",
            _enum(self.entry_scenario, EntryScenario, field="entry_scenario"),
        )
        object.__setattr__(
            self,
            "risk_unit",
            canonical_decimal(
                self.risk_unit, field="risk_unit", strictly_positive=True
            ),
        )
        for field_name in ("stop_r_multiple", "target_r_multiple"):
            object.__setattr__(
                self,
                field_name,
                canonical_decimal(
                    getattr(self, field_name),
                    field=field_name,
                    strictly_positive=True,
                ),
            )
        object.__setattr__(
            self,
            "max_holding_seconds",
            canonical_safe_int(
                self.max_holding_seconds,
                field="max_holding_seconds",
                minimum=1,
                maximum=MAX_HOLDING_SECONDS,
            ),
        )
        vintage = _enum(self.vintage_class, VintageClass, field="vintage_class")
        certified = _strict_bool(
            self.point_in_time_certified, field="point_in_time_certified"
        )
        blockers = canonical_reason_codes(
            self.certification_blockers, field="certification_blockers"
        )
        _validate_certification(vintage, certified, blockers)
        object.__setattr__(self, "vintage_class", vintage)
        object.__setattr__(self, "point_in_time_certified", certified)
        object.__setattr__(self, "certification_blockers", blockers)
        verdict = _enum(
            self.eligibility_verdict,
            EligibilityVerdict,
            field="eligibility_verdict",
        )
        if verdict is not EligibilityVerdict.ELIGIBLE:
            raise CanonicalizationError(
                "DecisionEventV3 may be created only for ELIGIBLE candidates"
            )
        object.__setattr__(self, "eligibility_verdict", verdict)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "action_protocol_id": self.action_protocol_id,
            "asset_id": self.asset_id,
            "barrier_policy_id": self.barrier_policy_id,
            "contract_id": self.contract_id,
            "cost_scenario_id": self.cost_scenario_id,
            "decision_ts": utc_iso(self.decision_ts),
            "earliest_entry_ts": utc_iso(self.earliest_entry_ts),
            "earliest_order_submission_ts": utc_iso(self.earliest_order_submission_ts),
            "entry_expiry_ts": utc_iso(self.entry_expiry_ts),
            "eligibility_decision_id": self.eligibility_decision_id,
            "eligibility_record_hash": self.eligibility_record_hash,
            "entry_scenario": _enum_value(self.entry_scenario),
            "information_set_id": self.information_set_id,
            "information_set_record_hash": self.information_set_record_hash,
            "label_protocol_id": self.label_protocol_id,
            "max_holding_seconds": self.max_holding_seconds,
            "primary_signal_id": self.primary_signal_id,
            "primary_signal_instance_id": self.primary_signal_instance_id,
            "primary_signal_policy_id": self.primary_signal_policy_id,
            "primary_signal_version": self.primary_signal_version,
            "risk_unit": self.risk_unit,
            "side": _enum_value(self.side),
            "stop_r_multiple": self.stop_r_multiple,
            "target_r_multiple": self.target_r_multiple,
            "timeframe_id": self.timeframe_id,
            "venue_id": self.venue_id,
            "vintage_class": _enum_value(self.vintage_class),
        }

    @property
    def decision_event_id(self) -> str:
        return _identity("DecisionEventV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "certification_blockers": list(self.certification_blockers),
            "decision_event_id": self.decision_event_id,
            "eligibility_evaluated_at": utc_iso(self.eligibility_evaluated_at),
            "eligibility_verdict": _enum_value(self.eligibility_verdict),
            "point_in_time_certified": self.point_in_time_certified,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("DecisionEventV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def create(
        cls,
        *,
        information_set: InformationSetV3,
        eligibility: EligibilityDecisionV3,
        **values: Any,
    ) -> DecisionEventV3:
        """Create an event while checking linked InformationSet/eligibility facts."""

        eligibility.validate_against(information_set)
        if eligibility.verdict is not EligibilityVerdict.ELIGIBLE:
            raise CanonicalizationError(
                "only ELIGIBLE candidates become decision events"
            )
        linked_values: dict[str, Any] = {
            "asset_id": information_set.asset_id,
            "venue_id": information_set.venue_id,
            "contract_id": information_set.contract_id,
            "timeframe_id": information_set.timeframe_id,
            "primary_signal_instance_id": eligibility.primary_candidate_id,
            "vintage_class": information_set.vintage_class,
            "point_in_time_certified": information_set.point_in_time_certified,
            "certification_blockers": information_set.certification_blockers,
        }
        for field_name, expected in linked_values.items():
            if field_name not in values:
                continue
            supplied = values.pop(field_name)
            if field_name == "vintage_class":
                supplied = _enum(supplied, VintageClass, field=field_name)
            elif field_name == "certification_blockers":
                supplied = canonical_reason_codes(supplied, field=field_name)
            if supplied != expected:
                raise CanonicalizationError(
                    f"{field_name} does not match the linked records"
                )
        if "decision_ts" not in values:
            raise CanonicalizationError("decision_ts is required")
        decision_ts = utc_datetime(values["decision_ts"], field="decision_ts")
        if decision_ts < information_set.assembled_at:
            raise CanonicalizationError(
                "decision_ts must not precede information-set assembly"
            )
        item = cls(
            information_set_id=information_set.information_set_id,
            information_set_record_hash=information_set.record_hash,
            eligibility_decision_id=eligibility.eligibility_decision_id,
            eligibility_record_hash=eligibility.record_hash,
            eligibility_evaluated_at=eligibility.evaluated_at,
            eligibility_verdict=eligibility.verdict,
            **linked_values,
            **values,
        )
        item.validate_against(information_set, eligibility)
        return item

    def validate_against(
        self,
        information_set: InformationSetV3,
        eligibility: EligibilityDecisionV3,
    ) -> None:
        """Validate the complete pre-outcome record graph."""

        eligibility.validate_against(information_set)
        if self.information_set_id != information_set.information_set_id:
            raise CanonicalizationError("event references a different information set")
        if self.information_set_record_hash != information_set.record_hash:
            raise CanonicalizationError(
                "event references a different information-set record"
            )
        if self.eligibility_decision_id != eligibility.eligibility_decision_id:
            raise CanonicalizationError(
                "event references a different eligibility decision"
            )
        if self.eligibility_record_hash != eligibility.record_hash:
            raise CanonicalizationError(
                "event references a different eligibility-decision record"
            )
        if eligibility.verdict is not EligibilityVerdict.ELIGIBLE:
            raise CanonicalizationError(
                "only ELIGIBLE candidates become decision events"
            )
        expected_values = {
            "asset_id": information_set.asset_id,
            "venue_id": information_set.venue_id,
            "contract_id": information_set.contract_id,
            "timeframe_id": information_set.timeframe_id,
            "primary_signal_instance_id": eligibility.primary_candidate_id,
            "vintage_class": information_set.vintage_class,
            "point_in_time_certified": information_set.point_in_time_certified,
            "certification_blockers": information_set.certification_blockers,
            "eligibility_evaluated_at": eligibility.evaluated_at,
        }
        for field_name, expected in expected_values.items():
            if getattr(self, field_name) != expected:
                raise CanonicalizationError(
                    f"event {field_name} differs from the linked records"
                )
        if self.decision_ts < information_set.assembled_at:
            raise CanonicalizationError(
                "decision_ts must not precede information-set assembly"
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> DecisionEventV3:
        expected = {
            "action_protocol_id",
            "asset_id",
            "barrier_policy_id",
            "canonicalization_version",
            "certification_blockers",
            "contract_id",
            "cost_scenario_id",
            "decision_event_id",
            "decision_ts",
            "earliest_entry_ts",
            "earliest_order_submission_ts",
            "entry_expiry_ts",
            "eligibility_decision_id",
            "eligibility_record_hash",
            "eligibility_evaluated_at",
            "eligibility_verdict",
            "entry_scenario",
            "information_set_id",
            "information_set_record_hash",
            "label_protocol_id",
            "max_holding_seconds",
            "point_in_time_certified",
            "primary_signal_id",
            "primary_signal_instance_id",
            "primary_signal_policy_id",
            "primary_signal_version",
            "record_hash",
            "risk_unit",
            "schema_version",
            "side",
            "stop_r_multiple",
            "target_r_multiple",
            "timeframe_id",
            "venue_id",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="DecisionEventV3")
        _require_versions(payload)
        item = cls(
            information_set_id=payload["information_set_id"],
            information_set_record_hash=payload["information_set_record_hash"],
            eligibility_decision_id=payload["eligibility_decision_id"],
            eligibility_record_hash=payload["eligibility_record_hash"],
            asset_id=payload["asset_id"],
            venue_id=payload["venue_id"],
            contract_id=payload["contract_id"],
            timeframe_id=payload["timeframe_id"],
            primary_signal_id=payload["primary_signal_id"],
            primary_signal_version=payload["primary_signal_version"],
            primary_signal_policy_id=payload["primary_signal_policy_id"],
            primary_signal_instance_id=payload["primary_signal_instance_id"],
            side=payload["side"],
            decision_ts=payload["decision_ts"],
            eligibility_evaluated_at=payload["eligibility_evaluated_at"],
            earliest_order_submission_ts=payload["earliest_order_submission_ts"],
            earliest_entry_ts=payload["earliest_entry_ts"],
            entry_expiry_ts=payload["entry_expiry_ts"],
            action_protocol_id=payload["action_protocol_id"],
            label_protocol_id=payload["label_protocol_id"],
            entry_scenario=payload["entry_scenario"],
            barrier_policy_id=payload["barrier_policy_id"],
            cost_scenario_id=payload["cost_scenario_id"],
            risk_unit=payload["risk_unit"],
            stop_r_multiple=payload["stop_r_multiple"],
            target_r_multiple=payload["target_r_multiple"],
            max_holding_seconds=payload["max_holding_seconds"],
            vintage_class=payload["vintage_class"],
            point_in_time_certified=payload["point_in_time_certified"],
            certification_blockers=_string_sequence(
                payload["certification_blockers"], field="certification_blockers"
            ),
            eligibility_verdict=payload["eligibility_verdict"],
        )
        _require_digest(
            payload["decision_event_id"],
            item.decision_event_id,
            field="decision_event_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class BarrierActivationV3:
    """Entry fill and exact barriers activated before outcome-path resolution."""

    decision_event_id: str
    barrier_policy_id: str
    entry_evidence_revision_id: str
    actual_entry_ts: datetime
    entry_price: str
    stop_price: str
    target_price: str
    evidence_available_at: datetime
    activated_at: datetime
    vintage_class: VintageClass
    point_in_time_certified: bool
    certification_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "decision_event_id",
            "barrier_policy_id",
            "entry_evidence_revision_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in ("actual_entry_ts", "evidence_available_at", "activated_at"):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.actual_entry_ts > self.evidence_available_at:
            raise CanonicalizationError(
                "actual_entry_ts must not exceed evidence_available_at"
            )
        if self.evidence_available_at > self.activated_at:
            raise CanonicalizationError(
                "evidence_available_at must not exceed activated_at"
            )
        for field_name in ("entry_price", "stop_price", "target_price"):
            object.__setattr__(
                self,
                field_name,
                canonical_decimal(
                    getattr(self, field_name),
                    field=field_name,
                    strictly_positive=True,
                ),
            )
        vintage = _enum(self.vintage_class, VintageClass, field="vintage_class")
        certified = _strict_bool(
            self.point_in_time_certified, field="point_in_time_certified"
        )
        blockers = canonical_reason_codes(
            self.certification_blockers, field="certification_blockers"
        )
        _validate_certification(vintage, certified, blockers)
        object.__setattr__(self, "vintage_class", vintage)
        object.__setattr__(self, "point_in_time_certified", certified)
        object.__setattr__(self, "certification_blockers", blockers)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "actual_entry_ts": utc_iso(self.actual_entry_ts),
            "barrier_policy_id": self.barrier_policy_id,
            "decision_event_id": self.decision_event_id,
            "entry_evidence_revision_id": self.entry_evidence_revision_id,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "vintage_class": _enum_value(self.vintage_class),
        }

    @property
    def barrier_activation_id(self) -> str:
        return _identity("BarrierActivationV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "activated_at": utc_iso(self.activated_at),
            "barrier_activation_id": self.barrier_activation_id,
            "certification_blockers": list(self.certification_blockers),
            "evidence_available_at": utc_iso(self.evidence_available_at),
            "point_in_time_certified": self.point_in_time_certified,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("BarrierActivationV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def create(
        cls,
        *,
        event: DecisionEventV3,
        entry_evidence_revision_id: str,
        actual_entry_ts: datetime | str,
        entry_price: Decimal | int | float | str,
        evidence_available_at: datetime | str,
        activated_at: datetime | str,
    ) -> BarrierActivationV3:
        entry = Decimal(canonical_decimal(entry_price, field="entry_price"))
        risk = Decimal(event.risk_unit)
        with localcontext() as context:
            context.prec = DECIMAL_ARITHMETIC_PRECISION
            stop_distance = risk * Decimal(event.stop_r_multiple)
            target_distance = risk * Decimal(event.target_r_multiple)
            if event.side is TradeSide.LONG:
                stop = entry - stop_distance
                target = entry + target_distance
            else:
                stop = entry + stop_distance
                target = entry - target_distance
        if stop <= 0 or target <= 0:
            raise CanonicalizationError(
                "frozen risk/barrier geometry produces a nonpositive price"
            )
        item = cls(
            decision_event_id=event.decision_event_id,
            barrier_policy_id=event.barrier_policy_id,
            entry_evidence_revision_id=entry_evidence_revision_id,
            actual_entry_ts=actual_entry_ts,
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            evidence_available_at=evidence_available_at,
            activated_at=activated_at,
            vintage_class=event.vintage_class,
            point_in_time_certified=event.point_in_time_certified,
            certification_blockers=event.certification_blockers,
        )
        item.validate_against(event)
        return item

    def validate_against(self, event: DecisionEventV3) -> None:
        if self.decision_event_id != event.decision_event_id:
            raise CanonicalizationError("activation references a different event")
        if self.barrier_policy_id != event.barrier_policy_id:
            raise CanonicalizationError("activation barrier policy differs from event")
        if self.vintage_class is not event.vintage_class:
            raise CanonicalizationError("activation vintage differs from event")
        if self.point_in_time_certified != event.point_in_time_certified:
            raise CanonicalizationError("activation certification differs from event")
        if self.certification_blockers != event.certification_blockers:
            raise CanonicalizationError("activation blockers differ from event")
        if not event.earliest_entry_ts <= self.actual_entry_ts <= event.entry_expiry_ts:
            raise CanonicalizationError(
                "activation entry lies outside the event's frozen entry window"
            )
        entry = Decimal(self.entry_price)
        risk = Decimal(event.risk_unit)
        with localcontext() as context:
            context.prec = DECIMAL_ARITHMETIC_PRECISION
            expected_stop_distance = risk * Decimal(event.stop_r_multiple)
            expected_target_distance = risk * Decimal(event.target_r_multiple)
            if event.side is TradeSide.LONG:
                stop_distance = entry - Decimal(self.stop_price)
                target_distance = Decimal(self.target_price) - entry
            else:
                stop_distance = Decimal(self.stop_price) - entry
                target_distance = entry - Decimal(self.target_price)
        if stop_distance != expected_stop_distance:
            raise CanonicalizationError(
                "activated stop differs from frozen event geometry"
            )
        if target_distance != expected_target_distance:
            raise CanonicalizationError(
                "activated target differs from frozen event geometry"
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> BarrierActivationV3:
        expected = {
            "activated_at",
            "actual_entry_ts",
            "barrier_activation_id",
            "barrier_policy_id",
            "canonicalization_version",
            "certification_blockers",
            "decision_event_id",
            "entry_evidence_revision_id",
            "entry_price",
            "evidence_available_at",
            "point_in_time_certified",
            "record_hash",
            "schema_version",
            "stop_price",
            "target_price",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="BarrierActivationV3")
        _require_versions(payload)
        item = cls(
            decision_event_id=payload["decision_event_id"],
            barrier_policy_id=payload["barrier_policy_id"],
            entry_evidence_revision_id=payload["entry_evidence_revision_id"],
            actual_entry_ts=payload["actual_entry_ts"],
            entry_price=payload["entry_price"],
            stop_price=payload["stop_price"],
            target_price=payload["target_price"],
            evidence_available_at=payload["evidence_available_at"],
            activated_at=payload["activated_at"],
            vintage_class=payload["vintage_class"],
            point_in_time_certified=payload["point_in_time_certified"],
            certification_blockers=_string_sequence(
                payload["certification_blockers"], field="certification_blockers"
            ),
        )
        _require_digest(
            payload["barrier_activation_id"],
            item.barrier_activation_id,
            field="barrier_activation_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class CostComponentV3:
    """One nonnegative, itemized cost known no later than label maturity."""

    name: str
    bps: str
    known_at: datetime
    evidence_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", canonical_identifier(self.name, field="name"))
        object.__setattr__(
            self, "bps", canonical_decimal(self.bps, field="bps", minimum=0)
        )
        object.__setattr__(
            self, "known_at", utc_datetime(self.known_at, field="known_at")
        )
        object.__setattr__(
            self,
            "evidence_id",
            canonical_hash(self.evidence_id, field="evidence_id"),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "bps": self.bps,
            "evidence_id": self.evidence_id,
            "known_at": utc_iso(self.known_at),
            "name": self.name,
        }

    @property
    def cost_component_id(self) -> str:
        return _identity("CostComponentV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "cost_component_id": self.cost_component_id,
            **self.identity_payload(),
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CostComponentV3:
        expected = {
            "bps",
            "canonicalization_version",
            "cost_component_id",
            "evidence_id",
            "known_at",
            "name",
            "schema_version",
        }
        require_exact_keys(payload, expected=expected, context="CostComponentV3")
        _require_versions(payload)
        item = cls(
            name=payload["name"],
            bps=payload["bps"],
            known_at=payload["known_at"],
            evidence_id=payload["evidence_id"],
        )
        _require_digest(
            payload["cost_component_id"],
            item.cost_component_id,
            field="cost_component_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class LabelOutcomeV3:
    """Append-only outcome evidence linked to an unchanged DecisionEventV3."""

    decision_event_id: str
    label_protocol_id: str
    cost_scenario_id: str
    execution_mode: ExecutionMode
    outcome: BarrierOutcomeV3
    label_interval_start_ts: datetime
    label_interval_end_ts: datetime
    outcome_ts: datetime
    barrier_trigger_ts: datetime | None
    barrier_trigger_price: str | None
    barrier_trigger_evidence_revision_id: str | None
    evidence_available_at: datetime
    label_known_ts: datetime
    path_evidence_root: str
    vintage_class: VintageClass
    barrier_activation_id: str | None = None
    barrier_activation_record_hash: str | None = None
    cost_components: tuple[CostComponentV3, ...] = ()
    actual_entry_ts: datetime | None = None
    entry_price: str | None = None
    exit_price: str | None = None
    stop_price: str | None = None
    target_price: str | None = None
    entry_evidence_revision_id: str | None = None
    exit_evidence_revision_id: str | None = None
    gross_return_bps: str | None = None
    net_return_bps: str | None = None
    r_multiple: str | None = None
    mae_bps: str | None = None
    mfe_bps: str | None = None
    gap_loss_bps: str | None = None
    ambiguity_resolution: AmbiguityResolution | None = None
    gross_return_lower_bound_bps: str | None = None
    gross_return_upper_bound_bps: str | None = None
    supersedes_label_outcome_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "decision_event_id",
            "label_protocol_id",
            "cost_scenario_id",
            "path_evidence_root",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "barrier_activation_id",
            _optional_hash(
                self.barrier_activation_id,
                field="barrier_activation_id",
            ),
        )
        object.__setattr__(
            self,
            "barrier_activation_record_hash",
            _optional_hash(
                self.barrier_activation_record_hash,
                field="barrier_activation_record_hash",
            ),
        )
        object.__setattr__(
            self,
            "supersedes_label_outcome_id",
            _optional_hash(
                self.supersedes_label_outcome_id,
                field="supersedes_label_outcome_id",
            ),
        )
        object.__setattr__(
            self,
            "barrier_trigger_evidence_revision_id",
            _optional_hash(
                self.barrier_trigger_evidence_revision_id,
                field="barrier_trigger_evidence_revision_id",
            ),
        )
        object.__setattr__(
            self,
            "entry_evidence_revision_id",
            _optional_hash(
                self.entry_evidence_revision_id,
                field="entry_evidence_revision_id",
            ),
        )
        object.__setattr__(
            self,
            "exit_evidence_revision_id",
            _optional_hash(
                self.exit_evidence_revision_id,
                field="exit_evidence_revision_id",
            ),
        )
        object.__setattr__(
            self,
            "execution_mode",
            _enum(self.execution_mode, ExecutionMode, field="execution_mode"),
        )
        outcome = _enum(self.outcome, BarrierOutcomeV3, field="outcome")
        object.__setattr__(self, "outcome", outcome)
        vintage = _enum(self.vintage_class, VintageClass, field="vintage_class")
        object.__setattr__(self, "vintage_class", vintage)
        for field_name in (
            "label_interval_start_ts",
            "label_interval_end_ts",
            "outcome_ts",
            "evidence_available_at",
            "label_known_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "actual_entry_ts",
            _optional_timestamp(self.actual_entry_ts, field="actual_entry_ts"),
        )
        object.__setattr__(
            self,
            "barrier_trigger_ts",
            _optional_timestamp(self.barrier_trigger_ts, field="barrier_trigger_ts"),
        )
        if self.label_interval_start_ts > self.label_interval_end_ts:
            raise CanonicalizationError(
                "label_interval_start_ts must not exceed label_interval_end_ts"
            )
        if not (
            self.label_interval_start_ts
            <= self.outcome_ts
            <= self.label_interval_end_ts
        ):
            raise CanonicalizationError("outcome_ts must lie inside the label interval")
        if self.evidence_available_at < self.outcome_ts:
            raise CanonicalizationError(
                "evidence_available_at must not precede outcome_ts"
            )
        if self.label_known_ts < self.evidence_available_at:
            raise CanonicalizationError(
                "label_known_ts must not precede evidence_available_at"
            )

        costs = tuple(self.cost_components)
        if not all(isinstance(item, CostComponentV3) for item in costs):
            raise CanonicalizationError(
                "cost_components must contain CostComponentV3 records"
            )
        if len(costs) > MAX_COST_COMPONENTS:
            raise CanonicalizationError(
                f"cost_components must not exceed {MAX_COST_COMPONENTS} entries"
            )
        if len({item.cost_component_id for item in costs}) != len(costs):
            raise CanonicalizationError("cost_components contain duplicate identities")
        costs = tuple(sorted(costs, key=lambda item: item.cost_component_id))
        if any(item.known_at > self.label_known_ts for item in costs):
            raise CanonicalizationError("a cost was not known by label_known_ts")
        object.__setattr__(self, "cost_components", costs)

        for field_name in (
            "barrier_trigger_price",
            "entry_price",
            "exit_price",
            "stop_price",
            "target_price",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(
                    getattr(self, field_name), field=field_name, strictly_positive=True
                ),
            )
        for field_name in ("gross_return_bps", "net_return_bps", "r_multiple"):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "gross_return_lower_bound_bps",
            "gross_return_upper_bound_bps",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(getattr(self, field_name), field=field_name),
            )
        if self.ambiguity_resolution is not None:
            object.__setattr__(
                self,
                "ambiguity_resolution",
                _enum(
                    self.ambiguity_resolution,
                    AmbiguityResolution,
                    field="ambiguity_resolution",
                ),
            )
        for field_name in ("mae_bps", "mfe_bps", "gap_loss_bps"):
            object.__setattr__(
                self,
                field_name,
                _optional_decimal(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        self._validate_lifecycle()
        if self.supersedes_label_outcome_id == self.label_outcome_id:
            raise CanonicalizationError("a label outcome cannot supersede itself")

    @property
    def total_cost_bps(self) -> str:
        with localcontext() as context:
            context.prec = DECIMAL_ARITHMETIC_PRECISION
            total = sum(
                (Decimal(item.bps) for item in self.cost_components),
                Decimal("0"),
            )
        return canonical_decimal(total, field="total_cost_bps", minimum=0)

    @property
    def holding_duration_microseconds(self) -> int | None:
        if self.actual_entry_ts is None:
            return None
        delta = self.outcome_ts - self.actual_entry_ts
        return (
            delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
        )

    def _validate_lifecycle(self) -> None:
        filled_fields = {
            "actual_entry_ts": self.actual_entry_ts,
            "barrier_activation_id": self.barrier_activation_id,
            "barrier_activation_record_hash": self.barrier_activation_record_hash,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "entry_evidence_revision_id": self.entry_evidence_revision_id,
            "exit_evidence_revision_id": self.exit_evidence_revision_id,
            "gross_return_bps": self.gross_return_bps,
            "net_return_bps": self.net_return_bps,
            "r_multiple": self.r_multiple,
            "mae_bps": self.mae_bps,
            "mfe_bps": self.mfe_bps,
            "gap_loss_bps": self.gap_loss_bps,
        }
        if self.outcome in FILLED_OUTCOMES:
            missing = sorted(
                name for name, value in filled_fields.items() if value is None
            )
            if missing:
                raise CanonicalizationError(
                    f"filled outcome is missing required fields: {missing}"
                )
            assert self.actual_entry_ts is not None
            if not (
                self.actual_entry_ts <= self.label_interval_start_ts <= self.outcome_ts
            ):
                raise CanonicalizationError(
                    "label interval start must lie between actual entry and outcome"
                )
            assert self.gross_return_bps is not None
            assert self.net_return_bps is not None
            with localcontext() as context:
                context.prec = DECIMAL_ARITHMETIC_PRECISION
                expected_net = Decimal(self.gross_return_bps) - Decimal(
                    self.total_cost_bps
                )
            if Decimal(self.net_return_bps) != expected_net:
                raise CanonicalizationError(
                    "net_return_bps must equal gross_return_bps minus itemized costs"
                )
        elif self.outcome in UNFILLED_OUTCOMES:
            present = sorted(
                name for name, value in filled_fields.items() if value is not None
            )
            if present:
                raise CanonicalizationError(
                    f"unfilled outcome must not contain fill/return fields: {present}"
                )
            if self.cost_components:
                raise CanonicalizationError(
                    "unfilled outcome must not contain execution cost components"
                )
        else:  # pragma: no cover - exhaustive guard for future enum extension
            raise CanonicalizationError("unsupported outcome lifecycle")
        trigger_fields = {
            "barrier_trigger_ts": self.barrier_trigger_ts,
            "barrier_trigger_price": self.barrier_trigger_price,
            "barrier_trigger_evidence_revision_id": (
                self.barrier_trigger_evidence_revision_id
            ),
        }
        if self.outcome in {
            BarrierOutcomeV3.TP_FIRST,
            BarrierOutcomeV3.SL_FIRST,
        }:
            missing_trigger = sorted(
                name for name, value in trigger_fields.items() if value is None
            )
            if missing_trigger:
                raise CanonicalizationError(
                    f"barrier outcome is missing trigger evidence: {missing_trigger}"
                )
            assert self.barrier_trigger_ts is not None
            if not (
                self.label_interval_start_ts
                <= self.barrier_trigger_ts
                <= self.outcome_ts
            ):
                raise CanonicalizationError(
                    "barrier_trigger_ts must lie inside the resolved label path"
                )
        else:
            present_trigger = sorted(
                name for name, value in trigger_fields.items() if value is not None
            )
            if present_trigger:
                raise CanonicalizationError(
                    f"non-barrier outcome must not contain trigger fields: {present_trigger}"
                )
        bounds = (
            self.gross_return_lower_bound_bps,
            self.gross_return_upper_bound_bps,
        )
        if self.outcome is BarrierOutcomeV3.AMBIGUOUS:
            if (
                self.ambiguity_resolution
                is not AmbiguityResolution.CONSERVATIVE_LOWER_BOUND
                or any(value is None for value in bounds)
            ):
                raise CanonicalizationError(
                    "AMBIGUOUS requires conservative lower/upper return bounds"
                )
            lower = Decimal(self.gross_return_lower_bound_bps or "0")
            upper = Decimal(self.gross_return_upper_bound_bps or "0")
            if lower > upper:
                raise CanonicalizationError(
                    "ambiguous gross-return lower bound exceeds upper bound"
                )
            if self.gross_return_bps is None or Decimal(self.gross_return_bps) != lower:
                raise CanonicalizationError(
                    "AMBIGUOUS gross return must equal its conservative lower bound"
                )
        elif self.ambiguity_resolution is not None or any(
            value is not None for value in bounds
        ):
            raise CanonicalizationError(
                "ambiguity resolution and bounds require AMBIGUOUS outcome"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "actual_entry_ts": (
                None if self.actual_entry_ts is None else utc_iso(self.actual_entry_ts)
            ),
            "ambiguity_resolution": (
                None
                if self.ambiguity_resolution is None
                else _enum_value(self.ambiguity_resolution)
            ),
            "barrier_activation_id": self.barrier_activation_id,
            "barrier_activation_record_hash": self.barrier_activation_record_hash,
            "barrier_trigger_evidence_revision_id": (
                self.barrier_trigger_evidence_revision_id
            ),
            "barrier_trigger_price": self.barrier_trigger_price,
            "barrier_trigger_ts": (
                None
                if self.barrier_trigger_ts is None
                else utc_iso(self.barrier_trigger_ts)
            ),
            "cost_components": [item.as_dict() for item in self.cost_components],
            "cost_scenario_id": self.cost_scenario_id,
            "decision_event_id": self.decision_event_id,
            "entry_evidence_revision_id": self.entry_evidence_revision_id,
            "entry_price": self.entry_price,
            "evidence_available_at": utc_iso(self.evidence_available_at),
            "execution_mode": _enum_value(self.execution_mode),
            "exit_evidence_revision_id": self.exit_evidence_revision_id,
            "exit_price": self.exit_price,
            "gap_loss_bps": self.gap_loss_bps,
            "gross_return_bps": self.gross_return_bps,
            "gross_return_lower_bound_bps": self.gross_return_lower_bound_bps,
            "gross_return_upper_bound_bps": self.gross_return_upper_bound_bps,
            "holding_duration_microseconds": self.holding_duration_microseconds,
            "label_interval_end_ts": utc_iso(self.label_interval_end_ts),
            "label_interval_start_ts": utc_iso(self.label_interval_start_ts),
            "label_known_ts": utc_iso(self.label_known_ts),
            "label_protocol_id": self.label_protocol_id,
            "mae_bps": self.mae_bps,
            "mfe_bps": self.mfe_bps,
            "net_return_bps": self.net_return_bps,
            "outcome": _enum_value(self.outcome),
            "outcome_ts": utc_iso(self.outcome_ts),
            "path_evidence_root": self.path_evidence_root,
            "r_multiple": self.r_multiple,
            "stop_price": self.stop_price,
            "supersedes_label_outcome_id": self.supersedes_label_outcome_id,
            "target_price": self.target_price,
            "total_cost_bps": self.total_cost_bps,
            "vintage_class": _enum_value(self.vintage_class),
        }

    @property
    def label_outcome_id(self) -> str:
        return _identity("LabelOutcomeV3", self.identity_payload())

    @property
    def record_hash(self) -> str:
        return _record_hash(
            "LabelOutcomeV3",
            {**self.identity_payload(), "label_outcome_id": self.label_outcome_id},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "label_outcome_id": self.label_outcome_id,
            "record_hash": self.record_hash,
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    def validate_against(
        self,
        event: DecisionEventV3,
        activation: BarrierActivationV3 | None = None,
    ) -> None:
        """Validate cross-record clocks and frozen policy references."""

        if self.decision_event_id != event.decision_event_id:
            raise CanonicalizationError("outcome references a different decision event")
        if self.label_protocol_id != event.label_protocol_id:
            raise CanonicalizationError("label_protocol_id differs from decision event")
        if self.cost_scenario_id != event.cost_scenario_id:
            raise CanonicalizationError("cost_scenario_id differs from decision event")
        if self.vintage_class is not event.vintage_class:
            raise CanonicalizationError("vintage_class differs from decision event")
        expected_mode = {
            EntryScenario.NEXT_REAL_BASE_BAR_OPEN: ExecutionMode.HISTORICAL_NOMINAL_SCENARIO,
            EntryScenario.FORWARD_MARKET_ORDER: ExecutionMode.FORWARD_PAPER,
            EntryScenario.LIVE_MARKET_ORDER: ExecutionMode.LIVE_ACTUAL,
        }[event.entry_scenario]
        if self.execution_mode is not expected_mode:
            raise CanonicalizationError(
                "execution_mode is incompatible with the event entry scenario"
            )
        if self.label_interval_start_ts < event.earliest_entry_ts:
            raise CanonicalizationError(
                "label interval starts before the event's earliest entry"
            )
        try:
            latest_possible_outcome = event.entry_expiry_ts + timedelta(
                seconds=event.max_holding_seconds
            )
        except OverflowError as exc:
            raise CanonicalizationError(
                "event holding horizon exceeds the supported datetime range"
            ) from exc
        if self.label_interval_end_ts > latest_possible_outcome:
            raise CanonicalizationError(
                "label interval exceeds the frozen entry and holding horizon"
            )
        if self.actual_entry_ts is not None:
            if activation is None:
                raise CanonicalizationError(
                    "filled outcome requires its barrier activation record"
                )
            activation.validate_against(event)
            if self.barrier_activation_id != activation.barrier_activation_id:
                raise CanonicalizationError(
                    "outcome references a different barrier activation"
                )
            if self.barrier_activation_record_hash != activation.record_hash:
                raise CanonicalizationError(
                    "outcome references a different barrier-activation record"
                )
            activation_values = {
                "actual_entry_ts": activation.actual_entry_ts,
                "entry_evidence_revision_id": activation.entry_evidence_revision_id,
                "entry_price": activation.entry_price,
                "stop_price": activation.stop_price,
                "target_price": activation.target_price,
            }
            for field_name, expected in activation_values.items():
                if getattr(self, field_name) != expected:
                    raise CanonicalizationError(
                        f"outcome {field_name} differs from barrier activation"
                    )
            if not (
                event.earliest_entry_ts <= self.actual_entry_ts <= event.entry_expiry_ts
            ):
                raise CanonicalizationError(
                    "actual entry lies outside the event's frozen entry window"
                )
            holding_deadline = self.actual_entry_ts + timedelta(
                seconds=event.max_holding_seconds
            )
            if self.outcome_ts > holding_deadline:
                raise CanonicalizationError(
                    "outcome exceeds max_holding_seconds from actual entry"
                )
            if (
                self.outcome is BarrierOutcomeV3.TIMEOUT
                and self.outcome_ts != holding_deadline
            ):
                raise CanonicalizationError(
                    "TIMEOUT must mature at the frozen holding deadline"
                )
            if self.label_interval_start_ts != activation.activated_at:
                raise CanonicalizationError(
                    "filled label interval must start when barriers become active"
                )
            if activation.activated_at > self.outcome_ts:
                raise CanonicalizationError(
                    "barrier activation occurs after the resolved outcome"
                )
            self._validate_basic_economics(event)
        else:
            if activation is not None:
                raise CanonicalizationError(
                    "unfilled outcome must not carry a barrier activation record"
                )
            if self.label_interval_start_ts != event.earliest_entry_ts:
                raise CanonicalizationError(
                    "unfilled label interval must start at earliest_entry_ts"
                )
            if self.outcome_ts > event.entry_expiry_ts:
                raise CanonicalizationError(
                    "unfilled outcome occurs after the frozen entry expiry"
                )
        if (
            self.outcome is BarrierOutcomeV3.NO_FILL
            and self.outcome_ts != event.entry_expiry_ts
        ):
            raise CanonicalizationError("NO_FILL must mature at entry_expiry_ts")

    def _validate_basic_economics(self, event: DecisionEventV3) -> None:
        """Check protocol-independent direction and barrier geometry invariants."""

        assert self.entry_price is not None
        assert self.exit_price is not None
        assert self.stop_price is not None
        assert self.target_price is not None
        assert self.gross_return_bps is not None
        assert self.r_multiple is not None
        entry = Decimal(self.entry_price)
        exit_price = Decimal(self.exit_price)
        stop = Decimal(self.stop_price)
        target = Decimal(self.target_price)
        gross = Decimal(self.gross_return_bps)
        r_multiple = Decimal(self.r_multiple)
        with localcontext() as context:
            context.prec = DECIMAL_ARITHMETIC_PRECISION
            if event.side is TradeSide.LONG:
                if not stop < entry < target:
                    raise CanonicalizationError(
                        "LONG requires stop_price < entry_price < target_price"
                    )
                price_pnl = exit_price - entry
                stop_pnl = stop - entry
                target_pnl = target - entry
            else:
                if not target < entry < stop:
                    raise CanonicalizationError(
                        "SHORT requires target_price < entry_price < stop_price"
                    )
                price_pnl = entry - exit_price
                stop_pnl = entry - stop
                target_pnl = entry - target
            expected_gross = (price_pnl / entry * Decimal("10000")).quantize(
                RETURN_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
            expected_r = (price_pnl / Decimal(event.risk_unit)).quantize(
                RETURN_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
            stop_gross = (stop_pnl / entry * Decimal("10000")).quantize(
                RETURN_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
            target_gross = (target_pnl / entry * Decimal("10000")).quantize(
                RETURN_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )
            stop_r = (stop_pnl / Decimal(event.risk_unit)).quantize(
                RETURN_QUANTUM,
                rounding=ROUND_HALF_EVEN,
            )

        if self.outcome in {BarrierOutcomeV3.TP_FIRST, BarrierOutcomeV3.SL_FIRST}:
            assert self.barrier_trigger_price is not None
            trigger = Decimal(self.barrier_trigger_price)
            if self.outcome is BarrierOutcomeV3.TP_FIRST:
                trigger_reached_barrier = (
                    trigger >= target
                    if event.side is TradeSide.LONG
                    else trigger <= target
                )
                nominal_exit_reached_barrier = (
                    exit_price >= target
                    if event.side is TradeSide.LONG
                    else exit_price <= target
                )
                barrier_name = "target"
            else:
                trigger_reached_barrier = (
                    trigger <= stop if event.side is TradeSide.LONG else trigger >= stop
                )
                nominal_exit_reached_barrier = (
                    exit_price <= stop
                    if event.side is TradeSide.LONG
                    else exit_price >= stop
                )
                barrier_name = "stop"
            if not trigger_reached_barrier:
                raise CanonicalizationError(
                    f"{self.outcome.value} trigger price did not reach the frozen "
                    f"{barrier_name}"
                )
            if (
                self.execution_mode
                in {
                    ExecutionMode.HISTORICAL_NOMINAL_SCENARIO,
                    ExecutionMode.FORWARD_PAPER,
                }
                and not nominal_exit_reached_barrier
            ):
                raise CanonicalizationError(
                    f"{self.outcome.value} nominal exit price did not reach the "
                    f"frozen {barrier_name}"
                )

        if self.outcome is BarrierOutcomeV3.AMBIGUOUS:
            if exit_price != stop:
                raise CanonicalizationError(
                    "AMBIGUOUS conservative exit_price must equal the frozen stop"
                )
            expected_lower = canonical_decimal(
                stop_gross,
                field="expected_ambiguous_lower_bound_bps",
            )
            expected_upper = canonical_decimal(
                target_gross,
                field="expected_ambiguous_upper_bound_bps",
            )
            if self.gross_return_lower_bound_bps != expected_lower:
                raise CanonicalizationError(
                    "AMBIGUOUS lower bound must equal the frozen stop-first return"
                )
            if self.gross_return_upper_bound_bps != expected_upper:
                raise CanonicalizationError(
                    "AMBIGUOUS upper bound must equal the frozen target-first return"
                )
            if self.r_multiple != canonical_decimal(
                stop_r,
                field="expected_ambiguous_r_multiple",
            ):
                raise CanonicalizationError(
                    "AMBIGUOUS r_multiple must equal the frozen stop-first outcome"
                )

        if (price_pnl > 0) != (gross > 0) or (price_pnl < 0) != (gross < 0):
            raise CanonicalizationError(
                "gross_return_bps sign disagrees with side-adjusted price movement"
            )
        if (price_pnl > 0) != (r_multiple > 0) or (price_pnl < 0) != (r_multiple < 0):
            raise CanonicalizationError(
                "r_multiple sign disagrees with side-adjusted price movement"
            )
        if self.outcome is BarrierOutcomeV3.TP_FIRST and price_pnl <= 0:
            raise CanonicalizationError("TP_FIRST must have positive gross price PnL")
        if self.outcome is BarrierOutcomeV3.SL_FIRST and price_pnl >= 0:
            raise CanonicalizationError("SL_FIRST must have negative gross price PnL")
        if canonical_decimal(expected_gross, field="expected_gross_return_bps") != (
            self.gross_return_bps
        ):
            raise CanonicalizationError(
                "gross_return_bps does not match entry/exit prices and side"
            )
        if (
            canonical_decimal(expected_r, field="expected_r_multiple")
            != self.r_multiple
        ):
            raise CanonicalizationError(
                "r_multiple does not match price PnL and frozen risk unit"
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> LabelOutcomeV3:
        expected = {
            "actual_entry_ts",
            "ambiguity_resolution",
            "barrier_activation_id",
            "barrier_activation_record_hash",
            "barrier_trigger_evidence_revision_id",
            "barrier_trigger_price",
            "barrier_trigger_ts",
            "canonicalization_version",
            "cost_components",
            "cost_scenario_id",
            "decision_event_id",
            "entry_evidence_revision_id",
            "entry_price",
            "evidence_available_at",
            "execution_mode",
            "exit_evidence_revision_id",
            "exit_price",
            "gap_loss_bps",
            "gross_return_bps",
            "gross_return_lower_bound_bps",
            "gross_return_upper_bound_bps",
            "holding_duration_microseconds",
            "label_interval_end_ts",
            "label_interval_start_ts",
            "label_known_ts",
            "label_outcome_id",
            "label_protocol_id",
            "mae_bps",
            "mfe_bps",
            "net_return_bps",
            "outcome",
            "outcome_ts",
            "path_evidence_root",
            "r_multiple",
            "record_hash",
            "schema_version",
            "stop_price",
            "supersedes_label_outcome_id",
            "target_price",
            "total_cost_bps",
            "vintage_class",
        }
        require_exact_keys(payload, expected=expected, context="LabelOutcomeV3")
        _require_versions(payload)
        raw_costs = payload["cost_components"]
        if not isinstance(raw_costs, list):
            raise CanonicalizationError("cost_components must be a JSON array")
        item = cls(
            decision_event_id=payload["decision_event_id"],
            label_protocol_id=payload["label_protocol_id"],
            cost_scenario_id=payload["cost_scenario_id"],
            execution_mode=payload["execution_mode"],
            outcome=payload["outcome"],
            label_interval_start_ts=payload["label_interval_start_ts"],
            label_interval_end_ts=payload["label_interval_end_ts"],
            outcome_ts=payload["outcome_ts"],
            barrier_trigger_ts=payload["barrier_trigger_ts"],
            barrier_trigger_price=payload["barrier_trigger_price"],
            barrier_trigger_evidence_revision_id=payload[
                "barrier_trigger_evidence_revision_id"
            ],
            evidence_available_at=payload["evidence_available_at"],
            label_known_ts=payload["label_known_ts"],
            path_evidence_root=payload["path_evidence_root"],
            vintage_class=payload["vintage_class"],
            barrier_activation_id=payload["barrier_activation_id"],
            barrier_activation_record_hash=payload["barrier_activation_record_hash"],
            cost_components=tuple(
                CostComponentV3.from_mapping(value) for value in raw_costs
            ),
            actual_entry_ts=payload["actual_entry_ts"],
            ambiguity_resolution=payload["ambiguity_resolution"],
            entry_price=payload["entry_price"],
            exit_price=payload["exit_price"],
            stop_price=payload["stop_price"],
            target_price=payload["target_price"],
            entry_evidence_revision_id=payload["entry_evidence_revision_id"],
            exit_evidence_revision_id=payload["exit_evidence_revision_id"],
            gross_return_bps=payload["gross_return_bps"],
            gross_return_lower_bound_bps=payload["gross_return_lower_bound_bps"],
            gross_return_upper_bound_bps=payload["gross_return_upper_bound_bps"],
            net_return_bps=payload["net_return_bps"],
            r_multiple=payload["r_multiple"],
            mae_bps=payload["mae_bps"],
            mfe_bps=payload["mfe_bps"],
            gap_loss_bps=payload["gap_loss_bps"],
            supersedes_label_outcome_id=payload["supersedes_label_outcome_id"],
        )
        _require_digest(
            payload["label_outcome_id"],
            item.label_outcome_id,
            field="label_outcome_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        if payload["total_cost_bps"] != item.total_cost_bps:
            raise CanonicalizationError("total_cost_bps does not match cost components")
        persisted_duration = payload["holding_duration_microseconds"]
        if persisted_duration is not None:
            persisted_duration = canonical_safe_int(
                persisted_duration,
                field="holding_duration_microseconds",
                minimum=0,
            )
        if persisted_duration != item.holding_duration_microseconds:
            raise CanonicalizationError(
                "holding_duration_microseconds does not match event clocks"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class EventDependenceAssignmentV3:
    """Population-derived overlap metadata kept outside intrinsic outcomes."""

    decision_event_id: str
    label_outcome_id: str
    dependence_policy_id: str
    event_cluster_id: str
    dependence_interval_start_ts: datetime
    dependence_interval_end_ts: datetime
    assignment_known_ts: datetime
    concurrency: int
    uniqueness_weight: str
    supersedes_assignment_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "decision_event_id",
            "label_outcome_id",
            "dependence_policy_id",
            "event_cluster_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "supersedes_assignment_id",
            _optional_hash(
                self.supersedes_assignment_id,
                field="supersedes_assignment_id",
            ),
        )
        for field_name in (
            "dependence_interval_start_ts",
            "dependence_interval_end_ts",
            "assignment_known_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.dependence_interval_start_ts > self.dependence_interval_end_ts:
            raise CanonicalizationError(
                "dependence interval start must not exceed its end"
            )
        if self.assignment_known_ts < self.dependence_interval_end_ts:
            raise CanonicalizationError(
                "assignment_known_ts must not precede dependence interval end"
            )
        object.__setattr__(
            self,
            "concurrency",
            canonical_safe_int(self.concurrency, field="concurrency", minimum=1),
        )
        weight = canonical_decimal(
            self.uniqueness_weight,
            field="uniqueness_weight",
            strictly_positive=True,
        )
        if Decimal(weight) > 1:
            raise CanonicalizationError("uniqueness_weight must not exceed 1")
        object.__setattr__(self, "uniqueness_weight", weight)
        if self.supersedes_assignment_id == self.assignment_id:
            raise CanonicalizationError("an assignment cannot supersede itself")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "assignment_known_ts": utc_iso(self.assignment_known_ts),
            "concurrency": self.concurrency,
            "decision_event_id": self.decision_event_id,
            "dependence_interval_end_ts": utc_iso(self.dependence_interval_end_ts),
            "dependence_interval_start_ts": utc_iso(self.dependence_interval_start_ts),
            "dependence_policy_id": self.dependence_policy_id,
            "event_cluster_id": self.event_cluster_id,
            "label_outcome_id": self.label_outcome_id,
            "supersedes_assignment_id": self.supersedes_assignment_id,
            "uniqueness_weight": self.uniqueness_weight,
        }

    @property
    def assignment_id(self) -> str:
        return _identity("EventDependenceAssignmentV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": CONTRACT_SCHEMA_VERSION,
        }

    def validate_against(
        self,
        event: DecisionEventV3,
        outcome: LabelOutcomeV3,
    ) -> None:
        if self.decision_event_id != event.decision_event_id:
            raise CanonicalizationError("assignment references a different event")
        if self.label_outcome_id != outcome.label_outcome_id:
            raise CanonicalizationError("assignment references a different outcome")
        if outcome.decision_event_id != event.decision_event_id:
            raise CanonicalizationError(
                "assignment event and outcome do not belong to the same graph"
            )
        if self.dependence_interval_start_ts != event.earliest_entry_ts:
            raise CanonicalizationError(
                "dependence interval must start at the event's earliest entry"
            )
        if self.dependence_interval_end_ts != outcome.label_known_ts:
            raise CanonicalizationError(
                "dependence interval must end when the label becomes known"
            )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EventDependenceAssignmentV3:
        expected = {
            "assignment_id",
            "assignment_known_ts",
            "canonicalization_version",
            "concurrency",
            "decision_event_id",
            "dependence_interval_end_ts",
            "dependence_interval_start_ts",
            "dependence_policy_id",
            "event_cluster_id",
            "label_outcome_id",
            "schema_version",
            "supersedes_assignment_id",
            "uniqueness_weight",
        }
        require_exact_keys(
            payload,
            expected=expected,
            context="EventDependenceAssignmentV3",
        )
        _require_versions(payload)
        item = cls(
            decision_event_id=payload["decision_event_id"],
            label_outcome_id=payload["label_outcome_id"],
            dependence_policy_id=payload["dependence_policy_id"],
            event_cluster_id=payload["event_cluster_id"],
            dependence_interval_start_ts=payload["dependence_interval_start_ts"],
            dependence_interval_end_ts=payload["dependence_interval_end_ts"],
            assignment_known_ts=payload["assignment_known_ts"],
            concurrency=payload["concurrency"],
            uniqueness_weight=payload["uniqueness_weight"],
            supersedes_assignment_id=payload["supersedes_assignment_id"],
        )
        _require_digest(
            payload["assignment_id"], item.assignment_id, field="assignment_id"
        )
        return item


def _require_versions(payload: Mapping[str, Any]) -> None:
    canonical_json_bytes(payload)
    if payload.get("schema_version") != CONTRACT_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported contract schema_version")
    if payload.get("canonicalization_version") != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")


def _require_digest(provided: Any, expected: str, *, field: str) -> None:
    normalized = canonical_hash(provided, field=field)
    if normalized != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _string_sequence(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CanonicalizationError(f"{field} must be a JSON array of strings")
    return tuple(value)


def _validate_certification(
    vintage: VintageClass,
    certified: bool,
    blockers: Sequence[str],
) -> None:
    if certified and blockers:
        raise CanonicalizationError(
            "point-in-time certified records must not carry certification blockers"
        )
    if not certified and not blockers:
        raise CanonicalizationError(
            "uncertified records require at least one certification blocker"
        )
    if vintage is VintageClass.NOMINAL_CURRENT_REVISION and certified:
        raise CanonicalizationError(
            "NOMINAL_CURRENT_REVISION cannot be point-in-time certified"
        )


__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "MAX_HOLDING_SECONDS",
    "BarrierActivationV3",
    "BarrierOutcomeV3",
    "AmbiguityResolution",
    "CostComponentV3",
    "DecisionEventV3",
    "EligibilityDecisionV3",
    "EligibilityVerdict",
    "EntryScenario",
    "EventDependenceAssignmentV3",
    "ExecutionMode",
    "InformationDependencyV3",
    "InformationSetV3",
    "LabelOutcomeV3",
    "TradeSide",
    "VintageClass",
]

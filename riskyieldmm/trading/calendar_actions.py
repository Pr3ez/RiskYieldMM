"""Authoritative schedule and action-resolution contracts for V3.2.

This module deliberately separates a *scheduled* action opportunity from
physical market-data and execution evidence.  A calendar snapshot is compiled
from immutable source bytes, an instrument mapping identifies the concrete
venue contract, and a frozen action protocol selects the first complete base
bar strictly after the order-ready clock.  No price row is consulted.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_reason_codes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .contracts import EntryScenario, InformationSetV3, TradeSide

CALENDAR_ACTION_SCHEMA_VERSION = "riskyieldmm_calendar_action_v3_2"
MAX_INTERVALS = 100_000
MAX_SEARCH_SECONDS = 31_557_600
MAX_EXECUTION_BAR_SECONDS = 86_400
MAX_ENTRY_WINDOW_BARS = 1_440
_TRADE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class CalendarAuthority(str, Enum):
    """Provenance class of the schedule input."""

    OFFICIAL_VENUE = "OFFICIAL_VENUE"
    OFFICIAL_REGULATOR = "OFFICIAL_REGULATOR"
    AUTHORIZED_VENDOR = "AUTHORIZED_VENDOR"
    SECONDARY_REFERENCE = "SECONDARY_REFERENCE"


_CERTIFYING_CALENDAR_AUTHORITIES = frozenset({CalendarAuthority.OFFICIAL_VENUE})


class ActionSelectionRule(str, Enum):
    """Frozen resolver algorithm."""

    NEXT_SCHEDULED_BASE_BAR_OPEN = "NEXT_SCHEDULED_BASE_BAR_OPEN"


class ActionResolutionStatus(str, Enum):
    """Whether the action request produced a scheduled entry window."""

    RESOLVED = "RESOLVED"
    ABSTAINED = "ABSTAINED"


class ActionAbstentionReason(str, Enum):
    """Stable fail-closed outcomes produced by the pure resolver."""

    CALENDAR_AUTHORITY_NOT_ALLOWED = "CALENDAR_AUTHORITY_NOT_ALLOWED"
    CALENDAR_NOT_KNOWN = "CALENDAR_NOT_KNOWN"
    CALENDAR_SCOPE_MISMATCH = "CALENDAR_SCOPE_MISMATCH"
    CALENDAR_COVERAGE_MISSING = "CALENDAR_COVERAGE_MISSING"
    PROTOCOL_NOT_FROZEN = "PROTOCOL_NOT_FROZEN"
    ACTION_PROTOCOL_MISMATCH = "ACTION_PROTOCOL_MISMATCH"
    MAPPING_NOT_KNOWN = "MAPPING_NOT_KNOWN"
    MAPPING_SCOPE_MISMATCH = "MAPPING_SCOPE_MISMATCH"
    MAPPING_NOT_EXECUTABLE = "MAPPING_NOT_EXECUTABLE"
    MAPPING_WINDOW_MISSING = "MAPPING_WINDOW_MISSING"
    SEARCH_HORIZON_EXHAUSTED = "SEARCH_HORIZON_EXHAUSTED"


class InstrumentMappingKind(str, Enum):
    """Relationship between model-facing and executable contracts."""

    DIRECT = "DIRECT"
    CONTINUOUS_ROLL = "CONTINUOUS_ROLL"
    SYNTHETIC_TRANSFORM = "SYNTHETIC_TRANSFORM"


class InstrumentPriceTransform(str, Enum):
    """Declared price relation; only independently governed transforms execute."""

    IDENTITY = "IDENTITY"
    RECIPROCAL = "RECIPROCAL"
    OTHER = "OTHER"


class ActionGridAnchor(str, Enum):
    """Reference used to align scheduled execution bars."""

    UTC_EPOCH = "UTC_EPOCH"


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }
    )


def _record_hash(domain: str, payload: Mapping[str, Any]) -> str:
    return _identity(f"{domain}.record", payload)


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


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


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload.get("canonicalization_version") != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload.get("schema_version") != CALENDAR_ACTION_SCHEMA_VERSION:
        raise CanonicalizationError("unsupported calendar/action schema_version")


def _require_digest(actual: Any, expected: str, *, field: str) -> None:
    if canonical_hash(actual, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarSourceArtifactV3:
    """Immutable bytes and receipt clock from which a schedule was compiled."""

    authority: CalendarAuthority
    authority_name: str
    source_locator: str
    source_document_id: str
    content_hash: str
    parser_contract_id: str
    first_seen_at: datetime
    retrieved_at: datetime
    effective_start_ts: datetime
    effective_end_ts_exclusive: datetime
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "authority",
            _enum(self.authority, CalendarAuthority, field="authority"),
        )
        for field_name in ("authority_name", "source_locator", "source_document_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(
                    getattr(self, field_name), field=field_name, maximum=2048
                ),
            )
        for field_name in ("content_hash", "parser_contract_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "first_seen_at",
            "retrieved_at",
            "effective_start_ts",
            "effective_end_ts_exclusive",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "published_at",
            _optional_timestamp(self.published_at, field="published_at"),
        )
        if self.first_seen_at > self.retrieved_at:
            raise CanonicalizationError("first_seen_at must not exceed retrieved_at")
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise CanonicalizationError("published_at must not exceed retrieved_at")
        if self.effective_start_ts >= self.effective_end_ts_exclusive:
            raise CanonicalizationError("calendar artifact effective interval is empty")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "authority": self.authority.value,
            "authority_name": self.authority_name,
            "content_hash": self.content_hash,
            "effective_end_ts_exclusive": utc_iso(self.effective_end_ts_exclusive),
            "effective_start_ts": utc_iso(self.effective_start_ts),
            "first_seen_at": utc_iso(self.first_seen_at),
            "parser_contract_id": self.parser_contract_id,
            "published_at": None
            if self.published_at is None
            else utc_iso(self.published_at),
            "retrieved_at": utc_iso(self.retrieved_at),
            "source_document_id": self.source_document_id,
            "source_locator": self.source_locator,
        }

    @property
    def calendar_source_artifact_id(self) -> str:
        return _identity("CalendarSourceArtifactV3", self.identity_payload())

    @property
    def record_hash(self) -> str:
        return _record_hash("CalendarSourceArtifactV3", self.record_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "calendar_source_artifact_id": self.calendar_source_artifact_id,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CalendarSourceArtifactV3:
        expected = {
            "authority",
            "authority_name",
            "calendar_source_artifact_id",
            "canonicalization_version",
            "content_hash",
            "effective_end_ts_exclusive",
            "effective_start_ts",
            "first_seen_at",
            "parser_contract_id",
            "published_at",
            "record_hash",
            "retrieved_at",
            "schema_version",
            "source_document_id",
            "source_locator",
        }
        require_exact_keys(
            payload, expected=expected, context="CalendarSourceArtifactV3"
        )
        _require_versions(payload)
        item = cls(
            authority=payload["authority"],
            authority_name=payload["authority_name"],
            source_locator=payload["source_locator"],
            source_document_id=payload["source_document_id"],
            content_hash=payload["content_hash"],
            parser_contract_id=payload["parser_contract_id"],
            first_seen_at=payload["first_seen_at"],
            retrieved_at=payload["retrieved_at"],
            effective_start_ts=payload["effective_start_ts"],
            effective_end_ts_exclusive=payload["effective_end_ts_exclusive"],
            published_at=payload["published_at"],
        )
        _require_digest(
            payload["calendar_source_artifact_id"],
            item.calendar_source_artifact_id,
            field="calendar_source_artifact_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class TradingIntervalV3:
    """One normalized, half-open scheduled market phase."""

    session_label: str
    trade_date: str
    phase: str
    open_ts: datetime
    close_ts_exclusive: datetime
    order_entry_allowed: bool
    matching_allowed: bool
    source_schedule_key: str

    def __post_init__(self) -> None:
        for field_name in ("session_label", "phase", "source_schedule_key"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        trade_date = canonical_identifier(
            self.trade_date, field="trade_date", maximum=10
        )
        if _TRADE_DATE_RE.fullmatch(trade_date) is None:
            raise CanonicalizationError("trade_date must use YYYY-MM-DD")
        try:
            datetime.fromisoformat(trade_date)
        except ValueError as exc:
            raise CanonicalizationError(
                "trade_date must be a real calendar date"
            ) from exc
        object.__setattr__(self, "trade_date", trade_date)
        object.__setattr__(self, "open_ts", utc_datetime(self.open_ts, field="open_ts"))
        object.__setattr__(
            self,
            "close_ts_exclusive",
            utc_datetime(self.close_ts_exclusive, field="close_ts_exclusive"),
        )
        object.__setattr__(
            self,
            "order_entry_allowed",
            _strict_bool(self.order_entry_allowed, field="order_entry_allowed"),
        )
        object.__setattr__(
            self,
            "matching_allowed",
            _strict_bool(self.matching_allowed, field="matching_allowed"),
        )
        if self.open_ts >= self.close_ts_exclusive:
            raise CanonicalizationError("trading interval must have positive duration")
        if self.matching_allowed and not self.order_entry_allowed:
            raise CanonicalizationError("matching interval must accept order entry")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "close_ts_exclusive": utc_iso(self.close_ts_exclusive),
            "matching_allowed": self.matching_allowed,
            "open_ts": utc_iso(self.open_ts),
            "order_entry_allowed": self.order_entry_allowed,
            "phase": self.phase,
            "session_label": self.session_label,
            "source_schedule_key": self.source_schedule_key,
            "trade_date": self.trade_date,
        }

    @property
    def trading_interval_id(self) -> str:
        return _identity("TradingIntervalV3", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "trading_interval_id": self.trading_interval_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TradingIntervalV3:
        expected = {
            "close_ts_exclusive",
            "matching_allowed",
            "open_ts",
            "order_entry_allowed",
            "phase",
            "session_label",
            "source_schedule_key",
            "trade_date",
            "trading_interval_id",
        }
        require_exact_keys(payload, expected=expected, context="TradingIntervalV3")
        item = cls(
            session_label=payload["session_label"],
            trade_date=payload["trade_date"],
            phase=payload["phase"],
            open_ts=payload["open_ts"],
            close_ts_exclusive=payload["close_ts_exclusive"],
            order_entry_allowed=payload["order_entry_allowed"],
            matching_allowed=payload["matching_allowed"],
            source_schedule_key=payload["source_schedule_key"],
        )
        _require_digest(
            payload["trading_interval_id"],
            item.trading_interval_id,
            field="trading_interval_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class CalendarScheduleSnapshotV3:
    """Finite, content-addressed schedule revision for one venue contract."""

    calendar_name: str
    venue_id: str
    contract_id: str
    product_id: str
    calendar_source_artifact_id: str
    calendar_source_artifact_record_hash: str
    timezone_name: str
    tzdb_version: str
    tzdb_artifact_hash: str
    compiler_contract_id: str
    base_timeframe_seconds: int
    coverage_start_ts: datetime
    coverage_end_ts_exclusive: datetime
    known_at: datetime
    frozen_at: datetime
    intervals: tuple[TradingIntervalV3, ...]
    parent_calendar_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "calendar_name",
            "venue_id",
            "contract_id",
            "product_id",
            "timezone_name",
            "tzdb_version",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "calendar_source_artifact_id",
            "calendar_source_artifact_record_hash",
            "tzdb_artifact_hash",
            "compiler_contract_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "parent_calendar_snapshot_id",
            _optional_hash(
                self.parent_calendar_snapshot_id, field="parent_calendar_snapshot_id"
            ),
        )
        object.__setattr__(
            self,
            "base_timeframe_seconds",
            canonical_safe_int(
                self.base_timeframe_seconds,
                field="base_timeframe_seconds",
                minimum=1,
                maximum=MAX_EXECUTION_BAR_SECONDS,
            ),
        )
        for field_name in (
            "coverage_start_ts",
            "coverage_end_ts_exclusive",
            "known_at",
            "frozen_at",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.coverage_start_ts >= self.coverage_end_ts_exclusive:
            raise CanonicalizationError("calendar coverage interval is empty")
        if self.known_at > self.frozen_at:
            raise CanonicalizationError("known_at must not exceed frozen_at")
        intervals = tuple(self.intervals)
        if (
            not intervals
            or len(intervals) > MAX_INTERVALS
            or not all(type(item) is TradingIntervalV3 for item in intervals)
        ):
            raise CanonicalizationError(
                "intervals must contain 1..MAX_INTERVALS TradingIntervalV3 records"
            )
        intervals = tuple(
            sorted(
                intervals,
                key=lambda item: (
                    item.open_ts,
                    item.close_ts_exclusive,
                    item.trading_interval_id,
                ),
            )
        )
        if len({item.trading_interval_id for item in intervals}) != len(intervals):
            raise CanonicalizationError(
                "calendar contains duplicate interval identities"
            )
        previous_close: datetime | None = None
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        step = self.base_timeframe_seconds
        for item in intervals:
            if (
                item.open_ts < self.coverage_start_ts
                or item.close_ts_exclusive > self.coverage_end_ts_exclusive
            ):
                raise CanonicalizationError(
                    "calendar interval is outside snapshot coverage"
                )
            if previous_close is not None and item.open_ts < previous_close:
                raise CanonicalizationError("calendar intervals overlap")
            previous_close = item.close_ts_exclusive
            for boundary in (item.open_ts, item.close_ts_exclusive):
                micros = (boundary - epoch) // timedelta(microseconds=1)
                if micros % (step * 1_000_000):
                    raise CanonicalizationError(
                        "calendar interval boundary is not aligned to the base timeframe"
                    )
        object.__setattr__(self, "intervals", intervals)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "base_timeframe_seconds": self.base_timeframe_seconds,
            "calendar_name": self.calendar_name,
            "calendar_source_artifact_id": self.calendar_source_artifact_id,
            "calendar_source_artifact_record_hash": self.calendar_source_artifact_record_hash,
            "compiler_contract_id": self.compiler_contract_id,
            "contract_id": self.contract_id,
            "coverage_end_ts_exclusive": utc_iso(self.coverage_end_ts_exclusive),
            "coverage_start_ts": utc_iso(self.coverage_start_ts),
            "frozen_at": utc_iso(self.frozen_at),
            "interval_ids": [item.trading_interval_id for item in self.intervals],
            "known_at": utc_iso(self.known_at),
            "parent_calendar_snapshot_id": self.parent_calendar_snapshot_id,
            "product_id": self.product_id,
            "timezone_name": self.timezone_name,
            "tzdb_artifact_hash": self.tzdb_artifact_hash,
            "tzdb_version": self.tzdb_version,
            "venue_id": self.venue_id,
        }

    @property
    def calendar_snapshot_id(self) -> str:
        return _identity("CalendarScheduleSnapshotV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        payload = self.identity_payload()
        payload.pop("interval_ids")
        return {
            **payload,
            "calendar_snapshot_id": self.calendar_snapshot_id,
            "intervals": [item.as_dict() for item in self.intervals],
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("CalendarScheduleSnapshotV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CalendarScheduleSnapshotV3:
        expected = {
            "base_timeframe_seconds",
            "calendar_name",
            "calendar_snapshot_id",
            "calendar_source_artifact_id",
            "calendar_source_artifact_record_hash",
            "canonicalization_version",
            "compiler_contract_id",
            "contract_id",
            "coverage_end_ts_exclusive",
            "coverage_start_ts",
            "frozen_at",
            "intervals",
            "known_at",
            "parent_calendar_snapshot_id",
            "product_id",
            "record_hash",
            "schema_version",
            "timezone_name",
            "tzdb_artifact_hash",
            "tzdb_version",
            "venue_id",
        }
        require_exact_keys(
            payload, expected=expected, context="CalendarScheduleSnapshotV3"
        )
        _require_versions(payload)
        raw_intervals = payload["intervals"]
        if not isinstance(raw_intervals, list):
            raise CanonicalizationError("intervals must be a JSON array")
        item = cls(
            calendar_name=payload["calendar_name"],
            venue_id=payload["venue_id"],
            contract_id=payload["contract_id"],
            product_id=payload["product_id"],
            calendar_source_artifact_id=payload["calendar_source_artifact_id"],
            calendar_source_artifact_record_hash=payload[
                "calendar_source_artifact_record_hash"
            ],
            timezone_name=payload["timezone_name"],
            tzdb_version=payload["tzdb_version"],
            tzdb_artifact_hash=payload["tzdb_artifact_hash"],
            compiler_contract_id=payload["compiler_contract_id"],
            base_timeframe_seconds=payload["base_timeframe_seconds"],
            coverage_start_ts=payload["coverage_start_ts"],
            coverage_end_ts_exclusive=payload["coverage_end_ts_exclusive"],
            known_at=payload["known_at"],
            frozen_at=payload["frozen_at"],
            intervals=tuple(
                TradingIntervalV3.from_mapping(value) for value in raw_intervals
            ),
            parent_calendar_snapshot_id=payload["parent_calendar_snapshot_id"],
        )
        _require_digest(
            payload["calendar_snapshot_id"],
            item.calendar_snapshot_id,
            field="calendar_snapshot_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


def validate_calendar_schedule_artifact_v3(
    calendar: CalendarScheduleSnapshotV3,
    artifact: CalendarSourceArtifactV3,
) -> None:
    """Validate the exact source bytes and effective coverage of a schedule."""

    if (
        calendar.calendar_source_artifact_id != artifact.calendar_source_artifact_id
        or calendar.calendar_source_artifact_record_hash != artifact.record_hash
    ):
        raise CanonicalizationError(
            "calendar snapshot does not bind the supplied source artifact"
        )
    if artifact.retrieved_at > calendar.known_at:
        raise CanonicalizationError(
            "calendar snapshot was known before its source artifact was retrieved"
        )
    if (
        artifact.authority is CalendarAuthority.OFFICIAL_VENUE
        and artifact.authority_name != calendar.venue_id
    ):
        raise CanonicalizationError(
            "official venue calendar authority_name differs from calendar venue_id"
        )
    if (
        artifact.effective_start_ts > calendar.coverage_start_ts
        or artifact.effective_end_ts_exclusive < calendar.coverage_end_ts_exclusive
    ):
        raise CanonicalizationError(
            "calendar snapshot coverage exceeds its source artifact"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionProtocolV3:
    """Frozen timing and interval-selection policy."""

    protocol_name: str
    protocol_version: str
    selection_rule: ActionSelectionRule
    entry_scenario: EntryScenario
    execution_bar_seconds: int
    entry_window_bars: int
    computation_delay_microseconds: int
    submission_delay_microseconds: int
    max_search_seconds: int
    grid_anchor: ActionGridAnchor
    require_full_bar: bool
    roll_to_next_interval: bool
    synthetic_rows_authorize_action: bool
    allowed_calendar_authorities: tuple[CalendarAuthority, ...]
    resolver_contract_id: str
    frozen_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("protocol_name", "protocol_version"):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "selection_rule",
            _enum(self.selection_rule, ActionSelectionRule, field="selection_rule"),
        )
        object.__setattr__(
            self,
            "entry_scenario",
            _enum(self.entry_scenario, EntryScenario, field="entry_scenario"),
        )
        if self.entry_scenario is not EntryScenario.NEXT_SCHEDULED_BASE_BAR_OPEN:
            raise CanonicalizationError(
                "V3.2 action protocol supports only NEXT_SCHEDULED_BASE_BAR_OPEN"
            )
        object.__setattr__(
            self,
            "grid_anchor",
            _enum(self.grid_anchor, ActionGridAnchor, field="grid_anchor"),
        )
        for field_name, minimum, maximum in (
            ("execution_bar_seconds", 1, MAX_EXECUTION_BAR_SECONDS),
            ("entry_window_bars", 1, MAX_ENTRY_WINDOW_BARS),
            ("computation_delay_microseconds", 0, MAX_SEARCH_SECONDS * 1_000_000),
            ("submission_delay_microseconds", 0, MAX_SEARCH_SECONDS * 1_000_000),
            ("max_search_seconds", 1, MAX_SEARCH_SECONDS),
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name),
                    field=field_name,
                    minimum=minimum,
                    maximum=maximum,
                ),
            )
        for field_name in (
            "require_full_bar",
            "roll_to_next_interval",
            "synthetic_rows_authorize_action",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_bool(getattr(self, field_name), field=field_name),
            )
        if not self.require_full_bar:
            raise CanonicalizationError("V3.2 requires the complete entry bar")
        if self.synthetic_rows_authorize_action:
            raise CanonicalizationError("synthetic rows must never authorize action")
        authorities = tuple(
            _enum(value, CalendarAuthority, field="allowed_calendar_authorities")
            for value in self.allowed_calendar_authorities
        )
        if not authorities or len(set(authorities)) != len(authorities):
            raise CanonicalizationError(
                "allowed_calendar_authorities must be non-empty and unique"
            )
        if not set(authorities).issubset(_CERTIFYING_CALENDAR_AUTHORITIES):
            raise CanonicalizationError(
                "V3.2 scheduled actions require official venue calendar authority"
            )
        object.__setattr__(
            self,
            "allowed_calendar_authorities",
            tuple(sorted(authorities, key=lambda value: value.value)),
        )
        object.__setattr__(
            self,
            "resolver_contract_id",
            canonical_hash(self.resolver_contract_id, field="resolver_contract_id"),
        )
        object.__setattr__(
            self, "frozen_at", utc_datetime(self.frozen_at, field="frozen_at")
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "allowed_calendar_authorities": [
                authority.value for authority in self.allowed_calendar_authorities
            ],
            "computation_delay_microseconds": self.computation_delay_microseconds,
            "entry_scenario": self.entry_scenario.value,
            "entry_window_bars": self.entry_window_bars,
            "execution_bar_seconds": self.execution_bar_seconds,
            "frozen_at": utc_iso(self.frozen_at),
            "grid_anchor": self.grid_anchor.value,
            "max_search_seconds": self.max_search_seconds,
            "protocol_name": self.protocol_name,
            "protocol_version": self.protocol_version,
            "require_full_bar": self.require_full_bar,
            "resolver_contract_id": self.resolver_contract_id,
            "roll_to_next_interval": self.roll_to_next_interval,
            "selection_rule": self.selection_rule.value,
            "submission_delay_microseconds": self.submission_delay_microseconds,
            "synthetic_rows_authorize_action": self.synthetic_rows_authorize_action,
        }

    @property
    def action_protocol_id(self) -> str:
        return _identity("ActionProtocolV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "action_protocol_id": self.action_protocol_id,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("ActionProtocolV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ActionProtocolV3:
        expected = {
            "action_protocol_id",
            "allowed_calendar_authorities",
            "canonicalization_version",
            "computation_delay_microseconds",
            "entry_scenario",
            "entry_window_bars",
            "execution_bar_seconds",
            "frozen_at",
            "grid_anchor",
            "max_search_seconds",
            "protocol_name",
            "protocol_version",
            "record_hash",
            "require_full_bar",
            "resolver_contract_id",
            "roll_to_next_interval",
            "schema_version",
            "selection_rule",
            "submission_delay_microseconds",
            "synthetic_rows_authorize_action",
        }
        require_exact_keys(payload, expected=expected, context="ActionProtocolV3")
        _require_versions(payload)
        if not isinstance(payload["allowed_calendar_authorities"], list):
            raise CanonicalizationError(
                "allowed_calendar_authorities must be a JSON array"
            )
        item = cls(
            **{
                key: payload[key]
                for key in expected
                - {
                    "action_protocol_id",
                    "canonicalization_version",
                    "record_hash",
                    "schema_version",
                }
            }
        )
        _require_digest(
            payload["action_protocol_id"],
            item.action_protocol_id,
            field="action_protocol_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class InstrumentMappingV3:
    """Point-in-time mapping from model scope to one executable contract."""

    asset_id: str
    venue_id: str
    source_contract_id: str
    executable_contract_id: str
    mapping_kind: InstrumentMappingKind
    provider_id: str
    source_symbol: str
    effective_start_ts: datetime
    effective_end_ts_exclusive: datetime
    known_at: datetime
    source_artifact_hash: str
    mapping_policy_id: str
    price_transform: InstrumentPriceTransform
    execution_transform_id: str | None
    execution_supported: bool
    blocker_codes: tuple[str, ...]
    parent_instrument_mapping_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "asset_id",
            "venue_id",
            "source_contract_id",
            "executable_contract_id",
            "provider_id",
            "source_symbol",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "mapping_kind",
            _enum(self.mapping_kind, InstrumentMappingKind, field="mapping_kind"),
        )
        object.__setattr__(
            self,
            "price_transform",
            _enum(
                self.price_transform, InstrumentPriceTransform, field="price_transform"
            ),
        )
        for field_name in (
            "effective_start_ts",
            "effective_end_ts_exclusive",
            "known_at",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.effective_start_ts >= self.effective_end_ts_exclusive:
            raise CanonicalizationError(
                "instrument mapping effective interval is empty"
            )
        for field_name in ("source_artifact_hash", "mapping_policy_id"):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "execution_transform_id",
            _optional_hash(self.execution_transform_id, field="execution_transform_id"),
        )
        object.__setattr__(
            self,
            "parent_instrument_mapping_id",
            _optional_hash(
                self.parent_instrument_mapping_id, field="parent_instrument_mapping_id"
            ),
        )
        object.__setattr__(
            self,
            "execution_supported",
            _strict_bool(self.execution_supported, field="execution_supported"),
        )
        blockers = canonical_reason_codes(self.blocker_codes, field="blocker_codes")
        object.__setattr__(self, "blocker_codes", blockers)
        if self.execution_supported == bool(blockers):
            raise CanonicalizationError(
                "supported mapping requires no blockers; unsupported mapping requires blockers"
            )
        if self.mapping_kind is InstrumentMappingKind.DIRECT:
            if (
                self.source_contract_id != self.executable_contract_id
                or self.price_transform is not InstrumentPriceTransform.IDENTITY
            ):
                raise CanonicalizationError(
                    "DIRECT mapping requires identical contract and price"
                )
        if (
            self.mapping_kind is InstrumentMappingKind.CONTINUOUS_ROLL
            and self.source_contract_id == self.executable_contract_id
        ):
            raise CanonicalizationError(
                "CONTINUOUS_ROLL must resolve to a concrete different contract"
            )
        if (
            self.price_transform is not InstrumentPriceTransform.IDENTITY
            and self.execution_supported
            and self.execution_transform_id is None
        ):
            raise CanonicalizationError(
                "transformed executable mapping requires execution_transform_id"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "blocker_codes": list(self.blocker_codes),
            "effective_end_ts_exclusive": utc_iso(self.effective_end_ts_exclusive),
            "effective_start_ts": utc_iso(self.effective_start_ts),
            "executable_contract_id": self.executable_contract_id,
            "execution_supported": self.execution_supported,
            "execution_transform_id": self.execution_transform_id,
            "known_at": utc_iso(self.known_at),
            "mapping_kind": self.mapping_kind.value,
            "mapping_policy_id": self.mapping_policy_id,
            "parent_instrument_mapping_id": self.parent_instrument_mapping_id,
            "price_transform": self.price_transform.value,
            "provider_id": self.provider_id,
            "source_artifact_hash": self.source_artifact_hash,
            "source_contract_id": self.source_contract_id,
            "source_symbol": self.source_symbol,
            "venue_id": self.venue_id,
        }

    @property
    def instrument_mapping_id(self) -> str:
        return _identity("InstrumentMappingV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "instrument_mapping_id": self.instrument_mapping_id,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("InstrumentMappingV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> InstrumentMappingV3:
        expected = {
            "asset_id",
            "blocker_codes",
            "canonicalization_version",
            "effective_end_ts_exclusive",
            "effective_start_ts",
            "executable_contract_id",
            "execution_supported",
            "execution_transform_id",
            "instrument_mapping_id",
            "known_at",
            "mapping_kind",
            "mapping_policy_id",
            "parent_instrument_mapping_id",
            "price_transform",
            "provider_id",
            "record_hash",
            "schema_version",
            "source_artifact_hash",
            "source_contract_id",
            "source_symbol",
            "venue_id",
        }
        require_exact_keys(payload, expected=expected, context="InstrumentMappingV3")
        _require_versions(payload)
        blockers = payload["blocker_codes"]
        if not isinstance(blockers, list):
            raise CanonicalizationError("blocker_codes must be a JSON array")
        item = cls(
            asset_id=payload["asset_id"],
            venue_id=payload["venue_id"],
            source_contract_id=payload["source_contract_id"],
            executable_contract_id=payload["executable_contract_id"],
            mapping_kind=payload["mapping_kind"],
            provider_id=payload["provider_id"],
            source_symbol=payload["source_symbol"],
            effective_start_ts=payload["effective_start_ts"],
            effective_end_ts_exclusive=payload["effective_end_ts_exclusive"],
            known_at=payload["known_at"],
            source_artifact_hash=payload["source_artifact_hash"],
            mapping_policy_id=payload["mapping_policy_id"],
            price_transform=payload["price_transform"],
            execution_transform_id=payload["execution_transform_id"],
            execution_supported=payload["execution_supported"],
            blocker_codes=tuple(blockers),
            parent_instrument_mapping_id=payload["parent_instrument_mapping_id"],
        )
        _require_digest(
            payload["instrument_mapping_id"],
            item.instrument_mapping_id,
            field="instrument_mapping_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionResolutionV3:
    """Deterministic scheduled-action result sealed before candidate creation."""

    information_set_id: str
    information_set_record_hash: str
    asset_id: str
    venue_id: str
    source_contract_id: str
    timeframe_id: str
    primary_signal_id: str
    primary_signal_version: str
    primary_signal_policy_id: str
    signal_ts: datetime
    side: TradeSide
    signal_available_ts: datetime
    resolved_at: datetime
    calendar_snapshot_id: str
    calendar_snapshot_record_hash: str
    action_protocol_id: str
    action_protocol_record_hash: str
    instrument_mapping_id: str
    instrument_mapping_record_hash: str
    entry_scenario: EntryScenario
    executable_contract_id: str
    status: ActionResolutionStatus
    abstention_reason: ActionAbstentionReason | None
    selected_interval_id: str | None
    earliest_order_submission_ts: datetime | None
    earliest_entry_ts: datetime | None
    entry_bar_close_ts_exclusive: datetime | None
    entry_expiry_ts: datetime | None
    resolver_contract_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "information_set_id",
            "information_set_record_hash",
            "primary_signal_policy_id",
            "calendar_snapshot_id",
            "calendar_snapshot_record_hash",
            "action_protocol_id",
            "action_protocol_record_hash",
            "instrument_mapping_id",
            "instrument_mapping_record_hash",
            "resolver_contract_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "asset_id",
            "venue_id",
            "source_contract_id",
            "timeframe_id",
            "primary_signal_id",
            "primary_signal_version",
            "executable_contract_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(self, "side", _enum(self.side, TradeSide, field="side"))
        object.__setattr__(
            self,
            "entry_scenario",
            _enum(self.entry_scenario, EntryScenario, field="entry_scenario"),
        )
        object.__setattr__(
            self, "status", _enum(self.status, ActionResolutionStatus, field="status")
        )
        reason = (
            None
            if self.abstention_reason is None
            else _enum(
                self.abstention_reason,
                ActionAbstentionReason,
                field="abstention_reason",
            )
        )
        object.__setattr__(self, "abstention_reason", reason)
        object.__setattr__(
            self,
            "selected_interval_id",
            _optional_hash(self.selected_interval_id, field="selected_interval_id"),
        )
        for field_name in ("signal_ts", "signal_available_ts", "resolved_at"):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "earliest_order_submission_ts",
            "earliest_entry_ts",
            "entry_bar_close_ts_exclusive",
            "entry_expiry_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_timestamp(getattr(self, field_name), field=field_name),
            )
        if (
            self.signal_ts > self.signal_available_ts
            or self.signal_available_ts > self.resolved_at
        ):
            raise CanonicalizationError(
                "action resolution signal clocks are not causal"
            )
        action_fields = (
            self.selected_interval_id,
            self.earliest_order_submission_ts,
            self.earliest_entry_ts,
            self.entry_bar_close_ts_exclusive,
            self.entry_expiry_ts,
        )
        if self.status is ActionResolutionStatus.RESOLVED:
            if reason is not None or any(value is None for value in action_fields):
                raise CanonicalizationError(
                    "RESOLVED action requires all clocks and no abstention reason"
                )
            assert self.earliest_order_submission_ts is not None
            assert self.earliest_entry_ts is not None
            assert self.entry_bar_close_ts_exclusive is not None
            assert self.entry_expiry_ts is not None
            if self.resolved_at > self.earliest_order_submission_ts:
                raise CanonicalizationError(
                    "resolution must be available before order submission"
                )
            if self.earliest_order_submission_ts >= self.earliest_entry_ts:
                raise CanonicalizationError(
                    "order submission must precede scheduled entry"
                )
            if self.earliest_entry_ts >= self.entry_bar_close_ts_exclusive:
                raise CanonicalizationError("entry bar must have positive duration")
            if self.entry_bar_close_ts_exclusive > self.entry_expiry_ts:
                raise CanonicalizationError(
                    "entry expiry must cover the complete entry bar"
                )
        elif reason is None or any(value is not None for value in action_fields):
            raise CanonicalizationError(
                "ABSTAINED action requires one reason and no action clocks"
            )

    def request_payload(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "information_set_id": self.information_set_id,
            "information_set_record_hash": self.information_set_record_hash,
            "primary_signal_id": self.primary_signal_id,
            "primary_signal_policy_id": self.primary_signal_policy_id,
            "primary_signal_version": self.primary_signal_version,
            "side": self.side.value,
            "signal_ts": utc_iso(self.signal_ts),
            "source_contract_id": self.source_contract_id,
            "timeframe_id": self.timeframe_id,
            "venue_id": self.venue_id,
        }

    @property
    def action_request_key(self) -> str:
        return _identity("ActionRequestKeyV3", self.request_payload())

    def identity_payload(self) -> dict[str, Any]:
        return {
            **self.request_payload(),
            "abstention_reason": None
            if self.abstention_reason is None
            else self.abstention_reason.value,
            "action_protocol_id": self.action_protocol_id,
            "action_protocol_record_hash": self.action_protocol_record_hash,
            "calendar_snapshot_id": self.calendar_snapshot_id,
            "calendar_snapshot_record_hash": self.calendar_snapshot_record_hash,
            "earliest_entry_ts": None
            if self.earliest_entry_ts is None
            else utc_iso(self.earliest_entry_ts),
            "earliest_order_submission_ts": None
            if self.earliest_order_submission_ts is None
            else utc_iso(self.earliest_order_submission_ts),
            "entry_bar_close_ts_exclusive": None
            if self.entry_bar_close_ts_exclusive is None
            else utc_iso(self.entry_bar_close_ts_exclusive),
            "entry_expiry_ts": None
            if self.entry_expiry_ts is None
            else utc_iso(self.entry_expiry_ts),
            "entry_scenario": self.entry_scenario.value,
            "executable_contract_id": self.executable_contract_id,
            "instrument_mapping_id": self.instrument_mapping_id,
            "instrument_mapping_record_hash": self.instrument_mapping_record_hash,
            "resolved_at": utc_iso(self.resolved_at),
            "resolver_contract_id": self.resolver_contract_id,
            "selected_interval_id": self.selected_interval_id,
            "signal_available_ts": utc_iso(self.signal_available_ts),
            "status": self.status.value,
        }

    @property
    def action_resolution_id(self) -> str:
        return _identity("ActionResolutionV3", self.identity_payload())

    def record_payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "action_request_key": self.action_request_key,
            "action_resolution_id": self.action_resolution_id,
        }

    @property
    def record_hash(self) -> str:
        return _record_hash("ActionResolutionV3", self.record_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.record_payload(),
            "record_hash": self.record_hash,
            "schema_version": CALENDAR_ACTION_SCHEMA_VERSION,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ActionResolutionV3:
        expected = {
            "abstention_reason",
            "action_protocol_id",
            "action_protocol_record_hash",
            "action_request_key",
            "action_resolution_id",
            "asset_id",
            "calendar_snapshot_id",
            "calendar_snapshot_record_hash",
            "canonicalization_version",
            "earliest_entry_ts",
            "earliest_order_submission_ts",
            "entry_bar_close_ts_exclusive",
            "entry_expiry_ts",
            "entry_scenario",
            "executable_contract_id",
            "information_set_id",
            "information_set_record_hash",
            "instrument_mapping_id",
            "instrument_mapping_record_hash",
            "primary_signal_id",
            "primary_signal_policy_id",
            "primary_signal_version",
            "record_hash",
            "resolved_at",
            "resolver_contract_id",
            "schema_version",
            "selected_interval_id",
            "side",
            "signal_available_ts",
            "signal_ts",
            "source_contract_id",
            "status",
            "timeframe_id",
            "venue_id",
        }
        require_exact_keys(payload, expected=expected, context="ActionResolutionV3")
        _require_versions(payload)
        item = cls(
            **{
                key: payload[key]
                for key in expected
                - {
                    "action_request_key",
                    "action_resolution_id",
                    "canonicalization_version",
                    "record_hash",
                    "schema_version",
                }
            }
        )
        _require_digest(
            payload["action_request_key"],
            item.action_request_key,
            field="action_request_key",
        )
        _require_digest(
            payload["action_resolution_id"],
            item.action_resolution_id,
            field="action_resolution_id",
        )
        _require_digest(payload["record_hash"], item.record_hash, field="record_hash")
        return item

    def validate_against(
        self,
        *,
        information_set: InformationSetV3,
        calendar_artifact: CalendarSourceArtifactV3,
        calendar: CalendarScheduleSnapshotV3,
        protocol: ActionProtocolV3,
        mapping: InstrumentMappingV3,
    ) -> None:
        expected = resolve_action_v3(
            information_set=information_set,
            calendar_artifact=calendar_artifact,
            calendar=calendar,
            protocol=protocol,
            mapping=mapping,
            primary_signal_id=self.primary_signal_id,
            primary_signal_version=self.primary_signal_version,
            primary_signal_policy_id=self.primary_signal_policy_id,
            signal_ts=self.signal_ts,
            side=self.side,
            signal_available_ts=self.signal_available_ts,
            resolved_at=self.resolved_at,
        )
        if self.as_dict() != expected.as_dict():
            raise CanonicalizationError(
                "action resolution differs from deterministic resolver output"
            )


def _resolution(
    *,
    information_set: InformationSetV3,
    calendar: CalendarScheduleSnapshotV3,
    protocol: ActionProtocolV3,
    mapping: InstrumentMappingV3,
    primary_signal_id: str,
    primary_signal_version: str,
    primary_signal_policy_id: str,
    signal_ts: datetime,
    side: TradeSide,
    signal_available_ts: datetime,
    resolved_at: datetime,
    status: ActionResolutionStatus,
    reason: ActionAbstentionReason | None,
    selected_interval_id: str | None = None,
    submission: datetime | None = None,
    entry: datetime | None = None,
    entry_close: datetime | None = None,
    expiry: datetime | None = None,
) -> ActionResolutionV3:
    return ActionResolutionV3(
        information_set_id=information_set.information_set_id,
        information_set_record_hash=information_set.record_hash,
        asset_id=information_set.asset_id,
        venue_id=information_set.venue_id,
        source_contract_id=information_set.contract_id,
        timeframe_id=information_set.timeframe_id,
        primary_signal_id=primary_signal_id,
        primary_signal_version=primary_signal_version,
        primary_signal_policy_id=primary_signal_policy_id,
        signal_ts=signal_ts,
        side=side,
        signal_available_ts=signal_available_ts,
        resolved_at=resolved_at,
        calendar_snapshot_id=calendar.calendar_snapshot_id,
        calendar_snapshot_record_hash=calendar.record_hash,
        action_protocol_id=protocol.action_protocol_id,
        action_protocol_record_hash=protocol.record_hash,
        instrument_mapping_id=mapping.instrument_mapping_id,
        instrument_mapping_record_hash=mapping.record_hash,
        entry_scenario=protocol.entry_scenario,
        executable_contract_id=mapping.executable_contract_id,
        status=status,
        abstention_reason=reason,
        selected_interval_id=selected_interval_id,
        earliest_order_submission_ts=submission,
        earliest_entry_ts=entry,
        entry_bar_close_ts_exclusive=entry_close,
        entry_expiry_ts=expiry,
        resolver_contract_id=protocol.resolver_contract_id,
    )


def _grid_at_or_after(value: datetime, *, step_seconds: int) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    micros = (value - epoch) // timedelta(microseconds=1)
    step = step_seconds * 1_000_000
    aligned = ((micros + step - 1) // step) * step
    return epoch + timedelta(microseconds=aligned)


@dataclass(frozen=True, slots=True, kw_only=True)
class ScheduledActionWindowV3:
    """First schedule-valid action window before instrument mapping is applied."""

    selected_interval_id: str
    earliest_order_submission_ts: datetime
    earliest_entry_ts: datetime
    entry_bar_close_ts_exclusive: datetime
    entry_expiry_ts: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_interval_id",
            canonical_hash(self.selected_interval_id, field="selected_interval_id"),
        )
        for field_name in (
            "earliest_order_submission_ts",
            "earliest_entry_ts",
            "entry_bar_close_ts_exclusive",
            "entry_expiry_ts",
        ):
            object.__setattr__(
                self,
                field_name,
                utc_datetime(getattr(self, field_name), field=field_name),
            )
        if self.earliest_order_submission_ts >= self.earliest_entry_ts:
            raise CanonicalizationError(
                "scheduled submission must precede scheduled entry"
            )
        if self.earliest_entry_ts >= self.entry_bar_close_ts_exclusive:
            raise CanonicalizationError(
                "scheduled entry bar must have positive duration"
            )
        if self.entry_bar_close_ts_exclusive > self.entry_expiry_ts:
            raise CanonicalizationError(
                "scheduled expiry must cover the complete entry bar"
            )


def resolve_scheduled_action_window_v3(
    *,
    calendar: CalendarScheduleSnapshotV3,
    protocol: ActionProtocolV3,
    resolved_at: datetime | str,
) -> tuple[ScheduledActionWindowV3 | None, ActionAbstentionReason | None]:
    """Return the first schedule-valid window without consulting a mapping."""

    resolved_at = utc_datetime(resolved_at, field="resolved_at")
    if calendar.base_timeframe_seconds != protocol.execution_bar_seconds:
        return None, ActionAbstentionReason.ACTION_PROTOCOL_MISMATCH
    submission = resolved_at + timedelta(
        microseconds=protocol.submission_delay_microseconds
    )
    search_end = submission + timedelta(seconds=protocol.max_search_seconds)
    if (
        submission < calendar.coverage_start_ts
        or submission >= calendar.coverage_end_ts_exclusive
    ):
        return None, ActionAbstentionReason.CALENDAR_COVERAGE_MISSING
    for interval in calendar.intervals:
        if not interval.order_entry_allowed or not interval.matching_allowed:
            continue
        if interval.close_ts_exclusive <= submission:
            continue
        if interval.open_ts > search_end:
            break
        entry = _grid_at_or_after(
            max(submission + timedelta(microseconds=1), interval.open_ts),
            step_seconds=protocol.execution_bar_seconds,
        )
        entry_close = entry + timedelta(seconds=protocol.execution_bar_seconds)
        expiry = entry + timedelta(
            seconds=protocol.execution_bar_seconds * protocol.entry_window_bars
        )
        if entry > search_end:
            break
        if (
            entry_close > interval.close_ts_exclusive
            or expiry > interval.close_ts_exclusive
        ):
            if not protocol.roll_to_next_interval:
                break
            continue
        return (
            ScheduledActionWindowV3(
                selected_interval_id=interval.trading_interval_id,
                earliest_order_submission_ts=submission,
                earliest_entry_ts=entry,
                entry_bar_close_ts_exclusive=entry_close,
                entry_expiry_ts=expiry,
            ),
            None,
        )
    return None, ActionAbstentionReason.SEARCH_HORIZON_EXHAUSTED


def resolve_action_v3(
    *,
    information_set: InformationSetV3,
    calendar_artifact: CalendarSourceArtifactV3,
    calendar: CalendarScheduleSnapshotV3,
    protocol: ActionProtocolV3,
    mapping: InstrumentMappingV3,
    primary_signal_id: str,
    primary_signal_version: str,
    primary_signal_policy_id: str,
    signal_ts: datetime | str,
    side: TradeSide | str,
    signal_available_ts: datetime | str,
    resolved_at: datetime | str,
) -> ActionResolutionV3:
    """Resolve the first complete scheduled entry window without reading prices."""

    primary_signal_id = canonical_identifier(
        primary_signal_id, field="primary_signal_id"
    )
    primary_signal_version = canonical_identifier(
        primary_signal_version, field="primary_signal_version"
    )
    primary_signal_policy_id = canonical_hash(
        primary_signal_policy_id, field="primary_signal_policy_id"
    )
    signal_ts = utc_datetime(signal_ts, field="signal_ts")
    signal_available_ts = utc_datetime(signal_available_ts, field="signal_available_ts")
    resolved_at = utc_datetime(resolved_at, field="resolved_at")
    side = _enum(side, TradeSide, field="side")
    if signal_ts > information_set.observation_cutoff_ts:
        raise CanonicalizationError("signal_ts exceeds information-set cutoff")
    if (
        signal_available_ts < information_set.assembled_at
        or signal_ts > signal_available_ts
    ):
        raise CanonicalizationError("signal availability is not causal")
    minimum_resolved = signal_available_ts + timedelta(
        microseconds=protocol.computation_delay_microseconds
    )
    if resolved_at < minimum_resolved:
        raise CanonicalizationError("resolved_at precedes the frozen computation delay")

    common = {
        "information_set": information_set,
        "calendar": calendar,
        "protocol": protocol,
        "mapping": mapping,
        "primary_signal_id": primary_signal_id,
        "primary_signal_version": primary_signal_version,
        "primary_signal_policy_id": primary_signal_policy_id,
        "signal_ts": signal_ts,
        "side": side,
        "signal_available_ts": signal_available_ts,
        "resolved_at": resolved_at,
    }
    cutoff = information_set.observation_cutoff_ts
    validate_calendar_schedule_artifact_v3(calendar, calendar_artifact)
    if calendar_artifact.authority not in protocol.allowed_calendar_authorities:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.CALENDAR_AUTHORITY_NOT_ALLOWED,
        )
    if information_set.calendar_manifest_id != calendar.calendar_snapshot_id:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.CALENDAR_SCOPE_MISMATCH,
        )
    if calendar.known_at > cutoff or calendar.frozen_at > cutoff:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.CALENDAR_NOT_KNOWN,
        )
    if protocol.frozen_at > cutoff:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.PROTOCOL_NOT_FROZEN,
        )
    if (
        calendar.venue_id != information_set.venue_id
        or calendar.contract_id != information_set.contract_id
    ):
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.CALENDAR_SCOPE_MISMATCH,
        )
    if mapping.known_at > cutoff:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.MAPPING_NOT_KNOWN,
        )
    if (mapping.asset_id, mapping.venue_id, mapping.source_contract_id) != (
        information_set.asset_id,
        information_set.venue_id,
        information_set.contract_id,
    ):
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.MAPPING_SCOPE_MISMATCH,
        )
    window, schedule_reason = resolve_scheduled_action_window_v3(
        calendar=calendar,
        protocol=protocol,
        resolved_at=resolved_at,
    )
    if window is None:
        assert schedule_reason is not None
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=schedule_reason,
        )
    if not mapping.execution_supported:
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.MAPPING_NOT_EXECUTABLE,
        )
    if (
        mapping.effective_start_ts > window.earliest_entry_ts
        or mapping.effective_end_ts_exclusive < window.entry_expiry_ts
    ):
        return _resolution(
            **common,
            status=ActionResolutionStatus.ABSTAINED,
            reason=ActionAbstentionReason.MAPPING_WINDOW_MISSING,
        )
    return _resolution(
        **common,
        status=ActionResolutionStatus.RESOLVED,
        reason=None,
        selected_interval_id=window.selected_interval_id,
        submission=window.earliest_order_submission_ts,
        entry=window.earliest_entry_ts,
        entry_close=window.entry_bar_close_ts_exclusive,
        expiry=window.entry_expiry_ts,
    )


__all__ = [
    "CALENDAR_ACTION_SCHEMA_VERSION",
    "ActionAbstentionReason",
    "ActionGridAnchor",
    "ActionProtocolV3",
    "ActionResolutionStatus",
    "ActionResolutionV3",
    "ActionSelectionRule",
    "CalendarAuthority",
    "CalendarScheduleSnapshotV3",
    "CalendarSourceArtifactV3",
    "InstrumentMappingKind",
    "InstrumentMappingV3",
    "InstrumentPriceTransform",
    "ScheduledActionWindowV3",
    "TradingIntervalV3",
    "resolve_action_v3",
    "resolve_scheduled_action_window_v3",
    "validate_calendar_schedule_artifact_v3",
]

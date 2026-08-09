from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import timedelta

import pytest

from riskyieldmm.trading.calendar_actions import (
    ActionAbstentionReason,
    ActionGridAnchor,
    ActionProtocolV3,
    ActionResolutionStatus,
    ActionResolutionV3,
    ActionSelectionRule,
    CalendarAuthority,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingKind,
    InstrumentMappingV3,
    InstrumentPriceTransform,
    TradingIntervalV3,
    resolve_action_v3,
)
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.contracts import (
    EntryScenario,
    InformationSetV3,
    TradeSide,
    VintageClass,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def artifact(**changes: object) -> CalendarSourceArtifactV3:
    values: dict[str, object] = {
        "authority": CalendarAuthority.OFFICIAL_VENUE,
        "authority_name": "BYBIT",
        "source_locator": "https://bybit-exchange.github.io/docs/v5/market/instrument",
        "source_document_id": "bybit-linear-schedule-2026-07-14",
        "content_hash": digest("official-calendar-bytes"),
        "parser_contract_id": digest("calendar-parser-v1"),
        "published_at": "2026-07-13T06:00:00Z",
        "first_seen_at": "2026-07-13T06:01:00Z",
        "retrieved_at": "2026-07-13T06:01:01Z",
        "effective_start_ts": "2026-07-14T00:00:00Z",
        "effective_end_ts_exclusive": "2026-07-15T00:00:00Z",
    }
    values.update(changes)
    return CalendarSourceArtifactV3(**values)  # type: ignore[arg-type]


def interval(
    open_ts: str = "2026-07-14T08:00:00Z",
    close_ts: str = "2026-07-14T12:00:00Z",
    **changes: object,
) -> TradingIntervalV3:
    values: dict[str, object] = {
        "session_label": "BYBIT-2026-07-14",
        "trade_date": "2026-07-14",
        "phase": "CONTINUOUS_TRADING",
        "open_ts": open_ts,
        "close_ts_exclusive": close_ts,
        "order_entry_allowed": True,
        "matching_allowed": True,
        "source_schedule_key": "bybit-linear-continuous",
    }
    values.update(changes)
    return TradingIntervalV3(**values)  # type: ignore[arg-type]


def calendar(
    source: CalendarSourceArtifactV3 | None = None,
    **changes: object,
) -> CalendarScheduleSnapshotV3:
    source = artifact() if source is None else source
    values: dict[str, object] = {
        "calendar_name": "bybit-linear-utc",
        "venue_id": "BYBIT",
        "contract_id": "BTCUSDT.LINEAR.PERP",
        "product_id": "BTCUSDT",
        "calendar_source_artifact_id": source.calendar_source_artifact_id,
        "calendar_source_artifact_record_hash": source.record_hash,
        "timezone_name": "Etc/UTC",
        "tzdb_version": "2026a",
        "tzdb_artifact_hash": digest("tzdata-2026a"),
        "compiler_contract_id": digest("schedule-compiler-v1"),
        "base_timeframe_seconds": 60,
        "coverage_start_ts": "2026-07-14T08:00:00Z",
        "coverage_end_ts_exclusive": "2026-07-14T12:00:00Z",
        "known_at": "2026-07-14T07:00:00Z",
        "frozen_at": "2026-07-14T07:00:01Z",
        "intervals": (interval(),),
    }
    values.update(changes)
    return CalendarScheduleSnapshotV3(**values)  # type: ignore[arg-type]


def protocol(**changes: object) -> ActionProtocolV3:
    values: dict[str, object] = {
        "protocol_name": "scheduled-next-minute",
        "protocol_version": "1.0.0",
        "selection_rule": ActionSelectionRule.NEXT_SCHEDULED_BASE_BAR_OPEN,
        "entry_scenario": EntryScenario.NEXT_SCHEDULED_BASE_BAR_OPEN,
        "execution_bar_seconds": 60,
        "entry_window_bars": 1,
        "computation_delay_microseconds": 1_000_000,
        "submission_delay_microseconds": 3_000_000,
        "max_search_seconds": 86_400,
        "grid_anchor": ActionGridAnchor.UTC_EPOCH,
        "require_full_bar": True,
        "roll_to_next_interval": True,
        "synthetic_rows_authorize_action": False,
        "allowed_calendar_authorities": (CalendarAuthority.OFFICIAL_VENUE,),
        "resolver_contract_id": digest("action-resolver-v1"),
        "frozen_at": "2026-07-14T07:00:00Z",
    }
    values.update(changes)
    return ActionProtocolV3(**values)  # type: ignore[arg-type]


def mapping(**changes: object) -> InstrumentMappingV3:
    values: dict[str, object] = {
        "asset_id": "BTC",
        "venue_id": "BYBIT",
        "source_contract_id": "BTCUSDT.LINEAR.PERP",
        "executable_contract_id": "BTCUSDT.LINEAR.PERP",
        "mapping_kind": InstrumentMappingKind.DIRECT,
        "provider_id": "bybit-v5",
        "source_symbol": "BTCUSDT",
        "effective_start_ts": "2026-07-14T00:00:00Z",
        "effective_end_ts_exclusive": "2026-07-15T00:00:00Z",
        "known_at": "2026-07-14T07:00:00Z",
        "source_artifact_hash": digest("bybit-instrument-response"),
        "mapping_policy_id": digest("direct-instrument-mapping"),
        "price_transform": InstrumentPriceTransform.IDENTITY,
        "execution_transform_id": None,
        "execution_supported": True,
        "blocker_codes": (),
    }
    values.update(changes)
    return InstrumentMappingV3(**values)  # type: ignore[arg-type]


def information(
    schedule: CalendarScheduleSnapshotV3 | None = None,
    *,
    timeframe_id: str = "1m",
    **changes: object,
) -> InformationSetV3:
    schedule = calendar() if schedule is None else schedule
    values: dict[str, object] = {
        "asset_id": "BTC",
        "venue_id": "BYBIT",
        "contract_id": "BTCUSDT.LINEAR.PERP",
        "timeframe_id": timeframe_id,
        "observation_cutoff_ts": "2026-07-14T09:01:03Z",
        "assembled_at": "2026-07-14T09:01:04Z",
        "source_manifest_id": digest("source-manifest"),
        "protocol_manifest_id": digest("protocol-manifest"),
        "calendar_manifest_id": schedule.calendar_snapshot_id,
        "feature_schema_id": digest("feature-schema"),
        "dependencies": (),
        "state_dependencies": (),
        "vintage_class": VintageClass.LIVE_FIRST_SEEN_CERTIFIED,
        "point_in_time_certified": True,
        "certification_blockers": (),
        "data_quality_flags": (),
        "universe_snapshot_id": digest("universe"),
    }
    values.update(changes)
    return InformationSetV3(**values)  # type: ignore[arg-type]


def resolution(**changes: object) -> ActionResolutionV3:
    source = changes.pop("source", artifact())
    schedule = changes.pop("schedule", calendar(source))
    action = changes.pop("action", protocol())
    instrument = changes.pop("instrument", mapping())
    info = changes.pop("info", information(schedule))
    values: dict[str, object] = {
        "information_set": info,
        "calendar_artifact": source,
        "calendar": schedule,
        "protocol": action,
        "mapping": instrument,
        "primary_signal_id": "online-cusum",
        "primary_signal_version": "v3.2",
        "primary_signal_policy_id": digest("signal-policy"),
        "signal_ts": "2026-07-14T09:01:03Z",
        "side": TradeSide.LONG,
        "signal_available_ts": "2026-07-14T09:01:05Z",
        "resolved_at": "2026-07-14T09:01:06Z",
    }
    values.update(changes)
    return resolve_action_v3(**values)  # type: ignore[arg-type]


def test_resolver_selects_first_strictly_later_complete_minute() -> None:
    result = resolution()

    assert result.status is ActionResolutionStatus.RESOLVED
    assert result.abstention_reason is None
    assert (
        result.earliest_order_submission_ts.isoformat() == "2026-07-14T09:01:09+00:00"
    )
    assert result.earliest_entry_ts.isoformat() == "2026-07-14T09:02:00+00:00"
    assert (
        result.entry_bar_close_ts_exclusive.isoformat() == "2026-07-14T09:03:00+00:00"
    )
    assert result.entry_expiry_ts == result.entry_bar_close_ts_exclusive


@pytest.mark.parametrize(
    "factory, parser",
    [
        (artifact, CalendarSourceArtifactV3.from_mapping),
        (calendar, CalendarScheduleSnapshotV3.from_mapping),
        (protocol, ActionProtocolV3.from_mapping),
        (mapping, InstrumentMappingV3.from_mapping),
        (resolution, ActionResolutionV3.from_mapping),
    ],
)
def test_calendar_action_records_round_trip_exactly(factory, parser) -> None:
    item = factory()
    parsed = parser(item.as_dict())
    assert parsed == item
    assert parsed.as_dict() == item.as_dict()


def test_exact_grid_boundary_still_selects_next_grid_open() -> None:
    result = resolution(
        resolved_at="2026-07-14T09:01:57Z",
        signal_available_ts="2026-07-14T09:01:56Z",
    )
    assert (
        result.earliest_order_submission_ts.isoformat() == "2026-07-14T09:02:00+00:00"
    )
    assert result.earliest_entry_ts.isoformat() == "2026-07-14T09:03:00+00:00"


def test_maintenance_break_rolls_to_next_matching_interval() -> None:
    source = artifact()
    schedule = calendar(
        source,
        intervals=(
            interval(close_ts="2026-07-14T09:02:00Z"),
            interval(
                open_ts="2026-07-14T09:03:00Z",
                close_ts="2026-07-14T12:00:00Z",
                session_label="BYBIT-2026-07-14-reopen",
                source_schedule_key="maintenance-reopen",
            ),
        ),
    )
    result = resolution(source=source, schedule=schedule, info=information(schedule))
    assert result.earliest_entry_ts.isoformat() == "2026-07-14T09:03:00+00:00"


def test_full_bar_must_fit_before_early_close() -> None:
    source = artifact()
    schedule = calendar(
        source,
        coverage_end_ts_exclusive="2026-07-14T09:02:00Z",
        intervals=(interval(close_ts="2026-07-14T09:02:00Z"),),
    )
    result = resolution(source=source, schedule=schedule, info=information(schedule))
    assert result.status is ActionResolutionStatus.ABSTAINED
    assert result.abstention_reason is ActionAbstentionReason.SEARCH_HORIZON_EXHAUSTED
    assert result.earliest_entry_ts is None


def test_schedule_first_seen_after_cutoff_fails_closed() -> None:
    source = artifact()
    schedule = calendar(
        source,
        known_at="2026-07-14T09:01:04Z",
        frozen_at="2026-07-14T09:01:04Z",
    )
    result = resolution(source=source, schedule=schedule, info=information(schedule))
    assert result.abstention_reason is ActionAbstentionReason.CALENDAR_NOT_KNOWN


@pytest.mark.parametrize(
    "authority",
    (
        CalendarAuthority.OFFICIAL_REGULATOR,
        CalendarAuthority.AUTHORIZED_VENDOR,
        CalendarAuthority.SECONDARY_REFERENCE,
    ),
)
def test_non_official_calendar_authority_cannot_certify_action(
    authority: CalendarAuthority,
) -> None:
    source = artifact(authority=authority)
    schedule = calendar(source)
    result = resolution(source=source, schedule=schedule, info=information(schedule))
    assert result.status is ActionResolutionStatus.ABSTAINED
    assert (
        result.abstention_reason
        is ActionAbstentionReason.CALENDAR_AUTHORITY_NOT_ALLOWED
    )
    with pytest.raises(CanonicalizationError, match="official venue"):
        protocol(allowed_calendar_authorities=(authority,))


def test_official_venue_authority_must_match_calendar_scope() -> None:
    source = artifact(authority_name="NOT-BYBIT")
    schedule = calendar(source)
    with pytest.raises(CanonicalizationError, match="authority_name differs"):
        resolution(source=source, schedule=schedule, info=information(schedule))


def test_calendar_cannot_precede_complete_source_artifact_retrieval() -> None:
    source = artifact(
        first_seen_at="2026-07-14T07:29:59Z",
        retrieved_at="2026-07-14T07:30:00Z",
    )
    schedule = calendar(source)
    with pytest.raises(CanonicalizationError, match="before its source artifact"):
        resolution(source=source, schedule=schedule, info=information(schedule))


def test_calendar_source_artifact_must_cover_the_full_schedule() -> None:
    source = artifact(effective_start_ts="2026-07-14T08:01:00Z")
    schedule = calendar(source)
    with pytest.raises(CanonicalizationError, match="coverage exceeds"):
        resolution(source=source, schedule=schedule, info=information(schedule))

    source = artifact(effective_end_ts_exclusive="2026-07-14T11:59:00Z")
    schedule = calendar(source)
    with pytest.raises(CanonicalizationError, match="coverage exceeds"):
        resolution(source=source, schedule=schedule, info=information(schedule))


def test_mapping_first_seen_after_cutoff_fails_closed() -> None:
    instrument = mapping(known_at="2026-07-14T09:01:04Z")
    result = resolution(instrument=instrument)
    assert result.abstention_reason is ActionAbstentionReason.MAPPING_NOT_KNOWN


def test_reciprocal_usdjpy_mapping_remains_non_executable() -> None:
    instrument = mapping(
        asset_id="USDJPY",
        source_contract_id="6J.v.0",
        executable_contract_id="6JU6",
        mapping_kind=InstrumentMappingKind.SYNTHETIC_TRANSFORM,
        source_symbol="6J.v.0",
        price_transform=InstrumentPriceTransform.RECIPROCAL,
        execution_supported=False,
        blocker_codes=("RECIPROCAL_EXECUTION_TRANSFORM_UNSPECIFIED",),
    )
    schedule = calendar(contract_id="6J.v.0", product_id="6J")
    info = information(
        schedule,
        asset_id="USDJPY",
        venue_id="BYBIT",
        contract_id="6J.v.0",
    )
    result = resolution(schedule=schedule, info=info, instrument=instrument)
    assert result.abstention_reason is ActionAbstentionReason.MAPPING_NOT_EXECUTABLE


def test_mapping_must_cover_the_complete_entry_window() -> None:
    instrument = mapping(effective_end_ts_exclusive="2026-07-14T09:02:30Z")
    result = resolution(instrument=instrument)
    assert result.abstention_reason is ActionAbstentionReason.MAPPING_WINDOW_MISSING


def test_mapping_gap_at_first_valid_window_does_not_shift_action_later() -> None:
    source = artifact()
    schedule = calendar(
        source,
        intervals=(
            interval(close_ts="2026-07-14T09:03:00Z"),
            interval(
                open_ts="2026-07-14T09:03:00Z",
                close_ts="2026-07-14T12:00:00Z",
                session_label="later-mapped-session",
                source_schedule_key="later-mapped-session",
            ),
        ),
    )
    instrument = mapping(effective_start_ts="2026-07-14T09:03:00Z")
    result = resolution(
        source=source,
        schedule=schedule,
        info=information(schedule),
        instrument=instrument,
    )
    assert result.status is ActionResolutionStatus.ABSTAINED
    assert result.abstention_reason is ActionAbstentionReason.MAPPING_WINDOW_MISSING
    assert result.earliest_entry_ts is None


def test_overlapping_calendar_intervals_are_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="overlap"):
        calendar(
            intervals=(
                interval(close_ts="2026-07-14T10:00:00Z"),
                interval(
                    open_ts="2026-07-14T09:59:00Z",
                    close_ts="2026-07-14T11:00:00Z",
                    session_label="overlap",
                    source_schedule_key="overlap",
                ),
            )
        )


def test_unaligned_interval_boundary_is_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="aligned"):
        calendar(intervals=(interval(open_ts="2026-07-14T08:00:30Z"),))


def test_synthetic_rows_can_never_authorize_action() -> None:
    with pytest.raises(CanonicalizationError, match="synthetic rows"):
        protocol(synthetic_rows_authorize_action=True)


def test_all_signal_timeframes_share_the_same_execution_grid() -> None:
    entries = {
        resolution(
            info=information(calendar(), timeframe_id=timeframe)
        ).earliest_entry_ts
        for timeframe in ("1m", "15m", "1h", "4h", "1d")
    }
    assert len(entries) == 1


def test_later_schedule_interval_does_not_change_selected_clock() -> None:
    source = artifact()
    first = calendar(source)
    extended = replace(
        first,
        coverage_end_ts_exclusive=first.coverage_end_ts_exclusive + timedelta(hours=2),
        intervals=(
            *first.intervals,
            interval(
                open_ts="2026-07-14T13:00:00Z",
                close_ts="2026-07-14T14:00:00Z",
                session_label="later-session",
                source_schedule_key="later-session",
            ),
        ),
    )
    first_result = resolution(source=source, schedule=first, info=information(first))
    extended_result = resolution(
        source=source,
        schedule=extended,
        info=information(extended),
    )
    assert first_result.earliest_entry_ts == extended_result.earliest_entry_ts


def test_resolution_self_validation_replays_the_pure_resolver() -> None:
    source = artifact()
    schedule = calendar(source)
    action = protocol()
    instrument = mapping()
    info = information(schedule)
    result = resolution(
        source=source,
        schedule=schedule,
        action=action,
        instrument=instrument,
        info=info,
    )
    result.validate_against(
        information_set=info,
        calendar_artifact=source,
        calendar=schedule,
        protocol=action,
        mapping=instrument,
    )

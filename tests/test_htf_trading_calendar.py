from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
from polars.testing import assert_frame_equal

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.features.regime_calendar_state import (
    add_regime_calendar_state_features,
    enrich_regime_calendar_state_sources,
)
from regression_feature_engineering.features.regime_calendar_state import (
    feature_columns as regime_calendar_feature_columns,
)
from regression_feature_engineering.features.regime_calendar_state import (
    source_columns as regime_calendar_source_columns,
)
from scripts.feature_engineering.htf_trading_calendar import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_FUTURES_SESSION_OBSERVED,
    _historical_session_close_minutes,
    aggregate_canonical_15m,
    aggregate_canonical_ohlcv,
    canonicalize_ohlcv,
)


def _bars(timestamps: list[datetime], *, base: float = 100.0) -> pl.DataFrame:
    close = [base + float(i) for i, _ in enumerate(timestamps)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [value - 0.1 for value in close],
            "high": [value + 0.2 for value in close],
            "low": [value - 0.2 for value in close],
            "close": close,
            "volume": [10.0 for _ in timestamps],
        }
    )


def test_crypto_calendar_generates_every_minute_and_flags_fill() -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    raw = _bars([start, start + timedelta(minutes=1), start + timedelta(minutes=3)])

    canonical, summary = canonicalize_ohlcv(
        raw,
        asset_id="BTCUSDT",
        calendar_id=CALENDAR_CRYPTO_24_7,
        timeframe="1m",
    )

    assert len(canonical) == 4
    assert summary.synthetic_rows == 1
    filled = canonical.filter(pl.col("is_open_session_gap_fill"))
    assert filled["timestamp"].to_list() == [start + timedelta(minutes=2)]
    assert filled["volume"].to_list() == [0.0]
    assert filled["open"].to_list() == filled["close"].to_list()


def test_session_calendar_does_not_fill_maintenance_break_or_weekend() -> None:
    friday_close = datetime(2021, 1, 8, 20, 59, tzinfo=timezone.utc)
    sunday_open = datetime(2021, 1, 10, 22, 0, tzinfo=timezone.utc)
    monday_open = datetime(2021, 1, 11, 0, 0, tzinfo=timezone.utc)
    monday_break_start = datetime(2021, 1, 11, 20, 59, tzinfo=timezone.utc)
    monday_reopen = datetime(2021, 1, 11, 22, 0, tzinfo=timezone.utc)
    raw = _bars(
        [
            friday_close,
            sunday_open,
            monday_open,
            monday_open + timedelta(minutes=2),
            monday_break_start - timedelta(minutes=1),
            monday_break_start,
            monday_reopen,
            monday_reopen + timedelta(minutes=1),
        ],
        base=200.0,
    )

    canonical, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    timestamps = set(canonical["timestamp"].to_list())
    assert datetime(2021, 1, 9, 12, 0, tzinfo=timezone.utc) not in timestamps
    assert datetime(2021, 1, 11, 21, 30, tzinfo=timezone.utc) not in timestamps
    assert monday_open + timedelta(minutes=1) in timestamps
    assert canonical.filter(pl.col("timestamp") == monday_open + timedelta(minutes=1))[
        "is_open_session_gap_fill"
    ].to_list() == [True]


def test_regime_model_inputs_are_invariant_to_future_session_rows() -> None:
    """Observed session ends may change with the suffix; model inputs must not."""

    start = datetime(2021, 1, 4, 14, 0, tzinfo=timezone.utc)
    raw = _bars([start + timedelta(minutes=i) for i in range(6)], base=250.0)
    prefix_rows = 3
    prefix_canonical, _ = canonicalize_ohlcv(
        raw.head(prefix_rows),
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )
    full_canonical, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    prefix_tail = prefix_canonical.row(-1, named=True)
    full_prefix_tail = full_canonical.row(prefix_rows - 1, named=True)
    assert (
        prefix_tail["session_minutes_to_close"]
        != full_prefix_tail["session_minutes_to_close"]
    )
    assert prefix_tail["is_session_close_bar"] is True
    assert full_prefix_tail["is_session_close_bar"] is False
    assert prefix_tail["is_weekly_close_bar"] is True
    assert full_prefix_tail["is_weekly_close_bar"] is False

    legacy_prefix_progress = prefix_tail["session_bar_pos"] / (
        prefix_tail["session_bar_pos"] + prefix_tail["session_minutes_to_close"] + 1
    )
    legacy_full_progress = full_prefix_tail["session_bar_pos"] / (
        full_prefix_tail["session_bar_pos"]
        + full_prefix_tail["session_minutes_to_close"]
        + 1
    )
    assert legacy_prefix_progress != legacy_full_progress

    lookbacks = (2,)
    source_cols = regime_calendar_source_columns(lookbacks=lookbacks)
    feature_cols = regime_calendar_feature_columns(
        timeframes=("15m",), lookbacks=lookbacks
    )
    retired_suffixes = (
        "session_progress",
        "minutes_to_close",
        "session_close",
        "weekly_close",
    )
    assert all(
        not any(column.endswith(suffix) for column in source_cols)
        for suffix in retired_suffixes
    )
    assert all(
        not any(f"_{suffix}_bnd" in column for column in feature_cols)
        for suffix in retired_suffixes
    )

    def model_inputs(canonical: pl.DataFrame) -> pl.DataFrame:
        enriched = enrich_regime_calendar_state_sources(canonical, lookbacks=lookbacks)
        prefix = source_prefix("15m")
        aligned = enriched.select(["timestamp", *source_cols]).rename(
            {column: f"{prefix}{column}" for column in source_cols}
        )
        return add_regime_calendar_state_features(
            aligned,
            timeframes=("15m",),
            lookbacks=lookbacks,
        ).select(["timestamp", *feature_cols])

    assert_frame_equal(
        model_inputs(prefix_canonical),
        model_inputs(full_canonical).head(prefix_rows),
    )


def test_canonical_15m_aggregation_preserves_fill_flags() -> None:
    start = datetime(2021, 1, 4, tzinfo=timezone.utc)
    raw = _bars(
        [start + timedelta(minutes=i) for i in range(15) if i != 7],
        base=300.0,
    )
    canonical_1m, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    canonical_15m = aggregate_canonical_15m(canonical_1m)

    assert len(canonical_15m) == 1
    assert canonical_15m["is_open_session_gap_fill"].to_list() == [True]
    assert canonical_15m["volume"].to_list() == [140.0]


def test_crypto_multi_timeframe_aggregation_drops_incomplete_tails() -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    raw = _bars([start + timedelta(minutes=i) for i in range(90)], base=400.0)
    canonical_1m, _ = canonicalize_ohlcv(
        raw,
        asset_id="BTCUSDT",
        calendar_id=CALENDAR_CRYPTO_24_7,
        timeframe="1m",
    )

    one_hour, one_hour_meta = aggregate_canonical_ohlcv(
        canonical_1m,
        target_timeframe="1h",
    )
    fifteen, fifteen_meta = aggregate_canonical_ohlcv(
        canonical_1m,
        target_timeframe="15m",
    )

    assert len(one_hour) == 1
    assert one_hour_meta["dropped_incomplete_buckets"] == 1
    assert len(fifteen) == 6
    assert fifteen_meta["dropped_incomplete_buckets"] == 0
    assert one_hour["open"].to_list() == [399.9]
    assert one_hour["close"].to_list() == [459.0]
    assert one_hour["high"].to_list() == [459.2]
    assert one_hour["low"].to_list() == [399.8]
    assert one_hour["volume"].to_list() == [600.0]


def test_session_aggregation_keeps_calendar_complete_maintenance_bucket() -> None:
    start = datetime(2021, 1, 4, 20, 0, tzinfo=timezone.utc)
    reopen = datetime(2021, 1, 4, 22, 0, tzinfo=timezone.utc)
    raw = _bars(
        [start + timedelta(minutes=i) for i in range(60)]
        + [reopen + timedelta(minutes=i) for i in range(120)],
        base=500.0,
    )
    canonical_1m, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    four_hour, meta = aggregate_canonical_ohlcv(
        canonical_1m,
        target_timeframe="4h",
    )

    assert len(four_hour) == 1
    assert meta["dropped_incomplete_buckets"] == 0
    assert four_hour["timestamp"].to_list() == [start]
    assert four_hour["volume"].to_list() == [1800.0]


def test_historical_session_close_minutes_do_not_overflow_int8() -> None:
    closes = pl.DataFrame(
        {
            "timestamp": [
                datetime(2021, 1, 1, 20, 59, tzinfo=timezone.utc),
                datetime(2021, 1, 2, 20, 59, tzinfo=timezone.utc),
            ],
            "is_session_close_bar": [True, True],
        }
    )

    assert _historical_session_close_minutes(closes) == {20 * 60 + 59}


def test_session_tail_does_not_match_overflow_alias_of_historical_close() -> None:
    raw = _bars(
        [
            datetime(2021, 1, 1, 20, 59, tzinfo=timezone.utc),
            datetime(2021, 1, 2, 20, 59, tzinfo=timezone.utc),
            # 03:55 and 20:59 differ by 1,024 minutes, but both become -21
            # when minute-of-day arithmetic is accidentally performed as Int8.
            datetime(2021, 1, 3, 3, 55, tzinfo=timezone.utc),
        ],
        base=600.0,
    )
    canonical_1m, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    four_hour, meta = aggregate_canonical_ohlcv(
        canonical_1m,
        target_timeframe="4h",
    )

    assert meta["dropped_incomplete_buckets"] == 1
    assert four_hour["timestamp"].to_list() == [
        datetime(2021, 1, 1, 20, 0, tzinfo=timezone.utc),
        datetime(2021, 1, 2, 20, 0, tzinfo=timezone.utc),
    ]


def test_session_tail_keeps_repeated_high_minute_close_after_widening() -> None:
    raw = _bars(
        [datetime(2021, 1, day, 20, 59, tzinfo=timezone.utc) for day in (1, 2, 3)],
        base=700.0,
    )
    canonical_1m, _ = canonicalize_ohlcv(
        raw,
        asset_id="ES",
        calendar_id=CALENDAR_FUTURES_SESSION_OBSERVED,
        timeframe="1m",
    )

    four_hour, meta = aggregate_canonical_ohlcv(
        canonical_1m,
        target_timeframe="4h",
    )

    assert meta["dropped_incomplete_buckets"] == 0
    assert four_hour["timestamp"].to_list()[-1] == datetime(
        2021, 1, 3, 20, 0, tzinfo=timezone.utc
    )

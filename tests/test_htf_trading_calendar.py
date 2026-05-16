from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl

from scripts.feature_engineering.htf_trading_calendar import (
    CALENDAR_CRYPTO_24_7,
    CALENDAR_FUTURES_SESSION_OBSERVED,
    aggregate_canonical_15m,
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


def test_canonical_15m_aggregation_preserves_fill_flags() -> None:
    start = datetime(2021, 1, 4, tzinfo=timezone.utc)
    raw = _bars(
        [
            start + timedelta(minutes=i)
            for i in range(15)
            if i != 7
        ],
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

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl

from fetchingMultiAsset.aggregate_ohlcv import aggregate_ohlcv
from fetchingMultiAsset.fetch_twelve_data import OHLCV_COLUMNS, TIMESTAMP_DTYPE


def _one_minute_frame(rows: int = 30) -> pl.DataFrame:
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    timestamps = [start + timedelta(minutes=i) for i in range(rows)]
    values = [float(i + 1) for i in range(rows)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": values,
            "high": [value + 0.5 for value in values],
            "low": [value - 0.5 for value in values],
            "close": [value + 0.25 for value in values],
            "volume": [10.0 for _ in values],
            "turnover": [None for _ in values],
            "interval": ["1m" for _ in values],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))


def test_aggregate_1m_to_complete_15m_ohlcv_contract() -> None:
    out = aggregate_ohlcv(
        _one_minute_frame(),
        source_interval="1m",
        target_interval="15m",
    )

    assert out.columns == OHLCV_COLUMNS
    assert out.schema["timestamp"] == TIMESTAMP_DTYPE
    assert out.height == 2
    assert out["timestamp"].to_list() == [
        datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 14, 45, tzinfo=timezone.utc),
    ]
    assert out["open"].to_list() == [1.0, 16.0]
    assert out["high"].to_list() == [15.5, 30.5]
    assert out["low"].to_list() == [0.5, 15.5]
    assert out["close"].to_list() == [15.25, 30.25]
    assert out["volume"].to_list() == [150.0, 150.0]
    assert out["turnover"].to_list() == [None, None]
    assert out["interval"].to_list() == ["15m", "15m"]


def test_aggregate_1m_to_15m_drops_partial_by_default() -> None:
    out = aggregate_ohlcv(
        _one_minute_frame(5),
        source_interval="1m",
        target_interval="15m",
    )
    assert out.height == 0


def test_aggregate_1m_to_15m_can_keep_partial_for_probes() -> None:
    out = aggregate_ohlcv(
        _one_minute_frame(5),
        source_interval="1m",
        target_interval="15m",
        allow_partial=True,
    )
    assert out.height == 1
    assert out["volume"].to_list() == [50.0]

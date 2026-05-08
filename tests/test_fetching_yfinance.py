from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import polars as pl

from fetchingMultiAsset.asset_config import selected_yfinance_futures
from fetchingMultiAsset.fetch_twelve_data import TIMESTAMP_DTYPE, append_ohlcv_batches
from fetchingMultiAsset.fetch_yfinance import (
    latest_complete_bar_start,
    plan_yfinance_demo,
    plan_yfinance_tail,
    resolve_yfinance_demo_window,
    validate_yfinance_continuation,
    yfinance_frame_to_ohlcv,
)


def test_yfinance_registry_maps_same_futures_family() -> None:
    assets = selected_yfinance_futures()

    assert tuple(asset.symbol for asset in assets) == (
        "EURUSD",
        "USDJPY",
        "GC",
        "CL",
        "ES",
        "NQ",
    )
    assert tuple(asset.provider_symbol for asset in assets) == (
        "6E=F",
        "6J=F",
        "GC=F",
        "CL=F",
        "ES=F",
        "NQ=F",
    )
    assert selected_yfinance_futures(["USDJPY"])[0].price_transform == "inverse"


def test_yfinance_frame_normalizes_to_bybit_style_schema() -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [10, 20],
        },
        index=pd.to_datetime(
            ["2026-05-06T12:00:00Z", "2026-05-06T12:01:00Z"],
            utc=True,
        ),
    )

    df = yfinance_frame_to_ohlcv(frame, "1m")

    assert df.columns == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover",
        "interval",
    ]
    assert df.schema["timestamp"] == TIMESTAMP_DTYPE
    assert df["timestamp"].to_list() == [
        datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 6, 12, 1, tzinfo=timezone.utc),
    ]
    assert df["turnover"].to_list() == [None, None]


def test_yfinance_jpy_futures_are_inverted_to_usdjpy_path() -> None:
    frame = pd.DataFrame(
        {
            "Open": [0.0068],
            "High": [0.0069],
            "Low": [0.0067],
            "Close": [0.00675],
            "Volume": [10],
        },
        index=pd.to_datetime(["2026-05-06T12:00:00Z"], utc=True),
    )

    df = yfinance_frame_to_ohlcv(frame, "1m", price_transform="inverse")

    assert df["open"][0] == 1.0 / 0.0068
    assert df["high"][0] == 1.0 / 0.0067
    assert df["low"][0] == 1.0 / 0.0069
    assert df["close"][0] == 1.0 / 0.00675


def test_latest_complete_bar_start_drops_current_incomplete_bar() -> None:
    now = datetime(2026, 5, 6, 12, 7, 22, tzinfo=timezone.utc)

    assert latest_complete_bar_start("1m", now) == datetime(
        2026, 5, 6, 12, 6, tzinfo=timezone.utc
    )
    assert latest_complete_bar_start("15m", now) == datetime(
        2026, 5, 6, 11, 45, tzinfo=timezone.utc
    )


def test_yfinance_tail_plan_requires_recent_databento_anchor(tmp_path) -> None:
    asset = selected_yfinance_futures(["ES"])[0]
    start = datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    rows = pl.DataFrame(
        {
            "timestamp": [start, start + timedelta(minutes=1)],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 20.0],
            "turnover": [None, None],
            "interval": ["1m", "1m"],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        rows,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    plan = plan_yfinance_tail(
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        now=datetime(2026, 5, 6, 12, 5, tzinfo=timezone.utc),
        overlap_bars=2,
    )

    assert plan.needs_fetch
    assert plan.fetch_start == datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc)
    assert plan.fetch_end == datetime(2026, 5, 6, 12, 4, tzinfo=timezone.utc)


def test_yfinance_demo_plan_uses_full_recent_one_minute_window_without_databento(
    tmp_path,
) -> None:
    asset = selected_yfinance_futures(["ES"])[0]
    target_end = datetime(2026, 5, 8, 11, 59, tzinfo=timezone.utc)

    start, end = resolve_yfinance_demo_window(interval="1m", target_end=target_end)
    plan = plan_yfinance_demo(
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        target_end=target_end,
    )

    assert start == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    assert end == target_end
    assert plan.status == "fetch"
    assert plan.fetch_start == start
    assert plan.fetch_end == end
    assert plan.local_last_ts is None


def test_yfinance_tail_plan_refuses_large_gap(tmp_path) -> None:
    asset = selected_yfinance_futures(["ES"])[0]
    rows = pl.DataFrame(
        {
            "timestamp": [datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
            "turnover": [None],
            "interval": ["1m"],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        rows,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    plan = plan_yfinance_tail(
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        now=datetime(2026, 5, 6, 12, 5, tzinfo=timezone.utc),
    )

    assert not plan.needs_fetch
    assert plan.status == "gap_too_large"


def test_yfinance_tail_plan_refuses_old_target_outside_retention(tmp_path) -> None:
    asset = selected_yfinance_futures(["ES"])[0]
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    rows = pl.DataFrame(
        {
            "timestamp": [start, start + timedelta(minutes=1)],
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.5, 101.5],
            "volume": [10.0, 20.0],
            "turnover": [None, None],
            "interval": ["1m", "1m"],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        rows,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    plan = plan_yfinance_tail(
        asset=asset,
        interval="1m",
        base_dir=tmp_path,
        now=datetime(2026, 5, 6, 12, 5, tzinfo=timezone.utc),
        target_end=start + timedelta(minutes=5),
        overlap_bars=2,
    )

    assert not plan.needs_fetch
    assert plan.status == "outside_yahoo_retention"


def test_yfinance_continuation_check_rejects_price_mismatch() -> None:
    timestamps = [
        datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 6, 12, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 6, 12, 2, tzinfo=timezone.utc),
    ]
    databento = pl.DataFrame(
        {"timestamp": timestamps, "close": [100.0, 101.0, 102.0]}
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    yfinance = pl.DataFrame(
        {"timestamp": timestamps, "close": [100.0, 110.0, 102.0]}
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))

    check = validate_yfinance_continuation(
        asset="ES",
        interval="1m",
        databento_df=databento,
        yfinance_df=yfinance,
        databento_last_ts=timestamps[-1],
        min_overlap_bars=3,
        max_close_diff_pct=1.0,
    )

    assert not check.passed
    assert check.overlap_rows == 3
    assert check.max_close_diff_pct is not None
    assert check.max_close_diff_pct > 1.0

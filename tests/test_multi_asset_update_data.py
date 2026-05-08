from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from fetchingMultiAsset.asset_config import (
    selected_assets,
    selected_databento_futures,
    selected_yfinance_futures,
)
from fetchingMultiAsset.fetch_twelve_data import (
    TIMESTAMP_DTYPE,
    append_ohlcv_batches,
    twelve_values_to_ohlcv,
)
from fetchingMultiAsset.update_data import (
    build_local_inventory,
    estimate_twelve_requests,
    plan_auto_fresh_tail,
    provider_list,
)


def test_provider_list_defaults_to_twelve_data_for_backward_compatibility() -> None:
    assert provider_list("", all_providers=False) == ("twelvedata",)
    assert provider_list("", all_providers=True) == (
        "twelvedata",
        "databento",
        "yfinance",
    )
    assert provider_list("auto") == ("auto",)
    assert provider_list("databento,twelvedata") == ("databento", "twelvedata")

    with pytest.raises(argparse.ArgumentTypeError):
        provider_list("unknown")
    with pytest.raises(argparse.ArgumentTypeError):
        provider_list("auto,databento")


def test_core_cli_plan_uses_only_intended_twelve_data_assets(capsys) -> None:
    from fetchingMultiAsset.update_data import main

    result = main(
        [
            "--providers",
            "twelvedata",
            "--core",
            "--dry-run",
            "--htf-only",
            "--start-date",
            "2024-01-02T14:30:00Z",
            "--end-date",
            "2024-01-02T15:30:00Z",
        ]
    )
    out = capsys.readouterr().out

    assert result == 0
    assert "Core source mix" in out
    assert "EURUSD" in out
    assert "USDJPY" in out
    assert "XAUUSD" not in out
    assert "SPX" not in out


def test_demo_cli_uses_yfinance_only_without_paid_fallbacks(capsys) -> None:
    from fetchingMultiAsset.update_data import main

    result = main(
        [
            "--demo",
            "--dry-run",
            "--skip-local-scan",
            "--end-date",
            "2026-05-08T12:00:30Z",
        ]
    )
    out = capsys.readouterr().out

    assert result == 0
    assert "Providers: yfinance" in out
    assert "Demo source mix" in out
    assert "YFINANCE DEMO PLAN" in out
    assert "DATABENTO PRELIMINARY PLAN" not in out
    assert "TWELVE DATA PLAN" not in out
    assert "ES=F" in out
    assert "NQ=F" in out


def test_estimate_twelve_requests_counts_small_missing_range_as_one_request(
    tmp_path,
) -> None:
    asset = selected_assets(["EURUSD"])[0]

    estimates = estimate_twelve_requests(
        assets=(asset,),
        intervals=("15m",),
        start_date=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
        base_dir=tmp_path,
    )

    assert len(estimates) == 1
    assert estimates[0].asset == "EURUSD"
    assert estimates[0].interval == "15m"
    assert estimates[0].estimated_requests == 1
    assert estimates[0].fetch_start == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert estimates[0].fetch_end == datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc)
    assert estimates[0].local_last_ts is None


def test_estimate_twelve_requests_marks_local_range_up_to_date(tmp_path) -> None:
    asset = selected_assets(["EURUSD"])[0]
    existing = twelve_values_to_ohlcv(
        [
            {
                "datetime": "2024-01-01 00:00:00",
                "open": "1",
                "high": "1",
                "low": "1",
                "close": "1",
            },
            {
                "datetime": "2024-01-01 00:15:00",
                "open": "2",
                "high": "2",
                "low": "2",
                "close": "2",
            },
        ],
        "15m",
    )
    append_ohlcv_batches(existing, asset=asset, interval="15m", base_dir=tmp_path)

    estimates = estimate_twelve_requests(
        assets=(asset,),
        intervals=("15m",),
        start_date=datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
        base_dir=tmp_path,
    )

    assert len(estimates) == 1
    assert estimates[0].estimated_requests == 0
    assert estimates[0].fetch_start is None
    assert estimates[0].fetch_end is None
    assert estimates[0].local_last_ts == datetime(
        2024, 1, 1, 0, 15, tzinfo=timezone.utc
    )


def test_local_inventory_reports_resume_boundary_without_provider_calls(
    tmp_path,
) -> None:
    asset = selected_databento_futures(["ES"])[0]
    rows = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 14, 31, tzinfo=timezone.utc),
                datetime(2024, 1, 2, 14, 32, tzinfo=timezone.utc),
            ],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [10.0, 20.0, 30.0],
            "turnover": [None, None, None],
            "interval": ["1m", "1m", "1m"],
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

    inventory = build_local_inventory(
        providers=("databento",),
        twelve_assets=(),
        futures_assets=(asset,),
        yfinance_assets=(),
        intervals=("1m",),
        start_date="2021-01-01",
        end_date="2024-01-02T14:35:00Z",
        base_dir=tmp_path,
    )

    assert len(inventory) == 1
    row = inventory[0]
    assert row.asset == "ES"
    assert row.files == 1
    assert row.rows == 3
    assert row.first_ts == datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    assert row.last_ts == datetime(2024, 1, 2, 14, 32, tzinfo=timezone.utc)
    assert any(note.startswith("missing_prefix_from=") for note in row.notes)
    assert any(note.startswith("resume_after=") for note in row.notes)


def test_local_inventory_flags_probe_fragmented_layout(tmp_path) -> None:
    asset = selected_databento_futures(["ES"])[0]
    start = datetime(2024, 1, 2, 14, 30, tzinfo=timezone.utc)
    rows = pl.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=i) for i in range(101)],
            "open": [100.0 + i for i in range(101)],
            "high": [101.0 + i for i in range(101)],
            "low": [99.0 + i for i in range(101)],
            "close": [100.5 + i for i in range(101)],
            "volume": [10.0 for _ in range(101)],
            "turnover": [None for _ in range(101)],
            "interval": ["1m" for _ in range(101)],
        }
    ).with_columns(pl.col("timestamp").cast(TIMESTAMP_DTYPE))
    append_ohlcv_batches(
        rows,
        asset=asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
        chunk_size=1,
    )

    inventory = build_local_inventory(
        providers=("databento",),
        twelve_assets=(),
        futures_assets=(asset,),
        yfinance_assets=(),
        intervals=("1m",),
        start_date=start.isoformat(),
        end_date=(start + timedelta(minutes=100)).isoformat(),
        base_dir=tmp_path,
    )

    assert inventory[0].files == 101
    assert inventory[0].rows == 101
    assert "probe_first_file_rows=1" in inventory[0].notes
    assert "fragmented_avg_rows=1.0" in inventory[0].notes


def test_auto_route_uses_yfinance_for_recent_databento_gap(tmp_path) -> None:
    databento_asset = selected_databento_futures(["ES"])[0]
    yfinance_asset = selected_yfinance_futures(["ES"])[0]
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
        asset=databento_asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    route = plan_auto_fresh_tail(
        futures_assets=(databento_asset,),
        yfinance_assets=(yfinance_asset,),
        end_date="2026-05-06T12:05:00Z",
        overlap_bars=2,
        base_dir=tmp_path,
        now=datetime(2026, 5, 6, 12, 6, tzinfo=timezone.utc),
    )

    assert route.yfinance_assets == (yfinance_asset,)
    assert route.databento_fallback_assets == ()
    assert route.yfinance_plans[0].status == "fetch"


def test_auto_route_uses_databento_when_gap_exceeds_yahoo_range(tmp_path) -> None:
    databento_asset = selected_databento_futures(["ES"])[0]
    yfinance_asset = selected_yfinance_futures(["ES"])[0]
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
        asset=databento_asset,  # type: ignore[arg-type]
        interval="1m",
        base_dir=tmp_path,
        provider="databento",
        market="futures",
    )

    route = plan_auto_fresh_tail(
        futures_assets=(databento_asset,),
        yfinance_assets=(yfinance_asset,),
        end_date="2026-05-06T12:05:00Z",
        overlap_bars=2,
        base_dir=tmp_path,
        now=datetime(2026, 5, 6, 12, 6, tzinfo=timezone.utc),
    )

    assert route.yfinance_assets == ()
    assert route.databento_fallback_assets == (databento_asset,)
    assert route.yfinance_plans[0].status == "gap_too_large"

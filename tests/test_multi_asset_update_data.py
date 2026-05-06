from __future__ import annotations

import argparse
from datetime import datetime, timezone

import pytest

from fetchingMultiAsset.asset_config import selected_assets
from fetchingMultiAsset.fetch_twelve_data import (
    append_ohlcv_batches,
    twelve_values_to_ohlcv,
)
from fetchingMultiAsset.update_data import estimate_twelve_requests, provider_list


def test_provider_list_defaults_to_twelve_data_for_backward_compatibility() -> None:
    assert provider_list("", all_providers=False) == ("twelvedata",)
    assert provider_list("", all_providers=True) == ("twelvedata", "databento")
    assert provider_list("databento,twelvedata") == ("databento", "twelvedata")

    with pytest.raises(argparse.ArgumentTypeError):
        provider_list("unknown")


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

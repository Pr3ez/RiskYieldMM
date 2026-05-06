from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from fetchingByBit import aggregate_to_8h as aggregator


def test_load_4h_data_does_not_fallback_to_other_symbol(tmp_path: Path) -> None:
    source_dir = tmp_path / "mark-price-4h-bybit-linear"
    source_dir.mkdir()
    (source_dir / "btcusdt_mark.parquet").touch()

    assert aggregator.load_4h_data(tmp_path, "mark-price", "ethusdt") is None


def test_aggregate_klines_writes_symbol_specific_8h_file(tmp_path: Path) -> None:
    source_dir = tmp_path / "sorted-4h-bybit-linear"
    source_dir.mkdir()
    rows = [
        datetime(2021, 1, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2021, 1, 1, 4, 0, tzinfo=timezone.utc),
    ]
    pl.DataFrame(
        {
            "timestamp": rows,
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "volume": [100.0, 150.0],
            "turnover": [1000.0, 1800.0],
            "interval": ["4h", "4h"],
        }
    ).write_parquet(source_dir / "ethusdt_linear_sorted_batch_000000.parquet")

    result = aggregator.aggregate_klines(tmp_path, "ethusdt")

    output_file = tmp_path / "sorted-8h-bybit-linear" / "ethusdt_8h.parquet"
    output = pl.read_parquet(output_file)
    assert result["symbol"] == "ethusdt"
    assert result["status"] == "success"
    assert output.height == 1
    assert output["open"].item() == 10.0
    assert output["close"].item() == 12.0
    assert output["volume"].item() == 250.0

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.feature_engineering.htf_multiregime_pipeline import (
    LABEL_WINDOW_OPPOSITE_FIRST_HALF,
    MultiRegimeHTFConfig,
    _build_1m_labels,
    _build_base_combined,
    _build_shifted_combined,
)


def _config(tmp_path: Path, *, asset_id: str = "BTCUSDT") -> MultiRegimeHTFConfig:
    return MultiRegimeHTFConfig(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        raw_data_dir=tmp_path / "fetchingByBit",
        pipeline_artifact_version="test-version",
        thresholds_by_tf={"15m": {"BREAKOUT": 2.1, "RISK_RATIO": 2.5}},
        distance_windows_by_tf={"1m": {}, "15m": {}},
        asset_id=asset_id,
        run_optimization=False,
        run_helpers=False,
        run_validation=False,
        label_window_policy=LABEL_WINDOW_OPPOSITE_FIRST_HALF,
    )


def _raw_ohlcv(start: datetime, rows: int, *, step_minutes: int, base: float) -> pl.DataFrame:
    timestamps = [start + timedelta(minutes=step_minutes * i) for i in range(rows)]
    close = [base + float(i) for i in range(rows)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [value - 0.25 for value in close],
            "high": [value + 0.50 for value in close],
            "low": [value - 0.50 for value in close],
            "close": close,
            "volume": [10.0 + float(i) for i in range(rows)],
            "interval": [f"{step_minutes}m" for _ in range(rows)],
        }
    )


def test_base_combined_routes_by_asset_symbol(tmp_path: Path) -> None:
    raw_dir = tmp_path / "fetchingByBit" / "sorted-1m-bybit-linear"
    raw_dir.mkdir(parents=True)
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    _raw_ohlcv(start, 4, step_minutes=1, base=100.0).write_parquet(
        raw_dir / "btcusdt_linear_sorted_batch_000000.parquet"
    )
    _raw_ohlcv(start, 4, step_minutes=1, base=200.0).write_parquet(
        raw_dir / "ethusdt_linear_sorted_batch_000000.parquet"
    )

    config = _config(tmp_path, asset_id="ETHUSDT")
    result = _build_base_combined(config, regime="8h", tf="1m")

    combined = pl.read_parquet(result["path"])
    assert combined["close"].to_list() == [200.0, 201.0, 202.0, 203.0]


def test_base_combined_prefers_validated_yfinance_tail_over_databento_overlap(
    tmp_path: Path,
) -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    db_dir = tmp_path / "fetchingMultiAsset" / "sorted-1m-databento-futures"
    yf_dir = tmp_path / "fetchingMultiAsset" / "sorted-1m-yfinance-futures"
    db_dir.mkdir(parents=True)
    yf_dir.mkdir(parents=True)
    _raw_ohlcv(start, 3, step_minutes=1, base=4000.0).write_parquet(
        db_dir / "es_databento_sorted_batch_000000.parquet"
    )
    _raw_ohlcv(start + timedelta(minutes=2), 2, step_minutes=1, base=5000.0).write_parquet(
        yf_dir / "es_yfinance_sorted_batch_000000.parquet"
    )

    config = _config(tmp_path, asset_id="ES")
    result = _build_base_combined(config, regime="8h", tf="1m")

    combined = pl.read_parquet(result["path"]).sort("timestamp")
    assert combined["timestamp"].to_list() == [
        start,
        start + timedelta(minutes=1),
        start + timedelta(minutes=2),
        start + timedelta(minutes=3),
    ]
    assert combined["close"].to_list() == [4000.0, 4001.0, 5000.0, 5001.0]


def test_opposite_family_labels_use_next_c_first_half_for_b_entries(tmp_path: Path) -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    raw_1m = tmp_path / "fetchingByBit" / "sorted-1m-bybit-linear"
    raw_15m = tmp_path / "fetchingByBit" / "sorted-15m-bybit-linear"
    raw_1m.mkdir(parents=True)
    raw_15m.mkdir(parents=True)
    _raw_ohlcv(start, 16 * 60, step_minutes=1, base=100.0).write_parquet(
        raw_1m / "btcusdt_linear_sorted_batch_000000.parquet"
    )
    _raw_ohlcv(start, 16 * 4, step_minutes=15, base=100.0).write_parquet(
        raw_15m / "btcusdt_linear_sorted_batch_000000.parquet"
    )

    config = _config(tmp_path, asset_id="BTCUSDT")
    for tf in ("1m", "15m"):
        _build_base_combined(config, regime="8h", tf=tf)
        _build_shifted_combined(config, regime="8h", tf=tf)

    result = _build_1m_labels(config, regime="8h", family="B")
    label_batch = pl.read_parquet(Path(result["label_dir"]) / "batch_0001.parquet")
    valid = label_batch.filter(pl.col("target_4class") >= 0)

    assert len(valid) == 240
    assert valid["label_window_policy"].unique().to_list() == [
        LABEL_WINDOW_OPPOSITE_FIRST_HALF
    ]
    assert valid["label_entry_family"].unique().to_list() == ["B"]
    assert valid["label_window_family"].unique().to_list() == ["C"]
    assert valid["label_window_batch_id"].unique().to_list() == [1]
    assert valid["label_window_start"].unique().to_list() == [
        start + timedelta(hours=4)
    ]
    assert valid["label_window_end"].unique().to_list() == [
        start + timedelta(hours=8)
    ]
    assert valid["remaining_bars"].unique().to_list() == [16]


def test_opposite_family_labels_use_next_b_first_half_for_c_entries(tmp_path: Path) -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    raw_1m = tmp_path / "fetchingByBit" / "sorted-1m-bybit-linear"
    raw_15m = tmp_path / "fetchingByBit" / "sorted-15m-bybit-linear"
    raw_1m.mkdir(parents=True)
    raw_15m.mkdir(parents=True)
    _raw_ohlcv(start, 16 * 60, step_minutes=1, base=100.0).write_parquet(
        raw_1m / "btcusdt_linear_sorted_batch_000000.parquet"
    )
    _raw_ohlcv(start, 16 * 4, step_minutes=15, base=100.0).write_parquet(
        raw_15m / "btcusdt_linear_sorted_batch_000000.parquet"
    )

    config = _config(tmp_path, asset_id="BTCUSDT")
    for tf in ("1m", "15m"):
        _build_base_combined(config, regime="8h", tf=tf)
        _build_shifted_combined(config, regime="8h", tf=tf)

    result = _build_1m_labels(config, regime="8h", family="C")
    label_batch = pl.read_parquet(Path(result["label_dir"]) / "batch_0001.parquet")
    valid = label_batch.filter(pl.col("target_4class") >= 0)

    assert len(valid) == 240
    assert valid["label_window_policy"].unique().to_list() == [
        LABEL_WINDOW_OPPOSITE_FIRST_HALF
    ]
    assert valid["label_entry_family"].unique().to_list() == ["C"]
    assert valid["label_window_family"].unique().to_list() == ["B"]
    assert valid["label_window_batch_id"].unique().to_list() == [2]
    assert valid["label_window_start"].unique().to_list() == [
        start + timedelta(hours=8)
    ]
    assert valid["label_window_end"].unique().to_list() == [
        start + timedelta(hours=12)
    ]
    assert valid["remaining_bars"].unique().to_list() == [16]

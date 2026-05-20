from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import json

import polars as pl

from scripts.feature_engineering.htf_trading_calendar import (
    CALENDAR_CRYPTO_24_7,
    canonicalize_ohlcv,
)
from scripts.feature_engineering.materialize_canonical_ohlcv import (
    canonical_ohlcv_path,
    materialize_one,
    normalize_timeframes,
    status_one,
)


def _raw_minutes(start: datetime, n: int) -> pl.DataFrame:
    close = [100.0 + i for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=i) for i in range(n)],
            "open": [value - 0.5 for value in close],
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [1.0 for _ in range(n)],
        }
    )


def _write_source_1m(project_root: Path, asset_id: str = "BTCUSDT", rows: int = 75) -> Path:
    raw = _raw_minutes(datetime(2021, 1, 1, tzinfo=timezone.utc), rows)
    canonical, _ = canonicalize_ohlcv(
        raw,
        asset_id=asset_id,
        calendar_id=CALENDAR_CRYPTO_24_7,
        timeframe="1m",
    )
    source_path = canonical_ohlcv_path(project_root, asset_id, "1m")
    source_path.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_parquet(source_path)
    return source_path


def test_normalize_timeframes_accepts_24h_alias_and_deduplicates() -> None:
    assert normalize_timeframes("15m,24h,1d,4h") == ("15m", "1d", "4h")


def test_materializer_dry_run_detects_source_without_writing(tmp_path: Path) -> None:
    _write_source_1m(tmp_path)

    result = materialize_one(
        project_root=tmp_path,
        asset_id="BTCUSDT",
        timeframe="15m",
        dry_run=True,
    )

    assert result.status == "would_create"
    assert not result.output_path.exists()


def test_materializer_writes_output_and_sidecar_metadata(tmp_path: Path) -> None:
    _write_source_1m(tmp_path, rows=75)

    result = materialize_one(
        project_root=tmp_path,
        asset_id="BTCUSDT",
        timeframe="1h",
        dry_run=False,
    )

    assert result.status == "written"
    assert result.rows == 1
    assert result.output_path.exists()
    assert result.meta_path.exists()
    out = pl.read_parquet(result.output_path)
    assert out["timestamp"].to_list() == [datetime(2021, 1, 1, tzinfo=timezone.utc)]
    assert out["volume"].to_list() == [60.0]
    meta = json.loads(result.meta_path.read_text())
    assert meta["target_timeframe"] == "1h"
    assert meta["rows"] == 1
    assert meta["dropped_incomplete_buckets"] == 1
    assert "timestamp + timeframe" in meta["timestamp_semantics"]


def test_status_fails_clearly_when_output_missing(tmp_path: Path) -> None:
    _write_source_1m(tmp_path)

    result = status_one(tmp_path, "BTCUSDT", "15m")

    assert result.status == "missing_output"
    assert "Missing derived canonical file" in result.detail

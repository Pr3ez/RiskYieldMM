from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import polars as pl

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_export as chart_export_module  # noqa: E402


def _canonical_file(path: Path, *, rows: int = 100) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pl.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=index) for index in range(rows)],
            "open": [100.0 + index for index in range(rows)],
            "high": [101.0 + index for index in range(rows)],
            "low": [99.0 + index for index in range(rows)],
            "close": [100.5 + index for index in range(rows)],
            "volume": [10.0] * rows,
        }
    )
    frame.write_parquet(path)
    return frame


def _patch_resolution(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(
        chart_export_module,
        "resolve_ohlcv_files",
        lambda **_kwargs: SimpleNamespace(
            asset="BTCUSDT",
            timeframe="1m",
            source="canonical",
            provider="canonical",
            description="test canonical",
            source_root=path.parent,
            files=(path,),
        ),
    )


def test_canonical_window_returns_exact_bounded_tail(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "canonical.parquet"
    source = _canonical_file(path)
    _patch_resolution(monkeypatch, path)

    frame, metadata = chart_export_module.load_ohlcv_window(
        asset="BTCUSDT",
        timeframe="1m",
        source="canonical",
        max_bars=10,
    )

    assert frame["timestamp"].to_list() == source.tail(10)["timestamp"].to_list()
    assert metadata["rows_before_window_limit"] == 100
    assert metadata["truncated_to_max_bars"] is True


def test_canonical_indicator_context_returns_rows_immediately_before_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "canonical.parquet"
    source = _canonical_file(path)
    _patch_resolution(monkeypatch, path)

    context = chart_export_module.load_ohlcv_calculation_context(
        asset="BTCUSDT",
        timeframe="1m",
        source="canonical",
        before=source["timestamp"][90],
        max_bars=5,
    )

    assert context["timestamp"].to_list() == source.slice(85, 5)["timestamp"].to_list()

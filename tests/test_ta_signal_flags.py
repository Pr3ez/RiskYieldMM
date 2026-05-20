from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from TA_backtest_optimization.materialize_ta_flags import (
    compute_ta_events,
    expand_events_to_1m,
    materialize_one,
    status_one,
    ta_events_path,
    ta_flags_path,
)
from scripts.htf_backtest.catboost.utils import get_feature_columns


def _minute_rows(start: datetime, rows: int) -> list[datetime]:
    return [start + timedelta(minutes=i) for i in range(rows)]


def _canonical_frame(timestamps: list[datetime]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + i for i in range(len(timestamps))],
            "high": [101.0 + i for i in range(len(timestamps))],
            "low": [99.0 + i for i in range(len(timestamps))],
            "close": [100.5 + i for i in range(len(timestamps))],
            "volume": [10.0 for _ in timestamps],
            "asset_id": ["BTCUSDT" for _ in timestamps],
            "calendar_id": ["crypto_24_7" for _ in timestamps],
            "is_market_open": [True for _ in timestamps],
            "is_synthetic_no_trade": [False for _ in timestamps],
            "is_open_session_gap_fill": [False for _ in timestamps],
            "minutes_since_prev_real_bar": [1.0 for _ in timestamps],
            "session_id": [1 for _ in timestamps],
            "session_date": [ts.date().isoformat() for ts in timestamps],
            "session_bar_pos": list(range(len(timestamps))),
            "session_minutes_to_close": [0 for _ in timestamps],
            "is_session_open_bar": [False for _ in timestamps],
            "is_session_close_bar": [False for _ in timestamps],
            "is_weekly_open_bar": [False for _ in timestamps],
            "is_weekly_close_bar": [False for _ in timestamps],
        }
    )


def test_post_close_expansion_does_not_flag_source_bar_rows() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    one_minute = pl.DataFrame({"timestamp": _minute_rows(start, 30)})
    events = pl.DataFrame(
        {
            "timestamp": [start],
            "signal_available_ts": [start + timedelta(minutes=15)],
            "ta_15m_test_long": [1],
        }
    )

    expanded = expand_events_to_1m(events, one_minute, "15m")

    assert expanded.filter(pl.col("timestamp") < start + timedelta(minutes=15))[
        "ta_15m_test_long"
    ].sum() == 0
    assert expanded.filter(pl.col("timestamp") >= start + timedelta(minutes=15))[
        "ta_15m_test_long"
    ].sum() == 15


def test_session_1d_expansion_uses_next_market_open_rows() -> None:
    friday = datetime(2024, 1, 5, 23, 50, tzinfo=timezone.utc)
    monday = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)
    one_minute = pl.DataFrame(
        {
            "timestamp": [
                *(friday + timedelta(minutes=i) for i in range(10)),
                *(monday + timedelta(minutes=i) for i in range(1440)),
            ]
        }
    )
    events = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 5, 0, 0, tzinfo=timezone.utc)],
            "signal_available_ts": [datetime(2024, 1, 6, 0, 0, tzinfo=timezone.utc)],
            "ta_1d_test_long": [1],
        }
    )

    expanded = expand_events_to_1m(events, one_minute, "1d")

    assert expanded.filter(pl.col("timestamp") < monday)["ta_1d_test_long"].sum() == 0
    assert expanded.filter(pl.col("timestamp") >= monday)["ta_1d_test_long"].sum() == 1440


def test_donchian_breakout_uses_previous_channel_not_current_high() -> None:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    timestamps = _minute_rows(start, 21)
    frame = _canonical_frame(timestamps).with_columns(
        [
            pl.lit(10.0).alias("high"),
            pl.lit(8.0).alias("low"),
            pl.lit(9.0).alias("close"),
        ]
    )
    frame = frame.with_columns(
        [
            pl.when(pl.arange(0, pl.len()) == 20).then(20.0).otherwise(pl.col("high")).alias("high"),
            pl.when(pl.arange(0, pl.len()) == 20).then(11.0).otherwise(pl.col("close")).alias("close"),
        ]
    )

    events = compute_ta_events(frame, "15m")

    assert events["ta_15m_donchian_breakout_long"][20] == 1


def test_warmup_rows_do_not_emit_supertrend_state_flags() -> None:
    frame = _canonical_frame(
        _minute_rows(datetime(2024, 1, 1, tzinfo=timezone.utc), 12)
    )

    events = compute_ta_events(frame, "15m")

    assert events["ta_15m_supertrend_long_state"][:9].sum() == 0
    assert events["ta_15m_supertrend_short_state"][:9].sum() == 0


def test_metadata_columns_are_excluded_from_model_features() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, tzinfo=timezone.utc)],
            "batch_id": [1],
            "signal_valid_rows": [15],
            "signal_params_hash": ["abc"],
            "ta_15m_test_long": [1],
            "target_4class": [2],
        }
    )

    assert get_feature_columns(df) == ["ta_15m_test_long"]


def test_materializer_writes_events_flags_and_status(tmp_path: Path) -> None:
    project_root = tmp_path
    asset_dir = project_root / "data" / "htf_multiasset" / "btcusdt" / "htf_canonical_ohlcv"
    one_minute = _canonical_frame(_minute_rows(datetime(2024, 1, 1, tzinfo=timezone.utc), 60))
    fifteen = _canonical_frame(
        [
            datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 1, 0, 15, tzinfo=timezone.utc),
        ]
    )
    (asset_dir / "1m").mkdir(parents=True)
    (asset_dir / "15m").mkdir(parents=True)
    one_minute.write_parquet(asset_dir / "1m" / "btcusdt_1m_canonical.parquet")
    fifteen.write_parquet(asset_dir / "15m" / "btcusdt_15m_canonical.parquet")

    result = materialize_one(project_root=project_root, asset_id="BTCUSDT", timeframe="15m")

    assert result.status == "written"
    assert ta_events_path(project_root, "BTCUSDT", "15m").exists()
    assert ta_flags_path(project_root, "BTCUSDT", "15m").exists()
    status = status_one(project_root, "BTCUSDT", "15m")
    assert status.status == "ok"
    assert status.flag_rows == 60
    assert status.flag_columns > 0


def test_materializer_valid_until_uses_canonical_market_open_rows(tmp_path: Path) -> None:
    project_root = tmp_path
    asset_dir = project_root / "data" / "htf_multiasset" / "btcusdt" / "htf_canonical_ohlcv"
    friday = datetime(2024, 1, 5, 23, 50, tzinfo=timezone.utc)
    monday = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)
    one_minute = _canonical_frame(
        [
            *(friday + timedelta(minutes=i) for i in range(10)),
            *(monday + timedelta(minutes=i) for i in range(1440)),
        ]
    )
    daily = _canonical_frame([datetime(2024, 1, 5, 0, 0, tzinfo=timezone.utc)])
    (asset_dir / "1m").mkdir(parents=True)
    (asset_dir / "1d").mkdir(parents=True)
    one_minute.write_parquet(asset_dir / "1m" / "btcusdt_1m_canonical.parquet")
    daily.write_parquet(asset_dir / "1d" / "btcusdt_1d_canonical.parquet")

    result = materialize_one(project_root=project_root, asset_id="BTCUSDT", timeframe="1d")

    assert result.status == "written"
    events = pl.read_parquet(ta_events_path(project_root, "BTCUSDT", "1d"))
    assert events["signal_valid_until_ts"][0] == datetime(
        2024, 1, 9, 0, 0, tzinfo=timezone.utc
    )

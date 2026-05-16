from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

from scripts.feature_engineering.htf_multiregime_pipeline import (
    LABEL_WINDOW_OPPOSITE_FIRST_HALF,
    LABEL_WINDOW_SAME_FAMILY,
    MultiRegimeHTFConfig,
    _build_1m_labels,
    _build_base_combined,
    _build_shifted_combined,
    _remaining_bars_validation_rule,
    _run_optimization,
    _unexpected_constant_helper_columns,
)
from scripts.feature_engineering.htf_trading_calendar import (
    CALENDAR_FUTURES_SESSION_OBSERVED,
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


def _raw_ohlcv_from_timestamps(timestamps: list[datetime], *, base: float) -> pl.DataFrame:
    close = [base + float(i) * 0.01 for i, _ in enumerate(timestamps)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [value - 0.25 for value in close],
            "high": [value + 0.50 for value in close],
            "low": [value - 0.50 for value in close],
            "close": close,
            "volume": [10.0 + float(i % 100) for i, _ in enumerate(timestamps)],
        }
    )


def _session_timestamps(
    start: datetime,
    days: int,
    *,
    step_minutes: int,
) -> list[datetime]:
    timestamps: list[datetime] = []
    for day_offset in range(days):
        day = start + timedelta(days=day_offset)
        midnight = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        weekday = midnight.weekday()
        segments: list[tuple[datetime, datetime]] = []
        if weekday <= 4:
            segments.append((midnight, midnight + timedelta(hours=20, minutes=59)))
        if weekday <= 3:
            segments.append((midnight + timedelta(hours=22), midnight + timedelta(hours=23, minutes=59)))
        if weekday == 6:
            segments.append((midnight + timedelta(hours=22), midnight + timedelta(hours=23, minutes=59)))
        for segment_start, segment_end in segments:
            cursor = segment_start
            while cursor <= segment_end:
                timestamps.append(cursor)
                cursor += timedelta(minutes=step_minutes)
    return timestamps


def _write_session_asset_raw(
    tmp_path: Path,
    *,
    asset_slug: str,
    start: datetime,
    days: int,
) -> None:
    raw_1m = tmp_path / "fetchingMultiAsset" / "sorted-1m-databento-futures"
    raw_15m = tmp_path / "fetchingMultiAsset" / "sorted-15m-databento-futures"
    raw_1m.mkdir(parents=True)
    raw_15m.mkdir(parents=True)
    _raw_ohlcv_from_timestamps(
        _session_timestamps(start, days, step_minutes=1),
        base=4000.0,
    ).write_parquet(raw_1m / f"{asset_slug}_databento_sorted_batch_000000.parquet")
    _raw_ohlcv_from_timestamps(
        _session_timestamps(start, days, step_minutes=15),
        base=4000.0,
    ).write_parquet(raw_15m / f"{asset_slug}_databento_sorted_batch_000000.parquet")


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


def test_base_combined_derives_canonical_15m_from_canonical_1m_when_raw_15m_absent(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "fetchingByBit" / "sorted-1m-bybit-linear"
    raw_dir.mkdir(parents=True)
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    _raw_ohlcv(start, 30, step_minutes=1, base=100.0).write_parquet(
        raw_dir / "btcusdt_linear_sorted_batch_000000.parquet"
    )

    config = _config(tmp_path, asset_id="BTCUSDT")
    _build_base_combined(config, regime="8h", tf="1m")
    result = _build_base_combined(config, regime="8h", tf="15m")

    combined_15m = pl.read_parquet(result["path"]).sort("timestamp")
    assert len(combined_15m) == 2
    assert combined_15m["timestamp"].to_list() == [
        start,
        start + timedelta(minutes=15),
    ]


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


def test_opposite_family_labels_use_period_keys_when_session_batches_skip(
    tmp_path: Path,
) -> None:
    start = datetime(2021, 1, 1, tzinfo=timezone.utc)
    raw_1m = tmp_path / "fetchingMultiAsset" / "sorted-1m-databento-futures"
    raw_15m = tmp_path / "fetchingMultiAsset" / "sorted-15m-databento-futures"
    raw_1m.mkdir(parents=True)
    raw_15m.mkdir(parents=True)

    pl.concat(
        [
            _raw_ohlcv(start, 8 * 60, step_minutes=1, base=100.0),
            _raw_ohlcv(start + timedelta(hours=16), 16 * 60, step_minutes=1, base=200.0),
        ]
    ).write_parquet(raw_1m / "es_databento_sorted_batch_000000.parquet")
    pl.concat(
        [
            _raw_ohlcv(start, 8 * 4, step_minutes=15, base=100.0),
            _raw_ohlcv(start + timedelta(hours=16), 16 * 4, step_minutes=15, base=200.0),
        ]
    ).write_parquet(raw_15m / "es_databento_sorted_batch_000000.parquet")

    config = _config(tmp_path, asset_id="ES")
    for tf in ("1m", "15m"):
        _build_base_combined(config, regime="8h", tf=tf)
        _build_shifted_combined(config, regime="8h", tf=tf)

    result = _build_1m_labels(config, regime="8h", family="B")

    assert result["batches"] == 3
    assert (Path(result["label_dir"]) / "batch_0002.parquet").exists()
    label_batch = pl.read_parquet(Path(result["label_dir"]) / "batch_0002.parquet")
    valid = label_batch.filter(pl.col("target_4class") >= 0)

    assert len(valid) == 240
    assert valid["bar_pos_15m"].null_count() == 0
    assert valid["label_window_batch_id"].unique().to_list() == [3]
    assert valid["label_window_start"].unique().to_list() == [
        start + timedelta(hours=20)
    ]
    assert valid["label_window_end"].unique().to_list() == [
        start + timedelta(hours=24)
    ]


def test_session_24h_and_7d_regimes_produce_valid_calendar_aware_labels(
    tmp_path: Path,
) -> None:
    start = datetime(2021, 1, 4, tzinfo=timezone.utc)
    _write_session_asset_raw(tmp_path, asset_slug="es", start=start, days=22)

    config = _config(tmp_path, asset_id="ES")
    for regime in ("24h", "7d"):
        for tf in ("1m", "15m"):
            _build_base_combined(config, regime=regime, tf=tf)
            _build_shifted_combined(config, regime=regime, tf=tf)

        b_result = _build_1m_labels(config, regime=regime, family="B")
        c_result = _build_1m_labels(config, regime=regime, family="C")

        assert b_result["valid_labels"] > 0
        assert c_result["valid_labels"] > 0
        combined = pl.read_parquet(
            tmp_path
            / "data"
            / f"htf_backtest_{regime}"
            / "1m_HTF_combined.parquet"
        )
        assert combined["calendar_id"].unique().to_list() == [
            CALENDAR_FUTURES_SESSION_OBSERVED
        ]
        assert not combined.filter(pl.col("timestamp").dt.weekday() == 6).height


def test_opposite_family_remaining_bars_validation_uses_label_window(tmp_path: Path) -> None:
    df = pl.DataFrame(
        {
            "target_4class": [0, 1, -1],
            "remaining_bars": [16, 16, 999],
            "bar_pos_15m": [31, 31, 31],
        }
    )

    opposite_config = _config(tmp_path, asset_id="BTCUSDT")
    check_name, violation_expr, detail = _remaining_bars_validation_rule(
        opposite_config,
        "8h",
    )
    opposite_violations = (
        df.lazy()
        .filter((pl.col("target_4class") >= 0) & violation_expr)
        .select(pl.len())
        .collect()
        .item()
    )

    same_family_config = _config(tmp_path, asset_id="BTCUSDT")
    same_family_config.label_window_policy = LABEL_WINDOW_SAME_FAMILY
    same_check_name, same_violation_expr, _ = _remaining_bars_validation_rule(
        same_family_config,
        "8h",
    )
    same_family_violations = (
        df.lazy()
        .filter((pl.col("target_4class") >= 0) & same_violation_expr)
        .select(pl.len())
        .collect()
        .item()
    )

    assert check_name == "remaining_bars_within_label_window"
    assert detail == "max=16"
    assert opposite_violations == 0
    assert same_check_name == "remaining_bars_within_batch"
    assert same_family_violations == 2


def test_garch_persistence_is_allowed_known_constant_helper() -> None:
    unexpected = _unexpected_constant_helper_columns(
        [
            {"column": "H_4cl_1_garch_persistence", "unique_non_null": 1},
            {"column": "H_4cl_1_other_helper", "unique_non_null": 1},
        ]
    )

    assert unexpected == [
        {"column": "H_4cl_1_other_helper", "unique_non_null": 1}
    ]


def test_optimization_skips_empty_label_directories(tmp_path: Path) -> None:
    config = _config(tmp_path, asset_id="BTCUSDT")
    feature_dir = tmp_path / "data" / "htf_features" / "1m"
    label_dir = tmp_path / "data" / "htf_4class_labels" / "1m"
    feature_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [datetime(2021, 1, 1, tzinfo=timezone.utc)],
            "batch_id": [1],
            "F_example": [1.0],
        }
    ).write_parquet(feature_dir / "batch_0001.parquet")

    result = _run_optimization(config, regime="8h", family="B")

    assert result == {"skipped": True, "reason": "no_label_batches"}

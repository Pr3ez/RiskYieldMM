from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl

from scripts.analysis.analyst_next_feature_study import (
    CANDIDATE_COLUMNS,
    build_candidate_frame,
)


def _bars(rows: int = 600) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close = np.asarray(
        [
            100.0 * np.exp(0.0003 * index + 0.01 * np.sin(index / 11.0))
            for index in range(rows)
        ]
    )
    open_value = np.r_[close[0], close[:-1]]
    spread = 0.002 + 0.001 * (1.0 + np.sin(np.arange(rows) / 7.0))
    high = np.maximum(open_value, close) * (1.0 + spread)
    low = np.minimum(open_value, close) * (1.0 - spread)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=index) for index in range(rows)],
            "open": open_value,
            "high": high,
            "low": low,
            "close": close,
            "volume": 1_000.0 + 100.0 * np.sin(np.arange(rows) / 5.0) + np.arange(rows),
            "session_id": [f"BTCUSDT_{index // 24}" for index in range(rows)],
            "session_bar_pos": [index % 24 for index in range(rows)],
            "is_synthetic_no_trade": [False] * rows,
        }
    )


def test_candidate_features_are_prefix_invariant() -> None:
    bars = _bars()
    prefix_rows = 480
    prefix = build_candidate_frame(
        bars.head(prefix_rows), asset="BTCUSDT", timeframe="1h"
    )
    full = build_candidate_frame(bars, asset="BTCUSDT", timeframe="1h").head(
        prefix_rows
    )

    for column in CANDIDATE_COLUMNS:
        np.testing.assert_allclose(
            prefix[column].to_numpy(),
            full[column].to_numpy(),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        )


def test_current_high_does_not_enter_its_own_prior_channel() -> None:
    bars = _bars()
    mutated = bars.with_columns(
        pl.when(pl.int_range(0, pl.len()) == 300)
        .then(pl.col("high") * 2.0)
        .otherwise(pl.col("high"))
        .alias("high")
    )
    original_features = build_candidate_frame(bars, asset="BTCUSDT", timeframe="1h")
    mutated_features = build_candidate_frame(mutated, asset="BTCUSDT", timeframe="1h")

    for column in (
        "channel_position_signed",
        "breakout_balance_vol",
        "room_balance",
    ):
        assert mutated_features.loc[300, column] == original_features.loc[300, column]
    assert (
        mutated_features.loc[301, "channel_position_signed"]
        != original_features.loc[301, "channel_position_signed"]
    )


def test_volume_phase_baseline_never_uses_future_volume() -> None:
    bars = _bars()
    prefix_rows = 520
    mutated = bars.with_columns(
        pl.when(pl.int_range(0, pl.len()) >= prefix_rows)
        .then(pl.col("volume") * 1_000.0)
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    original = build_candidate_frame(bars, asset="BTCUSDT", timeframe="1h")
    changed = build_candidate_frame(mutated, asset="BTCUSDT", timeframe="1h")

    np.testing.assert_allclose(
        original.loc[: prefix_rows - 1, "relative_volume_phase_log"].to_numpy(),
        changed.loc[: prefix_rows - 1, "relative_volume_phase_log"].to_numpy(),
        rtol=0.0,
        atol=0.0,
        equal_nan=True,
    )


def test_forward_outcome_starts_at_next_bar_open() -> None:
    bars = _bars().with_columns(
        pl.when(pl.int_range(0, pl.len()) == 401)
        .then(125.0)
        .otherwise(pl.col("open"))
        .alias("open"),
        pl.when(pl.int_range(0, pl.len()) == 401)
        .then(125.5)
        .otherwise(pl.col("close"))
        .alias("close"),
        pl.when(pl.int_range(0, pl.len()) == 401)
        .then(126.0)
        .otherwise(pl.col("high"))
        .alias("high"),
        pl.when(pl.int_range(0, pl.len()) == 401)
        .then(124.5)
        .otherwise(pl.col("low"))
        .alias("low"),
    )
    features = build_candidate_frame(bars, asset="BTCUSDT", timeframe="1h")

    recovered_raw_return = (
        features.loc[400, "forward_return_1_vol"]
        * features.loc[400, "prior_slow_sigma"]
    )
    assert recovered_raw_return == np.log(125.5 / 125.0)


def test_range_estimators_are_available_without_absolute_value_repair() -> None:
    features = build_candidate_frame(_bars(), asset="BTCUSDT", timeframe="1h")
    mature = features.tail(200)

    assert mature["parkinson_to_close_vol"].notna().all()
    assert mature["rogers_satchell_to_close_vol"].notna().all()
    assert (mature["rogers_satchell_to_close_vol"] >= 0.0).all()

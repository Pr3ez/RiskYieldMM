from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_SOURCE, build_chart_manifest  # noqa: E402
from chart_export import (  # noqa: E402
    build_lightweight_charts_payload,
    normalize_indicators,
)
from indicators import (  # noqa: E402
    CUSUM_SENSITIVITIES,
    CusumTrendEngine,
    compute_cusum_trend,
    compute_ewma_volatility,
)


def _sample_ohlcv(rows: int = 120) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    timestamps = [start + timedelta(hours=idx) for idx in range(rows)]
    close = [
        100.0 + idx * 0.4 + (8.0 if idx > rows // 2 else 0.0) for idx in range(rows)
    ]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [value - 0.2 for value in close],
            "high": [value + 0.8 for value in close],
            "low": [value - 0.8 for value in close],
            "close": close,
            "volume": [100.0 + idx for idx in range(rows)],
        }
    )


def test_cusum_trend_computes_chart_columns() -> None:
    result = compute_cusum_trend(_sample_ohlcv())

    assert result.height == 120
    assert {"up_band", "dn_band", "trail_stop", "regime", "candle_color"} <= set(
        result.columns
    )
    assert result["up_band"].drop_nulls().len() > 0
    assert set(result["regime"].unique().to_list()) <= {-1, 0, 1}


def test_standardized_cusum_waits_for_prior_scale_before_triggering() -> None:
    result = compute_cusum_trend(_sample_ohlcv())

    warmup = result.filter(~pl.col("scale_ready"))
    first_trigger = result.filter(pl.col("bull_start") | pl.col("bear_start")).row(
        0, named=True
    )
    assert (
        warmup.select((pl.col("bull_start") | pl.col("bear_start")).any()).item()
        is False
    )
    assert first_trigger["timestamp"] == result["timestamp"][62]
    assert first_trigger["res_std"] == pytest.approx(1.5178158392725842)
    assert first_trigger["bull_start"] is True
    assert first_trigger["regime"] == 1
    assert first_trigger["bull_pressure"] == 0.0
    assert first_trigger["pressure_pct"] == 0.0


@pytest.mark.parametrize("multiplier", [1e-6, 1e-3, 1.0, 1e3, 1e6])
def test_standardized_cusum_signal_path_is_price_scale_invariant(
    multiplier: float,
) -> None:
    base = compute_cusum_trend(_sample_ohlcv(rows=180))
    scaled = compute_cusum_trend(
        _sample_ohlcv(rows=180).with_columns(
            (pl.col("close") * multiplier).alias("close")
        )
    )

    assert scaled["regime"].to_list() == base["regime"].to_list()
    assert scaled["bull_start"].to_list() == base["bull_start"].to_list()
    assert scaled["bear_start"].to_list() == base["bear_start"].to_list()


def test_cusum_rejects_unknown_sensitivity_instead_of_silent_fallback() -> None:
    with pytest.raises(ValueError, match="Unknown CUSUM sensitivity"):
        compute_cusum_trend(_sample_ohlcv(), sensitivity="typo")


@pytest.mark.parametrize("sensitivity", CUSUM_SENSITIVITIES)
def test_cusum_streaming_engine_matches_batch_exactly(sensitivity: str) -> None:
    frame = _sample_ohlcv(rows=180)
    expected = compute_cusum_trend(frame, sensitivity=sensitivity)
    engine = CusumTrendEngine(sensitivity)
    actual = pl.DataFrame(
        [
            engine.update(timestamp=row["timestamp"], close=row["close"])
            for row in frame.sort("timestamp").iter_rows(named=True)
        ],
        infer_schema_length=None,
    ).select(expected.columns)

    assert_frame_equal(actual, expected, check_exact=True)


def test_cusum_prefix_is_invariant_to_future_close_mutation() -> None:
    frame = _sample_ohlcv(rows=180)
    prefix_rows = 93
    prefix = frame.head(prefix_rows)
    mutated = pl.concat(
        [
            prefix,
            frame.tail(frame.height - prefix_rows).with_columns(
                ((pl.col("close") * -7.0) + 1234.0).alias("close")
            ),
        ]
    )

    expected = compute_cusum_trend(prefix)
    actual = compute_cusum_trend(mutated).head(prefix_rows)

    assert_frame_equal(actual, expected, check_exact=True)


def test_cusum_snapshot_restore_matches_uninterrupted_stream_exactly() -> None:
    frame = _sample_ohlcv(rows=180).sort("timestamp")
    rows = frame.iter_rows(named=True)
    split_at = 87

    uninterrupted = CusumTrendEngine()
    expected = [
        uninterrupted.update(timestamp=row["timestamp"], close=row["close"])
        for row in rows
    ]

    prefix_engine = CusumTrendEngine()
    prefix_rows = frame.head(split_at).iter_rows(named=True)
    actual = [
        prefix_engine.update(timestamp=row["timestamp"], close=row["close"])
        for row in prefix_rows
    ]
    json_snapshot = json.loads(json.dumps(prefix_engine.snapshot()))
    restored = CusumTrendEngine.restore(
        json_snapshot,
        expected_sensitivity="Balanced (Swing)",
    )
    actual.extend(
        restored.update(timestamp=row["timestamp"], close=row["close"])
        for row in frame.tail(frame.height - split_at).iter_rows(named=True)
    )

    assert actual == expected
    assert restored.snapshot() == uninterrupted.snapshot()


def test_chart_payload_can_include_cusum_overlay() -> None:
    frame = _sample_ohlcv()
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "raw",
            "provider": "test",
        },
        indicator="cusum_trend",
        cusum_sensitivity="Balanced (Swing)",
    )

    overlay = payload["overlays"]["cusum_trend"]
    assert len(payload["candles"]) == frame.height
    assert "color" in payload["candles"][-1]
    assert overlay["sensitivity"] == "Balanced (Swing)"
    assert len(overlay["upper_band"]) > 0
    assert len(overlay["lower_band"]) > 0
    assert "status" in overlay["last"]


def test_ewma_volatility_uses_closed_log_return_recursion() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=idx) for idx in range(3)],
            "close": [100.0, 110.0, 110.0],
        }
    )

    result = compute_ewma_volatility(frame, half_lives=(2, 4, 8))
    log_return = math.log(1.1)
    retained = math.exp(-math.log(2.0) / 2.0)

    assert result["ewma_vol_fast_pct"][0] is None
    assert result["ewma_vol_fast_pct"][1] == pytest.approx(100.0 * log_return)
    assert result["ewma_vol_fast_pct"][2] == pytest.approx(
        100.0 * math.sqrt(retained * (log_return**2))
    )
    assert result["fast_slow_ratio"][1] == pytest.approx(1.0)


def test_ewma_variance_seed_has_exact_configured_half_life() -> None:
    half_life = 12
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    initial_return = 0.02
    closes = [100.0, 100.0 * math.exp(initial_return)]
    closes.extend([closes[-1]] * half_life)
    frame = pl.DataFrame(
        {
            "timestamp": [
                start + timedelta(hours=index) for index in range(len(closes))
            ],
            "close": closes,
        }
    )

    result = compute_ewma_volatility(frame, half_lives=(half_life, 48, 192))

    assert result["ewma_vol_fast_pct"][1] == pytest.approx(100.0 * initial_return)
    assert result["ewma_vol_fast_pct"][-1] == pytest.approx(
        100.0 * initial_return * math.sqrt(0.5)
    )
    assert result["ewma_observations"][-1] == half_life + 1


@pytest.mark.parametrize("multiplier", [1e-6, 1.0, 1e6])
def test_ewma_log_return_volatility_is_price_scale_invariant(
    multiplier: float,
) -> None:
    frame = _sample_ohlcv().select("timestamp", "close")
    expected = compute_ewma_volatility(frame)
    actual = compute_ewma_volatility(
        frame.with_columns((pl.col("close") * multiplier).alias("close"))
    )

    for column in (
        "ewma_vol_fast_pct",
        "ewma_vol_medium_pct",
        "ewma_vol_slow_pct",
        "fast_slow_ratio",
    ):
        assert actual[column].to_list() == pytest.approx(expected[column].to_list())


def test_ewma_volatility_resets_invalid_close_chains_without_nonfinite_values() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=idx) for idx in range(6)],
            "close": [100.0, 0.0, 110.0, float("nan"), 120.0, 126.0],
        }
    )

    result = compute_ewma_volatility(frame)

    assert result["ewma_vol_fast_pct"][:5].to_list() == [None] * 5
    assert result["fast_slow_ratio"][:5].to_list() == [None] * 5
    for column in (
        "ewma_vol_fast_pct",
        "ewma_vol_medium_pct",
        "ewma_vol_slow_pct",
        "fast_slow_ratio",
    ):
        for value in result[column].drop_nulls().to_list():
            assert math.isfinite(value)


def test_chart_payload_can_include_ewma_volatility_overlay() -> None:
    frame = _sample_ohlcv()
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
            "provider": "test",
        },
        indicators="ewma_volatility",
    )

    overlay = payload["overlays"]["ewma_volatility"]
    candle_times = {row["time"] for row in payload["candles"]}
    assert payload["metadata"]["indicator"] == "ewma_volatility"
    assert payload["metadata"]["indicator_labels"] == ["EWMA Volatility"]
    assert overlay["unit"] == "percent_per_bar"
    assert overlay["availability"] == "post_close_usable_next_bar"
    assert overlay["half_lives_bars"] == {"fast": 12, "medium": 48, "slow": 192}
    assert len(overlay["fast"]) == frame.height - 1
    assert len(overlay["medium"]) == frame.height - 1
    assert len(overlay["slow"]) == frame.height - 1
    assert all(point["time"] in candle_times for point in overlay["fast"][:-1])
    assert overlay["fast"][-1]["time"] == max(candle_times) + 3600
    assert overlay["plotted_at"] == "earliest_next_bar_execution_time"
    assert all(
        math.isfinite(point["value"]) and point["value"] >= 0.0
        for point in overlay["fast"]
    )
    assert overlay["last"]["status"] in {"Expanding", "Contracting", "Stable"}
    assert overlay["last"]["maturity"] == "warming"
    assert overlay["last"]["observations"] == frame.height - 1


def test_ewma_payload_uses_hidden_context_without_exporting_it() -> None:
    full_frame = _sample_ohlcv(rows=240)
    context = full_frame.head(160)
    display = full_frame.tail(80)
    expected = compute_ewma_volatility(full_frame).filter(
        pl.col("timestamp") >= display["timestamp"].min() - timedelta(hours=1)
    )

    payload = build_lightweight_charts_payload(
        display,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "canonical",
            "provider": "test",
        },
        indicators="ewma_volatility",
        indicator_context=context,
    )

    actual_fast = payload["overlays"]["ewma_volatility"]["fast"]
    expected_fast = expected["ewma_vol_fast_pct"].to_list()
    assert len(payload["candles"]) == display.height
    assert len(actual_fast) == display.height + 1
    assert actual_fast[0]["value"] == pytest.approx(expected_fast[0])
    assert actual_fast[-1]["value"] == pytest.approx(expected_fast[-1])
    assert actual_fast[0]["time"] == payload["candles"][0]["time"]
    assert actual_fast[-1]["time"] == payload["candles"][-1]["time"] + 3600


def test_chart_payload_combines_cusum_and_ewma_overlays() -> None:
    frame = _sample_ohlcv()
    payload = build_lightweight_charts_payload(
        frame,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": "raw",
            "provider": "test",
        },
        indicators=("cusum_trend", "ewma_volatility"),
    )

    assert set(payload["overlays"]) == {"cusum_trend", "ewma_volatility"}
    assert payload["metadata"]["indicator"] == "multiple"
    assert payload["metadata"]["indicator_labels"] == [
        "CUSUM Trend",
        "EWMA Volatility",
    ]
    assert "color" in payload["candles"][-1]


def test_manifest_defaults_to_canonical_dataset() -> None:
    manifest = build_chart_manifest()

    assert manifest["defaults"]["source"] == CANONICAL_SOURCE
    assert manifest["assets"][0]["sources"][0]["source"] == CANONICAL_SOURCE
    assert "main" in manifest["assets"][0]["sources"][0]["label"].lower()
    assert manifest["onlineSignals"]["canonicalSelectionCount"] == 56
    assert manifest["onlineSignals"]["availableForEveryCanonicalSelection"] is True
    assert manifest["onlineSignals"]["boundedReplayForDebugSelections"] is True
    assert manifest["minuteReplay"]["canonicalSelectionCount"] == 56
    assert manifest["minuteReplay"]["availableForEveryCanonicalSelection"] is True
    assert manifest["minuteReplay"]["sourceTimeframe"] == "1m"
    assert manifest["minuteReplay"]["asWasLiveJournal"] is False
    expected_formats = {
        "BTCUSDT": {"precision": 1, "min_move": 0.1},
        "ETHUSDT": {"precision": 2, "min_move": 0.01},
        "CL": {"precision": 2, "min_move": 0.01},
        "ES": {"precision": 2, "min_move": 0.25},
        "EURUSD": {"precision": 5, "min_move": 0.00001},
        "GC": {"precision": 1, "min_move": 0.1},
        "NQ": {"precision": 2, "min_move": 0.25},
        "USDJPY": {"precision": 3, "min_move": 0.001},
    }
    for asset in manifest["assets"]:
        assert asset["priceFormat"] == expected_formats[asset["asset"]]
        for source in asset["sources"]:
            for timeframe in source["timeframes"]:
                assert timeframe["onlineSignals"]["available"] is True
                assert timeframe["onlineSignals"]["persistentLiveReplay"] is (
                    source["source"] == CANONICAL_SOURCE
                )
                assert timeframe["minuteReplay"]["available"] is (
                    source["source"] == CANONICAL_SOURCE
                )


def test_indicator_normalization_accepts_multi_and_legacy_inputs() -> None:
    assert normalize_indicators("cusum_trend,none", indicator="none") == (
        "cusum_trend",
    )
    assert normalize_indicators(["cusum_trend", "cusum_trend"]) == ("cusum_trend",)
    assert normalize_indicators("ewma_volatility,cusum_trend") == (
        "ewma_volatility",
        "cusum_trend",
    )

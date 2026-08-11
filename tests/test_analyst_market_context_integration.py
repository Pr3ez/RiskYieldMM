from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_export as chart_export_module  # noqa: E402
import chart_server as chart_server_module  # noqa: E402
from chart_config import CANONICAL_SOURCE, build_chart_manifest  # noqa: E402
from chart_export import (  # noqa: E402
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_CUSUM_TREND,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
    INDICATOR_PRIOR_STRUCTURE,
    INDICATOR_WARMUP_BARS,
    normalize_indicators,
    required_indicator_warmup_bars,
)

MARKET_CONTEXT_IDS = {
    INDICATOR_PRIOR_STRUCTURE,
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
}
MARKET_CONTEXT_INDICATORS = (
    INDICATOR_PRIOR_STRUCTURE,
    INDICATOR_COMPARABLE_VOLATILITY,
    INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
)


def _minute_frame(rows: int = 4) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=index) for index in range(rows)],
            "open": [100.0 + index for index in range(rows)],
            "high": [101.0 + index for index in range(rows)],
            "low": [99.0 + index for index in range(rows)],
            "close": [100.5 + index for index in range(rows)],
            "volume": [10.0 + index for index in range(rows)],
        }
    )


def _hour_frame(rows: int = 500) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    close = [100.0 + (index * 0.03) + ((index % 17) * 0.02) for index in range(rows)]
    return pl.DataFrame(
        {
            "timestamp": [start + timedelta(hours=index) for index in range(rows)],
            "open": [value - 0.05 for value in close],
            "high": [value + 0.20 for value in close],
            "low": [value - 0.20 for value in close],
            "close": close,
            "volume": [
                100.0 + ((index % 24) * 4.0) + (index % 7) for index in range(rows)
            ],
        }
    )


def test_market_context_ids_support_legacy_and_multi_indicator_inputs() -> None:
    assert normalize_indicators(
        ",".join(sorted(MARKET_CONTEXT_IDS)),
        indicator=INDICATOR_PRIOR_STRUCTURE,
    ) == (
        INDICATOR_PRIOR_STRUCTURE,
        INDICATOR_COMPARABLE_VOLATILITY,
        INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
    )


@pytest.mark.parametrize(
    ("timeframe", "expected"),
    [
        ("1m", 31_872),
        ("5m", 6_528),
        ("15m", 2_304),
        ("1h", INDICATOR_WARMUP_BARS),
        ("1d", INDICATOR_WARMUP_BARS),
    ],
)
def test_participation_hidden_history_is_indicator_and_timeframe_dependent(
    timeframe: str,
    expected: int,
) -> None:
    assert (
        required_indicator_warmup_bars(
            (INDICATOR_PHASE_ADJUSTED_PARTICIPATION,),
            timeframe=timeframe,
        )
        == expected
    )
    assert (
        required_indicator_warmup_bars(
            (INDICATOR_PRIOR_STRUCTURE, INDICATOR_COMPARABLE_VOLATILITY),
            timeframe=timeframe,
        )
        == INDICATOR_WARMUP_BARS
    )


def test_manifest_discovers_all_market_context_layers_for_all_canonical_selections() -> (
    None
):
    manifest = build_chart_manifest()
    indicator_ids = {entry["id"] for entry in manifest["indicators"]}
    assert MARKET_CONTEXT_IDS <= indicator_ids
    assert set(manifest["defaults"]["indicators"]) == indicator_ids
    assert manifest["marketContext"] == {
        "availableForEveryCanonicalSelection": True,
        "boundedDiagnosticsForDebugSelections": True,
        "canonicalSelectionCount": 56,
        "indicators": [
            INDICATOR_PRIOR_STRUCTURE,
            INDICATOR_COMPARABLE_VOLATILITY,
            INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
        ],
        "availability": "post_close_usable_next_bar",
        "phaseReferenceOccurrences": 20,
        "diagnosticOnly": True,
        "changesExecutionDecisions": False,
    }
    canonical_entries = [
        timeframe
        for asset in manifest["assets"]
        for source in asset["sources"]
        if source["source"] == CANONICAL_SOURCE
        for timeframe in source["timeframes"]
    ]
    assert len(canonical_entries) == 56
    assert all(entry["marketContext"]["available"] for entry in canonical_entries)
    assert all(
        entry["marketContext"]["calendarQualityMetadata"] for entry in canonical_entries
    )


def test_canonical_scan_preserves_phase_and_quality_metadata(tmp_path: Path) -> None:
    path = tmp_path / "canonical.parquet"
    _minute_frame().with_columns(
        pl.lit("BTCUSDT").alias("asset_id"),
        pl.lit("crypto_24_7").alias("calendar_id"),
        pl.lit(True).alias("is_market_open"),
        pl.lit(False).alias("is_synthetic_no_trade"),
        pl.lit(False).alias("is_open_session_gap_fill"),
        pl.lit(1).alias("minutes_since_prev_real_bar"),
        pl.lit("BTCUSDT_2026-01-01").alias("session_id"),
        pl.lit("2026-01-01").alias("session_date"),
        pl.int_range(0, 4, eager=True).alias("session_bar_pos"),
        pl.int_range(3, -1, step=-1, eager=True).alias("session_minutes_to_close"),
        pl.lit(False).alias("is_session_open_bar"),
        pl.lit(False).alias("is_session_close_bar"),
        pl.lit(False).alias("is_weekly_open_bar"),
        pl.lit(False).alias("is_weekly_close_bar"),
    ).write_parquet(path)

    result = chart_export_module._scan_ohlcv((path,)).collect()

    assert {
        "asset_id",
        "calendar_id",
        "is_synthetic_no_trade",
        "is_open_session_gap_fill",
        "session_id",
        "session_bar_pos",
        "session_minutes_to_close",
        "is_session_close_bar",
    } <= set(result.columns)


def test_chart_api_requests_long_history_without_expanding_visible_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _minute_frame(2)
    context = _minute_frame(2)
    load_calls: list[dict[str, object]] = []
    captured: dict[str, object] = {}

    def fake_load(**kwargs):
        load_calls.append(kwargs)
        return (
            frame,
            {
                "asset": "BTCUSDT",
                "timeframe": "1m",
                "source": CANONICAL_SOURCE,
                "provider": "canonical",
                "requested_end": "2026-01-01T00:02:00Z",
                "row_count": frame.height,
                "max_bars": kwargs["max_bars"],
                "indicator_warmup_requested": kwargs["indicator_warmup_bars"],
            },
            context,
        )

    monkeypatch.setattr(
        chart_server_module, "load_ohlcv_window_with_context", fake_load
    )

    def fake_payload(**kwargs):
        captured.update(kwargs)
        return {"metadata": kwargs["metadata"], "candles": []}

    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        fake_payload,
    )

    chart_server_module._build_chart_response(
        "asset=BTCUSDT&timeframe=1m&source=canonical&max_bars=37"
        "&end=2026-01-01T00:02:00Z"
        "&indicators=phase_adjusted_participation,prior_structure"
    )

    assert load_calls[0]["max_bars"] == 37
    assert load_calls[0]["indicator_warmup_bars"] == 31_872
    assert captured["frame"].height == 2
    assert captured["indicators"] == (
        INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
        INDICATOR_PRIOR_STRUCTURE,
    )


def test_payload_builds_selected_market_context_once_with_action_time_series() -> None:
    full = _hour_frame()
    context = full.head(420)
    visible = full.tail(80)

    payload = chart_export_module.build_lightweight_charts_payload(
        visible,
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "source": CANONICAL_SOURCE,
            "provider": "canonical",
            "indicator_warmup_loaded": context.height,
        },
        indicators=MARKET_CONTEXT_INDICATORS,
        indicator_context=context,
    )

    assert set(payload["overlays"]) == MARKET_CONTEXT_IDS
    structure = payload["overlays"][INDICATOR_PRIOR_STRUCTURE]
    volatility = payload["overlays"][INDICATOR_COMPARABLE_VOLATILITY]
    participation = payload["overlays"][INDICATOR_PHASE_ADJUSTED_PARTICIPATION]
    assert set(structure["channels"]) == {"4", "16", "48"}
    assert len(structure["channels"]["48"]["upper"]) == visible.height
    assert volatility["volatility_percentile"]
    assert volatility["fast_slow_ratio_score"]
    assert participation["rvol_score"]
    assert structure["channels"]["48"]["upper"][-1]["time"] == int(
        visible["timestamp"].max().timestamp()
    )
    assert volatility["volatility_percentile"][-1]["time"] == int(
        (visible["timestamp"].max() + timedelta(hours=1)).timestamp()
    )
    assert participation["last"]["reference_count"] >= 10
    assert participation["implementation_scope"] == (
        "target_timeframe_prior_phase_median_proxy"
    )
    assert participation["not_implemented"] == (
        "one_minute_constituent_session_total_phase_share_decomposition"
    )
    assert participation["data_provenance"]["chart_provider"] == "canonical"
    assert participation["data_provenance"]["provider_cohort_status"] == (
        "not_carried_in_chart_frame"
    )
    assert participation["data_provenance"]["roll_provenance_status"] == (
        "not_carried_in_chart_frame"
    )
    assert payload["metadata"]["indicator"] == "multiple"
    assert payload["metadata"]["indicators"] == list(MARKET_CONTEXT_INDICATORS)
    assert payload["metadata"]["market_context"]["changes_execution_decisions"] is False


def test_extended_participation_context_does_not_expand_legacy_indicator_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full = _minute_frame(31_882)
    context = full.head(31_872)
    visible = full.tail(10)
    captured: dict[str, int] = {}
    original_cusum = chart_export_module.compute_cusum_trend

    def capture_cusum(frame, **kwargs):
        captured["legacy_rows"] = frame.height
        return original_cusum(frame, **kwargs)

    def capture_market_context(frame, **_kwargs):
        captured["market_context_rows"] = frame.height
        return {
            INDICATOR_PRIOR_STRUCTURE: {},
            INDICATOR_COMPARABLE_VOLATILITY: {},
            INDICATOR_PHASE_ADJUSTED_PARTICIPATION: {
                "id": INDICATOR_PHASE_ADJUSTED_PARTICIPATION,
                "label": "Phase-Adjusted Participation",
                "rvol_score": [],
                "rvol": [],
                "markers": [],
                "last": {},
            },
        }

    monkeypatch.setattr(chart_export_module, "compute_cusum_trend", capture_cusum)
    monkeypatch.setattr(
        chart_export_module,
        "build_market_context_overlays",
        capture_market_context,
    )

    chart_export_module.build_lightweight_charts_payload(
        visible,
        {
            "asset": "BTCUSDT",
            "timeframe": "1m",
            "source": CANONICAL_SOURCE,
            "provider": "canonical",
            "indicator_warmup_loaded": context.height,
        },
        indicators=(INDICATOR_CUSUM_TREND, INDICATOR_PHASE_ADJUSTED_PARTICIPATION),
        indicator_context=context,
    )

    assert captured == {
        "legacy_rows": INDICATOR_WARMUP_BARS + visible.height,
        "market_context_rows": full.height,
    }


def test_market_context_failure_is_explicit_without_hiding_candles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_context(*_args, **_kwargs):
        raise RuntimeError("bad diagnostic input")

    monkeypatch.setattr(
        chart_export_module,
        "build_market_context_overlays",
        fail_context,
    )
    frame = _minute_frame()

    payload = chart_export_module.build_lightweight_charts_payload(
        frame,
        {
            "asset": "BTCUSDT",
            "timeframe": "1m",
            "source": CANONICAL_SOURCE,
            "provider": "canonical",
        },
        indicators=MARKET_CONTEXT_INDICATORS,
    )

    assert len(payload["candles"]) == frame.height
    assert all(
        overlay["status"] == "calculation_error"
        for overlay in payload["overlays"].values()
    )
    assert all(
        "bad diagnostic input" in overlay["reason"]
        for overlay in payload["overlays"].values()
    )

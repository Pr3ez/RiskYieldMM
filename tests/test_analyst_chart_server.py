from __future__ import annotations

import sys
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

import chart_server as chart_server_module  # noqa: E402
from forward_paper.supervisor import ProcessStatus  # noqa: E402


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2026, 1, 1, tzinfo=timezone.utc)],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        }
    )


def _minute_frame(*minutes: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)
                for minute in minutes
            ],
            "open": [100.0 + minute for minute in minutes],
            "high": [101.0 + minute for minute in minutes],
            "low": [99.0 + minute for minute in minutes],
            "close": [100.5 + minute for minute in minutes],
            "volume": [10.0] * len(minutes),
        }
    )


def _chart_metadata(*, timeframe: str = "1m", max_bars: int = 2) -> dict[str, object]:
    return {
        "asset": "BTCUSDT",
        "timeframe": timeframe,
        "source": "canonical",
        "provider": "canonical",
        "description": "canonical test data",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-01T00:01:00Z",
        "requested_start": None,
        "requested_end": None,
        "row_count": 2,
        "rows_before_window_limit": 2,
        "truncated_to_max_bars": False,
        "max_bars": max_bars,
    }


def _source_metadata(generation: str = "source-v1") -> dict[str, object]:
    return {
        "asset": "BTCUSDT",
        "timeframe": "1h",
        "source": "canonical_1m",
        "evaluation_start": "2026-01-01T00:00:00Z",
        "evaluation_end": "2026-01-03T00:00:00Z",
        "source_rows": 2_880,
        "source_generation": generation,
    }


def test_boundary_context_tails_before_collecting_canonical_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int | None]] = []
    frame = _minute_frame(*range(50))

    class FakeSchema:
        def names(self):
            return frame.columns

    class FakeLazy:
        def collect_schema(self):
            return FakeSchema()

        def select(self, _columns):
            calls.append(("select", None))
            return self

        def tail(self, rows):
            calls.append(("tail", rows))
            return self

        def collect(self):
            calls.append(("collect", None))
            return frame

    monkeypatch.setattr(
        chart_server_module,
        "resolve_ohlcv_files",
        lambda **_kwargs: SimpleNamespace(files=(Path("canonical.parquet"),)),
    )
    monkeypatch.setattr(
        chart_server_module.pl,
        "scan_parquet",
        lambda _paths: FakeLazy(),
    )

    result = chart_server_module._canonical_minute_boundary_context(
        asset="BTCUSDT",
        timeframe="15m",
    )

    assert calls.index(("tail", 256)) < calls.index(("collect", None))
    assert result is not None
    assert result.height == 17


def test_chart_response_merges_live_tail_before_final_max_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _minute_frame(0, 1)
    combined = _minute_frame(0, 1, 2)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window",
        lambda **_kwargs: (canonical, _chart_metadata()),
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_live_chart_overlay",
        lambda frame, **kwargs: SimpleNamespace(
            frame=combined,
            metadata={
                "available": True,
                "generation": "journal-head-2",
                "live_rows_appended": 1,
                "provider": "bybit",
                "quality": "live",
            },
        ),
    )

    def fake_payload(**kwargs):
        captured.update(kwargs)
        return {"metadata": kwargs["metadata"], "candles": [{"time": 1}]}

    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        fake_payload,
    )

    payload = chart_server_module._build_chart_response(
        "asset=BTCUSDT&timeframe=1m&source=canonical&max_bars=2"
    )

    assert (
        captured["frame"]["timestamp"].to_list()
        == combined.tail(2)["timestamp"].to_list()
    )
    assert payload["metadata"]["live_source_generation"] == "journal-head-2"
    assert payload["metadata"]["live_overlay"]["quality"] == "live"
    assert payload["metadata"]["row_count"] == 2
    assert payload["metadata"]["rows_before_window_limit"] == 3
    assert payload["metadata"]["truncated_to_max_bars"] is True


def test_chart_response_moves_displaced_live_history_into_indicator_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _minute_frame(0, 1)
    canonical = _minute_frame(2, 3)
    combined = _minute_frame(2, 3, 4)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window_with_context",
        lambda **_kwargs: (canonical, _chart_metadata(), context),
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_live_chart_overlay",
        lambda *_args, **_kwargs: SimpleNamespace(
            frame=combined,
            metadata={"generation": "journal-head-4", "live_rows_appended": 1},
        ),
    )

    def fake_payload(**kwargs):
        captured.update(kwargs)
        return {"metadata": kwargs["metadata"], "candles": [{"time": 1}]}

    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        fake_payload,
    )

    chart_server_module._build_chart_response(
        "asset=BTCUSDT&timeframe=1m&source=canonical&max_bars=2&indicators=cusum_trend"
    )

    assert (
        captured["frame"]["timestamp"].to_list()
        == combined.tail(2)["timestamp"].to_list()
    )
    assert (
        captured["indicator_context"]["timestamp"].to_list()
        == _minute_frame(0, 1, 2)["timestamp"].to_list()
    )


def test_chart_response_supports_a_start_inside_the_journal_only_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _minute_frame(0, 1)
    context = _minute_frame()
    combined = _minute_frame(0, 1, 2, 3, 4)
    captured: dict[str, object] = {}
    load_calls: list[dict[str, object]] = []

    def fake_load(**kwargs):
        load_calls.append(kwargs)
        if kwargs.get("start") is not None:
            raise ValueError("No rows found for requested canonical start")
        return canonical, _chart_metadata(), context

    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window_with_context",
        fake_load,
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_live_chart_overlay",
        lambda *_args, **_kwargs: SimpleNamespace(
            frame=combined,
            metadata={"generation": "journal-head-4", "live_rows_appended": 3},
        ),
    )

    def fake_payload(**kwargs):
        captured.update(kwargs)
        return {"metadata": kwargs["metadata"], "candles": [{"time": 1}]}

    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        fake_payload,
    )

    payload = chart_server_module._build_chart_response(
        "asset=BTCUSDT&timeframe=1m&source=canonical&max_bars=2"
        "&start=2026-01-01T00:03:00Z&indicators=cusum_trend"
    )

    assert len(load_calls) == 2
    assert load_calls[1]["start"] is None
    assert (
        captured["frame"]["timestamp"].to_list()
        == _minute_frame(3, 4)["timestamp"].to_list()
    )
    assert (
        captured["indicator_context"]["timestamp"].to_list()
        == _minute_frame(0, 1, 2)["timestamp"].to_list()
    )
    assert payload["metadata"]["live_start_fallback"] is True
    assert payload["metadata"]["requested_start"] == "2026-01-01T00:03:00Z"


def test_mtf_context_retries_canonical_start_then_uses_live_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = _minute_frame(10, 11, 12)
    historical_context = _minute_frame(0, 1, 2)
    live_context = _minute_frame(10, 11, 12)
    load_calls: list[dict[str, object]] = []
    overlay_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        chart_server_module,
        "context_timeframes",
        lambda _timeframe: ("15m",),
    )

    def fake_load(**kwargs):
        load_calls.append(kwargs)
        if kwargs.get("start") is not None:
            raise ValueError("No rows found after canonical materialization")
        return (
            historical_context,
            {**_chart_metadata(), "timeframe": "15m"},
            pl.DataFrame(),
        )

    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window_with_context",
        fake_load,
    )

    def fake_overlay(**kwargs):
        overlay_calls.append(kwargs)
        assert kwargs["metadata"]["live_start_fallback"] is True
        return live_context, kwargs["metadata"], kwargs["indicator_context"]

    monkeypatch.setattr(chart_server_module, "_apply_live_chart_overlay", fake_overlay)
    monkeypatch.setattr(
        chart_server_module,
        "build_causal_mtf_context",
        lambda **kwargs: {
            "status": "ok",
            "frames": sorted(kwargs["calculation_frames"]),
        },
    )

    result = chart_server_module._build_mtf_overlay(
        frame=active,
        metadata=_chart_metadata(),
        indicator_context=pl.DataFrame(),
        max_bars=300,
        end=None,
        calculation_now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert result == {"status": "ok", "frames": ["15m", "1m"]}
    assert len(load_calls) == 2
    assert load_calls[0]["start"] is not None
    assert load_calls[1]["start"] is None
    assert len(overlay_calls) == 1


@pytest.mark.parametrize(
    "query",
    [
        "asset=BTCUSDT&timeframe=1m&source=canonical&end=2026-01-01T00:01:00Z",
        "asset=BTCUSDT&timeframe=1m&source=raw",
    ],
)
def test_chart_response_keeps_anchored_and_debug_requests_deterministic(
    monkeypatch: pytest.MonkeyPatch,
    query: str,
) -> None:
    canonical = _minute_frame(0, 1)
    metadata = _chart_metadata()
    if "source=raw" in query:
        metadata = {**metadata, "source": "raw", "provider": "bybit"}
    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window",
        lambda **_kwargs: (canonical, metadata),
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_live_chart_overlay",
        lambda *_args, **_kwargs: pytest.fail("live overlay must not be read"),
    )
    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        lambda **kwargs: {"metadata": kwargs["metadata"], "candles": [{"time": 1}]},
    )

    payload = chart_server_module._build_chart_response(query)

    assert "live_overlay" not in payload["metadata"]


def test_chart_response_degrades_to_canonical_when_overlay_reader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canonical = _minute_frame(0, 1)
    monkeypatch.setattr(
        chart_server_module,
        "load_ohlcv_window",
        lambda **_kwargs: (canonical, _chart_metadata()),
    )
    monkeypatch.setattr(
        chart_server_module,
        "load_live_chart_overlay",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad WAL")),
    )
    monkeypatch.setattr(
        chart_server_module,
        "build_lightweight_charts_payload",
        lambda **kwargs: {
            "metadata": kwargs["metadata"],
            "candles": kwargs["frame"].to_dicts(),
        },
    )

    payload = chart_server_module._build_chart_response(
        "asset=BTCUSDT&timeframe=1m&source=canonical&max_bars=2"
    )

    assert payload["candles"] == canonical.to_dicts()
    assert payload["metadata"]["live_overlay"]["status"] == "overlay_error"
    assert "bad WAL" in payload["metadata"]["live_overlay"]["reason"]


def test_parse_replay_request_normalizes_supported_parameters() -> None:
    query = urlencode(
        {
            "asset": "btcusdt",
            "timeframe": "4H",
            "source": "CANONICAL",
            "start": "2026-01-01T01:00:00+01:00",
            "end": "2026-01-03T00:00:00Z",
            "replay_days": "14",
            "fee_bps": "2.5",
            "slippage_bps": "3.5",
            "spread_bps": "1.25",
            "execution_latency_minutes": "2",
            "event_limit": "321",
            "cusum_sensitivity": "Fast (Day Trade)",
        }
    )

    request = chart_server_module._parse_replay_request(query)

    assert request.asset == "BTCUSDT"
    assert request.timeframe == "4h"
    assert request.source == "canonical"
    assert request.start == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert request.end == datetime(2026, 1, 3, tzinfo=timezone.utc)
    assert request.replay_days == 14
    assert request.costs.fee_bps == 2.5
    assert request.costs.slippage_bps == 3.5
    assert request.costs.spread_bps == 1.25
    assert request.costs.execution_latency_minutes == 2
    assert request.event_limit == 321
    assert request.strategy.cusum_sensitivity == "Fast (Day Trade)"


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("asset=UNKNOWN", "Unknown asset"),
        ("timeframe=5m", "Unsupported canonical timeframe"),
        ("source=raw", "require source=canonical"),
        ("start=not-a-date", "start must be an ISO-8601"),
        (
            "start=2026-01-03T00%3A00%3A00Z&end=2026-01-01T00%3A00%3A00Z",
            "start must be before end",
        ),
        ("replay_days=0", "replay_days must be between 1 and 730"),
        ("replay_days=731", "replay_days must be between 1 and 730"),
        ("replay_days=one", "replay_days must be an integer"),
        ("fee_bps=-0.1", "fee_bps must be between 0 and 1000"),
        ("fee_bps=1000.1", "fee_bps must be between 0 and 1000"),
        ("fee_bps=nan", "fee_bps must be between 0 and 1000"),
        ("slippage_bps=-1", "slippage_bps must be between 0 and 1000"),
        ("spread_bps=-1", "spread_bps must be between 0 and 1000"),
        (
            "execution_latency_minutes=61",
            "execution_latency_minutes must be between 0 and 60",
        ),
        ("event_limit=5001", "event_limit must be between 0 and 5000"),
        ("cusum_sensitivity=Unknown", "Unknown CUSUM sensitivity"),
    ],
)
def test_parse_replay_request_rejects_invalid_parameters(
    query: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        chart_server_module._parse_replay_request(query)


def test_backtest_orchestration_merges_metadata_and_caches_by_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_server_module._clear_response_cache()
    frame = _frame()
    generation = {"value": "source-v1"}
    load_calls: list[dict[str, object]] = []
    replay_calls: list[dict[str, object]] = []

    def fake_load(**kwargs):
        load_calls.append(kwargs)
        return frame, _source_metadata(generation["value"])

    def fake_replay(received_frame, **kwargs):
        assert received_frame is frame
        replay_calls.append(kwargs)
        return {
            "metadata": {"mode": "stub_minute_replay"},
            "metrics": {"net_return": 0.02},
        }

    monkeypatch.setattr(chart_server_module, "load_canonical_minute_window", fake_load)
    monkeypatch.setattr(chart_server_module, "run_minute_replay", fake_replay)
    query = urlencode(
        {
            "asset": "BTCUSDT",
            "timeframe": "1h",
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-03T00:00:00Z",
            "replay_days": "2",
            "fee_bps": "2",
            "slippage_bps": "3",
            "spread_bps": "4",
            "execution_latency_minutes": "2",
            "event_limit": "123",
            "cusum_sensitivity": "Slow (Trend)",
        }
    )

    first = chart_server_module._build_research_response(query, optimize=False)
    second = chart_server_module._build_research_response(query, optimize=False)

    assert first is second
    assert len(load_calls) == 2
    assert len(replay_calls) == 1
    assert first["metadata"]["source_generation"] == "source-v1"
    assert first["metadata"]["source_rows"] == 2_880
    assert first["metadata"]["mode"] == "stub_minute_replay"
    assert load_calls[0]["asset"] == "BTCUSDT"
    assert load_calls[0]["timeframe"] == "1h"
    assert load_calls[0]["replay_days"] == 2
    replay = replay_calls[0]
    assert replay["evaluation_start"] == "2026-01-01T00:00:00Z"
    assert replay["replay_clock"] == "2026-01-03T00:00:00Z"
    assert replay["strategy"].cusum_sensitivity == "Slow (Trend)"
    assert replay["costs"].fee_bps == 2.0
    assert replay["costs"].slippage_bps == 3.0
    assert replay["costs"].spread_bps == 4.0
    assert replay["costs"].execution_latency_minutes == 2
    assert replay["event_limit"] == 123

    generation["value"] = "source-v2"
    revised = chart_server_module._build_research_response(query, optimize=False)
    assert revised["metadata"]["source_generation"] == "source-v2"
    assert len(replay_calls) == 2


def test_optimize_orchestration_passes_research_window_and_costs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_server_module._clear_response_cache()
    frame = _frame()
    optimizer_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        chart_server_module,
        "load_canonical_minute_window",
        lambda **_kwargs: (frame, _source_metadata()),
    )

    def fake_optimize(
        received_frame,
        asset,
        timeframe,
        costs,
        *,
        research_start,
        replay_clock,
    ):
        optimizer_calls.append(
            {
                "frame": received_frame,
                "asset": asset,
                "timeframe": timeframe,
                "costs": costs,
                "research_start": research_start,
                "replay_clock": replay_clock,
            }
        )
        return {
            "optimizer_version": "test_optimizer_v1",
            "status": "rejected",
            "reason": "holdout failed",
            "best_config": {"cusum_sensitivity": "Balanced (Swing)"},
            "trials": {"candidate_count": 2},
            "final_replay": {
                "metadata": {"engine": "optimizer_replay"},
                "config": {"strategy": {"horizons": [12, 48, 192]}},
                "metrics": {"total_return_pct": -1.0},
                "equity": [{"time": 1, "value": 0.99}],
                "drawdown": [{"time": 1, "value": -1.0}],
                "position": [{"time": 1, "value": 0.0}],
                "markers": [],
            },
        }

    monkeypatch.setattr(
        chart_server_module,
        "optimize_indicator_strategy",
        fake_optimize,
    )
    monkeypatch.setattr(
        chart_server_module,
        "run_minute_replay",
        lambda *_args, **_kwargs: pytest.fail("backtest engine must not be called"),
    )

    response = chart_server_module._build_research_response(
        "asset=BTCUSDT&timeframe=1h&fee_bps=4&slippage_bps=5",
        optimize=True,
    )

    assert response["status"] == "rejected"
    assert response["metadata"]["source_generation"] == "source-v1"
    assert response["metadata"]["engine"] == "optimizer_replay"
    assert response["metadata"]["optimization"]["status"] == "rejected"
    assert response["metrics"]["total_return_pct"] == -1.0
    assert response["equity"] == [{"time": 1, "value": 0.99}]
    assert response["best_config"]["cusum_sensitivity"] == "Balanced (Swing)"
    assert response["trials"]["candidate_count"] == 2
    assert len(optimizer_calls) == 1
    call = optimizer_calls[0]
    assert call["frame"] is frame
    assert call["asset"] == "BTCUSDT"
    assert call["timeframe"] == "1h"
    assert call["costs"].fee_bps == 4.0
    assert call["costs"].slippage_bps == 5.0
    assert call["research_start"] == "2026-01-01T00:00:00Z"
    assert call["replay_clock"] == datetime(2026, 1, 3, tzinfo=timezone.utc)


def test_optimize_insufficient_evidence_still_matches_replay_payload_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_server_module._clear_response_cache()
    monkeypatch.setattr(
        chart_server_module,
        "load_canonical_minute_window",
        lambda **_kwargs: (_frame(), _source_metadata()),
    )
    monkeypatch.setattr(
        chart_server_module,
        "optimize_indicator_strategy",
        lambda *_args, **_kwargs: {
            "optimizer_version": "test_optimizer_v1",
            "status": "insufficient_evidence",
            "reason": "too short",
            "best_config": None,
            "trials": {"candidate_count": 0},
            "final_replay": None,
        },
    )

    response = chart_server_module._build_research_response(
        "asset=BTCUSDT&timeframe=1h",
        optimize=True,
    )

    assert response["status"] == "insufficient_evidence"
    assert response["metrics"] == {}
    assert response["config"]["strategy"] == {}
    assert response["config"]["costs"]["fee_bps"] == 1.0
    for field in ("equity", "drawdown", "position", "markers"):
        assert response[field] == []


def test_research_endpoint_errors_are_json_http_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}

    class FakeHandler:
        def _send_json(self, payload, status=HTTPStatus.OK):
            sent["payload"] = payload
            sent["status"] = status

    def fail_request(_raw_query: str, *, optimize: bool):
        assert optimize is False
        raise ValueError("bad replay request")

    monkeypatch.setattr(chart_server_module, "_build_research_response", fail_request)

    chart_server_module.ChartRequestHandler._handle_research(
        FakeHandler(),
        "source=raw",
        optimize=False,
    )

    assert sent == {
        "payload": {"error": "bad replay request", "type": "ValueError"},
        "status": HTTPStatus.BAD_REQUEST,
    }


@pytest.mark.parametrize(
    ("path", "optimize"),
    [
        ("/api/backtest?asset=BTCUSDT", False),
        ("/api/optimize?asset=BTCUSDT", True),
    ],
)
def test_get_dispatches_research_routes(path: str, optimize: bool) -> None:
    calls: list[tuple[str, bool]] = []

    class FakeHandler:
        def __init__(self) -> None:
            self.path = path

        def _handle_research(self, raw_query: str, *, optimize: bool) -> None:
            calls.append((raw_query, optimize))

    chart_server_module.ChartRequestHandler.do_GET(FakeHandler())

    assert calls == [("asset=BTCUSDT", optimize)]


def test_forward_paper_status_returns_only_selected_feed_and_stream(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    heartbeat = {
        "status": "running",
        "heartbeat_at": "2026-01-01T12:00:05Z",
        "real_order_routing": False,
        "profitability_guaranteed": False,
        "feeds": {
            "BTCUSDT": {"quality": "live", "provider": "bybit"},
            "ES": {"quality": "delayed", "provider": "yfinance"},
        },
        "streams": {
            "BTCUSDT|1h": {"metrics": {"total_return_pct": 1.25}},
            "ES|1h": {"metrics": {"total_return_pct": -0.5}},
        },
    }
    monkeypatch.setattr(chart_server_module, "default_state_dir", lambda: tmp_path)
    monkeypatch.setattr(
        chart_server_module,
        "status_path",
        lambda _state_dir: tmp_path / "status.json",
    )
    monkeypatch.setattr(
        chart_server_module,
        "read_json_object",
        lambda _path: heartbeat,
    )
    monkeypatch.setattr(
        chart_server_module,
        "inspect_process",
        lambda _state_dir: ProcessStatus(True, 1234, "running", {}),
    )

    payload = chart_server_module._build_forward_paper_status(
        "asset=btcusdt&timeframe=1H"
    )

    assert payload["selection"] == {"asset": "BTCUSDT", "timeframe": "1h"}
    assert payload["process"]["running"] is True
    assert payload["feed"] == {"quality": "live", "provider": "bybit"}
    assert payload["stream"]["metrics"]["total_return_pct"] == 1.25
    assert "feeds" not in payload["service"]
    assert "streams" not in payload["service"]
    assert payload["service"]["real_order_routing"] is False


def test_forward_paper_status_is_explicit_when_service_has_not_started(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(chart_server_module, "default_state_dir", lambda: tmp_path)
    monkeypatch.setattr(chart_server_module, "read_json_object", lambda _path: None)
    monkeypatch.setattr(
        chart_server_module,
        "inspect_process",
        lambda _state_dir: ProcessStatus(False, None, "not_started", None),
    )

    payload = chart_server_module._build_forward_paper_status(
        "asset=BTCUSDT&timeframe=1h"
    )

    assert payload["process"]["running"] is False
    assert payload["service"]["status"] == "not_started"
    assert payload["service"]["profitability_guaranteed"] is False
    assert payload["service"]["real_order_routing"] is False
    assert payload["feed"] is None
    assert payload["stream"] is None


def test_forward_paper_status_rejects_noncanonical_timeframe() -> None:
    with pytest.raises(ValueError, match="Unsupported canonical timeframe"):
        chart_server_module._build_forward_paper_status("asset=BTCUSDT&timeframe=5m")

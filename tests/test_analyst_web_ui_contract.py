from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = PROJECT_ROOT / "Risk_Yield_Meta_Model_Analyst_0_0_1" / "web"
APP_JS = WEB_ROOT / "app.js"
INDEX_HTML = WEB_ROOT / "index.html"
STYLES_CSS = WEB_ROOT / "styles.css"


def _javascript_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*{{", source
    )
    if match is None:
        raise AssertionError(f"JavaScript function {name!r} was not found")

    opening_brace = match.end() - 1
    depth = 0
    for position in range(opening_brace, len(source)):
        token = source[position]
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : position + 1]
    raise AssertionError(f"JavaScript function {name!r} is not balanced")


def test_live_refresh_keeps_panned_viewport_and_follows_right_edge() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    refresh = _javascript_function(source, "refreshLivePayload")
    apply_series = _javascript_function(source, "applySeriesData")

    range_capture = refresh.index("getVisibleLogicalRange()")
    data_update = refresh.index("historyState.candles =")
    stable_update = refresh.index("applySeriesData({")

    assert range_capture < data_update < stable_update
    assert "visibleRange.to >= priorCount - 1 - 0.01" in refresh
    assert "preserveVisibleRange: !wasAtRight" in refresh
    assert "stickToRealTime: wasAtRight" in refresh

    saved_range = apply_series.index("getVisibleLogicalRange()")
    saved_right_offset = apply_series.index("timeScale.scrollPosition()")
    candle_replacement = apply_series.index("candleSeries.setData")
    restored_range = apply_series.index("setVisibleLogicalRange")
    restored_right_offset = apply_series.index(
        "timeScale.scrollToPosition(rightOffset, false)"
    )
    assert saved_range < candle_replacement < restored_range
    assert saved_right_offset < candle_replacement < restored_right_offset
    assert "if (stickToRealTime && Number.isFinite(rightOffset))" in apply_series
    assert "else if (preserveVisibleRange && visibleLogicalRange)" in apply_series
    assert "scrollToRealTime" not in apply_series
    assert "else {\n    setInitialVisibleRange(timeScale);\n  }" in apply_series

    initial_range = _javascript_function(source, "setInitialVisibleRange")
    assert "const INITIAL_VISIBLE_BARS = 240" in source
    assert "candleCount - INITIAL_VISIBLE_BARS" in initial_range
    assert "to: candleCount - 1" in initial_range
    assert "timeScale.fitContent()" in initial_range


def test_indicator_display_contract_is_bounded_legible_and_semantically_clear() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    for color in (
        "#20c997",
        "#ff5b6e",
        "#f8c15c",
        "#ff8b5c",
        "#48a9ff",
        "#a879ff",
        "#e8edf3",
        "#7d8999",
        "#6e86a3",
        "#f8a94f",
        "#d46b91",
    ):
        assert color in html
        assert color in source

    assert 'trendScore: "#e8edf3"' in source
    assert "priceRange: { minValue: -1, maxValue: 1 }" in source
    assert "priceRange: { minValue: 0, maxValue: 1 }" in source
    assert source.count("autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER") == 5
    assert source.count("autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER") == 6

    assert "Analytical events" in html
    assert "bull change" in html
    assert "bear change" in html
    assert "regime risk" in html
    assert 'Buy: "CUSUM bull change"' in source
    assert 'Sell: "CUSUM bear change"' in source
    assert "const MARKER_LABEL_MAX_VISIBLE_EVENTS = 12" in source
    assert "const MARKER_LABEL_MIN_VIEWPORT_WIDTH = 720" in source
    assert "window.innerWidth < MARKER_LABEL_MIN_VIEWPORT_WIDTH" in source
    assert "visibleEventCount > MARKER_LABEL_MAX_VISIBLE_EVENTS" in source
    assert "Analytical events are separate from replay fills" in html

    assert 'id="indicator-guide"' in html
    assert "volatility per bar" in html
    assert "It measures risk magnitude, not direction" in html
    assert "not calibrated probabilities, confidence, or a trading gate" in html
    assert "become actionable no\n                earlier than the next bar" in html
    assert ".indicator-guide" in styles
    assert 'value="cross_timeframe_context"' in html
    assert 'id="mtf-context-matrix"' in html
    assert 'id="mtf-context-rows"' in html
    assert "Closed bars only" in html
    assert "not a trade instruction" in html
    assert "function renderMtfContext" in source
    assert "filtered switch" in source
    assert ".mtf-context-table" in styles
    assert "grid-template-rows: auto auto auto minmax(0, 1fr) auto auto" in styles
    assert "contain: inline-size" in styles
    assert "max-width: 100vw" in styles

    precision = _javascript_function(source, "precisionForPayload")
    min_move = _javascript_function(source, "priceMinMoveForPayload")
    assert "payload.metadata?.price_format?.precision" in precision
    assert "payload.metadata?.price_format?.min_move" in min_move
    assert "activePriceMinMove" in source


def test_mobile_chart_retains_freshness_and_scales_height_with_indicator_panes() -> (
    None
):
    styles = STYLES_CSS.read_text(encoding="utf-8")

    assert '.chart-wrap[data-pane-count="2"]' in styles
    assert '.chart-wrap[data-pane-count="3"]' in styles
    assert '.chart-wrap[data-pane-count="4"]' in styles
    assert '.chart-wrap[data-pane-count="5"]' in styles
    assert "height: max(780px, 105vh)" in styles
    assert "flex-wrap: nowrap" in styles
    assert "overflow-x: auto" in styles
    assert ".market-health .source-badge.live::after" in styles
    assert 'content: "LIVE"' in styles
    assert 'content: "DELAYED"' in styles
    assert 'content: "STALE"' in styles
    assert 'content: "ERROR"' in styles


def test_replay_controls_use_bounded_manual_execution_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")

    assert 'id="replay-days-input"' in html
    assert 'name="replay_days"' in html
    assert 'value="30"' in html
    assert 'id="replay-spread-input"' in html
    assert 'name="spread_bps"' in html
    assert 'id="replay-latency-input"' in html
    assert 'name="execution_latency_minutes"' in html
    assert 'value="1"' in html
    assert 'name="execution_latency_minutes" type="number" min="0" max="60"' in html
    assert html.count("bps / unit turnover") == 3
    assert "Manual snapshot · current canonical history · not the live journal" in html
    assert 'id="replay-refresh-toggle"' not in html

    request = _javascript_function(source, "replayRequestParams")
    assert 'params.set("spread_bps", String(spreadBps))' in request
    assert (
        'params.set("execution_latency_minutes", String(executionLatencyMinutes))'
        in request
    )
    assert 'params.set("event_limit", String(REPLAY_EVENT_LIMIT))' in request
    assert "executionLatencyMinutes > 60" in request
    assert "const REPLAY_EVENT_LIMIT = 2_000" in source
    assert "REPLAY_REFRESH_INTERVAL_MS" not in source
    assert "startReplayRefreshTimer" not in source


def test_research_panels_expose_contract_lifecycle_parity_and_busy_state() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    styles = STYLES_CSS.read_text(encoding="utf-8")

    required_ids = {
        "research-parity-note",
        "paper-risk-badge",
        "paper-contract",
        "paper-order-details",
        "paper-order-summary",
        "paper-order-facts",
        "replay-risk-badge",
        "replay-warning-message",
        "replay-outcome",
        "replay-run-meta",
        "replay-contract",
        "replay-fill-details",
        "replay-fill-summary",
        "replay-fill-rows",
        "replay-optimization-summary",
    }
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    assert required_ids <= html_ids
    assert "not a combined portfolio or a venue OMS" in html
    assert "partial fills are disabled" in html
    assert "partial fills are not modeled" in html

    for token in (
        "renderReplayContract",
        "renderReplayFills",
        "renderPaperContract",
        "renderPaperOrderDetails",
        "renderResearchParityNote",
        'setAttribute("aria-busy"',
        "source_generation",
        "signal_vintage",
        "validation_warning",
        "engine_contract",
        "pending_order",
        "last_order",
        "last_fill",
        "measured_lag_seconds",
        "consecutive_failures",
        "last_poll_duration_seconds",
        "poll_interval_seconds",
        "event_retention",
        "spread_paid",
    ):
        assert token in source
    for selector in (
        ".research-parity-note",
        ".risk-badge",
        ".research-contract",
        ".execution-details",
        ".execution-table",
        ".research-outcome",
        ".replay-results.is-stale",
    ):
        assert selector in styles


def test_optimizer_and_feed_failures_are_semantically_rendered() -> None:
    source = APP_JS.read_text(encoding="utf-8")
    optimizer = _javascript_function(source, "optimizationOutcome")
    paper = _javascript_function(source, "renderForwardPaperStatus")

    assert 'status === "accepted_for_paper_trading"' in optimizer
    assert 'status === "rejected"' in optimizer
    assert 'status === "insufficient_evidence"' in optimizer
    assert "Rejected by research gates" in optimizer
    assert "Insufficient evidence" in optimizer
    assert 'optimize ? "Optimized"' not in source

    assert 'const feedStatus = String(feed?.status ?? "unavailable")' in paper
    assert '"fetch_error"' in paper
    assert "!process.running || feedError" in paper
    assert "feed?.error" in paper


def test_every_javascript_dom_id_exists_once_in_html() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    source = APP_JS.read_text(encoding="utf-8")
    html_ids = re.findall(r'\bid="([^"]+)"', html)
    javascript_ids = re.findall(r'getElementById\("([^"]+)"\)', source)

    assert len(html_ids) == len(set(html_ids))
    assert set(javascript_ids) <= set(html_ids)

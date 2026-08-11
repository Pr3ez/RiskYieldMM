const API_MANIFEST_URL = "/api/manifest";
const API_CHART_URL = "/api/chart";
const API_BACKTEST_URL = "/api/backtest";
const API_OPTIMIZE_URL = "/api/optimize";
const API_PAPER_STATUS_URL = "/api/paper/status";
const FALLBACK_DATA_URL = "./data/current.json";
const HISTORY_LOAD_THRESHOLD_BARS = 80;
const LIVE_REFRESH_INTERVAL_MS = 30_000;
const PAPER_REFRESH_INTERVAL_MS = 60_000;
const MARKER_LABEL_MAX_VISIBLE_BARS = 400;
const MARKER_LABEL_MAX_VISIBLE_EVENTS = 12;
const MARKER_LABEL_MIN_VIEWPORT_WIDTH = 720;
const REPLAY_EVENT_LIMIT = 2_000;
const RECENT_REPLAY_FILL_LIMIT = 5;
const INITIAL_VISIBLE_BARS = 240;

const INDICATOR_COLORS = Object.freeze({
  cusumUpper: "#20c997",
  cusumLower: "#ff5b6e",
  cusumTrail: "#f8c15c",
  fast: "#ff8b5c",
  medium: "#48a9ff",
  slow: "#a879ff",
  trendScore: "#e8edf3",
  trendQuality: "#7d8999",
  regimeBull: "#20c997",
  regimeBear: "#ff5b6e",
  regimeRange: "#6e86a3",
  regimeTransition: "#f8a94f",
  regimeChangeRisk: "#d46b91",
  structureUpper: "#39d0c3",
  structureLower: "#ec7090",
  comparableVolatility: "#64b5f6",
  comparableVolatilityRatio: "#f4b860",
  comparableVolatilityShock: "#c792ea",
  participation: "#56dcb4",
  contextReference: "#8290a3",
  protectedStop: "#ff5b6e",
  protectedTarget: "#20c997",
  metaScore: "#f8c15c",
  forwardMetaScore: "#56dcb4",
});

const TREND_AUTOSCALE_PROVIDER = () => ({
  priceRange: { minValue: -1, maxValue: 1 },
});
const REGIME_AUTOSCALE_PROVIDER = () => ({
  priceRange: { minValue: 0, maxValue: 1 },
});
const META_SCORE_AUTOSCALE_PROVIDER = () => ({
  priceRange: { minValue: 0, maxValue: 1 },
});
const MARKET_CONTEXT_AUTOSCALE_PROVIDER = () => ({
  priceRange: { minValue: 0, maxValue: 1 },
});

let chart = null;
let candleSeries = null;
let volumeSeries = null;
let markerApi = null;
let markerLabelsCondensed = null;
let overlaySeries = {};
let overlayPriceLines = {};
let indicatorPanes = {};
let manifest = null;
let activePricePrecision = 4;
let activePriceMinMove = 0.0001;
let activeChartParams = null;
let loadGeneration = 0;
let suppressVisibleRangeEvents = false;
let overlayWarning = "";
let liveRefreshTimer = null;
let liveRefreshInFlight = false;
let paperRefreshTimer = null;
let paperRequestInFlight = false;
let layerReloadTimer = null;
let chartHasLiveOverlayMetadata = false;
let latestPaperPayload = null;
let replayElapsedTimer = null;

const replayState = {
  payload: null,
  selectionKey: null,
  requestInFlight: false,
  lastMode: null,
  startedAt: null,
  startedWallClock: null,
  completedAt: null,
  durationMs: null,
};

const historyState = {
  candles: [],
  volume: [],
  markers: [],
  overlays: {},
  metadata: {},
  forwardMetaShadow: null,
  canLoadHistory: false,
  isLoadingOlder: false,
  exhaustedLeft: true,
};

const elements = {
  workspace: document.querySelector(".workspace"),
  chart: document.getElementById("chart"),
  chartWrap: document.getElementById("chart-wrap"),
  loading: document.getElementById("loading"),
  reloadButton: document.getElementById("reload-button"),
  liveRefreshToggle: document.getElementById("live-refresh-toggle"),
  liveState: document.getElementById("live-state"),
  sourceQualityBadge: document.getElementById("source-quality-badge"),
  lastUpdateValue: document.getElementById("last-update-value"),
  layersPanel: document.getElementById("layers-panel"),
  layersToggleButton: document.getElementById("layers-toggle-button"),
  timeframeQuickbar: document.getElementById("timeframe-quickbar"),
  visibleLayerCount: document.getElementById("visible-layer-count"),
  allIndicatorsButton: document.getElementById("all-indicators-button"),
  clearIndicatorsButton: document.getElementById("clear-indicators-button"),
  indicatorCards: Array.from(document.querySelectorAll("[data-indicator-card]")),
  indicatorStatusCusum: document.getElementById("indicator-status-cusum"),
  indicatorStatusEwma: document.getElementById("indicator-status-ewma"),
  indicatorStatusTrend: document.getElementById("indicator-status-trend"),
  indicatorStatusRegime: document.getElementById("indicator-status-regime"),
  indicatorStatusMtf: document.getElementById("indicator-status-mtf"),
  indicatorStatusStructure: document.getElementById("indicator-status-structure"),
  indicatorStatusComparableVol: document.getElementById(
    "indicator-status-comparable-vol",
  ),
  indicatorStatusParticipation: document.getElementById(
    "indicator-status-participation",
  ),
  marketContextStrip: document.getElementById("market-context-strip"),
  marketContextDetails: document.getElementById("market-context-details"),
  contextCardStructure: document.getElementById("context-card-structure"),
  contextStateStructure: document.getElementById("context-state-structure"),
  contextMetricsStructure: document.getElementById("context-metrics-structure"),
  contextNoteStructure: document.getElementById("context-note-structure"),
  contextCardVolatility: document.getElementById("context-card-volatility"),
  contextStateVolatility: document.getElementById("context-state-volatility"),
  contextMetricsVolatility: document.getElementById("context-metrics-volatility"),
  contextNoteVolatility: document.getElementById("context-note-volatility"),
  contextCardParticipation: document.getElementById("context-card-participation"),
  contextStateParticipation: document.getElementById("context-state-participation"),
  contextMetricsParticipation: document.getElementById(
    "context-metrics-participation",
  ),
  contextNoteParticipation: document.getElementById("context-note-participation"),
  mtfContextMatrix: document.getElementById("mtf-context-matrix"),
  mtfContextDetails: document.getElementById("mtf-context-details"),
  mtfContextBadge: document.getElementById("mtf-context-badge"),
  mtfContextRows: document.getElementById("mtf-context-rows"),
  mtfContextReason: document.getElementById("mtf-context-reason"),
  decisionModeBadge: document.getElementById("decision-mode-badge"),
  decisionCardFeed: document.getElementById("decision-card-feed"),
  decisionFeedState: document.getElementById("decision-feed-state"),
  decisionFeedDetail: document.getElementById("decision-feed-detail"),
  decisionCardReadiness: document.getElementById("decision-card-readiness"),
  decisionReadinessState: document.getElementById("decision-readiness-state"),
  decisionReadinessDetail: document.getElementById("decision-readiness-detail"),
  decisionCardAgreement: document.getElementById("decision-card-agreement"),
  decisionAgreementState: document.getElementById("decision-agreement-state"),
  decisionAgreementDetail: document.getElementById("decision-agreement-detail"),
  decisionCardContext: document.getElementById("decision-card-context"),
  decisionContextState: document.getElementById("decision-context-state"),
  decisionContextDetail: document.getElementById("decision-context-detail"),
  decisionCardExecution: document.getElementById("decision-card-execution"),
  decisionExecutionState: document.getElementById("decision-execution-state"),
  decisionExecutionDetail: document.getElementById("decision-execution-detail"),
  decisionCardReplay: document.getElementById("decision-card-replay"),
  decisionReplayState: document.getElementById("decision-replay-state"),
  decisionReplayDetail: document.getElementById("decision-replay-detail"),
  decisionCardPaper: document.getElementById("decision-card-paper"),
  decisionPaperState: document.getElementById("decision-paper-state"),
  decisionPaperDetail: document.getElementById("decision-paper-detail"),
  researchDrawer: document.getElementById("research-drawer"),
  researchToggleButton: document.getElementById("research-toggle-button"),
  researchTabs: Array.from(document.querySelectorAll("[data-research-tab]")),
  researchPanels: Array.from(document.querySelectorAll("[data-research-panel]")),
  loadOlderButton: document.getElementById("load-older-button"),
  autoHistoryToggle: document.getElementById("auto-history-toggle"),
  chartForm: document.getElementById("chart-form"),
  assetSelect: document.getElementById("asset-select"),
  sourceSelect: document.getElementById("source-select"),
  timeframeSelect: document.getElementById("timeframe-select"),
  indicatorInputs: Array.from(document.querySelectorAll("input[name='indicators']")),
  cusumSensitivityField: document.getElementById("cusum-sensitivity-field"),
  cusumSensitivitySelect: document.getElementById("cusum-sensitivity-select"),
  startInput: document.getElementById("start-input"),
  endInput: document.getElementById("end-input"),
  maxBarsInput: document.getElementById("max-bars-input"),
  subtitle: document.getElementById("subtitle"),
  status: document.getElementById("status"),
  crosshair: document.getElementById("crosshair"),
  asset: document.getElementById("meta-asset"),
  timeframe: document.getElementById("meta-timeframe"),
  source: document.getElementById("meta-source"),
  bars: document.getElementById("meta-bars"),
  range: document.getElementById("meta-range"),
  diagnosticVintage: document.getElementById("diagnostic-vintage"),
  diagnosticVintageLabel: document.getElementById("diagnostic-vintage-label"),
  diagnosticVintageMessage: document.getElementById("diagnostic-vintage-message"),
  replayPanel: document.getElementById("replay-panel"),
  replaySourceBadge: document.getElementById("replay-source-badge"),
  replayRiskBadge: document.getElementById("replay-risk-badge"),
  replayWarningMessage: document.getElementById("replay-warning-message"),
  replayControls: document.getElementById("replay-controls"),
  replayDaysInput: document.getElementById("replay-days-input"),
  replayFeeInput: document.getElementById("replay-fee-input"),
  replaySlippageInput: document.getElementById("replay-slippage-input"),
  replaySpreadInput: document.getElementById("replay-spread-input"),
  replayLatencyInput: document.getElementById("replay-latency-input"),
  replayProtectedBracketInput: document.getElementById(
    "replay-protected-bracket-input",
  ),
  replayRiskUnitVolatilityInput: document.getElementById(
    "replay-risk-unit-volatility-input",
  ),
  replayStopRiskUnitsInput: document.getElementById(
    "replay-stop-risk-units-input",
  ),
  replayTargetRiskUnitsInput: document.getElementById(
    "replay-target-risk-units-input",
  ),
  replayTimeoutTargetBarsInput: document.getElementById(
    "replay-timeout-target-bars-input",
  ),
  replayBreakEvenSafetyMarginInput: document.getElementById(
    "replay-break-even-safety-margin-input",
  ),
  replayMetaFilterModeSelect: document.getElementById(
    "replay-meta-filter-mode-select",
  ),
  replayPolicyState: document.getElementById("replay-policy-state"),
  replayMetaState: document.getElementById("replay-meta-state"),
  runReplayButton: document.getElementById("run-replay-button"),
  optimizeReplayButton: document.getElementById("optimize-replay-button"),
  replayState: document.getElementById("replay-state"),
  replayResults: document.getElementById("replay-results"),
  replayOutcome: document.getElementById("replay-outcome"),
  replayOutcomeLabel: document.getElementById("replay-outcome-label"),
  replayOutcomeReason: document.getElementById("replay-outcome-reason"),
  replayRunMeta: document.getElementById("replay-run-meta"),
  replayContract: document.getElementById("replay-contract"),
  replayMetrics: document.getElementById("replay-metrics"),
  replayFillDetails: document.getElementById("replay-fill-details"),
  replayFillSummary: document.getElementById("replay-fill-summary"),
  replayFillRows: document.getElementById("replay-fill-rows"),
  replayOptimization: document.getElementById("replay-optimization"),
  replayOptimizationSummary: document.getElementById(
    "replay-optimization-summary",
  ),
  replayOptimizationDetails: document.getElementById(
    "replay-optimization-details",
  ),
  researchParityNote: document.getElementById("research-parity-note"),
  paperSection: document.getElementById("paper-section"),
  paperFeedBadge: document.getElementById("paper-feed-badge"),
  paperRiskBadge: document.getElementById("paper-risk-badge"),
  paperSummary: document.getElementById("paper-summary"),
  paperRefreshButton: document.getElementById("paper-refresh-button"),
  paperFacts: document.getElementById("paper-facts"),
  paperContract: document.getElementById("paper-contract"),
  paperOrderDetails: document.getElementById("paper-order-details"),
  paperOrderSummary: document.getElementById("paper-order-summary"),
  paperOrderFacts: document.getElementById("paper-order-facts"),
  paperMetrics: document.getElementById("paper-metrics"),
  paperState: document.getElementById("paper-state"),
  replayPaneLegend: document.getElementById("replay-pane-legend"),
  replayProtectionLegend: document.getElementById("replay-protection-legend"),
  replayMetaLegend: document.getElementById("replay-meta-legend"),
  forwardMetaShadowLegend: document.getElementById(
    "forward-meta-shadow-legend",
  ),
  forwardMetaShadowState: document.getElementById(
    "forward-meta-shadow-state",
  ),
  replayMarkerLegend: document.getElementById("replay-marker-legend"),
  legendGroups: Array.from(document.querySelectorAll("#chart-legend [data-overlay]")),
  markerLegend: document.getElementById("marker-legend"),
  legendTrendFast: document.getElementById("legend-trend-fast"),
  legendTrendMedium: document.getElementById("legend-trend-medium"),
  legendTrendSlow: document.getElementById("legend-trend-slow"),
};

function setLoading(isLoading) {
  elements.loading.classList.toggle("visible", isLoading);
}

function setStatus(message, level = "info") {
  elements.status.textContent = message;
  elements.status.className = `status ${level === "info" ? "" : level}`;
}

function setLiveState(message, level = "info") {
  elements.liveState.textContent = message;
  elements.liveState.className = `live-state ${level === "info" ? "" : level}`;
}

function setSourceQualityBadge(message, level = "checking") {
  if (!elements.sourceQualityBadge) {
    return;
  }
  elements.sourceQualityBadge.textContent = message;
  elements.sourceQualityBadge.className = `source-badge ${level}`;
}

function normalizedProviderLabel(provider) {
  const value = String(provider ?? "").trim();
  if (!value) {
    return "Source";
  }
  if (value.toLowerCase().includes("bybit")) {
    return "Bybit";
  }
  if (
    value.toLowerCase().includes("yahoo") ||
    value.toLowerCase().includes("yfinance")
  ) {
    return "Yahoo";
  }
  return value;
}

function isKnownFreeProvider(provider) {
  const value = String(provider ?? "").toLowerCase();
  return (
    value.includes("bybit") ||
    value.includes("yahoo") ||
    value.includes("yfinance")
  );
}

function presentSourceQuality({ provider, quality, status, expectedDelaySeconds } = {}) {
  const normalizedQuality = String(quality ?? "").toLowerCase();
  const normalizedStatus = String(status ?? "").toLowerCase();
  const providerLabel = normalizedProviderLabel(provider);
  const prefix = isKnownFreeProvider(provider) ? "Free · " : "";
  if (["error", "failed", "unavailable", "stopped"].includes(normalizedStatus)) {
    setSourceQualityBadge(`${providerLabel} · unavailable`, "error");
    return;
  }
  if (["stale", "catching_up"].includes(normalizedStatus)) {
    setSourceQualityBadge(`${prefix}${providerLabel} · ${normalizedStatus.replace("_", " ")}`, "warn");
    return;
  }
  if (normalizedQuality === "live") {
    setSourceQualityBadge(`${prefix}${providerLabel} · live`, "live");
    return;
  }
  if (normalizedQuality === "delayed") {
    const delay = Number(expectedDelaySeconds);
    const delayText = Number.isFinite(delay) && delay > 0
      ? ` · ~${Math.round(delay / 60)}m delay`
      : "";
    setSourceQualityBadge(`${prefix}${providerLabel} · delayed${delayText}`, "delayed");
    return;
  }
  setSourceQualityBadge(`${providerLabel} · checking`, "checking");
}

function formatCompactTimestamp(value) {
  if (value === undefined || value === null || value === "") {
    return "—";
  }
  const numeric = Number(value);
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(value));
  if (!Number.isFinite(date.getTime())) {
    return String(value);
  }
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC");
}

function setReplayStatus(message, level = "info") {
  elements.replayState.textContent = message;
  elements.replayState.className =
    `replay-state ${level === "info" ? "" : level}`;
}

function setPaperStatus(message, level = "info") {
  elements.paperState.textContent = message;
  elements.paperState.className =
    `replay-state ${level === "info" ? "" : level}`;
}

function formatTime(unixSeconds) {
  return new Date(unixSeconds * 1000).toISOString().replace(".000Z", "Z");
}

function timeframeSeconds(value) {
  const match = String(value ?? "").trim().toLowerCase().match(/^(\d+)([mhd])$/);
  if (!match) {
    return null;
  }
  const amount = Number.parseInt(match[1], 10);
  const multiplier = match[2] === "m" ? 60 : match[2] === "h" ? 3600 : 86400;
  return amount * multiplier;
}

function formatPrice(value, precision = activePricePrecision) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "-";
  }
  return Number(value).toFixed(precision);
}

function formatPercent(value, precision = 3) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "-";
  }
  return `${Number(value).toFixed(precision)}%`;
}

function seriesValueAtCrosshair(param, series) {
  if (!series || !param?.seriesData) {
    return null;
  }
  const point = param.seriesData.get(series);
  const value = point?.value;
  return value !== undefined && value !== null && Number.isFinite(Number(value))
    ? Number(value)
    : null;
}

function prototypeRegimeAtCrosshair(param) {
  const candidates = [
    ["Bull trend", seriesValueAtCrosshair(param, overlaySeries.regime_bull)],
    ["Bear trend", seriesValueAtCrosshair(param, overlaySeries.regime_bear)],
    ["Range / chop", seriesValueAtCrosshair(param, overlaySeries.regime_range)],
    [
      "Transition risk",
      seriesValueAtCrosshair(param, overlaySeries.regime_transition),
    ],
  ].filter(([, value]) => value !== null);
  if (candidates.length === 0) {
    return null;
  }
  return candidates.reduce((leader, candidate) =>
    candidate[1] > leader[1] ? candidate : leader,
  );
}

function decimalPlaces(value) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return 0;
  }
  const text = String(value).toLowerCase();
  if (text.includes("e-")) {
    const [, exponent] = text.split("e-");
    return Number.parseInt(exponent, 10);
  }
  const decimal = text.split(".")[1];
  return decimal ? decimal.replace(/0+$/, "").length : 0;
}

function minimumPrecisionForAsset(asset) {
  if (asset === "EURUSD" || asset === "USDJPY") {
    return 5;
  }
  return 4;
}

function precisionForPayload(payload) {
  const configured = Number(payload.metadata?.price_format?.precision);
  if (Number.isInteger(configured) && configured >= 0 && configured <= 8) {
    return configured;
  }
  const candles = payload.candles ?? [];
  const asset = payload.metadata?.asset;
  let precision = minimumPrecisionForAsset(asset);
  for (const candle of candles) {
    precision = Math.max(
      precision,
      decimalPlaces(candle.open),
      decimalPlaces(candle.high),
      decimalPlaces(candle.low),
      decimalPlaces(candle.close),
    );
    if (precision >= 8) {
      return 8;
    }
  }
  return Math.min(Math.max(precision, 0), 8);
}

function priceMinMoveForPayload(payload, precision) {
  const configured = Number(payload.metadata?.price_format?.min_move);
  return Number.isFinite(configured) && configured > 0
    ? configured
    : minMoveForPrecision(precision);
}

function minMoveForPrecision(precision) {
  return 10 ** -precision;
}

function resetHistoryState() {
  historyState.candles = [];
  historyState.volume = [];
  historyState.markers = [];
  historyState.overlays = {};
  historyState.metadata = {};
  historyState.forwardMetaShadow = null;
  historyState.canLoadHistory = false;
  historyState.isLoadingOlder = false;
  historyState.exhaustedLeft = true;
  overlayWarning = "";
  elements.chartWrap.dataset.paneCount = "0";
  elements.diagnosticVintage.hidden = true;
  elements.diagnosticVintage.removeAttribute("title");
  elements.mtfContextMatrix.hidden = true;
  elements.mtfContextRows.replaceChildren();
  elements.marketContextStrip.hidden = true;
  elements.contextCardStructure.hidden = true;
  elements.contextCardVolatility.hidden = true;
  elements.contextCardParticipation.hidden = true;
  elements.contextMetricsStructure.replaceChildren();
  elements.contextMetricsVolatility.replaceChildren();
  elements.contextMetricsParticipation.replaceChildren();
  updateHistoryControls();
}

function updateHistoryControls() {
  const disabled =
    !historyState.canLoadHistory ||
    historyState.isLoadingOlder ||
    historyState.exhaustedLeft ||
    historyState.candles.length === 0;
  elements.loadOlderButton.disabled = disabled;
  elements.autoHistoryToggle.disabled = !historyState.canLoadHistory;
}

function firstCandleTime() {
  return historyState.candles.length ? historyState.candles[0].time : null;
}

function lastCandleTime() {
  return historyState.candles.length
    ? historyState.candles[historyState.candles.length - 1].time
    : null;
}

function mergeByTime(existing, incoming) {
  const byTime = new Map();
  for (const item of existing) {
    byTime.set(item.time, item);
  }
  for (const item of incoming) {
    byTime.set(item.time, item);
  }
  return Array.from(byTime.values()).sort((left, right) => left.time - right.time);
}

function mergeMarkers(existing, incoming) {
  const byKey = new Map();
  for (const marker of existing) {
    byKey.set(`${marker.time}:${marker.position}:${marker.text}`, marker);
  }
  for (const marker of incoming) {
    byKey.set(`${marker.time}:${marker.position}:${marker.text}`, marker);
  }
  return Array.from(byKey.values()).sort((left, right) => left.time - right.time);
}

function mergeForwardMetaItems(existing, incoming, keyForItem, compareItems) {
  const byKey = new Map();
  for (const item of Array.isArray(existing) ? existing : []) {
    byKey.set(keyForItem(item), item);
  }
  for (const item of Array.isArray(incoming) ? incoming : []) {
    byKey.set(keyForItem(item), item);
  }
  return Array.from(byKey.values()).sort(compareItems);
}

function forwardMetaPayloadIdentity(payload) {
  return [
    payload?.run_id,
    payload?.stream_id,
    payload?.asset,
    payload?.timeframe,
  ];
}

function mergeForwardMetaShadow(existing, incoming) {
  if (!incoming || typeof incoming !== "object") {
    return existing ?? null;
  }
  if (!existing || typeof existing !== "object") {
    return incoming;
  }
  const existingIdentity = forwardMetaPayloadIdentity(existing);
  const incomingIdentity = forwardMetaPayloadIdentity(incoming);
  const identityChanged = existingIdentity.some(
    (value, index) =>
      value && incomingIdentity[index] && value !== incomingIdentity[index],
  );
  if (identityChanged) {
    return incoming;
  }

  const scores = mergeForwardMetaItems(
    existing.scores,
    incoming.scores,
    (item) =>
      item?.shadow_event_id ??
      `${item?.time}:${item?.side}:${item?.model_digest}:${item?.policy_digest}`,
    (left, right) => Number(left?.time) - Number(right?.time),
  );
  const outcomeMarkers = mergeForwardMetaItems(
    existing.outcome_markers,
    incoming.outcome_markers,
    (item) =>
      item?.shadow_event_id ??
      `${item?.time}:${item?.outcome}:${item?.side}:${item?.model_digest}`,
    (left, right) => Number(left?.time) - Number(right?.time),
  );
  const audit = mergeForwardMetaItems(
    existing.audit,
    incoming.audit,
    (item) =>
      item?.sequence_no ??
      `${item?.event_id}:${item?.event_type}:${item?.occurred_at}`,
    (left, right) => Number(left?.sequence_no) - Number(right?.sequence_no),
  );
  const predictions = audit.filter(
    (item) => item?.event_type === "meta_shadow_prediction",
  );
  const labels = audit.filter((item) => item?.event_type === "meta_shadow_label");
  const counts = {
    events: audit.length,
    predictions: predictions.length,
    available_scores: predictions.filter(
      (item) => item?.available === true && Number.isFinite(Number(item?.probability)),
    ).length,
    unavailable_predictions: predictions.filter(
      (item) => item?.available !== true,
    ).length,
    accepted: predictions.filter((item) => item?.accepted === true).length,
    rejected: predictions.filter((item) => item?.accepted === false).length,
    labels: labels.length,
  };
  const hasEvents = audit.length > 0;
  const hasScores = scores.length > 0;
  return {
    ...existing,
    ...incoming,
    available: hasEvents,
    status: hasScores
      ? "ok"
      : hasEvents
        ? "events_without_available_scores"
        : incoming.status,
    reason: hasScores
      ? null
      : hasEvents
        ? "no_available_predictions"
        : incoming.reason,
    scores,
    outcome_markers: outcomeMarkers,
    audit,
    counts,
    rows_truncated: Boolean(
      existing.rows_truncated || incoming.rows_truncated,
    ),
  };
}

function normalizedReplayTime(rawTime) {
  const numeric = Number(rawTime);
  if (Number.isFinite(numeric)) {
    return numeric;
  }
  const parsed = Date.parse(String(rawTime ?? ""));
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : null;
}

function normalizedReplaySeries(points) {
  if (!Array.isArray(points)) {
    return [];
  }
  return points
    .map((point) => ({
      ...point,
      time: normalizedReplayTime(point?.time),
      value: Number(point?.value),
    }))
    .filter(
      (point) => Number.isFinite(point.time) && Number.isFinite(point.value),
    )
    .sort((left, right) => left.time - right.time);
}

function normalizedReplayPriceSeries(points) {
  if (!Array.isArray(points)) {
    return [];
  }
  return points
    .map((point) => {
      const time = normalizedReplayTime(point?.time ?? point?.timestamp);
      const rawValue = point?.value ?? point?.price;
      if (rawValue === null || rawValue === undefined) {
        return { time };
      }
      const value = Number(rawValue);
      return Number.isFinite(value) ? { time, value } : { time };
    })
    .filter((point) => Number.isFinite(point.time))
    .sort((left, right) => left.time - right.time);
}

function outcomeMarkerDisplayTime(marker) {
  const explicitKnownTime =
    marker?.known_at ?? marker?.label_known_at ?? marker?.resolved_at;
  const isFutureOutcomeEvidence = marker?.outcome !== undefined;
  if (
    isFutureOutcomeEvidence &&
    explicitKnownTime === undefined &&
    marker?.time_semantics !== "known_at"
  ) {
    return null;
  }
  return normalizedReplayTime(
    explicitKnownTime ?? marker?.time ?? marker?.timestamp,
  );
}

function normalizedReplayMarkers(markers) {
  if (!Array.isArray(markers)) {
    return [];
  }
  return markers
    .map((marker) => {
      const time = outcomeMarkerDisplayTime(marker);
      const descriptor = String(
        marker?.side ?? marker?.action ?? marker?.text ?? "fill",
      ).toLowerCase();
      const isBuy =
        descriptor.includes("buy") ||
        descriptor.includes("long") ||
        descriptor.includes("entry");
      return {
        ...marker,
        time,
        position: marker?.position ?? (isBuy ? "belowBar" : "aboveBar"),
        color: marker?.color ?? (isBuy ? "#2a9d8f" : "#d1495b"),
        shape: marker?.shape ?? (isBuy ? "arrowUp" : "arrowDown"),
        text: String(marker?.text ?? marker?.label ?? (isBuy ? "Buy fill" : "Sell fill")),
      };
    })
    .filter((marker) => Number.isFinite(marker.time))
    .sort((left, right) => left.time - right.time);
}

function replaySeriesForLoadedChart(points) {
  const normalized = normalizedReplaySeries(points);
  const first = firstCandleTime();
  const last = lastCandleTime();
  const interval = timeframeSeconds(historyState.metadata.timeframe) ?? 60;
  if (!first || !last) {
    return [];
  }
  return normalized.filter(
    (point) => point.time >= first && point.time < last + interval,
  );
}

function replayRequiredProbabilityForLoadedChart(payload) {
  if (!Array.isArray(payload?.meta_score_events)) {
    return [];
  }
  return replaySeriesForLoadedChart(
    payload.meta_score_events
      .map((event) => ({
        time: event?.time ?? event?.decision_at,
        value: event?.required_probability,
      }))
      .filter((point) => {
        if (point.value === null || point.value === undefined) {
          return false;
        }
        const value = Number(point.value);
        return Number.isFinite(value) && value >= 0 && value <= 1;
      }),
  );
}

function replayPriceSeriesForLoadedChart(points) {
  const normalized = normalizedReplayPriceSeries(points);
  const first = firstCandleTime();
  const last = lastCandleTime();
  const interval = timeframeSeconds(historyState.metadata.timeframe) ?? 60;
  if (!first || !last) {
    return [];
  }
  return normalized.filter(
    (point) => point.time >= first && point.time < last + interval,
  );
}

function replayMarkersForLoadedChart(markers) {
  const normalized = normalizedReplayMarkers(markers);
  const candles = historyState.candles;
  const first = firstCandleTime();
  const last = lastCandleTime();
  const interval = timeframeSeconds(historyState.metadata.timeframe) ?? 60;
  if (!first || !last || candles.length === 0) {
    return [];
  }
  return normalized
    .filter((marker) => marker.time >= first && marker.time < last + interval)
    .map((marker) => {
      let low = 0;
      let high = candles.length;
      while (low < high) {
        const middle = Math.floor((low + high) / 2);
        if (candles[middle].time <= marker.time) {
          low = middle + 1;
        } else {
          high = middle;
        }
      }
      const candleTime = candles[Math.max(0, low - 1)].time;
      return { ...marker, time: candleTime };
    });
}

function newestOverlayLast(existingLast, incomingLast) {
  if (!incomingLast) {
    return existingLast;
  }
  if (!existingLast) {
    return incomingLast;
  }
  const existingAsOf = normalizedReplayTime(existingLast.as_of);
  const incomingAsOf = normalizedReplayTime(incomingLast.as_of);
  if (!Number.isFinite(incomingAsOf)) {
    return existingLast;
  }
  if (!Number.isFinite(existingAsOf) || incomingAsOf > existingAsOf) {
    return incomingLast;
  }
  return existingLast;
}

function mergeSeriesOverlay(existing = {}, incoming = {}, seriesFields = []) {
  const merged = { ...existing, ...incoming };
  for (const field of seriesFields) {
    merged[field] = mergeByTime(existing[field] ?? [], incoming[field] ?? []);
  }
  const last = newestOverlayLast(existing.last, incoming.last);
  if (last) {
    merged.last = last;
  }
  return merged;
}

function mergeCusumOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, [
    "upper_band",
    "lower_band",
    "trail_stop",
  ]);
}

function mergeEwmaVolatilityOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, ["fast", "medium", "slow"]);
}

function mergeVolatilityScaledTrendOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, [
    "fast",
    "medium",
    "slow",
    "score",
    "path_quality",
  ]);
}

function mergeOnlineRegimeOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, [
    "state_band",
    "bull",
    "bear",
    "range",
    "transition",
    "entropy",
    "filtered_switch_probability",
    "change_risk",
  ]);
}

function priorStructureChannels(overlay = {}) {
  const channels = overlay.channels ?? overlay.lookbacks ?? {};
  if (Array.isArray(channels)) {
    return Object.fromEntries(
      channels
        .filter((channel) => channel && typeof channel === "object")
        .map((channel) => [
          String(channel.lookback_bars ?? channel.lookback ?? channel.window ?? "default"),
          channel,
        ]),
    );
  }
  return channels && typeof channels === "object" ? channels : {};
}

function mergePriorStructureOverlay(existing = {}, incoming = {}) {
  const merged = mergeSeriesOverlay(existing, incoming, [
    "upper",
    "lower",
    "upper_channel",
    "lower_channel",
    "position_score",
    "channel_position",
    "up_room_sigma",
    "down_room_sigma",
  ]);
  const existingChannels = priorStructureChannels(existing);
  const incomingChannels = priorStructureChannels(incoming);
  const lookbacks = new Set([
    ...Object.keys(existingChannels),
    ...Object.keys(incomingChannels),
  ]);
  merged.channels = Object.fromEntries(
    Array.from(lookbacks).map((lookback) => [
      lookback,
      mergeSeriesOverlay(
        existingChannels[lookback],
        incomingChannels[lookback],
        ["upper", "lower", "upper_channel", "lower_channel", "position"],
      ),
    ]),
  );
  return merged;
}

function mergeComparableVolatilityOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, [
    "volatility_percentile",
    "rs_percentile",
    "percentile",
    "fast_slow_ratio_score",
    "regime_score",
    "range_shock_score",
    "shock_score",
    "fast_slow_ratio",
    "range_shock",
    "range_shock_ratio",
    "rs_fast",
    "rs_slow",
    "rs_to_close_vol_ratio",
  ]);
}

function mergeParticipationOverlay(existing = {}, incoming = {}) {
  return mergeSeriesOverlay(existing, incoming, [
    "participation_score",
    "rvol_score",
    "rvol_percentile",
    "percentile",
    "rvol",
    "log_rvol",
    "reference_count",
  ]);
}

function mergeMtfContextOverlay(existing = {}, incoming = {}) {
  const merged = mergeSeriesOverlay(existing, incoming, [
    "context_score",
    "agreement",
    "maximum_change_risk",
  ]);
  const existingSources = new Map(
    (existing.sources ?? []).map((source) => [source.timeframe, source]),
  );
  const incomingSources = new Map(
    (incoming.sources ?? []).map((source) => [source.timeframe, source]),
  );
  const timeframes = Array.from(
    new Set([...existingSources.keys(), ...incomingSources.keys()]),
  );
  merged.sources = timeframes.map((timeframe) => {
    const older = existingSources.get(timeframe) ?? {};
    const newer = incomingSources.get(timeframe) ?? {};
    const olderAsOf = normalizedReplayTime(older.latest?.available_at);
    const newerAsOf = normalizedReplayTime(newer.latest?.available_at);
    const latest =
      Number.isFinite(newerAsOf) &&
      (!Number.isFinite(olderAsOf) || newerAsOf >= olderAsOf)
        ? newer.latest
        : older.latest;
    return {
      ...older,
      ...newer,
      latest,
      trend_score: mergeByTime(older.trend_score ?? [], newer.trend_score ?? []),
    };
  });
  return merged;
}

function mergeOverlays(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming };
  if (existing.cusum_trend || incoming.cusum_trend) {
    merged.cusum_trend = mergeCusumOverlay(existing.cusum_trend, incoming.cusum_trend);
  }
  if (existing.ewma_volatility || incoming.ewma_volatility) {
    merged.ewma_volatility = mergeEwmaVolatilityOverlay(
      existing.ewma_volatility,
      incoming.ewma_volatility,
    );
  }
  if (existing.volatility_scaled_trend || incoming.volatility_scaled_trend) {
    merged.volatility_scaled_trend = mergeVolatilityScaledTrendOverlay(
      existing.volatility_scaled_trend,
      incoming.volatility_scaled_trend,
    );
  }
  if (existing.online_regime || incoming.online_regime) {
    merged.online_regime = mergeOnlineRegimeOverlay(
      existing.online_regime,
      incoming.online_regime,
    );
  }
  if (existing.cross_timeframe_context || incoming.cross_timeframe_context) {
    merged.cross_timeframe_context = mergeMtfContextOverlay(
      existing.cross_timeframe_context,
      incoming.cross_timeframe_context,
    );
  }
  if (existing.prior_structure || incoming.prior_structure) {
    merged.prior_structure = mergePriorStructureOverlay(
      existing.prior_structure,
      incoming.prior_structure,
    );
  }
  if (existing.comparable_volatility || incoming.comparable_volatility) {
    merged.comparable_volatility = mergeComparableVolatilityOverlay(
      existing.comparable_volatility,
      incoming.comparable_volatility,
    );
  }
  if (
    existing.phase_adjusted_participation ||
    incoming.phase_adjusted_participation
  ) {
    merged.phase_adjusted_participation = mergeParticipationOverlay(
      existing.phase_adjusted_participation,
      incoming.phase_adjusted_participation,
    );
  }
  return merged;
}

function trimOverlaySeriesFrom(overlays, startTime) {
  const fieldsByOverlay = {
    cusum_trend: ["upper_band", "lower_band", "trail_stop"],
    ewma_volatility: ["fast", "medium", "slow"],
    volatility_scaled_trend: ["fast", "medium", "slow", "score", "path_quality"],
    online_regime: [
      "state_band",
      "bull",
      "bear",
      "range",
      "transition",
      "entropy",
      "filtered_switch_probability",
      "change_risk",
    ],
    cross_timeframe_context: [
      "context_score",
      "agreement",
      "maximum_change_risk",
    ],
    prior_structure: [
      "upper",
      "lower",
      "upper_channel",
      "lower_channel",
      "position_score",
      "channel_position",
      "up_room_sigma",
      "down_room_sigma",
    ],
    comparable_volatility: [
      "volatility_percentile",
      "rs_percentile",
      "percentile",
      "fast_slow_ratio_score",
      "regime_score",
      "range_shock_score",
      "shock_score",
      "fast_slow_ratio",
      "range_shock",
      "range_shock_ratio",
      "rs_fast",
      "rs_slow",
      "rs_to_close_vol_ratio",
    ],
    phase_adjusted_participation: [
      "participation_score",
      "rvol_score",
      "rvol_percentile",
      "percentile",
      "rvol",
      "log_rvol",
      "reference_count",
    ],
  };
  const trimmed = {};
  for (const [key, overlay] of Object.entries(overlays ?? {})) {
    const next = { ...overlay };
    for (const field of fieldsByOverlay[key] ?? []) {
      next[field] = (overlay[field] ?? []).filter((point) => point.time < startTime);
    }
    if (key === "cross_timeframe_context") {
      next.sources = (overlay.sources ?? []).map((source) => ({
        ...source,
        trend_score: (source.trend_score ?? []).filter(
          (point) => point.time < startTime,
        ),
      }));
    }
    if (key === "prior_structure") {
      next.channels = Object.fromEntries(
        Object.entries(priorStructureChannels(overlay)).map(
          ([lookback, channel]) => [
            lookback,
            {
              ...channel,
              upper: (channel.upper ?? []).filter((point) => point.time < startTime),
              lower: (channel.lower ?? []).filter((point) => point.time < startTime),
              upper_channel: (channel.upper_channel ?? []).filter(
                (point) => point.time < startTime,
              ),
              lower_channel: (channel.lower_channel ?? []).filter(
                (point) => point.time < startTime,
              ),
              position: (channel.position ?? []).filter(
                (point) => point.time < startTime,
              ),
            },
          ],
        ),
      );
    }
    if (normalizedReplayTime(next.last?.as_of) >= startTime) {
      delete next.last;
    }
    trimmed[key] = next;
  }
  return trimmed;
}

function olderRequestParams() {
  if (!activeChartParams) {
    return null;
  }
  const earliest = firstCandleTime();
  if (!earliest) {
    return null;
  }
  const params = new URLSearchParams(activeChartParams.toString());
  params.set("end", formatTime(earliest - 1));
  return params;
}

function destroyChart() {
  if (chart) {
    chart.remove();
  }
  chart = null;
  candleSeries = null;
  volumeSeries = null;
  markerApi = null;
  markerLabelsCondensed = null;
  overlaySeries = {};
  overlayPriceLines = {};
  indicatorPanes = {};
  elements.chart.replaceChildren();
  resetHistoryState();
}

function initChart() {
  const { createChart, CandlestickSeries, HistogramSeries, CrosshairMode } =
    LightweightCharts;

  chart = createChart(elements.chart, {
    autoSize: true,
    layout: {
      background: { type: "solid", color: "#0b111a" },
      textColor: "#8e9bab",
      attributionLogo: true,
    },
    grid: {
      vertLines: { color: "#17212e" },
      horzLines: { color: "#17212e" },
    },
    crosshair: {
      mode: CrosshairMode.Normal,
    },
    rightPriceScale: {
      borderColor: "#243142",
      scaleMargins: { top: 0.08, bottom: 0.24 },
    },
    timeScale: {
      borderColor: "#243142",
      timeVisible: true,
      secondsVisible: false,
      rightOffsetPixels: 12,
      fixLeftEdge: false,
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    },
  });

  candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: "#26a69a",
    downColor: "#ef5350",
    borderVisible: false,
    wickUpColor: "#26a69a",
    wickDownColor: "#ef5350",
    priceLineVisible: true,
  });

  volumeSeries = chart.addSeries(HistogramSeries, {
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
    color: "#b8b5ad",
  });
  chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.78, bottom: 0 },
  });

  chart.subscribeCrosshairMove((param) => {
    if (!param || !param.time || !param.seriesData) {
      elements.crosshair.textContent = "Crosshair: -";
      return;
    }
    const bar = param.seriesData.get(candleSeries);
    const details = [formatTime(param.time)];
    if (bar) {
      details.push(
        `O ${formatPrice(bar.open)} H ${formatPrice(bar.high)} ` +
          `L ${formatPrice(bar.low)} C ${formatPrice(bar.close)}`,
      );
    }

    const cusumUpper = seriesValueAtCrosshair(param, overlaySeries.cusum_upper);
    const cusumLower = seriesValueAtCrosshair(param, overlaySeries.cusum_lower);
    const cusumTrail = seriesValueAtCrosshair(param, overlaySeries.cusum_trail);
    if (cusumUpper !== null || cusumLower !== null || cusumTrail !== null) {
      details.push(
        `CUSUM bands ${formatPrice(cusumLower)} / ${formatPrice(cusumUpper)}` +
          `${cusumTrail === null ? "" : ` · trail ${formatPrice(cusumTrail)}`}`,
      );
    }

    const ewmaFast = seriesValueAtCrosshair(param, overlaySeries.ewma_vol_fast);
    const ewmaMedium = seriesValueAtCrosshair(
      param,
      overlaySeries.ewma_vol_medium,
    );
    const ewmaSlow = seriesValueAtCrosshair(param, overlaySeries.ewma_vol_slow);
    if (ewmaFast !== null || ewmaMedium !== null || ewmaSlow !== null) {
      details.push(
        `EWMA vol/bar ${formatPercent(ewmaFast)} / ` +
          `${formatPercent(ewmaMedium)} / ${formatPercent(ewmaSlow)}`,
      );
    }

    const trendScore = seriesValueAtCrosshair(param, overlaySeries.trend_score);
    const trendQuality = seriesValueAtCrosshair(
      param,
      overlaySeries.trend_path_quality,
    );
    if (trendScore !== null) {
      let trendText = `Vol-scaled Trend ${trendScore.toFixed(3)}`;
      if (trendQuality !== null) {
        trendText += ` · path quality ${formatPercent(trendQuality * 100, 0)}`;
      }
      details.push(trendText);
    }

    const prototypeRegime = prototypeRegimeAtCrosshair(param);
    if (prototypeRegime) {
      details.push(
        `Prototype Regime ${prototypeRegime[0]} · top weight ` +
          `${formatPercent(prototypeRegime[1] * 100, 1)}`,
      );
    }
    const regimeRisk = seriesValueAtCrosshair(
      param,
      overlaySeries.regime_change_risk,
    );
    if (regimeRisk !== null) {
      details.push(`Prototype change caution ${formatPercent(regimeRisk * 100, 1)}`);
    }
    const structureUpper = seriesValueAtCrosshair(
      param,
      overlaySeries.structure_upper,
    );
    const structureLower = seriesValueAtCrosshair(
      param,
      overlaySeries.structure_lower,
    );
    if (structureUpper !== null || structureLower !== null) {
      details.push(
        `Prior 48-bar structure ${formatPrice(structureLower)} / ` +
          `${formatPrice(structureUpper)} · channel known at bar open`,
      );
    }
    const volatilityPercentile = seriesValueAtCrosshair(
      param,
      overlaySeries.comparable_vol_percentile,
    );
    const volatilityRatioState = seriesValueAtCrosshair(
      param,
      overlaySeries.comparable_vol_ratio,
    );
    const volatilityShock = seriesValueAtCrosshair(
      param,
      overlaySeries.comparable_vol_shock,
    );
    if (
      volatilityPercentile !== null ||
      volatilityRatioState !== null ||
      volatilityShock !== null
    ) {
      details.push(
        `Comparable volatility ` +
          `rank ${
            volatilityPercentile === null
              ? "—"
              : formatPercent(volatilityPercentile * 100, 0)
          } · fast/slow state ${
            volatilityRatioState === null
              ? "—"
              : formatSignedScore(volatilityRatioState * 2 - 1)
          } · shock ${
            volatilityShock === null
              ? "—"
              : formatSignedScore(volatilityShock * 2 - 1)
          }`,
      );
    }
    const participationScore = seriesValueAtCrosshair(
      param,
      overlaySeries.participation_score,
    );
    if (participationScore !== null) {
      details.push(
        `Phase-adjusted participation score ${formatSignedScore(
          participationScore * 2 - 1,
        )} · finalized bar`,
      );
    }
    const replayEquity = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_equity,
    );
    const replayDrawdown = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_drawdown,
    );
    const replayPosition = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_position,
    );
    if (replayEquity !== null) {
      details.push(`Replay equity ${replayEquity.toFixed(2)}`);
    }
    if (replayDrawdown !== null) {
      details.push(`Replay drawdown ${formatPercent(replayDrawdown)}`);
    }
    if (replayPosition !== null) {
      details.push(`Replay position ${replayPosition.toFixed(2)}`);
    }
    const protectedStop = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_risk_stop,
    );
    const protectedTarget = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_risk_target,
    );
    if (protectedStop !== null || protectedTarget !== null) {
      details.push(
        `Frozen bracket SL ${formatPrice(protectedStop)} / TP ${formatPrice(
          protectedTarget,
        )}`,
      );
    }
    const metaScore = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_meta_score,
    );
    if (metaScore !== null) {
      details.push(
        `Stored meta score P(TP first) ${formatPercent(metaScore * 100, 1)}`,
      );
    }
    const metaRequiredProbability = seriesValueAtCrosshair(
      param,
      overlaySeries.replay_meta_required_probability,
    );
    if (metaRequiredProbability !== null) {
      details.push(
        `Strict gate requires P > ${formatPercent(
          metaRequiredProbability * 100,
          1,
        )}`,
      );
    }
    const forwardMetaScore = seriesValueAtCrosshair(
      param,
      overlaySeries.forward_meta_shadow_score,
    );
    if (forwardMetaScore !== null) {
      details.push(
        `Forward META SHADOW P(TP first) ${formatPercent(
          forwardMetaScore * 100,
          1,
        )}`,
      );
    }
    elements.crosshair.textContent = details.join("  |  ");
  });

  chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    updateMarkerDensity();
    if (
      !range ||
      suppressVisibleRangeEvents ||
      !elements.autoHistoryToggle.checked ||
      !historyState.canLoadHistory ||
      historyState.isLoadingOlder ||
      historyState.exhaustedLeft
    ) {
      return;
    }
    if (range.from <= HISTORY_LOAD_THRESHOLD_BARS) {
      loadOlderHistory("auto");
    }
  });
}

function replayPayloadForActiveChart() {
  const params = replayRequestParams({ useActiveChart: true });
  if (!params || replayState.selectionKey !== replaySelectionKey(params)) {
    return null;
  }
  return replayState.payload;
}

function forwardMetaShadowPayload() {
  const payload = historyState.forwardMetaShadow;
  return payload && typeof payload === "object" ? payload : null;
}

function forwardMetaScoresForLoadedChart() {
  const points = replaySeriesForLoadedChart(
    forwardMetaShadowPayload()?.scores,
  );
  return mergeByTime([], points).filter(
    (point) => point.value >= 0 && point.value <= 1,
  );
}

function forwardMetaOutcomeMarkersForLoadedChart() {
  const markers = normalizedReplayMarkers(
    forwardMetaShadowPayload()?.outcome_markers,
  );
  const candles = historyState.candles;
  if (candles.length === 0) {
    return [];
  }
  // Lightweight Charts aligns an in-gap marker to the previous series point.
  // Map label evidence to the first candle at or after it became known so a
  // 12:15 label can never appear on a 12:00 hourly candle.  Keep known_at for
  // audit and hide the marker until that next candle is actually loaded.
  return markers
    .map((marker) => {
      let low = 0;
      let high = candles.length;
      while (low < high) {
        const middle = Math.floor((low + high) / 2);
        if (candles[middle].time < marker.time) {
          low = middle + 1;
        } else {
          high = middle;
        }
      }
      if (low >= candles.length) {
        return null;
      }
      return {
        ...marker,
        time: candles[low].time,
        time_semantics: "first_candle_at_or_after_known_at",
      };
    })
    .filter((marker) => marker !== null);
}

function analyticalMarkerForDisplay(marker) {
  const labels = {
    Buy: "CUSUM bull change",
    Sell: "CUSUM bear change",
    "Trend +": "Trend bull change",
    "Trend -": "Trend bear change",
    Risk: "Regime change risk",
  };
  const text = String(marker?.text ?? "");
  return labels[text] ? { ...marker, text: labels[text] } : marker;
}

function combinedChartMarkers() {
  const analyticalMarkers = historyState.markers.map(analyticalMarkerForDisplay);
  const replayMarkers = replayMarkersForLoadedChart(
    replayPayloadForActiveChart()?.markers,
  );
  return mergeMarkers(
    mergeMarkers(analyticalMarkers, replayMarkers),
    forwardMetaOutcomeMarkersForLoadedChart(),
  );
}

function applyMarkers() {
  if (
    !candleSeries ||
    !LightweightCharts.createSeriesMarkers
  ) {
    return;
  }
  const condensed = shouldCondenseMarkerLabels();
  markerLabelsCondensed = condensed;
  const markers = combinedChartMarkers();
  const displayedMarkers = condensed
    ? markers.map((marker) => ({ ...marker, text: "" }))
    : markers;
  if (markerApi?.setMarkers) {
    markerApi.setMarkers(displayedMarkers);
  } else if (displayedMarkers.length > 0) {
    markerApi = LightweightCharts.createSeriesMarkers(
      candleSeries,
      displayedMarkers,
    );
  }
}

function shouldCondenseMarkerLabels() {
  if (!chart || historyState.candles.length === 0) {
    return false;
  }
  if (window.innerWidth < MARKER_LABEL_MIN_VIEWPORT_WIDTH) {
    return true;
  }
  const visibleRange = chart.timeScale().getVisibleRange?.();
  const from = Number(visibleRange?.from);
  const to = Number(visibleRange?.to);
  if (!Number.isFinite(from) || !Number.isFinite(to)) {
    return historyState.candles.length > MARKER_LABEL_MAX_VISIBLE_BARS;
  }
  const lowerBound = (target, includeEqual) => {
    let low = 0;
    let high = historyState.candles.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      const time = historyState.candles[middle].time;
      if (time < target || (!includeEqual && time === target)) {
        low = middle + 1;
      } else {
        high = middle;
      }
    }
    return low;
  };
  const firstVisible = lowerBound(from, true);
  const afterVisible = lowerBound(to, false);
  const visibleEventCount = combinedChartMarkers().filter(
    (marker) => marker.time >= from && marker.time <= to,
  ).length;
  return (
    afterVisible - firstVisible > MARKER_LABEL_MAX_VISIBLE_BARS ||
    visibleEventCount > MARKER_LABEL_MAX_VISIBLE_EVENTS
  );
}

function updateMarkerDensity() {
  if (!markerApi || combinedChartMarkers().length === 0) {
    return;
  }
  const condensed = shouldCondenseMarkerLabels();
  if (condensed !== markerLabelsCondensed) {
    applyMarkers();
  }
}

function ensureLineSeries(key, options, paneIndex = 0) {
  if (overlaySeries[key]) {
    return overlaySeries[key];
  }
  const { LineSeries } = LightweightCharts;
  if (!LineSeries) {
    throw new Error("Lightweight Charts LineSeries API is unavailable.");
  }
  overlaySeries[key] = chart.addSeries(LineSeries, {
    priceLineVisible: false,
    lastValueVisible: false,
    ...options,
  }, paneIndex);
  return overlaySeries[key];
}

function ensureHistogramSeries(key, options, paneIndex = 0) {
  if (overlaySeries[key]) {
    return overlaySeries[key];
  }
  const { HistogramSeries } = LightweightCharts;
  if (!HistogramSeries) {
    throw new Error("Lightweight Charts HistogramSeries API is unavailable.");
  }
  overlaySeries[key] = chart.addSeries(HistogramSeries, {
    priceLineVisible: false,
    lastValueVisible: false,
    ...options,
  }, paneIndex);
  return overlaySeries[key];
}

function ensureIndicatorPane(key, { height = 135, fallbackScaleId = key } = {}) {
  if (indicatorPanes[key]) {
    return indicatorPanes[key];
  }
  if (typeof chart.addPane === "function") {
    const pane = chart.addPane(true);
    if (typeof pane.setHeight === "function") {
      pane.setHeight(height);
    }
    const paneIndex =
      typeof pane.paneIndex === "function"
        ? pane.paneIndex()
        : (chart.panes?.().length ?? 1) - 1;
    indicatorPanes[key] = { paneIndex, dedicated: true, fallbackScaleId };
    return indicatorPanes[key];
  }

  chart.priceScale(fallbackScaleId).applyOptions({
    scaleMargins: { top: 0.70, bottom: 0.05 },
    borderColor: "#d9d7cf",
  });
  indicatorPanes[key] = { paneIndex: 0, dedicated: false, fallbackScaleId };
  return indicatorPanes[key];
}

function hasNumericPoints(series) {
  return Array.isArray(series) && series.some((point) => point?.value !== undefined);
}

function firstNumericSeries(container, fieldNames) {
  for (const field of fieldNames) {
    if (hasNumericPoints(container?.[field])) {
      return container[field];
    }
  }
  return [];
}

function boundedDisplaySeries(points) {
  return (points ?? [])
    .map((point) => ({
      ...point,
      value: Math.min(1, Math.max(0, Number(point?.value))),
    }))
    .filter((point) => Number.isFinite(point.value));
}

function signedScoreAsUnitSeries(points) {
  return (points ?? [])
    .map((point) => {
      const signed = Math.min(1, Math.max(-1, Number(point?.value)));
      return { ...point, value: (signed + 1) / 2 };
    })
    .filter((point) => Number.isFinite(point.value));
}

function formatSignedScore(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}`;
}

function preferredStructureChannel(overlay) {
  const channels = priorStructureChannels(overlay);
  if (channels["48"]) {
    return { lookback: "48", channel: channels["48"] };
  }
  const ordered = Object.entries(channels).sort((left, right) => {
    const leftLookback = Number(left[0]);
    const rightLookback = Number(right[0]);
    if (Number.isFinite(leftLookback) && Number.isFinite(rightLookback)) {
      return rightLookback - leftLookback;
    }
    return left[0].localeCompare(right[0]);
  });
  if (ordered.length > 0) {
    return { lookback: ordered[0][0], channel: ordered[0][1] };
  }
  return { lookback: String(overlay?.lookback_bars ?? 48), channel: overlay ?? {} };
}

function overlayHasChartData(key, overlay) {
  if (!overlay || typeof overlay !== "object") {
    return false;
  }
  if (key === "prior_structure") {
    const { channel } = preferredStructureChannel(overlay);
    return [
      channel.upper,
      channel.upper_channel,
      channel.lower,
      channel.lower_channel,
    ].some(hasNumericPoints);
  }
  if (key === "comparable_volatility") {
    return [
      "volatility_percentile",
      "rs_percentile",
      "percentile",
      "fast_slow_ratio_score",
      "regime_score",
      "range_shock_score",
      "shock_score",
    ].some((field) => hasNumericPoints(overlay[field]));
  }
  if (key === "phase_adjusted_participation") {
    return [
      "participation_score",
      "rvol_score",
      "rvol_percentile",
      "percentile",
    ].some((field) => hasNumericPoints(overlay[field]));
  }
  return Object.values(overlay).some(hasNumericPoints);
}

function applyCusumOverlay(overlay) {
  if (!overlay || !chart) {
    return;
  }
  const lineStyle = LightweightCharts.LineStyle?.Dotted;
  const upper = ensureLineSeries("cusum_upper", {
    color: INDICATOR_COLORS.cusumUpper,
    lineWidth: 1,
  });
  const lower = ensureLineSeries("cusum_lower", {
    color: INDICATOR_COLORS.cusumLower,
    lineWidth: 1,
  });
  const trail = ensureLineSeries("cusum_trail", {
    color: INDICATOR_COLORS.cusumTrail,
    lineWidth: 2,
    ...(lineStyle === undefined ? {} : { lineStyle }),
  });
  upper.setData(overlay.upper_band ?? []);
  lower.setData(overlay.lower_band ?? []);
  trail.setData(overlay.trail_stop ?? []);
}

function applyEwmaVolatilityOverlay(overlay) {
  if (!overlay || !chart || !hasNumericPoints(overlay.fast)) {
    return;
  }
  const pane = ensureIndicatorPane("ewma_volatility", {
    height: 125,
    fallbackScaleId: "ewma_volatility",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "ewma_volatility" };
  const priceFormat = {
    type: "custom",
    minMove: 0.0001,
    formatter: (value) => formatPercent(value),
  };
  const fast = ensureLineSeries("ewma_vol_fast", {
    title: "EWMA volatility · fast",
    color: INDICATOR_COLORS.fast,
    lineWidth: 2,
    lastValueVisible: true,
    priceFormat,
    ...fallbackScale,
  }, pane.paneIndex);
  const medium = ensureLineSeries("ewma_vol_medium", {
    title: "EWMA volatility · medium",
    color: INDICATOR_COLORS.medium,
    lineWidth: 2,
    lastValueVisible: true,
    priceFormat,
    ...fallbackScale,
  }, pane.paneIndex);
  const slow = ensureLineSeries("ewma_vol_slow", {
    title: "EWMA volatility · slow",
    color: INDICATOR_COLORS.slow,
    lineWidth: 2,
    lastValueVisible: true,
    priceFormat,
    ...fallbackScale,
  }, pane.paneIndex);
  fast.setData(overlay.fast ?? []);
  medium.setData(overlay.medium ?? []);
  slow.setData(overlay.slow ?? []);
}

function applyVolatilityScaledTrendOverlay(overlay) {
  const hasTrendData = [
    overlay?.score,
    overlay?.fast,
    overlay?.medium,
    overlay?.slow,
  ].some(hasNumericPoints);
  if (!overlay || !chart || !hasTrendData) {
    return;
  }
  const pane = ensureIndicatorPane("volatility_scaled_trend", {
    height: 135,
    fallbackScaleId: "volatility_scaled_trend",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "volatility_scaled_trend" };
  const priceFormat = {
    type: "custom",
    minMove: 0.001,
    formatter: (value) => Number(value).toFixed(2),
  };
  const horizons = overlay.horizons_bars ?? {};
  const dotted = LightweightCharts.LineStyle?.Dotted;
  const fast = ensureLineSeries("trend_fast", {
    title: `Vol-scaled Trend · fast ${horizons.fast ?? "?"} bars`,
    color: INDICATOR_COLORS.fast,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const medium = ensureLineSeries("trend_medium", {
    title: `Vol-scaled Trend · medium ${horizons.medium ?? "?"} bars`,
    color: INDICATOR_COLORS.medium,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const slow = ensureLineSeries("trend_slow", {
    title: `Vol-scaled Trend · slow ${horizons.slow ?? "?"} bars`,
    color: INDICATOR_COLORS.slow,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const score = ensureLineSeries("trend_score", {
    title: "Vol-scaled Trend · composite score",
    color: INDICATOR_COLORS.trendScore,
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat,
    autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const pathQuality = ensureLineSeries("trend_path_quality", {
    title: "Vol-scaled Trend · path quality",
    color: INDICATOR_COLORS.trendQuality,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: TREND_AUTOSCALE_PROVIDER,
    ...(dotted === undefined ? {} : { lineStyle: dotted }),
    ...fallbackScale,
  }, pane.paneIndex);
  fast.setData(overlay.fast ?? []);
  medium.setData(overlay.medium ?? []);
  slow.setData(overlay.slow ?? []);
  score.setData(overlay.score ?? []);
  pathQuality.setData(overlay.path_quality ?? []);
  if (!overlayPriceLines.trendZero && typeof score.createPriceLine === "function") {
    overlayPriceLines.trendZero = score.createPriceLine({
      price: 0,
      color: "rgba(85, 80, 71, 0.45)",
      lineWidth: 1,
      ...(dotted === undefined ? {} : { lineStyle: dotted }),
      axisLabelVisible: true,
      title: "Vol-trend 0",
    });
  }
}

function applyOnlineRegimeOverlay(overlay) {
  if (!overlay || !chart || !hasNumericPoints(overlay.state_band)) {
    return;
  }
  const pane = ensureIndicatorPane("online_regime", {
    height: 150,
    fallbackScaleId: "online_regime",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "online_regime" };
  const priceFormat = {
    type: "custom",
    minMove: 0.001,
    formatter: (value) => formatPercent(Number(value) * 100, 0),
  };
  const dotted = LightweightCharts.LineStyle?.Dotted;
  const stateBand = ensureHistogramSeries("regime_state_band", {
    title: "Prototype Regime · active state band",
    base: 0,
    color: "rgba(87, 117, 144, 0.20)",
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const bull = ensureLineSeries("regime_bull", {
    title: "Prototype Regime · bull weight",
    color: INDICATOR_COLORS.regimeBull,
    lineWidth: 2,
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const bear = ensureLineSeries("regime_bear", {
    title: "Prototype Regime · bear weight",
    color: INDICATOR_COLORS.regimeBear,
    lineWidth: 2,
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const range = ensureLineSeries("regime_range", {
    title: "Prototype Regime · range weight",
    color: INDICATOR_COLORS.regimeRange,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const transition = ensureLineSeries("regime_transition", {
    title: "Prototype Regime · transition weight",
    color: INDICATOR_COLORS.regimeTransition,
    lineWidth: 2,
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const changeRisk = ensureLineSeries("regime_change_risk", {
    title: "Prototype Regime · change risk",
    color: INDICATOR_COLORS.regimeChangeRisk,
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat,
    autoscaleInfoProvider: REGIME_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  stateBand.setData(overlay.state_band ?? []);
  bull.setData(overlay.bull ?? []);
  bear.setData(overlay.bear ?? []);
  range.setData(overlay.range ?? []);
  transition.setData(overlay.transition ?? []);
  changeRisk.setData(overlay.change_risk ?? []);
  const riskThreshold = Number(overlay.change_risk_threshold);
  if (
    !overlayPriceLines.regimeRiskThreshold &&
    Number.isFinite(riskThreshold) &&
    typeof changeRisk.createPriceLine === "function"
  ) {
    overlayPriceLines.regimeRiskThreshold = changeRisk.createPriceLine({
      price: riskThreshold,
      color: INDICATOR_COLORS.regimeChangeRisk,
      lineWidth: 1,
      ...(dotted === undefined ? {} : { lineStyle: dotted }),
      axisLabelVisible: true,
      title: "Change-risk threshold",
    });
  }
}

function applyPriorStructureOverlay(overlay) {
  if (!overlay || !chart) {
    return;
  }
  const { lookback, channel } = preferredStructureChannel(overlay);
  const upperData = firstNumericSeries(channel, ["upper", "upper_channel"]);
  const lowerData = firstNumericSeries(channel, ["lower", "lower_channel"]);
  if (![upperData, lowerData].some(hasNumericPoints)) {
    return;
  }
  const dotted = LightweightCharts.LineStyle?.Dotted;
  const upper = ensureLineSeries("structure_upper", {
    title: `Prior Structure · ${lookback}-bar high`,
    color: INDICATOR_COLORS.structureUpper,
    lineWidth: 1,
    ...(dotted === undefined ? {} : { lineStyle: dotted }),
  });
  const lower = ensureLineSeries("structure_lower", {
    title: `Prior Structure · ${lookback}-bar low`,
    color: INDICATOR_COLORS.structureLower,
    lineWidth: 1,
    ...(dotted === undefined ? {} : { lineStyle: dotted }),
  });
  upper.setData(upperData);
  lower.setData(lowerData);
}

function applyComparableVolatilityOverlay(overlay) {
  if (!overlay || !chart || !overlayHasChartData("comparable_volatility", overlay)) {
    return;
  }
  const percentileData = boundedDisplaySeries(
    firstNumericSeries(overlay, [
      "volatility_percentile",
      "rs_percentile",
      "percentile",
    ]),
  );
  const ratioData = signedScoreAsUnitSeries(
    firstNumericSeries(overlay, ["fast_slow_ratio_score", "regime_score"]),
  );
  const shockData = signedScoreAsUnitSeries(
    firstNumericSeries(overlay, ["range_shock_score", "shock_score"]),
  );
  const pane = ensureIndicatorPane("comparable_volatility", {
    height: 132,
    fallbackScaleId: "comparable_volatility",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "comparable_volatility" };
  const priceFormat = {
    type: "custom",
    minMove: 0.01,
    formatter: (value) => formatPercent(Number(value) * 100, 0),
  };
  const dotted = LightweightCharts.LineStyle?.Dotted;
  const percentile = ensureLineSeries("comparable_vol_percentile", {
    title: "Comparable Volatility · RS percentile",
    color: INDICATOR_COLORS.comparableVolatility,
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat,
    autoscaleInfoProvider: MARKET_CONTEXT_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const ratio = ensureLineSeries("comparable_vol_ratio", {
    title: "Comparable Volatility · fast / slow score (50% neutral)",
    color: INDICATOR_COLORS.comparableVolatilityRatio,
    lineWidth: 2,
    priceFormat,
    autoscaleInfoProvider: MARKET_CONTEXT_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  const shock = ensureLineSeries("comparable_vol_shock", {
    title: "Comparable Volatility · range-shock score (50% neutral)",
    color: INDICATOR_COLORS.comparableVolatilityShock,
    lineWidth: 1,
    priceFormat,
    autoscaleInfoProvider: MARKET_CONTEXT_AUTOSCALE_PROVIDER,
    ...(dotted === undefined ? {} : { lineStyle: dotted }),
    ...fallbackScale,
  }, pane.paneIndex);
  percentile.setData(percentileData);
  ratio.setData(ratioData);
  shock.setData(shockData);
  if (
    !overlayPriceLines.comparableVolMidpoint &&
    typeof percentile.createPriceLine === "function"
  ) {
    overlayPriceLines.comparableVolMidpoint = percentile.createPriceLine({
      price: 0.5,
      color: "rgba(130, 144, 163, 0.48)",
      lineWidth: 1,
      ...(dotted === undefined ? {} : { lineStyle: dotted }),
      axisLabelVisible: false,
      title: "50% · neutral score / median rank",
    });
  }
}

function applyParticipationOverlay(overlay) {
  if (
    !overlay ||
    !chart ||
    !overlayHasChartData("phase_adjusted_participation", overlay)
  ) {
    return;
  }
  const scoreData = signedScoreAsUnitSeries(
    firstNumericSeries(overlay, [
      "participation_score",
      "rvol_score",
      "rvol_percentile",
      "percentile",
    ]),
  );
  const pane = ensureIndicatorPane("phase_adjusted_participation", {
    height: 122,
    fallbackScaleId: "phase_adjusted_participation",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "phase_adjusted_participation" };
  const dotted = LightweightCharts.LineStyle?.Dotted;
  const score = ensureLineSeries("participation_score", {
    title: "Phase-adjusted Participation · score (50% neutral)",
    color: INDICATOR_COLORS.participation,
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat: {
      type: "custom",
      minMove: 0.01,
      formatter: (value) => formatPercent(Number(value) * 100, 0),
    },
    autoscaleInfoProvider: MARKET_CONTEXT_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  score.setData(scoreData);
  if (
    !overlayPriceLines.participationMidpoint &&
    typeof score.createPriceLine === "function"
  ) {
    overlayPriceLines.participationMidpoint = score.createPriceLine({
      price: 0.5,
      color: INDICATOR_COLORS.contextReference,
      lineWidth: 1,
      ...(dotted === undefined ? {} : { lineStyle: dotted }),
      axisLabelVisible: false,
      title: "50% · neutral activity",
    });
  }
}

function applyReplayOverlay(payload) {
  if (!payload || !chart) {
    return;
  }
  const stopData = replayPriceSeriesForLoadedChart(payload.risk_stop);
  const targetData = replayPriceSeriesForLoadedChart(payload.risk_target);
  const stop = ensureLineSeries("replay_risk_stop", {
    title: "Protected replay · frozen stop",
    color: INDICATOR_COLORS.protectedStop,
    lineWidth: 2,
    ...(LightweightCharts.LineStyle?.Dashed === undefined
      ? {}
      : { lineStyle: LightweightCharts.LineStyle.Dashed }),
    priceFormat: {
      type: "price",
      precision: activePricePrecision,
      minMove: activePriceMinMove,
    },
  });
  const target = ensureLineSeries("replay_risk_target", {
    title: "Protected replay · take profit",
    color: INDICATOR_COLORS.protectedTarget,
    lineWidth: 2,
    ...(LightweightCharts.LineStyle?.Dashed === undefined
      ? {}
      : { lineStyle: LightweightCharts.LineStyle.Dashed }),
    priceFormat: {
      type: "price",
      precision: activePricePrecision,
      minMove: activePriceMinMove,
    },
  });
  stop.setData(stopData);
  target.setData(targetData);

  const metaScoreData = replaySeriesForLoadedChart(payload.meta_scores);
  const metaRequiredProbabilityData =
    replayRequiredProbabilityForLoadedChart(payload);
  if (
    hasNumericPoints(metaScoreData) ||
    hasNumericPoints(metaRequiredProbabilityData)
  ) {
    const metaPane = ensureIndicatorPane("meta_label_score", {
      height: 118,
      fallbackScaleId: "meta_label_score",
    });
    const fallbackScale = metaPane.dedicated
      ? {}
      : { priceScaleId: "meta_label_score" };
    const metaScore = ensureLineSeries("replay_meta_score", {
      title: "CUSUM meta-label · stored P(TP before SL)",
      color: INDICATOR_COLORS.metaScore,
      lineWidth: 3,
      lastValueVisible: true,
      priceFormat: {
        type: "custom",
        minMove: 0.01,
        formatter: (value) => formatPercent(Number(value) * 100, 1),
      },
      autoscaleInfoProvider: META_SCORE_AUTOSCALE_PROVIDER,
      ...fallbackScale,
    }, metaPane.paneIndex);
    metaScore.setData(metaScoreData);
    const metaRequiredProbability = ensureLineSeries(
      "replay_meta_required_probability",
      {
        title: "CUSUM meta-label · strict required P",
        color: "#c792ea",
        lineWidth: 2,
        lastValueVisible: true,
        ...(LightweightCharts.LineStyle?.Dashed === undefined
          ? {}
          : { lineStyle: LightweightCharts.LineStyle.Dashed }),
        priceFormat: {
          type: "custom",
          minMove: 0.01,
          formatter: (value) => formatPercent(Number(value) * 100, 1),
        },
        autoscaleInfoProvider: META_SCORE_AUTOSCALE_PROVIDER,
        ...fallbackScale,
      },
      metaPane.paneIndex,
    );
    metaRequiredProbability.setData(metaRequiredProbabilityData);
    const threshold = Number(
      payload.config?.meta_filter?.decision_threshold ??
        payload.metadata?.meta_filter?.decision_threshold,
    );
    if (Number.isFinite(threshold) && threshold >= 0 && threshold <= 1) {
      if (
        !overlayPriceLines.replayMetaThreshold &&
        typeof metaScore.createPriceLine === "function"
      ) {
        overlayPriceLines.replayMetaThreshold = metaScore.createPriceLine({
          price: threshold,
          color: "rgba(248, 193, 92, 0.45)",
          lineWidth: 1,
          ...(LightweightCharts.LineStyle?.Dotted === undefined
            ? {}
            : { lineStyle: LightweightCharts.LineStyle.Dotted }),
          axisLabelVisible: true,
          title: "frozen model threshold · strict event gate shown in purple",
        });
      } else {
        overlayPriceLines.replayMetaThreshold?.applyOptions?.({ price: threshold });
      }
    } else {
      clearReplayMetaModelThreshold();
    }
  } else {
    overlaySeries.replay_meta_score?.setData([]);
    overlaySeries.replay_meta_required_probability?.setData([]);
    clearReplayMetaModelThreshold();
  }

  const equityData = replaySeriesForLoadedChart(payload.equity);
  const drawdownData = replaySeriesForLoadedChart(payload.drawdown);
  const positionData = replaySeriesForLoadedChart(payload.position);
  if (![equityData, drawdownData, positionData].some(hasNumericPoints)) {
    return;
  }

  const pane = ensureIndicatorPane("causal_replay", {
    height: 185,
    fallbackScaleId: "replay_equity",
  });
  const equityScale = pane.dedicated ? {} : { priceScaleId: "replay_equity" };
  const equity = ensureLineSeries("replay_equity", {
    title: "1m causal replay · equity",
    color: "#1d3557",
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat: {
      type: "custom",
      minMove: 0.01,
      formatter: (value) => Number(value).toFixed(2),
    },
    ...equityScale,
  }, pane.paneIndex);
  const drawdown = ensureLineSeries("replay_drawdown", {
    title: "1m causal replay · drawdown",
    color: "#d1495b",
    lineWidth: 2,
    priceScaleId: "replay_drawdown",
    priceFormat: {
      type: "custom",
      minMove: 0.01,
      formatter: (value) => formatPercent(value),
    },
  }, pane.paneIndex);
  const position = ensureHistogramSeries("replay_position", {
    title: "1m causal replay · position",
    base: 0,
    color: "rgba(108, 117, 125, 0.35)",
    priceScaleId: "replay_position",
    priceFormat: {
      type: "custom",
      minMove: 0.01,
      formatter: (value) => Number(value).toFixed(2),
    },
  }, pane.paneIndex);
  equity.setData(equityData);
  drawdown.setData(drawdownData);
  position.setData(positionData);

  if (
    !overlayPriceLines.replayDrawdownZero &&
    typeof drawdown.createPriceLine === "function"
  ) {
    overlayPriceLines.replayDrawdownZero = drawdown.createPriceLine({
      price: 0,
      color: "rgba(209, 73, 91, 0.35)",
      lineWidth: 1,
      axisLabelVisible: false,
      title: "Drawdown 0%",
    });
  }
}

function clearReplayMetaModelThreshold() {
  const threshold = overlayPriceLines.replayMetaThreshold;
  const scoreSeries = overlaySeries.replay_meta_score;
  if (threshold && typeof scoreSeries?.removePriceLine === "function") {
    scoreSeries.removePriceLine(threshold);
  }
  delete overlayPriceLines.replayMetaThreshold;
}

function clearReplayOverlayData() {
  for (const key of [
    "replay_equity",
    "replay_drawdown",
    "replay_position",
    "replay_risk_stop",
    "replay_risk_target",
    "replay_meta_score",
    "replay_meta_required_probability",
  ]) {
    overlaySeries[key]?.setData([]);
  }
  clearReplayMetaModelThreshold();
}

function applyForwardMetaShadowOverlay() {
  const scoreData = forwardMetaScoresForLoadedChart();
  if (!chart || scoreData.length === 0) {
    overlaySeries.forward_meta_shadow_score?.setData([]);
    return;
  }
  const pane = ensureIndicatorPane("forward_meta_shadow", {
    height: 145,
    fallbackScaleId: "forward_meta_shadow_score",
  });
  const fallbackScale = pane.dedicated
    ? {}
    : { priceScaleId: "forward_meta_shadow_score" };
  const series = ensureLineSeries("forward_meta_shadow_score", {
    title: "Forward META SHADOW · stored P(TP before SL)",
    color: INDICATOR_COLORS.forwardMetaScore,
    lineWidth: 3,
    lastValueVisible: true,
    priceFormat: {
      type: "custom",
      minMove: 0.01,
      formatter: (value) => formatPercent(Number(value) * 100, 1),
    },
    autoscaleInfoProvider: META_SCORE_AUTOSCALE_PROVIDER,
    ...fallbackScale,
  }, pane.paneIndex);
  series.setData(scoreData);
}

function applyOverlays() {
  applyCusumOverlay(historyState.overlays.cusum_trend);
  applyEwmaVolatilityOverlay(historyState.overlays.ewma_volatility);
  applyVolatilityScaledTrendOverlay(
    historyState.overlays.volatility_scaled_trend,
  );
  applyOnlineRegimeOverlay(historyState.overlays.online_regime);
  applyPriorStructureOverlay(historyState.overlays.prior_structure);
  applyComparableVolatilityOverlay(
    historyState.overlays.comparable_volatility,
  );
  applyParticipationOverlay(
    historyState.overlays.phase_adjusted_participation,
  );
  const replayPayload = replayPayloadForActiveChart();
  if (replayPayload) {
    applyReplayOverlay(replayPayload);
  } else {
    clearReplayOverlayData();
  }
  applyForwardMetaShadowOverlay();
}

function applyOptionalDecorations() {
  overlayWarning = "";
  try {
    applyMarkers();
    applyOverlays();
  } catch (error) {
    overlayWarning = `Indicator overlay failed; candles are shown. ${error.message}`;
    console.error(error);
  }
}

function validatePayload(payload) {
  if (!payload || !Array.isArray(payload.candles)) {
    throw new Error("Payload is missing candles array.");
  }
  if (payload.candles.length === 0) {
    throw new Error("Payload contains zero candles.");
  }
}

function setOptions(select, options, getValue, getLabel, preferredValue = null) {
  select.replaceChildren();
  for (const optionData of options) {
    const option = document.createElement("option");
    option.value = getValue(optionData);
    option.textContent = getLabel(optionData);
    select.appendChild(option);
  }
  if (preferredValue && options.some((item) => getValue(item) === preferredValue)) {
    select.value = preferredValue;
  }
}

function getAssetEntry(asset = elements.assetSelect.value) {
  return manifest?.assets?.find((entry) => entry.asset === asset) ?? null;
}

function getSourceEntry(source = elements.sourceSelect.value) {
  const assetEntry = getAssetEntry();
  return assetEntry?.sources?.find((entry) => entry.source === source) ?? null;
}

function populateAssetOptions() {
  const defaultAsset = manifest?.defaults?.asset ?? "BTCUSDT";
  setOptions(
    elements.assetSelect,
    manifest?.assets ?? [],
    (entry) => entry.asset,
    (entry) => entry.asset,
    defaultAsset,
  );
}

function populateSourceOptions() {
  const assetEntry = getAssetEntry();
  const defaultSource = manifest?.defaults?.source ?? "canonical";
  setOptions(
    elements.sourceSelect,
    assetEntry?.sources ?? [],
    (entry) => entry.source,
    (entry) => entry.label ?? entry.source,
    defaultSource,
  );
}

function populateTimeframeOptions() {
  const sourceEntry = getSourceEntry();
  const defaultTimeframe = manifest?.defaults?.timeframe ?? "1h";
  setOptions(
    elements.timeframeSelect,
    sourceEntry?.timeframes ?? [],
    (entry) => entry.timeframe,
    (entry) =>
      `${entry.timeframe} (${entry.provider}, ${entry.sourcePathCount} files)`,
    defaultTimeframe,
  );
  renderTimeframeQuickbar();
}

function renderTimeframeQuickbar() {
  if (!elements.timeframeQuickbar) {
    return;
  }
  elements.timeframeQuickbar.replaceChildren();
  for (const option of Array.from(elements.timeframeSelect.options)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "timeframe-button";
    button.dataset.timeframe = option.value;
    button.textContent = option.value;
    button.title = option.textContent;
    button.classList.toggle("active", option.value === elements.timeframeSelect.value);
    button.setAttribute(
      "aria-pressed",
      option.value === elements.timeframeSelect.value ? "true" : "false",
    );
    button.addEventListener("click", () => {
      if (elements.timeframeSelect.value === option.value) {
        return;
      }
      elements.timeframeSelect.value = option.value;
      updateTimeframeQuickbarSelection();
      refreshForwardPaperStatus();
      loadPayload();
    });
    elements.timeframeQuickbar.appendChild(button);
  }
}

function updateTimeframeQuickbarSelection() {
  if (!elements.timeframeQuickbar) {
    return;
  }
  for (const button of elements.timeframeQuickbar.querySelectorAll(
    "[data-timeframe]",
  )) {
    const selected = button.dataset.timeframe === elements.timeframeSelect.value;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", selected ? "true" : "false");
  }
}

function populateControls() {
  populateAssetOptions();
  populateSourceOptions();
  populateTimeframeOptions();
  elements.maxBarsInput.max = manifest?.limits?.hardMaxBars ?? 50000;
  elements.maxBarsInput.value = manifest?.defaults?.maxBars ?? 5000;
  updateIndicatorControls();
  updateReplayAvailability();
}

function updateIndicatorControls() {
  const hasCusum = selectedIndicators().includes("cusum_trend");
  elements.cusumSensitivitySelect.disabled = !hasCusum;
  elements.cusumSensitivityField.classList.toggle("disabled", !hasCusum);
  for (const card of elements.indicatorCards) {
    const input = card.querySelector("input[name='indicators']");
    card.classList.toggle("active", Boolean(input?.checked));
  }
  const count = selectedIndicators().length;
  if (elements.visibleLayerCount) {
    elements.visibleLayerCount.textContent = `${count} visible`;
  }
}

function scheduleLayerReload() {
  if (layerReloadTimer !== null) {
    window.clearTimeout(layerReloadTimer);
  }
  layerReloadTimer = window.setTimeout(() => {
    layerReloadTimer = null;
    loadPayload();
  }, 180);
}

function setAllIndicators(checked) {
  for (const input of elements.indicatorInputs) {
    input.checked = checked;
  }
  updateIndicatorControls();
  scheduleLayerReload();
}

function selectedIndicators() {
  return elements.indicatorInputs
    .filter((input) => input.checked)
    .map((input) => input.value);
}

function selectedParams() {
  const params = new URLSearchParams();
  params.set("asset", elements.assetSelect.value);
  params.set("source", elements.sourceSelect.value);
  params.set("timeframe", elements.timeframeSelect.value);
  params.set("max_bars", elements.maxBarsInput.value || "5000");
  const indicators = selectedIndicators();
  if (indicators.length > 0) {
    params.set("indicators", indicators.join(","));
  }
  if (indicators.includes("cusum_trend")) {
    params.set("cusum_sensitivity", elements.cusumSensitivitySelect.value);
  }
  if (elements.startInput.value.trim()) {
    params.set("start", elements.startInput.value.trim());
  }
  if (elements.endInput.value.trim()) {
    params.set("end", elements.endInput.value.trim());
  }
  return params;
}

function isCanonicalSource(source) {
  return String(source ?? "").toLowerCase() === "canonical";
}

function chartSelectionMatchesControls() {
  if (!activeChartParams) {
    return false;
  }
  const selected = selectedParams();
  return ["asset", "source", "timeframe", "start", "end"].every(
    (field) => (activeChartParams.get(field) ?? "") === (selected.get(field) ?? ""),
  );
}

function setResearchModeState(element, message, level = "neutral") {
  element.textContent = message;
  element.className = `research-mode-state ${level}`;
}

function syncProtectedReplayControls(payload = null) {
  const protectedBracketEnabled = elements.replayProtectedBracketInput.checked;
  for (const input of [
    elements.replayRiskUnitVolatilityInput,
    elements.replayStopRiskUnitsInput,
    elements.replayTargetRiskUnitsInput,
    elements.replayTimeoutTargetBarsInput,
    elements.replayBreakEvenSafetyMarginInput,
  ]) {
    input.disabled = !protectedBracketEnabled;
  }

  const protection = payload?.config?.protected_bracket;
  if (protection?.enabled === true) {
    setResearchModeState(
      elements.replayPolicyState,
      `Protected · ${protection.stop_risk_units ?? "?"}R SL / ${
        protection.target_risk_units ?? "?"
      }R TP`,
      "active",
    );
  } else if (payload && protection?.enabled !== true) {
    setResearchModeState(elements.replayPolicyState, "E0 · protection off", "neutral");
  } else if (protectedBracketEnabled) {
    setResearchModeState(elements.replayPolicyState, "Protected · pending replay", "warn");
  } else {
    setResearchModeState(elements.replayPolicyState, "E0 · protection off", "neutral");
  }

  const selectedMetaMode = elements.replayMetaFilterModeSelect.value;
  const meta = payload?.config?.meta_filter ?? payload?.metadata?.meta_filter;
  const mode = typeof meta === "string" ? meta : meta?.mode;
  const status = String(meta?.artifact_status ?? meta?.status ?? "").toLowerCase();
  const artifactChecksum =
    meta?.artifact_checksum ?? meta?.artifact_digest ?? meta?.model_digest;
  const artifactDigest = compactDigest(artifactChecksum, 8);
  if ((mode ?? selectedMetaMode) === "off") {
    setResearchModeState(elements.replayMetaState, "ML off · no scoring", "neutral");
  } else if (
    ["available", "loaded", "compatible", "loaded_compatible", "promoted"].includes(
      status,
    )
  ) {
    setResearchModeState(
      elements.replayMetaState,
      `ML ${mode} · artifact ${artifactDigest ?? "loaded"}`,
      mode === "gate" ? "active" : "warn",
    );
  } else if (payload) {
    setResearchModeState(
      elements.replayMetaState,
      `ML ${mode ?? selectedMetaMode} · artifact unavailable`,
      "error",
    );
  } else {
    setResearchModeState(
      elements.replayMetaState,
      `ML ${selectedMetaMode} · artifact checked on run`,
      "warn",
    );
  }
}

function replayRequestParams({ useActiveChart = false } = {}) {
  const base = useActiveChart ? activeChartParams : selectedParams();
  if (!base || !isCanonicalSource(base.get("source"))) {
    return null;
  }

  const replayDays = Number(elements.replayDaysInput.value);
  const feeBps = Number(elements.replayFeeInput.value);
  const slippageBps = Number(elements.replaySlippageInput.value);
  const spreadBps = Number(elements.replaySpreadInput.value);
  const executionLatencyMinutes = Number(elements.replayLatencyInput.value);
  const protectedBracketEnabled = elements.replayProtectedBracketInput.checked;
  const riskUnitVolatilityMultiplier = Number(
    elements.replayRiskUnitVolatilityInput.value,
  );
  const stopRiskUnits = Number(elements.replayStopRiskUnitsInput.value);
  const targetRiskUnits = Number(elements.replayTargetRiskUnitsInput.value);
  const timeoutTargetBars = Number(elements.replayTimeoutTargetBarsInput.value);
  const breakEvenSafetyMargin = Number(
    elements.replayBreakEvenSafetyMarginInput.value,
  );
  const metaFilterMode = elements.replayMetaFilterModeSelect.value;
  if (
    !Number.isInteger(replayDays) ||
    replayDays < 1 ||
    replayDays > 730 ||
    !Number.isFinite(feeBps) ||
    feeBps < 0 ||
    feeBps > 1000 ||
    !Number.isFinite(slippageBps) ||
    slippageBps < 0 ||
    slippageBps > 1000 ||
    !Number.isFinite(spreadBps) ||
    spreadBps < 0 ||
    spreadBps > 1000 ||
    !Number.isInteger(executionLatencyMinutes) ||
    executionLatencyMinutes < 0 ||
    executionLatencyMinutes > 60 ||
    !["off", "shadow", "gate"].includes(metaFilterMode) ||
    (protectedBracketEnabled &&
      (!Number.isFinite(riskUnitVolatilityMultiplier) ||
        riskUnitVolatilityMultiplier < 0.1 ||
        riskUnitVolatilityMultiplier > 20 ||
        !Number.isFinite(stopRiskUnits) ||
        stopRiskUnits < 0.1 ||
        stopRiskUnits > 20 ||
        !Number.isFinite(targetRiskUnits) ||
        targetRiskUnits < 0.1 ||
        targetRiskUnits > 50 ||
        !Number.isInteger(timeoutTargetBars) ||
        timeoutTargetBars < 1 ||
        timeoutTargetBars > 1000 ||
        !Number.isFinite(breakEvenSafetyMargin) ||
        breakEvenSafetyMargin < 0 ||
        breakEvenSafetyMargin > 0.5))
  ) {
    return null;
  }

  const params = new URLSearchParams();
  params.set("asset", base.get("asset") ?? "");
  params.set("timeframe", base.get("timeframe") ?? "");
  for (const field of ["start", "end"]) {
    const value = base.get(field);
    if (value) {
      params.set(field, value);
    }
  }
  params.set("replay_days", String(replayDays));
  params.set("fee_bps", String(feeBps));
  params.set("slippage_bps", String(slippageBps));
  params.set("spread_bps", String(spreadBps));
  params.set("execution_latency_minutes", String(executionLatencyMinutes));
  params.set("event_limit", String(REPLAY_EVENT_LIMIT));
  params.set("cusum_sensitivity", elements.cusumSensitivitySelect.value);
  params.set("protected_bracket", protectedBracketEnabled ? "1" : "0");
  if (protectedBracketEnabled) {
    params.set(
      "risk_unit_volatility_multiplier",
      String(riskUnitVolatilityMultiplier),
    );
    params.set("stop_risk_units", String(stopRiskUnits));
    params.set("target_risk_units", String(targetRiskUnits));
    params.set("timeout_target_bars", String(timeoutTargetBars));
    params.set("break_even_safety_margin", String(breakEvenSafetyMargin));
  }
  params.set("meta_filter_mode", metaFilterMode);
  return params;
}

function replaySelectionKey(params) {
  return params ? params.toString() : null;
}

function updateReplayAvailability() {
  const available = isCanonicalSource(elements.sourceSelect.value);
  const wasAvailable = !elements.replayPanel.classList.contains("unavailable");
  elements.replayPanel.classList.toggle("unavailable", !available);
  elements.replayControls.disabled = !available || replayState.requestInFlight;
  elements.replaySourceBadge.textContent = available
    ? "Manual current-canonical snapshot"
    : "Unavailable for debug sources";
  if (!available) {
    elements.replayResults.hidden = true;
    elements.replayPaneLegend.hidden = true;
    elements.replayProtectionLegend.hidden = true;
    elements.replayMetaLegend.hidden = true;
    elements.replayMarkerLegend.hidden = true;
    clearReplayOverlayData();
    applyMarkers();
    setReplayStatus("Select canonical data", "info");
    renderResearchParityNote();
  } else if (!wasAvailable && !replayState.requestInFlight) {
    setReplayStatus("Ready for a manual canonical replay", "info");
  }
}

function humanizeMetricKey(key) {
  return String(key)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatReplayMetric(key, rawValue) {
  if (rawValue === null || rawValue === undefined) {
    return "-";
  }
  if (typeof rawValue === "boolean") {
    return rawValue ? "Yes" : "No";
  }
  const numeric = Number(rawValue);
  if (!Number.isFinite(numeric)) {
    return typeof rawValue === "object"
      ? JSON.stringify(rawValue)
      : String(rawValue);
  }
  const normalizedKey = String(key).toLowerCase();
  if (normalizedKey.includes("pct") || normalizedKey.includes("percent")) {
    return formatPercent(numeric, 2);
  }
  if (normalizedKey.includes("bps")) {
    return `${numeric.toFixed(2)} bps`;
  }
  if (
    normalizedKey.includes("count") ||
    normalizedKey.includes("trades") ||
    normalizedKey.endsWith("bars")
  ) {
    return Math.round(numeric).toLocaleString();
  }
  if (Number.isInteger(numeric) && Math.abs(numeric) >= 10) {
    return numeric.toLocaleString();
  }
  return Math.abs(numeric) < 0.01 && numeric !== 0
    ? numeric.toFixed(4)
    : numeric.toFixed(2);
}

function compactDigest(value, length = 12) {
  const text = String(value ?? "").trim();
  if (!text) {
    return null;
  }
  return text.length > length ? text.slice(0, length) : text;
}

function formatDurationSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`;
  }
  if (seconds < 60) {
    return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  }
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function ageFromTimestamp(value) {
  const timestamp = Date.parse(String(value ?? ""));
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  return formatDurationSeconds(Math.max(0, Date.now() - timestamp) / 1000);
}

function addFact(container, label, value, title = null) {
  if (value === null || value === undefined || value === "") {
    return;
  }
  const fact = document.createElement("span");
  fact.className = "paper-fact";
  fact.textContent = `${label}: ${value}`;
  fact.title = title ?? fact.textContent;
  container.appendChild(fact);
}

function setRiskBadge(element, message, level = "warn") {
  element.textContent = message;
  element.className = `risk-badge ${level}`;
}

function numericContractValue(object, key) {
  const value = Number(object?.[key]);
  return Number.isFinite(value) ? value : null;
}

function formatContractBps(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)} bps / unit turnover` : null;
}

function renderMetricCards(container, metrics) {
  container.replaceChildren();
  const entries = Object.entries(metrics ?? {});
  const priority = [
    "total_return_pct",
    "gross_total_return_pct",
    "annualized_sharpe",
    "max_drawdown_pct",
    "fill_count",
    "round_trip_count",
    "round_trip_win_rate_pct",
    "total_cost_pct_of_initial",
    "breakeven_all_in_cost_bps",
    "exposure_time_pct",
    "final_equity",
  ];
  entries.sort((left, right) => {
    const leftRank = priority.indexOf(left[0]);
    const rightRank = priority.indexOf(right[0]);
    return (
      (leftRank < 0 ? priority.length : leftRank) -
        (rightRank < 0 ? priority.length : rightRank) ||
      left[0].localeCompare(right[0])
    );
  });

  for (const [key, value] of entries) {
    const card = document.createElement("div");
    card.className = "replay-metric";
    const label = document.createElement("span");
    label.textContent = humanizeMetricKey(key);
    label.title = key;
    const displayedValue = document.createElement("strong");
    displayedValue.textContent = formatReplayMetric(key, value);
    displayedValue.title = displayedValue.textContent;
    card.append(label, displayedValue);
    container.appendChild(card);
  }
}

function renderReplayMetrics(metrics) {
  renderMetricCards(elements.replayMetrics, metrics);
}

function optimizationOutcome(payload) {
  const optimization = payload?.metadata?.optimization ?? {};
  const status = String(payload?.status ?? optimization.status ?? "unknown");
  const reason = String(
    payload?.reason ?? optimization.reason ?? "No optimizer reason was returned.",
  );
  if (status === "accepted_for_paper_trading") {
    return {
      status,
      label: "Accepted for forward-paper review",
      reason,
      level: "accepted",
      stateLevel: "ok",
    };
  }
  if (status === "rejected") {
    return {
      status,
      label: "Rejected by research gates",
      reason,
      level: "rejected",
      stateLevel: "warn",
    };
  }
  if (status === "insufficient_evidence") {
    return {
      status,
      label: "Insufficient evidence",
      reason,
      level: "insufficient",
      stateLevel: "warn",
    };
  }
  return {
    status,
    label: `Optimizer status: ${status.replace(/_/g, " ")}`,
    reason,
    level: "unknown",
    stateLevel: "warn",
  };
}

function renderReplayOutcome(payload) {
  if (replayState.lastMode !== "optimize") {
    elements.replayOutcome.hidden = true;
    elements.replayOutcome.className = "research-outcome";
    elements.replayOutcomeLabel.textContent = "";
    elements.replayOutcomeReason.textContent = "";
    return null;
  }
  const outcome = optimizationOutcome(payload);
  elements.replayOutcome.hidden = false;
  elements.replayOutcome.className = `research-outcome ${outcome.level}`;
  elements.replayOutcomeLabel.textContent = outcome.label;
  elements.replayOutcomeReason.textContent = outcome.reason;
  return outcome;
}

function renderReplayContract(payload) {
  const metadata = payload.metadata ?? {};
  const config = payload.config ?? {};
  const costs = config.costs ?? {};
  const protection = config.protected_bracket ?? {};
  const metaFilter = config.meta_filter ?? metadata.meta_filter ?? {};
  elements.replayContract.replaceChildren();
  addFact(elements.replayContract, "Mode", metadata.mode);
  addFact(elements.replayContract, "Signal vintage", metadata.signal_vintage);
  addFact(
    elements.replayContract,
    "Source generation",
    compactDigest(metadata.source_generation),
    metadata.source_generation,
  );
  addFact(elements.replayContract, "Loaded through", metadata.loaded_end);
  addFact(
    elements.replayContract,
    "Evaluation",
    metadata.evaluation_start && metadata.evaluation_end
      ? `${metadata.evaluation_start} → ${metadata.evaluation_end}`
      : null,
  );
  addFact(elements.replayContract, "Signal availability", metadata.signal_availability);
  addFact(elements.replayContract, "Execution", metadata.execution_timing);
  addFact(
    elements.replayContract,
    "Latency",
    `${costs.execution_latency_minutes ?? metadata.execution_latency_minutes ?? "?"}m`,
  );
  addFact(elements.replayContract, "Fee", formatContractBps(costs.fee_bps));
  addFact(elements.replayContract, "Slippage", formatContractBps(costs.slippage_bps));
  addFact(elements.replayContract, "Spread", formatContractBps(costs.spread_bps));
  addFact(
    elements.replayContract,
    "Trade policy",
    protection.enabled === true ? "protected static bracket" : "E0 · signal exits only",
  );
  if (protection.enabled === true) {
    addFact(
      elements.replayContract,
      "Risk unit",
      `${protection.risk_unit_volatility_multiplier ?? "?"} × causal volatility`,
    );
    addFact(
      elements.replayContract,
      "Frozen bracket",
      `${protection.stop_risk_units ?? "?"}R SL / ${
        protection.target_risk_units ?? "?"
      }R TP`,
    );
    addFact(
      elements.replayContract,
      "Barrier horizon",
      protection.timeout_target_bars === undefined
        ? null
        : `${protection.timeout_target_bars} selected-TF bars`,
    );
    addFact(
      elements.replayContract,
      "Timeout clock",
      "accepted finalized selected-TF bars",
    );
    const lockedSafetyMargin = numericContractValue(
      protection,
      "break_even_safety_margin",
    );
    addFact(
      elements.replayContract,
      "Locked break-even margin",
      lockedSafetyMargin === null
        ? null
        : `${(lockedSafetyMargin * 100).toFixed(1)} percentage points`,
    );
    addFact(
      elements.replayContract,
      "Barrier ambiguity",
      protection.same_minute_policy ?? metadata.same_minute_barrier_policy,
    );
    addFact(
      elements.replayContract,
      "Outcome visibility",
      "resolution/known-at time only",
    );
  }
  const metaMode = typeof metaFilter === "string" ? metaFilter : metaFilter.mode;
  addFact(elements.replayContract, "Meta filter", metaMode ?? "off");
  if (metaMode && metaMode !== "off") {
    addFact(
      elements.replayContract,
      "Model artifact",
      compactDigest(
        metaFilter.artifact_checksum ??
          metaFilter.artifact_digest ??
          metaFilter.model_digest,
      ) ??
        metaFilter.status ??
        "availability unreported",
      metaFilter.artifact_checksum ??
        metaFilter.artifact_digest ??
        metaFilter.model_digest,
    );
    addFact(
      elements.replayContract,
      "Frozen model threshold",
      metaFilter.decision_threshold,
    );
    addFact(
      elements.replayContract,
      "Trained through",
      metaFilter.trained_through,
    );
    addFact(
      elements.replayContract,
      "Labels mature through",
      metaFilter.label_mature_through,
    );
    addFact(
      elements.replayContract,
      "Entry threshold rule",
      metaFilter.entry_gate_rule ===
        "strictly_above_max_model_and_static_stop_threshold_with_margin"
        ? "stored P strictly > max(model threshold, static-stop estimate + locked margin)"
        : metaFilter.entry_gate_rule,
    );
    addFact(
      elements.replayContract,
      "Static break-even estimate",
      "decision-time stop/target approximation with declared non-embedded costs",
    );
  }
  addFact(elements.replayContract, "Synthetic minutes", metadata.synthetic_fill_policy);
  addFact(
    elements.replayContract,
    "Economic model",
    metadata.normalized_economic_proxy ? "normalized proxy" : "instrument-native",
  );
  addFact(
    elements.replayContract,
    "Instrument costs",
    metadata.instrument_costs_complete === true ? "complete" : "incomplete",
  );
  addFact(
    elements.replayContract,
    "Validation",
    metadata.validation_safe === true ? "as-was-live safe" : "diagnostic only",
  );

  const warning = metadata.validation_warning;
  elements.replayWarningMessage.textContent = warning ||
    "This uses current canonical history, not an immutable as-was-live record. " +
      "Historical revisions, costs, and model selection can alter results.";
  const riskParts = [];
  if (metadata.diagnostic_only !== false || metadata.validation_safe !== true) {
    riskParts.push("DIAGNOSTIC");
  }
  if (metadata.instrument_costs_complete !== true) {
    riskParts.push("COSTS INCOMPLETE");
  }
  setRiskBadge(
    elements.replayRiskBadge,
    riskParts.length ? riskParts.join(" · ") : "VALIDATION CONTRACT COMPLETE",
    riskParts.length ? "warn" : "ok",
  );

  elements.replayRunMeta.replaceChildren();
  addFact(elements.replayRunMeta, "Run", replayState.lastMode ?? "backtest");
  addFact(
    elements.replayRunMeta,
    "Completed",
    replayState.completedAt ? formatCompactTimestamp(replayState.completedAt) : null,
  );
  addFact(
    elements.replayRunMeta,
    "Client elapsed",
    replayState.durationMs === null
      ? null
      : formatDurationSeconds(replayState.durationMs / 1000),
  );
  addFact(elements.replayRunMeta, "Source rows", metadata.source_rows);
  addFact(
    elements.replayRunMeta,
    "Real source minutes",
    metadata.processed_real_source_minutes,
  );
  addFact(elements.replayRunMeta, "Evaluation minutes", metadata.evaluation_real_minutes);
  addFact(elements.replayRunMeta, "Closed target bars", metadata.target_closed_bars);
  addFact(
    elements.replayRunMeta,
    "Incomplete targets rejected",
    metadata.suppressed_incomplete_target_bars,
  );
  addFact(
    elements.replayRunMeta,
    "Continuous source gaps",
    metadata.continuous_source_gap_count,
  );
  const eventRetention = metadata.event_retention ?? {};
  const returnedSignals = eventRetention.signals;
  const returnedFills = eventRetention.fills;
  addFact(
    elements.replayRunMeta,
    "Signal evidence",
    returnedSignals
      ? `${returnedSignals.returned}/${returnedSignals.total} returned${
          returnedSignals.truncated ? " · bounded" : ""
        }`
      : null,
  );
  addFact(
    elements.replayRunMeta,
    "Fill evidence",
    returnedFills
      ? `${returnedFills.returned}/${returnedFills.total} returned${
          returnedFills.truncated ? " · bounded" : ""
        }`
      : null,
  );
  addFact(elements.replayRunMeta, "Event response cap", REPLAY_EVENT_LIMIT);
}

function appendExecutionCell(row, value, title = null) {
  const cell = document.createElement("td");
  cell.textContent = value ?? "—";
  if (title) {
    cell.title = title;
  }
  row.appendChild(cell);
}

function renderReplayFills(payload) {
  const fills = Array.isArray(payload.fills) ? payload.fills : [];
  const fillRetention = payload.metadata?.event_retention?.fills ?? null;
  const totalFills = Number(fillRetention?.total ?? fills.length);
  elements.replayFillRows.replaceChildren();
  elements.replayFillDetails.hidden = fills.length === 0;
  elements.replayFillSummary.textContent = fills.length
    ? `Execution ledger · ${fills.length.toLocaleString()}/${totalFills.toLocaleString()} returned fills · latest ${Math.min(
        RECENT_REPLAY_FILL_LIMIT,
        fills.length,
      )}`
    : "Execution ledger · no fills";
  for (const fill of fills.slice(-RECENT_REPLAY_FILL_LIMIT).reverse()) {
    const row = document.createElement("tr");
    appendExecutionCell(row, formatCompactTimestamp(fill.timestamp ?? fill.time));
    appendExecutionCell(
      row,
      `${Number(fill.from_position ?? 0).toFixed(2)} → ${Number(
        fill.to_position ?? 0,
      ).toFixed(2)}`,
      fill.signal_id ? `Signal ${fill.signal_id}` : null,
    );
    appendExecutionCell(
      row,
      `${formatPrice(fill.reference_open)} → ${formatPrice(fill.adverse_fill_price)}`,
    );
    appendExecutionCell(
      row,
      `${formatReplayMetric("fee_paid", fill.fee_paid)} fee + ` +
        `${formatReplayMetric("slippage_paid", fill.slippage_paid)} slip + ` +
        `${formatReplayMetric("spread_paid", fill.spread_paid)} spread`,
    );
    appendExecutionCell(row, formatReplayMetric("equity", fill.equity_after_cost));
    appendExecutionCell(row, fill.reason ?? "—");
    elements.replayFillRows.appendChild(row);
  }
}

function renderReplayResults(payload = replayPayloadForActiveChart()) {
  const isActive = Boolean(payload && payload === replayPayloadForActiveChart());
  elements.replayResults.hidden = !isActive;
  if (!isActive) {
    syncProtectedReplayControls();
    elements.replayPaneLegend.hidden = true;
    elements.replayProtectionLegend.hidden = true;
    elements.replayMetaLegend.hidden = true;
    elements.replayMarkerLegend.hidden = true;
    elements.replayOutcome.hidden = true;
    renderResearchParityNote();
    renderDecisionSupport();
    return;
  }

  syncProtectedReplayControls(payload);
  renderReplayContract(payload);
  renderReplayMetrics(payload.metrics ?? {});
  renderReplayFills(payload);
  const outcome = renderReplayOutcome(payload);
  const optimizationDetails = {
    status: payload.status ?? payload.metadata?.optimization?.status ?? null,
    reason: payload.reason ?? payload.metadata?.optimization?.reason ?? null,
    optimization: payload.metadata?.optimization ?? null,
    best_config: payload.best_config ?? null,
    trials: payload.trials ?? null,
    replay_config: payload.config ?? null,
  };
  const hasOptimization =
    optimizationDetails.optimization !== null ||
    optimizationDetails.best_config !== null ||
    optimizationDetails.trials !== null;
  elements.replayOptimization.hidden = !hasOptimization;
  elements.replayOptimizationSummary.textContent = outcome
    ? `${outcome.label} · technical details`
    : "Walk-forward optimization details";
  elements.replayOptimizationDetails.textContent = hasOptimization
    ? JSON.stringify(optimizationDetails, null, 2)
    : "";
  elements.replayPaneLegend.hidden = ![
    payload.equity,
    payload.drawdown,
    payload.position,
  ].some((series) => replaySeriesForLoadedChart(series).length > 0);
  elements.replayProtectionLegend.hidden = ![
    payload.risk_stop,
    payload.risk_target,
  ].some((series) =>
    replayPriceSeriesForLoadedChart(series).some(
      (point) => point.value !== undefined,
    ),
  );
  elements.replayMetaLegend.hidden =
    replaySeriesForLoadedChart(payload.meta_scores).length === 0 &&
    replayRequiredProbabilityForLoadedChart(payload).length === 0;
  elements.replayMarkerLegend.hidden =
    replayMarkersForLoadedChart(payload.markers).length === 0;
  renderResearchParityNote();
  renderDecisionSupport();
}

function validateReplayPayload(payload) {
  if (!payload || typeof payload !== "object") {
    throw new Error("Replay response is not an object.");
  }
  for (const field of ["equity", "drawdown", "position", "markers"]) {
    if (!Array.isArray(payload[field])) {
      throw new Error(`Replay response is missing ${field} array.`);
    }
  }
  for (const field of ["risk_stop", "risk_target", "meta_scores"]) {
    if (payload[field] !== undefined && !Array.isArray(payload[field])) {
      throw new Error(`Replay response has invalid optional ${field} series.`);
    }
  }
  if (!payload.metrics || typeof payload.metrics !== "object") {
    throw new Error("Replay response is missing metrics.");
  }
  if (!payload.config || typeof payload.config !== "object") {
    throw new Error("Replay response is missing config.");
  }
}

async function fetchReplayPayload(url) {
  const response = await fetch(withCacheBust(url), { cache: "no-store" });
  if (!response.ok) {
    let message = `Replay request failed: HTTP ${response.status}`;
    try {
      const errorPayload = await response.json();
      if (errorPayload.error) {
        message = errorPayload.error;
      }
    } catch {
      // Keep the HTTP status message.
    }
    throw new Error(message);
  }
  return response.json();
}

function setReplayBusy(isBusy, mode = replayState.lastMode ?? "backtest") {
  elements.replayPanel.setAttribute("aria-busy", isBusy ? "true" : "false");
  elements.replayResults.setAttribute("aria-busy", isBusy ? "true" : "false");
  elements.replayResults.classList.toggle(
    "is-stale",
    isBusy && !elements.replayResults.hidden,
  );
  if (replayElapsedTimer !== null) {
    window.clearInterval(replayElapsedTimer);
    replayElapsedTimer = null;
  }
  if (!isBusy) {
    return;
  }
  const updateElapsed = () => {
    const elapsed = replayState.startedAt === null
      ? 0
      : (performance.now() - replayState.startedAt) / 1000;
    const label = mode === "optimize" ? "Walk-forward optimization" : "Causal replay";
    const prior = elements.replayResults.hidden ? "" : " · showing previous completion";
    setReplayStatus(`${label} running · ${formatDurationSeconds(elapsed)}${prior}`, "running");
  };
  updateElapsed();
  replayElapsedTimer = window.setInterval(updateElapsed, 250);
}

async function runReplay({ optimize = false } = {}) {
  if (replayState.requestInFlight || document.visibilityState === "hidden") {
    return;
  }
  if (!isCanonicalSource(elements.sourceSelect.value)) {
    setReplayStatus("Canonical source required", "error");
    return;
  }
  if (!chartSelectionMatchesControls()) {
    setReplayStatus("Load Chart after changing the selection", "error");
    return;
  }
  if (
    optimize &&
    (elements.replayProtectedBracketInput.checked ||
      elements.replayMetaFilterModeSelect.value !== "off")
  ) {
    setReplayStatus(
      "Walk-forward optimizer is E0-only · turn protection and ML off",
      "error",
    );
    return;
  }
  const params = replayRequestParams({ useActiveChart: true });
  if (!params) {
    setReplayStatus(
      "Check replay, cost, latency, bracket, and meta-filter assumptions",
      "error",
    );
    return;
  }

  replayState.requestInFlight = true;
  replayState.startedAt = performance.now();
  replayState.startedWallClock = new Date().toISOString();
  replayState.completedAt = null;
  replayState.durationMs = null;
  updateReplayAvailability();
  setReplayBusy(true, optimize ? "optimize" : "backtest");
  const endpoint = optimize ? API_OPTIMIZE_URL : API_BACKTEST_URL;
  const requestKey = replaySelectionKey(params);
  try {
    const payload = await fetchReplayPayload(`${endpoint}?${params.toString()}`);
    validateReplayPayload(payload);
    replayState.payload = payload;
    replayState.selectionKey = requestKey;
    replayState.lastMode = optimize ? "optimize" : "backtest";
    replayState.completedAt = new Date().toISOString();
    replayState.durationMs = performance.now() - replayState.startedAt;
    renderReplayResults(payload);
    applySeriesData({ preserveVisibleRange: true, addedLeft: 0 });
    renderMetadata(historyState.metadata, historyState.candles.length);
    const timestamp = new Date().toISOString().slice(11, 19);
    const outcome = optimize ? optimizationOutcome(payload) : null;
    setReplayStatus(
      `${outcome?.label ?? "Replay complete"} · ${timestamp} UTC`,
      outcome?.stateLevel ?? "ok",
    );
    setStatus(
      optimize
        ? `${outcome.label}. ${outcome.reason}`
        : "1m causal replay loaded with fills and post-cost equity diagnostics.",
      optimize && outcome.stateLevel !== "ok" ? "warn" : "info",
    );
  } catch (error) {
    replayState.completedAt = new Date().toISOString();
    replayState.durationMs = performance.now() - replayState.startedAt;
    setReplayStatus(`Replay error: ${error.message}`, "error");
    setStatus(`Replay failed: ${error.message}`, "error");
    console.error(error);
  } finally {
    replayState.requestInFlight = false;
    setReplayBusy(false);
    updateReplayAvailability();
  }
}

function paperStatusRequestParams() {
  const params = new URLSearchParams();
  params.set("asset", elements.assetSelect.value || "BTCUSDT");
  params.set("timeframe", elements.timeframeSelect.value || "1h");
  return params;
}

function addPaperFact(label, value) {
  addFact(elements.paperFacts, label, value);
}

function paperContractFromPayload(payload) {
  const service = payload?.service ?? {};
  const stream = payload?.stream ?? {};
  const contract = service.engine_contract ?? stream.engine_contract ?? {};
  const streamConfig = stream.config ?? {};
  return {
    contract,
    costs: contract.costs ?? streamConfig.costs ?? service.costs ?? {},
    strategyDigest:
      contract.strategy_digest ?? streamConfig.strategy_digest ?? stream.strategy_digest,
    costDigest: contract.cost_digest ?? streamConfig.cost_digest ?? stream.cost_digest,
  };
}

function renderPaperContract(payload) {
  const service = payload?.service ?? {};
  const { contract, costs, strategyDigest, costDigest } =
    paperContractFromPayload(payload);
  elements.paperContract.replaceChildren();
  addFact(
    elements.paperContract,
    "Engine",
    contract.algorithm_version ?? service.service_version,
  );
  addFact(
    elements.paperContract,
    "Strategy",
    compactDigest(strategyDigest),
    strategyDigest,
  );
  addFact(elements.paperContract, "Costs", compactDigest(costDigest), costDigest);
  addFact(elements.paperContract, "Fee", formatContractBps(costs.fee_bps));
  addFact(elements.paperContract, "Slippage", formatContractBps(costs.slippage_bps));
  addFact(elements.paperContract, "Spread", formatContractBps(costs.spread_bps));
  addFact(
    elements.paperContract,
    "Latency",
    costs.execution_latency_minutes === undefined
      ? null
      : `${costs.execution_latency_minutes}m`,
  );
  addFact(
    elements.paperContract,
    "Source vintage",
    contract.source_vintage ?? service.source_vintage,
  );
  addFact(elements.paperContract, "Execution", contract.execution_timing);
  addFact(elements.paperContract, "Fill model", contract.fill_model);
  addFact(
    elements.paperContract,
    "Partial fills",
    contract.partial_fills === true ? "supported" : "unsupported",
  );
  addFact(elements.paperContract, "Spread model", contract.spread_model);
  addFact(
    elements.paperContract,
    "Market impact",
    contract.limitations?.market_impact === false
      ? "unsupported"
      : contract.market_impact_model,
  );
  addFact(
    elements.paperContract,
    "Margin",
    contract.limitations?.margin_and_liquidation === false
      ? "unsupported"
      : contract.margin_model,
  );
  addFact(
    elements.paperContract,
    "Frozen cohort",
    service.run_id && Object.keys(contract).length ? "yes" : "contract unavailable",
  );
}

function renderPaperOrderDetails(stream) {
  const pending = stream?.pending_order ?? null;
  const lastOrder = stream?.last_order ?? null;
  const lastFill = stream?.last_fill ?? null;
  elements.paperOrderFacts.replaceChildren();
  if (pending) {
    elements.paperOrderSummary.textContent =
      `Pending shadow order · target ${Number(pending.desired_position ?? 0).toFixed(2)} · ` +
      `eligible ${formatCompactTimestamp(pending.eligible_at)}`;
    elements.paperOrderDetails.open = true;
  } else if (lastFill) {
    elements.paperOrderSummary.textContent =
      `Last full shadow fill · ${formatCompactTimestamp(lastFill.fill_minute_open)}`;
  } else if (lastOrder) {
    elements.paperOrderSummary.textContent =
      `Last shadow order · ${formatCompactTimestamp(lastOrder.observed_at)}`;
  } else {
    elements.paperOrderSummary.textContent = "No shadow order activity for this stream";
  }
  addFact(
    elements.paperOrderFacts,
    "Lifecycle",
    "created → pending → full target fill",
  );
  addFact(elements.paperOrderFacts, "Venue OMS", "not modeled");
  addFact(elements.paperOrderFacts, "Partial fills", "unsupported");
  addFact(elements.paperOrderFacts, "Pending order", pending?.order_id);
  addFact(elements.paperOrderFacts, "Pending signal", pending?.signal_id);
  addFact(elements.paperOrderFacts, "Pending eligible", pending?.eligible_at);
  addFact(
    elements.paperOrderFacts,
    "Pending target",
    pending?.desired_position === undefined
      ? null
      : Number(pending.desired_position).toFixed(2),
  );
  addFact(elements.paperOrderFacts, "Last order", lastOrder?.order_id);
  addFact(
    elements.paperOrderFacts,
    "Last order position",
    lastOrder?.from_position === undefined
      ? null
      : `${Number(lastOrder.from_position).toFixed(2)} → ${Number(
          lastOrder.desired_position,
        ).toFixed(2)}`,
  );
  addFact(elements.paperOrderFacts, "Order eligible", lastOrder?.eligible_at);
  addFact(elements.paperOrderFacts, "Last fill", lastFill?.fill_minute_open);
  addFact(
    elements.paperOrderFacts,
    "Fill position",
    lastFill?.from_position === undefined
      ? null
      : `${Number(lastFill.from_position).toFixed(2)} → ${Number(
          lastFill.to_position,
        ).toFixed(2)}`,
  );
  addFact(
    elements.paperOrderFacts,
    "Reference → adverse",
    lastFill?.reference_open === undefined
      ? null
      : `${formatPrice(lastFill.reference_open)} → ${formatPrice(
          lastFill.adverse_fill_price,
        )}`,
  );
  addFact(
    elements.paperOrderFacts,
    "Fill fee",
    lastFill?.fee_paid === undefined
      ? null
      : formatReplayMetric("fee_paid", lastFill.fee_paid),
  );
  addFact(
    elements.paperOrderFacts,
    "Fill slippage",
    lastFill?.slippage_paid === undefined
      ? null
      : formatReplayMetric("slippage_paid", lastFill.slippage_paid),
  );
  addFact(
    elements.paperOrderFacts,
    "Fill spread",
    lastFill?.spread_paid === undefined
      ? null
      : formatReplayMetric("spread_paid", lastFill.spread_paid),
  );
  addFact(
    elements.paperOrderFacts,
    "Equity after cost",
    lastFill?.equity_after_cost === undefined
      ? null
      : formatReplayMetric("equity", lastFill.equity_after_cost),
  );
}

function nearlyEqual(left, right, tolerance = 1e-9) {
  return Number.isFinite(left) && Number.isFinite(right)
    ? Math.abs(left - right) <= tolerance
    : left === null && right === null;
}

function renderResearchParityNote() {
  const replay = replayPayloadForActiveChart();
  const paper = latestPaperPayload;
  const paperSelection = paper?.selection ?? {};
  const replayMetadata = replay?.metadata ?? {};
  const sameSelection = Boolean(
    replay &&
      paper &&
      paperSelection.asset === replayMetadata.asset &&
      paperSelection.timeframe === replayMetadata.timeframe,
  );
  elements.researchParityNote.hidden = !sameSelection;
  if (!sameSelection) {
    elements.researchParityNote.textContent = "";
    elements.researchParityNote.className = "research-parity-note";
    return;
  }

  const paperContract = paperContractFromPayload(paper);
  const replayConfig = replay.config ?? {};
  const replayCosts = replayConfig.costs ?? {};
  const replayStrategyDigest = replayConfig.strategy_digest;
  const strategyKnown = Boolean(
    paperContract.strategyDigest && replayStrategyDigest,
  );
  const strategyMatch = strategyKnown &&
    paperContract.strategyDigest === replayStrategyDigest;
  const costFields = [
    "fee_bps",
    "slippage_bps",
    "spread_bps",
    "execution_latency_minutes",
  ];
  const costDifferences = costFields.filter((field) => {
    const paperValue = numericContractValue(paperContract.costs, field);
    const replayValue = numericContractValue(replayCosts, field);
    return !nearlyEqual(paperValue, replayValue);
  });
  const costsKnown = costFields.every(
    (field) =>
      numericContractValue(paperContract.costs, field) !== null &&
      numericContractValue(replayCosts, field) !== null,
  );
  const costsMatch = costsKnown && costDifferences.length === 0;
  const paperTiming = paperContract.contract.execution_timing;
  const replayTiming = replayMetadata.execution_timing;
  const timingKnown = Boolean(paperTiming && replayTiming);
  const timingMatch = timingKnown && paperTiming === replayTiming;
  const strategyText = strategyKnown
    ? `strategy ${strategyMatch ? "match" : "MISMATCH"}`
    : "strategy parity unavailable";
  const costText = costsKnown
    ? costsMatch
      ? "frozen costs match"
      : `cost MISMATCH (${costDifferences.join(", ")})`
    : "cost parity unavailable";
  const timingText = timingKnown
    ? `execution timing ${timingMatch ? "matches" : "MISMATCH"}`
    : "execution timing unavailable";
  const paperVintage =
    paperContract.contract.source_vintage ?? paper.service?.source_vintage ?? "unknown";
  const replayVintage = replayMetadata.signal_vintage ?? "unknown";
  elements.researchParityNote.textContent =
    `Independent shadow parity · ${strategyText} · ${costText} · ${timingText} · ` +
    `vintage differs by design (${replayVintage} vs ${paperVintage}). ` +
    "This comparison is not a combined portfolio.";
  const mismatch =
    !strategyMatch || !costsMatch || (timingKnown && !timingMatch);
  elements.researchParityNote.className =
    `research-parity-note ${mismatch ? "warn" : "ok"}`;
}

function renderForwardPaperStatus(payload) {
  const process = payload?.process ?? {};
  const service = payload?.service ?? {};
  const feed = payload?.feed ?? null;
  const stream = payload?.stream ?? null;
  const quality = String(feed?.quality ?? "unavailable").toLowerCase();
  const provider = String(feed?.provider ?? "no feed");
  const feedStatus = String(feed?.status ?? "unavailable").toLowerCase();
  const feedError = Boolean(feed?.error) ||
    ["error", "failed", "fetch_error", "unavailable"].includes(feedStatus);
  latestPaperPayload = payload;
  renderDecisionSupport();

  if (!chartHasLiveOverlayMetadata) {
    presentSourceQuality({
      provider,
      quality,
      status: process.running ? service?.status : "unavailable",
      expectedDelaySeconds: feed?.expected_delay_seconds,
    });
    const paperSourceTimestamp = feed?.last_source_timestamp;
    if (paperSourceTimestamp) {
      elements.lastUpdateValue.textContent = formatCompactTimestamp(paperSourceTimestamp);
    }
  }

  elements.paperSection.classList.toggle("feed-delayed", quality === "delayed");
  elements.paperSection.classList.toggle(
    "feed-error",
    !process.running || feedError,
  );
  elements.paperFeedBadge.textContent = process.running
    ? `${provider} · ${quality}${feedError ? ` · ${feedStatus}` : ""}`
    : "Service not running";
  const observeOnly =
    String(service?.research_status ?? "").includes("observe_only") ||
    service?.real_order_routing === false;
  setRiskBadge(
    elements.paperRiskBadge,
    !process.running
      ? "SERVICE OFF · ROUTING OFF"
      : `${observeOnly ? "OBSERVE ONLY" : "SHADOW ACTIVE"} · ` +
          `${service?.real_order_routing === true ? "ROUTING ON" : "ROUTING OFF"}` +
          `${feedError ? " · FEED ERROR" : ""}`,
    !process.running || feedError ? "error" : "warn",
  );
  elements.paperFacts.replaceChildren();
  addPaperFact("Process", process.running ? `running (${process.pid})` : process.reason);
  addPaperFact("Provider", provider);
  addPaperFact("Feed grade", quality);
  addPaperFact("Feed status", feedStatus);
  addPaperFact("Expected delay", feed?.expected_delay_seconds !== undefined
    ? `${feed.expected_delay_seconds}s`
    : null);
  addPaperFact(
    "Measured lag",
    formatDurationSeconds(feed?.measured_lag_seconds),
  );
  addPaperFact("Consecutive failures", feed?.consecutive_failures);
  addPaperFact("Feed error", feed?.error);
  addPaperFact("Latest source bar", feed?.last_source_timestamp);
  addPaperFact("Observed", feed?.last_observed_at);
  addPaperFact("Observation age", ageFromTimestamp(feed?.last_observed_at));
  addPaperFact("Cohort", service?.research_status);
  addPaperFact("Source vintage", service?.source_vintage);
  addPaperFact("Run", compactDigest(service?.run_id));
  addPaperFact("Manifest", compactDigest(service?.manifest_hash));
  addPaperFact("Journal", service?.journal_integrity);
  addPaperFact("Heartbeat", service?.heartbeat_at);
  addPaperFact("Heartbeat age", ageFromTimestamp(service?.heartbeat_at));
  addPaperFact(
    "Poll duration",
    formatDurationSeconds(service?.last_poll_duration_seconds),
  );
  addPaperFact(
    "Poll interval",
    formatDurationSeconds(service?.poll_interval_seconds),
  );
  addPaperFact("Last poll", service?.last_poll_completed_at);
  addPaperFact("Last signal", stream?.last_signal?.observed_at);
  addPaperFact(
    "Signal target",
    stream?.last_signal?.desired_position !== undefined
      ? Number(stream.last_signal.desired_position).toFixed(2)
      : null,
  );
  addPaperFact("Signal reason", stream?.last_signal?.reason);
  addPaperFact("Last fill", stream?.last_fill?.fill_minute_open);

  renderPaperContract(payload);
  renderPaperOrderDetails(stream);
  renderMetricCards(elements.paperMetrics, stream?.metrics ?? {});
  renderResearchParityNote();
  if (!process.running) {
    elements.paperSummary.textContent =
      service?.message ??
      "Start the background journal with python update_data.py --live-start.";
    setPaperStatus("Not running", "error");
    return;
  }
  if (!feed) {
    elements.paperSummary.textContent =
      "The service is running, but this asset has no successful source observation yet.";
    setPaperStatus("Waiting for source", "running");
    return;
  }
  if (feedError) {
    elements.paperSummary.textContent =
      `The independent shadow stream is paused on feed status ${feedStatus}: ` +
      `${feed?.error ?? "no successful observation is currently available"}.`;
  } else if (quality === "delayed") {
    elements.paperSummary.textContent =
      "This independent forward-only shadow stream is journaled from delayed data. " +
      "It is not execution-quality and is not part of a combined portfolio.";
  } else {
    elements.paperSummary.textContent =
      "Finalized first-seen bars feed this independent append-only shadow stream. " +
      "It is not a venue OMS and no real orders can be sent.";
  }
  const gate = stream?.evidence_status ?? service?.research_status ?? "collecting";
  const heartbeat = String(service?.heartbeat_at ?? "").replace("T", " ");
  setPaperStatus(
    `${gate}${heartbeat ? ` · heartbeat ${heartbeat}` : ""}`,
    feedError ? "error" : quality === "delayed" || observeOnly ? "warn" : "ok",
  );
}

async function refreshForwardPaperStatus() {
  if (paperRequestInFlight || document.visibilityState === "hidden") {
    return;
  }
  paperRequestInFlight = true;
  elements.paperRefreshButton.disabled = true;
  elements.paperRefreshButton.textContent = "Refreshing…";
  elements.paperSection.setAttribute("aria-busy", "true");
  try {
    const params = paperStatusRequestParams();
    const response = await fetch(
      withCacheBust(`${API_PAPER_STATUS_URL}?${params.toString()}`),
      { cache: "no-store" },
    );
    if (!response.ok) {
      throw new Error(`Paper status HTTP ${response.status}`);
    }
    renderForwardPaperStatus(await response.json());
  } catch (error) {
    latestPaperPayload = null;
    renderDecisionSupport();
    elements.paperFeedBadge.textContent = "Status unavailable";
    if (!chartHasLiveOverlayMetadata) {
      setSourceQualityBadge("Feed status unavailable", "error");
    }
    elements.paperSummary.textContent = error.message;
    elements.paperFacts.replaceChildren();
    elements.paperContract.replaceChildren();
    elements.paperOrderFacts.replaceChildren();
    elements.paperOrderSummary.textContent = "Paper status unavailable";
    elements.paperMetrics.replaceChildren();
    elements.paperSection.classList.add("feed-error");
    setRiskBadge(elements.paperRiskBadge, "STATUS ERROR · ROUTING OFF", "error");
    setPaperStatus("Status error", "error");
    renderResearchParityNote();
    console.error(error);
  } finally {
    paperRequestInFlight = false;
    elements.paperRefreshButton.disabled = false;
    elements.paperRefreshButton.textContent = "Refresh status";
    elements.paperSection.setAttribute("aria-busy", "false");
  }
}

function startPaperRefreshTimer() {
  if (paperRefreshTimer !== null) {
    window.clearInterval(paperRefreshTimer);
  }
  paperRefreshTimer = window.setInterval(
    refreshForwardPaperStatus,
    PAPER_REFRESH_INTERVAL_MS,
  );
}

function withCacheBust(url) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}t=${Date.now()}`;
}

function renderDiagnosticVintage(metadata) {
  const liveMeta = metadata.online_signal ?? {};
  const prototypeRegime = historyState.overlays.online_regime ?? {};
  const trend = historyState.overlays.volatility_scaled_trend ?? {};
  const mtfContext = historyState.overlays.cross_timeframe_context ?? {};
  const priorStructure = historyState.overlays.prior_structure ?? {};
  const comparableVolatility = historyState.overlays.comparable_volatility ?? {};
  const participation = historyState.overlays.phase_adjusted_participation ?? {};
  const isDiagnostic =
    liveMeta.diagnostic_only === true ||
    prototypeRegime.diagnostic_only === true ||
    trend.diagnostic_only === true ||
    mtfContext.diagnostic_only === true ||
    priorStructure.diagnostic_only === true ||
    comparableVolatility.diagnostic_only === true ||
    participation.diagnostic_only === true;
  const isPrototype =
    liveMeta.trained_model === false || prototypeRegime.trained_model === false;
  const isValidationUnsafe = liveMeta.validation_safe === false;
  const signalVintage =
    liveMeta.signal_vintage ??
    prototypeRegime.signal_vintage ??
    trend.signal_vintage ??
    (liveMeta.mode === "full_origin_stream_replay"
      ? "current_canonical_replay"
      : null);
  const shouldShow =
    isDiagnostic || isPrototype || isValidationUnsafe || Boolean(signalVintage);

  elements.diagnosticVintage.hidden = !shouldShow;
  if (!shouldShow) {
    elements.diagnosticVintage.removeAttribute("title");
    return;
  }

  elements.diagnosticVintageLabel.textContent =
    signalVintage === "current_canonical_replay"
      ? "Diagnostic · current replay"
      : "Diagnostic signals";
  const notes = [];
  if (isPrototype) {
    notes.push(
      "Prototype regime values are untrained weights, not calibrated probabilities or confidence.",
    );
  }
  if (liveMeta.validation_warning) {
    notes.push(String(liveMeta.validation_warning));
  } else if (isValidationUnsafe || signalVintage === "current_canonical_replay") {
    notes.push(
      "Historical revisions can rewrite prior signals; this is not as-was-live backtest evidence.",
    );
  }
  if (notes.length === 0) {
    notes.push(
      "Use these causal, next-action values as visual diagnostics only; they are not calibrated trade gates.",
    );
  }
  const message = notes.join(" ");
  elements.diagnosticVintageMessage.textContent = message;
  elements.diagnosticVintage.title =
    `${signalVintage ? `Signal vintage: ${signalVintage}. ` : ""}${message}`;
}

function renderLiveOverlayMetadata(metadata, loadedEnd) {
  const liveOverlay = metadata.live_overlay;
  chartHasLiveOverlayMetadata = Boolean(
    liveOverlay && typeof liveOverlay === "object" && Object.keys(liveOverlay).length,
  );
  const latestSourceTimestamp =
    liveOverlay?.latest_source_timestamp ??
    liveOverlay?.source_timestamp ??
    (loadedEnd ? loadedEnd : null);
  elements.lastUpdateValue.textContent = formatCompactTimestamp(latestSourceTimestamp);

  if (!chartHasLiveOverlayMetadata) {
    const provider = metadata.provider ?? metadata.source ?? "Canonical";
    setSourceQualityBadge(`${normalizedProviderLabel(provider)} · history`, "checking");
    return false;
  }

  const quality = String(liveOverlay.quality ?? "unknown").toLowerCase();
  const status = String(liveOverlay.status ?? "unknown").toLowerCase();
  const provider = liveOverlay.provider ?? metadata.provider ?? metadata.source;
  const expectedDelaySeconds = liveOverlay.expected_delay_seconds;
  const freshness = String(liveOverlay.freshness ?? "").toLowerCase();
  const serviceStopped = liveOverlay.service_running === false;
  presentSourceQuality({
    provider,
    quality,
    status: serviceStopped
      ? "stopped"
      : freshness === "stale"
        ? "stale"
        : status,
    expectedDelaySeconds,
  });

  const observedAt = liveOverlay.latest_observed_at ?? liveOverlay.observed_at;
  const rowCount = Number(
    liveOverlay.live_rows_appended ??
      liveOverlay.target_rows_built ??
      liveOverlay.source_rows_loaded ??
      liveOverlay.overlay_row_count ??
      0,
  );
  const explicitlyStale =
    liveOverlay.stale === true ||
    liveOverlay.is_stale === true ||
    freshness === "stale" ||
    String(liveOverlay.staleness ?? "").toLowerCase() === "stale";
  const observedTime = Date.parse(String(observedAt ?? ""));
  const interval = timeframeSeconds(metadata.timeframe) ?? 60;
  const expectedDelay = Number(expectedDelaySeconds ?? 0);
  const maximumAgeSeconds = Math.max(interval * 2.5, expectedDelay + 120, 180);
  const computedStale =
    Number.isFinite(observedTime) &&
    Date.now() - observedTime > maximumAgeSeconds * 1000;
  const stale = explicitlyStale || computedStale;
  const observedText = observedAt ? formatCompactTimestamp(observedAt) : "waiting";
  const overlayName = quality === "delayed" ? "Delayed overlay" : "Live overlay";

  if (serviceStopped || ["error", "failed", "unavailable"].includes(status)) {
    setLiveState(`Overlay unavailable · ${observedText}`, "error");
  } else if (quality === "delayed") {
    setLiveState(`${overlayName} · ${rowCount} bars · ${observedText}`, "warn");
  } else if (stale) {
    setLiveState(`${overlayName} stale · ${rowCount} bars · ${observedText}`, "warn");
  } else if (rowCount > 0 || status === "ok") {
    setLiveState(`${overlayName} · ${rowCount} bars · ${observedText}`, "info");
  } else {
    setLiveState(`Live overlay waiting · ${observedText}`, "warn");
  }
  elements.liveState.title = [
    provider ? `Provider: ${provider}` : null,
    quality ? `Quality: ${quality}` : null,
    expectedDelay > 0 ? `Expected delay: ${expectedDelay}s` : null,
    liveOverlay.generation ?? liveOverlay.source_generation
      ? `Source generation: ${liveOverlay.generation ?? liveOverlay.source_generation}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return true;
}

function mtfContextLabel(contextClass) {
  return {
    trend_aligned: "Trend aligned",
    countertrend_conflict: "Countertrend conflict",
    range_context: "Mixed / range context",
    transition_risk: "Transition caution",
    insufficient_or_stale: "Incomplete / stale",
  }[contextClass] ?? "Context unavailable";
}

function appendMtfCell(row, text, className = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (className) {
    cell.className = className;
  }
  row.appendChild(cell);
}

function setDecisionCard(card, stateElement, detailElement, assessment) {
  if (!card || !stateElement || !detailElement) {
    return;
  }
  const state = String(assessment?.state ?? "Unavailable");
  const detail = String(assessment?.detail ?? "No evidence was returned.");
  card.dataset.tone = String(assessment?.tone ?? "waiting");
  stateElement.textContent = state;
  stateElement.title = state;
  detailElement.textContent = detail;
  detailElement.title = detail;
}

function decisionTimestampSeconds(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return numeric > 10_000_000_000 ? numeric / 1000 : numeric;
  }
  const parsed = Date.parse(String(value));
  return Number.isFinite(parsed) ? parsed / 1000 : null;
}

function decisionFeedAssessment(metadata) {
  const liveOverlay = metadata?.live_overlay;
  const interval = timeframeSeconds(metadata?.timeframe) ?? 60;
  const sourceTimestamp =
    liveOverlay?.latest_source_timestamp ??
    liveOverlay?.source_timestamp ??
    metadata?.online_signal?.computed_source_through ??
    lastCandleTime();
  const sourceSeconds = decisionTimestampSeconds(sourceTimestamp);
  const ageSeconds = sourceSeconds === null
    ? null
    : Math.max(0, Date.now() / 1000 - sourceSeconds);
  const ageText = ageSeconds === null
    ? "age unavailable"
    : `${formatDurationSeconds(ageSeconds)} source age`;
  const provider = normalizedProviderLabel(
    liveOverlay?.provider ?? metadata?.provider ?? metadata?.source,
  );

  if (!liveOverlay || typeof liveOverlay !== "object") {
    const replayVintage = metadata?.online_signal?.signal_vintage;
    return {
      state: replayVintage === "current_canonical_replay"
        ? "Historical replay"
        : "Historical source",
      detail: `${provider} · ${ageText} · not an as-was-live feed`,
      tone: "neutral",
      blocked: false,
      delayed: false,
    };
  }

  if (elements.liveRefreshToggle && !elements.liveRefreshToggle.checked) {
    return {
      state: "Refresh paused",
      detail: `${provider} · ${ageText} · resume polling before current review`,
      tone: "caution",
      blocked: false,
      delayed: false,
    };
  }

  const status = String(liveOverlay.status ?? "unknown").toLowerCase();
  const quality = String(liveOverlay.quality ?? "unknown").toLowerCase();
  const freshness = String(liveOverlay.freshness ?? "").toLowerCase();
  const expectedDelay = Number(liveOverlay.expected_delay_seconds ?? 0);
  const maximumAge = Math.max(interval * 2.5, expectedDelay + 120, 180);
  const unavailable =
    liveOverlay.service_running === false ||
    ["error", "failed", "unavailable", "stopped"].includes(status);
  const stale =
    liveOverlay.stale === true ||
    liveOverlay.is_stale === true ||
    freshness === "stale" ||
    (ageSeconds !== null && ageSeconds > maximumAge);
  if (unavailable) {
    return {
      state: "Feed unavailable",
      detail: `${provider} · ${status} · do not use for current decisions`,
      tone: "blocked",
      blocked: true,
      delayed: false,
    };
  }
  if (stale) {
    return {
      state: "Stale feed",
      detail: `${provider} · ${ageText} · wait for a current finalized bar`,
      tone: "blocked",
      blocked: true,
      delayed: quality === "delayed",
    };
  }
  if (quality === "delayed") {
    return {
      state: "Delayed feed",
      detail: `${provider} · ${ageText} · research timing only`,
      tone: "caution",
      blocked: false,
      delayed: true,
    };
  }
  return {
    state: quality === "live" ? "Live feed current" : "Feed observed",
    detail: `${provider} · ${ageText} · finalized bars only`,
    tone: quality === "live" ? "ready" : "neutral",
    blocked: false,
    delayed: false,
  };
}

function diagnosticDirectionAgreement() {
  const evidence = [];
  const cusum = historyState.overlays.cusum_trend?.last ?? {};
  const cusumRegime = Number(cusum.regime);
  if (cusumRegime === 1 || cusumRegime === -1) {
    evidence.push({ name: "CUSUM", direction: cusumRegime });
  }

  const trend = historyState.overlays.volatility_scaled_trend?.last ?? {};
  const trendState = Number(trend.state_code);
  const trendScore = Number(trend.score);
  if (trendState === 1 || trendState === -1) {
    evidence.push({ name: "Trend", direction: trendState });
  } else if (Number.isFinite(trendScore) && Math.abs(trendScore) >= 0.08) {
    evidence.push({ name: "Trend", direction: trendScore > 0 ? 1 : -1 });
  }

  const mtf = historyState.overlays.cross_timeframe_context?.latest ?? {};
  const mtfBias = String(mtf.direction_bias ?? "").toLowerCase();
  if (mtfBias === "bullish" || mtfBias === "bearish") {
    evidence.push({ name: "Cross-TF", direction: mtfBias === "bullish" ? 1 : -1 });
  }

  const positive = evidence.filter((item) => item.direction > 0);
  const negative = evidence.filter((item) => item.direction < 0);
  if (positive.length && negative.length) {
    return {
      state: "Directional conflict",
      detail: `${positive.map((item) => item.name).join(" + ")} lean higher; ` +
        `${negative.map((item) => item.name).join(" + ")} lean lower`,
      tone: "conflict",
      conflict: true,
      sufficient: true,
    };
  }
  if (evidence.length >= 2) {
    const direction = positive.length ? "higher" : "lower";
    return {
      state: `${evidence.length}/${evidence.length} aligned`,
      detail: `${evidence.map((item) => item.name).join(" + ")} lean ${direction}; ` +
        "this is diagnostic agreement, not an entry",
      tone: "aligned",
      conflict: false,
      sufficient: true,
    };
  }
  if (evidence.length === 1) {
    return {
      state: "Single direction source",
      detail: `${evidence[0].name} leans ${evidence[0].direction > 0 ? "higher" : "lower"}; ` +
        "confirmation is insufficient",
      tone: "caution",
      conflict: false,
      sufficient: false,
    };
  }
  return {
    state: "Mixed / no edge",
    detail: "No directional agreement is available from the selected diagnostics.",
    tone: "caution",
    conflict: false,
    sufficient: false,
  };
}

function decisionContextAssessment() {
  const structure = contextLast(historyState.overlays.prior_structure);
  const volatility = contextLast(historyState.overlays.comparable_volatility);
  const participation = contextLast(
    historyState.overlays.phase_adjusted_participation,
  );
  const structureState = humanizeContextState(
    firstContextValue(structure, ["state", "status", "structure_state"]),
    "structure unavailable",
  );
  const volatilityRank = numericContextValue(volatility, [
    "volatility_percentile",
    "rs_percentile",
    "percentile",
  ]);
  const rvol = numericContextValue(participation, [
    "rvol",
    "relative_volume",
    "phase_adjusted_rvol",
  ]);
  const qualities = [structure, volatility, participation]
    .filter((item) => Object.keys(item).length)
    .map((item) => String(item.quality ?? item.status ?? "unknown").toLowerCase());
  const immature = qualities.some((quality) =>
    ["warming", "insufficient", "unavailable", "degraded", "partial"].some(
      (token) => quality.includes(token),
    ),
  );
  const riskParts = [structureState];
  if (volatilityRank !== null) {
    riskParts.push(`RS rank ${formatFractionPercent(volatilityRank)}`);
  }
  if (rvol !== null) {
    riskParts.push(`phase RVOL ${rvol.toFixed(2)}×`);
  }
  const unusuallyQuiet = rvol !== null && rvol < 0.5;
  const extremeVolatility = volatilityRank !== null && volatilityRank >= 0.9;
  return {
    state: immature
      ? "Context warming"
      : unusuallyQuiet
        ? "Thin participation"
        : extremeVolatility
          ? "Elevated range risk"
          : "Context available",
    detail: riskParts.join(" · ") || "Context diagnostics are unavailable.",
    tone: immature || unusuallyQuiet || extremeVolatility ? "caution" : "neutral",
    immature,
    unusuallyQuiet,
    extremeVolatility,
  };
}

function decisionReplayAssessment() {
  const payload = replayPayloadForActiveChart();
  if (!payload) {
    return {
      state: "Historical: not run",
      detail: "Next allowed research action: run replay for this exact selection.",
      tone: "waiting",
    };
  }
  const metrics = payload.metrics ?? {};
  const status = String(
    payload.status ?? payload.metadata?.optimization?.status ?? "snapshot_available",
  );
  const returnValue = Number(metrics.total_return_pct);
  const drawdown = Number(metrics.max_drawdown_pct);
  const fillCount = Number(metrics.fill_count);
  const metricParts = [];
  if (Number.isFinite(returnValue)) {
    metricParts.push(`${returnValue.toFixed(2)}% net`);
  }
  if (Number.isFinite(drawdown)) {
    metricParts.push(`${drawdown.toFixed(2)}% max DD`);
  }
  if (Number.isFinite(fillCount)) {
    metricParts.push(`${Math.round(fillCount)} fills`);
  }
  if (status === "rejected" || status === "insufficient_evidence") {
    return {
      state: status === "rejected"
        ? "Historical: rejected"
        : "Historical: insufficient",
      detail: metricParts.join(" · ") || "Research gates did not accept this run.",
      tone: status === "rejected" ? "conflict" : "caution",
    };
  }
  if (status === "accepted_for_paper_trading") {
    return {
      state: "Historical: gate passed",
      detail: `${metricParts.join(" · ")} · forward paper evidence still required`,
      tone: "caution",
    };
  }
  return {
    state: "Historical: snapshot",
    detail: `${metricParts.join(" · ") || "Metrics available"} · diagnostic vintage`,
    tone: "neutral",
  };
}

function decisionPaperAssessment() {
  const process = latestPaperPayload?.process ?? {};
  const service = latestPaperPayload?.service ?? {};
  const feed = latestPaperPayload?.feed ?? null;
  const stream = latestPaperPayload?.stream ?? null;
  if (!process.running) {
    return {
      state: "Paper: service off",
      detail: "No independent forward evidence is being collected for this view.",
      tone: "caution",
    };
  }
  const metrics = stream?.metrics ?? {};
  const minutes = Number(
    metrics.forward_minutes_marked ?? metrics.evaluated_real_minutes,
  );
  const fills = Number(metrics.fill_count);
  const evidence = String(stream?.evidence_status ?? "collecting").replace(/_/g, " ");
  const feedError = Boolean(feed?.error) ||
    ["error", "failed", "unavailable"].includes(
      String(feed?.status ?? "").toLowerCase(),
    );
  const facts = [
    Number.isFinite(minutes) ? `${Math.round(minutes)} forward minutes` : null,
    Number.isFinite(fills) ? `${Math.round(fills)} fills` : null,
    evidence,
  ].filter(Boolean);
  return {
    state: feedError ? "Paper: feed blocked" : "Paper: observe only",
    detail: facts.join(" · "),
    tone: feedError ? "blocked" : "neutral",
  };
}

function renderDecisionSupport() {
  const metadata = historyState.metadata ?? {};
  const feed = decisionFeedAssessment(metadata);
  const agreement = diagnosticDirectionAgreement();
  const context = decisionContextAssessment();
  const replay = decisionReplayAssessment();
  const paper = decisionPaperAssessment();
  const policy = metadata.decision_support ?? metadata.trading_policy ?? {};
  const frozenPolicy = policy.policy_frozen === true;
  const mtfClass = String(
    historyState.overlays.cross_timeframe_context?.latest?.context_class ?? "",
  );
  const trend = historyState.overlays.volatility_scaled_trend?.last ?? {};
  const trendStatus = String(trend.status ?? "").toLowerCase();
  const pathQuality = Number(trend.path_quality);
  const blockers = [];
  if (!frozenPolicy) {
    blockers.push("no frozen strategy policy");
  }
  if (feed.blocked) {
    blockers.push("feed not current");
  }
  if (agreement.conflict) {
    blockers.push("directional conflict");
  } else if (!agreement.sufficient) {
    blockers.push("directional evidence insufficient");
  }
  if (["countertrend_conflict", "transition_risk", "insufficient_or_stale"].includes(mtfClass)) {
    blockers.push(mtfContextLabel(mtfClass).toLowerCase());
  }
  if (
    trendStatus.includes("mixed") ||
    trendStatus.includes("chop") ||
    (Number.isFinite(pathQuality) && pathQuality < 0.15)
  ) {
    blockers.push("trend path quality weak");
  }
  if (context.immature) {
    blockers.push("context warming");
  }
  const hardBlock = feed.blocked || agreement.conflict ||
    ["countertrend_conflict", "insufficient_or_stale"].includes(mtfClass);
  const readiness = frozenPolicy && blockers.length === 0
    ? {
        state: "Policy review ready",
        detail: "Frozen policy inputs are present; execution controls still apply.",
        tone: "ready",
      }
    : {
        state: hardBlock ? "No trade · blocked" : "No trade · insufficient",
        detail: blockers.slice(0, 3).join(" · ") ||
          "Evidence has not passed a frozen decision policy.",
        tone: hardBlock ? "blocked" : "caution",
      };

  const realRouting = latestPaperPayload?.service?.real_order_routing === true;
  const execution = realRouting
    ? {
        state: "Routing configured",
        detail: "No order ticket exists here; verify OMS, limits and reconciliation externally.",
        tone: "caution",
      }
    : {
        state: "Routing off",
        detail: frozenPolicy
          ? "Research only. Next allowed: forward paper before execution review."
          : "Research only. Next allowed: replay or forward-paper observation.",
        tone: "neutral",
      };

  const paperRunning = latestPaperPayload?.process?.running === true;
  const chartLive = String(metadata.live_overlay?.quality ?? "").toLowerCase() === "live";
  if (elements.decisionModeBadge) {
    elements.decisionModeBadge.textContent = paperRunning
      ? `${chartLive ? "LIVE DATA · " : ""}PAPER OBSERVE`
      : replayPayloadForActiveChart()
        ? "SIMULATION"
        : "DIAGNOSTIC";
  }
  setDecisionCard(
    elements.decisionCardFeed,
    elements.decisionFeedState,
    elements.decisionFeedDetail,
    feed,
  );
  setDecisionCard(
    elements.decisionCardReadiness,
    elements.decisionReadinessState,
    elements.decisionReadinessDetail,
    readiness,
  );
  setDecisionCard(
    elements.decisionCardAgreement,
    elements.decisionAgreementState,
    elements.decisionAgreementDetail,
    agreement,
  );
  setDecisionCard(
    elements.decisionCardContext,
    elements.decisionContextState,
    elements.decisionContextDetail,
    context,
  );
  setDecisionCard(
    elements.decisionCardExecution,
    elements.decisionExecutionState,
    elements.decisionExecutionDetail,
    execution,
  );
  setDecisionCard(
    elements.decisionCardReplay,
    elements.decisionReplayState,
    elements.decisionReplayDetail,
    replay,
  );
  setDecisionCard(
    elements.decisionCardPaper,
    elements.decisionPaperState,
    elements.decisionPaperDetail,
    paper,
  );
}

function renderMtfContext(overlay) {
  const available = overlay && typeof overlay === "object";
  elements.mtfContextMatrix.hidden = !available;
  elements.mtfContextDetails.hidden = !available;
  elements.mtfContextRows.replaceChildren();
  if (!available) {
    elements.mtfContextReason.textContent = "";
    return;
  }

  const latest = overlay.latest ?? {};
  const label = mtfContextLabel(latest.context_class);
  const bias = String(latest.direction_bias ?? "mixed");
  elements.mtfContextBadge.textContent =
    overlay.status === "no_higher_timeframe"
      ? "No higher canonical TF"
      : `${label} · ${bias}`;
  elements.mtfContextBadge.dataset.state = String(
    latest.context_class ?? overlay.status ?? "unavailable",
  );

  for (const source of overlay.sources ?? []) {
    const state = source.latest;
    const row = document.createElement("tr");
    row.dataset.direction = String(state?.direction ?? 0);
    row.dataset.status = String(state?.status ?? "unavailable");
    appendMtfCell(
      row,
      `${String(source.role ?? "context").toUpperCase()} · ${source.timeframe}`,
      "mtf-role",
    );
    if (!state) {
      appendMtfCell(row, "Warming / unavailable", "mtf-muted");
      appendMtfCell(row, "—", "mtf-muted");
      appendMtfCell(row, "—", "mtf-muted");
      appendMtfCell(row, "—", "mtf-muted");
      appendMtfCell(row, "—", "mtf-muted");
      elements.mtfContextRows.appendChild(row);
      continue;
    }
    const score = Number(state.trend_score);
    const scoreText = Number.isFinite(score)
      ? `${score >= 0 ? "+" : ""}${score.toFixed(2)}`
      : "—";
    appendMtfCell(row, `${state.trend_state} · ${scoreText}`, "mtf-trend");
    appendMtfCell(
      row,
      formatPercent(Number(state.path_quality) * 100, 0),
      "mtf-quality",
    );
    appendMtfCell(
      row,
      `${state.volatility_state} · ${Number(state.fast_slow_vol_ratio).toFixed(2)}×`,
      "mtf-volatility",
    );
    appendMtfCell(
      row,
      `${state.regime_label} · ${formatPercent(
        Number(state.prototype_top_weight) * 100,
        0,
      )} prototype weight · ${formatPercent(
        Number(state.filtered_switch_probability) * 100,
        0,
      )} filtered switch · ${formatPercent(Number(state.change_risk) * 100, 0)} caution`,
      "mtf-regime",
    );
    const availableAt = normalizedReplayTime(state.available_at);
    const availability = Number.isFinite(availableAt) ? formatTime(availableAt) : "—";
    const age = formatDurationSeconds(Number(state.age_seconds));
    appendMtfCell(
      row,
      `${availability} · ${age} old${state.status === "stale" ? " · STALE" : ""}`,
      "mtf-availability",
    );
    elements.mtfContextRows.appendChild(row);
  }

  elements.mtfContextReason.textContent =
    overlay.reason ?? latest.reason ?? overlay.limitations ?? "";
}

function contextLast(overlay) {
  for (const candidate of [overlay?.last, overlay?.latest, overlay?.current]) {
    if (candidate && typeof candidate === "object") {
      return candidate;
    }
  }
  return {};
}

function firstContextValue(container, names) {
  for (const name of names) {
    const value = container?.[name];
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return null;
}

function numericContextValue(container, names) {
  const rawValue = firstContextValue(container, names);
  if (rawValue === null) {
    return null;
  }
  const value = Number(rawValue);
  return Number.isFinite(value) ? value : null;
}

function formatFractionPercent(value, precision = 0) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "—";
  }
  return formatPercent(numeric * 100, precision);
}

function humanizeContextState(value, fallback = "Available") {
  const text = String(value ?? "").trim();
  if (!text) {
    return fallback;
  }
  return text.replace(/_/g, " ");
}

function marketContextTone(state, family) {
  const normalized = String(state ?? "").toLowerCase();
  if (
    normalized.includes("warm") ||
    normalized.includes("provisional") ||
    normalized.includes("insufficient") ||
    normalized.includes("unavailable")
  ) {
    return "warming";
  }
  if (
    normalized.includes("invalid") ||
    normalized.includes("error") ||
    normalized.includes("degraded") ||
    normalized.includes("synthetic") ||
    normalized.includes("partial") ||
    normalized.includes("missing") ||
    normalized.includes("nonpositive") ||
    normalized.includes("zero") ||
    normalized.includes("stale") ||
    normalized.includes("gap")
  ) {
    return "caution";
  }
  if (family === "structure") {
    if (normalized.includes("below") || normalized.includes("high_rejected")) {
      return "negative";
    }
    if (normalized.includes("above") || normalized.includes("low_rejected")) {
      return "positive";
    }
  }
  if (
    normalized.includes("elevated") ||
    normalized.includes("expansion") ||
    normalized.includes("high") ||
    normalized.includes("surge")
  ) {
    return "elevated";
  }
  return "neutral";
}

function renderContextMetrics(container, metrics) {
  container.replaceChildren();
  for (const [label, value] of metrics) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    const metric = document.createElement("span");
    metric.className = "context-metric";
    const metricLabel = document.createElement("span");
    metricLabel.textContent = label;
    const metricValue = document.createElement("strong");
    metricValue.textContent = value;
    metric.append(metricLabel, metricValue);
    container.appendChild(metric);
  }
}

function contextAvailabilityNote(
  overlay,
  last,
  defaultLimitation,
  timingText = "Post-close; next-action only",
) {
  const parts = [timingText];
  const maturity = firstContextValue(last, ["maturity", "quality", "data_quality"]);
  const observations = numericContextValue(last, [
    "observations",
    "reference_count",
    "baseline_count",
  ]);
  const required = numericContextValue(overlay, [
    "maturity_required_observations",
    "minimum_reference_count",
    "min_reference_count",
    "percentile_reference_prior_observations",
  ]);
  const nestedRequired = numericContextValue(overlay?.reference, [
    "full_maturity_required",
    "occurrences",
  ]);
  if (maturity) {
    parts.push(humanizeContextState(maturity));
  }
  if (observations !== null && (required !== null || nestedRequired !== null)) {
    parts.push(
      `${Math.round(observations)}/${Math.round(
        required ?? nestedRequired,
      )} references`,
    );
  }
  const availableAt = firstContextValue(last, [
    "available_at",
    "actionable_at",
    "as_of",
  ]);
  if (availableAt) {
    parts.push(`available ${formatCompactTimestamp(availableAt)}`);
  } else {
    parts.push("next-action after close");
  }
  if (overlay?.reason) {
    parts.push(String(overlay.reason));
  }
  const limitation = firstContextValue(overlay, [
    "limitation",
    "limitations",
    "quality_note",
    "comparability_warning",
  ]);
  parts.push(
    typeof limitation === "string" && limitation.trim()
      ? limitation.trim()
      : defaultLimitation,
  );
  return parts.join(" · ");
}

function renderContextCard({
  overlay,
  card,
  stateElement,
  metricsElement,
  noteElement,
  family,
  state,
  metrics,
  note,
}) {
  const available = Boolean(overlay && typeof overlay === "object");
  card.hidden = !available;
  if (!available) {
    metricsElement.replaceChildren();
    noteElement.textContent = "";
    return false;
  }
  const displayedState = humanizeContextState(
    state ?? overlay.status ?? overlay.reason,
    overlay.reason ? "Unavailable" : "Available",
  );
  stateElement.textContent = displayedState;
  card.dataset.tone = marketContextTone(displayedState, family);
  renderContextMetrics(metricsElement, metrics);
  noteElement.textContent = note;
  noteElement.title = note;
  return true;
}

function renderMarketContext() {
  const structure = historyState.overlays.prior_structure;
  const comparableVolatility = historyState.overlays.comparable_volatility;
  const participation = historyState.overlays.phase_adjusted_participation;

  const structureLast = contextLast(structure);
  const structurePosition = numericContextValue(structureLast, [
    "channel_position",
    "position",
    "position_48",
  ]);
  const roomUp = numericContextValue(structureLast, [
    "room_up_sigma",
    "up_room_sigma",
    "upside_room_sigma",
    "room_to_upper_sigma",
  ]);
  const roomDown = numericContextValue(structureLast, [
    "room_down_sigma",
    "down_room_sigma",
    "downside_room_sigma",
    "room_to_lower_sigma",
  ]);
  const structureVisible = renderContextCard({
    overlay: structure,
    card: elements.contextCardStructure,
    stateElement: elements.contextStateStructure,
    metricsElement: elements.contextMetricsStructure,
    noteElement: elements.contextNoteStructure,
    family: "structure",
    state: firstContextValue(structureLast, ["state", "status", "structure_state"]),
    metrics: [
      [
        "48-bar position",
        structurePosition === null
          ? null
          : formatFractionPercent(structurePosition),
      ],
      ["Room up", roomUp === null ? null : `${roomUp.toFixed(2)}σ`],
      ["Room down", roomDown === null ? null : `${roomDown.toFixed(2)}σ`],
    ],
    note: contextAvailabilityNote(
      structure ?? {},
      structureLast,
      "Prior-only rolling levels; location context, not direction.",
      "Channels known at bar open; state post-close / next-action",
    ),
  });

  const volatilityLast = contextLast(comparableVolatility);
  const volatilityPercentile = numericContextValue(volatilityLast, [
    "volatility_percentile",
    "rs_percentile",
    "percentile",
  ]);
  const volatilityRatio = numericContextValue(volatilityLast, [
    "fast_slow_ratio",
    "rs_fast_slow_ratio",
    "regime_ratio",
  ]);
  const rangeShock = numericContextValue(volatilityLast, [
    "range_shock",
    "range_shock_ratio",
    "shock_ratio",
  ]);
  const volatilityVisible = renderContextCard({
    overlay: comparableVolatility,
    card: elements.contextCardVolatility,
    stateElement: elements.contextStateVolatility,
    metricsElement: elements.contextMetricsVolatility,
    noteElement: elements.contextNoteVolatility,
    family: "volatility",
    state: firstContextValue(volatilityLast, [
      "volatility_state",
      "quality",
      "status",
    ]),
    metrics: [
      [
        "RS percentile",
        volatilityPercentile === null
          ? null
          : formatFractionPercent(volatilityPercentile),
      ],
      ["Fast / slow", volatilityRatio === null ? null : `${volatilityRatio.toFixed(2)}×`],
      ["Range shock", rangeShock === null ? null : `${rangeShock.toFixed(2)}×`],
    ],
    note: contextAvailabilityNote(
      comparableVolatility ?? {},
      volatilityLast,
      "Comparable only within this asset and interval; magnitude, not direction.",
      "Post-close; next-action only",
    ),
  });

  const participationLast = contextLast(participation);
  const rvol = numericContextValue(participationLast, [
    "rvol",
    "relative_volume",
    "phase_adjusted_rvol",
  ]);
  const participationPercentile = numericContextValue(participationLast, [
    "participation_score",
    "rvol_score",
    "participation_percentile",
    "rvol_percentile",
    "percentile",
  ]);
  const referenceCount = numericContextValue(participationLast, [
    "reference_count",
    "baseline_count",
    "observations",
  ]);
  const participationPhase = firstContextValue(participationLast, ["phase"]);
  const participationPhaseBasis = String(
    firstContextValue(participationLast, ["phase_basis"]) ??
      participation?.phase_basis ??
      "phase",
  );
  const participationPhaseText = participationPhase === null
    ? null
    : `${
        participationPhaseBasis === "session_bar_pos" ? "session" : "UTC"
      } ${participationPhase}`;
  const participationVisible = renderContextCard({
    overlay: participation,
    card: elements.contextCardParticipation,
    stateElement: elements.contextStateParticipation,
    metricsElement: elements.contextMetricsParticipation,
    noteElement: elements.contextNoteParticipation,
    family: "participation",
    state: firstContextValue(participationLast, [
      "participation_state",
      "quality",
      "status",
    ]),
    metrics: [
      ["Phase RVOL", rvol === null ? null : `${rvol.toFixed(2)}×`],
      [
        "Activity score",
        participationPercentile === null
          ? null
          : formatSignedScore(participationPercentile),
      ],
      ["References", referenceCount === null ? null : Math.round(referenceCount).toLocaleString()],
      ["Phase", participationPhaseText],
    ],
    note: contextAvailabilityNote(
      participation ?? {},
      participationLast,
      "Final bars only; volume units are comparable only within this stream.",
      "Finalized bar; next-action only",
    ),
  });

  const marketContextVisible =
    structureVisible || volatilityVisible || participationVisible;
  elements.marketContextStrip.hidden = !marketContextVisible;
  elements.marketContextDetails.hidden = !marketContextVisible;
}

function renderForwardMetaShadowLegend(payload) {
  if (!elements.forwardMetaShadowLegend || !elements.forwardMetaShadowState) {
    return;
  }
  const counts = payload?.counts ?? {};
  const hasRun = Boolean(payload?.run_id);
  const hasEvents = Number(counts.events ?? 0) > 0;
  elements.forwardMetaShadowLegend.hidden = !hasRun && !hasEvents;
  if (!hasRun && !hasEvents) {
    elements.forwardMetaShadowState.textContent = "journal unavailable";
    elements.forwardMetaShadowState.className = "legend-state unavailable";
    elements.forwardMetaShadowState.removeAttribute("title");
    return;
  }

  const scores = Number(counts.available_scores ?? 0);
  const labels = Number(counts.labels ?? 0);
  const unavailable = Number(counts.unavailable_predictions ?? 0);
  const latestAudit = Array.isArray(payload?.audit)
    ? [...payload.audit].reverse().find((item) => item?.model_digest || item?.policy_digest)
    : null;
  if (scores > 0) {
    elements.forwardMetaShadowState.textContent =
      `${scores.toLocaleString()} scored · ${labels.toLocaleString()} labels · shadow only`;
    elements.forwardMetaShadowState.className = "legend-state active";
  } else if (hasEvents) {
    elements.forwardMetaShadowState.textContent =
      `${unavailable.toLocaleString()} unavailable · ${labels.toLocaleString()} labels · shadow only`;
    elements.forwardMetaShadowState.className = "legend-state unavailable";
  } else {
    elements.forwardMetaShadowState.textContent =
      "not enabled for this run · no order effect";
    elements.forwardMetaShadowState.className = "legend-state unavailable";
  }
  const titleParts = [
    payload?.reason ? `State: ${payload.reason}` : null,
    latestAudit?.model_digest ? `Model: ${latestAudit.model_digest}` : null,
    latestAudit?.policy_digest ? `Policy: ${latestAudit.policy_digest}` : null,
    payload?.run_id ? `Run: ${payload.run_id}` : null,
  ].filter(Boolean);
  if (titleParts.length > 0) {
    elements.forwardMetaShadowState.title = titleParts.join(" · ");
  } else {
    elements.forwardMetaShadowState.removeAttribute("title");
  }
}

function renderMetadata(metadata, candleCount) {
  let paneCount = 0;
  for (const group of elements.legendGroups) {
    const overlay = historyState.overlays[group.dataset.overlay];
    const hasData = overlayHasChartData(group.dataset.overlay, overlay);
    group.hidden = !hasData;
    paneCount += hasData && group.dataset.priceOverlay !== "true" ? 1 : 0;
  }
  const replayPayload = replayPayloadForActiveChart();
  const hasReplayPane = Boolean(
    replayPayload &&
      [replayPayload.equity, replayPayload.drawdown, replayPayload.position].some(
        (series) => replaySeriesForLoadedChart(series).length > 0,
      ),
  );
  paneCount += hasReplayPane ? 1 : 0;
  const hasMetaPane = Boolean(
    replayPayload &&
      (replaySeriesForLoadedChart(replayPayload.meta_scores).length > 0 ||
        replayRequiredProbabilityForLoadedChart(replayPayload).length > 0),
  );
  paneCount += hasMetaPane ? 1 : 0;
  const hasForwardMetaPane = forwardMetaScoresForLoadedChart().length > 0;
  paneCount += hasForwardMetaPane ? 1 : 0;
  elements.chartWrap.dataset.paneCount = String(paneCount);
  elements.markerLegend.hidden = historyState.markers.length === 0;
  elements.replayPaneLegend.hidden = !hasReplayPane;
  elements.replayProtectionLegend.hidden = !(
    replayPayload &&
    [replayPayload.risk_stop, replayPayload.risk_target].some((series) =>
      replayPriceSeriesForLoadedChart(series).some(
        (point) => point.value !== undefined,
      ),
    )
  );
  elements.replayMetaLegend.hidden = !hasMetaPane;
  renderForwardMetaShadowLegend(forwardMetaShadowPayload());
  elements.replayMarkerLegend.hidden =
    replayMarkersForLoadedChart(replayPayload?.markers).length === 0;
  renderReplayResults(replayPayload);
  const source = [metadata.source, metadata.provider].filter(Boolean).join(" / ");
  const loadedStart = firstCandleTime();
  const loadedEnd = lastCandleTime();
  const range =
    loadedStart && loadedEnd
      ? `${formatTime(loadedStart)} -> ${formatTime(loadedEnd)}`
      : `${metadata.start ?? "-"} -> ${metadata.end ?? "-"}`;
  elements.asset.textContent = metadata.asset ?? "-";
  elements.timeframe.textContent = metadata.timeframe ?? "-";
  elements.source.textContent = source || "-";
  elements.bars.textContent = candleCount.toLocaleString();
  elements.range.textContent = range;
  const cusum = historyState.overlays.cusum_trend;
  const ewmaVolatility = historyState.overlays.ewma_volatility;
  const trend = historyState.overlays.volatility_scaled_trend;
  const onlineRegime = historyState.overlays.online_regime;
  const mtfContext = historyState.overlays.cross_timeframe_context;
  const priorStructure = historyState.overlays.prior_structure;
  const comparableVolatility = historyState.overlays.comparable_volatility;
  const participation = historyState.overlays.phase_adjusted_participation;
  elements.indicatorStatusCusum.textContent = cusum?.last?.status
    ? `${cusum.sensitivity ?? "CUSUM"} · ${cusum.last.status}`
    : cusum?.reason ?? "Change detection & trail";
  elements.indicatorStatusEwma.textContent = ewmaVolatility?.last?.status
    ? `${ewmaVolatility.last.status} · ${ewmaVolatility.last.maturity ?? "maturity unknown"}`
    : ewmaVolatility?.reason ?? "Fast / medium / slow";
  elements.indicatorStatusTrend.textContent = trend?.last?.status
    ? trend.last.status
    : trend?.reason ?? "Normalized multi-horizon trend";
  elements.indicatorStatusRegime.textContent = onlineRegime?.last?.status
    ? onlineRegime.last.status
    : onlineRegime?.reason ?? "Bull / bear / range / transition";
  elements.indicatorStatusMtf.textContent = mtfContext?.latest?.context_class
    ? `${mtfContextLabel(mtfContext.latest.context_class)} · ${
        mtfContext.latest.direction_bias ?? "mixed"
      }`
    : mtfContext?.reason ?? "Closed-bar alignment matrix";
  const structureLast = contextLast(priorStructure);
  elements.indicatorStatusStructure.textContent = firstContextValue(
    structureLast,
    ["state", "status", "structure_state"],
  )
    ? humanizeContextState(
        firstContextValue(structureLast, ["state", "status", "structure_state"]),
      )
    : priorStructure?.reason ?? "Prior-only channels & tests";
  const comparableVolatilityLast = contextLast(comparableVolatility);
  elements.indicatorStatusComparableVol.textContent = firstContextValue(
    comparableVolatilityLast,
    ["volatility_state", "quality", "status"],
  )
    ? humanizeContextState(
        firstContextValue(comparableVolatilityLast, [
          "volatility_state",
          "quality",
          "status",
        ]),
      )
    : comparableVolatility?.reason ?? "RS range state & percentile";
  const participationLast = contextLast(participation);
  const participationState = firstContextValue(participationLast, [
    "participation_state",
    "quality",
    "status",
  ]);
  const participationRvol = numericContextValue(participationLast, [
    "rvol",
    "relative_volume",
    "phase_adjusted_rvol",
  ]);
  elements.indicatorStatusParticipation.textContent = participationState
    ? `${humanizeContextState(participationState)}${
        participationRvol === null ? "" : ` · ${participationRvol.toFixed(2)}×`
      }`
    : participation?.reason ?? "Activity vs comparable market phase";
  renderMtfContext(mtfContext);
  renderMarketContext();
  const trendHorizons = trend?.horizons_bars ?? {};
  elements.legendTrendFast.textContent = `fast ${trendHorizons.fast ?? "?"} bars`;
  elements.legendTrendMedium.textContent =
    `medium ${trendHorizons.medium ?? "?"} bars`;
  elements.legendTrendSlow.textContent = `slow ${trendHorizons.slow ?? "?"} bars`;
  const indicatorDetails = [];
  if (cusum?.last?.status) {
    indicatorDetails.push(`CUSUM ${cusum.sensitivity}: ${cusum.last.status}`);
  }
  if (ewmaVolatility?.last?.status) {
    const halfLives = ewmaVolatility.half_lives_bars ?? {};
    const fast = formatPercent(ewmaVolatility.last.fast_pct);
    const slow = formatPercent(ewmaVolatility.last.slow_pct);
    const ratio = ewmaVolatility.last.fast_slow_ratio;
    const ratioText = ratio !== null && ratio !== undefined && Number.isFinite(Number(ratio))
      ? `, ${Number(ratio).toFixed(2)}× fast/slow`
      : "";
    indicatorDetails.push(
      `EWMA vol ${halfLives.fast ?? "?"}/${halfLives.medium ?? "?"}/` +
        `${halfLives.slow ?? "?"} bars: ${ewmaVolatility.last.status} ` +
      `(${fast} fast / ${slow} slow${ratioText})`,
    );
    if (ewmaVolatility.last.maturity === "warming") {
      indicatorDetails.push(
        `EWMA maturity: ${ewmaVolatility.last.observations ?? 0}/` +
          `${ewmaVolatility.maturity_required_observations ?? "?"} returns`,
      );
    }
  }
  if (trend?.last?.status) {
    indicatorDetails.push(
      `Vol-scaled Trend ${trendHorizons.fast ?? "?"}/` +
        `${trendHorizons.medium ?? "?"}/${trendHorizons.slow ?? "?"} bars: ` +
        `${trend.last.status} ` +
        `(score ${Number(trend.last.score).toFixed(3)}, ` +
        `quality ${formatPercent(Number(trend.last.path_quality) * 100, 0)}; next-bar)`,
    );
  } else if (trend?.reason) {
    indicatorDetails.push(`Vol-scaled Trend: ${trend.reason}`);
  }
  if (onlineRegime?.last?.status) {
    const topWeight = Number(
      onlineRegime.last.top_weight ??
        onlineRegime.last.max_weight ??
        onlineRegime.last.confidence,
    );
    const topWeightText = Number.isFinite(topWeight)
      ? formatPercent(topWeight * 100, 1)
      : "-";
    indicatorDetails.push(
      `Prototype Regime: ${onlineRegime.last.status} ` +
        `(${topWeightText} top weight, ` +
        `${formatPercent(Number(onlineRegime.last.change_risk) * 100, 1)} change risk; ` +
        `next-bar diagnostic)`,
    );
  } else if (onlineRegime?.reason) {
    indicatorDetails.push(`Prototype Regime unavailable: ${onlineRegime.reason}`);
  }
  if (mtfContext?.latest?.context_class) {
    indicatorDetails.push(
      `Cross-TF: ${mtfContextLabel(mtfContext.latest.context_class)} ` +
        `(${mtfContext.latest.direction_bias}, score ${Number(
          mtfContext.latest.direction_score,
        ).toFixed(2)}; closed bars only)`,
    );
  } else if (mtfContext?.reason) {
    indicatorDetails.push(`Cross-TF: ${mtfContext.reason}`);
  }
  const structureState = firstContextValue(structureLast, [
    "state",
    "status",
    "structure_state",
  ]);
  if (structureState) {
    indicatorDetails.push(
      `Prior Structure: ${humanizeContextState(structureState)} ` +
        `(48-bar prior-only channel; state next-action)`,
    );
  } else if (priorStructure?.reason) {
    indicatorDetails.push(`Prior Structure: ${priorStructure.reason}`);
  }
  const comparableState = firstContextValue(comparableVolatilityLast, [
    "volatility_state",
    "quality",
    "status",
  ]);
  if (comparableState) {
    const percentile = numericContextValue(comparableVolatilityLast, [
      "volatility_percentile",
      "rs_percentile",
      "percentile",
    ]);
    indicatorDetails.push(
      `Comparable Volatility: ${humanizeContextState(comparableState)}` +
        `${
          percentile === null
            ? ""
            : ` (${formatFractionPercent(percentile)} RS rank)`
        }` +
        `; within-selection, next-action`,
    );
  } else if (comparableVolatility?.reason) {
    indicatorDetails.push(
      `Comparable Volatility: ${comparableVolatility.reason}`,
    );
  }
  if (participationState) {
    indicatorDetails.push(
      `Phase Participation: ${humanizeContextState(participationState)}` +
        `${participationRvol === null ? "" : ` (${participationRvol.toFixed(2)}× RVOL)`}` +
        `; finalized-bar, within-stream`,
    );
  } else if (participation?.reason) {
    indicatorDetails.push(`Phase Participation: ${participation.reason}`);
  }
  const indicatorText = indicatorDetails.length
    ? ` | ${indicatorDetails.join(" | ")}`
    : "";
  elements.subtitle.textContent =
    `${metadata.description ?? "OHLCV payload"} ` +
    `(${metadata.source_path_count ?? 0} source files)` +
    indicatorText;
  renderDiagnosticVintage(metadata);

  if (metadata.truncated_to_max_bars) {
    setStatus(
      `Loaded latest ${metadata.max_bars.toLocaleString()} bars from ` +
        `${metadata.rows_before_window_limit.toLocaleString()} matching rows.`,
      "warn",
    );
  } else {
    setStatus("Payload loaded.");
  }
  if (overlayWarning) {
    setStatus(overlayWarning, "warn");
  }
  const hasLiveOverlayMetadata = renderLiveOverlayMetadata(metadata, loadedEnd);
  const liveMeta = metadata.online_signal;
  if (!hasLiveOverlayMetadata && liveMeta?.status === "ok") {
    const through = liveMeta.computed_source_through ?? "-";
    const throughTime = Date.parse(through);
    const interval = timeframeSeconds(metadata.timeframe);
    const isStale =
      Number.isFinite(throughTime) &&
      interval &&
      Date.now() - throughTime > interval * 2.5 * 1000;
    const displayTime = through.replace("T", " ").replace("Z", " UTC");
    const replaySource =
      liveMeta.signal_vintage === "current_canonical_replay" ||
      liveMeta.mode === "full_origin_stream_replay";
    setLiveState(
      `${replaySource ? "Replay source" : "Source"} ` +
        `${isStale ? "stale" : "current"}: through ${displayTime}`,
      isStale ? "warn" : "info",
    );
    if (liveMeta.validation_warning) {
      elements.liveState.title = String(liveMeta.validation_warning);
    } else {
      elements.liveState.removeAttribute("title");
    }
  } else if (!hasLiveOverlayMetadata && liveMeta?.reason) {
    setLiveState(`Live: ${liveMeta.reason}`, "warn");
    elements.liveState.removeAttribute("title");
  } else if (!hasLiveOverlayMetadata && !elements.liveRefreshToggle.checked) {
    setLiveState("Live: paused", "warn");
    elements.liveState.removeAttribute("title");
  }
  renderDecisionSupport();
}

function setInitialVisibleRange(timeScale) {
  const candleCount = historyState.candles.length;
  if (candleCount > INITIAL_VISIBLE_BARS) {
    timeScale.setVisibleLogicalRange({
      from: candleCount - INITIAL_VISIBLE_BARS,
      to: candleCount - 1,
    });
    return;
  }
  timeScale.fitContent();
}

function applySeriesData({
  preserveVisibleRange = false,
  addedLeft = 0,
  stickToRealTime = false,
} = {}) {
  if (!chart || !candleSeries || !volumeSeries) {
    return;
  }
  const timeScale = chart.timeScale();
  const visibleLogicalRange = preserveVisibleRange
    ? timeScale.getVisibleLogicalRange()
    : null;
  const rightOffset = stickToRealTime ? timeScale.scrollPosition() : null;

  activePricePrecision = precisionForPayload({
    metadata: historyState.metadata,
    candles: historyState.candles,
  });
  activePriceMinMove = priceMinMoveForPayload(
    { metadata: historyState.metadata },
    activePricePrecision,
  );
  candleSeries.applyOptions({
    priceFormat: {
      type: "price",
      precision: activePricePrecision,
      minMove: activePriceMinMove,
    },
  });

  suppressVisibleRangeEvents = true;
  candleSeries.setData(historyState.candles);
  volumeSeries.setData(historyState.volume);
  applyOptionalDecorations();

  if (stickToRealTime && Number.isFinite(rightOffset)) {
    timeScale.scrollToPosition(rightOffset, false);
  } else if (preserveVisibleRange && visibleLogicalRange) {
    timeScale.setVisibleLogicalRange({
      from: visibleLogicalRange.from + addedLeft,
      to: visibleLogicalRange.to + addedLeft,
    });
  } else {
    setInitialVisibleRange(timeScale);
  }

  requestAnimationFrame(() => {
    suppressVisibleRangeEvents = false;
  });
}

function renderPayload(payload, { canLoadHistory = true } = {}) {
  validatePayload(payload);
  destroyChart();
  initChart();

  historyState.candles = payload.candles;
  historyState.volume = payload.volume ?? [];
  historyState.markers = payload.markers ?? [];
  historyState.overlays = payload.overlays ?? {};
  historyState.metadata = payload.metadata ?? {};
  historyState.forwardMetaShadow = payload.forward_meta_shadow ?? null;
  historyState.canLoadHistory = canLoadHistory;
  historyState.isLoadingOlder = false;
  historyState.exhaustedLeft = !Boolean(payload.metadata?.truncated_to_max_bars);
  applySeriesData();

  renderMetadata(historyState.metadata, historyState.candles.length);
  if (historyState.exhaustedLeft && canLoadHistory) {
    setStatus("Loaded full available range for this selection.");
  }
  updateHistoryControls();
}

async function fetchChartPayload(url) {
  const response = await fetch(withCacheBust(url), {
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Failed to fetch chart payload: HTTP ${response.status}`;
    try {
      const errorPayload = await response.json();
      if (errorPayload.error) {
        message = errorPayload.error;
      }
    } catch {
      // Keep the HTTP status message.
    }
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function loadOlderHistory(trigger = "manual") {
  if (
    !historyState.canLoadHistory ||
    historyState.isLoadingOlder ||
    historyState.exhaustedLeft ||
    historyState.candles.length === 0
  ) {
    return;
  }

  const params = olderRequestParams();
  if (!params) {
    return;
  }

  const generation = loadGeneration;
  const previousEarliest = firstCandleTime();
  historyState.isLoadingOlder = true;
  updateHistoryControls();
  setStatus("Loading older bars...");

  try {
    const payload = await fetchChartPayload(`${API_CHART_URL}?${params.toString()}`);
    if (generation !== loadGeneration) {
      return;
    }
    validatePayload(payload);

    const incomingCandles = payload.candles ?? [];
    const incomingVolume = payload.volume ?? [];
    historyState.candles = mergeByTime(historyState.candles, incomingCandles);
    historyState.volume = mergeByTime(historyState.volume, incomingVolume);
    historyState.markers = mergeMarkers(historyState.markers, payload.markers ?? []);
    historyState.overlays = mergeOverlays(historyState.overlays, payload.overlays ?? {});
    historyState.forwardMetaShadow = mergeForwardMetaShadow(
      historyState.forwardMetaShadow,
      payload.forward_meta_shadow,
    );
    historyState.metadata = {
      ...historyState.metadata,
      start: formatTime(firstCandleTime()),
      end: formatTime(lastCandleTime()),
      row_count: historyState.candles.length,
    };

    const addedLeft = historyState.candles.filter(
      (candle) => candle.time < previousEarliest,
    ).length;
    historyState.exhaustedLeft =
      addedLeft === 0 || !Boolean(payload.metadata?.truncated_to_max_bars);
    applySeriesData({ preserveVisibleRange: true, addedLeft });
    renderMetadata(historyState.metadata, historyState.candles.length);
    setStatus(
      addedLeft > 0
        ? `Loaded ${addedLeft.toLocaleString()} older bars; ` +
            `${historyState.candles.length.toLocaleString()} total loaded.`
        : "No additional older bars were returned.",
      historyState.exhaustedLeft ? "info" : "warn",
    );
  } catch (error) {
    if (generation !== loadGeneration) {
      return;
    }
    if (error.status === 400 && error.message.includes("No rows found")) {
      historyState.exhaustedLeft = true;
      setStatus("Reached the beginning of available data for this selection.");
      return;
    }
    setStatus(
      `${trigger === "auto" ? "Auto history load" : "History load"} failed: ${
        error.message
      }`,
      "error",
    );
    console.error(error);
  } finally {
    if (generation === loadGeneration) {
      historyState.isLoadingOlder = false;
      updateHistoryControls();
    }
  }
}

function canRefreshLive() {
  return Boolean(
    elements.liveRefreshToggle.checked &&
      activeChartParams &&
      !activeChartParams.has("end") &&
      !historyState.isLoadingOlder &&
      !liveRefreshInFlight &&
      document.visibilityState !== "hidden",
  );
}

async function refreshLivePayload() {
  if (!canRefreshLive()) {
    return;
  }
  liveRefreshInFlight = true;
  const generation = loadGeneration;
  setLiveState("Live: checking...");
  try {
    const payload = await fetchChartPayload(
      `${API_CHART_URL}?${activeChartParams.toString()}`,
    );
    if (generation !== loadGeneration) {
      return;
    }
    validatePayload(payload);
    const incomingCandles = payload.candles ?? [];
    const incomingStart = incomingCandles[0]?.time;
    if (!incomingStart) {
      return;
    }

    const replayFromRaw = payload.metadata?.online_signal?.replay_from;
    const replayFrom = replayFromRaw
      ? Math.floor(new Date(replayFromRaw).getTime() / 1000)
      : null;
    if (
      Number.isFinite(replayFrom) &&
      replayFrom < incomingStart &&
      replayFrom >= firstCandleTime()
    ) {
      setLiveState("Live: corrected history; reloading", "warn");
      await loadPayload();
      return;
    }

    const visibleRange = chart?.timeScale().getVisibleLogicalRange();
    const priorCount = historyState.candles.length;
    const wasAtRight = Boolean(
      visibleRange && visibleRange.to >= priorCount - 1 - 0.01,
    );
    historyState.candles = mergeByTime(
      historyState.candles.filter((point) => point.time < incomingStart),
      incomingCandles,
    );
    historyState.volume = mergeByTime(
      historyState.volume.filter((point) => point.time < incomingStart),
      payload.volume ?? [],
    );
    historyState.markers = mergeMarkers(
      historyState.markers.filter((marker) => marker.time < incomingStart),
      payload.markers ?? [],
    );
    historyState.overlays = mergeOverlays(
      trimOverlaySeriesFrom(historyState.overlays, incomingStart),
      payload.overlays ?? {},
    );
    historyState.forwardMetaShadow = mergeForwardMetaShadow(
      historyState.forwardMetaShadow,
      payload.forward_meta_shadow,
    );
    historyState.metadata = {
      ...historyState.metadata,
      ...payload.metadata,
      start: formatTime(firstCandleTime()),
      end: formatTime(lastCandleTime()),
      row_count: historyState.candles.length,
    };
    applySeriesData({
      preserveVisibleRange: !wasAtRight,
      stickToRealTime: wasAtRight,
    });
    renderMetadata(historyState.metadata, historyState.candles.length);
  } catch (error) {
    if (generation === loadGeneration) {
      setLiveState(`Live error: ${error.message}`, "error");
    }
    console.error(error);
  } finally {
    liveRefreshInFlight = false;
  }
}

function startLiveRefreshTimer() {
  if (liveRefreshTimer !== null) {
    window.clearInterval(liveRefreshTimer);
  }
  liveRefreshTimer = window.setInterval(
    refreshLivePayload,
    LIVE_REFRESH_INTERVAL_MS,
  );
}

async function loadPayload(url = null) {
  const generation = ++loadGeneration;
  setLoading(true);
  setStatus("Loading payload...");
  try {
    const params = url ? null : selectedParams();
    activeChartParams = params;
    const target = url ?? `${API_CHART_URL}?${params.toString()}`;
    const payload = await fetchChartPayload(target);
    if (generation !== loadGeneration) {
      return;
    }
    renderPayload(payload, { canLoadHistory: url === null });
  } catch (error) {
    destroyChart();
    elements.subtitle.textContent = "Chart payload could not be loaded.";
    setStatus(error.message, "error");
    console.error(error);
  } finally {
    setLoading(false);
  }
}

async function loadManifest() {
  const response = await fetch(`${API_MANIFEST_URL}?t=${Date.now()}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch manifest: HTTP ${response.status}`);
  }
  manifest = await response.json();
  populateControls();
}

function setLayersVisible(visible) {
  elements.workspace.classList.toggle("layers-hidden", !visible);
  elements.layersToggleButton.classList.toggle("active", visible);
  elements.layersToggleButton.setAttribute("aria-expanded", visible ? "true" : "false");
}

function setResearchDrawerExpanded(expanded) {
  elements.researchDrawer.classList.toggle("is-collapsed", !expanded);
  elements.researchToggleButton.setAttribute(
    "aria-expanded",
    expanded ? "true" : "false",
  );
}

function selectResearchTab(name) {
  for (const tab of elements.researchTabs) {
    const selected = tab.dataset.researchTab === name;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
  }
  for (const panel of elements.researchPanels) {
    const selected = panel.dataset.researchPanel === name;
    panel.classList.toggle("is-active", selected);
    panel.hidden = !selected;
  }
  setResearchDrawerExpanded(true);
}

async function boot() {
  syncProtectedReplayControls();
  setLoading(true);
  try {
    await loadManifest();
    await loadPayload();
    await refreshForwardPaperStatus();
  } catch (error) {
    console.warn("API manifest unavailable, attempting static fallback.", error);
    setStatus("API unavailable. Loading static fallback payload.", "warn");
    await loadPayload(FALLBACK_DATA_URL);
  } finally {
    startLiveRefreshTimer();
    startPaperRefreshTimer();
    setLoading(false);
  }
}

elements.assetSelect.addEventListener("change", () => {
  populateSourceOptions();
  populateTimeframeOptions();
  updateReplayAvailability();
  refreshForwardPaperStatus();
  loadPayload();
});
elements.sourceSelect.addEventListener("change", () => {
  populateTimeframeOptions();
  updateReplayAvailability();
  refreshForwardPaperStatus();
  loadPayload();
});
elements.timeframeSelect.addEventListener("change", () => {
  updateTimeframeQuickbarSelection();
  refreshForwardPaperStatus();
  loadPayload();
});
for (const indicatorInput of elements.indicatorInputs) {
  indicatorInput.addEventListener("change", () => {
    updateIndicatorControls();
    scheduleLayerReload();
  });
}
elements.cusumSensitivitySelect.addEventListener("change", scheduleLayerReload);
elements.chartForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadPayload();
});
elements.reloadButton.addEventListener("click", () => loadPayload());
elements.layersToggleButton.addEventListener("click", () => {
  setLayersVisible(elements.workspace.classList.contains("layers-hidden"));
});
elements.allIndicatorsButton.addEventListener("click", () => setAllIndicators(true));
elements.clearIndicatorsButton.addEventListener("click", () => setAllIndicators(false));
elements.researchToggleButton.addEventListener("click", () => {
  setResearchDrawerExpanded(elements.researchDrawer.classList.contains("is-collapsed"));
});
for (const tab of elements.researchTabs) {
  tab.addEventListener("click", () => selectResearchTab(tab.dataset.researchTab));
}
elements.liveRefreshToggle.addEventListener("change", () => {
  if (elements.liveRefreshToggle.checked) {
    setLiveState("Live: enabled");
    refreshLivePayload();
  } else {
    setLiveState("Live: paused", "warn");
  }
  renderDecisionSupport();
});
elements.loadOlderButton.addEventListener("click", () => loadOlderHistory("manual"));
elements.autoHistoryToggle.addEventListener("change", () => {
  updateHistoryControls();
  setStatus(
    elements.autoHistoryToggle.checked
      ? "Auto history loading enabled."
      : "Auto history loading disabled. Use Load Older for manual paging.",
  );
});
elements.runReplayButton.addEventListener("click", () => {
  runReplay({ optimize: false });
});
elements.optimizeReplayButton.addEventListener("click", () => {
  runReplay({ optimize: true });
});
elements.paperRefreshButton.addEventListener("click", refreshForwardPaperStatus);
for (const input of [
  elements.replayDaysInput,
  elements.replayFeeInput,
  elements.replaySlippageInput,
  elements.replaySpreadInput,
  elements.replayLatencyInput,
  elements.replayProtectedBracketInput,
  elements.replayRiskUnitVolatilityInput,
  elements.replayStopRiskUnitsInput,
  elements.replayTargetRiskUnitsInput,
  elements.replayTimeoutTargetBarsInput,
  elements.replayBreakEvenSafetyMarginInput,
  elements.replayMetaFilterModeSelect,
]) {
  input.addEventListener("change", () => {
    syncProtectedReplayControls();
    renderReplayResults();
    if (!replayPayloadForActiveChart()) {
      clearReplayOverlayData();
    }
    applyMarkers();
    if (!replayPayloadForActiveChart()) {
      setReplayStatus("Assumptions changed · run a new manual replay", "info");
    }
    renderResearchParityNote();
  });
}
window.addEventListener("DOMContentLoaded", boot);
window.addEventListener("resize", updateMarkerDensity);

# %% [markdown]
# # Risk Yield Meta Model Analyst
#
# This notebook-style Python script is the focused workspace for the visual
# analyst layer of the RiskYieldMM project. New inspection tools, chart
# exports, and local UI helpers should live in this folder first:
#
# `Risk_Yield_Meta_Model_Analyst_0_0_1/`
#
# ## Current Goal
#
# Build a reliable visual inspection workflow around TradingView
# Lightweight Charts. The first target is interactive OHLCV inspection, then
# overlays for labels, model predictions, walk-forward splits, regimes, and
# other artifacts produced by the HTF / multi-asset pipeline.
#
# ## Raw OHLCV Data Available
#
# Raw source files are parquet batches with UTC timestamps and OHLCV fields.
# The common raw schema is:
#
# `timestamp, open, high, low, close, volume, turnover, interval`
#
# ### Bybit Linear Crypto
#
# Root: `../fetchingByBit/`
#
# Assets:
# - `BTCUSDT`
# - `ETHUSDT`
#
# Native raw OHLCV timeframes:
# - `1m`
# - `5m`
# - `15m`
# - `1h`
# - `4h`
# - `1d`
#
# Directories:
# - `sorted-1m-bybit-linear/`
# - `sorted-5m-bybit-linear/`
# - `sorted-15m-bybit-linear/`
# - `sorted-1h-bybit-linear/`
# - `sorted-4h-bybit-linear/`
# - `sorted-1d-bybit-linear/`
#
# Approximate coverage:
# - `BTCUSDT`: from `2021-01-01` through `2026-07-02`
# - `ETHUSDT`: from `2021-03-15` through `2026-07-02`
#
# ### Multi-Asset OHLCV
#
# Root: `../fetchingMultiAsset/`
#
# Assets:
# - `CL`
# - `ES`
# - `EURUSD`
# - `GC`
# - `NQ`
# - `USDJPY`
#
# Main raw source:
# - `sorted-1m-databento-futures/`
# - `sorted-15m-databento-futures/`
#
# Native raw OHLCV timeframes:
# - `1m`
# - `15m`
#
# Approximate coverage:
# - mostly from `2021-01-03` through `2026-07-02`
#
# Additional partial/fallback sources:
# - `sorted-1m-yfinance-futures/`
# - `sorted-15m-yfinance-futures/`
# - `sorted-1m-twelvedata-multi/` for partial `EURUSD`
# - `sorted-15m-twelvedata-multi/` for partial `EURUSD`
# - `sorted-1m-databento-futures_es_backup_before_2021_backfill/`
# - `sorted-15m-databento-futures_es_backup_before_2021_backfill/`
#
# ## Canonical Processed OHLCV
#
# Root: `../data/htf_multiasset/{asset}/htf_canonical_ohlcv/`
#
# Core assets:
# - `BTCUSDT`
# - `ETHUSDT`
# - `EURUSD`
# - `USDJPY`
# - `GC`
# - `CL`
# - `ES`
# - `NQ`
#
# Canonical timeframes:
# - `1m`
# - `15m`
# - `1h`
# - `4h`
# - `8h`
# - `12h`
# - `1d`
#
# Important: `8h` and `12h` are canonical/resampled outputs, not native raw
# source timeframes.
#
# ## Bybit Auxiliary Data
#
# Bybit also has raw auxiliary market data for `BTCUSDT` and `ETHUSDT`:
#
# - mark price OHLC: `mark-price-{tf}-bybit-linear/`
# - index price OHLC: `index-price-{tf}-bybit-linear/`
# - premium price OHLC: `premium-price-{tf}-bybit-linear/`
# - open interest: `open-interest-{tf}-bybit-linear/`
# - funding rate: `funding-rate-bybit-linear/`
# - long-short ratio: `long-short-ratio-{tf}-bybit-linear/`
#
# These are useful as overlays or feature diagnostics, but they are not the
# primary trade OHLCV candles.
#
# ## Visual Inspection Rules
#
# - Keep all chart timestamps in UTC unless there is a specific display reason
#   to shift time zones.
# - Do not load full multi-year `1m` history into the browser. Use windowed
#   exports by asset, timeframe, start/end, or recent bar count.
# - Use canonical OHLCV as the default visual inspection dataset.
# - Use raw/provider OHLCV sources for data-integrity debugging and source
#   comparison.
# - Every overlay should be traceable to an artifact path and generation step.
# - Browser charts support lazy historical loading: leave `Start UTC stop`
#   empty, load a bounded latest window, then pan/scroll left for older bars.
#
# ## Implemented Chart Overlays
#
# - `CUSUM Trend`: prior-scale standardized two-sided CUSUM on the Hull residual.
#   The 14/21/50-bar presets expose upper/lower bands, trailing state, candle
#   coloring, and bull/bear shift candidates. They are not Buy/Sell orders.
# - `EWMA Volatility`: a lower-pane, post-close log-return volatility diagnostic
#   with 12/48/192 observed-bar half-lives, fast/slow state, and lazy-page
#   warm-up history. It is a risk-context overlay, not a Buy/Sell signal.
# - `Volatility-Scaled Trend`: bounded 12/48/192-bar directional components
#   using the matching prior-bar EWMA volatility and path efficiency. Candidate
#   markers are plotted at the next bar, never on the generating close.
# - `Prototype Regime`: a four-state fixed-prototype Gaussian HMM filter
#   advanced with one-step causal forward recursion. It is available for all
#   8 canonical assets and all 7 canonical timeframes. The displayed values are
#   untrained prototype weights/change risk, not calibrated probabilities,
#   confidence, or predictive alpha.
# - `Cross-Timeframe Context`: a canonical-only closed-bar matrix using fixed
#   causal mappings (for example 1h -> 4h + 1d). It aligns backward-as-of on
#   `max(scheduled_close, first_seen_at)` and describes trend alignment,
#   countertrend conflict, range, or transition caution. It is not a trade gate.
# - `Prior Structure`: strict prior-only 4/16/48-bar channels. The 48-bar
#   channel is drawn on price; post-close break/rejection classifications are
#   shown only at their next actionable time and never labeled Buy/Sell.
# - `Comparable Volatility`: a bounded lower-pane view of drift-robust
#   Rogers-Satchell range variance, its fast/slow state, range shock, and a
#   prior-only within-selection percentile. Raw percent-per-bar values are not
#   compared across bar durations.
# - `Phase-adjusted Participation`: completed-bar volume relative to the prior
#   20 comparable UTC phases for crypto or exchange-session phases for the
#   other assets. Synthetic rows are excluded where canonical flags exist;
#   the chart reports maturity and missing provider/roll provenance explicitly.
#
# ## Market Context v1 Research and Implementation
#
# The 2026-07-12 source review and fixed 56-selection screen are recorded in:
#
# - `../docs/research/meta_model_analyst_next_feature_research_2026-07-12.md`
# - `../docs/validation/meta_model_analyst_next_feature_study_2026-07-12.json`
# - `../docs/validation/meta_model_analyst_market_context_matrix_2026-07-12.json`
# - `../docs/validation/meta_model_analyst_market_context_certification_2026-07-12.md`
#
# The selected diagnostic Market Context bundle is exposed as three
# independently selectable layers: prior structure, Rogers-Satchell range
# volatility, and session/UTC-phase-adjusted participation. Structure remains
# location/risk context, not another universal direction signal: channel
# position was highly redundant with the existing trend score and added nearly
# zero median partial directional association in the fixed screen. Volatility
# level and relative volume had the strongest stable relationship with future
# movement magnitude.
#
# Session-asset provenance must be improved before promotion: retain
# constituent-minute quality, provider cohort, resolved futures instrument, and
# roll boundaries. The existing BOCPD helper must also remain off the chart
# until Python/Rust parity and run-length probability semantics are repaired.
# None of these findings certifies a profitable strategy; each context still
# needs one-at-a-time locked replay and append-only forward-paper ablation.
#
# ## Live Signal Contract
#
# - Supported canonical matrix: 8 assets x 7 timeframes = 56 selections.
# - The service replays the chart window plus 1,922 hidden warm-up bars instead
#   of materializing millions of one-minute outputs.
# - Phase-adjusted participation uses a separate indicator-dependent hidden
#   context (31,872 bars at 1m, 6,528 at 5m, and 2,304 at 15m). Those rows are
#   never exported as candles and do not enlarge the legacy CUSUM/EWMA/HMM
#   replay. Longer chart timeframes retain the 1,922-bar warm-up.
# - Crypto requires exact continuous cadence. Futures/FX carry recursive state
#   across a non-nominal gap only when the incoming canonical row is explicitly
#   marked `is_session_open_bar` and the closure is at most four days.
# - A five-second ingestion lag protects the just-closed boundary.
# - Bar `t` updates state only after close. Historical signals use nominal
#   `t+1`; the cross-timeframe live tail also incorporates append-only
#   first-seen observation time. Price markers align to the first observed
#   executable candle at or after availability.
# - Historical revisions replay the bounded context. The chart is therefore a
#   current-canonical diagnostic vintage, not an append-only as-was-live PnL
#   backtest. The UI keeps this warning visible.
# - Raw/provider sources remain debug paths and use bounded request replay;
#   persistent live state is canonical-only. Because raw session feeds do not
#   carry canonical calendar flags, gaps up to four days are inferred from
#   timestamp spacing and labeled `debug_only`/unverified in payload metadata.
#   Feeds shorter than 193 closed bars show the available fast/medium trend
#   components plus an explicit Prototype Regime warm-up message.
#
# ## 1m Causal Replay and Indicator Optimization
#
# - Every canonical asset/timeframe selection can now be replayed from its
#   canonical 1m source. A UTC-anchored target candle is updated once per real
#   source minute and committed only at its scheduled bucket end.
# - CUSUM, EWMA volatility, and volatility-scaled trend share one causal
#   closed-candle decision path. The fixed untrained prototype regime is
#   visualization-only by default; it can veto execution only through the
#   explicit experimental optimizer ablation. Orders fill at the first eligible
#   real 1m open, never on the generating close.
# - The normalized ledger applies explicit fee and adverse-slippage assumptions
#   and exposes fills, position, equity, drawdown, turnover, and breakeven cost
#   on the chart. Synthetic gap-fill minutes are excluded from both signal
#   input and execution because their historical inference time is not stored.
# - `Walk-forward Optimize` searches a small predeclared grid across all four
#   indicator components, uses chronological development folds at 2x costs,
#   keeps the latest 20% as an untouched holdout, and appends every trial to a
#   JSONL registry. A pass is eligible only for forward paper trading.
# - This remains a current-canonical normalized research replay. Existing
#   parquet files lack first-seen/revision timestamps, and the cost model lacks
#   complete contract multipliers, rolls, funding, borrow, spread history, and
#   market impact. Results are not as-was-live evidence and cannot guarantee
#   profitable trading.
#
# ## Protected CUSUM Trades and Meta-Label Research
#
# - `Static stop / take profit` is an explicit opt-in replay experiment. A
#   causal risk unit is frozen from the wider of slow EWMA price volatility and
#   the prior-only CUSUM residual scale. The stop, target and timeout are then
#   activated from the actual adverse next-open fill and evaluated on finalized
#   real 1m bars. Timeout counts accepted finalized candles in the selected
#   timeframe. After fill, the bracket owns the position until terminal; later
#   strategy reversals cannot cancel it. A same-minute stop/target touch remains
#   `AMBIGUOUS`, with stop-first execution used conservatively.
# - Every fresh CUSUM bull/bear setup also enters an independent shadow event
#   book, even when the portfolio already has a position. TARGET, STOP, TIMEOUT
#   and AMBIGUOUS outcomes become trainable only at `label_known_at`; cancelled
#   and end-of-window pending/active events remain unlabelled and are counted.
#   Forward paper uses journaled actual observation time. Historical canonical
#   replay cannot reconstruct first-seen time, so its v2 study declares a
#   nominal-close-plus-5-second scenario and applies a 24-hour research embargo;
#   it is not as-was-live or deployment evidence.
# - The first secondary model is an L2 logistic meta-label baseline estimating
#   `P(TP before SL and net positive)`. CUSUM still chooses the side. The model
#   may only reject a proposed entry, and the experimental gate requires the
#   stored probability to be strictly above both its frozen model threshold and
#   the decision-time static-stop break-even estimate plus a locked safety
#   margin. The estimate is a versioned approximation using the proposed
#   stop/target geometry and declared non-embedded costs, not a profitability
#   forecast. The model cannot widen a stop, increase risk or block a protective
#   exit.
# - The 32-feature v2 schema is side-normalized and uses causal CUSUM, trend,
#   volatility, path-quality and declared trade geometry. Its timeout feature
#   represents the declared accepted-finalized-candle horizon in minutes. The
#   fixed untrained Prototype Regime/HMM values are deliberately excluded from
#   model confidence.
# - The first all-selection v1 artifact is rejected as deployment evidence
#   after the execution/label-clock audit. The corrected 180-day v2 candidate
#   has 65,096 mature events and improves pooled OOF Brier/log loss/PR-AUC over
#   the causal base-rate control, but it remains unpromoted with an empty exact
#   deployment scope. Session assets have causal rows at 1m/15m only; 1h+
#   selections remain zero-row because the current provider-inferred calendar
#   cannot certify sparse buckets or closed-session gaps.
# - Training uses global decision time across the selected asset/timeframe
#   scope. A row can enter a fold only when its decision and terminal label were
#   both known strictly before validation began. Imputation and scaling are fit
#   inside each training fold. Candidate probabilities are compared with a
#   causal training-prevalence forecast using Brier score, log loss and PR-AUC.
# - Candidate artifacts are immutable, checksummed JSON coefficient files. The
#   trainer never promotes one, changes an environment variable, enables a
#   chart gate or routes an order:
#
#   python scripts/analysis/train_analyst_cusum_meta_model.py \
#     --end 2026-07-10T21:00:00Z \
#     --assets BTCUSDT ETHUSDT CL ES EURUSD GC NQ USDJPY \
#     --timeframes 1m 15m 1h 4h 8h 12h 1d \
#     --historical-label-embargo-hours 24
#
# - Historical charts accept an artifact only through the server-side
#   `RISKYIELDMM_META_ARTIFACT` setting. Event-time validation prevents a newly
#   trained model from being painted onto older CUSUM events as if its score had
#   existed then.
# - Delayed live scoring is separately opt-in. Set the absolute candidate path
#   in `RISKYIELDMM_FORWARD_META_ARTIFACT` before starting a new forward-paper
#   cohort. The service journals one immutable prediction per fresh setup and
#   resolves shadow labels after finalized 1m data, but never changes the
#   existing paper orders or positions. Leave this unset until an artifact has
#   been reviewed; real-order routing remains absent.
#
# The complete causal target, validation, calibration and rollout boundaries
# are recorded in:
#
# - `../docs/research/cusum_meta_label_trade_filter_research_2026-07-13.md`
# %%
import sys
from pathlib import Path

ANALYST_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ANALYST_ROOT.parent

if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_export import export_ohlcv_payload  # noqa: E402

# %%
# Generate the default payload consumed by `web/index.html`.
#
# Keep `max_bars` bounded. Multi-year 1m files are too large for direct browser
# rendering; export a recent or date-bounded inspection window instead.
payload_meta = export_ohlcv_payload(
    asset="BTCUSDT",
    timeframe="1h",
    source="canonical",
    max_bars=5_000,
    indicators=(
        "cusum_trend",
        "ewma_volatility",
        "volatility_scaled_trend",
        "online_regime",
        "prior_structure",
        "comparable_volatility",
        "phase_adjusted_participation",
    ),
)
payload_meta  # noqa: B018

# %%
# Preferred: serve the interactive chart viewer with the local API server.
#
# python Risk_Yield_Meta_Model_Analyst_0_0_1/chart_server.py --port 8765
#
# Then open:
# http://localhost:8765
#
# The browser UI can select asset, dataset, timeframe, indicators, UTC
# start/end, and max bars. Canonical parquet remains the historical base; with
# no fixed End value, the server layers finalized first-seen rows from the
# append-only forward-paper journal before calculating indicators and enforcing
# the hard max-bar safety limit. `Live refresh` polls that merged view every 30
# seconds. Explicit End and raw/debug requests remain deterministic snapshots.
# The canonical-only `1m causal replay` panel runs an explicit manual snapshot
# with fee, slippage, full-spread scenario, execution latency, and bounded audit
# evidence. It plots replay fills plus equity/drawdown/position or launches the
# bounded chronological optimizer. It does not auto-refresh or silently turn an
# optimizer result into a forward-paper strategy.
# The viewer does not fetch exchange data itself. Root `update_data.py` now
# owns a separate append-only forward-paper service:
#
#   python update_data.py --live-start
#   python update_data.py --live-status
#   python update_data.py --live-stop
#   python update_data.py --live-start --live-strategy-manifest <accepted-result.json>
#
# It fans each first-seen finalized 1m row into all 56 asset/timeframe streams
# and writes provider grade plus normalized forward metrics to the paper panel.
# Each stream is an independent shadow experiment with equity 1.0; the 56
# ledgers are not a capital-netted portfolio or a venue order-management system.
# Bybit BTC/ETH are labelled `live`; the six Yahoo front-futures fallbacks are
# explicitly labelled `delayed` until a licensed Databento Live adapter is
# configured. Signal eligibility uses actual observation time, so delayed bars
# never receive a fill at an already-passed open. Real-order routing is absent.
#
# Historical validation currently rejects the default signal mapping: 13 of 14
# BTCUSDT/ES baseline selections were negative after 1 bp fee + 1 bp slippage,
# and the only positive selection had just four round trips. The forward cohort
# therefore runs as `historical_optimizer_rejected_observe_only`; it collects
# new evidence but is not eligible for live capital or a profitability claim.
#
# Offline/static fallback:
# - regenerate `web/data/current.json` with `export_ohlcv_payload(...)`
# - serve with `python -m http.server 8765 --directory Risk_Yield_Meta_Model_Analyst_0_0_1/web`

# Risk Yield Meta Model Analyst

This directory is the local decision-support, causal replay, and forward-paper
workspace for RiskYieldMM. It is intentionally a repository-local application,
not part of the installable `riskyieldmm` protocol package.

## Current status

- Canonical OHLCV is the primary chart source; provider/raw sources are debug
  views.
- The UI supports multiple simultaneous causal indicator layers across the
  configured 8 assets and 7 canonical timeframes.
- Historical replay fills only after a completed signal bar and models declared
  fees, spread/slippage, and latency assumptions.
- Forward paper trading journals first-seen finalized observations but does not
  route real orders.
- Current replay and model candidates are research evidence only. They are not
  certified profitable or eligible for live capital.

The immutable cross-system event/protocol foundation is documented in
[`../docs/architecture/trading_event_v3_contract.md`](../docs/architecture/trading_event_v3_contract.md).
It is not yet wired into these legacy Analyst records; that migration must be a
separate shadow-comparison gate.

## Run the chart workspace

From the repository root:

```bash
python Risk_Yield_Meta_Model_Analyst_0_0_1/chart_server.py --port 8765
```

Then open <http://localhost:8765>. The server reads bounded canonical windows
and serves the dynamic API. It does not require a checked-in
`web/data/current.json`.

`main.py` is a notebook-style inspection entry point. Running it regenerates a
bounded static `web/data/current.json`, which is deliberately ignored and can
be removed at any time.

Forward-paper controls live in the root updater:

```bash
python update_data.py --live-start
python update_data.py --live-status
python update_data.py --live-stop
```

Runtime journals use `RISKYIELDMM_STATE_DIR` or the platform XDG state
directory. They must not be committed as source.

## Component map

| Path | Responsibility |
|---|---|
| `chart_config.py` | Asset, source, timeframe, and chart defaults |
| `chart_export.py` | Bounded OHLCV loading and indicator/chart payload construction |
| `chart_server.py` | Local API and static UI server |
| `online_signals.py` | Causal closed-bar signal state |
| `market_context.py` / `multi_timeframe_context.py` | Prior-only structural and cross-timeframe context |
| `minute_replay.py` | One-minute candle construction and replay execution |
| `indicator_optimizer.py` | Bounded walk-forward indicator-policy experiments |
| `forward_paper/` | First-seen sources, event journals, service, stream, and supervisor |
| `trade_ml/` | Current CUSUM meta-label research contracts, features, training, inference, and shadow evaluation |
| `web/` | Lightweight Charts user interface |

## Safety boundaries

- Only finalized bars may update signals.
- Higher-timeframe context must use completed higher-timeframe observations.
- Historical canonical files are current-revision data, not proof of what was
  first observed in the past.
- The prototype regime/HMM layer is descriptive and uncalibrated.
- Optimizer results never auto-promote into paper or live execution.
- The current paper engine is a collection of shadow streams, not a capital-
  netted portfolio or venue order-management system.
- No component in this directory sends real broker or exchange orders.

See
[`../docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md`](../docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md)
for the audited limitations and ordered implementation roadmap.

## Verification

The application is covered by `tests/test_analyst_*.py`. Ingestion and
canonical-candle changes are additionally covered by:

- `tests/test_core_update_data.py`
- `tests/test_fetch_bybit_market_data.py`
- `tests/test_canonical_ohlcv_materializer.py`
- `tests/test_htf_trading_calendar.py`

Generated chart payloads, runtime journals, Python caches, and optimizer trial
logs are disposable. Research reports and `docs/validation/` artifacts are
versioned evidence and must not be treated as cleanup debris.

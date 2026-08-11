# Meta Model Analyst: Predictive Indicator Research and Next-Slice Decision

**Date:** 2026-07-10
**Scope:** Identify causal indicators and state variables worth exposing in
`Risk_Yield_Meta_Model_Analyst_0_0_1`, and distinguish useful visual diagnostics
from features that deserve a new walk-forward model experiment.

## Decision

Do **not** add a broad library of familiar technical indicators and assume it
improves predictions. The repository already contains most of those signal
families. The next work should instead be:

1. add a **causal EWMA / realized-volatility diagnostic** to the Analyst;
2. expose the existing **HMM and recursive change-risk artifacts** rather than
   fitting a disconnected chart-time HMM; and
3. run a small, pre-registered ablation for only the genuinely incremental
   volatility features: multi-half-life EWMA variance, HAR-RV forecast, and
   volatility-scaled momentum.

The first two improve observability immediately. The third is the only route
that can establish predictive uplift. None should be called predictive alpha
until it passes the specified out-of-sample test.

## Why the distinction matters

An indicator can have three different roles:

| Role | Example | Success criterion |
|---|---|---|
| Visual diagnostic | EWMA trend/volatility pane | Explains a market state and agrees with causal artifacts. |
| Model feature | Fast/slow EWMA-vol ratio | Improves frozen walk-forward metrics versus the current feature panel. |
| Risk gate / uncertainty signal | HMM posterior entropy or conformal set width | Reduces false positives at an acceptable coverage cost. |

The strongest literature case is for forecasting volatility and using regime or
uncertainty as *context* for a directional model. It is not evidence that an
HMM, an EMA crossover, or an oscillator alone predicts the next price move.

## Repository reality

The proposed work must reuse the current data and model layers where possible.

| Capability | Current state | Implication |
|---|---|---|
| Analyst UI | Only OHLCV and a Pine-port CUSUM Trend overlay are wired into `chart_export.py` / `web/app.js`. | Add an artifact-reader layer before adding another independent model. |
| EWMA state | `regression_feature_engineering/features/temporal_memory_transforms.py` emits prior-row EWM state, slope, and residual features for spans 16 and 64. | A plain EWMA is not a new production feature family; a volatility forecast and a visual diagnostic may be incremental. |
| Price EMA gate | `walkforward/ema_regime.py` safely compares the current price with a closed EMA200. The corresponding classifier path is explicitly `abandoned_active_path` in `rpf_ema_regime_batch_selection.md`. | Do not restart an EMA200-only gate. |
| Volatility and helper signals | The active helper cache includes OU, GARCH, CUSUM, Kalman, and EGARCH outputs; RPF also has causal volatility, range, and EWM families. | Start by rendering these artifacts, then benchmark a small new RV/HAR block against them. |
| HMM / change risk | The 2026-07-01 RPF diagnostic has causal-forward HMM filtering, prior-only scaler/PCA/model selection, recursive market CUSUM, and HMM-transition CUSUM. | Surface these outputs; do not fit full-history/smoothed HMM states in the browser. |
| Volume and liquidity | `liquidity_volume_pressure.py` already implements relative volume, dollar-volume, wake-up, OBV slope, money-flow balance, and zero-volume state. | Expose the small, interpretable subset before inventing another volume oscillator. |
| Uncertainty | The target-model calibration stack already includes conformal intervals, classification sets, ACI, and coverage monitoring. | A confidence/interval overlay is a high-value Analyst addition even though it is not a technical indicator. |

The latest causal HMM diagnostic is:

```text
test_output/rpf_ranked_signal_regime_diagnostic/
  20260701_064045_rank_signal_regime_diagnostic/
```

It used 240 prediction-safe market-context windows and 140 market-context
inputs. Its recursive market-CUSUM event rate was 21.7%, inside the configured
5--25% diagnostic target; the simple z-shift detector fired on 83.3% of windows
and is therefore diagnostic-only. The HMM/gate result is promising but not
promoted: a prequential replay weakened one of the Rocket candidates. That is
exactly why it belongs in the Analyst first, then in a constrained shadow test.

## Ranked research shortlist

### P0 — EWMA volatility plus realized-volatility forecast

**Recommendation:** add this next as an Analyst pane and as one minimal
model-ablation family.

Compute after bar `t` closes:

```text
ewma_var_h(t) = lambda_h * ewma_var_h(t - 1)
                + (1 - lambda_h) * r_t^2
ewma_vol_h(t) = sqrt(ewma_var_h(t))
```

Start with half-lives expressed in bars, for example `12`, `48`, and `192`,
then select them inside walk-forward training only. Do not transplant the
RiskMetrics daily decay parameter into intraday crypto or futures without a
test.

Export a small, non-redundant feature block:

- `ewma_vol_fast`, `ewma_vol_medium`, `ewma_vol_slow`;
- `log_ewma_vol` and `vol_ratio_fast_slow`;
- standardized return `r_t / ewma_vol_{t-1}`;
- realized variance from complete lower-timeframe returns;
- a HAR-RV one-step forecast and its surprise,
  `log(realized_vol / har_rv_forecast)`.

This is a risk/dispersion feature family, not a directional signal by itself.
It can improve a directional model through normalization, volatility-regime
interactions, calibrated thresholds, and position/risk decisions.

**Evidence.** RiskMetrics provides the canonical exponentially weighted
variance formulation. Andersen, Bollerslev, Diebold, and Labys show that
realized-volatility forecasts can provide calibrated return-density and
quantile forecasts. Corsi's HAR-RV gives a compact multi-horizon volatility
baseline. See [RiskMetrics Technical Document](https://faculty.runi.ac.il/kobi/riskmgt/rmtd.pdf),
[Andersen et al. (2003)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00418),
and [Corsi (2009)](https://doi.org/10.1093/jjfinec/nbp001).

### P0 — Artifact-backed HMM regime and recursive change-risk panel

**Recommendation:** add it to the Analyst next, but do not add a new HMM
training path.

The visual payload should read timestamp/batch-aligned outputs from the
existing RPF diagnostic and show:

- `regime_state_key` plus a human-readable state profile;
- forward-filtered posterior probabilities and entropy;
- state duration / transition rarity;
- `has_market_context_recursive_cusum_v1`;
- `has_hmm_transition_cusum_v1`; and
- the direct HMM state-change marker separately.

HMMs are appropriate when treated as latent-state probabilities and model
context. They must be train-history-only and forward-filtered. Full-sample
Viterbi paths or smoothed posteriors use future observations and must never
appear as prediction-time features. State labels also need canonicalisation by
training-set profile rather than raw state ID.

**Evidence.** Markov switching provides the latent-state framework; online
change-point detection can estimate a current run length without retrospective
segmentation. See [Hamilton (1989)](https://doi.org/10.2307/1912559) and
[Adams & MacKay (2007)](https://arxiv.org/abs/0710.3742). The repository's own
latest diagnostic is more relevant than a generic example: its results are
mixed enough that HMM should currently be a monitored suppression/context
candidate, not a direct Buy/Sell indicator.

### P1 — Volatility-scaled multi-horizon trend and reversal

**Recommendation:** test as a small interaction block only after the P0
volatility baseline.

Use log-return horizons, an EWMA fast/slow spread and slope, all divided by an
EWMA or range-volatility estimate. Keep short-horizon residual/reversal
features distinct from long-horizon trend:

```text
trend_h        = return_h / ewma_vol_h
trend_spread   = (ewma_fast_price - ewma_slow_price) / ewma_vol
reversal_short = (close - ewma_price_fast) / ewma_vol
```

The repository already has trend efficiency, acceptance/persistence, PPO,
ROC, RSI/Stochastic, ADX/DI, and EWM transforms. The experiment must therefore
prove incremental value over those existing families, rather than add a second
copy under a different name.

Time-series momentum is a credible broad empirical regularity across futures,
but its 1--12 month evidence does not guarantee intraday alpha. Treat it as a
hypothesis to test by asset and timeframe. See [Moskowitz, Ooi & Pedersen
(2012)](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf).

### P1 — Price-volume and liquidity confirmation

**Recommendation:** expose this immediately as a pane; keep a new
Amihud/jump-price-impact proxy as a small model experiment.

Useful causal chart series are relative volume, signed-volume proxy,
dollar-volume/turnover, OBV slope, money-flow balance, and volume wake-up after
compression. For assets with reliable dollar volume, test:

```text
amihud_t = abs(return_t) / dollar_volume_t
```

The raw crypto schema contains turnover, but the current Analyst OHLCV scan
does not export it. Futures volume needs a documented contract multiplier and
must not be treated as dollar volume blindly. Candle-sign times volume is a
proxy, not genuine trade-signed order flow.

Past volume has been found to condition momentum persistence, and the Amihud
ratio is a practical long-history illiquidity proxy. See [Lee & Swaminathan
(2000)](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00280) and
[Amihud (2002)](https://www.sciencedirect.com/science/article/abs/pii/S1386418101000246).

### P1 — Predictive uncertainty and selective action

**Recommendation:** add conformal interval/set width and calibrated model
confidence as the first model-artifact overlay.

This will not increase raw directional accuracy. It can raise accuracy and
reduce false positives *conditional on taking a signal* by abstaining when the
prediction set is wide or coverage is unreliable. That is aligned with the
project's risk-first objectives and existing conformal stack.

Adaptive conformal inference is designed to respond to distribution shift, and
selective classification formalises the accuracy-versus-coverage trade-off.
See [Gibbs & Candès (2021)](https://papers.neurips.cc/paper_files/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html)
and [Geifman & El-Yaniv (2017)](https://arxiv.org/abs/1705.08500).

### P2 — Jump/continuous volatility and BOCPD

**Recommendation:** defer until P0 features have a stable benchmark.

Complete lower-timeframe bars can support realized variance, bipower variation,
and a jump proxy. They may add information beyond a simple EWMA, but require
careful session/calendar handling. BOCPD can later supply a causal change
probability and expected run length. Do not use retrospective breakpoint
algorithms as live features.

### P2 — Cross-asset relative strength and breadth

The multi-asset panel enables cross-asset percentile ranks of volatility-scaled
returns and breadth (% assets with positive trend). It is worth a separate
experiment because the eight assets are heterogeneous and have different
trading calendars. All joins must be backward-asof and respect the availability
of each source bar.

## Explicit non-priorities

- **EMA200 as a new classifier gate:** already evaluated and abandoned on the
  active RPF path.
- **A pile of RSI/MACD/Stochastic variants:** the project already has closely
  related trend, oscillator, range, and EWM features. This would increase
  redundancy and multiple-testing risk.
- **Full-history HMM or retrospective change points:** prediction leakage.
- **GARCH/EGARCH as a new default:** helper outputs already exist. Benchmark
  them against EWMA/HAR before changing the active feature panel.
- **A raw HMM Buy/Sell overlay:** regime probabilities are context, not an
  automatically directional signal.

## Analyst implementation order

1. **EWMA / realized-volatility pane**
   - Short/medium/long EWMA volatility lines or a lower pane.
   - Fast/slow volatility ratio, volatility surprise, and a volatility-CUSUM
     marker.
   - Optional price EWMA trend lines strictly as an explanatory overlay.

2. **Existing helper and RPF artifact adapter**
   - Resolve `htf_with_helpers`, RPF, prediction, and diagnostic artifact paths
     separately from raw/canonical OHLCV.
   - Join only through timestamp and closed-bar/batch availability metadata.
   - Export source path, generation run, and availability time in payload
     metadata.

3. **HMM/change-risk panel**
   - Display the existing causal HMM posterior/state/entropy and explicit
     change flags as a timeline or lower pane.
   - Show raw state IDs only alongside canonical keys/profile labels.

4. **Prediction and uncertainty overlay**
   - Add model score, action, interval/set width, calibration state, and
     eventually realised outcome to one traceable payload.

5. **Volume/liquidity pane**
   - Begin with existing relative volume, volume-pressure balance, and
     money-flow/OBV features.

For every stateful chart indicator, load sufficient historical warm-up before
the requested window and trim it after calculation. Computing EWMA, CUSUM, or
HMM state independently for every lazy-loaded page causes boundary artifacts
and is not an acceptable visualisation of a causal signal.

## Minimal experiment contract

Freeze the current best feature panel and define three candidate blocks before
running anything:

```text
A: multi-half-life EWMA volatility / ratio / standardized-return block
B: HAR-RV forecast / surprise block
C: volatility-scaled multi-horizon trend block
```

Evaluate baseline, `+A`, `+B`, `+C`, and only then `+A+B+C`. Do not tune the
feature list after viewing the final test block.

For a prediction made after close `t`, use only values available through close
`t` and execute no earlier than `t+1`. Train scalers, HMMs, thresholds, state
ordering, and hyperparameters within each historical training window. Use only
complete lower-timeframe bars for higher-timeframe realized volatility and an
embargo at least as long as the forward label horizon.

Report per asset, timeframe, and volatility regime:

- primary directional loss/calibration and precision, FDR, coverage;
- target-specific regression metrics where applicable;
- QLIKE and log-volatility error for volatility forecasts;
- net-of-cost PnL, turnover, drawdown, and signal frequency; and
- the distribution of improvements across chronological test blocks, not only
  pooled averages.

Candidate selection must account for the number of tried variants. White's
Reality Check is the appropriate reminder: repeated searches over one market
history can make a chance result look predictive. See [White (2000)](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152).

## Bottom line

**Yes: add EWMA next, but specifically as EWMA volatility / volatility-scaled
trend with a locked ablation.**

**Yes: add HMM next to the Analyst, but as a viewer for the existing causal
diagnostic artifacts—not as a new full-sample chart calculation.**

The immediate highest-value build is therefore:

```text
EWMA/RV pane -> existing HMM + recursive-CUSUM panel -> prediction/conformal
overlay -> locked incremental feature ablation
```

## Live implementation follow-up

The user subsequently chose a live-first implementation rather than a viewer
bound to the historical May HMM artifact. The Analyst now uses a separate,
explicitly diagnostic online method:

```text
closed source bar t
-> prior-volatility-scaled trend/path-quality observation
-> fixed-prototype four-state Gaussian HMM forward update
-> plot at the t+1 availability/execution timestamp
```

This is not the RPF HMM and it is not trained predictive alpha. Its four
emission prototypes and transition probabilities are versioned diagnostic
defaults. The implementation never runs forward-backward smoothing or Viterbi
decoding, so appending future observations cannot revise an earlier posterior.

The live contract now covers the full canonical matrix:

```text
8 assets x 7 timeframes = 56 canonical selections
BTCUSDT, ETHUSDT, CL, ES, EURUSD, GC, NQ, USDJPY
x 1m, 15m, 1h, 4h, 8h, 12h, 1d
```

The scalable replay/cache rules are:

- replay the bounded chart window plus 1,922 hidden warm-up bars rather than
  materializing millions of one-minute output rows;
- key live state by asset, timeframe, source, algorithm version, and config
  digest, with a bounded LRU cache;
- append only when the prior bounded input is an exact prefix; replay after a
  revision or a rolling-window origin change;
- use the same scalar update for replay and newly finalized bars;
- apply a five-second ingestion safety lag;
- place signal points at the nominal next-bar availability time;
- align price markers to the first observed candle at or after availability;
  and
- poll for committed source changes every 30 seconds when the chart has no
  fixed End boundary.

Cadence handling is calendar-aware. Crypto canonical streams require exact
continuous cadence. For futures and FX, recursive state carries over a
non-nominal delta only when the incoming canonical row has
`is_session_open_bar=True`, the delta is interval-aligned, and it is no longer
than four days. An unflagged discontinuity resets state and restarts warm-up.
This matters because all observed futures/FX overnight and weekend deltas are
explicit session openings; resetting on every wall-clock gap would prevent the
192-bar slow signal from ever warming on most timeframes.

Persistent service state is canonical-only. Raw/provider files remain debug
inputs and receive a bounded request replay, avoiding pathological per-request
snapshotting of very large raw file sets. Raw session feeds lack canonical
calendar flags, so their bounded replay infers a possible session opening only
from an interval-aligned timestamp gap of at most four days. Payload metadata
labels this policy `bounded_timestamp_gap_inference_debug_only`; canonical data
remains the authoritative signal view.

Historical revisions are intentionally replayed from the current canonical
source. That preserves causal calculations but does not preserve the signal
that was first issued in real time. Payloads and the UI therefore declare:

```text
signal_vintage = current_canonical_replay
validation_safe = false
as_was_live_journal = false
```

These charts are suitable for visual diagnostics, not PnL validation or model
gating. A future append-only first-issued journal is required for genuine
as-was-live backtesting. The regime weights are also untrained prototypes, not
calibrated confidence.

Finally, the service does not download market data. At the 2026-07-11 audit,
all canonical streams ended on 2026-07-09, and the UI correctly marked the
source stale. Real-time updates depend on the upstream canonical materializer
committing newly closed bars.

The viewer does not ingest exchange data itself. `update_data.py` or another
upstream writer must keep canonical OHLCV current. The UI reports the source as
stale when its latest closed timestamp is more than 2.5 chart intervals old.

Before this online regime layer can become a model feature or trade gate, its
prototype parameters must be selected inside training folds and tested through
the same frozen walk-forward ablation and multiple-testing controls described
above.

# Research Feature Signal Backlog

## Purpose

Translate the local research notes into a concrete backlog of candidate signals
for `regression_path_features_v1`.

## Current Status

Research backlog and coverage tracker. Implemented entries are still not
promoted by this document; promotion requires walk-forward ablation and the
optimization gates in `optimization_strategy.md`.

## Scope

Applies to `distance_horizon_vol_v2` regression targets, starting with
`BTCUSDT 8h/B` and later expanding to root IDs `8h_b`, `8h_c`, `24h_b`,
`24h_c`, `7d_b`, and `7d_c`.

## Source Of Truth

- Research inputs: `regression_feature_engineering/research/features-1.md`
  and `regression_feature_engineering/research/features-2.md`
- Active taxonomy: `feature_taxonomy.md`
- Current HTF inventory: `htf_feature_helper_inventory.md`
- Temporal contract: `data_contract.md`
- Optimization contract: `optimization_strategy.md`

## What This Does Not Decide

This document does not choose final formulas, thresholds, parameter windows, or
feature promotion. It records candidate signals that still need causal
implementation, quality checks, ablation, and walk-forward validation.

## Research Conclusions To Preserve

The two research notes add four practical requirements to the current
regression design:

- use closed higher-timeframe bars only, joined to 1m rows by backward-looking
  as-of logic;
- normalize every price-distance signal into percent, volatility, z-score,
  rank, or bounded oscillator form before model use;
- add cross-asset features as relative pressure, spread, factor, and lead-lag
  signals, not raw foreign prices;
- validate every family by walk-forward ablation, chronological stability, and
  target-specific usefulness.

The useful feature surface for the four distance targets is therefore not just
direction. It must explain path shape:

- `target_reg_distance_up_extreme_hvol_v2`: upside spike/reach capacity.
- `target_reg_distance_up_mean_high_hvol_v2`: sustained upside acceptance.
- `target_reg_distance_down_mean_low_hvol_v2`: sustained downside acceptance.
- `target_reg_distance_down_extreme_hvol_v2`: downside spike/reach capacity.
- `target_reg_direction_extreme_up_share_hvol_v2`: bounded extreme-path
  directional balance.
- `target_reg_direction_mean_up_share_hvol_v2`: bounded persistent-path
  directional balance.

## Temporal Safety Rules

All candidate signals must satisfy these rules before implementation:

- compute from canonical local bars only;
- use only closed bars available at the prediction timestamp;
- join higher-timeframe values to 1m rows with backward-looking as-of semantics;
- never use the currently forming higher-timeframe candle unless it is exposed
  as an explicitly partial real-time feature in a later version;
- for session assets, skip closed sessions and use market-open canonical rows;
- fit rolling standardization, clipping, PCA, beta, cointegration, and
  lead-lag parameters from past data only.

## Candidate Signal Families

## Generic Feature-Type Coverage

This section maps the generic time-series feature search list to the active
`regression_path_features_v1` plan. It exists to prevent useful feature classes
from being implied but not tracked.

| Generic Type | Current Coverage | Status |
|---|---|---|
| lags | closed-bar as-of context plus `temporal_memory_transforms` | engineering_validated_not_promoted; BTCUSDT `8h/B` sliced validation clean |
| rolling means | volatility state, structural value, acceptance value/share windows | engineering_validated_not_promoted for implemented families |
| rolling standard deviations | `tb_volatility_pct`, realized-vol inputs, volatility-state windows | engineering_validated_not_promoted |
| EWM means | `temporal_memory_transforms` | engineering_validated_not_promoted; BTCUSDT `8h/B` sliced validation clean |
| differences, returns, slopes | closed-bar returns, return persistence, trend efficiency, cross-asset spreads | engineering_validated_not_promoted / planned depending on family |
| z-scores and rank-position proxies | volatility z/relative-median plus `temporal_memory_transforms` rank-position state | engineering_validated_not_promoted |
| ratios and spreads | ATR/std dominance, room asymmetry, return/vol spreads, cross-asset spreads | engineering_validated_not_promoted / planned |
| distance-to-reference | structural room, value distance, band/VWAP/support/resistance candidates | engineering_validated_not_promoted plus planned refinements |
| regime flags | `regime_calendar_state` plus existing HTF helper regimes as context | engineering_validated_not_promoted |
| interaction/confluence features | `interaction_confluence` | engineering_validated_not_promoted |
| cross-series/context features | cross-asset relative context backlog | engineering_validated_not_promoted |
| calendar/session features | `regime_calendar_state` | engineering_validated_not_promoted |
| CNN/sequence embeddings | `sequence_embedding_layer` | deterministic proxy engineering-validated, not promoted; learned encoders deferred |

Priority for trading regression remains:

1. distance-to-band, value, VWAP, support, and resistance features;
2. volatility denominator and volatility-regime features;
3. trend/range and acceptance/rejection regime features;
4. reversal/bounce and failed-break features;
5. multi-timeframe context features;
6. interaction/confluence features after the base families are stable.

### 1. Multi-Timeframe Closed-Bar Context

Purpose: give each 1m row stable context from completed `15m`, `1h`, `4h`,
`8h`, `12h`, and `1d` bars.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| closed-bar return by timeframe | log or percent return of the last completed bar | direction axis for distance and share targets |
| closed-bar high-low range in horizon-vol units | realized range scaled by prediction-time volatility | extreme target scale and expansion risk |
| close location inside closed bar | `(close - low) / (high - low)` | acceptance versus rejection |
| body-to-range ratio | candle body divided by high-low range | directional pressure versus wick noise |
| multi-timeframe return slope | monotonicity of returns across short to long horizons | persistence targets |
| timeframe agreement count | number of horizons with same directional sign | mean high/low persistence |

Implementation note: these are not raw OHLCV columns. They are normalized
summary signals derived from closed bars.

### 1b. Temporal Memory Transforms

Purpose: describe how validated base signals behaved recently, without
creating every possible lag for every generated column.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| selected signal lag | prior value of a validated feature | persistence and delayed reaction |
| selected signal difference | current causal value minus prior causal value | acceleration or fading pressure |
| selected signal slope | normalized slope over prior rows | direction and persistence |
| EWM mean | past exponential average of a selected signal | smooth state without long hard windows |
| EWM residual | current signal minus past EWM state | unusualness and regime shift |
| rolling percentile rank | signal rank inside prior window | compression, stretch, and anomaly state |

Implementation note: this family must use a curated source list. Applying lags,
EWM, and ranks to every generated feature would create redundant noise and high
memory cost.

### 2. Volatility Denominator And Expansion State

Purpose: explain why the same raw move can become a small or large
`distance_horizon_vol_v2` target.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| ATR versus realized-vol dominance | whether ATR or return std drives `tb_volatility_pct` | all targets |
| volatility compression percentile | current volatility rank versus trailing history | extreme reach targets |
| volatility expansion rate | short-vol divided by long-vol, or vol ROC | spike and breakdown risk |
| range-vol mismatch | high-low range versus close-to-close volatility | wick/chop and future range expansion |
| expected horizon volatility proxy | causal estimate of next-window scale from past horizon windows | all targets |
| volatility exhaustion flag | current range already stretched versus prior windows | reduces future reach expectation |

Optimization focus: these signals should improve target scale calibration and
tail quantile ranking. They should not be raw volatility duplicates.

### 3. Structural Room And Price Location

Purpose: explain how much available room exists above and below the entry close.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| distance to previous rolling high | upside room to a closed resistance level | `target_reg_distance_up_extreme_hvol_v2` |
| distance to previous rolling low | downside room to a closed support level | `target_reg_distance_down_extreme_hvol_v2` |
| Donchian channel position | location inside closed rolling high-low channel | all targets |
| room asymmetry | upside room minus downside room in volatility units | direction and tail asymmetry |
| prior session high/low distance | session-aware structure distance | session assets and daily path targets |
| VWAP/value distance | distance from current close to session or rolling value | acceptance and rejection |
| pivot distance | distance to prior closed pivot levels | breakout/breakdown proximity |

Implementation note: breakout levels must use previous channels or previous
session levels. Current-bar highs/lows cannot define a level used by the same
timestamp.

### 4. Acceptance And Persistence

Purpose: distinguish one spike from repeated future highs/lows beyond entry.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| closes above value count | recent closes above VWAP/EMA/local mean | `target_reg_distance_up_mean_high_hvol_v2` |
| closes below value count | recent closes below VWAP/EMA/local mean | `target_reg_distance_down_mean_low_hvol_v2` |
| shallow pullback score | directional trend with limited counter-move | mean targets |
| accepted breakout duration | time since price accepted beyond prior level | persistence after break |
| trend efficiency ratio | net move divided by path length | mean targets versus chop |
| directional close-location average | average close location near highs or lows | acceptance/rejection separation |
| higher-timeframe alignment score | agreement between 1m state and closed higher-timeframe state | mean targets |

Optimization focus: these signals are expected to help mean targets more than
extreme targets.

### 5. Spike, Breakout, And Breakdown Capacity

Purpose: identify conditions where one future high or low can travel far even
if the move does not persist.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| squeeze-release setup | low volatility followed by early range expansion | up/down extreme targets |
| breakout proximity | distance to previous upper channel or resistance | `target_reg_distance_up_extreme_hvol_v2` |
| breakdown proximity | distance to previous lower channel or support | `target_reg_distance_down_extreme_hvol_v2` |
| one-sided impulse score | large directional body plus range expansion | extreme targets |
| volume-confirmed impulse | impulse score confirmed by volume z-score | extreme targets |
| tail-risk asymmetry | upside wick potential versus downside wick potential | extreme target direction |

Implementation note: overlap with TA flags is acceptable only if the
regression feature carries calibrated distance/context rather than a binary
entry signal.

### 6. Rejection, Chop, And Two-Sided Path Risk

Purpose: identify paths where extremes may be high but direction is noisy, or
where mean targets should be lower because price rejects quickly.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| upper rejection score | upper wick plus failed close above value | lowers sustained upside, may raise upside extreme |
| lower rejection score | lower wick plus failed close below value | lowers sustained downside, may raise downside extreme |
| two-sided volatility ratio | high-low range versus absolute return | both extreme targets, lower persistence confidence |
| reversal count | number of sign changes in recent returns | chop risk |
| path entropy | dispersion of recent directional signs | chop risk |
| failed breakout count | breaks of prior level that close back inside | rejection and mean-target suppression |
| realized path efficiency | net displacement divided by cumulative movement | persistence versus noise |

Optimization focus: these signals should help the model distinguish high
extreme targets from high mean targets.

### 7. Cross-Asset Relative Context

Purpose: add broad pressure, relative strength, and risk state without using raw
foreign price levels.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| target versus context return spread | target return minus correlated asset return | relative pressure |
| log price ratio z-score | normalized pair ratio, for example BTC/ETH or ES/NQ | spread extension/reversion |
| rolling beta residual | target return minus beta-adjusted context return | idiosyncratic pressure |
| pair cointegration residual | distance from long-run pair equilibrium when valid | reversion and room |
| lead-lag shifted returns | past context returns at validated lags | directional pressure |
| cross-asset volatility factor | common volatility mode across selected assets | range expansion |
| PCA or factor components | group-level risk mode from standardized returns | broad market state |

Candidate asset groups:

- crypto: `BTCUSDT`, `ETHUSDT`;
- equity index futures: `ES`, `NQ`;
- FX: `EURUSD`, `USDJPY`;
- commodities: `GC`, `CL`;
- all-core risk factor: standardized returns and volatility across all core
  assets.

Implementation note: cointegration, PCA, beta, and lead-lag parameters must be
fit on historical training windows only or on strictly prior rolling windows.
They cannot be estimated globally and then reused inside walk-forward tests.

### 8. Session, Calendar, And Market-Open State

Purpose: explain path distance differences caused by market schedule and
liquidity timing.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| session progress | normalized position inside current session | all session assets |
| minutes to close/open | proximity to session boundary | spike and volume behavior |
| opening range position | location versus first session window | structure and breakout |
| prior session range | previous full session high-low in volatility units | room and expansion |
| day-of-week cyclic encoding | weekly seasonality without ordinal jumps | all assets |
| hour-of-day cyclic encoding | intraday seasonality | all assets |
| weekend gap context | crypto/FX boundary behavior where applicable | longer roots |

Implementation note: calendar features are allowed because they are known at
prediction time. Closed sessions must not be filled with artificial rows.

### 9. Liquidity And Volume Pressure

Purpose: measure whether movement has enough participation to travel or persist.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| volume z-score by timeframe | participation relative to recent history | impulse and persistence |
| dollar-volume proxy | normalized turnover when price and volume are available | liquidity state |
| volume-on-up versus down bars | simple pressure proxy from OHLCV only | directional pressure |
| OBV or money-flow slope | volume-confirmed direction | persistence targets |
| volume wake-up after compression | low-vol/low-volume state followed by volume increase | spike targets |
| session-volume percentile | current volume versus same session position history | session-aware expansion |

Implementation note: true order-flow imbalance requires data not currently in
the canonical OHLCV set. For v1, keep these as OHLCV-derived proxies.

### 10. Interaction And Confluence

Purpose: describe when multiple causal signals agree in a way that should
change the expected future path distance.

Candidate signals:

| Signal | Meaning | Target Use |
|---|---|---|
| compression plus breakout proximity | low volatility and price near prior high/low | extreme targets |
| trend plus acceptance | directional pressure confirmed by closes above/below value | mean targets |
| volume wake-up plus impulse | participation confirming directional movement | spike and persistence |
| room plus pressure | available path distance plus directional force | all directional targets |
| rejection plus chop gate | conditions that reduce mean-target confidence | mean versus extreme separation |
| TA compact confluence | optional agreement with deterministic TA flags | context only |

Implementation note: every confluence feature must be compared against its
component features. If the interaction does not add value beyond components, it
should be rejected or quarantined.

## First Implementation Priority

The first implementation should be small enough to validate cleanly on
`BTCUSDT 8h/B`:

1. Volatility denominator and expansion state.
2. Structural room above/below in horizon-vol units.
3. Acceptance/persistence from closed-bar close location and value distance.
4. Temporal memory transforms for a curated list of validated base signals.
5. Rejection/chop from wick, path efficiency, and two-sided volatility.
6. Spike/breakout and volume-pressure confirmation.
7. Regime/calendar state for session-aware behavior.
8. Interaction/confluence features after base families are stable.
9. Cross-asset relative return and volatility spread for BTC versus ETH.

This covers the distance-target needs and gives the two bounded share targets
the same causal directional and path-shape evidence without introducing global
PCA, cointegration, or lead-lag estimation too early.

## Signals To Defer

Defer these until the first causal feature layer validates:

- tick-level order-flow imbalance;
- live streaming watermarks and exactly-once state;
- global PCA/factor models across all assets;
- cointegration residuals promoted to production;
- dynamically inferred lead-lag features;
- partial in-progress higher-timeframe candle features.

These can be valuable, but they add implementation and temporal-safety risk.

## Validation Checklist

Each candidate signal must pass:

- no null, nonfinite, or raw-price scale leakage;
- no use of future labels or future diagnostics;
- causal availability timestamp is documented;
- duplicate or near-duplicate features are identified;
- relationship to each of the four targets is measured separately;
- walk-forward ablation improves at least one target without damaging the
  opposite direction target family;
- selected feature importance is stable across chronological folds.

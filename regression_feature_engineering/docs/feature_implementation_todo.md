# Feature Implementation TODO

## Purpose

Track the staged implementation plan for `regression_path_features_v1` feature
families before any formula is promoted.

## Current Status

Planning and tracking contract. Feature formulas are not implemented yet. The
registry in `regression_feature_engineering/core/registry.py` defines stable
family IDs, phase order, source inputs, availability rules, output prefixes, and
target intent.

## Scope

Applies to `distance_horizon_vol_v2` regression targets, starting with
`BTCUSDT 8h/B` and expanding to `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, and
`7d_c` after each family validates.

## Source Of Truth

- Registry: `regression_feature_engineering/core/registry.py`
- Research backlog: `research_feature_signal_backlog.md`
- Feature taxonomy: `feature_taxonomy.md`
- Rollout status: `regression_target_rollout.md`
- Validation rules: `optimization_strategy.md`

## What This Does Not Decide

This document does not choose final formulas, thresholds, lookback windows,
feature selection thresholds, or CatBoost parameters.

## Implementation Principles

- Start with deterministic, closed-bar features.
- Keep feature code separate from `notebooks/htf_pythonscript.py`.
- Use normalized values only: percent, volatility units, rank, bounded ratio,
  or train-window-safe derived factors.
- Write one manifest and feature catalog per generated asset/root.
- Validate one feature family at a time before combining families.
- Optimize feature selection per target inside walk-forward training, not by
  global correlations.

## Phase Checklist

| Phase | Family ID | Status | Output Prefix | Main Target Intent | Acceptance Result |
|---:|---|---|---|---|---|
| 1 | `foundation_alignment` | planned | `rpf_align_` | temporal safety and safe math | pending |
| 2 | `volatility_state` | planned | `rpf_vol_` | all targets, denominator quality, range expansion | pending |
| 3 | `structural_room` | planned | `rpf_room_` | up/down extreme room and asymmetry | pending |
| 4 | `acceptance_persistence` | planned | `rpf_accept_` | up/down mean path persistence | pending |
| 5 | `rejection_chop` | planned | `rpf_chop_` | rejection, chop, two-sided path risk | pending |
| 6 | `spike_breakout` | planned | `rpf_spike_` | up/down extreme tail reach | pending |
| 7 | `liquidity_volume_pressure` | planned | `rpf_liq_` | participation and impulse confirmation | pending |
| 8 | `cross_asset_context` | planned | `rpf_xasset_` | relative pressure and common risk state | pending |
| 9 | `unsupervised_factor_layer` | deferred | `rpf_factor_` | derived context and path regime | pending |

## Phase 1: Foundation And Alignment

Tasks:

- load canonical `15m`, `1h`, `4h`, `8h`, `12h`, and `1d` OHLCV sources;
- align closed higher-timeframe bars to 1m rows with backward-looking as-of
  semantics;
- align feature rows to `distance_horizon_vol_v2` row authority;
- add safe math helpers for percent distance, volatility units, ranks, bounded
  ratios, and divide-by-zero handling;
- produce alignment diagnostics only, not model-facing features.

Validation:

- prove no higher-timeframe value is available before its bar close;
- prove row count and `timestamp,batch_id` authority match the regression label
  root;
- prove no output column is used as a model feature in this phase.

## Phase 2: Volatility State

Tasks:

- add ATR versus realized-vol dominance;
- add volatility compression percentile;
- add short/long volatility expansion ratio;
- add range-versus-return-vol mismatch;
- add causal expected horizon-volatility proxy.

Validation:

- compare each feature against all four target columns;
- check scale and tail quantiles by chronological window;
- reject duplicate volatility estimators that add no target-specific signal.

## Phase 3: Structural Room

Tasks:

- add previous rolling high/low distance in volatility units;
- add Donchian position from previous closed channels;
- add upside/downside room asymmetry;
- add prior session high/low distance where session metadata exists;
- add VWAP/value distance only from closed or prior session context.

Validation:

- prove level features use previous levels only;
- test strongest relationship against `target_reg_distance_up_extreme_hvol_v2`
  and `target_reg_distance_down_extreme_hvol_v2`;
- verify session assets do not create closed-session rows.

## Phase 4: Acceptance And Persistence

Tasks:

- add closes above/below value counts;
- add shallow pullback score;
- add trend efficiency ratio;
- add directional close-location average;
- add higher-timeframe alignment score.

Validation:

- test mean-target separation against extreme-target separation;
- reject features that only duplicate raw momentum without persistence signal.

## Phase 5: Rejection And Chop

Tasks:

- add upper and lower rejection scores;
- add two-sided volatility ratio;
- add reversal count and path entropy;
- add failed breakout count;
- add realized path efficiency.

Validation:

- test whether features separate high-extreme/low-mean cases;
- check that rejection features do not become future-diagnostic proxies.

## Phase 6: Spike And Breakout

Tasks:

- add squeeze-release setup;
- add breakout and breakdown proximity;
- add one-sided impulse score;
- add volume-confirmed impulse;
- add tail-risk asymmetry.

Validation:

- focus on high-distance p95/p99 ranking for extreme targets;
- prove breakout levels come from closed or prior windows.

## Phase 7: Liquidity And Volume Pressure

Tasks:

- add volume z-score by timeframe;
- add dollar-volume proxy;
- add volume-on-up versus volume-on-down pressure;
- add OBV or money-flow slope;
- add volume wake-up after compression.

Validation:

- handle zero-volume synthetic/session rows explicitly;
- verify no nulls or infinities for session assets.

## Phase 8: Cross-Asset Context

Tasks:

- start with deterministic pair features: BTC/ETH, ES/NQ, EURUSD/USDJPY;
- add return spread, volatility spread, relative strength, and rolling
  correlation;
- keep raw foreign prices out of model-facing features;
- defer beta, PCA, cointegration, and lead-lag until this phase validates.

Validation:

- test exact timestamp or closed-bar availability;
- ablate pair groups independently;
- verify missing context handling is explicit and does not create stale rows.

## Phase 9: Unsupervised Factor Layer

Tasks:

- implement only after deterministic families have validation reports;
- candidates are rolling PCA factors, clustering states, and path-regime
  embeddings;
- fit factors from train windows only or strictly prior rolling windows.

Validation:

- prove no validation/prediction rows influence fitted transforms;
- treat outputs as context only, never label authority.

## First Benchmark Sequence

1. `BTCUSDT 8h/B`
2. `BTCUSDT 8h/C`
3. `BTCUSDT 24h/B`
4. all BTCUSDT roots
5. BTCUSDT and ETHUSDT pair context
6. all core assets after deterministic families are stable

## Required Tracking Per Family

Each family report must record:

- source input paths and schema hash;
- generated row count and duplicate count;
- feature count and output prefix;
- null, nonfinite, constant, and duplicate-feature counts;
- target relationship table for all four target columns;
- walk-forward ablation result;
- final status: `pending`, `accepted`, `quarantined`, or `rejected`.


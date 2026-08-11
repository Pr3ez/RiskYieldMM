# Regression Feature Taxonomy

## Purpose

Define what each feature family must represent for the regression distance and
direction-share targets.

## Current Status

Design contract and meaning map. Implemented formulas are tracked in
`feature_implementation_todo.md`; this document does not promote any formula by
itself.

## Scope

Applies to current and planned `regression_path_features_v1` features.

## Source Of Truth

- Target contract: `data_contract.md`
- Implementation TODO: `feature_implementation_todo.md`
- Optimization contract: `optimization_strategy.md`
- Research backlog: `research_feature_signal_backlog.md`

## What This Does Not Decide

This document does not select exact windows, formulas, or thresholds.

## Target Meaning

- `target_reg_distance_up_extreme_hvol_v2`: upside room and spike capacity.
- `target_reg_distance_up_mean_high_hvol_v2`: upside acceptance and persistence.
- `target_reg_distance_down_mean_low_hvol_v2`: downside acceptance and persistence.
- `target_reg_distance_down_extreme_hvol_v2`: downside room and breakdown capacity.
- `target_reg_direction_extreme_up_share_hvol_v2`: bounded upside share of
  extreme future reach versus downside extreme reach.
- `target_reg_direction_mean_up_share_hvol_v2`: bounded upside share of
  persistent future high reach versus persistent future low reach.

## Feature Families

- `volatility_state`: volatility denominator quality, compression, expansion,
  ATR/std dominance, and whether current volatility may understate future path
  range. Rolling z-score features must use prior rows only and fixed clipping.
- `structural_room`: distance to recent highs/lows, channels, value areas,
  support/resistance, and room above/below entry as bounded monotonic
  transforms of volatility-unit distances.
- `acceptance_persistence`: closes above/below local value, shallow pullbacks,
  sustained directional pressure, and accepted movement beyond entry. Value
  distance features are signed bounded transforms of volatility-unit distance.
- `temporal_memory_transforms`: explicit lags, EWM state, slopes, and
  percentile ranks built from already causal base signals.
- `spike_breakout`: one-sided reach capacity, breakout/breakdown proximity,
  squeeze release, and tail-risk asymmetry. Breakout proximity and active break
  distance features are bounded monotonic transforms of volatility-unit
  distance.
- `rejection_chop`: wick rejection, failed breaks, two-sided volatility, and
  noisy path behavior that can inflate extremes without persistence.
- `liquidity_volume_pressure`: volume participation, volume-confirmed
  direction, liquidity proxies, and volume wake-up after compression.
- `regime_calendar_state`: volatility/trend/range regime flags plus
  known-at-prediction session and calendar state.
- `interaction_confluence`: combinations such as compression plus breakout,
  trend plus acceptance, and volume plus impulse that should add information
  beyond their component features.
- `cross_asset_context`: correlated asset pressure, broad risk state, and
  multi-asset volatility context.
- `unsupervised_factor_layer`: deterministic factor/anomaly proxies derived
  from causal component features in static artifacts; learned PCA or clustering
  remains train-window-only and is not part of static RPF output.
- `sequence_embedding_layer`: deterministic multi-timeframe sequence-shape
  proxies derived from causal factor proxies in static artifacts; learned
  CNN/encoder embeddings remain train-window-only and are not part of static
  RPF output.

## Research-Derived Signal Backlog

The active candidate list is maintained in
`research_feature_signal_backlog.md`. That backlog expands the tracked feature
families into implementation-ready signal groups:

- closed higher-timeframe context;
- volatility denominator and expansion state;
- structural room and price location;
- acceptance and persistence;
- lags, EWM state, ranks, and slopes;
- spike, breakout, and breakdown capacity;
- rejection, chop, and two-sided path risk;
- liquidity and volume pressure;
- regime and calendar/session state;
- interaction and confluence;
- cross-asset relative context;
- sequence/factor context.

The first implementation prioritizes a causal set for `BTCUSDT 8h/B`:
volatility state, structural room, acceptance/persistence, temporal-memory
transforms for validated base signals, rejection/chop, spike/breakout,
liquidity/volume pressure, regime/calendar state, interaction/confluence,
cross-asset context, deterministic factor proxies, and deterministic
sequence-shape proxies.

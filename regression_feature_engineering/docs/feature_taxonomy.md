# Regression Feature Taxonomy

## Purpose

Define what each feature family must represent for the four regression targets.

## Current Status

Design contract only. No formula is promoted in this document.

## Scope

Applies to future `regression_path_features_v1` features.

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

## Feature Families

- `volatility_state`: volatility denominator quality, compression, expansion,
  ATR/std dominance, and whether current volatility may understate future path
  range.
- `structural_room`: distance to recent highs/lows, channels, value areas,
  support/resistance, and room above/below entry in volatility units.
- `acceptance_persistence`: closes above/below local value, shallow pullbacks,
  sustained directional pressure, and accepted movement beyond entry.
- `spike_breakout`: one-sided reach capacity, breakout/breakdown proximity,
  squeeze release, and tail-risk asymmetry.
- `rejection_chop`: wick rejection, failed breaks, two-sided volatility, and
  noisy path behavior that can inflate extremes without persistence.
- `cross_asset_context`: correlated asset pressure, broad risk state, and
  multi-asset volatility context.

## Research-Derived Signal Backlog

The active candidate list is maintained in
`research_feature_signal_backlog.md`. That backlog expands the six feature
families into implementation-ready signal groups:

- closed higher-timeframe context;
- volatility denominator and expansion state;
- structural room and price location;
- acceptance and persistence;
- spike, breakout, and breakdown capacity;
- rejection, chop, and two-sided path risk;
- cross-asset relative context;
- session/calendar state;
- liquidity and volume pressure.

The first implementation should prioritize a small causal set for
`BTCUSDT 8h/B`: volatility state, structural room, acceptance/persistence,
rejection/chop, and BTC-versus-ETH cross-asset pressure.

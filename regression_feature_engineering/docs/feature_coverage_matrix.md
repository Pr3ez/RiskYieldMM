# Feature Coverage Matrix

## Purpose

Map the full time-series feature checklist to explicit
`regression_path_features_v1` families so no useful feature class is left only
as an informal idea.

## Current Status

Coverage contract. Phase 1 through Phase 13 have materialized initial
implementations for the current BTCUSDT `8h/B` root and passed engineering
validation. None are predictively promoted yet.

## Scope

Applies to `distance_horizon_vol_v2` regression features for all core assets
and root IDs `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, and `7d_c`.

## Source Of Truth

- Registry: `../core/registry.py`
- Implementation plan: `feature_implementation_todo.md`
- Research backlog: `research_feature_signal_backlog.md`
- Optimization gates: `optimization_strategy.md`

## What This Does Not Decide

This matrix does not choose exact formulas, lookbacks, thresholds, model
hyperparameters, or promotion status.

## Coverage Matrix

| Feature Type | Family | Prefix | Phase | Status | Validation Gate |
|---|---|---|---:|---|---|
| closed higher-timeframe context | `foundation_alignment` | `rpf_align_` | 1 | engineering_validated | no future-close violations |
| rolling standard deviations and volatility scale | `volatility_state` | `rpf_vol_` | 2 | engineering_validated_not_promoted | target-scale and tail ranking |
| volatility z-scores and compression state | `volatility_state` | `rpf_vol_` | 2 | engineering_validated_not_promoted | chronological stability |
| distance-to-band/value/support/resistance | `structural_room` | `rpf_room_` | 3 | engineering_validated_not_promoted | previous-level temporal safety |
| rolling means and accepted value state | `acceptance_persistence` | `rpf_accept_` | 4 | engineering_validated_not_promoted | mean-target relationship |
| returns, slopes, trend efficiency | `acceptance_persistence` | `rpf_accept_` | 4 | engineering_validated_not_promoted | persistence versus spike separation |
| explicit lags | `temporal_memory_transforms` | `rpf_mem_` | 5 | engineering_validated_not_promoted | prior rows only |
| EWM means and EWM slopes | `temporal_memory_transforms` | `rpf_mem_` | 5 | engineering_validated_not_promoted | past-only recursive state |
| percentile-rank position proxies | `temporal_memory_transforms` | `rpf_mem_` | 5 | engineering_validated_not_promoted | rolling-window-only rank-position state |
| reversal/bounce and failed breaks | `rejection_chop` | `rpf_chop_` | 6 | engineering_validated_not_promoted | high-extreme versus low-mean separation |
| chop, entropy, two-sided range | `rejection_chop` | `rpf_chop_` | 6 | engineering_validated_not_promoted | persistence suppression signal |
| spike, breakout, breakdown, squeeze release | `spike_breakout` | `rpf_spike_` | 7 | engineering_validated_not_promoted | p95/p99 extreme-target ranking |
| volume pressure and liquidity proxies | `liquidity_volume_pressure` | `rpf_liq_` | 8 | engineering_validated_not_promoted | zero-volume/session safety |
| volatility/trend/range regime flags | `regime_calendar_state` | `rpf_regime_` | 9 | engineering_validated_not_promoted | regime ablation and stability |
| calendar/session/open-state features | `regime_calendar_state` | `rpf_regime_` | 9 | engineering_validated_not_promoted | known-at-prediction-time proof |
| interaction/confluence features | `interaction_confluence` | `rpf_conf_` | 10 | engineering_validated_not_promoted | improves over component features |
| cross-series/context features | `cross_asset_context` | `rpf_xasset_` | 11 | engineering_validated_not_promoted | no raw foreign prices, exact context availability |
| deterministic factor/anomaly proxies | `unsupervised_factor_layer` | `rpf_factor_` | 12 | engineering_validated_not_promoted | no global fit; causal component-derived proxies |
| deterministic sequence-shape proxies | `sequence_embedding_layer` | `rpf_seq_` | 13 | engineering_validated_not_promoted | no encoder fit; causal factor-stack summaries |

## Trading Priority Order

1. Distance-to-band, VWAP/value, support, and resistance.
2. Volatility denominator, compression, and expansion regime.
3. Trend/range and acceptance/rejection regime.
4. Reversal, bounce, failed-break, and two-sided chop.
5. Multi-timeframe context.
6. Interaction/confluence features.
7. Cross-asset context.
8. Deterministic factor and sequence-shape proxies.
9. Train-window-only learned factor or sequence embeddings.

## Implementation Guardrails

- Never expose raw unscaled OHLCV as model-facing features.
- Use only closed higher-timeframe bars or known-at-prediction calendar state.
- Fit any EWM state, rank, scaler, PCA, learned factor, or sequence encoder
  with past data only.
- Validate every family on `BTCUSDT 8h/B` before full-matrix rollout.
- Promote only after walk-forward ablation proves value for at least one target
  without consistently damaging its opposite-direction pair.

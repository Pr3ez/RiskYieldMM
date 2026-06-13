# Acceptance/Persistence Plan Compliance Check

## Purpose

Compare the implemented `acceptance_persistence` feature family against the
current regression feature docs and the Phase 4 implementation plan.

## Current Status

Status: `engineering_validated_not_promoted`.

The family is materialized for the first benchmark, `BTCUSDT 8h/B`, together
with `foundation_alignment`, `volatility_state`, and `structural_room`.

## Scope

- Feature set: `regression_path_features_v1`
- Target variant: `distance_horizon_vol_v2`
- Benchmark root: `BTCUSDT 8h/B`
- Output root:
  `data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/`

## Source Of Truth

- Plan/status: `regression_feature_engineering/docs/feature_implementation_todo.md`
- Workflow: `regression_feature_engineering/docs/workflow.md`
- Feature code: `regression_feature_engineering/features/acceptance_persistence.py`
- Materializer: `regression_feature_engineering/materialize_features.py`
- Validator: `regression_feature_engineering/validate_features.py`

## What This Does Not Decide

This report does not promote the feature family. Promotion still requires
walk-forward ablation and comparison against HTF-only and
HTF-plus-regression baselines.

## Compliance Summary

| Plan Item | Status | Evidence |
|---|---|---|
| Feature family `acceptance_persistence` exists | complete | `features/acceptance_persistence.py` |
| Prefix `rpf_accept_` | complete | manifest contains `201` `rpf_accept_` features |
| Defaults `4,16,48` | complete | `DEFAULT_ACCEPT_LOOKBACKS=(4,16,48)` |
| Timeframes `15m,1h,4h,8h,12h,1d` | complete | materializer and manifest use all six timeframes |
| Closed canonical OHLCV only | complete | `join_all_closed_bar_context` and alignment diagnostics |
| No raw OHLCV model columns | complete | source columns are dropped before output |
| Normalized/bounded outputs | complete | suffixes `_bnd` and `_vol`; no raw prices |
| Close-location features | complete | `close_loc_avg`, `close_loc_balance` |
| Body/return persistence | complete | `body_persist`, `return_persist` |
| Closes above/below value | complete | `above_value_share`, `below_value_share` |
| Trend efficiency | complete | `trend_eff` |
| Pullback shallowness | complete | `up_pullback_shallow`, `down_pullback_shallow` |
| Higher-timeframe agreement | complete | `tf_bull_agreement`, `tf_bear_agreement`, `tf_direction_agreement` |
| True consecutive accepted-duration/run-length | partial | current implementation uses rolling shares, not run-length duration |
| Catalog entries | complete | `feature_catalog.json` has `201` acceptance entries |
| Manifest lineage | complete | `manifest.json` records families, features, diagnostics, source paths |
| Report-only lookback sweep | complete | `experiments/acceptance_persistence_lookback_sweep.py` |
| OOM guardrails | complete | validator width limit and bounded sweep defaults |

## Validation Evidence

Materialized root:

- rows: `2,810,755`
- model-facing features: `410`
- `rpf_vol_`: `29`
- `rpf_room_`: `180`
- `rpf_accept_`: `201`
- duplicate keys: `0`
- null feature cells: `0`
- alignment diagnostics: `18`

Diagnostic slices:

All acceptance/persistence diagnostic prefixes completed with full-root safety
checks:

| Prefix | Diagnostic Columns | Strongest Abs Spearman | Strongest Feature | Target |
|---|---:|---:|---|---|
| `rpf_accept_15m_` | 33 | `0.0580` | `rpf_accept_15m_value_dist_l16_vol` | `target_reg_distance_down_mean_low_hvol_v2` |
| `rpf_accept_1h_` | 33 | `0.0578` | `rpf_accept_1h_value_dist_l4_vol` | `target_reg_distance_down_mean_low_hvol_v2` |
| `rpf_accept_4h_` | 33 | `0.0495` | `rpf_accept_4h_value_dist_l4_vol` | `target_reg_distance_down_mean_low_hvol_v2` |
| `rpf_accept_8h_` | 33 | `0.0498` | `rpf_accept_8h_value_dist_l4_vol` | `target_reg_distance_down_mean_low_hvol_v2` |
| `rpf_accept_12h_` | 33 | `0.0391` | `rpf_accept_12h_close_loc_avg_l48_bnd` | `target_mean_total` |
| `rpf_accept_1d_` | 33 | `0.0689` | `rpf_accept_1d_close_loc_avg_l48_bnd` | `target_mean_total` |
| `rpf_accept_tf_` | 3 | `0.0473` | `rpf_accept_tf_bull_agreement_share_bnd` | `target_reg_distance_down_mean_low_hvol_v2` |

Each slice reported:

- joined rows: `2,810,755`;
- valid rows: `1,405,427`;
- duplicate `timestamp,batch_id`: `0`;
- null feature cells: `0`;
- infinite feature cells: `0`;
- future-close timing violations: `0`.

Bounded lookback sweep:

- first `200` BTCUSDT `8h/B` batches;
- rows: `96,000`;
- valid rows: `47,987`;
- peak RSS: about `1.38GB`;
- best mean-direction signal: `0.2850` absolute Spearman from
  `rpf_accept_12h_return_persist_l72_bnd` against
  `target_mean_up_minus_down`.

## Remaining Gaps

1. Decide whether to add true consecutive accepted-duration/run-length features.
2. Run walk-forward ablation before any promotion:
   - HTF-only
   - regression-only
   - HTF plus regression
3. Test longer lookbacks suggested by bounded sweep evidence, especially
   `8,24,72`, without treating bounded-sample correlations as promotion
   evidence.

## Final Assessment

No critical implementation item is missing for the initial Phase 4 candidate.
The main incomplete plan detail is true accepted-duration/run-length; the
current implementation approximates it with rolling above/below-value shares.
The family is safe to include in strict Stage-1 regression ablations, but it is
not yet ready for rollout or Stage-1 promotion.

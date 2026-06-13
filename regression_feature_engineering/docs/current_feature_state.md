# Current Regression Feature State

## Purpose

Keep one blunt source of truth for what `regression_feature_engineering/`
actually built, what works technically, and what has not improved prediction.

## Current Status

Status: technically valid feature artifacts exist, but the current
`regression_path_features_v1` feature set is **not predictively promoted**.

The corrected walk-forward smoke for `BTCUSDT 8h/B`
`target_reg_distance_up_extreme_hvol_v2` showed:

```text
htf_only validation Spearman:            0.304247
regression_only validation Spearman:     0.059750
htf_plus_regression validation Spearman: 0.095225
```

This means the first corrected smoke favored the old HTF/helper feature set.
The new regression features from this workspace currently have technical
validity evidence, not production prediction-quality evidence.

## Scope

This document covers only features created by:

```text
regression_feature_engineering/
```

It does not cover old HTF/helper features under `htf_with_helpers`, except when
explaining feature-source comparisons.

## Source Of Truth

- Feature registry: `regression_feature_engineering/core/registry.py`
- Materializer: `regression_feature_engineering/materialize_features.py`
- Validator: `regression_feature_engineering/validate_features.py`
- Clean RPF walk-forward optimizer:
  `regression_feature_engineering/walkforward/`
- Clean optimizer contract: `clean_rpf_walkforward_reset.md`
- Latest BTCUSDT `8h/B` RPF manifest:
  `data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/manifest.json`
- Latest corrected smoke grid:
  `test_output/stage1_regression_grid_search/20260602_081108/grid_summary.parquet`

## What This Does Not Decide

This document does not authorize promotion, feature deletion, or final model
selection. It records current state so we stop mixing engineering correctness
with predictive value.

## What Was Built Here

The active feature set is:

```text
regression_path_features_v1
```

For `BTCUSDT 8h/B`, the current generated root is:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
```

Current artifact evidence:

```text
generated_at: 2026-06-02T22:18:37 UTC
local mtime:  2026-06-03 00:18:37 Europe/Warsaw
rows:         2,810,755
features:     2,530 model-facing rpf_* columns
duplicates:   0
null features:0
```

Feature counts in the current `BTCUSDT 8h/B` root:

| Prefix | Count | Status | Meaning |
|---|---:|---|---|
| `rpf_align_` | 18 | diagnostic only | closed-bar alignment and timing checks |
| `rpf_vol_` | 29 | implemented, not promoted | volatility denominator and range-expansion state |
| `rpf_room_` | 180 | implemented, not promoted | prior high/low/value room and Donchian position |
| `rpf_accept_` | 201 | implemented, not promoted | directional acceptance and persistence |
| `rpf_mem_` | 693 | implemented, not promoted | lags, EWM, slopes, residuals, rank-position transforms |
| `rpf_chop_` | 180 | implemented, not promoted | wick rejection, failed breaks, path efficiency, and two-sided chop |
| `rpf_spike_` | 288 | implemented, not promoted | squeeze release, breakout/breakdown proximity, one-sided impulse, and tail-risk asymmetry |
| `rpf_liq_` | 162 | implemented, not promoted | volume z-score, turnover proxy, volume wake-up, up/down volume pressure, OBV/money-flow proxy, and zero-volume context |
| `rpf_regime_` | 209 | implemented, not promoted | UTC calendar cycle, session metadata, trend/range regime, volatility expansion flags |
| `rpf_conf_` | 270 | implemented, not promoted | compression-breakout, trend-acceptance, volume-impulse, clean-persistence, and room-pressure confluence |
| `rpf_xasset_` | 144 | implemented, not promoted | BTC/ETH relative return, range, correlation, pressure, common-direction, and relative participation context |
| `rpf_factor_` | 144 | engineering validated, not promoted | deterministic factor/anomaly proxies from causal component features |
| `rpf_seq_` | 30 | engineering validated, not promoted | deterministic multi-timeframe sequence-shape proxies from factor proxies |

## What The Feature Sources Mean

The corrected walk-forward runner compares three feature sources:

```text
htf_only
regression_only
htf_plus_regression
```

They are not the same thing.

`htf_only` reads the old merged Stage-1 HTF/helper dataset:

```text
data/htf_multiasset_merged/btcusdt/corexself/target_reg_distance_up_extreme_hvol_v2/8h_b/features/
```

That root was generated at:

```text
2026-06-02T03:28:31 UTC
```

It was built by `build_multiasset_stage1_dataset(...)` from:

```text
data/htf_multiasset/{asset}/htf_with_helpers/1m/target_4class/
data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m/
```

`regression_only` uses the same Stage-1 row and label authority, but replaces
model features with the target asset's `rpf_*` columns from:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
```

`htf_plus_regression` uses the old merged HTF/helper features plus BTCUSDT
`rpf_*` features joined by exact `timestamp,batch_id`.

In v1, context-asset regression-path features are not joined. Context assets
only contribute through the old HTF/helper merged dataset.

## What Works Technically

The following is technically working:

- materialization of `BTCUSDT 8h/B` `regression_path_features_v1`;
- closed-bar alignment diagnostics;
- full-root row output with no duplicate keys;
- no null feature cells in the generated BTCUSDT `8h/B` root;
- feature catalog generation;
- validator full-root safety checks;
- sliced signal diagnostics for broad feature families;
- Stage-1 exact `timestamp,batch_id` join for target-asset `rpf_*`;
- Stage-1 RPF loading now uses `manifest.json` `feature_columns`, so
  `rpf_align_*` diagnostic metadata cannot enter model features;
- clean RPF default policy now uses all manifest model features with no
  feature-count cap;
- corrected grid output with separate validation and prediction metrics;
- clean RPF-native walk-forward package exists under
  `regression_feature_engineering/walkforward/`;
- the clean runner reads RPF feature batches directly, exact-joins hvol labels
  by `timestamp,batch_id`, freezes sparse windows, and writes stage artifacts
  under `test_output/rpf_clean_walkforward/`.
- the clean runner validates label-window metadata before training and writes
  per-window diagnostics to `window_metrics.parquet`;
- Optuna minimizes validation RMSE directly; rank, direction, tail, and p95
  metrics are diagnostics, not selection objectives;
- fixed family ablation is available through `feature_ablation`, while
  per-feature selection remains deferred.
- model-facing scale helpers now enforce causal bounded transforms for
  rolling z-scores and volatility-unit distances; existing RPF roots generated
  before this code change must be rematerialized before further walk-forward
  optimization.

Old Stage-1 regression optimizers remain available for historical comparison,
but they are not the active RPF optimization path.

## Scale Audit

On 2026-06-04, a recent-window scale audit found that some model-facing RPF
columns were not practically normalized:

```text
sample:   BTCUSDT 8h/B recent 200 batches
artifact: test_output/rpf_feature_scale_audit/btcusdt_8h_b_recent200_feature_scale_audit.parquet
```

Main issue:

- raw rolling volatility z-scores could explode when prior rolling standard
  deviation was tiny;
- temporal-memory EWM/slope/residual features propagated those outliers;
- raw volatility-unit room/proximity/value-distance features could reach
  hundreds of volatility units.

Corrected code contract:

- rolling z-scores are clipped to a fixed finite range;
- positive volatility-unit magnitudes use fixed `[0,1]` compression;
- signed volatility-unit values use fixed `[-1,1]` compression;
- no full-dataset scaler or future-aware quantile normalization is used.

This is an implementation fix only. The generated root on disk keeps its old
values until `materialize_features` is rerun.

## Walk-Forward Readiness Check

On 2026-06-04, a readiness audit found and fixed one issue before larger
walk-forward runs:

- RPF batch files contain `2,548` `rpf_*` columns because `18` `rpf_align_*`
  diagnostic columns are stored beside `2,530` model-facing features.
- The RPF manifest correctly lists only `2,530` model features, but the
  walk-forward loader previously scanned numeric `rpf_*` columns directly.
- That meant a full-feature policy could expose boolean alignment metadata if
  it ignored the manifest contract.
- The loader now reads `manifest.json` `feature_columns`, rejects missing or
  non-numeric manifest features, and excludes diagnostics from all feature
  policies.

Live loader check:

```text
loaded model feature columns: 2,530
manifest feature columns:     2,530
diagnostic columns loaded:    0
```

Coverage check against the active Stage-1 merged root:

```text
valid sparse Stage-1 batches: 3,942
batch id range:               262..5856
missing RPF batches:          0
sample exact-join duplicate:  0
sample exact-join RPF nulls:  0
```

Historical one-step Stage-1 `ml_env` smoke:

```text
run id:  stage1_regression_btcusdt_8h_b_ctx_corexself_reg_distance_up_extreme_hvol_v2_live_feat_regression_only_smoke_rpf_readiness_1step_mlenv
source:  regression_only
policy:  target_specific_v2
steps:   1
rows:    240 prediction rows
features selected: 20
status:  completed and wrote predictions, validation predictions, step metrics,
         feature-policy detail, selected-feature frequency, and summary files
```

This one-step smoke is historical plumbing evidence only. It used
`target_specific_v2`, not the current clean RPF default. Its negative
prediction Spearman must not be used for model selection because it uses one
final prediction batch, very small training windows, and only five CatBoost
iterations.

Clean RPF-native readiness also passed for the first reset target:

```text
command: python -m regression_feature_engineering.walkforward.optimize --stage readiness
target:  target_reg_direction_extreme_up_share_hvol_v2
run:     test_output/rpf_clean_walkforward/20260604_100626_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524

model feature count:   2,530
available batches:     5,856
valid target rows:      1,405,427
target min/max:         0.0 / 1.0
target mean/std:        0.5041 / 0.3656
frozen windows:         5
train/val per window:   120 / 10 available batches
```

This is an RPF data-contract check only. It does not train CatBoost or promote
the target.

A one-trial clean baseline-probe smoke also completed after vectorizing the
rank-correlation feature-selection path:

```text
run:                test_output/rpf_clean_walkforward/20260604_101326_baseline_probe_btcusdt_8h_b_target_reg_direction_extreme_up_sha_f53c5ec0
iterations/depth:   10 / 3
validation Spearman:0.3489
validation RMSE:    0.3350
prediction std:     0.0
prediction unique:  1
status:             rejected:low_prediction_unique
```

This is good plumbing evidence because the trial rejection rule fired correctly.
It is not a useful model-quality result because the intentionally tiny model
collapsed on the prediction batch.

## What Does Not Work Yet

The current `rpf_*` features have not beaten the old HTF/helper features in the
first corrected walk-forward smoke.

Do not claim these features improve prediction until a validation-led
walk-forward run proves it.

The current evidence says:

- volatility and memory features can describe total path width;
- structural-room features are weak for direct up/down separation;
- acceptance/persistence features are technically clean but still modest;
- rejection/chop features are technically clean and show modest purpose-aligned
  signal, but still need walk-forward ablation;
- spike/breakout features are technically clean and show stronger
  purpose-aligned extreme-path signal, but still need walk-forward ablation;
- liquidity/volume-pressure features are technically clean and show modest
  participation and directional-spread signal, but still need walk-forward
  ablation;
- regime/calendar-state features are technically clean and show useful
  calendar/session/path-width context, but still need walk-forward ablation;
- cross-asset-context features are technically clean and show modest BTC/ETH
  relative-context signal, but still need walk-forward ablation;
- adding current `rpf_*` features to HTF features can make selection worse;
- Phase 12/13 static deterministic factor and sequence-shape proxies are
  materialized in the current root; all `rpf_factor_*` timeframe-prefix
  validations and the `rpf_seq_` validation passed, but the families are still
  not predictively promoted.

## Current Decision

Do not promote `regression_path_features_v1` as better than HTF-only.

Use the corrected validation-led grid only after choosing an ablation scope. If
the all-target grid confirms HTF-only is better, stop tuning the current
families and revisit feature design with concrete ablation evidence.

## Rejection/Chop Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `rejection_chop` and validated by
narrow timeframe prefixes to avoid wide-diagnostic memory pressure.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_chop_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_chop_15m_` | 0.0843 | short-term path chop / failed breaks vs total extreme path width |
| `rpf_chop_1h_` | 0.0465 | weak path chop / failed-break signal |
| `rpf_chop_4h_` | 0.0509 | weak rejection/chop signal |
| `rpf_chop_8h_` | 0.0556 | weak reversal/rejection signal |
| `rpf_chop_12h_` | 0.1187 | upper rejection negatively associated with mean/total path width |
| `rpf_chop_1d_` | 0.1296 | upper rejection negatively associated with mean/total path width |

Interpretation:

- Long-timeframe upper rejection behaves like a persistence suppressor: higher
  rejection is associated with lower future mean/total path distance.
- Short-timeframe path chop behaves like a two-sided instability proxy: higher
  chop is associated with wider total extreme path movement.
- Directional up-vs-down separation remains modest. This family is useful
  context, not a standalone directional solution.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_1d/
```

## Spike/Breakout Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `spike_breakout` and validated by
narrow timeframe prefixes.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_spike_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_spike_15m_` | 0.1998 | downside breakout proximity vs total extreme path width |
| `rpf_spike_1h_` | 0.2364 | downside breakout proximity vs total extreme path width |
| `rpf_spike_4h_` | 0.2299 | downside breakout proximity vs total extreme path width |
| `rpf_spike_8h_` | 0.2381 | downside breakout proximity vs total extreme path width |
| `rpf_spike_12h_` | 0.2338 | downside breakout proximity vs total extreme path width |
| `rpf_spike_1d_` | 0.2304 | downside breakout proximity vs total extreme path width |

Interpretation:

- `rpf_spike_*` gives stronger sampled signal than `rpf_chop_*` for extreme
  path-width ranking.
- The strongest feature class is prior-channel breakout/breakdown proximity,
  especially downside proximity. This is purpose-aligned for extreme-distance
  targets but also indicates the family is currently more width/risk-state
  oriented than cleanly directional.
- Bin-spread checks show high breakout-proximity bins separating
  `target_extreme_total` by roughly `0.3` to `0.6` horizon-volatility units in
  the sampled validation.
- Directional up-vs-down separation remains modest; this family should be
  tested by walk-forward ablation, not promoted from correlation alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_1d/
```

## Liquidity/Volume Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `liquidity_volume_pressure` and
validated by narrow timeframe prefixes.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_liq_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_liq_15m_` | 0.1132 | volume wake-up / relative activity negatively associated with total extreme path width |
| `rpf_liq_1h_` | 0.1311 | volume wake-up negatively associated with total extreme path width |
| `rpf_liq_4h_` | 0.1595 | volume wake-up negatively associated with total extreme path width |
| `rpf_liq_8h_` | 0.0925 | volume z-score negatively associated with total extreme path width |
| `rpf_liq_12h_` | 0.1190 | dollar-volume relative activity associated with total extreme path width |
| `rpf_liq_1d_` | 0.0558 | money-flow balance associated with mean total path width |

Directional high-low quintile spreads:

| Prefix | Feature | Target | High-Low Spread |
|---|---|---|---:|
| `rpf_liq_15m_` | `volume_pressure_balance_l48` | `target_extreme_up_minus_down` | 0.2382 |
| `rpf_liq_1h_` | `volume_pressure_balance_l48` | `target_extreme_up_minus_down` | 0.2148 |
| `rpf_liq_4h_` | `volume_pressure_balance_l4` | `target_extreme_up_minus_down` | 0.1616 |
| `rpf_liq_8h_` | `volume_pressure_balance_l4` | `target_extreme_up_minus_down` | 0.1754 |
| `rpf_liq_12h_` | `money_flow_balance_l4` | `target_extreme_up_minus_down` | 0.1015 |
| `rpf_liq_1d_` | `money_flow_balance_l4` | `target_extreme_up_minus_down` | 0.0793 |

Interpretation:

- The liquidity family is technically clean and useful as participation
  context.
- Relative volume/wake-up features mostly act like path-width or volatility
  state context in the sampled reports.
- Up/down volume-pressure balance creates directional quintile separation, but
  rank correlations are still modest. This family should be kept for
  controlled ablation, not promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1d/
```

## Regime/Calendar Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `regime_calendar_state` and validated
by narrow calendar/timeframe prefixes. A single corrupted parquet batch
(`batch_2511.parquet`) was repaired by rebuilding that batch from the same
causal materializer path before rerunning the failed `12h` and `1d` reports.
All feature batches are now readable.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_regime_*` slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_regime_utc_` | 0.2916 | UTC hour cycle negatively associated with total extreme path width |
| `rpf_regime_15m_` | 0.1603 | 15m volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_1h_` | 0.1803 | 1h volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_4h_` | 0.1770 | 4h volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_8h_` | 0.1473 | 8h session progress negatively associated with total extreme path width |
| `rpf_regime_12h_` | 0.1474 | 12h session progress negatively associated with total extreme path width |
| `rpf_regime_1d_` | 0.1473 | 1d session progress negatively associated with total extreme path width |

Interpretation:

- The regime/calendar family is technically clean and provides useful timing,
  session, and path-width context.
- The strongest signal is calendar/session-style context rather than clean
  up/down direction.
- This family should be kept for controlled ablation and interaction work, not
  promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_utc/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_1d/
```

## Interaction/Confluence Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `interaction_confluence` and
validated by narrow `rpf_conf_*` timeframe prefixes.

Phase 10 generated-root result:

```text
rows:                    2,810,755
model-facing features:   2,212
interaction features:    270
duplicate keys:          0
null feature cells:      0
readable batch files:    5,856 / 5,856
```

Safety result across every `rpf_conf_*` prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest sampled signal by `rpf_conf_*` slice:

| Prefix | Strongest Abs Spearman | Feature | Target | Best Quintile Spread | Spread Target |
|---|---:|---|---|---:|---|
| `rpf_conf_15m_` | 0.1200 | `up_squeeze_break_l16` | `target_extreme_total` | 0.2135 | `target_extreme_total` |
| `rpf_conf_1h_` | 0.0996 | `up_squeeze_break_l4` | `target_extreme_total` | 0.2162 | `target_extreme_up_minus_down` |
| `rpf_conf_4h_` | 0.1530 | `down_squeeze_break_l4` | `target_extreme_total` | 0.1850 | `target_extreme_up_minus_down` |
| `rpf_conf_8h_` | 0.0933 | `down_squeeze_break_l48` | `target_extreme_total` | 0.1879 | `target_extreme_up_minus_down` |
| `rpf_conf_12h_` | 0.0838 | `down_squeeze_break_l16` | `target_extreme_total` | 0.1551 | `target_extreme_up_minus_down` |
| `rpf_conf_1d_` | 0.1002 | `down_squeeze_break_l16` | `target_extreme_total` | 0.1593 | `target_extreme_up_minus_down` |

Interpretation:

- The confluence family is technically clean.
- The strongest rank signal remains path-width oriented, mostly
  squeeze-break relationships with `target_extreme_total`.
- Directional information is more visible in high-low quintile spreads,
  especially volume-impulse, clean-persistence, and squeeze-break balance
  features against `target_extreme_up_minus_down`.
- This family should be kept for controlled ablation and target-specific
  selection, not promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1d/
```

## Cross-Asset Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `cross_asset_context` and validated by
narrow `rpf_xasset_ethusdt_*` timeframe prefixes. For BTCUSDT, auto context
uses ETHUSDT.

Current generated-root result:

```text
rows:                    2,810,755
model-facing features:   2,356
cross-asset features:    144
duplicate keys:          0
null feature cells:      0
readable batch files:    5,856 / 5,856
```

Safety result across every `rpf_xasset_ethusdt_*` prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest sampled signal by `rpf_xasset_ethusdt_*` slice:

| Prefix | Strongest Abs Spearman | Feature | Target | Best Quintile Spread | Spread Target |
|---|---:|---|---|---:|---|
| `rpf_xasset_ethusdt_15m_` | 0.0481 | `corr_l16` | `target_extreme_total` | 0.1294 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_1h_` | 0.0384 | `context_pressure_l4` | `target_reg_distance_down_mean_low_hvol_v2` | 0.1412 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_4h_` | 0.0395 | `context_range_share_l4` | `target_extreme_total` | 0.1158 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_8h_` | 0.0424 | `corr_l48` | `target_mean_total` | 0.1150 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_12h_` | 0.0495 | `volume_rel_spread_l4` | `target_extreme_total` | 0.1486 | `target_extreme_total` |
| `rpf_xasset_ethusdt_1d_` | 0.0581 | `corr_l48` | `target_mean_total` | 0.1358 | `target_extreme_total` |

Interpretation:

- The cross-asset family is technically clean and has no raw foreign
  price/volume model-facing columns.
- The sampled rank signal is modest; the strongest absolute Spearman is
  `0.0581`, mostly against total path-width or mean-total targets.
- Directional information appears more in quintile spreads than rank
  correlations, especially relative strength, relative volume, and context
  pressure against `target_extreme_up_minus_down`.
- Keep this family for controlled ablation and target-specific selection, not
  as a standalone promoted feature family.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1d/
```

## Clean Walk-Forward Optimizer State

The clean RPF walk-forward optimizer is organized as staged Optuna searches
instead of one broad all-parameter search.

Implemented optimizer stages:

```text
readiness -> baseline_probe -> geometry -> core_model -> sampling -> confirmation
```

Current status:

- `readiness` writes `readiness.json`, `batch_index.parquet`, and
  `frozen_windows.parquet`;
- all clean stages use RPF-only `feature_source=regression_only`;
- feature policy is fixed at `all_manifest_features` for now, so every
  model-facing RPF manifest feature is used;
- Optuna currently tunes only walk-forward geometry and CatBoost
  hyperparameters, selected by validation RMSE;
- feature-selection thresholds, selected-feature counts, dedupe thresholds,
  clipping quantiles, stability segments, and tail quantiles are deliberately
  not used or optimized yet;
- family ablation masks such as `only_volatility_state`,
  `minus_volatility_state`, and `group_volatility_state+structural_room` are
  fixed run inputs for later feature optimization;
- later stages can load a previous `best_config.json` or stage-specific lock
  file through `--base-run`;
- the walk-forward runner replays exact sparse windows from
  `frozen_windows.parquet`;
- CatBoost now records and validates staged parameters, including
  `has_time=true`, early stopping controls, and bootstrap/sampling options.
- long-running jobs now have live console progress and JSONL event logs:
  `events.jsonl` inside each clean stage run directory.

No staged Optuna result is promoted yet. The next valid evidence should come
from baseline-probe, geometry, and core-model smoke runs on `BTCUSDT 8h/B`
before any full confirmation run.

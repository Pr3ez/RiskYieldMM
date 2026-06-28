# Feature Implementation TODO

## Purpose

Track the staged implementation plan for `regression_path_features_v1` feature
families before any formula is promoted.

## Current Status

Planning and tracking contract. Current implemented families have engineering
validation evidence, but they are not predictively promoted. Earlier
`BTCUSDT 8h/B` comparison evidence showed the old HTF/helper baseline beating
initial RPF combinations, so promotion now requires RPF-first staged
walk-forward optimization rather than another broad mixed-source run. Current
model research is focused on binary UP/DOWN `2x` targets and stable
regime-gated prediction, while the feature families remain
engineering-valid-not-promoted. The registry in
`regression_feature_engineering/core/registry.py` defines stable family IDs,
phase order, source inputs, availability rules, output prefixes, and target
intent.

## Scope

Applies to `distance_horizon_vol_v2` regression targets, starting with
`BTCUSDT 8h/B` and expanding to `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, and
`7d_c` after each family validates.

## Source Of Truth

- Registry: `regression_feature_engineering/core/registry.py`
- Research backlog: `research_feature_signal_backlog.md`
- Feature taxonomy: `feature_taxonomy.md`
- Rollout status: `regression_target_rollout.md`
- Current state: `current_feature_state.md`
- Actual code/artifact status:
  `../reports/code_vs_plan_status_2026-06-02.md`
- Validation rules: `optimization_strategy.md`
- Regime-gate tracker: `rpf_regime_gate_implementation_todo.md`

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
- During the current clean RPF pass, use fixed all-manifest or fixed
  family-ablation scopes. Per-feature selection is deferred; when enabled, it
  must be train-window-only and never chosen from global correlations.

## Phase Checklist

| Phase | Family ID | Status | Output Prefix | Main Target Intent | Acceptance Result |
|---:|---|---|---|---|---|
| 1 | `foundation_alignment` | engineering_validated | `rpf_align_` | temporal safety and safe math | diagnostics only; not a predictive feature family |
| 2 | `volatility_state` | engineering_validated_not_promoted | `rpf_vol_` | all targets, denominator quality, range expansion | all-core six-root signal validation passed; first corrected smoke did not beat HTF-only |
| 3 | `structural_room` | engineering_validated_not_promoted | `rpf_room_` | up/down extreme room and asymmetry | BTCUSDT `8h/B` quality validation passed; directional imbalance signal weak |
| 4 | `acceptance_persistence` | engineering_validated_not_promoted | `rpf_accept_` | up/down mean path persistence | BTCUSDT `8h/B` materialized; all timeframe diagnostic slices clean; not predictively promoted |
| 5 | `temporal_memory_transforms` | engineering_validated_not_promoted | `rpf_mem_` | explicit lags, EWM state, slopes, rank-position proxies | BTCUSDT `8h/B` materialized; sliced memory-prefix validation clean; not predictively promoted |
| 6 | `rejection_chop` | engineering_validated_not_promoted | `rpf_chop_` | rejection, chop, two-sided path risk | BTCUSDT `8h/B` rebuilt and prefix-validations clean; modest purpose-aligned signal, not predictively promoted |
| 7 | `spike_breakout` | engineering_validated_not_promoted | `rpf_spike_` | up/down extreme tail reach | BTCUSDT `8h/B` rebuilt and prefix-validations clean; stronger extreme-width signal, not predictively promoted |
| 8 | `liquidity_volume_pressure` | engineering_validated_not_promoted | `rpf_liq_` | participation and impulse confirmation | BTCUSDT `8h/B` rebuilt and prefix-validations clean; modest volume/participation signal, not predictively promoted |
| 9 | `regime_calendar_state` | engineering_validated_not_promoted | `rpf_regime_` | volatility/trend/session/calendar regimes | BTCUSDT `8h/B` rebuilt and prefix-validations clean; useful calendar/session context, not predictively promoted |
| 10 | `interaction_confluence` | engineering_validated_not_promoted | `rpf_conf_` | validated signal interactions and confluence | BTCUSDT `8h/B` rebuilt and prefix-validations clean; path-width and directional-spread signal, not predictively promoted |
| 11 | `cross_asset_context` | engineering_validated_not_promoted | `rpf_xasset_` | relative pressure and common risk state | BTCUSDT `8h/B` rebuilt and prefix-validations clean; modest BTC/ETH context signal, not predictively promoted |
| 12 | `unsupervised_factor_layer` | engineering_validated_not_promoted | `rpf_factor_` | deterministic factor/anomaly context | BTCUSDT `8h/B` materialized; all factor timeframe-prefix validations passed |
| 13 | `sequence_embedding_layer` | engineering_validated_not_promoted | `rpf_seq_` | deterministic multi-timeframe sequence shape | BTCUSDT `8h/B` materialized; sequence-prefix validation passed |

## Current Post-Build Modeling TODO

Feature-family implementation has reached a complete deterministic v1 surface
for `BTCUSDT 8h/B`. The active next task is not another formula family. It is
model evaluation and gating:

1. Keep both binary direction targets:

   ```text
   target_cls_extreme_up_ge_2x_down_hvol_v2
   target_cls_extreme_down_ge_2x_up_hvol_v2
   ```

2. Use `regression_feature_engineering/walkforward/classify.py` for
   RPF-native binary classification experiments.
3. Evaluate binary target quality by regime, not by one global score.
4. Use label/performance diagnostics only as post-hoc analysis; never use
   same-batch label values as live features.
5. Validate the implemented live-safe regime gate described in
   `rpf_regime_gated_prediction_plan.md` and tracked in
   `rpf_regime_gate_implementation_todo.md`.
6. Return to feature formulas only if the gate analysis identifies a missing
   live-safe proxy for future up-dominant, down-dominant, two-sided, or
   no-edge regimes.

## Phase 1: Foundation And Alignment

Initial implementation:

- `regression_feature_engineering/core/alignment.py`
- `regression_feature_engineering/core/math.py`
- `regression_feature_engineering/materialize_features.py`

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

First result:

- All core assets now have Phase 1/2 feature roots for `8h_b`, `8h_c`,
  `24h_b`, `24h_c`, `7d_b`, and `7d_c`.
- All `48` asset/root validations reported `duplicate_count=0`,
  `null_feature_count=0`, `infinite_feature_count=0`, and no closed-bar
  availability violations across `15m`, `1h`, `4h`, `8h`, `12h`, or `1d`.
- Aggregate report index:
  `test_output/regression_feature_engineering_core_all_roots/validation_index.csv`.
- ES `7d/C` is internally valid but has shorter row coverage than matching
  session roots, so it remains a coverage caveat before cross-asset promotion.

## Phase 2: Volatility State

Initial implementation:

- `regression_feature_engineering/features/volatility_state.py`
- output prefix: `rpf_vol_`
- materializer family: `volatility_state`

Tasks:

- add ATR versus realized-vol dominance;
- add volatility compression percentile;
- add short/long volatility expansion ratio;
- add range-versus-return-vol mismatch;
- add causal expected horizon-volatility proxy.

Validation:

- compare each feature against all six target columns;
- check scale and tail quantiles by chronological window;
- reject duplicate volatility estimators that add no target-specific signal.

First result:

- All-core six-root validation covered `48` asset/root feature roots.
- Aggregate validation totals: `0` duplicate keys, `0` null feature cells,
  `0` infinite feature cells, and `0` future-close timing violations.
- Strongest absolute Spearman across roots ranged from `0.2578` to `0.7060`,
  with median `0.4334`.
- The strongest rank signals behaved as expected for a volatility family:
  current-volatility z-score and relative-median features were negatively
  associated with normalized future path width, while closed-bar range in
  volatility units was positively associated with future path width.
- BTCUSDT strongest absolute Spearman by root:
  - `8h/B`: `0.3997`
  - `8h/C`: `0.3841`
  - `24h/B`: `0.3991`
  - `24h/C`: `0.4424`
  - `7d/B`: `0.5113`
  - `7d/C`: `0.4977`
- Directional imbalance targets remained weaker, which is expected. Direction
  and opposite-target separation should come from `structural_room`,
  `acceptance_persistence`, `spike_breakout`, and `rejection_chop`.

## Phase 3: Structural Room

Initial implementation:

- `regression_feature_engineering/features/structural_room.py`
- output prefix: `rpf_room_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

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

First result:

- `BTCUSDT 8h/B` materialization with `foundation_alignment`,
  `volatility_state`, and `structural_room` produced `2,810,755` rows and
  `209` model-facing features: `29` `rpf_vol_` features and `180`
  `rpf_room_` features.
- Validation reported `duplicate_count=0`, `null_feature_count=0`,
  `infinite_feature_count=0`, and `0` future-close timing violations.
- Structural-room features added useful total path-width context. The strongest
  structural rank signal was `0.2424` absolute Spearman against
  `target_extreme_total`.
- Direct up/down imbalance remained weak: structural max absolute Spearman was
  about `0.0489` for `target_extreme_up_down_ratio`, `0.0336` for
  `target_mean_up_minus_down`, and `0.0237` for
  `target_extreme_up_minus_down`.
- Decision: keep the initial implementation for later ablation, but do not
  promote it as sufficient directional separation evidence. The next
  directional families should focus on accepted pressure, breakout/rejection,
  and persistence rather than static room alone.

Lookback sweep result:

- Report-only sweep command:
  `python -m regression_feature_engineering.experiments.structural_room_lookback_sweep --asset BTCUSDT --root 8h/B --timeframes 15m,1h,4h,8h,12h,1d --lookback-sets '2,4,8;4,8,16;4,16,48;8,24,72;16,48,144;24,72,240'`.
- Output report:
  `test_output/regression_feature_engineering_structural_room_sweeps/btcusdt_8h_b/lookback_sweep_summary.md`.
- Tested lookback sets: `2,4,8`, `4,8,16`, `4,16,48`,
  `8,24,72`, `16,48,144`, and `24,72,240`.
- Maximum directional imbalance signal stayed weak across the sweep. Best
  absolute Spearman remained about `0.0489` against
  `target_extreme_up_down_ratio`.
- Total path-width signal improved slightly with wider sets. Best absolute
  Spearman reached about `0.2521` against `target_extreme_total` for
  `8,24,72` and `24,72,240`.
- Decision: lookback tuning is useful as report-only optimization, but
  structural-room lookbacks alone do not solve directional separation. Keep the
  current `4,16,48` default until walk-forward ablation says otherwise, and use
  later dynamic families for directional pressure and persistence.

## Phase 4: Acceptance And Persistence

Initial implementation:

- `regression_feature_engineering/features/acceptance_persistence.py`
- output prefix: `rpf_accept_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

Tasks:

- add closes above/below value counts;
- add shallow pullback score;
- add trend efficiency ratio;
- add directional close-location average;
- add higher-timeframe alignment score.

Validation:

- test mean-target separation against extreme-target separation;
- reject features that only duplicate raw momentum without persistence signal.

First result:

- `BTCUSDT 8h/B` materialization with `foundation_alignment`,
  `volatility_state`, `structural_room`, and `acceptance_persistence` produced
  `2,810,755` rows and `410` model-facing features. The acceptance family added
  `201` `rpf_accept_` columns.
- Chunked materialization completed with peak RSS around `3.6GB` using
  `--batch-chunk-size 32`.
- Full-root safety checks plus a 15m diagnostic slice reported
  `duplicate_count=0`, `null_feature_count=0`, and `0` future-close timing
  violations.
- The 15m acceptance slice found strongest absolute Spearman around `0.0580`,
  slightly stronger than structural room's prior directional result around
  `0.0489`, but still weak.
- Decision: keep the implementation as an initial candidate. All diagnostic
  slices passed full-root safety checks: `15m`, `1h`, `4h`, `8h`, `12h`, `1d`,
  and `rpf_accept_tf_`. Run walk-forward ablations before promotion.
- Strongest full-root sampled rank signal by prefix:
  - `15m`: `0.0580`, `rpf_accept_15m_value_dist_l16_vol` against
    `target_reg_distance_down_mean_low_hvol_v2`
  - `1h`: `0.0578`, `rpf_accept_1h_value_dist_l4_vol` against
    `target_reg_distance_down_mean_low_hvol_v2`
  - `4h`: `0.0495`, `rpf_accept_4h_value_dist_l4_vol` against
    `target_reg_distance_down_mean_low_hvol_v2`
  - `8h`: `0.0498`, `rpf_accept_8h_value_dist_l4_vol` against
    `target_reg_distance_down_mean_low_hvol_v2`
  - `12h`: `0.0391`, `rpf_accept_12h_close_loc_avg_l48_bnd` against
    `target_mean_total`
  - `1d`: `0.0689`, `rpf_accept_1d_close_loc_avg_l48_bnd` against
    `target_mean_total`
  - `tf`: `0.0473`, `rpf_accept_tf_bull_agreement_share_bnd` against
    `target_reg_distance_down_mean_low_hvol_v2`
- Bounded lookback sweep on the first `200` BTCUSDT `8h/B` batches completed
  without OOM: `96,000` rows, `47,987` valid rows, and peak RSS about `1.38GB`.
  The strongest mean-direction signal was `0.2850` absolute Spearman from
  `rpf_accept_12h_return_persist_l72_bnd` against
  `target_mean_up_minus_down`. This supports testing longer acceptance
  lookbacks, but the evidence is still bounded-sample only.

Memory note:

- Do not run broad diagnostics with `--diagnostic-feature-prefix rpf_accept_`
  on the full root by default. Use timeframe prefixes such as
  `rpf_accept_15m_` or lower `--signal-sample-rows`.
- Acceptance lookback sweeps are report-only and default to `--batch-limit 200`.
  Use `--full-root` only for intentional high-memory runs.
- Compliance check:
  `regression_feature_engineering/reports/acceptance_persistence_plan_compliance_2026-06-02.md`.
  It confirms the initial family is implemented, with true consecutive
  accepted-duration/run-length marked as the remaining partial item.

## Phase 5: Temporal Memory Transforms

Initial implementation:

- `regression_feature_engineering/features/temporal_memory_transforms.py`
- output prefix: `rpf_mem_`
- materializer family: `temporal_memory_transforms`
- default lags: `1`, `16`
- default EWM spans: `16`, `64`
- default rank-position windows: `64`
- default difference lags: `16`

Tasks:

- add explicit lag features for selected validated base signals;
- add EWM means, EWM slopes, and EWM residuals for volatility, room, and
  acceptance features;
- add rolling rank-position proxies for distance, volatility, pressure, and
  volume proxies;
- add first and second differences for selected bounded signals;
- keep this family as a transform layer, not a source of raw price columns.

Validation:

- prove every lag/EWM/rank uses prior rows only;
- compare transformed features against the untransformed parent features;
- reject transforms that duplicate parent signal without target-specific value;
- verify memory use stays bounded by applying transforms only to a curated
  source list, not every generated column.

First implementation result:

- Phase 5 is implemented as a streaming stateful transform so chunked
  materialization does not reset lags, EWM state, rank-position windows, or
  difference history at chunk boundaries.
- Source selection is curated from already-generated `rpf_vol_`, `rpf_room_`,
  and `rpf_accept_` columns. It does not transform every feature column.
- All `rpf_mem_` values are prior-row only. The current row updates transform
  state after its memory features are emitted.
- Unit tests prove chunk-safe lag/EWM/diff/rank-position behavior and manifest
  writing with `temporal_memory_transforms`.
- Historical Phase 5-only `BTCUSDT 8h/B` materialization produced
  `2,810,755` rows, `1,103` model-facing features, `693` `rpf_mem_`
  features, duplicate count `0`, and null feature count `0`.
- Sliced memory-prefix validation reported duplicate count `0`, null feature
  count `0`, infinite feature count `0`, and future-close violations `0` across
  `rpf_mem_vol_*`, `rpf_mem_room_*`, and `rpf_mem_accept_*`.
- Strongest sampled Phase 5 signals are volatility/path-width transforms:
  `rpf_mem_vol_tb_vol_z_l1440_lag1` reached about `0.3997` absolute Spearman
  against `target_extreme_total`, and
  `rpf_mem_vol_tb_vol_rel_median_l1440_lag1` reached about `0.3858`.
- Clean RPF-native walk-forward now uses `regression_only` with
  `all_manifest_features` for new searches, so all model-facing RPF manifest
  columns are passed to CatBoost. `target_specific_v2` remains available only
  as a historical/optional policy, not the active clean optimization default.
- The broad `--max-runs 24` grid started before this fix is not promotion
  evidence: it tested only early `regression_only` configs and reported
  prediction-batch metrics as if they were selection metrics.

First dry-run command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-limit 10 \
  --batch-chunk-size 16 \
  --dry-run
```

## Phase 6: Rejection And Chop

Initial implementation:

- `regression_feature_engineering/features/rejection_chop.py`
- output prefix: `rpf_chop_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

Tasks:

- add upper and lower rejection scores;
- add two-sided volatility ratio;
- add reversal count and path entropy;
- add failed breakout count;
- add realized path efficiency.

Implementation notes:

- Upper/lower rejection uses closed-bar wick share, bounded to `[0,1]`.
- Two-sided chop uses recent return-sign persistence: lower persistence means
  stronger two-sided behavior.
- Failed upside/downside break counts use prior closed rolling high/low
  channels; the current bar must break the prior level and close back inside.
- Path efficiency is absolute net return divided by cumulative absolute return;
  path chop is `1 - path_efficiency`.
- These features are closed-bar-as-of only and do not use future target
  diagnostics.

Validation:

- test whether features separate high-extreme/low-mean cases;
- check that rejection features do not become future-diagnostic proxies.

First implementation command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,rejection_chop \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-limit 10 \
  --batch-chunk-size 4 \
  --dry-run
```

Promotion status:

- Not predictively promoted.
- Focused unit/materializer tests pass for source formulas, bounded outputs,
  manifest writing, and family gating.
- Historical Phase 6-only `BTCUSDT 8h/B` materialization with
  `rejection_chop` produced `2,810,755` rows, `1,283` model-facing features,
  `180` `rpf_chop_*` features, duplicate count `0`, and null feature count
  `0`.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_chop_15m_`, `rpf_chop_1h_`, `rpf_chop_4h_`, `rpf_chop_8h_`,
  `rpf_chop_12h_`, and `rpf_chop_1d_`.
- Strongest absolute Spearman by slice: `15m=0.0843`, `1h=0.0465`,
  `4h=0.0509`, `8h=0.0556`, `12h=0.1187`, and `1d=0.1296`.
- Signal interpretation: long-timeframe rejection suppresses mean/total path
  persistence; short-timeframe chop helps total extreme-width context.
  Directional up-vs-down separation remains modest.

## Phase 7: Spike And Breakout

Initial implementation:

- `regression_feature_engineering/features/spike_breakout.py`
- output prefix: `rpf_spike_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

Tasks:

- add squeeze-release setup;
- add breakout and breakdown proximity;
- add one-sided impulse score;
- add volume-confirmed impulse;
- add tail-risk asymmetry.

Implementation notes:

- Breakout and breakdown reference levels use previous closed rolling
  high/low channels only.
- Breakout proximity and active breakout/breakdown strength are measured in
  prediction-time volatility units.
- Squeeze/release features are bounded ratios from closed-bar range state.
- One-sided impulse combines closed-bar body direction, close location, and
  release state.
- Volume-confirmed impulse uses current closed-bar volume relative to prior
  rolling median volume.
- Tail-risk asymmetry combines directional impulse and volume-confirmed
  directional impulse into a bounded signed feature.

Validation:

- focus on high-distance p95/p99 ranking for extreme targets;
- prove breakout levels come from closed or prior windows.

First implementation status:

- Focused unit/materializer tests pass for prior-channel usage, bounded
  squeeze/release/impulse outputs, volume-confirmed impulse, manifest writing,
  and family gating.
- Bounded dry-run with `BTCUSDT 8h/B`, `15m`, `10` batches, and Phase 1-7
  non-memory families produced `4,800` rows, `158` model-facing features,
  duplicate count `0`, and null feature count `0`.
- Full `BTCUSDT 8h/B` materialization with `spike_breakout` produced
  `2,810,755` rows, `1,571` model-facing features, `288` `rpf_spike_*`
  features, duplicate count `0`, and null feature count `0`.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_spike_15m_`, `rpf_spike_1h_`, `rpf_spike_4h_`, `rpf_spike_8h_`,
  `rpf_spike_12h_`, and `rpf_spike_1d_`.
- Strongest absolute Spearman by slice: `15m=0.1998`, `1h=0.2364`,
  `4h=0.2299`, `8h=0.2381`, `12h=0.2338`, and `1d=0.2304`.
- Bin-spread checks show high breakout-proximity bins separating
  `target_extreme_total` by roughly `0.3` to `0.6` horizon-volatility units in
  sampled validation.
- Not predictively promoted. Directional up-vs-down separation remains modest;
  promotion requires walk-forward ablation.

## Phase 8: Liquidity And Volume Pressure

Initial implementation:

- `regression_feature_engineering/features/liquidity_volume_pressure.py`
- output prefix: `rpf_liq_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

Tasks:

- add volume z-score by timeframe;
- add dollar-volume proxy;
- add volume-on-up versus volume-on-down pressure;
- add OBV or money-flow slope;
- add volume wake-up after compression.

Implemented formulas:

- `volume_z`: current closed-bar volume versus prior rolling volume mean/std,
  clipped to `[-8, 8]`;
- `dollar_volume_rel`: bounded current typical-price dollar-volume versus
  prior rolling median dollar-volume;
- `volume_wakeup`: bounded confluence of current relative volume and current
  range release versus prior rolling range;
- `up_volume_share` and `down_volume_share`: rolling volume share on positive
  and negative closed-bar returns;
- `volume_pressure_balance`: signed up-minus-down volume share;
- `obv_slope`: rolling OBV-step sum divided by rolling volume sum;
- `money_flow_balance`: rolling close-location money-flow proxy divided by
  rolling volume sum;
- `zero_volume_share`: rolling share of zero-volume bars, kept as explicit
  session/synthetic/no-trade context.

Validation:

- handle zero-volume synthetic/session rows explicitly;
- verify no nulls or infinities for session assets.
- validate by narrow prefixes such as `rpf_liq_15m_` to keep diagnostics
  memory-bounded.

First implementation status:

- Focused unit/materializer tests cover zero-volume safety, directional volume
  pressure, bounded outputs, manifest writing, and family gating.
- Bounded dry-run with `BTCUSDT 8h/B`, `15m`, `10` batches, and families
  through Phase 8 produced `4,800` rows, `185` model-facing features,
  duplicate count `0`, and null feature count `0`. The `15m` liquidity slice
  adds `27` `rpf_liq_*` columns from `3` lookbacks x `9` formulas.
- Full `BTCUSDT 8h/B` materialization with `liquidity_volume_pressure`
  produced `2,810,755` rows, `1,733` model-facing features, `162` `rpf_liq_*`
  features, duplicate count `0`, and null feature count `0`.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_liq_15m_`, `rpf_liq_1h_`, `rpf_liq_4h_`, `rpf_liq_8h_`,
  `rpf_liq_12h_`, and `rpf_liq_1d_`.
- Strongest absolute Spearman by slice: `15m=0.1132`, `1h=0.1311`,
  `4h=0.1595`, `8h=0.0925`, `12h=0.1190`, and `1d=0.0558`.
- Directional high-low quintile spreads are present, especially
  `rpf_liq_15m_volume_pressure_balance_l48_bnd` against
  `target_extreme_up_minus_down` with spread `0.2382`, but rank correlations
  remain modest. Not predictively promoted.
- Bounded dry-run command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,rejection_chop,spike_breakout,liquidity_volume_pressure \
  --timeframes 15m \
  --batch-limit 10 \
  --batch-chunk-size 4 \
  --dry-run
```

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1d/
```

## Phase 9: Regime Calendar State

Initial implementation:

- `regression_feature_engineering/features/regime_calendar_state.py`
- output prefix: `rpf_regime_`
- default lookbacks: `4`, `16`, and `48` closed source bars per timeframe

Tasks:

- add volatility-regime flags from causal volatility state;
- add trend/range regime flags from efficiency, chop, and structural features;
- add session progress, minutes to close/open, opening range position, and
  prior-session range where canonical metadata exists;
- add cyclic hour/day encodings that are known at prediction time;
- keep crypto/session behavior explicit because not all assets trade seven days
  a week.

Implemented formulas:

- UTC hour sine/cosine and day-of-week sine/cosine from prediction timestamp;
- UTC weekend flag from prediction timestamp;
- latest closed-bar market-open, synthetic no-trade, gap-fill, session-open,
  session-close, weekly-open, and weekly-close metadata;
- bounded minutes-since-previous-real-bar and minutes-to-close;
- bounded session progress from closed canonical session metadata;
- closed-bar volatility-relative and volatility-expanding flags;
- closed-bar trend efficiency, trend sign, signed trend alignment,
  range/chop score, bullish trend flag, and bearish trend flag.

Validation:

- prove calendar features are known before prediction;
- verify closed sessions are not filled with artificial rows;
- ablate regime gates separately from their underlying continuous features;
- validate session assets and crypto separately before full-core rollout.

First implementation status:

- Focused unit/materializer tests cover known timestamp calendar features,
  closed-bar session metadata usage, trend/range regime sources, bounded
  outputs, manifest writing, and family gating.
- Bounded dry-run with `BTCUSDT 8h/B`, `15m`, `10` batches, and Phase 1-9
  non-memory families produced `4,800` rows, `224` model-facing features,
  duplicate count `0`, and null feature count `0`. The `15m` regime slice adds
  `39` `rpf_regime_*` columns from `5` row-level calendar features, `10`
  closed-bar session metadata features, and `24` lookback regime features.
- Bounded session-asset dry-run with `ES 8h/B`, `15m`, `10` batches, and
  Phase 1-9 non-memory families produced `4,620` rows, `224` model-facing
  features, duplicate count `0`, and null feature count `0`.
- Full `BTCUSDT 8h/B` materialization with `regime_calendar_state` produced
  `2,810,755` rows, `1,942` model-facing features, `209` `rpf_regime_*`
  features, duplicate count `0`, and null feature count `0`.
- A single corrupted parquet batch (`batch_2511.parquet`) was repaired by
  rebuilding only that batch from the same causal materializer path. A full
  feature-batch readability scan then passed with `0` unreadable batches.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_regime_utc_`, `rpf_regime_15m_`, `rpf_regime_1h_`, `rpf_regime_4h_`,
  `rpf_regime_8h_`, `rpf_regime_12h_`, and `rpf_regime_1d_`.
- Strongest absolute Spearman by slice: `utc=0.2916`, `15m=0.1603`,
  `1h=0.1803`, `4h=0.1770`, `8h=0.1473`, `12h=0.1474`, and `1d=0.1473`.
- Not predictively promoted. Signals are mostly calendar/session and
  path-width context rather than clean up/down direction.
- Bounded dry-run command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state \
  --timeframes 15m \
  --batch-limit 10 \
  --batch-chunk-size 4 \
  --dry-run
```

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

## Phase 10: Interaction And Confluence

Implementation status: `engineering_validated_not_promoted`.

Tasks:

- add low-volatility compression plus breakout/breakdown proximity;
- add trend alignment plus acceptance/persistence;
- add volume wake-up plus one-sided impulse;
- add rejection/chop gates that suppress mean-target confidence;
- add TA raw/compact flag confluence only as optional context, never as label
  authority.

Initial implementation:

- `regression_feature_engineering/features/interaction_confluence.py`
- default lookbacks: `4,16,48`
- output prefix: `rpf_conf_`
- outputs per timeframe/lookback:
  - `up_squeeze_break`, `down_squeeze_break`, `squeeze_break_balance`;
  - `up_trend_accept`, `down_trend_accept`, `trend_accept_balance`;
  - `up_volume_impulse`, `down_volume_impulse`, `volume_impulse_balance`;
  - `up_clean_persist`, `down_clean_persist`, `clean_persist_balance`;
  - `up_room_pressure`, `down_room_pressure`, `room_pressure_balance`.
- all outputs are bounded `0..1` or signed bounded `-1..1`;
- formulas use only already materialized causal component features from:
  `rpf_room_*`, `rpf_accept_*`, `rpf_chop_*`, `rpf_spike_*`,
  `rpf_liq_*`, and `rpf_regime_*`.
- the materializer rejects `interaction_confluence` unless all required
  component families are requested.

Validation:

- test every interaction against its component features;
- reject interactions that do not improve signal over both components;
- track sparsity, activation rate, and stability across chronological windows;
- verify no interaction uses label or future diagnostics.

First commands:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-chunk-size 16
```

```bash
for PREFIX in \
  rpf_conf_15m_ \
  rpf_conf_1h_ \
  rpf_conf_4h_ \
  rpf_conf_8h_ \
  rpf_conf_12h_ \
  rpf_conf_1d_
do
  SAFE="${PREFIX%_}"
  python -m regression_feature_engineering.validate_features \
    --assets BTCUSDT \
    --roots 8h/B \
    --timeframes 15m,1h,4h,8h,12h,1d \
    --signal-sample-rows 25000 \
    --diagnostic-feature-prefix "$PREFIX" \
    --output-dir "test_output/regression_feature_engineering_btcusdt_8h_b_confluence_${SAFE}"
done
```

First validation result:

- Full materialization produced `2,810,755` rows, `2,212` model-facing
  features, `270` `rpf_conf_*` features, duplicate count `0`, and null feature
  count `0`.
- All `5,856` batch parquet files were readable with a consistent schema.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_conf_15m_`, `rpf_conf_1h_`, `rpf_conf_4h_`, `rpf_conf_8h_`,
  `rpf_conf_12h_`, and `rpf_conf_1d_`.
- Strongest absolute Spearman by slice: `15m=0.1200`, `1h=0.0996`,
  `4h=0.1530`, `8h=0.0933`, `12h=0.0838`, and `1d=0.1002`.
- Strongest rank signals are mostly squeeze-break relationships against
  `target_extreme_total`.
- Directional evidence appears more in high-low quintile spreads, especially
  volume-impulse, clean-persistence, and squeeze-break balance features against
  `target_extreme_up_minus_down`.
- Not predictively promoted; keep for controlled ablation and target-specific
  selection.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1d/
```

## Phase 11: Cross-Asset Context

Implementation status: `engineering_validated_not_promoted`.

Tasks:

- start with deterministic pair features: BTC/ETH, ES/NQ, EURUSD/USDJPY;
- add return spread, volatility spread, relative strength, and rolling
  correlation;
- keep raw foreign prices out of model-facing features;
- defer beta, PCA, cointegration, and lead-lag until this phase validates.

Initial implementation:

- `regression_feature_engineering/features/cross_asset_context.py`
- default peer map:
  - `BTCUSDT <-> ETHUSDT`;
  - `ES <-> NQ`;
  - `EURUSD <-> USDJPY`;
  - `GC <-> CL`.
- default lookbacks: `4,16,48`
- output prefix: `rpf_xasset_`
- pair source bars are built by exact canonical-bar timestamp match before
  closed-bar as-of alignment to 1m prediction rows;
- no raw foreign prices or volumes are emitted as model-facing columns;
- outputs per context asset/timeframe/lookback:
  - `ret_spread`;
  - `rel_strength`;
  - `range_spread`;
  - `corr`;
  - `context_pressure`;
  - `common_direction`;
  - `context_range_share`;
  - `volume_rel_spread`.

Validation:

- test exact timestamp or closed-bar availability;
- ablate pair groups independently;
- verify missing context handling is explicit and does not create stale rows.

First commands:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence,cross_asset_context \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --xasset-context-assets auto \
  --batch-chunk-size 16
```

```bash
for PREFIX in \
  rpf_xasset_ethusdt_15m_ \
  rpf_xasset_ethusdt_1h_ \
  rpf_xasset_ethusdt_4h_ \
  rpf_xasset_ethusdt_8h_ \
  rpf_xasset_ethusdt_12h_ \
  rpf_xasset_ethusdt_1d_
do
  SAFE="${PREFIX%_}"
  python -m regression_feature_engineering.validate_features \
    --assets BTCUSDT \
    --roots 8h/B \
    --timeframes 15m,1h,4h,8h,12h,1d \
    --signal-sample-rows 25000 \
    --diagnostic-feature-prefix "$PREFIX" \
    --output-dir "test_output/regression_feature_engineering_btcusdt_8h_b_xasset_${SAFE}"
done
```

First validation result:

- Full materialization produced `2,810,755` rows, `2,356` model-facing
  features, `144` `rpf_xasset_*` features, duplicate count `0`, and null
  feature count `0`.
- All `5,856` batch parquet files were readable with a consistent schema.
- Prefix-level validations reported `0` duplicate keys, `0` null feature
  cells, `0` infinite feature cells, and `0` future-close violations for
  `rpf_xasset_ethusdt_15m_`, `rpf_xasset_ethusdt_1h_`,
  `rpf_xasset_ethusdt_4h_`, `rpf_xasset_ethusdt_8h_`,
  `rpf_xasset_ethusdt_12h_`, and `rpf_xasset_ethusdt_1d_`.
- Strongest absolute Spearman by slice: `15m=0.0481`, `1h=0.0384`,
  `4h=0.0395`, `8h=0.0424`, `12h=0.0495`, and `1d=0.0581`.
- Strongest rank signals are modest and mostly target total path-width or
  mean-total behavior.
- Directional evidence appears more in high-low quintile spreads, especially
  relative strength, relative volume, and context pressure against
  `target_extreme_up_minus_down`.
- Not predictively promoted; keep for controlled ablation and target-specific
  selection.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1d/
```

## Phase 12: Unsupervised Factor Layer

Implementation status: `engineering_validated_not_promoted`.

Tasks:

- implement deterministic static factor proxies from already causal component
  features;
- avoid globally fitted PCA, clustering, or anomaly models in static artifacts;
- learned PCA/clustering remains train-window-only inside later walk-forward
  experiments;
- output prefix: `rpf_factor_`;
- default lookbacks: `4,16,48`;
- features summarize path-width, direction, persistence, shock, rejection,
  cross-asset context, anomaly state, and chop-filtered clean direction.

Validation:

- prove outputs are finite, bounded, and derived only from existing causal
  `rpf_*` component features;
- prove no raw OHLCV, label, or future diagnostic columns are used;
- validate `rpf_factor_*` prefix slices before walk-forward ablation;
- treat outputs as context only, never label authority.

## Phase 13: Sequence Embedding Layer

Implementation status: `engineering_validated_not_promoted`.

Tasks:

- implement deterministic multi-timeframe sequence-shape proxies from
  `rpf_factor_*` columns;
- avoid learned CNN/encoder outputs in static artifacts;
- learned sequence encoders remain train-window-only inside later walk-forward
  experiments;
- output prefix: `rpf_seq_`;
- default lookbacks: `4,16,48`;
- features summarize direction stack, short-vs-long slope, dispersion,
  consensus, width stack, shock stack, persistence stack, and clean direction.

Validation:

- prove outputs are finite, bounded, and derived only from causal factor
  proxies;
- prove `sequence_embedding_layer` cannot run unless `unsupervised_factor_layer`
  is present in the same materialization request;
- validate `rpf_seq_*` prefix slices before walk-forward ablation;
- compare sequence-shape proxies against deterministic families by later
  walk-forward ablation.

First commands:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence,cross_asset_context,unsupervised_factor_layer,sequence_embedding_layer \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --xasset-context-assets auto \
  --batch-chunk-size 16
```

```bash
for PREFIX in \
  rpf_factor_15m_ rpf_factor_1h_ rpf_factor_4h_ \
  rpf_factor_8h_ rpf_factor_12h_ rpf_factor_1d_ \
  rpf_seq_
do
  SAFE="${PREFIX%_}"
  python -m regression_feature_engineering.validate_features \
    --assets BTCUSDT \
    --roots 8h/B \
    --timeframes 15m,1h,4h,8h,12h,1d \
    --signal-sample-rows 25000 \
    --diagnostic-feature-prefix "$PREFIX" \
    --output-dir "test_output/regression_feature_engineering_btcusdt_8h_b_phase12_13_${SAFE}"
done
```

First materialization result:

- command: Phase 1-13 materialization on full BTCUSDT `8h/B`;
- rows: `2,810,755`;
- model-facing features: `2,530`;
- duplicate keys: `0`;
- null feature cells: `0`;
- contribution: prior `2,356` features plus `144` `rpf_factor_*` features and
  `30` `rpf_seq_*` features.

Validation note:

- the first validation loop failed before report writing because the full
  Phase 1-13 family list exceeded the filesystem path-component length;
- `validate_features.py` now uses bounded hashed family slugs for long family
  lists;
- `rpf_seq_` validation passed after the fix with duplicate count `0`, null
  feature count `0`, future-close violations `0`, and strongest absolute
  Spearman `0.1215`;
- all `rpf_factor_*` timeframe-prefix validations passed with duplicate count
  `0`, null feature count `0`, infinite feature count `0`, and future-close
  violations `0`;
- strongest absolute Spearman by factor slice:
  - `rpf_factor_15m_`: `0.1362`;
  - `rpf_factor_1h_`: `0.1689`;
  - `rpf_factor_4h_`: `0.1826`;
  - `rpf_factor_8h_`: `0.0552`;
  - `rpf_factor_12h_`: `0.1021`;
  - `rpf_factor_1d_`: `0.0505`;
- Phase 12/13 are engineering-valid but still require walk-forward ablation
  before predictive promotion.

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
- target relationship table for all six target columns;
- walk-forward ablation result;
- final status: `pending`, `accepted`, `quarantined`, or `rejected`.

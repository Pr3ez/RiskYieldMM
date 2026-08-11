# Regression Feature Workflow

## Purpose

Describe the intended step-by-step workflow for regression feature production.

## Current Status

Phase 1 through Phase 13 are implemented, materialized, and
engineering-validated on `BTCUSDT 8h/B`. All `rpf_factor_*`
timeframe-prefix validations and the `rpf_seq_*` validation passed; none of
these families are predictively promoted yet.
All Phase 8 liquidity/volume-pressure, Phase 9 regime/calendar-state, Phase 10
interaction/confluence, and Phase 11 cross-asset-context prefix validations are
clean. Walk-forward ablation remains the next promotion gate after the
deterministic family buildout. Wide validations must be run in diagnostic
prefix slices to keep memory bounded.

## Scope

The workflow targets `regression_path_features_v1` for
`distance_horizon_vol_v2`.

## Source Of Truth

- Architecture: `architecture.md`
- Data contract: `data_contract.md`
- Feature coverage: `feature_coverage_matrix.md`
- Implementation TODO: `feature_implementation_todo.md`
- Clean RPF walk-forward: `clean_rpf_walkforward_reset.md`
- Detailed walk-forward report: `rpf_walkforward_optimization_report.md`
- Optimization: `optimization_strategy.md`
- Binary classification: `rpf_binary_classification_experiment.md`
- Binary prediction pipeline contract:
  `rpf_binary_prediction_pipeline_contract.md`
- Regime-gated prediction: `rpf_regime_gated_prediction_plan.md`
- Regime-gate implementation tracker:
  `rpf_regime_gate_implementation_todo.md`
- Signal-bank batch selection: `rpf_signal_bank_batch_selection.md`
- EMA-regime classifier batch selection:
  `rpf_ema_regime_batch_selection.md` (abandoned active path; historical reference only)

## What This Does Not Decide

This document does not choose feature formulas or final CatBoost parameters.

## Workflow Steps

1. Materialize `distance_horizon_vol_v2` labels for selected assets and roots.
2. Validate generated target roots before feature optimization.
3. Load canonical local inputs for one asset/root.
4. Load matching `distance_horizon_vol_v2` labels and diagnostics.
5. Run zero-target validation before feature optimization.
6. Build causal candidate features by family:
   - volatility state;
   - structural room;
   - acceptance and persistence;
   - temporal memory transforms;
   - rejection and chop;
   - spike and breakout;
   - liquidity and volume pressure;
   - regime and calendar/session state;
   - interaction and confluence;
   - cross-asset context.
7. Validate feature quality and temporal safety.
8. Write Silver regression features with a manifest and feature catalog.
9. Assemble Gold regression features for Stage-1 exact timestamp joins.
10. Run clean RPF-native readiness and freeze sparse windows.
11. Run clean RPF walk-forward with all model-facing manifest features.
12. Optimize only RPF window geometry and CatBoost hyperparameters in staged
    locks.
13. Compare the final locked RPF confirmation run against a same-window
    historical HTF baseline report.
14. For binary decision-layer work, evaluate both UP and DOWN `2x` targets by
    regime before making any promotion decision.
15. For the current binary path, run chronological recent windows with
    labeled-row-only supervised learning, train-only ElasticNet feature
    selection, and CatBoost final prediction.
16. Score candidate configs by prediction-batch decision cost, but require
    per-window stability: no whole-batch-positive collapse, no zero-positive
    collapse across most windows, bounded per-window FPR, and sufficient
    threshold-pass rate.
17. Reserve holdout windows with `--holdout-steps`; holdout is confirmation
    only and must not feed back into the same search.
18. Add CNN sequence embeddings only after the chronological tabular contract
    is stable; CNN may use all causal rows as sequence context, but supervised
    loss and scoring must use only labeled eligible anchors.
19. Treat EMA gates and EMA-regime banks as abandoned for the active path.
    Keep their code and docs only to reproduce historical evidence. Learned
    gates, signal banks, and decision banks are also deferred diagnostics
    unless a new plan explicitly reopens them.
20. Promote only after target-specific stability, tail coverage, and
    regime-conditioned false-positive control improve.

The full rollout repeats the same workflow for each core asset and each root ID.
Target materialization and validation details are tracked in
`regression_target_rollout.md`.
Feature implementation status is tracked in `feature_implementation_todo.md`.

Initial materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-limit 10
```

All-core Phase 1/2 materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets core \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --families foundation_alignment,volatility_state \
  --timeframes 15m,1h,4h,8h,12h,1d
```

All-core Phase 1/2 validation command:

```bash
python -m regression_feature_engineering.validate_features \
  --assets core \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --output-dir test_output/regression_feature_engineering_core_all_roots
```

The first all-core six-root pass validated clean feature roots with no duplicate
keys, no null feature cells, no infinite feature cells, and no closed-bar future
availability violations. Feature-family acceptance still requires walk-forward
ablation. ES `7d/C` is internally valid but has shorter row coverage than the
matching session roots, so it should be reviewed before cross-asset 7d/C
promotion.

For easier monitoring, the same commands can be staged by asset:

```bash
for ASSET in BTCUSDT ETHUSDT EURUSD USDJPY GC CL ES NQ; do
  python -m regression_feature_engineering.materialize_features \
    --assets "$ASSET" \
    --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
    --families foundation_alignment,volatility_state \
    --timeframes 15m,1h,4h,8h,12h,1d
done
```

Phase 3 structural-room benchmark command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room \
  --timeframes 15m,1h,4h,8h,12h,1d
```

```bash
python -m regression_feature_engineering.validate_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --output-dir test_output/regression_feature_engineering_btcusdt_8h_b_structural_room
```

The first structural-room pass is technically clean but not promoted. It adds
path-width context, while direct up/down imbalance remains weak.

Report-only structural-room lookback sweep command:

```bash
python -m regression_feature_engineering.experiments.structural_room_lookback_sweep \
  --asset BTCUSDT \
  --root 8h/B \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --lookback-sets '2,4,8;4,8,16;4,16,48;8,24,72;16,48,144;24,72,240' \
  --output-dir test_output/regression_feature_engineering_structural_room_sweeps
```

This command does not rewrite feature roots under `data/`. It computes
structural-room candidates in memory, writes correlation and bin-spread reports
under `test_output/`, and should be used before changing default lookback
parameters. The command now defaults to the first `200` batches for memory
safety. Use `--full-root` only for intentional high-memory runs.

First sweep result for `BTCUSDT 8h/B`:

- directional imbalance signal did not materially improve; best absolute
  Spearman stayed near `0.0489`;
- total path-width signal improved slightly to about `0.2521` with
  `8,24,72` and `24,72,240`;
- therefore the next implementation priority remains dynamic pressure,
  acceptance, rejection, and breakout families.

Phase 4 acceptance/persistence materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-chunk-size 32
```

First safe acceptance/persistence validation command:

```bash
python -m regression_feature_engineering.validate_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --signal-sample-rows 25000 \
  --diagnostic-feature-prefix rpf_accept_15m_ \
  --output-dir test_output/regression_feature_engineering_btcusdt_8h_b_acceptance_15m
```

Validation performs exact duplicate, row-join, and alignment checks across the
full root, but expensive feature/target diagnostics are sampled and limited to
the selected prefix. Broad prefixes such as `rpf_accept_` select hundreds of
columns and should be split into timeframe slices unless a high-memory run is
intentional.

First `BTCUSDT 8h/B` acceptance result:

- materialization produced `2,810,755` rows and `410` model-facing features,
  including `201` `rpf_accept_` features;
- duplicate keys, null feature cells, and future-close violations were `0`;
- all diagnostic prefixes passed full-root safety checks: `15m`, `1h`, `4h`,
  `8h`, `12h`, `1d`, and `rpf_accept_tf_`;
- strongest full-root sampled signals remained modest:
  - `15m`: `0.0580`
  - `1h`: `0.0578`
  - `4h`: `0.0495`
  - `8h`: `0.0498`
  - `12h`: `0.0391`
  - `1d`: `0.0689`
  - `tf`: `0.0473`
- next validation step is walk-forward ablation before any promotion.

Safe report-only acceptance lookback sweep command:

```bash
python -m regression_feature_engineering.experiments.acceptance_persistence_lookback_sweep \
  --asset BTCUSDT \
  --root 8h/B \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --lookback-sets '2,4,8;4,8,16;4,16,48;8,24,72;16,48,144' \
  --batch-limit 200 \
  --output-dir test_output/regression_feature_engineering_acceptance_sweeps
```

Phase 5 temporal-memory validation completed for the sliced prefixes:

```text
rpf_mem_vol_15m_, rpf_mem_vol_1h_, rpf_mem_vol_4h_, rpf_mem_vol_8h_,
rpf_mem_vol_12h_, rpf_mem_vol_1d_, rpf_mem_vol_atr_std_,
rpf_mem_vol_tb_vol_rel_median_, rpf_mem_vol_tb_vol_z_,
rpf_mem_room_15m_, rpf_mem_room_1h_, rpf_mem_room_4h_, rpf_mem_room_8h_,
rpf_mem_room_12h_, rpf_mem_room_1d_,
rpf_mem_accept_15m_, rpf_mem_accept_1h_, rpf_mem_accept_4h_,
rpf_mem_accept_8h_, rpf_mem_accept_12h_, rpf_mem_accept_1d_,
rpf_mem_accept_tf_
```

All reports had duplicate count `0`, null feature count `0`, and future-close
violations `0`. The strongest sampled signal remains volatility/path-width:
`rpf_mem_vol_tb_vol_z_l1440_lag1` reached about `0.40` absolute Spearman
against `target_extreme_total`. Directional acceptance and room signals remain
modest, so they require walk-forward proof rather than promotion from
correlation alone.

Clean RPF walk-forward readiness:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage readiness \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --n-steps 20
```

This stage proves the clean runner can join `regression_path_features_v1` and
`distance_horizon_vol_v2` labels by exact `timestamp,batch_id`, then freeze
sparse-safe windows. It also writes `label_window_index.parquet` and rejects
windows where train labels overlap validation rows, validation labels overlap
prediction rows, or zero-embargo labels are not self-contained in their source
batch. Readiness also records feature family counts, target zero/one rates, and
target mean/std drift between train, validation, and prediction windows.

Clean RPF geometry tuning:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage geometry \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<baseline_probe_run_id> \
  --lookback-choices 80,120,160,180 \
  --val-choices 8,10,12 \
  --embargo-choices 0 \
  --n-steps 15 \
  --n-trials 12 \
  --task-type GPU
```

Use `--n-trials 12` to cover the full `4 x 3 x 1` geometry grid once.
Smaller values are smoke runs only.

Clean RPF CatBoost tuning:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage core_model \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<geometry_run_id> \
  --iterations-choices 400,800,1200 \
  --depth-choices 3,4 \
  --learning-rate-choices 0.005,0.01,0.02 \
  --l2-leaf-reg-choices 100,200,300 \
  --early-stopping-rounds-choices 50,100,150 \
  --od-wait-choices 50,100,150 \
  --n-steps 15 \
  --n-trials 18 \
  --task-type GPU
```

The clean RPF optimizer baseline keeps the feature policy fixed at
`all_manifest_features`. It uses every model-facing manifest feature and does
not run selected-feature counts, Spearman thresholds, dedupe thresholds, clip
quantiles, stability segments, or tail quantiles.

The current binary-classification experiment should use
`--feature-policy elasticnet_logistic_v1` with CatBoost prediction. ElasticNet
is a selector only:

```text
Train | Validation | Prediction
-> compute selector mean/std on Train only
-> fit sparse ElasticNet LogisticRegression selector on scaled Train
-> freeze selected feature list for validation
-> optionally train causal CNN embeddings on scaled Train rows only
-> train CatBoost on selected scaled Train columns
-> score scaled Validation columns for early stopping and threshold/cap selection
-> freeze validation-selected feature mask
-> refit selector scaler on Train+Validation for that frozen mask
-> optionally refit causal CNN embeddings on scaled Train+Validation rows
-> refit CatBoost on selected scaled Train+Validation columns
-> score the held-out Prediction batch
```

The selector grid can tune `C`, `l1_ratio`, selected feature cap,
`coef_eps`, and the train-only ElasticNet prefilter candidate cap. The
prefilter ranks candidate columns by train-only standardized class separation
before the sparse ElasticNet fit, which keeps the selector causal while making
the walk-forward run practical. The scaler type is fixed to train-only
standardization.

For binary trading-decision experiments, use the Optuna wrapper:

```bash
python -m regression_feature_engineering.walkforward.classify_optuna
```

It is chronological-only and defaults to `--objective-metric
stable_prediction_quality`. Validation builds the fold model; aggregate
prediction-batch metrics score the trial. A later untouched confirmation
window is still needed after tuning. Use `--holdout-steps` to reserve that
confirmation slice inside the same command; trials are selected on tuning
windows and the selected best config is replayed once on the holdout windows
only when the selected tuning trial has `status=ok`. If every trial is rejected
by stability gates, no holdout replay is written because there is no candidate
worth confirming.

The binary decision rule is selected on validation as
`(threshold, decision_policy, max_signals_per_batch)`. Use
`--decision-policy causal_signal_budget --max-signals-grid 0,5,10,20,40,80`
to test uncapped thresholding plus small live-safe per-batch signal budgets.
This directly targets the observed failure mode where a model fires across too
much of one prediction batch. `threshold_only` is uncapped and must use
`--max-signals-grid 0`.

Use normal chronological windows. Do not combine this path with EMA-regime
banks, learned gates, signal banks, or decision banks in the active search.

The production-oriented target pipeline is documented in
`rpf_binary_prediction_pipeline_contract.md`. The implemented path is currently
the tabular branch:

```text
RPF features -> ElasticNet selector -> CatBoost -> threshold
```

For current binary runs, read this as:

```text
RPF features -> ElasticNet selector -> optional causal CNN embeddings -> CatBoost -> threshold + max_signals_per_batch
```

The CNN branch is disabled by default and enabled with:

```bash
--sequence-embedding-mode causal_cnn_v1
--sequence-length 16
--sequence-embedding-dim 8
--sequence-conv-channels 16
--sequence-kernel-size 3
--sequence-epochs 3
--sequence-max-train-rows 12000
```

Use a one-window smoke before wider runs because the CNN branch adds a
per-fold PyTorch fit before CatBoost.

The implemented CNN branch is:

```text
causal row sequence -> CNN encoder -> embedding columns -> CatBoost
```

All supervised operations use only labeled eligible rows. All causal continuous
rows may be used only as sequence/context state.

For new binary Optuna runs, keep the target-aware stability gates enabled.
They penalize the two failure modes seen in the 2026-06-18 UP holdout:
missing high-positive prediction batches and whole-batch firing in low/mixed
target batches. The relevant controls are:

```bash
--prediction-high-target-positive-rate-threshold 0.70
--min-prediction-high-target-window-recall 0.05
--min-prediction-high-target-window-signal-rate 0.01
--max-prediction-missed-high-target-window-rate 0.50
--prediction-low-target-positive-rate-threshold 0.35
--max-prediction-low-target-all-positive-window-rate 0.10
```

`geometry`, `baseline_probe`, and `core_model` use Optuna `GridSampler` for
their finite categorical choices, so repeated identical parameter tuples are
not expected in new runs.

Family ablation is available as a fixed run-level mask, not as train-time
feature selection:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<readiness_run_id> \
  --feature-ablation only_volatility_state \
  --n-steps 1 \
  --n-trials 6 \
  --task-type GPU
```

Use `all`, `only_<family>`, `minus_<family>`, or
`group_<family>+<family>`. Promotion decisions still require validation-RMSE
walk-forward evidence and prediction-collapse diagnostics.

Before further geometry or CatBoost tuning, run a controlled ablation sweep on
the same frozen windows:

```bash
ABLATIONS=(
  all
  only_volatility_state
  only_temporal_memory_transforms
  only_structural_room
  only_acceptance_persistence
  only_spike_breakout
  only_liquidity_volume_pressure
  only_regime_calendar_state
  only_interaction_confluence
  only_unsupervised_factor_layer
  only_sequence_embedding_layer
  minus_volatility_state
  minus_temporal_memory_transforms
  minus_regime_calendar_state
  group_volatility_state+temporal_memory_transforms
  group_acceptance_persistence+spike_breakout+liquidity_volume_pressure
  group_structural_room+spike_breakout+regime_calendar_state
)

READINESS_RUN="test_output/rpf_clean_walkforward/<readiness_run_id>"

for ABLATION in "${ABLATIONS[@]}"; do
  SAFE="${ABLATION//+/_}"
  /media/przem/linux_data/conda/envs/ml_env/bin/python \
    -m regression_feature_engineering.walkforward.optimize \
    --stage baseline_probe \
    --asset BTCUSDT \
    --root 8h/B \
    --target-col target_reg_direction_extreme_up_share_hvol_v2 \
    --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
    --base-run "$READINESS_RUN" \
    --feature-ablation "$ABLATION" \
    --iterations-choices 1200 \
    --depth-choices 3 \
    --learning-rate-choices 0.01 \
    --l2-leaf-reg-choices 200 \
    --early-stopping-rounds-choices 150 \
    --od-wait-choices 100 \
    --n-steps 15 \
    --n-trials 1 \
    --task-type GPU \
    2>&1 | tee "test_output/rpf_clean_walkforward_logs/ablation_${SAFE}.log"
done
```

Select candidate family scopes only when validation RMSE beats the
train-target-mean baseline and the run has no unacceptable per-window
prediction collapse.

First bounded sweep result using `--batch-limit 200`:

- rows: `96,000`;
- valid rows: `47,987`;
- peak RSS: about `1.38GB`;
- best mean-direction absolute Spearman was `0.2850` from
  `rpf_accept_12h_return_persist_l72_bnd` against
  `target_mean_up_minus_down`;
- best direction absolute Spearman was `0.2914` from
  `rpf_accept_12h_return_persist_l48_bnd` against
  `target_extreme_up_down_ratio`;
- because this is a bounded early-batch sample, treat it as tuning evidence,
  not promotion evidence.

Phase 5 temporal-memory dry-run command:

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

This command does not rewrite feature roots under `data/`. The Phase 5 family
uses a streaming state object, so lags, EWM state, rank-position windows, and
diffs continue across materialization chunks without requiring a full-root
wide frame in memory.

Phase 5 full materialization should be monitored and validated in narrow
diagnostic prefixes first:

```bash
python -m regression_feature_engineering.validate_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --signal-sample-rows 25000 \
  --diagnostic-feature-prefix rpf_mem_vol_15m_ \
  --output-dir test_output/regression_feature_engineering_btcusdt_8h_b_temporal_memory_vol
```

Do not use broad prefixes such as `rpf_mem_vol_` for default diagnostics. In
the current `BTCUSDT 8h/B` root, that prefix selects `220` columns and exceeds
the validator's default `--max-diagnostic-columns=80` guardrail. Use narrower
prefixes such as `rpf_mem_vol_15m_`, `rpf_mem_room_15m_`,
`rpf_mem_accept_15m_`, or `rpf_mem_accept_tf_`.

Phase 8 liquidity/volume-pressure bounded dry-run command:

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

First dry-run result:

- rows: `4,800`;
- model-facing features: `185`;
- duplicate keys: `0`;
- null feature cells: `0`;
- liquidity contribution: `27` `rpf_liq_15m_*` columns from `3` lookbacks x
  `9` formulas.

Phase 8 full materialization command for the first benchmark root:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,rejection_chop,spike_breakout,liquidity_volume_pressure,temporal_memory_transforms \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-chunk-size 8
```

Validate liquidity in narrow prefix slices after the full rebuild:

```bash
PREFIXES=(
  rpf_liq_15m_
  rpf_liq_1h_
  rpf_liq_4h_
  rpf_liq_8h_
  rpf_liq_12h_
  rpf_liq_1d_
)

for PREFIX in "${PREFIXES[@]}"; do
  SAFE="${PREFIX%_}"
  python -m regression_feature_engineering.validate_features \
    --assets BTCUSDT \
    --roots 8h/B \
    --timeframes 15m,1h,4h,8h,12h,1d \
    --signal-sample-rows 25000 \
    --diagnostic-feature-prefix "$PREFIX" \
    --output-dir "test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_${SAFE}"
done
```

First full-root result:

- rows: `2,810,755`;
- model-facing features: `1,733`;
- liquidity features: `162`;
- duplicate keys: `0`;
- null feature cells: `0`.

First liquidity validation result:

- every `rpf_liq_*` timeframe prefix had duplicate count `0`, null feature
  count `0`, infinite feature count `0`, and future-close violations `0`;
- strongest absolute Spearman by slice ranged from `0.0558` to `0.1595`;
- strongest directional high-low spread was `0.2382` from
  `rpf_liq_15m_volume_pressure_balance_l48_bnd` against
  `target_extreme_up_minus_down`.

Phase 9 regime/calendar-state bounded dry-run command:

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

First dry-run result:

- rows: `4,800`;
- model-facing features: `224`;
- duplicate keys: `0`;
- null feature cells: `0`;
- regime contribution: `39` features for `15m`.

Phase 9 full materialization command for the first benchmark root:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,temporal_memory_transforms \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-chunk-size 8
```

Validate regime/calendar features in narrow prefix slices after the full
rebuild:

```bash
PREFIXES=(
  rpf_regime_utc_
  rpf_regime_15m_
  rpf_regime_1h_
  rpf_regime_4h_
  rpf_regime_8h_
  rpf_regime_12h_
  rpf_regime_1d_
)

for PREFIX in "${PREFIXES[@]}"; do
  SAFE="${PREFIX%_}"
  python -m regression_feature_engineering.validate_features \
    --assets BTCUSDT \
    --roots 8h/B \
    --timeframes 15m,1h,4h,8h,12h,1d \
    --signal-sample-rows 25000 \
    --diagnostic-feature-prefix "$PREFIX" \
    --output-dir "test_output/regression_feature_engineering_btcusdt_8h_b_regime_${SAFE}"
done
```

Avoid the broad `rpf_regime_` prefix by default because it selects all regime
features and may hit the validator width guard.

First full-root Phase 9 result:

- rows: `2,810,755`;
- model-facing features: `1,942`;
- regime features: `209`;
- duplicate keys: `0`;
- null feature cells: `0`.

First regime/calendar validation result:

- every `rpf_regime_*` prefix had duplicate count `0`, null feature count `0`,
  infinite feature count `0`, and future-close violations `0`;
- strongest absolute Spearman by slice ranged from `0.1473` to `0.2916`;
- strongest feature was `rpf_regime_utc_hour_cos` against
  `target_extreme_total`;
- `batch_2511.parquet` was repaired after a parquet schema decode error by
  rebuilding only that batch from the same causal materializer path.

## Phase 10: Interaction And Confluence

Current status: engineering-validated on `BTCUSDT 8h/B`, not predictively
promoted.

Phase 10 combines only causal component features from already implemented
families. It does not read raw OHLCV, labels, or future diagnostics.

First full materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --batch-chunk-size 16
```

Validate confluence features in narrow prefix slices:

```bash
PREFIXES=(
  rpf_conf_15m_
  rpf_conf_1h_
  rpf_conf_4h_
  rpf_conf_8h_
  rpf_conf_12h_
  rpf_conf_1d_
)

for PREFIX in "${PREFIXES[@]}"; do
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

Acceptance gate:

- generated root contains `270` `rpf_conf_*` features;
- duplicate count `0`;
- null feature count `0`;
- confluence prefix validations have no nonfinite or future-close violations;
- signal reports show whether each interaction improves over component-only
  evidence before any walk-forward promotion decision.

First Phase 10 result:

- rows: `2,810,755`;
- model-facing features: `2,212`;
- interaction/confluence features: `270`;
- duplicate keys: `0`;
- null feature cells: `0`;
- all `5,856` feature batch files readable with consistent schema;
- strongest absolute Spearman by confluence slice ranged from `0.0838` to
  `0.1530`;
- strongest rank signals are mostly squeeze-break relationships against
  `target_extreme_total`;
- directional evidence appears more clearly in high-low quintile spreads
  against `target_extreme_up_minus_down`.

## Phase 11: Cross-Asset Context

Current status: engineering-validated on `BTCUSDT 8h/B`, not predictively
promoted.

Phase 11 starts with deterministic peer features. For `BTCUSDT`, auto peer
selection uses `ETHUSDT`. Pair source bars are built by exact canonical-bar
timestamp match, then aligned to prediction rows after the pair bar has closed.

First full materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
    --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence,cross_asset_context \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --xasset-context-assets auto \
  --batch-chunk-size 16
```

Validate cross-asset features in narrow prefix slices:

```bash
PREFIXES=(
  rpf_xasset_ethusdt_15m_
  rpf_xasset_ethusdt_1h_
  rpf_xasset_ethusdt_4h_
  rpf_xasset_ethusdt_8h_
  rpf_xasset_ethusdt_12h_
  rpf_xasset_ethusdt_1d_
)

for PREFIX in "${PREFIXES[@]}"; do
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

Acceptance gate:

- generated root contains `rpf_xasset_ethusdt_*` features;
- duplicate count `0`;
- null feature count `0`;
- cross-asset prefix validations have no nonfinite or future-close violations;
- no raw foreign price or volume columns appear in model-facing features;
- signal reports show whether deterministic peer context adds value before any
  walk-forward promotion decision.

First Phase 11 result:

- rows: `2,810,755`;
- model-facing features: `2,356` before Phase 12/13;
- cross-asset features: `144`;
- duplicate keys: `0`;
- null feature cells: `0`;
- all `5,856` feature batch files readable with consistent schema;
- strongest absolute Spearman by cross-asset slice ranged from `0.0384` to
  `0.0581`;
- strongest rank signals are modest and mostly target total path-width or
  mean-total behavior;
- directional evidence appears more clearly in high-low quintile spreads
  against `target_extreme_up_minus_down`.

## Phase 12/13: Factor And Sequence Proxies

Current status: materialized and engineering-validated on `BTCUSDT 8h/B`.
All `rpf_factor_*` timeframe-prefix validations and the `rpf_seq_` validation
passed. Predictive promotion still requires walk-forward ablation.

The static RPF artifact implements deterministic causal proxies only:

- `rpf_factor_*`: path-width, direction, persistence, shock, rejection,
  context, anomaly, and clean-direction factors derived from causal component
  features.
- `rpf_seq_*`: ordered multi-timeframe stack summaries derived from
  `rpf_factor_*` columns.

It does not implement globally fitted PCA, clustering, anomaly models, CNNs, or
learned encoders. Those remain train-window-only walk-forward experiments.

First full materialization command:

```bash
python -m regression_feature_engineering.materialize_features \
  --assets BTCUSDT \
  --roots 8h/B \
  --families foundation_alignment,volatility_state,structural_room,acceptance_persistence,temporal_memory_transforms,rejection_chop,spike_breakout,liquidity_volume_pressure,regime_calendar_state,interaction_confluence,cross_asset_context,unsupervised_factor_layer,sequence_embedding_layer \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --xasset-context-assets auto \
  --batch-chunk-size 16
```

Validate the new prefixes first:

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

Acceptance gate:

- generated root contains `rpf_factor_*` and `rpf_seq_*` features;
- duplicate count `0`;
- null feature count `0`;
- prefix validations have no nonfinite or future-close violations;
- catalog entries make clear these are deterministic proxies, not globally
  fitted PCA/CNN/cluster outputs.

Current Phase 12/13 materialization result:

- rows: `2,810,755`;
- model-facing features: `2,530`;
- factor features: `144`;
- sequence-shape features: `30`;
- duplicate keys: `0`;
- null feature cells: `0`.

The initial validation loop failed before report writing because the validator
used the full family list as one path component. The validator now writes
bounded hashed family slugs such as `families12_8449f07ebbb5_btcusdt_8h_b`.

Successful Phase 13 validation slice:

- prefix: `rpf_seq_`;
- rows: `2,810,755`;
- valid rows: `1,405,427`;
- feature columns: `2,530`;
- duplicate keys: `0`;
- null feature cells: `0`;
- future-close violations: `0`;
- strongest absolute Spearman: `0.1215`.

Successful Phase 12 factor validation slices:

| Prefix | Strongest Absolute Spearman | Top Feature/Target |
|---|---:|---|
| `rpf_factor_15m_` | `0.1362` | `rpf_factor_15m_path_width_l16_bnd` vs `target_extreme_total` |
| `rpf_factor_1h_` | `0.1689` | `rpf_factor_1h_shock_l16_bnd` vs `target_extreme_total` |
| `rpf_factor_4h_` | `0.1826` | `rpf_factor_4h_shock_l4_bnd` vs `target_extreme_total` |
| `rpf_factor_8h_` | `0.0552` | `rpf_factor_8h_shock_l48_bnd` vs `target_extreme_total` |
| `rpf_factor_12h_` | `0.1021` | `rpf_factor_12h_shock_l4_bnd` vs `target_extreme_total` |
| `rpf_factor_1d_` | `0.0505` | `rpf_factor_1d_rejection_l48_bnd` vs `target_mean_total` |

All Phase 12/13 validation slices had:

- rows: `2,810,755`;
- valid rows: `1,405,427`;
- feature columns: `2,530`;
- duplicate keys: `0`;
- null feature cells: `0`;
- infinite feature cells: `0`;
- future-close violations: `0`.

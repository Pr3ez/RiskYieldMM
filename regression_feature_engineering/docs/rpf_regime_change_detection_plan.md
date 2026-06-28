# RPF Regime And Change Detection Plan

## Purpose

Define the next RPF diagnostic layer for making the ranked-signal router aware
of market regime and regime-change risk.

The goal is not to replace the ranker. The goal is to explain and later reduce
validation-to-prediction transfer failures:

```text
RPF ranker score is useful in some contexts
same candidate fails in other contexts
router reliability becomes stale across regimes
```

## Current Decision

Add regime/change diagnostics before changing live router decisions.

Active command:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic
```

This command consumes completed `rank_signal_router` runs and writes:

```text
test_output/rpf_ranked_signal_regime_diagnostic/{run_id}/
```

Required artifacts:

```text
events.jsonl
stage_status.json
regime_diagnostic_config.json
regime_context.parquet
change_point_events.parquet
regime_signal_quality.parquet
hmm_state_metrics.parquet
regime_target_match.parquet
regime_change_target_match.parquet
change_risk_target_match.parquet
regime_suppression_candidates.parquet
regime_transfer_report.md
```

## Research Basis

- Markov-switching/HMM models are useful for latent state probabilities,
  transition probabilities, and expected regime durations.
- CUSUM/Page-Hinkley style detectors are useful for online mean/distribution
  shift alarms.
- Offline change-point tools are useful for analysis, but live routing must use
  only past information.

Reference docs used for this implementation direction:

```text
statsmodels Markov switching:
  https://www.statsmodels.org/stable/examples/notebooks/generated/markov_regression.html

hmmlearn GaussianHMM:
  https://hmmlearn.readthedocs.io/en/latest/tutorial.html
  https://hmmlearn.readthedocs.io/en/latest/api.html

ruptures offline change-point diagnostics:
  https://centre-borelli.github.io/ruptures-docs/

CUSUM reference:
  https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm

River online drift detectors:
  https://riverml.xyz/latest/api/drift/ADWIN/
  https://riverml.xyz/latest/api/drift/PageHinkley/
```

## Implementation Contract

The diagnostic is prediction-safe by construction.

Safe context may include:

```text
candidate name
side
validation metrics
rank score mean/std
threshold and signal budget
selected feature count
sequence feature count
batch-state gate fields
past 20/60 positive-rate diagnostics
prior matured reliability fields
```

Safe context must not include current prediction outcomes:

```text
true positives
false positives
precision
false-discovery rate
current prediction positive count
current prediction label/base-rate outcomes
```

Those outcomes are written only to `regime_signal_quality.parquet`.

## Model Behavior

For every side/candidate series:

1. Sort windows chronologically.
2. Build numeric safe-context features.
3. Wait for enough prior history.
4. Fit scaler/PCA/regime model using prior windows only.
5. Assign a regime state to the current window.
6. Estimate posterior confidence and transition risk.
7. Run CUSUM/Page-Hinkley style change alarms on safe context features.
8. Join matured outcomes only for analysis tables.

Router run order:

```text
The command sorts input runs by `window_end_offset_steps` automatically.
Larger offsets are older windows, so they are used before offset 0.
CLI argument order must not define regime history.
```

The command uses `hmmlearn.GaussianHMM` if available. In the current local
environment `hmmlearn` is not installed, so the command falls back to a
chronological Gaussian-mixture Markov proxy with an estimated transition matrix.

That fallback is acceptable for diagnostics because it still answers the first
question:

```text
do prediction-safe context states separate good signal windows from bad ones?
```

## What This Is Not

This is not yet:

```text
a production router mode
a trading strategy
a replacement for CatBoostRanker
a new target
a future-label regime gate
```

Do not promote a regime state directly. Promotion requires a later
`regime_aware_router_v1` mode that proves improvement in walk-forward replay.

## First Real Command

Run after a completed dual-target router replay:

```bash
cd /media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM

export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"

"$PY" -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic \
  --router-run test_output/rpf_ranked_signal_router/20260628_102938_rank_signal_router_btcusdt_8h_b \
  --router-run test_output/rpf_ranked_signal_router/20260628_110557_rank_signal_router_btcusdt_8h_b \
  --router-run test_output/rpf_ranked_signal_router/20260628_120309_rank_signal_router_btcusdt_8h_b \
  --router-run test_output/rpf_ranked_signal_router/20260628_123958_rank_signal_router_btcusdt_8h_b \
  --side both \
  --candidate-names up_rocket_64_v1,down_rocket_16_diag_v1 \
  --state-count 3 \
  --pca-components 5 \
  --regime-min-history-windows 80 \
  --regime-lookback-windows 240 \
  --model-mode gmm_markov \
  --change-lookback-windows 60 \
  --cusum-z 3.0 \
  --page-hinkley-delta 0.01 \
  --page-hinkley-threshold 3.0
```

## Interpretation

Useful evidence looks like:

```text
state A: precision lift > local base, lower FDR
state B: precision lift near/below 1, high FDR
high entropy or frequent change alarms before false-positive clusters
UP and DOWN prefer different states or different change-risk profiles
regime_target_match marks favorable contexts with enough signals
regime_suppression_candidates lists repeatable high-FDR or below-base contexts
```

Weak evidence looks like:

```text
states have similar precision/lift/FDR
change alarms do not align with degradation
state assignment is unstable or dominated by one noisy variable
```

## Next Step After Diagnostic

Only if states/change alarms explain quality should we implement:

```text
--selection-mode regime_aware_router_v1
```

That router mode should use:

```text
regime_state
regime_posterior_max
regime_entropy
regime_transition_probability
change_alarm
time_since_change
prior matured candidate reliability
```

to suppress, reduce budget, or choose UP/DOWN specialists.

Latest diagnostic extension:

```text
regime_target_match.parquet:
  labels each state as favorable / neutral / avoid per side/candidate

change_risk_target_match.parquet:
  labels CUSUM/Page-Hinkley/no-change contexts per side/candidate

regime_change_target_match.parquet:
  labels state + change-flag combinations

regime_suppression_candidates.parquet:
  ranks avoid contexts to test as false-positive suppression rules
```

## Suppression Simulator

Active command:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator
```

Purpose:

```text
offline replay of regime/change-risk suppressions before adding a live router
mode
```

First rule set:

```text
UP:
  suppress state 2
  suppress has_page_hinkley=true

DOWN:
  suppress state 0
  suppress has_cusum=true
```

Command:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator \
  --regime-run test_output/rpf_ranked_signal_regime_diagnostic/20260628_142856_rank_signal_regime_diagnostic \
  --suppress-up-states 2 \
  --suppress-up-change-flags has_page_hinkley \
  --suppress-down-states 0 \
  --suppress-down-change-flags has_cusum
```

First result:

```text
run:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_143451_rank_signal_regime_suppression_simulator/

DOWN:
  signals before: 3015
  signals after:  1977
  precision:      0.393 -> 0.408
  lift:           1.024 -> 1.064
  FDR:            0.607 -> 0.592
  FP reduction:   0.361

UP:
  signals before: 2678
  signals after:  1777
  precision:      0.416 -> 0.427
  lift:           1.072 -> 1.100
  FDR:            0.584 -> 0.573
  FP reduction:   0.349
```

Interpretation:

```text
The rule improves precision/lift modestly and removes about one third of false
positives, but it also removes about one third of signals. This is a valid risk
filter candidate, not a complete trading strategy.
```

## Market-Regime Context Mode

The regime diagnostic now supports explicit feature separation:

```bash
--regime-context-mode router_context|market_context|combined
--change-feature-set auto|router_context|market_context|combined
```

`router_context` is the historical diagnostic mode. It uses only model/router
context, such as score distribution, validation metrics, candidate reliability,
and positive-rate diagnostics.

`market_context` uses prior-batch RPF market-state aggregates only. It does not
use the ElasticNet-selected prediction feature mask.

`combined` appends both sets and is the preferred next backtest because it can
explain both:

```text
model behavior changed
market state changed
```

Default market families:

```text
volatility_state
temporal_memory_transforms
regime_calendar_state
rejection_chop
liquidity_volume_pressure
structural_room
```

The market context is computed from prior available batches by default:

```text
prediction batch t
regime market context = aggregates over batches < t
```

Do not enable `--market-regime-include-current-batch` for promotion-style
backtests. It is diagnostic-only because full current-batch aggregates are not
available at the start of the batch in live trading.

Recommended combined diagnostic command:

```bash
"$PY" -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic \
  --router-run "$OFFSET360_RUN" \
  --router-run "$OFFSET240_RUN" \
  --router-run "$MIDDLE_RUN" \
  --router-run "$LATEST_RUN" \
  --side both \
  --candidate-names up_rocket_64_v1,down_rocket_16_diag_v1 \
  --regime-context-mode combined \
  --change-feature-set combined \
  --base-run "$READINESS_RUN" \
  --market-regime-lookback-batches 20 \
  --market-regime-max-features-per-family 64 \
  --state-count 3 \
  --pca-components 5 \
  --regime-min-history-windows 80 \
  --regime-lookback-windows 240 \
  --change-lookback-windows 60 \
  --model-mode auto
```

## Validation

Code checks:

```bash
python -m pytest tests/test_rpf_rank_signal_regime_diagnostic.py -q
python -m pytest tests/test_rpf_rank_signal_router.py tests/test_rpf_rank_signal_regime_diagnostic.py -q
python -m py_compile $(find regression_feature_engineering -name '*.py' -print)
git diff --check
```

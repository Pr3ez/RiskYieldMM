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
market_regime_context.parquet
regime_input_features.parquet
hmm_filter_diagnostics.parquet
hmm_model_selection.parquet
hmm_transition_matrix.parquet
cusum_calibration.parquet
change_point_events.parquet
hmm_transition_events.parquet
regime_signal_quality.parquet
hmm_state_metrics.parquet
state_profile_labels.parquet
regime_target_match.parquet
regime_change_target_match.parquet
change_risk_target_match.parquet
regime_suppression_candidates.parquet
regime_gate_context_metrics.parquet
regime_gate_decisions.parquet
regime_gate_simulation.parquet
regime_transfer_report.md
```

Clean artifact contract:

```text
HMM/CUSUM inputs must come from approved prediction-safe market-context
features only.
State-level outputs must use regime_state_key, not raw regime_state alone.
Actionable change flags must be explicit detector flags; has_cusum is stale.
Gate simulation must be prior-only and may only allow or suppress.
```

## Research Basis

- Markov-switching/HMM models are useful for latent state probabilities,
  transition probabilities, and expected regime durations.
- CUSUM-style detectors are the first active clean change-point path because
  they are simple, causal, and easy to audit against prior market context.
- Page-Hinkley remains implemented as a comparative diagnostic, but it is not
  part of the current clean notebook path.
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
7. Run the configured causal change alarms on safe context features. The clean
   notebook uses CUSUM only.
8. Join matured outcomes only for analysis tables.

Router run order:

```text
The command sorts input runs by `window_end_offset_steps` automatically.
Larger offsets are older windows, so they are used before offset 0.
CLI argument order must not define regime history.
```

The command uses `hmmlearn.GaussianHMM` when `--model-mode hmm` is selected.
The configured `$PY` environment currently has `hmmlearn` available, and the
clean notebook checks that dependency before printing the regime command. If
`hmmlearn` is unavailable and `--model-mode auto` is used, the command can fall
back to a chronological Gaussian-mixture Markov proxy with an estimated
transition matrix.

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
  --prediction-source effective_selected \
  --regime-context-mode market_context \
  --asset BTCUSDT \
  --root 8h/B \
  --base-run "$READINESS_RUN" \
  --market-regime-max-features-per-family 16 \
  --market-regime-lookback-batches 20 \
  --state-count 3 \
  --pca-components 5 \
  --regime-min-history-windows 80 \
  --regime-lookback-windows 240 \
  --regime-refit-interval-windows 20 \
  --model-mode hmm \
  --change-lookback-windows 60 \
  --change-feature-set market_context \
  --change-detectors market_context_recursive_cusum_v1 \
  --cusum-z 3.0
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

Historical first rule set, now stale:

```text
UP:
  suppress state 2
  suppress has_page_hinkley=true

DOWN:
  suppress state 0
  suppress legacy has_cusum=true
```

Do not rerun that rule set. `has_cusum` was an old generic alias that mixed
detector intent. Clean runs must use explicit detector flags only:

```text
has_market_context_zshift_v1              # diagnostic only
has_market_context_recursive_cusum_v1     # actionable candidate
has_hmm_transition_cusum_v1               # actionable candidate
has_hmm_state_change_marker               # interpretation marker
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

## 2026-06-28 Live-Replay Correction

The first combined diagnostic proved that regime/change context can improve
precision slightly, but the replay was still post-hoc. The corrected contract
is:

```text
live-safe context:
  no current prediction outcomes
  no current full prediction-batch score summaries
  prior-market context only
  validation and prior reliability context allowed

suppression evaluation:
  learn avoid contexts from prior matured windows only
  apply to current prediction window
  mature current window after the decision
```

Implemented changes:

```text
rank_signal_regime_diagnostic:
  added live_router_context/live_combined modes
  live modes exclude score_mean, score_std, and batch_state_gate prediction summaries
  fixed live_combined so it actually builds market_context
  added --regime-refit-interval-windows for practical live-style backtests

rank_signal_regime_suppression_simulator:
  added --simulation-mode prequential
  writes suppression_rule_audit.parquet
```

Corrected replay result:

```text
diagnostic:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_175452_rank_signal_regime_diagnostic/

suppression:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_175635_rank_signal_regime_suppression_simulator/

DOWN:
  precision 0.393 -> 0.441
  lift      1.024 -> 1.151
  FDR       0.607 -> 0.559
  signals   3015 -> 641

UP:
  precision 0.416 -> 0.438
  lift      1.072 -> 1.130
  FDR       0.584 -> 0.562
  signals   2678 -> 890
```

Decision:

```text
The regime layer improves precision under live-style replay, but it suppresses
too many signals. It should remain a risk filter candidate. The next step is
side-specific allow-context testing, especially for UP, rather than promoting
global suppression as-is.
```

## 2026-06-28 Prediction-Source Correction

The replay above used `candidate_prediction_window_metrics.parquet`, which is
the shadow candidate stream. It answers:

```text
what would each candidate have done if evaluated independently?
```

It does not answer:

```text
what did the live router-selected stream actually trade?
```

Implemented correction:

```text
rank_signal_regime_diagnostic --prediction-source candidate_shadow|router_selected|row_rule_active|effective_selected
```

`router_selected` loads `router_window_metrics.parquet`.
`row_rule_active` loads `row_rule_active_window_metrics.parquet`.
`effective_selected` is the default. New router runs read
`effective_window_metrics.parquet`; historical runs resolve to row-rule active
output when active row-rule output exists, otherwise base router output.

Implementation integrity updates:

```text
- change-risk suppression candidates are true-alarm-only by default;
- change_flag=False is not allowed to become a prequential suppression rule;
- regime state IDs are canonicalized after each GMM/HMM fit to reduce label
  permutation across walk-forward refits;
- regime quality artifacts preserve both requested and resolved prediction
  source columns.
```

Base router-selected replay:

```text
diagnostic:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_192232_rank_signal_regime_diagnostic/

suppression:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_192425_rank_signal_regime_suppression_simulator/

DOWN:
  precision 0.207 -> 0.207
  lift      0.540 -> 0.540
  FDR       0.793 -> 0.793
  signals   29 -> 29

UP:
  precision 0.333 -> 0.333
  lift      0.860 -> 0.860
  FDR       0.667 -> 0.667
  signals   21 -> 21
```

Decision update:

```text
Regime/change suppression is not the current bottleneck in the base router
stream. The base router emits too few signals and those selected signals are
below base rate.
```

Effective selected stream correction:

```text
The latest active runs used row_rule_gate_output_mode=active_candidate.
For those runs, the effective selected stream is row_rule_active.

UP row_rule_active:
  signals   206
  precision 0.422
  base      0.388
  lift      1.089

DOWN row_rule_active:
  signals   204
  precision 0.466
  base      0.383
  lift      1.214
```

Current decision:

```text
The effective stream is not as broken as the base router stream, but it is
still weak. Continue only after every diagnostic/report explicitly declares
whether it is using candidate_shadow, router_selected, row_rule_active, or
effective_selected.
```

## Clean Notebook HMM/CUSUM Update

2026-07-01 implementation update:

```text
notebooks/rpf_walkforward_control.ipynb
rank_signal_regime_diagnostic --change-detectors market_context_zshift_v1,market_context_recursive_cusum_v1,hmm_transition_cusum_v1
```

The clean notebook now treats the regime stage as a fresh-only diagnostic:

```text
effective selected router output for strategy-performance inspection
candidate shadow router output for regime/candidate research
-> market_context regime features
-> hmmlearn GaussianHMM
-> market z-shift alarms
-> recursive market CUSUM alarms
-> HMM-transition recursive CUSUM alarms
```

Required command contract:

```text
--prediction-source candidate_shadow
--regime-context-mode market_context
--model-mode hmm
--hmm-selection-mode bic_v1
--hmm-state-count-choices 2,3,4
--hmm-filter-mode causal_forward_v1
--change-feature-set market_context
--change-detectors market_context_zshift_v1,market_context_recursive_cusum_v1,hmm_transition_cusum_v1
--cusum-standardization rolling_robust_z_v1
```

This intentionally avoids mixing:

```text
current prediction outcomes as regime input
Page-Hinkley alarms in the clean notebook path
GMM fallback when hmmlearn is available
historical suppression simulator artifacts
```

The diagnostic CLI still supports Page-Hinkley, router-context features, and
`auto` model mode for comparative research. The notebook does not use them for
the clean restart.

2026-07-01 correction lock:

```text
--hmm-selection-mode bic_v1
--hmm-state-count-choices 2,3,4
--hmm-filter-mode causal_forward_v1
--cusum-standardization rolling_robust_z_v1
--cusum-target-event-rate-min 0.05
--cusum-target-event-rate-max 0.25
```

HMM posterior filtering now uses the full prior train-window sequence plus the
current market vector and takes the final filtered posterior. It no longer uses
the old `last_train_vector + current_vector` shortcut. Scaler, PCA, HMM state
selection, and CUSUM calibration remain prior-only.

Recursive market CUSUM uses rolling prior-only robust z-scores by default.
`hmm_transition_cusum_v1` is a separate recursive CUSUM over HMM posterior
uncertainty, entropy, transition rarity, direct state-change markers, and
current observation surprise. Direct HMM state changes are written as
`hmm_state_change_marker`, not as `hmm_transition_cusum_v1`.

Implementation correction:

```text
market_context HMM states are assigned once per unique chronological prediction
window, then joined back to side/candidate rows for outcome analysis.
market_context CUSUM alarms are detected once per unique chronological
prediction window, then joined back to side/candidate rows.
HMM-transition CUSUM is detected from HMM posterior/entropy/transition
features, and direct HMM state-change markers are reported separately from
recursive HMM-transition CUSUM alarms.
```

This avoids the previous mixed logic where the same market observation could be
duplicated and fit separately by candidate branch. Candidate outcomes are used
only after state/alarm assignment to measure which regimes are favorable or
dangerous for UP/DOWN candidates.

Notebook validation update:

```text
notebooks/rpf_walkforward_control.ipynb
```

now includes explicit optimization checks for:

```text
state count and state balance
posterior confidence and entropy
market-context feature separation by HMM state
CUSUM event-window rate
CUSUM-triggering market features
HMM-transition CUSUM alignment versus direct HMM state-change markers
candidate quality under CUSUM true/false
favorable HMM contexts and avoid/suppression contexts
```

These checks must pass before using HMM/CUSUM as a router input. They are
diagnostic checks, not strategy-performance metrics.

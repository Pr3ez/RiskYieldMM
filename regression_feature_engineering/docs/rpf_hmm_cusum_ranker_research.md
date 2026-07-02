# RPF HMM/CUSUM Ranker Research Notes

## Purpose

Define how HMM-style regime detection and CUSUM-style change detection should
be used to improve the RPF CatBoostRanker workflow.

The objective is not to make HMM/CUSUM predict UP or DOWN directly. The
objective is to make the ranked-signal system context-aware:

```text
RPF features -> ElasticNet/ROCKET/CatBoostRanker candidate score
market context -> HMM regime state/posterior
market context and HMM stream -> change-risk alarms
candidate score + regime/change context -> allow, suppress, budget, or route
```

## Research Basis

- `hmmlearn` defines HMMs as latent-state sequence models with transition
  probabilities and emission distributions. It also warns that EM can get stuck
  in local optima, so model selection should use multiple starts or scores.
  Source: https://hmmlearn.readthedocs.io/en/latest/tutorial.html
- `hmmlearn.GaussianHMM` exposes state posterior probabilities, log likelihood,
  convergence monitor state, and transition matrix behavior.
  Source: https://hmmlearn.readthedocs.io/en/latest/api.html
- `statsmodels` Markov-switching examples interpret regimes through fitted
  state probabilities, transition probabilities, expected durations, and
  information criteria. Source:
  https://www.statsmodels.org/stable/examples/notebooks/generated/markov_regression.html
- NIST describes CUSUM as a cumulative-sum method for detecting small mean
  shifts, controlled by reference value `k` and threshold `h`. Source:
  https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc323.htm
- River's Page-Hinkley detector is a streaming change detector based on a
  CUSUM-style mean-shift test. Source:
  https://riverml.xyz/latest/api/drift/PageHinkley/
- River's ADWIN uses adaptive windows to detect distribution change and is a
  later option for candidate-performance drift, not the first HMM/CUSUM layer.
  Source: https://riverml.xyz/latest/api/drift/ADWIN/
- CatBoost ranking requires grouped data; CatBoost `Pool` requires objects with
  the same `group_id` to be contiguous. Source:
  https://catboost.ai/docs/en/concepts/python-reference_pool
- CatBoost ranking losses such as `YetiRank` optimize groupwise ranking
  objectives. Source:
  https://catboost.ai/docs/en/concepts/loss-functions-ranking
- Time-series validation must preserve order and may require a gap between
  train and test. Source:
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Selective prediction research frames this as a risk/coverage tradeoff:
  abstain or suppress when expected error risk is high. Source:
  https://arxiv.org/abs/1705.08500

## Current Repo Reality

The current clean notebook path uses:

```text
prediction_source = candidate_shadow
regime_context_mode = market_context
model_mode = hmm
change_feature_set = market_context
change_detectors = cusum
state_count = 3
pca_components = 5
regime_min_history_windows = 80
regime_lookback_windows = 240
regime_refit_interval_windows = 20
market_regime_lookback_batches = 20
```

Current HMM behavior:

- regime context is built once per chronological market window;
- current prediction labels are not used in the HMM input;
- scaler, PCA, and HMM are fit on prior windows only;
- current window receives `regime_state`, posterior probabilities, entropy,
  and transition diagnostics;
- state numbers are canonicalized mechanically but must be named post-hoc from
  feature profiles and outcome quality.

Current CUSUM behavior:

- alarms are computed once per market window, then joined to candidates;
- alarms use market-context features ending in `_last_z` or `_lookback_mean`;
- implementation is currently a rolling z-score shift detector:

```text
z = (current_value - prior_rolling_mean) / prior_rolling_std
alarm = abs(z) >= cusum_z
```

This is useful as a market-context shock diagnostic, but it is not a classical
recursive CUSUM. Rename or extend it before treating it as a final change-point
detector.

## Market States To Specify

Do not pre-label HMM states as bullish or bearish. HMM state IDs are latent and
can swap meaning across refits. Specify the observation space, then name states
from train-only/post-hoc profiles.

The RPF market-context state vector should cover these blocks:

```text
trend_direction:
  return over recent RPF/prediction-safe windows
  distance of price/path state from short and long memory anchors
  directional persistence / acceptance persistence

volatility_level:
  realized path width
  RPF volatility state mean/q10/q50/q90/std
  volatility-of-vol / temporal-memory std

chop_rejection:
  rejection_chop family summaries
  structural room compression/expansion
  path acceptance versus rejection pressure

liquidity_volume_pressure:
  liquidity and volume-pressure family summaries
  pressure imbalance and instability

calendar_session:
  regime calendar state summaries only if they are prediction-time safe

ranker_context:
  optional, separate layer only
  candidate threshold, score dispersion, selected feature count
  prior matured candidate reliability, never current outcomes
```

Recommended first HMM observation set:

```text
market_context only
families:
  volatility_state
  temporal_memory_transforms
  regime_calendar_state
  rejection_chop
  liquidity_volume_pressure
  structural_room
max_features_per_family: 16
lookback_batches: 20
include_current_batch: false
```

This detects market conditions available before the prediction batch. It should
not use ElasticNet-selected ranker features as the regime input, because those
features are target/candidate-specific. Regime detection needs a stable market
state representation shared by UP and DOWN.

## Recommended State Taxonomy

State names should be assigned after each fitted model from safe feature
profiles:

```text
quiet_compressed:
  lower volatility mean/q50/q90
  lower temporal-memory std
  lower liquidity-pressure std
  often fewer breakouts, lower ranker score dispersion

transition_chop:
  high rejection/chop or structural-room instability
  elevated entropy or frequent state changes
  ranker signals often need suppression or budget reduction

expanded_pressure:
  high volatility and liquidity/volume-pressure features
  stronger path-width and breakout conditions
  may favor UP or DOWN depending on directional/relevance evidence

directional_acceptance_up/down:
  only name this if trend-direction and acceptance features separate the state
  and post-hoc target quality confirms side-specific usefulness
```

With only `state_count=3`, expect broad states:

```text
quiet/compressed
transitional/choppy
expanded/pressure
```

If trend direction is not separated, add explicit safe trend-direction features
to market context before increasing state count. Increasing states without
better directional observations will produce unstable labels.

## Correct HMM Implementation

For each prediction window:

```text
1. Build one market row from prior batches only.
2. Use previous market rows only as HMM training history.
3. Fit train-only scaler.
4. Fit train-only PCA if needed.
5. Fit GaussianHMM with multiple random starts.
6. Select model by train log likelihood penalized by state count, or AIC/BIC
   if implemented.
7. Infer current filtered/posterior state probabilities.
8. Save state, posterior vector, entropy, transition probability, and expected
   duration.
9. Join the same state to all UP/DOWN candidates for that prediction window.
10. Use current prediction outcomes only later for diagnostics or future
    matured reliability.
```

Implementation requirements:

```text
fit only on prior windows
do not use smoothed probabilities that require future observations
run multiple initializations
track convergence and log likelihood
track transition matrix and expected duration
canonicalize states by feature profile, not arbitrary raw HMM index
write state profile tables for every refit
```

## Correct CUSUM Implementation

Keep two detector layers.

### Layer 1: Market Feature CUSUM

Detect shocks in prediction-safe market features:

```text
for each feature:
  reference_mean/std fit from prior lookback only
  x = standardized current value
  s_pos = max(0, s_pos + x - k)
  s_neg = min(0, s_neg + x + k)
  alarm_up = s_pos > h
  alarm_down = abs(s_neg) > h
  reset side after alarm
```

Recommended starting ranges:

```text
lookback_windows: 80,120,240
k: 0.25,0.50,0.75
h: 4,5,6
min_history_windows: 60
```

This replaces the current rolling z-score alarm or runs beside it under a
clear name:

```text
market_context_zshift_v1
market_context_recursive_cusum_v1
```

### Layer 2: HMM Transition-Risk CUSUM

Detect instability in the HMM stream:

```text
inputs:
  posterior_max
  entropy
  transition_probability
  1 - posterior_of_previous_state
  negative log likelihood of current observation under prior HMM
  per-state posterior probabilities

alarms:
  posterior_confidence_drop
  entropy_spike
  unlikely_transition
  log_likelihood_break
  state_change_cluster
```

This is the layer that answers:

```text
is CUSUM detecting change points of regimes HMM detects?
```

The current implementation does not yet do this. It detects feature shocks
that may coincide with state changes.

## How HMM/CUSUM Should Boost CatBoostRanker

Do not retrain the ranker differently just because HMM says state 1. First use
HMM/CUSUM as a selective routing layer:

```text
candidate CatBoostRanker scores rows
HMM/CUSUM decides whether that candidate is trusted in this context
trusted candidate applies threshold and signal budget
untrusted candidate emits no signal or lower budget
```

Only after this works should HMM features be appended to CatBoostRanker input.
Reason: if the HMM layer is wrong, feeding it directly into CatBoost hides the
failure inside the model. A separate router/gate keeps failure visible.

Promotion metrics:

```text
precision
precision_lift over local base rate
false discovery rate
signals per week / active-window rate
block-level repeatability
side balance: UP and DOWN tracked separately
```

Do not optimize HMM/CUSUM by raw prediction accuracy. Optimize by whether it
improves ranker trust decisions:

```text
same candidate, same ranker scores
with and without regime/change gate
prequential replay only
current window outcome never influences current gate
```

## Immediate Implementation Direction

1. Keep current HMM `market_context` diagnostic, but add state profile naming:
   `quiet_compressed`, `transition_chop`, `expanded_pressure`, or `unlabeled`.
2. Rename current z-score CUSUM output or mark it as
   `market_context_zshift_v1`.
3. Add true recursive CUSUM as `market_context_recursive_cusum_v1`.
4. Add HMM-stream detectors as `hmm_transition_cusum_v1`.
5. Add a notebook/table answering:

```text
HMM state changes detected by recursive CUSUM?
feature z-shifts preceding state changes?
state entropy/posterior degradation preceding false positives?
which states favor UP?
which states favor DOWN?
which states should suppress each candidate?
```

6. Only then implement `regime_aware_router_v1`.

## Acceptance Criteria

The HMM/CUSUM layer is useful only if, in prequential replay:

```text
UP and DOWN both remain tracked
signals do not collapse below practical trading frequency
precision lift improves versus ungated candidate_shadow
FDR falls materially
state/change rules repeat across chronological blocks
no current prediction outcome is used for current routing
```

If it only improves one old block and fails the next block, treat it as a
diagnostic, not a routing rule.

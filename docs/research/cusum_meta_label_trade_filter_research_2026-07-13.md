# CUSUM meta-label trade filter for RiskYieldMM Analyst

Date: 2026-07-13
Tracking: Linear `RIS-262`
Depends on: [Indicator-driven trade policy](./indicator_driven_trade_policy_research_2026-07-12.md) (`RIS-261`)
Status: research and implementation contract; profitability and live-readiness not established

## Implementation audit status (2026-07-13)

The first all-selection logistic artifact (`v1`) is **rejected as deployment
evidence**. It remains useful only as a pipeline smoke artifact. The audit found
that its label/execution contract did not yet guarantee all of the following:

- label maturity on the actual observation clock rather than only a nominal bar
  close;
- immutable bracket ownership after fill when a later strategy signal reversed;
- timeout on accepted finalized selected-timeframe candles rather than raw
  one-minute row density; and
- one consistent treatment of entry execution costs between the barrier return
  and the net-label deduction.

It must not be promoted, used to enable a gate, or presented as live-shadow
evidence. The corrected `v2` implementation now enforces immutable bracket
ownership, accepted-target-bar timeout, single-count execution costs, explicit
feature availability, exact persisted schemas, centralized deployment
eligibility, and cancellation across an unknown minute path.

The replacement `v2` research candidate was trained after those fixes over the
fixed 180-day window ending `2026-07-10T21:00:00Z`. It contains 65,096 mature
events (10,070 positive) and 64,029 expanding-walk-forward predictions. Against
the causal train-prevalence forecast, Brier improved from `0.130772` to
`0.129518`, log loss from `0.430811` to `0.426061`, and PR-AUC from `0.153624`
to `0.198832`. These pooled improvements are research evidence, not a profit or
deployment result: `candidate_only=true`, `auto_promoted=false`,
`deployment_eligible=false`, and the exact deployment-selection list is empty.

Historical canonical files still lack actual first-seen/revision timestamps.
The v2 historical study therefore declares a nominal close plus five-second
observation scenario and adds a 24-hour label-maturity embargo inside every
fold. Only the append-only forward journal can provide actual `first_seen_at`
for deployment evidence. The model remains a candidate until an untouched
holdout, calibration, exact-scope checks, and delayed forward-paper evidence
pass separately declared gates.

## Decision

The proposed machine-learning layer is feasible and has a recognized name:
**meta-labeling**. RiskYieldMM should keep its causal trend/CUSUM policy as the
primary model that proposes a trade side. A secondary classifier should estimate
whether that particular candidate trade is likely to reach its frozen
take-profit before its protective stop or other terminal exit.

```text
finalized bars and causal indicators
                |
                v
     primary SignalPolicy / TradeIntent
                |
                v
 deterministic draft stop, target and horizon
                |
                v
  meta-model probability and entry accept/reject
                |
                v
 portfolio/risk sizing and final PositionPlan
                |
                v
 restart-safe OMS, protective exits and reconciliation
```

The meta-model may initially reject an entry. After its probabilities have been
shown to remain calibrated out of sample, it may apply a capped haircut to the
already risk-sized quantity. It must not:

- choose trade direction independently of the primary policy;
- widen or remove a protective stop;
- cancel a mandatory risk, portfolio or operational exit;
- increase quantity above the deterministic risk budget;
- submit orders directly; or
- use the current prototype HMM as money confidence.

This design follows the side-versus-size separation described in Lopez de
Prado's meta-labeling framework and the later Journal of Financial Data Science
architecture work. It also fits the separation of signal, risk, `PositionPlan`
and order state selected in `RIS-261`.

**Nothing in this design guarantees profit.** A meta-label model can reduce
false-positive CUSUM entries only if stable predictive information exists in
the decision-time features. That claim must be established through locked
out-of-sample replay and delayed live paper evidence. The previously inspected
180-day strategy results do not establish such an edge.

## Relationship to the indicator trade policy

The prior trade-policy artifact deliberately selected no fixed full-position
take-profit for its baseline. It proposed the following independent exit
experiments:

- structure-plus-volatility initial stop and risk sizing;
- monotonic structure/volatility trail;
- fixed full-position target;
- partial target plus a trailing runner; and
- signal or time invalidation.

The ML work must not silently turn the fixed target into the baseline. Instead,
it should be a separately versioned experiment:

| Experiment | Behavior |
| --- | --- |
| `E2/E3` | Deterministic stop, sizing and trailing baseline without a full fixed target |
| `E4` | Frozen fixed stop/target/horizon policy, no ML |
| `M0` | `E4` plus stored shadow probabilities; execution remains identical to `E4` |
| `M1` | `E4` plus a locked probability entry gate in sequential paper replay |
| `M2` | Separately labeled partial-target-plus-runner plan |

The stop, target and maximum holding rule must be frozen before labels are
generated. Optimizing barrier geometry, event sampling, features, model,
calibration and entry threshold together on one period would create a large
researcher-degrees-of-freedom problem.

After an `E4` fill, that immutable bracket owns the position until TARGET,
STOP, AMBIGUOUS, TIMEOUT or a declared data-integrity terminal. A later primary
strategy signal cannot cancel, reverse or replace it. Fresh CUSUM events may
still be scored and resolved in the independent shadow book, but executable
re-entry requires a fresh event after the protected position terminates.

## Primary event and side

The training row is an event, not every minute inside a persistent regime.
Create one candidate when the versioned primary policy emits a new actionable
CUSUM threshold crossing, explicit regime transition or other declared setup.
An optional re-entry during the same regime requires its own causal reset and
cooldown rule; it must not be created retrospectively.

The primary policy supplies:

```text
event_id
decision_ts
asset
timeframe
side in {-1, +1}
setup_type and setup_version
CUSUM event/regime identity
```

At `decision_ts`, the signal timeframe bar must be finalized. An entry cannot
be assumed at an already-observed favorable price inside that bar. The first
eligible execution is the next real one-minute observation under the shared
replay/paper fill contract.

The pre-entry model can use only the known entry reference or worst acceptable
price (`P_ref` or `P_limit`). It cannot use the actual next-open fill as a
feature, because that fill is unknown when the model decides whether to submit
the order. The label resolver should nevertheless use the actual simulated or
paper fill and the actual frozen protective prices so that the outcome matches
the execution engine.

## Exact causal target definition

For candidate event `i`, define:

- `d_i`: finalized-bar decision time;
- `e_i`: first eligible fill time;
- `s_i`: primary side, `-1` short or `+1` long;
- `P_i`: actual simulated/paper fill;
- `S_i`: frozen initial protective stop;
- `T_i`: frozen take-profit;
- `v_i`: maximum accepted-finalized-candle count in the selected timeframe;
- `C_i`: versioned fee, spread, slippage and funding assumptions; and
- `policy_version_i`: the complete labeling and execution-policy version.

For a simple fixed-R target candidate:

```text
D_i = abs(P_i - S_i)
T_i = P_i + s_i * target_multiple * D_i
```

An opposing prior-only structure level may replace the R-multiple target, but
that is a different policy version. No universal stop multiple, target multiple
or holding horizon is asserted.

Resolve the candidate by replaying real one-minute opens, highs, lows and closes
after the eligible fill. Store one terminal outcome:

```text
TP | SL | TIMEOUT | AMBIGUOUS | INVALIDATED | CANCELLED
```

The initial binary meta-label is:

```text
y_meta = 1  only when TP is the first terminal exit and net result after costs is positive
y_meta = 0  for SL, TIMEOUT, INVALIDATED, or conservative AMBIGUOUS resolution
no label    for an unfilled/cancelled candidate
```

This asks the deployable question: "Given the state known when this trade was
proposed, would the exact plan reach its target before failing or expiring?"
It does not condition the sample on future knowledge.

In forward paper, `label_known_at` is the time at which the resolver actually
observed enough data to know the terminal result. It is at least both the
terminal market timestamp's nominal close and the journal observation time, so
delayed ingestion delays label maturity. Current-revision historical canonical
files cannot reconstruct that clock; their declared nominal-plus-five-second
scenario plus research embargo must never be described as actual first-seen
evidence.

### Timeout treatment

A vertical barrier is necessary so an event eventually matures. In the current
cross-asset contract it is counted on **accepted finalized candles in the
selected signal timeframe**, not on one-minute row count or wall-clock minutes.
A closed session counts zero. A sparse session candle may count only when an
authoritative calendar proves which source minutes were scheduled; the current
observed-provider session calendar does not satisfy that requirement, so v2
rejects every sparse target bucket. If the final constituent minute of the last
allowed candle touches a horizontal barrier, that touch is resolved before
timeout at that candle close. Do not discard timeouts and train only on events
that later touched TP or SL. At decision time, the system cannot know which
events will time out, so removing them would create selection bias.

The first conservative binary model should map timeout to `0`. Also preserve
the terminal mark-to-market return and exit reason. If timeouts are common or
economically heterogeneous, promote the target to three outcomes:

```text
TP | SL | TIMEOUT
```

and estimate their probabilities separately. This permits an explicit timeout
value in the economic decision instead of pretending every non-TP has the same
loss.

Events whose vertical barrier lies beyond the available historical dataset are
right-censored and unresolved. They must not be labeled `0` and must not enter
training or evaluation.

### Same-minute ambiguity and gaps

When both `S_i` and `T_i` lie inside one one-minute OHLC bar, OHLC data cannot
identify which price traded first. Use:

- stop-first as the primary conservative label and execution result;
- target-first as a separately reported optimistic sensitivity bound; and
- tick or quote data when a conclusion changes materially between the bounds.

Do not silently drop ambiguous events after seeing their outcome. Preserve an
`ambiguous_same_bar` flag and report their frequency by asset and timeframe.

When a verified market closure ends and a bar opens through a barrier, apply the
exact shared gap-through execution rule and realized open/eligible fill. When a
minute path is missing without authoritative closure proof, resolve the shadow
label as `CANCELLED`. Protected replay reconciles flat at the next observed open
but marks its performance path invalid; it must not claim that TP or SL occurred
inside the unknown interval. The labeler and paper execution engine must use the
same order precedence, price rounding, fees and slippage contract.

### Trailing stops and partial targets

A textbook static triple barrier does not describe a position whose stop moves
or whose quantity changes. If the executable plan uses a CUSUM/structure trail,
signal invalidation, partial TP or runner, the label resolver must execute the
same causal state machine and precedence rules. It must not calculate a static
triple-barrier label and then evaluate a different live exit plan.

For the first ML experiment, immutable stop, target and horizon are preferable
because they make label/executor parity directly testable. The partial-target
plan should be a separate target definition, for example "first partial target
before full protective exit," with runner performance evaluated separately.

## Decision-time static-stop break-even estimate

A classifier threshold of `0.5` is generally not the trade break-even point.
For one unit, let:

- `G_i > 0` be the gross gain at target;
- `L_i > 0` be the gross loss at stop; and
- `C_i >= 0` be expected round-trip fees, spread, slippage, funding and gap
  cushion not already embedded in `G_i` and `L_i`.

For calibrated probability `p_i`:

```text
EV_i = p_i * G_i - (1 - p_i) * L_i - C_i
```

The per-event static-stop break-even estimate is:

```text
p_static_stop_i = (L_i + C_i) / (G_i + L_i)
```

This is a decision-time approximation, not an empirical claim that the trade is
profitable. `G_i` and `L_i` are derived from the proposed immutable bracket and
adverse expected entry; `C_i` contains only declared round-trip costs not
already embedded in those prices. Entry slippage and half-spread must not be
deducted twice.

The implementation field is
`decision_static_stop_break_even_probability`. The initial gate should require:

```text
required_i = max(frozen_model_threshold,
                 p_static_stop_i + locked_safety_margin)
accept_i = p_i > required_i
```

The comparison is deliberately strict. Equality is rejection. If the static
estimate plus margin is at least `1`, the event is untradeable under this
approximation and fails closed. The safety margin must be selected on
training/calibration data and frozen before the final test. The replay UI may
set it only as an explicit, bounded pre-run assumption; it is then included in
the protected-policy digest. It is not a parameter to maximize on the inspected
backtest.

If timeout is modeled separately:

```text
EV_i = p_TP * G_i - p_SL * L_i + p_TIMEOUT * expected_timeout_value_i - C_i
```

The deterministic stop-based risk quantity remains the maximum. Only after
calibration is demonstrated may probability reduce that quantity, for example:

```text
confidence_i = clip((p_i - p_static_stop_i) / (1 - p_static_stop_i), 0, 1)
quantity_i = floor_to_lot(base_risk_quantity_i * confidence_i)
```

This mapping is a research candidate, not a validated sizing law. Entry gating
must be tested before probability-based sizing.

## Decision-time feature contract

The model estimates a conditional probability for the primary side and the
declared trade geometry. It should receive a compact, versioned event snapshot,
not arbitrary chart columns.

Candidate feature families are:

| Family | Causal event-time values |
| --- | --- |
| Primary signal | Side, CUSUM crossing direction, normalized excursion, regime age, reset/cooldown state |
| Trend | Normalized slope, direction agreement, path quality, trend age and distance from trend reference |
| Volatility | Prior-state EWMA fast/slow sigma, ratio, shock flag, ATR/True Range and comparable RS risk scale |
| Structure | Distance to prior-only support/resistance, stop anchor type, normalized stop distance |
| Trade geometry | Intended stop distance, target distance, reward/risk, vertical horizon and cost estimate |
| Path history | Lagged returns, momentum, prior-only autocorrelation and draw-up/drawdown state |
| Participation | Mature volume/activity values, never an unsupported executable-liquidity claim |
| Cross-timeframe | Last fully closed higher-timeframe trend, volatility and conflict context |
| Identity/calendar | Asset, timeframe, session and causal time-of-day/calendar values |
| Data quality | Indicator maturity, source age, freshness and degraded-data flags |

Whenever stop, target or horizon varies between events, its known geometry must
be present. Otherwise the model is asked to estimate one probability for
different questions.

For signed directional features, side-normalization can pool long and short
events:

```text
side_adjusted_feature_i = side_i * signed_feature_i
```

The implementation must assert:

```text
max_feature_source_ts <= decision_ts
```

All scalers, imputers, encoders and feature-selection decisions must be fit on
the training subset only. Higher-timeframe features require an as-of join on
`higher_bar_close_ts <= decision_ts`; an unfinished higher-timeframe candle is
not available.

Never include:

- actual next-open fill or realized slippage in a pre-entry feature;
- future high/low, maximum favorable/adverse excursion or forward return;
- touch time, label duration, terminal outcome or realized exit reason;
- full-history normalization or centered windows;
- a current-model rescore of historical events as if it were their original
  live prediction; or
- a smoothed HMM/Viterbi state that used observations after `decision_ts`.

The current fixed/untrained HMM remains excluded. A future HMM feature must use
training-only parameters and a forward-filtered probability
`P(state_t | observations_1:t)`, not a full-sequence smoothed state.

## Pooling assets and timeframes

Do not begin with one thin model for every asset/timeframe stream. The first
comparison should include:

1. a pooled, volatility-normalized model with asset and timeframe categories;
2. coarser timeframe-family models only if there is enough event support; and
3. the deterministic no-ML `E4` baseline.

Validate pooled behavior with per-asset, timeframe and side diagnostics plus
leave-one-asset and leave-one-timeframe stress tests. A pooled model must not be
allowed to appear successful merely by learning each stream's unconditional TP
rate.

Global chronological cutoffs must be shared across assets. Do not train on a
later date from one asset while calling an earlier date from another asset
out-of-sample. When features contain cross-asset or portfolio context, treat the
information interval as global rather than purging only within one asset.

## Overlapping events and sample weights

CUSUM events can overlap, and different timeframe events for the same asset can
depend on the same one-minute returns. They are not independent observations.

For event interval `I_i`, define concurrency:

```text
c_t = sum_j 1[t belongs to I_j]
```

and average uniqueness:

```text
u_i = mean over t in I_i of (1 / c_t)
w_i = u_i / mean(u)
```

Compute concurrency across all candidate events for the same underlying asset
on the common real one-minute clock, not separately for each displayed
timeframe. Use `w_i` as the first training sample weight.

Do not start with random oversampling or aggressive class weights. They alter
the apparent class prior and therefore the meaning of raw probabilities. If a
class-weighted learner is later tested, calibrate it on a later chronological
sample with the natural event prevalence. Sequential bootstrap or
return-attribution weights are separate ablations, not default additions.

## Model candidates

Start with two deliberately constrained candidates:

1. L2-regularized logistic regression as the interpretable probability
   baseline.
2. Shallow, strongly regularized CatBoost for nonlinear interactions and
   asset/timeframe categorical inputs.

CatBoost's ordered boosting was designed to reduce a form of target leakage in
categorical target statistics. It does not make a random split valid for time
series, and it does not replace purging, embargoing or chronological testing.

Do not begin with deep networks or the prototype HMM. A model should return
`insufficient_history` when a training/calibration fold lacks mature examples
or either class, rather than manufacturing an unstable probability.

## Purged chronological validation

Every event has an information interval:

```text
I_i = [decision_ts_i, label_known_ts_i]
```

For any train/test split, purge a training event when its interval intersects a
test event's interval:

```text
I_train_i intersects I_test_j  =>  remove train_i
```

The primary live proxy is nested chronological walk-forward evaluation:

```text
training core -> purged temporal calibration -> untouched test
```

At fit time `T`, an event is eligible for training only when:

```text
label_known_ts <= T
```

This condition is more exact than selecting rows by decision timestamp alone.
A signal near the boundary may have been observed, while its future barrier
outcome was not yet knowable.

Use:

- inner purged chronological folds for model and hyperparameter selection;
- a disjoint, later calibration block;
- outer chronological walk-forward folds for unbiased model comparison;
- one final chronological holdout never inspected during research; and
- delayed prequential/live-shadow evaluation after offline selection.

For inner Purged K-fold or combinatorial purged CV that permits training data
after a test block, also embargo future training observations immediately after
the test block. Derive the embargo from the declared maximum information span,
feature lookback and publication latency. Do not tune a convenient universal
percentage to improve results. Ordinary random K-fold and default stratified
cross-validation are prohibited.

Combinatorial purged CV can estimate a distribution over research paths. It is
a robustness supplement; chronological walk-forward and delayed live shadow
remain the closest tests of the deployment sequence.

## Probability calibration and metrics

The classifier and calibrator must see disjoint observations. A valid final
fold is:

```text
fit base classifier on train core
predict the later calibration block
fit calibrator on those out-of-fit predictions
evaluate classifier + calibrator once on the later test block
```

Use sigmoid/Platt calibration first. Official scikit-learn guidance warns that
isotonic calibration tends to overfit when calibration sample size is far below
roughly 1,000 observations. Isotonic may be a later ablation when each temporal
calibration block has adequate support.

Do not call `CalibratedClassifierCV` with its default random/stratified splitter.
Pass a custom purged chronological split or use an already fitted/frozen model
with a strictly later calibration set.

Evaluate probability quality with:

- log loss;
- Brier score;
- reliability curves and probability-bin counts;
- calibration by asset, timeframe and side; and
- calibration drift through time.

Evaluate filtering quality with:

- accepted-signal coverage;
- precision and recall for TP events;
- PR-AUC as a secondary imbalance diagnostic;
- net expectancy after costs;
- turnover, profit factor, Sharpe and maximum drawdown;
- performance by asset, timeframe, side and volatility regime; and
- paired comparison against the same primary candidate events without ML.

Accuracy, ROC-AUC and F1 alone are not trading objectives. A model can improve
precision simply by accepting almost no trades, or improve classification while
reducing net strategy value.

Every model, feature, target, threshold and barrier configuration attempted must
be recorded. Backtest-overfitting risk grows with the number of configurations
tried, even when each individual backtest appears clean.

## Delayed live scoring and retraining

Real-time prediction does not require training from unresolved current trades.
The correct initial lifecycle is:

```text
1. finalized CUSUM event arrives
2. freeze and journal causal feature snapshot plus draft plan
3. score once with the already promoted model
4. journal raw/calibrated probability, threshold, decision and model version
5. replay or paper-execute the exact plan
6. resolve its label only after TP, SL, invalidation or timeout
7. append the matured event to the immutable training store
8. retrain on a fixed background schedule
9. run purged validation and calibration
10. atomically promote only an artifact that passes declared gates
```

Required invariants are:

```text
model_training_max_label_known_ts < scoring_ts
max_feature_source_ts <= decision_ts
one immutable score per event_id and model_version
no unresolved event in fit or calibration
```

Scheduled batch retraining is preferable to per-minute `partial_fit` for the
first implementation because it is reproducible and auditable. If incremental
learning is later tested, the update still occurs only when the event's label
matures. Delayed progressive validation must reproduce the same
predict-first, learn-later order.

The promoted artifact should contain at least:

```text
model_version
policy_version and target-definition version
feature schema and hash
training/calibration cutoffs
asset/timeframe scope
estimator and calibrator
economic threshold rule
training metrics and validation gates
library/runtime versions
```

Scoring should fail closed in paper execution on a schema, policy, freshness or
artifact mismatch and emit a clear reason. Real order routing remains outside
this research and requires separate authorization.

### Rejected-event labels and feedback

Once the model starts rejecting entries, learning only from accepted trades
creates selective-label feedback. Keep a parallel shadow simulator that resolves
every otherwise eligible primary candidate under the same deterministic fill,
barrier and cost policy. Mark those outcomes as counterfactual simulation rather
than observed fills.

Maintain separate ledgers:

- an unchanged deterministic baseline candidate/shadow ledger; and
- the sequential ML-gated paper portfolio ledger.

This is necessary because rejecting one trade changes position state and which
later signals are executable. Strategy evaluation must replay the gate
sequentially; deleting rejected rows from an already-computed trade list is not
equivalent.

## Chart and audit presentation

Historical charts must display the prediction stored at the event time. Never
rescore old history with the newest model and present that as historical live
behavior.

For each candidate marker, expose:

```text
CUSUM side and setup
planned stop, target and vertical horizon
P(TP first), raw and calibrated
decision-time static-stop break-even estimate, locked margin and strict required probability
accepted/rejected/shadow-only status and reason
model and policy versions
terminal outcome only after label_known_ts
```

Use distinct styles for pending, TP, SL, timeout and ambiguous events. The UI
must not reveal a future outcome on the chart before the timestamp at which it
became known in replay.

Suggested immutable event fields are:

```text
event_id, asset, timeframe, decision_ts, entry_ts, side
setup_id, setup_version, CUSUM event/regime identity
feature_schema_hash, max_feature_ts, feature snapshot
entry_reference, worst_acceptable_entry, actual_fill
planned_stop, planned_target, timeout_target_bars, timeout_clock, policy_version
model_version, p_raw, p_calibrated, decision_static_stop_break_even_probability
locked_safety_margin, required_probability, accepted, reason
outcome, touch_ts, label_known_ts, ambiguous_same_bar
observed_or_counterfactual, fees, slippage, exit_price, net_pnl
```

## Failure modes that must be tested

1. **Signal-bar leakage:** using the current bar before it is finalized or
   assuming an entry inside its already-observed range.
2. **Unfinished higher timeframe:** forwarding the final 15m/1h value into
   minutes that occurred before that bar closed.
3. **Label-policy drift:** training on a stop, target, trail, cost or horizon
   different from the executable `PositionPlan`.
4. **Unresolved-label leakage:** fitting an event whose terminal outcome was not
   known at the declared training cutoff.
5. **Interval overlap:** a training label consumes returns inside a validation
   or test information interval.
6. **Calibration leakage:** calibrating on in-sample classifier predictions or
   on the final test.
7. **Same-bar fiction:** inventing a favorable TP/SL touch order from OHLC.
8. **Gap mismatch:** labeling at a barrier price while paper execution fills at
   a worse gap-through price.
9. **Timeout selection bias:** deleting timeouts because their future path is
   inconvenient.
10. **End-of-data censoring:** marking an unresolved final event as a loss.
11. **Persistent-regime duplication:** making every minute in one CUSUM regime
   appear to be an independent event.
12. **Cross-timeframe pseudo-replication:** weighting overlapping 1m/5m/15m
   events as independent observations.
13. **Class-prior distortion:** treating oversampled or class-weighted raw
   output as a live probability without later natural-prevalence calibration.
14. **Wrong decision threshold:** using `0.5`, a non-strict comparison, or a
   double-counted cost estimate despite asymmetric target, stop and costs.
15. **Historical rescore leakage:** displaying today's model prediction on an
   old event as if it were generated then.
16. **HMM smoothing leakage:** using future-dependent regime states as features.
17. **Feature-schema drift:** silently changing ordering, units, maturity or
   percent/fraction conventions between training and serving.
18. **Selective-label feedback:** retraining only from trades accepted by an
   earlier model without a declared shadow-label policy.
19. **Non-sequential filtering:** removing rows from a completed backtest
   without replaying the changed position and eligibility state.
20. **Risk override:** allowing confidence to enlarge risk, widen stops or block
   protective exits.
21. **Multiple testing:** selecting the best asset, timeframe, target, model or
   threshold from many trials without accounting for the search.
22. **Restart divergence:** losing pending events, scoring one event twice or
   resolving it differently after restart.

Required automated evidence includes:

- prefix invariance for events, features and predictions;
- batch-versus-stream feature and score parity;
- closed-higher-timeframe as-of-join tests;
- exact zero overlap between train and test information intervals;
- no unresolved label in fit, calibration or metrics;
- labeler-versus-executor parity for normal, gap and ambiguous paths;
- break-even threshold tests under changing reward, risk and costs;
- model/policy/feature-schema mismatch rejection;
- idempotent journal restore of pending and resolved events; and
- sequential gated-ledger versus independent baseline-ledger tests.

## Phased rollout

| Phase | Deliverable | Money behavior |
| --- | --- | --- |
| `P0` | Versioned event, draft barrier, outcome and artifact contracts | No behavior change |
| `P1` | Shared causal label resolver plus executor-parity and leakage tests | No behavior change |
| `P2` | Historical event store, uniqueness weights and purged chronological splits | No behavior change |
| `P3` | Logistic and constrained CatBoost research comparison with disjoint calibration | No behavior change |
| `P4` | Stored walk-forward predictions visible on charts and reports | Shadow only |
| `P5` | Delayed live paper shadow scoring and matured-label monitoring | Shadow only |
| `P6` | Locked probability gate in a separate sequential paper ledger | Paper entries may be rejected |
| `P7` | Capped probability size haircut after calibration evidence | Paper quantity may only decrease |

Promotion from one phase to the next requires declared minimum class/event
support, fold stability, calibration, net-after-cost improvement, subgroup
checks and no causal-contract failure. No universal sample count or performance
threshold is asserted in this research document; those governance gates must be
declared before results are inspected.

Do not enable real routing as part of `RIS-262`. A profitable backtest or brief
paper period is insufficient evidence of live profitability.

## Primary and official sources

- Marcos Lopez de Prado, *Advances in Financial Machine Learning*, Wiley. The
  official contents identify event sampling, the triple-barrier method,
  meta-labeling, sample weights, purged cross-validation and probability-based
  bet sizing as connected parts of the research pipeline:
  [publisher](https://uat.store.wiley.com/en-us/advances-in-financial-machine-learning-p-9781119482086),
  [official contents](https://catalogimages.wiley.com/images/db/pdf/9781119482086.toc.pdf).
- Hudson & Thames' author repository for the Journal of Financial Data Science
  meta-labeling papers describes the secondary model as a false-positive filter
  and sizing layer, and summarizes the calibration experiments:
  [paper code and summaries](https://github.com/hudson-and-thames/meta-labeling).
- Jacques Francois Joubert, "Meta-Labeling: Theory and Framework,"
  *Journal of Financial Data Science* 4(3), 2022:
  [DOI](https://doi.org/10.3905/jfds.2022.1.043).
- Michael Meyer, Jacques Francois Joubert and Mesias Alfeus,
  "Meta-Labeling Architecture," *Journal of Financial Data Science* 4(4), 2022:
  [DOI](https://doi.org/10.3905/jfds.2022.1.108).
- Michael Meyer, Illya Barziy and Jacques Francois Joubert,
  "Meta-Labeling: Calibration and Position Sizing," *Journal of Financial Data
  Science* 5(2), 2023:
  [DOI](https://doi.org/10.3905/jfds.2023.1.062).
- Hudson & Thames' official public implementation contract shows CUSUM-seeded
  events, profit-taking/stop-loss/vertical barriers and binary `{0,1}` labels
  when a primary side is supplied:
  [triple-barrier and meta-label source](https://github.com/hudson-and-thames/mlfinlab/blob/master/mlfinlab/labeling/labeling.py).
- Hudson & Thames' official public cross-validation contract defines
  `PurgedKFold` for labels spanning information intervals and supports training
  and scoring sample weights:
  [purged cross-validation source](https://github.com/hudson-and-thames/mlfinlab/blob/master/mlfinlab/cross_validation/cross_validation.py).
- Mlfin.py's official sampling documentation and source explain event
  concurrency, average uniqueness, sequential bootstrap and return/time-decay
  weights:
  [sampling documentation](https://mlfinpy.readthedocs.io/en/latest/Sampling.html),
  [weighting source](https://mlfinpy.readthedocs.io/en/stable/_modules/mlfinpy/sample_weights/attribution.html).
- E. S. Page, "Continuous Inspection Schemes," *Biometrika* 41(1-2), 1954,
  is the original CUSUM paper:
  [Oxford Academic](https://academic.oup.com/biomet/article-abstract/41/1-2/100/456627).
- Scikit-learn's official probability-calibration guide requires calibration
  data independent of model fitting, documents sigmoid and isotonic methods,
  reliability curves, Brier/log loss, and warns about small-sample isotonic
  overfit:
  [calibration guide](https://scikit-learn.org/stable/modules/calibration.html).
- Alexandru Niculescu-Mizil and Rich Caruana, "Predicting Good Probabilities
  with Supervised Learning," ICML 2005, studies characteristic probability
  distortions and Platt versus isotonic calibration:
  [conference paper](https://icml.cc/Conferences/2005/proceedings/papers/079_GoodProbabilities_NiculescuMizilCaruana.pdf).
- Scikit-learn's official `TimeSeriesSplit` documentation explains
  chronological expanding training sets and the explicit `gap` parameter:
  [documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
- CME Group publishes product/platform trading hours plus date-specific 2026
  Globex holiday schedules and warns that holiday schedules can change. Those
  venue schedules, not gaps inferred from observed bars, are the required
  authority for certifying futures/FX session closures:
  [official trading hours](https://www.cmegroup.com/trading-hours.html).
- Databento documents that OHLCV construction differs by trade breaks, bar
  boundaries and illiquid intervals; its daily bars are UTC-based rather than
  exchange-session bars. It also provides point-in-time instrument definitions
  and continuous-contract mappings to actual instruments. Those fields are
  required to preserve roll and instrument provenance without lookahead:
  [schema contract](https://databento.com/docs/schemas-and-data-formats/whats-a-schema),
  [point-in-time definitions](https://databento.com/docs/schemas-and-data-formats/instrument-definitions),
  [continuous symbology](https://databento.com/docs/standards-and-conventions/symbology).
- River's official delayed progressive-validation contract predicts first and
  reveals the target to the learner only after its declared delay, matching the
  live TP/SL label lifecycle:
  [documentation](https://riverml.xyz/dev/api/evaluate/progressive-val-score/).
- David H. Bailey, Jonathan Borwein, Marcos Lopez de Prado and Qiji Jim Zhu,
  "The Probability of Backtest Overfitting," documents how strategy selection
  over many trials can create overfit investment backtests:
  [SSRN paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253).
- Liudmila Prokhorenkova et al., "CatBoost: unbiased boosting with categorical
  features," NeurIPS 2018, describes ordered boosting and categorical target
  statistics designed to address prediction shift and a form of target leakage:
  [NeurIPS paper](https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html).

## Final research boundary

The cited literature establishes that CUSUM event sampling, triple-barrier
outcomes, meta-label filtering, probability calibration and purged validation
are legitimate techniques. It does not establish that the current RiskYieldMM
indicators contain enough stable information to predict TP-before-SL, that one
model will work across every asset and timeframe, or that filtered trades will
be profitable after costs.

Those are empirical claims. They remain false until the phased implementation
produces causal, locked out-of-sample and delayed live-paper evidence that
supports them.

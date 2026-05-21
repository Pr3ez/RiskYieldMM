# RiskYieldMM Label Redesign Document: Combining Stage‑1 Anomaly Findings With Triple‑Barrier Four‑Class Labels

Date: 2026-05-21
Scope: `RiskYieldMM` HTF / Stage‑1 research pipeline
Primary target scope: `8h/B` first, then controlled expansion only after stability evidence
Primary business target: collapsed four-class trading outcome
Authoring goal: combine earlier Stage‑1 findings — anomaly labeling, OOF label quality, helper models, event gates, and walk-forward discipline — with the proposed triple-barrier label family.

---

## 1. Executive decision

The new triple-barrier label should **not replace the Stage‑1 anomaly work**. It should become the cleaner parent label, while the anomaly system remains a label-quality and trade-quality control layer.

Recommended target stack:

```text
Layer 0: original legacy target_4class
Layer 1: target_4class_tb_atr_v1
Layer 2: target_4class_tb_hybrid_v1
Layer 3: target_8class_tb_anomaly_v1
Layer 4: target_meta_trade_quality_v1
```

The first production research candidate should be:

```text
target_4class_tb_atr_v1
```

with a second experimental arm:

```text
target_8class_tb_anomaly_v1
```

where anomaly classes are same-parent suspicious leaves:

```text
4 -> DOWN_BALANCED_ANOMALY
5 -> DOWN_EXPANSION_ANOMALY
6 -> UP_BALANCED_ANOMALY
7 -> UP_EXPANSION_ANOMALY
```

Primary evaluation must still collapse `4..7 -> 0..3`.

The previous Stage‑1 anomaly research found that the anomaly-label method is promising enough for continued `8h/B` work, but not strong enough for broad promotion across all roots/assets. The current best representative candidate was `catboost_8class_collapsed / thr8p0_full_hybrid_exclude_review`, while GC/ES instability and weak expansion recall remain active blockers. Therefore, the correct next step is not broad production promotion. It is a controlled `8h/B` comparison:

```text
legacy target_4class
vs
target_4class_tb_atr_v1
vs
target_8class_anomaly from legacy parent
vs
target_8class_tb_anomaly_v1
```

---

## 2. Non-negotiable constraints carried from Stage‑1

### 2.1 Do not overwrite source labels

Never overwrite `target_4class`.

All experimental labels must be new columns or new artifact roots:

```text
target_4class_legacy
target_4class_tb_atr_v1
target_4class_tb_hybrid_v1
target_8class_anomaly_legacy_parent
target_8class_tb_anomaly_v1
target_meta_trade_quality_v1
```

### 2.2 Anomaly means same-parent suspicious row

Anomaly class is not an unknown class and not an automatic opposite-direction correction.

Correct mapping:

```text
0 -> 4 only if suspicious but still DOWN_BALANCED parent
1 -> 5 only if suspicious but still DOWN_EXPANSION parent
2 -> 6 only if suspicious but still UP_BALANCED parent
3 -> 7 only if suspicious but still UP_EXPANSION parent
```

Wrong mapping:

```text
UP row looks like DOWN -> silently map to DOWN anomaly
```

High-confidence opposite-direction rows should be exported for review, excluded, or downweighted. They should not be automatically flipped or converted into anomaly leaves.

### 2.3 Primary metric remains collapsed four-class quality

The 8-class target is a training/control device. It is not the business target.

Primary metrics:

```text
collapsed_4_accuracy
collapsed_4_macro_f1
direction_accuracy
cross_direction_error
logloss
Brier score
ECE
```

Secondary diagnostics:

```text
8-class macro F1
anomaly leaf precision/recall
anomaly rate by parent class
review/exclude count
same-bar ambiguity count
barrier-hit distributions
MFE/MAE by class
```

### 2.4 No global static anomaly relabel file

The previous Stage‑1 plan correctly identified global anomaly files as leakage risk.

For walk-forward step `T`, anomaly scores must be generated from models whose training/scoring information ends before or at that step’s train end. Acceptable approaches:

```text
1. build anomaly labels inside each Stage‑1 step from historical OOF predictions only;
2. store anomaly score artifacts with score_generated_train_end_batch and filter by current step;
3. for offline research only, use a fixed discovery period and a later untouched holdout period.
```

### 2.5 Stage‑1 remains offline analysis, not live deployment

Stage‑1 is an offline fold-grid analysis layer. It stores validation and prediction payloads for later analysis, candidate pruning, selector policy research, reward building, and policy datasets. It is not the standard Optuna runtime selection path.

---

## 3. What earlier Stage‑1 findings mean for the new label

### 3.1 Legacy four-class label weakness

The legacy parent labels can mix economically different future paths into the same class, especially inside expansion classes. A row can become `UP_EXPANSION` because the future terminal direction is up, while the path also contains large opposite-side danger. This is bad for position sizing.

Triple barrier directly fixes this by making expansion path-based:

```text
UP_EXPANSION   = upper barrier hit first
DOWN_EXPANSION = lower barrier hit first
```

Balanced classes become terminal fallback classes when no barrier is reached.

### 3.2 Stage‑1 anomaly work should become a second layer

Earlier anomaly experiments were not merely generic market anomaly detection. They were label-quality diagnostics based on OOF probabilities, confidence, temporal inconsistency, and class-local outlier scores.

That means the anomaly layer should be applied **after** a parent label is chosen.

New sequence:

```text
1. Generate parent target_4class_tb_atr_v1.
2. Train OOF model on parent target inside train split.
3. Score label quality using OOF probabilities and supporting signals.
4. Convert only same-parent suspicious rows into parent+4 anomaly leaves.
5. Export high-confidence opposite-direction conflicts for review/exclusion.
6. Train split-class model and evaluate collapsed back to 4 classes.
```

### 3.3 Existing anomaly findings become stronger under triple barrier

The Stage‑1 anomaly runner found that suspicious rows can improve downstream results when handled carefully. The best representative candidate was an 8-class collapsed setup with `thr8p0_full_hybrid_exclude_review`. This suggests that splitting difficult/noisy rows into separate leaves can help CatBoost learn cleaner parent decision boundaries.

Triple-barrier labels should make the anomaly detector more meaningful because the parent labels are less ambiguous:

```text
Legacy parent:
    anomaly detector may catch label-design ambiguity and model weakness mixed together.

Triple-barrier parent:
    anomaly detector more likely catches genuinely hard/noisy rows, structure mismatch, or ambiguous path rows.
```

### 3.4 Do not use anomaly detection to “repair” bad barrier definitions

If many rows become anomalies under triple barrier, that is not automatically a success. It may mean the barriers are badly calibrated.

Warning signs:

```text
anomaly rate > 10–15% in one parent class
expansion classes become mostly anomaly leaves
same-bar both-hit rate high
terminal fallback dominates too strongly
UP/DOWN anomalies concentrated around one asset/session only
```

When this happens, first inspect barrier parameters, not only anomaly thresholds.

---

## 4. Proposed triple-barrier parent label

### 4.1 Parent classes

```text
0 = DOWN_BALANCED
1 = DOWN_EXPANSION
2 = UP_BALANCED
3 = UP_EXPANSION
-1 = invalid / ambiguous / no-trade / insufficient future window
```

### 4.2 Prediction-time barrier construction

At row `t`, after the current 1m bar is closed:

```text
close_t = current close
volatility_t = prediction-time volatility estimate
upper_barrier_t = close_t * (1 + k_up * volatility_t)
lower_barrier_t = close_t * (1 - k_down * volatility_t)
vertical_barrier_t = label_window_end
```

Recommended v1:

```text
volatility_t = max(ATR_pct_14, rolling_std_return_120)
k_up = 2.0
k_down = 1.5
theta_terminal = 0.25
same_bar_both_hit_policy = invalid
label_window_policy = opposite_family_first_half
```

### 4.3 Future event assignment

Use the future label window only for outcome assignment:

```text
if future high hits upper barrier before lower barrier:
    target = 3  # UP_EXPANSION

elif future low hits lower barrier before upper barrier:
    target = 1  # DOWN_EXPANSION

elif both barriers hit in the same 15m bar:
    target = -1  # ambiguous in symmetric research v1

else:
    terminal_z = end_return / volatility_t

    if terminal_z >= theta_terminal:
        target = 2  # UP_BALANCED
    elif terminal_z <= -theta_terminal:
        target = 0  # DOWN_BALANCED
    else:
        target = -1
```

### 4.4 Why same-bar both-hit should be invalid in v1

With OHLC bars, if high and low both cross barriers inside the same 15m bar, the true order is unknown. Conservative stop-first logic can be used for live long-only/short-only simulations, but for a symmetric multiclass research label it is cleaner to mark the row invalid.

Recommended v1:

```text
same_bar_both_hit -> -1
```

Later long-only meta-labeling can use conservative stop-first.

---

## 5. Indicator-aware barrier variants

### 5.1 V1: ATR-only

Purpose: clean baseline.

```text
upper = close_t * (1 + k_up * vol_t)
lower = close_t * (1 - k_down * vol_t)
```

Use this first because it isolates whether triple barrier itself improves class semantics.

### 5.2 V2: ATR + Bollinger

Purpose: connect to previous Stage‑1 band-gate logic.

```text
upper_atr = close_t * (1 + k_up * vol_t)
lower_atr = close_t * (1 - k_down * vol_t)

if bb_upper > close_t:
    upper = min(upper_atr, bb_upper)
else:
    upper = upper_atr

if bb_lower < close_t:
    lower = max(lower_atr, bb_lower)
else:
    lower = lower_atr
```

This connects to earlier Stage‑1 designs where entry/gate logic used Bollinger-zone conditions and first-event gates.

### 5.3 V3: ATR + Keltner

Purpose: smoother production candidate.

Keltner is often better for risk geometry because it is ATR-based and less jumpy than standard-deviation bands.

```text
upper = min(close_t * (1 + k_up * vol_t), keltner_upper_t)
lower = max(close_t * (1 - k_down * vol_t), keltner_lower_t)
```

### 5.4 V4: ATR + support/resistance or pivots

Purpose: realistic exit target geometry, but high overfit risk.

```text
upper_structure = nearest valid resistance/pivot/VWAP band above close_t
lower_structure = nearest valid support/pivot/VWAP band below close_t

upper = min(upper_atr, upper_structure) when valid
lower = max(lower_atr, lower_structure) when valid
```

Do not start here. Add only after ATR-only and ATR+Keltner are stable.

---

## 6. Combining with earlier Stage‑1 event-gate logic

Earlier Stage‑1 labeling used entry-row-only logic, Bollinger-zone conditions, and forward first-event scans. That historical idea is very close to triple barrier:

```text
old gate:
    entry condition at t
    scan future until gate or invalidation condition happens first

new triple barrier:
    define upper/lower barriers at t
    scan future until upper/lower barrier happens first
```

The right synthesis:

```text
Use indicator gates to define barrier geometry,
not as direct relabeling rules.
```

Examples:

### Mean-reversion long setup

```text
entry context:
    price near lower Bollinger/Keltner zone
    ADX not strongly bearish
    VWAP distance stretched

upper barrier:
    BB middle, VWAP, or ATR target

lower barrier:
    lower band minus ATR buffer or recent support break

label:
    UP_EXPANSION if upper barrier hit first
    DOWN_EXPANSION if lower invalidation hit first
    UP/DOWN_BALANCED based on terminal_z if no hit
```

### Breakout setup

```text
entry context:
    Donchian/Keltner breakout
    ADX rising
    DI direction confirms

upper barrier:
    ATR expansion target or next structure level

lower barrier:
    failed-breakout return inside channel

label:
    UP_EXPANSION only if continuation target is hit first
    DOWN_EXPANSION if failed breakout/invalidation hits first
```

This keeps the valuable Stage‑1 “first event wins” principle but removes the fragile hard-coded semantic label rules.

---

## 7. Combining with Stage‑1 helper models

The existing Stage‑1/helper ecosystem includes or has considered HMM regimes, GARCH volatility, Isolation Forest anomalies, Kalman state estimation, CUSUM changepoints, OU/AR(1), BOCPD, EVT, and drift tests. These should not all become label rules. They should have specific roles.

### 7.1 CUSUM

Best use:

```text
event sampling
vertical-barrier start selection
change-point/stress flag
```

Do not force every 1m row to be equally important. Use CUSUM to define event rows or to mark rows where barrier widths should be adjusted.

Recommended experiment:

```text
target_4class_tb_atr_all_rows
vs
target_4class_tb_atr_cusum_events
```

Expected benefit:

```text
fewer redundant overlapping labels
cleaner OOF anomaly scores
lower training noise
```

### 7.2 GARCH / EGARCH / EWMA volatility

Best use:

```text
volatility_t for barrier scaling
volatility regime feature
sizer volatility forecast
```

Recommended volatility stack:

```text
vol_t = max(
    ATR_pct_14,
    rolling_realized_vol_120,
    EWMA_vol_240,
    GARCH_vol_if_available
)
```

Do not use future realized volatility. Every volatility input must be available at prediction time.

### 7.3 HMM4/HMM5 regimes

Best use:

```text
regime-conditioned barrier parameters
regime-conditioned anomaly thresholds
regime-aware validation reports
```

Example:

```text
low-vol range:
    smaller k_up, smaller theta_terminal, structure/VWAP barriers allowed

trend regime:
    larger k_up, larger k_down, Keltner/Donchian barrier preferred

high-vol stress:
    larger volatility floor, lower max size, stricter no-trade filter
```

Do not directly label “HMM state 3 = UP_EXPANSION”. That would mix unsupervised state with target semantics.

### 7.4 Kalman filter

Best use:

```text
smooth state estimate
trend slope estimate
residual/z-score feature
barrier sanity filter
```

Example:

```text
if Kalman residual extreme and reverting:
    use mean-reversion barrier template

if Kalman slope strong and residual not stretched:
    use trend-continuation barrier template
```

### 7.5 Isolation Forest / anomaly ensemble

Best use:

```text
supporting anomaly score
not replacement target
not automatic relabeler
```

Important: Isolation Forest output is pseudo-labeling, not supervised truth. It can help identify suspicious feature-space outliers, but it should be combined with OOF probability conflict and class-local thresholds.

Recommended anomaly score:

```text
anomaly_score =
    0.45 * label_conflict_score
  + 0.20 * normalized_margin_score
  + 0.15 * entropy_score
  + 0.10 * temporal_inconsistency_score
  + 0.10 * class_local_outlier_score
```

For triple-barrier labels, add:

```text
+ same_bar_ambiguity_nearby_score
+ barrier_distance_extreme_score
+ hit_time_outlier_score
```

### 7.6 BOCPD / drift detectors

Best use:

```text
block training labels around changepoints
regime reset
reduce confidence after detected distribution shift
```

Do not relabel changepoint rows automatically. Treat them as high-review or low-weight candidates until validated.

### 7.7 EVT tail-risk

Best use:

```text
hard risk cap
no-trade filter
barrier max-distance adjustment
sizer penalty
```

Tail-risk helpers are more useful for sizing and risk control than for assigning parent class.

---

## 8. New target/artifact design

### 8.1 Parent label artifact columns

Add to label parquet outputs:

```text
target_4class_tb_atr_v1
target_name_tb_atr_v1
tb_first_hit
tb_hit_bar_offset
tb_same_bar_both_hit
tb_upper_barrier
tb_lower_barrier
tb_upper_distance_pct
tb_lower_distance_pct
tb_volatility_pct
tb_terminal_return
tb_terminal_z
tb_mfe_pct
tb_mae_pct
tb_label_reason
tb_barrier_mode
tb_label_version
```

### 8.2 Anomaly artifact columns

Write under experiment output, not source roots:

```text
target_8class_tb_anomaly_v1
target_4class_tb_parent
target_is_anomaly
anomaly_score
anomaly_detector_name
anomaly_threshold_pct
anomaly_action
review_reason
score_generated_train_end_batch
```

### 8.3 Meta-label artifact columns

Later:

```text
target_meta_trade_quality_v1
meta_trade_outcome
meta_hit_tp_before_sl
meta_net_return_after_costs
meta_max_adverse_excursion
meta_max_favorable_excursion
```

### 8.4 Label-only column policy

All `tb_*` future diagnostics must be label-only unless they are recomputed independently in the feature stage using only prediction-time data.

Safe feature names should be separate:

```text
F_VOL_atr_pct_14
F_VOL_ewma_vol_240
F_REG_hmm_state_prob_*
F_RISK_evt_tail_prob
F_STATE_kalman_residual_z
```

Do not allow:

```text
tb_mfe_pct
tb_mae_pct
tb_first_hit
tb_hit_bar_offset
tb_terminal_z
```

to appear in optimized/helper model-facing outputs.

---

## 9. Implementation plan inside RiskYieldMM

### 9.1 `htf_kernels.py`

Add:

```text
compute_triple_barrier_events(...)
compute_4class_triple_barrier_labels(...)
```

The low-level kernel should scan future `15m` high/low arrays by `label_window_batch_id`, exactly like the existing hybrid-distance path does for future metrics.

Return:

```text
target
first_hit
hit_bar_offset
terminal_z
mfe_pct
mae_pct
remaining_bars
same_bar_both_hit
```

### 9.2 `htf_multiregime_pipeline.py`

Inside `_build_1m_labels`:

1. Keep existing legacy path.
2. Compute prediction-time volatility and barriers.
3. Switch labeler by `config.label_method`.

Pseudo-switch:

```text
if label_method == "legacy_4class":
    use compute_4class_labels

elif label_method == "triple_barrier_4class":
    use compute_4class_triple_barrier_labels
```

### 9.3 `MultiRegimeHTFConfig`

Add:

```text
label_method = "legacy_4class"

tb_volatility_method = "atr_or_realized"
tb_atr_period = 14
tb_realized_vol_period = 120
tb_k_up = 2.0
tb_k_down = 1.5
tb_terminal_theta = 0.25
tb_min_volatility_pct = 0.0005
tb_min_barrier_pct = 0.0005
tb_max_barrier_pct = 0.05
tb_barrier_mode = "atr_only"
tb_same_bar_policy = "ambiguous_to_invalid"
tb_label_version = "tb_atr_v1"
```

### 9.4 `htf_feature_acceptance.py`

Add all future-dependent `tb_*` diagnostics to forbidden label-only columns:

```text
tb_first_hit
tb_hit_bar_offset
tb_same_bar_both_hit
tb_mfe_pct
tb_mae_pct
tb_terminal_z
tb_label_reason
tb_upper_barrier
tb_lower_barrier
tb_upper_distance_pct
tb_lower_distance_pct
```

Even if some barrier columns are prediction-time-safe, block them in final outputs unless generated in the feature stage. This prevents accidental leakage through label artifacts.

### 9.5 Stage‑1 anomaly runner

Extend the runner to support a parent target parameter:

```text
--parent-target-col target_4class_tb_atr_v1
--anomaly-target-col target_8class_tb_anomaly_v1
--collapse-map 4:0,5:1,6:2,7:3
```

The runner must preserve old behavior:

```text
--parent-target-col target_4class
```

so legacy-vs-triple-barrier comparisons are direct.

---

## 10. Experiment matrix

### 10.1 Phase A: label sanity only

No model training yet.

Compare:

```text
legacy target_4class
target_4class_tb_atr_v1
target_4class_tb_bollinger_v1
target_4class_tb_keltner_v1
```

Reports:

```text
class distribution
invalid ratio
same-bar both-hit ratio
mean end_return by class
median terminal_z by class
MFE/MAE by class
hit_bar_offset distribution
barrier distance distribution
label stability by HMM/GARCH regime
label stability by asset/session
```

Acceptance:

```text
UP_EXPANSION has highest positive MFE and positive terminal return
DOWN_EXPANSION has highest downside MAE and negative terminal return
BALANCED classes are less extreme than EXPANSION
invalid ratio not excessive
same-bar ambiguity not excessive
class distribution not collapsed into one class
```

### 10.2 Phase B: parent 4-class model

Train CatBoost with the same Stage‑1 protocol.

Compare:

```text
baseline_legacy_4class
catboost_tb_atr_4class
catboost_tb_keltner_4class
```

Primary metrics:

```text
collapsed_4_accuracy
macro_f1
direction_accuracy
cross_direction_error
logloss
Brier
ECE
```

Acceptance:

```text
direction_accuracy up or stable
cross_direction_error down
macro F1 up or stable
calibration not materially worse
```

### 10.3 Phase C: anomaly split on legacy vs TB parent

Compare:

```text
legacy_parent_8class_anomaly
tb_atr_parent_8class_anomaly
tb_keltner_parent_8class_anomaly
```

Anomaly detector candidates:

```text
thr3p0_label_conflict_exclude_review
thr8p0_full_hybrid_exclude_review
thr3p0_full_hybrid_exclude_review
```

Acceptance:

```text
collapsed four-class metrics improve vs same parent 4-class model
cross-direction error decreases
anomaly leaves do not become generic trash bin
review rows are duplicate-free
opposite-direction rows are exported/excluded, not silently relabeled
```

### 10.4 Phase D: CUSUM event sampling

Compare all-row vs event-row training:

```text
tb_atr_all_rows
tb_atr_cusum_events
tb_atr_cusum_events_plus_meta
```

Expected benefit:

```text
less overlapping label noise
fewer redundant rows
better calibration
lower anomaly rate
```

Risk:

```text
too few expansion examples
class imbalance worsens
```

### 10.5 Phase E: meta-labeling

Primary classifier predicts parent class.

Meta-label predicts whether to trade:

```text
1 = signal reached favorable barrier or positive net expectancy
0 = signal failed, hit adverse barrier, or not worth costs
```

Inputs:

```text
class probabilities
probability margin
entropy
volatility
HMM regime
GARCH vol
CUSUM state
IsolationForest score
Kalman residual
barrier distance
predicted expansion probability
```

Acceptance:

```text
lower trade count
higher expectancy
lower drawdown
better calibration of traded subset
```

---

## 11. Validation design

Use the existing Stage‑1 walk-forward discipline:

```text
contiguous train windows
contiguous validation windows
prediction batch isolated
no prediction batch rows in training or validation
train-only feature selection
OOF scores truly out-of-fold
purge/embargo when label horizons overlap
```

For triple-barrier labels, add:

```text
embargo >= max vertical barrier / label window overlap
```

Representative evaluation order:

```text
1. BTCUSDT 8h/B smoke
2. BTCUSDT 8h/B full Stage‑1
3. representative 8h/B panel:
   BTCUSDT, ETHUSDT, EURUSD, ES, GC
4. only then consider 8h/C or 24h/B
```

Do not promote to all roots until ES/GC instability and expansion recall problems are understood.

---

## 12. Acceptance gates

### 12.1 Parent label acceptance

A triple-barrier parent is accepted for modeling only if:

```text
invalid rate is bounded
same-bar ambiguity rate is bounded
class distributions are usable
UP/DOWN expansion classes have correct MFE/MAE signs
balanced classes are less extreme than expansion classes
label behavior is stable across at least two chronological windows
```

### 12.2 Model acceptance

A model is accepted only if:

```text
collapsed_4_accuracy improves or remains stable
macro_f1 improves or remains stable
direction_accuracy improves
cross_direction_error decreases
logloss/Brier/ECE do not materially worsen
results survive future chronological holdout
```

### 12.3 Anomaly acceptance

Anomaly layer is accepted only if:

```text
collapsed 4-class metrics improve after collapse
anomaly rate is bounded per parent class
opposite-direction rows are reviewed/excluded, not relabeled
anomaly leaves show distinct behavior rather than generic trash-bin behavior
improvement is not BTCUSDT-only
```

### 12.4 Promotion rejection rules

Reject or keep experimental if:

```text
only one asset improves
GC/ES instability remains unexplained
cross-direction error worsens
calibration worsens sharply
8-class metrics improve but collapsed 4-class metrics worsen
expansion recall collapses
anomaly leaves absorb too much of one class
```

---

## 13. Sizing interpretation after TB labels

The triple-barrier parent is directly useful for position sizing.

Class probabilities:

```text
p0 = P(DOWN_BALANCED)
p1 = P(DOWN_EXPANSION)
p2 = P(UP_BALANCED)
p3 = P(UP_EXPANSION)
```

Directional probabilities:

```text
p_down = p0 + p1
p_up = p2 + p3
directional_edge = p_up - p_down
```

Long-side score:

```text
long_score =
    +1.00 * p3
    +0.40 * p2
    -0.70 * p0
    -1.20 * p1
```

Then combine with:

```text
calibrated probability
volatility target
barrier distance
expected class payoff table
meta-label trade-quality probability
hard leverage/risk caps
```

This is better than fixed class-to-size mapping because it distinguishes:

```text
UP_BALANCED: modest favorable terminal drift
UP_EXPANSION: TP-like barrier event
DOWN_EXPANSION: stop-like adverse event
```

---

## 14. Concrete next run plan

### Step 1: Implement TB ATR parent

```text
label_method = triple_barrier_4class
tb_barrier_mode = atr_only
tb_label_version = tb_atr_v1
```

Run only `8h/B`, BTCUSDT first.

### Step 2: Generate label sanity report

Output:

```text
docs/research/tb-label-sanity-8h-b-btcusdt-YYYY-MM-DD.md
```

Must include:

```text
class distribution
invalid ratio
same-bar ambiguity ratio
MFE/MAE by class
terminal_z by class
hit offset by class
barrier distance distributions
```

### Step 3: Parent model comparison

Run:

```text
legacy target_4class
vs
target_4class_tb_atr_v1
```

Same features, same splits, same CatBoost settings.

### Step 4: Anomaly overlay comparison

Run:

```text
legacy_parent + anomaly
vs
tb_atr_parent + anomaly
```

Use:

```text
thr3p0_label_conflict_exclude_review
thr8p0_full_hybrid_exclude_review
thr3p0_full_hybrid_exclude_review
```

### Step 5: Representative 8h/B panel

Targets:

```text
BTCUSDT
ETHUSDT
EURUSD
ES
GC
```

Promotion only if median gate passes and no major asset-specific failure is hidden.

---

## 15. Final recommendation

The strongest design is:

```text
Triple-barrier parent label
+
Stage‑1 OOF anomaly leaf split
+
review/exclude for high-confidence opposite-direction conflicts
+
meta-label trade-quality layer
+
volatility/utility sizing
```

But implementation should be staged:

```text
1. parent TB label first
2. anomaly overlay second
3. CUSUM event sampling third
4. helper-regime-conditioned barrier parameters fourth
5. meta-label and live sizer fifth
```

Do not combine all methods in the first run. The first question is simple:

```text
Does target_4class_tb_atr_wide_v2 produce cleaner, more tradable parent classes than legacy target_4class under the same Stage‑1 validation protocol?
```

Only after that answer is positive should the anomaly and helper-model layers be promoted around it.

### 15.1 Implementation note: first sanity result

The initial `tb_atr_v1`, `tb_bollinger_v1`, and `tb_keltner_v1` variants were
materialized for BTCUSDT `8h/B` and kept as diagnostic baselines. After
separating non-entry rows from label-eligible entry-window rows, their invalid
rates were acceptable, but they still failed the class-share gate because
balanced classes were almost absent. The cause was barrier geometry: the v1
barriers were too close for BTCUSDT `8h/B`, so most eligible rows hit an
expansion barrier quickly.

The first model-ready parent candidate is therefore:

```text
target_4class_tb_atr_wide_v2
```

It uses symmetric wider ATR barriers:

```text
volatility_t = max(ATR_pct_14, rolling_std_return_120)
k_up = 15.0
k_down = 15.0
theta_terminal = 0.0
same_bar_both_hit_policy = invalid
label_window_policy = opposite_family_first_half
```

Current BTCUSDT `8h/B` sanity result:

```text
eligible rows: 1,405,440
valid eligible rows: 1,404,118
eligible invalid ratio: 0.09%
same-bar both-hit ratio: 0.09%
class shares:
  DOWN_BALANCED  22.95%
  DOWN_EXPANSION 25.77%
  UP_BALANCED    26.25%
  UP_EXPANSION   25.02%
```

This makes `target_4class_tb_atr_wide_v2` the next Stage‑1 comparison target.
The v1 variants should not be used for model comparison unless their barrier
geometry is revised.

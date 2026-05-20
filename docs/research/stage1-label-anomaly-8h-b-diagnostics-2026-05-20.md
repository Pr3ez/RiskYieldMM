# Stage-1 Label-Anomaly 8h/B Diagnostics

Date: 2026-05-20

Run:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_representative_20260520
```

Scope:

```text
targets: BTCUSDT, ETHUSDT, EURUSD, ES, GC
root: 8h/B
context: core-ex-target
models: baseline_4class, catboost_cleaned_4class, catboost_8class_collapsed
rows per target: 180,000
selected features per target: 250
OOF-scored train rows per target: 78,693
```

## Resume Checklist

Use this document as the current state for label-anomaly work. The original
research brief records the starting rationale; this diagnostics report records
what was actually run and why broad promotion is blocked.

When resuming:

1. Start from `8h/B` only.
2. Treat `catboost_8class_collapsed / thr8p0_full_hybrid_exclude_review` as the
   leading representative candidate, not a production default.
3. Do not run all roots until ES and GC are understood.
4. Focus next on GC validation-period drift, ES/GC review rows, expansion-class
   recall, and direction-conditioned modeling.
5. Keep the promotion gate unchanged: validation and test must both improve, and
   per-asset failures must be explained.

## Executive Decision

The implementation is valid and the representative `8h/B` CatBoost experiment
produced useful signal, but the method is not ready for all roots yet.

Keep testing on `8h/B` only.

Leading candidate:

```text
catboost_8class_collapsed / thr8p0_full_hybrid_exclude_review
```

Why:

- passed the median gate on both validation and test;
- passed both validation and test per-asset acceptance on BTCUSDT, ETHUSDT, and
  EURUSD;
- improved test median accuracy, macro F1, direction accuracy, and
  cross-direction error;
- uses a wider 8% class-local anomaly threshold, which gave stronger and more
  consistent split-class behavior than the 3% hybrid split-class setting.

Do not promote yet:

- ES and GC are not stable enough under the leading candidate;
- expansion class recall remains weak for Monday-Friday/session assets;
- several configs win on test but not validation, or validation but not test;
- the experiment validates the direction of the approach, not production
  readiness.

## Artifact Integrity

Merged root checks before the run:

| Target | Output Rows | Dropped Missing Context | Duplicate Count | Null Feature Count |
|---|---:|---:|---:|---:|
| BTCUSDT | 413,652 | 974,965 | 0 | 0 |
| ETHUSDT | 413,652 | 922,405 | 0 | 0 |
| EURUSD | 413,652 | 559,538 | 0 | 0 |
| ES | 413,652 | 655 | 0 | 0 |
| GC | 413,652 | 556,026 | 0 | 0 |

Experiment artifact checks:

- required run-level and unit-level artifacts are present;
- no duplicate review rows on `timestamp,batch_id`;
- anomaly labels stay within `0..7`;
- anomaly and cleaned sample weights are non-negative;
- label-quality scores are bounded where expected;
- prediction rows have no duplicate `model,config_id,split,row_id`;
- required probability columns are present and normalized per model family.

The large `Dropped Missing Context` counts are expected under the v1 exact
timestamp join policy. Rows are dropped rather than stale-filled.

## Chronological Split

All targets use the same target-row chronology:

| Split | Rows | Batches | Time Range UTC |
|---|---:|---:|---|
| train | 107,553 | 459 | 2025-05-08 01:15 -> 2025-12-10 03:59 |
| validation | 35,852 | 153 | 2025-12-10 08:00 -> 2026-02-23 11:59 |
| test | 36,595 | 154 | 2026-02-23 16:00 -> 2026-05-06 19:59 |

OOF training used five expanding folds inside the train split. This preserves
the research requirement that label-quality scores come from rows scored
out-of-sample.

## Baseline Test Quality

| Target | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | ECE |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSDT | 0.314633 | 0.218870 | 0.515344 | 0.484656 | 1.420286 | 0.112634 |
| ETHUSDT | 0.267058 | 0.248822 | 0.490176 | 0.509824 | 1.436171 | 0.123492 |
| EURUSD | 0.358300 | 0.192922 | 0.459790 | 0.540210 | 1.270358 | 0.145905 |
| ES | 0.435087 | 0.224361 | 0.538243 | 0.461757 | 1.221514 | 0.095764 |
| GC | 0.356688 | 0.204639 | 0.522476 | 0.477524 | 1.346920 | 0.140615 |

Baseline direction accuracy is weak across all targets. This makes
cross-direction error the most important acceptance criterion.

## Median Gate Results

Configs passing both validation and test median gates:

| Model | Config | Test Accuracy Delta | Test Macro F1 Delta | Test Direction Delta | Test Cross-Direction Delta | Test Pass Rate |
|---|---|---:|---:|---:|---:|---:|
| `catboost_8class_collapsed` | `thr8p0_full_hybrid_exclude_review` | +0.005848 | +0.005194 | +0.005465 | -0.005465 | 0.60 |
| `catboost_cleaned_4class` | `thr3p0_label_conflict_exclude_review` | +0.001503 | -0.000418 | +0.001530 | -0.001530 | 0.40 |

Other useful but unstable configs:

| Model | Config | Comment |
|---|---|---|
| `catboost_8class_collapsed` | `thr3p0_label_conflict_exclude_review` | strong test median and 0.80 test pass rate, but failed validation median |
| `catboost_cleaned_4class` | `thr3p0_full_hybrid_exclude_review` | strong test median and 0.80 test pass rate, but failed validation median |

## Per-Asset Stability

Passes both validation and test:

| Model | Config | BTCUSDT | ETHUSDT | EURUSD | ES | GC |
|---|---|---:|---:|---:|---:|---:|
| `catboost_8class_collapsed` | `thr8p0_full_hybrid_exclude_review` | yes | yes | yes | no | no |
| `catboost_8class_collapsed` | `thr3p0_label_conflict_exclude_review` | yes | no | no | no | no |
| `catboost_cleaned_4class` | `thr3p0_label_conflict_exclude_review` | yes | no | yes | no | no |
| `catboost_cleaned_4class` | `thr3p0_full_hybrid_exclude_review` | no | no | yes | no | no |

Interpretation:

- BTCUSDT is the easiest asset to improve and should not be used alone for
  promotion decisions.
- EURUSD benefits from the leading 8-class candidate and some cleaned settings.
- ETHUSDT benefits from the leading 8-class candidate but not the cleaned
  `thr3p0_label_conflict` test split.
- ES and GC require separate diagnosis before expanding roots.

## Leading Candidate Detail

Candidate:

```text
catboost_8class_collapsed / thr8p0_full_hybrid_exclude_review
```

Test deltas:

| Target | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | ECE | Accept |
|---|---:|---:|---:|---:|---:|---:|---|
| BTCUSDT | +0.023418 | +0.032758 | +0.025577 | -0.025577 | -0.008849 | -0.008080 | yes |
| ETHUSDT | +0.005848 | +0.004362 | +0.005465 | -0.005465 | +0.012222 | +0.006850 | yes |
| EURUSD | +0.007624 | +0.006071 | +0.006640 | -0.006640 | +0.006781 | +0.001210 | yes |
| ES | +0.000519 | +0.005194 | -0.001257 | +0.001257 | -0.000588 | -0.007024 | no |
| GC | -0.001421 | +0.002316 | +0.005192 | -0.005192 | +0.014690 | +0.006771 | no |

The ES failure is direction-related: cross-direction error worsened despite
accuracy and F1 being roughly stable. The GC failure is accuracy/logloss-related:
direction improved, but collapsed accuracy decreased and logloss worsened.

## Action Rates

Mean affected training-row rate by config:

| Config | Same-Parent Anomaly Rate | Low-Weight Opposite Rate | Review Exclude Rate | Total Affected Rate |
|---|---:|---:|---:|---:|
| `thr3p0_full_hybrid_exclude_review` | 0.002572 | 0.017298 | 0.002098 | 0.021967 |
| `thr3p0_label_conflict_exclude_review` | 0.001491 | 0.016678 | 0.003797 | 0.021967 |
| `thr8p0_full_hybrid_exclude_review` | 0.007035 | 0.048226 | 0.003293 | 0.058553 |

The leading 8% hybrid setting affects about 5.86% of OOF-scored train rows,
mostly as low-weight opposite-direction rows, not same-parent anomaly leaves.
This is important: the gain is probably coming from suppressing dangerous
opposite-direction rows more than from creating many clean anomaly subclasses.

Review-exclude rates for the leading candidate:

| Target | Review Rate | Highest Review Class |
|---|---:|---|
| BTCUSDT | 0.0036 | `UP_EXPANSION` |
| ETHUSDT | 0.0001 | `DOWN_BALANCED` |
| EURUSD | 0.0025 | `UP_BALANCED` |
| ES | 0.0106 | `DOWN_BALANCED` |
| GC | 0.0058 | `DOWN_BALANCED` |

ES has the highest review rate. That matches the unstable ES direction result
and should be inspected first.

## Class Recall Effects

Leading candidate test recall delta by class:

| Target | DOWN_BAL | DOWN_EXP | UP_BAL | UP_EXP |
|---|---:|---:|---:|---:|
| BTCUSDT | +0.052215 | +0.043080 | -0.008948 | +0.013041 |
| ETHUSDT | -0.010219 | -0.009110 | +0.010306 | +0.030489 |
| EURUSD | +0.033412 | +0.000000 | -0.013341 | +0.000000 |
| ES | +0.039780 | +0.001240 | -0.031130 | -0.000274 |
| GC | +0.043583 | +0.000368 | -0.044334 | +0.001403 |

Key issue:

- ES and GC improve DOWN_BALANCED recall but lose too much UP_BALANCED recall.
- EURUSD also loses UP_BALANCED recall, but direction metrics still improve.
- Expansion classes are barely learned for session assets, especially ES,
  EURUSD, and GC. This likely limits macro F1 and makes anomaly labels less
  informative for expansion subclasses.

## Direction Error Shape

Leading candidate test direction error rates:

| Target | Baseline DOWN->UP | Candidate DOWN->UP | Baseline UP->DOWN | Candidate UP->DOWN |
|---|---:|---:|---:|---:|
| BTCUSDT | 0.479938 | 0.434051 | 0.488990 | 0.482070 |
| ETHUSDT | 0.496351 | 0.503815 | 0.522991 | 0.504890 |
| EURUSD | 0.698582 | 0.671073 | 0.390616 | 0.403688 |
| ES | 0.698630 | 0.669596 | 0.267304 | 0.293427 |
| GC | 0.589596 | 0.540756 | 0.369795 | 0.406560 |

The leading candidate often reduces `DOWN -> UP` errors but can increase
`UP -> DOWN` errors. That is the main per-asset tradeoff to investigate next.

## OOF Label-Quality Diagnostics

For the leading candidate, rows marked as suspicious have much lower
out-of-sample `p_true` and negative normalized margins, as expected:

| Action | Typical Behavior |
|---|---|
| `clean` | `mean_p_true` around 0.28-0.36 and moderate negative margin |
| `low_weight_opposite` | `mean_p_true` around 0.12-0.16 and strongly negative margin |
| `review_exclude` | `mean_p_true` around 0.05-0.08 and very negative margin |
| `same_parent_anomaly` | low `p_true`, same-direction disagreement |

This supports the implementation logic: review rows are genuinely severe OOF
conflicts, not arbitrary noise buckets.

## Conclusions

1. The code path is consistent with the research plan:
   OOF probabilities drive anomaly decisions, opposite-direction conflicts are
   not blindly converted to anomaly leaves, and primary metrics collapse back to
   the original 4-class target.

2. The leading 8-class candidate is worth continued testing:
   it improves median test accuracy, macro F1, direction accuracy, and
   cross-direction error.

3. The gain is not uniformly robust:
   ES and GC need diagnosis before any broad-root execution.

4. Session assets expose a class-learning issue:
   expansion-class recall is near zero for several assets, so future label
   refinement may need class/regime-specific handling, not only anomaly flags.

5. Do not move to all `8 assets x 6 roots` yet.

## Recommended Next Diagnostics

The following additional diagnostics were run after the first representative
matrix.

### ES/GC Focused Sweep

Run:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_es_gc_sweep_20260520
```

Scope:

```text
targets: ES, GC
root: 8h/B
thresholds: 2%, 5%, 8%, 12%
detectors: full_hybrid, label_conflict, cl_normalized_margin
opposite policies: exclude_review, low_weight
models: catboost_cleaned_4class, catboost_8class_collapsed
configs: 24 anomaly configs, 48 model/config arms per target
```

Result:

- ES is fixable by several configs on both validation and test.
- GC improves on test for many configs, but zero tested configs pass GC
  validation.
- No config passes validation and test for both ES and GC individually.

Top ES test config:

```text
catboost_8class_collapsed / thr5p0_full_hybrid_exclude_review
accuracy_delta: +0.019866
macro_f1_delta: +0.014247
direction_accuracy_delta: +0.022517
cross_direction_error_delta: -0.022517
```

Top GC test config:

```text
catboost_8class_collapsed / thr5p0_cl_normalized_margin_low_weight
accuracy_delta: +0.020904
macro_f1_delta: +0.014393
direction_accuracy_delta: +0.026561
cross_direction_error_delta: -0.026561
```

But the GC validation split remains the blocker:

```text
GC validation pass count: 0 / 48 model/config arms
GC test pass count: 35 / 48 model/config arms
```

Interpretation:

- The sweep found stronger ES and GC test candidates, but not a temporally
  stable candidate.
- GC validation and GC test behave differently enough that a test-only win is
  not acceptable.
- More symmetric threshold sweeps are unlikely to solve this.

### Direction-Threshold Diagnostic

A validation-tuned post-hoc direction threshold was tested on saved
probabilities. The rule chooses the UP direction only when:

```text
P(UP_BALANCED) + P(UP_EXPANSION) >= threshold
```

The threshold was selected on validation only and then applied to test.

Result:

- threshold tuning can improve ES direction error;
- threshold tuning generally hurts GC direction or macro F1;
- no post-hoc threshold gives a robust ES+GC improvement;
- macro F1 often degrades because the threshold collapses expansion-class
  behavior even further.

Best pattern:

```text
ES: direction threshold around 0.34-0.39 can improve direction accuracy
GC: validation-selected threshold around 0.30 tends to hurt test direction
```

Interpretation:

- The ES/GC instability is not only an argmax/cost-threshold problem.
- The remaining issue is probably label/regime structure or feature/target
  mismatch for session commodities/index futures during the validation period.

## Updated Decision

The current CatBoost anomaly-label machinery is good enough to continue
research on `8h/B`, but not good enough to promote broadly.

Current status:

| Question | Answer |
|---|---|
| Is implementation correct? | yes |
| Does anomaly relabeling improve some assets? | yes |
| Does it pass representative median gates? | yes for selected configs |
| Does it stabilize every representative asset? | no |
| Are ES and GC solved by broader threshold sweeps? | no |
| Is post-hoc direction thresholding enough? | no |
| Should we expand to all roots now? | no |

Do not spend more time on broad symmetric threshold sweeps until the following
are addressed:

1. ES and GC review-set inspection:
   inspect high-confidence opposite-direction rows, especially
   `DOWN_BALANCED` review rows.

2. GC validation period analysis:
   compare GC validation (`2025-12-10 -> 2026-02-23`) against GC test
   (`2026-02-23 -> 2026-05-06`) for label distribution, volatility/regime
   balance, feature drift, and context-asset availability.

3. Expansion-class support check:
   inspect why ES/EURUSD/GC expansion classes have near-zero recall.

4. Direction-conditioned modeling:
   test a two-stage model where direction is predicted first, then
   balanced/expansion is predicted inside the chosen direction. The flat
   4-class and 8-class formulations are not protecting direction enough for
   ES/GC.

5. Direction-specific anomaly policy:
   implement per-direction or per-class suspicious-row actions, not just
   per-class thresholds. For example, `UP_BALANCED -> DOWN_BALANCED` conflicts
   may need different treatment than `DOWN_BALANCED -> UP_BALANCED` conflicts.

6. Add a diagnostic-only report that groups review rows by:
   target class, predicted class, session position, synthetic-fill flags if
   available, and batch/time period.

Promotion gate remains unchanged:

```text
Do not promote unless validation and test both improve by median gate and
per-asset failures are understood.
```

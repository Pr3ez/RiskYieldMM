# Stage-1 Label-Anomaly 8h/B Research Brief

Date: 2026-05-20

Status: active research brief. This document defines the safe implementation
scope until the label-anomaly method is tested more deeply.

## Current Decision

Use only the `8h/B` root for label-anomaly research until the full method is
validated. Do not run the broad root matrix yet.

Allowed now:

- `8h/B` merged multi-asset Stage-1 datasets;
- flat CatBoost 4-class baseline;
- flat CatBoost 8-class anomaly experiments collapsed back to 4 classes;
- review-set export for high-confidence opposite-direction rows;
- small PyTorch debugging runs only, not full matrix runs.

Blocked for promotion:

- `8h/C`, `24h/B`, `24h/C`, `7d/B`, `7d/C`;
- all-root or all-target production promotion;
- structured PyTorch model as a candidate model.

Reason: the first BTCUSDT `8h/B` CatBoost anomaly result is promising, but it
is one target/root only. The PyTorch prototype improves direction metrics but
fails the main acceptance gate because collapsed 4-class accuracy and
calibration worsen.

## Problem

The current Stage-1 target has four classes:

| Value | Meaning |
|---:|---|
| 0 | `DOWN_BALANCED` |
| 1 | `DOWN_EXPANSION` |
| 2 | `UP_BALANCED` |
| 3 | `UP_EXPANSION` |

The proposed experiment adds parent-conditioned anomaly leaves:

| Value | Meaning |
|---:|---|
| 4 | `DOWN_BALANCED_ANOMALY` |
| 5 | `DOWN_EXPANSION_ANOMALY` |
| 6 | `UP_BALANCED_ANOMALY` |
| 7 | `UP_EXPANSION_ANOMALY` |

The eight-class target is not the main business target. The main target remains
the original four classes. Every 8-class prediction must be collapsed before
primary evaluation:

```text
4 -> 0
5 -> 1
6 -> 2
7 -> 3
```

The method is useful only if it improves the original 4-class prediction
problem and reduces dangerous `DOWN <-> UP` errors.

## Research Position

The literature points toward a conservative data-centric pipeline:

1. use out-of-fold probabilities to score likely label issues;
2. add weak but complementary signals such as temporal inconsistency and
   class-conditional feature-space outlier scores;
3. relabel only same-parent suspicious rows as `k -> k+4`;
4. export high-confidence opposite-direction rows for review, exclusion, or
   downweighting;
5. evaluate only on chronological future data and collapse anomaly labels back
   to four classes for the primary decision.

This is aligned with:

- Confident Learning: label issues should be scored from out-of-sample
  predicted probabilities, not in-sample confidence.
- Co-teaching and DivideMix: noisy-label methods exploit early loss or model
  disagreement, but they require careful training diagnostics before use.
- Time-series noisy-label work: temporal label noise is different from ordinary
  static label noise, so temporal ordering and class-normalized selection matter.
- Calibration research: probability quality matters because the anomaly policy
  uses thresholds and confidence.

Important interpretation:

```text
anomaly class = same parent label, but suspicious/hard/noisy
anomaly class != unknown class
anomaly class != automatically flipped opposite direction
```

If opposite-direction rows are silently mapped into `4..7`, the experiment can
hide exactly the label errors we need to detect.

## Current Implementation

Entrypoint:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py --help
```

Current supported pieces:

- read merged Stage-1 roots from `data/htf_multiasset_merged`;
- chronological train/validation/test split by target batch;
- train-only feature selection;
- expanding out-of-fold probabilities on the train split;
- class-local anomaly thresholds;
- detectors:
  - label conflict from `1 - P(true_class)`;
  - OOF disagreement proxy;
  - temporal direction inconsistency;
  - class-conditional KMeans outlier percentile;
- opposite-direction policies:
  - keep clean;
  - low weight;
  - exclude/review;
- flat CatBoost 8-class anomaly model;
- optional structured PyTorch prototype;
- metrics:
  - collapsed 4-class accuracy;
  - macro F1;
  - direction accuracy;
  - cross-direction error;
  - logloss;
  - multiclass Brier score;
  - ECE;
- review-set export for high-confidence opposite-direction rows.

Test coverage currently validates:

- chronological split ordering;
- OOF folds do not score rows from models trained on those rows;
- train-only feature selection;
- same-direction anomaly mapping `k -> k+4`;
- high-confidence opposite-direction rows go to review/export, not automatic
  anomaly relabeling;
- collapsed 4-class primary metrics;
- review-set schema and duplicate protection.

Validation command:

```bash
python -m pytest tests/test_stage1_label_anomaly_experiment.py -q
```

Latest local result: `5 passed`.

## Local Evidence: BTCUSDT 8h/B

Validated artifact:

```text
target: BTCUSDT
root: 8h/B
context: core-ex-target
rows used: 180,000
selected features: 250
OOF scored train rows: 78,693
review rows: 176
```

Source input manifest:

```text
merged output rows: 413,652
rows dropped by missing context: 974,965
rows dropped by null features: 16,823
duplicate count: 0
null feature count: 0
feature columns: 1,162
time range: 2024-01-23 08:00 UTC -> 2026-05-06 19:59 UTC
```

Accepted CatBoost config:

```text
thr3p0_full_hybrid_exclude_review
threshold: top 3% suspicious rows per original class
detector: full hybrid score
opposite-direction policy: exclude/review
```

Compared with the baseline 4-class CatBoost model:

| Split | Accuracy Delta | Macro F1 Delta | Direction Accuracy Delta | Cross-Direction Error Delta | ECE Delta | Acceptance |
|---|---:|---:|---:|---:|---:|---|
| validation | +0.006806 | +0.009024 | +0.018911 | -0.018911 | -0.002915 | pass |
| test | +0.014838 | +0.019805 | +0.019566 | -0.019566 | -0.002817 | pass |

This is the strongest current evidence that the anomaly-label idea can help,
but it is still one target/root. It is not enough to promote globally.

## CatBoost Ablation Findings

On BTCUSDT `8h/B`, the following CatBoost ablations passed both validation and
test acceptance:

| Config | Interpretation |
|---|---|
| `thr3p0_label_conflict_exclude_review` | simplest OOF label-conflict score won this root |
| `thr8p0_full_hybrid_exclude_review` | wider anomaly rate also passed on this root |
| `thr3p0_full_hybrid_exclude_review` | safest currently documented default |
| `thr3p0_full_hybrid_keep_clean` | review rows kept clean still passed |
| `thr3p0_conflict_temporal_exclude_review` | temporal signal helped without outlier score |

Do not overfit to this ranking yet. The fact that label-conflict alone won this
root does not prove it is best across assets or market sessions. For the next
`8h/B` validation round, carry at least these candidates:

```text
thr3p0_label_conflict_exclude_review
thr3p0_full_hybrid_exclude_review
thr8p0_full_hybrid_exclude_review
```

## PyTorch Prototype Diagnosis

The structured PyTorch prototype is not ready.

BTCUSDT `8h/B`, same `thr3p0_full_hybrid_exclude_review` anomaly labels:

| Split | Accuracy Delta | Macro F1 Delta | Direction Accuracy Delta | Cross-Direction Error Delta | Logloss Delta | Brier Delta | ECE Delta | Acceptance |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| validation | -0.019971 | +0.040451 | +0.009790 | -0.009790 | +0.968664 | +0.219946 | +0.260590 | fail |
| test | -0.018664 | +0.047437 | +0.025878 | -0.025878 | +1.137170 | +0.251883 | +0.277652 | fail |

Interpretation:

- The model learned some direction separation.
- It predicted minority classes more often, so macro F1 rose.
- It became overconfident and badly calibrated.
- It lost collapsed 4-class accuracy, which is a hard fail.

Likely causes:

- no temperature scaling;
- no label smoothing;
- no focal or class-balanced loss for tiny anomaly leaves;
- no early stopping on the primary score;
- no saved training diagnostics by epoch;
- final inference uses only the 8-class leaf head, while direction/regime heads
  only influence training;
- anomaly leaves are very sparse, so the leaf loss can distort probabilities;
- no deep ensemble or calibrated uncertainty yet;
- no self-supervised or sequence-aware representation, only a tabular MLP over
  selected merged features.

Required before another broad PyTorch run:

1. prove a plain 4-class MLP can match or approach the CatBoost baseline on
   BTCUSDT `8h/B`;
2. save train/validation loss curves for leaf, direction, regime, anomaly, and
   total loss;
3. add early stopping on validation primary score;
4. add light label smoothing, starting with `0.02` and `0.05`;
5. add class-balanced or focal loss;
6. add temperature scaling on validation logits and report calibrated test
   metrics;
7. test decision fusion using the direction head, not only the leaf softmax;
8. run only BTCUSDT `8h/B` until these gates pass.

## What Has Not Been Tested Yet

Research items still untested in this repo:

- true Confident Learning joint/noise matrix estimation;
- early-loss noisy-label detection;
- Co-teaching;
- DivideMix;
- CTW;
- Scale-teaching;
- temporal label-noise function modeling;
- forecasting residual anomaly detectors;
- reconstruction or autoencoder anomaly detectors;
- Deep SAD or Multi-Class Deep SVDD;
- real deep ensemble disagreement;
- temperature scaling;
- focal loss and class-balanced focal loss;
- label smoothing;
- TS2Vec, TS-TCC, SimMTM, or SLOTS representation learning;
- change-point detection;
- T-SMOTE or TimeGAN augmentation;
- audited manual review feedback.

These should not be added all at once. The implementation should stay staged so
we know which change improves prediction quality.

## Implementation Guardrails

No leakage:

- all splits must be chronological;
- feature selection must use train data only;
- OOF scores must be produced by models that did not train on the scored row;
- no global anomaly relabel file may be reused inside historical walk-forward
  steps unless filtered by each step's training end;
- review/export rows may be inspected for research, but they must not
  contaminate validation decisions.

No silent target mutation:

- never overwrite `target_4class`;
- anomaly labels live only in experiment artifacts until promoted;
- Stage-1 production remains 4-class unless an explicit experimental target is
  selected.

No metric substitution:

- 8-class accuracy is secondary;
- the main gate is collapsed 4-class performance;
- cross-direction error must decrease or remain stable;
- calibration must not be ignored.

No broad expansion:

- until the method is reliable, run only `8h/B`;
- after BTCUSDT `8h/B`, expand across `8h/B` targets;
- only after all-target `8h/B` results pass should other roots be tested.

## Recommended Next Work

### Phase 1: Freeze Scope To 8h/B

Run CatBoost-only validation on `8h/B`, one target at a time. Start with:

```text
BTCUSDT
ETHUSDT
EURUSD
ES
GC
```

Reason: this covers crypto, FX/session, index futures, and commodity futures
without multiplying cost across six roots.

Build or verify merged roots:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B \
  --plan-only
```

Run CatBoost-only anomaly validation:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B \
  --threshold-pcts 0.03,0.08 \
  --detectors label_conflict,full_hybrid \
  --opposite-policies exclude_review \
  --models catboost \
  --outlier-feature-count 250 \
  --export-review-set
```

Promote only if median results across targets improve:

```text
collapsed_4_accuracy: up
direction_accuracy: up
cross_direction_error: down
macro_f1_4: stable or up
ECE/logloss: not materially worse
```

### Phase 2: PyTorch Debug Loop

Keep this isolated to BTCUSDT `8h/B`.

Minimum new diagnostics:

- epoch-level train/validation metrics;
- loss components by head;
- class prediction distributions;
- confidence histograms;
- reliability bins before and after temperature scaling;
- confusion matrices collapsed to 4 classes;
- direction-only confusion matrix.

Required PyTorch acceptance:

```text
4-class MLP baseline >= 95% of CatBoost primary_score on BTCUSDT 8h/B
structured MLP improves direction without reducing collapsed_4_accuracy
ECE after temperature scaling is close to CatBoost baseline
test primary_score improves over baseline
```

Until this passes, PyTorch remains a research branch only.

### Phase 3: 8h/B Across All 8 Targets

Only after Phase 1 passes the representative set:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py \
  --target-assets core \
  --context-assets core-ex-target \
  --roots 8h/B \
  --threshold-pcts 0.03,0.08 \
  --detectors label_conflict,full_hybrid \
  --opposite-policies exclude_review \
  --models catboost \
  --outlier-feature-count 250 \
  --export-review-set
```

### Phase 4: Other Roots

Only after all-target `8h/B` passes:

```text
8h/C -> same-family sanity check
24h/B -> longer regime, first long-root test
24h/C -> second long-root test
7d/B -> weekly behavior
7d/C -> weekly behavior
```

Do not jump directly to all `8 assets x 6 roots`.

## Acceptance Checklist

A configuration is promotable only if all are true:

- passes on chronological validation and test;
- improves median collapsed 4-class accuracy;
- improves median direction accuracy;
- reduces median cross-direction error;
- macro F1 is stable or higher;
- logloss and ECE are not materially worse;
- review-set rows are exported and duplicate-free;
- anomaly rate remains bounded per original class;
- no context or feature nulls appear in the merged root;
- the same behavior appears on more than one target asset.

Reject if:

- 8-class metrics improve but collapsed 4-class metrics worsen;
- cross-direction error worsens;
- calibration worsens sharply;
- anomaly classes become a generic trash bin;
- the method only works on BTCUSDT.

## Key Local Artifacts

Current accepted CatBoost pilot:

```text
test_output/stage1_label_anomaly_experiments/
  validation_btcusdt_8h_b_corexself_outlier250_20260520/
```

Current failed structured pilot:

```text
test_output/stage1_label_anomaly_experiments/
  validation_btcusdt_8h_b_corexself_structured_outlier250_20260520/
```

Current CatBoost ablation:

```text
test_output/stage1_label_anomaly_experiments/
  ablation_btcusdt_8h_b_corexself_catboost_20260520/
```

Current implementation:

```text
scripts/analysis/htf_stage1_label_anomaly_experiment.py
tests/test_stage1_label_anomaly_experiment.py
```

Original research note:

```text
notebooks/notes/anomaly.md
```

Visual pilot:

```text
notebooks/noise_removal.ipynb
```

## Primary Sources

- Confident Learning: Estimating Uncertainty in Dataset Labels:
  https://arxiv.org/abs/1911.00068
- Co-teaching: Robust Training of Deep Neural Networks with Extremely Noisy
  Labels:
  https://arxiv.org/abs/1804.06872
- DivideMix: Learning with Noisy Labels as Semi-supervised Learning:
  https://arxiv.org/abs/2002.07394
- CTW: Confident Time-Warping for Time-Series Label-Noise Learning:
  https://www.ijcai.org/proceedings/2023/450
- Learning from Time Series under Temporal Label Noise:
  https://arxiv.org/abs/2402.04398
- Scale-teaching: Robust Multi-scale Training for Time Series Classification
  with Noisy Labels:
  https://papers.neurips.cc/paper_files/paper/2023/file/6a6ecedac816a24f92ad1f444b1edcb0-Paper-Conference.pdf
- TS2Vec: Towards Universal Representation of Time Series:
  https://arxiv.org/abs/2106.10466
- On Calibration of Modern Neural Networks:
  https://arxiv.org/abs/1706.04599
- Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles:
  https://arxiv.org/abs/1612.01474
- Focal Loss for Dense Object Detection:
  https://arxiv.org/abs/1708.02002
- Class-Balanced Loss Based on Effective Number of Samples:
  https://arxiv.org/abs/1901.05555

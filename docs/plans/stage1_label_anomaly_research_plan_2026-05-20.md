# Stage-1 Label-Anomaly Research And Experiment Plan

Status: implemented as an experimental runner with the cleaned 4-class arm,
Confident-Learning-style diagnostics, and median matrix gate. The representative
CatBoost `8h/B` validation and the follow-up ES/GC diagnostics are complete.
Broader roots remain blocked because ES/GC are not stable across validation and
test.

Current execution guardrail: use only `8h/B` for label-anomaly validation until
the method is proven across targets. Broader roots and the structured PyTorch
prototype remain blocked from broad execution.

## Resume Here

Latest complete diagnostics:

```text
docs/research/stage1-label-anomaly-8h-b-diagnostics-2026-05-20.md
```

Latest experiment outputs:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_representative_20260520
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_es_gc_sweep_20260520
```

Current best representative candidate:

```text
catboost_8class_collapsed / thr8p0_full_hybrid_exclude_review
```

Current decision:

- the runner and label-anomaly mechanics are implemented and test-covered;
- the method is useful enough to continue `8h/B` research;
- do not promote to all roots or production Stage-1 yet;
- do not spend more time on broad symmetric threshold sweeps now;
- the active blocker is GC validation-period instability and ES/GC
  direction/regime behavior.

Next work should focus on:

1. GC validation-period analysis against the later test period.
2. ES/GC review-set inspection by target class, predicted class, session
   position, and time/batch period.
3. Expansion-class support, because ES/EURUSD/GC expansion recall is weak.
4. Direction-conditioned modeling or a two-stage direction -> regime design.
5. Direction-specific anomaly actions instead of one class-local threshold rule.

Research brief:

```text
docs/research/stage1-label-anomaly-8h-b-research-brief-2026-05-20.md
```

Completed representative-run diagnostics:

```text
docs/research/stage1-label-anomaly-8h-b-diagnostics-2026-05-20.md
```

Implementation reference collected from local notes and external primary docs:

```text
docs/research/stage1-label-anomaly-implementation-reference-2026-05-20.md
```

Additional local research note used for the next implementation pass:

```text
notebooks/notes/20-05-research.md
```

Implemented entrypoint:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py --help
```

The original visual pilot remains in `notebooks/noise_removal.ipynb`.

## Goal

Use the merged all-asset Stage-1 datasets to identify target-label rows that
systematically hurt prediction quality, then test whether isolating or removing
those rows improves out-of-sample Stage-1 results.

The current target surface is:

| Value | Class |
|---:|---|
| 0 | `DOWN_BALANCED` |
| 1 | `DOWN_EXPANSION` |
| 2 | `UP_BALANCED` |
| 3 | `UP_EXPANSION` |

The proposed experimental target is:

| Value | Class |
|---:|---|
| 0 | `DOWN_BALANCED` |
| 1 | `DOWN_EXPANSION` |
| 2 | `UP_BALANCED` |
| 3 | `UP_EXPANSION` |
| 4 | `DOWN_BALANCED_ANOMALY` |
| 5 | `DOWN_EXPANSION_ANOMALY` |
| 6 | `UP_BALANCED_ANOMALY` |
| 7 | `UP_EXPANSION_ANOMALY` |

For evaluation, classes `4..7` must also be collapsed back to `0..3` so the
experiment can be compared against the current Stage-1 objective without
changing the business meaning of up/down and balanced/expansion outcomes.

## Current Implementation

The reusable runner writes derived experiment artifacts under:

```text
test_output/stage1_label_anomaly_experiments/{run_id}/
```

For each target/root it writes metrics, baseline comparisons, anomaly-label
artifacts, reliability bins, optional predictions, review-set exports, and
unit/run manifests. Source merged Stage-1 roots are read-only inputs.

Supported experiment arms:

- baseline 4-class CatBoost;
- cleaned 4-class CatBoost using OOF-derived suspicious/review weights;
- flat 8-class CatBoost anomaly training;
- staged threshold, detector, and opposite-direction policy ablations;
- Confident-Learning-style detector presets based on self-confidence,
  normalized margin, and confidence-weighted entropy;
- optional PyTorch structured MLP prototype with leaf, direction, regime, and
  anomaly heads;
- calibration metrics: logloss, multiclass Brier score, and ECE;
- high-confidence opposite-direction review export.
- run-level `matrix_summary.*` and `matrix_decision.*` artifacts using a
  median-first promotion gate.

The default ablation mode is staged, not full Cartesian, so representative
matrix commands do not accidentally launch hundreds of fits. Use
`--ablation-mode cartesian` only for intentional stress testing.

The runner keeps all derived labels and weights inside `test_output/`; it does
not overwrite source merged Stage-1 roots or `target_4class`.

## Research Takeaways

The strongest match for this problem is label-noise detection, not generic
market anomaly detection.

- Confident Learning estimates label quality from out-of-sample predicted
  probabilities and can rank likely label errors under a class-conditional
  noise assumption. This fits Stage-1 because the runner already stores
  fold-level validation probabilities.
- Noisy labels can preserve apparent accuracy while harming reliability and
  calibration. That matters here because Stage-1 decisions use confidence,
  cross-direction errors, and saved probability payloads, not only accuracy.
- Time-series anomaly detection papers are useful for feature-space anomaly
  scores, but benchmark results are fragile. We should avoid trusting a generic
  anomaly detector unless it improves chronological holdout prediction metrics.
- Financial time-series label-correction research supports adaptive relabeling,
  but the safe v1 should stay simpler: use walk-forward out-of-fold probabilities
  and class-local thresholds before trying neural meta-label correction.
- Meta-labeling in finance is relevant as a control layer: first predict the
  original target, then learn when the original target row is unreliable or
  should be suppressed. The proposed `4..7` classes are a multiclass version of
  that control layer.
- K-means can be useful as a cluster-separability diagnostic and as one
  class-conditional outlier signal. It should not be the sole relabeling rule:
  rare but valid market regimes can be geometrically distant from their class
  center and still be important.
- The next test scope is CatBoost-first and `8h/B` only. The research notes are
  sufficient for this phase, but not sufficient to justify running CTW,
  DivideMix, Co-teaching, reconstruction models, or broad PyTorch matrices yet.
- The structured PyTorch branch stays blocked until a plain 4-class MLP gets
  close to CatBoost on BTCUSDT `8h/B` and calibration/diagnostics are added.

Sources:

- Northcutt, Jiang, Chuang, "Confident Learning: Estimating Uncertainty in
  Dataset Labels", JAIR/arXiv 1911.00068:
  https://arxiv.org/abs/1911.00068
- Olmin and Lindsten, "Robustness and Reliability When Training With Noisy
  Labels", AISTATS/PMLR 2022:
  https://proceedings.mlr.press/v151/olmin22a.html
- Carmona et al., "Neural Contextual Anomaly Detection for Time Series",
  arXiv 2107.07702:
  https://arxiv.org/abs/2107.07702
- Wu and Keogh, "Current Time Series Anomaly Detection Benchmarks are Flawed
  and are Creating the Illusion of Progress", arXiv 2009.13807:
  https://arxiv.org/abs/2009.13807
- Yang et al., "Multi-task Meta Label Correction for Time Series Prediction",
  arXiv 2303.08103:
  https://arxiv.org/abs/2303.08103
- Joubert, "Meta-Labeling: Theory and Framework", SSRN 4032018:
  https://ssrn.com/abstract=4032018

## Safe Experimental Design

Do not overwrite `target_4class`. Add derived experimental labels only.

The implemented runner follows this rule: derived `target_8class_anomaly`
labels are written only into experiment outputs and never back into the source
merged Stage-1 roots.

For each target asset and root:

1. Build the merged all-core-context dataset:

   ```bash
   python scripts/analysis/htf_stage1_regime_family_walkforward.py \
     --build-merged-dataset \
     --target-assets BTCUSDT \
     --context-assets core-ex-target \
     --roots 8h/B \
     --plan-only
   ```

2. Run a baseline Stage-1 window large enough to produce validation prediction
   payloads:

   ```bash
   python scripts/analysis/htf_stage1_regime_family_walkforward.py \
     --build-merged-dataset \
     --target-assets BTCUSDT \
     --context-assets core-ex-target \
     --roots 8h/B \
     --n-steps 25 \
     --resume-mode skip_completed \
     --runtime-mode routine
   ```

3. Build label-quality scores from `stage1_val_predictions.parquet` only:

   ```text
   p_true = predicted probability assigned to the observed target_4class
   margin = p_true - max(probability assigned to any other class)
   prediction_disagrees = y_pred != y_true
   anomaly_score = weighted combination of low p_true, negative margin, and
                   repeated disagreement across combos/folds
   ```

   In the standalone runner this is implemented as expanding OOF predictions
   inside the chronological train split, so the runner can work directly from
   merged Stage-1 feature/label roots without requiring a prior Stage-1 run.

4. Run cluster diagnostics on the same chronological split:

   ```text
   k=4 -> check whether selected features separate target_4class
   k=2 -> check whether selected features separate DOWN vs UP direction
   ```

   Feature subsets should be selected on train data only, then scored on later
   validation/holdout batches using adjusted Rand index, normalized mutual
   information, cluster-to-label mapped accuracy, and cross-direction error.

5. Add class-conditional K-means distance percentile as one noise signal, then
   threshold anomalies per original target class, asset, and root. Class-local
   thresholds are required so rare classes are not marked anomalous only because
   they are rare.

6. Generate an experimental label root:

   ```text
   target_8class_anomaly =
     target_4class + 4 if row is class-local anomaly
     target_4class otherwise
   target_is_anomaly = boolean flag
   target_4class_original = original label
   anomaly_score = score used for audit
   ```

7. Compare three arms on untouched chronological holdout batches:

   | Arm | Training target | Evaluation target |
   |---|---|---|
   | baseline | `target_4class` | `target_4class` |
   | cleaned | `target_4class`, anomalies removed or down-weighted | `target_4class` |
   | split-class | `target_8class_anomaly` | both 8-class and collapsed 4-class |

## Immediate 8h/B Validation Command

Build or verify the `8h/B` merged roots before running the next validation
matrix:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B \
  --plan-only
```

Run the staged CatBoost-only anomaly validation:

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

For a fast local smoke, use one already-built root:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --threshold-pcts 0.03 \
  --models catboost \
  --ablation-mode primary-only \
  --max-rows 30000 \
  --max-features 80 \
  --catboost-iterations 40 \
  --export-review-set
```

## Completed Representative 8h/B Validation

Run:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_representative_20260520
```

Scope:

```text
targets: BTCUSDT, ETHUSDT, EURUSD, ES, GC
root: 8h/B
models: baseline_4class, catboost_cleaned_4class, catboost_8class_collapsed
rows per target: 180,000
selected features per target: 250
OOF-scored train rows per target: 78,693
```

Merged-root validation before the run:

| Target | Output Rows | Dropped Missing Context | Duplicate Count | Null Feature Count |
|---|---:|---:|---:|---:|
| BTCUSDT | 413,652 | 974,965 | 0 | 0 |
| ETHUSDT | 413,652 | 922,405 | 0 | 0 |
| EURUSD | 413,652 | 559,538 | 0 | 0 |
| ES | 413,652 | 655 | 0 | 0 |
| GC | 413,652 | 556,026 | 0 | 0 |

All required experiment artifacts were produced, including metrics,
comparisons, action summaries, anomaly labels, label-quality scores,
Confident-Learning diagnostics, reliability bins, predictions, review exports,
and matrix decision files. Review exports were duplicate-free on
`timestamp,batch_id`.

Configs that passed the median gate on both validation and test:

| Model | Config | Test Accuracy Delta | Test Macro F1 Delta | Test Direction Delta | Test Cross-Direction Delta | Test Pass Rate |
|---|---|---:|---:|---:|---:|---:|
| `catboost_8class_collapsed` | `thr8p0_full_hybrid_exclude_review` | +0.005848 | +0.005194 | +0.005465 | -0.005465 | 0.60 |
| `catboost_cleaned_4class` | `thr3p0_label_conflict_exclude_review` | +0.001503 | -0.000418 | +0.001530 | -0.001530 | 0.40 |

Interpretation:

- The anomaly approach is validated enough for continued `8h/B` research.
- The best current candidate is the split-class 8-class setup with
  `thr8p0_full_hybrid_exclude_review`, because it passed both validation and
  test median gates with stronger test deltas and higher test pass rate.
- The cleaned 4-class `thr3p0_label_conflict_exclude_review` setup is useful as
  a conservative baseline, but its lower test pass rate means it should not be
  promoted alone.
- The result is not strong enough to promote anomaly labeling across all
  `8 assets x 6 roots`. Some asset/config pairs still fail individually, so the
  next step is careful per-asset diagnostics on `8h/B`, not broader execution.

## Implemented Test Additions And Remaining Matrix Work

The two research notes are enough to implement the next set of tests for the
CatBoost-first `8h/B` phase. They are not enough to promote every method in the
research survey. The implementation now includes the smallest missing pieces
needed to test the current hypothesis cleanly.

### Phase 1: Runner Gaps

Implemented: cleaned 4-class CatBoost arm.

Behavior:

- use the same anomaly decisions produced from train-only OOF scores;
- train a 4-class CatBoost model on `target_4class`;
- either exclude `review_exclude` rows or downweight suspicious rows according
  to the configured policy;
- do not alter validation/test labels;
- evaluate on the same collapsed 4-class metrics as the baseline and split-class
  arms.

Implemented: Confident-Learning-style score and diagnostic arms.

Behavior:

- derive a class-normalized label-quality score from OOF parent probabilities;
- keep implementation dependency-light unless `cleanlab` is explicitly added
  later;
- report estimated noisy-vs-predicted parent count matrix as diagnostics;
- continue using class-local thresholds and the same opposite-direction review
  rule.

Implemented: median-first representative-matrix gating.

Behavior:

- aggregate per-target deltas across the representative `8h/B` asset panel;
- report median and pass rate for accuracy, macro F1, direction accuracy,
  cross-direction error, logloss, Brier, ECE, and primary score;
- reject configs that win on one target but fail the median panel.

### Phase 2: Tests Added Before Running The Matrix

Implemented unit tests now cover:

- cleaned 4-class sample weights downweight suspicious rows and remove review
  rows without changing `target_4class`;
- train-only feature selection and chronological OOF split ordering;
- anomaly decisions are derived from scored train rows, with validation/test
  evaluation kept separate by the runner split contract;
- high-confidence opposite-direction rows remain review/exclude rows, not
  anomaly leaves;
- class-local thresholding produces bounded anomaly decisions per original
  class in the decision-table tests;
- Confident-Learning-style diagnostic matrix uses only OOF probabilities;
- matrix gating fails when only one target improves and the median target does
  not;
- generated review sets remain duplicate-free on `timestamp,batch_id`;
- all primary metrics are computed after collapsing `4..7 -> 0..3`.

Integration checks still to run before promotion:

- smoke run for BTCUSDT `8h/B` with baseline, cleaned, and split-class CatBoost
  arms on a small `--max-rows` sample;
- run-plan check that the representative command resolves only `8h/B`;
- artifact schema check for metrics, comparison, action summary, anomaly labels,
  reliability bins, review set, and matrix summary;
- no PyTorch model is launched when `--models catboost` is used.

Validation commands after implementation:

```bash
python -m pytest tests/test_stage1_label_anomaly_experiment.py -q
python -m py_compile scripts/analysis/htf_stage1_label_anomaly_experiment.py
git diff --check
```

### Phase 3: Experiment Gates

The representative `8h/B` panel has run once. Use the completed run above as
the baseline for next diagnostics.

Promote a CatBoost anomaly setup only if the median across
`BTCUSDT,ETHUSDT,EURUSD,ES,GC` satisfies:

```text
collapsed_4_accuracy: up
macro_f1_4: stable or up
direction_accuracy: up
cross_direction_error: down
logloss/ece: not materially worse
review/export rows: present and duplicate-free
```

Reject a setup if:

```text
it only wins on BTCUSDT,
8-class utility improves but collapsed 4-class metrics worsen,
cross-direction error worsens,
calibration worsens sharply,
or anomaly leaves become a generic trash bin.
```

### Phase 4: PyTorch Blocker Resolution

Do not run PyTorch on the representative matrix yet.

Before any broader PyTorch test:

- add a plain 4-class MLP baseline on BTCUSDT `8h/B`;
- save epoch-level loss and metric curves;
- add temperature scaling diagnostics;
- test mild label smoothing `0.02` and `0.05`;
- test class-balanced or focal loss;
- compare calibrated collapsed 4-class metrics against CatBoost.

PyTorch remains blocked unless:

```text
plain 4-class MLP approaches CatBoost primary_score,
structured MLP does not reduce collapsed_4_accuracy,
and calibrated ECE/logloss are close to CatBoost.
```

## Local Validation Evidence

Validated on the already-built merged root:

```text
target: BTCUSDT
root: 8h/B
context: core-ex-target
rows used: 180,000
selected features: 250
OOF scored train rows: 78,693
```

Accepted notebook-equivalent config:

```text
thr3p0_full_hybrid_exclude_review
```

Compared with the baseline 4-class CatBoost model:

| Split | Accuracy Delta | Macro F1 Delta | Direction Accuracy Delta | Cross-Direction Error Delta |
|---|---:|---:|---:|---:|
| validation | +0.006806 | +0.009024 | +0.018911 | -0.018911 |
| test | +0.014838 | +0.019805 | +0.019566 | -0.019566 |

The first staged CatBoost ablation on this root found five configs passing both
validation and test. Ranked by mean primary score:

1. `thr3p0_label_conflict_exclude_review`
2. `thr8p0_full_hybrid_exclude_review`
3. `thr3p0_full_hybrid_exclude_review`
4. `thr3p0_full_hybrid_keep_clean`
5. `thr3p0_conflict_temporal_exclude_review`

The structured MLP prototype improved direction metrics but failed acceptance
because collapsed 4-class accuracy and calibration worsened. It should remain
experimental until tuned and validated on the representative matrix.

## Leakage Rules

The main risk is future leakage from global anomaly labels.

Safe rule:

```text
For prediction step T, a row may only use anomaly scores produced by models
whose training/validation windows ended before or at T's training end.
```

Therefore v1 should not create one global static relabel file and use it in all
historical walk-forward steps. It should either:

- build anomaly labels inside each Stage-1 step from that step's historical
  validation payloads, or
- store score artifacts with `score_generated_train_end_batch` and filter them
  by the current step.

Offline research may use a fixed discovery period followed by a later untouched
holdout period, but the discovery period and holdout period must be separated
before looking at results.

## Acceptance Metrics

An anomaly relabeling method is only useful if it improves future prediction
quality after collapsing anomaly classes back to the original four classes.

Primary metrics:

- collapsed 4-class macro F1
- collapsed 4-class logloss
- directional accuracy: down classes `0,1,4,5` vs up classes `2,3,6,7`
- cross-direction error

Secondary diagnostics:

- anomaly rate by asset/root/original class
- class distribution before and after relabeling
- feature importance of anomaly classes
- whether anomaly rows cluster around synthetic fills, session boundaries, or
  known sparse batch spans
- calibration of probabilities on normal vs anomaly rows

Minimum acceptance:

```text
For at least one target/root pilot:
- collapsed 4-class macro F1 improves on holdout,
- cross-direction error does not worsen,
- anomaly rate remains bounded per class,
- results persist across at least two chronological holdout windows.
```

## Implementation Status

Implemented:

- read-only merged-root analyzer and OOF label-quality scoring;
- derived anomaly-label artifact writer under `test_output/`;
- cleaned 4-class CatBoost arm using `sample_weight`;
- Confident-Learning-style score columns and detector presets;
- per-config label-quality parquet and diagnostic JSON artifacts;
- class-local K-means outlier scoring;
- staged threshold, detector, and opposite-direction policy ablations;
- flat CatBoost 8-class experiment path;
- structured MLP prototype path;
- review/export handling for high-confidence opposite-direction rows;
- run-level median decision artifacts: `matrix_decision.csv/json`;
- tests for chronological splits, train-only feature selection, anomaly mapping,
  cleaned weights, CL-style diagnostics, matrix gating, collapsed metrics, and
  review-set export.

Still deferred:

- direct Stage-1 production support for `--target-col target_8class_anomaly`;
- per-step online anomaly labels filtered by each walk-forward train end;
- full representative matrix execution for roots beyond `8h/B`;
- promotion to all `8 assets x 6 roots`, blocked until GC validation-period
  instability and ES/GC direction/regime failures are understood.

# Stage-1 Label-Anomaly Research And Experiment Plan

Status: implemented as an experimental runner; representative-matrix validation
is still pending.

Current execution guardrail: use only `8h/B` for label-anomaly validation until
the method is proven across targets. Broader roots and the structured PyTorch
prototype remain blocked from broad execution.

Research brief:

```text
docs/research/stage1-label-anomaly-8h-b-research-brief-2026-05-20.md
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
- flat 8-class CatBoost anomaly training;
- staged threshold, detector, and opposite-direction policy ablations;
- optional PyTorch structured MLP prototype with leaf, direction, regime, and
  anomaly heads;
- calibration metrics: logloss, multiclass Brier score, and ECE;
- high-confidence opposite-direction review export.

The default ablation mode is staged, not full Cartesian, so representative
matrix commands do not accidentally launch hundreds of fits. Use
`--ablation-mode cartesian` only for intentional stress testing.

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

## Representative Matrix Command

Build merged roots before running the validation matrix:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B 8h/C 24h/B 7d/B \
  --plan-only
```

Run the staged anomaly validation:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B 8h/C 24h/B 7d/B \
  --threshold-pcts 0.02,0.03,0.05,0.08 \
  --models catboost,structured \
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
- class-local K-means outlier scoring;
- staged threshold, detector, and opposite-direction policy ablations;
- flat CatBoost 8-class experiment path;
- structured MLP prototype path;
- review/export handling for high-confidence opposite-direction rows;
- tests for chronological splits, train-only feature selection, anomaly mapping,
  collapsed metrics, and review-set export.

Still deferred:

- direct Stage-1 production support for `--target-col target_8class_anomaly`;
- per-step online anomaly labels filtered by each walk-forward train end;
- full representative matrix execution;
- promotion to all `8 assets x 6 roots`, pending representative-matrix results.

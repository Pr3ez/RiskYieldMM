# Stage-1 Label-Anomaly Implementation Reference

Date: 2026-05-20

Status: implementation reference for the `8h/B`-only CatBoost validation
phase. The runner now implements the cleaned 4-class arm,
Confident-Learning-style diagnostics, and median matrix gate described below;
the representative-matrix execution and follow-up ES/GC diagnostics have
completed. The implementation is usable for continued `8h/B` research, but not
for broad-root promotion yet.

## Scope Decision

The available local notes are enough to implement the next test phase:

- `notebooks/notes/anomaly.md`
- `notebooks/notes/20-05-research.md`
- `docs/research/stage1-label-anomaly-8h-b-research-brief-2026-05-20.md`
- `docs/plans/stage1_label_anomaly_research_plan_2026-05-20.md`

They are not enough to promote every research method yet. The next code work
should stay limited to:

```text
root: 8h/B only
models: CatBoost only
assets: BTCUSDT, ETHUSDT, EURUSD, ES, GC
arms: baseline 4-class, cleaned 4-class, split-class 8-class collapsed to 4
```

PyTorch, CTW, DivideMix, Co-teaching, reconstruction models, and self-supervised
sequence representation methods remain deferred.

## Source Evidence

| Source | Implementation consequence |
|---|---|
| Confident Learning paper, arXiv 1911.00068 | Label-quality scoring should use out-of-sample predicted probabilities and class-conditional noise assumptions, not in-sample confidence. |
| cleanlab `filter.find_label_issues` docs | `labels` must be integer classes `0..K-1`; `pred_probs` is `N x K`; output can be mask or ranked indices; class-local pruning controls matter. |
| cleanlab `count.compute_confident_joint` docs | Confident-joint/noise diagnostics assume out-of-sample holdout probabilities; if probabilities are not out-of-sample, overfitting can corrupt estimates. |
| cleanlab `rank.get_label_quality_scores` docs | Useful label-quality scores are `self_confidence`, `normalized_margin`, and `confidence_weighted_entropy`; lower quality means more suspicious. |
| cleanlab tabular tutorial | Cleaned-model comparison is valid: identify issues from out-of-sample probabilities, then train on the remaining clean subset and evaluate on untouched holdout. |
| CatBoost `fit` docs | `sample_weight` is supported directly, so cleaned 4-class experiments can exclude or downweight suspicious training rows without mutating labels. |
| CatBoost multiclass docs | `MultiClass` and weighted metrics are supported; keep `loss_function="MultiClass"` for 4-class and 8-class arms. |
| scikit-learn `TimeSeriesSplit` docs | Standard random CV is inappropriate for time-ordered data; train/test order must be preserved and train folds should accumulate past data only. |
| scikit-learn `calibration_curve` docs | Reliability bins should report predicted probability vs observed frequency; for multiclass, continue using our confidence-bin ECE implementation on max collapsed probability. |
| Guo et al. calibration paper | PyTorch remains blocked until temperature scaling and calibration diagnostics are added. |
| Focal Loss paper | Later PyTorch work can use focal modulation to focus on hard examples and reduce easy-example domination. |
| Class-Balanced Loss paper | Later PyTorch work can use effective-number reweighting for rare anomaly leaves. |
| Generalized Cross Entropy paper | Later PyTorch work can test robust losses after simpler calibration and imbalance controls. |

Primary source links:

- https://arxiv.org/abs/1911.00068
- https://docs.cleanlab.ai/v2.0.0/cleanlab/filter.html
- https://docs.cleanlab.ai/v2.0.0/cleanlab/count.html
- https://docs.cleanlab.ai/v2.4.0/cleanlab/rank.html
- https://docs.cleanlab.ai/v2.0.0/tutorials/tabular.html
- https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier_fit
- https://catboost.ai/docs/en/concepts/loss-functions-multiclassification
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://scikit-learn.org/stable/modules/generated/sklearn.calibration.calibration_curve.html
- https://arxiv.org/abs/1706.04599
- https://arxiv.org/abs/1708.02002
- https://arxiv.org/abs/1901.05555
- https://arxiv.org/abs/1805.07836

## Current Runner Map

Main file:

```text
scripts/analysis/htf_stage1_label_anomaly_experiment.py
```

Existing pieces to reuse:

- `assign_chronological_splits`
- `make_expanding_oof_folds`
- `select_train_variance_features`
- `run_oof_predictions`
- `build_base_noise_table`
- `apply_detector_score`
- `apply_anomaly_decisions`
- `attach_anomaly_decisions`
- `train_model`
- `run_baseline`
- `run_catboost_anomaly_model`
- `compare_to_baseline`
- `run_unit`

Existing test file:

```text
tests/test_stage1_label_anomaly_experiment.py
```

Existing safety checks:

- chronological train/validation/test split;
- expanding OOF folds;
- train-only feature selection;
- same-direction suspicious rows map to `k+4`;
- high-confidence opposite-direction rows go to review/exclude;
- collapsed `4..7 -> 0..3` metrics are primary;
- review set duplicate check on `timestamp,batch_id`.

## Implementation Item 1: Cleaned 4-Class Arm

Add a model arm between baseline and split-class 8-class.

Recommended model name:

```text
catboost_cleaned_4class
```

Behavior:

- use the same OOF-derived `training_action` values already created for the
  split-class arm;
- keep `target_4class` as the training target;
- do not write back to source merged roots;
- train only on train split rows;
- do not touch validation/test labels;
- evaluate with the same `compute_eval_metrics` function.

Recommended cleaned weights:

| `training_action` | Default cleaned 4-class weight |
|---|---:|
| `clean` | `1.0` |
| `clean_no_oof` | `1.0` |
| `same_parent_anomaly` | `0.35` |
| `low_weight_opposite` | `0.35` |
| `opposite_low_weight` | `0.35` |
| `opposite_keep_clean` | `1.0` |
| `review_exclude` | `0.0` |

Add CLI knobs:

```text
--cleaned-suspicious-weight 0.35
--cleaned-review-weight 0.0
```

The cleaned arm should filter rows with weight `0.0` before fitting, then pass
the remaining weights to CatBoost via `sample_weight`.

Output requirements:

- include cleaned rows in `metrics.csv`, `metrics.parquet`, and
  `comparison_to_baseline`;
- include model name, config id, detector, threshold, and opposite policy;
- include cleaned-action summary fields in `action_summary`;
- if predictions are saved, use the same prediction artifact schema as baseline
  and split-class models.

## Implementation Item 2: Confident-Learning-Style Diagnostics

Do not add a hard `cleanlab` dependency in the first pass. Implement a
dependency-light diagnostic first, then optionally use `cleanlab` if it is
installed.

Required columns from OOF probabilities:

```text
p_true
max_other_prob
normalized_margin = p_true - max_other_prob
self_confidence_quality = p_true
label_conflict_score = 1 - p_true
confidence_weighted_entropy_score
```

Recommended detector additions:

```text
cl_self_confidence
cl_normalized_margin
cl_confidence_weighted_entropy
```

Implementation detail:

- rank scores within each original class, as current detectors do;
- lower quality means more suspicious;
- convert quality to suspiciousness before ranking where needed;
- keep the current opposite-direction review rule unchanged.

Diagnostic matrices:

```text
argmax_confusion_observed_vs_oof_pred
confident_joint_like_counts
noise_rate_by_observed_class
review_rate_by_observed_class
anomaly_rate_by_observed_class
```

If `cleanlab` is available, optional diagnostics may call:

```python
from cleanlab.count import compute_confident_joint
from cleanlab.rank import get_label_quality_scores
```

But the experiment must still run without `cleanlab`.

## Implementation Item 3: Median-First Matrix Gate

The current matrix summary is not strict enough for promotion. Add a second
summary artifact:

```text
matrix_decision.csv
matrix_decision.json
```

Group by:

```text
model
config_id
split
```

Report:

```text
units
median_accuracy_delta
median_macro_f1_delta
median_direction_accuracy_delta
median_cross_direction_error_delta
median_logloss_delta
median_brier_delta
median_ece_delta
median_primary_score_delta
pass_rate
passes_median_gate
```

Median gate:

```text
median_accuracy_delta > 0
median_macro_f1_delta >= -0.002
median_direction_accuracy_delta > 0
median_cross_direction_error_delta < 0
median_ece_delta <= 0.01
median_logloss_delta <= 0.02
```

This gate is intentionally stricter than a single-target pass because BTCUSDT
alone is not enough evidence.

## Implementation Item 4: Artifact Contract

Every target/root directory should produce:

```text
manifest.json
metrics.csv
metrics.parquet
action_summary.csv
action_summary.parquet
oof_fold_summary.parquet
selected_features.json
selected_feature_variance.csv
reliability_bins.parquet
anomaly_labels/{config_id}.parquet
review_sets/{config_id}_review_set.parquet
review_sets/{config_id}_review_set.csv
```

If `--save-predictions` is used:

```text
predictions.parquet
```

New diagnostic artifacts:

```text
label_quality_scores/{config_id}.parquet
confident_learning_diagnostics/{config_id}.json
confident_learning_diagnostics/{config_id}_observed_vs_pred.csv
confident_learning_diagnostics/{config_id}_confident_joint.csv
confident_learning_diagnostics/{config_id}_class_rates.csv
```

Run-level artifacts should produce:

```text
metrics.csv
metrics.parquet
comparison_to_baseline.csv
comparison_to_baseline.parquet
matrix_summary.csv
matrix_summary.json
matrix_decision.csv
matrix_decision.json
```

The source merged Stage-1 root remains read-only.

## Implementation Item 5: Test Additions

Add unit tests before running the representative matrix:

- cleaned arm keeps `target_4class` unchanged;
- cleaned arm uses `sample_weight` and filters zero-weight rows;
- cleaned arm never uses validation/test rows for threshold decisions;
- same OOF decisions can drive both cleaned and split-class arms;
- Confident-Learning-style quality scores are computed from OOF probabilities
  only;
- quality scores are class-local ranked before thresholding;
- confident-joint-like matrix shape is `4 x 4`;
- median gate fails when only one target improves but the median does not;
- median gate passes only when all required median deltas satisfy the gate;
- artifact schema includes cleaned, split-class, and baseline rows;
- `--models catboost` does not run structured PyTorch.

Recommended test command:

```bash
python -m pytest tests/test_stage1_label_anomaly_experiment.py -q
```

Recommended compile/check commands:

```bash
python -m py_compile scripts/analysis/htf_stage1_label_anomaly_experiment.py
git diff --check
```

## Implementation Item 6: Representative 8h/B Run

Build or verify merged roots:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B \
  --plan-only
```

Representative command used after cleaned arm and tests were implemented:

```bash
python scripts/analysis/htf_stage1_label_anomaly_experiment.py \
  --target-assets BTCUSDT,ETHUSDT,EURUSD,ES,GC \
  --context-assets core-ex-target \
  --roots 8h/B \
  --threshold-pcts 0.03,0.08 \
  --detectors label_conflict,full_hybrid,cl_normalized_margin \
  --opposite-policies exclude_review \
  --models catboost \
  --outlier-feature-count 250 \
  --export-review-set
```

Decision rule:

- compare baseline vs cleaned vs split-class;
- promote only if median future holdout metrics improve across the panel;
- reject configs that only work on BTCUSDT.

Completed run:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_representative_20260520
```

Configs that passed the median gate on both validation and test:

| Model | Config | Test Accuracy Delta | Test Macro F1 Delta | Test Direction Delta | Test Cross-Direction Delta | Test Pass Rate |
|---|---|---:|---:|---:|---:|---:|
| `catboost_8class_collapsed` | `thr8p0_full_hybrid_exclude_review` | +0.005848 | +0.005194 | +0.005465 | -0.005465 | 0.60 |
| `catboost_cleaned_4class` | `thr3p0_label_conflict_exclude_review` | +0.001503 | -0.000418 | +0.001530 | -0.001530 | 0.40 |

Current decision:

- continue `8h/B` diagnostics;
- treat `thr8p0_full_hybrid_exclude_review` split-class training as the leading
  candidate;
- keep cleaned 4-class as a conservative comparison arm;
- do not promote to all roots yet.

Follow-up ES/GC diagnostics:

```text
test_output/stage1_label_anomaly_experiments/stage1_label_anomaly_8hb_es_gc_sweep_20260520
docs/research/stage1-label-anomaly-8h-b-diagnostics-2026-05-20.md
```

Result:

- ES can be improved by several settings on both validation and test.
- GC improves on test for many settings, but no tested setting passes GC
  validation.
- Direction-threshold tuning does not solve the ES/GC instability.
- More broad symmetric threshold sweeps are not the next best use of time.

Next implementation work should target GC validation-period diagnostics,
review-row grouping, expansion-class support, and direction-conditioned
modeling before any all-root run.

## PyTorch Blocker Reference

Do not run PyTorch on the representative panel yet.

Required before PyTorch broad testing:

- add plain 4-class MLP baseline on BTCUSDT `8h/B`;
- add epoch-level train/validation loss curves;
- save leaf, direction, regime, anomaly, and total loss components;
- add temperature scaling;
- test label smoothing `0.02` and `0.05`;
- test effective-number class-balanced weights;
- test focal loss;
- compare calibrated collapsed 4-class metrics against CatBoost.

PyTorch pass gate:

```text
plain 4-class MLP approaches CatBoost primary_score
structured MLP does not reduce collapsed_4_accuracy
calibrated ECE/logloss are close to CatBoost
```

## Do Not Implement Yet

The following are research-backed but not next-phase requirements:

- Co-teaching;
- DivideMix;
- CTW;
- Scale-teaching;
- temporal label-noise function modeling;
- reconstruction or autoencoder anomaly detectors;
- Deep SAD or Multi-Class Deep SVDD;
- TS2Vec, TS-TCC, SimMTM, SLOTS;
- T-SMOTE or TimeGAN;
- broad roots beyond `8h/B`.

These methods should be revisited only after the CatBoost `8h/B` path is stable
across the representative assets, including ES and GC validation windows.

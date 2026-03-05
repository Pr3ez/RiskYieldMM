# 1m/target_4class: Next Implementation Research (High-Accuracy + Higher Coverage)

Date: 2026-02-28
Scope: post-run analysis across existing 3500/500 outputs + research-backed next step selection.

## Current empirical constraints from collected data

Using `per_config_best_probabilities.parquet` from
`prediction_analysis/one_minute_target4class_pattern_outputs/20260228_004427_prod_full3500_cfg24_step1_groupwise_ltr_v2`:

- Holdout batches: 500
- Batches with at least one config `dir_acc >= 0.70`: **413 / 500 (82.6%)**
- If an oracle picked the highest-`dir_acc` config each batch:
  - coverage: **100%**
  - directional accuracy: **87.4%**
- If oracle activates only when best config has `dir_acc >= 0.70`:
  - coverage: **82.6%**
  - directional accuracy: **93.46%**

Interpretation: signal exists. The bottleneck is **ranking/selection quality**, not the absence of high-quality candidates.

## Why prior variants plateaued

Across recent production runs in `prediction_analysis/one_minute_target4class_pattern_outputs`:

- Best observed holdout safe-accuracy >= 0.70 was only at low coverage (~5.4%).
- Coverage increases consistently pushed opposite-FP up and safe-accuracy down.

This is consistent with selective prediction literature: post-hoc threshold tuning cannot recover performance if ranking confidence is weak.

## Research-backed next implementation

Implement **Set-Recall Selective Router (SRSR)** with explicit training-time objectives:

1. **Groupwise top-K set recall objective**
   - Target is not "best single config" but "recover at least one good config in top-K".
   - Optimize listwise/pairwise ranking for per-batch groups of 24 configs.

2. **Set-level direction utility head**
   - Build set features from top-K (e.g., vote margin, direction entropy, weighted margin, agreement structure).
   - Predict directional utility of the final set-vote, not only per-config hit probability.

3. **Constrained selective gate with rolling conformal calibration**
   - Apply class-conditional + shift-weighted conformal calibration to gate score.
   - Enforce constraints in model selection:
     - min safe-accuracy (>=0.70)
     - max opposite-FP rates
     - min active coverage floor (anti-collapse)

4. **Coverage regularization during train-time model selection**
   - Penalize candidate models that achieve high accuracy only by collapsing active set.

## Why this is the next best step

- Current data shows abundant latent high-accuracy opportunities (82.6% of holdout batches have at least one >=0.70 config).
- The critical task is **retrieval + set decision**, not pure single-action calibration.
- Literature supports this structure: ranking for retrieval, selective prediction for abstention, and conformal risk control for valid risk bounds under shift.

## Key references

- Selective classification risk/coverage framework:
  - Geifman & El-Yaniv (2017), *Selective Classification for Deep Neural Networks* (arXiv:1705.08500)
- Train-time abstention with explicit coverage control:
  - Geifman & El-Yaniv (2019), *SelectiveNet* (arXiv:1901.09192)
- Reject-option training with reservation utility:
  - Liu et al. (2019), *Deep Gamblers: Learning to Abstain with Portfolio Theory* (arXiv:1905.09501)
- Distribution-free risk control for selective systems:
  - Angelopoulos et al. (2022), *Conformal Risk Control* (arXiv:2208.02814)
- Adaptive conformal under distribution shift:
  - Gibbs & Candès (2021), *Adaptive Conformal Inference Under Distribution Shift* (arXiv:2106.00170)
- Conformal under covariate shift weighting:
  - Tibshirani et al. (2019), *Conformal Prediction Under Covariate Shift* (arXiv:1904.06019)
- Learning-to-rank objective family for top-k retrieval:
  - Wang et al. (2018), *The LambdaLoss Framework for Ranking Metric Optimization* (CIKM)

## Immediate execution plan (implementation order)

1. Add groupwise set-recall labels/targets and ranking loss hooks.
2. Add set-level direction utility head and top-K set feature builder.
3. Add constrained gate selection with coverage floor in training-time candidate selection.
4. Run full `3500/500` benchmark and compare against:
   - `20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1`
   - `20260228_004427_prod_full3500_cfg24_step1_groupwise_ltr_v2`


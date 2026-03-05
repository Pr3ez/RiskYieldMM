# RIS-91: Next Methods to Keep `>0.70` Safety and Raise Coverage

## Current empirical diagnosis (from our runs)

- Best safety run remains:
  - `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1`
  - holdout: `safe_acc=0.7037`, `coverage=0.054`, `opp_active=0.2963`, `opp_covered=0.016`
- New P0 Top-K set-recall run:
  - `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_235648_prod_full3500_cfg24_p0_topk_set_utility_v1`
  - holdout: `safe_acc=0.4091`, `coverage=0.088`, `opp_active=0.5909`, `opp_covered=0.052`

Interpretation:
- P0 increased activity but degraded directional safety heavily.
- This indicates we improved “act more” pressure without enough directional discrimination.

## Research-backed methods with highest fit to our failure mode

### 1) Two-stage selective pipeline with explicit constraints (most important)

- Stage A: **Set selection** optimized for “any good config in set” (set recall).
- Stage B: **Direction decision** optimized with asymmetric utility (opposite-direction penalty) conditioned on selected set.
- Stage C: **Reject gate** calibrated to risk constraints.

Why:
- Selective prediction literature emphasizes joint optimization of prediction + rejection.
- Our failure mode is exactly this tradeoff (coverage up, risk up).

Primary sources:
- Selective Classification for Deep Neural Networks (Geifman & El-Yaniv, 2017): https://arxiv.org/abs/1705.08500
- SelectiveNet (Geifman & El-Yaniv, 2019): https://arxiv.org/abs/1901.09192
- Deep Gamblers (Liu et al., 2019): https://arxiv.org/abs/1905.06016

### 2) Replace pointwise router with groupwise learning-to-rank inside each batch

- Train ranker with `batch_id` as query/group (24 configs per query).
- Objective: listwise/pairwise ranking on utility-derived relevance, not independent row classification.

Why:
- We need relative ordering inside batch, not only absolute per-row calibration.
- Groupwise LTR is a better inductive bias for this setup.

Primary sources:
- XGBoost learning-to-rank tutorial and objectives: https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html
- CatBoost ranking losses (groupwise ranking support): https://catboost.ai/en/docs/concepts/loss-functions-ranking
- LambdaLoss framework (Wang et al., 2018): https://arxiv.org/abs/1809.06969

### 3) Risk-calibrated abstention with conformal control under shift

- Keep empirical gate, but promote with conformal risk bounds on opposite-direction error.
- Use class-conditional + shift-weighted calibration windows.

Why:
- Our primary risk is opposite-direction error; conformal gives statistical control for deployment gating.

Primary sources:
- Conformal Risk Control (Angelopoulos et al., 2024): https://arxiv.org/abs/2208.02814
- Adaptive Conformal Inference Under Distribution Shift (Gibbs & Candès, 2021): https://arxiv.org/abs/2106.00170
- Weighted Conformal Prediction Under Covariate Shift (Tibshirani et al., 2019): https://arxiv.org/abs/1904.06019

### 4) Regime-adaptive forecast combination on top of model scores

- Add dynamic expert weighting (time-varying) for direction head calibration.
- Use discounted history / adaptive windows for nonstationarity.

Why:
- Current behavior is regime-sensitive; static fit is unstable.

Primary source:
- Dynamic model averaging (Raftery et al., 2010): https://doi.org/10.1016/j.ijforecast.2009.10.003

## Recommended implementation order (next)

1. Implement **groupwise LTR router** (query=`batch_id`) + keep current risk gate unchanged.
2. Add **separate direction head** over Top-K set features (do not multiply heads directly at row level).
3. Add **conformal risk gate selection** as primary operating-point chooser.
4. Run full `3500/500`, compare against `20260227_215602...` baseline by:
   - `directional_active_safe_accuracy`
   - `opposite_fp_rate_active`
   - `opposite_fp_rate_covered`
   - `coverage`

## Immediate acceptance target for next iteration

- Keep `safe_acc >= 0.70`
- Improve coverage from `0.054` toward `>= 0.07` without violating:
  - `opp_active <= 0.30`
  - `opp_covered <= 0.03`


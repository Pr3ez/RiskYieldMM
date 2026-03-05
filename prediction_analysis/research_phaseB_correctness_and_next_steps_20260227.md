# Phase-B Research Continuation + Correctness Audit (1m/target_4class)

## Scope

- Continue research from primary sources toward production-grade risk-first performance.
- Audit Phase-B conformal implementation for correctness consistency.
- Define next implementation sequence grounded in observed failure mode.

## Observed bottleneck (still unresolved)

From latest full runs:

- `20260227_161314_prod_full3500_cfg24_phaseA_rank_utility`
- `20260227_184933_prod_full3500_cfg24_phaseB_classcond_shift`

Main issue remains **directional separability under active trades**:

- active opposite-direction FP remains high (`~0.48-0.52`)
- safe active directional accuracy remains below target (`~0.48-0.52`)
- cadence improved vs earlier baseline but still misses strict production constraints

Consequence: post-hoc gating/calibration improvements alone are not enough; base score ranking quality for “which config to trust now” is still the core limiter.

## Correctness audit and fixes applied

File: `prediction_analysis/one_minute_target4class_config_activation_meta.py`

1. **Holdout gate consistency fix**
- Before: holdout pass/fail used empirical scoring even in conformal mode.
- Now: when `gate_selection_mode=conformal_risk`, holdout pass/fail uses conformal UCB/LCB terms (same logic class as train calibration selection).

2. **Class-conditional robustness fix**
- Before: class-conditional max could be dominated by a missing-class infinite bound.
- Now: only classes with positive effective active support contribute to class-conditional max bound.

3. **Calibration artifact consistency**
- Added explicit calibration weights artifact and optional path handling:
  - `conformal_calibration_weights_by_batch.csv`

4. **Smoke validation**
- Ran a reduced correctness smoke with Phase-B settings:
  - output: `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_190501_smoke_phaseB_correctness`
- Confirms end-to-end execution after fixes.

## Research synthesis (primary sources)

## 1) Conformal risk control is correct direction, but ranking signal quality dominates

- Conformal Risk Control gives finite-sample risk control under its assumptions; weighted/non-exchangeable extensions are needed under drift.
- If base ranking is weak, conformal gating mainly trades coverage/cadence, not fundamental directional accuracy.

## 2) Drift-aware calibration and model selection should be online, not one-shot

- Weighted conformal under covariate shift supports recency/test-distribution emphasis.
- Non-exchangeable conformal risk control and online conformal model selection support nonstationary time series operation.

## 3) Abstention should be learned as a policy, not only thresholded post-hoc

- Online learning with abstention gives a principled regret framework for reject-or-act decisions.
- Selective prediction literature shows direct optimization of risk-coverage can outperform confidence-threshold baselines.

## 4) Dynamic model averaging is a suitable low-variance baseline for nonstationary weighting

- DMA remains a practical finance-tested approach for time-varying model weights and can anchor a robust baseline while more complex policies are tested.

## Recommended next implementation order

## Phase C.1 (next immediate): Online policy pool over gate configurations

Implement an **online abstention selector** over a policy pool:

- policy = `(router_model, lookback, k, threshold, calibration_variant)`
- reward/cost = risk-first utility (heavy penalty for opposite-direction mistakes, abstain cost, optional cadence prior)
- update online with bandit/expert-style rule

Why first:
- directly addresses nonstationary policy drift
- avoids overcommitting to one frozen threshold/regime

## Phase C.2: Non-exchangeable weighted conformal risk variant

- Add non-exchangeable/recency weighting explicitly into conformal bound computation and reporting.
- Keep class-conditional bounds and track per-class effective sample size.

## Phase C.3: Selective-training router objective

- Add a true selective objective (abstain-aware training) for router score generation.
- Compare to current rank-utility objective under identical WF + holdout.

## Phase C.4: DMA-style fallback baseline in production package

- Keep a robust low-variance adaptive baseline for guardrail deployment.

## Acceptance for next promotion attempt

On untouched holdout:

- `opposite_fp_rate_active <= 0.25`
- `opposite_fp_rate_covered <= 0.03`
- `directional_active_safe_accuracy >= 0.70`
- cadence in `[10, 15]` batches/signal

No single metric override; all four must pass.

## Sources

1. Conformal Risk Control (arXiv:2208.02814): https://arxiv.org/abs/2208.02814  
2. Distribution-Free, Risk-Controlling Prediction Sets (arXiv:2101.02703): https://arxiv.org/abs/2101.02703  
3. Conformal Prediction Under Covariate Shift (arXiv:1904.06019): https://arxiv.org/abs/1904.06019  
4. Conformal Decision Theory (arXiv:2310.05921): https://arxiv.org/abs/2310.05921  
5. Online Conformal Model Selection for Nonstationary Time Series (arXiv:2506.05544): https://arxiv.org/abs/2506.05544  
6. Online Learning with Abstention (ICML 2018, PMLR): https://proceedings.mlr.press/v80/cortes18a.html  
7. Selective Classification for Deep Neural Networks (arXiv:1705.08500): https://arxiv.org/abs/1705.08500  
8. SelectiveNet (arXiv:1901.09192): https://arxiv.org/abs/1901.09192  
9. Deep Gamblers (arXiv:1907.00208): https://arxiv.org/abs/1907.00208  
10. On Calibration of Modern Neural Networks (arXiv:1706.04599): https://arxiv.org/abs/1706.04599  
11. eDMA package (JSS 2018): https://www.jstatsoft.org/article/view/v084i11  
12. Conformal Risk Control for Non-Monotonic Losses (arXiv:2602.20151): https://arxiv.org/abs/2602.20151


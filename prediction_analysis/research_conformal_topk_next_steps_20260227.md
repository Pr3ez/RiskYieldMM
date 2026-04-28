# Research Follow-up: Why Conformal Top-K Still Misses Production Gate (1m/target_4class, 3500/500)

## Current failure mode (from latest run)

Run: `prediction_analysis/one_minute_target4class_pattern_outputs/20260227_154656_prod_full3500_cfg24_conformal_topk`

- Holdout selected point: `k=4`, `threshold=0.55`
- `directional_active_safe_accuracy = 0.5538` (target `>= 0.70`)
- `opposite_fp_rate_active = 0.4462` (target `<= 0.25`)
- `opposite_fp_rate_covered = 0.1160` (target `<= 0.03`)
- cadence `= 3.85 batches/signal` (target `10-15`)

Additional diagnostic (holdout, all `(batch, config)` rows):

- router score (`p_hit_router`) is weakly informative:
  - mean `0.5000`, std `0.0267`, range `[0.408, 0.588]`
  - AUC vs correct-direction target: `0.502`
  - AUC vs opposite-direction target: `0.495`
- per-config score (`p_hit`) is slightly better but still weak:
  - AUC vs correct-direction target: `0.516`
  - AUC vs opposite-direction target: `0.484`

Implication: the primary bottleneck is **score separability**, not just thresholding. Conformal gating can only enforce risk on the quality of available scores.

## Research findings mapped to our issue

## 1) Risk control with abstention is valid, but coverage/cadence must be explicitly optimized

- Conformal Risk Control provides finite-sample risk control for user-defined losses, but does not automatically optimize cadence/coverage tradeoff.
- Risk-Controlling Prediction Sets formalize controlling error metrics under constraints.
- Recent reject-option conformal work explicitly uses error-reject curves and risk bounds, which aligns with our cadence and opposite-FP constraints.

## 2) We should calibrate to the correct data regime (distribution shift)

- Weighted conformal under covariate shift is directly relevant because train history and holdout/live regimes drift.
- We currently calibrate on a fixed recent window, but no density-ratio weighting is applied.

## 3) Online adaptation is needed for nonstationary behavior

- Online conformal model selection for nonstationary time series supports adaptive model/gate choice with online guarantees.
- Dynamic model averaging (with forgetting) is established for time-varying model weights.

## 4) Selective prediction objective should directly encode reject behavior

- SelectiveNet / Deep Gambler show integrated reject-option learning can produce better risk-coverage fronts than post-hoc thresholding on weak scores.

## 5) Probability calibration still matters

- Temperature scaling remains a low-complexity calibration baseline and should be checked after changing objectives.

## Recommended implementation order (next)

## Phase A (next immediate): improve separability before new gate complexity

1. Train **batch-wise ranking objective** for config selection (optimize relative order within batch, not absolute hit probability).
2. Use utility-weighted target emphasizing opposite-direction penalties.
3. Recompute diagnostics:
   - AUC vs correct-direction and opposite-direction
   - risk-coverage curve
   - cadence feasibility region

Exit criterion: score AUC materially above random (`> 0.58` as initial target) and non-empty feasible cadence region.

## Phase B: class-conditional weighted conformal gate

1. Build separate calibration for UP and DOWN directional decisions (Mondrian-style partition).
2. Add **covariate-shift weights** on calibration window (recent regime emphasis).
3. Optimize operating point under hard constraints:
   - opposite FP active/covered caps
   - cadence target `10-15`

Exit criterion: feasible threshold exists on train-calibration and remains feasible on holdout.

## Phase C: online gate/model selection

1. Maintain a pool of gate policies (different `k`, thresholds, calibration variants).
2. Apply online conformal model selection / adaptive weighting to switch policies over time.
3. Keep strict no-lookahead and log policy choice per batch for traceability.

Exit criterion: improved holdout stability (reduced regime-dependent collapses) and lower opposite-FP variance across rolling windows.

## Phase D (optional if needed): integrated reject-option learner

1. Implement selective objective (abstain-aware model, not just thresholding).
2. Compare against Phase B/C under identical walk-forward and holdout protocol.

## Sources (primary)

1. Conformal Risk Control (arXiv 2208.02814): https://arxiv.org/abs/2208.02814  
2. Risk-Controlling Prediction Sets (arXiv 2101.02703): https://arxiv.org/abs/2101.02703  
3. Prediction Sets under Covariate Shift (NeurIPS 2019, arXiv 1904.06019): https://arxiv.org/abs/1904.06019  
4. Conformal Decision Theory (arXiv 2310.05921): https://arxiv.org/abs/2310.05921  
5. Online Conformal Model Selection for Nonstationary Time Series (arXiv 2506.05544): https://arxiv.org/abs/2506.05544  
6. Classification with Reject Option via Conformal Prediction (Machine Learning with Applications, 2025): https://www.sciencedirect.com/science/article/pii/S2666827025000344  
7. SelectiveNet (arXiv 1901.09192): https://arxiv.org/abs/1901.09192  
8. Deep Gamblers (arXiv 1907.00263): https://arxiv.org/abs/1907.00263  
9. On Calibration of Modern Neural Networks (arXiv 1706.04599): https://arxiv.org/abs/1706.04599  
10. eDMA (J. Statistical Software): https://www.jstatsoft.org/article/view/v084i11  
11. Dynamic Logistic Regression and Dynamic Model Averaging (Review of Economics and Statistics): https://academic.oup.com/jrsssa/article-abstract/174/3/799/7084388  
12. Conformal Risk Control for Non-Monotonic Losses (arXiv 2602.20151): https://arxiv.org/abs/2602.20151


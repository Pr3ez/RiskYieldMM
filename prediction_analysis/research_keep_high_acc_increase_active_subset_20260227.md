# Research: Keep High Directional Accuracy While Increasing Active Subset

Date: 2026-02-27
Scope: 1m/target_4class router (24 configs), no-lookahead walk-forward

## Current bottleneck

Latest run reached high directional quality on active trades but remains too sparse:
- `directional_active_safe_accuracy = 0.7037`
- `coverage = 0.054` (27/500)
- `opposite_fp_rate_active = 0.2963`

So the core trade-off is now: **increase coverage without letting opposite-direction risk blow up**.

## What research indicates should work best next

## 1) Replace threshold tuning with constrained selective training

### Why
Selective-classification literature shows better risk-coverage tradeoffs when rejection is optimized during training rather than only post-hoc thresholding.

### How to apply here
- Train router with a constrained objective:
  - maximize utility / minimize opposite-direction errors
  - subject to coverage target band (e.g., 0.067-0.10 for 10-15 cadence)
- Practical optimization: primal-dual / Lagrangian updates over coverage and opposite-risk constraints.

### Sources
- SelectiveNet (end-to-end reject option): https://proceedings.mlr.press/v97/geifman19a.html
- Deep Gamblers (abstention loss): https://arxiv.org/abs/1907.00208
- Predictor-Rejector multi-class abstention theory: https://arxiv.org/abs/2310.14772

## 2) Enforce asymmetric error constraints directly (NP-style)

### Why
Your business objective is asymmetric: opposite-direction errors are much more costly than abstentions.

### How to apply here
- Reformulate final decision as NP-style constrained classification:
  - control opposite-direction error rate under target alpha
  - optimize directional hit within that constraint.
- Extend per-direction constraints (UP and DOWN separately) for stability.

### Sources
- NP classification under strict constraint: https://proceedings.mlr.press/v19/rigollet11a.html
- NP multi-class via cost-sensitive learning (with guarantees): https://pubmed.ncbi.nlm.nih.gov/40689012/

## 3) Stabilize coverage under drift with online abstention control

### Why
Static operating points degrade under distribution shift; coverage collapses or expands unexpectedly.

### How to apply here
- Maintain an online abstention controller that updates decision aggressiveness each batch.
- Use regret-minimizing updates on policy set (aggressive/medium/conservative gates) with abstention cost.

### Sources
- Online learning with abstention (ICML 2018): https://research.google/pubs/online-learning-with-abstention/
- Dynamic Model Averaging for time-varying model weights: https://pubmed.ncbi.nlm.nih.gov/20607102/

## 4) Calibrate for drift-aware risk guarantees, not just mean calibration

### Why
Score compression on holdout indicates calibration under shift is still unstable.

### How to apply here
- Use conformal risk control for gate calibration against explicit risk targets.
- Add adaptive conformal updates for nonstationary periods.
- For hyperparameter/operating-point selection, use LTT/qLTT style risk-calibrated selection.

### Sources
- Conformal Risk Control: https://arxiv.org/abs/2208.02814
- Adaptive conformal inference under shift: https://arxiv.org/abs/2106.00170
- Learn then Test: https://arxiv.org/abs/2110.01052
- Quantile Learn-Then-Test: https://arxiv.org/abs/2407.17358

## 5) Keep shift-aware model selection mandatory

### Why
Coverage collapse was linked to train-holdout score distribution mismatch.

### How to apply here
- Keep covariate-shift weighting in candidate selection and calibration splits.
- Use importance-weighted validation for objective comparison.

### Sources
- IWCV under covariate shift: https://jmlr.org/beta/papers/v8/sugiyama07a.html
- Generalized IW for broader shift settings: https://arxiv.org/abs/2305.14690

## Recommended next implementation order

1. Add **primal-dual constrained selective objective** (coverage band + opposite-risk cap) to router training.
2. Add **UP/DOWN separate risk multipliers/constraints** (direction-conditional NP-style control).
3. Add **online abstention controller** over a small policy set to stabilize live coverage.
4. Keep **CRC/aLTT/qLTT** for post-training calibration and operating-point validation only.

This sequence best matches your current failure mode: sparse but high-quality signals, needing controlled expansion of active subset.

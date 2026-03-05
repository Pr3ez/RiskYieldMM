# RIS-89: Accuracy-Coverage Bridge for 1m/target_4class (24 configs)

## 1) What current results show (3500/500 holdout)

From `prediction_analysis/research_outputs/20260227_ris89_accuracy_coverage_bridge.json`:

- Best safe-accuracy run so far: `20260227_215602_prod_full3500_cfg24_shift_reject_rollingq_covcon_v1`
  - `directional_active_safe_accuracy=0.7037`
  - `coverage=0.054` (27/500 active)
  - `opposite_fp_rate_active=0.2963`
- When pushing coverage up (e.g. primal-dual runs), safe accuracy collapses to ~0.53.

Core diagnostic:
- Router top-1 ranking quality is weak:
  - `top1_roc_auc_actual_hit=0.5298`
  - `top1_avg_precision_actual_hit=0.3637`
- But oracle ceiling is high:
  - In `413/500` holdout batches (`82.6%`), at least one config has `dir_acc >= 0.70`.
  - Average number of such configs per batch: `6.886`.

Interpretation:
- The problem is not lack of good configs in each batch.
- The problem is selecting the right one with current top-1 router score.

## 2) Research-backed implication

This pattern matches selective prediction literature: with abstention, performance depends on confidence ranking quality, not only base model accuracy.

Relevant sources:
- Selective classification framework: Geifman & El-Yaniv (2017) https://arxiv.org/abs/1705.08500
- SelectiveNet (joint prediction + selection): https://arxiv.org/abs/1901.09192
- Deep Gamblers (learned abstention): https://arxiv.org/abs/1905.06016
- Conformal Risk Control (risk-constrained selection): https://arxiv.org/abs/2208.02814
- Adaptive conformal inference under shift: https://arxiv.org/abs/2106.00170
- Weighted conformal under covariate shift: https://arxiv.org/abs/1904.06019
- Dynamic model averaging (time-varying weights): https://www.jstatsoft.org/article/view/v084i11 and https://www.sciencedirect.com/science/article/pii/S0377221724006096

## 3) Proper next method (to raise coverage without losing >=0.70)

### Method: Set-then-Direction selective router

Instead of top-1 config selection, optimize in two stages:

1. **Set selector (Top-K candidate set)**
- Train a ranker to output calibrated scores over 24 configs.
- Keep a dynamic Top-K set (K chosen causally per batch from score dispersion + quantile gate).
- Goal: maximize probability that set contains at least one high-quality config (set recall), not exact top-1 hit.

2. **Directional decision head (within selected set)**
- Build direction probability from selected set using weighted directional vote + disagreement features.
- Optimize this head directly for directional utility (opposite-direction penalty) rather than `hit>=0.70` classification alone.

3. **Risk-calibrated reject gate**
- Apply class-conditional + shift-weighted conformal threshold on direction confidence.
- Enforce constraints during selection:
  - `directional_active_safe_accuracy >= 0.70`
  - opposite FP caps
  - cadence floor/ceiling

Why this is the correct move for current data:
- Your oracle stats show many “good” configs per batch, so recovering any good config (set recall) is easier than picking one exact winner.
- Current top-1 AUC ~0.53 indicates exact ranking is too noisy; set-based selection reduces this bottleneck.

## 4) Concrete implementation order

P0 (immediate):
- Add `set_recall_target` training mode:
  - label per `(batch, config)` remains quality indicator
  - train objective to maximize `P(any hit in Top-K)`
- Add `direction_head` trained on selected-set aggregate features with opposite-FP penalty.

P1:
- Add class-conditional shift-weighted conformal gating for direction head output.
- Keep rolling quantile fallback for stability.

P2:
- Add online adaptation of K via primal-dual constraint on coverage vs risk.

## 5) Expected behavior change

Given holdout diagnostics (`k=1 any_hit=0.304`, `k=3 any_hit=0.424`, `k=5 any_hit=0.56`), a set-based router should materially improve candidate quality entering the final directional gate. This is the most plausible path to increase active coverage while keeping safe accuracy near/above 0.70.


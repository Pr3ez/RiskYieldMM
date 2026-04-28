# Research Comparison and Next Implementation Step (After Utility Router)

Date: 2026-02-27

## 1) Where current results stand

Evaluated runs (1m/target_4class, 3500/500):

- `20260227_141406_prod_full3500_cfg24` (hit router baseline)
- `20260227_143553_prod_full3500_cfg24_rank_router` (dir_acc router)
- `20260227_144749_prod_full3500_cfg24_cost_sensitive_router` (dir_acc + opposite weighting)
- `20260227_151043_prod_full3500_cfg24_utility_router` (utility target)

Selected operating-point holdout metrics:

- Baseline hit router: safe=0.368, opp_active=0.632, opp_cov=0.024, bps=26.3
- Rank router: active=0 (threshold collapse)
- Cost-sensitive router: active=0 (threshold collapse)
- Utility router: safe=0.500, opp_active=0.500, opp_cov=0.014, bps=35.7

Posthoc (same predictions, finer threshold, no retrain):

- Best prior rank-router point: safe=0.653, opp_active=0.347, opp_cov=0.034, bps=10.2
- Best utility-router point: safe=0.568, opp_active=0.432, opp_cov=0.032, bps=13.5

Conclusion: utility-router did not outperform prior rank-router on risk-adjusted directional quality.

## 2) What research says relative to our observed failure mode

Observed failure mode:
- Data/leakage checks pass.
- Oracle per-batch opportunity is high, but selector quality is weak and score thresholds are unstable train->holdout.

Research-aligned interpretation:

1. Selective prediction is the right framing (predict-or-abstain):
- Use abstention as first-class objective, not posthoc patch.
- Source: SelectiveNet (PMLR 2019) — https://proceedings.mlr.press/v97/geifman19a.html

2. Abstention under online/expert settings should be learned with explicit abstain costs:
- Source: Online Learning with Abstentions (arXiv 2017) — https://arxiv.org/abs/1708.06828

3. We are doing contextual expert selection; top-1 should be learned as contextual expert policy, not only proxy regression:
- Source: Contextual Bandits with Stochastic Experts (AISTATS 2018) — https://proceedings.mlr.press/v84/ban18a.html

4. Risk control should be explicitly calibrated under shift (coverage-risk control):
- Source: Conformal Risk Control (arXiv 2022) — https://arxiv.org/abs/2208.02814

5. Groupwise/listwise ranking is appropriate for selecting best config within each batch group:
- Source: YetiRank (PMLR 2011) — https://proceedings.mlr.press/v14/gulin11a.html
- CatBoost ranking references — https://catboost.ai/docs/en/concepts/loss-functions-ranking

## 3) Immediate next implementation (recommended)

Implement **Top-K consensus selective router** on top of the best rank-router scores.

Why this next:
- It directly targets opposite-direction risk by requiring directional agreement among strong candidates.
- It is simple, causal, and easy to validate quickly.
- In local holdout diagnostics, consensus already moved us near target:
  - for rank-router scores, `k=4`, `threshold≈0.56` gave about:
    - safe≈0.694
    - opp_active≈0.306
    - opp_cov≈0.030
    - bps≈10.2
  - This is much closer to production gates than utility-router selected output.

Implementation details:
- At each batch:
  1. take top-K configs by router score
  2. if top score >= tau and all K directions agree -> emit that direction
  3. else HOLD
- Tune `(K, tau)` on train walk-forward only with existing risk-first objective.
- Keep final untouched holdout = last 500.

## 4) What to implement after that if still below target

Second step:
- Replace pointwise router with **groupwise ranker** (CatBoostRanker / YetiRank style) with batch as group and cost-aware labels.
- Then run same Top-K consensus gate + risk calibration.

## 5) Promotion gates (unchanged)

- safe >= 0.70
- opposite_fp_rate_active <= 0.25
- opposite_fp_rate_covered <= 0.03
- cadence 10-15 batches/signal

If no feasible point: output best-near-feasible and explicit violations.

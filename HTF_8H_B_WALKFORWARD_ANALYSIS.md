# 8h/B Walk-Forward Analysis Snapshot

Last verified: 2026-04-29

This page summarizes the latest completed `8h/B` Stage-1 walk-forward analysis found in this repository. It is written for reviewers who want to understand the engineering quality behind the project without reading every run artifact.

This is not trading advice and it is not a live trading performance claim. The value of this artifact is the validation discipline: chronological evaluation, leakage checks, reproducible artifacts, selector-policy audits, and honest treatment of weak or unstable results.

## Source Run

The latest completed `8h/B` run found is:

`data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live`

The raw `data/` run directory is a local generated artifact and is ignored by Git by default. The reviewer-facing metrics below are backed by tracked `test_output/` summary snapshots where possible.

Core metadata:

| Field | Value |
|---|---:|
| Run id | `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live` |
| Completed at | `2026-04-21T23:40:14.177641` |
| Model | CatBoost |
| Target | `1m/target_4class` |
| Regime / family | `8h/B` |
| Execution mode | Stage-1 v2 fixed policy |
| Prediction batches | `5170` to `5669` |
| Walk-forward steps | 500 |
| Runtime | 9,974.42 s, about 2.77 h |
| Artifact contract | `2026-04-20-stage1-v2-contract-v1` |

Primary source files and snapshots:

| Artifact | Path | Availability |
|---|---|---|
| Run summary | `data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live/run_summary.json` | Local generated artifact |
| Stage-1 v2 summary | `data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_pb5170_5669_live/stage1_v2_run_summary.json` | Local generated artifact |
| Family summary | `test_output/htf_stage1_regime_family_walkforward/summary_20260421_234014.json` | Tracked summary snapshot |
| Nested selector audit | `test_output/stage1_v2_loss_discounted_selector_nested_audit_20260422_8h_b_pb5170_5669/summary.json` | Tracked summary snapshot |
| Rolling selector audit | `test_output/stage1_v2_loss_discounted_selector_rolling_audit_20260422_8h_b_pb5170_5669/summary.json` | Tracked summary snapshot |
| Pairwise prediction audit | `test_output/stage1_v2_pairwise_prediction_audit_20260421_8h_b_pb5170_5669/summary.json` | Tracked summary snapshot |
| Subset reduction audit | `test_output/stage1_v2_subset_reduction_audit_20260421_8h_b_pb5170_5669/summary.json` | Tracked summary snapshot |

## What The Run Demonstrates

The run completed 500 chronological prediction steps using a fixed policy registry created from the preceding `8h/B` v2 run. Each step evaluated 8 action-key combinations over 21 fold windows, then persisted validation and prediction-batch payloads for downstream audits.

Important run-health checks:

| Check | Result |
|---|---:|
| Leakage guard | Passed on all 500 step summaries |
| Combo completion | 8 of 8 combos completed at every step |
| Mean validation payload rows per step | 7,440 |
| Mean prediction payload rows per step | 1,920 |
| Feature importance rows | 680,000 |
| Feature mask rows | 680,000 |

The per-step validation winners were diverse, not dominated by a single static configuration:

| Validation winner metric | Value |
|---|---:|
| Mean winner accuracy | 52.13% |
| Mean winner macro F1 | 0.2481 |
| Mean cross-direction error | 28.17% |
| Strict quality-threshold passes | 114 / 500 |
| Unique winning combos | 8 / 8 |

## Selector Audit Result

The selector audit is the most important analysis layer. It shows that the underlying combo pool contains useful signal, but the causal selector policy is not yet robust enough to claim production readiness.

Nested selector audit:

| Metric | Value |
|---|---:|
| Policy grid | 30 discounted-loss policies |
| Train / test split | 350 / 150 walk-forward steps |
| Inner train / validation split | 244 / 106 steps |
| Best nested policy | `composite__discount_0.9800` |
| Best nested test mean filtered CDE | 0.4827 |
| Best nested test mean accuracy | 25.26% |
| Best nested test top-1 capture rate | 12.67% |
| Static best combo test accuracy | 27.72% |
| Static best combo test direction accuracy | 53.02% |
| Full-pool oracle test accuracy | 52.66% |
| Full-pool oracle test direction accuracy | 71.22% |

Rolling selector audit:

| Metric | Selected policy | Static combo | Ex-post oracle |
|---|---:|---:|---:|
| Mean test accuracy | 29.38% | 30.81% | 54.26% |
| Mean test CDE, lower is better | 0.4911 | 0.4642 | 0.2686 |

The selected rolling policy matched the ex-post best policy in 0 of 5 rolling windows. That is a useful negative result: the current causal policy selector is unstable and should be improved before any deployment-oriented interpretation.

## Model Diversity Result

The pairwise prediction audit inspected 120,000 prediction rows across 8 combos and 28 pairwise relationships.

| Pairwise metric | Value |
|---|---:|
| Mean class agreement rate | 43.01% |
| Mean direction agreement rate | 62.81% |
| Mean opposite-direction rate | 37.19% |

This is useful because the candidate pool is not just duplicating the same decision boundary. However, the class and direction disagreement audits did not find stable enough pairwise rules to use directly: stable useful pair count was 0 in both the class-disagreement and direction-disagreement summaries.

## Subset Reduction Result

The subset audit tested how much of the full combo pool can be removed without losing the ex-post oracle behavior.

| Subset size | Test direction accuracy | Test class accuracy | Top-1 capture rate |
|---:|---:|---:|---:|
| 1 | 53.02% | 27.72% | 10.00% |
| 4 | 66.23% | 44.09% | 43.33% |
| 6 | 69.23% | 48.51% | 72.00% |
| 7 | 71.21% | 51.11% | 88.00% |
| 8, full pool | 71.22% | 52.66% | 100.00% |

The size-7 subset nearly preserved full-pool direction accuracy, but the full 8-combo pool still gave the best class accuracy and complete top-1 capture. This suggests that combo diversity is valuable, while also pointing to a possible future efficiency tradeoff.

## Engineering Takeaways

For a reviewer, this artifact demonstrates:

- Walk-forward validation over chronological prediction batches instead of random cross-validation.
- Explicit leakage guarding recorded in the per-step artifacts.
- Fixed-policy replay to separate policy evaluation from policy discovery.
- Recursive SHAP feature-selection diagnostics with persisted masks and importances.
- Post-run selector, pairwise, disagreement, and subset-reduction audits.
- Clear distinction between deployable causal metrics and ex-post oracle upper bounds.
- Willingness to publish diagnostic negative results instead of only headline metrics.

The strongest conclusion is not that the 8h/B model is production-ready. The stronger conclusion is that the research loop can find, measure, and explain why a tempting selector policy is not ready yet.

## Next Technical Step

The next useful step is to improve the causal selector rather than enlarge the base model blindly. The evidence points toward:

- stronger history-only selector features,
- alternative objectives that penalize cross-direction errors directly,
- more stable policy families across rolling windows,
- and better gating between static combo fallback and dynamic selector decisions.

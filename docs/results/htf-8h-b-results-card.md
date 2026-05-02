# HTF 8h/B Results Card

This card summarizes the current reviewer-facing interpretation of the
documented `8h/B` walk-forward run.

## Scope

| Field | Value |
|---|---|
| Regime/family | `8h/B` |
| Target | `1m/target_4class` |
| Model layer | Stage-1 CatBoost |
| Evaluation style | Chronological walk-forward |
| Prediction batches | `5170` to `5669` |
| Steps | 500 |
| Detailed snapshot | [`../../HTF_8H_B_WALKFORWARD_ANALYSIS.md`](../../HTF_8H_B_WALKFORWARD_ANALYSIS.md) |

## What It Demonstrates

- End-to-end HTF feature/label/run artifact discipline.
- Chronological validation and leakage-guarded step summaries.
- Persisted validation and prediction-batch payloads.
- Post-run selector-policy, pairwise prediction, and subset-reduction audits.
- Clear distinction between causal selector results and ex-post oracle bounds.

## Main Interpretation

The run shows that the combo pool contains useful signal and diversity, but the
current causal selector policy is not robust enough to treat as deployment-ready.
That is a valuable engineering result: the workflow can identify and document
why a tempting model-selection path is unstable.

## Key Metrics

| Metric | Value |
|---|---:|
| Walk-forward steps | 500 |
| Unique validation-winning combos | 8 / 8 |
| Mean validation winner accuracy | 52.13% |
| Nested selector test accuracy | 25.26% |
| Static best combo test accuracy | 27.72% |
| Full-pool oracle test accuracy | 52.66% |
| Full-pool oracle test direction accuracy | 71.22% |

## Limitations

- This is not a live trading result.
- Raw generated run artifacts are local and not committed.
- The strongest selector result is still weaker than the ex-post oracle.
- Further work should improve causal selector stability before expanding model
  complexity.

## Next Research Step

Improve the history-only selector feature set and objective, with special focus
on penalizing cross-direction errors and stabilizing policy choice across rolling
windows.

# HTF Documentation

These documents describe the higher-timeframe workflow. Source data, HTF
materialization, and Stage-1 merged dataset assembly are now multi-asset-aware.
Downstream diagnostics and Step-2 documents may still describe older
regime/family run groupings.

| Document | Purpose |
|---|---|
| [`stage1-logic.md`](stage1-logic.md) | Stage-1 design, leakage constraints, and multi-asset dataset assembly rules |
| [`stage1-artifacts.md`](stage1-artifacts.md) | Stage-1 artifact contract, merged dataset roots, and persisted payloads |
| [`stage1-step2-plan.md`](stage1-step2-plan.md) | Legacy feature pruning and baseline-vs-filtered analysis plan |
| [`target-labeling-logic.md`](target-labeling-logic.md) | Historical 8-class label reference; current 4-class policy is documented in the root README and multi-asset plan |
| [`backtest-investigation.md`](backtest-investigation.md) | HTF backtest investigation notes |

Related high-signal research notes remain in
[`../../notebooks/notes/`](../../notebooks/notes/), especially the Stage-1 v2,
walk-forward diagnostics, helper-cache, and data-label audit notes.

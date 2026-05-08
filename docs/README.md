# Documentation Map

This directory is the main documentation home for RiskYieldMM. The repository
also keeps two root-level review snapshots beside `README.md` for GitHub
visibility:

- [`HTF_8H_B_WALKFORWARD_ANALYSIS.md`](../HTF_8H_B_WALKFORWARD_ANALYSIS.md)
- [`FEATURE_AND_DATASET_SNAPSHOT.md`](../FEATURE_AND_DATASET_SNAPSHOT.md)

## Current Workflow Docs

Current source data and HTF materialization are multi-asset-aware. Stage-1 and
downstream analysis docs still describe the legacy regime/family workflow unless
they explicitly mention `data/htf_multiasset/{asset}/` target/context support.

| Area | Location | Purpose |
|---|---|---|
| Reproducibility | [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) | Setup, data refresh, HTF feature generation, and Stage-1 run commands |
| HTF pipeline and Stage-1 | [`htf/`](htf/) | Current multi-regime HTF logic plus legacy Stage-1 design |
| Data sources and target inputs | [`data/`](data/) | Bybit source integration, target-label notes, and data/target verification |
| Architecture | [`architecture/`](architecture/) | System-level and backtest architecture references |
| Results summaries | [`results/`](results/) | Reviewer-facing result cards and interpretation notes |
| Validation and leakage | [`validation/`](validation/) | Leakage audits, validation checklists, and adaptive validation research |
| Conformal prediction | [`conformal/`](conformal/) | Conformal/ACI architecture, experiments, and integration results |
| Preprocessing | [`preprocessing/`](preprocessing/) | Helper optimization, preprocessing design, and audit notes |

## Supporting Research And Plans

| Area | Location | Purpose |
|---|---|---|
| Modeling research | [`modeling/`](modeling/) | L2 models, ensemble research, dynamic windows, and accuracy work |
| Implementation plans | [`plans/`](plans/) | Refactor plans, implementation plans, status notes, and cleanup todo items |
| General research | [`research/`](research/) | Research reports that are broader than one pipeline module |
| Project handoff notes | [`project/`](project/) | Dated handoff material; use as historical context |
| Experiments | [`experiments/`](experiments/) | Experiment plans and grid-search notes |
| Target redesign | [`target-redesign/`](target-redesign/) | Multi-label and target-system redesign notes |

## Legacy Or Specialized References

| Area | Location | Purpose |
|---|---|---|
| Feature catalog | [`feature-engineering/stage1-feature-catalog/`](feature-engineering/stage1-feature-catalog/) | Older Stage-1 feature naming/catalog material |
| Analysis script review | [`analysis-scripts/architecture-review/`](analysis-scripts/architecture-review/) | Older analysis-script architecture review |
| Target-model docs | [`target-models/legacy-target-models/`](target-models/legacy-target-models/) | Legacy target-model documentation |
| L2 backtest review | [`l2-backtest-review/`](l2-backtest-review/) | Detailed L2/backtest review notes |
| Astra extension research | [`astra-research/`](astra-research/) | Agent/extension research and validation notes |
| Bybit API reference copy | [`../BybitApiDocs/`](../BybitApiDocs/) | Local Bybit API documentation notes |

## Notes And Archive

- [`../notebooks/notes/README.md`](../notebooks/notes/README.md) indexes the
  chronological HTF research and implementation notes.
- [`../Archive/README.md`](../Archive/README.md) indexes legacy code and older
  pipeline documentation.
- Generated run outputs and local datasets are not documentation sources of
  truth unless explicitly referenced from this map or the root `README.md`.

## Placement Policy

- Put current, maintained design docs under a topical `docs/` subfolder.
- Put chronological session notes under `notebooks/notes/` with a date suffix.
- Put retired implementation notes or legacy code explanations under `Archive/`.
- Keep root-level markdown limited to project identity, contribution/security
  docs, and high-signal review snapshots.

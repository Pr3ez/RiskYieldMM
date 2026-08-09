# Documentation Map

This directory is the main documentation home for RiskYieldMM. The repository
also keeps two root-level review snapshots beside `README.md` for GitHub
visibility:

- [`HTF_8H_B_WALKFORWARD_ANALYSIS.md`](../HTF_8H_B_WALKFORWARD_ANALYSIS.md)
- [`FEATURE_AND_DATASET_SNAPSHOT.md`](../FEATURE_AND_DATASET_SNAPSHOT.md)

## Current Workflow Docs

Current source data, HTF materialization, and Stage-1 merged dataset assembly
are multi-asset-aware. Downstream analysis docs may still describe the legacy
regime/family workflow unless they explicitly mention
`data/htf_multiasset_merged/` target/context support.

<!-- STAGE1_ACTIVE_GATE: S1-A3 -->

| Area | Location | Purpose |
|---|---|---|
| Reproducibility | [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md) | Setup, data refresh, HTF feature generation, and Stage-1 run commands |
| HTF pipeline and Stage-1 | [`htf/`](htf/) | Current multi-regime HTF logic plus legacy Stage-1 design |
| Trading-system redesign / Stage 1 execution | **Current control:** [`research/stage1_execution_control_2026-08-08.md`](research/stage1_execution_control_2026-08-08.md). Program roadmap: [`research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md`](research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md). Latest accepted packet: [`S1-A2 dual-preflight acceptance`](research/v4_9f_a2_raw_v8_step2_v2_dual_preflight_acceptance_2026-08-09.md). Active design: [`S1-A3 final-freeze correction`](research/v4_9f_a2_raw_v8_step2_v2_final_freeze_design_correction_2026-08-09.md). | `S1-A1` and `S1-A2` are accepted. `S1-A3` is the sole active gate; `A3-T` fail-first manifest tests are next. Offline Stage 2 and paper/live activation remain blocked. |
| Raw V8 Step-2 V3 inventory acceptance | [`research/v4_9f_a2_raw_v8_step2_v3_inventory_acceptance_2026-08-01.md`](research/v4_9f_a2_raw_v8_step2_v3_inventory_acceptance_2026-08-01.md) | Canonical re-frozen V3 identities, byte-identical 408-profile proof, 45/98-test security/consumer evidence, bounded-context defect closure, and pending maxima/production gates |
| Raw V8 maximum protocol V1 rejection | [`research/v4_9f_a2_raw_v8_step2_maximum_protocol_v1_feasibility_rejection_2026-08-02.md`](research/v4_9f_a2_raw_v8_step2_maximum_protocol_v1_feasibility_rejection_2026-08-02.md) | Accepted verifier-derived 94,905-coordinate and 94,906-node/depth lower bounds; V1 pilot/publication remains prohibited |
| Raw V8 compact maximum-proof V2 correction | [`research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md`](research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md) and [`acceptance`](research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_acceptance_2026-08-02.md) | Accepted upper-bound-plus-legal-attainer theorem, separate publication/resource artifacts, V4 authority migration, and non-circular all-row preflight design |
| Raw V8 Step-2 V4 inventory acceptance | [`research/v4_9f_a2_raw_v8_step2_v4_inventory_acceptance_2026-08-02.md`](research/v4_9f_a2_raw_v8_step2_v4_inventory_acceptance_2026-08-02.md) | Accepted exact V3→V4 delta, five authorities, independent generator/validator, unchanged registry/408 profiles/474 rows, and final predecessor/V4 consumer evidence; V2 protocol and preflights remain open |
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

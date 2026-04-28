# HTF Current Workflow Documentation Inventory - 2026-04-07

## Scope

Identify where the repo currently documents:

- the supported `notebooks/htf_pythonscript.py` production workflow
- the HTF data artifacts it prepares
- the data roots consumed by the walk-forward diagnostics stack

## Short Answer

Yes, the documentation exists, but it is fragmented.

There is **not one single current end-to-end document** that fully explains:

`raw fetch -> HTF production build -> helper/label roots -> Stage-1 -> Step-2 -> causal diagnostics`

The current picture is spread across:

- one current production entrypoint file
- one current workflow audit note
- one Stage-1 multiregime enablement note
- one data/label audit note
- the diagnostics runner itself
- the raw fetch README

## Best Current Sources Of Truth

### 1. Production entrypoint

- `notebooks/htf_pythonscript.py`

What it documents well:

- this is the supported HTF production launcher
- legacy mixed notebook body was archived
- orchestration lives here, execution lives in shared modules
- current production config surface:
  - `data_dir = PROJECT_ROOT / "data"`
  - `raw_data_dir = PROJECT_ROOT / "fetchingByBit"`
  - build regimes = `8h`, `24h`, `7d`
  - validation regimes = `8h`, `24h`, `7d`
  - optimization/helpers/validation toggles

What it does **not** document fully:

- exact downstream artifact roots by regime/family
- exact handoff into Stage-1 / Step-2 / causal diagnostics

### 2. Current workflow lineage into diagnostics

- `notebooks/notes/htf_walkforward_workflow_audit_2026-04-07.md`

This is the **best current narrative doc** for:

- production HTF entrypoint
- Stage-1 / Step-2 / causal-analysis source-of-truth files
- per-root evaluation ranges
- directional-accuracy outcomes
- incomplete-combo filtering

This is the most useful current doc if the question is:

- “what production data are we using in walk-forward diagnostics right now?”

### 3. Exact root mapping used by the diagnostics runner

- `scripts/analysis/htf_walkforward_diagnostics.py`

This is the **code source of truth** for current root-to-data mapping.

It explicitly maps:

- `8h/B -> data/htf_with_helpers + data/htf_4class_labels`
- `8h/C -> data/htf_with_helpers_shift4h + data/htf_4class_labels_shift4h`
- `24h/B -> data/htf_with_helpers_24h + data/htf_4class_labels_24h`
- `24h/C -> data/htf_with_helpers_24h_shift12h + data/htf_4class_labels_24h_shift12h`
- `7d/B -> data/htf_with_helpers_7d + data/htf_4class_labels_7d`
- `7d/C -> data/htf_with_helpers_7d_shift84h + data/htf_4class_labels_7d_shift84h`

It also records that the diagnostics scope is:

- `1m / target_4class`
- current six roots only
- no-lookahead causal analysis only

### 4. Stage-1 enablement and root-awareness

- `notebooks/notes/htf_stage1_multiregime_enablement_2026-04-01.md`

This is the best doc for:

- how Stage-1 was adapted to current HTF production roots
- the override mechanism for helper/label roots
- the one-run-per-root architecture
- run IDs used for:
  - `stage1_catboost_8h_b_live`
  - `stage1_catboost_8h_c_live`
  - `stage1_catboost_24h_b_live`
  - `stage1_catboost_24h_c_live`
  - `stage1_catboost_7d_b_live`
  - `stage1_catboost_7d_c_live`

This is the best doc for:

- “how do current HTF helper/label artifacts become Stage-1 walk-forward runs?”

### 5. Current saved data/label validity

- `notebooks/notes/htf_data_label_audit_2026-04-01.md`

This documents:

- current saved HTF corpus validation status
- label coverage by regime/family
- target distributions
- whether saved data/labels are structurally valid under the production contract

This is the best doc for:

- “are the current production artifacts valid before they go into walk-forward?”

### 6. Raw source layer

- `fetchingByBit/README.md`

This documents:

- raw Bybit fetch/update pipeline
- source directories and scripts
- update procedure
- 8h aggregation logic

Useful as Step 0 context, but it is **not HTF-walkforward-specific**.

## Useful But Historical / Partly Stale

These notes still contain valuable context, but they are **not the best current-state references**:

### `notebooks/notes/htf_walkforward_workflow_audit_2026-04-02.md`

- still useful
- older snapshot of the same lineage now refreshed in the 2026-04-07 note

### `notebooks/notes/htf_walkforward_diagnostics_implementation_2026-04-02.md`

- useful for what the diagnostics runner was built to do
- more implementation-focused than current-state workflow-focused

### `notebooks/notes/htf_entrypoint_split_2026-04-01.md`

- historical only
- describes a temporary split state
- should not be treated as current HTF entrypoint guidance

### `notebooks/notes/mtf_htf_workflow_migration_plan_2026-04-01.md`

- historical planning note
- not current production truth

### `notebooks/notes/htf_pythonscript_runtime_report_2026-03-18.md`

- large and detailed
- but it describes the older mixed-file era
- many line references and ownership assumptions are no longer current

### `notebooks/notes/htf_workflow_audit_2026-03-18.md`

- useful background
- pre-clean-entrypoint state
- not the best source for today’s launcher/data-lineage state

## Current Documentation Gap

The repo still lacks one concise current document that explains the full chain in one place:

1. `fetchingByBit` raw source prerequisite
2. `notebooks/htf_pythonscript.py` production build
3. exact produced artifact roots under `data/`
4. Stage-1 run IDs and root mappings
5. Step-2 root mappings and outputs
6. causal ensemble outputs and final evaluation artifacts

Right now that story has to be reconstructed from multiple notes plus code.

## Recommended Current Reading Order

If someone wants the current truth with minimum confusion, the best order is:

1. `notebooks/htf_pythonscript.py`
2. `notebooks/notes/htf_walkforward_workflow_audit_2026-04-07.md`
3. `scripts/analysis/htf_walkforward_diagnostics.py`
4. `notebooks/notes/htf_stage1_multiregime_enablement_2026-04-01.md`
5. `notebooks/notes/htf_data_label_audit_2026-04-01.md`
6. `fetchingByBit/README.md`

## Conclusion

Yes, the repo already contains documentation for the current HTF production workflow and its use in walk-forward diagnostics.

But the documentation is:

- **present**
- **usable**
- **not centralized**

The strongest current references are:

- `notebooks/htf_pythonscript.py`
- `notebooks/notes/htf_walkforward_workflow_audit_2026-04-07.md`
- `scripts/analysis/htf_walkforward_diagnostics.py`
- `notebooks/notes/htf_stage1_multiregime_enablement_2026-04-01.md`
- `notebooks/notes/htf_data_label_audit_2026-04-01.md`

If needed, the next cleanup step should be to write one consolidated current-state doc for the full HTF-to-walkforward data lineage.

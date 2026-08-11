# RPF Workflow Integrity Audit

## Purpose

Create one strict map of the current RPF walk-forward workflow after the
shadow-versus-live artifact bug. This document defines which command surfaces
are active, which are diagnostic, which are historical, and which rules must be
enforced before any further modeling work.

## Current Decision

Status: `workflow_integrity_fixes_in_progress`.

The RPF code is technically executable, but the workflow accumulated too many
research branches. The immediate failure was not a model-capacity issue. It was
a workflow integrity issue:

```text
candidate shadow artifacts were interpreted as live router-selected evidence
```

That is now fixed in code for regime diagnostics, but the broader workflow must
stay under this contract.

Additional integrity fixes applied after the first source correction:

- `rank_signal_router` writes explicit `effective_*` artifacts and the report
  now shows effective selected output before base-router output.
- `rank_signal_regime_diagnostic` preserves `requested_prediction_source` and
  resolved `prediction_source` in `regime_signal_quality.parquet`.
- Prequential regime suppression no longer learns suppression rules from
  `change_flag=False`. Change-point suppression is true-alarm-only by default.
- Regime suppression candidates exclude false change-flag contexts.
- GMM/HMM regime state IDs are canonicalized by train-cluster centroid order
  after each fit, so state IDs are less likely to permute across refits.
- Router now writes `effective_conflict_diagnostics.parquet` in addition to the
  base `conflict_diagnostics.parquet`.

## Command Ownership

### Active Foundation

These commands are allowed for data readiness and controlled ranked-signal
work:

```bash
python -m regression_feature_engineering.walkforward.optimize --stage readiness
python -m regression_feature_engineering.walkforward.rank_signal
python -m regression_feature_engineering.walkforward.rank_signal_router
```

Meaning:

- `optimize --stage readiness` builds sparse frozen windows and validates
  feature/label alignment.
- `rank_signal` tests one side/candidate configuration in isolation.
- `rank_signal_router` is the only command that can produce current
  router-selected decision artifacts.

### Active Diagnostics

These commands are diagnostic only. They may explain failures, but their output
is not a promoted decision stream unless joined back through a live router
contract:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic
python -m regression_feature_engineering.walkforward.rank_signal_transfer_separator
python -m regression_feature_engineering.walkforward.rank_signal_context_diagnostic
python -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator
python -m regression_feature_engineering.walkforward.rank_signal_rule_bank
python -m regression_feature_engineering.walkforward.rank_signal_row_diagnostic
python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank
python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic
python -m regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator
```

Hard rule:

```text
diagnostic output can propose a future router rule, but cannot be reported as
live trading performance by itself.
```

### Historical Baselines

These are kept for reproduction and comparison only:

```bash
python -m regression_feature_engineering.walkforward.classify
python -m regression_feature_engineering.walkforward.classify_optuna
python -m regression_feature_engineering.walkforward.cnn_feature_diagnostic
python -m regression_feature_engineering.walkforward.evidence_panel
```

Meaning:

- binary classifier results explain why probability-threshold classification
  was abandoned as the active path;
- CNN/evidence-panel diagnostics can provide candidate panels, but they are not
  final decision evidence.

### Abandoned Or Quarantined Paths

These are not active unless a new written plan explicitly reopens them:

```bash
python -m regression_feature_engineering.walkforward.ema_gate
python -m regression_feature_engineering.walkforward.regime_gate
python -m regression_feature_engineering.walkforward.signal_bank
python -m regression_feature_engineering.walkforward.decision_bank
python -m regression_feature_engineering.walkforward.panel_select
python -m regression_feature_engineering.walkforward.classify --window-mode ema_regime_bank
```

Reason:

- EMA gates, signal banks, decision banks, and learned gates did not produce a
  stable live-safe decision layer;
- their code remains for reproducibility, but they must not steer active work.

## Artifact Contract

### Router Artifacts

Inside `test_output/rpf_ranked_signal_router/{run_id}/`:

```text
candidate_prediction_window_metrics.parquet
candidate_prediction_scores.parquet
```

Role:

```text
shadow candidate diagnostics
```

They answer:

```text
what would each candidate have done independently?
```

They do **not** answer:

```text
what did the live router select?
```

Live router-selected artifacts:

```text
router_window_metrics.parquet
router_prediction_scores.parquet
router_decisions.parquet
side_summary.json
```

Role:

```text
base router-selected decision stream
```

When `row_rule_gate_output_mode=active_candidate` is enabled, the effective
active stream is:

```text
row_rule_active_window_metrics.parquet
row_rule_active_prediction_scores.parquet
row_rule_active_decisions.parquet
row_rule_active_side_summary.json
```

Current `rank_signal_router` runs also write explicit effective artifacts:

```text
effective_window_metrics.parquet
effective_prediction_scores.parquet
effective_decisions.parquet
effective_block_summary.parquet
effective_side_summary.json
effective_artifact_source.json
```

These are the first files to inspect for live-style selected performance. For
old runs that do not have `effective_*`, diagnostics resolve `effective_selected`
to `row_rule_active_*` when active row-rule output exists, otherwise to
`router_*`.

Reports must use `Effective Selected Summary` for current live-style claims.
`Base Router Summary` is diagnostic when row-rule active output is enabled.

Only `router_*` or `row_rule_active_*` artifacts may be used for selected
performance claims. Which one is active must be declared.

### Regime Diagnostic Source

`rank_signal_regime_diagnostic` now has:

```bash
--prediction-source effective_selected
--prediction-source router_selected
--prediction-source row_rule_active
--prediction-source candidate_shadow
```

Default:

```text
effective_selected
```

Reason:

```text
live-style checks must use the effective selected stream. If row-rule active
output exists, that is the effective stream; otherwise base router output is
used. Shadow analysis must be explicitly requested.

For new router runs, `effective_selected` reads `effective_window_metrics.parquet`
directly. For historical runs, it resolves the source from available artifacts.
```

## Current Corrected Evidence

Shadow candidate prequential suppression replay:

```text
run:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_175635_rank_signal_regime_suppression_simulator/

DOWN:
  signals   3015 -> 641
  precision 0.393 -> 0.441
  lift      1.024 -> 1.151

UP:
  signals   2678 -> 890
  precision 0.416 -> 0.438
  lift      1.072 -> 1.130
```

Interpretation:

```text
candidate-shadow evidence only. Useful for diagnosing branch potential, not
live router performance.
```

Base router-selected prequential suppression replay:

```text
run:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_192425_rank_signal_regime_suppression_simulator/

DOWN:
  signals   29 -> 29
  precision 0.207 -> 0.207
  lift      0.540 -> 0.540

UP:
  signals   21 -> 21
  precision 0.333 -> 0.333
  lift      0.860 -> 0.860
```

Interpretation:

```text
the base router-selected stream is sparse and below base rate on both sides.
```

Effective active stream across the same four 960-window latest runs:

```text
UP row_rule_active:
  signals   206
  precision 0.422
  base      0.388
  lift      1.089

DOWN row_rule_active:
  signals   204
  precision 0.466
  base      0.383
  lift      1.214
```

Interpretation:

```text
row-rule active output is the current effective stream when active output mode
is enabled. It beats base rate, but precision/frequency are still too weak for
promotion.
```

## Integrity Rules

1. Do not compare shadow candidate metrics against live router metrics without
   naming the source.
2. Do not promote any run unless the artifact source is `router_selected`,
   `row_rule_active`, or an explicitly live-safe command writes selected
   decisions.
3. Do not add another modeling branch until the active command and artifact
   source are written in the experiment note.
4. Do not treat validation metrics as prediction evidence.
5. Do not use current prediction labels, current full-batch score summaries, or
   current full-batch aggregates as live gate inputs.
6. Any rule learned from matured prediction outcomes must be replayed
   prequentially before it can be considered.
7. If a run has fewer than useful weekly signal frequency, report it as a sparse
   diagnostic branch, not a trading workflow.

## Required Fixes Before More Modeling

### Done

- Added `--prediction-source` to `rank_signal_regime_diagnostic`.
- Changed default source to `effective_selected`.
- Documented corrected live-router results.
- Added tests for router-selected regime diagnostic loading.
- Added tests for effective selected source resolving to `row_rule_active`.

### Still Required

- Add a small workflow registry or status table in code so commands can write
  `workflow_status`, `artifact_source`, and `promotion_scope` into
  `stage_status.json`.
- Update `rpf_walkforward_code_review_cleanup.md`, because it is outdated and
  still describes the classifier as the main active path.
- Add tests that fail if a live report reads
  `candidate_prediction_window_metrics.parquet` without explicitly declaring
  `candidate_shadow`.
- Add a top-level summary table of all current command outputs and whether they
  are `active`, `diagnostic`, `historical`, or `abandoned`.

## Next Engineering Step

Do not run new RPF experiments yet.

First, add code-level workflow metadata to active commands:

```text
rank_signal
rank_signal_router
rank_signal_regime_diagnostic
rank_signal_regime_suppression_simulator
```

Then rerun only a small smoke to verify each artifact writes the correct
contract.

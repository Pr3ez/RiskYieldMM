# RPF Walk-Forward Code Review And Cleanup

## Purpose

Review the current `regression_feature_engineering/walkforward/` package,
identify what is active versus exploratory, and define the cleanup path toward
a simpler RPF binary walk-forward.

## Current Status

Status: `historical_cleanup_notes_superseded_for_active_status`.

The package works technically, but it has accumulated too many command
surfaces from research iterations. This document records the earlier classifier
cleanup pass. It is no longer the active source of truth for command status.

Use the current workflow contract instead:

```text
regression_feature_engineering/docs/rpf_workflow_integrity_audit.md
```

Reason:

```text
The active path moved from probability-threshold binary classification to
ranked-signal candidates, router-selected decisions, and explicit
shadow-versus-live artifact separation.
```

## Scope

This review covers:

```text
regression_feature_engineering/walkforward/
```

It does not review feature formulas, RPF materialization, or old Stage-1 HTF
scripts.

## Source Of Truth

- Current summary: `rpf_current_experiment_summary.md`
- Binary classifier command wrapper:
  `regression_feature_engineering/walkforward/classify.py`
- Binary classifier internals:
  `regression_feature_engineering/walkforward/classification/`
- Abandoned active-path EMA-regime selector:
  `regression_feature_engineering/walkforward/ema_regime.py`
- RPF data/window contracts:
  - `regression_feature_engineering/walkforward/data.py`
  - `regression_feature_engineering/walkforward/windows.py`
- Regime plan: `rpf_regime_gated_prediction_plan.md`

## What This Does Not Decide

This doc does not delete files by itself. It defines what should be treated as
active, diagnostic, or deprecated before code is moved or removed.

## Main Findings

### 1. AUC Was Over-Visible

`auc` is not an appropriate primary metric for the current binary trading
targets.

Reasons:

- the decision is thresholded and cost-sensitive;
- false positives are more harmful than false negatives;
- ranking quality can look acceptable while the selected threshold still
  produces bad trades;
- regime dependence means a global rank metric hides the failure mode.

Current correction:

- AUC remains stored in `trials.parquet` only as a secondary rank diagnostic;
- terminal logs and docs now lead with decision cost, precision, recall,
  false-positive rate, and predicted-positive rate;
- promotion language no longer uses AUC.

### 2. `classify.py` Was Too Large

Before the first cleanup pass, `classify.py` mixed:

- CLI parsing;
- EMA-regime window preparation;
- feature ablation selection;
- per-window batch loading;
- CatBoost training;
- threshold sweep;
- metric calculation;
- report writing.

The first cleanup pass split the active implementation into:

```text
walkforward/classification/
  __init__.py
  cli.py
  runner.py
  data.py
  model.py
  metrics.py
  targets.py
```

`classify.py` remains the public command surface and backward-compatible import
wrapper. This keeps existing commands and historical diagnostic modules working
while the active implementation is auditable by responsibility.

### 3. Several Modules Are Historical Or Exploratory

Some modules are useful for evidence but should not be treated as active
optimization paths.

| Module | Status | Keep? | Reason |
|---|---|---|---|
| `classify.py` | active wrapper | yes | Stable command and compatibility exports |
| `classification/cli.py` | active | yes | CLI orchestration and artifact writing |
| `classification/runner.py` | active | yes | Per-window train/validation/prediction loop |
| `classification/data.py` | active | yes | Binary label join and model row conversion |
| `classification/metrics.py` | active | yes | Decision metrics, threshold sweep, objective |
| `classification/model.py` | active | yes | CatBoostClassifier boundary |
| `classification/targets.py` | active | yes | Binary target definitions |
| `ema_regime.py` | abandoned active path | yes | EMA-selected train/validation/prediction experiment kept only for reproducibility |
| `data.py` | active | yes | RPF manifest, exact joins, batch index |
| `windows.py` | active | yes | Sparse frozen windows |
| `ablation.py` | active | yes | Family-scope selection |
| `policy.py` | active but constrained | yes | Current binary path mainly uses all/frozen panels |
| `reports.py` | active | yes | Shared artifact writing |
| `ema_gate.py` | compatibility wrapper | keep | Wrapper to `experimental/ema_gate.py` |
| `regime_gate.py` | compatibility wrapper | keep | Wrapper to `experimental/regime_gate.py` |
| `signal_bank.py` | compatibility wrapper | keep | Wrapper to `experimental/signal_bank.py` |
| `decision_bank.py` | compatibility wrapper | keep | Wrapper to `experimental/decision_bank.py` |
| `optimize.py` | regression/share research | separate from binary | Not active binary workflow |
| `panel_select.py` | compatibility wrapper | keep | Wrapper to `experimental/panel_select.py` |
| `experimental/` | historical/diagnostic | yes | Reproducibility for failed or deferred branches |
| `metrics.py` | regression active | yes | Clean regression metrics |
| `model.py` | regression active | yes | Clean regression CatBoost config |
| `config.py` | shared | yes | Clean RPF config parsing |

### 4. Active Binary Decision Metrics Need One Canonical Contract

The current primary binary metrics should be:

```text
decision_cost_per_row
precision
recall
false_positive_rate
false_negative_rate
predicted_positive_rate
tp/fp/fn/tn
threshold
prob_std/prob_unique
executed_window_count
skipped_window_count
```

Secondary diagnostics:

```text
logloss
brier
balanced_accuracy
auc
```

`auc` must not be used for promotion or primary comparison.

### 5. Deletion Should Be Staged

Do not delete exploratory modules immediately while:

- tests still cover them;
- docs still explain why they failed;
- local reports reference their command outputs;
- current runs may still be in progress.

Instead:

1. Mark inactive modules as exploratory/deprecated in docs.
2. Stop linking them as active command surfaces.
3. Move their implementations under an `experimental/` package and keep thin
   compatibility wrappers at old command paths.
4. Remove or reduce tests for rejected paths only after their evidence is
   captured in docs.

## Active Command Surface

Use these commands for current work:

```bash
python -m regression_feature_engineering.walkforward.optimize --stage readiness
python -m regression_feature_engineering.walkforward.classify
```

Use these only for historical reproduction or explicit diagnostics. EMA paths
are abandoned for active modeling:

```bash
python -m regression_feature_engineering.walkforward.ema_gate
python -m regression_feature_engineering.walkforward.classify --window-mode ema_regime_bank
python -m regression_feature_engineering.walkforward.decision_bank
python -m regression_feature_engineering.walkforward.regime_gate
```

Do not rerun unchanged:

```bash
python -m regression_feature_engineering.walkforward.regime_gate --window-mode signal_bank
python -m regression_feature_engineering.walkforward.regime_gate --window-mode hybrid_recent_signal_bank
```

## Cleanup Plan

### Phase 1: Documentation Cleanup

Status: `implemented_initial`.

- Add this review doc.
- Add `rpf_current_experiment_summary.md`.
- Remove AUC from primary logs and primary docs.
- Keep AUC only as stored diagnostic.

### Phase 2: Classifier Refactor

Status: `implemented_initial`.

`classify.py` has been reduced to a public wrapper. The implementation now
lives in:

```text
classification/cli.py
classification/runner.py
classification/data.py
classification/metrics.py
classification/model.py
classification/targets.py
```

Acceptance:

- command behavior stays unchanged;
- tests pass;
- existing output schema remains readable;
- terminal logs use primary decision metrics only.

Remaining cleanup:

- move old private helper imports in exploratory modules to the new package
  after their reports are finalized;
- add a smaller direct unit-test surface for each `classification/` module;
- keep rejected gate/signal-bank/EMA paths quarantined as historical
  diagnostics unless a new plan explicitly reopens them.

### Phase 3: Quarantine Exploratory Paths

Status: `implemented_initial`.

The first quarantine pass moved these implementations under
`walkforward/experimental/`:

```text
experimental/ema_gate.py
experimental/regime_gate.py
experimental/signal_bank.py
experimental/decision_bank.py
experimental/panel_select.py
```

Thin wrappers remain at the old module paths so existing commands, tests, and
historical report references keep working. Do not promote these wrappers as
active model-development surfaces.

### Phase 4: Canonical Binary Runner

Status: `planned`.

Create one clean command surface for the current decision problem:

```bash
python -m regression_feature_engineering.walkforward.binary_decision
```

It should support:

- chronological windows;
- fixed feature-family scopes;
- false-positive-aware threshold selection;
- row-level prediction output;
- window-level regime diagnostics.

It should not support:

- learned gate experiments;
- EMA-regime prediction-window selection;
- EMA-regime train/validation banks;
- signal-bank gate training;
- SHAP feature selection;
- old regression/share target optimization.

## Acceptance For A Clean Walk-Forward

A clean binary walk-forward run must write:

```text
run_config.json
trials.parquet
window_metrics.parquet
validation_scores.parquet
prediction_scores.parquet
selected_windows.parquet
report.md
```

Every report must show:

```text
target
feature scope
window mode
EMA timeframe if used
train/validation/prediction window counts
skipped window count and reason
decision threshold
precision
recall
false-positive rate
predicted-positive rate
decision cost per row
TP/FP/FN/TN
```

This is the minimum standard before any result is considered comparable.

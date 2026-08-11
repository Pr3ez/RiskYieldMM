# RPF Signal Bank Batch Selection

## Purpose

Define the causal batch-selection method for training UP/DOWN gate models from
historical clean-signal batches instead of only the most recent chronological
window.

## Current Status

Status: `rejected_for_current_gate_training_shape`.

The implementation is available in:

```text
regression_feature_engineering/walkforward/signal_bank.py
```

and is exposed through:

```bash
python -m regression_feature_engineering.walkforward.regime_gate \
  --window-mode signal_bank
```

The first implemented modes are:

```text
chronological_recent
signal_bank
hybrid_recent_signal_bank
```

First pure `signal_bank` validation:

```text
test_output/rpf_regime_gate/20260616_031453_regime_gate_future_down_dominant
```

The maturity audit passed, but the model did not produce a useful gate. It
suppressed all paired DOWN classifier positives and produced too many false
positives against `future_down_dominant`. Do not rerun the same pure
signal-bank configuration unchanged.

The first `hybrid_recent_signal_bank` DOWN run was also stopped early after
three completed trials because it showed weaker objective evidence than the
sparse chronological calendar gate while giving back false positives.

The active replacement is the separate decision-bank planner:

```bash
python -m regression_feature_engineering.walkforward.decision_bank
```

That planner keeps the target model bank and the gate/trust bank separate.

## Scope

Initial scope is `BTCUSDT 8h/B` regime-gate experiments for:

```text
future_up_dominant
future_down_dominant
```

The method is designed for `regression_path_features_v1` and
`distance_horizon_vol_v2` labels. Two-sided and low-edge gate targets remain
chronological-only until their batch-bank definitions are explicitly validated.

## Source Of Truth

- Signal-bank selector: `regression_feature_engineering/walkforward/signal_bank.py`
- Separate-bank planner: `regression_feature_engineering/walkforward/decision_bank.py`
- Gate runner: `regression_feature_engineering/walkforward/regime_gate.py`
- Gate tracker: `rpf_regime_gate_implementation_todo.md`
- Current state: `current_feature_state.md`
- Output artifacts:
  - `batch_signal_inventory.parquet`
  - `window_signal_bank.parquet`

## What This Does Not Decide

This doc does not promote signal-bank training, choose final thresholds, or
authorize label leakage. It defines the first causal implementation contract.

## Causal Rule

For prediction batch `P`, a historical candidate batch is allowed only when:

```text
label_window_batch_id_max <= P - 1 - label_maturity_embargo_batches
```

This means the candidate batch's future label window must be fully mature
before the prediction batch. Prediction-batch labels are never used for
selection, training, validation, threshold selection, or model fitting.

## Batch Inventory

The signal bank builds one batch-level inventory from hvol v2 labels:

```text
batch_id
rows
label_window_batch_id_max
up_dom_rate
down_dom_rate
mixed_rate
extreme_total_mean
up_extreme_mean
down_extreme_mean
```

Dominant rates are:

```text
up_dom_rate   = mean(up_extreme >= 2 * down_extreme)
down_dom_rate = mean(down_extreme >= 2 * up_extreme)
```

These rates are labels, but they are allowed for selecting historical training
batches only after their label windows are mature.

## Window Modes

`chronological_recent` keeps the existing frozen walk-forward train/validation
batches unchanged.

`signal_bank` replaces train/validation batches with clean historical batches:

```text
positive train batches: target-side dominant rate >= positive_batch_min_rate
negative train batches: target-side dominant rate <= opposite_batch_max_rate
validation batches: most recent mature clean positives/negatives
training batches: next older mature clean positives/negatives
```

`hybrid_recent_signal_bank` adds recent mature chronological batches to the
signal-bank train/validation selection.

## First Command

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
DOWN_CLS_RUN="$(ls -td test_output/rpf_clean_classification/*classification_cls_extreme_down_ge_2x_up_hvol_v2 | head -1)"

"$PY" -m regression_feature_engineering.walkforward.regime_gate \
  --asset BTCUSDT \
  --root 8h/B \
  --gate-target future_down_dominant \
  --base-run "$READINESS_RUN" \
  --feature-ablation only_regime_calendar_state \
  --window-mode signal_bank \
  --positive-batch-min-rate 0.8 \
  --opposite-batch-max-rate 0.2 \
  --train-positive-batches 80 \
  --train-negative-batches 160 \
  --val-positive-batches 20 \
  --val-negative-batches 40 \
  --candidate-lookback-batches 2000 \
  --label-maturity-embargo-batches 1 \
  --classifier-score-path "$DOWN_CLS_RUN/prediction_scores.parquet" \
  --classifier-side down \
  --n-steps 50 \
  --max-configs 12 \
  --threshold-mode validation_sweep \
  --objective-metric validation_decision_cost \
  --fp-cost 5 \
  --fn-cost 1 \
  --min-validation-recall 0.05 \
  --min-validation-predicted-positive-rate 0.02 \
  --iterations-choices 400,800 \
  --depth-choices 2,3 \
  --learning-rate-choices 0.01,0.02 \
  --l2-leaf-reg-choices 10,30 \
  --early-stopping-rounds-choices 100 \
  --od-wait-choices 100 \
  --task-type GPU
```

## Required Artifacts

Every signal-bank run must write:

```text
batch_signal_inventory.parquet
window_signal_bank.parquet
trials.parquet
window_metrics.parquet
gate_scores.parquet
gated_decision_metrics.parquet
report.md
best_config.json
stage_status.json
```

`window_signal_bank.parquet` must prove:

- selected train/validation batch IDs;
- mature cutoff batch ID;
- positive/negative candidate counts;
- selected positive/negative counts;
- max selected label-window batch ID;
- selected train/validation target rates for audit only.

## Acceptance Criteria

Signal-bank selection is useful only if it improves the current DOWN calendar
gate tradeoff:

```text
current false positives: 1286 -> 0
current true positives: 833 -> 60
current recall retained: 7.2%
```

The next candidate must keep false positives materially lower while retaining
more useful true positives than the sparse chronological gate.

## First Result

Pure `signal_bank` with `positive_batch_min_rate=0.8` and
`opposite_batch_max_rate=0.2` was temporally safe but predictively rejected:

```text
train maturity violations: 0
validation maturity violations: 0
gate future_down_dominant TP/FP: 31 / 449
gate future_down_dominant precision: 0.065
gate future_down_dominant false-positive rate: 0.054
gated DOWN classifier TP/FP: 0 / 0
```

Rejected next candidates:

```text
hybrid_recent_signal_bank
signal_bank + regime-similarity ranking
less diluted positive/negative train ratios
threshold constraints that require nonzero gated classifier recall
```

Current next candidate:

```text
separate target-event bank + classifier-outcome gate-trust bank
```

Use `rpf_separate_decision_banks.md` for the next commands.

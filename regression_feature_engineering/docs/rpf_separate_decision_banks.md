# RPF Separate Decision Banks

## Purpose

Define the next RPF decision-layer workflow: separate historical data banks for
the main UP/DOWN target classifier and for the gate/trust classifier.

## Current Status

Status: `implemented_planning_audit`.

The planning command exists:

```bash
python -m regression_feature_engineering.walkforward.decision_bank
```

It does not train a model yet. It builds and audits two independent historical
batch banks:

- target-event bank: clean historical UP/DOWN event and non-event batches for
  the main binary classifier;
- gate-trust bank: historical classifier-fired batches split into true-positive
  trust examples and false-positive reject examples.

This replaces the failed first pure `signal_bank` gate direction. The rejected
pure signal-bank trained the gate against raw `future_down_dominant` labels; the
separate gate bank trains the gate against classifier behavior, which is the
actual failure mode we need to control.

## Scope

Initial scope remains:

```text
asset: BTCUSDT
root:  8h/B
feature_set: regression_path_features_v1
target_variant: distance_horizon_vol_v2
```

The first sides are:

```text
up
down
```

The paired binary targets remain:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

## Source Of Truth

- Bank planner: `regression_feature_engineering/walkforward/decision_bank.py`
- Binary classifier scores: `prediction_scores.parquet`
- Prior signal-bank selector: `regression_feature_engineering/walkforward/signal_bank.py`
- Gate runner: `regression_feature_engineering/walkforward/regime_gate.py`
- Tracker: `rpf_regime_gate_implementation_todo.md`
- Current state: `current_feature_state.md`

## What This Does Not Decide

This doc does not promote a gate, select final model parameters, or authorize
target leakage. The bank planner only proves whether enough mature historical
target and classifier-outcome examples exist before a heavier training command
is added.

## Why Separate Banks

The target classifier and the gate classifier solve different problems.

Target classifier:

```text
Question: is a clean UP/DOWN event likely?
Training positives: clean historical target-side events.
Training negatives: clean historical opposite/non-event conditions.
```

Gate classifier:

```text
Question: should we trust the target classifier when it fires?
Training positives: historical classifier-fired rows that became true positives.
Training negatives: historical classifier-fired rows that became false positives.
```

This matters because a raw future-dominance gate can learn the wrong target. We
do not only need to know whether future DOWN dominance happened. We need to know
when the DOWN classifier's active signal is likely to be correct.

## Causal Rule

For prediction batch `P`, every selected historical candidate must satisfy:

```text
candidate_label_or_score_batch <= P - 1 - label_maturity_embargo_batches
```

For the target-event bank this is checked with:

```text
label_window_batch_id_max
```

For the gate-trust bank this is checked with:

```text
score_pred_batch_id_max
```

The prediction batch itself is never used for bank selection, training,
validation, threshold selection, or clipping.

## Output Artifacts

The planner writes under:

```text
test_output/rpf_decision_banks/<run_id>/
```

Artifacts:

```text
events.jsonl
stage_status.json
bank_config.json
target_signal_inventory.parquet
gate_trust_inventory.parquet
separate_bank_plan.parquet
report.md
```

`separate_bank_plan.parquet` is the main audit file. It records per prediction
window:

- target train/validation batch IDs;
- gate train/validation batch IDs;
- selected positive/negative target-bank counts;
- selected trust/reject gate-bank counts;
- weighted target rates;
- weighted gate precision and false-positive rates;
- maturity violations;
- target-bank usability flag;
- gate-bank usability flag.

## First Planning Commands

Prepare the latest readiness and classifier score paths:

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
UP_CLS_RUN="$(ls -td test_output/rpf_clean_classification/*classification_cls_extreme_up_ge_2x_down_hvol_v2 | head -1)"
DOWN_CLS_RUN="$(ls -td test_output/rpf_clean_classification/*classification_cls_extreme_down_ge_2x_up_hvol_v2 | head -1)"
```

Plan the DOWN-side banks:

```bash
"$PY" -m regression_feature_engineering.walkforward.decision_bank \
  --asset BTCUSDT \
  --root 8h/B \
  --side down \
  --base-run "$READINESS_RUN" \
  --classifier-score-path "$DOWN_CLS_RUN/prediction_scores.parquet" \
  --classifier-threshold 0.5 \
  --n-steps 50 \
  --target-positive-batch-min-rate 0.8 \
  --target-opposite-batch-max-rate 0.2 \
  --target-train-positive-batches 80 \
  --target-train-negative-batches 160 \
  --target-val-positive-batches 20 \
  --target-val-negative-batches 40 \
  --gate-min-active-rows 10 \
  --gate-trust-min-precision 0.7 \
  --gate-reject-min-fp-rate 0.7 \
  --gate-train-trust-batches 80 \
  --gate-train-reject-batches 160 \
  --gate-val-trust-batches 20 \
  --gate-val-reject-batches 40 \
  --candidate-lookback-batches 2000 \
  --label-maturity-embargo-batches 1
```

Plan the UP-side banks:

```bash
"$PY" -m regression_feature_engineering.walkforward.decision_bank \
  --asset BTCUSDT \
  --root 8h/B \
  --side up \
  --base-run "$READINESS_RUN" \
  --classifier-score-path "$UP_CLS_RUN/prediction_scores.parquet" \
  --classifier-threshold 0.5 \
  --n-steps 50 \
  --target-positive-batch-min-rate 0.8 \
  --target-opposite-batch-max-rate 0.2 \
  --target-train-positive-batches 80 \
  --target-train-negative-batches 160 \
  --target-val-positive-batches 20 \
  --target-val-negative-batches 40 \
  --gate-min-active-rows 10 \
  --gate-trust-min-precision 0.7 \
  --gate-reject-min-fp-rate 0.7 \
  --gate-train-trust-batches 80 \
  --gate-train-reject-batches 160 \
  --gate-val-trust-batches 20 \
  --gate-val-reject-batches 40 \
  --candidate-lookback-batches 2000 \
  --label-maturity-embargo-batches 1
```

## Acceptance Criteria

The planner is usable for the next model-training phase only if:

- `target_bank_usable_window_rate` is high enough for the selected 50 windows;
- `gate_bank_usable_window_rate` is high enough for the selected 50 windows;
- `any_maturity_violations` is false;
- gate-bank reject examples are actual classifier false positives;
- gate-bank trust examples are actual classifier true positives;
- selected bank counts are stable enough that the next trainer does not depend
  on one or two isolated batches.

If the gate bank is sparse, lower `gate_min_active_rows`, lower
`gate_trust_min_precision`, lower `gate_reject_min_fp_rate`, or reduce requested
gate train/validation batch counts before adding another heavy training loop.

## Next Implementation Step

After the planner shows sufficient mature examples, add the training commands:

- target classifier with `target_bank_train_ids` and `target_bank_val_ids`;
- gate classifier with `gate_bank_train_ids` and `gate_bank_val_ids`;
- final decision join that reports ungated/gated precision, recall,
  false-positive reduction, recall retained, both-suppressed rate, and
  both-active conflict rate.

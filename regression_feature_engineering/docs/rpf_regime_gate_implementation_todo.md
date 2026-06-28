# RPF Regime Gate Implementation TODO

## Purpose

Track the implementation and validation work for live-safe regime-gated RPF
UP/DOWN predictions.

## Current Status

Status: `validated_plumbing`.

The first RPF-native gate command has been added:

```bash
python -m regression_feature_engineering.walkforward.regime_gate
```

It trains CatBoost gate classifiers from live-safe RPF features, writes
row-level gate scores, and can evaluate a gate against row-level binary
classifier score files when those files are available.

First smoke run completed successfully as a plumbing check:

```text
test_output/rpf_regime_gate/20260615_164318_regime_gate_future_up_dominant
```

The run wrote every required artifact and produced `1,200` row-level gate
scores across prediction batches `5852` through `5856`, with no duplicate
`trial_number,timestamp,batch_id` keys. It is **not** signal evidence: the
single smoke trial was rejected for `low_prediction_unique`, selected threshold
`0.55`, and activated no prediction rows.

The first 15-step gate sweep also completed for both `future_up_dominant` and
`future_down_dominant` across the five planned feature scopes. Post-hoc joins
against the refreshed 50-step binary classifier score files were written to:

```text
test_output/rpf_regime_gate/posthoc_gate_decision_analysis/
```

Current interpretation:

- `future_down_dominant / only_regime_calendar_state` is the only useful
  candidate so far. On the 15-step overlap it reduced DOWN classifier false
  positives from `339` to `0` and retained `60 / 261 = 23.0%` of true
  positives. This is strict but potentially useful.
- Other DOWN gate scopes either collapsed to zero useful classifier positives
  or kept too few true positives with worse precision.
- All `future_up_dominant` gate scopes collapsed to zero active classifier
  positives on the 15-step prediction overlap. Treat those as rejected in the
  current threshold/objective shape until anti-collapse threshold constraints
  are tested.

The 50-step native confirmation of the DOWN calendar gate completed:

```text
test_output/rpf_regime_gate/20260616_021308_regime_gate_future_down_dominant
```

Result:

- selected trial: `2`
- selected threshold: `0.70`
- gate active rate: `0.005`
- active prediction windows: `1 / 50`, only batch `5855`
- DOWN classifier false positives: `1286 -> 0`
- DOWN classifier true positives: `833 -> 60`
- false-positive reduction: `100%`
- recall retained: `7.2%`
- gated precision: `1.0`

Interpretation: this is a clean high-precision suppressor, not a stable broad
regime gate yet. It is too sparse for promotion and needs an anti-collapse
threshold/objective pass before any 100-step confirmation.

The first pure signal-bank DOWN run completed:

```text
test_output/rpf_regime_gate/20260616_031453_regime_gate_future_down_dominant
```

Structural result:

- `window_mode`: `signal_bank`
- signal-bank audit rows: `50`
- train maturity violations: `0`
- validation maturity violations: `0`
- selected train batches per step: `240`
- selected validation batches per step: `60`
- eligible historical candidates per step: `1999`
- clean DOWN candidate count per step: roughly `452-459`
- clean negative candidate count per step: roughly `918-931`

Signal result:

- selected trial: `11`
- selected threshold: `0.50`
- gate prediction false positives against `future_down_dominant`: `449`
- gate prediction true positives against `future_down_dominant`: `31`
- gate prediction precision against `future_down_dominant`: `0.065`
- gate prediction false-positive rate against `future_down_dominant`: `0.054`
- gated DOWN classifier true positives: `833 -> 0`
- gated DOWN classifier false positives: `1286 -> 0`

Interpretation: pure clean-label signal-bank sampling is temporally valid but
not useful in this first configuration. It suppresses all classifier positives
and does not generalize to recent prediction batches. Do not promote this
configuration.

The first `hybrid_recent_signal_bank` DOWN run was interrupted after three
completed trials:

```text
test_output/rpf_regime_gate/20260616_043723_regime_gate_future_down_dominant
```

Partial evidence was weaker than the sparse chronological DOWN calendar gate:

```text
best visible validation decision cost per row: 0.343688
prediction false-positive rate:              0.01637
```

Next active direction is separate target/gate decision-bank planning:

```bash
python -m regression_feature_engineering.walkforward.decision_bank
```

The planner builds target-event banks for the main classifier and gate-trust
banks from historical classifier true-positive/false-positive behavior.

## Scope

Initial scope:

```text
asset: BTCUSDT
root:  8h/B
feature_set: regression_path_features_v1
target_variant: distance_horizon_vol_v2
```

Active binary prediction targets remain:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

Gate research targets:

```text
future_up_dominant
future_down_dominant
future_two_sided
future_low_edge
```

## Source Of Truth

- Gate runner: `regression_feature_engineering/walkforward/regime_gate.py`
- Binary runner: `regression_feature_engineering/walkforward/classify.py`
- Gate plan: `rpf_regime_gated_prediction_plan.md`
- Signal-bank batch selection: `rpf_signal_bank_batch_selection.md`
- Separate decision banks: `rpf_separate_decision_banks.md`
- Binary experiment notes: `rpf_binary_classification_experiment.md`
- Current state: `current_feature_state.md`
- Output root: `test_output/rpf_regime_gate/`

## What This Does Not Decide

This tracker does not promote a gate, binary target, threshold, feature scope,
or trading rule. It records implementation state and the exact validation path.

## Status Values

Use only these status values:

```text
planned
implemented_unvalidated
validated_plumbing
validated_signal
rejected
promoted_experimental
```

## Implementation Tracker

| Phase | Status | Command | Output Artifact | Acceptance Result | Next Action |
|---|---|---|---|---|---|
| Add regime-gate CLI | validated_plumbing | `python -m regression_feature_engineering.walkforward.regime_gate --help` | `regression_feature_engineering/walkforward/regime_gate.py` | Unit/compile checks passed | Keep command as active gate surface |
| Add row-level classifier scores | implemented_unvalidated | `python -m regression_feature_engineering.walkforward.classify ...` | `prediction_scores.parquet`, `validation_scores.parquet` | Pending rerun | Rerun UP/DOWN classifier configs before gated decision join |
| Gate label formulas | validated_plumbing | unit tests | `future_up_dominant`, `future_down_dominant`, `future_two_sided`, `future_low_edge` | Dominant and train-quantile targets covered | Keep thresholds train-window-only |
| Gate model artifacts | validated_plumbing | first smoke command below | `events.jsonl`, `stage_status.json`, `trials.parquet`, `window_metrics.parquet`, `gate_scores.parquet`, `gated_decision_metrics.parquet`, `report.md`, `best_config.json` | Smoke wrote all artifacts; no duplicate gate-score row keys | Run first signal sweep |
| Gated decision evaluation | validated_plumbing | post-hoc join against refreshed classifier scores | `test_output/rpf_regime_gate/posthoc_gate_decision_analysis/gated_decision_comparison.parquet` | Exact joins worked; metrics generated for each gate scope | Rerun best DOWN gate natively with `--classifier-score-path` |
| Regime signal validation | implemented_unvalidated | UP and DOWN gate targets across first feature scopes | timestamped `test_output/rpf_regime_gate/` dirs | DOWN regime-calendar gate confirmed zero FP but only 7.2% recall retained over 50 steps; UP gates collapsed | Add anti-collapse constraints and rerun constrained DOWN/UP gate search |
| Signal-bank batch selection | rejected | `--window-mode signal_bank` | `batch_signal_inventory.parquet`, `window_signal_bank.parquet` | Temporal safety passed, but first DOWN signal-bank run suppressed all classifier positives | Test `hybrid_recent_signal_bank` or regime analog filtering |
| Hybrid signal-bank batch selection | rejected | `--window-mode hybrid_recent_signal_bank` | `test_output/rpf_regime_gate/20260616_043723_regime_gate_future_down_dominant` | Interrupted after 3 trials; objective worse than sparse chronological gate and prediction FPR nonzero | Replace with separate target/gate decision-bank planning |
| Separate decision-bank planner | implemented_unvalidated | `python -m regression_feature_engineering.walkforward.decision_bank --help` | `regression_feature_engineering/walkforward/decision_bank.py` | Unit tests passed; real-data bank availability audit pending | Run UP/DOWN 50-step bank planning commands |
| EMA-regime classifier batch selection | rejected | `python -m regression_feature_engineering.walkforward.classify --window-mode ema_regime_bank ...` | `ema_regime_inventory_{timeframe}.parquet`, `window_ema_regime.parquet`, classifier score files | Plumbing passed, but EMA work is no longer active because it does not address the chronological classifier's per-window collapse | Do not rerun unless a new plan explicitly reopens EMA-regime selection |

## First Plumbing Command

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"

"$PY" -m regression_feature_engineering.walkforward.regime_gate \
  --asset BTCUSDT \
  --root 8h/B \
  --gate-target future_up_dominant \
  --base-run "$READINESS_RUN" \
  --feature-ablation only_regime_calendar_state \
  --n-steps 5 \
  --max-configs 1 \
  --iterations-choices 50 \
  --depth-choices 2 \
  --learning-rate-choices 0.02 \
  --l2-leaf-reg-choices 10 \
  --early-stopping-rounds-choices 20 \
  --od-wait-choices 20 \
  --threshold-mode validation_sweep \
  --objective-metric validation_decision_cost \
  --fp-cost 5 \
  --fn-cost 1 \
  --task-type GPU
```

## First Signal Sweep

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"

for GATE_TARGET in future_up_dominant future_down_dominant; do
  for SCOPE in \
    only_regime_calendar_state \
    group_volatility_state+temporal_memory_transforms+rejection_chop \
    group_structural_room+acceptance_persistence+spike_breakout+liquidity_volume_pressure \
    group_structural_room+liquidity_volume_pressure+interaction_confluence \
    all
  do
    "$PY" -m regression_feature_engineering.walkforward.regime_gate \
      --asset BTCUSDT \
      --root 8h/B \
      --gate-target "$GATE_TARGET" \
      --base-run "$READINESS_RUN" \
      --feature-ablation "$SCOPE" \
      --n-steps 15 \
      --max-configs 12 \
      --threshold-mode validation_sweep \
      --objective-metric validation_decision_cost \
      --fp-cost 5 \
      --fn-cost 1 \
      --iterations-choices 400,800 \
      --depth-choices 2,3 \
      --learning-rate-choices 0.01,0.02 \
      --l2-leaf-reg-choices 10,30 \
      --early-stopping-rounds-choices 100 \
      --od-wait-choices 100 \
      --task-type GPU
  done
done
```

## Acceptance Rules

A gate can move to `validated_signal` only if it:

- uses live-safe RPF features only;
- writes every required artifact under a timestamped run directory;
- lowers false-positive rate for the paired UP/DOWN classifier;
- retains useful recall;
- does not collapse predicted positives to near zero;
- improves or preserves precision after gating;
- keeps both-active conflicts measurable rather than hidden.

## Signal-Bank DOWN Validation Command

Use this to test whether clean historical DOWN-signal batches improve recall
without giving back the false-positive control from the sparse chronological
gate:

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

## Current Caveat

Existing classifier runs created before row-level score output cannot be joined
by `timestamp,batch_id`. Rerun the selected UP/DOWN classifier configs with the
updated classifier runner to produce `prediction_scores.parquet` before using
`--classifier-score-path`. If the score file contains multiple classifier
trials, the gate runner reads the adjacent `best_config.json`; otherwise pass
`--classifier-trial-number` explicitly.

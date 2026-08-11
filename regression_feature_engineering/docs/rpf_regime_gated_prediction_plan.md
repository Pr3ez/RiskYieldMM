# RPF Regime-Gated Prediction Plan

## Purpose

Define the current next step after the RPF binary-classification and
regime/label diagnostics: keep both UP and DOWN targets, then learn when each
target's prediction should be trusted.

## Current Status

The RPF feature surface is engineering-valid, but not predictively promoted.
The binary `2x` extreme targets are implemented and have completed exploratory
15-step and 50-step runs on `BTCUSDT 8h/B`.

The latest diagnostic evidence says global performance is not the right
decision surface. UP and DOWN prediction quality changes by market regime,
future path composition, and label imbalance. The next valid milestone is a
live-safe regime gate, not dropping one side of the target pair.

## Scope

Primary benchmark:

```text
asset: BTCUSDT
root:  8h/B
feature_set: regression_path_features_v1
target_variant: distance_horizon_vol_v2
```

Active binary targets:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

Regression/share targets remain part of the broader RPF workflow, but this doc
focuses on stable trading-decision classification and gating.

## Source Of Truth

- Binary runner: `regression_feature_engineering/walkforward/classify.py`
- Regime-gate runner: `regression_feature_engineering/walkforward/regime_gate.py`
- Clean regression runner: `regression_feature_engineering/walkforward/optimize.py`
- RPF feature roots: the canonical RPF feature root defined in
  `data_contract.md`
- Hvol v2 labels: `data/htf_multiasset/{asset}/htf_4class_labels_reg_distance_horizon_vol_v2/1m/`
- Binary classification notes: `rpf_binary_classification_experiment.md`
- Gate implementation tracker: `rpf_regime_gate_implementation_todo.md`
- Signal-bank batch selection: `rpf_signal_bank_batch_selection.md`
- Current feature state: `current_feature_state.md`

Current local diagnostic artifacts:

```text
test_output/rpf_clean_classification_objective_15step/
test_output/rpf_clean_classification/regime_target_quality_analysis/
test_output/rpf_clean_classification/label_quality_correlation_analysis/
```

## What This Does Not Decide

This doc does not promote a model, choose final thresholds, or allow
future-label values into live features. Same-batch labels and actual
prediction-batch returns are post-hoc diagnostics only.

## Diagnostic Evidence

The true 50-step selected runs use prediction batches `5807` through `5856`
and `group_structural_room+liquidity_volume_pressure+interaction_confluence`
features.

For `target_cls_extreme_up_ge_2x_down_hvol_v2`:

- global prediction positive rate is low;
- in actual up batches, precision was clean but recall remained weak;
- in actual down batches, UP false positives were concentrated and harmful;
- label diagnostics show that UP loss worsens when upside-dominant labels are
  common, which means the model under-detects high-upside regimes.

For `target_cls_extreme_down_ge_2x_up_hvol_v2`:

- prediction quality changes strongly with actual/prior trend context;
- downside precision improves when downside-dominant labels are common, but the
  model still underpredicts positives;
- label diagnostics show strong dependence on future up/down imbalance and
  path composition.

Key report files:

```text
test_output/rpf_clean_classification/regime_target_quality_analysis/true50_regime_quality_report.md
test_output/rpf_clean_classification/label_quality_correlation_analysis/true50_label_quality_correlation_report.md
```

## Gating Principle

Keep four conceptual outputs separate:

```text
P(up_extreme >= 2x down_extreme)
P(down_extreme >= 2x up_extreme)
up_gate_score
down_gate_score
```

Optionally add:

```text
two_sided_risk_score
no_edge_score
```

Use UP predictions only when the live-safe gate says the environment supports
upside-dominant path reach. Use DOWN predictions only when the live-safe gate
says the environment supports downside-dominant path reach. Suppress both
when the environment is mixed, noisy, or two-sided unless the trading logic is
explicitly designed for two-sided path risk.

## Live-Safe Gate Candidates

Gate features must be available at prediction time. They may use current and
prior closed-bar RPF/OHLCV context, but not future labels or actual
prediction-batch returns.

Candidate gate inputs:

- prior trend: `prior_10b_return`, `prior_20b_return`, `prior_50b_return`
  equivalents from causal RPF features;
- volatility/range state: `rpf_vol_*`, `rpf_mem_vol_*`, `rpf_chop_*`,
  `rpf_regime_*`;
- structural location: `rpf_room_*`, Donchian/value distance, drawdown-style
  causal proxies;
- directional pressure: `rpf_accept_*`, `rpf_spike_*`, `rpf_liq_*`;
- confluence: `rpf_conf_*`;
- relative context: `rpf_xasset_*`.

## Research Labels For Gate Training

These labels are allowed as supervised targets for a gate model, but never as
features:

```text
future_up_dominant    = up_extreme >= 2 * down_extreme
future_down_dominant  = down_extreme >= 2 * up_extreme
future_two_sided      = up_extreme high and down_extreme high
future_low_edge       = up_extreme low and down_extreme low
future_up_acceptance  = up_mean_high > down_mean_low
future_down_acceptance= down_mean_low > up_mean_high
```

## Evaluation Contract

Every gated run must report:

- ungated UP and DOWN metrics;
- gated UP and DOWN metrics;
- gate acceptance rate;
- false-positive rate;
- precision;
- recall;
- balanced accuracy;
- logloss/calibration diagnostics where probability quality matters;
- decision cost with high false-positive penalty;
- performance by prior trend, volatility/range, and structural-location
  buckets.

Promotion requires lower false-positive rate without collapsing predicted
positive rate to zero. A gate that only suppresses all trades is not useful.

## Implemented Command Surface

The first implementation is:

```bash
python -m regression_feature_engineering.walkforward.regime_gate
```

It:

1. loads RPF features and hvol v2 labels by exact `timestamp,batch_id`;
2. builds research-only gate targets from labels;
3. trains gate models using only live-safe RPF features;
4. scores each prediction batch with gate probabilities;
5. writes row-level `gate_scores.parquet`;
6. optionally joins gate scores to row-level UP/DOWN classifier predictions;
7. reports gated versus ungated metrics.

Start with fixed feature-family ablations, not per-feature selection. Only add
SHAP/panel selection after a family-level gate improves stability.

Existing classifier runs created before `prediction_scores.parquet` existed
cannot be joined by exact row key. Rerun selected UP/DOWN classifier configs
with the updated binary runner before using gate decision evaluation. When a
classifier score file contains multiple trials, the gate runner uses the
adjacent `best_config.json` or an explicit `--classifier-trial-number`.

## Signal-Bank Batch Selection

The first chronological gate found a clean but too-sparse DOWN suppressor. The
first follow-up path was causal signal-bank training:

```text
chronological_recent
signal_bank
hybrid_recent_signal_bank
```

For prediction batch `P`, signal-bank candidates must satisfy:

```text
label_window_batch_id_max <= P - 1 - label_maturity_embargo_batches
```

This allows historical labels to select clean train/validation batches only
after those labels are fully mature. It does not allow prediction-batch labels
or future labels to influence model fitting, threshold selection, or gate
activation.

The first pure `signal_bank` DOWN run and the interrupted
`hybrid_recent_signal_bank` DOWN run did not improve the useful gate tradeoff.
Treat them as rejected exploratory evidence in their current form.

## Separate Decision Banks

The active next path is:

```bash
python -m regression_feature_engineering.walkforward.decision_bank
```

This planner separates the two training problems:

```text
target-event bank:
    selected from mature clean UP/DOWN label batches;
    used for the main binary event classifier.

gate-trust bank:
    selected from mature historical classifier score rows;
    trust positives are classifier true positives;
    reject negatives are classifier false positives;
    used for the gate/trust classifier.
```

The reason is direct: the gate must learn when the classifier should be trusted
after it fires. A raw future-dominance gate can miss that failure mode because
it is not conditioned on classifier activity.

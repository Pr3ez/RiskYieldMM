# HTF Stage-1-v2 Fixed Policy Replay Design

Date: 2026-04-20
Owner: Codex
Tracking:
- Linear: `RIS-199`

## Purpose

Design a replay layer that allows:

- one frozen, combo-specific feature policy per `action_key`
- fair comparison of all combos on the same walkforward steps
- no repeated recursive feature selection on every step
- direct comparison between:
  - Stage-1 baseline full-feature results
  - Stage-1-v2 dynamic nested-selector results
  - Stage-1-v2 fixed-policy replay results

This design answers the current gap:

- we already have step-specific selected masks from the completed `8h/B` nested-selector run
- but those masks vary by step
- therefore we cannot yet claim how each combo would perform if it always used the same chosen mask

That requires a replay pass.

## Short Answer

The correct workflow is:

1. use completed nested-selector artifacts as historical evidence
2. build a versioned feature policy for each `action_key`
3. replay historical steps with those frozen combo-specific masks
4. score every combo on every step, even if it is not the winner
5. compare fixed-policy results against both:
   - baseline full features
   - dynamic per-step selector masks

## Why Replay Is Required

Current completed `8h/B` artifacts already store:

- baseline full-feature metrics for each combo on each step
- dynamic selected-mask metrics for each combo on each step
- the exact mask selected for that combo on that step

But they do **not** store:

- how `f2_v2_t4` would perform on all completed steps if it always used one fixed mask
- how `f2_v1_t6` would perform on all completed steps if it always used another fixed mask

That cannot be inferred exactly from the current run because predictions depend on retraining the model under that fixed feature set.

So:

- evidence discovery can reuse current artifacts
- fair fixed-mask comparison requires replay

## Existing Assets We Can Reuse

From the completed nested-selector run:

- per-step combo metrics:
  - `stage1_v2_combo_metrics.parquet`
- per-step feature evidence:
  - `stage1_v2_feature_importance_steps.parquet`
- explicit per-step selected masks:
  - `stage1_v2_selected_features.json`
- row-level baseline and selected predictions:
  - `stage1_v2_pred_batch_predictions_baseline.parquet`
  - `stage1_v2_pred_batch_predictions_selected.parquet`
- step completion gate:
  - `batch_metadata.json`

These are sufficient to build an initial feature policy for `8h/B` without rerunning selector discovery.

## Core Concepts

### 1. Feature Policy

A feature policy is a versioned rule set for one `action_key`.

It contains:

- `core_keep`
- `conditional_keep`
- `avoid`
- `final_mask`
- policy metadata and support counts

The replay path uses `final_mask`.

The other buckets remain useful for later debugging and policy refresh.

### 2. Policy Build Window

Policies must be built using only steps strictly before the replayed step or refresh boundary.

That means:

- retrospective analysis may use completed `8h/B` data to simulate policy refreshes
- but at replay step `t`, the effective mask version must be built only from steps `< t`

This keeps the replay live-safe.

### 3. Refresh Window

A policy should stay frozen for a bounded number of future steps.

Recommended initial rule:

- refresh every `25` steps

This gives:

- stable combo comparison inside a refresh window
- much lower cost than dynamic selector-per-step
- less policy staleness than one global mask for the entire run

## Proposed Workflow

### Phase A. Policy Discovery

Input:

- completed nested-selector artifacts for a root, for example:
  - `stage1_catboost_8h_b_v2_live`

Process:

For each `action_key`, compute per-feature statistics across completed steps:

- `selection_rate_all`
- `selection_rate_improved`
- `selection_rate_non_improved`
- `improved_selection_lift`
- `delta_accuracy_selected_lift`
- `delta_cde_selected_lift`
- support counts:
  - `selected_steps`
  - `selected_improved_steps`

Then classify:

- `core_keep`
  - repeated often
  - enough support
  - non-negative or positive lift
- `conditional_keep`
  - appears more on improved steps
  - useful but lower stability
- `avoid`
  - repeats often
  - negative lift on both accuracy and cross-direction error

Then produce `final_mask`.

### Phase B. Fixed Policy Replay

Input:

- one policy registry version
- same root
- same walkforward batch sequence

Process per step:

1. load fixed mask for each `action_key`
2. train each combo using only its frozen mask
3. predict the current `pred_batch`
4. score the current `pred_batch`
5. persist combo metrics for every combo
6. choose winner from replay metrics

No selector runs during replay.

### Phase C. Comparison

For each combo and each step, compare:

- baseline full features
- dynamic selected mask
- fixed-policy mask

This gives three comparable layers:

- `baseline`
- `dynamic_selected`
- `fixed_policy`

## Policy Registry Design

Recommended root-level file:

- `stage1_v2_feature_policy_registry.json`

Recommended structure:

```json
{
  "policy_version": "2026-04-20-8h-b-policy-v1",
  "artifact_contract_version": "2026-04-20-stage1-v2-fixed-policy-v1",
  "source_run_id": "stage1_catboost_8h_b_v2_live",
  "root": {
    "regime": "8h",
    "family": "B",
    "timeframe": "1m",
    "target": "target_4class"
  },
  "build_scope": {
    "completed_step_count": 186,
    "pred_batch_min": 5170,
    "pred_batch_max": 5355,
    "support_min_selected_steps": 40,
    "refresh_stride_steps": 25
  },
  "policy_rules": {
    "core_keep": {
      "selection_rate_all_min": 0.80,
      "delta_accuracy_selected_lift_min": 0.0,
      "delta_cde_selected_lift_min": 0.0
    },
    "conditional_keep": {
      "improved_selection_lift_min": 0.10,
      "selected_improved_steps_min": 10
    },
    "avoid": {
      "selection_rate_all_min": 0.80,
      "delta_accuracy_selected_lift_max": 0.0,
      "delta_cde_selected_lift_max": 0.0
    }
  },
  "combos": {
    "f2_v2_t4": {
      "mask_version": "f2_v2_t4_policy_v1",
      "mask_hash": "sha256:...",
      "core_keep": ["close", "high"],
      "conditional_keep": ["D_dist_bot5_low_w120"],
      "avoid": ["M_N_stochasticK_long_bnd"],
      "final_mask": ["close", "high", "D_dist_bot5_low_w120"],
      "support": {
        "steps_seen": 186,
        "improved_steps": 65
      }
    }
  }
}
```

## How To Build `final_mask`

Initial pragmatic rule:

`final_mask = core_keep + top conditional_keep`

with caps:

- minimum size:
  - `min_features_keep = 24`
- maximum size:
  - use a per-combo size derived from historical accepted masks
  - recommended initial statistic:
    - median `n_features_used` over steps where `apply_pruned_step = true`

This keeps the fixed mask aligned with the mask sizes that actually worked in the dynamic run.

## Replay Semantics

### Replay Unit

Replay scope remains:

- root
- timeframe
- target
- `action_key`
- `pred_batch`

### What Must Stay Identical To Original Stage-1

For fairness, replay must reuse:

- same walkforward step sequence
- same fold/training-window construction
- same CatBoost base params
- same combo triplet definition
- same labels and feature source for the root

Only the feature columns differ.

### Winner Choice During Replay

Replay should produce:

- combo-level scores for all combos
- a replay winner for that step

But replay winner must be stored as a separate contract:

- not overwrite the original baseline winner
- not overwrite the dynamic-selector winner

This keeps comparison explicit.

## Live-Safe Refresh Design

Recommended first implementation:

- build policy snapshots on a refresh grid
- each snapshot can only use prior completed steps

Example:

- replay steps `5170..5194` use policy built from history before `5170`
- replay steps `5195..5219` use policy built from history before `5195`
- replay steps `5220..5244` use policy built from history before `5220`

If historical support is insufficient at an early boundary:

- fallback to:
  - full feature set
  - or a looser policy threshold
  - or `top_k` historically selected features with positive lift only

The fallback must be recorded in metadata.

## Artifact Contract

### Root Level

Recommended new root artifacts:

- `stage1_v2_fixed_policy_registry.json`
- `stage1_v2_fixed_policy_build_summary.json`
- `stage1_v2_fixed_policy_refresh_log.parquet`
- `stage1_v2_fixed_policy_replay_progress.parquet`
- `stage1_v2_fixed_policy_combo_metrics_root.parquet`
- `stage1_v2_fixed_policy_winner_summary.parquet`
- `stage1_v2_fixed_policy_vs_baseline_root.parquet`
- `stage1_v2_fixed_policy_vs_dynamic_root.parquet`
- `stage1_v2_fixed_policy_run_summary.json`

### Step Level

Under each step:

- `stage1_v2_fixed_policy/`

Files:

- `stage1_v2_fixed_policy_step_summary.json`
- `stage1_v2_fixed_policy_combo_metrics.parquet`
- `stage1_v2_fixed_policy_predictions.parquet`
- `stage1_v2_fixed_policy_masks_applied.json`

The step combo metrics should include:

- `action_key`
- `pred_batch`
- `mask_version`
- `mask_hash`
- `n_features_used`
- `fixed_policy_accuracy`
- `fixed_policy_cross_direction_error`
- `fixed_policy_macro_f1`
- `fixed_policy_rank`
- optional deltas:
  - vs baseline
  - vs dynamic selected

## Minimal Code Touchpoints

### New

Recommended new modules:

- `scripts/htf_backtest/catboost/stage1_feature_policy.py`
  - build per-combo policy from completed v2 artifacts
- `scripts/htf_backtest/catboost/stage1_fixed_policy_replay.py`
  - run fixed-mask combo replay on a step sequence
- `scripts/analysis/htf_stage1_v2_policy_replay.py`
  - CLI entrypoint for policy build and replay orchestration

### Existing Files To Extend

- [stage1_v2_contract.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_v2_contract.py)
  - add fixed-policy artifact contract constants
- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)
  - do **not** mix this into the current nested-selector step loop first
  - keep replay separate for initial rollout
- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)
  - leave current live runner unchanged for now
  - if proven useful later, add a launcher bridge to the replay entrypoint

## Why Separate Replay First

Do not bolt fixed-policy replay directly into the current live runner yet.

Reasons:

- current `stage1_v2_execution_mode` is still selector-oriented:
  - `parity`
  - `nested_selector`
- replay is conceptually different:
  - no selector execution
  - mask registry lookup
  - periodic policy refresh
- a separate entrypoint is easier to validate against existing stored artifacts

After replay is stable, it can be folded back into the main launcher if needed.

## Comparison Matrix We Want At The End

For every completed step and every combo:

| Variant | Meaning |
| --- | --- |
| `baseline` | full original feature set |
| `dynamic_selected` | step-specific mask chosen by nested selector |
| `fixed_policy` | frozen combo-specific mask from policy registry |

This supports the exact questions we care about:

- does fixed-policy preserve most of the dynamic-selector gain?
- which combos become stronger or weaker under stable masks?
- do some combos require adaptivity while others are stable enough for frozen masks?
- which features are truly structural for a combo rather than just often selected?

## Expected Benefits

- much faster than nested-selector-per-step
- fair per-combo comparison under stable masks
- simpler downstream diagnostics
- easier feature-governance by combo
- easier ablation:
  - remove one policy family
  - rerun replay
  - measure effect directly

## Expected Risks

### Risk 1. Policy Staleness

Frozen masks may drift out of date.

Mitigation:

- periodic refresh
- compare fixed-policy replay vs dynamic-selector history

### Risk 2. Overfitting Policy To Historical Discovery Run

If policy rules are too tailored to one completed slice, replay may look better in-sample than out-of-sample.

Mitigation:

- use refresh windows
- keep support thresholds explicit
- require a holdout replay slice not used for initial policy build

### Risk 3. Carrying Forward Bad Repeaters

Some frequently selected features are already flagged as over-kept in `8h/B`.

Mitigation:

- make `avoid` a first-class bucket
- keep policy-build outputs inspectable

## Proposed Rollout

### Slice 1

Build-only:

- derive `stage1_v2_fixed_policy_registry.json` from completed `8h/B` artifacts
- no replay yet

### Slice 2

Replay one root:

- `8h/B`
- completed steps only
- all combos scored with frozen masks

### Slice 3

Comparison reports:

- baseline vs dynamic vs fixed-policy
- winner-change analysis
- per-combo stability analysis

### Slice 4

Wider rollout:

- other roots
- periodic refresh windows

## Recommended First Implementation Choice

Start with:

- one root:
  - `8h/B`
- one fixed-policy build from the completed steps we already have
- one replay over those same completed steps

This is enough to answer:

- whether fixed-policy replay preserves the gains from dynamic selection
- whether replay is fast enough to become the routine evaluation path

## Success Criteria

The design is successful if replay can answer all of the following with explicit artifacts:

1. For each combo, what is its performance under one stable mask?
2. Does fixed-policy replay retain most of the dynamic-selector benefit?
3. Which combos are stable under frozen masks and which require adaptive masking?
4. Which features are structural core features versus over-kept repeaters?

## Immediate Next Slice

Implement:

1. `stage1_feature_policy.py`
2. `stage1_v2_fixed_policy_registry.json` builder
3. `stage1_fixed_policy_replay.py`
4. one-root `8h/B` replay smoke over completed steps only


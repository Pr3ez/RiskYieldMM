# HTF Stage-1-v2 Design And Rollout

Date: 2026-04-20
Owner: Codex
Tracking:
- Linear: `RIS-199`

## Purpose

Design a new `Stage-1-v2` walkforward mode that performs:

- per-step combo evaluation
- nested, live-safe feature selection for each candidate combo
- baseline vs selected-feature replay for each combo
- winner selection after combo-specific feature selection
- direct persistence of feature-importance, mask, and prediction artifacts during the walkforward itself

The goal is to stop treating feature analysis as only a post-hoc diagnostics layer and instead collect the full model-and-data evidence during the actual walkforward.

## Current State

### Stage-1-v1

Current Stage-1 in:
- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)
- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)

Current behavior:
- fixed feature set
- evaluate combo triplet grid on historical folds
- predict next `pred_batch`
- choose winner by Stage-1 ranking
- persist step summaries and prediction payloads

This gives a clean predictive benchmark, but it does not answer:
- which features each combo actually needs
- whether a different feature mask would change the winning combo
- how feature selection affects `cross_direction_error`, `macro_f1`, and directional safety per combo

### Step-2

Current Step-2 in:
- [stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)
- orchestrated by [htf_walkforward_diagnostics.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_walkforward_diagnostics.py)

Current behavior:
- replay selected Stage-1 paths after Stage-1 is finished
- compute feature importance
- run recursive feature selection
- retrain filtered models
- compare baseline vs filtered models

This is useful, but it is post-hoc. It does not affect Stage-1 winner choice.

## Core Problem

Current workflow answers:
- which combo wins under a fixed feature set

It does not answer:
- which `combo + feature mask` wins for a given step

If the winning combo changes materially after feature selection, the current workflow hides that.

## Stage-1-v2 Objective

For each root, for each `pred_batch`, for each candidate combo:

1. evaluate baseline full-feature behavior on historical folds
2. perform feature selection using only data before `pred_batch`
3. derive a combo-specific selected feature mask
4. retrain the combo using the selected mask
5. predict the current `pred_batch` with both:
   - baseline full-feature model
   - selected-feature model
6. score both versions after realized labels are known
7. choose the per-step winner after combo-specific feature selection has already happened

This creates a richer and more correct dataset for later analysis.

## Non-Negotiable Constraints

1. No lookahead.
- Feature selection must use only historical folds before the current `pred_batch`.
- The current `pred_batch` must never influence the feature mask used to predict itself.

2. Stage-1-v1 must remain available.
- `Stage-1-v1` stays as the stable benchmark.
- `Stage-1-v2` is added as a new mode, not a silent replacement.

3. Artifact contracts must stay explicit.
- Every persisted mask and importance table must carry enough metadata to reproduce:
  - root
  - step
  - combo key
  - fold plan
  - selector config
  - feature-importance type

4. Storage must stay bounded.
- Persist aggregated importance and masks.
- Do not persist raw full SHAP tensors per row/fold unless explicitly needed for a narrow debug mode.

## Stage-1-v2 Algorithm

### Per Root

For each root:
- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

run the same walkforward process independently.

### Per Step

For each `pred_batch`:

1. Build allowed combo set.
- same triplet grid logic as Stage-1-v1 unless explicitly overridden

2. For each combo:
- build historical fold windows using only data before `pred_batch`
- train baseline fold models on the full feature set
- collect baseline fold metrics
- compute fold-level feature importance
- derive fold-level kept-feature candidates
- vote/aggregate to a step-level selected mask for that combo
- retrain the combo on the selected mask
- infer on current `pred_batch` with:
  - baseline model
  - selected-mask model
- score realized `pred_batch` rows for both variants

3. Rank candidates.
- choose winner from combo-specific selected-mask results
- optionally persist the baseline full-feature ranking beside the selected-mask ranking

4. Persist artifacts.

## Why This Is Better

This directly measures:
- which features help each combo
- which combos only become competitive after pruning
- which feature families reduce `cross_direction_error`
- whether data quality changes:
  - combo ranking
  - selected masks
  - directional safety
  - confidence structure

## Current vs Stage-1-v2

| Area | Current Stage-1-v1 | Proposed Stage-1-v2 |
|---|---|---|
| Winner choice | best combo on fixed features | best combo after combo-specific feature selection |
| Feature selection timing | post-hoc in Step-2 | nested inside live-safe walkforward |
| Feature importance | only for selected replay scopes later | collected during primary walkforward for every candidate combo |
| Baseline vs filtered comparison | post-hoc only | native per-step, per-combo artifact |
| Ability to analyze data effect | indirect | direct |
| Compute cost | lower | materially higher |
| Benchmark simplicity | higher | lower |

## Artifact Contract

### Per Step / Per Combo

Under each step directory, Stage-1-v2 should write:

- `stage1_v2_combo_metrics.parquet`
  - one row per combo
  - baseline metrics
  - selected-mask metrics
  - deltas

- `stage1_v2_feature_importance_steps.parquet`
  - aggregated feature importance for that combo on that step

- `stage1_v2_selected_features.json`
  - selected feature list
  - keep count
  - selector config hash
  - feature mask hash

- `stage1_v2_selector_fold_outputs.parquet`
  - fold-level selector summary
  - no raw huge tensors

- `stage1_v2_pred_batch_predictions_baseline.parquet`
- `stage1_v2_pred_batch_predictions_selected.parquet`

- `stage1_v2_step_summary.json`
  - selected winner
  - baseline winner
  - chosen comparison metric
  - whether the winner changed because of feature selection

### Per Root

At root level:

- `stage1_v2_progress.parquet`
- `stage1_v2_run_summary.json`
- `stage1_v2_feature_importance_global.parquet`
- `stage1_v2_feature_mask_global.parquet`
- `stage1_v2_feature_stability.parquet`
- `stage1_v2_baseline_vs_selected_root.parquet`
- `stage1_v2_winner_change_summary.parquet`

## Module-Level Change Plan

### 1. Launcher

Update:
- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)

Add:
- `--stage1-version v1|v2`
- explicit selector config overrides for v2
- v2 output subdir naming

### 2. Stage-1 runner

Update:
- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)

Add:
- a v2 orchestration path
- per-combo baseline and selected-mask evaluation
- winner selection on selected-mask results
- v2 artifact writing
- resume logic for v2 artifacts

### 3. Extract reusable selector kernel

Refactor from:
- [stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)

Target:
- new reusable selector module, for example:
  - `stage1_selector_kernel.py`

This kernel should expose:
- fold-level importance collection
- feature voting
- mask derivation
- filtered retrain/eval

Without:
- current heavy post-hoc orchestration assumptions
- winner-only / root-topk logic

### 4. Diagnostics

Update later:
- [htf_walkforward_diagnostics.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_walkforward_diagnostics.py)

Purpose after v2:
- aggregate Stage-1-v2 artifacts
- reduce redundant Step-2 recomputation where possible

Diagnostics should become thinner once Stage-1-v2 already emits the needed evidence.

## Selector Policy For v2

The first v2 implementation should stay narrower than current full diagnostics.

Recommended initial selector policy:
- selector method: recursive SHAP
- feature importance type: `PredictionValuesChange`
- bounded keep-count grid
- no full exhaustive dual-importance sweep inside v2 initial rollout

Rationale:
- keep v2 tractable
- prove correctness first
- add richer selector modes later

## Validation Gates

### Gate 1: v1 parity mode

Run v2 with selector disabled or pass-through mask.

Expectation:
- same predictions as v1
- same winners as v1
- same metrics as v1

This proves the new orchestration path itself does not break causality.

### Gate 2: no-lookahead proof

For selected smoke roots:
- verify selector inputs use only folds before `pred_batch`
- verify current `pred_batch` does not affect chosen mask

### Gate 3: artifact completeness

For each completed step:
- baseline metrics exist
- selected metrics exist
- feature mask exists
- importance summary exists
- winner summary exists

### Gate 4: resume safety

Interrupt and resume a v2 run.

Expectation:
- no duplicated step outputs
- no mixed partial step artifacts
- deterministic state reconstruction

### Gate 5: root-level smoke

Run on:
- one `8h` root
- one `24h` root
- one `7d` root

before any full all-root rollout.

## Rollout Phases

### Phase 0: design and schemas

Deliver:
- this plan
- artifact schema definitions
- config surface definition

### Phase 1: selector kernel extraction

Deliver:
- reusable selector kernel module
- unit tests for mask derivation and fold voting

### Phase 2: Stage-1-v2 orchestration

Deliver:
- v2 step loop in runner
- v2 artifact writing
- parity mode

### Phase 3: smoke validation

Deliver:
- one-root v1 vs v2 parity check
- one-root selected-mask experimental run

### Phase 4: multi-root experimental collection

Deliver:
- initial v2 runs on all six roots
- compare:
  - v1 combo winners
  - v2 combo+mask winners
  - accuracy
  - macro F1
  - cross-direction error

### Phase 5: diagnostics simplification

Deliver:
- reduce post-hoc recomputation where v2 already produced the same evidence

## Recommended Output Naming

New run ids should not overwrite v1:

- `stage1_catboost_8h_b_v2_live`
- `stage1_catboost_8h_c_v2_live`
- `stage1_catboost_24h_b_v2_live`
- `stage1_catboost_24h_c_v2_live`
- `stage1_catboost_7d_b_v2_live`
- `stage1_catboost_7d_c_v2_live`

## Risks

1. Compute cost explosion
- v2 is materially heavier than v1

2. Artifact size explosion
- must keep only aggregated feature analysis by default

3. Debug complexity
- more moving pieces per step

4. Benchmark drift
- if v2 replaces v1 too early, historical comparison becomes harder

## Recommendation

Proceed with `Stage-1-v2` as an additive research mode.

Do not replace `Stage-1-v1` yet.

Correct sequencing:
1. implement v2 in parallel
2. validate no-lookahead and parity behavior
3. collect first v2 experimental runs
4. only then decide whether v2 becomes the main evaluation path

## Immediate Next Actions

1. define the exact v2 artifact schemas in code-facing detail
2. extract the selector kernel from `stage1_step2.py`
3. add `stage1_version` and v2 config surface to the launcher
4. implement v2 parity mode first
5. run a one-root smoke test before broader rollout

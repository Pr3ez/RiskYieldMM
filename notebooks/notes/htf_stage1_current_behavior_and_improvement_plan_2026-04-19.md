# HTF Stage-1 Current Behavior And Improvement Plan

Date: 2026-04-19

## Purpose

This note captures what Stage-1 is currently doing in production for the HTF multiregime CatBoost walk-forward, what the expensive parts are, and which improvements are safest if we want faster analysis without weakening the generalization estimate.

Primary code paths:
- [htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)
- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)

## What Stage-1 Does Today

Stage-1 is the core predictive walk-forward evaluation. It is the part we should treat as the main generalization estimate.

Current launcher behavior:
- roots:
  - `8h/B`
  - `8h/C`
  - `24h/B`
  - `24h/C`
  - `7d/B`
  - `7d/C`
- timeframe: `1m`
- target: `target_4class`
- model: CatBoost on GPU
- default resume mode: `skip_completed`

Current runner behavior per root:
1. Resolve a candidate triplet grid from the Stage-1 portfolio metadata.
2. Build a root-specific override pointing at the current rebuilt `htf_with_helpers*` and `htf_4class_labels*` directories.
3. Run `run_walk_forward_stage1_grid(...)`.
4. For each prediction batch:
   - construct fold-CV windows
   - train/evaluate the active combo grid
   - select the winner combo on the pred batch
   - write step-level artifacts
5. Persist run-level summary and run-state metadata.

## Effective Current Search Space

Although the code supports adaptive probing and promotion, the current live runs are effectively using a fixed base grid.

Observed from current live run artifacts:
- combo count per step: `8`
- average probe candidates evaluated per step: `0.0` on all 6 roots
- dynamic combo registry: empty on current live runs

This means the actual live workload is currently:
- base grid only
- no effective archive probing
- no effective dynamic promoted triplets

## Current Step Artifacts

Each completed batch step writes:
- `stage1_step_summary.json`
- `stage1_combo_index.parquet`
- `stage1_fold_windows.parquet`
- `stage1_val_predictions.parquet`
- `stage1_pred_batch_predictions.parquet`
- `stage1_probe_log.parquet`
- `stage1_predecision_context.json`
- `stage1_predecision_context.parquet`
- `stage1_runtime_profile.json`

Example step artifact directory:
- [8h/B sample step](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live/catboost/1m/target_4class/batch_5170/stage1)

Observed sample step summary for `8h/B batch_5170`:
- combos evaluated: `8`
- fold windows completed: `21`
- cache hits: `2`
- cache misses: `19`
- runtime: `15.48s`
- winner quality pass: `False`
- probe tiers run: `0`
- probe candidates evaluated: `0`

## Current Live Run Metrics

From current `stage1_catboost_*_live/run_summary.json` artifacts:

### 8h
- `8h/B`
  - steps: `500`
  - total runtime: `7797.5s`
  - avg step runtime: `15.594s`
  - quality pass rate: `0.228`
  - quality unresolved rate: `0.772`
- `8h/C`
  - steps: `500`
  - total runtime: `8121.62s`
  - avg step runtime: `16.242s`
  - quality pass rate: `0.238`
  - quality unresolved rate: `0.762`

### 24h
- `24h/B`
  - steps: `500`
  - total runtime: `10777.11s`
  - avg step runtime: `21.553s`
  - quality pass rate: `0.184`
  - quality unresolved rate: `0.816`
- `24h/C`
  - steps: `500`
  - total runtime: `10943.0s`
  - avg step runtime: `21.885s`
  - quality pass rate: `0.128`
  - quality unresolved rate: `0.872`

### 7d
- `7d/B`
  - steps: `170`
  - total runtime: `10774.4s`
  - avg step runtime: `63.377s`
  - quality pass rate: `0.312`
  - quality unresolved rate: `0.688`
- `7d/C`
  - steps: `170`
  - total runtime: `11067.86s`
  - avg step runtime: `65.102s`
  - quality pass rate: `0.394`
  - quality unresolved rate: `0.606`

## What Is Actually Expensive

The cost center is repeated fold-CV combo training inside each step.

Evidence:
- per-step combo runtime profile for the sample step is dominated by combo execution
- sample step had:
  - `8` combos
  - `21` fold windows
  - only `2` cache hits vs `19` misses

So current cost is approximately:
- `steps`
  x `active combos`
  x `fold windows`
  x CatBoost train/eval

This is why:
- `7d` is much slower per step than `8h`
- diagnostics are slow after Stage-1, but Stage-1 itself is already a major compute block

## Important Current Findings

### 1. Adaptive probe path is effectively inactive

Current live runs show:
- `probe_candidates_evaluated = 0`
- `probe_tiers_run = 0`
- empty `stage1_dynamic_combo_registry.json`

Interpretation:
- adaptive probe/promotion is not currently adding real search breadth
- the runtime overhead from the probe system is small
- but the conceptual complexity remains

### 2. Quality threshold is usually not reached

Current unresolved rates:
- `8h`: about `76% to 77%`
- `24h`: about `82% to 87%`
- `7d`: about `61% to 69%`

Interpretation:
- the current thresholding logic labels most steps as unresolved
- but because probing is inactive, these unresolved steps do not trigger a meaningful expanded search

### 3. Current portfolio cap is already narrow

Current active combo count per step is `8`.

So the current runtime is not caused by a very wide candidate universe. It is caused by:
- repeated fold-CV training
- long history windows
- low training-cache reuse

## What We Should Not Change If We Want To Preserve Generalization

Avoid these as default speedups:
- reducing `n_steps`
- evaluating only a subset of roots that are part of the intended deployment portfolio
- replacing walk-forward with a shortcut metric for final quality claims

Those reduce runtime, but they also weaken the validity of the main estimate.

## Safe Improvement Options

These are ordered by impact and safety.

### A. Separate core evaluation from interpretability work

Keep full Stage-1 unchanged, but reduce reruns of downstream analysis:
- full Stage-1 walk-forward
- full causal analysis
- lighter default diagnostics

This gives faster iteration without weakening the actual predictive evaluation.

### B. Make Stage-1 cache reuse materially better

Current sample step shows:
- cache hits: `2`
- cache misses: `19`

Best technical target:
- improve train-model reuse across combos/folds inside the same step when window overlap is high

This is the safest internal speedup because it does not change the evaluated batches or target logic.

### C. Reassess the inactive probe architecture

Current system carries complexity for probing and promotion, but live runs show no practical contribution.

Possible actions:
- temporarily disable probe logic in routine runs if it remains inactive
- or fix archive/current candidate discovery so it actually contributes

This is worth inspecting before adding more complexity elsewhere.

### D. Add a two-tier operating mode

Recommended operating modes:

1. Full evaluation mode
- current full Stage-1 setup
- used for official comparisons

2. Fast iteration mode
- same `n_steps`
- same roots
- same candidate grid
- but skip expensive downstream diagnostics unless data or code changed materially

This preserves generalization while reducing repeated end-to-end wall time.

### E. Investigate why `24h` and `7d` quality unresolved rates are so high

If the threshold is too strict relative to realistic achievable accuracy, then:
- many steps become unresolved
- but no meaningful search expansion happens

That means the current quality gate may add reporting complexity without improving selection.

This should be tested analytically before changing the threshold.

## Recommended Next Plan

1. Measure Stage-1 runtime composition more systematically.
- Aggregate `stage1_runtime_profile.json` across roots.
- Quantify time in combo execution, IO, and fold-window generation.

2. Verify whether adaptive probing is dead or just starved.
- Check whether `current+archive` is actually exposing new candidates in the current live layout.
- If not, either fix it or simplify it.

3. Improve training-cache reuse before reducing evaluation breadth.
- This is the most promising speedup that should not weaken generalization.

4. Keep full `n_steps` for official runs.
- Speed up interpretation layers first.

5. Only if needed, introduce a clearly labeled fast-analysis mode.
- Same Stage-1 core
- lighter post-analysis

## Current Bottom Line

Stage-1 is currently:
- valid as the main walk-forward evaluation
- narrower than it looks, because effective search is only the base 8-combo grid
- expensive mainly because of repeated fold-CV combo training
- not benefiting in practice from the adaptive probe/promotion machinery

So the best improvement path is:
- do not shorten the evaluation first
- first improve cache reuse and remove ineffective complexity
- keep Stage-1 as the full generalization anchor

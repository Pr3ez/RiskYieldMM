# HTF Walk-Forward Diagnostics Reverification

Date: 2026-04-11

## Scope

This note re-checks the merged HTF walk-forward diagnostics output at:

- `/media/przem/linux_data/RiskYieldMM (Copy)/test_output/htf_walkforward_diagnostics/20260411_153744_merged`

The goal is to answer four questions cleanly:

1. What analysis did we actually run?
2. What data did it collect?
3. What do the merged results actually say?
4. What should we extract from it for the next iteration?

## What The Analysis Actually Did

The merged diagnostics stack covers the latest six HTF roots:

- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

On top of the current production HTF corpus from `notebooks/htf_pythonscript.py`, it combined four layers:

1. Workflow and artifact audit
   - production HTF data roots
   - Stage-1 walk-forward source roots
   - causal ensemble result roots
   - exact file dependencies and block coverage

2. Root profiles from existing walk-forward artifacts
   - evaluated batch ranges
   - class and direction distributions
   - majority-direction baseline
   - Stage-1 winner quality
   - incomplete-combo filtering

3. Step-2 feature analysis
   - scopes:
     - `winner_only`
     - `root_topk`
   - importance types:
     - `PredictionValuesChange`
     - `LossFunctionChange`
   - outputs:
     - feature importance stability
     - feature noise summary
     - action-key ranking
     - baseline-vs-filtered comparisons
     - winner-vs-near-winner overlap

4. Causal final-method comparison
   - direct baselines
   - safe ensemble methods
   - full-coverage and reduced-coverage ranking
   - directional accuracy and coverage

## What Data It Collected

Core merged outputs:

- `workflow_manifest.json`
- `root_profiles.csv|json|parquet`
- `cross_root_summary.csv|parquet`
- `causal_method_refresh.csv|parquet`
- `base_model_diagnostics.csv|parquet`
- `step2_aggregate_artifacts.csv|parquet`
- `winner_vs_near_winner_overlap.csv|parquet`
- `recommendations.csv|parquet`
- `research_sources.json`
- `run_summary.json`

Per-root Step-2 outputs exist for all `24/24` expected blocks:

- scopes:
  - `winner_only`
  - `root_topk`
- importance types:
  - `PredictionValuesChange`
  - `LossFunctionChange`
- roots:
  - all six HTF roots

Important per-root Step-2 artifacts:

- `baseline_vs_filtered_root.parquet`
- `feature_importance_stability.parquet`
- `feature_noise_summary.parquet`
- `top_features_by_combo.parquet`
- `action_key_ranking.parquet`

Merged validation:

- selected Step-2 blocks: `24`
- missing Step-2 blocks: `0`
- `step2_aggregate_artifacts.parquet`: `108` rows
- `winner_vs_near_winner_overlap.parquet`: `24` rows
- `recommendations.parquet`: `17` rows

## Verified Evaluation Windows

- `8h/B`: batches `5290..5669`, `380` eval batches, `91,200` eval rows
- `8h/C`: batches `5290..5669`, `380` eval batches, `91,200` eval rows
- `24h/B`: batches `1511..1890`, `378` eval batches, `272,160` eval rows
- `24h/C`: batches `1510..1889`, `380` eval batches, `273,600` eval rows
- `7d/B`: batches `221..270`, `50` eval batches, `252,000` eval rows
- `7d/C`: batches `223..270`, `48` eval batches, `241,920` eval rows

Incomplete-combo filtering affected only:

- `24h/B`: prediction batches `1866`, `1867`
- `7d/C`: prediction batches `171`, `172`

No root showed missing feature batches or missing label batches in the merged profile.

## What The Results Actually Say

### 1. Final causal prediction quality

Best full-coverage method per root:

- `8h/B`: `per_class_specialist` -> `0.515888`
- `8h/C`: `discounted_model_averaging` -> `0.543542`
- `24h/B`: `stacking_meta` -> `0.509634`
- `24h/C`: `uniform_direction_sum` -> `0.521630`
- `7d/B`: `diversity_subset` -> `0.517647`
- `7d/C`: `stacking_meta` -> `0.648070`

Direct baseline directional accuracy:

- `8h/B`: `0.504200`
- `8h/C`: `0.516557`
- `24h/B`: `0.491380`
- `24h/C`: `0.521630`
- `7d/B`: `0.504179`
- `7d/C`: `0.605646`

Gain vs direct baseline under best full coverage:

- `8h/B`: `+0.011689`
- `8h/C`: `+0.026985`
- `24h/B`: `+0.018254`
- `24h/C`: `+0.000000`
- `7d/B`: `+0.013468`
- `7d/C`: `+0.042423`

Reduced-coverage abstention methods only matter materially for:

- `8h/B`: `all_agree_direction` -> `0.562381` at `17.21%` row coverage
- `8h/C`: `all_agree_class` -> `0.640842` at `4.43%` row coverage

Interpretation:

- `7d/C` is the strongest full-coverage root by a wide margin.
- `8h/C` is the second-strongest full-coverage root.
- `24h/C` does not improve beyond the direct baseline, so extra ensemble complexity is not helping there yet.

### 2. Root difficulty and winner quality

Winner quality-pass rates:

- `8h/B`: `0.231579`
- `8h/C`: `0.244737`
- `24h/B`: `0.243386`
- `24h/C`: `0.165789`
- `7d/B`: `0.440000`
- `7d/C`: `0.604167`

Winner mean accuracy:

- `8h/B`: `0.520921`
- `8h/C`: `0.528410`
- `24h/B`: `0.517978`
- `24h/C`: `0.486630`
- `7d/B`: `0.626663`
- `7d/C`: `0.706229`

Interpretation:

- `7d/C` is not only better at the final ensemble layer; the underlying walk-forward winners are also materially stronger.
- `24h/C` is the weakest root by winner quality.
- `8h/B`, `8h/C`, and `24h/B` all have similar winner-quality weakness.

### 3. Importance-mode agreement is unusually strong

For `root_topk`, the top-10 features from `PredictionValuesChange` and `LossFunctionChange` are identical for every root:

- `8h/B`: identical top-10
- `8h/C`: identical top-10
- `24h/B`: identical top-10
- `24h/C`: identical top-10
- `7d/B`: identical top-10
- `7d/C`: identical top-10

This is one of the strongest verification signals in the whole analysis. It means the importance picture is not an artifact of one CatBoost importance mode.

### 4. Winner-vs-near-winner feature overlap is mostly absent

`winner_vs_near_winner_overlap.parquet` shows near-zero overlap for almost every root.

Observed pattern:

- `24h/B`: `0.0`
- `24h/C`: `0.0`
- `7d/B`: `0.0`
- `7d/C`: `0.0`
- `8h/B`: `0.0`
- `8h/C`: one strong overlap pair at `0.764706`

Interpretation:

- Most roots are combo-specific and brittle.
- `8h/C` is the only root that shows a meaningful shared feature core between winner and near-winner action keys.

### 5. Root-topk pruning is much more useful than winner-only pruning

Mean Step-2 pruning effect on accuracy for `root_topk`:

- `8h/B`: about `+0.0335` to `+0.0338`
- `8h/C`: about `+0.0285` to `+0.0289`
- `24h/B`: about `+0.0171` to `+0.0176`
- `24h/C`: about `+0.0222`
- `7d/B`: about `+0.0029`
- `7d/C`: about `+0.0014` to `+0.0025`

Mean features removed under `root_topk`:

- `8h/B`: `81` to `84`
- `8h/C`: `69` to `71`
- `24h/B`: `61` to `63`
- `24h/C`: `62` to `64`
- `7d/B`: `51`
- `7d/C`: `43` to `62`

Interpretation:

- Feature pruning is most valuable for `8h` and `24h`.
- `7d` roots already carry a stronger core signal, so pruning helps less.
- `root_topk` gives a clearer and more consistent benefit than `winner_only`.

### 6. The recurring high-risk features are consistent

Recurring null-heavy influential features:

- `X_D_fundingBasisPressure_xlong_pct`
- `X_D_fundingBasisPressure_long_pct`
- `X_D_basisRetPressure_long_pct`
- `D_dist_bot5_low_w120` in `8h/B` and `24h/B`

Recurring drifting influential features:

- `family_batch_id`
- `source_base_batch_id`

Most concerning root-specific cases:

- `8h/B`
  - `X_D_fundingBasisPressure_xlong_pct` null rate about `46.56%`
  - `D_dist_bot5_low_w120` null rate `50%`
- `24h/B`
  - `X_D_fundingBasisPressure_xlong_pct` null rate about `47.19%`
  - `D_dist_bot5_low_w120` null rate `16.67%`
- `7d/C`
  - `X_D_fundingBasisPressure_xlong_pct` null rate about `45.52%`
  - `family_batch_id` and `source_base_batch_id` drift score about `6.94`

Interpretation:

- The merged diagnostics are not just ranking roots; they are also repeatedly pointing to the same unstable or null-heavy feature families.

## Root-Level Takeaways

### 7d/C

Strengths:

- strongest final full-coverage method
- strongest direct baseline
- best winner quality-pass rate

Risks:

- strong reliance on structural timing fields:
  - `family_batch_id`
  - `family_bar_pos`
  - `source_base_batch_id`
  - `bar_in_batch_norm`
- still influenced by null-heavy funding-basis features

Interpretation:

- keep it
- treat it as the strongest root
- but audit whether part of the edge is phase structure rather than robust market-state signal

### 7d/B

Strengths:

- materially healthier than most non-`7d/C` roots
- decent full-coverage gain

Risks:

- same structural timing dependence pattern as `7d/C`
- weaker than `7d/C`
- winner-vs-near-winner overlap is still zero

Interpretation:

- keep it as the complementary weekly phase root
- improve data quality before expecting major ensemble gains

### 8h/C

Strengths:

- second-best full-coverage root
- best stability story
- only root with a real shared winner/near-winner feature core
- pruning gives strong benefit

Risks:

- still exposed to null-heavy `X_D_*` basis-pressure features
- `family_batch_id` is still influential

Interpretation:

- this is the best development root for feature and parameter work

### 8h/B

Strengths:

- pruning helps a lot
- reduced-coverage abstention can lift directional accuracy strongly

Risks:

- weak winner-quality pass rate
- `D_dist_bot5_low_w120` is still structurally problematic here
- winner-vs-near-winner overlap is zero

Interpretation:

- keep it for complementary coverage
- treat it as a cleanup + tuning root, not a trust-the-current-signal root

### 24h/C

Strengths:

- okay direct baseline
- pruning helps materially

Risks:

- no full-coverage causal gain over the direct baseline
- weakest winner-quality pass rate of all roots
- timing/drift fields remain prominent

Interpretation:

- base-model and feature-quality work should come before more ensemble work

### 24h/B

Strengths:

- modest full-coverage ensemble lift
- pruning helps

Risks:

- null-heavy influential features
- drift-heavy structural fields
- weak winner-quality pass rate

Interpretation:

- this root needs data-quality remediation first

## What We Should Extract From This

If all six roots must stay, the merged diagnostics support this development order:

1. Keep all six roots in the portfolio.
2. Treat `7d/C` as strongest but structurally audit it.
3. Use `8h/C` as the main root for feature-core and parameter development.
4. Treat `24h/B`, `24h/C`, and `8h/B` as cleanup-first roots.
5. Promote `root_topk` Step-2 pruning into the next research iteration, especially for `8h` and `24h`.
6. Audit and possibly redesign the repeatedly flagged feature families before broad parameter sweeps:
   - `X_D_fundingBasisPressure_*`
   - `X_D_basisRetPressure_*`
   - `D_dist_bot5_low_w120`
   - `family_batch_id`
   - `source_base_batch_id`

## Bottom Line

The merged diagnostics are coherent and worth trusting.

The strongest verified findings are:

- `7d/C` is the strongest current full-coverage root.
- `8h/C` is the healthiest root for development because it combines lift, pruning benefit, and actual feature-core stability.
- `24h/C` currently gets no value from extra ensemble complexity.
- `root_topk` pruning is a real signal, especially for `8h` and `24h`.
- the same null-heavy and drift-heavy features keep resurfacing, so data-quality debt is still directly influencing model behavior.

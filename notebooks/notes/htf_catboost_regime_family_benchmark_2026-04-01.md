# HTF CatBoost Regime/Family Benchmark - 2026-04-01

## Scope

Bounded CatBoost multiclass benchmark on the current production HTF `1m/target_4class`
helper outputs across:

- regimes: `8h`, `24h`, `7d`
- families: `B`, `C`

This is a **comparative probe**, not a fully optimized Stage-1 search.

Artifacts:

- `test_output/htf_catboost_regime_family_benchmark/summary_20260401.json`
- `test_output/htf_catboost_regime_family_benchmark/summary_table_20260401.csv`
- `scripts/analysis/htf_catboost_regime_family_benchmark.py`

## Method

- input root per unit: current `htf_with_helpers*/1m/target_4class`
- labels joined from the matching `htf_4class_labels*` root
- only **post-warmup** helper batches were used
- recent batch windows were capped to keep total row budgets comparable by regime:
  - `8h`: `1000` batches
  - `24h`: `333` batches
  - `7d`: `48` batches
- chronological batch split:
  - train `60%`
  - validation `20%`
  - test `20%`
- model:
  - `CatBoostClassifier`
  - `loss_function=MultiClass`
  - `auto_class_weights=Balanced`
  - shared parameters across all roots
- features used:
  - numeric saved model-facing columns only
  - metadata/id/date columns excluded

## Summary Ranking

### By macro F1

1. `24h/B` -> `0.3762`
2. `24h/C` -> `0.3069`
3. `8h/B` -> `0.2873`
4. `8h/C` -> `0.2702`
5. `7d/B` -> `0.2302`
6. `7d/C` -> `0.1747`

### By balanced accuracy

1. `24h/B` -> `0.3814`
2. `24h/C` -> `0.3070`
3. `8h/B` -> `0.2889`
4. `8h/C` -> `0.2800`
5. `7d/B` -> `0.2454`
6. `7d/C` -> `0.2305`

### By directional accuracy

1. `24h/B` -> `0.5480`
2. `8h/B` -> `0.5182`
3. `7d/B` -> `0.4907`
4. `24h/C` -> `0.4836`
5. `8h/C` -> `0.4780`
6. `7d/C` -> `0.4708`

## Per-Root Results

### 24h/B

- best overall unit in this benchmark
- accuracy: `0.4000`
- balanced accuracy: `0.3814`
- macro F1: `0.3762`
- weighted F1: `0.4022`
- log loss: `1.2866`
- directional accuracy: `0.5480`

Interpretation:

- strongest class separation of all six units
- both down and up classes are materially learnable
- current best candidate if one unit needs to be prioritized first

### 24h/C

- second best overall by balanced metrics
- accuracy: `0.3102`
- balanced accuracy: `0.3070`
- macro F1: `0.3069`
- directional accuracy: `0.4836`

Interpretation:

- weaker than `24h/B`, but still clearly better than the `7d` roots
- `C` shift costs useful signal here relative to `B`

### 8h/B

- mid-pack, but stronger than `8h/C`
- accuracy: `0.2946`
- balanced accuracy: `0.2889`
- macro F1: `0.2873`
- directional accuracy: `0.5182`

Interpretation:

- decent directional signal
- weaker class separation than `24h/B`
- current `B` family again beats `C`

### 8h/C

- slightly worse than `8h/B`
- accuracy: `0.2714`
- balanced accuracy: `0.2800`
- macro F1: `0.2702`
- directional accuracy: `0.4780`

Interpretation:

- class prediction is weaker than base `8h/B`
- no evidence here that the shifted family is preferable for 4-class prediction

### 7d/B

- raw accuracy looks high: `0.4187`
- but balanced accuracy and macro F1 are weak:
  - balanced accuracy: `0.2454`
  - macro F1: `0.2302`
- directional accuracy: `0.4907`

Interpretation:

- `7d/B` benefits from class imbalance on plain accuracy
- it predicts dominant classes much better than minority classes
- this is **not** a genuinely strong balanced 4-class model despite the headline accuracy

### 7d/C

- worst unit in the benchmark
- accuracy: `0.2578`
- balanced accuracy: `0.2305`
- macro F1: `0.1747`
- directional accuracy: `0.4708`

Interpretation:

- severe class imbalance / rarity problem in the test split
- `UP_BALANCED` had only `31` test rows here
- this root currently looks least promising for stable 4-class prediction

## Important Interpretation

Do **not** rank these units by raw accuracy alone.

That would be misleading because:

- `7d` roots are much more class-skewed
- raw accuracy rewards predicting dominant classes
- macro F1 and balanced accuracy are more informative here

For current 4-class predictive quality, the cleaner ordering is:

`24h/B` -> `24h/C` -> `8h/B` -> `8h/C` -> `7d/B` -> `7d/C`

## Structural Takeaways

1. `B` beats `C` in every regime in this benchmark.
2. `24h` is the strongest regime for balanced 4-class prediction.
3. `7d` currently looks weak for balanced 4-class classification even after class weighting.
4. The current saved feature set is usable enough to benchmark, but not all roots are equally learnable.

## Caveats

- This is a bounded benchmark, not a full walk-forward optimization.
- One shared CatBoost configuration was used for comparability.
- Results are therefore best interpreted as:
  - **relative regime/family ranking**
  - not final production-optimal scores

## Recommended Next Step

If the goal is to decide where deeper modeling effort should go first:

1. prioritize `24h/B`
2. keep `24h/C` and `8h/B` as secondary candidates
3. treat `7d` as a separate imbalance/problem-framing task rather than a straightforward 4-class winner search

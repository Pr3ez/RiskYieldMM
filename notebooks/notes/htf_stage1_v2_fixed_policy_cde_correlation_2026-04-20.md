# HTF Stage-1-v2 Fixed-Policy CDE Correlation

Date: 2026-04-20

Run:

- `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

Window:

- `pred_batch 5170..5355`
- `186` steps

## Question

Do cross-direction-error changes move together across combos on the same step?

Definition used:

- `delta_cde_improve = baseline_cross_direction_error - filtered_cross_direction_error`
- positive means fixed preselection improved CDE
- negative means fixed preselection worsened CDE

## Short Answer

Not strongly.

There is only weak overall co-movement of CDE changes between combos.

What exists is:

- a small moderate-positive cluster around `f2_v2_t10`, `f2_v3_t9`, and `f2_v2_t8`
- weak-to-negligible relationships for most other pairs
- a few mildly negative relationships involving `f7_v1_t4`

So the CDE response is mostly combo-specific, not a single common step-level effect shared by all combos.

## Overall Pairwise Stats

Across all `28` combo pairs:

- mean Pearson correlation of `delta_cde_improve`: `0.1158`
- median Pearson correlation: `0.1331`
- minimum Pearson correlation: `-0.1033`
- maximum Pearson correlation: `0.4441`

Interpretation:

- average correlation is positive, but weak
- there is no broad lockstep behavior
- the strongest relationships are still only moderate

## Sign Co-Movement

Across all pair-step comparisons:

- mean sign agreement rate: `43.4%`
- median sign agreement rate: `42.5%`
- mean both-improve rate: `22.3%`
- mean opposite-sign rate: `35.3%`

Interpretation:

- two combos do **not** usually improve or worsen together
- opposite-direction behavior is common
- this again points to combo-specific reaction rather than a shared global pattern

## Strongest Positive Pair Relationships

- `f2_v2_t10` vs `f2_v3_t9`
  - Pearson: `0.4441`
  - sign agreement: `50.0%`
  - both improve: `24.2%`

- `f2_v2_t8` vs `f2_v3_t9`
  - Pearson: `0.3187`
  - sign agreement: `47.8%`
  - both improve: `23.1%`

- `f2_v2_t10` vs `f2_v2_t8`
  - Pearson: `0.2744`
  - sign agreement: `48.4%`
  - both improve: `25.8%`

- `f2_v1_t5` vs `f2_v2_t4`
  - Pearson: `0.2146`

- `f2_v1_t5` vs `f7_v1_t4`
  - Pearson: `0.2030`

Interpretation:

The only meaningful co-movement cluster is:

- `f2_v2_t10`
- `f2_v2_t8`
- `f2_v3_t9`

Those three tend to move in the same CDE direction more often than the rest, but still not strongly enough to call them tightly coupled.

## Most Negative Pair Relationships

- `f2_v2_t10` vs `f7_v1_t4`
  - Pearson: `-0.1033`

- `f2_v2_t4` vs `f7_v1_t4`
  - Pearson: `-0.0672`

- `f2_v2_t10` vs `f2_v2_t4`
  - Pearson: `-0.0090`

- `f2_v2_t4` vs `f2_v3_t9`
  - Pearson: `-0.0066`

Interpretation:

The negative relationships are weak, not severe. They mean some combos often benefit on steps where `f7_v1_t4` does not, but the antagonism is mild rather than strong.

## Step Breadth

How many combos improved or worsened together on the same step:

- mean improved combos per step: `3.63 / 8`
- mean worsened combos per step: `3.24 / 8`
- mean unchanged combos per step: `1.13 / 8`
- median improved combos per step: `4`
- median worsened combos per step: `3`

Broad-move counts:

- steps with `>= 6` combos improving: `27 / 186`
- steps with `>= 6` combos worsening: `18 / 186`
- steps with all `8` combos improving: `2 / 186`
- steps with all `8` combos worsening: `0 / 186`
- split steps with `>= 4` improving and `>= 3` worsening: `50 / 186`

Interpretation:

- some broad common-improvement steps do exist
- but they are not dominant
- split behavior is frequent
- most steps are mixed rather than uniform

## Practical Meaning

For model analysis, this means:

1. You should not assume CDE improvement is a single root-level phenomenon affecting all combos the same way.
2. Combo-level feature policies matter because different combos react differently on the same step.
3. The best next grouping candidate for shared analysis is the moderate cluster:
   - `f2_v2_t10`
   - `f2_v2_t8`
   - `f2_v3_t9`
4. `f7_v1_t4` looks more independent and is a good candidate for separate interpretation.

## Generated Artifacts

- [summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_cde_correlation_20260420_8h_b_pb5170_5355/summary.json)
- [pairwise_cde_correlation.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_cde_correlation_20260420_8h_b_pb5170_5355/pairwise_cde_correlation.csv)
- [per_combo_average_relationship.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_cde_correlation_20260420_8h_b_pb5170_5355/per_combo_average_relationship.csv)
- [step_breadth.csv](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/stage1_v2_fixed_policy_cde_correlation_20260420_8h_b_pb5170_5355/step_breadth.csv)

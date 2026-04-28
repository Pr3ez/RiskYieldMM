# HTF Null-Heavy Feature Remediation Plan 2026-03-30

## Objective
Make the final model-facing HTF parquet files acceptable for training by eliminating feature families whose current behavior is structurally incompatible with the final saved rows.

This plan follows the current repo evidence and avoids guessing.

## Current Evidence Base
- Feature inventory and intended storage contract:
  - [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md)
- Current live missingness trace:
  - [htf_current_missing_value_root_cause_trace_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_current_missing_value_root_cause_trace_2026-03-30.md)
- Design-intent synthesis:
  - [htf_null_heavy_feature_design_synthesis_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_null_heavy_feature_design_synthesis_2026-03-30.md)
- Existing usability validation and cleanup work:
  - [htf_usability_audit_implementation_2026-03-28.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_usability_audit_implementation_2026-03-28.md)
  - [htf_final_parquet_usability_cleanup_2026-03-28.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_final_parquet_usability_cleanup_2026-03-28.md)

## Key Principle
Do not treat all null-heavy features the same way.

The current evidence splits them into two groups:

### Group A. Structural design-mismatch features
These are not mainly source-data problems.

- batch-local `D_*` windows whose warmup nulls land inside final saved rows
- funding z-score features on broadcast stepwise `8h` funding

### Group B. Conceptually valid but source-gap-sensitive features
These are valid ideas but unstable under the current sparse auxiliary-source policy.

- `D_F_N_S_premiumZscore_xlong_zsc`
- `X_D_fundingBasisPressure_xlong_pct`

## Recommended Fix Order

### Step 1. Introduce an explicit final-output feature acceptance registry
Goal:
- stop relying on generic null thresholds alone
- make final training-output policy explicit per feature family

Registry should classify model-facing feature families into:
- `allowed`
- `temporarily_excluded`
- `needs_redesign`
- `needs_source_gap_policy`

Minimum initial entries:
- `D_*` batch-local windows: `temporarily_excluded` for windows proven structurally invalid in final saved rows
- `F_I_N_S_fundingZscore_*`: `needs_redesign` and temporarily excluded from final model-facing outputs
- `D_F_N_S_premiumZscore_xlong_zsc`: `needs_source_gap_policy`
- `X_D_fundingBasisPressure_xlong_pct`: `needs_source_gap_policy`

Why first:
- lowest-risk structural improvement
- makes the training-data contract explicit
- prevents silent reintroduction after future reruns

### Step 2. Exclude structural design-mismatch columns from final model-facing outputs
Goal:
- make final optimized/helper outputs stop carrying feature families we already know are structurally incompatible with final saved rows

This is the safest first implementation slice.

Scope:
- final model-facing outputs only:
  - `htf_optimized*`
  - `htf_with_helpers*`
- do not delete them from raw feature-stage artifacts yet

Recommended initial exclusions:

#### 2A. Funding z-score family
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`

Reason:
- stepwise-source z-score mismatch is a design problem, not a small data-cleaning issue
- keeping them in final training outputs while they remain null-heavy is lower-quality than dropping them pending redesign

#### 2B. Structurally bad batch-local `D_*` windows
Use explicit exclusions only where the batch-local warmup rule is proven to conflict with final saved rows.

Already supported by existing evidence:
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

Likely next candidate after confirmation:
- `D_dist_bot5_low_w120`

Important:
- do not use a vague global null threshold for this family
- use explicit window-by-window acceptance based on deterministic warmup logic and final row retention

### Step 3. Keep source-gap-sensitive long-window derivatives features out of semantic changes until policy is decided
Do not guess here.

Affected features:
- `D_F_N_S_premiumZscore_xlong_zsc`
- `X_D_fundingBasisPressure_xlong_pct`

Reason:
- these are not obviously “bad ideas”
- they are currently null-heavy because tiny raw 1m gaps get amplified by 480-row rolling windows

The correct fix depends on a policy decision:

Option A:
- causally fill very small 1m source gaps before feature computation

Option B:
- keep source data untouched and exclude these features from final training outputs

Option C:
- keep them only if the final model contract allows bounded missingness

Current repo evidence is not enough to choose among A/B/C automatically without making a modeling decision.

So this is the first true stop point where we should not guess.

### Step 4. Redesign funding z-score on native cadence or retire it
If we want to preserve the funding-extremeness concept, the best evidence-backed redesign is:
- compute the normalization on native funding events
- then broadcast the normalized signal

Why:
- this matches the source cadence
- avoids minute-level rolling std on constant 8h plateaus

Alternative:
- retire the funding z-score family entirely if the concept is not worth the extra complexity

### Step 5. Decide whether batch-local `D_*` should remain batch-local
This is the second semantic decision point.

Two valid directions:

Option A:
- keep them batch-local by design
- then prune windows that are incompatible with final saved rows

Option B:
- redesign them as continuous-history distances
- then they stop behaving like batch-local context features

The repo documentation currently describes them as batch-local, so Option A is the safer default unless we intentionally want a different signal.

## Validation Gates For Each Step

### After Step 1
- registry exists in code or config
- shared validation reads it
- final-output audit clearly reports violations by policy category, not just null rate

### After Step 2
- rerun only optimized/helper stages
- confirm excluded columns are absent from saved `htf_optimized*` and `htf_with_helpers*`
- confirm no re-leak through metadata preservation

### After Step 3
- if a source-gap policy is chosen, reproduce the null-heavy feature on bounded live slices before and after the policy change
- prove whether the policy removes null amplification without leakage

### After Step 4
- bounded recomputation must match the redesigned funding-zscore implementation exactly
- final helper usability report should show the old family removed or the redesigned family with acceptable null behavior

### After Step 5
- if batch-local behavior is kept, final outputs must no longer contain structurally invalid `D_*` windows
- if continuous redesign is chosen, the feature inventory and documentation must be updated because the feature meaning changes

## Recommended Immediate Next Implementation Slice
The safest next coding step is:

1. add the explicit final-output feature acceptance registry
2. exclude the current structural design-mismatch families from final model-facing outputs:
   - funding z-score family
   - already-proven bad `D_*` windows
3. rerun only optimized/helper stages

Why this is the safest first move:
- no raw-source semantics change
- no helper semantics change
- no source-gap imputation yet
- immediate improvement to training-data quality

## Explicit Decision Points Where We Should Not Guess

### Decision Point 1
Should sparse 1m premium/index gaps be:
- causally filled,
- tolerated,
- or cause feature exclusion?

This affects:
- `D_F_N_S_premiumZscore_xlong_zsc`
- `X_D_fundingBasisPressure_xlong_pct`

### Decision Point 2
Should `D_*` remain batch-local by design?

If yes:
- prune incompatible windows

If no:
- redesign the feature family and update docs/meaning

## Bottom Line
There is enough context to start fixing the problem safely, but not enough to justify blind semantic edits.

The repo evidence supports:
- immediate exclusion of structural design-mismatch families from final model-facing outputs
- deferred policy decision for sparse-source-gap-sensitive derivatives features

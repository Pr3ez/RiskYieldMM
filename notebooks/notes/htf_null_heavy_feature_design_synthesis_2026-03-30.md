# HTF Null-Heavy Feature Design Synthesis 2026-03-30

## Purpose
This note collects the design intent already present in the repo for the current null-heavy HTF feature families and turns it into evidence-backed fix guidance.

The goal is not to guess a new design. The goal is to answer:
- what these features were supposed to measure,
- how the current code computes them,
- why that conflicts with the saved final training rows,
- and which solutions are consistent with the repo's own design rules.

## Existing Repo Context That Matters

### 1. Feature inventory and time-window meaning
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- `short ~= 1h`
- `med ~= 2h`
- `long ~= 4h`
- `xlong ~= 8h`
- `1m`/`15m` features are computed on the **full continuous combined series**, then split back into batch files
- this continuous computation is explicitly intended to preserve long-window features across batch boundaries

This tells us:
- long and xlong engine features are meant to use continuous history
- batch boundaries should not break standard rolling engine features
- only custom `D_*` distances are intentionally batch-context-specific

### 2. Legacy notebook comments still reflect the intended feature-build rule
From [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1608):
- `Features with long windows (xlong=8h) need continuous data to avoid NaN`
- `Strategy: Compute features on FULL combined data, THEN split into batch files`

This is important because it tells us the current design already assumes:
- long-window NaNs caused only by batch boundaries are considered a bug
- long-window continuity is supposed to be preserved

### 3. Current root-cause trace
From [htf_current_missing_value_root_cause_trace_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_current_missing_value_root_cause_trace_2026-03-30.md):
- nulls are first produced in the **feature stage**
- exact causes are:
  - batch-local warmup for `D_*`
  - zero rolling std on stepwise funding
  - rolling-window amplification of tiny premium/index source gaps

### 4. Current usability/cleanup notes
From [htf_usability_audit_implementation_2026-03-28.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_usability_audit_implementation_2026-03-28.md) and [htf_final_parquet_usability_cleanup_2026-03-28.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_final_parquet_usability_cleanup_2026-03-28.md):
- the workflow already distinguishes between:
  - structurally bad all-null columns
  - high-null but not fully all-null columns
- the repo already points toward policy decisions, not blind acceptance:
  - decide whether to redesign or retire funding z-score
  - decide policy for `D_*`
  - decide policy for high-null source-gap-derived columns

## Feature-Family Synthesis

### A. `D_*` custom causal distance features

Examples:
- `D_dist_bot5_low_w120`
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

### Intended purpose
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- these measure where the current close sits versus recent past highs/lows
- they are explicitly described as:
  - `computed only from past OHLCV inside the current batch context`

So these are not generic rolling engine features.
They are special batch-local causal context features.

### Current implementation
From [htf_kernels.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_kernels.py#L141):
- they use only prior rows in the same batch
- if `bar_pos < window`, output stays `NaN`

### What this means
The nulls here are not accidental.
They are a direct consequence of the feature definition.

### Correct solution direction
The repo evidence points to this:
- if these are meant to stay **batch-local**, then early-batch nulls are expected
- so the real decision is not “fix a bug”
- it is:
  - either keep them and accept front-half warmup nulls,
  - or exclude windows that are structurally unusable in the saved label-eligible rows,
  - or redesign them as continuous-history distances instead of batch-local distances

The repo currently leans toward:
- keeping the concept,
- but dropping windows that become structurally useless in final training outputs

That is consistent with the existing cleanup work for all-null `D_*` columns.

### B. `F_I_N_S_fundingZscore_*`

Examples:
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`

### Intended purpose
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- these are supposed to normalize funding into an unusual-vs-normal measure
- conceptually: detect when current funding is extreme relative to recent funding regime

That is a valid feature idea.

### Current implementation
From [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L1590):
- plain rolling z-score on broadcast `fundingRate`
- denominator is rolling std
- `0` std is replaced with `NaN`

### Why current implementation conflicts with intent
Funding is an `8h` stepwise source.
At `1m`, `long=240` and `xlong=480`.

So the current implementation is asking:
- “how many rolling stds away is this minute-level funding point”
on a series that is often constant for hundreds of minutes.

That is not a good statistical match for the intended signal.

### Correct solution direction
The repo evidence points most strongly to:
- **redesign or retire** funding z-score, not “fill its NaNs”

Why:
- the nulls are mathematically correct under the current formula
- imputing them would hide a design mismatch
- the intended signal is “funding extreme vs recent funding regime,” but the current minute-level rolling std on a stepwise source does not express that well

The clean fix directions are:
- compute the z-score on native funding events, then broadcast the result
- or use a different normalization that is stable on stepwise data
- or remove the feature family if we do not trust it

The repo's own notes already point toward “redesign or retire funding z-score.”

### C. `D_F_N_S_premiumZscore_xlong_zsc`

### Intended purpose
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- normalize premium into a relative-extremeness signal over a long horizon
- this is conceptually a derivatives crowding / mispricing regime signal

### Current implementation
From [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L1646):
- rolling z-score on minute-level `premiumClose`
- `xlong=480` at `1m`

### Why current implementation conflicts with saved outputs
The feature itself is conceptually fine.
The problem is the input contract:
- raw `1m` premium has tiny timestamp holes
- a full rolling z-score window amplifies those tiny holes into hundreds of null rows

So this is not the same problem as funding z-score.
Here the concept is reasonable, but the source-gap policy is missing.

### Correct solution direction
The repo evidence points toward:
- do **not** silently accept the current null-heavy result
- decide explicit policy for sparse auxiliary-feed holes

That policy could be:
- impute tiny 1m feed gaps causally before feature computation
- mask and drop affected feature rows
- or exclude this feature family from final training outputs if gap amplification remains too severe

What the repo does **not** support is pretending the current result is fine.

### D. `X_D_fundingBasisPressure_xlong_pct`

### Intended purpose
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- rolling mean of `fundingRate × basis`
- intended to capture joint pressure between carry/funding and futures-vs-index dislocation

This is a coherent derivatives pressure idea.

### Current implementation
From [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L956):
- build `basis`
- multiply by broadcast `fundingRate`
- take rolling mean over `long`/`xlong`

### Why current implementation conflicts with saved outputs
This is like premium z-score:
- concept is fine
- minute-level `indexClose` holes make `basis` null
- rolling mean over `480` rows amplifies tiny gaps into many null rows

So this is mainly a **source-gap propagation** problem, not a concept problem.

### Correct solution direction
Repo evidence points toward:
- keep the concept,
- but define a source-gap handling policy before trusting it in final training outputs

### What the existing work already tells us about the right solution
From the repo and audits together, the strongest supported direction is:

1. `D_*`
- keep only windows that are usable in final saved rows
- redesign only if we want continuous rather than batch-local context

2. `funding zscore`
- redesign on native funding cadence or retire
- current minute-level rolling z-score on a stepwise source is not the right expression of the intended signal

3. `premium zscore xlong`
- concept is fine
- must decide explicit policy for tiny raw source gaps

4. `funding-basis pressure xlong`
- concept is fine
- must decide explicit policy for tiny raw index/basis gaps

## Strongest Evidence-Based Recommendation

If we want the least risky order of fixes:

1. **Do not start by filling final parquet nulls directly.**
- that would hide the real cause

2. **Separate design-mismatch fixes from source-gap-policy fixes.**
- design mismatch:
  - funding z-score
  - some batch-local `D_*` windows
- source-gap policy:
  - premium z-score xlong
  - funding-basis pressure xlong

3. **Use different decisions for those two groups.**
- redesign/retire the design-mismatch features
- define causal gap handling for the sparse-source features

## Practical Next Fix Tasks

The repo evidence supports these next tasks:

1. `funding zscore redesign`
- decide native-cadence z-score vs retirement

2. `D_* usability pruning`
- formalize which windows are invalid for final saved rows and exclude them

3. `sparse auxiliary source policy`
- decide how to handle tiny `1m` premium/index gaps before long rolling features are built

## Bottom Line
Yes, there is enough information in our work and in the repo to point to the correct solution direction.

The important conclusion is:
- not all problematic columns should be treated the same way
- the repo already gives us the split:
  - some features are conceptually wrong for their current computation context
  - others are conceptually fine but need an explicit sparse-source handling policy

# HTF Feature Purpose And Batch Validity Synthesis 2026-03-31

## Purpose
Collect the verified repo context for the remaining problematic HTF feature families so the next fixes are guided by:
- intended feature purpose,
- actual compute path,
- why the current outputs fail or remain mixed,
- and which remediation path is consistent with that design.

This note is intentionally evidence-backed. It does not assume that all null-heavy features should be fixed the same way.

## Evidence Base
- Feature inventory and intended storage contract:
  - [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md)
- Current null root-cause trace:
  - [htf_current_missing_value_root_cause_trace_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_current_missing_value_root_cause_trace_2026-03-30.md)
- Existing design synthesis:
  - [htf_null_heavy_feature_design_synthesis_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_null_heavy_feature_design_synthesis_2026-03-30.md)
- Post raw-repair audit:
  - [htf_post_raw_repair_output_audit_2026-03-31.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_post_raw_repair_output_audit_2026-03-31.md)
- Compute code:
  - [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
  - [htf_kernels.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_kernels.py)
  - [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

## The Main Design Split

### 1. Standard engine features are meant to be valid on continuous history
This is explicit in [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- `1m` and `15m` features are computed on the full continuous combined series
- auxiliary sources are causally merged before feature computation
- then the results are split back into per-batch parquet files

It is repeated in [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py):
- long/xlong windows should use full continuous history so batch boundaries do not create artificial NaNs

So for standard rolling engine features:
- missingness caused only by batch boundaries is a bug
- missingness caused by true source gaps or formula/source mismatch is a data/design issue

### 2. `D_*` is the exception
The `D_*` family is explicitly documented in [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md) as:
- computed only from past OHLCV inside the current batch context

So `D_*` is not supposed to behave like the continuous-history engine features.

That distinction is the key to the current issue map.

## Feature Family Map

### A. `D_*` causal distance features
Examples:
- `D_dist_bot5_low_w120`
- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

Intended purpose:
- measure where current close sits versus past highs/lows inside the current batch context
- encode local causal context, not full-series regime structure

Actual computation:
- [htf_kernels.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_kernels.py) `_compute_past_distance_metrics(...)`
- exact warmup rule:
  - `if bar_pos[i] < window: continue`

What this means:
- early in-batch rows are intentionally undefined
- this resets every batch
- this is a per-batch warmup, not a one-time global warmup

Why this becomes a final-output problem:
- final `optimized/helpers` outputs keep the label-eligible portion of each batch
- for family `B`, that saved slice starts at `family_bar_pos = 0`
- so `B` outputs directly include the in-batch warmup zone

Verified current live examples:
- [data/htf_with_helpers/1m/target_4class/batch_5670.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers/1m/target_4class/batch_5670.parquet)
  - `D_dist_bot5_low_w120 = 100.00%` missing
  - saved rows: `family_bar_pos = 0..74`
- [data/htf_with_helpers_24h/1m/target_4class/batch_1890.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers_24h/1m/target_4class/batch_1890.parquet)
  - `D_dist_bot5_low_w120 = 16.67%` missing
  - saved rows: `family_bar_pos = 0..719`
- [data/htf_with_helpers_7d/1m/target_4class/batch_0271.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers_7d/1m/target_4class/batch_0271.parquet)
  - `D_dist_bot5_low_w120 = 2.38%` missing
  - saved rows: `family_bar_pos = 0..5039`

Important nuance:
- the same feature is clean in current `C` outputs:
  - [data/htf_with_helpers_shift4h/1m/target_4class/batch_5669.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers_shift4h/1m/target_4class/batch_5669.parquet)
  - [data/htf_with_helpers_24h_shift12h/1m/target_4class/batch_1889.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers_24h_shift12h/1m/target_4class/batch_1889.parquet)
  - [data/htf_with_helpers_7d_shift84h/1m/target_4class/batch_0270.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers_7d_shift84h/1m/target_4class/batch_0270.parquet)
  - `D_dist_bot5_low_w120 = 0.00%` missing

Why `C` behaves differently:
- `C` feature files are materialized from timestamp-aligned base `B` feature rows, not recomputed on a fresh `C` warmup
- see [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md) and [_build_shifted_feature_batches_from_base(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
- the shifted rows often inherit feature values from later-in-base timestamps that are already past the `D_*` warmup zone

Conclusion:
- `D_*` is not a generic pipeline bug
- `B` family warmup leakage is structural under the current batch-local definition
- if the contract is “valid feature for all saved rows,” then some `D_*` windows must be excluded from final `B` outputs or redesigned

### B. `F_I_N_S_fundingZscore_*`
Examples:
- `F_I_N_S_fundingZscore_long_zsc`
- `F_I_N_S_fundingZscore_xlong_zsc`

Intended purpose:
- measure whether current funding is extreme relative to recent funding regime

Actual computation:
- [_compute_funding_zscore(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- plain rolling z-score on broadcast `fundingRate`

Why it fails:
- `fundingRate` is an `8h` stepwise source
- minute-level rolling std becomes `0` on constant plateaus
- current code replaces `0` std with `NaN`

Conclusion:
- this is a formula/source-cadence mismatch
- not a raw-source gap problem
- current exclusion from model-facing outputs is still the right safety policy
- the real long-term fix is redesign on native funding cadence or retirement

### C. `D_F_N_S_premiumZscore_xlong_zsc`
Intended purpose:
- long-horizon premium extremeness signal

Actual computation:
- rolling z-score on `premiumClose`
- `xlong = 480` at `1m`

What was wrong:
- raw `1m` premium feed had deterministic pagination gaps
- long rolling windows amplified tiny raw holes into large null regions

What changed:
- raw auxiliary source repair fixed the fetch-layer cause
- newest rebuilt tail batches are now clean for this family

What is still mixed:
- root-wide historical helper reports are still high-null because many older batches are stale pre-repair artifacts
- [htf_post_raw_repair_output_audit_2026-03-31.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_post_raw_repair_output_audit_2026-03-31.md) shows the latest rebuilt tail batches are clean while the global reports remain inflated

Conclusion:
- concept is still valid
- current remaining issue is historical stale corpus, not ongoing tail corruption
- this family does not need the same treatment as `D_*` or funding z-score

### D. `X_D_fundingBasisPressure_xlong_pct`
Intended purpose:
- rolling mean of `funding × basis`
- intended to capture joint carry/dislocation pressure

Actual computation:
- [_compute_basis(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- [_rolling_mean_product(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)

What was wrong:
- same raw auxiliary gap issue, but through `basis` and `indexClose`

Current state:
- same as premium xlong:
  - latest rebuilt tails are clean
  - historical corpus remains mixed until a full rebuild materializes the raw repair everywhere

Conclusion:
- concept remains valid
- this is now a corpus-refresh problem, not a current-tail formula bug

## What “Valid For All Different Batches” Means By Family

### Continuous engine families
Target contract:
- valid across all batches once:
  - source alignment is causal,
  - raw auxiliary sources are healthy,
  - and full historical rebuild has materialized repairs

That applies to:
- premium xlong
- funding-basis pressure xlong
- most standard rolling features

### Batch-local `D_*`
Target contract under current design:
- not valid for the earliest in-batch rows by definition

So there are only two honest ways to get “valid for all saved rows”:
- exclude the incompatible `D_*` windows from final model-facing outputs where saved rows overlap warmup
- or redesign `D_*` as continuous-history features instead of batch-local ones

Imputation is not a valid fix here because those rows are undefined under the current formula.

## Evidence-Backed Fix Order

### 1. Full historical rebuild for affected premium/index-derived families
Reason:
- the raw repair solved the cause
- but current root-wide reports are still polluted by stale historical batches

Needed if the goal is a fully clean historical training corpus, not just a clean tail.

### 2. Scope-aware final-output policy for `D_*`
Reason:
- current acceptance rules in [htf_feature_acceptance.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_feature_acceptance.py) are global by column pattern
- `D_dist_bot5_low_w120` is structurally bad in current `B` outputs but clean in current `C` outputs

So the next policy step should be:
- support rule scope by regime/family/timeframe/stage
- then exclude `D_dist_bot5_low_w120` where it is structurally invalid in final saved rows

### 3. Keep funding z-score excluded until redesigned
Reason:
- the underlying design mismatch has not changed
- there is no trustworthy imputation shortcut

## Strongest Conclusion
The repo now points to a clear split:

- `D_*` is a structural batch-local design issue
- `funding zscore` is a source-cadence/formula mismatch
- `premium xlong` and `funding-basis xlong` were primarily raw auxiliary gap problems and are now healthy in rebuilt tails

So the next fix should not be a generic “remove all null-heavy features.”
It should be:
1. full historical rebuild where raw repair matters,
2. scoped `D_*` policy for final outputs,
3. later redesign of funding z-score if we still want that signal family.

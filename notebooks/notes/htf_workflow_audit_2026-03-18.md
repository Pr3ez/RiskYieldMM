# HTF Workflow Audit - 2026-03-18

## Scope

This audit covers the current HTF workflow end to end, with focus on:

- protecting existing production data
- ensuring only the rows and features that actually need recomputation are recomputed
- verifying that the richer fetched-source feature expansion is wired safely
- identifying what should happen next before another long production run

Reviewed files:

- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)

## Executive Summary

The workflow is structurally safe in the places that matter most:

- combined batch generation is isolated from feature schema changes
- labels do not depend on HTF feature columns, so richer features do not invalidate existing label logic
- optimization and helpers are downstream of features and should be refreshed after a feature schema change
- both the legacy `8h` path and the shared multi-regime `8h/24h/7d` path now contain feature-stage invalidation logic for auxiliary fetched sources and expected schema drift

The main current fact is:

- **the code is ready for the richer `1m` and `15m` feature schema**
- **the production artifact trees are still on the old schema**

So there is no evidence that existing combined or label data is broken, but there is also no basis to treat the production feature/optimized/helper trees as already refreshed.

## Workflow Map

### Legacy notebook path

Main stages in [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py):

1. Setup, run logging, artifact metadata helpers
2. Legacy `8h` combined generation for family `B`
3. Legacy shifted `4h` combined generation for family `C`
4. Legacy feature engineering for `1m` and `15m`
5. Shifted-family feature materialization from base features
6. Legacy feature validation
7. Legacy distance metrics for label generation
8. Legacy `15m` labels
9. Legacy `1m` hybrid labels
10. Optimization
11. Helper cache + helper materialization
12. Split helpers back to batch structure
13. Legacy validation
14. Shared authoritative multi-regime pipeline for `8h`, `24h`, `7d`

### Shared multi-regime path

Main stages in [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py):

1. Base combined generation
2. Shifted-family combined generation
3. Feature batches
4. `15m` distance metrics
5. `1m` labels
6. Optimization
7. Helpers
8. Validation

This is the current authoritative implementation for `8h`, `24h`, and `7d`.

## What Protects Existing Data

### 1. Combined data is not coupled to feature schema

Combined batch files are built from fetched OHLCV only. They are not invalidated by richer feature columns.

Relevant code:

- [htf_pythonscript.py:540](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L540)
- [htf_pythonscript.py:809](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L809)
- [htf_multiregime_pipeline.py:2871](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L2871)

Effect:

- a feature expansion should not force combined artifacts to be destroyed
- existing combined data remains the source of truth for labels

### 2. Labels depend on combined plus distance metrics, not on HTF feature files

Legacy `15m` and `1m` labels are computed from combined OHLCV plus distance metrics / future path logic, not from `htf_features`.

Relevant code:

- [htf_pythonscript.py:3380](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L3380)
- [htf_pythonscript.py:4511](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L4511)
- [htf_multiregime_pipeline.py:1979](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1979)

Effect:

- richer feature columns do not require label recomputation
- existing `target_4class` and `target_breakfree` artifacts are not invalidated by feature schema changes

### 3. Shifted family `C` features are materialized from `B`, not recomputed from raw

This is important both for speed and consistency.

Relevant code:

- [htf_pythonscript.py:2045](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2045)
- [htf_multiregime_pipeline.py:1445](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1445)

Effect:

- `C` feature values are inherited by exact `timestamp`
- only family metadata is remapped
- no extra raw feature recompute is introduced for shifted families

### 4. Optimizer is numeric-only and excludes metadata

Relevant code:

- [optimize_htf_features.py:124](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L124)

Effect:

- new bookkeeping columns like `batch_regime`, `anchor_utc`, and other non-feature metadata are not sent into the rolling transform
- richer numeric features will be picked up automatically once feature batches are refreshed

### 5. Helper cache and helper materialization are separate

Relevant code:

- [htf_helper_cache.py:322](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L322)
- [htf_helper_cache.py:590](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L590)

Effect:

- helper math stays exact and causal
- helper outputs can be refreshed independently from label logic
- downstream helper outputs only need refreshed features/optimized inputs, not a full label rebuild

## What Now Works Correctly

### Feature-stage invalidation now accounts for richer inputs

The critical gap that existed earlier was that feature outputs could be considered `current` even when:

- auxiliary fetched-source inputs changed
- code added new expected feature columns

That is now patched in both paths.

Relevant code:

- [compute_htf_features.py:439](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L439)
- [compute_htf_features.py:479](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py#L479)
- [htf_pythonscript.py:1718](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1718)
- [htf_multiregime_pipeline.py:1403](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1403)
- [htf_multiregime_pipeline.py:1572](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L1572)

This means the next rerun should correctly detect old feature trees as stale for:

- `artifact_version`
- `source_fingerprint`
- `schema_columns`

## What Is Incremental vs What Is Not

### Safe incremental behavior

These stages are designed to update only affected tails or changed batches:

- combined: current unless raw OHLCV advanced
- features: tail rebuild plus context
- labels: tail plus missing-batch backfill
- optimization: batch-fingerprint based resume
- helper cache: affected-tail rebuild
- helper materialization: affected-tail rewrite based on optimized/cache mtimes

Relevant code:

- [htf_pythonscript.py:1735](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L1735)
- [htf_pythonscript.py:2541](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py#L2541)
- [optimize_htf_features.py:593](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py#L593)
- [htf_helper_cache.py:410](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L410)
- [htf_helper_cache.py:673](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L673)

### What still must rebuild after a schema change

The first rerun after the fetched-source feature expansion is expected to rebuild:

- `1m` and `15m` HTF feature trees
- `1m / target_4class` optimized outputs
- final helper outputs

This is not a regression. It is the correct behavior because downstream artifacts still reflect the old feature schema.

Labels do **not** need rebuilding for this change.

## Current Production Artifact State

### Production features are still on the old schema

Measured live production batch schemas under `ml_env`:

- legacy `8h/B` `1m`: `116` total columns, `93` feature columns
- legacy `8h/B` `15m`: `116` total columns, `93` feature columns
- legacy `8h/C` `1m`: `116` total columns, `93` feature columns
- legacy `8h/C` `15m`: `116` total columns, `93` feature columns
- `24h/B,C` `1m`, `15m`: all still `116` total columns, `93` feature columns
- `7d/B,C` `1m`, `15m`: all still `116` total columns, `93` feature columns

This confirms the production trees have **not** yet been refreshed onto the richer feature schema.

### Production metadata also shows pre-expansion feature outputs

Example metadata currently shows:

- `artifact_version = 2026-03-06-repair-01-features-b-v1`
- `auxiliary_source_paths = []`
- `source_plan = None`

for current production feature trees.

This matches the older build, not the new fetched-source-aware feature path.

### Resume logic correctly identifies those trees as stale

The invalidation probe artifact:

- [resume_logic_feature_invalidation_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/resume_logic_feature_invalidation_summary.json)

shows:

- current production columns: `116`
- expected columns: `146`
- rebuild reasons: `artifact_version`, `source_fingerprint`, `schema_columns`

Interpretation:

- code-side safety is in place
- production-side refresh has not happened yet

### Production optimized and helper trees are also still pre-expansion

Measured live production batch schemas:

- optimized `1m / target_4class` for `8h`, `24h`, `7d`, both families: `116` columns
- helper outputs for the same trees: `159` columns with `43` helper columns

These do **not** contain:

- `X_D_*` composites
- funding features
- open-interest features
- other newly activated auxiliary-source features

So optimized and helper outputs are also still on the old feature set.

## Risk Assessment

### Low risk

- existing combined artifacts
- existing labels and distance metrics
- existing weekly validation fix
- helper math and anti-leakage contract

### Medium risk

- coexistence of two implementations in one notebook:
  - legacy `8h` path
  - shared multi-regime authoritative path

This is manageable now, but it remains a maintenance risk because the logic still exists in parallel.

### Main operational cost

- the first post-schema-change production refresh will still be expensive
- current resume logic prevents silent skipping, but it does not eliminate the need for that first rebuild

## Answer To The Core Questions

### Will existing data be broken?

Not by the current code changes, based on this audit.

More precisely:

- combined data is not affected
- labels are not invalidated by the richer feature schema
- the code now avoids silently treating old feature outputs as current

So the risk is not corrupting existing combined/label data. The risk is only that production feature/optimized/helper trees are still old until a refresh is run.

### Will only the rows and features we need be calculated?

After the first schema-refresh run, yes, that is the intended behavior.

Current behavior:

- first rerun after schema expansion:
  - recompute affected `1m` and `15m` feature trees because schema and auxiliary inputs changed
  - refresh optimized and helper outputs downstream
- later unchanged reruns:
  - should go `current` or incremental tail only

That matches the design target.

## Recommended Next Steps

### Immediate next action

Do **not** run the full notebook from the very top again unless raw OHLCV actually changed.

Instead, run a controlled production refresh of:

1. `1m` and `15m` features
2. `1m / target_4class` optimization
3. helper cache/materialization

and keep:

- combined artifacts
- distance metrics
- labels

unchanged unless there is a separate raw-data reason to refresh them.

### Best practical implementation step

Add or use a dedicated refresh entrypoint that starts at the feature stage onward, rather than forcing a full end-to-end notebook rerun.

Why:

- current code correctness is acceptable
- current operational pain is runtime, not correctness
- the biggest missing piece now is a cheaper production refresh path

### Longer-term cleanup

Reduce duplication between:

- legacy `8h` notebook stages
- shared multi-regime pipeline

The more the shared pipeline becomes the only production path, the lower the drift risk.

## Decision

Based on the current code and live artifact inspection:

- **the implementation is safe enough to proceed**
- **existing combined and label data should not be considered broken**
- **production feature, optimized, and helper trees still need a one-time refresh onto the richer schema**
- **the next task should be a targeted feature-forward production refresh path, not another full top-to-bottom notebook run**

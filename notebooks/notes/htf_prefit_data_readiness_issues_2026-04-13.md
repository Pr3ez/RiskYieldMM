# HTF Pre-Fit Data Readiness Issues — 2026-04-13

## Scope

This note records the remaining model-input data issues found after the helper-contract rebuild and all-regime validation pass.

Checked scope:

- model-facing `1m / target_4class` inputs only
- actual CatBoost loader-visible features
- roots:
  - `8h/B`, `8h/C`
  - `24h/B`, `24h/C`
  - `7d/B`, `7d/C`

Audit source:

- `test_output/htf_feature_null_constant_audit/20260413_catboost_input_audit.json`

## Bottom Line

The rebuilt data is **not yet fully ready** under a strict pre-fit requirement of:

- no missing values in model-facing features
- no constant features in model-facing features

Current status:

- constant features: `0` across all six roots
- all-null features: `0` across all six roots
- non-zero missing values: **present**

So CatBoost inputs are cleaner than before, but still not fully null-free.

## Issue 1: Distance Metric Warmup Resets Every Batch

Affected feature:

- `D_dist_bot5_low_w120`

Code path:

- [`scripts/feature_engineering/htf_kernels.py`](../../scripts/feature_engineering/htf_kernels.py)
- [`scripts/feature_engineering/htf_multiregime_pipeline.py`](../../scripts/feature_engineering/htf_multiregime_pipeline.py)

Root cause:

- `_compute_past_distance_metrics(...)` gates computation with:
  - `if bar_pos[i] < window: continue`
- the pipeline passes `bar_pos = family_bar_pos`
- `family_bar_pos` resets at the start of each batch

That means the first `window` rows of **every batch** are null for that feature, even though earlier rows from the same family stream already exist.

Relevant code:

```python
# scripts/feature_engineering/htf_kernels.py
if bar_pos[i] < window:
    continue
```

```python
# scripts/feature_engineering/htf_multiregime_pipeline.py
bar_pos = df_full["bar_pos"].to_numpy().astype(np.int32)
...
_compute_past_distance_metrics(close, high, low, bar_pos, window, OUTLIER_PERCENTILE)
```

Observed null pattern:

- `8h/B`: `680,356` nulls, about `50.00%`
- `24h/B`: `226,801` nulls, about `16.67%`
- `7d/B`: `32,401` nulls, about `2.38%`

Per-batch pattern:

- `8h/B`: batch 1 has `121` nulls, every later batch has `120`
- `24h/B`: batch 1 has `121` nulls, every later batch has `120`
- `7d/B`: batch 2 has `121` nulls, every later batch has `120`

Interpretation:

- this is causal
- this is not data corruption
- this is still a model-readiness problem because the feature unnecessarily resets by batch instead of using continuous causal history

## Issue 2: Helper Warmup Nulls Are Materialized Into Early Trainable Batches

Affected features:

- all helper families inspected show the same pattern, for example:
  - `H_4cl_1_cp_any`
  - `H_4class_1_egarch_vol`
  - `H_4class_1_kalman_zscore`
  - `H_4class_1_ou_reverting`
  - `H_4cl_1_garch_cond_vol`

Code path:

- [`scripts/feature_engineering/htf_helper_cache.py`](../../scripts/feature_engineering/htf_helper_cache.py)
- [`scripts/feature_engineering/htf_multiregime_pipeline.py`](../../scripts/feature_engineering/htf_multiregime_pipeline.py)

Root cause:

- helper generation uses walk-forward warmup:
  - `helper_warmup_by_tf["1m"] = 20000`
  - `helper_refit_every_by_tf["1m"] = 10000`
- before helper output exists for a batch, the cache explicitly writes a null helper batch
- if the first helper chunk starts partway through a batch, the leading part of that batch is also written as null

Relevant code:

```python
# scripts/feature_engineering/htf_multiregime_pipeline.py
helper_warmup_by_tf = {"1m": 20000, "15m": 5000}
helper_refit_every_by_tf = {"1m": 10000, "15m": 2500}
```

```python
# scripts/feature_engineering/htf_helper_cache.py
def _null_cache_batch(batch_id: int) -> pl.DataFrame:
    ...
    return ts_only.with_columns(null_columns).select(["timestamp", *helper_cols])
```

```python
# scripts/feature_engineering/htf_helper_cache.py
while next_batch_pos < len(batches_to_write) and batches_to_write[next_batch_pos] < batch_id:
    _write_cache_batch(batches_to_write[next_batch_pos], _null_cache_batch(...))
```

```python
# scripts/feature_engineering/htf_helper_cache.py
if segment_global_start > batch_start:
    current_batch_parts.append(
        _null_cache_batch(batch_id).slice(0, segment_global_start - batch_start)
    )
```

Observed null pattern:

- `8h/B`: `10080` helper null rows
- `8h/C`: `10080`
- `24h/B`: `10080`
- `24h/C`: `10080`
- `7d/B`: `10080`
- `7d/C`: `5600`

These nulls are not helper-specific. They affect OU, Kalman, EGARCH, GARCH, CUSUM, and change-point helper columns in the same early batches.

## Why Validation Still Passed

The validation pass succeeded because the current pipeline does **not** fail on high-null columns.

Config:

- [`scripts/feature_engineering/htf_multiregime_pipeline.py`](../../scripts/feature_engineering/htf_multiregime_pipeline.py)

```python
usability_audit_fail_on_all_null = True
usability_audit_fail_on_high_null = False
usability_audit_fail_on_constant = True
```

So the pipeline currently blocks:

- all-null columns
- constant columns

but it only reports high-null columns. It does not fail the run on them.

## First Fully Helper-Clean Batch

Using `H_4class_1_egarch_vol` as the representative helper feature:

- `8h/B`: first fully clean batch = `43`
- `8h/C`: first fully clean batch = `43`
- `24h/B`: first fully clean batch = `15`
- `24h/C`: first fully clean batch = `15`
- `7d/B`: first fully clean batch = `4`
- `7d/C`: first fully clean batch = `4`

This is the earliest batch where model-facing helper features no longer contain warmup nulls.

## Decision

Do **not** proceed to CatBoost fitting yet if the acceptance bar is:

- no missing values in model-facing features

The remaining blockers are:

1. `D_dist_bot5_low_w120` resetting by batch instead of using continuous family history
2. early helper warmup nulls being materialized into model-facing training batches

## Recommended Fix Order

1. Add a strict pre-fit guard that fails if loader-visible features contain any nulls in trainable rows.
2. Fix `D_dist_bot5_low_w120` to use continuous causal family-stream history, or remove it from model-facing training.
3. Stop exposing early helper-warmup rows to fitting:
   - either exclude pre-helper-ready batches from model fitting
   - or change helper materialization / eligibility so only helper-ready batches are treated as trainable
4. Rebuild affected artifacts.
5. Re-run the CatBoost-input null audit.

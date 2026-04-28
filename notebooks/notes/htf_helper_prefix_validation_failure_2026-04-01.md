# HTF Helper Prefix Validation Failure 2026-04-01

## Failure

Production HTF validation failed with:

- `8h / B / 1m / helpers / usability_prefix_all_null_helper_columns`
- `8h / C / 1m / helpers / usability_prefix_all_null_helper_columns`

## Root Cause

This failure is caused by a mismatch between:

1. helper warmup configuration
2. current helper-prefix validation policy

It is not primarily a helper resume bug.

## Code Path

### Helper warmup

The production config uses:

- `helper_warmup_by_tf["1m"] = 20000`

Source:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L210)

Helper generation begins only at `start_row >= warmup_rows`:

- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L162)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py#L194)

So for `1m` helpers, rows before raw row index `20000` have no helper values.

### Validation

The failing validation audits the first `20` helper batches and hard-fails if any helper column is `100%` null across that prefix:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L3240)
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py#L3265)

## Why `8h` Fails

For `8h / 1m`:

- raw rows per full batch = `480`
- helper warmup = `20000` raw rows

Batch boundaries:

- batch 41 raw rows: `19200..19679`
- batch 42 raw rows: `19680..20159`
- batch 43 raw rows: `20160..20639`

Final model-facing `optimized/helpers` outputs keep only the early label-eligible rows, which are `240` rows per `8h` batch.

That means:

- batches `0001..0042` in `8h/B/1m/helpers` and `8h/C/1m/helpers` have all `43` helper columns null
- batch `0043` is the first batch with non-null helper values

Verified directly:

- [batch_0001.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers/1m/target_4class/batch_0001.parquet): `43/43` helper columns all null
- [batch_0020.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers/1m/target_4class/batch_0020.parquet): `43/43` helper columns all null
- [batch_0042.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers/1m/target_4class/batch_0042.parquet): `43/43` helper columns all null
- [batch_0043.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_with_helpers/1m/target_4class/batch_0043.parquet): helper values present

Same pattern holds for shifted `8h/C`.

## Conclusion

The assertion is correctly reporting a real current training-data problem:

- early `8h` helper batches are not model-ready

But it is not evidence that helper resume is broken.

It is a consequence of the current helper warmup design and the decision to keep early `8h` label-eligible rows in final helper outputs.

## Practical Options

1. Keep current outputs and relax/disable this validation.
   - Lowest effort
   - Hides invalid early training rows

2. Lower helper warmup.
   - Changes helper-model behavior
   - Needs model-quality justification

3. Add prehistory before the dataset start.
   - Best if older raw data exists
   - Preserves current helper logic

4. Drop early helper-unavailable rows/batches from final model-facing outputs.
   - Cleanest final-training-data contract
   - Changes row coverage and needs downstream contract updates

Given the stated goal that final training parquets should be clean, option `4` is the most defensible unless older prehistory is available.

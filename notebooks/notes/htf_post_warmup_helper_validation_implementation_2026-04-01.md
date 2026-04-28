# HTF Post-Warmup Helper Validation Implementation 2026-04-01

## Change

Updated helper-prefix validation so it audits the first model-usable helper batches after helper warmup, not the first numeric helper batch ids.

Implementation:

- added `_select_post_warmup_helper_prefix_ids(...)`
- helper validation now finds the first batch with any non-null helper values
- then audits the next configured prefix from that batch onward

Changed file:

- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

## Why

With current config:

- `helper_warmup_by_tf["1m"] = 20000`
- `8h/1m` full raw rows per batch = `480`

That makes early `8h` helper batches expectedly all-null, so prefix validation starting at `batch_0001` was testing the unavoidable warmup region instead of the first model-usable helper region.

## Validation

Confirmed on live outputs:

- `8h/B/1m/helpers` first ready batch = `43`
- `8h/C/1m/helpers` first ready batch = `43`
- post-warmup prefix `43..62` has `0` all-null helper columns for both roots

## Result

The helper-prefix validation now reflects the intended contract:

- fail if post-warmup helper outputs are all-null
- ignore the unavoidable pre-warmup helper-null region

# HTF Final Output Broad Quality Verification

Date: 2026-03-28

## Why This Follow-Up Exists

The earlier audit focused on auxiliary-source-derived features. This follow-up checks whether those were the only material final-output issues, using a safer streaming audit after an earlier all-root lazy scan caused an OOM.

Primary artifact:

- `test_output/htf_final_output_streaming_quality_check.json`

Audited final-output roots:

- `data/htf_with_helpers/1m/target_4class`
- `data/htf_with_helpers_shift4h/1m/target_4class`
- `data/htf_with_helpers_24h/1m/target_4class`
- `data/htf_with_helpers_24h_shift12h/1m/target_4class`
- `data/htf_with_helpers_7d/1m/target_4class`
- `data/htf_with_helpers_7d_shift84h/1m/target_4class`
- `data/htf_with_helpers/15m/target_4class`
- `data/htf_with_helpers_shift4h/15m/target_4class`

## Checks Performed

For each root, the streaming audit verified:

- all-null columns
- top null-heavy columns
- infinite values
- duplicate `(batch_id, timestamp)` pairs
- timestamp monotonicity within batch
- timestamp overlap between consecutive batch files
- batch size ranges

## Broad Result

No, the auxiliary-feature issues were **not** the only data-quality issue.

The broader sweep found an additional class of structural null problems in the batch-local `D_*` distance features.

At the same time, several generic integrity classes came back clean:

- no infinite values in any audited root
- no duplicate `(batch_id, timestamp)` pairs
- no non-monotonic batches
- no overlapping timestamp ranges between consecutive batches

So the final outputs are not generally corrupted, but they do contain more than one material missingness/design issue.

## Newly Confirmed Additional Issue

## Issue 2. Some batch-local distance features are structurally all-null in final outputs

Affected roots:

- `8h / B / 1m`
  - `D_dist_avg_high_w240`
  - `D_dist_avg_low_w240`
  - `D_dist_top5_high_w240`
  - all `100%` null

- `8h / B / 15m`
  - `D_dist_avg_high_w16`
  - `D_dist_avg_low_w16`
  - `D_dist_top5_high_w16`
  - all `100%` null

Related structural missingness:

- `8h / B / 1m`
  - `D_dist_bot5_low_w120`: `50.00%` null

- `24h / B / 1m`
  - `D_dist_avg_high_w240`
  - `D_dist_avg_low_w240`
  - `D_dist_top5_high_w240`
  - each about `33.33%` null

- `7d / B / 1m`
  - same `w240` distance features
  - each about `4.76%` null

Interpretation:

- these `D_*` features are batch-local and require within-batch history
- final outputs retain only the label-eligible front part of each batch
- when the feature window is as large as, or too close to, the retained final window, the feature never becomes valid or is valid only near the end of the retained slice

Conclusion:

- this is not random missingness
- it is another structural feature-design mismatch between window size and final retained rows

## Previously Confirmed Issue Still Stands

The auxiliary audit remains valid:

- funding z-score features are structurally problematic, especially shifted `8h/C`
- basis / mark features inherit sparse raw mark/index holes
- premium z-score and funding-basis composites amplify sparse source gaps through rolling windows

See:

- `notebooks/notes/htf_final_output_data_quality_audit_2026-03-27.md`

## Root-by-Root Summary

### `8h / B / 1m`

Additional all-null columns:

- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

Also high structural nulls:

- `D_dist_bot5_low_w120`: `50.00%`

### `8h / C / 1m`

No additional all-null `D_*` columns, but:

- `F_I_N_S_fundingZscore_long_zsc`: still `100%` null

### `24h / B / 1m`

No all-null columns, but structural null-heavy `D_*` windows remain:

- `D_dist_avg_high_w240`
- `D_dist_avg_low_w240`
- `D_dist_top5_high_w240`

each about `33.33%`

### `24h / C / 1m`

No all-null columns, but the same auxiliary-heavy missingness remains.

### `7d / B / 1m`

No all-null columns, but smaller structural `D_*` null bands remain:

- `w240` distance features around `4.76%`

### `7d / C / 1m`

No all-null columns, but the same auxiliary-heavy missingness remains.

### `8h / B / 15m`

Additional all-null columns:

- `D_dist_avg_high_w16`
- `D_dist_avg_low_w16`
- `D_dist_top5_high_w16`

### `8h / C / 15m`

Still has:

- `F_I_N_S_fundingZscore_long_zsc`: `100%` null

## What Came Back Clean

Across all audited roots:

- no infinite values
- no duplicate `(batch_id, timestamp)` pairs
- no within-batch timestamp disorder
- no batch-to-batch timestamp overlap

This matters because it means the workflow is not broadly producing corrupted or duplicate final rows. The issues are concentrated in feature usefulness / missingness, not in basic file integrity.

## Answer To The Question

No, it is not only the auxiliary-feature issue.

There are now two confirmed material issue classes:

1. auxiliary-source-derived missingness, especially funding z-score design problems and gap-amplified premium/basis composites
2. structurally unusable or partially unusable `D_*` distance features caused by window-size mismatch against the retained final label window

## Recommended Next Actions

1. Add a formal feature usability audit after feature generation and before optimization/helper materialization.
   - flag all-null columns
   - flag columns above missingness thresholds
   - flag columns whose nulls are structural rather than prefix-only

2. Rework or remove structurally invalid features from final modeling sets.
   - funding z-score family
   - `D_*` windows that cannot become valid inside retained final rows

3. Keep generic integrity checks in the workflow.
   - duplicate keys
   - monotonic timestamps
   - overlap detection
   - infinity detection


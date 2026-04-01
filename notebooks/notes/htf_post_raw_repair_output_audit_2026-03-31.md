# HTF Post-Raw-Repair Output Audit 2026-03-31

## Scope
Audit the current live HTF outputs after:
- repairing the raw auxiliary `mark/index/premium` gaps
- swapping the repaired raw files into `fetchingByBit`
- completing the supported `CELL 14` downstream rebuild

Question:
- did the rebuilt live outputs actually clear the previously null-heavy premium/index-derived xlong families?

## Evidence
- rebuild log:
  [htf_pythonscript_20260330_203337_pid93804.log](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_run_logs/htf_pythonscript_20260330_203337_pid93804.log)
- current helper usability reports:
  - [8h_latest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability/8h_latest.json)
  - [24h_latest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability/24h_latest.json)
  - [7d_latest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability/7d_latest.json)
- machine-readable audit summary:
  [htf_post_raw_repair_audit_20260331.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_post_raw_repair_audit/htf_post_raw_repair_audit_20260331.json)

## Main Result
The raw repair **did help**, but the current root-wide helper reports are misleading if read alone.

What is true at the same time:
- the repaired raw `premium/index` sources are now gap-free
- the newest rebuilt helper batches are clean for:
  - `D_F_N_S_premiumZscore_xlong_zsc`
  - `X_D_fundingBasisPressure_xlong_pct`
- the current root-wide helper usability reports still show those families as high-null in several regimes

These are not contradictory.
The reason is that the downstream rebuild mostly ran in `incremental_tail` mode for the affected `B` feature roots, so the raw repair was materialized into the newest rebuilt tail batches, while many older historical helper batches remained unchanged.

## Evidence For The Incremental-Tail Explanation
From the rebuild log:
- `8h/B/1m/features`: `run_mode=incremental_tail`, `write_batches=3`
- `24h/B/1m/features`: `run_mode=incremental_tail`, `write_batches=3`
- `7d/B/1m/features`: `run_mode=incremental_tail`, `write_batches=3`

So the rebuild did **not** regenerate the full historical feature trees for those roots.

## Current Root-Wide Helper Reports
Current helper usability reports still show the premium/index-derived xlong families as high-null:
- `8h/B`: about `47.85%`
- `8h/C`: about `47.86%`
- `24h/B`: about `47.80%`
- `24h/C`: about `47.80%`
- `7d/B`: about `47.34%`
- `7d/C`: about `47.50%`

If viewed alone, that would suggest the raw repair failed.
But it did not.

## Current Tail-Batch Spot-Checks
The newest rebuilt helper batches are clean for the premium/index-derived xlong families.

### 8h/B last 3 batches
- `batch_5668`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_5669`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_5670`: premium xlong `0.00%`, funding-basis xlong `0.00%`

### 24h/B last 3 batches
- `batch_1888`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_1889`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_1890`: premium xlong `0.00%`, funding-basis xlong `0.00%`

### 24h/C last 3 batches
- `batch_1888`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_1889`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_1890`: premium xlong `0.00%`, funding-basis xlong `0.00%`

### 7d/B last 3 batches
- `batch_0269`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_0270`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_0271`: premium xlong `0.00%`, funding-basis xlong `0.00%`

### 7d/C last 3 batches
- `batch_0269`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_0270`: premium xlong `0.00%`, funding-basis xlong `0.00%`
- `batch_0271`: premium xlong `0.00%`, funding-basis xlong `0.00%`

## What Still Remains A Real Problem
The structural `D_*` family is still a real issue.

Example:
- latest `8h/B` helper batch `5670`:
  - `D_dist_bot5_low_w120 = 100.00%` null
- latest `24h/B` helper batch `1890`:
  - `D_dist_bot5_low_w120 = 16.67%` null
- latest `7d/B` helper batch `0271`:
  - `D_dist_bot5_low_w120 = 2.38%` null

So after the raw repair, the premium/index-derived xlong issue is no longer the main current-tail problem.
The remaining live problem is the structural batch-local `D_*` warmup family.

## Conclusion
The raw auxiliary repair worked.

But the current live dataset is now mixed:
- newest rebuilt batches reflect the repaired raw data and no longer show null-heavy premium/index-derived xlong columns
- root-wide historical helper trees still contain old pre-repair batches, so global null-rate reports remain inflated

So the right next step is **not** to keep blaming raw source gaps.
The right next step is:
1. decide whether to perform a full historical rebuild of affected feature/optimized/helper roots so the repaired raw data is materialized across the entire training corpus
2. continue remediation of the structural `D_*` warmup family, which is still a genuine current-tail issue

## Bottom Line
- raw-gap repair: successful
- current latest rebuilt tail batches: healthy for premium/index-derived xlong families
- root-wide historical corpus: still partially stale
- remaining active data-quality issue: structural `D_*` warmup nulls

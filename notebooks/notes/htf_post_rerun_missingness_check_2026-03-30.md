# HTF Post-Rerun Missingness Check 2026-03-30

## Scope
- Validate the current live HTF outputs after the `2026-03-28` production rerun.
- Answer one narrow question: do the rebuilt final helper parquets contain missing values inside current live batches?

## Evidence Used
- Run log:
  - `test_output/htf_run_logs/htf_pythonscript_20260328_021004_pid898685.log`
- Run status:
  - `test_output/htf_run_logs/htf_pythonscript_20260328_021004_pid898685_status.json`
- Current validation usability reports:
  - `test_output/htf_validation_usability/8h_latest.json`
  - `test_output/htf_validation_usability/24h_latest.json`
  - `test_output/htf_validation_usability/7d_latest.json`
- Direct current parquet spot-checks:
  - `data/htf_with_helpers/1m/target_4class/batch_0001.parquet`
  - `data/htf_with_helpers_24h_shift12h/1m/target_4class/batch_0002.parquet`
  - `data/htf_with_helpers_7d/1m/target_4class/batch_0002.parquet`

## Run Completion
- The rerun finished cleanly.
- Status file shows:
  - `reason = "shutdown"`
  - final stage `CELL 14 / all/-/validation`
- Log tail shows:
  - `7d/C/1m/optimization` completed
  - `7d/C/1m/helpers` completed
  - final validation completed with `[HTF][DONE ] regime=all | stage=validation`

## Conclusion
No. The current rebuilt final helper parquets still contain missing values inside live batches.

The good news is that the previously known all-null model-facing columns no longer appear as `all_null_columns` in the current helper usability reports. The `RIS-165` cleanup seems to have removed the worst all-null columns from the rebuilt optimized/helper outputs.

But high-null columns still remain in current live helper outputs, and direct parquet spot-checks confirm that those nulls are present in the saved batches themselves.

## Current Helper Output Summary

### 8h helpers
- `8h/B`
  - `all_null_columns = []`
  - high-null columns:
    - `D_dist_bot5_low_w120`: `50.00%`
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.85%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.85%`
    - `F_I_N_S_fundingZscore_long_zsc`: `29.68%`
    - `F_I_N_S_fundingZscore_xlong_zsc`: `29.39%`
- `8h/C`
  - `all_null_columns = []`
  - high-null columns:
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.86%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.86%`
    - `F_I_N_S_fundingZscore_xlong_zsc`: `29.68%`

### 24h helpers
- `24h/B`
  - `all_null_columns = []`
  - high-null columns:
    - `F_I_N_S_fundingZscore_long_zsc`: `52.90%`
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.85%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.85%`
    - `D_dist_avg_high_w240`: `33.33%`
    - `D_dist_avg_low_w240`: `33.33%`
- `24h/C`
  - `all_null_columns = []`
  - high-null columns:
    - `F_I_N_S_fundingZscore_long_zsc`: `76.79%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.86%`
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.86%`
    - `F_I_N_S_fundingZscore_xlong_zsc`: `30.15%`

### 7d helpers
- `7d/B`
  - `all_null_columns = []`
  - high-null columns:
    - `F_I_N_S_fundingZscore_long_zsc`: `62.92%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.84%`
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.84%`
    - `F_I_N_S_fundingZscore_xlong_zsc`: `29.19%`
- `7d/C`
  - `all_null_columns = []`
  - high-null columns:
    - `F_I_N_S_fundingZscore_long_zsc`: `66.77%`
    - `D_F_N_S_premiumZscore_xlong_zsc`: `47.86%`
    - `X_D_fundingBasisPressure_xlong_pct`: `47.86%`
    - `F_I_N_S_fundingZscore_xlong_zsc`: `29.90%`

## Direct Current Batch Spot-Checks

### `8h/B` current helper batch
- file: `data/htf_with_helpers/1m/target_4class/batch_0001.parquet`
- rows: `240`
- null counts:
  - `D_dist_bot5_low_w120`: `121` (`50.42%`)
  - `D_F_N_S_premiumZscore_xlong_zsc`: `240` (`100.00%`)
  - `F_I_N_S_fundingZscore_long_zsc`: `240` (`100.00%`)

### `24h/C` current helper batch
- file: `data/htf_with_helpers_24h_shift12h/1m/target_4class/batch_0002.parquet`
- rows: `720`
- null counts:
  - `F_I_N_S_fundingZscore_long_zsc`: `482` (`66.94%`)
  - `D_F_N_S_premiumZscore_xlong_zsc`: `322` (`44.72%`)
  - `X_D_fundingBasisPressure_xlong_pct`: `322` (`44.72%`)

### `7d/B` current helper batch
- file: `data/htf_with_helpers_7d/1m/target_4class/batch_0002.parquet`
- rows: `5040`
- null counts:
  - `F_I_N_S_fundingZscore_long_zsc`: `2412` (`47.86%`)
  - `D_F_N_S_premiumZscore_xlong_zsc`: `2436` (`48.33%`)
  - `X_D_fundingBasisPressure_xlong_pct`: `2436` (`48.33%`)

## Interpretation
- The rerun completed and rebuilt the intended artifacts.
- The worst all-null final columns appear to have been removed from the current model-facing outputs.
- Final helper parquets are still not missing-free.
- Remaining null-heavy families are still concentrated in:
  - funding z-score features
  - premium z-score xlong
  - funding-basis pressure xlong
  - some `D_*` distance windows

## Next Actions
- Decide whether final helper outputs are allowed to contain bounded missingness at all.
- If the answer is no, make final helper usability a hard-fail gate.
- Then redesign, remove, or post-filter the remaining null-heavy feature families before treating these parquets as fully model-ready.

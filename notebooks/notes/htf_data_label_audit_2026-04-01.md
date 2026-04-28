# HTF Data And Label Audit - 2026-04-01

## Scope

Verify the current saved HTF artifacts and the built 1m target/label roots after the latest production changes.

Artifacts used:

- `test_output/htf_data_label_audit/validation_rows_20260401.json`
- `test_output/htf_data_label_audit/validation_summary_20260401.json`
- `test_output/htf_data_label_audit/validation_failed_20260401.json`
- `test_output/htf_data_label_audit/target_distribution_20260401.json`

## Headline Result

The current saved HTF corpus passes the shared production validator cleanly:

- total validation rows: `552`
- failed rows: `0`

This includes combined, features, labels, optimized, helpers, and cross-family checks across:

- regimes: `8h`, `24h`, `7d`
- families: `B`, `C`
- timeframes: `1m`, `15m`

## Data / Label Integrity Result

The current label roots are structurally healthy.

Verified by the shared validator:

- required label columns present
- no duplicate `(batch_id, timestamp)` pairs within label batches
- no null `timestamp`
- no null `batch_id`
- family metadata backfilled
- `target_4class` restricted to `{-1, 0, 1, 2, 3}`
- `target_breakfree` restricted to `{-1, 0, 1, 2}`
- `target_breakfree = -1` whenever `target_4class = -1`
- valid row count per batch matches the regime contract
- no late labeled rows beyond the allowed entry window
- `close_end` matches the batch end close used by breakfree labeling

## Label Coverage

Current saved label batch coverage:

- `8h/B`: `5670` batches, `batch_0001 .. batch_5670`
- `8h/C`: `5669` batches, `batch_0001 .. batch_5669`
- `24h/B`: `1890` batches, `batch_0001 .. batch_1890`
- `24h/C`: `1890` batches, `batch_0001 .. batch_1890`
- `7d/B`: `270` batches, `batch_0002 .. batch_0271`
- `7d/C`: `270` batches, `batch_0002 .. batch_0271`

The weekly roots starting at `batch_0002` are expected and valid. The validator confirms they match the eligible weekly label-batch contract.

## Target Distribution Summary

`target_4class = -1` is not corruption. It is the expected withheld / non-trainable sentinel outside the valid label window.

### 8h/B

- total rows: `2,721,207`
- valid `target_4class` rows: `1,360,635`
- withheld `target_4class` rows: `1,360,572`
- `target_4class`: `0=346,775`, `1=324,015`, `2=374,866`, `3=314,979`
- `target_breakfree`: `0=534,488`, `1=507,017`, `2=319,130`

### 8h/C

- total rows: `2,720,967`
- valid `target_4class` rows: `1,360,560`
- withheld `target_4class` rows: `1,360,407`
- `target_4class`: `0=351,995`, `1=322,626`, `2=375,409`, `3=310,530`
- `target_breakfree`: `0=539,040`, `1=518,650`, `2=302,870`

### 24h/B

- total rows: `2,721,207`
- valid `target_4class` rows: `1,360,800`
- withheld `target_4class` rows: `1,360,407`
- `target_4class`: `0=223,748`, `1=453,767`, `2=227,630`, `3=455,655`
- `target_breakfree`: `0=561,859`, `1=552,069`, `2=246,872`

### 24h/C

- total rows: `2,720,487`
- valid `target_4class` rows: `1,360,395`
- withheld `target_4class` rows: `1,360,092`
- `target_4class`: `0=265,228`, `1=397,004`, `2=294,555`, `3=403,608`
- `target_breakfree`: `0=577,544`, `1=525,944`, `2=256,907`

### 7d/B

- total rows: `2,716,887`
- valid `target_4class` rows: `1,360,800`
- withheld `target_4class` rows: `1,356,087`
- `target_4class`: `0=46,191`, `1=620,925`, `2=42,102`, `3=651,582`
- `target_breakfree`: `0=601,848`, `1=556,224`, `2=202,728`

### 7d/C

- total rows: `2,711,847`
- valid `target_4class` rows: `1,356,075`
- withheld `target_4class` rows: `1,355,772`
- `target_4class`: `0=33,333`, `1=600,806`, `2=31,449`, `3=690,487`
- `target_breakfree`: `0=619,845`, `1=505,926`, `2=230,304`

## Interpretation

Current saved HTF labels look correct under the current production contract.

Important nuance:

- the validator says the saved corpus is structurally valid
- it does **not** say the class balance is ideal for modeling

Main modeling implication from the saved targets:

- `7d` regimes are strongly concentrated in classes `1` and `3`
- `7d` classes `0` and `2` are comparatively rare

That is a modeling/imbalance issue to handle downstream, not a labeling-integrity failure.

## Conclusion

The current saved HTF data and label outputs are valid under the shared production validation contract.

At the level of saved artifacts:

- data stages validate cleanly
- label stages validate cleanly
- target ranges are correct
- weekly label coverage is correct
- no label corruption was found

The next questions, if needed, are modeling questions rather than artifact-integrity questions:

- class imbalance handling
- regime-specific target usefulness
- training-set sampling/weighting policy

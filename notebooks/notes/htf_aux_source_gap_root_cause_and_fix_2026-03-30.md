# HTF Auxiliary Source Gap Root Cause And Fix 2026-03-30

## Scope
- inspect the fetched raw `mark/index/premium` sources directly
- determine whether the current long-window feature nulls come from random
  exchange holes or a deterministic upstream fetch bug
- choose the safest fix path consistent with the repo's causal/data-quality rules

## Evidence
- raw 1m gap scan:
  [htf_aux_source_gap_scan_20260330.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_aux_source_gap_scan_20260330.json)
- interval summary across all fetched auxiliary intervals:
  [htf_aux_source_gap_interval_summary_20260330.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_aux_source_gap_interval_summary_20260330.json)
- downstream root-cause trace:
  [htf_current_missing_value_root_cause_trace_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_current_missing_value_root_cause_trace_2026-03-30.md)
- fetcher code:
  [fetch_bybit_market_data.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/fetchingByBit/fetch_bybit_market_data.py)

## Main Conclusion
The dominant auxiliary-source gaps are **not random exchange noise**.

They are primarily a **deterministic page-boundary bug in the auxiliary
mark/index/premium fetcher pagination logic**.

That means the best first fix is upstream:
- fix the raw fetcher pagination
- repair the affected raw auxiliary files
- then rebuild downstream HTF features and final model-facing outputs

This is better than trying to hide the issue with downstream feature-level gap
filling first.

## What The Raw Data Shows

### 1m sources
Current raw files:
- `fetchingByBit/premium-price-1m-bybit-linear/btcusdt_premium.parquet`
- `fetchingByBit/index-price-1m-bybit-linear/btcusdt_index.parquet`
- `fetchingByBit/mark-price-1m-bybit-linear/btcusdt_mark.parquet`

Observed:
- all three start at `2021-01-01 00:01 UTC`
- premium/index each have `2712` gap events and `2712` missing timestamps
- mark has `2712` gap events and `2712` missing timestamps
- every detected gap is exactly **one missing minute**
- the dominant spacing between gap events is **1001 bars**

This is not the pattern of random exchange downtime.
It is the pattern of dropping one boundary bar per 1000-row API page.

### Cross-source overlap
Observed overlap of actual missing minute timestamps:
- `index & mark`: `2712 / 2712` shared
- `premium & index & mark`: `2660` shared
- premium has `52` extra missing timestamps not shared by index/mark

Interpretation:
- the majority of gaps come from the same deterministic fetch pattern
- premium has a small additional divergence near the end, but that is secondary

### Same pattern across multiple intervals
Observed gap-event counts:

| Source | 1m | 5m | 15m | 1h | 4h | 1d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| premium | 2712 | 539 | 177 | 42 | 9 | 0 |
| index | 2712 | 538 | 176 | 42 | 9 | 0 |
| mark | 2712 | 538 | 176 | 42 | 9 | 0 |

This is exactly what you would expect from the same pagination bug affecting
every interval that needs more than one API page. `1d` is unaffected because it
never reaches the page boundary count.

## Exact Upstream Root Cause
In [fetch_mark_index_premium()](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/fetchingByBit/fetch_bybit_market_data.py),
the old logic used:

```python
window_ms = step_ms * 1000
cur_end = min(cur_start + window_ms, end_ts)
```

With inclusive `[start, end]` API semantics and `limit=1000`, that request span
contains **1001 timestamps**, but the API still returns at most 1000 rows. One
boundary bar gets dropped every page, and then pagination advances from the last
returned timestamp:

```python
cur_start = newest_time + step_ms
```

That is why the raw feeds show one missing bar roughly every 1001 bars.

The kline fetcher in the same file already avoids this bug correctly by using:

```python
cur_end = min(cur_start + step_window_ms - step_ms, end_ts)
```

## Implemented Code Fix
The auxiliary fetcher has been patched to match the correct kline pagination
semantics:

- keep `1000` bars per request
- use an inclusive window ending at `cur_start + window_ms - step_ms`

Patched file:
- [fetch_bybit_market_data.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/fetchingByBit/fetch_bybit_market_data.py)

This prevents future fetches from introducing the same systematic boundary gaps.

## Best Fix Path

### Step 1. Keep the fetcher patch
Already done.

### Step 2. Repair the affected raw auxiliary sources
Because the gaps are already baked into the saved raw files, the fetcher patch
alone is not enough.

Affected source families:
- `mark-price-*`
- `index-price-*`
- `premium-price-*`

Affected intervals:
- `1m`
- `5m`
- `15m`
- `1h`
- `4h`

`1d` does not appear affected.

### Step 3. Rebuild downstream HTF artifacts that depend on those sources
At minimum:
- HTF features
- optimized outputs
- helper outputs

### Step 4. Re-audit the remaining null-heavy long-window families
Only after raw source repair should we decide what residual null-heavy behavior
is still real and requires feature-policy decisions.

## Why Upstream Repair Is Better Than Downstream Filling First
Repo data-quality docs already say training should only proceed on gap-free
source data. These gaps are deterministic fetch loss, not unavoidable market
behavior.

So the safest order is:
1. repair raw data quality first
2. then evaluate whether any remaining null-heavy features still need semantic
   redesign

If we filled downstream features first, we would be masking a known upstream
data defect.

## Remaining Open Question
After the upstream raw repair, we still need to re-check whether:
- `D_F_N_S_premiumZscore_xlong_zsc`
- `X_D_fundingBasisPressure_xlong_pct`

remain null-heavy due to genuine sparse exchange holes or just because of the
current fetch bug.

That decision should be made only after the repaired raw auxiliary sources are
in place.

## Bottom Line
The best way to fix the source-gap issue is:
- **upstream pagination fix first**
- **raw auxiliary refetch/backfill second**
- **downstream HTF rebuild third**

Not downstream imputation first.

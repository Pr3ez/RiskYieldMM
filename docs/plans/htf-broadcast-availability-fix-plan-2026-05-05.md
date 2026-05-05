# HTF Broadcast Availability Fix Plan

- **Date:** 2026-05-05
- **Status:** phase 1-2 implemented and smoke-verified in `compute_htf_features.py`
- **Related audit:** `docs/validation/htf-feature-helper-temporal-audit-2026-05-05.md`

## Summary

The original audit found that `compute_htf_features.py::broadcast_higher_tf()` floors lower-timeframe timestamps to the current higher-timeframe boundary, while its docstring claims it uses the last complete higher-timeframe value.

After deeper investigation, this is best classified as an unsafe missing timestamp contract, not a confirmed current leakage bug for all active sources.

Current 1m HTF auxiliary sources are:

| Source | Current 1m resolution | Local/API evidence | Current risk |
|---|---:|---|---|
| OHLCV | native 1m | Bybit kline REST timestamp is candle start; websocket has `confirm=true` when closed | safe if prediction happens after 1m close |
| Mark/index/premium | native 1m | kline-style endpoints, candle start timestamps | safe if prediction happens after 1m close |
| Open interest | 5m broadcast | Bybit returns 5m records at exact 5m timestamps; live latest at 10:10 when server time was 10:14 | likely availability/snapshot timestamp |
| Long/short ratio | 5m broadcast | Bybit returns 5m records at exact 5m timestamps; docs call this a data recording period but do not define start/end | likely availability timestamp, still ambiguous |
| Funding rate | 8h broadcast | Bybit docs describe returned rate as the last funding rate settled at the funding timestamp | availability/settlement timestamp |

The code becomes unsafe if a future source is a period-start aggregate and is broadcast without an availability offset.

## External Source Check

Official Bybit docs checked:

- Kline REST docs: `/v5/market/kline` returns `startTime` as the start time of the candle, and `closePrice` can be the last traded price when the candle is not closed.
  URL: https://bybit-exchange.github.io/docs/v5/market/kline
- Kline websocket docs: `confirm=true` means the candle has closed.
  URL: https://bybit-exchange.github.io/docs/v5/websocket/public/kline
- Open interest docs: `/v5/market/open-interest` exposes `intervalTime` and `timestamp`, but does not explicitly say period start or availability time.
  URL: https://bybit-exchange.github.io/docs/v5/market/open-interest
- Long/short ratio docs: `/v5/market/account-ratio` uses a data recording period and returns `timestamp`, but does not explicitly define the timestamp as period start or end.
  URL: https://bybit-exchange.github.io/docs/v5/market/long-short-ratio
- Funding history docs: if current time is UTC 12 and the funding interval is 8 hours, the endpoint returns the last funding rate settled at UTC 8.
  URL: https://bybit-exchange.github.io/docs/v5/market/history-fund-rate

Live public API probe at 2026-05-05 10:14 UTC:

```text
open interest latest 5m timestamps: 10:10, 10:05, 10:00
long/short latest 5m timestamps: 10:10, 10:05, 10:00
funding latest timestamps: 08:00, 00:00, previous day 16:00
```

This supports treating OI/L/S/funding timestamps as availability or sampled-at timestamps, but the docs are not precise enough to leave the behavior implicit.

## Local Code Findings

Current source metadata in `DATA_SOURCE_PATTERNS` contains file patterns and columns only. It does not encode:

- whether a source timestamp is a candle start, snapshot time, settlement time, period end, or availability time;
- whether the source should be shifted before joining;
- whether the lower-timeframe row timestamp is the bar start or prediction availability time;
- what publication delay should be assumed in live mode.

Current broadcast implementation:

```python
df_base["_merge_ts"] = base_merge_ts.dt.floor(f"{high_mins}min")
df_high["_merge_ts"] = high_merge_ts
df_merged = df_base.merge(df_high[cols_to_merge], on="_merge_ts", how="left")
```

Synthetic example with current behavior:

```text
5m source rows: 00:00=100, 00:05=105
1m rows 00:00..00:04 all receive 00:00=100
1m rows 00:05..00:09 all receive 00:05=105
```

This is safe for an availability timestamp at 00:00. It is lookahead if `00:00=100` is an aggregate for `[00:00,00:05)` that only becomes known at 00:05.

## Recommended Design

Replace implicit flooring with an explicit availability-aware aligner.

Add timestamp metadata to `DATA_SOURCE_PATTERNS`:

```python
"timestamp_role": "bar_start" | "available_at" | "settlement_at" | "period_start_aggregate",
"availability_offset": "0m" | "source_tf",
"publication_lag": "0m",
```

Initial source policy:

| Source | timestamp_role | availability_offset | Notes |
|---|---|---:|---|
| OHLCV | `bar_start` | `source_tf` | native row is usable after the bar closes |
| mark/index/premium | `bar_start` | `source_tf` | native row is usable after the bar closes |
| open_interest | `available_at` | `0m` | sampled/snapshot endpoint; optional publication lag can be added later |
| long_short_ratio | `available_at` | `0m` | docs ambiguous; treat as sampled/recorded timestamp, but test and document |
| funding_rate | `settlement_at` | `0m` | settled/pre-announced at timestamp |

Add a new alignment function:

```python
def align_source_to_base(
    df_base,
    df_source,
    *,
    target_tf: str,
    source_tf: str,
    data_type: str,
    columns: list[str],
    strict_live: bool = True,
) -> pd.DataFrame:
    ...
```

Internal rules:

1. Compute `base_available_ts`.
   - For candle rows timestamped at bar start, default to `timestamp + target_tf`.
   - If a caller has already converted row timestamps to prediction time, allow `timestamp` directly.
2. Compute `source_available_ts`.
   - `available_at`, `settlement_at`: `source.timestamp + publication_lag`.
   - `bar_start`, `period_start_aggregate`: `source.timestamp + source_tf + publication_lag`.
3. Use `merge_asof(..., direction="backward")` on `source_available_ts <= base_available_ts`.
4. Preserve current `ffill()` repair after alignment only for sources where carry-forward is valid.

This makes future source additions safe by default and removes the mismatch between docstring and implementation.

## Test Plan

Add `tests/test_htf_auxiliary_alignment.py`.

Required unit tests:

1. `test_period_start_aggregate_not_visible_before_available_time`
   - source row timestamp `00:00`, source TF `5m`, role `period_start_aggregate`;
   - 1m base rows before availability must not see the value;
   - row whose available time is `00:05` may see it.

2. `test_available_at_snapshot_is_visible_after_timestamp`
   - source row timestamp `00:05`, role `available_at`;
   - base rows with `base_available_ts >= 00:05` may see the value;
   - earlier rows may not.

3. `test_funding_settlement_alignment`
   - funding timestamp `08:00`, role `settlement_at`;
   - rows whose prediction availability is at or after `08:00` may see the new funding rate.

4. `test_current_broadcast_wrapper_deprecated_or_compat`
   - either remove direct use of `broadcast_higher_tf()` or keep it as a wrapper that delegates to the new aligner with explicit metadata.

5. `test_source_metadata_complete_for_broadcast_sources`
   - every source that can use `method="broadcast"` must define timestamp role and availability offset.

Optional integration test:

- Build a 20-row synthetic 1m OHLCV frame plus synthetic OI/L/S/funding sources and verify exact aligned values before feature calculation.

## Migration Plan

Phase 1: Contract and tests

- Add source timestamp metadata.
- Add alignment tests.
- Keep current effective policy for OI/L/S/funding by setting them to `available_at`/`settlement_at` with zero offset.
- Update the docstring to remove the misleading "last complete higher TF bar" wording.

Phase 2: Alignment implementation

- Replace `broadcast_higher_tf()` calls with `align_source_to_base()`.
- Keep a compatibility wrapper for old callers.
- Add debug output to the source-resolution plan showing timestamp role and availability offset.

Phase 3: Differential audit

- Run synthetic tests.
- Run a small real-data comparison for the first 1,000 rows and latest 1,000 rows:
  - count changed rows per source column;
  - inspect changes around 5m and 8h boundaries;
  - confirm no unexpected broad feature drift.

Phase 4: Artifact version bump and rebuild

- If alignment changes any model-facing values, bump `SHARED_PIPELINE_ARTIFACT_VERSION`.
- Rebuild HTF features, labels, optimized outputs, and helper materializations.
- Re-run:
  - HTF pipeline validation;
  - helper causality audit;
  - walk-forward/backtest checks used for the active 8h/24h/7d B/C surfaces.

## Expected Blast Radius

Small code surface:

- `scripts/feature_engineering/compute_htf_features.py`
- `tests/test_htf_auxiliary_alignment.py`
- `docs/data/data-contract.md` or the current HTF workflow README section
- `docs/validation/htf-feature-helper-temporal-audit-2026-05-05.md`

Potential large artifact surface if enabled alignment changes feature values:

- `data/htf_features*`
- `data/htf_optimized*`
- `data/htf_with_helpers*`
- downstream walk-forward/backtest outputs

## Recommendation

Implement Phase 1 and Phase 2 first. Do not immediately change OI/L/S/funding to a conservative one-source-period lag unless a live replay check proves Bybit publishes those records after the timestamp. With the current evidence, the professional fix is explicit source metadata plus an availability-aware as-of aligner, not a blind one-period shift.

If strict production conservatism is preferred, add a config option:

```text
HTF_AUX_STRICT_PUBLICATION_LAG=source_tf
```

and use it only for live deployment or conservative backtest comparisons.

## Implementation Note

Phase 1-2 implementation now adds:

- source `timestamp_role`, `availability_offset`, and `publication_lag` metadata;
- `source_available_timestamps()` for source availability calculation;
- `HTFFeatureEngine.align_source_to_base()` using `pandas.merge_asof`;
- compatibility routing from `broadcast_higher_tf()`;
- synthetic tests in `tests/test_htf_auxiliary_alignment.py`.

The first real-data differential check over 5,000 1m rows showed no changed values for active OI, long/short, or funding columns compared with the previous floor-join behavior.

The README-path data refresh was then checked on 2026-05-05:

```text
python update_data.py --status   # source-resolution contract OK
python update_data.py --dry-run  # dry-run OK
python update_data.py            # 36/36 fetch sources completed
python update_data.py --verify   # command OK; historical quality monitor still reports older raw-source gaps
```

A latest-batch HTF feature smoke over 24 fresh 1m rows resolved open interest,
long/short ratio, and funding columns with zero missing values.

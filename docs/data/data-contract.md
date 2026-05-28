# HTF Data Contract

This document defines the maintained data surface for the current
multi-regime HTF workflow. It is a contract for local generated artifacts, not a
commit policy for uploading full datasets.

## Source Scope

Every core asset requires normalized OHLCV. Bybit crypto assets can also use
derivatives context streams. Non-crypto Databento/Yahoo assets currently start
as OHLCV-only sources; Bybit-only derivatives streams are not fabricated for
them.

| Source | Required timeframes | Purpose |
|---|---|---|
| OHLCV klines/bars | provider `1m`; canonical derived `15m`, `1h`, `4h`, `8h`, `12h`, `1d` | Base price/volume stream for HTF batches, features, and multi-timeframe analysis across all assets |
| Open interest | `5m`, `15m` | Crypto derivatives positioning context; `5m` broadcasts into `1m` rows |
| Funding rate | native funding interval | Crypto funding pressure features |
| Long/short ratio | `5m`, `15m` | Crypto positioning/sentiment context; `5m` broadcasts into `1m` rows |
| Mark price | `1m`, `15m` | Crypto mark/close deviations and derivatives context |
| Index price | `1m`, `15m` | Crypto basis and price reference context |
| Premium index | `1m`, `15m` | Crypto premium/basis context |

The workflow builds `8h`, `24h`, and `7d` regimes internally. It does not depend
on native 8h exchange candles. Compatibility `*-8h-*` fetcher outputs, when
present, are derived local aggregates for older/supporting scripts and are not
the source of the current `8h` regime.

## Minimum Raw Columns

OHLCV source rows should provide:

```text
timestamp
open
high
low
close
volume
turnover
interval
```

Derivative/context sources should provide a timestamp column plus the source
value columns:

```text
openInterest
fundingRate
buyRatio
sellRatio
mark/index/premium OHLC columns
```

Timestamps must be UTC-normalized and deduplicated by timestamp before they are
used by feature generation.

## Canonical OHLCV Layer

Raw provider files remain unchanged. Before HTF batches are built, provider
OHLCV is canonicalized into market-open bars:

- `BTCUSDT`, `ETHUSDT`: `crypto_24_7`, every minute from first to latest raw
  timestamp.
- `EURUSD`, `USDJPY`, `GC`, `CL`, `ES`, `NQ`:
  `futures_session_observed`, inferred from continuous timestamp segments in
  the locally fetched parquet data.

Open-session missing minutes are carry-forward synthetic no-trade candles:

```text
open = high = low = close = previous close
volume = 0
is_synthetic_no_trade = true
is_open_session_gap_fill = true
```

Closed sessions, daily maintenance breaks, and weekends are not filled. The
current observed-session implementation is data-derived; it does not call an
external exchange-calendar API. Canonical higher-timeframe OHLCV bars are
derived from canonical `1m` bars so gap flags and session metadata survive
aggregation.

Maintained derived canonical OHLCV timeframes:

```text
15m
1h
4h
8h
12h
1d
```

`24h` is accepted by the materializer as an alias for `1d`, but files are
written only under the `1d` directory. Derived bars use bar-open timestamps; a
model feature from one of these bars is only available after
`timestamp + timeframe`. Crypto assets require full wall-clock minute counts
for derived bars. Session assets require all expected market-open canonical
minutes inside the bucket, so session closes, maintenance breaks, and weekends
do not create missing rows.

Canonical rows add:

```text
asset_id
calendar_id
is_market_open
is_synthetic_no_trade
is_open_session_gap_fill
minutes_since_prev_real_bar
session_id
session_date
session_bar_pos
session_minutes_to_close
is_session_open_bar
is_session_close_bar
is_weekly_open_bar
is_weekly_close_bar
```

## Canonical TA Signal Flags

Technical-analysis flags are derived from the canonical OHLCV layer only. They
are not fetched and they do not rewrite HTF feature/helper/label roots.

Source bars:

```text
data/htf_multiasset/{asset}/htf_canonical_ohlcv/{tf}/{asset}_{tf}_canonical.parquet
```

Generated TA artifacts:

```text
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_events.parquet
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_flags.parquet
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_flags_meta.json
data/htf_multiasset/{asset}/ta_compact_signal_flags/{tf}/{asset}_{tf}_ta_compact_events.parquet
data/htf_multiasset/{asset}/ta_compact_signal_flags/{tf}/{asset}_{tf}_ta_compact_flags.parquet
data/htf_multiasset/{asset}/ta_compact_signal_flags/{tf}/{asset}_{tf}_ta_compact_flags_meta.json
```

TA event rows are one row per closed higher-timeframe source bar. Model-facing
TA flags are expanded onto canonical `1m` timestamps only after the source bar
closes. For example, a `15m` signal from a bar opening at `10:00` is first
usable at `10:15`; it must not flag rows inside the `10:00 -> 10:14` source
bar. Session assets expand over the next market-open canonical `1m` rows only,
so weekends and closed maintenance periods are skipped rather than filled.
`signal_valid_until_ts` is the exclusive end of that expanded canonical `1m`
window, so for session assets it is derived from observed market-open rows
rather than wall-clock minutes alone.

Model-facing TA columns use:

```text
ta_{tf}_{indicator}_{signal}_long
ta_{tf}_{indicator}_{signal}_short
ta_{tf}_{indicator}_{state}
ta_{tf}_compact_{signal}
```

Signal metadata columns such as `signal_source_tf`, `signal_bar_open_ts`,
`signal_available_ts`, `signal_valid_until_ts`, `signal_valid_rows`, and
`signal_params_hash` are excluded from Stage-1 model features. When Stage-1
merged dataset assembly is run with `--include-ta-flags`, target TA flags are
prefixed as `T_{asset}__ta_*` and context TA flags as `C_{asset}__ta_*`.
`--ta-signal-set raw`, `compact`, or `all` chooses which reusable TA layer is
joined.

## HTF Batch Metadata

Model-facing HTF rows must carry enough metadata to prove regime/family
alignment:

```text
timestamp
batch_id
period_8h_start
batch_family
family_batch_id
family_period_start
family_period_end
family_bar_pos
source_base_batch_id
source_base_period_start
source_half_in_base
is_label_half
bar_in_batch_norm
batch_regime
batch_duration_hours
family_shift_hours
anchor_utc
entry_window_hours
asset_id
calendar_id
is_market_open
is_synthetic_no_trade
is_open_session_gap_fill
minutes_since_prev_real_bar
session_id
session_date
session_bar_pos
session_minutes_to_close
is_session_open_bar
is_session_close_bar
is_weekly_open_bar
is_weekly_close_bar
expected_rows_in_batch
actual_rows_in_batch
expected_entry_rows
actual_entry_rows
has_synthetic_open_gap_fill
```

`period_8h_start` remains as a compatibility alias even for `24h` and `7d`
regimes. The actual regime is recorded in `batch_regime`.

## Regime Families

| Regime | Duration | Family B | Family C |
|---|---:|---|---|
| `8h` | 8 hours | anchored base family | shifted by 4 hours |
| `24h` | 24 hours | anchored base family | shifted by 12 hours |
| `7d` | 168 hours | anchored base family | shifted by 84 hours |

For `1m` labels, crypto full batches still contain the fixed 24/7 row counts
below. Session-asset expected rows are calendar-aware: they equal market-open
canonical timestamps inside the period, excluding closed sessions and breaks.

| Regime | Crypto full batch rows | Crypto entry-window rows |
|---|---:|---:|
| `8h` | 480 | 240 |
| `24h` | 1,440 | 720 |
| `7d` | 10,080 | 5,040 |

Label eligibility requires complete entry and label windows by calendar for
both `1m` and `15m`, not fixed row counts for session assets.

## Model-Facing Label Columns

The active HTF label surface is `1m/target_4class`. Stage-1 multi-asset
assembly keeps labels target-specific: context labels are never joined as
features, and merged Stage-1 labels are filtered target-label rows under
`data/htf_multiasset_merged/{target}/{context_hash}/{root_id}/labels/1m/`.
TA-enabled merged datasets add a dataset variant directory between
`context_hash` and `root_id`, for example
`data/htf_multiasset_merged/{target}/{context_hash}/ta_raw_15m_1h_4h_8h_12h_1d/{root_id}/`.
The same variant is included in Stage-1 run ids so baseline, raw TA, compact
TA, and combined TA runs cannot share output directories.
Merged feature rows use exact timestamp context joins only. Rows missing any
selected context asset, or containing null model feature values after the join,
are dropped and reported in the manifest. Written merged feature batches must
have no duplicate `timestamp,batch_id` rows and no null model feature values.

Merged Stage-1 roots may be sparse. The original `batch_id` remains the HTF
source identifier, but Stage-1 window planning uses the dense available-batch
sidecar:

```text
data/htf_multiasset_merged/{target}/{context_hash}/{variant?}/{root_id}/stage1_batch_index.parquet
```

Required sidecar columns:

```text
stage1_available_pos
batch_id
batch_start_ts
batch_end_ts
row_count
valid_row_count
target_col
feature_target_col
```

Fold-window artifacts must preserve explicit `train_batch_ids` and
`val_batch_ids` when sparse windows are used. Context rows are still joined only
by exact `timestamp`; the sparse index never authorizes stale/as-of context
fills.

Required label outputs include:

```text
target_4class
target_breakfree
label_window_policy
label_entry_family
label_window_family
label_window_batch_id
label_window_start
label_window_end
dist_avg_high
dist_avg_low
dist_top5_high
dist_bot5_low
remaining_bars
end_return
```

Label rows must be generated without access to future prediction batches outside
the permitted forward-distance label window.

## Incremental Update Contract

The HTF materializer should not recompute stable historical artifacts when new
market rows are appended.

Expected behavior:

- Existing complete source batches are skipped when fingerprints and schema are
  still valid.
- New tail batches are materialized.
- Former partial tail batches may be repaired.
- Label files are repaired when a previously partial batch becomes complete.
- Helper caches are reused when source fingerprints match.
- Validation fails the run when batch row counts, metadata, or cross-family
  coverage are inconsistent.

The focused regression coverage for this behavior is:

```bash
pytest -q tests/test_htf_incremental_resume.py
```

## Tiny Synthetic Example

Raw `1m` input:

| timestamp | open | high | low | close | volume |
|---|---:|---:|---:|---:|---:|
| `2021-01-01T00:00:00Z` | 100.0 | 101.0 | 99.5 | 100.5 | 12.0 |
| `2021-01-01T00:01:00Z` | 100.5 | 101.2 | 100.1 | 100.8 | 10.0 |

Model-facing HTF row:

| timestamp | batch_regime | batch_family | batch_id | family_bar_pos | is_label_half | target_4class |
|---|---|---|---:|---:|---|---:|
| `2021-01-01T00:00:00Z` | `8h` | `B` | 1 | 0 | true | 2 |

This example is intentionally small and synthetic. Real generated artifacts
contain hundreds of feature columns and are stored locally under `data/`.

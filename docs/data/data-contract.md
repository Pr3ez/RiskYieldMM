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
| OHLCV klines/bars | `1m`, `15m` | Base price/volume stream for HTF batches and features across all assets |
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
```

`period_8h_start` remains as a compatibility alias even for `24h` and `7d`
regimes. The actual regime is recorded in `batch_regime`.

## Regime Families

| Regime | Duration | Family B | Family C |
|---|---:|---|---|
| `8h` | 8 hours | anchored base family | shifted by 4 hours |
| `24h` | 24 hours | anchored base family | shifted by 12 hours |
| `7d` | 168 hours | anchored base family | shifted by 84 hours |

For `1m` labels, full batches contain:

| Regime | Full batch rows | Model entry-window rows |
|---|---:|---:|
| `8h` | 480 | 240 |
| `24h` | 1,440 | 720 |
| `7d` | 10,080 | 5,040 |

## Model-Facing Label Columns

The active HTF label surface is `1m/target_4class`. Stage-1 multi-asset
target/context analysis is still pending.

Required label outputs include:

```text
target_4class
target_breakfree
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

# Session-Aware Multi-Asset HTF Implementation

Created: 2026-05-16
Status: implemented in branch, pending full local core run

## Goal

Use one HTF workflow for both crypto and Monday-Friday/session assets:

```text
BTCUSDT, ETHUSDT -> crypto_24_7 -> 8h, 24h, 7d
EURUSD, USDJPY, GC, CL, ES, NQ -> futures_session_observed -> 8h, 24h, 7d
```

Raw provider files stay unchanged. HTF first builds canonical market-open bars,
then computes regimes, features, labels, optimization outputs, helpers, and
validation artifacts from that canonical layer.

## Implemented

- [x] Calendar ids in the HTF asset registry.
- [x] Local-data-derived canonical OHLCV layer.
- [x] Open-session gap fill with zero volume and explicit flags.
- [x] No fill across observed session breaks, weekends, or other closed spans.
- [x] Canonical `15m` derivation from canonical `1m`.
- [x] Calendar/session/fill metadata preserved into combined, feature, label,
      optimized, and helper schemas through `FAMILY_META_COLS`.
- [x] `is_label_half` computed by timestamp window, not fixed row position.
- [x] Label eligibility based on complete calendar entry and outcome windows
      for both `1m` and `15m`.
- [x] Session assets enabled for `8h`, `24h`, and `7d` by default.
- [x] Rollback control: `HTF_SESSION_REGIMES=8h`.
- [x] Unit tests for calendar generation/fills and session `24h`/`7d` labels.

## Local Inference Contract

The first session calendar is inferred from fetched parquet timestamps. It does
not call a web schedule or exchange-calendar API.

Observed session behavior in local data:

- Sunday open around `22:00/23:00 UTC`, depending on the observed UTC shift.
- Daily maintenance break around `20:59 -> 22:00` or `21:59 -> 23:00 UTC`.
- Friday close around `20:59/21:59 UTC`.
- Saturday closed.

Implementation detail: continuous observed timestamp segments are treated as
open sessions. Small missing timestamps inside those segments are filled. Large
gaps split sessions and are not filled.

## Label Contract

The label policy remains:

```text
B entry window -> next C first-half outcome window
C entry window -> next B first-half outcome window
```

Eligibility requires:

- entry window complete by canonical calendar,
- opposite label window complete by canonical calendar,
- both `1m` and `15m` windows present,
- at least one future `15m` bar for distance labels.

The newest tail can remain unlabeled until the future opposite-family window is
available.

## Validation Commands

```bash
python -m pytest tests/test_htf_trading_calendar.py tests/test_htf_multi_asset_pipeline.py -q
python -m pytest tests/test_htf_multi_asset_pipeline.py -q
python -m py_compile notebooks/htf_pythonscript.py scripts/feature_engineering/htf_multiregime_pipeline.py scripts/feature_engineering/htf_trading_calendar.py
git diff --check
```

Recommended real-data smoke:

```bash
HTF_ASSETS=ES \
HTF_ASSET_OUTPUT_MODE=multiasset \
HTF_RUN_OPTIMIZATION=0 \
HTF_RUN_HELPERS=0 \
python notebooks/htf_pythonscript.py
```

Expected before full core run: nonzero valid labels for `8h/B`, `8h/C`,
`24h/B`, `24h/C`, `7d/B`, and `7d/C`.

## Still Pending

- Full local core run across all assets after this branch is accepted.
- Stage-1 multi-asset target/context assembly.
- Cross-asset context features with causal as-of joins.

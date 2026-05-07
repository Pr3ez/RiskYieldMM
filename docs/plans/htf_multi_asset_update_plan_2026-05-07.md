# HTF Multi-Asset Implementation Plan

Created: 2026-05-07
Status: active branch plan

This document is the current multi-asset HTF plan. Older single-asset HTF notes
are historical context only; the branch direction is now per-asset HTF
materialization followed by Stage-1 target selection and optional cross-asset
feature joins.

## Active Asset Set

HTF now targets these assets:

| Asset | Source path | Notes |
|---|---|---|
| `BTCUSDT` | Bybit crypto | OHLCV plus available derivative auxiliary streams |
| `ETHUSDT` | Bybit crypto | OHLCV plus available derivative auxiliary streams |
| `EURUSD` | Databento/Yahoo futures proxy | `6E`, USD per EUR |
| `USDJPY` | Databento/Yahoo futures proxy | `6J`, inverted to USD/JPY-like prices |
| `GC` | Databento/Yahoo futures proxy | Gold futures |
| `CL` | Databento/Yahoo futures proxy | WTI crude futures |
| `ES` | Databento/Yahoo futures proxy | E-mini S&P 500 futures |
| `NQ` | Databento/Yahoo futures proxy | E-mini Nasdaq 100 futures |

The normalized model-facing raw bar contract is:

```text
timestamp, open, high, low, close, volume, interval
```

Provider metadata stays in manifests and registry code. HTF feature/label code
should consume canonical bars, not provider-specific dataframes.

## Implemented

These pieces are implemented in this branch:

1. `scripts/feature_engineering/htf_asset_registry.py`
   - defines the core HTF asset set
   - maps crypto assets to Bybit roots
   - maps non-crypto assets to Databento historical roots and Yahoo recent-tail
     roots

2. Asset-aware raw routing in
   `scripts/feature_engineering/htf_multiregime_pipeline.py`
   - loads only files for the selected asset
   - keeps Databento as historical source priority
   - lets Yahoo replace overlapping recent rows only through the normalized
     recent-tail source

3. Asset-scoped HTF output support
   - multi-asset mode writes under `data/htf_multiasset/{asset}/`
   - legacy global roots are not the default direction for new multi-asset work

4. Symbol-aware crypto auxiliary discovery
   - `compute_htf_features.py` no longer hardcodes `btcusdt`
   - derivative auxiliary streams are used only for assets that have them
   - non-crypto assets start with OHLCV-derived features

5. Opposite-family label windows
   - default label policy is `opposite_family_first_half`
   - B entry rows label from the next C first-half window
   - C entry rows label from the next B first-half window
   - labels store `label_window_policy`, `label_entry_family`,
     `label_window_family`, `label_window_batch_id`, `label_window_start`, and
     `label_window_end`

6. Tests
   - asset-specific raw routing
   - Databento/Yahoo overlap priority
   - B -> C label-window mapping
   - existing HTF incremental and auxiliary alignment tests still pass

## During / Not Yet Implemented

These are the next implementation items:

1. Stage-1 multi-asset dataset assembly
   - choose one prediction target asset at a time
   - read that asset's HTF feature and label roots
   - optionally join causal context features from other assets
   - keep labels target-specific; do not merge labels from other assets into
     the target label

2. Cross-asset context features
   - compute only as-of features available at or before the target timestamp
   - start with lagged returns, volatility/range, rolling correlation/beta,
     relative strength, and basket proxies
   - prefix columns with `ctx_{asset}_...` or `basket_...`
   - add truncation tests to prove no future context leakage

3. Stage-1 runner updates
   - add `--target-asset`
   - add `--context-assets`
   - resolve asset-scoped HTF roots under `data/htf_multiasset/{asset}/`
   - keep current regime/family selection behavior

4. Full production validation on real local data
   - run HTF for all core assets
   - confirm labels exist for every asset/regime/family where enough future
     window data exists
   - inspect latest tails, especially C labels that need the next B window

## Step-By-Step Multi-Asset Workflow

### 1. Fetch / update raw data

From repo root:

```bash
python update_data.py --core --dry-run --htf-only
python update_data.py --core --htf-only
```

Use cost guards when Databento is involved:

```bash
python update_data.py --core --htf-only --max-databento-cost-usd 50
```

The root update command coordinates:

- Bybit for `BTCUSDT`, `ETHUSDT`
- Databento for historical non-crypto futures proxies
- Yahoo only for validated recent-tail continuation when allowed

### 2. Build HTF artifacts for a smoke pair

Use this before a full core run:

```bash
HTF_ASSETS=BTCUSDT,ES \
HTF_ASSET_OUTPUT_MODE=multiasset \
HTF_RUN_OPTIMIZATION=0 \
HTF_RUN_HELPERS=0 \
python notebooks/htf_pythonscript.py
```

Expected output roots:

```text
data/htf_multiasset/btcusdt/
data/htf_multiasset/es/
```

### 3. Build HTF artifacts for all core assets

```bash
HTF_ASSETS=core \
HTF_ASSET_OUTPUT_MODE=multiasset \
python notebooks/htf_pythonscript.py
```

Each asset receives all configured regimes and families:

```text
8h/B, 8h/C, 24h/B, 24h/C, 7d/B, 7d/C
```

For each family the pipeline prepares:

- combined `1m` and `15m` HTF batches
- feature batches
- `15m` distance metrics
- `1m` `target_4class` and `target_breakfree` labels
- optimized/model-facing feature batches
- helper features when enabled
- validation output

### 4. Check labels

Labels are prepared per asset. The expected label policy is:

```text
B entry half -> C first-half outcome window
C entry half -> next B first-half outcome window
```

The newest tail can be unlabeled when the future opposite-family window is not
complete yet. That is correct and should not be force-filled.

### 5. Stage-1 analysis

Stage-1 should merge after HTF is complete:

1. choose target asset
2. load that asset's feature and label roots
3. optionally add causal cross-asset context features
4. run walk-forward selection
5. compare standalone vs cross-asset feature groups with ablations

Do not merge all assets into one target before label preparation. Labels remain
per target asset.

## Validation Checklist

Before Stage-1:

1. `python update_data.py --core --dry-run --htf-only` shows the expected
   providers and no surprise full Databento refetch.
2. Raw `1m` and `15m` files exist for all selected assets.
3. `HTF_ASSETS=core HTF_ASSET_OUTPUT_MODE=multiasset python notebooks/htf_pythonscript.py`
   finishes or fails only on a clearly documented data gap.
4. Each asset has `data/htf_multiasset/{asset}/` output roots.
5. Labels contain `label_window_*` metadata.
6. Latest unlabeled tails are explained by missing future opposite-family
   windows, not by schema or source errors.
7. Stage-1 plan points to the intended target asset roots.

## Research Position On Cross-Asset Features

Cross-asset features are worth adding, but only as causal context after
standalone per-asset HTF outputs are reproducible. The initial feature groups
should be simple and auditable:

- lagged returns of context assets
- realized volatility/range of context assets
- rolling correlation and beta to the target asset
- relative strength pairs: `BTCUSDT/ETHUSDT`, `ES/NQ`, `GC/CL`,
  `EURUSD/USDJPY`
- baskets: risk-on, USD/FX, commodity
- market/session/source missingness flags

Primary references:

- Moskowitz, Ooi, Pedersen, "Time Series Momentum":
  https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf
- Asness, Moskowitz, Pedersen, "Value and Momentum Everywhere":
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1363476
- Pitkajarvi, Suominen, Vaittinen, "Cross-Asset Signals and Time Series
  Momentum": https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2891434
- Rapach, Strauss, Zhou, "International Stock Return Predictability: What is
  the Role of the United States?":
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1508484
- Gu, Kelly, Xiu, "Empirical Asset Pricing via Machine Learning":
  https://www.nber.org/papers/w25398

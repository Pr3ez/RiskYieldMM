# Reproducibility Guide

This guide describes how to reproduce the maintained workflow surfaces without
committing local market data or generated model artifacts.

The full HTF workflow expects a local Python environment with the project
research stack installed. The lightweight verification surface below is suitable
for pull-request review and future hosted CI, but hosted GitHub Actions is
deferred until repository billing allows Actions jobs to run.

## Repository Setup

```bash
git clone https://github.com/Pr3ez/RiskYieldMM.git
cd RiskYieldMM
python -m pip install --upgrade pip
python -m pip install -r requirements-ci.txt
```

For full Stage-1 modelling runs, use the local ML environment that includes
CatBoost and the broader research dependencies. The lightweight setup above
installs the `.[ci]` optional dependency set from `pyproject.toml`, keeping the
contract-check environment tied to the canonical project dependency metadata.

## Lightweight Verification

These checks match the lightweight Python contract:

```bash
ruff check . \
  --select E9,F63,F7,F82 \
  --exclude Archive \
  --exclude notebooks \
  --exclude test_output

pytest -q \
  tests/test_fetch_bybit_market_data.py \
  tests/test_htf_workflow_contract.py \
  tests/test_htf_incremental_resume.py
```

Extension checks:

```bash
cd extensions/astra-workflow
npm ci
npm run compile
npm run lint
npm audit --audit-level=low
```

Rust helper checks:

```bash
cd riskyield_rust
cargo check --locked
```

## Fetch HTF Source Data

The active HTF source contract uses provider `1m` OHLCV for each core asset,
then derives canonical `15m`, `1h`, `4h`, `8h`, `12h`, and `1d` bars locally
from canonical `1m`. Crypto assets also use available Bybit derivative context.
The repo-root orchestrator coordinates Bybit crypto, Databento historical
futures proxies, and validated Yahoo recent-tail continuation.

```bash
python update_data.py --core --dry-run --htf-only
python update_data.py --core --htf-only --max-databento-cost-usd 50
python update_data.py --core --derive-ohlcv-timeframes
```

The fetcher is incremental. It should resume from the latest available local
timestamp for each source instead of restarting from the beginning. Relevant
source folders include:

- `sorted-1m-bybit-linear/`
- `sorted-15m-bybit-linear/`
- `fetchingMultiAsset/sorted-1m-databento-futures/`
- `fetchingMultiAsset/sorted-15m-databento-futures/`
- `fetchingMultiAsset/sorted-1m-yfinance-futures/`
- `fetchingMultiAsset/sorted-15m-yfinance-futures/`
- `open-interest-15m-bybit-linear/`
- `funding-rate-bybit-linear/`
- `long-short-ratio-15m-bybit-linear/`
- `mark-price-1m-bybit-linear/`
- `mark-price-15m-bybit-linear/`
- `index-price-1m-bybit-linear/`
- `premium-price-15m-bybit-linear/`

Derived canonical OHLCV files are written under:

```text
data/htf_multiasset/{asset}/htf_canonical_ohlcv/{15m,1h,4h,8h,12h,1d}/
```

`24h` is accepted by the materializer as an alias for `1d`; only `1d` is
written on disk.

## Build HTF Features And Labels

Run the maintained production launcher:

```bash
HTF_ASSETS=core HTF_ASSET_OUTPUT_MODE=multiasset \
python notebooks/htf_pythonscript.py
```

The launcher delegates the real work to
`scripts/feature_engineering/htf_multiregime_pipeline.py`.

Important behavior:

- Existing complete batches are reused.
- Freshly fetched rows are appended through incremental batch processing.
- Feature, label, optimized, and helper stages write metadata/fingerprint files.
- Validation checks run at the end unless explicitly disabled in configuration.

Expected local outputs are under `data/`, including:

- `data/htf_multiasset/{asset}/htf_features*/`
- `data/htf_multiasset/{asset}/htf_4class_labels*/`
- `data/htf_multiasset/{asset}/htf_optimized*/`
- `data/htf_multiasset/{asset}/htf_with_helpers*/`

These outputs are generated artifacts and are not committed.

## Run Stage-1 Walk-Forward Analysis

The Stage-1 launcher can run legacy six-root analysis or build a
Stage-1-compatible merged dataset from per-asset HTF outputs first. In
multi-asset mode, each run has one target asset; context assets are joined by
exact `timestamp`, and labels come only from the target asset.

Plan a run first:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py --plan-only
```

Build one merged multi-asset root without training:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT \
  --context-assets ETHUSDT,EURUSD,USDJPY,GC,CL,ES,NQ \
  --roots 8h/B \
  --plan-only
```

Example focused run for the documented `8h/B` root:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --target-assets BTCUSDT \
  --context-assets ETHUSDT,EURUSD,USDJPY,GC,CL,ES,NQ \
  --roots 8h/B \
  --n-steps 1 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

Current local smoke evidence for `BTCUSDT`, `8h/B`, and `core-ex-target`
context:

```text
all-core exact timestamp rows: 413,652
merged manifest duplicate_count: 0
merged manifest null_feature_count: 0
Stage-1 smoke: steps_ok=1, steps_error=0
quality: weak smoke only, winner_accuracy=0.2667, macro_f1=0.1053
```

That smoke validates plumbing, not predictive quality. Run more walk-forward
steps and inspect `stage1_step_summary.json` before making modelling decisions.

Generated Stage-1 outputs are written below:

```text
data/htf_multiasset_merged/{target}/{context_hash}/{root_id}/
data/htf_backtest_results/stage1_catboost_*_live/
```

Merged roots include a `stage1_batch_index.parquet` sidecar beside
`manifest.json`. Exact timestamp context joins can make merged batch ids
sparse; this is supported. Stage-1 keeps original `batch_id` values for
traceability while train/validation windows count dense available batches and
fold artifacts preserve explicit `train_batch_ids` / `val_batch_ids`.

Tracked summary snapshots live under `test_output/` when they are intentionally
kept as review artifacts.

## Expected Review Artifacts

For a public/code-review pass, the important artifacts are:

- [`HTF_8H_B_WALKFORWARD_ANALYSIS.md`](../HTF_8H_B_WALKFORWARD_ANALYSIS.md)
- [`FEATURE_AND_DATASET_SNAPSHOT.md`](../FEATURE_AND_DATASET_SNAPSHOT.md)
- [`docs/data/data-contract.md`](data/data-contract.md)
- [`docs/architecture/htf-workflow-architecture.md`](architecture/htf-workflow-architecture.md)
- [`docs/results/htf-8h-b-results-card.md`](results/htf-8h-b-results-card.md)

The repository intentionally separates code and review summaries from local data
and model artifacts.

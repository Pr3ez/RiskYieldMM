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

The active HTF source contract uses native `1m` and `15m` OHLCV plus derivative
context from Bybit. The 8h aggregate files are retained for compatibility, but
the multi-regime HTF workflow builds `8h`, `24h`, and `7d` batches internally
from the lower-timeframe sources.

```bash
cd fetchingByBit
python update_data.py --status
python update_data.py
```

The fetcher is incremental. It should resume from the latest available local
timestamp for each source instead of restarting from the beginning. Relevant
source folders include:

- `sorted-1m-bybit-linear/`
- `sorted-15m-bybit-linear/`
- `open-interest-15m-bybit-linear/`
- `funding-rate-bybit-linear/`
- `long-short-ratio-15m-bybit-linear/`
- `mark-price-1m-bybit-linear/`
- `mark-price-15m-bybit-linear/`
- `index-price-1m-bybit-linear/`
- `premium-price-15m-bybit-linear/`

## Build HTF Features And Labels

Run the maintained production launcher:

```bash
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

- `data/htf_features*/`
- `data/htf_4class_labels*/`
- `data/htf_optimized*/`
- `data/htf_with_helpers*/`

These outputs are generated artifacts and are not committed.

## Run Stage-1 Walk-Forward Analysis

Plan a run first:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py --plan-only
```

Example focused run for the documented `8h/B` root:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --roots 8h/B \
  --n-steps 500 \
  --resume-mode skip_completed \
  --stage1-version v2 \
  --stage1-v2-execution-mode fixed_policy
```

Generated Stage-1 outputs are written below:

```text
data/htf_backtest_results/stage1_catboost_*_live/
```

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

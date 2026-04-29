# Contributing

Thank you for improving RiskYieldMM. This repository is a research-oriented ML
system for leakage-aware cryptocurrency perpetual-futures workflows. Contributions
should preserve reproducibility, temporal correctness, and clear artifact
boundaries.

## Scope

Good contributions include:

- bug fixes in feature engineering, backtesting, analysis, or artifact handling
- tests and smoke fixtures that make the workflow easier to reproduce
- documentation that clarifies current code behavior
- refactors that reduce hidden state, notebook coupling, or path assumptions
- validation work around temporal continuity, leakage prevention, and schema
  consistency

Out of scope:

- trading advice, live trading signals, or profit guarantees
- committed API keys, credentials, private datasets, or personal files
- large generated outputs unless explicitly agreed
- unrelated style churn that makes research history harder to review

## Local Setup

Use Python 3.10 or newer. A typical editable setup is:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

If you need the Rust extension:

```bash
pip install maturin
maturin develop --release -m riskyield_rust/Cargo.toml
```

Project-root resolution supports:

```bash
export RISKYIELDMM_PROJECT_ROOT="/path/to/RiskYieldMM"
```

## Data And Artifacts

- Keep private/generated data out of commits unless the file is an intentional,
  small fixture or audit artifact.
- Preserve artifact metadata when changing schemas or output paths.
- For parquet/data changes, document the source, batch range, timestamp range,
  and whether the data is synthetic, fixture, or real historical data.
- Do not commit secrets, exchange credentials, personal CV files, or local
  machine paths.

## Temporal ML Requirements

RiskYieldMM is sensitive to look-ahead bias. Any workflow change that touches
features, labels, walk-forward splits, helper caches, model selection, or
post-processing should explain:

- what information is available at prediction time
- how train/validation/test windows are separated
- whether purge/embargo or tail-exclusion behavior changed
- which artifacts were regenerated or invalidated
- which leakage checks or smoke tests were run

## Testing And Validation

Run the narrowest checks that cover your change. Useful commands include:

```bash
python -m compileall -q scripts prediction_analysis notebooks
python test_catboost_optimization_unit.py
python test_hmm_rust.py
```

If a command cannot run because dependencies or data are unavailable, state that
clearly in the pull request and include the exact failure.

For documentation-only changes, check links, paths, and stale claims against the
current code. Code is the source of truth when older notes disagree with current
implementation.

## Pull Request Expectations

Every pull request should include:

- a concise summary of the change
- affected paths and artifact contracts
- validation commands and outcomes
- known limitations or skipped checks
- screenshots/plots only when they materially help review

Keep changes focused. Separate large data migrations, notebook exports,
algorithmic changes, and documentation cleanup when possible.

## Community Standards

By participating, you agree to follow `CODE_OF_CONDUCT.md`. Report
security-sensitive issues through `SECURITY.md` rather than public issue details.

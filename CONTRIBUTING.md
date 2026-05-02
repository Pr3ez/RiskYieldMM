# Contributing

RiskYieldMM is maintained as a research codebase with production-style review
discipline. Contributions should preserve temporal correctness, artifact
reproducibility, and reviewable repository size.

## Scope

Good contributions include:

- bug fixes in feature engineering, backtesting, analysis, or artifact handling,
- tests and small fixtures that make the workflow easier to reproduce,
- documentation that clarifies current code behavior,
- refactors that reduce hidden state, notebook coupling, or path assumptions,
- validation work around temporal continuity, leakage prevention, and schema
  consistency.

Out of scope:

- trading advice, live trading signals, or profit guarantees,
- committed API keys, credentials, private datasets, or personal files,
- large generated outputs unless they are explicitly curated review artifacts,
- unrelated style churn that makes research history harder to review.

## Development Workflow

1. Start from current `main`.

   ```bash
   git checkout main
   git pull --ff-only origin main
   ```

2. Create a focused branch.

   ```bash
   git checkout -b docs/my-change
   ```

3. Keep changes scoped. Avoid combining documentation, dependency upgrades,
   generated data, and behavioral code changes in one commit unless they are
   tightly related.

4. Run the relevant checks before opening a pull request.

   ```bash
   # Python contract checks
   python -m pip install -r requirements-ci.txt
   ruff check . --select E9,F63,F7,F82 --exclude Archive --exclude notebooks --exclude test_output
   pytest -q tests/test_fetch_bybit_market_data.py tests/test_htf_workflow_contract.py tests/test_htf_incremental_resume.py

   # VS Code extension checks
   cd extensions/astra-workflow
   npm ci
   npm run compile
   npm run lint
   npm audit --audit-level=low

   # Rust helper checks
   cd ../../riskyield_rust
   cargo check --locked
   ```

5. Open a pull request to `main`. The protected branch expects review before
   regular collaborators can change `main`.

## Full Local Setup

Use Python 3.10 or newer. A typical lightweight setup is:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-ci.txt
python -m pip install -e .
```

For the Rust helper module:

```bash
python -m pip install maturin
maturin develop --release -m riskyield_rust/Cargo.toml
```

For the VS Code extension:

```bash
cd extensions/astra-workflow
npm ci
npm run compile
```

## Data And Artifact Policy

Do not commit raw market data, generated Parquet datasets, model artifacts,
local run logs, or personal working files. The repository documents the data
contract and includes small schema/sample snippets instead of uploading full
datasets.

Ignored by default:

- `data/`
- `datasets/`
- `precomputed/`
- model output directories
- generated Parquet/CSV/HDF/NPZ files
- extension `node_modules/`

Tracked `test_output/` files are historical review snapshots only. New generated
outputs should be committed only when they are intentionally curated as an audit
artifact.

## Dependabot PRs

Dependabot may open dependency update pull requests. Review them like normal
code:

- confirm they are not superseded by a newer update,
- run the affected checks,
- approve only if compile/lint/audit or build checks pass,
- request changes when a version update requires migration work.

Security updates can still break tooling, so do not merge automatically unless
the checks prove the change is safe.

## Time-Series ML Requirements

Any change to data, feature, label, or validation logic should explicitly
consider:

- chronological train/validation/test separation,
- no look-ahead access to future rows,
- stable feature values when new rows are appended,
- batch and family alignment across `8h`, `24h`, and `7d`,
- resume behavior for already-computed artifacts,
- validation evidence in tests or audit output.

## Documentation Placement

- Put current design docs under `docs/`.
- Put chronological investigation notes under `notebooks/notes/`.
- Put retired designs and legacy references under `Archive/`.
- Keep root-level markdown limited to project identity, contribution/security
  policy, changelog, and high-signal review snapshots.

## Community And Security

By participating, you agree to follow `CODE_OF_CONDUCT.md`. Report
security-sensitive issues through `SECURITY.md` or GitHub private vulnerability
reporting rather than public issue details.

# HTF Test Script Validation - 2026-04-29

## Scope

Validated current test scripts against the local HTF workflow documentation, the
Astra workflow extension validation model, and executable smoke checks in the
current shell.

Tracking:

- Linear: RIS-208
- Notion worklog: Codex Worklog - RiskYieldMM

## Current HTF Workflow Baseline

The current documented production path is:

- launcher: `notebooks/htf_pythonscript.py`
- materialization source of truth: `scripts/feature_engineering/htf_multiregime_pipeline.py`
- Stage-1 runner: `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- timeframe/target: `1m` / `target_4class`
- model family: CatBoost
- roots: `8h/B`, `8h/C`, `24h/B`, `24h/C`, `7d/B`, `7d/C`

The current validation principles require chronological separation, leakage
checks, purged evaluation, artifact-first analysis, and selector discipline.

## Commands Run

Passed:

```bash
python -m py_compile tests/*.py scripts/tests/test_lstm_gap_fix.py scripts/target_models/validation/backtest/tests/test_catboost_optimization_unit.py scripts/target_models/validation/test_hmm_rust.py test_ruff.py
python -m compileall tests scripts/tests scripts/target_models/validation/backtest/tests scripts/target_models/validation/test_hmm_rust.py test_ruff.py -q
python -m compileall scripts riskyield_rust -q
npm run compile  # in extensions/astra-workflow
```

Failed due missing environment dependencies:

```bash
python -m pytest --collect-only -q tests scripts/tests scripts/target_models/validation/backtest/tests scripts/target_models/validation/test_hmm_rust.py test_ruff.py
# No module named pytest

python scripts/analysis/htf_stage1_regime_family_walkforward.py --plan-only
# No module named polars

python scripts/analysis/htf_walkforward_diagnostics.py --help
# No module named polars

python scripts/analysis/htf_stage1_v2_subset_reduction_audit.py --help
# No module named polars

python scripts/tests/test_lstm_gap_fix.py
# No module named torch

python scripts/target_models/validation/backtest/tests/test_catboost_optimization_unit.py
# No module named optuna

python scripts/target_models/validation/test_hmm_rust.py
# No module named hmmlearn

npm test -- --help  # in extensions/astra-workflow
# Cannot find module out/test/runTest.js
```

## Test Inventory

Static count:

- `tests/test_registry.py`: 26 test functions
- `tests/test_features.py`: 8 test functions
- `tests/test_icir_selection.py`: 19 test functions
- `tests/test_models.py`: 11 test functions
- `tests/test_optimizers.py`: 31 test functions
- `scripts/tests/test_lstm_gap_fix.py`: 4 pytest-discoverable functions, but they are helper routines with required data arguments and no fixtures
- `scripts/target_models/validation/backtest/tests/test_catboost_optimization_unit.py`: 7 test functions
- `scripts/target_models/validation/test_hmm_rust.py`: 1 pytest-discoverable function
- `test_ruff.py`: 0 test functions

## Findings

1. The current shell is not prepared to run the Python test suite.

   Missing packages include `pytest`, `polars`, `catboost`, `torch`, `hmmlearn`,
   and `optuna`. `pyproject.toml` only has project metadata and Ruff settings;
   there is no detected Python dependency lockfile, `requirements.txt`, or
   `environment.yml`.

2. Existing tests do not directly cover the current active HTF core.

   They cover older analysis utilities, PurgedKFold, optimizers, registry/model
   helper behavior, ICIR selection, older L2 validation scripts, and Rust HMM
   validation. They do not unit-test the current multi-regime HTF materializer,
   `target_4class` entry-window labeling, helper-cache materialization, six-root
   Stage-1 artifact contracts, Stage-1-v2 fold membership, or resume/grid
   migration behavior.

3. Several scripts named like tests are not pytest-ready unit tests.

   `scripts/tests/test_lstm_gap_fix.py` is a standalone experiment script. Its
   `test_lstm_*` functions require arrays/config objects as positional
   arguments without fixtures, so pytest would treat them as missing fixtures if
   the import got past `torch`.

   `scripts/target_models/validation/test_hmm_rust.py` has one pytest-discovered
   function, but it prints validation state and does not assert the critical
   checks. It also imports `hmmlearn` unconditionally.

4. Some test assumptions are stale relative to the documented current workflow.

   `tests/test_registry.py` locks the older 20-target L2 registry. The current
   HTF workflow is `1m/target_4class` over six HTF roots, not the old
   volatility/returns/direction/vol_regime/trend_regime registry.

   `scripts/target_models/validation/backtest/tests/test_catboost_optimization_unit.py`
   describes "28 configs" but lists 6 target types times 4 horizons, i.e. 24
   configs. It tests older L2 target names rather than `target_4class` or the
   Stage-1 CatBoost artifact contract.

   `tests/test_models.py` checks generic PurgedKFold defaults with an `8h`
   synthetic frequency. It remains useful as a narrow unit test, but it does not
   validate current Stage-1 fold-window artifact constraints.

5. Test/import ergonomics are fragile.

   Importing `scripts.analysis.features`, `scripts.analysis.models`, or
   `scripts.analysis.optimizers` triggers `scripts.analysis.__init__`, which
   imports `data`, and `data` requires `polars`. This means pure synthetic unit
   tests for non-Polars helpers cannot import unless Polars is installed.

6. Extension validation status is partial.

   The Astra workflow extension compiles and declares 15 language-model tools.
   Its own package test script points to `out/test/runTest.js`, which is absent.
   The extension's execution tool requires validation evidence before marking a
   workflow step complete, but the extension does not currently provide a runnable
   test harness in this checkout.

7. Checkout currentness caveat.

   `git status --short --branch` reports `main...origin/main [behind 1]`. The
   remote tracking delta is one README-only commit, but the local branch is not
   exactly current with `origin/main`.

## Assessment

The current test scripts are not sufficient to prove the latest HTF workflow is
correct. They are syntactically valid, but the executable Python test environment
is incomplete and the test coverage is mostly aimed at older support layers.

The most useful current checks are:

- syntax/compile checks for source and tests
- generic synthetic tests for PurgedKFold, optimizer behavior, ICIR selection,
  and permutation importance once dependencies are installed
- standalone older L2 validation scripts only when their heavy dependencies and
  data assumptions are available

They are not prepared as a reliable HTF workflow gate.

## Recommended Next Tests

Priority test additions:

1. Synthetic multi-regime HTF fixture covering `8h/B`, `8h/C`, `24h/B`, `24h/C`,
   `7d/B`, and `7d/C`.
2. `target_4class` entry-window tests for 4h, 12h, and 84h windows, including
   invalid `-1` rows outside the entry window.
3. Artifact contract tests for Stage-1 required files and columns:
   `stage1_combo_index.parquet`, `stage1_fold_windows.parquet`,
   `stage1_val_predictions.parquet`, `stage1_pred_batch_predictions.parquet`,
   and predecision context JSON/parquet.
4. Stage-1 fold causality tests proving train/validation/prediction batch
   ordering and no prediction-batch leakage into fold validation.
5. Helper-cache materialization tests checking row alignment, timestamp/batch
   uniqueness, helper prefix readiness, and helper contract fingerprints.
6. Stage-1-v2 artifact tests for persisted selector outputs and explicit fold
   membership once that missing artifact is added.
7. Environment reproducibility: add a Python dependency spec and a documented
   smoke command that can run in a clean environment.

## Follow-up Update - RIS-209

After this validation, focused lightweight contract tests were added under
`tests/test_htf_workflow_contract.py`. These tests cover:

- current HTF regime durations, family shifts, and entry-window hours
- current `1m` / `target_4class` Stage-1 runner contract
- all six model-facing roots: `8h/B`, `8h/C`, `24h/B`, `24h/C`, `7d/B`, `7d/C`
- required Stage-1 v1 artifact filenames
- Stage-1-v2 root, step, and fixed-policy artifact contract constants

`pytest.ini` was also added so default pytest collection is scoped to `tests/`
instead of recursively collecting standalone experiment scripts under `scripts/`.
Older dependency-heavy test modules now skip cleanly when `polars` is absent.

## Environment Correction - RIS-209 Follow-up

The first verification pass used the shell-default interpreter:
`/media/przem/linux_data/conda/bin/python` (`base`, Python 3.12). That was not
the workflow-capable HTF environment; it lacked `pytest`, `polars`, `catboost`,
`torch`, `hmmlearn`, and `optuna`.

The available workflow-capable environment is:
`/media/przem/linux_data/conda/envs/ml_env/bin/python` (Python 3.11). It has the
required HTF/test dependencies checked in this audit:

- `pytest` 9.0.2
- `polars` 1.36.1
- `catboost` 1.2.8
- `torch` 2.5.1+cu121
- `hmmlearn` 0.3.3
- `optuna` 4.6.0

Re-run results under `ml_env`:

- `python -m pytest tests/test_htf_workflow_contract.py -q`: 5 passed
- `python -m pytest --collect-only -q`: 108 tests collected
- `python -m pytest -q`: 85 passed, 23 failed

The 23 full-suite failures are in `tests/test_registry.py` and are caused by
missing generated datasets under `data/datasets/*.parquet`, for example
`data/datasets/volatility_6bar.parquet`, `data/datasets/direction_3bar.parquet`,
and `data/datasets/returns_6bar.parquet`. They are not caused by the new HTF
contract tests.

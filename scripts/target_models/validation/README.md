# Fast Validation / Backtest (L1 precompute + L2-only)

This folder contains the **validation-speed** workflow:
- **Precompute L1 helper features once** (production-parity `drop_na=True`).
- Run **fast walk-forward backtests** that only train/run L2 (and optional conformal/ACI), reusing those L1 artifacts.

The main entrypoint is:
- `scripts/target_models/validation/run_fast_validation.py`

## Prereqs

Run commands from the repo root (`RiskYieldMM/`).

Activate your environment and make sure `PYTHONPATH=.` is set so `scripts.*` imports resolve.

## Quick sanity run (2 configs, tiny backtest)

```bash
cd /media/przem/linux_data/RiskYieldMM
conda activate /media/przem/linux_data/conda/envs/ml_env
PYTHONPATH=. python scripts/target_models/validation/run_fast_validation.py \
  --configs returns_1bar returns_12bar \
  --backtest-rows 3 \
  --precompute force \
  --precomputed-dir data/precomputed_tmp \
  --results-dir data/backtest_results_tmp \
  --write-csv \
  --fail-fast
```

## Full run (all 20 configs, production-parity, resumable)

Recommended defaults:
- `--precompute ensure` (rebuild only if missing/mismatched)
- global-end alignment enabled (default) so **all configs end on the same final decision bar**
- `--write-csv` for a shallow summary table

```bash
cd /media/przem/linux_data/RiskYieldMM
conda activate /media/przem/linux_data/conda/envs/ml_env
PYTHONPATH=. python scripts/target_models/validation/run_fast_validation.py \
  --backtest-rows 300 \
  --precompute ensure \
  --write-csv
```

### Resume a previous run

`--resume` only skips configs already present in that run’s `summary.json`.
To resume, re-run with the **same** `--run-id`:

```bash
PYTHONPATH=. python scripts/target_models/validation/run_fast_validation.py \
  --run-id fast_validation_YYYYMMDD_HHMMSS \
  --resume \
  --backtest-rows 300 \
  --precompute ensure \
  --write-csv
```

## Common options

- Config selection:
  - `--configs <name...>` (explicit list)
  - `--targets returns direction volatility vol_regime trend_regime`
  - `--horizons 1 3 6 12`

- Precompute policy (`--precompute`):
  - `skip`: require existing L1 artifacts
  - `ensure`: rebuild if missing or metadata mismatches
  - `force`: rebuild every selected config

- End alignment:
  - Default: `--align-global-end` is enabled (truncate all configs to earliest dataset end after drop-na).
  - Disable: `--no-align-global-end` (each config ends at its own end; not merge-safe).
  - Override: `--global-end-timestamp <ISO8601>`

- Verification:
  - Default verifies the last iteration ends at the (possibly truncated) dataset end.
  - Disable with `--no-verify-ends`.

- Conformal:
  - Disable with `--no-conformal`.

- Error handling:
  - `--fail-fast` stops on first failure (unless `--continue-on-error` is set).

## Outputs

For each run, a folder is created under `--results-dir`:
- `data/backtest_results/fast_validation_<timestamp>/summary.json`
- `data/backtest_results/fast_validation_<timestamp>/summary.csv` (if `--write-csv`)

The summary JSON is written **incrementally after each config**, so it’s safe to interrupt and resume.

## Precompute artifacts

L1 precomputes are stored per config in `--precomputed-dir`:

```
data/precomputed/<config_name>/
├── YYYY-MM-DD_HHh.parquet   # helper_features for the iteration’s prediction timestamp
├── index.json               # per-iteration mapping (pred idx, aligned idx, timestamps)
└── metadata.json            # config-level metadata (drop_na, horizon, window sizes, truncation)
```

## Optional: precompute-only / production parity spot-check

- Precompute-only across configs (with shared end alignment) is provided by:
  - `scripts/target_models/validation/regenerate_all_precomputes.py`

- Exact production-parity validation for a few iterations (slow; debugging tool):
  - `scripts/target_models/validation/precompute_and_validate_all.py`

## Notes

- The runner enforces production-style NA filtering (`drop_na=True`) via metadata checks.
- You may still see model/library warnings (e.g. convergence warnings). These are usually noise unless they correlate with failures or large metric shifts.

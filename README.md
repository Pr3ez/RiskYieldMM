# RiskYieldMM

**Machine learning research system for cryptocurrency perpetual futures**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange.svg)](https://rust-lang.org)

RiskYieldMM is a research and portfolio project for building leakage-aware financial time-series ML workflows. The active workflow is a multi-regime HTF pipeline for cryptocurrency perpetual futures: it builds higher-timeframe batches, generates current prediction labels, attaches helper/regime features, runs CatBoost walk-forward Stage-1 experiments, and audits model-selection behavior from saved artifacts.

This is not trading advice and is not a live trading bot. The focus is ML engineering discipline: temporal validation, reproducible artifacts, auditability, and careful treatment of non-stationary market data.

## Recruiter Overview

This repository demonstrates the ability to build and reason about a non-trivial ML system rather than only train a single notebook model.

| Area | Evidence |
|------|----------|
| **Data engineering** | Bybit market-data ingestion, multi-source aggregation, Parquet/JSON artifact workflows |
| **Feature engineering** | Multi-regime HTF feature materialization, helper/regime features, technical/time-series feature families |
| **ML modelling** | CatBoost Stage-1 selection, LightGBM/PyTorch experiments, Ridge/linear baselines, ensemble tooling |
| **Time-series validation** | Walk-forward splits, purged windows, chronological train/test separation, leakage checks |
| **Uncertainty estimation** | Conformal prediction, Adaptive Conformal Inference, coverage monitoring |
| **Performance engineering** | Rust/PyO3 helper implementations for Kalman, GARCH, EGARCH, CUSUM, OU, EVT, BOCPD |
| **Experiment analysis** | HTF Stage-1 CatBoost selector audits, pairwise disagreement analysis, discounted-loss policy replay |
| **Documentation** | Architecture notes, validation findings, run summaries, artifact specifications, implementation plans |

Generated data, model outputs, private CV files, and local run artifacts are not required to review the code. Some historical output snapshots may exist in the repository as audit/reference material, but new generated data is ignored by default.

## Main Workflow

### 1. Multi-Regime HTF Pipeline

The HTF workflow is the current main path. It builds leakage-aware higher-timeframe batches for the 8h, 24h, and 7d regimes, generates the active labels, attaches helper features, and produces saved artifacts for walk-forward CatBoost evaluation.

Current regimes:

| Regime | Batch duration | Shift | Entry window | Current usage |
|--------|----------------|-------|--------------|---------------|
| `8h` | 8 hours | 4 hours | 4 hours | intraday HTF root |
| `24h` | 24 hours | 12 hours | 12 hours | daily HTF root |
| `7d` | 168 hours | 84 hours | 84 hours | weekly HTF root |

The active analysis roots are the six regime/family variants `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, and `7d_c`, evaluated primarily through `1m/target_4class`.

Key locations:

- `scripts/feature_engineering/compute_htf_features.py`
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/htf_kernels.py`
- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/htf_backtest/`
- `notebooks/htf_pythonscript.py`
- `notebooks/notes/`

### 2. Stage-1 CatBoost Selection Audits

Stage-1 is the main model-selection audit layer for the HTF workflow. It is an offline dataset-generation framework for CatBoost window/action-key selection. It stores raw validation and prediction-batch payloads so model-selection behavior can be studied after the run without leaking future information into selector decisions.

Stage-1 specs cover `1m`, `5m`, and `15m` units for `target_4class` and `target_breakfree`. Current production-style audits focus on `1m/target_4class` across the six HTF regime/family roots.

Recent Stage-1 v2 analysis includes:

- 8 action-key combinations
- 500 walk-forward steps
- 120,000 selected prediction rows
- 30 discounted-loss selector policies
- nested chronological train/validation/test selector evaluation
- pairwise prediction disagreement and subset-reduction audits

Key locations:

- `scripts/htf_backtest/catboost/stage1_runner.py`
- `scripts/htf_backtest/catboost/stage1_selector_step.py`
- `scripts/htf_backtest/catboost/stage1_step2.py`
- `scripts/analysis/htf_stage1_v2_loss_discounted_selector_audit.py`
- `scripts/analysis/htf_stage1_v2_pairwise_prediction_audit.py`
- `scripts/analysis/htf_stage1_v2_subset_reduction_audit.py`
- `docs/htf_stage1_logic.md`
- `docs/htf_stage1_artifacts.md`

### 3. Secondary Target-Model and Conformal Layer

The target-model layer is the older L2 modelling system and conformal uncertainty module. It is useful as supporting engineering evidence, but it is no longer the main HTF workflow. It includes multi-target configuration, helper features, model wrappers, validation tooling, conformal classification/regression wrappers, and Adaptive Conformal Inference.

Validated conformal outputs documented in `docs/conformal/` include regression coverage around **90.7-96.3%** against a 90% target.

Key locations:

- `scripts/target_models/pipeline.py`
- `scripts/target_models/models/`
- `scripts/target_models/helpers/`
- `scripts/target_models/calibration/`
- `scripts/target_models/validation/`
- `docs/conformal/README.md`

### 4. Rust-Accelerated Helper Computation

Performance-critical helper models are implemented in Rust and exposed to Python with PyO3/maturin.

Implemented Rust modules:

- Kalman filter
- GARCH / EGARCH
- CUSUM
- Ornstein-Uhlenbeck
- EVT / POT
- BOCPD
- HMM support

Key locations:

- `riskyield_rust/src/`
- `scripts/target_models/helpers/`

## Repository Map

```text
RiskYieldMM/
├── scripts/
│   ├── workflow/                # Original workflow orchestration and target config
│   ├── feature_engineering/     # Feature generation, HTF pipelines, helper cache
│   ├── htf_backtest/            # HTF CatBoost/LightGBM backtest and Stage-1 tooling
│   ├── analysis/                # Offline audits, diagnostics, selector analysis
│   ├── target_models/           # L2 model layer, helpers, conformal prediction
│   ├── strategy/                # Strategy research utilities
│   └── tests/                   # Focused experiment/test scripts
├── riskyield_rust/              # Rust/PyO3 helper acceleration module
├── fetchingByBit/               # Bybit data acquisition and local market data folders
├── prediction_analysis/         # Historical research outputs and reports
├── test_output/                 # Local/generated audit outputs and snapshots
├── data/                        # Local/generated datasets and backtest artifacts
├── docs/                        # Architecture, validation, conformal, and research notes
├── notebooks/notes/             # Session-level research and audit notes
├── Archive/                     # Legacy implementations kept for reference
└── cv_tmp/                      # Private CV/certificate files, ignored by git
```

## Data Sources and Prediction Targets

The project uses Bybit perpetual-futures data and related market sources such as:

- OHLCV klines
- funding rates
- open interest
- long/short ratios
- mark price
- index price
- premium price data

### Current HTF Targets

The current HTF workflow centers on `target_4class`, generated from forward distance and breakout/risk metrics inside the HTF batch structure.

| Value | Class | Meaning |
|-------|-------|---------|
| `0` | `DOWN_BALANCED` | downside outcome without expansion/risk trigger |
| `1` | `DOWN_EXPANSION` | downside outcome with expansion/risk behavior |
| `2` | `UP_BALANCED` | upside outcome without expansion/risk trigger |
| `3` | `UP_EXPANSION` | upside outcome with expansion/risk behavior |

Invalid or unresolved rows are marked as `-1` and excluded from training/evaluation where required.

`target_breakfree` is a secondary Stage-1 target derived from the current HTF labeling surface. It uses three classes:

- `UP_ABOVE_BREAKFREE`
- `DOWN_ABOVE_BREAKFREE`
- `IN_BETWEEN_BELOW_BREAKFREE`

Older targets such as next-period direction, volatility regime, trend regime, triple-barrier outcomes, and return/volatility regression belong to the legacy L2 target-model layer. They remain in the repository for research history and conformal-prediction work, but they should not be read as the current main HTF objective.

## Quick Start for Reviewers

Full reproduction requires local market data under `data/` and `fetchingByBit/`. For a code review or recruiter review, start with a lightweight environment and run import/syntax checks.

```bash
git clone https://github.com/Pr3ez/RiskYieldMM.git
cd RiskYieldMM

conda create -n riskyieldmm python=3.10 -y
conda activate riskyieldmm

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install \
  polars pandas numpy scipy scikit-learn catboost lightgbm xgboost torch \
  matplotlib seaborn optuna mapie mlflow pyarrow tqdm pydantic

# Basic source smoke check.
python -m compileall scripts riskyield_rust -q
```

Optional Rust helper build:

```bash
cd riskyield_rust
python -m pip install maturin
maturin develop --release
cd ..
```

Useful entry points for review:

- `docs/htf_stage1_logic.md`
- `docs/htf_stage1_artifacts.md`
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/htf_kernels.py`
- `notebooks/htf_stage1.py`
- `docs/conformal/README.md`
- `docs/validation/`
- `scripts/analysis/`
- `scripts/htf_backtest/catboost/`
- `scripts/target_models/calibration/`
- `riskyield_rust/src/`

## Common Commands

Show available Stage-1 selector audit options:

```bash
python scripts/analysis/htf_stage1_v2_loss_discounted_selector_audit.py --help
python scripts/analysis/htf_stage1_v2_pairwise_prediction_audit.py --help
python scripts/analysis/htf_stage1_v2_subset_reduction_audit.py --help
```

Run a syntax check:

```bash
python -m compileall scripts riskyield_rust -q
```

Run Ruff if installed:

```bash
ruff check scripts
```

Check Rust helper build status after installing `riskyield_rust`:

```python
from scripts.workflow.l1_helpers import print_rust_status
print_rust_status()
```

## Validation Principles

RiskYieldMM is built around financial time-series validation constraints:

1. **Chronological separation** - training, validation, and prediction windows are ordered in time.
2. **Leakage checks** - feature generation and helper outputs are audited for future-information leakage.
3. **Purged evaluation** - validation logic uses gaps/purges where needed to reduce overlap leakage.
4. **Artifact-first analysis** - raw prediction payloads, metrics, masks, summaries, and run metadata are persisted for offline audit.
5. **Selector discipline** - Stage-1 selector policies are evaluated with nested chronological splits instead of selecting directly on final test behavior.
6. **Uncertainty monitoring** - conformal prediction and coverage diagnostics are used where prediction certainty matters.

## Documentation Index

High-signal documents:

- `docs/htf_stage1_logic.md` - isolated Stage-1 design and leakage constraints
- `docs/htf_stage1_artifacts.md` - Stage-1 artifact contract
- `docs/htf_stage1_step2_plan.md` - feature-pruning and baseline-vs-filtered analysis
- `docs/conformal/README.md` - conformal prediction module summary
- `docs/conformal/ARCHITECTURE.md` - conformal integration details
- `docs/VALIDATION_TESTING_RESEARCH.md` - validation research notes
- `docs/preprocessing/` - preprocessing and leakage-audit planning
- `notebooks/notes/` - chronological research and implementation notes

## Technology Stack

Core stack:

- Python 3.10+
- Polars, pandas, NumPy, SciPy
- scikit-learn
- CatBoost, LightGBM, XGBoost
- PyTorch
- MAPIE/conformal prediction
- Optuna, MLflow
- Parquet/JSON artifacts
- Rust, PyO3, maturin

Development tools:

- Linux/Ubuntu
- Git
- Jupyter / notebooks
- VS Code
- Ruff

## Notes on Repository Hygiene

- `cv_tmp/` is ignored because it contains private CV/certificate files.
- Most generated data and model-output directories are ignored for future commits.
- Some historical `test_output/`, `prediction_analysis/`, and data snapshots may remain as committed audit/reference artifacts.
- GitHub may warn about historical large files. Future cleanup can move large market-data snapshots to external storage or Git LFS if the repository needs to be made lightweight.

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Author

Przemysław Augustyniak  
GitHub: https://github.com/Pr3ez/RiskYieldMM

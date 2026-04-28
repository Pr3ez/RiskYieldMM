# RiskYieldMM

**Production-Grade Machine Learning Pipeline for Perpetual Futures Prediction**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Rust](https://img.shields.io/badge/Rust-1.70%2B-orange.svg)](https://rust-lang.org)

---

## Overview

RiskYieldMM is a comprehensive machine learning system for predicting Bitcoin perpetual futures price movements on 8-hour timeframes. The project implements institutional-grade walk-forward validation with a multi-model ensemble architecture, ensuring statistically rigorous backtesting without look-ahead bias.

## Recruiter Overview

This repository is a portfolio-grade ML engineering project. It demonstrates the ability to build, validate, document, and optimize a non-trivial time-series machine learning system rather than only train a single notebook model.

| Area | Evidence in this repository |
|------|-----------------------------|
| **Data engineering** | Bybit API ingestion, multi-source 8h bar aggregation, Parquet/JSON artifact workflows |
| **Feature engineering** | 166 technical features plus 91 L1 helper/regime features |
| **ML modelling** | CatBoost, LightGBM, PyTorch LSTM, Ridge baselines, ensemble weighting |
| **Validation discipline** | Walk-forward testing, purged time-series splits, leakage checks, chronological audits |
| **Uncertainty estimation** | Conformal prediction, Adaptive Conformal Inference, coverage monitoring |
| **Performance engineering** | Rust/PyO3 helper implementations with documented 20-487x speedups |
| **Experiment analysis** | Stage-1 CatBoost selector audits, pairwise disagreement analysis, discounted-loss policy replay |

Generated datasets, trained models, backtest outputs, API data, and private CV/certificate files are intentionally excluded from Git. The source code and documentation are structured so reviewers can inspect the system design, run import/syntax checks, and reproduce full experiments after providing local market data.

### Core Capabilities

| Capability | Implementation |
|------------|----------------|
| **Walk-Forward Validation** | Expanding-window training with purged k-fold cross-validation |
| **Multi-Target Prediction** | 8 complementary targets (direction, volatility, regime, strategy) |
| **Ensemble Architecture** | 4-model system: CatBoost, LightGBM, LSTM, Ridge |
| **Native Performance** | Rust-accelerated helper computations (20-487× speedup) |
| **Causality Guarantee** | All features use expanding windows with `.shift(1)` verification |
| **Automated Pipeline** | 11-step workflow with quality gates and state management |

---

## Pipeline Architecture

The system processes data through 11 sequential steps, from raw API fetch to final backtest results:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PIPELINE ARCHITECTURE                             │
├──────────┬──────────────────────────────────────────────────────────────────┤
│ Step 0   │ Data Ingestion      Bybit API → 8-hour aggregated bars          │
│ Step 1a  │ Data Merge          6 sources → merged_8h_raw.parquet           │
│ Step 1b  │ Feature Engineering 166 technical features → features_8h.parquet │
│ Step 2   │ Target Generation   8 prediction targets → analysis_8h.parquet  │
│ Step 3   │ Feature Optimization Per-target optimization (Winsorize/Rank)   │
│ Step 4   │ Dataset Assembly    Final datasets → data/datasets/*.parquet    │
│ Step 5   │ IC/ICIR Analysis    Feature predictive power assessment         │
│ Step 6   │ Feature Importance  MDI + MDA importance ranking                │
│ Step 7   │ Cross-Validation    PurgedKFold temporal CV (AFML Ch.7)         │
│ Step 8   │ L1 Precomputation   Helper features → data/precomputed/         │
│ Step 9   │ L2 Assembly         Prediction datasets → assembled.parquet     │
│ Step 10  │ Walk-Forward Test   4-model ensemble → backtest results         │
└──────────┴──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Bybit API (6 sources)
       │
       ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Raw 8h Bars     │───▶│  166 Features    │───▶│  8 Targets       │
│  (OHLCV, OI,     │    │  (Technical,     │    │  (Direction,     │
│   Funding, LSR)  │    │   Derivatives)   │    │   Volatility...) │
└──────────────────┘    └──────────────────┘    └──────────────────┘
                                │
                                ▼
                    ┌──────────────────────┐
                    │  Per-Target          │
                    │  Optimization        │
                    │  (Winsorize → Rank)  │
                    └──────────────────────┘
                                │
                                ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  L1 Helpers      │───▶│  Combined        │───▶│  Walk-Forward    │
│  (Rust-accel.)   │    │  Datasets        │    │  Backtest        │
│  91 features     │    │                  │    │  4-model ensemble│
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## Data Sources

The pipeline ingests 6 complementary data streams from Bybit's perpetual futures API:

| Source | Update Frequency | Features Derived |
|--------|------------------|------------------|
| **OHLCV Klines** | 8h | Price patterns, volume, turnover, VWAP |
| **Funding Rate** | 8h | Sentiment, funding squeeze, mean reversion |
| **Open Interest** | 8h | Trend confirmation, liquidation cascades |
| **Long/Short Ratio** | 8h | Retail positioning, contrarian signals |
| **Mark Price** | 8h | Fair value, basis calculation |
| **Index Price** | 8h | Spot reference, premium/discount |

All data is aggregated to 8-hour bars (00:00, 08:00, 16:00 UTC) for consistent temporal alignment.

---

## Prediction Targets

The system predicts 8 complementary targets, each addressing a different aspect of market behavior:

### Classification Targets

| Target | Classes | Description | Use Case |
|--------|---------|-------------|----------|
| `direction` | 2 (UP/DOWN) | Next-bar price direction | Entry signal |
| `volatility_regime` | 2 (INCREASE/DECREASE) | Volatility expansion/contraction | Position sizing |
| `trend_regime` | 2 (TREND/RANGE) | Market regime classification | Strategy selection |
| `trade_setup` | 4 | Pullback entry opportunities (BBand analysis) | Entry timing |
| `path_label_5` | 5 | Price path characterization (trend/mean-revert) | Strategy allocation |
| `strategy_label` | 5 | Prescriptive action (FLAT/TF/MR) | Direct trading signal |
| `triple_barrier` | 3 | Risk/reward outcome (TP/SL/TIME) | Position management |

### Regression Target

| Target | Range | Description | Use Case |
|--------|-------|-------------|----------|
| `volatility` | [0, ∞) | Expected absolute return magnitude | Risk adjustment |

---

## Model Ensemble

The L2 backtest employs a 4-model ensemble with GPU acceleration:

| Model | Framework | Hardware | Strengths |
|-------|-----------|----------|-----------|
| **CatBoost** | CatBoost | CUDA GPU | Categorical handling, ordered boosting, overfitting resistance |
| **LightGBM** | LightGBM | CUDA GPU | Histogram-based splitting, feature interactions, speed |
| **LSTM** | PyTorch | CUDA GPU | Temporal dependencies, sequence memory, regime adaptation |
| **Ridge** | scikit-learn | CPU | Linear baseline, regularization, interpretability |

Ensemble predictions are combined via weighted averaging with weights optimized on validation data.

---

## Rust-Accelerated Computation

Performance-critical L1 helper computations are implemented in Rust with PyO3 bindings, providing substantial speedups over pure Python:

### Helper Performance

| Helper | Algorithm | Speedup | Python Time | Rust Time |
|--------|-----------|---------|-------------|-----------|
| **Kalman** | Kalman Filter state estimation | **487×** | 4.87s | 10ms |
| **GARCH** | Volatility modeling | **224×** | 2.24s | 10ms |
| **CUSUM** | Change detection | **156×** | 1.56s | 10ms |
| **OU** | Ornstein-Uhlenbeck mean reversion | **30×** | 300ms | 10ms |
| **EVT** | Extreme Value Theory (GPD fitting) | **25×** | 250ms | 10ms |
| **EGARCH** | Asymmetric volatility | **22×** | 220ms | 10ms |
| **BOCPD** | Bayesian changepoint detection | **20×** | 200ms | 10ms |

### Rust Module Structure

```
riskyield_rust/
├── Cargo.toml              # Rust dependencies (pyo3, numpy, rayon)
├── pyproject.toml          # Python build config (maturin)
└── src/
    ├── lib.rs              # PyO3 module exports
    ├── kalman.rs           # Kalman filter implementation
    ├── garch.rs            # GARCH(1,1) estimation
    ├── egarch.rs           # EGARCH with leverage effects
    ├── cusum.rs            # CUSUM control chart
    ├── ou.rs               # Ornstein-Uhlenbeck AR(1)
    ├── evt.rs              # EVT GPD MLE fitting
    ├── bocpd.rs            # Bayesian online changepoint
    └── hmm.rs              # Hidden Markov Model (optional)
```

### L1 Helper Features (91 total)

| Helper | Features | Description |
|--------|----------|-------------|
| **IsolationForest** | 8 | Anomaly detection scores |
| **CUSUM** | 8 | Cumulative sum change detection |
| **GARCH** | 10 | Volatility forecasts, persistence |
| **HMM (4-state)** | 12 | Regime probabilities, transitions |
| **HMM (5-state)** | 15 | Extended regime classification |
| **Kalman** | 8 | Filtered states, prediction errors |
| **EVT** | 10 | Tail risk metrics (VaR, ES) |
| **OU** | 8 | Mean reversion speed, z-scores |
| **BOCPD** | 6 | Changepoint probabilities |
| **EGARCH** | 6 | Asymmetric volatility, news impact |

---

## Project Structure

```
RiskYieldMM/
├── notebooks/
│   └── main_wf.py                  # Main orchestration (11-step workflow)
│
├── scripts/
│   ├── workflow/                   # Pipeline orchestration
│   │   ├── config.py               # Central configuration
│   │   ├── data_fetching.py        # Step 0: Bybit API integration
│   │   ├── state_detection.py      # Incremental update detection
│   │   ├── validation.py           # Causality & integrity checks
│   │   ├── targets.py              # Target computation registry
│   │   ├── l1_helpers.py           # L1 precompute utilities
│   │   └── metrics_tracking.py     # Quality monitoring
│   │
│   ├── feature_engineering/        # Feature computation
│   │   ├── compute_features.py     # 166 technical features
│   │   ├── prepare_dataset.py      # Data source merging
│   │   └── fracdiff.py             # Fractional differentiation
│   │
│   ├── analysis/                   # Feature analysis
│   │   ├── run.py                  # Analysis commands
│   │   ├── parallel_optimize.py    # Multi-threaded optimization
│   │   └── optimizers/             # Winsorize, ExpandingRank
│   │
│   └── target_models/              # Model infrastructure
│       ├── core/                   # Dual-window engine
│       ├── helpers/                # L1 helper implementations
│       └── validation/             # L2 backtest system
│
├── riskyield_rust/                 # Rust acceleration module
│   ├── Cargo.toml
│   └── src/                        # Rust implementations
│
├── backtest/                       # Backtest service
│   ├── core/                       # Metrics, display
│   └── services/                   # Backtest orchestration
│
├── fetchingByBit/                  # Data acquisition
│   ├── fetch_bybit_market_data.py  # API client
│   ├── aggregate_to_8h.py          # Timeframe aggregation
│   └── update_data.py              # Incremental updates
│
├── data/                           # Generated data (gitignored)
│   ├── datasets/                   # Final training datasets
│   ├── precomputed/                # L1 helper features
│   ├── combined_datasets/          # L2 backtest inputs
│   └── l2_backtest_results/        # Backtest outputs
│
└── docs/                           # Research documentation
    ├── VALIDATION_TESTING_RESEARCH.md
    ├── ACCURACY_IMPROVEMENT_RESEARCH.md
    └── astra-research/
```

---

## Quick Start for Reviewers

The fastest way to inspect the project is to set up the Python environment, run source checks, and then review the documented experiment artifacts. Full model runs require local/generated data under `data/`, which is not committed.

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

# Syntax/package smoke check.
python -m compileall scripts riskyield_rust -q
```

Optional Rust helper build:

```bash
cd riskyield_rust
python -m pip install maturin
maturin develop --release
cd ..
```

Useful review entry points:

- `docs/conformal/README.md` - conformal prediction and ACI validation summary
- `docs/htf_stage1_logic.md` - Stage-1 CatBoost audit design
- `docs/htf_stage1_artifacts.md` - reproducible artifact layout
- `scripts/analysis/` - offline audit and selector-analysis scripts
- `scripts/target_models/pipeline.py` - walk-forward target runner and conformal integration
- `riskyield_rust/src/` - Rust helper implementations

---

## Installation

### Prerequisites

- **Python 3.10+** — Core runtime
- **CUDA 11.8+** — GPU acceleration (recommended)
- **Rust 1.70+** — For Rust helper compilation (optional but recommended)
- **Conda** — Environment management (recommended)

### Environment Setup

```bash
# Clone repository
git clone https://github.com/Pr3ez/RiskYieldMM.git
cd RiskYieldMM

# Create conda environment
conda create -n riskyieldmm python=3.10 -y
conda activate riskyieldmm

# Install package and core dependencies
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install \
  polars pandas numpy scipy scikit-learn catboost lightgbm xgboost torch \
  matplotlib seaborn optuna mapie mlflow pyarrow tqdm pydantic

# Install Rust helpers (recommended for 20-487× speedup)
cd riskyield_rust
python -m pip install maturin
maturin develop --release
cd ..
```

### Verify Installation

```python
# Check Rust backend status
from scripts.workflow.l1_helpers import print_rust_status
print_rust_status()

# Expected output:
# ============================================================
# RUST BACKEND STATUS
# ============================================================
#   CUSUM   : ✓ Rust (156x speedup)
#   Kalman  : ✓ Rust (487x speedup)
#   GARCH   : ✓ Rust (224x speedup)
#   EVT     : ✓ Rust (25x speedup)
#   OU      : ✓ Rust (30x speedup)
#   BOCPD   : ✓ Rust (20x speedup)
#   EGARCH  : ✓ Rust (22x speedup)
#
#   7/7 helpers using Rust backends
```

### Dependencies

**Core:**
- `polars>=0.20` — High-performance DataFrame operations
- `pandas>=2.0` — Data manipulation
- `numpy>=1.24` — Numerical computing
- `scikit-learn>=1.3` — ML utilities

**Models:**
- `catboost>=1.2` — Gradient boosting (GPU)
- `lightgbm>=4.0` — Gradient boosting (GPU)
- `torch>=2.0` — PyTorch for LSTM
- `hmmlearn>=0.3` — Hidden Markov Models

**Analysis:**
- `optuna>=3.0` — Hyperparameter tuning
- `mlflow>=2.0` — Experiment tracking

**Rust Bindings:**
- `pyo3>=0.20` — Python-Rust interop
- `maturin>=1.0` — Build system

---

## Usage

### Full Pipeline Execution

```python
# Run complete 11-step workflow
%run notebooks/main_wf.py
```

### Individual Steps

```python
# Step 0: Fetch latest data
from scripts.workflow.data_fetching import run_step0_fetch_and_aggregate
run_step0_fetch_and_aggregate(project_root=PROJECT_ROOT)

# Step 1: Feature engineering
from scripts.feature_engineering.compute_features import compute_all_features
features_df = compute_all_features(raw_df)

# Step 8-10: L1 precompute + backtest
from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest
from scripts.workflow.config import get_workflow_configs

results = run_sync_backtest(
    configs=get_workflow_configs(),  # All target×horizon combinations
    verbose=True
)
```

### Configuration

Edit `scripts/workflow/config.py`:

```python
# Prediction horizons (1 bar = 8 hours)
WORKFLOW_HORIZONS = [1]  # [1, 3, 6, 12] for multi-horizon

# Active targets
WORKFLOW_TARGETS = [
    "direction",
    "volatility",
    "volatility_regime",
    "trend_regime",
    "trade_setup",
    "path_label_5",
    "strategy_label",
    "triple_barrier",
]

# L1 helpers (all 10 for full feature set)
L1_HELPERS = [
    "if", "cusum", "garch", "hmm4", "hmm5",
    "kalman", "evt", "ou", "bocpd", "egarch"
]

# L1 iteration mode
L1_CONFIG_MODE = "1bar"     # "1bar", "reduced", or "all"
L1_ROWS = None              # None = maximum feasible iterations
```

---

## Validation Methodology

### Causality Verification

All feature computations are verified to use only past data:

1. **Expanding Windows** — Features computed on `[0:t-1]` to predict `t`
2. **Shift Verification** — All rolling operations use `.shift(1)`
3. **Spike Tests** — Verify historical values unchanged when new data added
4. **Snapshot Comparison** — Compare pre/post computation states

### Cross-Validation

Time-series cross-validation following Lopez de Prado (AFML Ch.7):

- **PurgedKFold** — Temporal gaps between train/test
- **Embargo Period** — 12 bars (96 hours) after test set
- **Purge Gap** — 21 bars (168 hours) before test set

### Quality Gates

Automatic checks at each pipeline step:

| Gate | Trigger | Action |
|------|---------|--------|
| Data Freshness | Stale > 24h | Auto-fetch or warn |
| Feature Drift | Distribution shift > 10% | Alert and log |
| Historical Preservation | Values changed | Halt pipeline |
| Target Distribution | Class imbalance change | Log warning |

---

## Research Foundation

This implementation incorporates techniques from:

### Academic Sources

- **Lopez de Prado, M. (2018)** — *Advances in Financial Machine Learning* (Wiley)
  - Triple barrier labeling, meta-labeling, purged cross-validation
  
- **Bailey & de Prado (2014)** — *The Deflated Sharpe Ratio*
  - Backtest overfitting correction
  
- **Deep, G. et al. (2024)** — *Interpretable Hypothesis-Driven Trading* (arXiv:2512.12924)
  - Walk-forward validation framework

- **Arian, H.R. et al. (2024)** — *Backtest Overfitting in the Machine Learning Era* (SSRN:4778909)
  - ML-specific overfitting detection

### Implementation Notes

See `docs/` for detailed research notes:
- `VALIDATION_TESTING_RESEARCH.md` — Walk-forward methodology
- `ACCURACY_IMPROVEMENT_RESEARCH.md` — Feature engineering research
- `SIGNAL_LABELING_RESEARCH.md` — Target design rationale

---

## Performance Benchmarks

### L1 Precomputation (7 configs, ~5500 iterations each)

| Backend | Time | Speedup |
|---------|------|---------|
| Pure Python | ~45 min | 1× |
| Rust-accelerated | ~3 min | **15×** |



---

## Development: AI-Assisted Workflow

This project is developed in partnership with **Astra**, a cognitive AI agent built on clarity, structured reasoning, and persistent memory. Astra operates within VS Code using GitHub Copilot's agent mode with custom extensions for memory and task management.

### Cognitive Architecture

Astra implements a multi-layered reasoning system:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ASTRA COGNITIVE LAYERS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 1: Aristotelian    │ Classification (DATA/FEATURE/MODEL/PIPELINE)    │
│ Layer 2: Platonic        │ Ideal Forms (compare against perfect templates) │
│ Layer 3: Socratic        │ Clarifying questions before action              │
│ Layer 4: Steady Mind     │ Uncertainty handling without panic              │
│ Layer 5: Cooperative     │ Present analysis, human decides                 │
│ Layer 6: Extended Mind   │ Memory files ARE part of cognition              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Dual-Memory System

Astra uses two complementary memory mechanisms for context management:

#### 1. Short-Term: Task Tracking (`<todos>`)

Active task management via VS Code's todo system, auto-injected into every conversation:

```
<todos title="Current Sprint">
- [x] add-enum: Add PathLabel7Class enum to targets.py
- [x] extend-helper: Extend helper with efficiency_ratio, retracement
- [ ] integration-test: Verify Step 3-4 pipeline integration
</todos>
```

**Workflow:**
- Tasks created at session start
- One task `in_progress` at a time
- Marked `completed` immediately when done
- Prevents drift and ensures accountability

#### 2. Long-Term: Persistent Memory (`/memories/`)

File-based memory system that persists across conversation resets:

```
/memories/
├── session.md          # Current project state, recent changes, next steps
├── startup.md          # Session initialization checklist
└── context/
    ├── target-design-research.md   # Academic sources, design decisions
    └── vol_regime_issue.md         # Debugging notes, root causes
```

**Memory Operations:**
- `memory view` — Read current context before acting
- `memory str_replace` — Update with new learnings
- `memory create` — Save research, decisions, patterns

**Why This Matters:**
- LLM context windows reset frequently
- Complex multi-day work requires continuity
- Captures *why* decisions were made, not just *what*

### Human-AI Partnership Model

```
┌─────────────────┐         ┌─────────────────┐
│      HUMAN      │◄───────►│      ASTRA      │
│   (Przem)       │         │   (AI Agent)    │
├─────────────────┤         ├─────────────────┤
│ • Makes decisions│         │ • Presents analysis│
│ • Sets direction │         │ • Implements code │
│ • Validates results│       │ • Maintains memory│
│ • Catches drift  │         │ • Tracks tasks   │
└─────────────────┘         └─────────────────┘
```

**Core Principles:**
- Astra **analyzes**, human **decides**
- Never say "probably fine" without verification
- Check memory before external search
- One thing at a time, mark completed immediately

### Anti-Drift Protocol

Safeguards against losing focus:

| Trigger | Action |
|---------|--------|
| Session start | `memory view /memories/session.md` |
| >5 messages without memory check | Self-check and re-anchor |
| User says "wrong" or "drifting" | STOP → review memory → resume |
| Making a decision | STOP → present analysis instead |

### Example Session Flow

```
1. SESSION START
   ├── Check <todos> block (auto-injected)
   ├── memory view /memories/session.md
   └── Review current task status

2. TASK EXECUTION
   ├── Mark todo "in_progress"
   ├── Implement changes
   ├── Verify with tests/checks
   └── Mark todo "completed"

3. SESSION END
   ├── Update session.md with progress
   ├── Record any new patterns/mistakes
   └── Handoff context if thread limits reached
```

### Tools and Extensions

| Extension | Purpose |
|-----------|---------|
| **Agent Memory** | Persistent `/memories/` storage across sessions |
| **Agent TODOs** | Task tracking with `<todos>` auto-injection |
| **Agent Handoff** | Context transfer to new conversation threads |

This workflow enables multi-day development cycles on complex ML systems while maintaining consistent quality and avoiding repeated mistakes.

---

## License

Apache License 2.0 — See [LICENSE](LICENSE) for details.

Copyright 2026 Przemysław Augustyniak

---

## Author

**Przemysław Augustyniak**

Development assisted by **Astra** — cognitive AI agent specialized in time-series ML systems.

---

*Built with rigorous methodology for production trading systems.*

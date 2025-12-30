# Part 1: Analysis Scripts Architecture

> **Document Version**: 1.0  
> **Last Updated**: 2025-12-22  
> **Module**: `scripts/analysis/`

---

## Overview

The Analysis Scripts module provides a modular, academically-grounded framework for:
- Feature analysis and selection
- Model training and evaluation
- Walk-forward backtesting
- Performance visualization

**Design Philosophy**: Single responsibility per module, centralized configuration, CLI-driven execution.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RiskYieldMM Analysis System                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
            ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
            │   Data      │   │   Features  │   │   Models    │
            │   Layer     │   │   Layer     │   │   Layer     │
            └─────────────┘   └─────────────┘   └─────────────┘
                    │                 │                 │
                    └─────────────────┼─────────────────┘
                                      │
                                      ▼
                              ┌─────────────┐
                              │  Backtest   │
                              │   Layer     │
                              └─────────────┘
                                      │
                                      ▼
                              ┌─────────────┐
                              │    Viz      │
                              │   Layer     │
                              └─────────────┘
```

---

## Data Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW DIAGRAM                                │
└──────────────────────────────────────────────────────────────────────────────┘

  RAW DATA                    FEATURE DATA                 ANALYSIS DATA
  ─────────                   ────────────                 ─────────────
      │                            │                            │
      ▼                            ▼                            ▼
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│merged_8h_raw │           │ features_8h  │           │ analysis_8h  │
│  .parquet    │──────────▶│  .parquet    │──────────▶│  .parquet    │
│  (24 cols)   │  External │  (167 cols)  │  data.py  │  (178 cols)  │
└──────────────┘  Pipeline └──────────────┘  merge    └──────────────┘
      │                            │                        │
      │                            │                        │
      │   RAW_* columns            │   Feature columns      │   + y_* targets
      │   (OHLCV, timestamps)      │   (166 signals)        │   (9 targets)
      │                            │                        │
      └────────────────────────────┴────────────────────────┘
                                   │
                                   ▼
                    ┌───────────────────────────────┐
                    │        ANALYSIS PIPELINE       │
                    ├───────────────────────────────┤
                    │  features.py: IC/ICIR         │
                    │  models.py: Train & CV        │
                    │  backtest.py: Walk-forward    │
                    │  viz.py: Plots & Reports      │
                    └───────────────────────────────┘
```

### Column Naming Convention

| Prefix | Type | Example | Usage |
|--------|------|---------|-------|
| `RAW_*` | Raw Data | `RAW_close`, `RAW_volume` | Context only, NOT for training |
| `y_*` | Target | `y_forward_return_1`, `y_direction_1` | Prediction targets |
| `rolling_*` | Rolling Stats | `rolling_volatility_21` | Features (past data only) |
| (none) | Features | `rsi_14`, `premiumZscore_21` | Model inputs |

---

## Module Responsibilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MODULE DEPENDENCY GRAPH                            │
└─────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────┐
                              │  config  │  ◄── Centralized configuration
                              └────┬─────┘
                                   │
           ┌───────────┬───────────┼───────────┬───────────┐
           │           │           │           │           │
           ▼           ▼           ▼           ▼           ▼
      ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
      │  data  │  │features│  │ models │  │backtest│  │  viz   │
      └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘  └────────┘
           │           │           │           │
           │           │           │           │
           └───────────┴───────────┴───────────┘
                              │
                              ▼
                        ┌──────────┐
                        │   run    │  ◄── CLI entry point
                        └──────────┘
```

| Module | Responsibility | Key Dependencies |
|--------|---------------|------------------|
| `config.py` | All configuration, paths, hyperparameters | None |
| `data.py` | Data loading, target generation, sample weights | config |
| `features.py` | IC/ICIR, domain classification, importance | config, scipy |
| `models.py` | Model training, CV, calibration | config, data, sklearn |
| `backtest.py` | Position sizing, walk-forward, metrics | config, data, models |
| `viz.py` | All plotting and visualization | config, matplotlib |
| `run.py` | CLI interface, orchestration | all modules |

---

## CLI Interface

```bash
# Prepare analysis dataset (merge features + create targets)
python -m scripts.analysis.run prepare [--output PATH]

# Run cross-validation for direction/volatility models
python -m scripts.analysis.run cv [--n-folds N] [--model TYPE]

# Compute IC/ICIR for all features
python -m scripts.analysis.run features [--target COL] [--output PATH]

# Compute feature importance (LightGBM-based)
python -m scripts.analysis.run importance [--top N]

# Run walk-forward backtest
python -m scripts.analysis.run backtest [--iterations N] [--train-size N]

# Generate full analysis report
python -m scripts.analysis.run all
```

### CLI Architecture

```
run.py
├── prepare_cmd()      → data.create_analysis_dataset()
├── cv_cmd()           → models.run_direction_cv() / run_volatility_cv()
├── features_cmd()     → features.compute_ic_analysis()
├── importance_cmd()   → features.compute_feature_importance()
├── backtest_cmd()     → backtest.run_walk_forward()
└── all_cmd()          → Orchestrates all above
```

---

## Configuration System

All configuration is centralized in `config.py` using dataclasses:

```python
# Paths
DATA_DIR = Path("data")
FEATURES_FILE = DATA_DIR / "features_8h.parquet"
ANALYSIS_FILE = DATA_DIR / "analysis_8h.parquet"

# Dataclass configs
@dataclass
class ModelConfig:
    cb_iterations: int = 500
    cb_depth: int = 6
    lgb_n_estimators: int = 500
    ...

@dataclass
class PositionConfig:
    confidence_threshold: float = 0.55
    max_leverage: float = 2.0
    ...
```

**Design Decision**: No magic numbers in module code — all configurable values live in `config.py`.

---

## Academic Foundation

Each analysis method is grounded in peer-reviewed literature:

| Method | Source | Citation |
|--------|--------|----------|
| IC/ICIR | Grinold & Kahn | "Active Portfolio Management" (1999) |
| FDR Correction | Benjamini & Hochberg | JRSS-B (1995), 12,814 citations |
| Feature Importance | Lopez de Prado | "Advances in Financial ML" (2018) |
| Gradient Boosting | Prokhorenkova et al. | NeurIPS 2018 (CatBoost) |
| Time-Series CV | scikit-learn | TimeSeriesSplit with gap |

See **Part_4_Analysis_Methods.md** for detailed formulas and implementations.

---

## Leakage Prevention

**Critical Design Constraint**: No future information in features.

```
                    TEMPORAL BOUNDARY
                          │
  ◄────── PAST ───────────│────────── FUTURE ──────►
                          │
  ┌─────────────┐         │    ┌─────────────┐
  │   Features  │─────────│────│   Targets   │
  │  (inputs)   │    ✗    │ ✓  │  (y_* cols) │
  └─────────────┘  NEVER  │    └─────────────┘
                   cross  │
                          │
```

**Enforced Rules**:
1. All targets prefixed with `y_` — easy identification
2. Features use only past data (rolling windows look backward)
3. Train/test splits respect temporal ordering
4. Gap parameter in CV prevents label overlap

---

## Directory Structure

```
scripts/analysis/
├── __init__.py        # Package exports, version
├── config.py          # ★ All configuration (4.8 KB)
├── data.py            # Data loading, targets (5.5 KB)
├── features.py        # IC/ICIR, importance (9.9 KB)
├── models.py          # Training, CV (11.8 KB)
├── backtest.py        # Walk-forward (7.9 KB)
├── viz.py             # Plotting (10.5 KB)
└── run.py             # CLI entry point (8.2 KB)
                       ─────────────────────
                       Total: ~58.6 KB (7 modules)
```

---

## Execution Flow Example

```
User runs: python -m scripts.analysis.run backtest --iterations 100

run.py
  │
  ├── Parse CLI arguments
  ├── Load config
  │
  └── backtest_cmd()
        │
        ├── data.load_analysis_data()
        │     └── Read analysis_8h.parquet
        │
        ├── data.get_feature_columns()
        │     └── Filter out y_*, RAW_*, timestamp
        │
        └── backtest.run_walk_forward()
              │
              ├── For each iteration:
              │     ├── Split train/calibration/test
              │     ├── models.train_direction_ensemble()
              │     ├── models.train_volatility_model()
              │     ├── backtest.position_sizer_v3()
              │     └── Accumulate results
              │
              └── backtest.compute_backtest_metrics()
                    │
                    └── viz.plot_backtest_results() [optional]
```

---

## Next Documents

- **Part_2_Libraries.md** — Library choices and justifications
- **Part_3_Data_Schema.md** — Full schema of analysis_8h.parquet
- **Part_4_Analysis_Methods.md** — Formulas with academic citations
- **Part_5_Modules.md** — Detailed module documentation

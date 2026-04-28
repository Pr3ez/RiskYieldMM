# Kaggle Pipeline Documentation

> Documentation of the Hull Tactical ML pipeline from `/media/przem/w/kaggle/`

---

## Overview

This folder documents the complete ML pipeline for the Hull Tactical Market Prediction Kaggle competition. The pipeline processes market data row-by-row to ensure perfect consistency between training and inference.

**Source Location:** `/media/przem/w/kaggle/`

**Main Scripts:**
| Script | Lines | Purpose |
|--------|-------|---------|
| `final-1.py` | 15,743 | Base version |
| `final-2.py` | 17,046 | Extended HMM features + Feature-Group HMMs |
| `final-3.py` | 16,976 | Full pipeline with model training |
| `final-upl.py` | 13,136 | Upload/submission version |
| `row_by_row_features.py` | 885 | Core feature calculator class |

---

## Documentation Parts

| Part | File | Description |
|------|------|-------------|
| 1 | [Part_1_Cell_Structure.md](Part_1_Cell_Structure.md) | Cell-by-cell structure of scripts |
| 2 | [Part_2_Features.md](Part_2_Features.md) | All features with formulas |
| 3 | [Part_3_Models.md](Part_3_Models.md) | Models and ensembles |
| 4 | [Part_4_Row_By_Row.md](Part_4_Row_By_Row.md) | Row-by-row calculation flow |
| 5 | [Part_5_API_Simulation.md](Part_5_API_Simulation.md) | API inference simulation |

---

## Key Concepts

### 1. Three Dataset Splits
```
PARTIAL: Rows with some NaNs (warm-up period for rolling features)
TRAIN:   Complete rows (no NaNs) - used for model training
VALID:   Last 180 rows - held out for validation
```

### 2. Row-by-Row Guarantee
All features are calculated using `RowByRowFeatureCalculator` to ensure:
- ZERO discrepancy between training and inference
- Same code path for all datasets
- No batch vs row-by-row mismatches
- Production-ready from day 1

### 3. Target Variables
```python
# Direction Target (Binary Classification) - NET CANDLE method
# Uses full candle info for better signal
up_move = (future_high - close) / close
down_move = (close - future_low) / close
net_candle_ret = up_move - down_move
direction_target = (net_candle_ret > 0).astype(int)

# Volatility Target (Regression, uses close-to-close)
volatility_target = |forward_returns| clipped to [5th, 95th] percentile
```

---

## Quick Reference

**Feature Count:** ~400+ features total

**Models:**
- CatBoost Direction Model (binary classification)
- CatBoost Volatility Model (regression)
- HMM-4 (4-regime Hidden Markov Model)
- HMM-5 (5-regime volatility-specific HMM)
- Feature-Group HMMs (per feature prefix)
- Isolation Forest (anomaly detection)
- Kalman Filter (H=20)
- GARCH(1,1)

**Position Sizing:**
- Global optimization across model combinations
- Risk-aware sizing strategies

---

## Pipeline Flow

> **This documentation (Part 2) covers FEATURES. For MODEL TRAINING, see Part 3.**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    COMPLETE PIPELINE: Part 2 → Part 3                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   PART 2 (This Folder)              PART 3 (Walk-Forward System)            │
│   ═══════════════════               ══════════════════════════════          │
│                                                                              │
│   ┌─────────────────┐               ┌─────────────────────────────┐         │
│   │ Raw Market Data │               │      4-Window Training       │         │
│   └────────┬────────┘               │  [TRAIN]→[CAL]→[VAL]→[PRED] │         │
│            │                        └──────────────┬──────────────┘         │
│            ▼                                       │                         │
│   ┌─────────────────┐                              │                         │
│   │ RowByRowFeature │                              │                         │
│   │   Calculator    │──────── Features ──────────►│                         │
│   │  (~450 features)│                              │                         │
│   └────────┬────────┘                              ▼                         │
│            │                        ┌─────────────────────────────┐         │
│            ▼                        │  CatBoost + LightGBM        │         │
│   ┌─────────────────┐               │  Ensemble Training          │         │
│   │  HMM/DTMC/      │               └──────────────┬──────────────┘         │
│   │  Kalman/GARCH   │                              │                         │
│   │  (regime feat.) │──────── Regime Info ───────►│                         │
│   └─────────────────┘                              ▼                         │
│                                     ┌─────────────────────────────┐         │
│                                     │  Calibration + Meta-Stack   │         │
│                                     └──────────────┬──────────────┘         │
│                                                    │                         │
│                                                    ▼                         │
│                                     ┌─────────────────────────────┐         │
│                                     │  Position Sizing V3         │         │
│                                     │  → Final Prediction         │         │
│                                     └─────────────────────────────┘         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**→ Continue to:** [Part 3: Walk-Forward System](../3-Walk_Forward_System/README.md) — Model training, calibration, position sizing

---

## Related Documentation

- [Feature Engineering Stage 1](../1-Feature_Eng_st1/README.md) — Feature naming conventions
- [Walk-Forward System](../3-Walk_Forward_System/README.md) — **Next step: Model training using these features**
- [Bybit API Docs](../../BybitApiDocs/README.md) — Data source documentation

# Part 1: Cell Structure

> Cell-by-cell breakdown of final-2.py and final-3.py

---

## final-2.py Structure (17,046 lines)

| Cell | Lines | Purpose |
|------|-------|---------|
| **CELL 1** | 1-225 | Load Raw Data, Create Targets & Lagged Features |
| **CELL 2** | 226-259 | DEBUG: Validate Data Loading |
| **CELL 3** | 260-527 | Dataset Split: PARTIAL / TRAIN / VALIDATION |
| **CELL 4** | 528-664 | DEBUG: Validate Target Features |
| **CELL 5** | 665-843 | Feature Engineering (ROW-BY-ROW) |
| **CELL 5.5** | 844-966 | Validate Row-by-Row Feature Consistency |
| **CELL 5.6** | 967-1221 | Forward Returns Relative to Expectations |
| **CELL 6** | 1222-1675 | HMM-4: 4-Regime Hidden Markov Model |
| **CELL 7** | 1676-2391 | HMM-5: 5-Regime Volatility-Specific HMM |
| **CELL 7.5** | 2392-2922 | Advanced Markov Features (DTMC, Transition Matrix) |
| **CELL 7.6** | 2923-4158 | Feature-Group HMMs (M*, E*, I*, P*, V*, S*) |
| **CELL 7.7** | 4159-4641 | Derived Feature HMMs (MOM*, D*) |
| **CELL 7.8** | 4642-5673 | Per-Group Isolation Forest + Regime Change Detection |
| **CELL 9** | 5674-6112 | Helper Baseline Models (LR, EWMA, Direction) |
| **CELL 10** | 6113-6630 | Isolation Forest Multi-Level Anomaly Detection |
| **CELL 11** | 6631-6967 | CUSUM Changepoint Detection |
| **CELL 12** | 6968-7605 | Multi-Signal Ensemble Changepoint Detection |
| **CELL 13** | 7606-8007 | Kalman Filter H=20 Training |
| **CELL 14** | 8008-8577 | Create Kalman H=20 Features |
| **CELL 14.5** | 8578-8882 | GARCH(1,1) Volatility Features |
| **CELL 15** | 8883-8904 | Save TRAIN Dataset to CSV |
| **CELL 16** | 8905-9601 | Incremental HMM Feature Calculator Class |
| **CELL 17** | 9602-9857 | API Feature Calculator Class |
| **CELL 25.5** | 9858-11717 | Save Training DataFrame for Feature Validation |
| **CELL 27** | 11718-11756 | Prepare Incremental Isolation Forest for API |
| **CELL 27.5** | 11757-11948 | Save All Model States for API Inference |
| **CELL 28** | 11949-15712 | API SIMULATION: Row-by-Row Processing |
| **CELL 28.5** | 15713-17046 | Comprehensive Feature Consistency Debug |

---

## final-3.py Structure (16,976 lines)

| Cell | Lines | Purpose |
|------|-------|---------|
| **CELL 1** | 1-222 | Load Raw Data, Create Targets & Lagged Features |
| **CELL 2** | 223-256 | DEBUG: Validate Data Loading |
| **CELL 3** | 257-524 | Dataset Split: PARTIAL / TRAIN / VALIDATION |
| **CELL 4** | 525-661 | DEBUG: Validate Target Features |
| **CELL 5** | 662-840 | Feature Engineering (ROW-BY-ROW) |
| **CELL 5.5** | 841-963 | Validate Row-by-Row Feature Consistency |
| **CELL 6** | 964-1416 | HMM-4: 4-Regime Hidden Markov Model |
| **CELL 7** | 1417-2092 | HMM-5: 5-Regime Volatility-Specific HMM |
| **CELL 8** | 2093-2509 | Enhanced Feature Engineering (Momentum, Mean-Reversion) |
| **CELL 9** | 2510-2948 | Helper Baseline Models (LR, EWMA, Direction) |
| **CELL 10** | 2949-3432 | Isolation Forest Multi-Level Anomaly Detection |
| **CELL 11** | 3433-3755 | CUSUM Changepoint Detection |
| **CELL 12** | 3756-4393 | Multi-Signal Ensemble Changepoint Detection |
| **CELL 13** | 4394-4761 | Kalman Filter H=20 Training |
| **CELL 14** | 4762-5201 | Create Kalman H=20 Features |
| **CELL 15** | 5202-5223 | Save TRAIN Dataset to CSV |
| **CELL 16** | 5224-5522 | Incremental HMM Feature Calculator Class |
| **CELL 17** | 5523-5778 | API Feature Calculator Class |
| **CELL 18** | 5779-6504 | **Direction Model - Conservative Feature Selection** |
| **CELL 19** | 6505-7205 | **Volatility Regression Model - CatBoost** |
| **CELL 20** | 7206-7387 | Prepare 15% Validation Data for Position Sizing |
| **CELL 21** | 7388-8146 | **Position Sizing - Global Optimization** |
| **CELL 22** | 8147-8714 | Modern Risk-Aware Position Sizing (Strategy 2) |
| **CELL 23** | 8715-9058 | Validate Position Sizing on 15% Dataset |
| **CELL 24** | 9059-9400 | Walk-Forward Direction Model (Early Stopping) |
| **CELL 25** | 9401-9736 | Walk-Forward Volatility Model (Early Stopping) |
| **CELL 26** | 9737-12297 | Position Sizing Optimization |
| **CELL 27** | 12298-12336 | Prepare Incremental Isolation Forest for API |
| **CELL 28** | 12337-15643 | API SIMULATION: Row-by-Row Processing |
| **CELL 28.5** | 15644-16976 | Comprehensive Feature Consistency Debug |

---

## Key Differences: final-2.py vs final-3.py

| Aspect | final-2.py | final-3.py |
|--------|-----------|------------|
| Feature-Group HMMs | ✅ Yes (Cell 7.6, 7.7) | ❌ No |
| Derived Feature HMMs | ✅ Yes (Cell 7.7) | ❌ No |
| Per-Group Isolation Forest | ✅ Yes (Cell 7.8) | ❌ No |
| GARCH(1,1) Features | ✅ Yes (Cell 14.5) | ❌ No |
| Direction Model Training | ❌ No | ✅ Yes (Cell 18) |
| Volatility Model Training | ❌ No | ✅ Yes (Cell 19) |
| Position Sizing | ❌ No | ✅ Yes (Cells 20-26) |
| Walk-Forward Validation | ❌ No | ✅ Yes (Cells 24-25) |

---

## Data Flow Summary

```
                    ┌─────────────────┐
                    │   Raw Data      │
                    │   train.csv     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   CELL 1        │
                    │ Load + Targets  │
                    │ + Lagged Cols   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   CELL 3        │
                    │  Split Data     │
                    │ PARTIAL/TRAIN/  │
                    │   VALIDATION    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
         ┌─────────┐   ┌─────────┐   ┌─────────┐
         │ PARTIAL │   │  TRAIN  │   │  VALID  │
         │(warm-up)│   │(training)│   │(holdout)│
         └────┬────┘   └────┬────┘   └────┬────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   CELL 5        │
                    │  ROW-BY-ROW     │
                    │  FEATURES       │
                    │ (same calculator│
                    │  for all)       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  CELLS 6-14     │
                    │  HMM, IF,       │
                    │  Kalman, etc.   │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  CELLS 18-19    │
                    │  Model Training │
                    │ (Direction +    │
                    │  Volatility)    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  CELLS 20-26    │
                    │ Position Sizing │
                    │ Optimization    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   CELL 28       │
                    │ API Simulation  │
                    │ (row-by-row     │
                    │  inference)     │
                    └─────────────────┘
```

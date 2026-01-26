# Window Size Grid Search Experiment Plan

## Goal
Find optimal training window size for each model (CatBoost, LightGBM, LSTM, Linear) through full L2 backtest evaluation.

## Created Files
- `scripts/experiments/window_grid_search.py` — Main grid search runner
- `scripts/experiments/analyze_window_results.py` — Results analysis and visualization

---

## Experiment Phases

### Phase 1: Coarse Grid (Start Here)
**Goal:** Identify promising window ranges per model

```bash
# CatBoost first (fastest with GPU)
python scripts/experiments/window_grid_search.py --model catboost --coarse

# Then others
python scripts/experiments/window_grid_search.py --model lightgbm --coarse
python scripts/experiments/window_grid_search.py --model lstm --coarse
python scripts/experiments/window_grid_search.py --model linear --coarse
```

**Coarse grid:** 250, 300, 400, 500, 600, 700, 800 (7 values)

**Estimated time:** ~2-4 hours per model (full backtest)

### Phase 2: Fine Grid (After Phase 1)
**Goal:** Refine around best windows found in Phase 1

```bash
# Example: if CatBoost best was 400
python scripts/experiments/window_grid_search.py --model catboost --fine --base 400

# Creates grid: 300, 350, 375, 400, 425, 450, 500
```

### Phase 3: Target-Specific (Optional)
**Goal:** Check if different targets need different windows

```bash
# Direction targets only
python scripts/experiments/window_grid_search.py --model catboost --coarse \
    --configs direction_1bar,direction_3bar,direction_6bar,direction_12bar

# Volatility targets only  
python scripts/experiments/window_grid_search.py --model catboost --coarse \
    --configs volatility_1bar,volatility_3bar,volatility_6bar,volatility_12bar
```

---

## Quick Test Run
For testing the pipeline (100 steps only):

```bash
python scripts/experiments/window_grid_search.py --model catboost --coarse --n-steps 100
```

---

## Analyze Results

```bash
# After experiments complete
python scripts/experiments/analyze_window_results.py \
    data/experiments/window_grid_search/*_final.csv
```

**Outputs:**
- `optimal_windows.csv` — Best window per model × config
- `window_vs_accuracy.png` — Line plots
- `heatmap_accuracy.png` — Heatmap visualization
- `boxplot_accuracy.png` — Distribution comparison

---

## Expected Results

Based on research and current baselines:

| Model | Current Baseline | Expected Optimal Range |
|-------|------------------|----------------------|
| CatBoost | 400 | 300-500 |
| LightGBM | 400 | 350-500 |
| LSTM | 600 | 400-700 |
| Linear | 800 | 600-900 |

**Hypothesis:** 
- Tree models (CatBoost, LightGBM) may prefer smaller windows (faster adaptation)
- Sequence model (LSTM) may prefer medium windows (enough context)
- Linear may prefer larger windows (needs more data for stable coefficients)

---

## After Grid Search: Implementation

Once optimal windows are found, update baselines in:

**File:** `scripts/target_models/validation/backtest/services/training.py`

```python
# Lines 108-136 - Update BASELINE_* dictionaries
BASELINE_CB = {
    "train_window": <optimal_catboost>,  # From grid search
    ...
}
BASELINE_LGB = {
    "train_window": <optimal_lightgbm>,
    ...
}
BASELINE_LSTM = {
    "train_window": <optimal_lstm>,
    ...
}
BASELINE_LINEAR = {
    "train_window": <optimal_linear>,
    ...
}
```

---

## Time Estimates

| Experiment | Est. Time | Notes |
|------------|-----------|-------|
| Single model, coarse (7 windows) | 2-4 hours | Full backtest per window |
| Single model, fine (7 windows) | 2-4 hours | Narrower range |
| All models, coarse | 8-16 hours | Run sequentially or parallel |
| Quick test (100 steps) | 10-20 min | For validation only |

---

## Notes

1. **Disable Optuna** for grid search (`--enable-optuna` is off by default)
   - Optuna adds per-step tuning overhead
   - Grid search isolates window effect

2. **Full backtest is essential**
   - Single-fold may not capture regime changes
   - Walk-forward shows true out-of-sample performance

3. **Keep other parameters fixed**
   - Only window size varies
   - Other model params use current baselines
   - This isolates window size effect

4. **Results saved incrementally**
   - `*_intermediate.csv` updated after each window
   - Can resume analysis if interrupted

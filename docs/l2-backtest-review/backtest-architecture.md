# L2 Backtest Architecture

## Package Structure

```
scripts/target_models/validation/backtest/
├── domain/config.py        # SyncBacktestConfig, PerModelConfig
├── core/
│   ├── base.py             # ModelConfig ABC, ModelResult
│   ├── features.py         # apply_feature_selection, extract_per_model_splits
│   ├── ensemble.py         # AdaptiveWeightTracker, MWU algorithm
│   └── metrics.py          # build_step_metrics, compute_config_metrics
├── models/
│   ├── catboost_model.py   # CatBoost pipeline + Optuna tuning
│   ├── lightgbm_model.py   # LightGBM pipeline + Optuna tuning
│   ├── lstm_model.py       # LSTM pipeline + tuning
│   └── linear_model.py     # Ridge regularized baseline
├── adapters/
│   ├── data_loader.py      # ConfigData, load_config_data
│   └── output.py           # DualOutput (console + log file)
└── services/
    ├── training.py         # Orchestration per-model
    └── backtest.py         # run_sync_backtest (main entry)
```

Reference: [l2_backtest_sync.py#L12-32](../scripts/target_models/validation/l2_backtest_sync.py)

---

## 4-Model Ensemble

| Model | Default Weight | Device | Window |
|-------|----------------|--------|--------|
| CatBoost | 0.30 | GPU | 400 |
| LightGBM | 0.30 | GPU | 400 |
| LSTM | 0.25 | GPU | 600 |
| Linear | 0.15 | CPU | 800 |

Reference: [config.py#L233-246](../scripts/workflow/config.py)

---

## Walk-Forward Flow

```
For each step:
1. Load aligned data across all configs
2. For each config:
   a. Slice window per-model (different windows per model)
   b. Split: train(55%) | embargo | val(15%) | embargo | cal(30%)
   c. Optuna tune (warm-started from previous step)
   d. Train all 4 models
   e. Ensemble predict (MWU adaptive weights)
   f. Conformal calibration
3. Record predictions, update adaptive weights
4. Move to next step
```

Reference: [backtest.py#L72-300](../scripts/target_models/validation/backtest/services/backtest.py)

---

## Adaptive Weight Update (MWU)

From arXiv 2304.09947 - Multiplicative Weights Update:
- Tracks per-model accuracy over `adaptive_lookback` (default: 50) steps
- Updates weights with `adaptive_learning_rate` (default: 0.1)
- Enforces `adaptive_min_weight` (default: 0.05) per model

Reference: [backtest.py#L390-420](../scripts/target_models/validation/backtest/services/backtest.py)

---

## Data Alignment

All configs aligned to common `pred_idx` range before backtest:
- `compute_common_pred_idx_range()` finds overlap
- Each config loaded with same sample count

Reference: [backtest.py#L146-167](../scripts/target_models/validation/backtest/services/backtest.py)

---

## Embargo (de Prado)

Gap between splits to prevent leakage:
- Default: 24 bars
- Applied between train↔val and val↔cal

Reference: [config.py#L230](../scripts/workflow/config.py)

---

## Output Files

| File | Contents |
|------|----------|
| `{config}_sync_predictions.parquet` | Per-step predictions |
| `sync_backtest_summary.json` | Aggregate metrics |
| `classification_metrics_history.parquet` | Step-by-step metrics |
| `regression_metrics_history.parquet` | Step-by-step metrics |
| `backtest_run.log` | Console output |

Location: `data/l2_backtest_results/`

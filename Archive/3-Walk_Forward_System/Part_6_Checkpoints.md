# Part 6: Checkpoints & Deployment

## Checkpoint System

The Walk-Forward system uses checkpoints to persist state between runs, enabling:
1. **Resume interrupted backtests**
2. **Warmup → Live transitions**
3. **Skip Optuna tuning on restart**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CHECKPOINT ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  deploy_checkpoint.pkl                                                       │
│  ├── Model params (Optuna results)                                          │
│  │   ├── catboost_params                                                    │
│  │   ├── lightgbm_params                                                    │
│  │   └── histgb_params                                                      │
│  │                                                                           │
│  ├── Calibration state                                                       │
│  │   ├── cb_calibrator (fitted Platt)                                       │
│  │   ├── lgb_calibrator (fitted Platt)                                      │
│  │   └── meta_stacker (fitted RF)                                           │
│  │                                                                           │
│  ├── Config scorer state                                                     │
│  │   ├── config_data (per-config TP/FP)                                     │
│  │   ├── EMA histories                                                      │
│  │   └── switch_history                                                     │
│  │                                                                           │
│  ├── Rolling buffers                                                         │
│  │   ├── rolling_pred_types (deque)                                         │
│  │   ├── rolling_actuals                                                    │
│  │   ├── rolling_market_returns                                             │
│  │   └── rolling_strategy_returns                                           │
│  │                                                                           │
│  ├── Hull scorer histories                                                   │
│  │   ├── hull_benchmark_history                                             │
│  │   └── hull_baseline_history                                              │
│  │                                                                           │
│  ├── Pending prediction (for lagged eval)                                   │
│  │   ├── pred_class                                                         │
│  │   ├── pred_prob                                                          │
│  │   ├── threshold                                                          │
│  │   └── iteration                                                          │
│  │                                                                           │
│  └── Metadata                                                                │
│      ├── iteration                                                          │
│      ├── pred_start                                                         │
│      └── created_at                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## WarmupCheckpoint Dataclass

```python
@dataclass
class WarmupCheckpoint:
    """Complete state for checkpoint persistence."""
    # Position tracking
    iteration: int
    pred_start: int
    
    # Model hyperparameters
    catboost_params: Dict[str, Any]
    lightgbm_params: Dict[str, Any]
    histgb_params: Dict[str, Any]
    
    # Calibration buffers (deprecated - use calibrators directly)
    cb_cal_buffer_data: List
    lgb_cal_buffer_data: List
    meta_buffer_data: List
    
    # Fitted calibrators
    cb_calibrator: Any  # LogisticRegression or IsotonicRegression
    lgb_calibrator: Any
    meta_stacker: Any   # RandomForest meta-stacker
    
    # Config scorer state
    config_scorer_state: Dict[str, Any]
    config_results: Dict[str, Dict]
    
    # Hull scorer histories
    hull_benchmark_history: List
    hull_baseline_history: List
    
    # Tracker states
    benchmark_tracker: Dict
    baseline_tracker: Dict
    
    # Rolling buffers (converted from deque to list)
    rolling_pred_types: List[str]
    rolling_actuals: List[int]
    rolling_market_returns: List[float]
    rolling_strategy_returns: List[float]
    
    # Predictions made during warmup
    warmup_predictions: List[Dict]
    warmup_iterations: List[Dict]
    
    # Feature state
    aggregated_feature_cols: List[str]
    selected_features: List[str]
    
    # Diagnostics
    diagnostics: Dict
    drift_alerts: List
    calibration_diagnostics: List
    model_diversity_metrics: List
    
    # Live mode: pending prediction for lagged evaluation
    pending_prediction: Optional[Dict]
    
    # Metadata
    warmup_time_seconds: float
    created_at: str  # Timestamp
```

## Checkpoint Operations

### Save Checkpoint

```python
def save_checkpoint(checkpoint: WarmupCheckpoint, path: str):
    """Save checkpoint to pickle file."""
    import pickle
    
    with open(path, 'wb') as f:
        pickle.dump(checkpoint, f)
    
    print(f"✅ Checkpoint saved: {path}")
    print(f"   Iteration: {checkpoint.iteration}")
    print(f"   Created: {checkpoint.created_at}")
```

### Load Checkpoint

```python
def load_checkpoint(path: str) -> Optional[WarmupCheckpoint]:
    """Load checkpoint from pickle file."""
    import pickle
    
    if not os.path.exists(path):
        print(f"⚠️ Checkpoint not found: {path}")
        return None
    
    with open(path, 'rb') as f:
        checkpoint = pickle.load(f)
    
    print(f"✅ Checkpoint loaded: {path}")
    print(f"   Iteration: {checkpoint.iteration}")
    print(f"   Created: {checkpoint.created_at}")
    
    return checkpoint
```

## Resume Modes

### Full Resume

```python
# USE_CHECKPOINT_RESUME=True, USE_FEATURES_ONLY_RESUME=False
# Loads EVERYTHING - continue exactly where left off

if USE_CHECKPOINT_RESUME and not USE_FEATURES_ONLY_RESUME:
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    if checkpoint:
        # Position
        iteration = checkpoint.iteration
        pred_start = checkpoint.pred_start
        
        # Model params
        CATBOOST_DIR_PARAMS = checkpoint.catboost_params
        LIGHTGBM_DIR_PARAMS = checkpoint.lightgbm_params
        
        # Calibrators
        cb_calibrator = checkpoint.cb_calibrator
        lgb_calibrator = checkpoint.lgb_calibrator
        meta_stacker = checkpoint.meta_stacker
        
        # Rolling buffers (convert back to deque)
        rolling_pred_types = deque(checkpoint.rolling_pred_types, maxlen=ROLLING_WINDOW_SIZE)
        rolling_actuals = deque(checkpoint.rolling_actuals, maxlen=ROLLING_WINDOW_SIZE)
        
        # Hull scorers
        hull_scorer_benchmark.history = checkpoint.hull_benchmark_history
        hull_scorer_baseline.history = checkpoint.hull_baseline_history
        
        # Trackers
        benchmark_tracker = checkpoint.benchmark_tracker
        baseline_tracker = checkpoint.baseline_tracker
        
        # Config scorer
        config_scorer.restore_state(checkpoint.config_scorer_state)
```

### Features-Only Resume

```python
# USE_CHECKPOINT_RESUME=True, USE_FEATURES_ONLY_RESUME=True
# Loads calibrators/config history, RESETS metrics (TP/FP from 0)

if USE_FEATURES_ONLY_RESUME:
    checkpoint = load_checkpoint(CHECKPOINT_PATH)
    if checkpoint:
        # Model params
        CATBOOST_DIR_PARAMS = checkpoint.catboost_params
        LIGHTGBM_DIR_PARAMS = checkpoint.lightgbm_params
        
        # Calibrators (keep trained)
        cb_calibrator = checkpoint.cb_calibrator
        lgb_calibrator = checkpoint.lgb_calibrator
        meta_stacker = checkpoint.meta_stacker
        
        # Config scorer (rebase iterations to 0)
        config_scorer.restore_state(checkpoint.config_scorer_state, rebase_to_zero=True)
        
        # RESET everything else
        iteration = 0
        pred_start = MIN_HISTORY
        rolling_pred_types = deque(maxlen=ROLLING_WINDOW_SIZE)
        rolling_actuals = deque(maxlen=ROLLING_WINDOW_SIZE)
        hull_scorer_benchmark.history = []
        hull_scorer_baseline.history = []
        benchmark_tracker = {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0, ...}
```

## Deployment Modes

### Backtest Mode

```python
# DEPLOY_MODE='backtest' (default)
# Full run from scratch for optimization

DEPLOY_MODE = 'backtest'

first_pred_start = MIN_HISTORY
last_pred_start = total_rows - WF_PRED
n_expected_iterations = (last_pred_start - first_pred_start) // WF_PRED + 1

# Runs ALL iterations
# No checkpoint saving (unless explicitly enabled)
```

### Warmup Mode

```python
# DEPLOY_MODE='warmup'
# Run last N iterations to build state for live trading

DEPLOY_MODE = 'warmup'
WARMUP_ITERATIONS = 30

# Start from near end of data
production_first_pred = max(MIN_HISTORY, (total_rows - WF_PRED) - WARMUP_ITERATIONS + 1)
first_pred_start = production_first_pred
n_expected_iterations = WARMUP_ITERATIONS

# State built during warmup:
# ✓ Optuna hyperparameters
# ✓ Platt calibrators
# ✓ Meta-stacker weights
# ✓ Rolling TP/FP buffers
# ✓ Config scorer EMA histories
# ✓ Hull scorer histories

# Auto-saves checkpoint at end
PRODUCTION_AUTO_SAVE = True
```

### Live Mode

```python
# DEPLOY_MODE='live'
# Load checkpoint, make SINGLE prediction, save updated state

DEPLOY_MODE = 'live'

# Force checkpoint load
USE_CHECKPOINT_RESUME = True
CHECKPOINT_PATH = DEPLOY_CHECKPOINT_PATH

# Only predict on LAST row
first_pred_start = total_rows - WF_PRED
n_expected_iterations = 1

# Lagged evaluation enabled
if LIVE_LAGGED_EVALUATION and pending_prediction is not None:
    # Evaluate YESTERDAY's prediction with today's lagged_direction_target
    lagged_actual = source_df.iloc[pred_start][LAGGED_DIRECTION_TARGET]
    # Update TP/FP based on lagged actual
```

### Auto Mode

```python
# DEPLOY_MODE='auto'
# Automatically choose warmup or live based on checkpoint existence

DEPLOY_MODE = 'auto'

if os.path.exists(DEPLOY_CHECKPOINT_PATH):
    # Checkpoint exists → LIVE mode
    effective_mode = 'live'
    print("⭐ AUTO MODE: Checkpoint found → LIVE prediction")
else:
    # No checkpoint → WARMUP first
    effective_mode = 'warmup'
    print("⭐ AUTO MODE: No checkpoint → WARMUP first")
```

## Checkpoint Saving (Production Mode)

```python
if PRODUCTION_MODE and PRODUCTION_AUTO_SAVE:
    # Build checkpoint with all state
    production_checkpoint = WarmupCheckpoint(
        iteration=iteration,
        pred_start=pred_start,
        catboost_params=CATBOOST_DIR_PARAMS,
        lightgbm_params=LIGHTGBM_DIR_PARAMS,
        histgb_params=HISTGB_DIR_PARAMS,
        cb_cal_buffer_data=[],
        lgb_cal_buffer_data=[],
        meta_buffer_data=[],
        cb_calibrator=cb_calibrator,
        lgb_calibrator=lgb_calibrator,
        meta_stacker=meta_stacker,
        config_scorer_state=config_scorer.get_state(),
        config_results={k: {kk: vv for kk, vv in v.items() if kk != 'rolling_pred_types'} 
                       for k, v in config_results.items()},
        hull_benchmark_history=hull_scorer_benchmark.history.copy(),
        hull_baseline_history=hull_scorer_baseline.history.copy(),
        benchmark_tracker={k: v if not isinstance(v, deque) else list(v) 
                         for k, v in benchmark_tracker.items()},
        baseline_tracker={k: v if not isinstance(v, deque) else list(v) 
                         for k, v in baseline_tracker.items()},
        rolling_pred_types=list(rolling_pred_types),
        rolling_actuals=list(rolling_actuals),
        rolling_market_returns=list(rolling_market_returns),
        rolling_strategy_returns=list(rolling_strategy_returns),
        warmup_predictions=walkforward_predictions,
        warmup_iterations=walkforward_iterations,
        aggregated_feature_cols=aggregated_feature_cols,
        selected_features=[],
        diagnostics=DIAGNOSTICS,
        drift_alerts=drift_alerts,
        calibration_diagnostics=calibration_diagnostics,
        model_diversity_metrics=model_diversity_metrics,
        pending_prediction=pending_prediction.__dict__ if pending_prediction else None,
        warmup_time_seconds=0.0,
        created_at=time.strftime('%Y-%m-%d %H:%M:%S'),
    )
    
    save_checkpoint(production_checkpoint, DEPLOY_CHECKPOINT_PATH)
```

## Checkpoint Saving (Live Mode)

```python
if LIVE_MODE:
    # Store pending prediction for lagged evaluation
    pending_prediction = PendingPrediction(
        pred_class=pred_class,
        pred_prob=float(pred_dir_probs[0]),
        threshold=float(optimal_threshold),
        signal=float(ensemble_signal),
        config_name=selected_config_name,
        iteration=iteration,
        timestamp=time.strftime('%Y-%m-%d %H:%M:%S'),
        config_predictions=config_probs_for_ensemble,
    )
    
    # Build updated checkpoint
    live_checkpoint = WarmupCheckpoint(
        # ... same as production checkpoint ...
        pending_prediction=pending_prediction.__dict__,
        # ...
    )
    
    save_checkpoint(live_checkpoint, DEPLOY_CHECKPOINT_PATH)
    
    # Output prediction result
    print(f"⭐ LIVE PREDICTION COMPLETE")
    print(f"  Prediction: {'LONG' if pred_class == 1 else 'STAY OUT'}")
    print(f"  Probability: {pred_dir_probs[0]:.1%}")
    print(f"  Threshold:   {optimal_threshold:.1%}")
    print(f"  Signal:      {ensemble_signal:.2f}")
```

## Typical Workflow

```bash
# 1. Development: Full backtest
WF_DEPLOY_MODE=backtest python sliding_window_evidence_based56.py

# 2. Prepare for production: Warmup
WF_DEPLOY_MODE=warmup WARMUP_ITERATIONS=50 python sliding_window_evidence_based56.py
# Creates: deploy_checkpoint.pkl

# 3. Daily live prediction
WF_DEPLOY_MODE=live python sliding_window_evidence_based56.py
# Loads checkpoint, predicts, updates checkpoint

# 4. Or use auto mode (recommended)
WF_DEPLOY_MODE=auto python sliding_window_evidence_based56.py
# Auto-selects warmup or live based on checkpoint existence
```

---

*See [Part_7_Modules.md](Part_7_Modules.md) for supporting module reference.*

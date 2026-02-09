# ============================================================================
# WF_DOCS.MD - Walk-Forward System Documentation
# ============================================================================
# Full documentation for sliding_window_evidence_based56.py
# See this file for detailed explanations of architecture, algorithms, and references.
# ============================================================================

## ARCHITECTURE OVERVIEW

### SLIDING WINDOW - IMPROVED ARCHITECTURE - NO LEAKAGE

**Required Stages (In Order):**
1. Dataset Analysis
2. Window-Length Estimation  
3. Sliding Window Construction
4. Feature Engineering
5. Feature Selection (FS window = TRAIN + CAL)
6. Model Training (TRAIN window)
7. Calibration (CAL window → rolling buffer for Platt scaling)
8. Validation - early stopping/HPO (VAL window - closest to PRED)
9. Class Balance Weight Calculation (CB ⊆ TRAIN only)
10. Walk-Forward Prediction
11. Final Evaluation

### 4-WINDOW ARCHITECTURE WITH ROLLING CALIBRATION

```
Layout: [---- TRAIN ----][-- CAL --][-- VAL --][PRED]
             ↑               ↑           ↑        ↑
        Fit model      Add to buffer Early stop  Apply
                       Fit Platt
        [------- FS = TRAIN + CAL -------]
        [--- CB = TRAIN only ---]
```

### ROLLING CALIBRATION BUFFER
- Individual CAL windows (~370 samples) are too small for stable calibration
- Solution: Accumulate multiple past CAL windows into a rolling buffer
- Platt scaling is more stable than isotonic for smaller datasets
- This is LEAKAGE-FREE: all buffer data is strictly BEFORE val/pred

---

## LEAKAGE PREVENTION RULES

1. Calibration buffer uses ONLY past CAL windows (never VAL or PRED)
2. Feature selection uses TRAIN + CAL (never VAL or PRED)
3. Class weights from TRAIN only (conservative)
4. Signal aggregator fitted ONLY on TRAIN window per iteration
5. Direction model output feeds volatility model (regime coupling)

---

## TEMPORAL SAFEGUARDS

### 1. WINDOW ORDERING (STRICTLY CHRONOLOGICAL)
```
TRAIN[t-n:t-c-v] < CAL[t-c-v:t-v] < VAL[t-v:t] < PRED[t]
```
- Each window is strictly before the next
- No overlap between any windows
- Indices enforced: train_start < cal_start < val_start < pred_start

### 2. CATBOOST TEMPORAL AWARENESS
- `has_time=True`: Forces CatBoost to respect row ordering
- Ordered boosting not used because incompatible with Lossguide on GPU
- Lossguide (leaf-wise) chosen for accuracy, with has_time=True for temporal
- `bootstrap_type='Bernoulli'` compatible with has_time on GPU

### 3. CALIBRATION BUFFER (STRICTLY HISTORICAL)
- Only includes CAL windows from PAST iterations
- Never includes VAL or PRED data
- Rolling buffer drops oldest windows when full
- Per-model buffers prevent cross-contamination

### 4. CLASS WEIGHTS (FROM TRAIN ONLY)
- scale_pos_weight calculated from TRAIN window
- Never uses CAL, VAL, or PRED labels for class balance

### 5. FEATURE SELECTION (TRAIN + CAL)
- FS window = TRAIN + CAL (never includes VAL or PRED)
- Feature importance from this window used for selection

### 6. META STACKER (TRAINED ON VAL ONLY)
- LogisticRegression meta-stacker trained on VAL (out-of-sample for base models)
- Uses calibrated probabilities from base models
- Never sees PRED data during training

### 7. RETURNS PREDICTION MODEL (TRAINED ON TRAIN)
- Ridge regression trained on TRAIN window only
- Features: ensemble probs, volatility, lagged returns
- Applied to PRED for final returns forecast

---

## CLASSES REFERENCE

### RollingCalBuffer
Rolling buffer for accumulating CAL window predictions for calibration.
- Stores (scores, labels) pairs from past CAL windows
- Strictly historical: never includes VAL/PRED data
- Configurable max windows and max samples
- Provides combined buffer for fitting Platt calibrator

### RollingMetaBuffer
Rolling buffer for accumulating VAL window predictions for meta-stacker training.
- Stores (cb_probs, lgb_probs, labels) from past VAL windows
- Strictly historical: only completed VAL windows with known labels
- Configurable max windows and max samples
- Provides combined buffer for training LogisticRegression meta-stacker

### AdaptiveMultiPeriodScorerV3
Adaptive Config Scorer with features:
1. Normalized scores - divide by √(window) so windows are comparable
2. True momentum - compare score NOW vs score 20 iters ago
3. Stricter thresholds - 15% min for declining path, 25% to leave current
4. Score floor - don't switch to weak configs
5. Hysteresis - asymmetric thresholds for switching
6. Multi-window scoring across range [5, 180] for robust selection
7. Dual EMA scoring (long-term + short-term) across 161 windows [20..180]

**Stability formula (normalized):**
```
score = (TP / max(FP, 1)) × √(TP) / √(window)
```

**Window progression:**
- Iter 10: [10]
- Iter 20: [10, 20]
- Iter 40: [10, 20, 40]
- Iter 80: [10, 20, 40, 80]
- Iter 160: [10, 20, 40, 80, 160]
- Iter 250: [10, 20, 40, 80, 160, 250]
- Every 80 iters after: add new window

### StableConfigEnsemble
Combines stable configs to estimate probability and generate position signal (0-2).
Uses raw probabilities weighted by reliability (TP/FP ratio) with risk adjustments.

**Key features:**
1. Uses raw probabilities (before thresholding) for full information
2. Weights by rolling TP/FP ratio (empirical reliability)
3. Agreement adjustment - reduces leverage when configs disagree
4. Stability adjustment - reduces leverage when configs are unstable
5. Momentum adjustment - reduces leverage when performance declining

**Signal range:**
- 0.0 = Full short (0% equity / max short)
- 1.0 = Neutral (100% equity baseline)
- 2.0 = Full long (200% equity / max leverage)

### HullScorer
Track Hull Tactical competition score on a rolling basis.

Competition metric is an adjusted Sharpe ratio with penalties for:
1. Excess volatility (if strategy_vol > 1.2 * market_vol)
2. Return underperformance (if strategy_return < market_return)

**Position interpretation (signal 0-2):**
- 0.0 = 0% equity (100% risk-free)
- 1.0 = 100% equity (buy and hold)
- 2.0 = 200% equity (max leverage)

**Strategy return formula:**
```
strategy_return = rf * (1 - position) + position * market_return
```

---

## FUNCTIONS REFERENCE

### Calibration Metrics (wf_functions.py)
- `compute_brier_score(probs, labels)` - MSE of probability estimates
- `compute_ece(probs, labels, n_bins)` - Expected Calibration Error
- `compute_calibration_stats(probs_before, probs_after, labels)` - Full stats

### Class Balancing (wf_functions.py)
- `calculate_scale_pos_weight(labels)` - Class weight for imbalanced data
- `calculate_half_life_weights(n_samples, half_life)` - Temporal decay weights

### Probability Calibration (wf_functions.py)
- `calibrate_probabilities_adaptive(val_probs, val_labels, pred_probs)` - Auto-select Platt/Isotonic

### Threshold Calculation (wf_functions.py)
- `calculate_optimal_threshold(val_probs, val_labels, method)` - Find optimal cutoff
- `adjust_threshold_for_regime(base_threshold, vol_regime)` - Regime-based adjustment

### Feature Selection (wf_functions.py)
- `select_top_features(model, feature_names, top_percent)` - Top N% by importance

---

## OPTUNA TUNING

### Data-Driven Search Space
Uses N (sample size), G (gap size), sparsity to bound search space:
- Larger gap = simpler model needed (more regularization, fewer leaves)
- Prevents Optuna from finding overfit configurations

### Warm-Start Enqueuing
Instead of fully persistent study:
1. Create FRESH study each time (adapts to new data distribution)
2. Enqueue best CB + best LGB params from PREVIOUS run as first 2 trials
3. Gives warm start without carrying stale exploration history

**Benefits:**
- Start from known-good configurations
- Still explore new parameter space freely
- Adapts to changing market conditions
- Avoids getting stuck in local optima

---

## ENSEMBLE CONFIGURATION

### ENSEMBLE_MODE options:
- `'single_cb'` - Only CatBoost classifier (fastest, simplest)
- `'cb_lgb'` - CatBoost + LightGBM ensemble (good balance)

### CB+LGB mode:
- Uses CatBoost and LightGBM direction classifiers
- Platt calibration applied to each model's probs
- Simple averaging or meta-stacker to combine
- Good diversity: GPU-based (CB) + CPU-based (LGB)

---

## MULTI-CONFIG TRACKING

Parallel tracking of 96 configurations across dimensions:
- Model: single vs ensemble
- Calibration: none vs platt
- Threshold: quantile_match vs youden_j vs class_balanced
- AUC adjustment: on vs off
- Regime threshold: on vs off
- Window: original vs shrunk

---

## BENCHMARK vs BASELINE

Two parallel metrics tracked from the SAME probability/threshold inputs:

### BENCHMARK (gates-only, works from iteration 1):
- Uses: alpha gate + direction gate ONLY
- Position: 0.0 (fail) or 1.0 (pass)
- NO EMA/RSI scaling - purely gate-based
- Tracked from first iteration for consistent comparison

### BASELINE (full system with EMA scaling):
- Uses: alpha gate + direction gate + ratio gate
- Position: 0.0-2.0 with EMA/RSI adjustments
- Requires ~194+ iterations for dual EMA warmup
- Full system with all refinements

---

## REFERENCES

### Calibration
- Niculescu-Mizil & Caruana (2005): Predicting Good Probabilities
- Kuleshov et al. (2018): Platt more stable with small datasets
- Gneiting & Raftery (2007): Strictly Proper Scoring Rules
- Platt (1999): Probabilistic Outputs for SVMs

### Time Series Cross-Validation
- Bailey et al.: Probability of Backtest Overfitting
- Bergmeir & Benítez: Time-series CV
- Hyndman (2018): Rolling-origin time-series CV

### Model Training
- CatBoost docs: Ordered boosting for CTR leakage prevention
- VC Dimension Theory: model capacity must grow slower than sqrt(N)
- Covariate Shift: simpler models generalize better under distribution shift

---

## MODULE STRUCTURE

```
sliding_window_evidence_based56.py  - Main walk-forward loop
├── wf_config.py                    - Configuration constants
├── wf_functions.py                 - Utility functions
├── wf_classes.py                   - Buffer and scorer classes (TODO)
├── window_diagnostics.py           - Diagnostic computations
└── signal_aggregator.py            - Signal combination
```

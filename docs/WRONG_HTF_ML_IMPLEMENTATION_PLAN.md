# HTF ML Signal Filter - Implementation Plan
## Walk-Forward Training for Meta-Labeling (Notebook-Centric)

**Goal:** Filter BB+RSI signals using ML to achieve >50% win rate (overcoming 0.11% Bybit fees)

**Design Principle:** ALL implementation stays within `htf_strategy_backtest.ipynb` - no external module files

---

## ✅ EXISTING NOTEBOOK VALIDATION (18 Cells)

### Cell-by-Cell Analysis

| Cell# | Type | Lines | Purpose | Status | Validates |
|-------|------|-------|---------|--------|-----------|
| 1 | MD | 2-21 | Data summary (5,574 batches, 3 TFs) | ✅ Doc | Data structure |
| 2 | PY | 24-42 | Load 1m/5m/15m combined parquet | ✅ Exec=2 | Data availability |
| 3 | PY | 45-171 | **Validate 8h OHLCV alignment** | ✅ Exec=8 | OPEN/CLOSE match 8h candles |
| 4 | MD | 174-190 | Feature engineering rules | ✅ Doc | `shift(1)` methodology |
| 5 | PY | 193-373 | **Add indicators** (BB, RSI, ATR, Vol, EMA) | ✅ Exec=12 | All use `shift(1)` |
| 6 | PY | 376-502 | **Leakage validation** | ✅ Exec=13 | Confirms no future leakage |
| 7 | PY | 505-587 | Signal statistics | ✅ Exec=14 | Signal frequency per batch |
| 8 | MD | 590-600 | Backtest methodology | ✅ Doc | TP/SL simulation rules |
| 9 | PY | 603-829 | **Numba backtest engine** | ✅ Exec=15 | `backtest_with_signals()` |
| 10 | PY | 832-1001 | Grid search (fixed TP/SL) | ✅ Exec=16 | Multiple configs tested |
| 11 | PY | 1004-1126 | Results analysis | ✅ Exec=17 | Win rate, PnL stats |
| 12 | PY | 1129-1431 | **Dynamic target backtest** | ✅ Exec=18 | BB_mid TP, ATR SL |
| 13 | PY | 1434-1593 | Best configs summary | ✅ Exec=19 | 0 profitable configs |
| 14 | MD | 1596-1630 | **Conclusions** | ✅ Doc | 36% WR, need >50% |
| 15 | MD | 1633-1653 | Constant TP/SL docs | ✅ Doc | Fee structure |
| 16 | PY | 1656-1854 | Alt backtest engine | ✅ Exec=3 | Comparison testing |
| 17 | PY | 1857-2105 | Extended grid search | ✅ Exec=10 | Additional configs |
| 18 | PY | 2108-2223 | Final results | ✅ Exec=11 | Summary statistics |

### Validation Summary

| Category | Cells | Status |
|----------|-------|--------|
| **Data Loading** | 2, 3 | ✅ 8h alignment verified |
| **Feature Engineering** | 5, 6 | ✅ shift(1) leakage-free |
| **Signal Generation** | 5, 7 | ✅ BB+RSI combinations |
| **Backtest Engine** | 9, 12 | ✅ Numba JIT optimized |
| **Results Analysis** | 10, 11, 13 | ✅ 36% WR documented |

### Key Validated Components to Reuse

```python
# From Cell 5 - Reusable
add_technical_indicators()  # BB, RSI, ATR, EMA with shift(1)

# From Cell 9 - Reusable  
backtest_with_signals()     # Numba JIT, fixed TP/SL

# From Cell 12 - Reusable
backtest_with_dynamic_targets()  # BB_mid TP, ATR SL
backtest_all_batches_dynamic()   # Parallel batch processing
```

---

## 📦 EXTERNAL ASSETS INVENTORY

### ⚠️ CRITICAL DATA VERIFICATION (Feb 4, 2026)

**The precomputed files in `data/precomputed/` are NOT usable for HTF backtest!**

| What I Assumed | Reality | Impact |
|----------------|---------|--------|
| 91 features per 8h batch | 91 features per **walk-forward iteration** | ❌ Wrong granularity |
| 5,574 batch files | 3,648 iteration files (starts 2022-08) | ❌ Missing 18 months |
| Aligned with HTF OHLCV | From main_wf.py pipeline (different system) | ❌ Can't merge |

### ✅ CORRECT Data Sources for HTF

| Source | Location | Rows | Features | Join Key |
|--------|----------|------|----------|----------|
| **HTF OHLCV** | `data/htf_backtest/5m_HTF_combined.parquet` | 535,060 | 8 (OHLCV) | `period_8h_start` |
| **Main Dataset** | `data/datasets/direction_1bar.parquet` | 5,574 | 175 | `timestamp` |

**Join Strategy:**
- HTF OHLCV has `period_8h_start` (e.g., "2021-11-30 00:00:00")
- Main Dataset has `timestamp` at 8h resolution
- **Match verified:** `period_8h_start == timestamp` ✅
- Broadcast 175 features to all ~96 candles in each 8h batch

### Available Features (175 from Main Dataset)

| Category | Prefix | Count | Examples |
|----------|--------|-------|----------|
| Momentum | `M_` | ~40 | rsi, roc, ppo, adx, stochastic |
| Volatility | `V_` | ~30 | atrPct, parkinson, garmanKlass, hurst |
| Liquidity | `L_` | ~30 | volumeRoc, oiRoc, cmf, mfi, obv |
| Normalized | `N_` | ~25 | zScore, pctB, vwapDeviation, cci |
| Derivatives | `D_` | ~20 | premiumZscore, markAtrRatio |
| Funding | `F_` | ~15 | fundingMa, fundingCumulative |
| Sentiment | `S_` | ~5 | longShortRatio, longShortChange |
| Candle | `B_`, `C_` | ~8 | candleDirection, bodySize |

### NOT Available (Correction from Previous Plan)

| What | Why Not |
|------|---------|
| 91 HTF precomputed features | Those are WF iterations, not 8h batch data |
| HMM regime states | Part of WF system, not accessible per 8h period |
| GARCH/Kalman features | Same - would need to recompute for HTF |

| Category | Features | Examples |
|----------|----------|----------|
| **HMM Regime** | 20+ | hmm4_state, hmm4_prob_bullish/bearish/neutral/volatile, hmm5_state |
| **GARCH/EGARCH** | 15+ | garch_cond_vol, garch_persistence, egarch_asymmetry, egarch_vol_regime |
| **Kalman Filter** | 8 | kalman_velocity, kalman_acceleration, kalman_zscore, kalman_regime |
| **BOCPD Changepoint** | 8 | bocpd_run_length, bocpd_cp_prob, bocpd_stability, bocpd_regime_age |
| **OU Mean-Revert** | 8 | ou_kappa, ou_halflife, ou_zscore, ou_is_stationary, ou_reverting |
| **Isolation Forest** | 12 | if_mean_score, if_mild/moderate/extreme_is, if_n_anomalies |
| **EVT Tail Risk** | 10 | evt_var95, evt_var99, evt_es95, evt_tail_prob_2std/3std |
| **CUSUM** | 4 | cusum_ret_pos/neg, cusum_vol_pos/neg |

### Main Dataset Features (177 features)
Located in `data/datasets/direction_1bar.parquet`:

| Category | Count | Examples |
|----------|-------|----------|
| Momentum (M_) | ~40 | rsi_6/12/21, roc_3/6/12/21, ppo, adx, stochastic |
| Volatility (V_) | ~30 | atrPct, parkinson, garmanKlass, yangZhang, hurst |
| Liquidity (L_) | ~30 | volumeRoc, oiRoc, cmf, mfi, obv, amihudIlliquidity |
| Normalized (N_) | ~25 | zScore, pctB, vwapDeviation, cci |
| Derivatives (D_) | ~20 | premiumZscore, markAtrRatio, closeVsMarkVol |
| Funding (F_) | ~15 | fundingMa, fundingCumulative, fundingZscore |
| Sentiment (S_) | ~5 | longShortRatio, longShortChange, longShortZscore |
| Candle | `B_`, `C_` | ~8 | candleDirection, bodySize |

### NOT Available (Correction from Previous Plan)

| What | Why Not |
|------|---------|
| 91 HTF precomputed features | Those are WF iterations, not 8h batch data |
| HMM regime states | Part of WF system, not accessible per 8h period |
| GARCH/Kalman features | Same - would need to recompute for HTF |

---

## 🎯 REVISED IMPLEMENTATION PLAN

### Architecture: Two-Level Features

```
Per 8h Batch:
├── BATCH-LEVEL (175 features from main dataset)
│   └── Broadcast to all signals in batch (same value)
│   └── E.g., M_N_rsi_12, V_atrPct_12, S_longShortRatio
│
└── SIGNAL-LEVEL (computed per signal from HTF OHLCV)
    └── Different for each signal bar
    └── E.g., bb_position, rsi_at_signal, time_in_batch
```

### Phase 1: Feature Loader (Revised)

```python
# Cell 19: LOAD 8H FEATURES AND MERGE WITH HTF
# =============================================

def load_batch_features() -> pl.DataFrame:
    """Load 175 features at 8h level from main dataset"""
    return pl.read_parquet('../data/datasets/direction_1bar.parquet')

def merge_features_to_htf(htf_df: pl.DataFrame, 
                          features_df: pl.DataFrame) -> pl.DataFrame:
    """
    Join 8h features to HTF OHLCV by period_8h_start == timestamp
    Each 96-candle batch gets the same 175 feature values
    """
    # Normalize timestamps for join
    features = features_df.with_columns(
        pl.col('timestamp').dt.replace_time_zone(None).alias('join_ts')
    )
    htf = htf_df.with_columns(
        pl.col('period_8h_start').dt.replace_time_zone(None).alias('join_ts')
    )
    
    # Join - broadcasts features to all candles in batch
    return htf.join(features, on='join_ts', how='left')
```

### Phase 2: Label Generation (Same as before)

```python
# Cell 20: SIGNAL OUTCOME LABELER
# ===============================
# Uses existing backtest logic from Cell 12
# Labels: WIN=1 (TP hit), LOSS=0 (SL hit or timeout)
```

### Phase 3: Meta-Model (Revised Features)

```python
# Cell 21: META-MODEL TRAINER
# ===========================
# Features for each signal:
#   - 175 batch-level features (from main dataset)
#   - ~10 signal-level features (computed per signal):
#     - bb_position: where in BB range
#     - rsi_value: RSI at signal
#     - atr_pct: ATR as % of price
#     - time_in_batch: bar position 0-95
#     - recent_win_rate: rolling win rate of last 20 signals
#
# Total: ~185 features per signal
```
    batch_df: pl.DataFrame,
    sl_atr_mult: float = 2.0,
    max_bars: int = 96
) -> pl.DataFrame:
    """Add 'signal_outcome' column to batch data"""
    - Compute BB bands with shift(1)
    - Compute RSI with shift(1)
    - Identify signal bars (BB+RSI conditions met)
    - For each signal: run triple barrier to get outcome
    - Return df with signal_outcome column (1=WIN, 0=LOSS, null=NO_SIGNAL)
```

### Phase 3: Meta-Labeling Model

```
Step 3.1: Feature engineering for meta-model
────────────────────────────────────────────
At signal bar[i], compute SHIFTED features (leakage-free):
  
  A) Signal context (from bar[i-1] and earlier):
     - BB position: (close - BB_lower) / (BB_upper - BB_lower)
     - RSI value: RSI[i-1]
     - ATR percentile: rank of ATR vs last 100 bars
     - Distance to BB_mid: (close - BB_mid) / BB_std
  
  B) Regime features (from precomputed):
     - HMM state (0-3 for bullish/bearish/neutral/volatile)
     - GARCH vol regime
     - OU mean-reversion strength (kappa)
     - Changepoint probability
  
  C) Market context:
     - Recent win rate (last 20 signals)
     - Time since last signal
     - Funding rate direction
     - Volume ratio

Step 3.2: Model configuration
─────────────────────────────
model_config = {
---

## ⏱️ IMPLEMENTATION TIMELINE (Notebook-Centric)

All code stays within `htf_strategy_backtest.ipynb`. New cells are added after Cell 14 (Conclusions).

| Phase | New Cell# | Purpose | Dependencies |
|-------|-----------|---------|--------------|
| **Phase 1** | Cell 19 | Feature Loader (merge 175 8h features to HTF) | Cells 2-3 |
| **Phase 2** | Cell 20 | Signal Outcome Labeler (triple barrier) | Cells 5, 12 |
| **Phase 3** | Cell 21 | Meta-Model Trainer (LightGBM) | Cells 19-20 |
| **Phase 4** | Cell 22 | Walk-Forward ML Backtest | Cells 9, 12, 21 |
| **Phase 5** | Cell 23 | Optimization & Results | Cell 22 |

**Total: 5 new cells, estimated 10-15 hours**

---

## 📝 NEW CELL SPECIFICATIONS (Revised)

### Cell 19: Feature Loader (8h Features → HTF)

**Purpose:** Load 175 features from main dataset and merge with HTF OHLCV

```python
# =============================================================================
# Cell 19: LOAD 8H FEATURES AND MERGE WITH HTF BATCHES
# =============================================================================
# Main dataset has 175 features at 8h level (one row per 8h period)
# HTF OHLCV has 96 rows per 8h batch (5m candles)
# JOIN: period_8h_start (HTF) == timestamp (main)
# RESULT: Each candle in batch gets same 175 features (broadcast)
# =============================================================================

def load_8h_features() -> pl.DataFrame:
    """Load 175 features at 8h level from main dataset"""
    df = pl.read_parquet('../data/datasets/direction_1bar.parquet')
    
    # Get feature columns (exclude targets and timestamp)
    feature_cols = [c for c in df.columns if not c.startswith(('y_', 'timestamp'))]
    
    # Keep timestamp for joining + feature columns
    return df.select(['timestamp'] + feature_cols)

def merge_features_to_htf(htf_df: pl.DataFrame, 
                          features_df: pl.DataFrame) -> pl.DataFrame:
    """
    Join 8h features to HTF OHLCV by timestamp alignment.
    Broadcasts same 175 values to all ~96 candles in each batch.
    """
    # Normalize timestamps for join (remove timezone)
    features = features_df.with_columns(
        pl.col('timestamp').dt.replace_time_zone(None).cast(pl.Datetime('us')).alias('join_ts')
    )
    htf = htf_df.with_columns(
        pl.col('period_8h_start').dt.replace_time_zone(None).cast(pl.Datetime('us')).alias('join_ts')
    )
    
    # Join - each candle gets the features of its 8h period
    result = htf.join(features, on='join_ts', how='left')
    
    # Verify join worked
    null_count = result.select(pl.col(features.columns[1]).is_null().sum()).item()
    if null_count > 0:
        print(f"⚠️ WARNING: {null_count} rows have null features (timestamp mismatch)")
    
    return result.drop('join_ts')

# Load and merge
print("Loading 8h features from main dataset...")
features_8h = load_8h_features()
print(f"  Shape: {features_8h.shape} ({len(features_8h)} 8h periods × {len(features_8h.columns)-1} features)")

print("Merging with HTF OHLCV (5m)...")
df_5m_with_features = merge_features_to_htf(df_5m_feat, features_8h)
print(f"  Result: {df_5m_with_features.shape}")
print(f"  Features per candle: {len(df_5m_with_features.columns) - 8}")  # 8 = original OHLCV cols
```

**Outputs:** `features_8h`, `df_5m_with_features` (HTF + 175 features)

---

### Cell 20: Signal Outcome Labeler

**Purpose:** Generate binary labels (WIN=1, LOSS=0) for BB+RSI signals

```python
# =============================================================================
# Cell 20: SIGNAL OUTCOME LABELER
# =============================================================================
# For each BB+RSI signal, determine if it hits TP or SL
# Uses existing backtest logic from Cell 12 (triple barrier)
# Labels only signal rows, others are null
# =============================================================================

@njit(cache=True)
def label_signal_outcome(
    ohlc: np.ndarray,       # (N, 4) OHLC for batch
    signal_idx: int,         # Bar index where signal fired
    bb_mid: float,           # BB middle band (TP for mean-reversion)
    atr: float,              # ATR for SL calculation
    sl_mult: float = 2.0,    # SL = entry ± sl_mult × ATR
    max_bars: int = 96,      # Max hold (rest of batch)
    direction: int = 1       # 1=LONG, -1=SHORT
) -> int:
    """
    Triple barrier labeling for single signal.
    Returns: 1=WIN (TP hit), 0=LOSS (SL hit or timeout)
    """
    entry_price = ohlc[signal_idx, 0]  # Open price
    
    if direction == 1:  # LONG
        tp_price = bb_mid  # Target = BB middle
        sl_price = entry_price - sl_mult * atr
    else:  # SHORT
        tp_price = bb_mid
        sl_price = entry_price + sl_mult * atr
    
    # Scan forward for TP or SL
    for j in range(signal_idx + 1, min(signal_idx + max_bars, len(ohlc))):
        high, low = ohlc[j, 1], ohlc[j, 2]
        
        if direction == 1:  # LONG
            if high >= tp_price:
                return 1  # WIN - TP hit
            if low <= sl_price:
                return 0  # LOSS - SL hit
        else:  # SHORT
            if low <= tp_price:
                return 1  # WIN - TP hit
            if high >= sl_price:
                return 0  # LOSS - SL hit
    
    return 0  # TIMEOUT = LOSS

def generate_batch_labels(batch_df: pl.DataFrame, 
                          sl_mult: float = 2.0,
                          max_bars: int = 96) -> pl.DataFrame:
    """
    Add 'signal_outcome' column to batch with labels for all signals.
    Non-signal rows get null.
    """
    # Already has indicators from Cell 5 (bb_sma, rsi, atr, entry signals)
    ohlc = batch_df.select(['open', 'high', 'low', 'close']).to_numpy()
    
    outcomes = np.full(len(batch_df), np.nan)
    
    # Label LONG signals
    long_mask = batch_df['entry_long_bb_rsi'].to_numpy()
    bb_mid = batch_df['bb_sma'].to_numpy()
    atr = batch_df['atr'].to_numpy()
    
    for i in np.where(long_mask)[0]:
        if not np.isnan(bb_mid[i]) and not np.isnan(atr[i]):
            outcomes[i] = label_signal_outcome(ohlc, i, bb_mid[i], atr[i], sl_mult, max_bars, 1)
    
    # Label SHORT signals  
    short_mask = batch_df['entry_short_bb_rsi'].to_numpy()
    for i in np.where(short_mask)[0]:
        if not np.isnan(bb_mid[i]) and not np.isnan(atr[i]):
            outcomes[i] = label_signal_outcome(ohlc, i, bb_mid[i], atr[i], sl_mult, max_bars, -1)
    
    return batch_df.with_columns(pl.Series('signal_outcome', outcomes))

# Generate labels for all batches
print("Generating signal outcome labels...")
df_5m_labeled = df_5m_with_features.group_by('batch_id').map_groups(generate_batch_labels)
n_signals = df_5m_labeled['signal_outcome'].drop_nulls().len()
n_wins = (df_5m_labeled['signal_outcome'] == 1).sum()
print(f"  Total signals: {n_signals}")
print(f"  Wins: {n_wins} ({100*n_wins/n_signals:.1f}%)")
```

**Outputs:** `df_5m_labeled` with `signal_outcome` column

---

### Cell 21: Meta-Model Trainer

**Purpose:** Train LightGBM to predict P(signal wins)

```python
# =============================================================================
# Cell 21: META-MODEL TRAINER
# =============================================================================
# Train LightGBM on historical signals to predict win probability
# Features: 175 batch-level + ~10 signal-level context features
# =============================================================================

from lightgbm import LGBMClassifier
from sklearn.isotonic import IsotonicRegression

META_CONFIG = dict(
    n_estimators=200,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    class_weight='balanced',
    verbose=-1,
    n_jobs=-1,
    random_state=42,
)

# Feature columns = all 175 8h features + signal context
FEATURE_COLS_8H = [c for c in features_8h.columns if c != 'timestamp']
SIGNAL_CONTEXT_COLS = ['bb_position', 'rsi', 'atr_pct', 'vol_ratio']

def extract_signal_features(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Extract feature matrix X and labels y for signal rows only.
    """
    # Filter to signal rows with valid labels
    signals = df.filter(pl.col('signal_outcome').is_not_null())
    
    # Features: 8h-level + signal context
    feature_cols = FEATURE_COLS_8H + SIGNAL_CONTEXT_COLS
    available = [c for c in feature_cols if c in signals.columns]
    
    X = signals.select(available).fill_null(0).to_numpy()
    y = signals['signal_outcome'].to_numpy()
    
    return X, y

def train_meta_model(X_train: np.ndarray, y_train: np.ndarray):
    """Train LightGBM + isotonic calibration"""
    # Train base model
    model = LGBMClassifier(**META_CONFIG)
    model.fit(X_train, y_train)
    
    # Calibrate probabilities (fit isotonic on OOB or CV)
    probs_train = model.predict_proba(X_train)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds='clip')
    calibrator.fit(probs_train, y_train)
    
    return model, calibrator

def predict_win_probability(model, calibrator, X: np.ndarray) -> np.ndarray:
    """Return calibrated P(win) for each sample"""
    raw_probs = model.predict_proba(X)[:, 1]
    return calibrator.predict(raw_probs)
```

**Outputs:** `train_meta_model()`, `predict_win_probability()`

---

### Cell 22: Walk-Forward ML Backtest

**Purpose:** Main loop - train on history, filter signals, track results

```python
# =============================================================================
# Cell 22: WALK-FORWARD ML BACKTEST
# =============================================================================
# For each batch N:
#   1. Train on signals from batches [0:N-1]
#   2. Predict P(win) for signals in batch N
#   3. Trade only if P(win) >= threshold
# =============================================================================

MIN_TRAIN_BATCHES = 90    # ~30 days minimum training
TRADE_THRESHOLD = 0.55    # Only trade if P(win) >= 55%
RETRAIN_EVERY = 9         # Retrain every 3 days (9 batches)

def walk_forward_ml_backtest(
    df: pl.DataFrame,
    min_train: int = MIN_TRAIN_BATCHES,
    threshold: float = TRADE_THRESHOLD,
    retrain_freq: int = RETRAIN_EVERY,
    sl_mult: float = 2.0,
    max_bars: int = 96
) -> dict:
    """Walk-forward backtest with ML signal filtering."""
    
    batch_ids = sorted(df['batch_id'].unique().to_list())
    n_batches = len(batch_ids)
    
    results = []
    model, calibrator = None, None
    last_train_idx = -retrain_freq  # Force train on first iteration
    
    for test_idx in tqdm(range(min_train, n_batches), desc="Walk-forward"):
        test_batch_id = batch_ids[test_idx]
        
        # Retrain model periodically
        if test_idx - last_train_idx >= retrain_freq:
            train_batch_ids = batch_ids[:test_idx]
            train_df = df.filter(pl.col('batch_id').is_in(train_batch_ids))
            X_train, y_train = extract_signal_features(train_df)
            
            if len(y_train) >= 50:  # Minimum samples to train
                model, calibrator = train_meta_model(X_train, y_train)
                last_train_idx = test_idx
        
        if model is None:
            continue  # Skip until we have a model
        
        # Get test batch
        test_df = df.filter(pl.col('batch_id') == test_batch_id)
        X_test, y_test = extract_signal_features(test_df)
        
        if len(X_test) == 0:
            continue  # No signals in this batch
        
        # Predict win probabilities
        win_probs = predict_win_probability(model, calibrator, X_test)
        
        # Filter by threshold
        for i, (prob, actual) in enumerate(zip(win_probs, y_test)):
            if prob >= threshold:
                results.append({
                    'batch_idx': test_idx,
                    'win_prob': prob,
                    'actual_outcome': int(actual),
                    'traded': True,
                })
            else:
                results.append({
                    'batch_idx': test_idx,
                    'win_prob': prob,
                    'actual_outcome': int(actual),
                    'traded': False,
                })
    
    return analyze_ml_results(results, threshold)

def analyze_ml_results(results: list, threshold: float) -> dict:
    """Analyze walk-forward results"""
    df = pl.DataFrame(results)
    
    traded = df.filter(pl.col('traded'))
    not_traded = df.filter(~pl.col('traded'))
    
    return {
        'total_signals': len(df),
        'traded': len(traded),
        'not_traded': len(not_traded),
        'traded_win_rate': traded['actual_outcome'].mean() if len(traded) > 0 else 0,
        'not_traded_win_rate': not_traded['actual_outcome'].mean() if len(not_traded) > 0 else 0,
        'baseline_win_rate': df['actual_outcome'].mean(),
        'threshold': threshold,
    }

# Run walk-forward backtest
print("=" * 70)
print("WALK-FORWARD ML BACKTEST")
print("=" * 70)
ml_results = walk_forward_ml_backtest(df_5m_labeled)

print(f"\nResults:")
print(f"  Total signals:     {ml_results['total_signals']}")
print(f"  Traded:            {ml_results['traded']} ({100*ml_results['traded']/ml_results['total_signals']:.1f}%)")
print(f"  Baseline win rate: {100*ml_results['baseline_win_rate']:.1f}%")
print(f"  TRADED win rate:   {100*ml_results['traded_win_rate']:.1f}%")  # <- Target: >50%
print(f"  Not traded WR:     {100*ml_results['not_traded_win_rate']:.1f}%")
```

---

### Cell 23: Optimization & Results

Same as before - grid search over threshold, min_train, sl_mult.

---

## 🚨 CRITICAL CONSTRAINTS

Secondary:
  - Trades taken vs signals seen (selectivity)
  - False positive rate (predicted win, actual loss)
  - Model calibration (Brier score)

Step 5.3: Robustness checks
───────────────────────────
  - Out-of-sample test (last 6 months)
  - Different market regimes (bull/bear/sideways)
  - Different symbols (ETH, SOL)
```

---

## ⏱️ IMPLEMENTATION TIMELINE (Notebook-Centric)

All code stays within `htf_strategy_backtest.ipynb`. New cells are added after Cell 14 (Conclusions).

| Phase | New Cell# | Purpose | Dependencies |
|-------|-----------|---------|--------------|
| **Phase 1** | Cell 19 | Precomputed Feature Loader | Cells 2-3 (data loading) |
| **Phase 2** | Cell 20 | Signal Outcome Labeler | Cells 5, 12 (indicators, backtest) |
| **Phase 3** | Cell 21 | Meta-Model Trainer | Cells 19-20 (features, labels) |
| **Phase 4** | Cell 22 | Walk-Forward ML Backtest | Cells 9, 12, 21 (backtest, model) |
| **Phase 5** | Cell 23 | Optimization & Results | Cell 22 (ML backtest) |

**Total: 5 new cells, estimated 10-15 hours**

---

## 📝 NEW CELL SPECIFICATIONS

### Cell 19: Precomputed Feature Loader

**Purpose:** Load and merge precomputed 91-feature batches with OHLCV data

```python
# Cell 19: PRECOMPUTED FEATURE LOADER
# ===================================
# Loads 91 HTF features per batch from data/precomputed/
# Merges with OHLCV by timestamp for unified feature matrix

def get_batch_files() -> list[str]:
    """Return sorted list of all batch parquet files"""
    precomputed_dir = Path("../data/precomputed/direction_1bar")
    return sorted(precomputed_dir.glob("*.parquet"))

def load_precomputed_batch(batch_file: Path) -> pl.DataFrame:
    """Load 91 HTF features for single batch"""
    return pl.read_parquet(batch_file)

def merge_batch_features(ohlcv_batch: pl.DataFrame, 
                         htf_features: pl.DataFrame) -> pl.DataFrame:
    """Merge OHLCV with precomputed features by row alignment"""
    # Both have 501 rows per batch, aligned by position
    return pl.concat([ohlcv_batch, htf_features], how="horizontal")

# Index all batches
BATCH_FILES = get_batch_files()
print(f"Found {len(BATCH_FILES)} precomputed batches")
print(f"Date range: {BATCH_FILES[0].stem} to {BATCH_FILES[-1].stem}")
```

**Outputs:** `BATCH_FILES` list, loader functions

---

### Cell 20: Signal Outcome Labeler

**Purpose:** Generate binary labels (WIN=1, LOSS=0) for BB+RSI signals using triple barrier

```python
# Cell 20: SIGNAL OUTCOME LABELER
# ===============================
# For each BB+RSI signal, compute if it hit TP (WIN) or SL (LOSS)
# Uses existing backtest logic from Cell 12

@njit(cache=True)
def label_signal_outcome(
    ohlc: np.ndarray,      # (N, 4) OHLC for batch
    signal_idx: int,        # Bar index where signal fired
    bb_mid: float,          # BB middle band value (TP target)
    atr: float,             # ATR value for SL calculation
    sl_mult: float = 2.0,   # SL = entry - sl_mult * ATR
    max_bars: int = 96,     # Max hold period
    direction: int = 1      # 1=LONG, -1=SHORT
) -> int:
    """
    Label signal outcome using triple barrier.
    Returns: 1=WIN (TP hit), 0=LOSS (SL hit or timeout)
    """
    entry_price = ohlc[signal_idx, 0]  # Open
    
    if direction == 1:  # LONG
        tp_price = bb_mid
        sl_price = entry_price - sl_mult * atr
    else:  # SHORT
        tp_price = bb_mid
        sl_price = entry_price + sl_mult * atr
    
    # Scan forward
    for j in range(signal_idx + 1, min(signal_idx + max_bars, len(ohlc))):
        high, low = ohlc[j, 1], ohlc[j, 2]
        
        if direction == 1:
            if high >= tp_price:
                return 1  # WIN
            if low <= sl_price:
                return 0  # LOSS
        else:
            if low <= tp_price:
                return 1  # WIN
            if high >= sl_price:
                return 0  # LOSS
    
    return 0  # TIMEOUT = LOSS

def generate_batch_labels(batch_df: pl.DataFrame) -> pl.DataFrame:
    """Add 'signal_outcome' column for all signals in batch"""
    # Uses add_technical_indicators() from Cell 5
    # Labels only rows where entry_long_bb_rsi or entry_short_bb_rsi is True
    ...
```

**Outputs:** `label_signal_outcome()`, `generate_batch_labels()`

---

### Cell 21: Meta-Model Trainer

**Purpose:** Train LightGBM meta-model on historical signals to predict win probability

```python
# Cell 21: META-MODEL TRAINER
# ===========================
# Train LightGBM to predict P(signal wins) from features
# Walk-forward: train on batches [0:N-1], predict batch N

from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV

META_MODEL_CONFIG = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "class_weight": "balanced",
    "verbose": -1,
    "n_jobs": -1,
}

def extract_signal_features(batch_df: pl.DataFrame, 
                            signal_rows: pl.DataFrame) -> np.ndarray:
    """Extract feature matrix for signal rows only"""
    # Columns: 91 HTF features + 10 signal context features
    # Signal context: bb_position, rsi, atr_pct, vol_ratio, etc.
    ...

def train_meta_model(X_train: np.ndarray, 
                     y_train: np.ndarray) -> CalibratedClassifierCV:
    """Train and calibrate meta-labeling model"""
    base_model = LGBMClassifier(**META_MODEL_CONFIG)
    calibrated = CalibratedClassifierCV(base_model, method='isotonic', cv=3)
    calibrated.fit(X_train, y_train)
    return calibrated

def predict_win_probability(model, X_signal: np.ndarray) -> float:
    """Return P(signal wins)"""
    return model.predict_proba(X_signal.reshape(1, -1))[0, 1]
```

**Outputs:** `train_meta_model()`, `predict_win_probability()`

---

### Cell 22: Walk-Forward ML Backtest

**Purpose:** Main loop - train model on history, filter signals on current batch

```python
# Cell 22: WALK-FORWARD ML BACKTEST
# =================================
# Core implementation: expanding window training, signal filtering

MIN_TRAIN_BATCHES = 90   # ~30 days minimum training
TRADE_THRESHOLD = 0.55   # Only trade if P(win) >= 55%
RETRAIN_EVERY = 3        # Retrain every 3 batches (1 day)

def walk_forward_ml_backtest(
    batch_files: list[Path],
    min_train: int = MIN_TRAIN_BATCHES,
    threshold: float = TRADE_THRESHOLD,
    retrain_freq: int = RETRAIN_EVERY,
    sl_mult: float = 2.0,
    max_bars: int = 96
) -> dict:
    """
    Walk-forward backtest with ML signal filtering.
    
    For batch N:
    1. Load training data from batches [0:N-1]
    2. Train meta-model on signal outcomes
    3. For each signal in batch N:
       - Predict P(win) using meta-model
       - Trade only if P(win) >= threshold
    4. Record results
    """
    results = []
    model = None
    last_train_idx = -1
    
    for test_idx in tqdm(range(min_train, len(batch_files)), desc="Walk-forward"):
        
        # Retrain model if needed
        if model is None or (test_idx - last_train_idx) >= retrain_freq:
            X_train, y_train = load_training_data(batch_files[:test_idx])
            model = train_meta_model(X_train, y_train)
            last_train_idx = test_idx
        
        # Load test batch
        test_batch = load_batch_with_features(batch_files[test_idx])
        signals = identify_signals(test_batch)
        
        for signal in signals:
            X_signal = extract_signal_features(test_batch, signal)
            win_prob = predict_win_probability(model, X_signal)
            
            # Filter by threshold
            if win_prob >= threshold:
                # Execute trade using existing backtest logic
                outcome = simulate_trade(test_batch, signal, sl_mult, max_bars)
                results.append({
                    "batch_idx": test_idx,
                    "signal_bar": signal["bar_idx"],
                    "direction": signal["direction"],
                    "win_prob": win_prob,
                    "outcome": outcome["result"],
                    "pnl_gross": outcome["pnl_gross"],
                    "pnl_net": outcome["pnl_net"],
                })
    
    return analyze_results(results)

# Run the backtest
print("=" * 70)
print("WALK-FORWARD ML BACKTEST")
print("=" * 70)
ml_results = walk_forward_ml_backtest(BATCH_FILES)
```

**Outputs:** `walk_forward_ml_backtest()`, `ml_results`

---

### Cell 23: Optimization & Results

**Purpose:** Grid search over hyperparameters, final analysis

```python
# Cell 23: OPTIMIZATION & RESULTS
# ===============================
# Test different thresholds, training windows, SL multipliers

PARAM_GRID = {
    "threshold": [0.50, 0.55, 0.60, 0.65],
    "min_train": [45, 90, 180],
    "sl_mult": [1.5, 2.0, 2.5],
}

def run_optimization():
    """Grid search over parameters"""
    results = []
    for thresh in PARAM_GRID["threshold"]:
        for min_t in PARAM_GRID["min_train"]:
            for sl_m in PARAM_GRID["sl_mult"]:
                r = walk_forward_ml_backtest(
                    BATCH_FILES,
                    threshold=thresh,
                    min_train=min_t, 
                    sl_mult=sl_m
                )
                results.append({
                    "threshold": thresh,
                    "min_train": min_t,
                    "sl_mult": sl_m,
                    **r
                })
    return pl.DataFrame(results)

# Run optimization
opt_results = run_optimization()

# Display best configs
print("\n" + "=" * 70)
print("TOP 5 CONFIGURATIONS BY NET PNL")
print("=" * 70)
print(opt_results.sort("net_pnl", descending=True).head(5))
```

**Outputs:** Optimization results, best configuration

---

## 🚨 CRITICAL CONSTRAINTS

### No Data Leakage
1. **Feature calculation**: All indicators use `shift(1)` - only prior bar data
2. **Training data**: Batches [0:N-1] for predicting batch N
3. **Label lookback**: Triple barrier uses only FUTURE bars within same batch
4. **Model training**: Never train on test batch data

### Walk-Forward Validation
```
Time: ───────────────────────────────────────►
Batches: [0][1][2]...[N-1] | [N]
         └────────────────┘  │
              TRAIN          TEST
              
Next iteration:
Batches: [0][1][2]...[N-1][N] | [N+1]
         └───────────────────┘   │
              TRAIN              TEST
```

### Memory Management
- Don't load all 5,574 batches at once
- Use lazy loading with batch index
- Clear old models after retraining
- Cache feature computations where possible

---

## 📁 NOTEBOOK STRUCTURE (After Implementation)

```
htf_strategy_backtest.ipynb (23 cells total)
│
├── EXISTING (Cells 1-18) ────────────────────────────────
│   ├── Data Layer (Cells 1-3)
│   │   ├── Cell 1: MD - Data summary
│   │   ├── Cell 2: PY - Load 1m/5m/15m data
│   │   └── Cell 3: PY - Validate 8h alignment ✅
│   │
│   ├── Feature Layer (Cells 4-7)
│   │   ├── Cell 4: MD - Feature rules
│   │   ├── Cell 5: PY - Technical indicators ✅
│   │   ├── Cell 6: PY - Leakage validation ✅
│   │   └── Cell 7: PY - Signal statistics
│   │
│   ├── Backtest Layer (Cells 8-13)
│   │   ├── Cell 8: MD - Methodology
│   │   ├── Cell 9: PY - Numba backtest engine ✅
│   │   ├── Cell 10: PY - Grid search
│   │   ├── Cell 11: PY - Results analysis
│   │   ├── Cell 12: PY - Dynamic target backtest ✅
│   │   └── Cell 13: PY - Config summary
│   │
│   └── Analysis Layer (Cells 14-18)
│       ├── Cell 14: MD - Conclusions (36% WR)
│       └── Cells 15-18: Alt implementations
│
└── NEW ML LAYER (Cells 19-23) ───────────────────────────
    ├── Cell 19: PY - Precomputed Feature Loader
    │   └── get_batch_files(), load_precomputed_batch()
    │
    ├── Cell 20: PY - Signal Outcome Labeler
    │   └── label_signal_outcome(), generate_batch_labels()
    │
    ├── Cell 21: PY - Meta-Model Trainer
    │   └── train_meta_model(), predict_win_probability()
    │
    ├── Cell 22: PY - Walk-Forward ML Backtest
    │   └── walk_forward_ml_backtest() - MAIN ENTRY POINT
    │
    └── Cell 23: PY - Optimization & Results
        └── run_optimization(), analysis tables
```

---

## ✅ VALIDATION CHECKLIST

Before implementation, verify:

| Check | Method | Expected |
|-------|--------|----------|
| Precomputed files exist | `ls data/precomputed/direction_1bar/*.parquet \| wc -l` | ~5,574 |
| Feature count per batch | `pl.read_parquet().shape[1]` | 91 columns |
| Batch date alignment | Compare batch filenames to OHLCV timestamps | Match |
| LightGBM available | `import lightgbm` | No error |
| Existing backtest works | Run Cell 12 | Completes |

After implementation, validate:

| Check | Method | Target |
|-------|--------|--------|
| No data leakage | Training uses only [0:N-1] for batch N | ✅ Verify in code |
| Win rate improvement | Compare ML-filtered vs baseline | >50% vs 36% |
| Net profitability | PnL after 0.11% fees | Positive |
| Model calibration | Brier score | <0.25 |

---

## 🎯 SUCCESS CRITERIA

| Metric | Baseline (BB+RSI only) | Target (with ML) |
|--------|------------------------|------------------|
| Win Rate | 36% | **>50%** |
| Net PnL/Trade | -0.08% | **>+0.02%** |
| Trades Taken | 4,700 | ~1,500-2,500 (selective) |
| Profitable Configs | 0 | **≥1** |

---

## ▶️ READY TO IMPLEMENT

**Przem, the plan is now:**
1. ✅ Validated all 18 existing cells
2. ✅ Designed 5 new cells (19-23) for ML
3. ✅ All code stays in notebook
4. ✅ Walk-forward training architecture defined

**Next action:** Start implementing Cell 19 (Precomputed Feature Loader)?

# Implementation Plan: Accuracy Improvements

**Goal:** Methodically implement research-backed accuracy improvements without breaking existing functionality.

**Current State:**
- Baseline accuracy: 52%
- Regime-filtered accuracy: 67.5% (vol=0, trend=1)
- Break-even: ~55% with 10bps transaction costs

---

## � PHASE 0: LEAKAGE FIX (CRITICAL - DO FIRST)

### Issue Identified
`y_vol_regime` uses full-dataset quantiles, causing future data leakage.

**Location:** [scripts/analysis/data.py#L163-164](scripts/analysis/data.py#L163-164)
```python
# CURRENT (LEAKAGE!):
vol_25 = df["rolling_vol_21"].quantile(0.25)  # Uses ALL data including future!
vol_75 = df["rolling_vol_21"].quantile(0.75)
```

**Same issue in:**
- [scripts/analysis/run.py#L616-617](scripts/analysis/run.py#L616-617)
- [scripts/analysis/run.py#L811-812](scripts/analysis/run.py#L811-812)
- [scripts/analysis/run.py#L1091](scripts/analysis/run.py#L1091)

### Fix Options Analysis

| Option | Leakage-Free? | Consistent Thresholds? | Production-Ready? |
|--------|---------------|------------------------|-------------------|
| ❌ Current (full quantile) | NO | Yes | Yes |
| ⚠️ Expanding + shift(1) | YES | **No** (varies over time) | Complex |
| ✅ **Fixed historical** | YES | **Yes** | **Yes** |

### Recommended Fix: Fixed Historical Thresholds
```python
# Use first WARMUP_PERIOD bars to establish thresholds
# These thresholds are FIXED and apply to all subsequent rows
WARMUP_PERIOD = 1000  # ~333 days of 8h bars

# Compute thresholds from warmup period ONLY
warmup_vol = df["rolling_vol_21"].head(WARMUP_PERIOD).drop_nulls()
vol_25 = warmup_vol.quantile(0.25)  # Fixed scalar
vol_75 = warmup_vol.quantile(0.75)  # Fixed scalar

# Apply to ALL rows (consistent thresholds)
y_vol_regime = (
    pl.when(df["rolling_vol_21"] < vol_25).then(0)
    .when(df["rolling_vol_21"] < vol_75).then(1)
    .otherwise(2)
)
```

**Why fixed thresholds are better than expanding:**
1. ✅ No future data used (only first 1000 bars)
2. ✅ Consistent interpretation: "LOW vol" means same thing everywhere
3. ✅ Production-ready: Same approach we'd use in live trading
4. ✅ Simpler implementation

### Verification Steps
1. Before fix: Check current accuracy with leaked labels
2. After fix: Re-run backtest, compare metrics
3. Ensure no regressions in other targets (direction, returns, volatility)

**Risk:** LOW (fix is straightforward)
**Impact:** May slightly change regime-filtered results (expected)

---

## �🗺️ Architecture Overview

```
DATA FLOW (Current):
fetchingByBit/            scripts/analysis/data.py      scripts/target_models/
├── OHLCV        →        create_analysis_dataset() →   registry.py
├── funding_rate (UNUSED)         ↓                     ↓
├── open_interest (UNUSED)  y_direction (simple sign)   load_target_data()
└── long_short_ratio (UNUSED)     ↓                     ↓
                          scripts/feature_engineering/  pipeline.py
                          compute_features.py            ↓
                                   ↓                    ensemble.py fit()
                          L1 helpers (HMM, GARCH, etc)      ↓
                                   ↓                    predict_proba()
                          enriched features                 ↓
                                                       fast_backtest.py
```

---

## 📋 Integration Points (File:Line)

### 1. Label Engineering (Triple-Barrier)

**Current location:**
- [scripts/analysis/data.py#L130](scripts/analysis/data.py#L130) - Simple sign labeling:
  ```python
  y_direction = (net_candle_ret_1 > 0).cast(pl.Int8).alias("y_direction")
  ```

**Triple-barrier already exists:**
- [scripts/strategy/exit_manager.py#L128](scripts/strategy/exit_manager.py#L128) - `ExitManager` class
- **Currently only used at backtest time, NOT for training labels**

**Integration approach:**
1. Create `scripts/analysis/triple_barrier_labels.py`
2. Compute triple-barrier outcomes for historical data
3. Add `y_tb_direction` column alongside existing `y_direction`
4. Modify registry.py to optionally load TB labels

**Risk:** LOW - additive change, doesn't modify existing labels

---

### 2. Derivatives Features (Funding Rate, OI, L/S Ratio)

**Data available:**
- `fetchingByBit/funding-rate-bybit-linear/btcusdt_funding_rate.parquet`
  - Columns: `symbol, fundingRate, fundingRateTimestamp, timestamp`
  - Shape: 5438 rows (8h intervals)
  - Date range: 2021-01-01 onwards

- `fetchingByBit/open-interest-8h-bybit-linear/btcusdt_open_interest_8h.parquet`
  - Columns: `timestamp, openInterest`
  - Shape: 5438 rows

- `fetchingByBit/long-short-ratio-8h-bybit-linear/btcusdt_ls_ratio.parquet`
  - Columns: `timestamp_ms, buyRatio, sellRatio, timestamp`
  - Shape: 5002 rows (starts 2021-05-28)

**Current feature engineering:**
- [scripts/feature_engineering/compute_features.py](scripts/feature_engineering/compute_features.py)
- [scripts/analysis/data.py#L67](scripts/analysis/data.py#L67) - `create_analysis_dataset()`

**Integration approach:**
1. Create `scripts/feature_engineering/derivatives_features.py`
2. Load and resample derivatives data to 8h
3. Compute features:
   - `funding_rate_raw` - raw funding rate
   - `funding_rate_ma_3` - 3-period MA
   - `funding_rate_zscore` - z-score over rolling window
   - `oi_change_pct` - OI change %
   - `oi_momentum` - OI momentum (rate of change)
   - `ls_ratio` - buyRatio / sellRatio
   - `ls_ratio_zscore` - z-score
4. Join to main dataset by timestamp
5. Add to feature set in `create_analysis_dataset()`

**Risk:** LOW - additive features, no existing code modified

**Note:** L/S ratio data starts 2021-05-28, need to handle NaN for earlier dates

---

### 3. Sample Weighting (Label Uniqueness)

**Current implementation:**
- [scripts/analysis/data.py#L184](scripts/analysis/data.py#L184) - `compute_sample_weights()` (half-life only)
- NOT USED in training!

**Where training happens:**
- [scripts/target_models/models/ensemble.py#L220](scripts/target_models/models/ensemble.py#L220) - `ModelEnsemble.fit()`
- [scripts/target_models/validation/fast_backtest.py#L512](scripts/target_models/validation/fast_backtest.py#L512)

**Lopez de Prado's approach (AFML Ch. 4):**
1. **Concurrent labels:** Count how many other labels overlap in time
2. **Uniqueness:** `uniqueness[t] = 1 / num_concurrent_labels[t]`
3. **Sample weight:** Combine uniqueness with time decay

**⚠️ CRITICAL: MUST compute per training window, NOT globally!**
```python
# WRONG (leakage): Pre-compute on full dataset
weights = compute_uniqueness(all_data)  # Uses future concurrency info!

# RIGHT (no leakage): Compute per training window in backtest loop
for iteration in walk_forward:
    train_data = data[train_start:train_end]
    weights = compute_uniqueness(train_data)  # Only uses training window
    model.fit(X_train, y_train, sample_weight=weights)
```

**Integration approach:**
1. Create `scripts/analysis/sample_uniqueness.py`
2. Function must accept a SLICE of data, not compute globally
3. Compute label concurrency using triple-barrier touch times
4. Compute uniqueness weights
5. Modify `ModelEnsemble.fit()` to accept `sample_weight` parameter
6. Compute weights INSIDE backtest loop for each training window

**Risk:** MEDIUM - modifies training API, needs careful testing

---

### 4. Meta-Labeling (Secondary Model)

**Concept:** Primary model predicts direction, secondary model predicts "will primary be correct?"

**Dependencies:**
- Requires triple-barrier labels (for clean outcomes)
- Requires trained primary model

**Integration approach:**
1. Create `scripts/target_models/meta_labeling.py`
2. After primary model training:
   - Get primary predictions on validation set
   - Create `y_meta = (primary_correct).astype(int)`
   - Train secondary classifier on same features + primary_prob
3. At inference:
   - Get primary prediction
   - Get meta prediction (confidence that primary is correct)
   - Final signal = primary_direction * meta_confidence

**Risk:** MEDIUM - adds complexity, but isolated to new module

---

### 5. Fractional Differentiation

**Current features:**
- Standard returns (log, pct)
- Standard differencing

**Lopez de Prado's approach (AFML Ch. 5):**
- Use fractional order `d < 1` to maintain memory while achieving stationarity
- `d = 0.5` is common starting point

**Integration approach:**
1. Add `fractional_diff()` to `scripts/feature_engineering/compute_features.py`
2. Apply to price series and volume
3. Add as new features (don't replace existing)

**Risk:** LOW - additive features

---

## 🎯 Implementation Order (Priority Sequence)

| Phase | Item | Expected Impact | Risk | Dependencies |
|-------|------|----------------|------|--------------|
| **0** | **Leakage fix (y_vol_regime)** | **Correctness** | **LOW** | **None** |
| **1** | Derivatives features | +2-5% | LOW | Phase 0 |
| **2** | Triple-barrier labels | +5-10% | LOW | Phase 0 |
| **3** | Sample weighting | +3-5% | MEDIUM | Phase 2 |
| **4** | Meta-labeling | +3-7% | MEDIUM | Phase 2 + trained model |
| **5** | Fractional differentiation | +1-3% | LOW | Phase 0 |

---

## 📋 DETAILED TODO LIST (Step-by-Step)

### ═══════════════════════════════════════════════════════════════
### PHASE 0: LEAKAGE FIX
### ═══════════════════════════════════════════════════════════════

- [ ] **0.1** Record baseline metrics BEFORE fix
  - Run: `python -m scripts.target_models.validation.fast_backtest --config direction_1bar --iterations 50`
  - Document: accuracy, regime distribution, skip rate
  
- [ ] **0.2** Fix `scripts/analysis/data.py` (lines 163-164)
  - Replace full-dataset quantile with expanding quantile
  - Add `min_periods=252` for warmup
  - Add `.shift(1)` to exclude current row
  
- [ ] **0.3** Fix `scripts/analysis/run.py` (lines 616-617)
  - Same pattern as 0.2
  
- [ ] **0.4** Fix `scripts/analysis/run.py` (lines 811-812)
  - Same pattern as 0.2
  
- [ ] **0.5** Fix `scripts/analysis/run.py` (line 1091)
  - Same pattern as 0.2
  
- [ ] **0.6** Regenerate datasets
  - Run: `python -m scripts.analysis.data`
  - Verify: Check y_vol_regime distribution is similar
  
- [ ] **0.7** Run validation backtest AFTER fix
  - Same command as 0.1
  - Compare metrics - expect small changes (not dramatically worse)
  
- [ ] **0.8** Run regime-filtered strategy test
  - Verify regime filtering still works
  - Document any accuracy changes

### ═══════════════════════════════════════════════════════════════
### PHASE 1: DERIVATIVES FEATURES
### ═══════════════════════════════════════════════════════════════

- [ ] **1.1** Verify data alignment
  - Load funding_rate, OI, L/S ratio parquets
  - Check timestamp format matches main dataset
  - Document any gaps or misalignments
  
- [ ] **1.2** Create `scripts/feature_engineering/derivatives_features.py`
  - Function: `load_funding_rate()`
  - Function: `load_open_interest()`
  - Function: `load_long_short_ratio()`
  - Function: `compute_derivatives_features(df)`
  
- [ ] **1.3** Implement funding rate features
  - `F_funding_rate_raw` - raw value
  - `F_funding_rate_ma_3` - 3-period MA
  - `F_funding_rate_zscore_21` - z-score (ROLLING, no leakage!)
  - `F_funding_rate_cumsum_3` - cumulative 3 periods
  
- [ ] **1.4** Implement open interest features
  - `F_oi_change_pct` - period-over-period change
  - `F_oi_momentum_3` - 3-period momentum
  - `F_oi_zscore_21` - z-score (ROLLING)
  
- [ ] **1.5** Implement L/S ratio features
  - `F_ls_ratio` - buyRatio / sellRatio
  - `F_ls_ratio_zscore_21` - z-score (ROLLING)
  - Handle NaN for dates before 2021-05-28
  
- [ ] **1.6** Unit test each feature function
  - Test: No NaN in output (except expected)
  - Test: No future data used (lag correlation test)
  - Test: Values in reasonable range
  
- [ ] **1.7** Integrate into `create_analysis_dataset()`
  - Join by timestamp
  - Add to feature columns
  - Regenerate analysis_8h.parquet
  
- [ ] **1.8** Run backtest with new features
  - Compare accuracy: before vs after
  - Check feature importance ranking
  - Document results

### ═══════════════════════════════════════════════════════════════
### PHASE 2: TRIPLE-BARRIER LABELS
### ═══════════════════════════════════════════════════════════════

- [ ] **2.1** Create `scripts/analysis/triple_barrier_labels.py`
  - Function: `compute_triple_barrier_events(df, tp_mult, sl_mult, max_bars)`
  - Function: `get_barrier_touch(row, df)`
  - Function: `label_from_barrier(touch_type, final_return)`
  
- [ ] **2.2** Implement barrier detection
  - Take-profit barrier: price > entry * (1 + tp)
  - Stop-loss barrier: price < entry * (1 - sl)
  - Time barrier: max_bars reached
  - Track which barrier touched first
  
- [ ] **2.3** Implement labeling logic
  - TP hit → label = 1 (profitable long)
  - SL hit → label = 0 (unprofitable)
  - Time exit → label based on final return sign
  
- [ ] **2.4** Compute labels for historical data
  - Use ATR for dynamic TP/SL (like exit_manager.py)
  - Default: TP=2x ATR, SL=2x ATR, max_bars=3
  
- [ ] **2.5** Add `y_tb_direction` column
  - Alongside existing `y_direction`
  - Save to analysis_8h.parquet
  
- [ ] **2.6** Unit test label generation
  - Manual spot-check: verify labels match expected outcomes
  - Test: Label distribution similar to y_direction
  - Test: No future data in features (labels CAN use future)
  
- [ ] **2.7** Update registry.py (optional)
  - Add `use_triple_barrier: bool = False` flag
  - Allow loading y_tb_direction instead of y_direction
  
- [ ] **2.8** Run backtest with TB labels
  - Compare: y_direction vs y_tb_direction accuracy
  - Document improvement (if any)

### ═══════════════════════════════════════════════════════════════
### PHASE 3: SAMPLE WEIGHTING
### ═══════════════════════════════════════════════════════════════

- [ ] **3.1** Create `scripts/analysis/sample_uniqueness.py`
  - Function: `compute_concurrent_labels(touch_times, horizon)` - takes SLICE, not full data
  - Function: `compute_uniqueness_weights(concurrency)`
  - Function: `combine_with_decay(uniqueness, half_life)`
  - **⚠️ Functions must work on training window only, NOT pre-computed globally**
  
- [ ] **3.2** Implement concurrency calculation (CAUSAL)
  - For each label at time t with span [t, t+horizon]
  - Count overlapping labels WITHIN the training window only
  - At time t, only count concurrent labels from rows < t (expanding within window)
  
- [ ] **3.3** Implement uniqueness weights
  - `uniqueness[t] = 1 / num_concurrent[t]`
  - Normalize to mean=1
  
- [ ] **3.4** Combine with time decay
  - Multiply uniqueness by half-life decay weights
  - Final weight = uniqueness * decay
  
- [ ] **3.5** Modify `ModelEnsemble.fit()` to accept sample_weight
  - Add parameter: `sample_weight: np.ndarray | None = None`
  - Pass to CatBoost: `sample_weight=sample_weight`
  - Pass to LightGBM: `sample_weight=sample_weight`
  
- [ ] **3.6** Modify `fast_backtest.py` to compute weights PER ITERATION
  - **⚠️ Compute weights INSIDE backtest loop, not pre-computed**
  - For each iteration: `weights = compute_uniqueness(train_slice)`
  - Pass to model.fit()
  
- [ ] **3.7** Unit test weight computation
  - Test: Weights sum to n_samples (after normalization)
  - Test: **No future data used (test with synthetic data)**
  - Test: Highly concurrent samples have lower weight
  
- [ ] **3.8** Run backtest with sample weighting
  - Compare: without vs with weighting
  - Document improvement (if any)

### ═══════════════════════════════════════════════════════════════
### PHASE 4: META-LABELING
### ═══════════════════════════════════════════════════════════════

- [ ] **4.1** Create `scripts/target_models/meta_labeling.py`
  - Class: `MetaLabeler`
  - Methods: `fit()`, `predict()`, `predict_proba()`
  
- [ ] **4.2** Implement meta-label generation
  - Input: primary model predictions, actual outcomes
  - Output: y_meta = (prediction == actual).astype(int)
  
- [ ] **4.3** Implement secondary model training
  - Features: original features + primary_probability
  - Target: y_meta (will primary be correct?)
  - Model: Same ensemble (CatBoost + LightGBM)
  
- [ ] **4.4** Implement combined inference
  - Get primary prediction (direction)
  - Get meta prediction (confidence primary is correct)
  - Final signal = direction * meta_confidence
  
- [ ] **4.5** Integrate into backtest flow
  - Train primary → Generate meta labels → Train meta model
  - Predict: primary + meta
  
- [ ] **4.6** Unit test meta-labeler
  - Test: Meta model accuracy > 50% (better than random)
  - Test: Combined signal filters out weak predictions
  
- [ ] **4.7** Run backtest with meta-labeling
  - Compare: primary only vs primary + meta
  - Focus on precision improvement (fewer but better trades)

### ═══════════════════════════════════════════════════════════════
### PHASE 5: FRACTIONAL DIFFERENTIATION
### ═══════════════════════════════════════════════════════════════

- [ ] **5.1** Implement `fractional_diff()` function
  - Location: `scripts/feature_engineering/compute_features.py`
  - Algorithm: FFD (Fixed-width window Fracdiff)
  - Parameter: `d` (differentiation order, typically 0.3-0.7)
  
- [ ] **5.2** Find optimal `d` for stationarity
  - Run ADF test for various d values
  - Find minimum d where ADF p-value < 0.05
  
- [ ] **5.3** Apply to price series
  - `M_close_fracdiff_d` - fractionally differenced close
  - `M_volume_fracdiff_d` - fractionally differenced volume
  
- [ ] **5.4** Unit test fractional diff
  - Test: Output is more stationary than input (ADF test)
  - Test: Memory preserved (autocorrelation structure)
  - Test: No future data used
  
- [ ] **5.5** Add to feature set
  - Integrate into compute_features.py
  - Regenerate features
  
- [ ] **5.6** Run backtest with fracdiff features
  - Compare: without vs with fracdiff
  - Document improvement (if any)

---

## 🧪 Testing Strategy

### For Each Change:

1. **Unit test:** New function works in isolation
2. **Integration test:** Joins correctly with existing data
3. **Regression test:** Existing pipeline still works
4. **Performance test:** Compare accuracy before/after on same holdout

### Holdout Protocol:

- Use SAME holdout period for all comparisons
- Never touch 2024-07+ data until final evaluation
- Compare: accuracy, Sharpe, max drawdown

---

## 🔒 Rollback Plan

Each phase creates new files/columns. If issues arise:
1. Simply don't use new columns/files
2. Registry defaults to original `y_direction`
3. No existing code paths modified until proven

---

## 📁 New Files to Create

```
scripts/
├── analysis/
│   ├── triple_barrier_labels.py  # Phase 2
│   └── sample_uniqueness.py      # Phase 3
├── feature_engineering/
│   └── derivatives_features.py   # Phase 1
└── target_models/
    └── meta_labeling.py          # Phase 4
```

---

## ✅ Pre-Implementation Checklist

- [ ] Verify derivatives data timestamps align with main dataset
- [ ] Check for gaps in derivatives data
- [ ] Confirm triple-barrier exit_manager.py can be adapted for labeling
- [ ] Document current accuracy metrics for comparison baseline
- [ ] **FIX LEAKAGE FIRST (Phase 0)**

---

## 📊 Success Metrics

| Metric | Current | After P0 | After P1-2 | Target |
|--------|---------|----------|------------|--------|
| Baseline accuracy | 52% | ~52%* | 55%+ | 58% |
| Regime-filtered accuracy | 67.5% | ~65%* | 70%+ | 75% |
| Sharpe ratio | TBD | TBD | +0.2 | +0.5 |

*Phase 0 may slightly reduce metrics (removing leaked future info)

---

## 🔄 Progress Tracking

### Phase 0: Leakage Fix
- [ ] Started
- [ ] Baseline recorded
- [ ] Code fixed
- [ ] Datasets regenerated
- [ ] Verified
- [ ] **COMPLETE**

### Phase 1: Derivatives Features
- [ ] Started
- [ ] Data aligned
- [ ] Features implemented
- [ ] Tests pass
- [ ] Backtest run
- [ ] **COMPLETE**

### Phase 2: Triple-Barrier Labels
- [ ] Started
- [ ] Labels computed
- [ ] Tests pass
- [ ] Backtest run
- [ ] **COMPLETE**

### Phase 3: Sample Weighting
- [ ] Started
- [ ] Weights computed
- [ ] Ensemble modified
- [ ] Tests pass
- [ ] Backtest run
- [ ] **COMPLETE**

### Phase 4: Meta-Labeling
- [ ] Started
- [ ] Meta-labeler built
- [ ] Tests pass
- [ ] Backtest run
- [ ] **COMPLETE**

### Phase 5: Fractional Differentiation
- [ ] Started
- [ ] Optimal d found
- [ ] Features added
- [ ] Tests pass
- [ ] Backtest run
- [ ] **COMPLETE**

---

*Document created: Methodical implementation plan for accuracy improvements*
*Based on: Academic research review (docs/ACCURACY_IMPROVEMENT_RESEARCH.md)*

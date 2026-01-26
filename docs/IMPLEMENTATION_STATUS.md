# Implementation Status & Next Steps

## Executive Summary

Based on comprehensive code review, here's what's **DONE** vs **TODO**:

| Phase | Component | Status | Notes |
|-------|-----------|--------|-------|
| **0** | Leakage Fix (y_vol_regime) | ✅ **DONE** | Uses WARMUP_PERIOD=1000 |
| **1** | Derivatives Features | ✅ **DONE** | 29 features (funding, OI, L/S) |
| **2** | Triple-Barrier Labels | ❌ **TODO** | ExitManager exists, need labeling |
| **3** | Sample Weighting | ⚠️ **PARTIAL** | Decay exists, uniqueness missing |
| **4** | Meta-Labeling | ❌ **TODO** | New module needed |
| **5** | Fractional Differentiation | ❌ **TODO** | Add to compute_features.py |

---

## ✅ Phase 0: Leakage Fix - COMPLETE

**Files Fixed:**
- [scripts/analysis/data.py](scripts/analysis/data.py#L163-L167) - Uses WARMUP_PERIOD=1000
- [scripts/analysis/run.py](scripts/analysis/run.py#L578-L581) - Line 578
- [scripts/analysis/run.py](scripts/analysis/run.py#L776-L779) - Line 776
- [scripts/analysis/run.py](scripts/analysis/run.py#L1059-L1062) - Line 1059

**Verification:**
```python
# data.py line 163-167
WARMUP_PERIOD = 1000
warmup_vol = df["rolling_vol_21"].head(WARMUP_PERIOD).drop_nulls()
vol_25 = warmup_vol.quantile(0.25)
vol_75 = warmup_vol.quantile(0.75)
```

---

## ✅ Phase 1: Derivatives Features - COMPLETE

**Already computed in `features_8h.parquet`:**

| Category | Count | Examples |
|----------|-------|----------|
| Funding | 12 | F_I_fundingCumulative_*, F_I_N_S_fundingZscore_* |
| OI | 12 | L_M_N_S_oiPctChange, L_N_volOiRatio, L_M_N_S_oiRoc_* |
| L/S Ratio | 5 | S_longShortRatio, S_N_longShortZscore_*, S_M_longShortChange_* |

**Location:** [scripts/feature_engineering/compute_features.py](scripts/feature_engineering/compute_features.py)
- Lines 243-270: Funding features
- Lines 313-340: OI features  
- Lines 958-990: L/S ratio features

**No action needed.**

---

## ❌ Phase 2: Triple-Barrier Labels - TODO

### Current State
- `y_direction` uses simple sign: `(net_candle_ret > 0)`
- `ExitManager` class EXISTS but only for backtest exits, NOT for training labels

### What Needs to Be Done

#### 2.1 Create: `scripts/analysis/triple_barrier_labels.py`

```python
"""
Triple-Barrier Labels for Training

López de Prado's triple-barrier method applied to historical data
to create cleaner training labels than simple sign(return).
"""

import numpy as np
import pandas as pd
import polars as pl


def compute_triple_barrier_labels(
    df: pl.DataFrame,
    tp_mult: float = 2.0,    # TP = tp_mult × ATR
    sl_mult: float = 2.0,    # SL = sl_mult × ATR  
    max_bars: int = 3,       # Time barrier
    atr_window: int = 21,    # ATR lookback
) -> pl.DataFrame:
    """
    Compute triple-barrier labels for historical data.
    
    Label logic:
    - 1 (profitable): TP hit first
    - 0 (unprofitable): SL hit first
    - Based on sign(final_return) if time barrier hit
    
    Args:
        df: DataFrame with columns [timestamp, open, high, low, close]
        tp_mult: ATR multiplier for take profit
        sl_mult: ATR multiplier for stop loss
        max_bars: Maximum holding period (time barrier)
        atr_window: Window for ATR calculation
        
    Returns:
        DataFrame with added column: y_tb_direction
    """
    # Implementation needed
    pass


def get_first_barrier_touch(
    entry_price: float,
    tp_price: float,
    sl_price: float,
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    max_bars: int,
) -> tuple[str, int, float]:
    """
    Determine which barrier is touched first.
    
    Returns:
        (barrier_type, bars_to_touch, exit_price)
        barrier_type: 'TP', 'SL', or 'TIME'
    """
    # Implementation needed
    pass
```

#### 2.2 Modify: `scripts/analysis/data.py`

Add call to compute_triple_barrier_labels() after existing target computation:

```python
# After line ~180 (after y_vol_regime)
from scripts.analysis.triple_barrier_labels import compute_triple_barrier_labels

# Compute triple-barrier labels
df = compute_triple_barrier_labels(
    df, 
    tp_mult=2.0, 
    sl_mult=2.0, 
    max_bars=3
)
```

#### 2.3 Update Target Columns

Add `y_tb_direction` to the saved parquet alongside existing `y_direction`.

---

## ⚠️ Phase 3: Sample Weighting - PARTIAL

### Current State

**Recency-based decay: IMPLEMENTED**
- Location: [l2_backtest_sync.py#L679](scripts/target_models/validation/l2_backtest_sync.py#L679)
- `_compute_sample_weights()` with exponential halflife decay
- Applied to CatBoost, LightGBM, Linear models

**Uniqueness-based weighting: NOT IMPLEMENTED**
- López de Prado's AFML Ch.4 approach counts label overlap
- Not the same as recency decay

### Decision Point

**Option A: Keep current recency decay (recommended for now)**
- Already working, tuned
- Addresses concept drift
- No additional complexity

**Option B: Add uniqueness weighting**
- Create `scripts/analysis/sample_uniqueness.py`
- Compute label overlap within training window
- Combine with recency decay
- Risk: May conflict with existing weighting

**Recommendation:** Defer uniqueness weighting until triple-barrier labels are implemented (they define label spans).

---

## ❌ Phase 4: Meta-Labeling - TODO

### What Needs to Be Done

#### 4.1 Create: `scripts/target_models/meta_labeling.py`

```python
"""
Meta-Labeling: Secondary Model for Signal Confidence

From López de Prado's AFML Ch. 3:
- Primary model predicts direction
- Secondary model predicts "will primary be correct?"
- Final signal = direction × meta_confidence
"""

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier


class MetaLabeler:
    """
    Meta-labeling for signal quality filtering.
    
    Architecture:
    1. Primary model: direction prediction
    2. Meta model: confidence prediction (will primary be correct?)
    3. Final: trade only when meta_confidence > threshold
    """
    
    def __init__(
        self,
        primary_model=None,
        meta_threshold: float = 0.5,
    ):
        self.primary = primary_model
        self.meta_threshold = meta_threshold
        self.meta_model = None
        
    def fit_meta(
        self,
        X: pd.DataFrame,
        y_true: np.ndarray,
        y_primary_pred: np.ndarray,
    ):
        """
        Train meta-model to predict primary model correctness.
        
        Args:
            X: Features
            y_true: Actual outcomes
            y_primary_pred: Primary model predictions
        """
        # Meta-label: 1 if primary was correct, 0 if wrong
        y_meta = (y_primary_pred == y_true).astype(int)
        
        # Features for meta-model: original features + primary probability
        # Implementation needed
        pass
        
    def predict_with_meta(self, X: pd.DataFrame) -> dict:
        """
        Get predictions filtered by meta-confidence.
        
        Returns:
            dict with keys: direction, meta_confidence, trade_signal
        """
        # Implementation needed
        pass
```

#### 4.2 Integration Points

- Modify `l2_backtest_sync.py` to optionally use MetaLabeler
- Add config flag: `use_meta_labeling: bool = False`
- After primary model trains, train meta-model on validation set

---

## ❌ Phase 5: Fractional Differentiation - TODO

### What Needs to Be Done

#### 5.1 Add to: `scripts/feature_engineering/compute_features.py`

```python
def compute_fractional_diff(
    series: pd.Series,
    d: float = 0.5,
    window: int = 100,
    threshold: float = 1e-5,
) -> pd.Series:
    """
    Fixed-width window Fractional Differentiation (FFD).
    
    From López de Prado AFML Ch. 5:
    - Preserves memory while achieving stationarity
    - d=0 is original series, d=1 is standard diff
    - d=0.3-0.7 typically optimal for financial series
    
    Args:
        series: Input price/volume series
        d: Differentiation order (0 < d < 1)
        window: Fixed lookback window
        threshold: Weight cutoff for efficiency
        
    Returns:
        Fractionally differenced series
    """
    # Compute weights using binomial expansion
    # w_k = (-1)^k × Γ(d+1) / (Γ(k+1) × Γ(d-k+1))
    
    # Implementation needed - see AFML Ch. 5
    pass
```

#### 5.2 Add Features

```python
# In compute_all_features():

# Fractional differentiation (AFML Ch. 5)
for d in [0.3, 0.5, 0.7]:
    features[f"M_P_close_fracdiff_{d}_pct_N"] = compute_fractional_diff(
        df["close"], d=d, window=100
    )
```

---

## Files to Create

| File | Phase | Lines (est.) | Priority |
|------|-------|--------------|----------|
| `scripts/analysis/triple_barrier_labels.py` | 2 | ~150 | HIGH |
| `scripts/target_models/meta_labeling.py` | 4 | ~200 | MEDIUM |
| `scripts/analysis/sample_uniqueness.py` | 3 | ~100 | LOW |

---

## Files to Modify

| File | Phase | Changes | Priority |
|------|-------|---------|----------|
| `scripts/analysis/data.py` | 2 | Add TB label computation | HIGH |
| `scripts/feature_engineering/compute_features.py` | 5 | Add fracdiff functions | LOW |
| `scripts/target_models/validation/l2_backtest_sync.py` | 4 | Optional meta-labeling | MEDIUM |

---

## Implementation Order (Recommended)

### Week 1: Triple-Barrier Labels
1. Create `triple_barrier_labels.py`
2. Test with historical data
3. Add `y_tb_direction` to analysis_8h.parquet
4. Compare backtest: `y_direction` vs `y_tb_direction`

### Week 2: Fractional Differentiation  
1. Implement `compute_fractional_diff()`
2. Find optimal `d` (ADF test)
3. Add 3-6 new features
4. Regenerate features_8h.parquet
5. Run backtest comparison

### Week 3: Meta-Labeling (if above show improvement)
1. Create `meta_labeling.py`
2. Test on validation data
3. Integrate into backtest
4. Evaluate precision/recall tradeoff

---

## Quick Start: Test Current Setup

Before implementing new features, verify baseline:

```bash
# Run backtest on direction_1bar (quick test)
cd "/media/przem/linux_data/RiskYieldMM (Copy)"
python -c "
from scripts.target_models.validation.l2_backtest_sync import (
    run_sync_backtest, SyncBacktestConfig
)

config = SyncBacktestConfig(
    step_size=50,  # Quick test
    enable_optuna=False,
    verbose=True,
)

results = run_sync_backtest(
    configs=['direction_1bar'],
    config=config,
)
"
```

---

## Key Dependencies

```
ExitManager (exists) → Triple-Barrier Labels (create)
                            ↓
                    y_tb_direction column
                            ↓
                    Sample Uniqueness (optional)
                            ↓
                    Meta-Labeling (create)
```

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| 2 (TB Labels) | LOW | Additive column, doesn't break existing |
| 3 (Uniqueness) | MEDIUM | May conflict with recency weights |
| 4 (Meta-Label) | MEDIUM | Adds complexity, isolated module |
| 5 (Fracdiff) | LOW | Additive features only |

---

*Document created: 2026-01-16*
*Based on: Full codebase review*

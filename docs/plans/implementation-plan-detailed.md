# RiskYieldMM Enhancement Implementation Plan

## Overview

Systematic implementation of 3 remaining AFML-based improvements:
1. **Phase 2**: Triple-Barrier Labels (HIGH priority)
2. **Phase 5**: Fractional Differentiation (MEDIUM priority)  
3. **Phase 4**: Meta-Labeling (LOW priority)

**Order rationale:**
- Phase 2 before 4: Meta-labeling needs TB labels as input
- Phase 5 independent: Can be done in parallel
- Phase 4 last: Highest complexity, needs verified components

---

## Module Organization

### Current Structure (Relevant)

```
scripts/
├── analysis/                    # Target generation & analysis
│   ├── data.py                 # Creates analysis_8h.parquet with targets
│   ├── run.py                  # CLI for dataset building
│   └── [NEW] triple_barrier_labels.py
│
├── feature_engineering/         # Feature computation
│   ├── compute_features.py     # 166 features
│   └── [NEW] fracdiff.py       # Fractional differentiation
│
├── strategy/                    # Strategy components
│   └── exit_manager.py         # REUSE: ExitManager has TB logic
│
└── target_models/               # Model infrastructure
    ├── [NEW] meta_labeling.py  # Secondary confidence model
    └── validation/
        └── l2_backtest_sync.py # Integration point for meta-labeling
```

### Data Flow (After Implementation)

```
┌──────────────────────────────────────────────────────────────────┐
│                         DATA PIPELINE                            │
└──────────────────────────────────────────────────────────────────┘

Step 1a: merge_all_sources()
         └─> merged_8h_raw.parquet

Step 1b: compute_all_features()
         └─> features_8h.parquet
             └─> INCLUDES: fracdiff features (NEW Phase 5)

Step 2: create_analysis_dataset()
        └─> analysis_8h.parquet
            ├─> y_direction (existing)
            ├─> y_tb_direction (NEW Phase 2)  ◄── Triple-Barrier
            ├─> y_vol_regime, y_trend_regime (existing)
            └─> y_forward_return_* (existing)

Step 3-4: Optimization & Dataset building
          └─> data/datasets/{target}_{horizon}.parquet

Step 8-9: L1 precompute & assembly
          └─> data/precomputed/{config}/assembled.parquet

L2 Backtest: run_sync_backtest()
             └─> Optional meta-labeling (NEW Phase 4)
```

---

## Phase 2: Triple-Barrier Labels

### 2.1 Create Module

**File:** `scripts/analysis/triple_barrier_labels.py`

**Dependencies:**
- polars (for DataFrame ops)
- numpy (for array math)
- Existing ExitManager (for barrier logic reference)

**Module structure:**

```python
"""
Triple-Barrier Labels for Training (AFML Ch.3)

Creates y_tb_direction column using:
- Take profit barrier: entry + tp_mult × ATR
- Stop loss barrier: entry - sl_mult × ATR
- Time barrier: max_bars forward

Label = 1 if TP hit first, 0 if SL hit first, sign(return) if time barrier
"""

__all__ = ["compute_triple_barrier_labels", "get_barrier_touch"]


def compute_triple_barrier_labels(
    df: pl.DataFrame,
    tp_mult: float = 2.0,
    sl_mult: float = 2.0,
    max_bars: int = 3,
    atr_col: str = "atr_21",
    price_col: str = "close",
) -> pl.DataFrame:
    """
    Compute TB labels for entire dataset.
    
    Returns df with new column: y_tb_direction (0 or 1)
    """
    ...


def get_barrier_touch(
    entry_price: float,
    tp_price: float,
    sl_price: float,
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    future_closes: np.ndarray,
    max_bars: int,
) -> tuple[str, int, float]:
    """
    Vectorized barrier touch detection for a single entry.
    
    Returns:
        (barrier_type, bars_to_touch, exit_price)
        barrier_type: 'TP', 'SL', or 'TIME'
    """
    ...
```

### 2.2 Integration Point

**File:** `scripts/analysis/data.py`

**Location:** After line ~180 (after vol_regime computation)

```python
# --- Triple-Barrier Labels (AFML Ch.3) ---
from scripts.analysis.triple_barrier_labels import compute_triple_barrier_labels

df = compute_triple_barrier_labels(
    df,
    tp_mult=2.0,      # TP = 2 × ATR
    sl_mult=2.0,      # SL = 2 × ATR
    max_bars=3,       # 3 bars = 24h
    atr_col="atr_21", # Use existing ATR
)
```

### 2.3 main_wf.py Changes

**File:** `notebooks/main_wf.py`

**Step 2 verification cell - add TB stats:**

```python
# Triple-barrier label distribution
tb_col = "y_tb_direction"
if tb_col in df_check.columns:
    tb_dist = df_check[tb_col].value_counts().sort("y_tb_direction")
    print(f"\n✓ Triple-Barrier Labels (y_tb_direction):")
    for row in tb_dist.iter_rows():
        pct = 100 * row[1] / len(df_check)
        print(f"    {row[0]}: {row[1]:,} ({pct:.1f}%)")
```

### 2.4 Verification Checklist

```
[ ] Module imports without errors
[ ] Labels computed for full dataset
[ ] NaN count acceptable (<5% of rows)
[ ] Distribution reasonable (40-60% class balance)
[ ] Compare y_tb_direction vs y_direction correlation
```

---

## Phase 5: Fractional Differentiation

### 5.1 Create Module

**File:** `scripts/feature_engineering/fracdiff.py`

**Implementation (AFML Ch.5):**

```python
"""
Fractional Differentiation (AFML Ch.5)

FFD (Fixed-Width Window) method that preserves memory while
achieving stationarity. Key for price series transformation.
"""

import numpy as np
import pandas as pd


def get_ffd_weights(d: float, threshold: float, max_window: int) -> np.ndarray:
    """
    Compute FFD weights using binomial expansion.
    
    w[k] = (-1)^k × prod_{i=0}^{k-1}(d-i) / k!
    
    Stop when |w[k]| < threshold
    """
    ...


def compute_ffd(
    series: pd.Series | np.ndarray,
    d: float,
    threshold: float = 1e-5,
    max_window: int = 100,
) -> np.ndarray:
    """
    Apply Fixed-Width Window Fractional Differentiation.
    
    Args:
        series: Price or volume series
        d: Differentiation order (0 < d < 1, typically 0.3-0.7)
        threshold: Weight cutoff for efficiency
        max_window: Maximum lookback
        
    Returns:
        Fractionally differenced series (same length, NaN padded)
    """
    ...


def find_optimal_d(
    series: pd.Series,
    min_d: float = 0.1,
    max_d: float = 1.0,
    step: float = 0.1,
    p_value: float = 0.05,
) -> float:
    """
    Find minimum d that achieves stationarity (ADF test).
    
    Returns:
        Optimal d value
    """
    from statsmodels.tsa.stattools import adfuller
    ...
```

### 5.2 Integration Point

**File:** `scripts/feature_engineering/compute_features.py`

**Location:** After momentum features section (~line 450)

```python
# =============================================================================
# FRACTIONAL DIFFERENTIATION (AFML Ch.5)
# =============================================================================
from scripts.feature_engineering.fracdiff import compute_ffd

# Fracdiff features for close price
for d in [0.3, 0.5, 0.7]:
    features[f"M_P_close_fracdiff_{d}_pct_N"] = compute_ffd(
        df["close"], d=d, max_window=100
    )

# Fracdiff for volume (optional)
features["L_V_volume_fracdiff_0.5_N"] = compute_ffd(
    df["volume"], d=0.5, max_window=100
)
```

### 5.3 main_wf.py Changes

**Step 1b verification - add fracdiff check:**

```python
# Verify fracdiff features
fracdiff_cols = [c for c in features.columns if "fracdiff" in c]
print(f"\n✓ Fracdiff features: {len(fracdiff_cols)}")
for col in fracdiff_cols[:3]:
    print(f"    {col}: range [{features[col].min():.4f}, {features[col].max():.4f}]")
```

### 5.4 Verification Checklist

```
[ ] FFD weights decay properly (plot to verify)
[ ] ADF test passes for d >= 0.3
[ ] Features correlate with original (r > 0.5)
[ ] No NaN explosion (only warmup period)
[ ] IC comparable to standard returns
```

---

## Phase 4: Meta-Labeling

### 4.1 Create Module

**File:** `scripts/target_models/meta_labeling.py`

```python
"""
Meta-Labeling: Secondary Model for Signal Confidence (AFML Ch.3)

Architecture:
1. Primary model predicts direction
2. Meta-model predicts: "Will primary be correct?"
3. Trade only when meta_confidence > threshold

This improves precision by filtering low-confidence signals.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier


@dataclass
class MetaLabelConfig:
    """Configuration for meta-labeling."""
    threshold: float = 0.5         # Min confidence to trade
    min_samples: int = 100         # Min samples for meta training
    use_primary_proba: bool = True # Include primary's probability as feature


class MetaLabeler:
    """
    Meta-labeling model for signal quality assessment.
    
    Usage:
        meta = MetaLabeler(config)
        meta.fit(X_train, y_true, primary_preds, primary_proba)
        meta_conf = meta.predict_confidence(X_test, primary_preds_test)
        trade_mask = meta_conf > config.threshold
    """
    
    def __init__(self, config: MetaLabelConfig = None):
        self.config = config or MetaLabelConfig()
        self.model = None
        self._fitted = False
        
    def fit(
        self,
        X: pd.DataFrame,
        y_true: np.ndarray,
        primary_pred: np.ndarray,
        primary_proba: np.ndarray | None = None,
    ) -> "MetaLabeler":
        """
        Train meta-model on primary model's correctness.
        
        Meta-label = 1 if primary was correct, 0 if wrong.
        """
        ...
        
    def predict_confidence(
        self,
        X: pd.DataFrame,
        primary_pred: np.ndarray,
        primary_proba: np.ndarray | None = None,
    ) -> np.ndarray:
        """
        Predict probability that primary prediction is correct.
        
        Returns:
            Array of confidence scores [0, 1]
        """
        ...
```

### 4.2 Integration Point

**File:** `scripts/target_models/validation/l2_backtest_sync.py`

**Config addition:**

```python
@dataclass
class SyncBacktestConfig:
    # ... existing fields ...
    
    # Meta-labeling (Phase 4)
    use_meta_labeling: bool = False
    meta_threshold: float = 0.5
```

**Integration in `_train_predict_classification()`:**

```python
if self.config.use_meta_labeling and has_enough_samples:
    # Train meta-model on validation correctness
    from scripts.target_models.meta_labeling import MetaLabeler
    
    meta = MetaLabeler()
    meta.fit(X_val, y_val, primary_preds_val, primary_proba_val)
    
    # Get confidence for prediction row
    meta_conf = meta.predict_confidence(X_pred, primary_pred, primary_proba)
    
    # Store in results
    row["meta_confidence"] = float(meta_conf)
    row["trade_signal"] = int(meta_conf > self.config.meta_threshold)
```

### 4.3 main_wf.py Changes

Add optional Step 10 for meta-labeling verification:

```python
# %% [markdown]
# # Step 10 (Optional): Meta-Labeling Analysis
#
# Analyze meta-labeling impact on direction predictions.

# %%
# Step 10: Meta-labeling evaluation
from scripts.target_models.validation.l2_backtest_sync import (
    run_sync_backtest, SyncBacktestConfig
)

config = SyncBacktestConfig(
    step_size=10,  # Quick test
    use_meta_labeling=True,
    meta_threshold=0.5,
)

results = run_sync_backtest(
    configs=['direction_1bar'],
    config=config,
)

# Compare with/without meta-labeling
print("Meta-labeling impact:")
print(f"  Trades taken: {results['trade_rate']:.1%}")
print(f"  Accuracy on taken: {results['meta_accuracy']:.1%}")
```

### 4.4 Verification Checklist

```
[ ] Meta-model trains without errors
[ ] Confidence scores distributed [0.4, 0.7] typically
[ ] Higher threshold → fewer trades, higher accuracy
[ ] Trade rate 30-70% (not all filtered)
[ ] Precision improves vs baseline
```

---

## Dependency Graph

```
                          ┌─────────────────────┐
                          │  merged_8h_raw.parquet │
                          └──────────┬──────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  Step 1b: compute_all_features()                                 │
│  ├── Existing 166 features                                       │
│  └── [Phase 5] Fracdiff features (+4 features)                  │
└──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  Step 2: create_analysis_dataset()                               │
│  ├── y_direction (existing)                                      │
│  ├── [Phase 2] y_tb_direction (NEW)                             │
│  └── Other targets (existing)                                    │
└──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  Steps 3-9: Optimization → Datasets → L1 → Assembly             │
│  (No changes needed for Phase 2, 5)                              │
└──────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  L2 Backtest: run_sync_backtest()                                │
│  └── [Phase 4] Optional meta-labeling                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## Implementation Sequence

### Day 1-2: Triple-Barrier Labels (Phase 2)

| Task | File | Est. Time |
|------|------|-----------|
| 2.1 Create triple_barrier_labels.py | scripts/analysis/ | 2h |
| 2.2 Add unit tests | tests/test_tb_labels.py | 1h |
| 2.3 Integrate in data.py | scripts/analysis/data.py | 30m |
| 2.4 Add to main_wf.py Step 2 | notebooks/main_wf.py | 30m |
| 2.5 Verify & document | - | 1h |

**Deliverable:** `y_tb_direction` column in analysis_8h.parquet

### Day 3-4: Fractional Differentiation (Phase 5)

| Task | File | Est. Time |
|------|------|-----------|
| 5.1 Create fracdiff.py | scripts/feature_engineering/ | 2h |
| 5.2 Add unit tests | tests/test_fracdiff.py | 1h |
| 5.3 Integrate in compute_features.py | scripts/feature_engineering/ | 30m |
| 5.4 Add to main_wf.py Step 1b | notebooks/main_wf.py | 30m |
| 5.5 Verify stationarity | - | 1h |

**Deliverable:** 4 fracdiff features in features_8h.parquet

### Day 5-7: Meta-Labeling (Phase 4)

| Task | File | Est. Time |
|------|------|-----------|
| 4.1 Create meta_labeling.py | scripts/target_models/ | 3h |
| 4.2 Add unit tests | tests/test_meta_labeling.py | 1h |
| 4.3 Integrate in l2_backtest_sync.py | scripts/target_models/validation/ | 2h |
| 4.4 Add to main_wf.py | notebooks/main_wf.py | 30m |
| 4.5 Tune threshold | - | 2h |

**Deliverable:** Optional meta-labeling in backtest with tuned threshold

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| TB labels all same class | Check ATR validity, tune multipliers |
| Fracdiff NaN explosion | Use bounded window, pad properly |
| Meta-model overfits | Use separate val set, regularize |
| Integration breaks pipeline | Run full regression test after each phase |

---

## Testing Strategy

### Unit Tests (per module)

```bash
# After each phase
pytest tests/test_{module}.py -v
```

### Integration Test (full pipeline)

```bash
# After all phases
python notebooks/main_wf.py  # Run Steps 1-9
python -c "
from scripts.target_models.validation.l2_backtest_sync import run_sync_backtest
run_sync_backtest(configs=['direction_1bar'], step_size=50)
"
```

### Regression Test (no performance degradation)

```bash
# Compare baseline vs new
python scripts/target_models/run_full_eval.py --quick
```

---

*Created: 2026-01-16*
*Status: Ready for implementation*

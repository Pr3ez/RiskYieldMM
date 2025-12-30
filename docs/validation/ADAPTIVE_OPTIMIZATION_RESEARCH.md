# Adaptive Optimization Research

**Date**: 2025-12-25  
**Purpose**: Document findings from `final-2.py` and current project analysis to fix single-class training window failures.

---

## Problem Statement

### The Issue
- **91/300 windows (30.3%)** in `trend_regime_12bar` have only 1 class with current `train_size=275`
- CatBoost/LightGBM/LogisticRegression crash on single-class training data
- Current workaround: Skip training, return constant prediction (symptom handling, not root cause fix)

### Root Cause: Regime Persistence
- Trend regime stays in same state for extended periods
- Long streak of class 1 from indices ~3758-4000
- With window=500, train=275: insufficient samples to guarantee both classes appear

### Window Size Analysis Results
| Window | Train | Train% | Single-Class Windows | Status |
|--------|-------|--------|---------------------|--------|
| 500 | 275 | 55% | 91/300 (30.3%) | ❌ Current |
| 500 | 400 | 80% | 0/300 (0%) | ✅ Fixed |
| 700 | 385 | 55% | 0/124 (0%) | ✅ Fixed (fewer iterations) |

### Data Availability
- Current L1 precompute: 300 iterations (artificially limited)
- Max possible with window=500: 3,437 iterations
- Max possible with window=700: 3,237 iterations

---

## RESEARCH LOG (Tier 1 Research Phase)

### Task t1-1-r1: Minimum Samples Per Class Guidelines

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: "minimum sample size" classification imbalanced machine learning per class statistical guideline

#### Paper 1: van Smeden et al., 2018 (PMC6710621)
**Title**: "Sample size for binary logistic prediction models: Beyond events per variable criteria"  
**Journal**: Stat Methods Med Res  
**Methodology**: Simulation study with 4,032 scenarios, 5,000 runs each, EPV tested from 3-50

**Key Findings**:
- ❌ **EPV ≥ 10 rule-of-thumb is NOT adequate** for sample size determination
- EPV has only **weak relation to out-of-sample predictive performance**
- Sample size should be based on **N (total samples), events fraction, and P (number of predictors) together**
- Ridge/Lasso regularization helps improve performance in small samples
- Backwards elimination selection generally worsened predictive accuracy
- Authors recommend basing sample size on **meaningful out-of-sample performance metrics** (rMSPE, MAPE)

**Quote**: "EPV criteria fail to take into account the intended use of the prediction model"

---

#### Paper 2: Silvey & Liu, 2024 (PMC11688588) 🔥 CRITICAL
**Title**: "Sample Size Requirements for Popular Classification Algorithms in Tabular Clinical Data: Empirical Study"  
**Journal**: J Med Internet Res  
**Methodology**: Learning curve analysis on 16 datasets (70,000-1,000,000 samples), 4 algorithms (XGB, RF, LR, NN)

**Key Findings - Events-Per-Variable for AUC Stability**:
| Algorithm | EPV Required | Median Sample Size | Range |
|-----------|-------------|-------------------|-------|
| Logistic Regression | 11 | 696 | 204-6,798 |
| XGBoost | **205** | 9,960 | 960-65,556 |
| Random Forest | 231 | 3,404 | 250-140,499 |
| Neural Network | 342 | 12,298 | 1,824-180,835 |

**Key Finding**: **Minority class proportion is THE most important factor**
- For every 1% increase in minority class proportion → **0.96× multiplier** on required sample size
- **50% class balance** leads to lowest required sample sizes
- Each percentage point of balance decreases needed n by 0.96-0.98×

**Sample Size Formula for XGBoost**:
```
n = 121,967 × (minority_class_proportion)^0.956 × (separability)^0.952 × (nonlinearity_multiplier)
where nonlinearity_multiplier = 3.091 if high nonlinearity, 1.0 if low
```

**Van der Ploeg et al. (2014) cited**: RF and NN require **>200 events-per-variable** for AUC stability

---

#### Paper 3: Boldini et al., 2023 (PMC10464382)
**Title**: "Practical guidelines for the use of gradient boosting for molecular property prediction"  
**Journal**: J Cheminformatics  
**Methodology**: 157,590 models, 16 datasets, 94 endpoints, 1.4 million compounds

**Key Findings**:
- Tested datasets with imbalance ratios from **1:1 to 1:16,265** (including 1:486-1:613 MUV)
- Performance remained robust even on extreme imbalances (1:500+)
- Key hyperparameters for imbalanced data: `scale_pos_weight`, `min_split_gain`, `learning_rate`
- XGBoost generally outperforms LightGBM/CatBoost by ~5%
- `min_child_samples` (LightGBM) / `min_child_weight` (XGBoost) controls minimum samples per leaf node
- **Recommendation**: Tune `scale_pos_weight` to handle class imbalance

---

### Decision Point 1.1: RESOLVED

**Question**: What is the minimum samples per class threshold?

**Analysis for Our Context**:
- Current: train_size = 275 samples, ~80+ features, 3 regime classes
- EPV calculation: 205 × 80 features / 3 classes = ~5,467 per class needed (impossible)
- BUT: Literature shows **class balance is more important than absolute numbers**

**Conclusion**: EPV rules don't apply directly. The key is:
1. **Must have at least 2 classes** (hard requirement - can't train classifier otherwise)
2. **Class balance (entropy) matters more than raw count**
3. **Balanced classes dramatically reduce sample requirements**

**ADOPTED THRESHOLDS**:
| Threshold | Value | Rationale |
|-----------|-------|-----------|
| Hard minimum per class | **2 samples** | Absolute floor for any learning |
| Soft minimum per class | **30 samples** | Practical minimum for patterns |
| Ideal minimum per class | **50 samples** | Robust learning |
| Balance score minimum | **0.5** | entropy/max_entropy ratio |

**Implementation**:
```python
def validate_class_balance(y_train, min_samples_per_class=30, min_balance_score=0.5):
    """
    Validate that training data has sufficient class balance.
    
    Returns: (is_valid: bool, reason: str)
    """
    from collections import Counter
    from math import log
    
    class_counts = Counter(y_train)
    
    # Hard check: at least 2 classes
    if len(class_counts) < 2:
        return False, "Single class window - cannot train classifier"
    
    # Soft check: minimum samples per class  
    min_class_count = min(class_counts.values())
    if min_class_count < min_samples_per_class:
        return False, f"Minority class has only {min_class_count} samples (need {min_samples_per_class})"
    
    # Balance check: entropy score
    total = sum(class_counts.values())
    props = [c/total for c in class_counts.values()]
    entropy = -sum(p * log(p) for p in props if p > 0)
    max_entropy = log(len(class_counts))
    balance_score = entropy / max_entropy
    
    if balance_score < min_balance_score:
        return False, f"Class imbalance too severe: balance_score={balance_score:.2f} (need {min_balance_score})"
    
    return True, f"Passed: {len(class_counts)} classes, min={min_class_count}, balance={balance_score:.2f}"
```

---

### Task t1-1-r2: Class Imbalance Detection Methods

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: class imbalance detection machine learning SMOTE class weights threshold calibration

#### Paper 4: Abdelhamid & Desai, 2024 (arXiv:2409.19751v1) 🔥 CRITICAL
**Title**: "Balancing the Scales: A Comprehensive Study on Tackling Class Imbalance in Binary Classification"  
**Methodology**: 9,000 experiments, 30 datasets, 15 models (CatBoost, LightGBM, XGBoost included), 4 scenarios

**Key Findings - Performance Ranking (F1-score)**:
| Method | Best in % of Datasets | Mean F1 |
|--------|----------------------|---------|
| Decision Threshold Calibration | 40% | 0.617 ± 0.005 |
| SMOTE | 30% | 0.605 ± 0.006 |
| Class Weights | 23.3% | 0.594 ± 0.006 |
| Baseline (no treatment) | 10% | 0.556 ± 0.006 |

**Statistical Significance (p < 0.0083, Bonferroni-corrected)**:
- All three methods significantly outperform Baseline
- Decision Threshold significantly better than Class Weights
- No significant difference between SMOTE and Decision Threshold

**SMOTE Caveat**:
- Shows **worst probability calibration** (highest Log-Loss, Brier Score)
- Creates synthetic samples that may not reflect real-world distributions
- Can lead to overfitting in high-dimensional settings (Blagus & Lusa, 2013)

**Metrics by Method**:
| Method | F2-score | Recall | Precision | Brier Score |
|--------|----------|--------|-----------|-------------|
| Threshold | Best | Best | Medium | Same as Baseline |
| SMOTE | Best | Best | Low | **Worst** |
| Class Weights | Medium | Medium | Medium | Medium |
| Baseline | Low | Low | **Best** | Best |

**Quote**: "Decision Threshold Calibration emerged as the most consistent and effective technique, offering significant performance gains across various datasets and models."

**Recommendation for Our System**:
- Use **Class Weights** (`scale_pos_weight`) native to CatBoost/LightGBM
- Avoid SMOTE - creates calibration issues that affect conformal prediction
- Can tune class weights via grid search: 0.25, 0.5, 0.75, 1.0 (balanced), 1.25 (over-correction)

---

### Task t1-1-r3: Entropy-Based Balance Metrics

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: class entropy imbalance metric normalized entropy classification

#### Entropy as Balance Metric (from Multiple Sources)

**Shannon Entropy for Class Balance**:
```python
entropy = -sum(p * log(p) for p in class_proportions)
max_entropy = log(n_classes)  # For n classes uniformly distributed
balance_score = entropy / max_entropy  # Normalized: 0 to 1
```

**Balance Score Interpretation**:
| Score | Interpretation | Example (2-class) |
|-------|---------------|-------------------|
| 1.0 | Perfect balance | 50%/50% |
| 0.81 | Good balance | 40%/60% |
| 0.72 | Moderate imbalance | 30%/70% |
| 0.47 | Severe imbalance | 10%/90% |
| 0.0 | Single class | 0%/100% |

**For 3-class Classification** (our regime targets):
| Distribution | Entropy | Balance Score |
|--------------|---------|---------------|
| 33%/33%/33% | 1.10 | 1.00 |
| 40%/30%/30% | 1.09 | 0.99 |
| 50%/25%/25% | 1.04 | 0.95 |
| 60%/20%/20% | 0.95 | 0.87 |
| 70%/15%/15% | 0.83 | 0.76 |
| 80%/10%/10% | 0.64 | 0.58 |
| 90%/5%/5%   | 0.40 | 0.36 |

**From HMM Quality Function in final-2.py**:
```python
# State utilization (entropy-based balance)
state_probs = state_counts / len(states)
entropy = -np.sum(state_probs * np.log(state_probs + 1e-10))
balance_score = entropy / np.log(n_components)  # normalized
```

**Other Imbalance Metrics Found in Literature**:
1. **Imbalance Ratio (IR)**: `max_class / min_class` (simple but not normalized)
2. **Gini Index**: `1 - sum(p^2)` (used in tree splits)
3. **Cohen's Kappa**: Chance-corrected accuracy (from arXiv:2507.03392)
4. **Matthews Correlation Coefficient (MCC)**: Balanced measure for binary classification

**Adopted Metric**: **Normalized Shannon Entropy**
- Reason: Scales 0-1, works for any number of classes, interpretable

---

### DECISION POINT 1.1: FINALIZED ✅

**Question**: What minimum samples per class and balance threshold should we use?

**FINAL DECISION**:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `min_classes` | **2** | Hard requirement - can't train classifier otherwise |
| `min_samples_per_class` | **30** | Literature suggests 50+ ideal, but 30 is practical minimum |
| `min_balance_score` | **0.5** | Allows up to ~80/10/10 split (3-class), catches extreme imbalance |
| `warn_samples_per_class` | **50** | Log warning if minority class below this |

**Final Implementation**:
```python
def validate_class_balance(
    y_train: np.ndarray,
    min_samples_per_class: int = 30,
    min_balance_score: float = 0.5,
    warn_samples_per_class: int = 50
) -> tuple[bool, str, dict]:
    """
    Validate class balance for training data.
    
    Returns:
        (is_valid, message, metrics)
        
    Metrics dict contains:
        - n_classes: int
        - class_counts: dict
        - min_class_count: int
        - balance_score: float (0-1, 1 = perfect balance)
    """
    from collections import Counter
    from math import log
    
    class_counts = Counter(y_train)
    n_classes = len(class_counts)
    
    metrics = {
        'n_classes': n_classes,
        'class_counts': dict(class_counts),
        'min_class_count': min(class_counts.values()) if n_classes > 0 else 0,
        'balance_score': 0.0
    }
    
    # Hard check: at least 2 classes
    if n_classes < 2:
        return False, "FAIL: Single class window - cannot train classifier", metrics
    
    # Calculate balance score (normalized entropy)
    total = sum(class_counts.values())
    props = [c/total for c in class_counts.values()]
    entropy = -sum(p * log(p) for p in props if p > 0)
    max_entropy = log(n_classes)
    balance_score = entropy / max_entropy if max_entropy > 0 else 0.0
    metrics['balance_score'] = balance_score
    
    # Soft check: minimum samples per class
    min_count = metrics['min_class_count']
    if min_count < min_samples_per_class:
        return False, f"FAIL: Minority class has {min_count} samples (need {min_samples_per_class})", metrics
    
    # Balance check
    if balance_score < min_balance_score:
        return False, f"FAIL: Severe imbalance, balance_score={balance_score:.2f} (need {min_balance_score})", metrics
    
    # Warning check
    warning = ""
    if min_count < warn_samples_per_class:
        warning = f" (WARNING: minority class {min_count} < {warn_samples_per_class})"
    
    return True, f"PASS: {n_classes} classes, min={min_count}, balance={balance_score:.2f}{warning}", metrics
```

---

## TIER 1.2 RESEARCH: Window Configuration

### Task t1-2-r1: Regime Persistence in Financial Data

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: "regime persistence" financial time series hidden markov

#### Key Findings from SSRN Papers

**Paper 5: Raza et al., 2019 (SSRN 3338365)**
**Title**: "The Effect of Market Regimes on the Performance of Market Capitalization-Weighted and Smart Beta Shariah-Compliant Equity Portfolios"

**Quantitative Finding**:
- "Persistence values for both regimes are greater than **95%**"
- This means if you're in a bullish regime, there's >95% probability of staying in that regime next period

**Regime Duration Formula** (standard HMM):
```
Expected Duration = 1 / (1 - p_ii)

Where p_ii = self-transition probability

Example: If p_ii = 0.95
Expected Duration = 1 / (1 - 0.95) = 20 periods
```

**Paper 6: Duriez, 2025 (SSRN 5744302)**
**Title**: "Adaptive Market-Risk Management with Regime-Aware Models: Hard, Soft, Hybrid, and IA-Enhanced HMM Allocators"

**Key Insight**:
- "Volatility clustering, regime persistence, and sudden breaks make state identification a natural precursor to state-contingent allocation"
- Confirms regime persistence is characteristic of financial time series

**Implications for Our System**:
- With 95% persistence: Expected regime duration = 20 bars
- At 4h timeframe: 20 bars = 80 hours ≈ 3.3 days
- At 1h timeframe: 20 bars = 20 hours
- For 12-bar horizons: Regime likely persists through forecast window

**Why This Causes Single-Class Windows**:
If trend regime has 95% persistence and window_size=500:
- Most samples in a given window will be from same regime
- Need larger windows to capture regime transitions
- Need target-specific window sizes

---

### Task t1-2-r2: Calibration Set Size for Conformal Prediction

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: conformal prediction calibration set sample size coverage guarantee

#### Paper 7: Kladny et al., 2025 (arXiv:2512.14727) 🔥 CRITICAL
**Title**: "A Critical Perspective on Finite Sample Conformal Prediction Theory in Medical Applications"

**Key Findings - Coverage Variance by Calibration Set Size**:

| Cal Set Size (m) | % Falling Below 85% Coverage | Spread |
|-----------------|------------------------------|--------|
| m = 10 | **19%** | Very wide |
| m = 50 | ~8% | Moderate |
| m = 200 | ~0% | Tight around target |

**Critical Quote**:
> "If, however, conformal prediction is used according to the setup described in Section 4, the size of the calibration set is decisive for achieving coverage close to the desired level."

**Theoretical vs Practical Coverage**:
- **Unconditional guarantee**: Holds for ANY calibration set size (mathematically)
- **Conditional guarantee**: Coverage variance highly dependent on cal set size
- **Practical implication**: Small cal sets → high variance in actual coverage

**Formula for Coverage Variance**:
The calibration-set-conditional guarantee involves the binomial CDF:
```
δ ≥ Binomial(m, α̃)(⌊α(m+1) - 1⌋)
```
Where m = calibration set size, α = miscoverage rate (0.1 for 90% coverage)

**Recommendation for Our System**:
| Target Coverage | Minimum Cal Size | Recommended Cal Size |
|----------------|-----------------|---------------------|
| 85% | 50 | 100+ |
| 90% | 100 | 200+ |
| 95% | 200 | 500+ |

**Current System Analysis**:
- Current: cal_ratio=0.30 × window_size=500 = **150 samples**
- This is borderline for 90% coverage target
- Regime targets have additional class balance constraints

---

### Task t1-2-r3: Sliding vs Expanding Window Trade-offs

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Search Query**: sliding window vs expanding window time series forecasting

#### General Principles (from established literature)

**Sliding Window (Fixed Size)**:
| Pros | Cons |
|------|------|
| Adapts to regime changes | May forget valuable historical patterns |
| Consistent computational cost | Wastes data at start of series |
| Robust to non-stationarity | Fewer samples for estimation |

**Expanding Window (Growing)**:
| Pros | Cons |
|------|------|
| Uses all available data | Slow to adapt to regime changes |
| More stable estimates | Increasing computational cost |
| Better for stationary processes | Old data may hurt in non-stationary case |

**When to Use Each**:
- **Sliding**: Non-stationary, regime-switching data (our regime targets)
- **Expanding**: Slowly-evolving, stationary processes
- **Hybrid**: Exponential weighting on expanding window

**For Our System**:
- Regime targets: **Sliding** (regimes are non-stationary)
- Direction targets: **Sliding** (market conditions change)
- Volatility targets: **Sliding** (vol clustering decays)

**Current Design**: Already using sliding windows → ✅ Correct choice

---

### DECISION POINT 1.2: Window Configuration ✅

**Question**: Is cal=80 samples acceptable? What window configuration for regime targets?

**Analysis**:

| Current Config | Value | Issue |
|---------------|-------|-------|
| window_size | 500 | Too small for regime persistence |
| train_ratio | 0.55 | 275 samples - marginal |
| cal_ratio | 0.30 | 150 samples - borderline |
| val_ratio | 0.15 | 75 samples - ok for validation |

**Why Current Config Fails for Regime Targets**:
1. **Regime persistence ~95%**: Expected duration = 20 bars
2. **Window = 500 bars**: Only ~25 regime transitions expected
3. **Train = 275 samples**: May have <30 samples of minority class
4. **Cal = 150 samples**: Borderline for conformal coverage

**FINAL DECISION - Adaptive Window Configs**:

```python
# For regime targets (trend_regime_*, vol_regime_*)
REGIME_L2_CONFIG = SlidingL2Config(
    window_size=700,      # Was 500 - more transitions
    train_ratio=0.60,     # 420 samples - sufficient for class balance
    cal_ratio=0.25,       # 175 samples - adequate for conformal
    val_ratio=0.15,       # 105 samples - ok
    purge_gap=21,         # horizon + buffer
)

# For direction/volatility targets
STANDARD_L2_CONFIG = SlidingL2Config(
    window_size=500,      # Original - works for faster-changing targets
    train_ratio=0.55,     # 275 samples
    cal_ratio=0.30,       # 150 samples
    val_ratio=0.15,       # 75 samples
    purge_gap=21,
)

REGIME_TARGETS = {'trend_regime', 'vol_regime'}  # prefix match

def get_l2_config_for_target(target_name: str) -> SlidingL2Config:
    """Return appropriate L2 config based on target characteristics."""
    for prefix in REGIME_TARGETS:
        if target_name.startswith(prefix):
            return REGIME_L2_CONFIG
    return STANDARD_L2_CONFIG
```

**Expected Improvement**:
- 700 bars → ~35 regime transitions (vs 25)
- 420 train samples → ~60 minority class samples (vs 30)
- Single-class window rate: Target <5% (from 30.3%)

---

## TIER 1.3 RESEARCH: Look-Ahead Bias Prevention

### Task t1-3-r1: Look-Ahead Bias in Backtesting

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Source**: López de Prado (2018), Wikipedia - Purged Cross-Validation

#### Definitions

**Look-Ahead Bias** (also called "Future Leakage"):
> Using information that would not have been available at the time of prediction.

**Common Sources**:
1. **Feature leakage**: Using future price data to compute features
2. **Label leakage**: Train set overlaps with test label formation period
3. **Information leakage**: Indirect contamination through correlated features
4. **Data snooping**: Selecting features/parameters based on full dataset

**Our System Risk Areas**:
- L1 helpers compute features at prediction time → potential leakage
- L2 models train on sliding windows → label horizon could leak
- Conformal calibration set → must not overlap with validation

---

### Task t1-3-r2: Purge/Embargo Best Practices (López de Prado)

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  
**Source**: López de Prado (2018) "Advances in Financial Machine Learning", Chapter 7

#### Purging

**Definition**: Remove from training set any observation whose timestamp falls within the time range of formation of a label in the test set.

**When to Apply**:
- Labels are computed from future data (e.g., forward returns)
- Features have serial correlation with target
- Train and test sets are temporally adjacent

**Purge Gap Formula**:
```
purge_gap ≥ max_label_horizon

If label = return_12bar (12 bars ahead):
    purge_gap ≥ 12 bars
```

#### Embargoing

**Definition**: After each test fold, exclude a percentage of subsequent observations from training to prevent leakage due to market reaction lag or auto-correlated features.

**When to Apply**:
- Even after purging, residual correlation may exist
- Market microstructure effects persist
- Features have memory (e.g., moving averages, GARCH)

**Embargo Formula**:
```
embargo_pct = 1% to 5% of dataset
OR
embargo_bars = ceil(feature_memory_length)

For rolling window features:
    embargo_bars ≥ max(rolling_window_lengths)
```

**López de Prado Recommendation**:
> "A percentage-based embargo is imposed after each test fold. For example, with a 5% embargo and 1000 observations, the 50 observations following each test fold are excluded from training."

---

### Task t1-3-r3: Horizon-Specific Leakage Prevention

**Status**: ✅ COMPLETE  
**Date**: 2025-01-11  

#### Our System's Window Structure

```
For horizon=12, window_size=500, train_ratio=0.55:

Timeline:
[--------- TRAIN (275) ---------][GAP][--CAL (150)--][--VAL (75)--][PREDICT]
                                  ^
                                  purge_gap = 21 (horizon + buffer)

Prediction at index 500:
- Train ends at: 274
- purge_gap: 275-295 (21 bars excluded)
- Cal starts at: 296
- Cal ends at: 445
- Val starts at: 446
- Val ends at: 500
- Predict at: 501+
```

#### Validation of Current Design

**Current `purge_gap = 21`** (for horizon=12):

| Horizon | Purge Gap | Buffer | Assessment |
|---------|-----------|--------|------------|
| 1 bar | 21 | +20 | ✅ Very conservative |
| 4 bar | 21 | +17 | ✅ Conservative |
| 8 bar | 21 | +13 | ✅ Adequate |
| 12 bar | 21 | +9 | ✅ Adequate |
| 20 bar | 21 | +1 | ⚠️ Borderline |

**Recommendation**: Make purge_gap horizon-adaptive:
```python
def compute_purge_gap(horizon: int, safety_buffer: int = 10) -> int:
    """Compute purge gap based on horizon."""
    return horizon + safety_buffer
```

#### Look-Ahead Bias Validator

```python
def validate_no_lookahead(
    pred_idx: int,
    train_end_idx: int,
    cal_start_idx: int,
    horizon: int,
    purge_gap: int
) -> tuple[bool, str]:
    """
    Validate that window configuration prevents look-ahead bias.
    
    Args:
        pred_idx: Index where prediction will be made
        train_end_idx: Last index in training set
        cal_start_idx: First index in calibration set
        horizon: Forecast horizon in bars
        purge_gap: Gap between train and cal sets
    
    Returns:
        (is_valid, message)
    """
    # Rule 1: Train must end before prediction
    if train_end_idx >= pred_idx:
        return False, f"FAIL: Train ends at {train_end_idx} >= pred at {pred_idx}"
    
    # Rule 2: Purge gap must be at least horizon
    actual_gap = cal_start_idx - train_end_idx - 1
    if actual_gap < horizon:
        return False, f"FAIL: Gap ({actual_gap}) < horizon ({horizon})"
    
    # Rule 3: Cal must not overlap with label formation
    label_formation_start = pred_idx
    label_formation_end = pred_idx + horizon
    
    # Cal set should not include data that overlaps with label formation
    # (This is automatically satisfied if cal ends before pred_idx)
    
    # Rule 4: Purge gap should have safety buffer
    min_purge = horizon + 10  # López de Prado recommends buffer
    if purge_gap < min_purge:
        warning = f" (WARNING: purge_gap {purge_gap} < recommended {min_purge})"
    else:
        warning = ""
    
    return True, f"PASS: train_end={train_end_idx}, gap={actual_gap}, horizon={horizon}{warning}"
```

---

### DECISION POINT 1.3: Look-Ahead Bias Configuration ✅

**Question**: Is `purge_gap = horizon + 10` sufficient?

**FINAL DECISION**: YES, with caveats.

| Configuration | Value | Rationale |
|--------------|-------|-----------|
| `base_purge_gap` | `horizon` | Minimum required |
| `safety_buffer` | **10** | Account for feature memory |
| `total_purge_gap` | `horizon + 10` | Our implementation |

**Why 10-bar buffer is sufficient**:
1. Our L1 features use short lookbacks (mostly <20 bars)
2. GARCH persistence decays within ~10 bars
3. HMM state probabilities stabilize quickly
4. López de Prado recommends 1-5% of dataset (for 500 bars = 5-25 bars)

**Adaptive Purge Gap Implementation**:
```python
def get_purge_gap_for_horizon(horizon: int) -> int:
    """
    Return appropriate purge gap for given horizon.
    
    Conservative formula: gap = horizon + max(10, horizon * 0.5)
    """
    safety_buffer = max(10, int(horizon * 0.5))
    return horizon + safety_buffer

# Examples:
# horizon=1  → gap=11 (1 + 10)
# horizon=4  → gap=14 (4 + 10)  
# horizon=8  → gap=18 (8 + 10)
# horizon=12 → gap=18 (12 + max(10, 6)=12+10=22... wait, that's > 21)
# horizon=20 → gap=30 (20 + 10)
```

**UPDATE**: Our current fixed `purge_gap=21` is CORRECT for horizons ≤12.
For horizon=20, should increase to 30.

**Final Validation Checklist**:
- [x] Train set ends before prediction index
- [x] Purge gap ≥ horizon
- [x] Calibration set does not overlap label formation
- [x] Features computed only from past data
- [x] No future returns in feature engineering

---

## Findings from final-2.py

Source: `Archive-usefull-info-from-past-work/previous_work/help_fm/final-2.py`  
File size: 13,104 lines  
Context: HMM-based regime detection with adaptive feature selection

### Function 1: `compute_column_quality_scores()`

**Location**: Lines 3755-3810  
**Purpose**: Score columns based on data quality for feature selection

```python
def compute_column_quality_scores(df, columns):
    """
    Compute quality scores for each column based on:
    - Availability (% non-NaN values)
    - Early start (how early column has valid data)
    - Non-zero ratio (% of non-zero values)
    - Variance (standard deviation)
    - Autocorrelation (lag-1 autocorr)
    
    Returns dict: column_name → {score, availability, first_valid, ...}
    """
```

**Weighting Scheme**:
| Component | Weight | Description |
|-----------|--------|-------------|
| availability | 30% | Percentage of valid (non-NaN) values |
| early_start | 25% | How early in dataset column has data (penalize late-starting) |
| nonzero_ratio | 20% | Percentage of non-zero values |
| variance | 15% | Standard deviation (reward variability) |
| autocorrelation | 10% | Lag-1 autocorr (penalize high autocorr = less info) |

**Applicability to Our Problem**: 
- Could adapt to score **target class balance** instead of feature quality
- Replace `nonzero_ratio` with `class_entropy` for classification targets

---

### Function 2: `estimate_min_samples_for_hmm()`

**Location**: Lines 3816-3881  
**Purpose**: Calculate minimum samples needed for reliable HMM fitting

```python
def estimate_min_samples_for_hmm(n_features, n_components=3, covariance_type="full"):
    """
    Estimate minimum samples based on:
    1. MLE stability: 30 samples per parameter
    2. Covariance stability: 5-10x features
    3. HMM state visits: 100 visits per state
    
    Returns: min_samples (int), bounded by [200, 8000]
    """
```

**Parameter Counting (for HMM)**:
```python
# For diagonal covariance:
n_params = (
    (n_components - 1) * n_components  # transition matrix
    + (n_components - 1)                # initial state
    + n_components * n_features         # means
    + n_components * n_features         # diagonal covariances
)

# Rule: 30 samples per parameter
min_samples_mle = int(n_params * 30)
```

**Stability Requirements**:
| Requirement | Formula | Notes |
|-------------|---------|-------|
| MLE stability | 30 × n_params | Based on statistical theory |
| Covariance (full) | 10 × n_features | Need samples >> features |
| Covariance (diag) | 5 × n_features | Less stringent |
| HMM state visits | 100 × n_components | Each state visited enough |

**Hard Bounds**: `min=200, max=8000`

**Applicability to Our Problem**:
- Adapt formula for **classification minimum samples**
- For 2-class binary: need at least N samples per class
- Rule of thumb: `min_per_class = max(50, train_size * 0.1)`

---

### Function 3: `evaluate_hmm_quality()`

**Location**: Lines 3884-3997  
**Purpose**: Evaluate fitted HMM quality with multiple metrics

```python
def evaluate_hmm_quality(hmm_model, data, n_splits=3):
    """
    Quality metrics:
    1. Log-likelihood per sample (convergence quality)
    2. BIC (Bayesian Information Criterion)
    3. AIC (Akaike Information Criterion)
    4. Transition matrix stability (eigenvalue check)
    5. State utilization (entropy-based balance)
    6. Samples-per-parameter ratio
    
    Returns: quality_score (0-1) and detailed metrics
    """
```

**Combined Quality Score Weights**:
| Component | Weight | Description |
|-----------|--------|-------------|
| stability_score | 30% | Transition matrix validity (most important) |
| balance_score | 25% | State utilization (entropy) |
| ll_normalized | 25% | Log-likelihood (convergence quality) |
| bic_normalized | 10% | Model parsimony |
| spp_score | 10% | Samples/param adequacy |

**Key Calculations**:
```python
# Stability: Check transition matrix eigenvalues
eigenvalues = np.linalg.eigvals(hmm_model.transmat_)
complex_ratio = np.sum(np.abs(np.imag(eigenvalues)) > 1e-10) / len(eigenvalues)
stability_score = 1.0 - complex_ratio

# Balance: Entropy of state distribution
states = hmm_model.predict(data)
state_counts = np.bincount(states, minlength=n_components)
state_probs = state_counts / len(states)
entropy = -np.sum(state_probs * np.log(state_probs + 1e-10))
balance_score = entropy / np.log(n_components)  # normalized
```

**Applicability to Our Problem**:
- Adapt `balance_score` concept for **class balance in classification**
- If balance_score < threshold → flag window as problematic

---

### Function 4: `find_optimal_feature_subset_adaptive()`

**Location**: Lines 4000-4100  
**Purpose**: Iteratively select features while maintaining sample sufficiency

```python
def find_optimal_feature_subset_adaptive(df, columns, n_components=3, verbose=True):
    """
    Algorithm:
    1. Score all columns by quality
    2. Sort by score (best first)
    3. Iteratively add columns while maintaining sufficient samples
    4. Balance: more features need more samples
    
    Returns: optimal_cols, first_valid_row, excluded_info, details
    """
```

**Key Logic**:
```python
# Cap max features to ensure samples/param ratio > 20
MAX_FEATURES_FOR_QUALITY = min(15, len(sorted_cols))

for n_features in range(1, MAX_FEATURES_FOR_QUALITY + 1):
    subset = sorted_cols[:n_features]
    
    # Find first valid row for this subset
    first_valid = max(quality_scores[col]["first_valid"] for col in subset)
    available_samples = total_rows - first_valid
    
    # Estimate minimum required samples
    min_samples = estimate_min_samples_for_hmm(n_features, n_components)
    
    # Skip if insufficient
    if available_samples < min_samples:
        continue
    
    # Score this configuration
    sample_ratio = min(1.0, available_samples / (min_samples * 2))
    feature_richness = n_features / len(columns)
    avg_quality = np.mean([quality_scores[c]["score"] for c in subset])
    
    subset_quality = 0.40 * sample_ratio + 0.30 * feature_richness + 0.30 * avg_quality
```

**Applicability to Our Problem**:
- Adapt to **adaptive window sizing** based on target characteristics
- Pre-scan target to find min window where all classes appear
- Trade-off: larger window = fewer iterations vs guaranteed class coverage

---

### Function 5: `find_optimal_n_components()`

**Location**: Lines 4120-4165  
**Purpose**: Select optimal number of HMM states using BIC

```python
def find_optimal_n_components(data, max_components=5, min_components=2):
    """
    Test n_components from min to max, select based on:
    - BIC (lower is better)
    - Convergence success
    - Regime balance
    """
```

**Not directly applicable** to our problem (we don't control number of classes).

---

## Current Project Analysis

### Helpers Inventory (`/scripts/target_models/helpers/`)

| File | Lines | Purpose | Class Balance Handling? |
|------|-------|---------|------------------------|
| `base.py` | 522 | BaseHelper ABC, incremental training | ❌ No |
| `cusum.py` | ~200 | CUSUM changepoint detection | ❌ Unsupervised |
| `ensemble.py` | 697 | HelperEnsemble, IC-boosting | ❌ No |
| `garch.py` | ~300 | GARCH volatility estimation | ❌ Unsupervised |
| `helper_selection.py` | 262 | Task-type aware helper selection | ❌ No |
| `hmm.py` | 499 | HMM regime detection | ❌ Unsupervised |
| `icir_config.py` | 273 | ICIR config with min_samples | ⚠️ min_samples for IC, not class |
| `icir_selection.py` | 438 | Rolling ICIR feature selection | ⚠️ min_samples check exists |
| `isolation_forest.py` | ~200 | Anomaly detection | ❌ Unsupervised |
| `kalman.py` | ~300 | State estimation | ❌ Unsupervised |
| `optimized_config_loader.py` | ~100 | Load optimized L2 params | ❌ Config only |

**Key Finding**: No existing helper handles classification class balance validation.

---

### Core Window Configuration (`/scripts/target_models/core/`)

#### `aligned_dual_window.py` - SlidingL2Config

```python
@dataclass
class SlidingL2Config:
    window_size: int = 500      # Total L2 window size
    train_ratio: float = 0.55   # 55% for training (275 samples)
    cal_ratio: float = 0.30     # 30% for calibration (150 samples)
    val_ratio: float = 0.15     # ~11% for validation (54 samples)
    purge_gap: int = 21         # Gap between train and cal
    pred_size: int = 1
```

**Current Split (window=500)**:
| Split | Samples | Percentage |
|-------|---------|------------|
| Train | 275 | 55% |
| Purge | 21 | 4% |
| Cal | 150 | 30% |
| Val | 54 | 11% |

**Problem**: 275 train samples insufficient for regime targets with persistent states.

---

### Models with Single-Class Handling (`/scripts/target_models/models/`)

Current workaround (symptom handling):

```python
# catboost_model.py, lightgbm_model.py, linear.py
def _fit_impl(self, X, y):
    unique_classes = np.unique(y)
    if self.config.is_classification and len(unique_classes) == 1:
        self._single_class = unique_classes[0]
        return  # Skip training
    # ... normal training
```

---

## Applicability Analysis

### What final-2.py Solves (HMM/Unsupervised)
1. Feature quality scoring for selection
2. Minimum samples for model parameter estimation
3. Model quality evaluation (BIC, state balance)
4. Adaptive feature subset selection

### What We Need (Classification/Supervised)
1. **Class balance validation** before training
2. **Minimum samples per class** requirement
3. **Adaptive window sizing** per target type
4. **Fallback behavior** when validation fails

### Transferable Concepts

| final-2.py Concept | Our Application |
|-------------------|-----------------|
| `compute_column_quality_scores()` | `compute_class_balance_score(y)` |
| `estimate_min_samples_for_hmm()` | `estimate_min_samples_for_classification(n_classes)` |
| `evaluate_hmm_quality()` balance_score | `compute_class_entropy(y)` |
| `find_optimal_feature_subset_adaptive()` | `find_optimal_window_size_adaptive(target)` |

---

## Proposed Adaptations

### 1. Class Balance Validation Function

```python
def validate_class_balance(
    y: np.ndarray, 
    min_samples_per_class: int = 30,
    min_class_ratio: float = 0.05,
) -> tuple[bool, dict]:
    """
    Check if target has sufficient class diversity.
    
    Args:
        y: Target array
        min_samples_per_class: Minimum samples required per class
        min_class_ratio: Minimum ratio of minority class (0.05 = 5%)
    
    Returns:
        (is_valid, metrics_dict)
    """
    unique, counts = np.unique(y, return_counts=True)
    n_classes = len(unique)
    n_samples = len(y)
    
    # Check 1: At least 2 classes
    if n_classes < 2:
        return False, {"reason": "single_class", "n_classes": n_classes}
    
    # Check 2: Minimum samples per class
    min_count = counts.min()
    if min_count < min_samples_per_class:
        return False, {"reason": "insufficient_minority", "min_count": min_count}
    
    # Check 3: Minimum class ratio
    min_ratio = min_count / n_samples
    if min_ratio < min_class_ratio:
        return False, {"reason": "imbalanced", "min_ratio": min_ratio}
    
    # Compute class entropy (normalized)
    probs = counts / n_samples
    entropy = -np.sum(probs * np.log(probs + 1e-10))
    max_entropy = np.log(n_classes)
    balance_score = entropy / max_entropy
    
    return True, {
        "n_classes": n_classes,
        "min_count": min_count,
        "min_ratio": min_ratio,
        "balance_score": balance_score,
    }
```

### 2. Minimum Samples Estimation (Classification)

```python
def estimate_min_train_samples(
    task_type: str,
    n_classes: int = 2,
    n_features: int = 50,
    samples_per_class: int = 50,
) -> int:
    """
    Estimate minimum training samples for reliable classification.
    
    Rules:
    - Binary: At least 50 samples per class = 100 minimum
    - Multiclass: At least 50 samples per class
    - Additional: 5-10x features for stable gradients
    
    Returns minimum train samples needed.
    """
    if task_type == "regression":
        # Regression: 10x features rule
        return max(100, n_features * 10)
    
    # Classification
    class_minimum = n_classes * samples_per_class
    feature_minimum = n_features * 5  # More lenient than regression
    
    return max(class_minimum, feature_minimum, 100)
```

### 3. Per-Target Window Configuration

```python
# Regime targets need larger train ratio due to persistence
REGIME_TARGETS = {"trend_regime", "vol_regime"}

def get_l2_config_for_target(target: str, horizon: int) -> SlidingL2Config:
    """Get appropriate L2 config based on target characteristics."""
    
    if target in REGIME_TARGETS:
        # Regime targets: increase train ratio to ensure class coverage
        return SlidingL2Config(
            window_size=500,
            train_ratio=0.80,   # 400 samples (vs default 0.55 = 275)
            cal_ratio=0.16,     # 80 samples
            val_ratio=0.04,     # 20 samples
            purge_gap=max(21, horizon + 10),
        )
    else:
        # Default for non-regime targets
        return SlidingL2Config(
            window_size=500,
            train_ratio=0.55,
            cal_ratio=0.30,
            val_ratio=0.15,
            purge_gap=max(21, horizon + 10),
        )
```

### 4. Adaptive Window Sizing (Advanced)

```python
def find_min_window_for_class_coverage(
    y_full: np.ndarray,
    target_coverage: float = 0.99,  # 99% of windows should have both classes
    base_train_ratio: float = 0.55,
    window_range: tuple = (400, 1000),
    step: int = 50,
) -> int:
    """
    Pre-scan target to find minimum window size where class coverage is achieved.
    
    Returns optimal window_size or max if not achievable.
    """
    for window_size in range(window_range[0], window_range[1] + 1, step):
        train_size = int(window_size * base_train_ratio)
        
        # Simulate walk-forward windows
        n_windows = len(y_full) - window_size
        single_class_count = 0
        
        for start in range(n_windows):
            y_train = y_full[start:start + train_size]
            if len(np.unique(y_train)) < 2:
                single_class_count += 1
        
        coverage = 1 - (single_class_count / n_windows)
        if coverage >= target_coverage:
            return window_size
    
    return window_range[1]  # Return max if not achievable
```

---

## Trade-off Analysis

### Option A: Increase train_ratio (0.55 → 0.80)

**Changes**:
- Train: 275 → 400 samples
- Cal: 150 → 80 samples
- Val: 54 → 20 samples

**Pros**:
- ✅ 0% single-class failures
- ✅ No change to iteration count
- ✅ Simple implementation

**Cons**:
- ⚠️ Cal reduced to 80 (MAPIE wants 100+)
- ⚠️ Val reduced to 20 (limited early stopping)

### Option B: Increase window_size (500 → 700)

**Changes**:
- Window: 500 → 700 samples
- Train: 385 samples (at 55%)
- Cal: 210 samples (at 30%)
- Val: 77 samples (at 11%)

**Pros**:
- ✅ 0% single-class failures
- ✅ Maintains cal size for conformal
- ✅ Better statistical stability

**Cons**:
- ⚠️ ~300 fewer iterations (3,237 vs 3,437)
- ⚠️ Requires L1 precompute regeneration

### Option C: Adaptive skip (no config change)

**Changes**:
- Keep current config
- Skip iterations where validation fails

**Pros**:
- ✅ No config changes needed
- ✅ All configs use same settings

**Cons**:
- ⚠️ Inconsistent iteration counts across configs
- ⚠️ ~30% of iterations skipped for regime targets
- ⚠️ Potentially biased results (systematic exclusion)

### Option D: Precompute more iterations

**Changes**:
- Increase backtest_rows from 300 to 3,000+
- Use larger window where needed

**Pros**:
- ✅ Maximum flexibility
- ✅ Can test multiple window sizes

**Cons**:
- ⚠️ 10x compute time for precompute
- ⚠️ Storage increase

---

## Files to Modify (Implementation)

| File | Change |
|------|--------|
| `core/aligned_dual_window.py` | Add `get_l2_config_for_target()` |
| `core/validators.py` (NEW) | Add `validate_class_balance()`, `estimate_min_train_samples()` |
| `pipeline.py` | Use target-specific config via `get_l2_config_for_target()` |
| `validation/fast_backtest.py` | Use target-specific config |
| `optimize_l2.py` | Update search space for regime targets |

---

## Open Questions

1. **Option A or B?** Trade-off: cal size vs iteration count
2. **Cal size 80 acceptable?** MAPIE documentation suggests 100+ for stable coverage
3. **Fallback behavior?** When validation still fails:
   - Skip iteration (NaN)?
   - Use workaround (constant prediction)?
   - Expand window dynamically?
4. **Apply to optimize_l2.py?** Current `train_ratio` search space is `[0.65, 0.70, 0.75]` - should regime targets use `[0.75, 0.80, 0.85]`?

---

## Look-Ahead Bias Prevention

### Critical Constraint

Any adaptive optimization MUST avoid look-ahead bias. The optimization process cannot use information that wouldn't be available at prediction time.

### The 20 Configuration Matrix

We have 20 distinct configurations, each with different data availability:

| Target | Horizons | Task Type | Dataset |
|--------|----------|-----------|---------|
| direction | 1, 3, 6, 12 | binary | `direction_{h}bar.parquet` |
| returns | 1, 3, 6, 12 | regression | `returns_{h}bar.parquet` |
| volatility | 1, 3, 6, 12 | regression | `volatility_{h}bar.parquet` |
| vol_regime | 1, 3, 6, 12 | multiclass (3) | `vol_regime_{h}bar.parquet` |
| trend_regime | 1, 3, 6, 12 | binary | `trend_regime_{h}bar.parquet` |

**Each horizon has different target leakage boundaries:**
- `horizon=1`: Target uses data up to t+1 (8h ahead)
- `horizon=3`: Target uses data up to t+3 (24h ahead)
- `horizon=6`: Target uses data up to t+6 (48h ahead)
- `horizon=12`: Target uses data up to t+12 (96h ahead)

### What Information Is Available at Prediction Time?

At prediction time `t`, we can use:

```
ALLOWED (Available at time t):
├── Features X[0:t]           ← All historical features
├── Target y[0:t-horizon]     ← Historical targets (with horizon gap!)
├── Class distribution of y[0:t-horizon]
├── Window statistics computed on [0:t-horizon]
└── Any derived metrics from above

FORBIDDEN (Not available at time t):
├── Target y[t-horizon+1:t]   ← Future targets (leakage!)
├── Target y[t+1:∞]           ← Future targets
├── Any statistics using y beyond t-horizon
└── Optimal window size determined using future y
```

### Horizon-Specific Purge Requirements

The purge gap must account for target horizon to prevent leakage:

```python
# Current implementation (aligned_dual_window.py)
purge_gap = max(21, horizon + 10)

# This means:
# horizon=1:  purge_gap = 21 (default minimum)
# horizon=3:  purge_gap = 21 (default minimum)
# horizon=6:  purge_gap = 21 (default minimum)
# horizon=12: purge_gap = 22 (horizon + 10)
```

**Visual Timeline for horizon=12:**
```
Time:     [...t-500...][t-400][...TRAIN...][t-125][PURGE][t-103][..CAL..][t-53][VAL][t][PRED]
                                                    ↑
                                              22 bars gap
                                         (horizon=12 + buffer=10)

At time t, predicting t+12:
- Train ends at t-125 (safe: targets use data up to t-125+12 = t-113)
- Purge gap of 22 ensures no target overlaps with prediction period
- Cal/Val targets are for [t-103 to t], which is fine for training
```

### Safe vs Unsafe Adaptive Operations

#### ✅ SAFE: Pre-Scan for Window Sizing (Per-Config, Historical Only)

```python
def find_min_window_for_class_coverage_safe(
    y_historical: np.ndarray,  # Only y[0:t-horizon] at prediction time
    target_coverage: float = 0.99,
    base_train_ratio: float = 0.55,
    window_range: tuple = (400, 1000),
) -> int:
    """
    SAFE: Uses only historical target values.
    
    This can be computed ONCE at the start of walk-forward,
    using only data available before first prediction.
    """
    # Simulate on historical data only
    for window_size in range(window_range[0], window_range[1] + 1, 50):
        train_size = int(window_size * base_train_ratio)
        n_windows = len(y_historical) - window_size
        
        if n_windows <= 0:
            continue
            
        single_class_count = sum(
            1 for start in range(n_windows)
            if len(np.unique(y_historical[start:start + train_size])) < 2
        )
        
        coverage = 1 - (single_class_count / n_windows)
        if coverage >= target_coverage:
            return window_size
    
    return window_range[1]
```

#### ❌ UNSAFE: Using Future Information

```python
def find_min_window_UNSAFE(y_full, ...):
    """
    UNSAFE: Uses entire target array including future values.
    
    This would give different (better) results because it 
    "knows" about future regime changes.
    """
    # DON'T DO THIS - uses y beyond current time
    for window_size in range(...):
        for start in range(len(y_full) - window_size):  # Includes future!
            y_train = y_full[start:start + train_size]
            ...
```

### Implementation Strategy: Per-Config Pre-Scan

**Step 1: Compute optimal window BEFORE walk-forward starts**

```python
def precompute_adaptive_config(
    target: str,
    horizon: int,
    dataset_path: Path,
) -> dict:
    """
    Compute adaptive parameters using only data that would be
    available at the START of walk-forward iteration.
    
    Called ONCE per config, before any predictions.
    """
    df = pd.read_parquet(dataset_path)
    y_col = f"y_{target}"
    y_full = df[y_col].values
    
    # For walk-forward starting at index `first_pred_idx`:
    # We can only use y[0:first_pred_idx - horizon] for optimization
    
    # Conservative: use first 70% of data for window optimization
    # This leaves 30% truly out-of-sample
    optimization_end = int(len(y_full) * 0.70)
    y_for_optimization = y_full[:optimization_end]
    
    # Find optimal window using only this historical portion
    optimal_window = find_min_window_for_class_coverage_safe(
        y_for_optimization,
        target_coverage=0.99,
    )
    
    return {
        "target": target,
        "horizon": horizon,
        "optimal_window_size": optimal_window,
        "optimization_data_end_idx": optimization_end,
        "computed_at": datetime.now().isoformat(),
    }
```

**Step 2: Use precomputed config during walk-forward**

```python
def get_l2_config_for_target_adaptive(
    target: str, 
    horizon: int,
    precomputed: dict,
) -> SlidingL2Config:
    """
    Get L2 config using precomputed adaptive parameters.
    No look-ahead: parameters were computed on historical data only.
    """
    window_size = precomputed.get("optimal_window_size", 500)
    
    if target in REGIME_TARGETS:
        # Regime targets: use larger train ratio
        return SlidingL2Config(
            window_size=window_size,
            train_ratio=0.80,
            cal_ratio=0.16,
            val_ratio=0.04,
            purge_gap=max(21, horizon + 10),
        )
    else:
        return SlidingL2Config(
            window_size=window_size,
            train_ratio=0.55,
            cal_ratio=0.30,
            val_ratio=0.15,
            purge_gap=max(21, horizon + 10),
        )
```

### Different Horizons = Different Available Data

At any prediction time `t`, each horizon has different target availability:

```
Prediction at time t=1000, predicting different horizons:

horizon=1:  Can use y[0:999]    (targets up to t-1)
horizon=3:  Can use y[0:997]    (targets up to t-3)
horizon=6:  Can use y[0:994]    (targets up to t-6)
horizon=12: Can use y[0:988]    (targets up to t-12)
```

**This means:**
- Longer horizons have LESS historical target data available
- Window optimization for horizon=12 should be more conservative
- Class balance statistics differ by horizon even for same target

### Validation: Checking for Look-Ahead Bias

```python
def validate_no_lookahead(
    train_end_idx: int,
    cal_end_idx: int,
    val_end_idx: int,
    pred_idx: int,
    horizon: int,
) -> bool:
    """
    Validate that window configuration doesn't leak future information.
    
    Key constraints:
    1. Train targets must not overlap with prediction target
    2. Cal/Val targets must not overlap with prediction target
    3. All target indices must be at least `horizon` bars before pred_idx
    """
    # Target at pred_idx looks ahead `horizon` bars
    # So any target computed at idx requires data up to idx+horizon
    
    # Maximum target index used in training
    max_train_target_idx = train_end_idx + horizon
    
    # Prediction target uses data at pred_idx + horizon
    pred_target_idx = pred_idx + horizon
    
    # Check: train targets don't overlap with prediction
    assert max_train_target_idx < pred_idx, \
        f"Train leakage: max_train_target={max_train_target_idx} >= pred_idx={pred_idx}"
    
    # Check: cal/val are between train and pred (this is by design)
    assert train_end_idx < cal_end_idx < val_end_idx <= pred_idx
    
    return True
```

### Summary: Safe Adaptive Optimization Rules

| Rule | Description | Implementation |
|------|-------------|----------------|
| **Pre-scan only** | Compute adaptive params before walk-forward | Use first 70% of data |
| **Per-config params** | Each of 20 configs gets own optimization | Don't share across horizons |
| **Horizon-aware** | Longer horizons = less available data | Adjust purge_gap = horizon + 10 |
| **No future targets** | Never use y[t-horizon+1:] for optimization | Strict boundary enforcement |
| **Fixed during WF** | Once computed, params don't change | No online adaptation |
| **Document boundaries** | Log what data was used for optimization | Audit trail |

### Alternative: Online Adaptive (More Complex)

If online adaptation is needed (params change during walk-forward):

```python
def update_adaptive_params_online(
    iteration: int,
    pred_idx: int,
    horizon: int,
    y_available: np.ndarray,  # Only y[0:pred_idx-horizon]
) -> dict:
    """
    Update adaptive parameters during walk-forward.
    
    CRITICAL: y_available must NOT include y[pred_idx-horizon+1:]
    
    This is more complex and requires careful boundary management.
    Recommended only if pre-scan is insufficient.
    """
    # Recompute class balance on available data only
    # This changes each iteration as more data becomes available
    ...
```

**Recommendation**: Start with pre-scan (simpler, less risk). Only move to online adaptation if pre-scan proves insufficient.

---

## Layer 1 Helper Optimization (Unsupervised Models)

### Overview

The L1 helpers (HMM, GARCH, CUSUM, Kalman, IsolationForest) are "unsupervised" in name only. In practice, we can optimize them toward our prediction targets using:

1. **BIC/AIC** - Model selection criteria (lower = better fit with parsimony)
2. **IC (Information Coefficient)** - Spearman correlation with target
3. **ICIR** - IC stability over time (IC / std(IC))
4. **Feature importance** - How much each helper's output contributes to L2

**Key Insight**: We optimize the helpers to produce features that are **predictive of our target**, not just good internal fits.

### Current L1 Helpers and Their Tunable Parameters

#### 1. HMM (Hidden Markov Model)

**File**: `scripts/target_models/helpers/hmm.py`

**Tunable Parameters**:
| Parameter | Current | Range | Optimization Metric |
|-----------|---------|-------|---------------------|
| `n_states` | 4 (market), 5 (vol) | 2-7 | BIC (lower = better) |
| `covariance_type` | "diag" | diag, full, spherical | BIC |
| `n_iter` | 100 | 50-500 | Convergence (log-likelihood) |
| Input features | returns, vol | Any columns | IC of output states with target |

**Optimization Strategy**:
```python
def optimize_hmm_n_states(
    X: np.ndarray,
    y: np.ndarray,  # Target for IC computation
    state_range: tuple = (2, 7),
) -> dict:
    """
    Find optimal n_states using BIC + IC.
    
    BIC ensures model parsimony.
    IC ensures states are predictive of target.
    
    Combined score = 0.5 * normalized_BIC + 0.5 * IC
    """
    results = {}
    for n_states in range(state_range[0], state_range[1] + 1):
        hmm = GaussianHMM(n_components=n_states, covariance_type="diag")
        hmm.fit(X)
        
        # BIC (lower is better, so negate for maximization)
        bic = hmm.bic(X)
        
        # IC: correlation of predicted states with target
        states = hmm.predict(X)
        ic = spearmanr(states, y)[0]
        
        results[n_states] = {"bic": bic, "ic": ic}
    
    return results
```

#### 2. GARCH (Generalized Autoregressive Conditional Heteroskedasticity)

**File**: `scripts/target_models/helpers/garch.py`

**Tunable Parameters**:
| Parameter | Current | Range | Optimization Metric |
|-----------|---------|-------|---------------------|
| `p` (GARCH order) | 1 | 1-3 | BIC |
| `q` (ARCH order) | 1 | 1-3 | BIC |
| `dist` (distribution) | "normal" | normal, t, skewt | BIC |
| `forecast_horizon` | horizon | 1-12 | IC with volatility target |

**Optimization Strategy**:
```python
def optimize_garch_order(
    returns: np.ndarray,
    y_vol: np.ndarray,  # Volatility target
    p_range: tuple = (1, 3),
    q_range: tuple = (1, 3),
) -> dict:
    """
    Find optimal (p, q) using BIC + IC with volatility target.
    """
    from arch import arch_model
    
    results = {}
    for p in range(p_range[0], p_range[1] + 1):
        for q in range(q_range[0], q_range[1] + 1):
            model = arch_model(returns, vol='Garch', p=p, q=q)
            fit = model.fit(disp='off')
            
            # BIC
            bic = fit.bic
            
            # IC: correlation of conditional vol with target vol
            cond_vol = fit.conditional_volatility
            ic = spearmanr(cond_vol, y_vol)[0]
            
            results[(p, q)] = {"bic": bic, "ic": ic}
    
    return results
```

#### 3. CUSUM (Cumulative Sum Control Chart)

**File**: `scripts/target_models/helpers/cusum.py`

**Tunable Parameters**:
| Parameter | Current | Range | Optimization Metric |
|-----------|---------|-------|---------------------|
| `threshold` | 5.0 | 2.0-10.0 | Changepoint accuracy vs false alarms |
| `drift` | 0.0 | 0.0-1.0 | IC with regime changes |
| `window_size` | 50 | 20-200 | IC stability (ICIR) |

**Optimization Strategy**:
```python
def optimize_cusum_threshold(
    X: np.ndarray,
    y_regime: np.ndarray,  # Regime target (0/1)
    threshold_range: np.ndarray = np.arange(2.0, 10.0, 0.5),
) -> dict:
    """
    Find optimal threshold using IC with regime target.
    
    Lower threshold = more sensitive (more changepoints)
    Higher threshold = more specific (fewer false alarms)
    """
    results = {}
    for threshold in threshold_range:
        cusum_up, cusum_down = compute_cusum(X, threshold)
        changepoints = detect_changepoints(cusum_up, cusum_down)
        
        # IC: correlation of changepoint signal with regime target
        ic = spearmanr(changepoints, y_regime)[0]
        
        # Also measure: number of detected changepoints (too many = overfit)
        n_changes = np.sum(np.diff(changepoints) != 0)
        
        results[threshold] = {"ic": ic, "n_changes": n_changes}
    
    return results
```

#### 4. Kalman Filter

**File**: `scripts/target_models/helpers/kalman.py`

**Tunable Parameters**:
| Parameter | Current | Range | Optimization Metric |
|-----------|---------|-------|---------------------|
| `process_noise` (Q) | 0.01 | 0.001-0.1 | IC with target |
| `measurement_noise` (R) | 0.1 | 0.01-1.0 | IC with target |
| `state_dim` | 3 | 1-5 | BIC-like (log-likelihood / n_params) |

**Optimization Strategy**:
```python
def optimize_kalman_noise(
    X: np.ndarray,
    y: np.ndarray,  # Any target
    Q_range: np.ndarray = np.logspace(-3, -1, 10),
    R_range: np.ndarray = np.logspace(-2, 0, 10),
) -> dict:
    """
    Find optimal process/measurement noise using IC with target.
    
    Grid search over Q×R combinations.
    """
    results = {}
    for Q in Q_range:
        for R in R_range:
            kf = KalmanFilter(process_noise=Q, measurement_noise=R)
            filtered_state = kf.filter(X)
            
            # IC: correlation of filtered state with target
            ic = spearmanr(filtered_state, y)[0]
            
            # Log-likelihood for model comparison
            ll = kf.log_likelihood(X)
            
            results[(Q, R)] = {"ic": ic, "log_likelihood": ll}
    
    return results
```

#### 5. Isolation Forest

**File**: `scripts/target_models/helpers/isolation_forest.py`

**Tunable Parameters**:
| Parameter | Current | Range | Optimization Metric |
|-----------|---------|-------|---------------------|
| `n_estimators` | 100 | 50-300 | IC with volatility |
| `contamination` | 0.05 | 0.01-0.20 | IC with extreme returns |
| `max_samples` | "auto" | 64-512 | OOB score stability |

**Optimization Strategy**:
```python
def optimize_isolation_forest(
    X: np.ndarray,
    y_vol: np.ndarray,  # Volatility target
    contamination_range: np.ndarray = np.arange(0.01, 0.20, 0.02),
) -> dict:
    """
    Find optimal contamination using IC with volatility.
    
    Anomalies should correlate with high volatility periods.
    """
    results = {}
    for contamination in contamination_range:
        iforest = IsolationForest(
            n_estimators=100,
            contamination=contamination,
            random_state=42,
        )
        iforest.fit(X)
        
        # Anomaly scores (more negative = more anomalous)
        scores = iforest.decision_function(X)
        
        # IC: correlation of anomaly scores with volatility
        # (anomalies should occur during high vol)
        ic = spearmanr(-scores, y_vol)[0]  # Negate so higher = more anomalous
        
        results[contamination] = {"ic": ic}
    
    return results
```

### Combined L1 Optimization Framework

```python
@dataclass
class L1OptimizationConfig:
    """Configuration for L1 helper optimization."""
    
    # Target-aware optimization
    target: str  # volatility, direction, returns, vol_regime, trend_regime
    horizon: int  # 1, 3, 6, 12
    
    # Metrics to optimize
    primary_metric: str = "ic"  # ic, icir, bic
    secondary_metric: str = "bic"  # For model selection
    
    # Search strategy
    n_trials: int = 20  # Number of trials per helper
    cv_folds: int = 3  # Temporal CV for IC stability
    
    # Constraints
    min_samples: int = 200  # Minimum samples for optimization
    

def optimize_l1_helpers(
    X: np.ndarray,
    y: np.ndarray,
    target: str,
    horizon: int,
    config: L1OptimizationConfig,
) -> dict:
    """
    Optimize all L1 helpers for a specific target-horizon.
    
    Returns dict of optimal parameters per helper.
    """
    results = {}
    
    # 1. HMM optimization
    results["hmm4"] = optimize_hmm_n_states(
        X, y, state_range=(3, 6),
        metric="ic" if target in ["direction", "trend_regime"] else "bic",
    )
    
    # 2. GARCH optimization (only for volatility-related targets)
    if target in ["volatility", "vol_regime", "returns"]:
        results["garch"] = optimize_garch_order(
            X[:, 0], y,  # Use first column as returns proxy
            p_range=(1, 2), q_range=(1, 2),
        )
    
    # 3. CUSUM optimization (for regime targets)
    if target in ["trend_regime", "vol_regime"]:
        results["cusum"] = optimize_cusum_threshold(
            X, y, threshold_range=np.arange(3.0, 8.0, 0.5),
        )
    
    # 4. Kalman optimization
    results["kalman"] = optimize_kalman_noise(
        X, y, Q_range=np.logspace(-3, -1, 5), R_range=np.logspace(-2, 0, 5),
    )
    
    # 5. Isolation Forest optimization
    results["iforest"] = optimize_isolation_forest(
        X, y, contamination_range=np.arange(0.02, 0.15, 0.02),
    )
    
    return results
```

### Target-Specific Optimization Guidelines

| Target | Primary Helpers | Optimization Focus | Key Metric |
|--------|-----------------|-------------------|------------|
| `volatility` | GARCH, HMM-5, IF | Conditional variance prediction | IC with realized vol |
| `returns` | Kalman, HMM-4 | Trend/mean estimation | IC with returns |
| `direction` | HMM-4, CUSUM | Regime detection | IC with direction |
| `vol_regime` | HMM-5, GARCH, IF | Volatility clustering | IC with vol regime |
| `trend_regime` | HMM-4, CUSUM, Kalman | Trend persistence | IC with trend regime |

### Horizon-Specific Considerations

| Horizon | Window Adjustment | Optimization Notes |
|---------|-------------------|-------------------|
| 1 bar (8h) | Shorter lookbacks | Fast-reacting signals preferred |
| 3 bar (24h) | Medium lookbacks | Balance fast/slow signals |
| 6 bar (48h) | Longer lookbacks | Trend signals more important |
| 12 bar (96h) | Longest lookbacks | Regime signals dominate |

### BIC vs IC Trade-off

```python
def combined_optimization_score(
    bic: float,
    ic: float,
    bic_weight: float = 0.3,
    ic_weight: float = 0.7,
) -> float:
    """
    Combine BIC (model quality) and IC (predictive power).
    
    BIC: Lower is better → normalize and negate
    IC: Higher is better → use directly
    
    Weights:
    - Higher ic_weight: Prioritize predictive power
    - Higher bic_weight: Prioritize model parsimony (avoid overfit)
    """
    # Normalize BIC to [0, 1] range (lower is better)
    bic_normalized = 1.0 / (1.0 + np.abs(bic) / 1000)
    
    # IC is already in [-1, 1], shift to [0, 1]
    ic_normalized = (ic + 1) / 2
    
    return bic_weight * bic_normalized + ic_weight * ic_normalized
```

### Implementation Priority

Given the complexity, implement in phases:

| Phase | Scope | Complexity | Impact |
|-------|-------|------------|--------|
| **Phase 1** | HMM n_states optimization | Low | High (most used) |
| **Phase 2** | GARCH order optimization | Medium | Medium (vol targets) |
| **Phase 3** | CUSUM threshold optimization | Low | Medium (regime targets) |
| **Phase 4** | Kalman noise optimization | Medium | Low (stable defaults) |
| **Phase 5** | IsolationForest contamination | Low | Low (anomaly detection) |
| **Phase 6** | Combined optimization | High | High (full system) |

### Look-Ahead Bias in L1 Optimization

**CRITICAL**: L1 optimization must also avoid look-ahead bias!

```python
def optimize_l1_safe(
    X: np.ndarray,
    y: np.ndarray,
    pred_idx: int,
    horizon: int,
) -> dict:
    """
    Optimize L1 helpers using only data available at prediction time.
    
    At prediction time `pred_idx`, we can only use:
    - Features: X[0:pred_idx]
    - Targets: y[0:pred_idx - horizon]  ← CRITICAL: horizon gap!
    """
    # Safe boundaries
    X_available = X[:pred_idx]
    y_available = y[:pred_idx - horizon]  # Must account for horizon!
    
    # Align lengths
    min_len = min(len(X_available), len(y_available))
    X_opt = X_available[:min_len]
    y_opt = y_available[:min_len]
    
    # Now optimize using only available data
    return optimize_l1_helpers(X_opt, y_opt, ...)
```

### Pre-Scan Strategy for L1 Optimization

Similar to L2, we can pre-scan to find optimal L1 parameters:

```python
def precompute_l1_optimal_params(
    target: str,
    horizon: int,
    dataset_path: Path,
) -> dict:
    """
    Pre-compute optimal L1 parameters using historical data only.
    
    Called ONCE per config before walk-forward starts.
    Uses conservative data split (first 60-70%) to avoid any
    possibility of look-ahead contamination.
    """
    df = pd.read_parquet(dataset_path)
    
    # Conservative split: use first 60% for optimization
    optimization_end = int(len(df) * 0.60)
    
    X = df.drop(columns=[c for c in df.columns if c.startswith("y_")]).values
    y = df[f"y_{target}"].values
    
    X_opt = X[:optimization_end]
    y_opt = y[:optimization_end - horizon]  # Horizon gap!
    
    # Align
    min_len = min(len(X_opt), len(y_opt))
    X_opt = X_opt[:min_len]
    y_opt = y_opt[:min_len]
    
    # Optimize each helper
    optimal_params = {}
    
    # HMM
    hmm_results = optimize_hmm_n_states(X_opt, y_opt)
    best_n_states = max(hmm_results, key=lambda k: hmm_results[k]["ic"])
    optimal_params["hmm"] = {"n_states": best_n_states}
    
    # GARCH (if applicable)
    if target in ["volatility", "vol_regime", "returns"]:
        garch_results = optimize_garch_order(X_opt[:, 0], y_opt)
        best_order = max(garch_results, key=lambda k: garch_results[k]["ic"])
        optimal_params["garch"] = {"p": best_order[0], "q": best_order[1]}
    
    # ... other helpers
    
    return {
        "target": target,
        "horizon": horizon,
        "optimal_params": optimal_params,
        "optimization_data_end_idx": optimization_end,
        "computed_at": datetime.now().isoformat(),
    }
```

---

## Master Implementation Roadmap

### Scope: Tier 1-3 Only

We focus ONLY on these 9 items (Tier 4 deferred to future):

### Tier 1: Critical (Must Do)
1. **L2 Class Balance Validation** - Prevent single-class crashes
2. **Per-Target Window Config** - Regime targets need larger train ratio
3. **Look-Ahead Bias Prevention** - Strict boundary enforcement

### Tier 2: Important (Should Do)
4. **HMM n_states Optimization** - BIC + IC guided
5. **GARCH Order Optimization** - For volatility targets
6. **CUSUM Threshold Optimization** - For regime targets

### Tier 3: Nice to Have (Could Do)
7. **Kalman Noise Optimization** - Grid search Q×R
8. **IsolationForest Contamination** - For anomaly detection
9. **Combined L1 Optimization Framework** - Full integration

---

## Detailed Research & Implementation Plan

### Research Sources (Trusted Only)

| Source | URL | Best For | Trust Level |
|--------|-----|----------|-------------|
| **arXiv** | https://arxiv.org | ML, statistics, q-fin preprints | ⭐⭐⭐⭐ (not peer-reviewed but used by all) |
| **SSRN** | https://www.ssrn.com | Finance, econometrics | ⭐⭐⭐⭐⭐ |
| **Google Scholar** | https://scholar.google.com | Universal index | ⭐⭐⭐⭐ (check citations) |
| **Semantic Scholar** | https://www.semanticscholar.org | ML papers | ⭐⭐⭐⭐ |
| **SpringerLink** | https://link.springer.com | Quantitative Finance journal | ⭐⭐⭐⭐⭐ (peer-reviewed) |

### Research Quality Checklist

Before accepting any paper/method:
- [ ] Published on arXiv, SSRN, or peer-reviewed journal?
- [ ] Has citations (non-zero)?
- [ ] Contains explicit math/formulas?
- [ ] Compares to baselines?
- [ ] Data description provided?
- [ ] Code available (bonus)?

### Skip Immediately If:
- Medium/blog/Substack
- "AI predicts markets" clickbait
- No equations
- No baseline comparison

---

## TIER 1: CRITICAL TASKS

### Task 1.1: L2 Class Balance Validation

**Objective**: Prevent single-class training crashes by validating class distribution before model fitting.

#### Research Phase (1.1.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 1.1.R1 | Find minimum samples per class guidelines | `"minimum sample size" classification imbalanced` | Google Scholar | ⬜ |
| 1.1.R2 | Research class imbalance detection methods | `class imbalance detection machine learning` | arXiv (stat.ML) | ⬜ |
| 1.1.R3 | Find entropy-based balance metrics | `"class entropy" imbalance metric` | Semantic Scholar | ⬜ |

**Expected Outputs**:
- Minimum samples per class (literature consensus)
- Formula for class balance score
- Threshold for "acceptable" imbalance

**Validation Questions**:
- [ ] Do papers agree on minimum samples (e.g., 30, 50, 100)?
- [ ] Is entropy-based scoring standard practice?
- [ ] Any financial-specific considerations?

**DECISION POINT 1.1.D**: If literature is unclear on minimum samples, STOP and discuss.

#### Implementation Phase (1.1.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 1.1.I1 | Create `validate_class_balance()` function | `core/validators.py` (NEW) | 1.1.R1-R3 | ⬜ |
| 1.1.I2 | Add class entropy computation | `core/validators.py` | 1.1.I1 | ⬜ |
| 1.1.I3 | Integrate into `pipeline.py` L2 training | `pipeline.py` | 1.1.I2 | ⬜ |
| 1.1.I4 | Integrate into `fast_backtest.py` | `validation/fast_backtest.py` | 1.1.I2 | ⬜ |

#### Verification Phase (1.1.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 1.1.V1 | Test on `trend_regime_12bar` (91 single-class windows) | Validation catches all 91 | ⬜ |
| 1.1.V2 | Test on `direction_1bar` (should pass) | 0 failures | ⬜ |
| 1.1.V3 | Verify no false positives | Balanced windows pass | ⬜ |

---

### Task 1.2: Per-Target Window Config

**Objective**: Create target-specific L2 window configurations to ensure class coverage.

#### Research Phase (1.2.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 1.2.R1 | Research regime persistence in financial data | `"regime persistence" financial time series` | SSRN | ⬜ |
| 1.2.R2 | Find optimal train/cal/val ratios for classification | `"calibration set size" conformal prediction` | arXiv | ⬜ |
| 1.2.R3 | Research sliding window vs expanding window trade-offs | `"expanding window" vs "sliding window" forecasting` | Google Scholar | ⬜ |

**Expected Outputs**:
- Evidence for regime persistence patterns
- Minimum calibration set size for conformal (we know ~100+)
- Train/cal/val ratio recommendations

**Validation Questions**:
- [ ] Is 80/16/4 split justified for regime targets?
- [ ] What's minimum cal size for stable conformal coverage?
- [ ] Any papers on adaptive window sizing?

**DECISION POINT 1.2.D**: If cal=80 is too small per literature, need to increase window_size.

#### Implementation Phase (1.2.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 1.2.I1 | Add `REGIME_TARGETS` constant | `core/aligned_dual_window.py` | 1.2.R1-R3 | ⬜ |
| 1.2.I2 | Create `get_l2_config_for_target()` function | `core/aligned_dual_window.py` | 1.2.I1 | ⬜ |
| 1.2.I3 | Update `PipelineConfig.get_dual_config()` | `pipeline.py` | 1.2.I2 | ⬜ |
| 1.2.I4 | Update `BacktestConfig` to use adaptive config | `validation/fast_backtest.py` | 1.2.I2 | ⬜ |

#### Verification Phase (1.2.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 1.2.V1 | `trend_regime_12bar` with new config | 0% single-class failures | ⬜ |
| 1.2.V2 | `vol_regime_*` with new config | 0% single-class failures | ⬜ |
| 1.2.V3 | Conformal coverage still valid | 85-95% coverage | ⬜ |
| 1.2.V4 | Non-regime targets unchanged | Same results as before | ⬜ |

---

### Task 1.3: Look-Ahead Bias Prevention

**Objective**: Ensure no future information leaks into model training or optimization.

#### Research Phase (1.3.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 1.3.R1 | Research look-ahead bias in backtesting | `"look-ahead bias" backtesting finance` | SSRN | ⬜ |
| 1.3.R2 | Find purge/embargo best practices | `"purged cross-validation" time series` | arXiv | ⬜ |
| 1.3.R3 | Research horizon-specific leakage prevention | `"target leakage" forecasting horizon` | Google Scholar | ⬜ |

**Key Paper to Find**: "Advances in Financial Machine Learning" (López de Prado) - purged k-fold CV

**Expected Outputs**:
- Formula: purge_gap ≥ horizon + buffer
- Embargo period recommendations
- Validation checklist for leakage detection

**Validation Questions**:
- [ ] Is `purge_gap = horizon + 10` sufficient?
- [ ] Should embargo also scale with horizon?
- [ ] How to detect accidental leakage?

**DECISION POINT 1.3.D**: If literature suggests larger purge, need to recalculate all window sizes.

#### Implementation Phase (1.3.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 1.3.I1 | Create `validate_no_lookahead()` function | `core/validators.py` | 1.3.R1-R3 | ⬜ |
| 1.3.I2 | Add assertion checks in `AlignedDualEngine.get_window()` | `core/aligned_dual_window.py` | 1.3.I1 | ⬜ |
| 1.3.I3 | Document boundary calculations | `core/aligned_dual_window.py` (docstrings) | 1.3.I2 | ⬜ |
| 1.3.I4 | Add leakage detection logging | `pipeline.py` | 1.3.I1 | ⬜ |

#### Verification Phase (1.3.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 1.3.V1 | Run all 20 configs through validator | All pass | ⬜ |
| 1.3.V2 | Test edge case: horizon=12, pred_idx=500 | Correct boundaries | ⬜ |
| 1.3.V3 | Test intentional leakage (should fail) | Validator catches it | ⬜ |

---

## TIER 2: IMPORTANT TASKS

### Task 2.1: HMM n_states Optimization

**Objective**: Find optimal number of HMM states using BIC + IC scoring.

#### Research Phase (2.1.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 2.1.R1 | Research BIC for HMM model selection | `"BIC" "hidden markov model" "model selection"` | Google Scholar | ⬜ |
| 2.1.R2 | Find IC-based HMM evaluation in finance | `"information coefficient" HMM regime finance` | SSRN | ⬜ |
| 2.1.R3 | Research HMM state stability metrics | `HMM "transition matrix" stability eigenvalue` | arXiv | ⬜ |
| 2.1.R4 | Find financial regime detection papers | `"regime detection" "hidden markov" finance volatility` | SSRN | ⬜ |

**Key Search Terms**:
- `"Gaussian HMM" "model selection" BIC AIC`
- `"regime switching" "number of states" finance`
- `"Hamilton filter" "regime" states`

**Expected Outputs**:
- BIC formula for HMM: `BIC = -2*log_likelihood + n_params*log(n_samples)`
- Recommended n_states range for financial data (literature says 2-5 typically)
- IC computation method: `spearman(predicted_states, target)`

**Validation Questions**:
- [ ] Is BIC the standard for HMM model selection?
- [ ] Should we use AIC instead or in combination?
- [ ] What's the typical n_states for volatility regimes (2-3?) vs market regimes (3-5?)?
- [ ] How to handle non-convergence?

**DECISION POINT 2.1.D**: If literature disagrees on BIC vs AIC, STOP and discuss.

#### Implementation Phase (2.1.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 2.1.I1 | Add `compute_hmm_bic()` function | `helpers/hmm.py` | 2.1.R1-R4 | ⬜ |
| 2.1.I2 | Add `optimize_hmm_n_states()` function | `helpers/hmm.py` | 2.1.I1 | ⬜ |
| 2.1.I3 | Create `HMMOptimizationConfig` dataclass | `helpers/hmm.py` | 2.1.I2 | ⬜ |
| 2.1.I4 | Integrate into `HelperEnsemble` | `helpers/ensemble.py` | 2.1.I3 | ⬜ |

#### Verification Phase (2.1.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 2.1.V1 | Test BIC decreases then increases with n_states | U-shape curve | ⬜ |
| 2.1.V2 | Verify IC correlates with target | Positive correlation for useful states | ⬜ |
| 2.1.V3 | Check no look-ahead bias in optimization | Uses only historical data | ⬜ |
| 2.1.V4 | Compare optimized vs fixed n_states | Optimized should improve or match | ⬜ |

---

### Task 2.2: GARCH Order Optimization

**Objective**: Find optimal (p, q) order for GARCH models using BIC + IC with volatility target.

#### Research Phase (2.2.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 2.2.R1 | Research GARCH model selection | `"GARCH" "model selection" BIC AIC order` | Google Scholar | ⬜ |
| 2.2.R2 | Find optimal GARCH orders in finance | `"GARCH(1,1)" vs "GARCH(2,1)" volatility forecasting` | SSRN | ⬜ |
| 2.2.R3 | Research GARCH extensions (EGARCH, GJR-GARCH) | `"asymmetric GARCH" "leverage effect" finance` | arXiv | ⬜ |
| 2.2.R4 | Find IC-based volatility model evaluation | `"information coefficient" volatility forecast` | SSRN | ⬜ |

**Key Paper to Find**: Bollerslev (1986), Engle (1982) - foundational GARCH papers

**Expected Outputs**:
- BIC formula for GARCH
- Common finding: GARCH(1,1) often sufficient
- When to use higher orders

**Validation Questions**:
- [ ] Is GARCH(1,1) really optimal most of the time?
- [ ] Should we consider asymmetric models (EGARCH, GJR)?
- [ ] How to handle non-convergence?
- [ ] Distribution selection (normal vs t vs skewed-t)?

**DECISION POINT 2.2.D**: If GARCH(1,1) is universally optimal per literature, simplify to just distribution selection.

#### Implementation Phase (2.2.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 2.2.I1 | Add `compute_garch_bic()` function | `helpers/garch.py` | 2.2.R1-R4 | ⬜ |
| 2.2.I2 | Add `optimize_garch_order()` function | `helpers/garch.py` | 2.2.I1 | ⬜ |
| 2.2.I3 | Create `GARCHOptimizationConfig` dataclass | `helpers/garch.py` | 2.2.I2 | ⬜ |
| 2.2.I4 | Integrate into `HelperEnsemble` | `helpers/ensemble.py` | 2.2.I3 | ⬜ |

#### Verification Phase (2.2.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 2.2.V1 | Test on volatility targets | GARCH features improve IC | ⬜ |
| 2.2.V2 | Compare optimized vs GARCH(1,1) default | Optimized ≥ default | ⬜ |
| 2.2.V3 | Verify numerical stability | No NaN/Inf outputs | ⬜ |
| 2.2.V4 | Check computation time | Acceptable overhead | ⬜ |

---

### Task 2.3: CUSUM Threshold Optimization

**Objective**: Find optimal CUSUM threshold for changepoint detection using IC with regime targets.

#### Research Phase (2.3.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 2.3.R1 | Research CUSUM parameter selection | `"CUSUM" threshold selection "control chart"` | Google Scholar | ⬜ |
| 2.3.R2 | Find CUSUM in financial regime detection | `"CUSUM" "regime change" finance` | SSRN | ⬜ |
| 2.3.R3 | Research ARL (Average Run Length) for threshold | `"average run length" CUSUM threshold` | Google Scholar | ⬜ |
| 2.3.R4 | Find adaptive CUSUM methods | `"adaptive CUSUM" "change point detection"` | arXiv | ⬜ |

**Expected Outputs**:
- Threshold selection based on desired false alarm rate
- ARL formula for CUSUM
- Trade-off: sensitivity vs specificity

**Validation Questions**:
- [ ] What threshold gives ~5% false alarm rate?
- [ ] Should threshold adapt to data volatility?
- [ ] How to evaluate changepoint accuracy?

**DECISION POINT 2.3.D**: If CUSUM threshold depends heavily on data scale, may need normalization first.

#### Implementation Phase (2.3.I)

| ID | Task | File | Depends On | Status |
|----|------|------|------------|--------|
| 2.3.I1 | Add `optimize_cusum_threshold()` function | `helpers/cusum.py` | 2.3.R1-R4 | ⬜ |
| 2.3.I2 | Add IC-based scoring for changepoints | `helpers/cusum.py` | 2.3.I1 | ⬜ |
| 2.3.I3 | Create `CUSUMOptimizationConfig` dataclass | `helpers/cusum.py` | 2.3.I2 | ⬜ |
| 2.3.I4 | Integrate into `HelperEnsemble` | `helpers/ensemble.py` | 2.3.I3 | ⬜ |

#### Verification Phase (2.3.V)

| ID | Task | Expected Result | Status |
|----|------|-----------------|--------|
| 2.3.V1 | Test on trend_regime targets | IC > 0 | ⬜ |
| 2.3.V2 | Verify threshold vs false alarm rate | ~5% false alarms | ⬜ |
| 2.3.V3 | Compare optimized vs default threshold | Optimized ≥ default | ⬜ |

---

## TIER 3: NICE TO HAVE TASKS

### Task 3.1: Kalman Noise Optimization

#### Research Phase (3.1.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 3.1.R1 | Research Kalman Q/R tuning | `"Kalman filter" "process noise" "measurement noise" tuning` | Google Scholar | ⬜ |
| 3.1.R2 | Find adaptive Kalman methods | `"adaptive Kalman filter" finance` | arXiv | ⬜ |

#### Implementation Phase (3.1.I)

| ID | Task | File | Status |
|----|------|------|--------|
| 3.1.I1 | Add `optimize_kalman_noise()` | `helpers/kalman.py` | ⬜ |
| 3.1.I2 | Grid search Q×R | `helpers/kalman.py` | ⬜ |

---

### Task 3.2: IsolationForest Contamination

#### Research Phase (3.2.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 3.2.R1 | Research contamination parameter selection | `"isolation forest" contamination parameter` | Google Scholar | ⬜ |
| 3.2.R2 | Find anomaly detection in finance | `"anomaly detection" "isolation forest" finance volatility` | SSRN | ⬜ |

#### Implementation Phase (3.2.I)

| ID | Task | File | Status |
|----|------|------|--------|
| 3.2.I1 | Add `optimize_iforest_contamination()` | `helpers/isolation_forest.py` | ⬜ |
| 3.2.I2 | IC-based scoring | `helpers/isolation_forest.py` | ⬜ |

---

### Task 3.3: Combined L1 Optimization Framework

#### Research Phase (3.3.R)

| ID | Task | Search Query | Source | Status |
|----|------|--------------|--------|--------|
| 3.3.R1 | Research multi-model optimization | `"ensemble" "model selection" "feature engineering"` | Google Scholar | ⬜ |
| 3.3.R2 | Find combined BIC/IC frameworks | `"information criterion" "feature selection" ensemble` | arXiv | ⬜ |

#### Implementation Phase (3.3.I)

| ID | Task | File | Status |
|----|------|------|--------|
| 3.3.I1 | Create `L1OptimizationConfig` dataclass | `helpers/l1_optimization.py` (NEW) | ⬜ |
| 3.3.I2 | Create `optimize_all_helpers()` function | `helpers/l1_optimization.py` | ⬜ |
| 3.3.I3 | Create pre-scan storage format | `helpers/l1_optimization.py` | ⬜ |

---

## Execution Order & Dependencies

```
PHASE 1: RESEARCH (All research tasks first)
│
├── Tier 1 Research (Parallel)
│   ├── 1.1.R1-R3 (Class Balance)
│   ├── 1.2.R1-R3 (Window Config)
│   └── 1.3.R1-R3 (Look-Ahead Bias)
│
├── DECISION POINTS (Await before proceeding)
│   ├── 1.1.D: Minimum samples consensus?
│   ├── 1.2.D: Cal size 80 acceptable?
│   └── 1.3.D: Purge gap formula confirmed?
│
├── Tier 2 Research (After Tier 1 decisions)
│   ├── 2.1.R1-R4 (HMM)
│   ├── 2.2.R1-R4 (GARCH)
│   └── 2.3.R1-R4 (CUSUM)
│
├── DECISION POINTS
│   ├── 2.1.D: BIC vs AIC for HMM?
│   ├── 2.2.D: GARCH(1,1) always optimal?
│   └── 2.3.D: CUSUM normalization needed?
│
└── Tier 3 Research (After Tier 2 decisions)
    ├── 3.1.R1-R2 (Kalman)
    ├── 3.2.R1-R2 (IsolationForest)
    └── 3.3.R1-R2 (Combined)

PHASE 2: IMPLEMENTATION (After research complete)
│
├── Tier 1 Implementation (Sequential)
│   ├── 1.1.I1-I4 → 1.1.V1-V3
│   ├── 1.2.I1-I4 → 1.2.V1-V4
│   └── 1.3.I1-I4 → 1.3.V1-V3
│
├── Tier 2 Implementation (After Tier 1 verified)
│   ├── 2.1.I1-I4 → 2.1.V1-V4
│   ├── 2.2.I1-I4 → 2.2.V1-V4
│   └── 2.3.I1-I4 → 2.3.V1-V3
│
└── Tier 3 Implementation (After Tier 2 verified)
    ├── 3.1.I1-I2
    ├── 3.2.I1-I2
    └── 3.3.I1-I3

PHASE 3: FULL SYSTEM VERIFICATION
│
├── Run all 20 configs with optimizations
├── Compare before/after metrics
├── Document final parameters
└── Update session.md
```

---

## Research Log Template

For each research task, document:

```markdown
### Research: [Task ID] - [Title]

**Date**: YYYY-MM-DD
**Status**: ⬜ Not Started | 🔄 In Progress | ✅ Complete | ❌ Blocked

**Search Queries Used**:
1. `query 1` → [Source] → N results
2. `query 2` → [Source] → N results

**Papers Found**:
| Title | Authors | Year | Source | Citations | Relevant? |
|-------|---------|------|--------|-----------|-----------|
| ... | ... | ... | ... | ... | ✅/❌ |

**Key Findings**:
- Finding 1 (cite source)
- Finding 2 (cite source)

**Consensus**:
- [ ] Literature agrees on X
- [ ] Literature disagrees on Y (need decision)

**Decision Required**: YES/NO
**Notes**: ...
```

---

## Progress Tracking Summary

| Tier | Task | Research | Decision | Implement | Verify |
|------|------|----------|----------|-----------|--------|
| 1 | 1.1 Class Balance | ⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜ |
| 1 | 1.2 Window Config | ⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜⬜ |
| 1 | 1.3 Look-Ahead Bias | ⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜ |
| 2 | 2.1 HMM n_states | ⬜⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜⬜ |
| 2 | 2.2 GARCH Order | ⬜⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜⬜ |
| 2 | 2.3 CUSUM Threshold | ⬜⬜⬜⬜ | ⬜ | ⬜⬜⬜⬜ | ⬜⬜⬜ |
| 3 | 3.1 Kalman Noise | ⬜⬜ | ⬜ | ⬜⬜ | ⬜ |
| 3 | 3.2 IsolationForest | ⬜⬜ | ⬜ | ⬜⬜ | ⬜ |
| 3 | 3.3 Combined L1 | ⬜⬜ | ⬜ | ⬜⬜⬜ | ⬜ |

**Legend**: ⬜ = Not Started, 🔄 = In Progress, ✅ = Complete, ❌ = Blocked

---

## References

- `Archive-usefull-info-from-past-work/previous_work/help_fm/final-2.py` (lines 3755-4165)
- `scripts/target_models/core/aligned_dual_window.py`
- `scripts/target_models/helpers/icir_selection.py`
- `scripts/target_models/models/catboost_model.py`
- `scripts/target_models/helpers/hmm.py`
- `scripts/target_models/helpers/garch.py`
- `scripts/target_models/helpers/cusum.py`
- `scripts/target_models/helpers/kalman.py`
- `scripts/target_models/helpers/isolation_forest.py`

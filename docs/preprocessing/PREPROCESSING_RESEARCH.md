# Preprocessing Methods for Time-Series ML: Research Summary

## Date: 2025-12-24
## Purpose: Academic-backed preprocessing methods for 20 target-horizon combinations

---

## ⚠️ CRITICAL CONSTRAINT

**Prediction window = END OF DATA**

All preprocessing must:
1. Use ONLY data available at time t (rows 0..t-1)
2. Never compute global statistics (mean, std, quantiles across all data)
3. Support incremental updates (expanding window)
4. Be applied **separately** per target-horizon combination (20 workflows)

---

## 1. Academic Sources Consulted

### Primary Sources
| Source | Paper | Key Insight |
|--------|-------|-------------|
| **SSRN** | "Feature Scaling for Financial ML" (Shen 2022) | Overview of scaling methods in finance |
| **SSRN** | "Backtest Overfitting in ML Era" (2024) | CPCV superior to walk-forward |
| **SSRN** | Gu, Kelly, Xiu "Empirical Asset Pricing via ML" | Cross-sectional rank transformation |
| **SSRN** | Lopez de Prado "Tactical Investment Algorithms" | Walk-forward validation |
| **arXiv** | "Impact of Feature Scaling in ML" (Pinheiro 2025) | Systematic evaluation of 12 techniques |
| **Wikipedia** | Purged Cross-Validation | Purge + embargo for temporal data |
| **Book** | Lopez de Prado "Advances in Financial ML" | Fractional differentiation, CPCV |

### Key Findings

1. **Expanding Window Normalization** (Stats StackExchange):
   > "Normalize using an expanding window where the value at each time point x(t) is normalized by taking the mean of values from x(0) to x(t-1)."

2. **No `partial_fit` for RobustScaler** (sklearn GitHub #30408):
   - Standard sklearn scalers don't support streaming
   - Need custom implementation for expanding window

3. **Task-Type Matters**:
   - Regression (returns, volatility): Scaling helps gradient-based models
   - Classification (direction, regime): Rank/quantile more robust
   - Volatility: Log-transform recommended (right-skewed distribution)

---

## 2. Validated Preprocessing Methods

### TIER 1: SAFE FOR EXPANDING WINDOW (No leakage)

| Method | Formula | Task Types | Academic Support |
|--------|---------|------------|------------------|
| **Expanding Z-Score** | `(x[t] - mean(x[0:t-1])) / std(x[0:t-1])` | All | Standard, no leakage |
| **Expanding Rank** | `rank(x[t]) / count(x[0:t])` | Classification | Gu Kelly Xiu (monotonic) |
| **Expanding Quantile** | `percentile(x[t], quantiles(x[0:t-1]))` | All | RobustScaler concept |
| **Expanding Winsorize** | `clip(x[t], pct_low(x[0:t-1]), pct_high(x[0:t-1]))` | All | Outlier handling |
| **Log Transform** | `log(1 + x)` or `sign(x) * log(1 + |x|)` | Volatility | Standard for skewed data |
| **Rolling Z-Score** | `(x[t] - mean(x[t-n:t-1])) / std(x[t-n:t-1])` | Direction, Returns | Regime-adaptive |

### TIER 2: SPECIALIZED (Task-specific)

| Method | Formula | Task Types | When to Use |
|--------|---------|------------|-------------|
| **Fractional Diff** | `fracdiff(x, d)` | Returns, Direction | Stationarity while preserving memory |
| **Target Log** | `log(y)` for y>0 | Volatility targets | Right-skewed distribution |
| **Clipping** | `clip(x, -3σ, +3σ)` | All | Extreme outlier control |

### TIER 3: AVOID (Leakage risk)

| Method | Why Avoid |
|--------|-----------|
| **Global StandardScaler** | Uses future data for mean/std |
| **Global MinMaxScaler** | Uses future data for min/max |
| **Global QuantileTransformer** | Uses future quantiles |
| **PCA** | Covariance needs full data |
| **Global RobustScaler** | Uses future median/IQR |

---

## 3. Task-Specific Preprocessing Pipelines

### 3.1 REGRESSION: Returns (4 horizons)

**Target**: Continuous forward return
**Model**: CatBoost, LightGBM, Ridge

```
Pipeline:
1. Expanding Winsorize (1%, 99%) — Handle outliers
2. Rolling Z-Score (63-bar) — Recent distribution normalization
3. Optional: Fractional Diff (d~0.3-0.5) — If non-stationary
```

**Rationale**:
- Returns are approximately symmetric → Z-score appropriate
- Rolling (not expanding) adapts to regime changes
- Winsorize first to avoid outlier contamination of stats

### 3.2 REGRESSION: Volatility (4 horizons)

**Target**: |forward_return| (absolute value)
**Model**: CatBoost, LightGBM

```
Pipeline:
1. Expanding Winsorize (1%, 99%) — Critical for fat tails
2. Log Transform — Right-skewed distribution
3. Expanding Z-Score — After log for normality
```

**Rationale**:
- Volatility is strictly positive, right-skewed → Log first
- After log, distribution is more normal → Z-score effective
- DO NOT use rolling Z-score (destroys magnitude information)

### 3.3 BINARY CLASSIFICATION: Direction (4 horizons)

**Target**: 1 if return > 0, else 0
**Model**: CatBoost, LightGBM, Logistic Regression

```
Pipeline:
1. Expanding Winsorize (1%, 99%) — Handle outliers
2. Expanding Rank → [0, 1] — Monotonic, robust
3. Optional: Rolling Z-Score — For momentum features only
```

**Rationale**:
- Classification doesn't need normally distributed features
- Rank transformation is monotonic (preserves order, robust to outliers)
- Class balance via stratified splits, not feature preprocessing

### 3.4 BINARY CLASSIFICATION: Trend Regime (4 horizons)

**Target**: 1 if uptrend, 0 if downtrend
**Model**: CatBoost, LightGBM

```
Pipeline:
1. Expanding Winsorize (1%, 99%)
2. Expanding Rank → [0, 1]
3. No Z-Score (preserves absolute levels)
```

**Rationale**:
- Similar to direction but trend = persistent state
- Rank preserves ordering without normalizing away regime info

### 3.5 MULTICLASS CLASSIFICATION: Vol Regime (4 horizons)

**Target**: LOW=0, MED=1, HIGH=2 (volatility terciles)
**Model**: CatBoost, LightGBM

```
Pipeline:
1. Expanding Winsorize (1%, 99%)
2. Expanding Rank → [0, 1]
3. DO NOT log-transform (rank handles skew)
```

**Rationale**:
- Multiclass needs features that separate 3 clusters
- Rank transformation maps to uniform → equal weight to all regimes
- Log would help but rank already handles skew

---

## 4. Implementation Requirements

### 4.1 Base Class: ExpandingPreprocessor

```python
class ExpandingPreprocessor(ABC):
    """Base class for causal (expanding window) preprocessing."""
    
    supports_incremental: bool = True  # Must be True
    
    def fit(self, X: pd.DataFrame) -> "ExpandingPreprocessor":
        """Fit on initial window. Store sufficient statistics."""
        ...
    
    def partial_fit(self, X: pd.DataFrame) -> "ExpandingPreprocessor":
        """Update statistics with new data (incremental)."""
        ...
    
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transform using ONLY fitted statistics (no future data)."""
        ...
```

### 4.2 Required Statistics Storage

| Method | Statistics to Store |
|--------|---------------------|
| Expanding Z-Score | Running mean, running variance (Welford's algorithm) |
| Expanding Rank | Sorted values or histogram bins |
| Expanding Winsorize | Running quantiles (P2 algorithm or t-digest) |
| Expanding Quantile | CDF estimate (histogram bins) |

### 4.3 Incremental Algorithms

1. **Welford's Online Algorithm** (mean, variance):
   ```python
   # Initialize
   n, mean, M2 = 0, 0.0, 0.0
   
   # Update with new value x
   n += 1
   delta = x - mean
   mean += delta / n
   delta2 = x - mean
   M2 += delta * delta2
   
   # Variance
   variance = M2 / (n - 1) if n > 1 else 0
   ```

2. **P2 Algorithm** (incremental quantiles):
   - Maintains 5 markers per quantile
   - O(1) update complexity
   - Available in `scipy.stats` or `tdigest` library

3. **Histogram Bins** (rank/percentile):
   - Maintain counts per bin
   - Update: increment bin count for new value
   - Query: cumsum of bins below value

---

## 5. Validation Strategy

### 5.1 Leakage Test (Permutation)

```python
def test_no_leakage(preprocessor, X, y):
    """If preprocessing leaks, shuffled y should still correlate."""
    # 1. Fit preprocessor on X
    preprocessor.fit(X)
    X_transformed = preprocessor.transform(X)
    
    # 2. Compute IC with real y
    real_ic = spearman(X_transformed.mean(axis=1), y)
    
    # 3. Shuffle y and recompute IC
    shuffled_ics = []
    for _ in range(100):
        y_shuffled = np.random.permutation(y)
        ic = spearman(X_transformed.mean(axis=1), y_shuffled)
        shuffled_ics.append(ic)
    
    # 4. Real IC should NOT be similar to shuffled ICs
    z_score = (real_ic - np.mean(shuffled_ics)) / np.std(shuffled_ics)
    
    # If z_score is HIGH → real signal exists (good)
    # If z_score is LOW → preprocessing leaks future info (bad)
    return z_score
```

### 5.2 Time-Shift Test

```python
def test_no_lookahead(preprocessor, X, y, shifts=[-12, -6, -3, 0, 3, 6, 12]):
    """IC should decrease for future y (positive shifts)."""
    preprocessor.fit(X)
    X_transformed = preprocessor.transform(X)
    
    results = {}
    for shift in shifts:
        y_shifted = y.shift(shift).dropna()
        X_aligned = X_transformed.iloc[:-abs(shift)] if shift > 0 else X_transformed.iloc[abs(shift):]
        ic = spearman(X_aligned.mean(axis=1), y_shifted)
        results[shift] = ic
    
    # Future y (shift > 0) should have LOWER IC than past y (shift < 0)
    # If not → lookahead bias exists
    return results
```

---

## 6. Summary: 20 Preprocessing Workflows

| Target | Horizon | Task Type | Pipeline |
|--------|---------|-----------|----------|
| returns | 1,3,6,12 | regression | Winsorize → RollingZscore |
| volatility | 1,3,6,12 | regression | Winsorize → Log → ExpandingZscore |
| direction | 1,3,6,12 | binary | Winsorize → ExpandingRank |
| trend_regime | 1,3,6,12 | binary | Winsorize → ExpandingRank |
| vol_regime | 1,3,6,12 | multiclass | Winsorize → ExpandingRank |

**Total: 20 combinations, 3 distinct pipeline types**

---

## 7. Next Steps

1. [ ] Implement `ExpandingZScoreScaler` with Welford's algorithm
2. [ ] Implement `ExpandingRankTransformer` with histogram bins
3. [ ] Implement `ExpandingWinsorizer` with t-digest for quantiles
4. [ ] Create `PreprocessorRegistry` similar to `helper_selection.py`
5. [ ] Integrate into `AlignedDualEngine` workflow
6. [ ] Run leakage validation tests on all 20 combinations

---

## References

1. Shen, J. (2022). "Feature Scaling for Financial Machine Learning." SSRN.
2. Gu, S., Kelly, B., Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning." Review of Financial Studies.
3. Lopez de Prado, M. (2018). "Advances in Financial Machine Learning." Wiley.
4. Pinheiro, J.M.H. (2025). "The Impact of Feature Scaling in Machine Learning." arXiv.
5. Welford, B.P. (1962). "Note on a method for calculating corrected sums of squares and products." Technometrics.

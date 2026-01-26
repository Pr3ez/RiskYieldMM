# Dynamic Window Sizing Research Notes

**Source:** "Dynamic Optimisation of Window Sizes for Enhanced Time-Series Forecasting"
- Authors: David John, Sebastian Binnewies, Bela Stantic (Griffith University)
- Published: January 2025 (Preprint)
- Link: https://www.preprints.org/manuscript/202501.1424

---

## 1. Core Finding

**Dynamic window sizing based on volatility consistently outperforms static windows:**

| Model Type | MSE | MAE | Directional Accuracy |
|------------|-----|-----|---------------------|
| Dynamic | 0.1749 | 0.2281 | **56.77%** |
| Best Static (W=10) | 0.1933 | 0.2883 | 49.11% |

**Improvement:** ~9.5% lower MSE, ~15.6% better directional accuracy

---

## 2. Volatility Calculation Method

### Formula
```
σ_t = sqrt( (1/N_σ) * Σ(r_i - r̄)² )

where:
  r_i = log(P_i / P_{i-1})  # Log returns
  N_σ = 60 intervals        # Volatility lookback window (5 hours at 5-min data)
  r̄ = mean of log returns over N_σ
```

### Implementation
```python
def calculate_volatility(prices: pd.Series, window: int = 60) -> pd.Series:
    """Calculate rolling volatility from log returns."""
    log_returns = np.log(prices / prices.shift(1))
    volatility = log_returns.rolling(window=window).std()
    return volatility
```

**Key insight:** They use a SEPARATE lookback window (N_σ=60) just for volatility calculation, independent of the prediction window.

---

## 3. Volatility Categorization (Quartile Method)

```python
def categorize_volatility(volatility_series: pd.Series) -> pd.Series:
    """Categorize volatility into high/medium/low using quartiles."""
    Q1 = volatility_series.quantile(0.25)
    Q3 = volatility_series.quantile(0.75)
    
    conditions = [
        volatility_series > Q3,      # High volatility
        volatility_series < Q1,      # Low volatility
    ]
    choices = ['high', 'low']
    
    return np.select(conditions, choices, default='medium')
```

**Thresholds are data-driven (quartiles), not arbitrary.**

---

## 4. Optimal Windows by Volatility Category

### Empirical Results (5-minute crypto data)

| Volatility | Optimal Window Range | Best Single | Reasoning |
|------------|---------------------|-------------|-----------|
| **High** | 5-7 periods | 5 | Recent data most relevant; old data = noise |
| **Medium** | 12-20 periods | 12 | Balance recent + historical trends |
| **Low** | 25-35 periods | 25 | Stable patterns; more data improves fit |

### Theoretical Justification

**High Volatility:**
- Volatility clustering (Mandelbrot) — high vol persists but patterns change rapidly
- Older data reflects different regime, introduces noise
- Short windows capture current dynamics

**Medium Volatility:**
- Mean reversion more pronounced
- Need both recent data AND historical context for cycles
- Intermediate windows balance responsiveness vs stability

**Low Volatility:**
- Stable, gradual trends dominated by fundamentals
- Longer windows smooth noise, capture long-term patterns
- Window choice less critical (MSE nearly flat across sizes)

---

## 5. Dynamic Window Selection Logic

```python
def select_window_dynamically(current_volatility: float, 
                               Q1: float, Q3: float,
                               W_high: int = 5,
                               W_medium: int = 12,
                               W_low: int = 25) -> int:
    """Select prediction window based on current volatility."""
    if current_volatility > Q3:
        return W_high
    elif current_volatility < Q1:
        return W_low
    else:
        return W_medium
```

**Key:** This runs at EACH prediction step, not once per training session.

---

## 6. Zero-Padding for Variable Window Sizes

When window size changes dynamically, input dimensions vary. Their solution:

```python
def prepare_input(data: np.ndarray, window_size: int, max_window: int) -> np.ndarray:
    """Pad input to max_window size with zeros."""
    if window_size < max_window:
        padding = np.zeros((max_window - window_size, data.shape[1]))
        return np.vstack([padding, data[-window_size:]])
    return data[-max_window:]
```

**Example:**
- Max window = 25, Current = 5 (high vol)
- First 20 rows = zeros
- Last 5 rows = actual data

---

## 7. Testing Protocol for Window Optimization

### Phase 1: Find Optimal Windows per Category
```
For each volatility category (high, medium, low):
    Segment data by that category
    For window_size in [3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50]:
        Train model on segmented data
        Record validation MSE
    Optimal[category] = argmin(MSE)
```

### Phase 2: Grid Search Over Combinations
```
For W_high in [5, 6, 7]:
    For W_medium in [12, 15, 20]:
        For W_low in [25, 30, 35]:
            Train dynamic model with (W_high, W_medium, W_low)
            Record validation MSE
Best_combo = argmin(MSE)  # Result: (5, 12, 25)
```

---

## 8. MSE Patterns by Window Size

### Key Observations from Their Results

**High Volatility:**
- MSE increases monotonically as window grows beyond 7
- No benefit from longer windows
- Clear optimal region: 5-7

**Medium Volatility:**
- U-shaped curve: too short = underfit, too long = noise
- Clear minimum around 12-20
- Both extremes (3-7 and 40-50) perform worse

**Low Volatility:**
- Relatively flat MSE across all windows
- Slight improvement at longer windows (25-35)
- Window choice less critical — model robust

---

## 9. Applicable Insights for RiskYieldMM

### A. What We Already Do Well
- Multi-factor characterization (volatility + stationarity + drift)
- Target-type awareness (direction vs volatility vs regime)
- Holdout validation to pick best config

### B. What We Could Add

**1. Quartile-based volatility thresholds**
Current: Rule-based "high"/"low" labels
Improvement: Data-driven quartile boundaries per fold

**2. Explicit window ranges per volatility**
Current: 300-700 with adjustments
Improvement: Tighter ranges based on volatility category
```
High vol: 300-400
Med vol:  400-500
Low vol:  500-700
```

**3. Per-fold volatility characterization**
Current: Characterize once per config
Improvement: Calculate Q1/Q3 from actual fold data

**4. Faster window validation**
Paper tested 17 window sizes × 3 categories = 51 models
Then 27 combinations in grid search
Consider: Coarse-to-fine search (test 5 windows, then refine around best)

---

## 10. Limitations of the Paper

1. **Single target (price change)** — doesn't address multi-target like us
2. **LSTM-GRU only** — no gradient boosting comparison
3. **Crypto 5-min data** — our hourly data has different dynamics
4. **No feature selection** — they use fixed 46 features
5. **No conformal calibration** — pure point predictions
6. **Preprint** — not yet peer-reviewed

---

## 11. Implementation Priority

| Enhancement | Effort | Impact | Priority |
|-------------|--------|--------|----------|
| Quartile-based volatility thresholds | Low | Medium | **P1** |
| Volatility-specific window ranges | Medium | High | **P1** |
| Per-fold Q1/Q3 calculation | Low | Medium | **P2** |
| Zero-padding for variable windows | Medium | Low | **P3** |
| Grid search over window combos | High | Medium | **P3** |

---

## 12. Key Takeaway

> "The selection of an appropriate window size is paramount, as it determines the model's ability to learn from past trends and adapt to new developments, balancing the need to capture sufficient historical context without diluting the relevance of the most recent data."

**Translation for us:** Window size should ADAPT to current market conditions. High volatility = short window. Low volatility = longer window. This is more important than finding one "optimal" window.

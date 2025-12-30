# Part 4: Row-by-Row Logic

> How data flows, rolling calculations, API simulation, and state management

---

## Why Row-by-Row?

### The Problem

In Kaggle's Hull Tactical competition, inference happens **one row at a time**:
- You receive today's data
- You must predict without seeing tomorrow's data
- Rolling windows must use only past data

**Batch vectorized code fails** because it uses `pandas.rolling()` which can accidentally look ahead.

### The Solution

`RowByRowFeatureCalculator` processes data **exactly as the inference API does**:
- One row at a time
- No future leakage
- Same features during train and inference

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ROW-BY-ROW FEATURE CALCULATOR                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   INTERNAL STATE (persists across rows)                                     │
│   ├── hist_returns[]          # Last 600 returns for rolling calcs         │
│   ├── hist_volatilities[]     # Last 600 volatilities                       │
│   ├── ewma_states{}           # EWMA values per span                        │
│   ├── cumsum_vol              # Cumulative sum for expanding mean           │
│   ├── cumsum_vol_count        # Count for expanding mean                    │
│   ├── cumsum_ret              # Cumulative return sum                       │
│   ├── cumsum_ret_sq           # Cumulative squared return sum               │
│   ├── cumsum_ret_count        # Count for expanding std                     │
│   ├── current_consecutive_up  # Running up-day counter                      │
│   ├── current_consecutive_down # Running down-day counter                  │
│   └── row_count               # Total rows processed                        │
│                                                                             │
│   INPUT                                                                     │
│   └── lagged_forward_returns: float   # Today's (already-known) return      │
│                                                                             │
│   OUTPUT                                                                    │
│   └── features: Dict[str, float]      # ~400 features                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## State Variables

### Historical Data Buffers

```python
# Rolling calculations need history
self.hist_returns: List[float] = []        # Max 600 entries
self.hist_volatilities: List[float] = []   # Max 600 entries

# Why 600?
# Longest period = 252 (annual)
# Buffer = 252 + 348 margin for safety
self.max_history = 600
```

### EWMA States

```python
# EWMA requires remembering last smoothed value
self.ewma_states: Dict[int, float] = {span: None for span in ewma_spans}

# Spans used
ewma_spans = [2, 3, 5, 7, 10, 14, 20, 21, 30, 50, 60, 63, 70, 100, 120, 150, 200, 252]
```

**EWMA Update Formula:**
```python
alpha = 2 / (span + 1)
if previous_ewma is None:
    ewma = current_value
else:
    ewma = alpha * current_value + (1 - alpha) * previous_ewma
```

### Expanding Window States

```python
# Cumulative sums enable O(1) expanding calculations
self.cumsum_vol = 0.0          # Sum of volatilities
self.cumsum_vol_count = 0       # Count of valid volatilities
self.cumsum_ret = 0.0           # Sum of returns
self.cumsum_ret_sq = 0.0        # Sum of squared returns
self.cumsum_ret_count = 0       # Count of valid returns

# Expanding mean = cumsum_vol / cumsum_vol_count
# Expanding std = sqrt(E[X²] - E[X]²)
```

### Microstructure States

```python
# Consecutive day counters
self.current_consecutive_up = 0     # Reset when direction changes
self.current_consecutive_down = 0   # Reset when direction changes
```

---

## Core Method: `calculate_features_for_row()`

### Signature

```python
def calculate_features_for_row(
    self, 
    lagged_forward_returns: float, 
    is_valid: bool = True
) -> Dict[str, float]:
```

### Critical Contract

**CRITICAL:** This method calculates features using ONLY data available
up to and including the current row. No future information is used.

### Processing Steps

```
1. RECEIVE INPUT
   └── lagged_forward_returns (today's known return)

2. UPDATE HISTORY
   ├── Append to hist_returns
   ├── Calculate daily volatility = |return|
   └── Append to hist_volatilities

3. UPDATE EWMA STATES
   └── For each span: ewma_new = alpha * current + (1-alpha) * ewma_old

4. UPDATE CUMULATIVE SUMS (if is_valid)
   ├── cumsum_vol += volatility
   ├── cumsum_vol_count += 1
   ├── cumsum_ret += return
   ├── cumsum_ret_sq += return²
   └── cumsum_ret_count += 1

5. UPDATE CONSECUTIVE COUNTERS
   ├── If return > 0: consecutive_up++, consecutive_down = 0
   └── If return ≤ 0: consecutive_down++, consecutive_up = 0

6. CALCULATE FEATURES (using history only)
   ├── Rolling features (if len(hist) >= period)
   ├── EWMA features (from ewma_states)
   ├── Expanding features (from cumsums)
   ├── Lag features (from hist_returns)
   └── Distribution features (scipy.stats on history)

7. TRIM HISTORY (if > max_history)
   └── Keep only last max_history entries

8. RETURN features dict
```

---

## State Management

### Save State (after training)

```python
def save_state(self) -> Dict:
    """Save state after training to resume for validation."""
    return {
        'hist_returns': copy.deepcopy(self.hist_returns),
        'hist_volatilities': copy.deepcopy(self.hist_volatilities),
        'ewma_states': copy.deepcopy(self.ewma_states),
        'cumsum_vol': self.cumsum_vol,
        'cumsum_vol_count': self.cumsum_vol_count,
        'cumsum_ret': self.cumsum_ret,
        'cumsum_ret_sq': self.cumsum_ret_sq,
        'cumsum_ret_count': self.cumsum_ret_count,
        'current_consecutive_up': self.current_consecutive_up,
        'current_consecutive_down': self.current_consecutive_down,
        'row_count': self.row_count,
    }
```

### Load State (before validation)

```python
def load_state(self, state: Dict):
    """Resume from saved state for validation processing."""
    self.hist_returns = copy.deepcopy(state['hist_returns'])
    self.hist_volatilities = copy.deepcopy(state['hist_volatilities'])
    self.ewma_states = copy.deepcopy(state['ewma_states'])
    # ... (all other fields)
```

### Reset State (fresh start)

```python
def reset_state(self):
    """Reset all internal state for a new processing run."""
    self.hist_returns = []
    self.hist_volatilities = []
    self.ewma_states = {span: None for span in self.ewma_spans}
    self.cumsum_vol = 0.0
    self.cumsum_vol_count = 0
    # ... (all other fields)
```

---

## Usage Pattern: Train → Save → Validate

```python
# TRAINING PHASE
calculator = RowByRowFeatureCalculator()
df_train_features = calculator.process_dataframe(df_train)

# SAVE STATE (critical!)
train_state = calculator.save_state()

# VALIDATION PHASE  
calculator.load_state(train_state)  # Resume from where training ended
df_val_features = calculator.process_dataframe(df_validation)
```

**Why This Matters:**
- EWMA at row 1001 depends on all previous rows
- If you reset before validation, EWMA starts from scratch → WRONG
- Loading state continues the EWMA chain → CORRECT

---

## Rolling Window Calculations

### Pattern

```python
# Only calculate if enough history
if len(self.hist_returns) >= period:
    window = self.hist_returns[-period:]
    feature_value = calculation(window)
else:
    feature_value = np.nan  # Not enough data yet
```

### Example: Mean Historical Volatility

```python
for n in [5, 10, 21, 63, 126, 252]:
    if len(self.hist_returns) >= n:
        window = self.hist_returns[-n:]
        std = np.std(window, ddof=0)
        annualized = std * np.sqrt(252)
        features[f'mean_hist_vol_{n}'] = annualized
```

### Example: Momentum

```python
for n in PERIODS_ALL:
    if len(self.hist_returns) >= n:
        window = self.hist_returns[-n:]
        features[f'momentum_{n}d'] = sum(window)
```

---

## Expanding Window Calculations

### Expanding Mean Volatility

```python
# O(1) calculation using cumulative sums
if self.cumsum_vol_count > 0:
    features['expanding_mean_vol'] = self.cumsum_vol / self.cumsum_vol_count
```

### Expanding Standard Deviation

```python
# Uses E[X²] - E[X]² formula
if self.cumsum_ret_count >= 2:
    mean = self.cumsum_ret / self.cumsum_ret_count
    mean_sq = self.cumsum_ret_sq / self.cumsum_ret_count
    variance = mean_sq - mean**2
    if variance > 0:
        features['expanding_std_returns'] = np.sqrt(variance)
```

---

## EWMA Calculations

### Update Step

```python
alpha = 2 / (span + 1)
current_vol = abs(lagged_forward_returns)

if self.ewma_states[span] is None:
    # First value - initialize
    self.ewma_states[span] = current_vol
else:
    # EWMA update
    self.ewma_states[span] = alpha * current_vol + (1 - alpha) * self.ewma_states[span]
```

### Feature Extraction

```python
for span in self.ewma_spans:
    if self.ewma_states[span] is not None:
        features[f'ewma_vol_{span}d'] = self.ewma_states[span]
```

---

## Handling Invalid Data

### Input Validation

```python
def process_row(self, lagged_ret):
    if lagged_ret is None or np.isnan(lagged_ret):
        # Pass is_valid=False
        features = self.calculate_features_for_row(0.0, is_valid=False)
    else:
        features = self.calculate_features_for_row(float(lagged_ret), is_valid=True)
```

### When is_valid=False

- **Consecutive counters**: Still updated (direction=0)
- **Expanding windows**: NOT updated (cumsum counts unchanged)
- **Rolling windows**: Value added to history (as 0.0)
- **EWMA**: Updated with 0.0

---

## DataFrame Processing

### Batch Processing Method

```python
def process_dataframe(self, df: pl.DataFrame, verbose: bool = True) -> pl.DataFrame:
    """Process entire dataframe row-by-row."""
    self.reset_state()  # Fresh start
    
    rows_with_features = []
    for idx in range(len(df)):
        lagged_ret = df['lagged_forward_returns'][idx]
        
        if is_invalid(lagged_ret):
            features = self.calculate_features_for_row(0.0, is_valid=False)
        else:
            features = self.calculate_features_for_row(float(lagged_ret), is_valid=True)
        
        # Combine original row + new features
        row_dict = df[idx].to_dicts()[0]
        row_dict.update(features)
        rows_with_features.append(row_dict)
    
    return pl.DataFrame(rows_with_features)
```

---

## Validation: Batch vs Row-by-Row

```python
def validate_features_match(batch_df, row_by_row_df, tolerance=0.01):
    """Validate batch-processed and row-by-row features match."""
    discrepancies = {}
    
    for col in common_columns:
        batch_vals = batch_df[col].to_numpy()
        rbr_vals = row_by_row_df[col].to_numpy()
        
        rel_diff = abs(batch_vals - rbr_vals) / (abs(batch_vals) + 1e-10)
        max_diff = np.nanmax(rel_diff)
        
        if max_diff > tolerance:
            discrepancies[col] = max_diff
    
    return len(discrepancies) == 0, discrepancies
```

---

## API Simulation Pattern

For Kaggle inference:

```python
class KaggleInferenceAPI:
    def __init__(self, model, calculator_state):
        self.model = model
        self.calculator = RowByRowFeatureCalculator()
        self.calculator.load_state(calculator_state)  # Resume from training
    
    def predict(self, row_data):
        """Single row prediction - mimics competition API."""
        lagged_ret = row_data['lagged_forward_returns']
        
        # Calculate features (updates internal state)
        features = self.calculator.calculate_features_for_row(lagged_ret)
        
        # Make prediction
        feature_vector = [features[f] for f in self.model.feature_names]
        prediction = self.model.predict([feature_vector])
        
        return prediction[0]
```

---

## Summary: Key Principles

1. **One Row at a Time**: Never use vectorized operations that look ahead
2. **State Persists**: EWMA, cumsums, history carry forward
3. **Save/Load**: Critical for train→validation continuity
4. **No Future Leakage**: Only `hist_returns[-n:]` (past data)
5. **API Simulation**: Same logic during training and inference

# New L1 Helper Implementation Plan

## Executive Summary

This document outlines the implementation plan for 4 priority helper models to enhance our L1 feature pipeline. These helpers address critical gaps identified in our current system:

| Priority | Helper | Purpose | Gap Addressed |
|----------|--------|---------|---------------|
| **1** | **EVT POT** | Tail risk estimation | Mean-reverting into traps → survival |
| **2** | **OU** | Mean-reversion strength | Vibes → quantified half-life |
| **3** | **BOCPD** | Online changepoint | Better than CUSUM for regime breaks |
| **4** | **EGARCH** | Asymmetric volatility | Leverage effect (neg shocks → higher vol) |

---

## Part 1: Architecture Review

### Current Helper Interface (from `base.py`)

```
BaseHelper (ABC)
├── Properties:
│   ├── helper_name (str) - Unique identifier
│   └── supports_incremental (bool) - Can partial_fit?
├── Core Methods:
│   ├── _fit_impl(X, y) - Fit on L1 train
│   ├── _transform_impl(X) → np.ndarray - Generate features
│   └── _get_feature_names() → list[str] - Feature names
├── Public API:
│   ├── fit(X, y) → self
│   ├── transform(X) → HelperOutput
│   ├── fit_transform(X, y) → HelperOutput
│   ├── optimize(X_cal, y_cal) → dict - Hyperparameter tuning
│   └── validate(X_val, y_val) → dict - Quality metrics
└── Incremental:
    └── partial_fit(X, y) → self (if supports_incremental=True)
```

### Config Pattern (from `cusum.py`, `garch.py`)

```python
@dataclass
class MyHelperConfig(HelperConfig):
    """Configuration specific to MyHelper."""
    # Model-specific params
    param1: float = 1.0
    param2: int = 10
    # Feature column indices
    return_col_idx: int = 0
    vol_col_idx: int = 1
```

### Registration Pattern (from `ensemble.py`)

```python
# In helper_selection.py or at module level:
def create_my_helper(target: str, horizon: int, random_state: int) -> MyHelper:
    config = MyHelperConfig(
        target=target,
        horizon=horizon,
        random_state=random_state,
        prefix=f"H_{target}_{horizon}",
    )
    return MyHelper(config)

# In ensemble.py _init_helpers():
elif name == "my_helper":
    self._helpers["my_helper"] = create_my_helper(
        self.target, self.horizon, self.random_state
    )
```

---

## Part 2: Implementation Plan by Helper

---

### Helper 1: EVT POT (Extreme Value Theory - Peaks Over Threshold)

**File:** `scripts/target_models/helpers/evt_pot.py`

**Purpose:** Estimate tail risk using Generalized Pareto Distribution (GPD) fitted to exceedances over a threshold. Provides probability estimates for extreme moves.

**Math:**
```
For high threshold u, exceedances Y = X - u | X > u follow GPD:
P(Y ≤ y) = 1 - (1 + ξy/β)^(-1/ξ)

Where:
- ξ (xi) = shape parameter (tail heaviness)
- β (beta) = scale parameter
- ξ > 0 means Fréchet (heavy tail), ξ < 0 means Weibull (bounded)
```

**Key Outputs:**
- Exceedance rate λ_u (% of observations exceeding threshold)
- Shape parameter ξ (tail heaviness indicator)
- Scale parameter β
- VaR/ES proxy (tail quantile estimates)
- Tail probability features P(X > u + y) for various y

**Configuration:**
```python
@dataclass
class EVTPOTConfig(HelperConfig):
    # Threshold selection
    threshold_percentile: float = 95.0  # Use 95th percentile as threshold
    min_exceedances: int = 30  # Minimum exceedances for stable fit
    
    # Rolling window for time-varying tail
    rolling_window: int = 252  # ~1 year of daily data, 63 for 8h bars
    
    # Declustering (handle vol clustering)
    decluster: bool = True
    decluster_gap: int = 5  # Min bars between cluster peaks
    
    # Feature column index
    return_col_idx: int = 0
```

**Features Generated (~10):**
```
H_{prefix}_evt_xi              # Shape parameter (tail heaviness)
H_{prefix}_evt_beta            # Scale parameter
H_{prefix}_evt_exceedance_rate # λ_u (fraction above threshold)
H_{prefix}_evt_var95           # 95% VaR from GPD
H_{prefix}_evt_var99           # 99% VaR from GPD
H_{prefix}_evt_es95            # 95% Expected Shortfall
H_{prefix}_evt_tail_prob_2std  # P(|return| > 2σ)
H_{prefix}_evt_tail_prob_3std  # P(|return| > 3σ)
H_{prefix}_evt_tail_flag       # Binary: tail risk elevated (xi > threshold)
H_{prefix}_evt_regime          # 0=NORMAL, 1=FAT_TAIL based on xi
```

**Dependencies:**
- `scipy.stats.genpareto` - GPD fitting
- No external packages required

**Implementation Steps:**
1. Create `EVTPOTConfig` dataclass
2. Implement threshold selection (mean excess plot or fixed percentile)
3. Implement declustering (peaks over threshold with gap)
4. Implement GPD MLE fitting
5. Implement rolling window updates
6. Implement `_transform_impl` with all features
7. Add factory function to `helper_selection.py`
8. Register in `ensemble.py`

**Validation:**
- Check ξ is stable (not wildly fluctuating)
- Verify VaR backtesting (exceedance rate matches target)
- Compare to historical tail events

---

### Helper 2: OU (Ornstein-Uhlenbeck / AR(1) Mean Reversion)

**File:** `scripts/target_models/helpers/ou.py`

**Purpose:** Quantify mean-reversion strength and speed. Estimate half-life and z-score for trading signals.

**Math:**
```
AR(1) model: x_t = φ * x_{t-1} + ε_t

Mapping to OU (continuous time):
κ = -ln(φ) / Δt           # Mean reversion speed
t_{1/2} = ln(2) / κ       # Half-life (time to decay 50%)

Mean reversion requires |φ| < 1
```

**Key Outputs:**
- φ (phi) - AR(1) coefficient
- κ (kappa) - Mean reversion speed
- t_{1/2} - Half-life in bars
- z-score - Deviation from rolling mean normalized by rolling std
- Confidence in stationarity (based on φ confidence interval)

**Configuration:**
```python
@dataclass
class OUConfig(HelperConfig):
    # Rolling window for estimation
    rolling_window: int = 63  # ~3 weeks of 8h bars
    
    # Z-score parameters
    zscore_window: int = 21  # Rolling mean/std window for z-score
    
    # Half-life bounds (for gating)
    min_halflife: float = 2.0   # Don't trade if reverts too fast (noise)
    max_halflife: float = 50.0  # Don't trade if too slow (trending)
    
    # Feature column index (typically deviation from trend)
    deviation_col_idx: int = 0
    
    # What series to analyze
    analyze_spread: bool = False  # If True, use spread; else use deviation
```

**Features Generated (~8):**
```
H_{prefix}_ou_phi              # AR(1) coefficient
H_{prefix}_ou_kappa            # Mean reversion speed
H_{prefix}_ou_halflife         # Half-life in bars
H_{prefix}_ou_zscore           # Current z-score
H_{prefix}_ou_zscore_abs       # |z-score|
H_{prefix}_ou_is_stationary    # Binary: |φ| < 1 with confidence
H_{prefix}_ou_halflife_regime  # 0=TOO_FAST, 1=OPTIMAL, 2=TOO_SLOW
H_{prefix}_ou_reverting        # Binary: z * Δz < 0 (moving toward mean)
```

**Dependencies:**
- `numpy` - OLS for AR(1) estimation
- No external packages required

**Implementation Steps:**
1. Create `OUConfig` dataclass
2. Implement rolling AR(1) estimation (OLS)
3. Implement φ → κ → t_{1/2} conversion
4. Implement z-score calculation
5. Implement halflife regime classification
6. Implement `_transform_impl` with all features
7. Add factory function
8. Register in ensemble

**Validation:**
- Compare half-life to empirical decay observation
- Check φ confidence intervals
- Verify z-score predictive power (does extreme z-score predict reversal?)

---

### Helper 3: BOCPD (Bayesian Online Changepoint Detection)

**File:** `scripts/target_models/helpers/bocpd.py`

**Purpose:** Online detection of regime changes with probability distribution over run length (time since last changepoint).

**Math:**
```
Run length r_t = time since last changepoint

Recursion:
P(r_t | x_{1:t}) ∝ Σ_{r_{t-1}} P(r_t | r_{t-1}) × P(x_t | r_{t-1}) × P(r_{t-1} | x_{1:t-1})

Changepoint probability: P(r_t = 0)

Hazard function H(τ) = P(changepoint | run length = τ)
- Constant hazard: H(τ) = 1/λ (expected segment length = λ)
```

**Key Outputs:**
- Changepoint probability p_cp = P(r_t = 0)
- Expected run length E[r_t]
- Run length entropy (uncertainty in regime duration)
- Reset flag (when p_cp > threshold)

**Configuration:**
```python
@dataclass
class BOCPDConfig(HelperConfig):
    # Hazard rate (expected segment length)
    hazard_rate: float = 100.0  # Expected bars between changepoints
    
    # Observation model
    observation_model: str = "gaussian"  # or "student_t" for robustness
    student_t_df: float = 5.0  # Degrees of freedom if using t
    
    # Detection threshold
    changepoint_threshold: float = 0.3  # Flag if p_cp > this
    
    # Maximum run length to track (memory bound)
    max_run_length: int = 500
    
    # Feature column index
    return_col_idx: int = 0
```

**Features Generated (~8):**
```
H_{prefix}_bocpd_cp_prob       # P(r_t = 0) - changepoint probability
H_{prefix}_bocpd_run_length    # E[r_t] - expected run length
H_{prefix}_bocpd_run_std       # Std[r_t] - uncertainty in run length
H_{prefix}_bocpd_cp_flag       # Binary: p_cp > threshold
H_{prefix}_bocpd_regime_age    # Most likely run length (mode)
H_{prefix}_bocpd_entropy       # Entropy of run length distribution
H_{prefix}_bocpd_reset_count   # Rolling count of resets in 21 bars
H_{prefix}_bocpd_stable        # Binary: regime stable (low entropy)
```

**Dependencies:**
- `scipy.stats` - For observation model PDFs
- `numpy` - Core computation
- No external packages required (pure Python/numpy implementation)

**Implementation Steps:**
1. Create `BOCPDConfig` dataclass
2. Implement hazard function (constant hazard λ)
3. Implement observation model (Gaussian with conjugate prior, or Student-t)
4. Implement BOCPD recursion with message passing
5. Implement run length truncation (memory efficiency)
6. Implement `_transform_impl` with streaming computation
7. Add factory function
8. Register in ensemble

**Validation:**
- Compare changepoint detections to known regime breaks
- Verify p_cp spikes at obvious breaks (large moves)
- Compare detection lag to CUSUM

**Reference Implementation:**
Adams & MacKay (2007) - Bayesian Online Changepoint Detection

---

### Helper 4: EGARCH (Exponential GARCH with Asymmetry)

**File:** `scripts/target_models/helpers/egarch.py`

**Purpose:** Model volatility with leverage effect (negative returns → higher volatility). Captures asymmetric response to shocks.

**Math:**
```
EGARCH (Nelson 1991):
log(h_t) = ω + β log(h_{t-1}) + α(|z_{t-1}| - E|z|) + γ z_{t-1}

Where:
- h_t = conditional variance
- z_t = ε_t / √h_t (standardized residual)
- γ < 0 captures leverage effect (negative z → higher vol)
- No positivity constraints needed (modeling log variance)

GJR-GARCH (alternative):
h_t = ω + α ε²_{t-1} + γ 1_{ε_{t-1}<0} ε²_{t-1} + β h_{t-1}
```

**Key Outputs:**
- Conditional volatility forecast
- Asymmetry coefficient γ (leverage effect strength)
- News impact curve (response to positive vs negative shocks)
- Volatility regime with asymmetry awareness

**Configuration:**
```python
@dataclass
class EGARCHConfig(HelperConfig):
    # Model type
    model_type: str = "egarch"  # "egarch" or "gjr"
    
    # Order
    p: int = 1  # GARCH lag
    q: int = 1  # ARCH lag
    
    # Mean model
    mean: str = "Zero"
    
    # Forecasting
    forecast_horizon: int = 1
    
    # Regime thresholds
    regime_low_pct: float = 33.0
    regime_high_pct: float = 67.0
    
    # Feature column
    return_col_idx: int = 0
    rescale: float = 100.0
```

**Features Generated (~10):**
```
H_{prefix}_egarch_cond_vol      # Conditional volatility
H_{prefix}_egarch_vol_forecast  # h-step forecast
H_{prefix}_egarch_leverage      # γ coefficient (asymmetry)
H_{prefix}_egarch_news_impact   # Response to last shock
H_{prefix}_egarch_vol_shock     # Standardized residual
H_{prefix}_egarch_vol_regime    # 0=LOW, 1=MED, 2=HIGH
H_{prefix}_egarch_asymmetry_ratio # Vol after neg vs pos shock
H_{prefix}_egarch_persistence   # α + β
H_{prefix}_egarch_leverage_flag # Binary: leverage active (recent neg shock)
H_{prefix}_egarch_vol_zscore    # Current vol vs rolling mean
```

**Dependencies:**
- `arch` package (already used by GARCH helper)
- Falls back to manual EWMA if arch fails

**Implementation Steps:**
1. Create `EGARCHConfig` dataclass
2. Implement EGARCH fitting via arch package
3. Implement GJR-GARCH as alternative
4. Extract asymmetry coefficient and news impact
5. Implement fallback for failed fits
6. Implement `_transform_impl` with all features
7. Add factory function
8. Register in ensemble

**Validation:**
- Check γ < 0 (leverage effect present in crypto?)
- Compare forecasts to realized volatility
- News impact curve visualization

---

## Part 3: Integration Plan

### Step 1: Create Helper Files (Sequential)

```
scripts/target_models/helpers/
├── evt_pot.py    ← Create first (highest priority)
├── ou.py         ← Create second
├── bocpd.py      ← Create third
└── egarch.py     ← Create fourth
```

### Step 2: Update `helper_selection.py`

Add factory functions:
```python
def create_evt_pot_helper(target: str, horizon: int, random_state: int) -> EVTPOTHelper:
    ...

def create_ou_helper(target: str, horizon: int, random_state: int) -> OUHelper:
    ...

def create_bocpd_helper(target: str, horizon: int, random_state: int) -> BOCPDHelper:
    ...

def create_egarch_helper(target: str, horizon: int, random_state: int) -> EGARCHHelper:
    ...
```

### Step 3: Update `ensemble.py`

Add to `_init_helpers()`:
```python
elif name == "evt":
    self._helpers["evt"] = create_evt_pot_helper(...)
elif name == "ou":
    self._helpers["ou"] = create_ou_helper(...)
elif name == "bocpd":
    self._helpers["bocpd"] = create_bocpd_helper(...)
elif name == "egarch":
    self._helpers["egarch"] = create_egarch_helper(...)
```

Update default helper list:
```python
if helpers is None:
    helpers = [
        "if", "cusum", "garch", "hmm4", "hmm5", "kalman",
        # New helpers (add incrementally after testing each)
        # "evt", "ou", "bocpd", "egarch"
    ]
```

### Step 4: Update `__init__.py`

Add exports:
```python
from .evt_pot import EVTPOTHelper, EVTPOTConfig
from .ou import OUHelper, OUConfig
from .bocpd import BOCPDHelper, BOCPDConfig
from .egarch import EGARCHHelper, EGARCHConfig
```

### Step 5: Notebook Integration

Add to `pipeline_regeneration.ipynb`:

```python
# Cell: Test new helpers individually
from scripts.target_models.helpers.evt_pot import EVTPOTHelper, EVTPOTConfig

config = EVTPOTConfig(prefix="H_test")
helper = EVTPOTHelper(config)
helper.fit(X_train)
output = helper.transform(X_test)
print(output.features.describe())
```

---

## Part 4: Testing Strategy

### Unit Tests (per helper)

```python
# tests/test_helpers/test_evt_pot.py
def test_evt_pot_fit_transform():
    """Test basic fit/transform cycle."""
    ...

def test_evt_pot_gpd_parameters():
    """Test GPD parameter estimation accuracy."""
    ...

def test_evt_pot_var_coverage():
    """Test VaR exceedance rate matches target."""
    ...
```

### Integration Tests

```python
# Test in L1 precompute context
def test_new_helpers_in_ensemble():
    """Test new helpers work with existing ensemble."""
    ensemble = HelperEnsemble(
        target="direction",
        horizon=1,
        helpers=["garch", "evt", "ou"]  # Mix old and new
    )
    ensemble.fit(X_train)
    output = ensemble.transform(X_test)
    assert "H_direction_1_evt_xi" in output.features.columns
```

### Performance Tests

```python
def test_helper_timing():
    """Ensure new helpers don't slow L1 precompute excessively."""
    # Target: < 100ms per helper per iteration
```

---

## Part 5: Rollout Plan

### Phase 1: EVT POT (Week 1)
1. Implement `evt_pot.py`
2. Unit tests
3. Add to ensemble (disabled by default)
4. Test in notebook
5. Enable in ensemble after validation

### Phase 2: OU (Week 1-2)
1. Implement `ou.py`
2. Unit tests
3. Add to ensemble
4. Test in notebook
5. Enable in ensemble

### Phase 3: BOCPD (Week 2)
1. Implement `bocpd.py`
2. Unit tests
3. Compare to CUSUM performance
4. Add to ensemble
5. Optionally replace CUSUM or keep both

### Phase 4: EGARCH (Week 2-3)
1. Implement `egarch.py`
2. Unit tests
3. Compare to GARCH performance
4. Add to ensemble
5. Optionally replace GARCH or keep both

### Phase 5: Full Integration (Week 3)
1. Enable all new helpers in ensemble
2. Re-run full L1 precompute
3. Evaluate feature importance
4. Tune helper parameters via ICIR

---

## Part 6: Decision Points

### DP1: Replace or Augment CUSUM?
- If BOCPD significantly outperforms → **Replace**
- If both provide value → **Keep both**
- Measure: Detection lag, false positive rate

### DP2: Replace or Augment GARCH?
- If EGARCH leverage effect is significant in crypto → **Replace**
- If crypto lacks leverage effect → **Keep GARCH**
- Measure: Forecast accuracy, IC improvement

### DP3: Which helpers to enable by default?
- After testing all 4, select subset that:
  - Improves direction accuracy in optimal regime
  - Doesn't add excessive computation
  - Has consistent IC across validation windows

---

## Part 7: Feature Usage in Strategy

### EVT POT → Tail Risk Gate
```python
if evt_tail_flag or evt_xi > 0.3:  # Heavy tail detected
    skip_trade = True  # Survival mode
```

### OU → Mean Reversion Gate
```python
if ou_halflife < 2 or ou_halflife > 50:
    skip_trade = True  # Not mean-reverting or too slow
if ou_zscore_abs < 1.0:
    skip_trade = True  # Not far enough from mean
```

### BOCPD → Reset Signal
```python
if bocpd_cp_flag:
    invalidate_regime_estimates()  # Reset HMM beliefs
    reduce_position_size()  # Uncertainty high
```

### EGARCH → Asymmetry Awareness
```python
if recent_return < 0 and egarch_leverage < -0.1:
    widen_stop_loss()  # Expect higher vol after neg shock
```

---

---

## Part 8: Leakage Prevention Rules (CRITICAL)

**Context:** We already discovered major leakage in `y_vol_regime` (using full dataset quantiles).
This dropped our accuracy from 65% → 46% and Sharpe from 5.3 → -1.9. **Leakage is the enemy.**

### 8.1 Formal Leakage Definition

A feature at time $t$ is **leak-free** if it depends only on information available **at or before** $t$:

$$\text{feature}(t) = f(\{x_\tau : \tau \le t\})$$

### 8.2 Architecture Rules (Already Following)

| Rule | Status | Implementation |
|------|--------|----------------|
| Single timeframe (8h) | ✅ | No HTF leakage risk |
| Backward-only rolling windows | ✅ | CUSUM/GARCH use `[i-window:i]` |
| Chronological train/val/test | ✅ | Walk-forward framework |
| Scaler fit on train only | ✅ | `SafeScaler` in ensemble.py |

### 8.3 Helper-Specific Leakage Rules

**Every new helper MUST follow these rules:**

#### EVT POT
```python
# ❌ WRONG: Fit GPD on full dataset
gpd.fit(all_exceedances)

# ✅ CORRECT: Rolling fit ending at t
def transform(X):
    for t in range(window, n):
        exceedances = X[t-window:t][X[t-window:t] > threshold]
        xi[t], beta[t] = fit_gpd(exceedances)  # Only past data
```

#### OU / AR(1)
```python
# ❌ WRONG: Estimate phi on full series
phi = ols(x[:-1], x[1:])

# ✅ CORRECT: Rolling OLS ending at t
def transform(X):
    for t in range(window, n):
        x_past = X[t-window:t]
        phi[t] = ols(x_past[:-1], x_past[1:])  # Only data up to t
```

#### BOCPD
```python
# BOCPD is online by design (good!)
# ❌ WRONG: Tune hazard_rate using test performance
# ✅ CORRECT: Fix hazard_rate or tune on train/val only
```

#### EGARCH
```python
# ❌ WRONG: Fit EGARCH on full history
arch_model(returns).fit()

# ✅ CORRECT: Rolling fit ending at t
def transform(X):
    for t in range(window, n):
        model = arch_model(X[t-window:t])
        result = model.fit()
        params[t] = result.params  # Only past data
```

### 8.4 Implementation Checklist (Per Helper)

Before merging ANY helper, verify:

- [ ] **Rolling fit only** - Parameters estimated only on `[t-window:t]`
- [ ] **No centered windows** - All rolling operations use `[t-window:t]`, not `[t-window/2:t+window/2]`
- [ ] **No backfill** - Only forward-fill allowed for NaN handling
- [ ] **Thresholds from train** - Percentile thresholds computed on fit(), not transform()
- [ ] **Time-shift test** - Shifting target destroys performance (proves no leakage)

### 8.5 Leakage Unit Tests (Add to Each Helper)

```python
def test_no_future_leakage():
    """Verify helper uses only past data."""
    helper = MyHelper(config)
    helper.fit(X_train)
    
    # Transform should produce same result regardless of future data
    output_full = helper.transform(X_all)
    output_partial = helper.transform(X_all[:split_idx])
    
    # Features at indices < split_idx should be IDENTICAL
    assert np.allclose(
        output_full.features.iloc[:split_idx],
        output_partial.features
    ), "Future data leaked into past features!"

def test_time_shift_destroys_performance():
    """Shifting target should destroy IC (proves no leakage)."""
    helper = MyHelper(config)
    helper.fit(X_train)
    output = helper.transform(X_cal)
    
    # Original IC
    ic_original = spearman_ic(output.features, y_cal)
    
    # Shifted target (break causality)
    y_shifted = np.roll(y_cal, 10)
    ic_shifted = spearman_ic(output.features, y_shifted)
    
    # IC should collapse
    assert abs(ic_shifted) < abs(ic_original) * 0.5, \
        "IC didn't collapse with shifted target - possible leakage!"
```

### 8.6 max_input_ts Audit (Optional but Recommended)

For paranoid leakage prevention, each helper can track:

```python
class BaseHelper:
    def transform(self, X):
        # Store provenance
        self._last_transform_info = {
            'asof_ts': X.index[-1] if hasattr(X, 'index') else len(X),
            'max_input_ts': X.index[-1] if hasattr(X, 'index') else len(X),
            'lookback_window': self.config.rolling_window,
        }
        # Assert no future data
        assert self._last_transform_info['max_input_ts'] <= self._last_transform_info['asof_ts']
```

### 8.7 Current Pipeline Leakage Status

| Component | Status | Notes |
|-----------|--------|-------|
| y_vol_regime | ✅ FIXED | Now uses warmup window |
| CUSUM rolling | ✅ OK | Uses `[i-window:i]` |
| GARCH rolling | ✅ OK | Uses `[i-window:i]` |
| HMM fit | ⚠️ CHECK | Fits on L1 train window (OK if window is past-only) |
| Kalman | ✅ OK | Online filter by design |
| IsolationForest | ⚠️ CHECK | Fits on L1 train (verify no global stats) |
| SafeScaler | ✅ OK | Fit on train, apply to val/test |

---

## Summary

| Helper | Priority | Est. Effort | Key Feature | Trading Use |
|--------|----------|-------------|-------------|-------------|
| EVT POT | 1 | 4h | `evt_tail_flag` | Veto trades in fat-tail regime |
| OU | 2 | 3h | `ou_halflife` | Gate mean-reversion trades |
| BOCPD | 3 | 5h | `bocpd_cp_prob` | Reset signals, invalidate estimates |
| EGARCH | 4 | 3h | `egarch_leverage` | Asymmetric stop management |

**Total estimated implementation time:** ~15 hours

**Leakage Prevention:** All helpers will include:
1. Rolling-only parameter estimation
2. Leakage unit tests
3. Time-shift sanity test

**Next step:** Await approval to begin implementation with EVT POT.

---

*Document created: 2025-12-31*
*Updated: 2025-12-31 (Added Part 8: Leakage Prevention)*
*Author: Astra*

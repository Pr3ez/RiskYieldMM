# Validation Framework Implementation Plan

**Date:** 2025-12-24  
**Status:** Planning Phase  
**Author:** Astra

---

## 🎯 Goal

Implement production-grade validation framework **without breaking** existing pipeline:

### Primary Goals
1. **Strategy Backtesting** - Test on holdout period before live deployment
2. **Go/No-Go Validation** - Automated checks for safe deployment
3. **Performance Monitoring** - Detect degradation before it hurts
4. **Optimization Support** - Use validation for strategy tuning

### Metrics to Implement
1. **Deflated Sharpe Ratio (DSR)** - Multiple testing correction  
2. **Probability of Backtest Overfitting (PBO)** - Strategy reliability  
3. **Regime-Conditional Testing** - Performance by market state  
4. **Coverage Monitoring** - Conformal prediction health

---

## 📊 Data Budget Analysis

**Current Pipeline Configuration (after MAPIE/ACI changes):**
```
L1 (Expanding):  min_warmup = 500 rows
L2 (Sliding):    window = 500 rows
                 ├── train: 275 (55%)
                 ├── cal:   150 (30%)  ← For conformal prediction
                 ├── purge:  21
                 └── val:    54 (15%)

Total warmup before first prediction: 1,001 rows
```

```
Total Data: 5,438 rows (~5 years, 2021-2025)

┌────────────────────────────────────────────────────────────────────────┐
│  WARMUP           │ DEVELOPMENT/OPTIMIZATION    │ FINAL VALIDATION    │
│  (1,001 rows)     │ (3,937 rows ~4 years)       │ (500 rows ~4mo)     │
│  L1=500 + L2=501  │ ← USE FOR OPTIMIZATION →    │ ← NEVER TOUCH →     │
└────────────────────────────────────────────────────────────────────────┘
                    │                             │
                    ↓                             ↓
             Walk-forward iterations       FINAL GO/NO-GO TEST
             Tune hyperparameters          Only run ONCE before live
             Current: 500 iterations       Must pass all checks
```

**Actual Numbers:**
- Total rows: 5,438
- Warmup: 1,001 (L1=500 + L2 window=501)
- Available for backtest: **4,437 rows**
- Current backtest_rows: 500
- Remaining (for final validation): **3,937 rows**

### Key Principle: **Touch Final Validation ONCE**
- Development on first ~3,937 rows → iterate freely
- Final 500 rows → run ONCE before deployment
- If fails → go back to development, DO NOT re-run on validation  

---

## 🏗️ Architecture Analysis

### Current Pipeline Structure

```
scripts/
├── target_models/                    ← MAIN PIPELINE
│   ├── pipeline.py                   ← PipelineOrchestrator, TargetRunner
│   ├── core/                         
│   │   ├── window.py                 ← WalkForwardWindow, WalkForwardEngine
│   │   └── aligned_dual_window.py    ← SlidingL2Config, DualLayerWindow
│   ├── models/                       ← ModelEnsemble, CatBoost, LightGBM
│   ├── helpers/                      ← HelperEnsemble (L1)
│   ├── calibration/                  ← Conformal prediction (just added)
│   └── registry.py                   ← load_target_data(), TargetSpec
│
├── analysis/                         ← QUICK ANALYSIS (separate)
│   ├── run.py                        ← cmd_* functions
│   ├── backtest.py                   ← run_walk_forward()
│   ├── data.py                       ← create_analysis_dataset()
│   └── config.py                     ← WalkForwardConfig
│
data/
├── pipeline_results/                 ← Pipeline outputs
│   └── conformal_validation.csv
└── l2_optimization/                  ← Optuna results
    ├── baseline.csv
    └── summary.csv
```

### NEW: Validation Module Structure

```
scripts/target_models/validation/     ← NEW MODULE
├── __init__.py
├── config.py                         ← ValidationConfig, DataSplitConfig
├── strategy/                         ← Strategy testing
│   ├── __init__.py
│   ├── backtester.py                 ← StrategyBacktester (PnL simulation)
│   ├── position_sim.py               ← Position sizing simulation
│   └── pnl.py                        ← PnL calculation & metrics
├── metrics/                          ← Statistical metrics
│   ├── __init__.py
│   ├── dsr.py                        ← DeflatedSharpeRatio
│   ├── pbo.py                        ← ProbabilityBacktestOverfitting
│   └── regime.py                     ← RegimeConditionalMetrics
├── monitors/                         ← Health monitoring
│   ├── __init__.py
│   ├── coverage.py                   ← CoverageMonitor (conformal)
│   ├── drift.py                      ← DriftDetector
│   └── staleness.py                  ← ModelStalenessAlert
├── checks/                           ← Go/No-Go validation
│   ├── __init__.py
│   ├── deployment.py                 ← DeploymentChecks
│   └── thresholds.py                 ← Pass/fail thresholds
├── reports/
│   ├── __init__.py
│   ├── summary.py                    ← ValidationReport generator
│   └── plots.py                      ← Visualization
└── validate.py                       ← Main CLI entry point
```

### Data Flow (Current)

```
load_target_data() → X, y (per config)
         │
         ↓
WalkForwardEngine.iterate() → DualLayerWindow (per step)
         │
         ↓
TargetRunner.run_iteration() → TargetPrediction
         │
         ├── HelperEnsemble.fit/transform() → helper_features
         ├── ModelEnsemble.fit() → trained model
         ├── ModelEnsemble.calibrate() → isotonic calibration
         ├── ConformalClassifier/Regressor → uncertainty
         │
         ↓
PipelineOrchestrator → StepResult (all 20 targets)
         │
         ↓
PositionSizer → PositionOutput (final signal)
```

### Key Insight: WHERE to Add Validation

| Component | Purpose | Add Validation? |
|-----------|---------|-----------------|
| `pipeline.py` | Run pipeline | NO - keep pure |
| `TargetRunner` | Per-config execution | NO - keep pure |
| **NEW: `validation/`** | Post-hoc analysis | **YES** |
| `data/pipeline_results/` | Store outputs | **YES** (metrics storage) |

**Decision:** Create NEW `validation/` module. Pipeline produces predictions, validation module analyzes them AFTER.

---

## 📁 Proposed File Structure

```
scripts/target_models/validation/     ← NEW MODULE
├── __init__.py
├── config.py                         ← ValidationConfig dataclass
├── metrics/
│   ├── __init__.py
│   ├── dsr.py                        ← DeflatedSharpeRatio
│   ├── pbo.py                        ← ProbabilityBacktestOverfitting
│   └── regime.py                     ← RegimeConditionalMetrics
├── monitors/
│   ├── __init__.py
│   ├── coverage.py                   ← CoverageMonitor (conformal health)
│   ├── drift.py                      ← DriftDetector (concept/covariate)
│   └── staleness.py                  ← ModelStalenessAlert
├── reports/
│   ├── __init__.py
│   ├── summary.py                    ← ValidationSummary generator
│   └── plots.py                      ← Visualization functions
└── validate.py                       ← Main entry point
```

---

## 📐 Component Specifications

### 0. StrategyBacktester (`strategy/backtester.py`) - **NEW PRIORITY**

**Purpose:** Simulate complete trading strategy on holdout data.

**Key Features:**
- Runs pipeline predictions on validation period
- Simulates position sizing decisions
- Calculates realistic PnL with costs
- Provides go/no-go recommendation

**Interface:**
```python
@dataclass
class DataSplitConfig:
    """Control train/validation splits.
    
    Reflects actual pipeline configuration:
    - L1 min_warmup: 500 rows
    - L2 window: 500 rows (train=275, cal=150, purge=21, val=54)
    - L2 total_size: 501 (window + pred_size=1)
    """
    total_rows: int = 5438
    l1_warmup: int = 500              # L1 min_warmup
    l2_window: int = 501              # L2 total_size (500 + pred)
    validation_rows: int = 500        # Final holdout (~4 months)
    
    @property
    def warmup_rows(self) -> int:
        """Total warmup before first prediction."""
        return self.l1_warmup + self.l2_window  # 1001
    
    @property
    def available_backtest(self) -> int:
        """Rows available for walk-forward backtest."""
        return self.total_rows - self.warmup_rows  # 4437
    
    @property
    def development_rows(self) -> int:
        """Rows for development (excluding final validation)."""
        return self.available_backtest - self.validation_rows  # 3937

@dataclass
class BacktestResult:
    # Returns
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    
    # Risk metrics
    volatility: float
    var_95: float                     # Value at Risk
    cvar_95: float                    # Conditional VaR
    
    # Trade metrics
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float              # gross_profit / gross_loss
    
    # Position metrics
    avg_position_size: float
    max_position_size: float
    pct_long: float
    pct_short: float
    pct_flat: float
    
    # Costs
    total_trades: int
    total_costs: float
    cost_drag: float                  # Annual cost as % of return
    
    # Conformal
    avg_coverage: float
    avg_uncertainty: float

class StrategyBacktester:
    def __init__(
        self,
        pipeline_config: PipelineConfig,
        split_config: DataSplitConfig,
        transaction_cost: float = 0.001,  # 10 bps
        slippage: float = 0.0005,         # 5 bps
    ):
        ...
    
    def run_development(self) -> BacktestResult:
        """Run on development data (iterate freely)."""
        
    def run_validation(self) -> BacktestResult:
        """Run on holdout data (ONCE before deployment)."""
        
    def compare(
        self, 
        dev_result: BacktestResult, 
        val_result: BacktestResult,
    ) -> ValidationComparison:
        """Check for performance degradation."""
```

**Usage:**
```python
# Development iteration (run many times)
backtester = StrategyBacktester(pipeline_config, split_config)
dev_result = backtester.run_development()
print(f"Dev Sharpe: {dev_result.sharpe_ratio:.2f}")

# Final validation (run ONCE)
val_result = backtester.run_validation()
comparison = backtester.compare(dev_result, val_result)
print(f"GO/NO-GO: {comparison.recommendation}")
```

---

### 0b. DeploymentChecks (`checks/deployment.py`) - **NEW PRIORITY**

**Purpose:** Automated go/no-go decision before live deployment.

**Interface:**
```python
@dataclass
class DeploymentThresholds:
    """Pass/fail thresholds for deployment."""
    min_sharpe: float = 0.3
    max_drawdown: float = -0.20       # -20%
    min_win_rate: float = 0.45
    max_degradation: float = 0.30     # Dev→Val performance drop
    min_coverage: float = 0.85        # Conformal coverage
    max_coverage_drift: float = 0.05  # Stability

@dataclass
class CheckResult:
    name: str
    passed: bool
    value: float
    threshold: float
    message: str

@dataclass  
class DeploymentDecision:
    go: bool                          # Safe to deploy?
    checks: list[CheckResult]
    blocking_issues: list[str]
    warnings: list[str]
    recommendation: str               # "GO", "NO-GO", "REVIEW"

class DeploymentValidator:
    def __init__(self, thresholds: DeploymentThresholds):
        ...
    
    def validate(
        self,
        dev_result: BacktestResult,
        val_result: BacktestResult,
    ) -> DeploymentDecision:
        """Run all deployment checks."""
        
    def generate_report(
        self,
        decision: DeploymentDecision,
    ) -> str:
        """Generate human-readable deployment report."""
```

**Checks Performed:**
1. **Performance Check**: Sharpe > 0.3, Drawdown < 20%
2. **Degradation Check**: Val metrics within 30% of Dev
3. **Stability Check**: Consistent across time periods
4. **Regime Check**: Works in both high/low vol
5. **Coverage Check**: Conformal coverage 85-95%
6. **Cost Check**: Transaction costs don't kill returns

---

### 1. DeflatedSharpeRatio (`dsr.py`)

**Purpose:** Correct Sharpe Ratio for multiple testing and non-normality.

**Formula (Bailey & de Prado 2014):**
```python
DSR = SR × sqrt((1 - γ₃×skew/6 + γ₄×(kurt-3)/24) × T/(T-1))

where:
    SR = Sharpe Ratio
    γ₃ = E[(r - μ)³] / σ³  (skewness correction)
    γ₄ = E[(r - μ)⁴] / σ⁴  (kurtosis correction)
    T = number of observations
```

**Interface:**
```python
@dataclass
class DSRResult:
    sharpe_ratio: float           # Raw SR
    deflated_sharpe: float        # Corrected SR
    t_statistic: float            # For significance
    p_value: float                # Statistical significance
    skewness: float
    kurtosis: float
    n_trials: int                 # Number of strategies tested

def compute_dsr(
    returns: np.ndarray,
    n_trials: int = 1,            # Multiple testing adjustment
    annualization: int = 252,     # Trading days
) -> DSRResult
```

**Input:** Array of strategy returns  
**Output:** DSRResult with corrected metrics  
**Location:** `validation/metrics/dsr.py`

---

### 2. ProbabilityBacktestOverfitting (`pbo.py`)

**Purpose:** Estimate probability that best in-sample strategy is worst out-of-sample.

**Method:**
1. Run N parameter combinations (already done via Optuna)
2. For each, record (IS_rank, OOS_rank) pairs
3. PBO = fraction where best_IS = worst_OOS

**Interface:**
```python
@dataclass
class PBOResult:
    pbo: float                    # 0-1 (lower = better)
    is_overfit: bool              # pbo > 0.5
    rank_correlation: float       # Spearman(IS, OOS ranks)
    n_trials: int

def compute_pbo(
    is_scores: list[float],       # In-sample scores (e.g., IC)
    oos_scores: list[float],      # Out-of-sample scores
) -> PBOResult
```

**Data Source:** `data/l2_optimization/*.json` (we have 20 Optuna studies)  
**Location:** `validation/metrics/pbo.py`

---

### 3. RegimeConditionalMetrics (`regime.py`)

**Purpose:** Compute metrics separately for high/low volatility regimes.

**Regime Definition:**
```python
# Simple volatility-based
rolling_vol = returns.rolling(20).std() * sqrt(252)
high_vol = rolling_vol > rolling_vol.quantile(0.75)
low_vol = rolling_vol < rolling_vol.quantile(0.25)

# Or use existing vol_regime target from pipeline
```

**Interface:**
```python
@dataclass
class RegimeMetrics:
    overall: MetricSet
    high_vol: MetricSet
    low_vol: MetricSet
    normal: MetricSet
    regime_alpha: float           # Excess return in high vol
    regime_stability: float       # Correlation across regimes

@dataclass  
class MetricSet:
    ic: float | None              # Regression
    auc: float | None             # Classification
    coverage: float | None        # Conformal
    sharpe: float | None
    n_samples: int

def compute_regime_metrics(
    predictions: pd.DataFrame,    # Pipeline output
    actuals: pd.DataFrame,
    regime_col: str = 'volatility',
) -> RegimeMetrics
```

**Data Source:** Pipeline results + returns for regime classification  
**Location:** `validation/metrics/regime.py`

---

### 4. CoverageMonitor (`coverage.py`)

**Purpose:** Track conformal prediction coverage stability over time.

**Interface:**
```python
@dataclass
class CoverageHealth:
    current_coverage: float       # Last N samples
    target_coverage: float        # 0.90
    rolling_coverage: np.ndarray  # Historical
    is_healthy: bool              # abs(current - target) < 0.05
    drift_detected: bool          # Significant trend
    samples_since_alert: int

class CoverageMonitor:
    def __init__(self, target: float = 0.90, window: int = 100):
        ...
    
    def update(self, covered: bool) -> CoverageHealth:
        """Update with single observation."""
        
    def get_status(self) -> CoverageHealth:
        """Get current health status."""
```

**Integration Point:** Called from `TargetRunner._apply_conformal_prediction()`  
**Location:** `validation/monitors/coverage.py`

---

### 5. ValidationSummary (`summary.py`)

**Purpose:** Generate comprehensive validation report.

**Interface:**
```python
@dataclass
class ValidationReport:
    timestamp: datetime
    config_name: str
    dsr: DSRResult | None
    pbo: PBOResult | None
    regime: RegimeMetrics | None
    coverage: CoverageHealth | None
    warnings: list[str]
    passed: bool

def generate_summary(
    results_dir: Path,
    config_filter: list[str] | None = None,
) -> ValidationReport
```

**Output:** Markdown report + CSV metrics  
**Location:** `validation/reports/summary.py`

---

## 🔄 Integration Points

### Point 1: Post-Pipeline Analysis (MAIN)

**When:** After `run_full_pipeline()` completes  
**How:** New CLI command or function

```python
# In scripts/target_models/validate.py

from validation import (
    compute_dsr,
    compute_pbo,
    compute_regime_metrics,
    CoverageMonitor,
    generate_summary,
)

def run_validation(
    results_dir: Path = Path("data/pipeline_results"),
    configs: list[str] | None = None,
) -> ValidationReport:
    """
    Run validation on pipeline results.
    
    Called AFTER pipeline completes, NOT during.
    """
    # Load pipeline results
    # Compute DSR
    # Compute PBO (from Optuna studies)
    # Compute regime metrics
    # Check coverage
    # Generate report
```

**Why Post-Hoc:**
- Doesn't slow down pipeline
- Can re-run validation without re-running pipeline
- Clean separation of concerns

---

### Point 2: Real-Time Coverage (OPTIONAL)

**When:** During pipeline execution  
**How:** Enhance `conformal_metrics` tracking in `TargetRunner`

```python
# In pipeline.py, TargetRunner.__init__()

self.coverage_monitor = CoverageMonitor(
    target=self.conformal_config.alpha,
    window=100,
)

# In TargetRunner._apply_conformal_prediction()
if self.coverage_monitor:
    self.coverage_monitor.update(covered)
```

**Note:** Only add if coverage alerts are needed during run.

---

### Point 3: PBO from Optuna Studies

**Data Already Available:**
```
data/l2_optimization/
├── studies/                      ← Optuna SQLite DBs
│   ├── direction_1bar.sqlite
│   ├── direction_3bar.sqlite
│   └── ... (20 total)
└── results/
    ├── direction_1bar_best_params.json
    └── ... (20 total)
```

**Integration:**
```python
# Load Optuna study
import optuna
study = optuna.load_study(
    study_name=config_name,
    storage=f"sqlite:///data/l2_optimization/studies/{config_name}.sqlite"
)

# Get all trials with IS/OOS scores
trials = study.get_trials()
is_scores = [t.value for t in trials]  # Objective = IC or AUC
# OOS scores require separate tracking (need to add during optimization)
```

**Gap:** Current Optuna studies only track IS score. Need OOS for PBO.

---

## 🚀 Implementation Order (REVISED)

### Phase 0: Strategy Testing Infrastructure (Day 1-3) ⭐ **NEW PRIORITY**

**Goal:** Enable strategy backtesting on development/validation splits.

```
0.1 Create validation/ module skeleton
0.2 Implement DataSplitConfig (train/dev/val boundaries)
0.3 Implement StrategyBacktester.run_development()
0.4 Implement BacktestResult with PnL metrics
0.5 Implement position simulation with costs
0.6 Add unit tests for backtester
```

**Files Created:**
- `validation/__init__.py`
- `validation/config.py` (DataSplitConfig, DeploymentThresholds)
- `validation/strategy/__init__.py`
- `validation/strategy/backtester.py`
- `validation/strategy/pnl.py`
- `tests/test_strategy_backtest.py`

**Success Criteria:**
- Can run backtest on development period
- Get realistic PnL with transaction costs
- Sharpe, Drawdown, Win Rate calculated correctly

---

### Phase 1: Deployment Checks (Day 4-5)

**Goal:** Automated go/no-go validation.

```
1.1 Implement DeploymentThresholds dataclass
1.2 Implement DeploymentValidator.validate()
1.3 Implement StrategyBacktester.run_validation()
1.4 Implement comparison (dev vs val degradation check)
1.5 Generate deployment report
```

**Files Created:**
- `validation/checks/__init__.py`
- `validation/checks/deployment.py`
- `validation/checks/thresholds.py`
- `validation/reports/summary.py`

**Success Criteria:**
- Get GO/NO-GO recommendation
- Degradation detection (dev→val)
- Clear report with blocking issues

---

### Phase 2: Statistical Metrics (Day 6-7)

**Goal:** Add DSR and Regime analysis.

```
2.1 Implement DSRResult and compute_dsr()
2.2 Implement RegimeMetrics and compute_regime_metrics()
2.3 Integrate with BacktestResult
2.4 Add to deployment checks
```

**Files Created:**
- `validation/metrics/__init__.py`
- `validation/metrics/dsr.py`
- `validation/metrics/regime.py`

---

### Phase 3: Coverage Monitoring (Day 8)

**Goal:** Track conformal prediction health.

```
3.1 Implement CoverageMonitor
3.2 Add coverage to BacktestResult
3.3 Add coverage drift check to deployment validation
```

**Files Created:**
- `validation/monitors/__init__.py`
- `validation/monitors/coverage.py`

---

### Phase 4: PBO & Optimization Support (Day 9-10)

**Goal:** Use for hyperparameter tuning validation.

```
4.1 Update optimize_l2.py to track OOS scores per trial
4.2 Implement compute_pbo()
4.3 Add PBO to deployment report
4.4 Create optimization mode (run on dev only)
```

**Files Modified:**
- `scripts/target_models/optimize_l2.py`

**Files Created:**
- `validation/metrics/pbo.py`

---

### Phase 5: CLI & Final Integration (Day 11-12)

**Goal:** Easy-to-use command line interface.

```
5.1 Create validate.py CLI entry point
5.2 Add visualization/plots
5.3 Integration tests
5.4 Documentation
```

**Files Created:**
- `validation/reports/__init__.py`
- `validation/reports/plots.py`
- `scripts/target_models/validate.py`

---

## ⚠️ Risk Mitigation

### Risk 1: Breaking Pipeline

**Mitigation:** Validation is POST-HOC. Pipeline code changes are OPTIONAL.
- All phases run without touching pipeline.py
- Backtester uses existing pipeline output format

### Risk 2: Touching Validation Data During Development

**Mitigation:** Strict data discipline enforced in code.
```python
class StrategyBacktester:
    _validation_touched: bool = False
    
    def run_validation(self):
        if self._validation_touched:
            raise RuntimeError(
                "Validation already run! "
                "Go back to development if changes needed."
            )
        self._validation_touched = True
        # ... run validation
```

### Risk 3: OOS Data for PBO

**Mitigation:** PBO is Phase 4 (later). 
- Strategy testing works without PBO
- Can skip or defer PBO if needed

### Risk 4: Scope Creep

**Mitigation:** Strict phase boundaries.
- Each phase has clear deliverables
- Don't start Phase N+1 until Phase N tests pass
- Strategy testing (Phase 0-1) is MINIMUM VIABLE

---

## ✅ Success Criteria

| Phase | Criterion | Test |
|-------|-----------|------|
| **0** | Backtest runs on dev data | PnL curve generated |
| **0** | Realistic costs applied | Cost drag calculated |
| **0** | Sharpe/Drawdown correct | Match manual calculation |
| **1** | GO/NO-GO works | Pass/fail based on thresholds |
| **1** | Degradation detected | Val < Dev triggers warning |
| **2** | DSR computes correctly | Unit test with known returns |
| **2** | Regime splits data correctly | Sample counts sum to total |
| **3** | Coverage tracks accurately | Rolling coverage matches target |
| **4** | PBO computes correctly | Known rank pairs → expected PBO |
| **5** | CLI runs end-to-end | `python validate.py --help` works |

---

## 📋 Decision Points

**Before Phase 0:**
- [x] Confirm architecture approach (post-hoc vs inline)
- [x] Confirm strategy testing is priority (YES)
- [ ] Confirm transaction cost assumptions (10 bps?)

**Before Phase 1:**
- [ ] Review deployment thresholds (Sharpe > 0.3?)

**Before Phase 4:**
- [ ] Decide: Re-run Optuna with OOS tracking, or skip PBO initially?

---

## 🗂️ Summary

| What | Where | When |
|------|-------|------|
| **Strategy Testing** | `validation/strategy/` | **Before deployment** |
| **Deployment Checks** | `validation/checks/` | **Before deployment** |
| Validation metrics | `validation/metrics/` | Post-pipeline |
| Coverage monitoring | `validation/monitors/` | Optional real-time |
| Reports | `validation/reports/` | On-demand |
| CLI | `scripts/target_models/validate.py` | Manual trigger |

**Key Principles:**
1. **Strategy testing FIRST** - must work before other metrics
2. **Validation is a LENS** - doesn't modify pipeline
3. **Touch validation ONCE** - strict data discipline
4. **GO/NO-GO is binary** - safe to deploy or not

---

## 🎯 Usage Example (End Goal)

```bash
# During development (iterate freely)
python -m scripts.target_models.validate --mode development
# Output: Dev Sharpe=0.45, Drawdown=-12%, Win Rate=52%

# Before deployment (run ONCE)
python -m scripts.target_models.validate --mode final
# Output:
# ═══════════════════════════════════════════════════════
# DEPLOYMENT VALIDATION REPORT
# ═══════════════════════════════════════════════════════
# Development Period: 2021-04 to 2025-08 (3,438 samples)
# Validation Period:  2025-08 to 2025-12 (500 samples)
# 
# CHECKS:
# ✅ Sharpe Ratio:     0.42 > 0.30 threshold
# ✅ Max Drawdown:     -14% > -20% threshold  
# ✅ Win Rate:         51% > 45% threshold
# ✅ Degradation:      -8% (within 30% tolerance)
# ✅ Coverage:         89% (within 85-95% range)
# ⚠️ Regime Stability: High-vol 0.48, Low-vol 0.38 (warning)
#
# RECOMMENDATION: ✅ GO - Safe to deploy
# ═══════════════════════════════════════════════════════
```

---

*Plan created 2025-12-24 by Astra. Ready for review.*

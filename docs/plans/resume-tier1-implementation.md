# RESUME: Tier 1 Adaptive Window Implementation

**Created**: 2025-12-25  
**Updated**: 2025-07-20 - Verification complete! 0% skip rate achieved
**Purpose**: Complete context to resume Tier 1-3 Adaptive Optimization work  
**Status**: Tier 1 Verification COMPLETE - 2 tasks remaining (t1-1-i4, t1-3-i2)

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Research Summary](#research-summary)
3. [Implementation Status](#implementation-status)
4. [Files Modified/Created](#files-modifiedcreated)
5. [Current State (In Progress)](#current-state-in-progress)
6. [Next Steps](#next-steps)
7. [Full Task Inventory](#full-task-inventory)
8. [Technical Details](#technical-details)
9. [Key Decisions Made](#key-decisions-made)
10. [Commands Reference](#commands-reference)

---

## Problem Statement

### The Issue
- **91/300 windows (30.3%)** in `trend_regime_12bar` have only 1 class with current `train_size=275`
- CatBoost/LightGBM/LogisticRegression crash on single-class training data
- Current workaround: Skip training, return constant prediction (symptom handling)

### Root Cause: Regime Persistence
- Trend regime stays in same state for extended periods (indices ~3758-4000)
- Regime persistence >95% → expected duration ~20 bars
- With window=500, train=275: insufficient samples to guarantee both classes appear

### Solution Approach (DECIDED)
**Increase window size for regime targets, NOT skip iterations.**

| Target Type | Window | Train Ratio | Train Size | Result |
|-------------|--------|-------------|------------|--------|
| Standard (direction, returns, volatility) | 500 | 55% | 275 | ✅ Works |
| Regime (trend_regime, vol_regime) | **700** | **60%** | **420** | ✅ 0% single-class |

---

## Research Summary

### Research COMPLETE (12/12 tasks)

All research documented in: `docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md` (~2500 lines)

#### Key Research Findings

| Topic | Source | Finding |
|-------|--------|---------|
| Minimum samples/class | Silvey & Liu 2024, van Smeden 2018 | XGBoost needs ~205 EPV; 30 is practical minimum |
| Class imbalance handling | Abdelhamid & Desai 2024 | Decision threshold > SMOTE > Class weights > Baseline |
| Balance metric | Shannon Entropy | Normalized entropy (0-1), 0.5 threshold allows 80/10/10 |
| Regime persistence | Raza 2019 (SSRN) | Financial regimes have >95% persistence |
| Conformal cal size | Kladny 2025 | 150+ samples for stable 90% coverage |
| Look-ahead prevention | López de Prado 2018 | purge_gap ≥ horizon + 10 |

### Decision Points Resolved

| Decision | Question | Answer |
|----------|----------|--------|
| 1.1.D | Minimum samples per class? | **30** (practical), **50** (ideal) |
| 1.2.D | Cal size 80 acceptable? | **NO** → Use window=700 to get cal=175 |
| 1.3.D | Purge gap formula? | **purge_gap = max(21, horizon + 10)** |

---

## Implementation Status

### Tier 1: Critical (15/16 tasks complete)

| Task ID | Description | Status | Notes |
|---------|-------------|--------|-------|
| **t1-1-r1** | Min samples per class research | ✅ | Silvey & Liu 2024 |
| **t1-1-r2** | Class imbalance detection research | ✅ | Abdelhamid & Desai 2024 |
| **t1-1-r3** | Entropy balance metrics research | ✅ | Shannon normalized entropy |
| **t1-1-i1** | Create `validate_class_balance()` | ✅ | `core/validators.py` |
| **t1-1-i2** | Add class entropy computation | ✅ | `compute_class_entropy()` |
| **t1-1-i3** | Integrate into `fast_backtest.py` | ✅ | Safety net validation |
| **t1-1-i4** | Integrate into `pipeline.py` | 🟡 | PENDING (safety net) |
| **t1-2-r1** | Regime persistence research | ✅ | >95% persistence |
| **t1-2-r2** | Cal set size for conformal | ✅ | 150+ needed |
| **t1-2-r3** | Sliding vs expanding window | ✅ | Sliding correct |
| **t1-2-i1** | Add `REGIME_TARGETS` constant | ✅ | `aligned_dual_window.py` |
| **t1-2-i2** | Create `get_l2_config_for_target()` | ✅ | Returns adaptive config |
| **t1-2-i3** | Update `l1_precompute.py` | ✅ | Uses adaptive config |
| **t1-2-i4** | Regenerate regime precompute | ✅ | 8 configs × 300 files |
| **t1-2-v1** | Verify trend_regime 0 skips | ✅ | **0/200 skipped (0.0%)** |
| **t1-2-v2** | Verify vol_regime 0 skips | ✅ | **0/200 skipped (0.0%)** |
| **t1-3-r1** | Look-ahead bias research | ✅ | López de Prado |
| **t1-3-r2** | Purge/embargo best practices | ✅ | purge_gap = h + 10 |
| **t1-3-r3** | Horizon-specific leakage | ✅ | Per-horizon boundaries |
| **t1-3-i1** | Create `validate_no_lookahead()` | ✅ | `core/validators.py` |
| **t1-3-i2** | Add assertions in engine | 🟡 | PENDING |

### Tier 2: Important (0/12 complete)

| Task ID | Description | Status |
|---------|-------------|--------|
| t2-1-r1 | HMM BIC model selection research | ⬜ |
| t2-1-r2 | IC-based HMM evaluation | ⬜ |
| t2-1-r3 | HMM state stability metrics | ⬜ |
| t2-1-r4 | Financial regime detection papers | ⬜ |
| t2-2-r1 | GARCH model selection | ⬜ |
| t2-2-r2 | GARCH orders in finance | ⬜ |
| t2-2-r3 | Asymmetric GARCH extensions | ⬜ |
| t2-2-r4 | IC-based volatility evaluation | ⬜ |
| t2-3-r1 | CUSUM parameter selection | ⬜ |
| t2-3-r2 | CUSUM in finance | ⬜ |
| t2-3-r3 | ARL threshold calculation | ⬜ |
| t2-3-r4 | Adaptive CUSUM methods | ⬜ |

### Tier 3: Nice to Have (0/6 complete)

All deferred until Tier 1 & 2 complete.

---

## Files Modified/Created

### NEW Files

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/target_models/core/validators.py` | ~433 | Class balance & lookahead validation |
| `docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md` | ~2528 | Full research documentation |
| `docs/plans/resume-tier1-implementation.md` | This file | Resume context |

### MODIFIED Files

| File | Changes |
|------|---------|
| `scripts/target_models/core/aligned_dual_window.py` | Added `REGIME_TARGETS`, `REGIME_L2_CONFIG`, `STANDARD_L2_CONFIG`, `get_l2_config_for_target()`, `is_regime_target()` |
| `scripts/target_models/core/__init__.py` | Exports for validators and config functions |
| `scripts/target_models/validation/l1_precompute.py` | Uses `get_l2_config_for_target()` for adaptive window |
| `scripts/target_models/validation/fast_backtest.py` | Added `validate_class_balance` before fit, `use_adaptive_window` in BacktestConfig |

---

## Current State (In Progress)

### L1 Precompute Regeneration Status

**Running**: Regenerating 8 regime configs with window=700, train=420

| Config | Status | Iterations | Window |
|--------|--------|------------|--------|
| trend_regime_12bar | ✅ COMPLETE | 300 | 700 |
| trend_regime_1bar | ✅ COMPLETE | 300 | 700 |
| trend_regime_3bar | ✅ COMPLETE | 300 | 700 |
| trend_regime_6bar | ✅ COMPLETE | 300 | 700 |
| vol_regime_1bar | 🔄 IN PROGRESS | ~38/300 | 700 |
| vol_regime_3bar | ⏳ QUEUED | - | 700 |
| vol_regime_6bar | ⏳ QUEUED | - | 700 |
| vol_regime_12bar | ⏳ QUEUED | - | 700 |

**ETA**: ~50-60 minutes remaining for all 4 vol_regime configs

### Background Process

```bash
# PID: 154531 (running)
# Log: /tmp/precompute_regime.log
```

---

## Next Steps

### Immediate (After Precompute Completes)

1. **t1-2-v1**: Verify `trend_regime_12bar` with new window has 0 skips (was 149/300)
2. **t1-2-v2**: Verify all `vol_regime_*` with new window have 0 skips

### Short Term

3. **t1-1-i4**: Add validation to `pipeline.py` TargetRunner (safety net only)
4. **t1-3-i2**: Add lookahead assertions in `AlignedDualEngine.get_window()`

### Verification Command (Run After Precompute)

```bash
cd /media/przem/linux_data/RiskYieldMM

# Test trend_regime_12bar (should show 0 skips)
python3 -c "
from scripts.target_models.validation.fast_backtest import fast_backtest, BacktestConfig

config = BacktestConfig(
    config_name='trend_regime_12bar',
    backtest_rows=300,
    validate_class_balance=True,
    use_adaptive_window=True,
)
result = fast_backtest(config, verbose=True)
print(f'Skipped: {result.n_skipped}/{result.n_iterations} ({result.skip_rate:.1%})')
"
```

### Medium Term (Tier 2)

5. **t2-1-r1**: Research HMM model selection (BIC formula, optimal n_states)
6. **t2-2-r1**: Research GARCH model selection (is GARCH(1,1) always optimal?)
7. **t2-3-r1**: Research CUSUM parameter selection (threshold vs false alarm rate)

---

## Full Task Inventory

### Complete Task Count

| Tier | Total Tasks | Complete | In Progress | Pending |
|------|-------------|----------|-------------|---------|
| 1.1 (Class Balance) | 7 | 6 | 0 | 1 |
| 1.2 (Window Config) | 8 | 5 | 1 | 2 |
| 1.3 (Lookahead) | 7 | 5 | 0 | 2 |
| 2.1 (HMM) | 8 | 0 | 0 | 8 |
| 2.2 (GARCH) | 8 | 0 | 0 | 8 |
| 2.3 (CUSUM) | 7 | 0 | 0 | 7 |
| 3.1 (Kalman) | 4 | 0 | 0 | 4 |
| 3.2 (IsoForest) | 4 | 0 | 0 | 4 |
| 3.3 (Combined) | 5 | 0 | 0 | 5 |
| **TOTAL** | **58** | **16** | **1** | **41** |

### Progress by Phase

```
TIER 1: ████████████░░░░░░░░ 73% (16/22)
TIER 2: ░░░░░░░░░░░░░░░░░░░░ 0% (0/23)
TIER 3: ░░░░░░░░░░░░░░░░░░░░ 0% (0/13)
```

---

## Technical Details

### Adaptive Window Configurations

```python
# Standard targets (direction, returns, volatility)
STANDARD_L2_CONFIG = SlidingL2Config(
    window_size=500,
    train_ratio=0.55,   # 275 samples
    cal_ratio=0.30,     # 150 samples
    val_ratio=0.15,     # ~54 samples
    purge_gap=21,
)

# Regime targets (trend_regime, vol_regime)
REGIME_L2_CONFIG = SlidingL2Config(
    window_size=700,
    train_ratio=0.60,   # 420 samples
    cal_ratio=0.25,     # 175 samples
    val_ratio=0.15,     # ~84 samples
    purge_gap=21,
)

# Target detection
REGIME_TARGETS = frozenset({'vol_regime', 'trend_regime'})

def get_l2_config_for_target(target_name: str) -> SlidingL2Config:
    for prefix in REGIME_TARGETS:
        if target_name.startswith(prefix):
            return REGIME_L2_CONFIG
    return STANDARD_L2_CONFIG
```

### Validation Functions

```python
# Class balance validation (safety net)
def validate_class_balance(
    y_train: np.ndarray,
    min_samples_per_class: int = 30,
    min_balance_score: float = 0.5,
    warn_samples_per_class: int = 50,
) -> tuple[bool, str, ClassBalanceMetrics]:
    """
    Returns:
        (is_valid, message, metrics)
    
    Checks:
        1. At least 2 classes present
        2. Minority class has >= min_samples_per_class
        3. Balance score >= min_balance_score
    """

# Lookahead bias validation
def validate_no_lookahead(
    train_end_idx: int,
    cal_start_idx: int,
    pred_idx: int,
    horizon: int,
    purge_gap: int,
) -> tuple[bool, str, LookaheadMetrics]:
    """
    Returns:
        (is_valid, message, metrics)
    
    Checks:
        1. Train ends before prediction
        2. Purge gap >= horizon
        3. Cal does not overlap label formation
    """
```

### Config Inventory (20 Configs)

```
STANDARD CONFIGS (window=500): 12 configs
├── direction_1bar, direction_3bar, direction_6bar, direction_12bar
├── returns_1bar, returns_3bar, returns_6bar, returns_12bar
└── volatility_1bar, volatility_3bar, volatility_6bar, volatility_12bar

REGIME CONFIGS (window=700): 8 configs
├── trend_regime_1bar, trend_regime_3bar, trend_regime_6bar, trend_regime_12bar
└── vol_regime_1bar, vol_regime_3bar, vol_regime_6bar, vol_regime_12bar
```

---

## Key Decisions Made

### 1. Window Size vs Train Ratio

**Decision**: Increase BOTH window size (500→700) AND train ratio (55%→60%)

**Rationale**:
- Window=700 alone with 55% train = 385 samples → still marginal
- Window=700 with 60% train = 420 samples → sufficient for regime persistence
- Cal=175 samples (25% of 700) → adequate for conformal prediction

### 2. Validation as Safety Net (Not Primary Fix)

**Decision**: Class balance validation is SAFETY NET, not the solution

**Rationale**:
- Goal is to PREVENT single-class windows by increasing window size
- Validation catches edge cases where even 420 samples isn't enough
- Skip rate should be <5% with proper window config (not 30%+)

### 3. Validators Location

**Decision**: Create `core/validators.py` (new file)

**Rationale**:
- Separates validation concerns from window management
- Can be imported by both `fast_backtest.py` and `pipeline.py`
- Clear responsibility boundary

---

## Commands Reference

### Check Precompute Progress

```bash
# Process status
ps aux | grep -E "python.*precompute" | grep -v grep

# Log tail
tail -f /tmp/precompute_regime.log

# File counts
for d in /media/przem/linux_data/RiskYieldMM/data/precomputed/vol_regime_*; do
    echo -n "$d: "
    ls "$d"/*.parquet 2>/dev/null | wc -l
done
```

### Check Precompute Metadata

```bash
# Check window size in metadata
for config in trend_regime_12bar vol_regime_1bar; do
    echo "=== $config ==="
    cat "/media/przem/linux_data/RiskYieldMM/data/precomputed/$config/metadata.json" | jq '.l2_window_size'
done
```

### Run Verification After Precompute

```bash
cd /media/przem/linux_data/RiskYieldMM

# Quick test with 50 iterations
python3 -c "
from scripts.target_models.validation.fast_backtest import fast_backtest, BacktestConfig

for config_name in ['trend_regime_12bar', 'vol_regime_1bar']:
    config = BacktestConfig(
        config_name=config_name,
        backtest_rows=50,
        validate_class_balance=True,
        use_adaptive_window=True,
    )
    result = fast_backtest(config, verbose=False)
    print(f'{config_name}: {result.n_skipped}/{result.n_iterations} skipped ({result.skip_rate:.1%})')
"
```

### Regenerate Single Config

```bash
# If needed to regenerate a single config
python3 -c "
from scripts.target_models.validation.l1_precompute import precompute_config, L1PrecomputeConfig

cfg = L1PrecomputeConfig(backtest_rows=300)
precompute_config('trend_regime_12bar', cfg, verbose=True, force=True)
"
```

---

## Research Document Reference

**Full research documentation**: `docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md`

Key sections:
- Lines 1-200: Problem statement and research log
- Lines 200-600: Class balance research (Papers 1-4)
- Lines 600-800: Window configuration research
- Lines 800-1000: Lookahead bias prevention
- Lines 1000-1200: Trade-off analysis
- Lines 1200-1800: L1 Helper optimization research
- Lines 1800-2528: Master implementation roadmap

---

## Session Memory Reference

**Session file**: `/memories/session.md`

Contains:
- Current task status
- Verification results
- Files created/modified
- Key design decisions

---

## Lessons Learned

1. **Don't interrupt background processes** with status check commands in same terminal
2. **Use nohup for long-running precompute** jobs
3. **Validation is safety net, not primary fix** - increase window to prevent problem
4. **All 8 regime configs** need regeneration (not just 1)
5. **Check file counts** to verify precompute progress, not just logs

---

## Contact Points in Code

| Concern | Primary File | Key Function |
|---------|--------------|--------------|
| Adaptive config | `core/aligned_dual_window.py` | `get_l2_config_for_target()` |
| Class balance | `core/validators.py` | `validate_class_balance()` |
| Lookahead | `core/validators.py` | `validate_no_lookahead()` |
| Precompute | `validation/l1_precompute.py` | `precompute_config()` |
| Fast backtest | `validation/fast_backtest.py` | `fast_backtest()` |
| Config selection | `core/aligned_dual_window.py` | `REGIME_TARGETS`, `REGIME_L2_CONFIG` |

---

**Last Updated**: 2025-12-25 15:30 UTC

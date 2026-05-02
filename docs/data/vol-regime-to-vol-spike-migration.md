# Migration: `vol_regime` → `vol_spike`

**Created:** 2026-01-23  
**Status:** Planning  
**Issue:** LightGBM crashes with "Number of classes should be specified and greater than 1" because vol_regime has 3 classes but recent data only contains 2 (missing HIGH class due to regime shift)

---

## Summary of Change

| Aspect | Old (`vol_regime`) | New (`vol_spike`) |
|--------|-------------------|-------------------|
| Target Type | 3-class classification | Binary classification |
| Classes | 0=LOW, 1=MED, 2=HIGH | 0=NO_SPIKE, 1=SPIKE |
| Logic | Fixed thresholds from warmup | Relative change: `future_vol / current_vol >= 1.5` |
| Purpose | Classify current volatility level | Predict if volatility will spike 50%+ |

---

## Files to Modify

### 1. TARGET DEFINITION (Core)

#### `scripts/workflow/targets.py`
| Line | Current | Change |
|------|---------|--------|
| 271-277 | `TargetSpec(name="vol_regime", ...)` | Change to `name="vol_spike"`, `n_classes=2` |
| 278-313 | `def compute_vol_regime(...)` | Replace with `def compute_vol_spike(...)` |

```python
# Current (lines 271-277):
TargetSpec(
    name="vol_regime",
    task_type="classification",
    horizons=[1, 3, 6, 12],
    target_column="y_vol_regime",
    n_classes=3,
    compute_fn=compute_vol_regime,
)

# New:
TargetSpec(
    name="vol_spike",
    task_type="classification",
    horizons=[1, 3, 6, 12],
    target_column="y_vol_spike",
    n_classes=2,
    compute_fn=compute_vol_spike,
)
```

---

### 2. CONFIG REGISTRATIONS

#### `scripts/workflow/config.py`
| Line | Current | Change |
|------|---------|--------|
| 51 | `"vol_regime",` | `"vol_spike",` |
| 113 | Comment: `vol_regime` | Update comment |
| 206 | Comment: `vol_regime_1bar` | Update comment |

#### `scripts/target_models/config.py`
| Line | Current | Change |
|------|---------|--------|
| 81-84 | `TargetConfig(name="vol_regime", ..., n_classes=3)` | `name="vol_spike"`, `n_classes=2` |

```python
# Current (lines 81-84):
"vol_regime": TargetConfig(
    name="vol_regime",
    task_type="classification",
    target_column_pattern="y_vol_regime",
    n_classes=3,
),

# New:
"vol_spike": TargetConfig(
    name="vol_spike",
    task_type="classification",
    target_column_pattern="y_vol_spike",
    n_classes=2,
),
```

---

### 3. BACKTEST SERVICES

#### `scripts/target_models/validation/backtest/services/backtest.py`
| Line | Current | Change |
|------|---------|--------|
| 63 | `"vol_regime": {0: "LOW", 1: "MED", 2: "HIGH"}` | `"vol_spike": {0: "NO_SPIKE", 1: "SPIKE"}` |

#### `scripts/target_models/validation/backtest/adapters/data_loader.py`
| Line | Current | Change |
|------|---------|--------|
| 67 | Comment: `vol_regime: 3 (LOW/MED/HIGH)` | `vol_spike: 2 (NO_SPIKE/SPIKE)` |
| 265 | Comment: `vol_regime_*: uses y_vol_regime` | `vol_spike_*: uses y_vol_spike` |

#### `scripts/target_models/validation/backtest/models/optimal_storage.py`
| Line | Current | Change |
|------|---------|--------|
| 154-156 | `"name": "vol_regime_1bar"` | `"name": "vol_spike_1bar"` |
| 160-162 | `"name": "vol_regime_3bar"` | `"name": "vol_spike_3bar"` |
| 166-168 | `"name": "vol_regime_6bar"` | `"name": "vol_spike_6bar"` |
| 172-174 | `"name": "vol_regime_12bar"` | `"name": "vol_spike_12bar"` |

---

### 4. PIPELINE RUNTIME

#### `scripts/target_models/pipeline.py`
| Line | Current | Change |
|------|---------|--------|
| 380 | `vol_regime: dict[int, int]` | `vol_spike: dict[int, int]` |
| 395-399 | `def is_high_vol_regime(self)` | `def is_vol_spike(self)` |
| 396 | `"""Check if majority of vol_regime predictions are HIGH (2)."""` | `"""Check if any vol_spike predictions are SPIKE (1)."""` |
| 397 | `if not self.vol_regime:` | `if not self.vol_spike:` |
| 399 | `return np.mean([v == 2 for v in self.vol_regime.values()]) > 0.5` | `return any(v == 1 for v in self.vol_spike.values())` |
| 1016-1017 | `elif pred.target == "vol_regime": ensemble.vol_regime[horizon] = ...` | `elif pred.target == "vol_spike": ensemble.vol_spike[horizon] = ...` |
| 1195 | `vol_factor = 0.7 if ensemble.is_high_vol_regime() else 1.0` | `vol_factor = 0.7 if ensemble.is_vol_spike() else 1.0` |

---

### 5. METRICS TRACKING

#### `scripts/workflow/metrics_tracking.py`
| Line | Current | Change |
|------|---------|--------|
| 199 | `elif target == "vol_regime":` | `elif target == "vol_spike":` |
| 443 | `"y_vol_regime"` in list | `"y_vol_spike"` |

---

### 6. STRATEGY (Leverage Calculation)

#### `scripts/strategy/leverage.py`
| Line | Current | Change |
|------|---------|--------|
| Multiple | Uses 3-tier regime (LOW/MEDIUM/HIGH) | **Design decision needed** |

**Options for leverage.py:**
1. **Binary approach**: spike=1 → reduce leverage by 30%, spike=0 → normal
2. **Keep existing interface**: Treat spike=1 as HIGH, spike=0 as MEDIUM (ignore LOW)
3. **Separate logic**: New `get_spike_multiplier()` method

---

### 7. OPTIMIZATION SCRIPTS (Low Priority)

#### `scripts/optimization/catboost_full_optimization.py`
| Line | Current | Change |
|------|---------|--------|
| 59-61 | `elif "vol_regime" in config_name:` | `elif "vol_spike" in config_name:` |
| 528 | `elif "vol_regime" in config_name:` | `elif "vol_spike" in config_name:` |
| 664 | `"vol_regime_1bar",` | `"vol_spike_1bar",` |

#### `scripts/optimization/test_bootstrap_type.py`
| Line | Current | Change |
|------|---------|--------|
| 44-46 | `elif "vol_regime" in config_name:` | `elif "vol_spike" in config_name:` |
| 274 | `"vol_regime_1bar",` | `"vol_spike_1bar",` |

---

### 8. DATASETS

| File | Action |
|------|--------|
| `data/datasets/vol_regime_1bar.parquet` | DELETE |
| `data/datasets/vol_spike_1bar.parquet` | GENERATE (run pipeline step 2) |

---

### 9. GARCH HELPER (No Change Needed)

#### `scripts/target_models/helpers/garch.py`
| Lines | Status |
|-------|--------|
| 80, 289-291, 313, 356 | `garch_vol_regime` is a **FEATURE**, not the target |

**Note:** This file creates a `garch_vol_regime` **feature** used as input. It's separate from the `vol_regime` **target** we're replacing. No changes needed here.

---

## Verification Checklist

After all changes, verify:

- [ ] `grep -r "vol_regime" scripts/` returns only GARCH feature references
- [ ] `python scripts/main_wf.py --step 2` generates `vol_spike_1bar.parquet`
- [ ] `python scripts/run_l2_backtest.py --n-steps 10 --1bar` completes without crash
- [ ] Backtest logs show `vol_spike_1bar` instead of `vol_regime_1bar`

---

## Implementation Order

1. **Read** `targets.py:271-313` to understand current logic
2. **Implement** `compute_vol_spike()` function
3. **Update** target registration in `targets.py`
4. **Update** `workflow/config.py` TARGETS list
5. **Update** `target_models/config.py` TargetConfig
6. **Update** `backtest/services/backtest.py` label map
7. **Update** `backtest/adapters/data_loader.py` comments
8. **Update** `backtest/models/optimal_storage.py` config names
9. **Update** `pipeline.py` dataclass and methods
10. **Update** `metrics_tracking.py` references
11. **Review** `leverage.py` (design decision)
12. **Update** `optimization/*.py` scripts
13. **Delete** old dataset
14. **Regenerate** new dataset
15. **Run** test backtest

---

## Notes

- The GARCH helper's `garch_vol_regime` feature can stay as-is (it's a predictor feature, not a target)
- Legacy/backup files in `Archive-usefull-info-from-past-work/` don't need updating
- `.bak` files don't need updating

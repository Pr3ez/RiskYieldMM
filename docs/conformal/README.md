# Conformal Prediction Documentation

**Status:** ✅ Fully Implemented (2025-12-23)

---

## Quick Start

```python
from scripts.target_models.calibration import (
    ConformalClassifier,
    ConformalRegressor,
    ConformalConfig,
)

# Configuration
config = ConformalConfig(
    confidence_level=0.90,
    aci_enabled=True,
    aci_gamma=0.04,
)

# Regression
conf_reg = ConformalRegressor(fitted_model, config)
conf_reg.calibrate(X_cal, y_cal)
y_pred, intervals = conf_reg.predict(X_test)
# intervals[:, 0] = lower bounds, intervals[:, 1] = upper bounds

# Classification
conf_cls = ConformalClassifier(fitted_model, config)
conf_cls.calibrate(X_cal, y_cal)
y_pred, pred_sets = conf_cls.predict(X_test)
# pred_sets: [{0}, {1}, {0, 1}, ...] - Python sets of possible classes
```

---

## Documentation Index

| Document | Content |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System overview, integration points, technical details |
| [PHASE_1_1_MAPIE_RESEARCH.md](PHASE_1_1_MAPIE_RESEARCH.md) | MAPIE API study |
| [PHASE_1_2_ACI_RESEARCH.md](PHASE_1_2_ACI_RESEARCH.md) | ACI algorithm, gamma selection |
| [PHASE_1_3_GAP_ANALYSIS.md](PHASE_1_3_GAP_ANALYSIS.md) | Pipeline gaps identified |
| [PHASE_2_COMPATIBILITY_RESULTS.md](PHASE_2_COMPATIBILITY_RESULTS.md) | Model compatibility testing |
| [PHASE_3_CALIBRATION_RESULTS.md](PHASE_3_CALIBRATION_RESULTS.md) | Sample size analysis |
| [PHASE_4_METHODS_RESULTS.md](PHASE_4_METHODS_RESULTS.md) | LAC vs APS, EnbPI testing |
| [PHASE_5_ACI_RESULTS.md](PHASE_5_ACI_RESULTS.md) | ACI validation |
| [PHASE_6_7_IMPLEMENTATION.md](PHASE_6_7_IMPLEMENTATION.md) | Module code details |
| [PHASE_8_9_INTEGRATION.md](PHASE_8_9_INTEGRATION.md) | Pipeline integration |

---

## Key Numbers

| Parameter | Value | Reason |
|-----------|-------|--------|
| `min_cal_samples` | 100 | MAPIE minimum requirement |
| `cal_ratio` | 0.30 | 150 samples from 500-sample window |
| `aci_gamma` | 0.04 | Validated for financial data |
| `alpha_target` | 0.10 | 90% coverage target |

---

## Module Structure

```
scripts/target_models/calibration/
├── __init__.py       # Exports
├── config.py         # ConformalConfig
├── patches.py        # sklearn 1.8.0 compatibility
├── aci.py            # AdaptiveConformalInference
├── classifier.py     # ConformalClassifier (LAC)
└── regressor.py      # ConformalRegressor (EnbPI)
```

---

## Validation Results

| Task | Coverage | Target |
|------|----------|--------|
| Regression (8 configs) | 90.7-96.3% | 90% ✅ |
| Classification (binary) | ~91.5% | 90% ✅ |
| Classification (multiclass) | 89-93% | 90% ✅ |

---

## Technical Notes

1. **sklearn 1.8.0**: Requires `__sklearn_tags__()` - handled by `patches.py`
2. **ModelEnsemble**: Returns `EnsembleOutput` - wrapped by `_SklearnRegressorWrapper`
3. **ACI Updates**: Call `update_aci(y_true, intervals)` after each batch
4. **Window Config**: Updated to 55% train / 30% cal / 15% val+purge

# ML Pipeline Overview

## 11-Step Architecture

| Step | Purpose | Output | Reference |
|------|---------|--------|-----------|
| 0 | Fetch Bybit data | `fetchingByBit/*-8h-bybit-linear/` | [main_wf.py#L120-200](../notebooks/main_wf.py) |
| 1a | Merge raw data | `data/merged_8h_raw.parquet` | [main_wf.py#L200-240](../notebooks/main_wf.py) |
| 1b | Feature engineering | `data/features_8h.parquet` | [main_wf.py#L240-280](../notebooks/main_wf.py) |
| 2 | Target generation | `data/analysis_8h.parquet` | [main_wf.py#L280-370](../notebooks/main_wf.py) |
| 3 | Feature optimization | `data/features_8h_optimized_{target}_{horizon}bar.parquet` | [main_wf.py#L370-490](../notebooks/main_wf.py) |
| 4 | Dataset matrix | `data/datasets/{target}_{horizon}bar.parquet` | [main_wf.py#L490-560](../notebooks/main_wf.py) |
| 5 | IC/ICIR analysis | `data/analysis/results/ic_*.csv` | [main_wf.py#L560-590](../notebooks/main_wf.py) |
| 6 | Feature importance | `data/analysis/results/{mdi,mda}_importance.csv` | [main_wf.py#L590-620](../notebooks/main_wf.py) |
| 7 | Cross-validation | `data/analysis/results/cv_results.csv` | [main_wf.py#L620-650](../notebooks/main_wf.py) |
| 8 | L1 precompute | `data/precomputed/{config}/*.parquet` | [main_wf.py#L650-810](../notebooks/main_wf.py) |
| 9 | Dataset assembly | `data/precomputed/{config}/assembled.parquet` | [main_wf.py#L830-900](../notebooks/main_wf.py) |
| 9b | Combined datasets | `data/combined_datasets/{config}.parquet` | [main_wf.py#L945-980](../notebooks/main_wf.py) |
| 10 | L2 backtest | `data/l2_backtest_results/` | [main_wf.py#L985-1091](../notebooks/main_wf.py) |

---

## Key Config Modes

| Mode | Configs | Use Case |
|------|---------|----------|
| `1bar` | 7 configs | Fast testing (WORKFLOW_HORIZONS=[1]) |
| `reduced` | 14 configs | Balanced (horizons 1,3) |
| `all` | 28 configs | Full optimization (horizons 1,3,6,12) |

Config naming: `{target}_{horizon}bar` (e.g., `direction_1bar`)

---

## Targets (7 total)

| Target | Type | Reference |
|--------|------|-----------|
| `direction` | Classification (3-class) | [config.py#L46](../scripts/workflow/config.py) |
| `volatility` | Regression | [config.py#L47](../scripts/workflow/config.py) |
| `vol_regime` | Classification (3-class) | [config.py#L48](../scripts/workflow/config.py) |
| `trend_regime` | Classification (2-class) | [config.py#L49](../scripts/workflow/config.py) |
| `first_extreme` | Classification (binary) | [config.py#L50](../scripts/workflow/config.py) - uses 15m intrabar |
| `time_to_extreme` | Regression (0-31 bars) | [config.py#L51](../scripts/workflow/config.py) |
| `vol_to_extreme` | Regression | [config.py#L52](../scripts/workflow/config.py) |

---

## Data Flow

```
Bybit API → 8h bars → Features → Targets → Optimization → L1 precompute → L2 backtest
                                    ↓
                           per-target causal optimization
                           (expanding window + shift(1))
```

---

## Key Files

| Purpose | Location |
|---------|----------|
| Main workflow | [notebooks/main_wf.py](../notebooks/main_wf.py) |
| Workflow config | [scripts/workflow/config.py](../scripts/workflow/config.py) |
| L2 backtest facade | [l2_backtest_sync.py](../scripts/target_models/validation/l2_backtest_sync.py) |
| Backtest service | [backtest/services/backtest.py](../scripts/target_models/validation/backtest/services/backtest.py) |

---

## Causality Verification

Step 3 optimization uses causal methods:
- `ExpandingRankNormalizer` with `shift(1)` - [main_wf.py#L380](../notebooks/main_wf.py)
- Winsorize/Interactions also use `shift(1)`
- L1 snapshot + quality gate in Step 8 - [main_wf.py#L776-796](../notebooks/main_wf.py)

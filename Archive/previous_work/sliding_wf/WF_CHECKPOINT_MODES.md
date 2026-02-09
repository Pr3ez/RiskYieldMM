# Walk-Forward Checkpoint Modes

## Overview

The walk-forward script (`sliding_window_evidence_based56.py`) supports three run modes:

### Mode 1: Fresh Start (Default)
```python
USE_CHECKPOINT_RESUME = False
USE_FEATURES_ONLY_RESUME = False
```
- Runs from iteration 1
- TP/FP start at 0
- Hull scores build from scratch (HullB shows at iter 60, HullF at iter 230)
- All features computed from scratch (less accurate early, improves over time)

### Mode 2: Full Resume
```python
USE_CHECKPOINT_RESUME = True
USE_FEATURES_ONLY_RESUME = False  # ignored when USE_CHECKPOINT_RESUME=True
```
- Continues from checkpoint iteration
- TP/FP resume from checkpoint values
- Hull scores continue building
- Features use accumulated history

### Mode 3: Features-Only Resume (Hybrid)
```python
USE_CHECKPOINT_RESUME = False
USE_FEATURES_ONLY_RESUME = True
```
- Runs from iteration 1 (fresh metrics)
- TP/FP start at 0 (clean metrics)
- Hull scores build from scratch (clean Sharpe)
- BUT: Calibrators loaded from checkpoint (better probability calibration)
- BUT: rolling_pred_types loaded (past_ratio gate works immediately)

## When to Use Each Mode

| Mode | Use Case |
|------|----------|
| Fresh Start | Final competition submission, clean metrics needed |
| Full Resume | Development, continue interrupted run |
| Features-Only | Best of both: accurate features + clean metrics |

## Data Flow Summary

### Feature-Related (kept in Features-Only mode):
- `cb_calibrator`, `lgb_calibrator` - probability calibration
- `meta_stacker` - ensemble combination
- `rolling_pred_types` - past_ratio gate calculation
- `CATBOOST_DIR_PARAMS`, `LIGHTGBM_DIR_PARAMS` - tuned hyperparameters

### Metrics-Related (reset in Features-Only mode):
- `benchmark_tracker` (TP/FP/TN/FN)
- `baseline_tracker` (TP/FP/TN/FN)
- `hull_scorer_benchmark.history`
- `hull_scorer_baseline.history`
- `walkforward_predictions`
- `walkforward_iterations`

## Quick Reference

```bash
# Fresh start (clean metrics, features build from scratch)
# Set in script: USE_CHECKPOINT_RESUME = False, USE_FEATURES_ONLY_RESUME = False
python sliding_window_evidence_based56.py

# Features-only resume (clean metrics, pre-trained calibrators)
# Set in script: USE_CHECKPOINT_RESUME = False, USE_FEATURES_ONLY_RESUME = True
# Requires: wf_checkpoint.pkl exists
python sliding_window_evidence_based56.py

# Full resume (continue from where you left off)
# Set in script: USE_CHECKPOINT_RESUME = True
# Requires: wf_checkpoint.pkl exists
python sliding_window_evidence_based56.py
```

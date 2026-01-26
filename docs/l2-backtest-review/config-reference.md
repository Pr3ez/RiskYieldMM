# Configuration Reference

## Workflow Config Location

[scripts/workflow/config.py](../scripts/workflow/config.py)

---

## Tunable Parameters (L2BacktestDefaults)

### Walk-Forward Settings

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `train_window` | 500 | Samples in training window | [L218](../scripts/workflow/config.py) |
| `step_size` | 1 | Bars between predictions | [L219](../scripts/workflow/config.py) |
| `n_steps` | None | Limit to last N steps (None=all) | [L220](../scripts/workflow/config.py) |

### Split Ratios

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `train_ratio` | 0.55 | Training portion | [L223](../scripts/workflow/config.py) |
| `val_ratio` | 0.15 | Validation portion | [L224](../scripts/workflow/config.py) |
| `cal_ratio` | 0.30 | Calibration portion | [L225](../scripts/workflow/config.py) |
| `embargo_bars` | 24 | Gap between splits | [L228](../scripts/workflow/config.py) |

### Ensemble Weights

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `cb_weight` | 0.30 | CatBoost weight | [L237](../scripts/workflow/config.py) |
| `lgb_weight` | 0.30 | LightGBM weight | [L238](../scripts/workflow/config.py) |
| `lstm_weight` | 0.25 | LSTM weight | [L239](../scripts/workflow/config.py) |
| linear_weight | 0.15 | Auto: `1 - sum(others)` | computed |

### Adaptive Weights (MWU)

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `use_adaptive_weights` | True | Enable MWU | [L243](../scripts/workflow/config.py) |
| `adaptive_lookback` | 50 | Recent steps to evaluate | [L244](../scripts/workflow/config.py) |
| `adaptive_learning_rate` | 0.1 | Weight adjustment speed | [L245](../scripts/workflow/config.py) |
| `adaptive_min_weight` | 0.05 | Floor per model | [L246](../scripts/workflow/config.py) |

### CatBoost

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `cb_learning_rate` | 0.03 | Learning rate | [L249](../scripts/workflow/config.py) |
| `cb_l2_leaf_reg` | 5.0 | L2 regularization | [L250](../scripts/workflow/config.py) |

### LightGBM

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `lgb_learning_rate` | 0.03 | Learning rate | [L253](../scripts/workflow/config.py) |
| `lgb_reg_lambda` | 3.0 | L2 regularization | [L254](../scripts/workflow/config.py) |
| `lgb_min_child_samples` | 20 | Min samples in leaf | [L255](../scripts/workflow/config.py) |

### LSTM

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `lstm_hidden_size` | 64 | Hidden layer size | [L258](../scripts/workflow/config.py) |
| `lstm_num_layers` | 2 | Number of layers | [L259](../scripts/workflow/config.py) |
| `lstm_lr` | 0.001 | Learning rate | [L260](../scripts/workflow/config.py) |
| `lstm_epochs` | 100 | Training epochs | [L261](../scripts/workflow/config.py) |
| `lstm_batch_size` | 32 | Batch size | [L262](../scripts/workflow/config.py) |
| `lstm_dropout` | 0.2 | Dropout rate | [L263](../scripts/workflow/config.py) |
| `lstm_seq_len` | 20 | Sequence length | [L264](../scripts/workflow/config.py) |

### Optuna

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `enable_optuna` | True | Enable tuning | [L275](../scripts/workflow/config.py) |
| `n_optuna_trials` | 15 | Trials per step | [L276](../scripts/workflow/config.py) |
| `optuna_timeout` | 30.0 | Timeout (seconds) | [L277](../scripts/workflow/config.py) |
| `optuna_prune` | True | Enable pruning | [L278](../scripts/workflow/config.py) |

### Conformal Prediction

| Param | Default | Description | Line |
|-------|---------|-------------|------|
| `conformal_alpha` | 0.1 | 90% confidence | [L267](../scripts/workflow/config.py) |

---

## Per-Model Config Override

Each model can have custom settings:

```python
cb_config: dict | None   # Override CatBoost settings
lgb_config: dict | None  # Override LightGBM settings
lstm_config: dict | None # Override LSTM settings
linear_config: dict | None # Override Linear settings
```

Per-model config fields:
- `train_window`: Custom window size
- `feature_selection`: `"importance"` | `"variance"` | `"none"`

Reference: [config.py#L285-289](../scripts/workflow/config.py)

---

## L1 Precompute Config

| Param | Default | Description |
|-------|---------|-------------|
| `L1_CONFIG_MODE` | "1bar" | `1bar` / `reduced` / `all` |
| `L1_ROWS` | None | Iterations (None=auto) |
| `L1_HELPERS` | 10 helpers | Feature generators |
| `EXPECTED_FEATURES` | 91 | Expected feature count |

Reference: [config.py#L103-120](../scripts/workflow/config.py)

---

## L1 Helpers List

```python
["if", "cusum", "garch", "hmm4", "hmm5", 
 "kalman", "evt", "ou", "bocpd", "egarch"]
```

Reference: [config.py#L115-125](../scripts/workflow/config.py)

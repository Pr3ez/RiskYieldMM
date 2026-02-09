# Part 5: Multi-Config Tracking

## Overview

The Walk-Forward system tracks **48+ parallel configurations** simultaneously, each with different model/calibration/threshold combinations. This enables adaptive selection based on recent performance.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MULTI-CONFIG TRACKING SYSTEM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CONFIG GRID (48 combinations):                                              │
│                                                                              │
│  Model:       [single, ensemble]          ×2                                │
│  Calibration: [platt, isotonic, none]     ×3                                │
│  Threshold:   [quantile_match, youden_j, class_balanced, 0.5]  ×4          │
│  AUC Adjust:  [True, False]               ×2                                │
│  Regime Thr:  [True, False]               ×2                                │
│  Window:      [original, shrunk]          ×2 (optional)                     │
│                                                                              │
│  Each iteration: ALL configs evaluated → TP/FP tracked → Best selected     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Config Grid Definition

```python
# From wf_config.py
CONFIG_GRID = {
    'model': ['single', 'ensemble'],           # CB only vs CB+LGB
    'calibration': ['platt', 'isotonic', 'none'],
    'threshold': ['quantile_match', 'youden_j', 'class_balanced', 'fixed'],
    'auc_adjust': [True, False],               # AUC confidence adjustment
    'regime_thr': [True, False],               # Regime-specific thresholds
    'window': ['original', 'shrunk'],          # Train window variant
}

# Generate all combinations
from itertools import product

def generate_config_combinations(grid):
    keys = list(grid.keys())
    values = [grid[k] for k in keys]
    configs = []
    
    for combo in product(*values):
        config = dict(zip(keys, combo))
        # Generate config name: e.g., "ens_pla_qua_auc1_reg0_wo"
        config_name = f"{config['model'][:3]}_{config['calibration'][:3]}_{config['threshold'][:3]}_auc{int(config['auc_adjust'])}_reg{int(config['regime_thr'])}_w{config['window'][0]}"
        configs.append({
            'name': config_name,
            **config
        })
    
    return configs

ALL_CONFIGS = generate_config_combinations(CONFIG_GRID)  # 48+ configs
```

## Config Results Tracking

```python
# Storage structure per config
config_results = {cfg['name']: {
    'config': cfg,
    'predictions': [],                      # Full history
    'rolling_tp': 0,                        # True positives
    'rolling_fp': 0,                        # False positives
    'rolling_tn': 0,                        # True negatives
    'rolling_fn': 0,                        # False negatives
    'total_correct': 0,
    'total_predictions': 0,
    'rolling_pred_types': deque(maxlen=ROLLING_WINDOW_SIZE),  # Recent outcomes
} for cfg in ALL_CONFIGS}
```

## Per-Iteration Config Evaluation

```python
for cfg in ALL_CONFIGS:
    cfg_name = cfg['name']
    
    # Select probability based on model config
    if cfg['model'] == 'single':
        if cfg['calibration'] == 'none':
            cfg_prob = cb_pred_probs[0]          # Raw CB
        else:
            cfg_prob = cb_pred_probs_cal[0]      # Calibrated CB
    else:
        # Ensemble: combine CB + LGB
        if cfg['calibration'] == 'none':
            cfg_prob = (cb_pred_probs[0] + lgb_pred_probs[0]) / 2.0
        else:
            cfg_prob = (cb_pred_probs_cal[0] + lgb_pred_probs_cal[0]) / 2.0
    
    # Calculate threshold based on config
    if cfg['threshold'] == 'quantile_match':
        pos_rate = np.mean(y_cal_dir)
        cfg_threshold = np.percentile(cfg_cal_probs, (1 - pos_rate) * 100)
    elif cfg['threshold'] == 'youden_j':
        cfg_threshold = calculate_youden_threshold(cfg_cal_probs, y_cal_dir)
    elif cfg['threshold'] == 'class_balanced':
        cfg_threshold = np.mean(y_cal_dir)
    else:
        cfg_threshold = 0.5
    
    # Apply AUC adjustment
    if cfg['auc_adjust']:
        auc_conf = max(0, min(1, (cb_val_auc - 0.5) * 2))
        auc_uncert = 1.0 - auc_conf
        auc_adj = (0.5 - cfg_threshold) * auc_uncert * 0.5
        cfg_threshold += auc_adj
    
    # Apply regime adjustment
    if cfg['regime_thr']:
        vol_regime = classify_vol_regime(pred_vol_preds[0])
        regime_adj = REGIME_THRESHOLD_ADJUSTMENTS.get(vol_regime, 0.0)
        cfg_threshold += regime_adj
    
    # Clamp threshold
    cfg_threshold = max(0.35, min(0.75, cfg_threshold))
    
    # Make prediction
    cfg_pred = 1 if cfg_prob >= cfg_threshold else 0
    
    # Classify result
    if cfg_pred == 1 and actual_label == 1:
        cfg_result = 'TP'
    elif cfg_pred == 0 and actual_label == 0:
        cfg_result = 'TN'
    elif cfg_pred == 1 and actual_label == 0:
        cfg_result = 'FP'
    else:
        cfg_result = 'FN'
    
    # Update results
    config_results[cfg_name]['rolling_pred_types'].append(cfg_result)
    config_results[cfg_name]['predictions'].append({
        'iteration': iteration,
        'prob': cfg_prob,
        'threshold': cfg_threshold,
        'pred': cfg_pred,
        'actual': actual_label,
        'result': cfg_result,
    })
    
    # Update counters
    if cfg_result == 'TP':
        config_results[cfg_name]['rolling_tp'] += 1
        config_results[cfg_name]['total_correct'] += 1
    elif cfg_result == 'TN':
        config_results[cfg_name]['rolling_tn'] += 1
        config_results[cfg_name]['total_correct'] += 1
    elif cfg_result == 'FP':
        config_results[cfg_name]['rolling_fp'] += 1
    else:
        config_results[cfg_name]['rolling_fn'] += 1
    
    config_results[cfg_name]['total_predictions'] += 1
    
    # Update scorer
    config_scorer.update(cfg_name, iteration, 
                         tp=1 if cfg_result == 'TP' else 0,
                         fp=1 if cfg_result == 'FP' else 0,
                         tn=1 if cfg_result == 'TN' else 0,
                         fn=1 if cfg_result == 'FN' else 0)
```

## AdaptiveMultiPeriodScorerV3

The scorer tracks performance across multiple time periods and computes composite scores:

```python
# wf_adaptive_scorer.py
class AdaptiveMultiPeriodScorerV3:
    """
    Multi-period scoring with EMA smoothing and momentum signals.
    """
    def __init__(self, 
                 min_samples_per_window=3,
                 switch_threshold=0.20,
                 leave_threshold=0.25,
                 declining_threshold=0.15,
                 min_score_floor=2.0,
                 switch_cooldown=5):
        
        self.config_data = {}           # Per-config tracking
        self.current_config = None      # Currently selected config
        self.switch_history = []        # Config switch log
        self.actual_ratio_history = []  # Rolling ratio over time
        
        # EMA spans for smoothing
        self.lt_ema_span = 30           # Long-term EMA
        self.st_ema_span = 7            # Short-term EMA
    
    def update(self, config_name, iteration, tp, fp, tn, fn):
        """Update config with new prediction outcome."""
        if config_name not in self.config_data:
            self.config_data[config_name] = {
                'results': [],
                'tp_cumulative': 0,
                'fp_cumulative': 0,
            }
        
        data = self.config_data[config_name]
        data['results'].append({
            'iteration': iteration,
            'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
        })
        data['tp_cumulative'] += tp
        data['fp_cumulative'] += fp
```

## Composite Score Calculation

```python
def get_composite_score(self, config_name, current_iteration):
    """
    Calculate composite score from multiple signals.
    """
    data = self.config_data.get(config_name, {})
    results = data.get('results', [])
    
    if len(results) < 10:
        return {'final_score': 0, 'momentum_signal': 'WARMUP'}
    
    # Calculate ratios over different periods
    def calc_ratio(results_slice):
        tp = sum(r['tp'] for r in results_slice)
        fp = sum(r['fp'] for r in results_slice)
        return tp / fp if fp > 0 else (3.0 if tp > 0 else 1.0)
    
    # Period ratios
    ratio_30d = calc_ratio(results[-30:]) if len(results) >= 30 else 1.0
    ratio_60d = calc_ratio(results[-60:]) if len(results) >= 60 else 1.0
    ratio_all = calc_ratio(results)
    
    # EMA smoothed ratio
    ratios = [calc_ratio([r]) for r in results]
    lt_ema = self._calculate_ema(ratios, self.lt_ema_span)
    st_ema = self._calculate_ema(ratios, self.st_ema_span)
    
    # Momentum signal
    if st_ema > lt_ema * 1.05:
        momentum_signal = 'BULLISH'
    elif st_ema < lt_ema * 0.95:
        momentum_signal = 'BEARISH'
    else:
        momentum_signal = 'NEUTRAL'
    
    # Composite score (weighted average)
    final_score = (
        0.4 * ratio_30d +
        0.3 * ratio_60d +
        0.2 * ratio_all +
        0.1 * st_ema
    )
    
    return {
        'final_score': final_score,
        'ratio_30d': ratio_30d,
        'ratio_60d': ratio_60d,
        'ratio_all': ratio_all,
        'lt_ema': lt_ema,
        'st_ema': st_ema,
        'momentum_signal': momentum_signal,
    }
```

## Config Selection

### Standard Selection

```python
def select_best_config(self, current_iteration):
    """
    Select config with highest composite score.
    """
    best_config = None
    best_score = -float('inf')
    selection_info = {}
    
    for config_name in self.config_data:
        score_data = self.get_composite_score(config_name, current_iteration)
        
        if score_data['final_score'] > best_score:
            best_score = score_data['final_score']
            best_config = config_name
            selection_info = score_data
    
    # Handle config switch
    if best_config != self.current_config:
        self.switch_history.append({
            'iteration': current_iteration,
            'from': self.current_config,
            'to': best_config,
            'score': best_score,
        })
        self.current_config = best_config
    
    return best_config, selection_info
```

### Regime-Adaptive Selection

```python
def select_regime_adapted_config(self, current_iteration, market_ratio, n_top=5):
    """
    Select config based on current regime (BULL/BEAR/STABLE).
    """
    # Determine market regime
    if market_ratio > 1.3:
        regime = 'BULL'
    elif market_ratio < 0.7:
        regime = 'BEAR'
    else:
        regime = 'STABLE'
    
    # Get top N configs by score
    top_configs = self.get_top_configs(current_iteration, n=n_top)
    
    # In BULL regime: prefer configs with momentum_signal='BULLISH'
    # In BEAR regime: prefer configs with momentum_signal='BEARISH'
    # In STABLE regime: prefer highest overall score
    
    for cfg in top_configs:
        score_data = self.get_composite_score(cfg['name'], current_iteration)
        
        if regime == 'BULL' and score_data['momentum_signal'] == 'BULLISH':
            return cfg['name'], {
                'regime': regime,
                'decision': 'regime_match',
                'regime_info': score_data,
            }
        elif regime == 'BEAR' and score_data['momentum_signal'] == 'BEARISH':
            return cfg['name'], {
                'regime': regime,
                'decision': 'regime_match',
                'regime_info': score_data,
            }
    
    # No regime match → use highest score
    return top_configs[0]['name'], {
        'regime': regime,
        'decision': 'fallback_best_score',
    }
```

## StableConfigEnsemble

Combines signals from multiple stable configs:

```python
# wf_stable_ensemble.py
class StableConfigEnsemble:
    """
    Ensemble of stable configs for signal calculation.
    """
    def __init__(self, config_scorer, min_ratio=1.05, n_configs=10, 
                 min_samples=30, ratio_window=50):
        self.config_scorer = config_scorer
        self.min_ratio = min_ratio
        self.n_configs = n_configs
        self.min_samples = min_samples
        self.ratio_window = ratio_window
    
    def get_stable_configs(self, iteration):
        """
        Get configs that meet stability criteria.
        """
        stable = []
        
        for config_name, data in self.config_scorer.config_data.items():
            results = data.get('results', [])
            if len(results) < self.min_samples:
                continue
            
            # Calculate recent ratio
            recent = results[-self.ratio_window:]
            tp = sum(r['tp'] for r in recent)
            fp = sum(r['fp'] for r in recent)
            ratio = tp / fp if fp > 0 else (3.0 if tp > 0 else 0.0)
            
            if ratio >= self.min_ratio:
                stable.append({
                    'name': config_name,
                    'ratio': ratio,
                    'tp': tp,
                    'fp': fp,
                    'n_samples': len(results),
                })
        
        # Sort by ratio
        stable.sort(key=lambda x: x['ratio'], reverse=True)
        return stable[:self.n_configs]
```

## Ensemble Signal Calculation

```python
def calculate_ensemble_signal(self, config_probs, iteration, 
                              precision_zone, net_signal, market_ratio):
    """
    Calculate ensemble signal from stable configs.
    """
    stable_configs = self.get_stable_configs(iteration)
    
    if len(stable_configs) < 3:
        return 0.0, {'status': 'INSUFFICIENT_CONFIGS'}
    
    # Weighted probability based on config ratios
    total_weight = 0
    weighted_prob = 0
    
    for cfg in stable_configs:
        prob = config_probs.get(cfg['name'], 0.5)
        weight = cfg['ratio']
        weighted_prob += prob * weight
        total_weight += weight
    
    ensemble_prob = weighted_prob / total_weight if total_weight > 0 else 0.5
    
    # Agreement: fraction of stable configs predicting UP
    votes_up = sum(1 for cfg in stable_configs 
                   if config_probs.get(cfg['name'], 0.5) >= 0.5)
    agreement = votes_up / len(stable_configs)
    
    # Signal scaling based on agreement
    if agreement > 0.8:
        signal = 1.5  # Strong agreement
    elif agreement > 0.6:
        signal = 1.0  # Moderate agreement
    else:
        signal = 0.5  # Weak agreement
    
    return signal, {
        'status': 'OK',
        'weighted_p_up': ensemble_prob,
        'agreement': agreement,
        'n_stable': len(stable_configs),
        'avg_config_ratio': np.mean([c['ratio'] for c in stable_configs]),
    }
```

## Top10 Config Display

```python
# Printed every iteration
if MULTI_CONFIG_TRACKING and iteration >= 10:
    n_display = min(10, N_TOP_CONFIGS)
    top_cfgs = config_scorer.get_top_configs(iteration, n=n_display)
    
    top_strs = []
    for cfg_data in top_cfgs[:5]:
        name_short = cfg_data['name'][:12]
        ratio = cfg_data['ratio']
        ratio_s = f"{ratio:.1f}" if ratio < 100 else "∞"
        top_strs.append(f"{name_short}({cfg_data['tp']}/{cfg_data['fp']}={ratio_s})")
    
    print(f"    Top{n_display}: {' | '.join(top_strs)}")
```

## Config Switch History

```python
# Track every config switch
switch_history = []

# Log entry
{
    'iteration': 150,
    'from': 'ens_pla_qua_auc1_reg0_wo',
    'to': 'ens_iso_you_auc0_reg1_ws',
    'score': 2.45,
    'reason': 'higher_score',
}

# Summary at end
print(f"TOTAL: {iteration} iterations | Switches: {len(switch_history)} | Final: {current_config}")
```

---

*See [Part_6_Checkpoints.md](Part_6_Checkpoints.md) for checkpoint persistence details.*

# Part 4: Position Sizing V3

## Overview

Position Sizing V3 is a clean, modular pipeline that converts model probabilities into position sizes (0.0 to 2.0).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      POSITION SIZING V3 PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1: Gate Check                                                          │
│     prob >= threshold?                                                       │
│          │                                                                   │
│          ├─ NO  → return 0.0 (no position)                                  │
│          └─ YES ↓                                                            │
│                                                                              │
│  Step 2: Rolling EMA Ratio                                                   │
│     Recent TP/FP performance                                                 │
│          │                                                                   │
│          └─ ratio_factor (0.0 to 1.2)                                       │
│                                                                              │
│  Step 3: Config Alignment                                                    │
│     Top10 config agreement                                                   │
│          │                                                                   │
│          └─ alignment_factor (0.5 to 1.0)                                   │
│                                                                              │
│  Step 4: Volatility Adjustment                                               │
│     High vol regime?                                                         │
│          │                                                                   │
│          └─ vol_factor (0.7 or 1.0)                                         │
│                                                                              │
│  Step 5: Final Position                                                      │
│     base × ratio × alignment × vol                                          │
│          │                                                                   │
│          └─ Leverage rules applied                                          │
│          │                                                                   │
│          └─ position ∈ [0.0, 2.0]                                           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Configuration

All tunable parameters are in `PositionSizingConfig`:

```python
@dataclass
class PositionSizingConfig:
    # Step 1: Gates
    min_prob: float = 0.50                    # Minimum probability to consider
    use_alpha_gate: bool = True               # Expected return > risk-free
    
    # Step 2: Rolling EMA Ratio
    ratio_window: int = 50                    # TP/FP tracking window
    ratio_ema_alpha: float = 0.1              # EMA decay rate
    ratio_min_trades: int = 10                # Minimum trades before using
    
    # Step 3: Config Alignment
    alignment_min_configs: int = 3            # Minimum configs needed
    alignment_weight: float = 1.0             # How much alignment affects
    
    # Step 3b: EMA Crossover Scaling
    use_ema_crossover_scale: bool = True
    ema_crossover_boost: float = 0.15         # +15% when StEMA > LtEMA
    ema_crossover_reduce: float = 0.10        # -10% when StEMA <= LtEMA
    
    # Step 3c: LtEMA Quartile Scaling
    use_ltema_quartile_scale: bool = True
    ltema_q1_threshold: float = 0.95          # Contrarian boost threshold
    ltema_q4_threshold: float = 1.47          # Regression reduce threshold
    ltema_q1_boost: float = 0.05              # +5% at Q1
    ltema_q4_reduce: float = 0.08             # -8% at Q4
    
    # Step 4: Volatility
    high_vol_reduction: float = 0.70          # 30% reduction in high vol
    
    # Step 5: Position scaling
    base_position: float = 1.0                # 100% equity
    max_position: float = 2.0                 # 200% max (2x leverage)
    min_position: float = 0.0                 # 0% min (cash)
    
    # Leverage rules
    leverage_min_ratio: float = 1.3           # Min ratio to allow >1.0
    leverage_min_alignment: float = 0.7       # Min alignment to allow >1.0
    
    # Step 5b: Inverse Ratio Scale (mean reversion)
    use_ratio_inverse_scale: bool = True
    ratio_inverse_low_threshold: float = 0.8  # Below → increase position
    ratio_inverse_high_threshold: float = 1.2 # Above → decrease position
    ratio_inverse_low_scale: float = 1.20     # +20% when ratio low
    ratio_inverse_high_scale: float = 0.80    # -20% when ratio high
    ratio_inverse_min_trades: int = 20
    
    # Step 6: Drawdown Protection
    use_drawdown_protection: bool = True
```

## Step-by-Step Calculation

### Step 1: Gate Check

```python
def check_gates(self, prob_up, threshold, expected_return, risk_free_rate, dual_ema_data):
    """
    Binary gates: pass = continue, fail = return 0.
    """
    # Direction gate
    if prob_up < threshold:
        return False, 'direction'
    
    # Alpha gate: expected_return > risk_free
    if self.config.use_alpha_gate:
        alpha = expected_return - risk_free_rate
        if alpha <= 0:
            return False, 'alpha'
    
    # All gates passed
    return True, None
```

### Step 2: Rolling Ratio Factor

```python
def calculate_ratio_factor(self):
    """
    Factor based on recent TP/FP performance.
    Higher ratio → higher factor (momentum)
    Or inverse: lower ratio → higher factor (mean reversion)
    """
    if len(self.result_buffer) < self.config.ratio_min_trades:
        return 1.0, 'warmup'
    
    # Count TP and FP
    tp = sum(1 for r in self.result_buffer if r == 'TP')
    fp = sum(1 for r in self.result_buffer if r == 'FP')
    
    if fp == 0:
        ratio = 3.0 if tp > 0 else 1.0
    else:
        ratio = tp / fp
    
    # Apply EMA smoothing
    if self.ema_ratio is None:
        self.ema_ratio = ratio
    else:
        self.ema_ratio = (self.config.ratio_ema_alpha * ratio + 
                         (1 - self.config.ratio_ema_alpha) * self.ema_ratio)
    
    # Convert ratio to factor
    if self.config.use_ratio_inverse_scale:
        # Mean reversion: low ratio → increase, high ratio → decrease
        if self.ema_ratio < self.config.ratio_inverse_low_threshold:
            return self.config.ratio_inverse_low_scale, 'inverse_low'
        elif self.ema_ratio > self.config.ratio_inverse_high_threshold:
            return self.config.ratio_inverse_high_scale, 'inverse_high'
    
    # Default: momentum scaling
    return min(1.2, max(0.0, self.ema_ratio / 1.5)), 'momentum'
```

### Step 3: Config Alignment Factor

```python
def calculate_alignment_factor(self, config_predictions, threshold):
    """
    How many Top10 configs agree with the signal.
    """
    if len(config_predictions) < self.config.alignment_min_configs:
        return 1.0, {'alignment': 0.5}
    
    # Count votes above threshold
    votes_up = sum(1 for cfg in config_predictions if cfg['prob'] >= cfg['threshold'])
    alignment = votes_up / len(config_predictions)
    
    # Scale alignment to factor (0.5 to 1.0)
    factor = 0.5 + 0.5 * alignment
    
    return factor, {'alignment': alignment, 'votes_up': votes_up, 'n_configs': len(config_predictions)}
```

### Step 3b: EMA Crossover Scaling

```python
def apply_ema_crossover(self, factor, dual_ema_data):
    """
    Boost when short-term EMA crosses above long-term EMA.
    """
    if not self.config.use_ema_crossover_scale:
        return factor
    
    if not dual_ema_data.get('has_data'):
        return factor
    
    lt_ema = dual_ema_data['long_term_ema']
    st_ema = dual_ema_data['short_term_ema']
    
    if st_ema > lt_ema:
        # Bullish crossover
        return factor * (1 + self.config.ema_crossover_boost)
    else:
        # Bearish crossover
        return factor * (1 - self.config.ema_crossover_reduce)
```

### Step 3c: LtEMA Quartile Scaling

```python
def apply_ltema_quartile(self, factor, dual_ema_data):
    """
    Contrarian boost at low LtEMA (Q1), reduction at high LtEMA (Q4).
    """
    if not self.config.use_ltema_quartile_scale:
        return factor
    
    lt_ema = dual_ema_data.get('long_term_ema', 1.0)
    
    if lt_ema < self.config.ltema_q1_threshold:
        # Q1: contrarian boost
        return factor * (1 + self.config.ltema_q1_boost)
    elif lt_ema > self.config.ltema_q4_threshold:
        # Q4: regression reduce
        return factor * (1 - self.config.ltema_q4_reduce)
    
    return factor
```

### Step 4: Volatility Adjustment

```python
def apply_volatility_adjustment(self, factor, high_vol):
    """
    Reduce position in high volatility regime.
    """
    if high_vol:
        return factor * self.config.high_vol_reduction, 'HIGH_VOL'
    return factor, 'NORMAL'
```

### Step 5: Final Position

```python
def calculate_final_position(self, ratio_factor, alignment_factor, vol_factor, 
                              alignment, ema_ratio):
    """
    Combine all factors into final position.
    """
    raw_position = (self.config.base_position * 
                    ratio_factor * 
                    alignment_factor * 
                    vol_factor)
    
    # Leverage rules
    can_leverage = (
        ema_ratio >= self.config.leverage_min_ratio and
        alignment >= self.config.leverage_min_alignment
    )
    
    if can_leverage:
        max_position = self.config.max_position
    else:
        max_position = 1.0  # No leverage
    
    # Clamp to valid range
    final_position = min(max_position, max(self.config.min_position, raw_position))
    
    return final_position, {
        'raw_position': raw_position,
        'can_leverage': can_leverage,
        'max_position': max_position,
    }
```

## Full Pipeline

```python
def calculate_position(self, prob_up, threshold, config_predictions, high_vol,
                       expected_return, risk_free_rate, dual_ema_data, best_top10_ratio,
                       verbose=False):
    """
    Full position sizing pipeline.
    Returns: (position, metadata)
    """
    meta = {}
    
    # Step 1: Gate Check
    gates_passed, failed_gate = self.check_gates(
        prob_up, threshold, expected_return, risk_free_rate, dual_ema_data
    )
    meta['step1_gate'] = 'PASS' if gates_passed else f'FAIL:{failed_gate}'
    
    if not gates_passed:
        return 0.0, meta
    
    # Step 2: Rolling Ratio Factor
    ratio_factor, ratio_reason = self.calculate_ratio_factor()
    meta['step2_ratio_factor'] = ratio_factor
    meta['step2_reason'] = ratio_reason
    
    # Step 3: Config Alignment
    alignment_factor, align_meta = self.calculate_alignment_factor(config_predictions, threshold)
    meta['step3_alignment_factor'] = alignment_factor
    meta['align_meta'] = align_meta
    
    # Step 3b: EMA Crossover
    alignment_factor = self.apply_ema_crossover(alignment_factor, dual_ema_data)
    
    # Step 3c: LtEMA Quartile
    alignment_factor = self.apply_ltema_quartile(alignment_factor, dual_ema_data)
    
    # Step 4: Volatility
    vol_factor, vol_regime = self.apply_volatility_adjustment(1.0, high_vol)
    meta['step4_vol_factor'] = vol_factor
    meta['step4_vol_regime'] = vol_regime
    
    # Step 5: Final Position
    final_position, final_meta = self.calculate_final_position(
        ratio_factor, alignment_factor, vol_factor,
        align_meta['alignment'], self.ema_ratio or 1.0
    )
    meta.update(final_meta)
    
    if verbose:
        print(f"    [V3] Gate:{meta['step1_gate']} Ratio:{ratio_factor:.2f}({ratio_reason}) "
              f"Align:{alignment_factor:.2f} Vol:{vol_factor:.2f} → {final_position:.2f}")
    
    return final_position, meta
```

## Result Tracking

```python
def update_result(self, result: str):
    """
    Update rolling buffer with prediction outcome.
    Called after each iteration when outcome is known.
    """
    if result in ('TP', 'FP', 'TN', 'FN'):
        self.result_buffer.append(result)
        
        # Update counters
        if result == 'TP':
            self.tp_count += 1
        elif result == 'FP':
            self.fp_count += 1
```

## Benchmark Signal (Gates Only)

For comparison, a simpler "benchmark" signal uses only gates, no EMA scaling:

```python
def calculate_benchmark_signal(self, probability, threshold, estimated_return, risk_free_rate):
    """
    Simple signal using only gates (works from iteration 1).
    """
    # Direction gate
    if probability < threshold:
        return 0.0, {'status': 'GATE_FAIL', 'gate_failed': 'direction'}
    
    # Alpha gate
    alpha_excess = estimated_return - risk_free_rate
    if alpha_excess <= 0:
        return 0.0, {'status': 'GATE_FAIL', 'gate_failed': 'alpha'}
    
    # Gates passed → full position
    return 1.0, {'status': 'SIGNAL_GENERATED', 'alpha_excess': alpha_excess}
```

## Baseline Signal (with EMA)

The baseline signal adds EMA scaling on top of gates:

```python
def calculate_position_size_baseline(self, probability, threshold, estimated_return,
                                     risk_free_rate, dual_ema_data, past_ratio):
    """
    Signal with gates + EMA scaling + ratio gate.
    """
    # Gate checks (same as benchmark)
    if probability < threshold:
        return 0.0, {'status': 'GATE_FAIL', 'gate_failed': 'direction'}
    
    alpha_excess = estimated_return - risk_free_rate
    if alpha_excess <= 0:
        return 0.0, {'status': 'GATE_FAIL', 'gate_failed': 'alpha'}
    
    # Ratio gate (only if past_ratio is available)
    if past_ratio is not None and past_ratio < 1.0:
        return 0.0, {'status': 'GATE_FAIL', 'gate_failed': 'ratio'}
    
    # EMA scaling (if data available)
    if dual_ema_data.get('has_data'):
        lt_ema = dual_ema_data['long_term_ema']
        st_ema = dual_ema_data['short_term_ema']
        
        ema_bonus = 0.0
        danger_penalty = 0.0
        
        # Bullish crossover bonus
        if st_ema > lt_ema:
            ema_bonus = 0.15
        
        # Q1 contrarian boost
        if lt_ema < 0.95:
            ema_bonus += 0.10
        
        # Q4 regression penalty
        if lt_ema > 1.47:
            danger_penalty = 0.10
        
        position = 1.0 + ema_bonus - danger_penalty
        position = min(1.5, max(0.5, position))
        
        return position, {
            'status': 'SIGNAL_GENERATED',
            'ema_has_data': True,
            'ema_bonus': ema_bonus,
            'danger_penalty': danger_penalty,
        }
    
    # No EMA data → warmup signal
    return 1.0, {
        'status': 'SIGNAL_WARMUP',
        'ema_has_data': False,
    }
```

## Position Recommendations

```python
def get_position_recommendation(self, signal):
    """
    Convert signal to human-readable recommendation.
    """
    if signal <= 0:
        return "STAY OUT (no position)"
    elif signal < 0.5:
        return f"SMALL LONG ({signal:.0%} equity)"
    elif signal < 1.0:
        return f"PARTIAL LONG ({signal:.0%} equity)"
    elif signal == 1.0:
        return "FULL LONG (100% equity)"
    elif signal < 1.5:
        return f"LEVERAGED LONG ({signal:.0%} equity)"
    else:
        return f"AGGRESSIVE LONG ({signal:.0%} equity)"
```

---

*See [Part_5_Config_Tracking.md](Part_5_Config_Tracking.md) for multi-config tracking details.*

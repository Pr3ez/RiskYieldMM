# 5-Minute Timeframe Target Labeling Findings

**Date:** 2026-02-05  
**Status:** Analysis Complete, Implementation Deferred

---

## Executive Summary

The 5-minute timeframe exhibits fundamentally different market behavior than 15m, making it incompatible with the standard 8-class target distribution. This document captures the findings for future implementation of a 5m-specific labeling approach.

---

## Key Finding: Structural Mismatch

### Data Composition (5m)
| Scenario | Count | % of Data |
|----------|-------|-----------|
| Breakout UP (avg_low < 0) | 205,783 | 42.9% |
| Breakout DOWN (avg_high < 0) | 196,813 | 41.1% |
| **Total Breakouts** | **402,596** | **84.0%** |
| Oscillation (both > 0) | 76,663 | 16.0% |

### Comparison to 15m
| Metric | 5m | 15m |
|--------|-----|------|
| Breakout % | 84% | 74% |
| Oscillation % | 16% | 26% |
| MSE to doc targets | 47.21 | 1.39 |

---

## Why 5m Differs

1. **Shorter timeframe = stronger directional momentum**
   - Within an 8h batch, 5m bars capture more granular price movement
   - Once price moves in a direction, 5m sees many sequential bars in that direction
   - Less mean-reversion within batch window

2. **Breakout definition is more sensitive**
   - `dist_avg_low < 0` means average of remaining lows is ABOVE entry
   - With 96 bars per batch, price easily trends away from early entries
   - 15m has only 32 bars per batch → more balanced movement

3. **REVERSAL classes are structurally rare**
   - Reversal requires oscillation + one-sided outliers
   - Only 16% oscillation × reversal probability → <1.5% of data
   - Cannot be increased through threshold tuning

---

## Optimal Thresholds for 5m

```python
THRESHOLDS_5M = {
    "BREAKOUT_THRESHOLD": 1.6,   # % (absolute distance for continuation)
    "RISK_THRESHOLD": 2.5,       # x (ratio for oscillation risk)
}
```

These minimize MSE (47.21) but cannot match doc targets due to structural constraints.

---

## 5m Natural Distribution

Use these as **5m-specific targets** instead of doc targets:

| Class | Name | 5m Natural % | Doc Target % | Gap |
|-------|------|--------------|--------------|-----|
| 0 | DOWN_BALANCED | 28.2% | 25.5% | +2.7% |
| 1 | DOWN_CONT | 12.9% | 11.2% | +1.7% |
| 2 | DOWN_VOLATILE | 7.4% | 9.8% | -2.4% |
| 3 | UP_BALANCED | 30.2% | 28.4% | +1.8% |
| 4 | UP_CONT | 12.7% | 9.5% | +3.2% |
| 5 | UP_VOLATILE | 7.3% | 9.6% | -2.3% |
| 6 | UP_REVERSAL_RISK | 0.7% | 3.5% | -2.8% |
| 7 | DOWN_REVERSAL_RISK | 0.6% | 2.6% | -2.0% |

### Group Summary
| Group | 5m % | Doc % |
|-------|------|-------|
| BALANCED | 58.4% | 53.9% |
| CONT | 25.6% | 20.7% |
| VOLATILE | 14.7% | 19.4% |
| REVERSAL | 1.3% | 6.1% |

---

## Implementation Options for 5m

### Option 1: Accept Natural Distribution
- Use 5m-specific targets (table above)
- Train separate model for 5m
- Pros: Matches actual data behavior
- Cons: Different class meanings across timeframes

### Option 2: Reclassify Breakouts
- Current: Breakouts → BALANCED or CONT only
- Alternative: Create breakout-specific classes
  - BREAK_UP_BALANCED, BREAK_UP_CONT
  - BREAK_DOWN_BALANCED, BREAK_DOWN_CONT
- Pros: More semantic meaning
- Cons: Changes 8-class structure

### Option 3: Longer Batch Window for 5m
- Instead of 8h batches, use 24h or 48h
- More time for mean-reversion → more oscillation
- Pros: May achieve similar distribution to 15m
- Cons: Different batch semantics, requires recomputation

### Option 4: Different Batch Segmentation
- Use 2h segments within 8h (current `segment_2h`)
- Compute metrics per 2h instead of full batch
- Pros: More granular, may capture oscillation better
- Cons: Fewer remaining bars, statistical reliability issues

---

## Labeling Logic Reference

### For Breakout Scenarios (84% of 5m data)

```python
# Breakout UP: avg_low < 0 (price moved up so strongly avg of lows > entry)
if dist_avg_low < 0:
    direction = UP
    if dist_top5_high > BREAKOUT_THRESHOLD:
        class = UP_CONT (4)       # Strong upward momentum continues
    else:
        class = UP_BALANCED (3)   # Moderate upward move

# Breakout DOWN: avg_high < 0 (price moved down so strongly avg of highs < entry)
if dist_avg_high < 0:
    direction = DOWN
    if dist_bot5_low > BREAKOUT_THRESHOLD:
        class = DOWN_CONT (1)     # Strong downward momentum continues
    else:
        class = DOWN_BALANCED (0) # Moderate downward move
```

### For Oscillation Scenarios (16% of 5m data)

```python
# Oscillation: both avg_high > 0 AND avg_low > 0
if dist_avg_high > 0 and dist_avg_low > 0:
    direction = UP if dist_avg_high > dist_avg_low else DOWN
    
    risk_up = dist_top5_high / dist_avg_high
    risk_down = dist_bot5_low / dist_avg_low
    
    high_risk_up = risk_up > RISK_THRESHOLD
    high_risk_down = risk_down > RISK_THRESHOLD
    
    # Apply 8-class logic based on direction and risk flags
    # (See main implementation doc for full logic)
```

---

## Data Files

Precomputed distance metrics available at:
```
data/htf_backtest/5m_distance_metrics.parquet
```

Columns:
- `timestamp`, `close`, `high`, `low`
- `batch_id`, `bar_pos`, `remaining_bars`
- `dist_avg_high`, `dist_avg_low` (can be negative = breakout)
- `dist_top5_high`, `dist_bot5_low` (always positive)
- `bb_upper`, `bb_lower`, `bb_middle`

---

## Next Steps

1. Decide on implementation approach (Option 1-4 above)
2. If Option 1: Implement with 5m-specific targets
3. If Option 2-4: Design new methodology and recompute metrics
4. Test model performance on 5m with chosen approach
5. Compare to 15m baseline results

---

## Related Documents

- [target_labeling_implementation.md](target_labeling_implementation.md) - Main implementation guide (15m-focused)
- [target_labeling_analysis_2026-02-05.md](target_labeling_analysis_2026-02-05.md) - Original analysis

---

*This document will be updated when 5m implementation is revisited.*

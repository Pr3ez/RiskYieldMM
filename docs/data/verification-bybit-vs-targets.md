# Verification: bybitmodel.py vs targets.py Implementation

**Date:** 2026-02-03  
**Purpose:** Line-by-line comparison of strategy documentation vs ML target implementation  
**Status:** 🔴 CRITICAL DIFFERENCES FOUND

---

## Summary of Differences

| Category | Item | bybitmodel.py (Doc) | targets.py (Implementation) | Severity |
|----------|------|---------------------|----------------------------|----------|
| BBand Period | Period | **NOT SPECIFIED** (likely 20) | **20** | ⚠️ VERIFY |
| BBand Sigma | Sigma levels | **±2σ only** | **±1σ AND ±2σ** | 🔴 MAJOR |
| Entry Zone (LONG) | Calculation | `(Lower + Mid) / 2` | Tracks `close > ±1σ` band | 🔴 DIFFERENT |
| Entry Zone (SHORT) | Calculation | `(Upper + Mid) / 2` on 5m | Not implemented | 🔴 MISSING |
| Timeframes | Used | 5m, 15m, 1h, 4h | 15m only | 🔴 DIFFERENT |
| TP Calculation | LONG | `SMA_20_1h` | `tp_mult * volatility` | 🔴 DIFFERENT |
| TP Calculation | SHORT | `BBand_Lower_1h` | `tp_mult * volatility` | 🔴 DIFFERENT |
| SL Calculation | Formula | `entry ± 1.5 * ATR_14` | `sl_mult * volatility` (range-based) | 🔴 DIFFERENT |
| ATR Multiplier | Value | **1.5** | Not used (uses range volatility) | 🔴 DIFFERENT |

---

## Detailed Analysis

### 1. Bollinger Band Parameters

#### bybitmodel.py (from doc)
```
Bollinger Bands (`Bollinger_Upper`, `Bollinger_Middle`, `Bollinger_Lower`): BollingerBands on close.
```
- **Period:** Not explicitly stated, standard is 20
- **Sigma:** Uses only ±2σ (standard BBand has Upper = Mid + 2σ, Lower = Mid - 2σ)

#### targets.py (implementation)
```python
# Line 654-661 in _load_15m_data_for_8h()
bband_period = 20

# 5-level bands
upper_band = sma + 2.0 * std        # +2σ (outer upper)
upper_mid_band = sma + 1.0 * std    # +1σ (inner upper)
mid_band = sma                       # SMA
lower_mid_band = sma - 1.0 * std    # -1σ (inner lower)
lower_band = sma - 2.0 * std        # -2σ (outer lower)
```
- **Period:** 20 ✅ MATCHES
- **Sigma:** Uses BOTH ±1σ AND ±2σ (5-level system)

**🔴 DIFFERENCE:** targets.py uses a 5-level BBand system while bybitmodel uses standard 3-level (±2σ). The ±1σ bands don't exist in the live strategy.

---

### 2. LONG Entry Zone Calculation

#### bybitmodel.py (from doc)
```
LONG entry price is derived from 15m and 1h Bollinger levels:
midpoint_15 = (Bollinger_Lower_15m + Bollinger_Middle_15m) / 2

If midpoint_15 < Bollinger_Lower_1h:
    entry_long = Bollinger_Lower_1h
else:
    entry_long = midpoint_15

Gate: last 15m close must be <= entry_long
```

**Formula breakdown:**
- `Bollinger_Lower_15m` = SMA - 2σ (on 15m)
- `Bollinger_Middle_15m` = SMA (on 15m)
- `midpoint_15` = (SMA - 2σ + SMA) / 2 = SMA - σ = **-1σ level**

So the entry zone is actually at **-1σ** (or lower if 1h is lower).

#### targets.py (implementation)
```python
# trade_setup target uses first_touch detection:
# Line 696-708 in _load_15m_data_for_8h()
first_touch_upper = -1       # First close above +2σ
first_touch_upper_mid = -1   # First close above +1σ
first_touch_lower_mid = -1   # First close below -1σ
first_touch_lower = -1       # First close below -2σ

# Line 1020-1042 in compute_trade_setup()
# STRONG_LONG: Touched -2σ BEFORE reaching +1σ
strong_long = (ft_lower >= 0) & ((ft_upper_mid < 0) | (ft_lower < ft_upper_mid))

# LONG_SETUP: Touched -1σ BEFORE reaching +1σ (but not already STRONG_LONG)
long_setup = (~strong_long & (ft_lower_mid >= 0) & 
              ((ft_upper_mid < 0) | (ft_lower_mid < ft_upper_mid)))
```

**🔴 CRITICAL DIFFERENCE:**

| Aspect | bybitmodel.py | targets.py |
|--------|--------------|------------|
| Entry zone | Midpoint = -1σ level | Tracks touches at -1σ and -2σ |
| Uses 1h cap | Yes (`max(midpoint_15, Lower_1h)`) | No 1h data used |
| Gate logic | `close <= entry_zone` | `close < band` (touch detection) |

The **entry zone calculation is fundamentally different**:
- bybitmodel: Uses a COMPUTED midpoint between Lower and Middle bands
- targets.py: Uses SIMPLE touch detection at ±1σ and ±2σ bands

---

### 3. SHORT Entry Zone Calculation

#### bybitmodel.py (from doc)
```
SHORT entry price is derived from 5m and 1h Bollinger levels:
midpoint_5 = (Bollinger_Upper_5m + Bollinger_Middle_5m) / 2

If midpoint_5 > Bollinger_Upper_1h:
    entry_short = Bollinger_Upper_1h
else:
    entry_short = midpoint_5

Gate: last 5m close must be >= entry_short
```

**Formula breakdown:**
- `Bollinger_Upper_5m` = SMA + 2σ (on 5m)
- `midpoint_5` = (SMA + 2σ + SMA) / 2 = SMA + σ = **+1σ level**

#### targets.py (implementation)

**🔴 MISSING:** targets.py does NOT use 5m data at all. It only uses 15m data for all intrabar analysis.

The trade_setup target's SHORT logic:
```python
# SHORT_SETUP: Touched +1σ BEFORE reaching -1σ
short_setup = (~strong_short & (ft_upper_mid >= 0) & 
               ((ft_lower_mid < 0) | (ft_upper_mid < ft_lower_mid)))
```

This tracks +1σ touches on 15m data, not the exact bybitmodel midpoint logic on 5m data.

---

### 4. Take-Profit Calculation

#### bybitmodel.py (from doc)
```
LONG signals:
- Take profit: tp_long = SMA_20_1h (must satisfy tp_long >= entry_long * 1.006)

SHORT signals:
- Take profit: tp_short = Bollinger_Lower_1h (must satisfy tp_short <= entry_short * 0.994)
```

**Key details:**
- Uses **1h timeframe** data
- LONG uses **SMA_20** (not BBand)
- SHORT uses **BBand_Lower** (not symmetric)
- Has **minimum R:R requirement** (0.6% for LONG, -0.6% for SHORT)

#### targets.py (implementation)
```python
# Line 1380-1384 in compute_triple_barrier()
# Volatility for barrier sizing (using range-based for efficiency)
hl_range = np.log(high / low)
volatility = hl_range.rolling(21).mean()

# Calculate barriers relative to entry price
tp_barrier = close * (1 + tp_mult * volatility)  # tp_mult = 1.5
sl_barrier = close * (1 - sl_mult * volatility)  # sl_mult = 1.0
```

**🔴 CRITICAL DIFFERENCES:**

| Aspect | bybitmodel.py | targets.py |
|--------|--------------|------------|
| TP formula (LONG) | `SMA_20_1h` (fixed target) | `close * (1 + 1.5 * volatility)` |
| TP formula (SHORT) | `BBand_Lower_1h` (fixed target) | `close * (1 - 1.5 * volatility)` |
| Volatility measure | Not used for TP | Range-based log(high/low) |
| Asymmetry | LONG uses SMA, SHORT uses BBand | Symmetric formula |
| Min R:R check | Yes (1.006x / 0.994x) | No |

The triple_barrier target uses a **completely different TP calculation** based on generic volatility, not the strategy's BBand/SMA targets.

---

### 5. Stop-Loss Calculation

#### bybitmodel.py (from doc)
```
Shared inputs:
- adjusted_atr = ATR_14 * atr_multiplier (default atr_multiplier = 1.5)

LONG signals:
- Stop loss: stop_loss = entry_long - adjusted_atr

SHORT signals:
- Stop loss: stop_loss = entry_short + adjusted_atr
```

**Key details:**
- Uses **ATR_14** (Average True Range, 14-period)
- Multiplier is **1.5**
- Formula: `entry ± 1.5 * ATR_14`

#### targets.py (implementation)
```python
# Line 1380-1384
hl_range = np.log(high / low)
volatility = hl_range.rolling(21).mean()

sl_barrier = close * (1 - sl_mult * volatility)  # sl_mult = 1.0
```

**🔴 CRITICAL DIFFERENCES:**

| Aspect | bybitmodel.py | targets.py |
|--------|--------------|------------|
| Volatility measure | ATR_14 | log(high/low) range |
| Period | 14 | 21 |
| Multiplier | 1.5 | 1.0 |
| Formula | `entry - 1.5 * ATR` | `close * (1 - volatility)` |

The stop-loss calculation is fundamentally different:
- bybitmodel uses **absolute ATR** (dollar amount)
- targets.py uses **percentage-based** range volatility

---

### 6. Timeframe Discrepancy

#### bybitmodel.py (from doc)
```
Timeframes used in the open/SL/TP flow: 1d, 4h, 1h, 15m, and 5m

- 5m: SHORT entry construction and gating
- 15m: LONG entry construction and gating
- 1h: core entry evaluation, TP targets, dynamic SL/TP
- 4h: regime classification, leverage sizing, dynamic SL/TP
- 1d: breakout skip filters
```

#### targets.py (implementation)
```python
# _load_15m_data_for_8h() - Line 504
data_dir: str = "fetchingByBit/sorted-15m-bybit-linear"
```

**🔴 MISSING TIMEFRAMES:**
- No 5m data used (critical for SHORT entries)
- No 1h data used (critical for TP targets)
- No 4h data used (critical for regime/leverage)

The implementation only uses 15m data aggregated to 8h, missing the multi-timeframe nature of the live strategy.

---

### 7. Direction Target vs Strategy Zones

#### targets.py direction target
```python
# Uses 5-level BBands: ±2σ and ±1σ
# STRONG_BULLISH: >50% above +1σ AND closes above +1σ
# BULLISH: >50% above SMA AND closes above SMA
# NEUTRAL: Mixed or didn't persist
# BEARISH: >50% below SMA AND closes below SMA
# STRONG_BEARISH: >50% below -1σ AND closes below -1σ
```

**🔴 MISMATCH:** The direction target uses persistence-based classification (time spent in zones), while bybitmodel uses point-in-time band touches for entry triggers.

---

## Impact Assessment

### High Impact 🔴

1. **Entry Zone Calculation** - The core entry logic is different
   - Impact: ML model predicts different "pullback" opportunities than live strategy would use
   - Action: Reimplement entry zone calculation to match `(Lower + Mid) / 2` formula

2. **Missing 5m/1h/4h Data** - Multi-timeframe analysis missing
   - Impact: Can't replicate the cross-timeframe confirmation logic
   - Action: Add 1h and 4h indicator alignment to targets

3. **TP/SL Barrier Mismatch** - triple_barrier uses wrong formulas
   - Impact: Predicted risk/reward doesn't match actual strategy outcomes
   - Action: Reimplement barriers using ATR and SMA_20/BBand_Lower

### Medium Impact ⚠️

4. **5-level vs 3-level BBands** - Using ±1σ bands that don't exist in strategy
   - Impact: "STRONG" classifications may not align with strategy behavior
   - Action: Verify if ±1σ adds value or causes confusion

5. **Volatility Measure** - Range-based vs ATR
   - Impact: Barrier widths differ ~10-20% from actual stops
   - Action: Switch to ATR_14 for barrier calculations

### Lower Impact ℹ️

6. **Period Differences** - 21-period vs 14-period volatility
   - Impact: Smoother volatility estimate in targets
   - Action: Consider aligning to 14-period

---

## Recommended Fixes

### Priority 1: Fix triple_barrier target

```python
# CURRENT (wrong):
hl_range = np.log(high / low)
volatility = hl_range.rolling(21).mean()
tp_barrier = close * (1 + tp_mult * volatility)

# SHOULD BE:
# Use ATR_14 for volatility
atr_14 = compute_atr(high, low, close, period=14)
adjusted_atr = atr_14 * 1.5

# LONG barriers
tp_barrier = sma_20_1h  # Need 1h SMA_20
sl_barrier = entry - adjusted_atr

# SHORT barriers
tp_barrier = bband_lower_1h  # Need 1h BBand_Lower
sl_barrier = entry + adjusted_atr
```

### Priority 2: Fix trade_setup entry zones

```python
# CURRENT (simplified):
# Tracks ±1σ and ±2σ touches

# SHOULD BE:
# LONG entry zone: midpoint = (BBand_Lower + BBand_Mid) / 2 = -1σ level
# SHORT entry zone: midpoint = (BBand_Upper + BBand_Mid) / 2 = +1σ level (on 5m)

# Calculate entry zones
long_entry_zone = (lower_band + mid_band) / 2  # This IS the -1σ level
short_entry_zone = (upper_band + mid_band) / 2  # This IS the +1σ level

# Track touches relative to these zones, not raw bands
```

### Priority 3: Add multi-timeframe support

Need to incorporate:
- 1h BBand/SMA for TP targets
- 4h data for regime classification  
- (Optional) 5m data for precise SHORT entries

---

## Verification Checklist

- [ ] BBand period confirmed as 20 in bybitmodel.py source code
- [ ] ATR multiplier confirmed as 1.5 in source
- [ ] SMA_20 confirmed for LONG TP in source
- [ ] BBand_Lower confirmed for SHORT TP in source
- [ ] Verify 5m is actually used for SHORT (or if 15m is acceptable)

---

## Conclusion

**The current targets.py implementation does NOT accurately replicate the bybitmodel.py strategy.**

Major gaps:
1. Entry zone calculation uses simple band touches instead of midpoint formula
2. TP/SL barriers use generic volatility instead of ATR and specific BBand/SMA targets
3. Multi-timeframe analysis (1h, 4h) is completely missing
4. 5m data for SHORT entries is not used

**Recommendation:** Before training models on these targets, fix the triple_barrier and trade_setup calculations to match the documented strategy. Otherwise, ML predictions won't align with actual trading signals.

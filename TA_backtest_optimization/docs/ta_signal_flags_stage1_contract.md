# TA Signal Flags Stage-1 Contract

This working area materializes deterministic technical-analysis signal flags
from canonical OHLCV bars and keeps them separate from core HTF artifacts.

## Source And Outputs

Source data:

```text
data/htf_multiasset/{asset}/htf_canonical_ohlcv/{tf}/{asset}_{tf}_canonical.parquet
```

Generated outputs:

```text
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_events.parquet
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_flags.parquet
data/htf_multiasset/{asset}/ta_signal_flags/{tf}/{asset}_{tf}_ta_flags_meta.json
```

`*_ta_events.parquet` stores one row per closed higher-timeframe bar with
indicator values, event flags, `signal_available_ts`, and parameter metadata.
`*_ta_flags.parquet` stores one row per canonical 1m timestamp with binary
model-facing flags.

## Timing Contract

Signals are post-close only. A signal computed from a `15m` bar opening at
`10:00` is available at `10:15` and is expanded onto the next 15 canonical 1m
rows. It does not flag rows inside `10:00 -> 10:14`.

For session assets, expansion uses the next market-open canonical 1m rows.
Closed sessions and weekends are skipped because canonical 1m data has no rows
for those periods.

`signal_valid_until_ts` is the exclusive end of the expanded canonical 1m
validity window. For session assets this timestamp can move past weekends or
maintenance breaks because it is derived from actual market-open canonical rows,
not from wall-clock minutes alone.

## Indicator Set

V1 implements the full researched set:

- ADX + DMI
- RSI
- MACD
- VWAP
- Donchian Channels
- OBV
- Bollinger Bands
- Pivot Points
- Supertrend
- Aroon
- Stochastic

All formulas are implemented locally with Polars/Pandas/NumPy; TA-Lib is not a
runtime dependency.

The V1 materializer intentionally writes independent indicator-family flags.
It does not yet apply mutual-exclusion voting, optimized cooldowns, exits,
position sizing, leverage, or PnL ranking. Those decisions remain in the later
optimization/backtest stage after the default flags have been validated inside
Stage-1.

Warm-up periods emit inactive flags. Breakout rules that can leak through the
current bar, such as Donchian channels, use previous-channel values.

## Stage-1 Integration

TA flags are optional in Stage-1 merged dataset assembly:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --include-ta-flags \
  --ta-timeframes 15m,1h,4h,8h,12h,1d \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --plan-only
```

Target columns are prefixed as `T_{asset}__ta_*`; context columns are prefixed
as `C_{asset}__ta_*`. Missing inactive flags are filled with `0`, so rows are
not dropped merely because no TA signal is active.

## Commands

Status only:

```bash
python TA_backtest_optimization/materialize_ta_flags.py \
  --assets core \
  --timeframes 15m,1h,4h,8h,12h,1d \
  --status
```

Materialize flags:

```bash
python TA_backtest_optimization/materialize_ta_flags.py \
  --assets core \
  --timeframes 15m,1h,4h,8h,12h,1d
```

Validation commands:

```bash
python -m pytest tests/test_ta_signal_flags.py -q
python -m pytest tests/test_htf_multiasset_stage1_dataset.py -q
python -m py_compile \
  TA_backtest_optimization/materialize_ta_flags.py \
  scripts/htf_backtest/catboost/stage1_multiasset_dataset.py
git diff --check
```

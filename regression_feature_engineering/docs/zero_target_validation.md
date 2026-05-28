# Zero Target Validation

## Purpose

Define how to verify zero-valued regression targets before blaming features or
models.

## Current Status

BTCUSDT `8h/B` checks found no current evidence of label arithmetic bugs.

## Scope

Applies to `distance_horizon_vol_v2` target columns.

## Source Of Truth

- Validation module contract: `regression_feature_engineering/validation/zero_targets.py`
- Existing target validator: `scripts/analysis/validate_stage1_regression_targets.py`

## What This Does Not Decide

This document does not change label formulas.

## Current Evidence

For BTCUSDT `8h/B`, zero targets are currently explainable:

- up-distance targets are zero when raw future upside distance is exactly zero;
- down-distance targets are zero when raw future downside distance is exactly zero;
- this means the future label window did not trade beyond the row close in that
  direction.

Exact `distance_horizon_vol_v2` scan on the local BTCUSDT `8h/B` label root:

- label rows: `2,810,755`;
- valid rows: `1,405,427`;
- invalid rows: `1,405,328`;
- invalid reasons: `not_label_half=1,405,315`, `invalid_volatility=13`;
- up-distance zeros: `213,813` valid rows (`15.2134%`);
- down-distance zeros: `228,602` valid rows (`16.2657%`);
- both up and down extreme targets zero on the same row: `0`;
- normalized target zero while raw distance is positive: `0`;
- normalized target positive while raw distance is zero: `0`.

The directional split is also consistent with the legacy label direction:

- up-distance zeros appear only on `DOWN_BALANCED` and `DOWN_EXPANSION` rows;
- down-distance zeros appear only on `UP_BALANCED` and `UP_EXPANSION` rows.

This is expected because the target is directional path distance from the row
close to the future opposite-family first-half window. For an up-distance zero,
the row close is at or above every future high in the label window. For a
down-distance zero, the row close is at or below every future low in the label
window.

Observed future-window range checks:

- all `213,813` up-zero rows have `future_window_max_high <= close`;
- all `228,602` down-zero rows have `future_window_min_low >= close`;
- up-zero median margin between row close and future max high is `0.2721%`;
- down-zero median margin between future min low and row close is `0.2643%`.

Example up-zero row:

```text
timestamp: 2021-01-01 01:30 UTC
close: 29454.5
future label window: 2021-01-01 04:00 UTC -> 2021-01-01 07:45 UTC
future max high: 29397.5
future min low: 28847.0
raw up extreme pct: 0.0
raw down extreme pct: 0.0206250318
normalized up extreme: 0.0
normalized down extreme: 0.9368522002
```

Example down-zero row:

```text
timestamp: 2021-01-01 00:13 UTC
close: 28710.5
future label window: 2021-01-01 04:00 UTC -> 2021-01-01 07:45 UTC
future max high: 29397.5
future min low: 28847.0
raw up extreme pct: 0.0239285279
raw down extreme pct: 0.0
normalized up extreme: 1.1825509150
normalized down extreme: 0.0
```

## Required Checks

A zero target is valid only when:

- the row is marked valid;
- raw distance percentage is exactly zero;
- horizon volatility is finite and positive;
- future window bar count is positive;
- max-high/min-low metadata exists and explains the path.

A zero target is suspicious when normalized target is zero but raw distance is
positive, volatility is invalid, or future-window metadata is missing.

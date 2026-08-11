# RPF CNN Feature Diagnostic

## Purpose

Document what kind of existing RPF columns are plausible inputs for a causal
CNN sequence branch.

## Current Status

Status: diagnostic evidence exists, but no CNN feature panel is predictively
promoted.

The latest diagnostic runs were:

```text
UP:
test_output/rpf_cnn_feature_diagnostics/20260622_162023_cnn_feature_diagnostic_cls_extreme_up_ge_2x_down_hvol_v2/

DOWN:
test_output/rpf_cnn_feature_diagnostics/20260622_162047_cnn_feature_diagnostic_cls_extreme_down_ge_2x_up_hvol_v2/
```

Both runs used `BTCUSDT 8h/B`, `30` frozen prediction windows, `2,530`
candidate RPF features, and selected a diagnostic `160`-feature CNN candidate
panel.

This is post-hoc feature-input analysis. It uses held-out labels to understand
which feature types have useful row-level movement. It must not be treated as
production feature selection.

## Scope

This document covers only CNN input-panel evidence for the binary RPF targets:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

It does not cover old HTF features, EMA gates, signal banks, decision banks, or
final classifier promotion.

## Source Of Truth

- Diagnostic CLI:
  `regression_feature_engineering/walkforward/cnn_feature_diagnostic.py`
- Binary pipeline contract:
  `rpf_binary_prediction_pipeline_contract.md`
- Current feature state:
  `current_feature_state.md`
- Output artifacts:
  `test_output/rpf_cnn_feature_diagnostics/*/`

## What This Does Not Decide

This does not select final CNN architecture, final CatBoost inputs, thresholds,
or a promoted model. It only answers which RPF feature families/timeframes are
worth feeding into a causal sequence encoder.

## Diagnostic Method

The diagnostic scores each manifest feature by:

- within-batch nonconstant rate;
- within-batch unique value count;
- row-level target ranking inside mixed prediction batches;
- top-20-row target lift;
- batch-level target association;
- timeframe speed prior;
- feature-family sequence prior.

The key intent is to separate:

```text
tabular regime/context features
```

from:

```text
fast row-varying sequence-memory features
```

The CNN branch should receive the second group. Slow context can still go to
CatBoost through the tabular branch.

## Main Finding

The best CNN inputs are not the same slow context features that dominated many
ElasticNet/CatBoost runs.

CNN candidates should emphasize:

```text
15m / 1h / 4h
structural_room
temporal_memory_transforms
spike_breakout
interaction_confluence
acceptance_persistence
```

The weakest CNN sequence candidates are mostly:

```text
1d / 12h slow context
regime_calendar_state
rejection_chop
cross_asset_context
low-variance liquidity features
```

Those weaker groups may still be useful as tabular regime state, but they are
not the first choice for short-sequence memory.

## UP Target Evidence

Selected diagnostic CNN panel composition:

```text
temporal_memory_transforms: 45
structural_room:            45
spike_breakout:             32
interaction_confluence:     25
acceptance_persistence:      9
unsupervised_factor_layer:   4
```

Timeframe composition:

```text
4h:  45
1h:  37
15m: 33
8h:  28
12h: 16
1d:   1
```

Strong UP candidate types:

- room-pressure confluence features from `4h` and `1h`;
- Donchian position, room asymmetry, up-room-share, and value-distance
  features from `1h`, `15m`, and `4h`;
- lagged/EWM temporal-memory transforms of room features;
- squeeze/breakout-balance interaction features;
- short-timeframe acceptance distance-to-value features;
- short-timeframe spike/breakout proximity balance.

Representative top candidates:

```text
rpf_conf_4h_up_room_pressure_l48_bnd
rpf_conf_4h_room_pressure_balance_l48_bnd
rpf_conf_1h_room_pressure_balance_l48_bnd
rpf_room_1h_asym_l48_bnd
rpf_room_1h_up_room_share_l48_bnd
rpf_accept_15m_value_dist_l16_vol
rpf_spike_15m_break_prox_balance_l16_vol
```

## DOWN Target Evidence

Selected diagnostic CNN panel composition:

```text
structural_room:            45
temporal_memory_transforms: 45
spike_breakout:             29
interaction_confluence:     24
acceptance_persistence:     12
unsupervised_factor_layer:   3
liquidity_volume_pressure:   2
```

Timeframe composition:

```text
15m: 44
1h:  43
4h:  40
8h:  21
12h:  9
1d:   3
```

Strong DOWN candidate types:

- room-pressure and up-room-pressure confluence features;
- short-timeframe up-break proximity features that may indicate failed upside
  or downside setup;
- room asymmetry, room balance, and up-room-share features;
- value-distance and temporal-memory transforms from `15m` and `1h`.

Representative top candidates:

```text
rpf_conf_4h_up_room_pressure_l48_bnd
rpf_conf_4h_room_pressure_balance_l48_bnd
rpf_spike_15m_up_break_prox_l16_vol
rpf_room_1h_asym_l16_bnd
rpf_room_1h_up_room_share_l16_bnd
rpf_accept_15m_value_dist_l16_vol
```

## Practical CNN Input Contract

Next CNN experiments should use a separate CNN input panel instead of feeding
the CNN the same ElasticNet-selected tabular columns.

Recommended first CNN panel:

```text
target-specific diagnostic panel, 120-160 columns
families: structural_room, temporal_memory_transforms, spike_breakout,
          interaction_confluence, acceptance_persistence
timeframes: 15m, 1h, 4h first; allow limited 8h/12h context
exclude: diagnostic rpf_align_* columns, target columns, labels,
         and low-variance slow context as primary sequence inputs
```

The implemented command surface for this is:

```bash
--sequence-panel-path test_output/rpf_cnn_feature_diagnostics/<run>/selected_cnn_panel_160.json
```

This is intentionally separate from:

```bash
--candidate-panel-path ...
```

`--candidate-panel-path` narrows the tabular ElasticNet candidate universe.
`--sequence-panel-path` narrows only the CNN sequence input universe.

Recommended model structure remains:

```text
tabular branch:
RPF features -> causal scaler -> ElasticNet selector -> CatBoost

sequence branch:
diagnostic CNN panel -> causal scaler -> causal CNN embeddings -> CatBoost
```

CatBoost should receive:

```text
ElasticNet-selected tabular features + CNN embedding columns
```

The CNN should not replace ElasticNet or CatBoost.

## Next Validation

The next useful run is not broader Optuna. It is a controlled A/B test:

```text
A: ElasticNet tabular + CatBoost, no CNN
B: same config + CNN using the old broad/all panel
C: same config + CNN using the diagnostic fast panel
```

Promotion requires `C` to improve high-precision repeating signals without
increasing false-positive bursts or reducing active windows to near zero.

Minimum checks:

- same frozen windows;
- same target;
- same decision policy;
- same CatBoost/ElasticNet grid;
- compare active-window count, precision, false positives, high-target misses,
  and stability gates.

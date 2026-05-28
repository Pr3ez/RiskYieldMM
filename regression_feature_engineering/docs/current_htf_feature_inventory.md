# Current HTF Feature Inventory

## Purpose

Summarize the current HTF feature surface and why a separate regression feature
workflow is needed.

## Current Status

Evidence summary from the current BTCUSDT `8h/B` regression analysis.

## Scope

This document describes existing features; it does not reject them globally.

## Source Of Truth

- Existing feature roots: `data/htf_multiasset/{asset}/htf_with_helpers*/1m/target_4class/`
- Merged regression roots: `data/htf_multiasset_merged/btcusdt/corexself/`
- Detailed feature/helper list: `htf_feature_helper_inventory.md`

## What This Does Not Decide

This document does not remove existing HTF features.

## Observed Current Surface

The current merged BTCUSDT `8h/B` regression root has:

- `923,240` rows;
- `1,162` model features;
- `0` duplicate rows;
- `0` null model features;
- about `169` target BTC features, `992` context features, and one unprefixed
  `bar_in_batch_norm` feature.

Current feature families are mostly:

- volatility estimators;
- momentum and oscillators;
- normalized price/band position;
- volume and liquidity;
- candle shape;
- derivatives pressure for crypto assets;
- helper features such as OU, GARCH, EGARCH, CUSUM, and Kalman;
- cross-asset context features.

These are valid, leakage-aware classification/regime features. The weak
regression results are signal-mismatch evidence, not proof of data corruption.
The missing surface is direct path-distance information: structural room,
acceptance, persistence, spike capacity, breakdown risk, and rejection/chop.

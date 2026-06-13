# Code Vs Plan Status

## Purpose

Compare the expanded `regression_path_features_v1` plan against the actual
code, tests, generated manifests, and validation outputs currently present in
the repository.

## Current Status

Status: Phase 1 through Phase 13 are implemented, materialized, and
engineering-validated on the first benchmark root, `BTCUSDT 8h/B`. None of
the new regression feature families are predictively promoted yet.

The current `BTCUSDT 8h/B` generated root contains `2,530` model-facing
`rpf_*` features with duplicate count `0` and null feature count `0`.

## Scope

- Feature set: `regression_path_features_v1`
- Target variant: `distance_horizon_vol_v2`
- First benchmark: `BTCUSDT 8h/B`
- Full intended matrix: 8 core assets x 6 roots x 4 regression targets

## Source Of Truth

- Registry: `regression_feature_engineering/core/registry.py`
- Materializer: `regression_feature_engineering/materialize_features.py`
- Validator: `regression_feature_engineering/validate_features.py`
- Current state: `regression_feature_engineering/docs/current_feature_state.md`
- Coverage matrix: `regression_feature_engineering/docs/feature_coverage_matrix.md`
- Implementation TODO: `regression_feature_engineering/docs/feature_implementation_todo.md`

## What This Does Not Decide

This report does not promote any family into production. Promotion still
requires walk-forward ablation and target-specific feature selection evidence.

## Actual Code Coverage

| Phase | Family | Prefix | Registry Status | Actual Code Status | Generated Output Status |
|---:|---|---|---|---|---|
| 1 | `foundation_alignment` | `rpf_align_` | engineering_validated | implemented as alignment diagnostics | all generated roots include alignment diagnostics |
| 2 | `volatility_state` | `rpf_vol_` | engineering_validated_not_promoted | implemented in `features/volatility_state.py` | all 48 asset/root Phase 1/2 manifests have `29` vol features; BTCUSDT `8h/B` current root also includes them |
| 3 | `structural_room` | `rpf_room_` | engineering_validated_not_promoted | implemented in `features/structural_room.py` | BTCUSDT `8h/B` current root has `180` features |
| 4 | `acceptance_persistence` | `rpf_accept_` | engineering_validated_not_promoted | implemented in `features/acceptance_persistence.py` | BTCUSDT `8h/B` current root has `201` features |
| 5 | `temporal_memory_transforms` | `rpf_mem_` | engineering_validated_not_promoted | implemented in `features/temporal_memory_transforms.py` | BTCUSDT `8h/B` current root has `693` features |
| 6 | `rejection_chop` | `rpf_chop_` | engineering_validated_not_promoted | implemented in `features/rejection_chop.py` | BTCUSDT `8h/B` current root has `180` features |
| 7 | `spike_breakout` | `rpf_spike_` | engineering_validated_not_promoted | implemented in `features/spike_breakout.py` | BTCUSDT `8h/B` current root has `288` features |
| 8 | `liquidity_volume_pressure` | `rpf_liq_` | engineering_validated_not_promoted | implemented in `features/liquidity_volume_pressure.py` | BTCUSDT `8h/B` current root has `162` features |
| 9 | `regime_calendar_state` | `rpf_regime_` | engineering_validated_not_promoted | implemented in `features/regime_calendar_state.py` | BTCUSDT `8h/B` current root has `209` features |
| 10 | `interaction_confluence` | `rpf_conf_` | engineering_validated_not_promoted | implemented in `features/interaction_confluence.py` | BTCUSDT `8h/B` current root has `270` features |
| 11 | `cross_asset_context` | `rpf_xasset_` | engineering_validated_not_promoted | implemented in `features/cross_asset_context.py` | BTCUSDT `8h/B` current root has `144` features |
| 12 | `unsupervised_factor_layer` | `rpf_factor_` | engineering_validated_not_promoted | implemented in `features/unsupervised_factor_layer.py` | BTCUSDT `8h/B` current root has `144` features; all factor prefix validations passed |
| 13 | `sequence_embedding_layer` | `rpf_seq_` | engineering_validated_not_promoted | implemented in `features/sequence_embedding_layer.py` | BTCUSDT `8h/B` current root has `30` features; `rpf_seq_` validation passed |

## Generated Manifest Evidence

Current `BTCUSDT 8h/B` root:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
generated_at: 2026-06-02T22:18:37 UTC
rows:         2,810,755
features:     2,530 model-facing rpf_* columns
duplicates:   0
null features:0
```

Feature counts:

| Prefix | Count |
|---|---:|
| `rpf_vol_` | 29 |
| `rpf_room_` | 180 |
| `rpf_accept_` | 201 |
| `rpf_mem_` | 693 |
| `rpf_chop_` | 180 |
| `rpf_spike_` | 288 |
| `rpf_liq_` | 162 |
| `rpf_regime_` | 209 |
| `rpf_conf_` | 270 |
| `rpf_xasset_` | 144 |
| `rpf_factor_` | 144 |
| `rpf_seq_` | 30 |

The current artifact also contains `18` `rpf_align_` diagnostic columns.

## Validation Evidence

Implemented code has focused tests and validations:

- docs/registry/config consistency tests;
- closed-bar alignment test;
- safe math test;
- per-family formula and bounded-output tests through Phase 11;
- materializer manifest/catalog tests;
- validator report/index tests;
- experiment lookback parser tests;
- validator guard test for wide diagnostics.

Latest focused verification:

```bash
python -m pytest \
  tests/test_regression_feature_engineering_docs.py \
  tests/test_regression_feature_engineering_materializer.py \
  tests/test_regression_feature_engineering_validator.py -q
```

Current result: `40 passed`.

Additional checks:

```bash
python -m py_compile $(find regression_feature_engineering -name '*.py' -print)
git diff --check
```

Current result: both clean.

Validation status by family:

| Family | Validation Result | Predictive Status |
|---|---|---|
| `volatility_state` | all-core six-root Phase 1/2 validation passed | not promoted |
| `structural_room` | BTCUSDT `8h/B` validation passed; directional imbalance weak | not promoted |
| `acceptance_persistence` | BTCUSDT `8h/B` sliced validations passed | not promoted |
| `temporal_memory_transforms` | BTCUSDT `8h/B` sliced validations passed | not promoted |
| `rejection_chop` | BTCUSDT `8h/B` sliced validations passed; modest purpose-aligned signal | not promoted |
| `spike_breakout` | BTCUSDT `8h/B` sliced validations passed; stronger extreme-width signal | not promoted |
| `liquidity_volume_pressure` | BTCUSDT `8h/B` sliced validations passed; modest participation/directional-spread signal | not promoted |
| `regime_calendar_state` | BTCUSDT `8h/B` sliced validations passed after repairing one corrupt parquet batch | not promoted |
| `interaction_confluence` | BTCUSDT `8h/B` sliced validations passed; path-width signal and directional-spread evidence | not promoted |
| `cross_asset_context` | BTCUSDT `8h/B` sliced validations passed; modest BTC/ETH relative-context signal | not promoted |
| `unsupervised_factor_layer` | BTCUSDT `8h/B` all `rpf_factor_*` timeframe-prefix validations passed | not promoted |
| `sequence_embedding_layer` | BTCUSDT `8h/B` `rpf_seq_` validation passed; strongest abs Spearman `0.1215` | not promoted |

## Important Guardrails

The materializer supports only implemented families. Planned families remain
blocked until their code branch exists, which prevents manifests from claiming
features that were not generated.

Validation of broad families must use narrow diagnostic prefixes to keep memory
bounded. This is now standard for `rpf_mem_*`, `rpf_accept_*`, `rpf_chop_*`,
`rpf_spike_*`, `rpf_liq_*`, `rpf_regime_*`, `rpf_conf_*`, and
`rpf_xasset_*`. The validator also uses bounded hashed family slugs for long
family lists, which prevents Phase 1-13 report paths from exceeding filesystem
path-component limits.

## Done

- Separate regression feature workspace exists.
- Canonical closed-bar alignment utilities exist.
- Safe math utilities exist.
- Manifest and feature catalog writing exists.
- Chunked materialization exists for large roots.
- Full-root validation with sampled/prefix diagnostics exists.
- OOM guardrails exist for wide diagnostics and sweeps.
- Phase 1 through Phase 13 feature families are implemented.
- BTCUSDT `8h/B` has a current Phase 1-13 root with clean full-root safety at
  manifest level.
- Phase 12 all `rpf_factor_*` timeframe-prefix validations passed after the
  validator path-slug fix.
- Phase 13 `rpf_seq_` prefix validation passed after the validator path-slug
  fix.
- Stage-1 regression walk-forward supports `htf_only`, `regression_only`, and
  `htf_plus_regression` feature-source modes. In v1, regression-path features
  are joined for the target asset by exact `timestamp,batch_id`.

## Left To Do

Highest priority:

1. Run controlled walk-forward ablations after all static feature families are
   complete:
   - HTF-only;
   - regression-only;
   - HTF plus regression.
2. Run strict grid search over feature source, lookback, validation width,
   selected feature count, Spearman threshold, dedupe threshold, and CatBoost
   hyperparameters.

Rollout tasks:

1. After walk-forward evidence on `BTCUSDT 8h/B`, decide whether to materialize
   Phase 3-13 features for:
   - `BTCUSDT 8h/C`;
   - `BTCUSDT 24h/B`;
   - all BTCUSDT roots;
   - ETHUSDT;
   - all core assets.
2. Keep learned PCA/clustering/anomaly models and learned sequence encoders
   deferred until deterministic proxy layers validate.

## Final Assessment

The code and docs are now consistent with a technically validated deterministic
feature stack through Phase 11 on `BTCUSDT 8h/B`. The feature stack is not
predictively promoted.

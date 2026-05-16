# Repository Code Documentation Rollout

Created: 2026-05-16
Status: active maintenance plan

## Goal

Make the repository maintainable by ensuring every maintained module explains
what it owns, how it fits into the workflow, and any important data/temporal
safety assumptions.

## Standard

Follow `docs/development/code-documentation-standard.md`.

## Current Scope

Initial inventory found roughly 210 Python files under:

```text
scripts/
notebooks/
fetchingByBit/
fetchingMultiAsset/
```

This is too large for a safe one-pass comment sweep. Work should be batched so
code comments stay accurate and do not become noise.

## Phase 1: Active HTF And Multi-Asset Workflow

- [x] `notebooks/htf_pythonscript.py`
- [x] `scripts/feature_engineering/htf_asset_registry.py`
- [x] `scripts/feature_engineering/htf_shared_config.py`
- [x] `scripts/feature_engineering/htf_trading_calendar.py`
- [ ] `scripts/feature_engineering/htf_multiregime_pipeline.py`
- [ ] `scripts/feature_engineering/compute_htf_features.py`
- [ ] `scripts/feature_engineering/htf_kernels.py`
- [ ] `scripts/feature_engineering/htf_helper_cache.py`
- [ ] `scripts/feature_engineering/optimize_htf_features.py`
- [ ] `fetchingMultiAsset/*.py`
- [ ] `fetchingByBit/*.py`
- [ ] repo-root `update_data.py`

## Phase 2: Stage-1 And HTF Analysis

- [ ] `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- [ ] `scripts/htf_backtest/catboost/*.py`
- [ ] `scripts/analysis/htf_walkforward_diagnostics.py`
- [ ] `scripts/analysis/htf_causal_multiregime_method_analysis.py`
- [ ] Stage-1 v2 audit scripts.

## Phase 3: Target-Model And Conformal Layer

- [ ] `scripts/target_models/pipeline.py`
- [ ] `scripts/target_models/registry.py`
- [ ] `scripts/target_models/helpers/*.py`
- [ ] `scripts/target_models/calibration/*.py`
- [ ] `scripts/target_models/validation/*.py`

## Phase 4: Legacy And Research Scripts

- [ ] Mark historical scripts as legacy where appropriate.
- [ ] Add module docstrings that point to the current replacement workflow.
- [ ] Avoid heavy refactors unless tests already cover the file.

## Audit Command

```bash
python scripts/maintenance/audit_python_documentation.py \
  --roots scripts notebooks fetchingByBit fetchingMultiAsset \
  --output test_output/python_documentation_audit.md
```

The audit is advisory. Some small private helpers can remain undocumented when
the surrounding code is already clear.

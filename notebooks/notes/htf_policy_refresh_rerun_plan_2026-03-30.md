# HTF Policy Refresh Rerun Plan 2026-03-30

## Objective
- materialize the new final-output feature acceptance policy into live HTF
  optimized/helper training parquets
- do this without touching combined, feature-stage, or label-stage artifacts
- use the supported production path only: plain-script `CELL 14`

## Evidence Base
- policy implementation:
  - [htf_feature_acceptance_registry_implementation_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_feature_acceptance_registry_implementation_2026-03-30.md)
- production entrypoint and supported run path:
  - [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
- current live state proof:
  - optimized metadata still has no
    `final_output_feature_policy_version/signature`
  - current live optimized/helper batches still contain policy-blocked columns

## Supported Run Contract
- run as a plain terminal script, not through an interactive kernel
- do not set `HTF_RUN_LEGACY_NOTEBOOK_CELLS=1`
- keep:
  - `HTF_RUN_MULTI_REGIME_EXTENSION=1`
  - shared defaults from `CELL 14`
  - `rebuild_existing=False`

Supported command:

```bash
HTF_RUN_LEGACY_NOTEBOOK_CELLS=0 \
HTF_RUN_MULTI_REGIME_EXTENSION=1 \
/media/przem/linux_data/conda/envs/ml_env/bin/python notebooks/htf_pythonscript.py
```

## Rerun Scope
Only the final model-facing `1m/target_4class` trees need refresh.

### Affected optimized roots
- `data/htf_optimized`
- `data/htf_optimized_shift4h`
- `data/htf_optimized_24h`
- `data/htf_optimized_24h_shift12h`
- `data/htf_optimized_7d`
- `data/htf_optimized_7d_shift84h`

### Affected helper roots
- `data/htf_with_helpers`
- `data/htf_with_helpers_shift4h`
- `data/htf_with_helpers_24h`
- `data/htf_with_helpers_24h_shift12h`
- `data/htf_with_helpers_7d`
- `data/htf_with_helpers_7d_shift84h`

### Stages that should remain current
- combined/backtest
- raw feature-stage artifacts
- labels
- helper cache

## Why Targeted Rotation Is Still Recommended
The optimizer does contain policy-version invalidation now, so a plain rerun would
recompute optimized outputs from batch `1`. However, targeted rotation is still
the safer operational procedure because it:
- preserves a direct before/after comparison of the current live optimized/helper
  outputs
- prevents any stale final parquets from being mistaken for current artifacts
- makes the rerun scope explicit in logs and manifests

## Safe Rotation Procedure
Before the run, move aside only:
- `data/htf_optimized*/1m/target_4class`
- `data/htf_optimized*/1m/optimized_target_4class_meta.json`
- `data/htf_with_helpers*/1m/target_4class`

Do not rotate:
- feature-stage roots
- label roots
- helper cache roots

## Expected Run Behavior
- combined stages: `current`
- feature stages: `current`
- label stages: `current`
- optimization stages: rebuild from batch `1` under the new policy
- helper materialization stages: rebuild from the refreshed optimized outputs
- validation: pass with policy-blocked columns absent from final model-facing
  outputs

## Post-Run Checks
- optimized metadata should contain:
  - `final_output_feature_policy_version`
  - `final_output_feature_policy_signature`
- policy-blocked columns should be absent from rebuilt optimized/helper batches
- shared validation should pass

## Explicit Non-Goals
- no change to raw source data
- no change to feature-stage parquet schema
- no redesign of sparse-source-gap-sensitive features yet
- no change to helper warmup policy in this rerun

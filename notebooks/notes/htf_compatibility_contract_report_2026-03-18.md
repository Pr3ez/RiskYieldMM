# HTF Compatibility Contract Report

Date: 2026-03-18

## Scope
Repo-wide dependency trace for HTF compatibility contracts that must stay stable during unification.

Checked active code under:
- `scripts/`
- `notebooks/*.py`

Excluded from contract evidence:
- `Archive/`
- markdown notes
- notebook checkpoint noise

## Summary
The active compatibility contracts are narrower than the historical notebook suggests.

Hard preserve in phase 1:
- `bar_in_batch_norm`
- base legacy roots:
  - `data/htf_features`
  - `data/htf_4class_labels`
  - `data/htf_optimized`
  - `data/htf_with_helpers`
- phase-1 `*_shift4h` roots inside the HTF pipeline itself

Preserve for compatibility, but the dependency is weaker:
- `period_8h_start`
- `data/htf_backtest`

Preserve for now as internal bookkeeping contract:
- family/regime metadata columns such as
  - `batch_family`
  - `family_batch_id`
  - `source_base_period_start`
  - `family_period_start`
  - `family_period_end`
  - `family_bar_pos`
  - `source_base_batch_id`
  - `source_half_in_base`
  - `is_label_half`
  - `batch_regime`
  - `batch_duration_hours`
  - `family_shift_hours`
  - `anchor_utc`
  - `entry_window_hours`

## Contract Findings

### 1. `bar_in_batch_norm`
Classification:
- active downstream contract

Why it matters:
- used directly for tail exclusion in production backtest loaders
- used directly for head/tail slicing in active analysis notebooks

Evidence:
- [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py)
  - filters rows with `bar_in_batch_norm <= cutoff`
- [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py)
  - same tail-exclusion logic
- [notebooks/htf_batch_correlation.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_batch_correlation.py)
  - uses it for head/tail windowing during similarity analysis

Phase-1 rule:
- do not rename
- do not remove
- do not silently change semantics

### 2. `period_8h_start`
Classification:
- active compatibility column
- not currently a strong production-compute dependency

Why it matters:
- used as metadata/exclusion column in active analysis
- retained in optimizer bookkeeping exclusions

Evidence:
- [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  - included in `OPTIMIZER_META_COLS`
- [notebooks/htf_batch_correlation.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_batch_correlation.py)
  - excluded from feature matrix
- [notebooks/htf_analyze.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_analyze.py)
  - treated as metadata, not a model feature

Important nuance:
- current active code does not appear to depend on its exact numeric contents for training logic
- but it is part of the stable external artifact shape and should stay in phase 1

Phase-1 rule:
- preserve name and presence
- do not treat it as removable just because it is not heavily used

### 3. Family and Regime Metadata Columns
Classification:
- internal pipeline + optimizer bookkeeping contract
- not currently proven as external model-consumer contract

Checked columns:
- `batch_family`
- `family_batch_id`
- `source_base_period_start`
- `family_period_start`
- `family_period_end`
- `family_bar_pos`
- `source_base_batch_id`
- `source_half_in_base`
- `is_label_half`
- `batch_regime`
- `batch_duration_hours`
- `family_shift_hours`
- `anchor_utc`
- `entry_window_hours`

Evidence:
- [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  - these columns are explicitly kept in `OPTIMIZER_META_COLS`
  - they are treated as bookkeeping, never transformable features
- [scripts/feature_engineering/htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
  - used extensively in validation and family/regime consistency checks

What the trace did not find:
- no active non-pipeline, non-notebook consumer outside optimizer bookkeeping

Phase-1 rule:
- preserve the full family/regime metadata set
- treat removal or renaming as a later cleanup step only after optimizer and validation contracts are intentionally migrated

### 4. Base Legacy Roots

#### `data/htf_with_helpers`
Classification:
- production-critical downstream root

Evidence:
- [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py)
- [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py)
- [notebooks/htf_analyze.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_analyze.py)
- [notebooks/htf_batch_correlation.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_batch_correlation.py)

Rule:
- preserve

#### `data/htf_4class_labels`
Classification:
- production-critical downstream root

Evidence:
- [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py)
- [scripts/htf_backtest/lightgbm/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/lightgbm/utils.py)
- [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)

Rule:
- preserve

#### `data/htf_features`
Classification:
- pipeline-critical root

Evidence:
- [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  - default feature source for optimization

Rule:
- preserve in phase 1

#### `data/htf_optimized`
Classification:
- pipeline-critical root

Evidence:
- [scripts/feature_engineering/optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
  - default optimized output root

Rule:
- preserve in phase 1

#### `data/htf_backtest`
Classification:
- active but weaker dependency

Evidence:
- [scripts/feature_engineering/optimize_distance_windows.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_distance_windows.py)
  - reads `data/htf_backtest/<tf>_HTF_combined.parquet`

Important nuance:
- this is not the main production model-training path
- it is still active code, so the root should remain stable in phase 1

Rule:
- preserve in phase 1

### 5. `*_shift4h` Paths
Classification:
- internal compatibility contract

What the trace found:
- no active external readers outside:
  - [notebooks/htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)
  - [scripts/feature_engineering/htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

Implication:
- `shift4h` naming is not currently a broad downstream public contract
- but it is still a phase-1 compatibility contract because both the legacy notebook path and shared engine still write/read those roots

Rule:
- preserve `*_shift4h` in phase 1
- treat the name as compatibility baggage, not future architecture guidance

### 6. `*_shift12h` and `*_shift84h` Paths
Classification:
- shared-engine internal naming only

What the trace found:
- no active external readers outside the pipeline/notebook implementation

Rule:
- keep stable for now
- they are lower-risk than `*_shift4h` because current active downstream readers were not found

## Decisions Supported By This Trace
- `bar_in_batch_norm` must remain untouched during unification.
- `period_8h_start` should remain present in phase 1.
- the full family/regime metadata set should stay intact until optimizer and validation contracts are intentionally redesigned.
- `htf_with_helpers` and `htf_4class_labels` are hard downstream roots and must not move in phase 1.
- `htf_features` and `htf_optimized` remain pipeline-critical roots and should not move in phase 1.
- `htf_backtest` remains active enough to preserve in phase 1.
- `*_shift4h` should be preserved in phase 1 even though current evidence says it is mostly an internal compatibility path.

## What This Report Does Not Claim
- It does not prove every metadata column is semantically required forever.
- It does not prove `period_8h_start` is a hard model-training dependency.
- It does not decide final post-phase-1 naming cleanup.

Those are later cleanup questions. This report only defines what is unsafe to drop or rename now.

## Recommended Next Step
Use this report to close the phase-6 checklist items that are now evidence-backed, then move to:
- finishing shared validation authority
- simplifying the notebook further into orchestration/debug only
- delaying any compatibility-root renames until after production validation and schema-promotion refresh

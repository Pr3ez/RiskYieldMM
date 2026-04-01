# MTF HTF Workflow Definition Context 2026-04-01

Superseded later the same day.
Current canonical HTF production entrypoint is:
- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)

This note is kept only as historical context from the temporary `mtf_htf_workflow.py`
split experiment.

## Purpose
Collect the verified current-state context needed to define
`notebooks/mtf_htf_workflow.py` as the new supported production workflow entrypoint.

This note is not a migration patch plan. It is the definition input set:
- what production currently does,
- which shared modules already own the real logic,
- what data contracts and quality gates exist,
- what operational run patterns are already proven,
- and which decisions still need to be made explicitly in the new workflow file.

## 1. Current Source Of Truth

### Shared production authority
The actual production HTF logic already lives in:
- [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)
- [compute_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/compute_htf_features.py)
- [htf_kernels.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_kernels.py)
- [optimize_htf_features.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/optimize_htf_features.py)
- [htf_helper_cache.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_helper_cache.py)
- [htf_artifact_utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_artifact_utils.py)
- [htf_shared_config.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_shared_config.py)
- [htf_feature_acceptance.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_feature_acceptance.py)

### Current thin production wrapper
The current production wrapper surface in [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py) is only:
- project/path bootstrap
- run logging/status plumbing
- supported production config block
- `multi_regime_progress_callback(...)`
- `run_supported_multi_regime_pipeline()`
- plain-script launch gate

Everything else in that file is legacy/debug notebook scope.

### Meaning for the new workflow
`mtf_htf_workflow.py` should not re-implement pipeline logic.
It should define and own:
- workflow modes,
- execution intent,
- config/profile selection,
- operational quality gates,
- production entrypoint behavior.

It should delegate actual stage execution to the shared pipeline module.

## 2. Current Stage Graph

The real shared production stage order is already defined in:
- [run_multi_regime_htf_pipeline(...)](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py)

For each regime:

1. combined `B`
2. combined `C`
3. features `B` `1m`
4. features `B` `15m`
5. features `C` `1m`
6. features `C` `15m`
7. distance metrics `15m`
8. labels `1m`
9. optimization `1m`
10. helpers `1m`
11. validation across configured regimes

Important stage ownership facts:
- feature computation is shared and continuous-history for normal engine features
- `C` feature files are materialized from timestamp-aligned base `B` feature rows plus shifted metadata
- optimization/helpers are model-facing stages
- validation is already the shared production pass/fail gate

## 3. Current Production Config Surface

### Shared config constants
From [htf_shared_config.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_shared_config.py):
- `SHARED_PIPELINE_ARTIFACT_VERSION = "2026-03-06-repair-01"`
- thresholds:
  - `5m`: `BREAKOUT=1.6`, `RISK_RATIO=2.5`
  - `15m`: `BREAKOUT=2.1`, `RISK_RATIO=2.5`
- distance windows:
  - `1m`: `240/240/240/120`
  - `5m`: `48/48/48/24`
  - `15m`: `16/16/16/8`
- `SHARED_BREAKOUT_THRESHOLD = 2.1`
- `SHARED_RISK_RATIO = 2.5`
- `SHARED_BREAKFREE_THRESHOLD_1M = 0.001`

### Shared pipeline runtime config
From `MultiRegimeHTFConfig` in [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py):

Core execution:
- `build_regimes`
- `validate_regimes`
- `rebuild_existing`
- `run_optimization`
- `run_helpers`
- `run_validation`

Incremental behavior:
- `feature_incremental_update`
- `feature_incremental_overlap_batches_by_tf`
- `feature_context_batches_by_tf`
- `incremental_distance_metrics`
- `incremental_distance_tail_batches_by_tf`
- `incremental_label_update`
- `incremental_label_tail_batches_by_tf`
- `incremental_helpers_skip_unchanged`
- `helper_overlap_batches_by_tf`
- `incremental_helper_cache_update`
- `helper_cache_overlap_batches_by_tf`

Time/range controls:
- `date_start`
- `date_end`
- `smoke_mode`
- `smoke_start`
- `smoke_end`

Helper behavior:
- `use_canonical_helper_cache`
- `helper_cache_dir`
- `helper_warmup_by_tf`
- `helper_refit_every_by_tf`
- `write_helpers_combined`

Validation/usability:
- `usability_audit_enabled`
- `usability_audit_null_rate_threshold`
- `usability_audit_report_top_n`
- `usability_audit_helper_prefix_batches`
- `usability_audit_fail_on_all_null`
- `usability_audit_fail_on_high_null`

Progress:
- `stage_progress_every_batches`
- `progress_callback`

## 4. Current Data And Artifact Contract

### Regimes and families
Shared production currently supports:
- regimes: `8h`, `24h`, `7d`
- families: `B`, `C`

### Timeframes
- upstream timeframes: `1m`, `15m`
- targets remain `1m` only

### Artifact roots
Defined by `_family_scope(...)` in [htf_multiregime_pipeline.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_multiregime_pipeline.py):

Base roots:
- `htf_backtest`
- `htf_features`
- `htf_4class_labels`
- `htf_optimized`
- `htf_with_helpers`

Compatibility shifted `8h/C` roots:
- `*_shift4h`

Longer regimes:
- `*_24h`, `*_24h_shift12h`
- `*_7d`, `*_7d_shift84h`

Helper cache:
- root defaults to `data/htf_helper_cache`

### Metadata compatibility
Still intentionally preserved:
- `period_8h_start`
- `bar_in_batch_norm`
- family/regime metadata columns:
  - `batch_family`
  - `family_batch_id`
  - `family_period_start`
  - `family_period_end`
  - `family_bar_pos`
  - `source_base_batch_id`
  - `source_base_period_start`
  - `source_half_in_base`
  - `is_label_half`
  - `batch_regime`
  - `batch_duration_hours`
  - `family_shift_hours`
  - `anchor_utc`
  - `entry_window_hours`

### Feature schema
From [features.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/features.md):
- `1m` and `15m`: `128` feature columns
- legacy `5m`: `93` feature columns and remains out of shared production scope

Stored `1m` / `15m` features contain:
- `89` core OHLCV engine features
- `25` source-dependent fetched-data features
- `10` composite derivatives-pressure features
- `4` custom causal `D_*` features

## 5. Current Quality Gate Contract

### Validation authority
The shared pipeline is already the production pass/fail gate.
This was part of the completed unification work and documented in:
- [htf_unification_execution_checklist.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_unification_execution_checklist.md)

Current behavior:
- if shared validation finds failures, the run raises and is not considered successful

### Usability audit
The pipeline also writes usability reports under:
- [test_output/htf_validation_usability](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_validation_usability)

Current defaults:
- null threshold: `0.25`
- top N: `20`
- helper prefix batches: `20`
- fail on all-null: `True`
- fail on high-null: `False`

Meaning:
- all-null model-facing columns are blocking
- high-null-but-not-all-null columns are currently reported, not blocked

### Final-output acceptance policy
Current explicit policy in [htf_feature_acceptance.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/feature_engineering/htf_feature_acceptance.py):
- exclude from model-facing optimized/helpers:
  - `F_I_N_S_fundingZscore_*_zsc`
  - `D_dist_avg_high_w240`
  - `D_dist_avg_low_w240`
  - `D_dist_top5_high_w240`

Important current limitation:
- policy is global by column pattern
- not yet scoped by regime/family/timeframe/stage

## 6. Current Proven Operational Run Patterns

These are the real workflows already used, even if they are not formalized as first-class run modes yet.

### A. Normal incremental production run
Intent:
- normal resumable production materialization
- no legacy replay
- plain script only

Current behavior:
- combined/features/labels/helpers/validation run as needed
- unchanged stages stay `current`
- features often use `incremental_tail`

### B. Optimized/helper policy refresh
Intent:
- materialize new final-output acceptance policy into optimized/helpers only

Documented in:
- [htf_policy_refresh_rerun_plan_2026-03-30.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_policy_refresh_rerun_plan_2026-03-30.md)

Key idea:
- rotate only optimized/helper target trees
- keep combined/features/labels/helper cache current
- rerun through supported production path

### C. Raw-source repair refresh
Intent:
- after upstream raw auxiliary source fix, rebuild downstream artifacts

What actually happened:
- repaired raw `mark/index/premium` source trees
- downstream rebuild still ran mostly as `incremental_tail` for affected feature roots
- newest tails are healthy
- historical corpus remains mixed/stale

### D. Validation/audit-only analysis
Used repeatedly in:
- compatibility audits
- null root-cause traces
- post-repair audits

This is not yet a formal workflow mode in code, but it is clearly needed operationally.

### E. Smoke/bounded run
Shared config already supports:
- `smoke_mode`
- `smoke_start`
- `smoke_end`

So bounded execution is already part of the runtime contract.

## 7. Current Known Good State

### Good / stable now
- shared multi-regime pipeline is the production compute authority
- plain script production execution path is known
- raw auxiliary pagination bug is fixed upstream
- latest rebuilt tails are healthy for:
  - `D_F_N_S_premiumZscore_xlong_zsc`
  - `X_D_fundingBasisPressure_xlong_pct`
- known structurally bad all-null model-facing columns already blocked by policy

### Still unresolved
- historical corpus is still partially stale after raw repair because rebuild was mostly incremental-tail
- `D_dist_bot5_low_w120` remains a real current-tail issue in `B` outputs
- funding z-score remains excluded but not semantically redesigned
- high-null-but-not-all-null columns are still not a blocking quality gate

## 8. Current Data-Quality Reality That The New Workflow Must Respect

From:
- [htf_post_raw_repair_output_audit_2026-03-31.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_post_raw_repair_output_audit_2026-03-31.md)
- [htf_feature_purpose_and_batch_validity_synthesis_2026-03-31.md](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/notes/htf_feature_purpose_and_batch_validity_synthesis_2026-03-31.md)

### Premium/index-derived xlong families
- latest rebuilt tails are healthy
- root-wide reports remain inflated because historical batches are stale
- this is now a corpus-refresh problem, not a current-tail formula bug

### `D_*`
- batch-local by design
- current `B` outputs still leak warmup nulls into final saved rows
- current `C` outputs can be clean because `C` features inherit from timestamp-aligned base `B` feature rows

### Funding z-score
- structurally mismatched to minute-level rolling std on stepwise `8h` funding
- should remain excluded until redesigned or retired

## 9. What The New Workflow File Should Own

The new file should define:
- which workflow mode is being run
- what that mode means operationally
- which stages are intended to run
- expected rebuild intent
- expected artifact scope
- validation/quality strictness
- whether the result is training-usable

The new file should **not** own:
- feature math
- label math
- helper math
- batch-building internals
- optimizer internals

Those remain in shared modules.

## 10. Decisions Still Needed Before The Workflow Is Fully Defined

### Decision 1. Workflow modes
We still need explicit first-class modes, for example:
- `production_incremental`
- `validation_only`
- `smoke`
- `optimized_helper_refresh`
- `raw_source_repair_refresh`
- `full_historical_refresh`

### Decision 2. Training-usable quality contract
We still need to decide:
- should high-null-but-not-all-null columns fail the workflow?
- what null policy is acceptable for final helper parquets?

### Decision 3. `D_*` policy
We still need to decide:
- keep `D_*` batch-local and exclude structurally invalid windows by scope
- or redesign `D_*` as continuous-history features

### Decision 4. Historical refresh policy
We still need explicit rules for:
- when raw-source repairs require full historical rebuild instead of incremental-tail
- whether the workflow should force that automatically or expose it as an explicit mode

### Decision 5. Funding z-score future
We still need to choose:
- redesign on native funding cadence
- or retire the family permanently

## Bottom Line
We already have most of the hard facts needed to define the new workflow.

What is already clear:
- the shared pipeline owns the real production logic
- the new file should be an operational workflow/orchestration layer
- the new file must encode workflow intent explicitly instead of relying on one generic run path
- the next design step is not more reverse-engineering; it is choosing the explicit workflow modes and their quality contract.

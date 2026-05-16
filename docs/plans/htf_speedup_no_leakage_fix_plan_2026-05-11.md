# HTF Speedup No-Leakage Fix Plan

Created: 2026-05-11
Status: phases 1-4 implemented; phase 5 asset subprocess runner deferred

## Goal

Speed up the HTF materialization workflow without changing model-facing results
or weakening the temporal-safety contract.

This plan is based on the maintained HTF documentation and the current code path:

- `README.md`
- `docs/architecture/htf-workflow-architecture.md`
- `docs/REPRODUCIBILITY.md`
- `docs/data/data-contract.md`
- `docs/validation/htf-feature-helper-temporal-audit-2026-05-05.md`
- `docs/plans/htf_multi_asset_update_plan_2026-05-07.md`
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/optimize_htf_features.py`
- `scripts/feature_engineering/htf_kernels.py`
- `scripts/analysis/optimizers/rolling_rank_winsorize.py`

## Non-Negotiable Invariants

1. HTF source rows stay chronological and UTC-normalized.
2. Features may only use data available at or before the feature timestamp.
3. Prediction convention remains "after the current 1m bar closes"; current-row
   OHLCV is allowed only under that convention.
4. Label columns may use future outcome windows, but label-only fields must stay
   out of optimized/helper model-facing feature outputs.
5. The default label policy remains `opposite_family_first_half`:
   - B entries use the matching C first-half outcome window.
   - C entries use the next B first-half outcome window.
6. Latest rows may remain unlabeled when the required future opposite-family
   window is not complete.
7. Stage-1 multi-asset target/context assembly remains pending and must not be
   silently mixed into HTF materialization.
8. Existing batch metadata and directory contracts must remain compatible unless
   the shared HTF artifact version is intentionally bumped.

## Operational Preconditions

1. Do not change or test HTF implementation against the same output roots while a
   production HTF process is writing to them.
   - Either let the active process finish, or stop it intentionally and record the
     last log/status path.
   - A running process keeps its imported Python code in memory, but it can still
     write old-code artifacts while new-code tests are being prepared.

2. Do not clean or rewrite paid/source raw data as part of this speedup work.
   - Parity fixtures should use temporary directories.
   - Real-data proof runs should write to normal HTF artifact roots only after
     unit parity tests pass.

3. Capture a baseline before implementation:
   - latest HTF run log/status file;
   - selected optimizer metadata for one current root;
   - row counts and schema for one label root and one model-facing helper root;
   - current `git status --short --branch`.

4. Any semantic change requires a shared HTF artifact-version bump in
   `scripts/feature_engineering/htf_shared_config.py`. Pure exact-parity
   acceleration should not bump the artifact version.

## Review Findings

### Safe To Optimize

1. Optimizer selection can reuse causal rolling ranks by window.
   - Current `1m` candidates are 3 windows x 3 clip bounds x 2 post transforms.
   - The rolling-rank calculation depends only on the window and historical
     feature values.
   - Clip bounds and post transforms can be applied to cached raw ranks.
   - This preserves the same candidate scores if the cached rank arrays are
     produced by the same causal streaming logic.

2. Opposite-family label distance metrics can be precomputed by label window.
   - In the active `opposite_family_first_half` path, `bar_pos_15m_for_entry` is
     `-1` for every entry row.
   - Every 1m row pointing to the same label-window batch uses the same future
     first-half 15m high/low set.
   - Precomputing count, average high/low, and top/bottom 5 percent high/low per
     label-window batch gives the same labels while avoiding an all-15m scan per
     1m row.
   - The optimized path must only run when this active shape is detected; the
     existing kernel remains the fallback.

3. Asset-level parallelism is structurally possible but should be later.
   - Asset outputs are separated under `data/htf_multiasset/{asset}/`.
   - The current launcher has process-global logging and heartbeat state.
   - Parallelism should therefore be implemented as separate subprocesses per
     asset, not threads inside the existing launcher.
   - This is safe only with an explicit worker limit because optimizer runs can
     use several GB of RAM per process.
   - Worker subprocesses must set `HTF_ASSET_WORKERS=1` or an equivalent guard so
     they cannot recursively spawn more workers.

4. Optimizer selection cache invalidation should be added as a safety fix.
   - The temporal audit notes that cached optimizer configs can become stale when
     feature definitions, labels, target definitions, or candidate grids change.
   - This is not look-ahead leakage, but it is a reproducibility/correctness risk.
   - Store enough early-selection fingerprints to invalidate selection metadata
     intentionally when the selection inputs change materially.

### Do Not Change Yet

1. Do not reduce `n_early_batches`.
   - That changes optimizer selection data and can change selected configs.

2. Do not shrink the optimizer candidate grid.
   - That changes the search space and can change selected configs.

3. Do not change batch file layout.
   - Stage-1 and validation code assume current `batch_*.parquet` roots.

4. Do not skip validation by default.
   - `HTF_RUN_VALIDATION=0` can be useful for targeted local runs, but full
     validation remains the safe default.

5. Do not add cross-asset features in this speedup patch.
   - Cross-asset context belongs to the later Stage-1 target/context assembly
     work and needs separate as-of tests.

6. Do not parallelize regimes or B/C families inside one asset.
   - C combined/features depend on B artifacts.
   - Labels depend on both B and C combined windows.
   - Helper cache/materialization depends on optimized outputs and canonical
     helper-cache source selection.

## Implementation Outcome

Implemented in this branch:

1. Exact-parity regression tests for the opposite-family label kernel and
   grouped optimizer selection.
2. Fast opposite-family label distance path guarded by active-shape detection;
   the previous row-scanning kernel remains the fallback.
3. Optimizer selection rank reuse by rolling-rank window, with validation ranks
   built by a Numba-parallel matrix kernel that preserves the original
   streaming buffer semantics; final streaming application to all batches is
   unchanged.
4. Optimizer selection input signatures:
   - early feature/label file fingerprints;
   - target, timeframe, validation settings, and candidate grid;
   - final model-facing feature policy signature;
   - optimizer selection implementation version.
5. Optimized batch reuse now checks the selected transform config. If the cached
   selection is invalidated and the selected config changes, existing optimized
   batches are rebuilt from the first batch instead of being silently reused.
6. Data-contract label field names were updated to the current
   `dist_avg_*` / `dist_top5_*` / `dist_bot5_*` / `remaining_bars` surface.

Still deferred:

1. Asset subprocess parallelism (`HTF_ASSET_WORKERS` or equivalent).
2. Full one-asset production rerun timing evidence after restarting from the new
   code.
3. Stage-1 multi-asset target/context assembly.

Restart evidence:

- Restarting with base Python remained slow because that environment does not
  have Numba installed.
- Restarting with `ml_env` used Numba and completed the first invalidated
  `8h/B/1m/optimization` stage in about 3m39s, then moved on to helpers and
  `8h/C`.
- The first invalidated root selected the same config as older metadata:
  `L=960`, `clip=(0.01,0.99)`, `post=signed`.

## Phase Notes

Phases 0-4 and 6 are complete. Phase 5 asset subprocess orchestration remains
deferred.

### Phase 0: Baseline And Process Safety

Completed process-safety checks:

1. The old long-running HTF process was stopped intentionally before restarting
   with the new implementation.
2. Baseline metadata targets were identified:
   - `*_labels_meta.json`
   - `optimized_target_4class_meta.json`
   - `_helpers_meta.json`
3. Runtime evidence from the old log and the `ml_env` restart was recorded in
   this plan.
4. Raw source folders were left untouched.

### Phase 1: Exact-Parity Tests First

Implemented tests:

1. `tests/test_htf_label_kernel_parity.py`
   - Build synthetic B/C 1m and 15m windows.
   - Compare current `compute_hybrid_distance_metrics()` output against the new
     opposite-family precompute path.
   - Assert equality for:
     - `dist_avg_high`
     - `dist_avg_low`
     - `dist_top5_high`
     - `dist_bot5_low`
     - `remaining_bars`
   - Include incomplete latest window cases.
   - Include missing `label_window_batch_id` / `-1` batch ids.
   - Include small windows where `top_n = max(1, int(count * outlier_pct))`.
   - Include NaNs in 15m high/low if the current kernel behavior can encounter
     them; parity should use `equal_nan=True`.
   - Assert row-level arrays, not only class distributions.

2. `tests/test_htf_optimizer_selection_parity.py`
   - Build deterministic feature/target data.
   - Compare old per-candidate selection with the grouped-rank selection path.
   - Assert same best config and numerically equivalent scores.
   - Include NaN features and policy-blocked feature names.
   - Preserve the current scoring semantics exactly, including the
     `_should_transform()` feature subset used by `walk_forward_validate()`.

3. Extend model-facing leakage tests.
   - The optimizer regression fixture injects label-only fields into an upstream
     feature batch and asserts the optimized model-facing output drops them.
   - HTF validation asserts optimized/helper schemas never include:
     - `target_4class`
     - `target_long`
     - `target_short`
     - `target_breakfree`
     - `target_name`
     - `close_end`
     - `end_return`
     - `remaining_bars`
     - `dist_avg_high`
     - `dist_avg_low`
     - `dist_top5_high`
     - `dist_bot5_low`
     - `bar_pos_15m`

4. Future cross-asset context remains deferred.
   - This speedup patch does not implement cross-asset features.
   - The later Stage-1 target/context assembly should add an as-of regression
     before any context features are productionized.

### Phase 2: Fast Opposite-Family Label Kernel

Implemented in `scripts/feature_engineering/htf_kernels.py`:

- Detect the active optimized case:
  - `bar_pos_15m_for_entry` is all `-1` for valid rows.
  - `batch_id_entry` references label-window batch ids.
- Precompute per 15m label-window batch:
  - count
  - average high
  - average low
  - top 5 percent average high
  - bottom 5 percent average low
- Emit the same distance arrays by comparing those batch summaries with each
  row's `close_entry`.
- Preserve the current `min_remaining` gate exactly.
- Preserve current `np.sort` / `np.mean` behavior, including NaN behavior, unless
  tests prove NaNs are impossible at this stage.
- Fall back to the existing `compute_hybrid_distance_metrics()` behavior when
  the fast-path assumptions are not met.

No artifact version bump is needed because focused parity tests preserve the
distance arrays and row-level label behavior.

### Phase 3: Optimizer Selection Rank Reuse

Implemented grouped selection in `scripts/feature_engineering/optimize_htf_features.py`:

- Group candidates by `window`.
- For each fold and window, compute causal raw rolling ranks once.
- Apply each candidate's clip bounds and post transform to the cached ranks.
- Score candidates exactly as today.
- Preserve the existing selection metadata fields.

Important guard:

- The final streaming application to all batches should remain unchanged in this
  phase. Only hyperparameter selection is optimized first.
- Do not change `n_early_batches`, candidate generation, fold boundaries,
  `mutual_info_classif(random_state=42)`, target filtering, or final metadata
  field names.

No artifact version bump is needed because parity tests keep best configs and
scores equivalent on deterministic fixtures.

### Phase 4: Optimizer Selection Cache Invalidation

Implemented metadata invalidation when selection inputs change:

- early feature batch fingerprints used by `load_early_batches()`;
- early label batch fingerprints used by `load_early_batches()`;
- target name and target policy/version;
- candidate-grid signature;
- optimizer selection implementation version.

Acceptance rule:

- If these signatures are unchanged, cached config reuse should behave exactly as
  today.
- If they change, rerun selection intentionally before streaming application.

This phase is a safety correction. It can cause future runs to recompute a
cached config after a real feature/label semantic change, which is intended.

### Phase 5: Optional Asset Subprocess Runner

Only after Phase 2, Phase 3, and Phase 4 are stable:

- Add an optional orchestration mode, for example `HTF_ASSET_WORKERS`.
- Default stays `1`.
- Launch separate subprocesses with `HTF_ASSETS=<single_asset>`.
- Keep one log/status file per process.
- Refuse worker counts that are unsafe for local memory if possible.
- Pass through source/label/optimization flags explicitly to each subprocess.
- Force worker subprocesses not to spawn children.

This phase changes execution scheduling only. It must not change artifacts.

### Phase 6: Documentation Cleanup

Completed documentation cleanup:

1. `docs/data/data-contract.md`
   - Updated label field names to the current `dist_avg_*`, `dist_top5_*`,
     `dist_bot5_*`, and `remaining_bars` label surface.

2. `docs/validation/htf-feature-helper-temporal-audit-2026-05-05.md`
   - Added optimizer-rank reuse and label-window precompute parity evidence.

3. `README.md`
   - Added a short note that speedups preserve the existing temporal contract.

4. This plan
   - Updated status and outcome to the implemented state.

## Required Validation Commands

Run focused checks after adding the new tests:

```bash
python -m pytest \
  tests/test_htf_auxiliary_alignment.py \
  tests/test_htf_incremental_resume.py \
  tests/test_htf_multi_asset_pipeline.py \
  tests/test_htf_workflow_contract.py \
  tests/test_htf_label_kernel_parity.py \
  tests/test_htf_optimizer_selection_parity.py \
  -q
```

Run full local test suite:

```bash
conda run -n ml_env python -m pytest -q
```

Run parity checks on a temporary/synthetic fixture before touching production
artifact roots:

- old vs new label distance arrays;
- old vs new row-level label files;
- old vs new optimizer selected config and scores;
- model-facing schema check for label-only column exclusion.

Run a smoke HTF materialization without optimization/helpers first:

```bash
HTF_ASSETS=BTCUSDT,ES \
HTF_ASSET_OUTPUT_MODE=multiasset \
HTF_RUN_OPTIMIZATION=0 \
HTF_RUN_HELPERS=0 \
python notebooks/htf_pythonscript.py
```

Then run one optimized asset end to end:

```bash
HTF_ASSETS=BTCUSDT \
HTF_ASSET_OUTPUT_MODE=multiasset \
python notebooks/htf_pythonscript.py
```

Only after one asset passes validation should `HTF_ASSETS=core` be rerun.
In core mode, crypto and session-based assets run `8h/24h/7d` by default. Use
`HTF_SESSION_REGIMES=8h` only when intentionally rolling session assets back to
the conservative smoke surface.

## Acceptance Criteria

The plan is complete only when all of these are true:

1. Focused parity tests pass.
2. Full local pytest suite passes in `ml_env`.
3. Row-level labels match old behavior on synthetic parity fixtures.
4. Optimizer best config and score table match old behavior on deterministic
   fixtures.
5. Model-facing optimized/helper schemas contain no label-only fields.
6. A one-asset HTF run completes with validation enabled.
7. Runtime evidence shows the targeted stages are faster, with no increase in
   missing labels or validation failures.
8. Documentation has been updated for the stale label-field contract and for any
   implemented speedup.

## Rollback Rules

1. If parity tests fail, keep the old implementation and investigate before
   touching production HTF artifacts.
2. If labels differ beyond floating tolerance, do not accept the label fast path.
3. If optimizer best config differs, do not accept grouped-rank selection.
4. If model-facing outputs gain any label-only columns, stop and fix before any
   Stage-1 work.
5. If a run is interrupted during implementation testing, rerun from the same
   code with existing incremental metadata; use `HTF_FORCE_FULL_REBUILD=1` only
   after an intentional artifact-version or semantic change.

## Current Runtime Evidence

A local BTCUSDT run was observed still active in `7d/B/1m/optimization` after
more than two days. Earlier log lines show:

- `24h/B` labels took about 5h41m.
- `24h/B` optimization took about 14h07m.
- `24h/C` labels took about 5h54m.
- `24h/C` optimization took about 14h05m.
- `7d/B` labels took about 5h51m.
- `7d/B` optimization was still running after more than 15h.

This supports prioritizing label-kernel and optimizer-selection speedups before
parallel asset orchestration.

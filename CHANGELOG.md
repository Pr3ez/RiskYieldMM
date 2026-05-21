# Changelog

All notable repository-level changes are recorded here.

## Unreleased

### Added

- Core multi-asset source workflow through repo-root `update_data.py --core`,
  covering Bybit `BTCUSDT`/`ETHUSDT`, Databento historical futures proxies for
  `EURUSD`, `USDJPY`, `GC`, `CL`, `ES`, and `NQ`, and validated Yahoo Finance
  recent-tail continuation when the local Databento anchor is eligible.
- Free demo source mode via repo-root `python update_data.py --demo`, using
  Bybit for crypto plus Yahoo Finance futures proxies for the non-crypto core
  assets over Yahoo's configured `1m` retention window, with local `15m`
  aggregation and no Databento/Twelve Data calls.
- `fetchingMultiAsset/` provider layer for normalized non-crypto OHLCV data,
  including Databento, Yahoo Finance, Twelve Data fallback/reference support,
  local provider preflight checks, local inventory scanning, resume planning,
  and `1m` to `15m` aggregation.
- HTF asset registry and asset-aware HTF materialization. `HTF_ASSETS=core`
  with `HTF_ASSET_OUTPUT_MODE=multiasset` writes per-asset outputs under
  `data/htf_multiasset/{asset}/`.
- Stage-1-compatible multi-asset dataset assembly. The Stage-1 launcher can now
  build merged target/context roots with `--build-merged-dataset`,
  `--target-assets`, and `--context-assets`, writing ignored outputs under
  `data/htf_multiasset_merged/{target}/{context_hash}/`.
- Experimental Stage-1 label-anomaly runner for `8h/B` research, including
  cleaned 4-class CatBoost, split-class 8-class CatBoost collapsed back to the
  original 4-class target, Confident-Learning-style diagnostics, review-set
  export, matrix decision artifacts, and resume-ready diagnostics docs.
- Stage-1 merged dataset tests and smoke documentation covering exact timestamp
  joins, target-only labels, context prefixing, duplicate checks, null-row
  dropping, sparse merged batch ids, and all-core `8h/B` readiness.
- Calendar-aware canonical HTF OHLCV layer with `crypto_24_7` and
  `futures_session_observed` calendars, open-session gap-fill flags, derived
  canonical `15m` bars, and preserved session metadata in HTF artifacts.
- Canonical multi-timeframe OHLCV materializer that derives `15m`, `1h`, `4h`,
  `8h`, `12h`, and `1d` bars from local canonical `1m` data, with `24h` as a
  CLI alias for `1d`, status/dry-run modes, metadata sidecars, and an explicit
  repo-root `update_data.py --derive-ohlcv-timeframes` post-fetch hook.
- Canonical TA signal flag layer under `TA_backtest_optimization/` that derives
  post-close binary indicator flags from canonical OHLCV timeframes, writes
  reusable per-asset flag/event artifacts, and lets Stage-1 merged dataset
  assembly opt in with `--include-ta-flags --ta-timeframes ...`.
- Research-guided compact TA signal set and diagnostics: compact flags are
  written separately from raw indicator flags, Stage-1 can choose
  `--ta-signal-set raw|compact|all`, and `diagnose_ta_flags.py` reports
  activation rates, dead/always-on flags, long/short conflicts, and high-overlap
  pairs before optimization. Diagnostics now also assign `gold/silver/bronze/fail`
  quality tiers so Stage-1 analysis can reject redundant/noisy flag sets before
  model runs.
- TA-enabled merged Stage-1 datasets now include the TA signal-set/timeframe
  variant in their generated path and run id so baseline, raw TA, compact TA,
  and combined TA smoke runs remain isolated.
- Experimental Stage-1 target-survey layer for triple-barrier four-class labels:
  `materialize_stage1_target_variants.py` writes separate BTCUSDT `8h/B`
  `target_4class_tb_*_v1` label roots, Stage-1 accepts
  `--stage1-target-col`, and target variants receive separate merged dataset
  paths/run ids. Sanity reporting now separates label-eligible entry-window
  invalids from non-entry rows, keeps the original v1 variants for diagnostics,
  and adds `tb_atr_wide_v2`, a wider symmetric ATR candidate that passes the
  BTCUSDT `8h/B` label sanity gate for first Stage-1 comparison.
- Stage-1 merged dataset assembly now has `--merged-batch-min`,
  `--merged-batch-max`, and `--merged-batch-limit` for fast dataset-contract
  smoke tests on mature batch windows; full production merged datasets still
  omit these limits and assemble every target batch.
- Multi-asset HTF tests for asset-specific raw routing, Databento/Yahoo
  recent-tail precedence, opposite-family label-window behavior, session
  calendar gap handling, and session `24h`/`7d` valid-label production.
- Multi-asset implementation plans and source documentation under `docs/plans/`.
- Canonical Python dependency metadata in `pyproject.toml`, including
  lightweight `ci`/`dev` extras and heavier research/Rust extras.
- Dataset-free repository smoke tests for CLI help surfaces, dependency
  metadata, and tracked backup-file hygiene.
- Local verification checkset for Python contract checks, VS Code extension
  checks, and Rust helper checks. Hosted GitHub Actions wiring is deferred until
  repository Actions can run successfully.
- `CONTRIBUTING.md` with branch, PR, artifact, and Dependabot review policy.
- Reproducibility guide for source data refresh, HTF materialization, Stage-1
  walk-forward execution, and local verification.
- HTF data contract with source requirements, metadata invariants, and
  incremental update expectations.
- HTF workflow architecture overview and results card.
- Lightweight verification dependency list in `requirements-ci.txt`.

### Changed

- HTF labels now document and test the `opposite_family_first_half` policy:
  B-family entries label from the next C-family first-half window, and C-family
  entries label from the next B-family first-half window.
- HTF materialization now has guarded speedups for opposite-family label
  distance computation and optimizer hyperparameter selection. The new paths are
  covered by parity tests, preserve the model-facing temporal contract, compute
  validation rolling-rank caches in parallel across feature columns, and
  invalidate optimized output reuse when the selected transform config changes.
- Model-facing HTF optimized/helper outputs now explicitly reject label-only
  future fields; the optimizer drops those fields if they ever appear in an
  upstream feature batch.
- HTF validation now checks `remaining_bars` against the active label-window
  policy, so opposite-family labels are no longer rejected by the older
  same-batch assumption.
- HTF opposite-family labels now resolve the label window by family period start
  instead of sequential batch id, preventing Monday-Friday/session closures from
  shifting B/C batch numbering and labeling against the wrong opposite-family
  window.
- HTF launcher regime routing now enables `8h/24h/7d` for both crypto and
  session assets by default. `HTF_BUILD_REGIMES` and `HTF_VALIDATE_REGIMES`
  select requested regimes; `HTF_SESSION_REGIMES=8h` is available as a
  conservative rollback for session assets only.
- Multi-asset HTF launcher runs now attempt remaining assets after a per-asset
  failure and raise a final summary error at the end; set
  `HTF_FAIL_FAST_ASSET_ERRORS=1` to restore immediate fail-fast behavior.
- Stage-1 batch discovery now uses the highest available `batch_*.parquet` id
  instead of file count, so sparse merged multi-asset roots can be scanned
  correctly.
- Stage-1 merged dataset assembly now drops rows with null model feature values
  after exact timestamp joins and reports them as
  `rows_dropped_by_null_features`, while preserving `null_feature_count=0` in
  written outputs.
- HTF helper validation now treats constant `H_*_garch_persistence` as a known
  fitted-parameter artifact instead of failing the full run.
- Bybit fetching and compatibility aggregation are symbol-aware for both
  `BTCUSDT` and `ETHUSDT`.
- Generated local progress/status artifacts are removed from the merge surface
  and ignored by default, including fetch progress files and HTF run heartbeat
  status JSON files.
- Target-model registry integration tests now skip dataset-loading checks when
  ignored generated `data/datasets/*bar.parquet` files are absent, while keeping
  registry metadata tests always active.
- Replaced deprecated Polars `pl.count()` usage in 8h aggregation with
  `pl.len()`.
- Migrated the Astra VS Code extension lint setup to ESLint flat config for
  ESLint 10 compatibility.
- Deferred hosted CI workflow activation because GitHub Actions is currently
  blocked by an account billing lock.
- Clarified ignored local artifact wording and the distinction between current
  HTF `8h` regimes and legacy derived `*-8h-*` compatibility outputs.
- Clarified documentation boundaries for the current multi-asset HTF workflow:
  active 4-class labeling, legacy 8-class notes, session-aware calendars, and
  the Stage-1 target/context assembly layer.
- Replaced the Astra extension test target that pointed at a missing VS Code
  test runner with a compile-and-lint smoke check.
- Removed tracked local backup files from maintained source/notebook paths and
  added backup ignore patterns.

### Not Yet Implemented

- Downstream causal method analysis, walk-forward diagnostics, and Stage-1
  Step-2 reports still need multi-asset-aware review. The current Stage-1
  launcher can build target/context datasets and run one target asset per run,
  but downstream comparison/reporting layers still assume older run groupings.
- Stage-1 label-anomaly modeling remains research-only. The `8h/B`
  representative run found useful CatBoost signal, but ES/GC validation
  instability blocks promotion to all roots, production Stage-1 training, or
  automatic use of `target_8class_anomaly`.
- As-of/freshness-based cross-asset joins are intentionally deferred. The
  implemented v1 assembly uses exact timestamp joins only and drops rows that
  are missing any selected context asset.

### Security

- Main branch protection, Dependabot security updates, secret scanning, push
  protection, and private vulnerability reporting are enabled at the repository
  settings level.
- Tracked `node_modules` content was removed from Git in earlier hardening work;
  extension dependencies are restored with `npm ci`.

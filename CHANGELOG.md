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
- Multi-asset HTF tests for asset-specific raw routing, Databento/Yahoo
  recent-tail precedence, and opposite-family label-window behavior.
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
- Replaced the Astra extension test target that pointed at a missing VS Code
  test runner with a compile-and-lint smoke check.
- Removed tracked local backup files from maintained source/notebook paths and
  added backup ignore patterns.

### Not Yet Implemented

- Stage-1 and downstream analysis scripts are not fully multi-asset-aware yet.
  The current merge prepares source data and HTF feature/label artifacts per
  asset; the next implementation step is explicit target-asset selection,
  optional causal context-asset joins, and analysis outputs that resolve
  `data/htf_multiasset/{asset}/` roots.
- Cross-asset context features are planned but not yet productionized. They
  should be added after standalone per-asset HTF outputs are reproducible and
  tested for no look-ahead leakage.

### Security

- Main branch protection, Dependabot security updates, secret scanning, push
  protection, and private vulnerability reporting are enabled at the repository
  settings level.
- Tracked `node_modules` content was removed from Git in earlier hardening work;
  extension dependencies are restored with `npm ci`.

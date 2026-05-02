# Changelog

All notable repository-level changes are recorded here.

## Unreleased

### Added

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

- Migrated the Astra VS Code extension lint setup to ESLint flat config for
  ESLint 10 compatibility.
- Deferred hosted CI workflow activation because GitHub Actions is currently
  blocked by an account billing lock.
- Clarified ignored local artifact wording and the distinction between current
  HTF `8h` regimes and legacy derived `*-8h-*` compatibility outputs.

### Security

- Main branch protection, Dependabot security updates, secret scanning, push
  protection, and private vulnerability reporting are enabled at the repository
  settings level.
- Tracked `node_modules` content was removed from Git in earlier hardening work;
  extension dependencies are restored with `npm ci`.

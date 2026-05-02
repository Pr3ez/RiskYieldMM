# Changelog

All notable repository-level changes are recorded here.

## Unreleased

### Added

- GitHub Actions CI workflow for Python contract checks, VS Code extension
  checks, and Rust helper checks.
- `CONTRIBUTING.md` with branch, PR, artifact, and Dependabot review policy.
- Reproducibility guide for source data refresh, HTF materialization, Stage-1
  walk-forward execution, and local verification.
- HTF data contract with source requirements, metadata invariants, and
  incremental update expectations.
- HTF workflow architecture overview and results card.
- CI dependency list in `requirements-ci.txt`.

### Changed

- Migrated the Astra VS Code extension lint setup to ESLint flat config for
  ESLint 10 compatibility.

### Security

- Main branch protection, Dependabot security updates, secret scanning, push
  protection, and private vulnerability reporting are enabled at the repository
  settings level.
- Tracked `node_modules` content was removed from Git in earlier hardening work;
  extension dependencies are restored with `npm ci`.

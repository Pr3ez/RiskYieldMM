# HTF Pre-Phase-9 Backup

Date: 2026-03-18

## Scope
- Create a full snapshot of the completed production HTF artifact trees before
  starting the Phase 9 richer-feature schema promotion.
- Preserve the previous long-run outputs for later comparison against the
  refreshed workflow.

## Backup Root
- [htf_production_snapshot_pre_phase9_20260318_131026](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/backups/htf_production_snapshot_pre_phase9_20260318_131026)

## Included Roots
- `data/htf_backtest*`
- `data/htf_features*`
- `data/htf_4class_labels*`
- `data/htf_optimized*`
- `data/htf_with_helpers*`
- `data/htf_helper_cache`

The exact source-root list is recorded in:
- [source_roots.txt](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/backups/htf_production_snapshot_pre_phase9_20260318_131026/source_roots.txt)

## Verification
- Copy method: `rsync -a --relative --stats`
- Copy log:
  - [rsync.log](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/backups/htf_production_snapshot_pre_phase9_20260318_131026/rsync.log)
- Verification manifest:
  - [manifest.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/backups/htf_production_snapshot_pre_phase9_20260318_131026/manifest.json)

Verified values:
- copied regular files: `193,440`
- copied total size: `29,905,430,070` bytes
- verification result: `true`
- verified source roots: `31`

## Notes
- This step was a backup only. It did not rebuild, clear, or overwrite the
  source HTF production trees.
- The backup root contains two administrative files in addition to the copied
  production files:
  - `source_roots.txt`
  - `rsync.log`
- `manifest.json` was written after the copy and records per-root source versus
  backup file counts and total bytes.

## Next Step
- Use the shared production path for the actual Phase 9 richer-feature schema
  promotion, with the backup snapshot kept as the before-state comparison point.

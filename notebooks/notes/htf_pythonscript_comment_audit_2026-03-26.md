# HTF Python Script Comment Audit

Date: 2026-03-26

## Scope
Review and update stale or misleading inline documentation in
`notebooks/htf_pythonscript.py` after the HTF unification work.

## What Was Corrected

- Replaced the stale opening summary that still contained old hard-coded batch
  counts, old performance claims, and an outdated description of the production
  path.
- Updated the opening documentation to reflect the real ownership boundary:
  - Cells `1-13` are legacy/debug/back-compat only
  - Cell `14` is the supported production HTF path
- Reworded setup/path comments so the script no longer implies the legacy cells
  are the default production flow.
- Reworded the legacy feature-cell incremental comments so they no longer claim
  to be the production default.
- Corrected the legacy Cell 8 header comment, which still described an obsolete
  8-class scheme even though the code and outputs are `4-class`.
- Corrected the legacy Cell 8 output comment so it now describes per-batch label
  files rather than a single `{tf}_labels.parquet` output.
- Removed a stale hybrid-label performance claim from Cell 9.
- Reworded the helper-materialization comments in Cell 11 so they describe the
  current raw-input invariant instead of reading like an unfinished hotfix note.
- Normalized remaining stale wording like `CORRECTED` and `production default`
  where it no longer reflected the current architecture.

## Validation

- `python -m py_compile notebooks/htf_pythonscript.py`

## Result

The script comments now align materially better with the current architecture:

- supported production path: shared `CELL 14`
- retained notebook body: legacy/debug island
- legacy-only `5m` scope remains clearly fenced
- helper/feature/label comments no longer describe outdated behavior

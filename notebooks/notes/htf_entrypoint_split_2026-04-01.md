# HTF Entrypoint Split 2026-04-01

Superseded later the same day.
Current canonical production entrypoint is:
- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)

## Historical Scope
- archive the mixed legacy/production `notebooks/htf_pythonscript.py`
- create a clean production-only entrypoint in `notebooks/mtf_htf_workflow.py`
- leave `notebooks/htf_pythonscript.py` as a thin redirect shim so legacy code
  cannot run accidentally during normal production execution

## Result

### Archived legacy notebook body
- [htf_pythonscript_legacy_2026-04-01.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/Archive/htf_pythonscript_legacy_2026-04-01.py)

### Temporary production entrypoint used during the split
- `notebooks/mtf_htf_workflow.py` (removed later the same day)

### Temporary thin redirect shim
- [htf_pythonscript.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/notebooks/htf_pythonscript.py)

## Historical Ownership After The Split

### `notebooks/mtf_htf_workflow.py`
Owns:
- production-only bootstrap
- production logging/status behavior
- shared production config block
- production workflow callback
- call into the shared multi-regime HTF pipeline

Does not own:
- legacy notebook replay
- legacy `5m`
- inline old feature/label/helper/validation logic

### `notebooks/htf_pythonscript.py`
At the time of this note it owned only:
- a deprecation message
- redirect into `mtf_htf_workflow.py`

### Shared modules under `scripts/feature_engineering/`
Still own the real production implementation.

## Why This Split Was Needed
- the previous `htf_pythonscript.py` mixed a thin production launcher with a
  large retained legacy notebook body
- that made the file ambiguous and easy to misuse
- archiving the legacy body removes accidental replay risk without changing the
  shared production implementation itself

## Current State
- `htf_pythonscript.py` is again the single supported HTF production entrypoint
- the archived mixed legacy body still lives in
  [htf_pythonscript_legacy_2026-04-01.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/Archive/htf_pythonscript_legacy_2026-04-01.py)
- this note is kept only as a historical record of the temporary split

# HTF Phase 8 Simplification Audit

Date: 2026-03-18

## Scope
Audit `notebooks/htf_pythonscript.py` after the Phase 8 execution-flow change to identify:
- what still belongs to the supported production path
- what remains only for legacy/debug scope
- what can be removed later versus what must stay for compatibility in phase 1

## Main Result
The notebook is no longer the default production compute path, but it still contains a large legacy compute island.

Important distinction:
- supported production execution now short-circuits directly into `run_supported_multi_regime_pipeline()`
- the remaining large body of notebook code is still present, but it belongs to the legacy/debug path unless legacy replay is explicitly enabled or the file is used interactively

So the remaining Phase 8 work is mainly structural clarity and cleanup, not a hidden production-authority conflict.

## Verified Production-Owned Notebook Responsibilities
These notebook responsibilities are still valid and should remain notebook-owned:
- runtime bootstrap and path setup
- run logging and status JSON
- heartbeat and progress formatting
- `CELL 14` wrapper: `run_supported_multi_regime_pipeline()`
- explicit shared-path config surface
- user-facing production/legacy messaging

## Verified Legacy/Debug-Only Scope
Everything after the short-circuit gate and before `CELL 14` is still the legacy/debug island.

This includes:
- legacy `8h` combined generation
- legacy feature batching
- legacy label generation
- legacy optimization/helper stages
- legacy validation
- legacy `5m` logic

These sections are not part of the supported production run recipe anymore.

## Remaining Compatibility Shims
The notebook still keeps thin wrappers around shared implementations for the legacy path:
- artifact/control helpers
- kernel helpers

These wrappers are still justified in phase 1 because they preserve legacy notebook conventions such as:
- project-relative fingerprint serialization
- notebook-local logging
- legacy metadata formatting details

So they should not be removed blindly just because shared implementations now exist.

## What Was Updated In This Audit
- added an explicit legacy/debug boundary comment block in `htf_pythonscript.py`
- added an explicit comment that the artifact/control and kernel wrappers are legacy/shared compatibility shims for cells `1-13` only

These are clarity changes only; no behavior change is intended.

## What Still Needs To Happen In Phase 8
- decide which remaining compatibility wrappers can be retired safely after final acceptance
- continue reducing ambiguity between:
  - supported production path
  - legacy/debug notebook replay
- complete naming/ownership cleanup so module boundaries are obvious from the file layout

## Conclusion
The notebook is already structurally safer than before:
- default script execution uses the shared production path only
- the remaining large notebook compute body is legacy/debug scope, not supported production scope

The next safe Phase 8 step is not broad deletion. It is targeted cleanup:
- verify which wrappers are still needed for phase-1 compatibility
- remove only the ones that no longer carry compatibility behavior

# Raw V8 Step-2 V2 parent pilot runner design

Date: 2026-08-10  
Status: **A4-P6-R DESIGN FROZEN — IMPLEMENTATION NOT YET ACCEPTED**

## 1. Decision

`A4-P6-R` will add one parent-owned runner at the already frozen path:

```text
scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py
```

The runner is an orchestration and enforcement component, not a fourth
semantic implementation. It must execute the accepted separate producer and
independent verifier through their fixed `python -I -S -B` CLIs. It may not
import either role, copy either role's marker, derive a witness, repair a
result, or read the accepted producer report as an answer catalog.

The only legal six-case authority selector is the packed successor boundary.
The predecessor constructive boundary and its original six-case test remain
historical expected-red evidence. In particular, the active case-435 row uses
successor logical plan
`343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8`,
not the predecessor plan stored in the original pilot fixture.

## 2. Chosen execution architecture

The runner uses one private sibling staging root for the complete pilot:

```text
validate and snapshot authorities and all three role sources
  -> for each fixed pilot position 1..6
       fork -> setrlimit -> execve accepted producer
       validate and snapshot the closed candidate root
       fork -> setrlimit -> execve accepted verifier
       prove candidate closure unchanged
       validate the closed verified root and per-case F2 vector
  -> reconcile all 18 whole-run F2 metrics using frozen SUM/MAXIMUM modes
  -> recheck every parent-owned authority/source snapshot
  -> build and validate the identity-bound pilot manifest
  -> fsync files/directories
  -> publish the complete staging directory by one root-last rename
```

Any exception, child failure, timeout, noisy success, resource excess,
authority drift, closure mutation, malformed result, F2 excess, or publication
collision removes the private staging tree and leaves no accepted output root.

## 3. Process and resource boundary

The parent, rather than either semantic child, owns process enforcement:

- fixed argv and a minimal deterministic environment;
- no shell and no `subprocess` API;
- `fork`, `setrlimit`, `execve`, and Linux `wait4`;
- zero core files, frozen CPU/address-space/file-size/open-file ceilings;
- monotonic wall watchdog with process-group termination;
- bounded nonblocking stdout/stderr capture;
- allocated-block monitoring for private temporary and publication staging
  storage; and
- post-`wait4` CPU and peak-RSS checks.

Runtime telemetry is deliberately nonsemantic. It can reject a run but cannot
enter an identity, change F2, or repair a semantic result.

## 4. Output and check modes

The public CLI has exactly one of two fixed modes:

```text
--repository-root ROOT --boundary PACKED_BOUNDARY --write-output-root ABSENT
--repository-root ROOT --boundary PACKED_BOUNDARY --check-output-root EXISTING
```

Write mode requires an absent output root and publishes it last. Check mode
performs a read-only reconstruction of the complete manifest, case closures,
source authorities, identities, and F2 reconciliation. It never creates,
repairs, normalizes, or deletes the checked root.

The manifest remains the frozen `constructive_pilot.v2` schema. Its seed and
manifest IDs are the packed successor IDs. Its six case rows come from the
versioned successor target delta. Candidate and verified closure digests are
recomputed from ordered regular-file records; no child-reported directory
digest is trusted.

## 5. Alternatives rejected

### Import the producer or verifier

Rejected because it collapses process, import, namespace, failure, and
resource boundaries and violates the frozen role contract.

### Use `subprocess.run`

Rejected because the contract specifically assigns fixed `fork` / `setrlimit`
/ `execve` / `wait4` enforcement to the parent.

### Reuse the predecessor six-case test as the active target

Rejected because its authority intentionally keeps five successor cases red
and binds the pre-correction case-435 plan. It remains historical evidence.

### Publish each case directly under the final root

Rejected because a later failure would expose a partial accepted pilot.

### Copy expected candidates or results from the accepted producer report

Rejected because the runner would become answer-bearing. The historical report
is usable by independent acceptance tests, but the runner itself must derive
only structural bindings from frozen authorities and child outputs.

### Add a public failure-injection flag

Rejected because it expands the frozen CLI and creates a production bypass.
Rollback is tested through an internal orchestration seam plus public
fail-closed/check-mode cases.

## 6. Acceptance boundary

`A4-P6-R` is accepted only if independent tests establish:

1. the source marker, import allowlist, role separation, fixed child paths,
   process controls, and absence of accepted answer literals;
2. one exact fail-first transition from absent runner to green runner suite;
3. two complete write runs with byte-identical manifests and closure snapshots;
4. a read-only check run that leaves every byte and mode unchanged;
5. exact six-case IDs, result/resource ledgers, and full-run F2 reconciliation;
6. candidate immutability across verifier execution;
7. invalid CLI, pre-existing output, malformed/partial check root, child failure,
   and internal rollback all fail without an accepted or private leftover;
8. accepted producer and verifier source bytes remain unchanged; and
9. Stage-1 control and documentation move one pointer only, to `A4-P6-E`.

This packet does not accept the six-case end-to-end gate, the 475-case result
campaign, Raw V8 Step 2, Stage 1, Stage 2, live trading, or profitability.


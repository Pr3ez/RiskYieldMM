# Raw V8 Step-2 V2 all-case campaign contract design

Date: 2026-08-11  
Status: **A4-R475-T DESIGN FROZEN — CONTRACT-ONLY PACKET — IMPLEMENTATION REMAINS FAIL-FIRST**

## 1. Decision

`A4-R475-T` freezes a new versioned producer, verifier, and parent-runner
surface for the complete 475-case constructive campaign. It does not widen or
edit the accepted six-case binaries. Those sources remain immutable regression
authorities for cases 5, 24, 54, 69, 435, and 475.

The selected campaign architecture is:

```text
exclusive single-writer lock
  -> immutable campaign anchor
  -> case 0001 producer -> verifier -> parent case commit
  -> case 0002 producer -> verifier -> parent case commit
  -> ...
  -> case 0475 producer -> verifier -> parent case commit
  -> exact 18-metric all-case reconciliation
  -> complete deterministic campaign manifest
  -> fsync complete private tree
  -> rename private work root to absent accepted root once
```

The first complete qualification remains deliberately sequential. Parallel
execution may be proposed only as a later version that reproduces the accepted
sequential semantic output exactly.

## 2. Why the six-case binaries cannot simply be widened

The current producer has six explicit witness constructors and rejects every
other case at its CLI allowlist. The current verifier has a reusable recurrence
engine, but typed-legality and application-rule execution still dispatch only
the same pilot cases. Therefore removing the allowlist would expose unsupported
semantic paths; it would not create an all-case implementation.

The effective all-case universe is also not identical to the base seed at one
coordinate. Cases 1–434 and 436–475 use their base-seed plans, while case 435
must resolve through the accepted exactness successor delta and packed-context
transport. A new role version must preserve that dispatch explicitly.

## 3. Complete execution-family decomposition

The contract independently derives 475 ordered execution records:

| Execution family | Cases | Required behavior |
|---|---:|---|
| intrinsic template attainment | 66 | construct and independently validate exact typed attainers from the frozen template and codec closure |
| generic profile attainment | 406 | prove P1 legality and P3 equality for an independently retained witness; a structural P2 superset alone is never accepted as exact |
| signed analytic exact profile | 1 | preserve the accepted case-69 analytic endpoint and full typed application validation |
| corrected application-exact profile | 1 | preserve case 435’s accepted successor plan, C3 exact cell, 67-object packed context, and 137-application replay |
| local minimality | 1 | preserve case 475’s exact adjacent crossing and single-field minimal mutation proof |

The case ledger is ordered strictly from 1 through 475. Each record binds the
case kind, row/type/profile coordinates, effective logical plan, transport, and
execution family through its own domain-separated semantic ID. The complete
ledger is additionally bound by a canonical hash and ledger ID.

## 4. Alternatives evaluated

### Edit the accepted pilot roles in place

Rejected. It destroys the byte identities that make the pilot a useful
regression authority and hides the fact that generic typed legality and witness
synthesis are absent.

### One monolithic 475-case transaction with no checkpoints

Rejected. Any process, storage, or power failure would discard all prior work,
and there would be no trustworthy resume boundary.

### Publish each verified case directly as accepted

Rejected. It exposes a partial campaign as accepted state and makes whole-run
F2 failure impossible to roll back atomically.

### Run cases concurrently from the first all-case attempt

Rejected for the baseline version. Completion-order nondeterminism, concurrent
storage growth, multiple mutable writers, and more complicated failure
reconciliation add risk before generic semantic coverage is qualified. The
six-case timing does not justify claiming that arbitrary all-case concurrency
fits the frozen budgets.

### Sequential resumable case commits with root-last publication

Selected. It gives deterministic ordering, one mutable owner, bounded
simultaneous child resources, safe reuse of already verified work, and no
partial accepted root. Its performance cost is acceptable for the first
qualification campaign and can be measured before designing a parallel V2.

## 5. Checkpoint and resume semantics

The future runner owns a deterministic private work root and a separate kernel
`flock` held for every mutating invocation. The anchor binds the campaign
contract, effective authorities, complete case ledger, and the source
identities of the three newly accepted role versions.

Each case is built under a recognized private attempt root. The producer emits
one closed candidate root; the verifier emits one separate closed verified
root; the parent proves candidate immutability, validates both closures and all
18 metrics, writes the case commit last, fsyncs the tree, and renames it to an
absent four-digit case directory.

On resume:

1. acquire the exclusive lock;
2. revalidate the anchor, every authority, and every role source;
3. validate every committed case from position 1 without trusting filenames or
   stored hashes alone;
4. reject any corrupt, ambiguous, reordered, duplicate, or non-contiguous
   checkpoint without repairing, deleting, or skipping it;
5. remove only a recognized uncommitted attempt as rollback; and
6. execute only the lowest missing position.

A case failure removes the current uncommitted attempt but preserves the
already verified prefix. No checkpoint is an accepted campaign result.

## 6. Resource semantics

All 12 immutable F0 records and all 18 immutable F2 records are copied exactly
from their accepted authorities. No observed run may raise, round again, tune,
or repair them.

- F0 process and artifact limits apply independently to every producer and
  verifier child.
- The complete private work tree must remain within the frozen publication
  staging storage ceiling.
- Every verified case must fit all 18 `f2_per_case` limits.
- The parent aggregates all 475 vectors using each frozen `SUM` or `MAXIMUM`
  mode.
- Final acceptance requires every aggregate to equal the preflight
  `required_full_run` value and remain at or below `f2_full_run`.
- Wall, CPU, RSS, and storage telemetry may reject a run but never enters a
  semantic identity.

The exact required full-run vector remains:

```text
[475, 29189597, 66119, 417528, 170915620, 1735, 66119,
 44461267, 329067149, 367039374, 619175993, 4160, 4198492,
 46268, 17, 569, 54297, 15585644]
```

## 7. Publication semantics

After all 475 case commits validate, the runner reconstructs the aggregate,
rechecks every authority/source/case closure, writes the deterministic campaign
manifest, and fsyncs the complete private tree bottom-up. It then renames that
work root to the absent accepted root exactly once and fsyncs the parent.

An existing accepted root, authority drift, source drift, malformed closure,
missing case, F2 mismatch, or fsync/rename error rejects without overwrite,
merge, normalization, or repair. Check mode is strictly read-only.

## 8. Implementation order

The contract freezes one active pointer at a time:

1. `A4-R475-V0` — versioned verifier authority resolver, generic typed
   legality, and rule-AST foundation;
2. `A4-R475-V1` — all 66 intrinsic-template cases plus six-case regression;
3. `A4-R475-V2` — all 406 generic profile-attainment cases;
4. `A4-R475-V3` — special cases 69/435/475 and full verifier acceptance;
5. `A4-R475-P` — independent generic witness synthesis and all-case producer;
6. `A4-R475-R` — resumable single-writer runner and crash/recovery matrix; and
7. `A4-R475-E` — complete execution, independent replay, and acceptance.

This ordering establishes the semantic verifier before trusting producer
outputs and establishes both single-case roles before campaign orchestration.

## 9. Evidence boundary and nonclaims

This is a repository-specific deterministic protocol decision. External
research would not override the frozen byte authorities, case semantics, or
resource ceilings, so no web evidence was needed for this packet.

`A4-R475-T` does not implement any new role, produce any new constructive
maximum, start the 475-case campaign, accept Raw V8 Step 2, exit Stage 1, or
claim live readiness, trading safety, predictive edge, or profitability.


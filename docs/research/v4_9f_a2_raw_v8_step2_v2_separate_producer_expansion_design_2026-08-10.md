# Raw V8 Step-2 V2 separate-producer expansion design

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-P`  
**Design state:** `IMPLEMENTED_AND_ACCEPTED_BY_A4_P6_P`  
**Formal Stage 1 state:** `NO-GO`  
**Parent runner:** `ABSENT_AND_HELD`

## 1. Objective and nonclaims

Expand the one accepted `SEPARATE_PRODUCER` role so it can construct legal,
closed candidates for pilot cases `5`, `24`, `54`, `69`, `435`, and `475`.
The accepted independent verifier remains the only semantic authority: the
producer supplies data, never a maximum, upper-bound, resource, result, or
acceptance claim.

This packet does not release the parent runner, run the six-case pilot as one
transaction, complete the 475-case campaign, close Raw V8 Step 2 or Stage 1,
or claim trading readiness, predictive edge, or profitability.

## 2. Hidden boundary issue found before implementation

The accepted fail-first module
`tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py`
is predecessor evidence. It passes the original constructive boundary to both
children and expects five producer failures plus the absent runner. The
accepted V4 verifier deliberately supports only case 5 under that predecessor
authority. Cases 24, 54, and 69 require the exact-delta successor authority;
case 435 additionally requires the packed-context authority; case 475 is
accepted only by the V4 packed successor.

Consequently, changing only the producer cannot make the frozen predecessor
target green. Doing so would either produce predecessor-bound candidates that
the verifier correctly rejects, or silently bypass the accepted authority
resolver. Both are invalid.

The solution is a versioned successor qualification target using:

```text
scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_context_pack_boundary_delta_v49f.json
```

for both producer and verifier. The predecessor fail-first target remains
historical expected-red evidence and must keep its exact failure set.

## 3. Alternatives challenged

| Alternative | Benefit | Decisive weakness | Decision |
|---|---|---|---|
| Make predecessor mode accept all six cases | Minimal test change | Contradicts the accepted verifier authority resolver and loses corrected case-435 identity | Rejected |
| Add a second producer role/path | Clean source split | No accepted implementation-role authority; the packed correction preserves the role records | Rejected |
| Import or execute verifier/C2 proof code | Reuses working logic | Collapses independence, violates the no-dynamic-import/no-subprocess boundary, and can leak proof answers | Rejected |
| Store a precomputed case-435 witness/candidate as producer input | Fast runtime | Violates the frozen shared-material policy and does not scale to the later 475-case campaign | Rejected |
| One role source with predecessor case-5 compatibility and a packed-successor dispatcher | Preserves the frozen role path and old case-5 contract while using the correct authority for the six-case packet | Requires explicit authority loading, independent constructors, and versioned checkpoint handling | **Selected** |

No external literature search is required for this decision. It concerns
repository-local byte identities, authority resolution, role separation, and
fail-closed process behavior; external sources cannot validate those facts.

## 4. Authority-mode contract

The fixed producer CLI remains:

```text
python -I -S -B PRODUCER \
  --repository-root ABSOLUTE_ROOT \
  --boundary ABSOLUTE_FROZEN_BOUNDARY \
  --case-position CANONICAL_DECIMAL \
  --output-root ABSENT_ABSOLUTE_OUTPUT
```

Two modes are permitted:

1. `PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1`
   - accepts case 5 only;
   - preserves the exact accepted 1,333-byte case-5 candidate;
   - rejects cases 24, 54, 69, 435, and 475.
2. `SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1`
   - accepts exactly cases 5, 24, 54, 69, 435, and 475;
   - validates the predecessor boundary/seed/manifest, exact-delta seed,
     manifest and boundary records, and packed-context correction before
     construction;
   - binds successor seed/manifest IDs and the corrected case-435 plan;
   - keeps every F0 and F2 value unchanged.

Unknown paths, intermediate successor-only paths, duplicate/extra inputs,
noncanonical case strings, source aliases, authority aliases, or drift reject
before publication.

## 5. Independent construction strategy

The producer does not contain accepted result IDs, receipt IDs, proof-resource
vectors, certified maxima, or verifier branches. It constructs candidate data
from the frozen schema/inventory/plan authorities:

| Case | Constructor | Information source |
|---:|---|---|
| 5 | Exhaust the exact Boolean record alternatives and select the longest canonical value | Structural registry |
| 24 | Derive the owner payload budget from the owner codec and canonical shell; solve array cardinality plus safe-integer decimal-width residue; reseal the owner context object | Inventory + structural registry |
| 54 | Derive the 512-member ordered vocabulary and fill the last legal text member to the descriptor codec boundary | Structural registry |
| 69 | Start from the fixed local-shutdown result, choose the longer legal nullable-SHA and unrestricted-safe-integer alternatives, reseal the result, and bind exact witness/spec references | Inventory + structural registry + profile binding |
| 435 | Recompute closed scalar/DFA/status/method/reason proposals, exhaust the coupled A1 tuple, select longest legal field witnesses, assemble 67 observations and the root, then pack the 67 non-inline logical context objects | Inventory + structural registry + predecessor P1 schedule; no C1/C2/verifier import |
| 475 | Search legal one-field integer mutations, find the minimum absolute delta whose constructed prospective result crosses the owner codec, compare all mutable fields, and emit the unique objective winner | Inventory + structural registry + local plan |

The case-435 constructor deliberately reuses the *algorithmic design* proven
by the earlier independent C2 work, but it is reimplemented inside the
producer role. It neither imports nor executes the C2 source, its runtime, its
certificate, the exactness join, or the verifier. The accepted verifier then
recomputes P1, P2, P3, F0, and F2 independently.

## 6. Publication and input closure

The producer must snapshot and later recheck every file it actually reads,
including its own single-link source and all selected authority deltas. It
must remain within immutable F0:

- at most 64 input files;
- at most 67,108,864 pinned input octets;
- each JSON/context-pack file below its frozen individual limit;
- exact bounded read with EOF and metadata recheck;
- no symlink, hard-link alias, FIFO, device, socket, or source alias.

Candidate publication remains all-or-nothing. The private root is mode 0700,
candidate/context files are mode 0600 and single-link, directories are mode
0700, all files and directories are fsynced, inputs are rechecked immediately
before the final rename, and any failed attempt removes only the producer's
own private staging tree.

## 7. Checkpoint transition rule

`A4-P`, the predecessor six-case fail-first target, and `A4-P6-V-A` are
historical accepted checkpoints. Their recorded byte identities and report
remain evidence of what was accepted before producer mutation. A downstream
source change cannot honestly keep re-executing a report whose purpose was to
prove that the producer was still case-5-only.

`A4-P6-P` therefore requires a successor acceptance artifact that:

1. preserves and identity-binds the earlier acceptance report and its exact
   producer hash as historical evidence;
2. never rewrites the old report to pretend it observed the new state;
3. independently reviews the new producer source and authority closure;
4. runs predecessor case-5 compatibility;
5. runs two packed-successor producer/verifier passes for all six cases;
6. proves the frozen predecessor expected-red set is unchanged;
7. proves the parent runner is still absent; and
8. moves the control pointer only after all hostile and integrated checks pass.

## 8. Fail-first and acceptance criteria

Before implementation, the successor target must fail exactly at the six
packed-successor producer invocations while its static authority, source-role,
legacy case-5, forbidden-claim, and absent-runner checks pass.

Acceptance requires:

- all six candidates produced twice with byte-identical closures;
- all twelve verifier runs accepted with byte-identical result/receipt/resource
  closures per case;
- candidate closures unchanged by verification;
- exact predecessor case-5 bytes unchanged;
- cases 24/54/69/435/475 still rejected in predecessor mode;
- hostile authority, CLI, filesystem, context-pack, and source-coupling tests
  reject fail-closed;
- no verifier, proof checker, accepted result vector, dynamic import, or child
  process in producer source;
- immutable F0/F2 values and accepted verifier bytes unchanged;
- parent runner absent; and
- Stage 1 remains formal `NO-GO`.

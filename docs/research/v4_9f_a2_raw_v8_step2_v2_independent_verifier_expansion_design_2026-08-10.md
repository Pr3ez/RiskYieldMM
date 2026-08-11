# Raw V8 Step-2 V2 independent-verifier expansion design

**Date:** 2026-08-10  
**Formal sub-gate:** `A4-P6-V`  
**Current work packet:** `A4-P6-P`  
**Decision:** `IMPLEMENTATION DESIGN FROZEN; V0/V1/V2/V3/V4/V-A AND FORMAL VERIFIER EXPANSION ACCEPTED`  
**Stage 1:** `NO-GO`

Implementation status is recorded by the
[`V0 acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_expansion_v0_acceptance_2026-08-10.md),
[`V1 acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_expansion_v1_acceptance_2026-08-10.md),
[`V2 acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_expansion_v2_acceptance_2026-08-10.md),
[`V3 acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_expansion_v3_acceptance_2026-08-10.md),
[`V4 acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_expansion_v4_acceptance_2026-08-10.md),
[`V-A acceptance`](v4_9f_a2_raw_v8_step2_v2_independent_verifier_acceptance_2026-08-10.md),
the accepted
[`case-435 packed-context boundary`](v4_9f_a2_raw_v8_step2_v2_case435_context_pack_boundary_acceptance_2026-08-10.md),
and the mutable
[`Stage 1 execution control`](stage1_execution_control_2026-08-08.md). Packet
states and the immediate action below are execution metadata, not changes to
the frozen verifier design. V0/V1/V2/V3/V4 and the independent acceptance
review `V-A` are accepted; formal verifier expansion is closed and the
separate producer packet `A4-P6-P` is now active.

## 1. Purpose

This design turns the accepted case-435 exact-delta transition into an
executable, independently checked verifier expansion for cases 24, 54, 69,
435, and 475. It preserves the already accepted case-5 verifier and does not
by itself release any producer or parent runner; the later accepted V-A review
releases only the separate producer implementation packet.

The expansion must prove the complete verifier decision, not merely compare a
candidate with a stored answer:

```text
accepted predecessor authorities
  + accepted C3 exactness theorem
  + four accepted D delta authorities
  -> exact effective-authority resolution before candidate access
  -> closed candidate/context-object resolution
  -> independent structural or analytic P2 execution
  -> intrinsic and cross-application P1 execution on retained bytes
  -> measured P3 equality or exact local-shutdown minimality
  -> immutable per-case F2 enforcement
  -> atomic verified bundle publication
```

`A4-P6-V` remains one formal gate. The work packets below are implementation
controls only; none is an independently accepted trading-system or Stage-1
milestone.

## 2. Alternatives considered

| Option | Benefit | Decisive problem | Decision |
|---|---|---|---|
| Treat the predecessor boundary as the corrected authority | No CLI change | Silently ignores D and continues to bind the falsified case-435 plan | Rejected |
| Replace the predecessor verifier behavior in place | Small implementation surface | Breaks accepted case-5 replay and makes predecessor/successor interpretation implicit | Rejected |
| Add a second verifier role/path | Clean source split | D deliberately preserves the frozen `INDEPENDENT_VERIFIER` role path; a new path has no accepted role authority | Rejected |
| Import the D checker or a C1/C2 proof checker and accept its answer | Less code | Collapses independent consumption into proof-checker trust and does not implement the effective resolver/P1 replay itself | Rejected |
| One verifier source with an exact authority-mode dispatcher | Preserves case 5; consumes D only when the D boundary is explicitly supplied; keeps one frozen role | Requires two closed loaders and careful drift tests | **Selected** |

The selected source accepts exactly three boundary paths:

1. the predecessor constructive boundary, which retains the accepted case-5
   behavior and predecessor IDs; or
2. the D boundary delta, which requires the entire predecessor-plus-delta
   chain and successor IDs before any candidate path is opened and preserves
   the accepted V0/V1/V2 flat-context cases; or
3. the additive case-435 packed-context boundary delta, which first accepts
   the complete D chain and then authorizes only the corrected physical
   transport needed by V3.

There is no heuristic fallback between modes. Any other path, missing delta,
duplicate override, unresolved record, or mismatched physical/semantic
identity rejects.

## 3. Frozen dependencies and independence boundary

The successor verifier may execute the already accepted generic typed-rule
runtime only after securely reading and pinning it:

```text
scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py
SHA-256 47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22
bytes   249268
```

This runtime is a value-schema and rule-AST execution authority, not a
producer, maximum solver, attainer constructor, D migrator, or D checker. The
verifier must provide it complete retained records and independently execute
the exact schedule. It may not import:

- the producer;
- the D migrator or D checker;
- the C1 upper solver/checker;
- the C2 attainer constructor/checker or its certificate;
- the C3 join implementation/checker; or
- a stored pilot result.

The accepted C3 ID is consumed only as the case-435 exact P2 authority bound by
the D successor program. P1 is replayed from candidate/context bytes, and P3
is measured again.

## 4. Effective successor authority model

In successor mode, the verifier loads in this strict order before candidate
access:

1. predecessor boundary;
2. predecessor seed, manifest, and all ordered seed authorities;
3. accepted C1/C2/C3 theorem authorities required by the seed delta;
4. seed delta;
5. manifest delta;
6. boundary delta;
7. corrected six-case target delta;
8. the pinned verifier source and typed-rule runtime.

For a case-435 V3 invocation it then loads and verifies the accepted
packed-context boundary delta before opening candidate bytes. That delta does
not replace or reinterpret the D authorities; it adds one transport authority
and leaves the effective seed, manifest, program, plan, exactness join, and F2
catalog unchanged.

It reconstructs the same exact resolution proved by D:

- case 435 uses successor program
  `160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820`
  and successor plan
  `343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8`;
- the other 474 cases and 407 profile programs resolve byte-for-byte to the
  predecessor seed;
- candidate/receipt `seed_catalog_id` becomes
  `7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b`;
- candidate/receipt `finalization_manifest_id` becomes
  `6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c`;
- `maximum_protocol_sha256` is the manifest-delta raw SHA-256
  `daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf`;
  and
- every resource report uses successor F2 catalog
  `5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f`.

The 18 predecessor F2 records remain the byte-exact numerical ceilings. Their
new successor catalog identity binds them to the successor seed and manifest;
it does not raise a limit or reuse the predecessor comparison as a successor
preflight claim.

## 5. Candidate/context rules

All candidate and result schemas remain inherited from the predecessor
boundary. The verifier snapshots every file, directory, inode, byte extent,
and digest it consumes and rechecks them before publication.

The non-null maximum contexts are resolved exactly as follows:

| Case | Context form | Required retained inputs |
|---:|---|---|
| 24 | `OWNER_MEMBER` | One complete `CapacityMeasurementOperationResultEvidence` context object whose `result` member byte-equals the inline witness and whose owner discriminators/identity/rules/codec validate |
| 54 | null | Inline intrinsic record only |
| 69 | `OUTER_RESULT_APPLICATION` | Inline result `WITNESS_RECORD`, exact V4 operation-spec pointer, and the one frozen signed-spec invocation |
| 435 | `ROOT_APPLICATION` via `MAXIMUM_WITNESS_PACKED_CONTEXT` | One compact canonical input pack containing the root plus 66 non-inline observations, 67 ordered observation references with exactly one inline witness at ordinal 64, exact selector/target-registry/marker authorities, and the frozen 137-invocation schedule |
| 475 | local tagged candidate | Complete mutated spec plus complete prospective result; no maximum context catalog |

Flat `CONTEXT_OBJECT` files and case-435 packed logical context records are
compact canonical complete records. Their IDs, record identities, declared
types, intrinsic rules, codec limits, hashes, lengths, sorted order, reference
closure, and candidate-root file closure are recomputed. A hash-only,
summary-only, copied authority, unreferenced object, duplicate object, symlink,
or reopened/replaced record rejects. The pack is input transport only: verified
publication returns to the inherited individual logical context-object files
and receipt entries.

The packed correction is required because the D successor pins 38 authority
files while the inherited flat case-435 closure needs 67 context-object files;
`38 + 1 candidate + 67 = 106` exceeds immutable F0 `INPUT_FILE_COUNT = 64`.
The correction uses 41 input files and changes no F0/F2 ceiling. See the linked
transport acceptance for the independent contradiction proof and hostile
matrix.

## 6. Case-specific proof obligations

### Case 24 — owner-member union

- execute the complete intrinsic union-alternative structural template;
- validate the selected local-shutdown result body and its intrinsic rule;
- validate the complete owner record, owner discriminators, identity, and
  codec;
- prove the legal witness attains the independently recomputed P2 upper; and
- meter the actual ordinary recurrence/event stream under successor F2.

### Case 54 — raw-string array record

- execute finite/bounded text, ordered raw-string recurrence, record, and
  codec transfers;
- execute strict-ascending intrinsic legality on the concrete `members`;
- require the concrete canonical length to equal P2; and
- reject a duplicate/reordered string, malformed Unicode, or nonattaining
  endpoint even if the envelope is re-sealed.

### Case 69 — exact local-shutdown fixture

- independently execute the structural template ceiling;
- execute the pinned local analytic program to derive 2,581 octets;
- require the analytic endpoint not to exceed the structural endpoint;
- resolve the exact baseline spec from V4;
- execute `APPLY/OPERATION_RESULT_SIGNED_SPEC_V1` on the retained result/spec;
  and
- require P1 true and measured P3 exactly 2,581.

### Case 435 — C3 exact endpoint

- resolve only the successor program and plan;
- import the C3 `EXACT_ATTAINED_MAXIMUM` endpoint 257,887 and verify it remains
  below the immutable predecessor structural ceiling 262,143;
- resolve the complete 67-observation/root/selector context;
- replay all 137 frozen applications using the verifier-owned static typed
  subset and compare that subset separately against the pinned generic runtime;
- require 12,531 charged/completed rule evaluations and 125,431 direct
  expression nodes;
- require the inline ordinal-64 observation to be P1 legal and exactly 257,887
  canonical octets; and
- meter the complete verifier work against every immutable per-case F2 limit.

No C2 certificate or stored witness is an acceptance input.

### Case 475 — local minimality

- execute all 11 ordered controller transitions from the frozen analytic
  catalog;
- recompute the baseline spec and winning one-field mutation;
- prove the winner is
  `maximum_terminal_ingress_batches = 1948`, absolute delta 1,947;
- prove the predecessor value 1,947 remains below the strict outer limit and
  the winner has attainable maximum 524,380, above the `< 524288` limit;
- reconstruct and validate the complete prospective result; and
- prove no lexicographically better legal one-field nondecreasing mutation
  exists.

## 7. Resource metering

The verifier extends the existing event-grammar interpreter instead of
inventing shortcut counts:

- ordinary cases emit one physical transition token per transition and retain
  the exact logical-unbatched multiplicity partition;
- scope applications emit `APPLICATION_EVALUATION` and
  `CROSS_RULE_EVALUATION` from completed runtime evidence;
- case 475 emits the frozen local-controller state/transition order;
- byte metrics are derived from the actual canonical subjects/preimages;
- depth/retention metrics are derived from the actual postorder live set; and
- every measurement must be at most both its immutable `f2_per_case` and the
  full-run aggregation ceiling when combined by the later runner.

For `A4-P6-V`, per-case enforcement is mandatory. The verifier also emits the
exact vector needed by `A4-P6-R/E`; it may not tune the vector or F2 values from
observed pilot output.

## 8. Ordered implementation packets

| Packet | State | Falsifiable exit |
|---|---|---|
| `A4-P6-V0` successor resolver/read barrier | `ACCEPTED` | Dual-mode dispatcher preserves case 5; successor mode independently reconstructs all D identities/resolution before candidate access; missing/extra/ambiguous/tampered authority and path aliases reject |
| `A4-P6-V1` intrinsic cases 24/54 | `ACCEPTED` | Independently constructed legal attaining fixtures pass; owner/context, union, raw-string, Unicode, order/uniqueness, codec, nonattainment, and re-sealed mutation oracles reject |
| `A4-P6-V2` exact profile case 69 | `ACCEPTED` | Structural/analytic intersection derives 2,581; exact result/spec application passes; context, schedule, analytic endpoint, P1, and P3 mutations reject |
| `A4-P6-V3` corrected case 435 | `ACCEPTED` | Packed-context delta and exact-delta plan resolve; complete context and 137 P1 invocations pass; 257,887 P2/P3 equality and all immutable F2 limits pass; old plan/C2 trust/flat-context/substitution mutations reject |
| `A4-P6-V4` local case 475 and consolidated F2 | `ACCEPTED` | Eleven-transition minimality proof passes; better/equal/incorrect mutation and prospective-result substitutions reject; all five cases pass twice byte-identically under per-case F2 |
| `A4-P6-V-A` independent acceptance | `ACCEPTED` | Separate acceptance reviewer/test reconstructs identities, results, resource vectors, source isolation, candidate immutability, and expected-red producer/runner boundary |

Advancement is strictly ordered. A packet is not marked complete because its
positive fixture works; its hostile matrix, deterministic rerun, source
isolation, and predecessor case-5 regression must all pass first.

## 9. Acceptance matrix

The final verifier acceptance must include at least:

1. two byte-identical successes per supported successor case;
2. preserved predecessor case-5 success under the predecessor boundary;
3. independently built fixtures that import no verifier implementation;
4. candidate and context immutability snapshots before/after verification;
5. re-sealed candidate identity mutations for every decision-bearing member;
6. wrong predecessor/successor ID, plan, program, target, F2, and manifest
   bindings;
7. missing/extra/duplicate context records and reference substitutions;
8. intrinsic/cross-rule false cases, nonattainment, and codec violations;
9. per-metric `f2_per_case - 1`, exact-limit, and `f2_per_case + 1` enforcement
   where constructible without changing accepted authorities;
10. duplicate keys, floats, non-finite numbers, BOM, invalid UTF-8, symlinks,
    hardlink aliases, output races, and partial-publication cleanup;
11. a static import/isolation audit; and
12. unchanged expected-red producer and runner tests.

## 10. Immediate next action

The V0/V1/V2/V3/V4 instructions and independent V-A review are fulfilled by
the linked acceptances. Formal verifier expansion is accepted. Execute only
`A4-P6-P` next: expand the separate producer for cases 24, 54, 69, 435, and
475 against the frozen accepted verifier contract without importing verifier
answers or weakening F0/F2.

The producer packet is released; the parent runner remains held until producer
expansion is independently accepted. Do not claim the six-case pilot, all-475 result set,
Stage 1, Stage 2, predictive edge, or profitability.

No external literature search was needed for this design. It is a
repository-defined exact authority, filesystem, type/rule execution, and
resource-accounting problem; the controlling evidence is the accepted
boundary, C1/C2/C3 chain, D transition, frozen typed-rule runtime, and event
grammar.

# Raw V8 Step-2 compact maximum-proof V2 correction acceptance

Date: 2026-08-02  
Decision: **narrow GO — `V2_CORRECTION_ONLY_V4_MIGRATION_AUTHORIZED`**

This report accepts the compact maximum-proof V2 correction as the normative
design authority for the next V4 inventory-migration gate. It does not accept
the V4 inventory, the future V2 proof protocol, either full-row counting
preflight, a pilot, any constructive maximum, the local-shutdown result,
Raw V8 Step 2, A2-M, A2-E, public-live operation, or Stage 1.

## 1. Accepted authority

| Artifact | UTF-8 bytes | Physical SHA-256 |
|---|---:|---|
| `docs/research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md` | 49,849 | `f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4` |

The accepted document is an additive authority. The predecessor External
Schema V2 correction, accepted V3 inventory, and rejected V1 proof protocol
remain immutable historical authorities. V1 stays rejected and pinned to V3;
it must not be relabelled, migrated, or made accepting.

## 2. Accepted design boundary

The correction establishes these design decisions:

1. An exact maximum is accepted only when an independently reconstructed legal
   witness-context pair has length `U`, every legal pair has length at most
   `U`, and the witness itself is in the legal domain.
2. A verifier-proved safe relaxation may establish the upper bound, but legal
   attainment remains mandatory. The relaxation need not find its own maximum.
3. Global lexicographic leastness and one serialized prefix-proof node per
   primitive coordinate are not byte-maximum safety requirements.
4. Mathematical validity is separate from deterministic publication. Multiple
   equal legal maxima may validate; publication pins one accepted attainer
   under `PINNED_ACCEPTED_ATTAINER_V1`.
5. The mathematical row binds its exact per-row context closure, not a global
   publication manifest. Publication subsequently binds the union of selected
   row closures and rejects orphan or unselected context objects.
6. Producer artifacts, independent proof recomputation, proof-resource
   reports, and selected-artifact publication limits have separate identities
   and accounting phases. No resource cap may be learned from a pilot that the
   cap is supposed to authorize.
7. The local-shutdown question remains a separate minimality proof. Its
   prospective upper-bound certificate is embedded and independently rebuilt
   over a scope masking exactly the frozen outer `LT 524288` codec coordinate.
8. The complete verifier-owned universe is exactly 475 cases: 474 maximum
   scopes plus the one separate local-shutdown problem.

These decisions replace only the V1 proof/publication surfaces enumerated by
the correction. They do not change the 52-node schema graph, 236 value schemas,
42 rules, eight applications, two resolvers, 408 V3 scope profiles, 474 row
order, Unicode/canonicalization semantics, or production codec ceilings.

## 3. Independent review record

Two independent read-only reviews examined the same 49,915-byte candidate at
SHA-256
`0bb76ec468ca7e0b18115e7a07c85def625eb5d292e0537d5bc6d9aa2c12dd3d`.
One review identified a single count ambiguity in Phase F1: the wording said
475 cases *plus* local shutdown even though the rest of the document correctly
defined 475 as 474 plus local shutdown.

The sentence was changed to the explicit 475-case partition. The resulting
49,920-byte technical candidate had SHA-256
`d513524dd20f99c377815f8d58a4219970c952f9c8d59a2c84f77518b9026538`.
Both reviewers independently:

- re-read and hashed those bytes;
- reversed only the corrected sentence and reproduced the prior byte count and
  SHA-256 exactly;
- returned `READY` with no remaining blocking defect; and
- retained the final-protocol obligations described below.

After both technical verdicts, exactly six governance-only text replacements
changed the document from candidate to accepted correction while preserving
the explicit Raw V8 Step-2 `NO-GO`. Mechanical reversal reproduced the
reviewed 49,920-byte SHA-256 exactly. Both reviewers independently verified the
final 49,849-byte artifact and SHA-256 shown in Section 1 and confirmed that
the acceptance did not authorize a later gate.

The reviews covered:

- the P1/P2/P3 maximum theorem and safe-relaxation condition;
- narrow supersession and preservation of legal-domain/codec semantics;
- acyclic amendment → V4 inventory → V2 protocol authority flow;
- exact artifact identity/member schemas and context-closure separation;
- F0 → F1 → F2 → F3 resource ordering and separate publication limits;
- embedded resolution of the local prospective certificate; and
- the 32-item falsification matrix.

## 4. Required V4 migration

The next authorized implementation is a parallel V3→V4 inventory migration,
not an edit to the accepted V3 generator or golden. V4 must:

- use schema `riskyieldmm.raw_v8_step2_inventory.v4`;
- retain the same 12 logical root keys;
- insert this correction as ordered normative input four of five under role
  `STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION`;
- add only the exact compact-proof contract, input-count/hash mirrors, schema
  version, and recomputed root identity permitted by the correction;
- preserve the complete registry, every one of the 408 profile objects and
  IDs, the 474 row universe/order, authority pointers, fixtures, and every
  unrelated invariant byte-for-byte; and
- reject a four-input V3 object merely relabelled as V4 or any consumer that
  treats the fifth authority as optional.

The V4 migrator and validator must be independent, use bounded secure reads,
enforce an exact recursive delta allowlist, and retain the V3 artifact and V1
consumers unchanged.

## 5. Deferred obligations and nonclaims

The eventual V2 protocol must still freeze the complete derivation/result
grammar, recurrence and cache-state keys, resource-measurement item grammar,
meter catalog, exact recipe/report paths and schemas, deterministic strategy,
F0 seed ceilings, and subsequently derived immutable F2 limits.

Before a pilot is authorized, two independent counting-only implementations
must agree for all 475 scope cases under F0, the final F2 limits must be frozen
without changing proof semantics, and both preflights must repeat successfully
against the final protocol bytes. An independent verifier must then reject
producer evidence without importing the producer before a separate generator
may produce the six-case replacement pilot.

No claim of maximum completeness, runtime boundedness, production
compatibility, predictive edge, trading safety, or profitability follows from
this correction acceptance. A later empirical or implementation result cannot
retroactively authorize a skipped earlier gate.

## 6. Gate disposition

```text
V1 feasibility rejection                 ACCEPTED
V2 compact-proof correction              ACCEPTED
V4 successor inventory                   IN PROGRESS / NOT ACCEPTED
V2 full-row counting preflight           NOT STARTED
V2 immutable protocol freeze             NOT STARTED
V2 pilot                                 NOT AUTHORIZED
474 constructive maxima                  NOT STARTED
local-shutdown V2 result                 NOT STARTED
runtime-work accounting                  INCOMPLETE
production adapters / compatibility      INCOMPLETE
Raw V8 Step-2 acceptance                 NO-GO
A2-M / A2-E / Stage 1                    INCOMPLETE
```

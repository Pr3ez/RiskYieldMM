# Raw V8 Step-2 V2 profile-attainability scope and correction design

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-C435-A`  
**Decision:** `CENSUS AND CORRECTION ARCHITECTURE ACCEPTED`  
**Implementation state:** `NO-GO — EXACT CASE-435 MAXIMUM IS NOT YET DERIVED`  
**Stage 1:** `NO-GO`

## 1. Executive decision

The case-435 contradiction is not safely repairable as a one-case exception.
An independent seed/inventory census proves that 407 of the 408
profile-conditioning programs use the same structural-only P2 shortcut. Those
407 programs cover 474 of the 475 internal profile scope cases. Every one of
the 408 programs then executes the same P1/P3 rule requiring a P1-legal
retained witness whose canonical length equals the P2 endpoint.

Only case 69 has an application-aware exact P2 derivation. The other 407
programs are not all proven infeasible: case 435 is the one currently
falsified. They are, however, all **unqualified for an exact-maximum claim**
until each has both a proved legal-domain upper bound and an independently
validated legal attainer.

The selected correction is therefore a versioned three-result proof:

```text
application-aware legal-domain optimizer
  -> PROVED_LEGAL_UPPER_BOUND

independent retained-witness constructor + pinned P1 validator
  -> INDEPENDENT_LEGAL_ATTAINMENT

identity-bound equality join
  -> EXACT_ATTAINED_MAXIMUM
```

A structural cell remains a useful safety ceiling, but it can no longer serve
as exactness evidence. A structural superset is forbidden from entering the
equality join.

## 2. New executable audit

The independent checker is:

```text
scripts/tests/check_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py
```

Its focused test is:

```text
tests/test_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py
```

It reads only these pinned data authorities:

| Authority | Raw SHA-256 |
|---|---|
| Corrected V2 seed catalog | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| V4 source inventory | `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b` |

It imports neither the seed generator nor `riskyieldmm`, the rule runtime,
application-witness helpers, producer, verifier, or rejected V1 constructive
implementation. It verifies the complete program/profile/plan binding, all
475 internal scope cases, weighted application-schedule counts, every generic
cross-application deletion mapping, the exact P1/P3 opcode chain, and the
case-69 analytic control.

The audit identity is:

```text
10e0ce8a277053e7d4e04d08fada484ccc656c92607eba2d8f2518c1fe8fd09a
```

## 3. Exact affected surface

| Surface | Programs | Internal scope cases | Disposition |
|---|---:|---:|---|
| Generic structural-superset P2 | 407 | 474 | Must transition to V2 exactness join or remain `NO-GO` |
| Local-shutdown analytic exact P2 | 1 | 1 | Case-69 positive control; adapt to the V2 join |
| Total profile-conditioning surface | 408 | 475 | All execute exact P1/P3 equality |

The 407 affected publication rows occupy cases 67 through 474, excluding the
case-69 exact control. Their case-position vector, profile-ID vector,
program-ID vector, and full normalized audit-record vector are sealed as:

| Vector | SHA-256 |
|---|---|
| Affected case positions | `1fa6eb9883e12d3e901dca4af938fbb13131fd06c43e0e4f6ce98e86d3813748` |
| Affected profile IDs | `b4c3cdc7ef2822a068300f5bd7280d5d88ce14f96d9eee6ae32e23418c9ec907` |
| Affected program IDs | `5600deb5f597db75b8061b9c522add7fb7bd0ff2d6b415ce48194fbab3b81af1` |
| Full affected records | `59cf77bfade5b3f53c96ef7d53eb2afccff2b3ca146a8c43f8296726aa02c244` |

### 3.1 Measured-type and profile-kind decomposition

| Measured type / profile kind | Programs | Scope cases |
|---|---:|---:|
| `CapacityMeasurementOperationResultEvidence` / outer-result fixture | 3 | 3 |
| `TargetObservationV2` / checkpoint coordinate | 400 | 400 |
| `TargetObservationV2` / non-checkpoint root family | 4 | 71 |
| **Affected total** | **407** | **474** |

The target-observation surface therefore contains 404 programs and 471 scope
cases. The four family programs expand to 71 scope cases and must not be
mistaken for four proof obligations.

### 3.2 Operation decomposition

| Operation | Programs | Scope cases |
|---|---:|---:|
| `ACK_DEADLINE_EXPIRY` | 17 | 33 |
| `INGRESS` | 342 | 361 |
| `LOCAL_SHUTDOWN` | 26 | 42 |
| `SUBSCRIPTION_DISPATCH` | 22 | 38 |
| **Affected total** | **407** | **474** |

Of the affected scope cases, 427 have a selector and 47 do not. The structural
P2 programs delete 2,023 scheduled cross-application references. The exact P1
side still represents 46,266 application invocations, 4,198,490 cross-rule
evaluations, and 42,023,958 direct cross-expression-node evaluations.

These counts make a 407-formula repair both risky and unnecessary. They also
show why validating only case 435 would leave the protocol incomplete.

## 4. Confirmed contract conflict

The accepted V1 catalog says all of the following:

1. A generic P2 instruction loads one
   `P2_SUPERSET_BOUND_CELL` from the structural template.
2. `generic_attainability_claimed` is false.
3. `structural_bound_only_acceptance_forbidden` is true.
4. `unresolved_or_unattained_policy` is `NO_GO`.
5. Every profile P1/P3 program terminates in
   `REQUIRE_P1_AND_P3_EQUALITY_V1` with
   `P1_TRUE_AND_MEASURED_CANONICAL_OCTETS_EQUALS_P2_UPPER`.
6. The corresponding logical plans label the generic publication mode
   `LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT`.

Items 1 through 4 correctly distinguish a safe superset from an exact maximum.
Items 5 and 6 require the missing legal attainer. Case 435 proves that its
structural endpoint cannot be attained, so its current equality is not merely
unproven—it is impossible.

For the remaining 406 generic programs, this audit makes no infeasibility
claim. It establishes that the same proof shortcut exists and must be closed
before all-profile constructive qualification.

## 5. Alternatives considered

| Option | Strength | Failure mode | Decision |
|---|---|---|---|
| Change P3 equality to `witness_length <= P2.U` | Keeps the structural safety bound | Proves only enclosure, not a maximum; downstream maximum rows become mislabeled | Rejected |
| Patch or replace case 435 in the six-case pilot | Small local change | Hides a 407-program protocol gap and leaves the all-475 claim unsound | Rejected |
| Pad a legal witness to the structural endpoint | Could force byte equality | Changes the external schema and economic meaning of the measured record | Rejected |
| One hand formula per profile | Potentially exact | Duplicates rules 407 times, invites drift, and does not scale to future profiles | Rejected |
| Full Cartesian enumeration | Conceptually simple and exact | State space is intractable because text, integer, list, field, context, and sequence domains multiply | Rejected as the primary implementation |
| SMT/CP-SAT as acceptance authority | Expressive search | Adds opaque solver/version semantics and does not by itself yield a portable independently checked proof | Rejected as authority; permitted as a challenger/proposal tool |
| Typed dependency graph plus exact component optimization and a checkable certificate | Exact when dependency closure is proved; reusable across profiles; independently reproducible | Requires explicit complex-operator dependency contracts and exact domain solvers | **Selected** |

The selected method is not an approximation. If any domain, dependency,
operator, or component maximum cannot be closed exactly within the frozen
resource budget, that profile remains `NO-GO`.

## 6. Frozen correction contract

The checker carries an identity-bound machine-readable correction contract:

```text
e95d6f101942c0f1171616f0b05cf8978991fda639fc63a355765dd73b18c37b
```

Its principal rules are:

### 6.1 Upper-bound channel

- Output `PROVED_LEGAL_UPPER_BOUND`, never an attained cell.
- Treat the structural root cell only as a safety ceiling.
- Derive one exact maximum for every internal scope case.
- Take the maximum across those cases and bind the winning scope case.
- Use only a pinned typed dependency graph and exact component optimizers.
- Emit an identity-bound certificate that an independent implementation can
  recompute from the frozen authorities.
- Reject unresolved, unbounded, or computationally unclosed components.

### 6.2 Independent attainment channel

- Construct retained canonical bytes independently of the upper-bound
  derivation executable and any precomputed answer.
- Execute the pinned application-rule AST over those bytes.
- Measure the retained witness canonical length.
- Reject an invalid, unresolved, or unavailable witness.

The producer and the upper-bound proof may use the same frozen data
authorities. They may not share executable optimization code or a stored
maximum/witness answer.

### 6.3 Exactness join

The join accepts only when:

```text
upper result kind == PROVED_LEGAL_UPPER_BOUND
attainment result kind == INDEPENDENT_LEGAL_ATTAINMENT
profile ID, scope case, fixed authorities, and schedule identities match
P1 legality == true
witness canonical octets == proved legal upper bound
```

It then emits `EXACT_ATTAINED_MAXIMUM`. A `SUPERSET_UPPER_BOUND` input is never
joinable.

### 6.4 Migration

The accepted V1 seed, manifest, constructive boundary, six-case target,
verifier, producer, and their identities remain immutable predecessor
evidence. The correction requires new versioned authorities. `A4-P6-V` may
resume only after corrected case 435 passes the exact upper-bound proof and
independent attainer. All 407 programs and 474 scope cases must close before
the complete 475-case maximum claim.

## 7. Dependency structure that the optimizer must prove

The six scheduled cross rules reduce to two measured-type engines, not 407
unrelated algorithms.

### 7.1 Operation-result engine

`RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1` binds the result to one fixed
signed operation spec. The exact optimizer must retain the selected union
branch and every equality/limit imposed by that operation's spec. The three
generic outer-result profiles can share this engine; case 69 remains the
analytic local-shutdown control.

### 7.2 Target-observation engine

The exact dependency audit must account for:

- `V2_OBSERVATION_FIELD_REGISTRY`: each field depends on its descriptor,
  target registry, ordinal, and shared observation context;
- `V2_OBSERVATION_AGGREGATE_REGISTRY`: the A1 FIFO count, sequence, and kind
  fields form one coupled component when all three are available;
- `V2_ROOT_OBSERVATION_MEMBERSHIP`: candidate, attempt, operation,
  instrumentation mode, and registry identities are shared with the root;
- `V2_ROOT_SELECTOR_LIFECYCLE`: the observation role sequence, selector
  binding, checkpoint entries, exact-marker ordinal order, and observation
  identities are sequence-coupled; and
- `SELECTOR_MARKER_CONTRACT`: selector entries are restricted by operation and
  the fixed marker contract.

This suggests four candidate optimization components:

1. root, selector, shared context, and sequence lifecycle;
2. ordinary fields conditioned on one exact context state;
3. the coupled A1 FIFO three-field group; and
4. canonical record composition and fixed-width identity recomputation.

That partition is a hypothesis until the next sub-gate walks every rule AST
and every complex-operator read/write set. No component may be separated on
the basis of field names or intuition alone.

## 8. Required certificate surface

The implementation-stage certificate must at minimum bind:

```text
certificate version
seed / inventory / structural-registry / rule-literal identities
profile-program / profile / logical-plan identities
fixed-authority IDs and canonical hashes
exact application-schedule identity
ordered internal scope cases
complete rule/operator dependency manifest
finite or analytic domain descriptor per variable
ordered dependency components
exact per-component maxima and constructive endpoint evidence
exact per-scope-case canonical maximum
winning scope case and deterministic tie-break
publication upper bound
structural safety-ceiling comparison
certificate semantic identity
```

Stored maxima without recomputation are not proof. A certificate is accepted
only if an independent implementation reconstructs every component maximum
and the final canonical-length composition.

## 9. Acceptance and falsification tests

Before the corrected shared authority is generated, the next implementation
must pass all of these:

1. The exact case-435 dependency manifest is closed and identity-bound.
2. Every dependency edge is derived from a rule AST input path or a pinned
   complex-operator contract.
3. Removing or adding one edge, scope case, field descriptor, application, or
   authority fails closed.
4. Micro-domains are compared with independent exhaustive enumeration.
5. Negative controls with random labels/values, shifted ordinals, invalid
   selector order, A1 mismatch, wrong context identity, and wrong fixed
   authority are rejected.
6. The P2 implementation derives one exact case-435 upper bound without using
   producer or P1 witness code.
7. The independent constructor produces different source code and a legal
   witness whose canonical length equals that upper bound.
8. A forged longer witness, a valid shorter witness labeled maximum, and a
   structural-superset cell presented to the join are rejected.
9. The case-435 result is reproduced in separate processes and is stable under
   input-order-preserving replay.
10. The accepted V1 seed and all predecessor artifact hashes remain unchanged
    until the explicit versioned transition.

## 10. Current verification

The focused audit suite currently reports:

```text
10 passed
```

It covers the exact census and group matrix, deterministic CLI output, source
isolation, the fail-first correction boundary, both authority hashes, a
structural P2 disguised as exact, a missing cross-application deletion, a
weakened P1/P3 equality, and a profile/plan root substitution.

The current catalog is intentionally rejected by:

```text
A4_P6_C435_APPLICATION_AWARE_EXACTNESS_NOT_IMPLEMENTED:
407 programs / 474 scope cases remain
```

## 11. Next bounded action: `A4-P6-C435-B`

Freeze the complete case-435 rule/operator dependency manifest and prove or
reject the four-component factorization proposed in section 7. Then define
the exact domain and component solvers needed for case 435. Do not edit the
accepted generator, seed, manifest, boundary, target, verifier, producer, or
runner during this sub-gate.

Only after that dependency manifest is independently reviewable should the
case-435 exact upper-bound implementation and separate legal attainer begin.

The successor
[`case-435 dependency-closure acceptance`](v4_9f_a2_raw_v8_step2_v2_case435_dependency_closure_acceptance_2026-08-10.md)
accepts `A4-P6-C435-B`, proves the factorization only in nested conditional
form, and makes exact upper-bound channel `A4-P6-C435-C1` the next bounded
action.

## 12. Nonclaims

This packet does not derive the exact case-435 maximum, construct its legal
attainer, correct the shared seed, qualify the six-case pilot, close all 475
maxima, complete Raw V8 Step 2, exit Stage 1, establish predictive edge, prove
trading safety, or claim profitability.

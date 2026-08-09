# Raw V8 Step-2 constructive-maximum V2 seed design review

Date: 2026-08-02
Decision: **NO-GO — F1 IMPLEMENTATION NOT AUTHORIZED**

## 1. Scope

Three independent read-only reviews tested the first V2 seed candidate against
the accepted compact maximum-proof correction and V4 inventory. The review
evaluated mathematical soundness, implementation determinism, resource and
filesystem closure, identity schemas, phase ordering, and adversarial
testability before either counting implementation was written.

The reviewed candidate is:

```text
docs/research/v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_v2_freeze_2026-08-02.md
```

It is not accepted authority and may be revised in place until a later
acceptance report pins final candidate bytes.

## 2. Findings that survived review

The following foundations were independently confirmed:

- the compact P1/P2/P3 theorem is sound;
- the accepted V4 physical and semantic pins are correct;
- the top-level universe is 474 publication rows plus one separate local-
  shutdown minimality case;
- ordinary local-shutdown maximum row 69/profile 3 remains in the 474 rows;
- V1's 475 contextual internal expansions and 33 synthetic axes are not the
  top-level case universe;
- V1 global leastness, component coordinates, prefix nodes, winner digests,
  bitmap frontier, and certificate/resource fixed point are correctly
  excluded;
- the 18 proposed semantic metric families, cap-before-mutation rule, F0
  numeric ceilings, watchdog separation, no-percentage rule, and
  `F1 <= F2 <= F0` direction are viable design foundations; and
- the binary-lift composition formula is arithmetically correct.

These findings do not authorize F1.

## 3. Blocking defects

### 3.1 Recurrence and state grammar is not executable

The first draft names derivation kinds but leaves per-kind
`recurrence_parameters`, exact transition equations, state-component records,
registry-to-plan construction, cache schemas, and catalog/step identities
open. Equivalent independent implementations could legally count different
states, transitions, cache keys, canonical bytes, and hash preimages.

The replacement must provide a normative machine-readable derivation catalog
and a closed transfer for every admitted kind. A max-only cell must be defined
as an abstract upper bound unless the key includes residual budget and exact
attainability; it must not silently discard shorter child values needed by an
ancestor cap.

### 3.2 Batching lacks a proof rule

Equality through cardinality 16 is challenger evidence, not proof for
524,288. The replacement must freeze an associative endomorphism, identity,
composition operator, ordinal/canonical-boundary state, and inductive
equivalence theorem. Otherwise the array must use the stream fold. Maximum
cardinality may be selected directly only after proving monotone extendability
and absence of a surviving cardinality-sensitive observer.

### 3.3 Meter bytes and retention are open

Transition-token bytes, result-cell encoding, every semantic-ID envelope,
cache insertion/release, last-parent ordering, peak-live representation, and
`DERIVATION_RESULT_CANONICAL_OCTETS` events are incomplete. Every metric needs
one closed event grammar and exact aggregation equation.

### 3.4 Seed/final invariant is contradictory

The draft includes a phase-bound event-stream digest in the cross-phase count
vector while plans and results bind the changing protocol SHA. The replacement
must define a separate phase-invariant logical count-plan projection that
excludes protocol-bound identities. Physical derivation digests remain
same-phase A/B evidence only.

### 3.5 Identity and report schemas are incomplete

Every catalog, state, cache, plan, step, batch, case, payload, report, source
manifest, and comparison record needs an exact version literal, member order,
identity payload, domain, and canonical envelope. `case_binding` needs closed
maximum-row and local-minimality variants. Pretty and compact encodings cannot
be byte-equal; object equality plus independent equality under each specified
encoding is the correct test.

### 3.6 Physical source closure is incomplete

The six Unicode 15.0.0 files are hash-pinned but absent from the repository.
The replacement must either vendor the exact official bytes at frozen local
paths or define and accept a separate secure cache/download authority before
F1. The complete ordered input manifest, byte total, file count, parser-node
meter, and watchdog cleanup behavior must be enumerable.

### 3.7 Local minimality recurrence is not closed

The exact mutable-field set, breakpoint equations, interval equivalence proof,
ordering, embedded prospective-bound invocation, and metric events are missing.
Case 475 cannot be counted until these are machine-exact.

### 3.8 F2 and source freeze are not unique

The final equation must be exactly `F2 = round_up(required_F1, unit)`, subject
to F0, not merely any value in an interval. The patch allowlist miscounts ten
source/report fields as six and does not freeze the final Status literal. A
pre-run A/B source-manifest path/schema/hash and secure before/after snapshot
are required; post-run hashes inserted into a document do not prove pre-run
source freeze.

## 4. Frozen boundary oracles for the redesign

For `n >= 2`:

```text
binary_lift_compositions(n)
  = (n.bit_length() - 1) + n.bit_count() - 1

binary_lift_depth(n)
  = (n - 1).bit_length(), n > 1
```

The exact controls are:

| n | Compositions | Depth |
|---:|---:|---:|
| 0 | 0 | 0 |
| 1 | 0 | 0 |
| 2 | 1 | 1 |
| 185 | 11 | 8 |
| 511 | 16 | 9 |
| 512 | 9 | 9 |
| 524,287 | 36 | 19 |
| 524,288 | 19 | 19 |

The revised catalog must additionally freeze complete expected 18-metric
vectors for representative scalar, array, object-reference, record,
rule/application, contextual-profile, and local-minimality fixtures before the
full run.

## 5. Required corrective sequence

```text
vendor or securely freeze Unicode 15.0.0 source bytes
  -> define exact ordered input/source manifest
  -> freeze machine-readable derivation/event/identity catalog
  -> close scalar, record, rule/application, batching, and local transfers
  -> add phase-invariant logical count-plan projection
  -> freeze pre-run A/B source-manifest schema
  -> add hand-oracle fixtures with complete vectors
  -> repeat three independent seed-design reviews
  -> only on unanimous GO, author A/B/comparator implementations
```

Until that sequence passes, both F1 implementations, F2 insertion, verifier,
producer, pilot, 474 maxima, local result, and Raw V8 Step 2 remain NO-GO.


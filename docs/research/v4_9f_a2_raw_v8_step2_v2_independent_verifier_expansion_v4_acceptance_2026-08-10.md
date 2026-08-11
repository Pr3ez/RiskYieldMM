# Raw V8 Step-2 V2 independent-verifier expansion V4 acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-V4`  
**Decision:** `ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-V-A` — independent verifier acceptance

## 1. Accepted claim

`A4-P6-V4` extends the accepted V0/V1/V2/V3 verifier only for successor
packed-authority case 475. It independently resolves the frozen local analytic
catalog, executes all 11 controller transitions and 12 states, reconstructs
every non-batch endpoint plus the concrete batch predecessor and winner,
validates the complete mutated spec and prospective result, and accepts only
the lexicographically minimal one-field mutation:

```text
maximum_terminal_ingress_batches = 1948
absolute delta = 1947
predecessor 1947 = 524112 canonical octets
winner 1948 = 524380 canonical octets
outer codec requirement = canonical length < 524288
```

Every prospective-result condition remains active except the one declared
outer `CapacityMeasurementOperationResultEvidence LT 524288` codec coordinate.
The nested result codec, scalar and array domains, semantic identities,
intrinsic result/spec rules, signed-spec cross rule, and exact P3 length remain
mandatory. The accepted result is therefore an exact attained maximum in the
single-mask domain, not a structural upper bound and not a producer claim.

V4 completes implementation coverage for verifier cases 5, 24, 54, 69, 435,
and 475. It does **not** yet accept the independent verifier acceptance packet,
producer expansion, parent runner, six-case end-to-end pilot, all 475 result
artifacts, Raw V8 Step 2, Stage 1, paper/live readiness, predictive edge,
trading safety, or profitability.

## 2. Architecture decision

Three local-minimality designs were challenged:

1. trust the catalog's stored winner and endpoint numbers;
2. brute-force every safe-integer mutation value; or
3. independently execute the finite 11-member controller while using concrete
   endpoint attainers and a proved monotone adjacent crossing for the only
   enormous batch interval.

The third design is the narrowest complete solution. Trusting stored numbers
would make the candidate/catalog its own proof. Exhausting values through
`9007199254740991` is computationally impossible and adds no evidence once the
closed affine-plus-decimal-width program is proved strictly increasing. V4
therefore:

- recomputes the local analytic catalog, state, transition, kernel, plan, and
  typed-record identities;
- cross-checks every mutable integer interval against the structural registry;
- reconstructs every non-batch one-field endpoint as a complete legal
  result/spec pair;
- constructs complete legal batch attainers at 1,947 and 1,948;
- proves the affine-plus-decimal-width length function is monotone and the two
  adjacent values straddle the strict outer limit;
- executes the frozen objective fold and proves that the only eligible
  one-field objective is `(1, 1947, [maximum_terminal_ingress_batches],
  [1948])` in the frozen member convention;
- separately validates the candidate's complete prospective result at exactly
  524,380 compact canonical octets; and
- derives byte metrics from actual tagged state, transition, cell, cache,
  commitment, retention, and hash-preimage subjects.

No external literature search was needed. This packet is governed by local
canonical bytes, typed opcodes, accepted identities, and exact arithmetic;
external sources cannot establish repository-specific semantic identities.

## 3. Exact deterministic result

Two fresh candidate roots produce byte-identical accepted output trees, and
the complete candidate trees remain byte-identical before and after each run:

| Artifact | Octets | SHA-256 / semantic ID |
|---|---:|---|
| Candidate envelope | 614,566 | raw `bdf7f8e4213cbf51b70b2dac0bdc97ffd1d55304b37bd3d20b8b9d54ba7977dc`; ID `ee38407312f872f0d8dc3f5d6b3ebe9990f294ce245b406ba3e33cce243dcb42` |
| Mutated operation spec | — | `572155284c3b8b0852b406d5cbce662aba7579180f89ee3740a6c86ede66f16a` |
| Prospective result | 524,380 compact | `8a22dfcb61a9e083c2edccc7902d0e4e414c8be4d130570a495b1cdecb1a014c` |
| Local proof scope | — | `4db3b0d60c9487e2b0913cf54fc05fa88ee5cac9e7aa979b3c97d6d46d1974b1` |
| Winning upper certificate | — | `bc4594ce40f5ba4d80276ae1eec89c34f2e9eaff8328834093fa1e2cfa4dd118` |
| Better-objective exclusion digest | — | `4cf7a46c0488d044368be412db5f837be5b4bd8f5c71907df83271d89d5cceb9` |
| Minimality certificate | — | `62c6c97f9af5a8f4924f45a4c4e2d144d93eb17cd84d5b17b0cd06af6eb15792` |
| Resource report | — | `ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8` |
| Local result artifact | 604,156 | raw `a1e1316c970e60db198d8775eeb89a1e0eb7e4cdda5ddca64f54c666130fb7f8`; ID `937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73` |
| Verification receipt | 3,173 | raw `93b1ab8dc2fdbbd8dadabae5bd5591f8129d0ce2611f6bb1d25e74f46078f5b2`; ID `eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f` |

The streamed derivation hash is
`5f2f61d0f9f09174d3bb17288c02f36d9ec7ec358468d36ed19a2e44958cbbb3`.
The candidate uses no context file, and accepted publication contains the
local result plus receipt and an empty `context_objects/` directory.

## 4. Immutable F2 result

The verifier independently reproduces the preflight-A case-475 vector:

```text
[1, 11, 12, 11, 11, 0, 12, 9591, 20047,
 28612, 49103, 4, 1, 1, 1, 11, 18156, 672]
```

Metric 12 is intentionally four: two intrinsic-rule subjects are charged in
the local controller and the same two are charged again when the exact
attainer is validated. This is the frozen two-phase grammar, not duplicate
accidental counting. The exact F2 margins are:

```text
[0, 2102261, 1012, 1013, 4204533, 1024, 1012, 96905, 770481,
 852028, 1433649, 1020, 49151, 1023, 16, 558, 39188, 40288]
```

No F2 value was changed. The lower V0/V1/V2/V4 matrix passed 83 tests, and the
packed-transport/V3/V4 compatibility matrix passed 61 tests. Each positive
case fixture performs two fresh byte-identical verifier runs; together the
accepted V1–V4 tests cover every successor pilot case twice under the same F2
catalog.

## 5. Immutable F0 result

Replacing the V3 verifier with V4 changes only the verifier byte count. The
successor authority surface remains 39 files. Case 475 requires one candidate
file and no context file:

| Input surface | Files | Pinned octets | File headroom | Octet headroom |
|---|---:|---:|---:|---:|
| successor authorities before candidate | 39 | 29,004,595 | 25 | 38,104,269 |
| case 475 authorities + candidate | 40 | 29,619,161 | 24 | 37,489,703 |
| worst accepted case 435 with V4 verifier | 41 | 42,035,913 | 23 | 25,072,951 |

All surfaces remain below immutable F0 limits of 64 files, 67,108,864 total
pinned octets, and 16,777,216 octets per individual file. No F0 value was
raised or repaired from observed output.

## 6. Contract-variance resolution

Two inherited texts differ from the executable/corrected V2 authority:

1. the corrected compact-proof V2 certificate uses
   `local_shutdown_minimality_certificate_id`; the older still-red six-case
   harness looks for `minimality_certificate_id`; and
2. historical correction prose names a local-specific proof-resource report
   version/domain, while the accepted constructive boundary exposes one
   executable generic V2 proof-resource report schema for both result kinds.

V4 follows the later corrected certificate contract and the executable
boundary. It does not emit an alias field, relax closed members, rewrite a
historical freeze, or invent an unexposed report schema. Before producer and
runner qualification, the still-red harness requires an explicit versioned
correction to read `local_shutdown_minimality_certificate_id`. This is a
recorded dependency, not a V4 acceptance loophole.

## 7. Hostile evidence

The focused V4 suite rejects, after complete resealing where applicable:

- unchanged value, predecessor 1,947, wrong successor 1,949, and a two-field
  mutation;
- a P1-legal but 524,112-octet nonattainer;
- false terminal outcome, malformed nested SHA-256, and stale typed identity;
- producer-authored proof claims and the wrong payload tag;
- predecessor or non-packed successor authority modes; and
- any extra local context file.

The verifier remains standard-library-only, imports no producer, preflight,
test, generic runtime, or C1/C2/C3 proof checker, and performs no dynamic code
loading. Candidate and output roots remain disjoint; failed runs publish no
partial output and accepted runs recheck all authority/candidate bytes before
atomic publication.

## 8. Accepted artifacts and checks

Accepted implementation bytes before the final control-document seal:

- `scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`
  - 373,327 octets
  - SHA-256 `b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25`
- `tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v4_v49f.py`
  - 24,380 octets
  - SHA-256 `fe5721c92b73b4fd357a0be453581cfbe7a305722c840493d7540ae3f289941b`

Focused and compatibility evidence:

```text
V4 focused acceptance
16 passed in 35.30s

case 5 + V0/V1/V2 differentials + V4
83 passed in 187.48s

packed boundary + V3 differential + V4
61 passed in 671.16s

pre-implementation 32-file Stage 1 baseline
487 passed in 2183.29s

V4-extended 33-file Stage 1 core matrix
503 passed

filtered A4-T
59 passed, 2 skipped, 3 deselected

unfiltered A4-T
61 passed, 2 skipped, 1 failed
sole failure: A4_T_PARENT_PILOT_RUNNER_MISSING

filtered A4-P6-T
13 passed, 2 skipped, 6 deselected

unfiltered A4-P6-T
13 passed, 2 skipped, 6 failed
failures: five frozen producer-not-qualified cases and the absent parent runner
```

The V4-extended core count above is the required final target for the control
seal. Generator check, control checker/tests, lint, compilation, expected-red
recheck, and repository diff hygiene must agree on the final documentation
tree before this packet is treated as durably sealed.

## 9. Advancement decision

`A4-P6-V4` is accepted. `A4-P6-V-A` is the only next verifier packet. It must
independently reconstruct all V0–V4 authority modes, exact result and receipt
identities, all successor resource vectors, deterministic double runs, source
isolation, candidate immutability, and the still-red producer/runner boundary.

Producer expansion and the parent runner remain held. Formal `S1-A4`, Raw V8
Step 2, Stage 1, and every paper/live or profitability claim remain `NO-GO`.

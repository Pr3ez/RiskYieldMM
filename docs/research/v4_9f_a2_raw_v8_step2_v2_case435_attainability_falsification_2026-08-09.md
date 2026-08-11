# Raw V8 Step-2 V2 case-435 attainability falsification

**Date:** 2026-08-09  
**Gate:** `S1-A4 / A4-P6-V`  
**Decision:** `NO-GO — FROZEN P2/P3 CONTRACT IS INFEASIBLE`  
**Correction sub-gate:** `A4-P6-C435`  
**Stage 1:** `NO-GO`

## Executive decision

Do not extend the independent verifier or producer to case 435 under the
current frozen maximum-protocol V2 profile. The profile's P2 structural
endpoint is 262,143 canonical octets, while an independent, deliberately
permissive upper-bound construction proves that every P1-legal retained
`TargetObservationV2` is smaller than that endpoint. P3 requires equality with
the P2 endpoint, so no conforming case-435 witness can exist.

This is a contract falsification, not a failed search for a large example. The
analyzer admits some combinations that the exact application predicates would
reject, maximizes components independently, and still reaches at most 260,909
canonical octets. Its 1,234-octet deficit therefore also applies to the
smaller legal domain.

The 260,909-octet result is **not** an exact attainable maximum and must not be
substituted into the seed, finalization manifest, boundary, verifier, producer,
or six-case target.

## Frozen authority coordinate

| Property | Frozen value |
|---|---:|
| Case position | `435` |
| Logical count plan ID | `9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a` |
| Constraint-scope profile position | `369` |
| Constraint-scope profile ID | `505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540` |
| Measured type | `TargetObservationV2` |
| Measured sequence ordinal | `64` |
| Target-field count | `185` |
| P2 source | `STRUCTURAL_TEMPLATE_SUPERSET_V1` |
| Generic P2 attainability claimed by seed | `false` |
| Root codec relation | canonical octets `< 262,144` |
| Frozen P2 upper endpoint | `262,143` octets |

The seed already labels the generic structural P2 result as an unattained
superset. That status is compatible with the counting preflights, but it is
not compatible with the later P3 requirement that a retained legal witness
have canonical length exactly equal to P2.U.

## Independent method

The checker is:

`scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py`

It reads only three pinned data authorities:

| Authority | Raw SHA-256 |
|---|---|
| Corrected V2 seed catalog | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| V4 inventory | `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b` |
| External-schema V2 structural registry | `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3` |

It does not import or read the candidate producer, independent verifier,
rejected V1 constructive implementation, production runtime, or an existing
application-witness artifact. Its Python import surface is restricted to
`hashlib`, `json`, `pathlib`, and `sys`.

For every one of the 185 ordered target fields, it enumerates the available,
censored, unavailable, not-applicable, attempt-state, failure-phase, and error
forms admitted by the inventory, then retains the longest canonical record.
The construction is intentionally no narrower than the legal domain:

- repeated longest collection members are permitted even where a later rule
  could require uniqueness;
- an OS error form retains both maximal errno data and a maximal non-OS class;
- context scalars are maximized independently even where discriminator and
  status combinations are mutually inconsistent;
- exact-marker and operation compatibility restrictions are not used to
  reduce the length bound; and
- record identities are recomputed, while their fixed-width digest fields do
  not hide any variable-length contribution.

The analyzer separately reconstructs the top-level canonical length from the
185 field bounds, array punctuation, and fixed non-field portion. This guards
against relying only on the constructed superset object's serialized length.

## Reproducible result

| Component | Canonical octets |
|---|---:|
| Sum of 185 independent field superset bounds | `258,347` |
| Field-array brackets and commas | `186` |
| Observation fixed/non-field portion | `2,376` |
| Derived legal-domain superset upper bound | `260,909` |
| Frozen structural P2 endpoint | `262,143` |
| Unattainable gap | `1,234` |

The exact arithmetic is:

```text
258347 + 186 + 2376 = 260909
262143 - 260909 = 1234
```

Additional frozen evidence:

| Property | Value |
|---|---|
| Analysis ID | `b126fb9bef8439baf49c993c036c80a874a03ab0e8f6ab1be016d140dd5d0491` |
| Ordered field-bound vector SHA-256 | `8ce7e847cf0020ca6ab10f763f7702cc6aad82e7043a865ce55574af6bd73b57` |
| Constructed superset canonical SHA-256 | `cc7e307b1a7f20dc99b9288441701f4d704e63e088e6dd23e25d7488cee9df36` |
| Analyzer raw octets / SHA-256 | `30,809` / `9c524159509c93d45e6e00ace592498c8bf61bfffab0f3d9167f265482f92b22` |
| Test raw octets / SHA-256 | `5,247` / `db658cbdead10b102081fa659e7b65b2694975c07a61e5e69619f121e24bf879` |

The dedicated test result is `7 passed`. It covers the exact report, two-run
CLI determinism, import and evidence-source isolation, three authority-hash
substitutions, and the distinction between a domain upper-bound proof and a
failed candidate search.

Fresh final-tree regression preserves every accepted predecessor identity:

| Check | Result |
|---|---|
| Seed catalog exact check | `13,419,905` bytes; SHA-256 `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Finalization-manifest exact check | PASS with required empty output |
| Green seed-through-falsification/control matrix | `258 passed` in 417.85 s on the final tree |
| A4-T accepted selection | `59 passed, 2 skipped, 3 deselected` |
| A4-T full fail-first surface | `61 passed, 2 skipped, 1 failed`; only `A4_T_PARENT_PILOT_RUNNER_MISSING` |
| A4-P6-T accepted selection | `13 passed, 2 skipped, 6 deselected` |
| A4-P6-T full fail-first surface | `13 passed, 2 skipped, 6 failed`; exactly five producer-not-qualified cases plus absent runner |
| Combined accepted selections | `330 passed, 4 skipped, 9 deselected` |
| Stage-1 control plus case-435 focused tests | `18 passed` |

The seed, finalization manifest, constructive boundary, independent verifier,
separate producer, and six-case target retain their accepted byte identities.

## Logical consequence

Let `L` be the P1-legal case-435 witness domain and `S` the analyzer's
deliberately enlarged domain. The construction establishes:

```text
L is a subset of S
max canonical_length(S) <= 260909
P2.U = 262143
P3 requires canonical_length(witness) = P2.U
```

Therefore:

```text
for every witness in L:
    canonical_length(witness) < P2.U
```

P3 is unsatisfiable at this frozen coordinate. A verifier accepting a
case-435 candidate under these authorities would necessarily weaken P1, P2,
or P3 and would be incorrect.

## Impact on accepted work

- `S1-A1`, `S1-A2`, and `S1-A3` remain valid for the claims they actually
  made: closed seed structure, exact counting agreement, and frozen resource
  authority. The falsification does not change their counting identities.
- `A4-B0`, `A4-T`, `A4-V`, and `A4-P` remain valid at the accepted case-5
  boundary.
- `A4-P6-T` remains accepted as historical fail-first test infrastructure and
  case-5 positive control. Its frozen case-435 success condition is now known
  to be infeasible, so it cannot serve as an achievable six-case acceptance
  target without a new versioned correction.
- `A4-P6-V` is on `HOLD`. Extending the verifier now would either stop at case
  435 or silently encode a false attainability claim.
- The independent verifier, separate producer, parent runner, accepted
  six-case target, constructive boundary, seed, and finalization manifest were
  not edited by this falsification packet.

This evidence does not prove that other generic structural P2 endpoints are
unattainable, but it disproves the assumption that such endpoints can be
promoted to exact maxima without an application-aware attainability proof.
Merely replacing case 435 in the pilot would hide, not solve, the all-475-case
closure problem.

## Required correction: `A4-P6-C435`

The next bounded action is a fail-first, versioned correction design. It must:

1. derive an application-aware upper bound for case 435 from the frozen target
   registry, external-schema rules, profile application schedule, and exact
   retained coordinate;
2. independently construct a P1-legal witness that attains the same value;
3. distinguish `SUPERSET_UPPER_BOUND` from `EXACT_ATTAINED_MAXIMUM` in the
   transfer result and prohibit P3 equality claims for unattained supersets;
4. determine which other generic profiles rely on the same structural-only
   shortcut before changing shared authorities;
5. freeze a versioned seed/manifest/boundary/qualification transition rather
   than mutating an accepted identity in place; and
6. rerun both independent preflights, comparator, finalization, boundary,
   case-5 regression, and corrected pilot target before `A4-P6-V` resumes.

The correction may use 260,909 only as a falsifying ceiling. Its acceptance
requires an independently reproduced **exact attainable** maximum, not a
tighter unattained bound.

The successor
[`profile-attainability scope and correction design`](v4_9f_a2_raw_v8_step2_v2_profile_attainability_scope_and_correction_design_2026-08-10.md)
accepts `A4-P6-C435-A`, expands the affected surface to 407 programs / 474
internal scope cases, freezes the three-channel exactness contract, and makes
case-435 dependency closure `A4-P6-C435-B` the next bounded action.

That next action is now accepted by the
[`case-435 dependency-closure acceptance`](v4_9f_a2_raw_v8_step2_v2_case435_dependency_closure_acceptance_2026-08-10.md);
exact upper-bound channel `A4-P6-C435-C1` is current.

## Nonclaims

This packet does not provide the corrected exact maximum, a legal case-435
attainer, a corrected seed, an expanded verifier or producer, a passing
six-case pilot, all-475-case maximum evidence, Stage-1 exit, paper/live
readiness, predictive edge, trading safety, or profitability.

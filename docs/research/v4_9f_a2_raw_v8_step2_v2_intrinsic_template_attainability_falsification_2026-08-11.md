# Raw V8 Step-2 V2 intrinsic-template attainability falsification

**Date:** 2026-08-11  
**Gate:** `S1-A4 / A4-R475-V1`  
**Accepted packet:** `A4-R475-V1-F-A`  
**Decision:** `NO-GO — 26 FROZEN P2 ENDPOINTS ARE UNATTAINABLE`  
**Correction umbrella:** `A4-R475-V1-C`  
**Stage 1:** `NO-GO`

## Executive decision

Do not implement the all-case verifier against the current intrinsic-template
plans. The accepted `A4-R475-T` policy explicitly requires a complete-campaign
`NO-GO` when a P2 endpoint is unattained. The pre-implementation audit proves
that 26 of the 66 intrinsic cases have exactly that defect.

The templates replace several bounded text languages with an ambient
`RELAXED_JSON_STRING` cell while computing P2. Restoring even a deliberately
permissive canonical-JSON upper bound from the pinned language authority makes
each of the 26 root bounds strictly smaller than its published P2 endpoint.
Intrinsic rules, identity equalities, and cross-field constraints are not used
to reduce these new bounds, so they remain supersets of the legal P1 domain.
No legal witness can bridge the resulting positive gaps.

Case 8 independently closes the issue without relying on the 26-case census:

```text
published P2 endpoint                         524288
independently derived exact legal maximum        928
independent legal attainer                       928
unattainable P3 gap                           523360
```

The attainer passes the pinned typed runtime, its intrinsic time/monotonic
ordering rule, standalone semantic-identity recomputation, and the codec. An
all-66 V1 acceptance under the frozen plans is therefore impossible.

## What changed in our understanding

`A4-R475-V0` correctly established the complete authority and typed-runtime
foundation while accepting no candidates. Its acceptance did not prove that
the 66 future structural endpoints were attainable. The `A4-R475-V1` design
audit was the first point at which those endpoints had to meet an actual legal
witness.

The earlier roadmap wording treated `LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT`
as an established property. It is only a frozen plan claim. This packet tests
that claim and rejects it where it conflicts with the registry.

## Independent method

The primary analyzer is:

`scripts/tests/check_raw_v8_step2_maximum_protocol_v2_intrinsic_template_attainability_v49f.py`

It imports no verifier, producer, runtime, test oracle, or stored witness. It
reads only these pinned data authorities:

| Authority | Raw octets | Raw SHA-256 |
|---|---:|---|
| Corrected V2 seed | `13,419,905` | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Structural registry | `1,469,663` | `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3` |
| All-case contract | `382,710` | `3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb` |

For each of positions 1–66 it independently executes the frozen postorder
transfer template twice:

1. the published P2 execution, including ambient relaxed-string cells;
2. a language-aware superset execution that restores sound serialized-length
   ceilings for finite/enum, RFC3339 UTC, UInt128 decimal, SHA-256, canonical
   base64, ASCII-DFA, and Unicode-identifier languages.

The second execution remains deliberately permissive:

- it does not execute an intrinsic rule to lower an endpoint;
- it does not use payload-derived identity equality to lower an endpoint;
- it uses a per-byte worst-case JSON expansion for ASCII DFAs;
- it allows the maximum UTF-8 budget plus a per-scalar JSON escape allowance
  for Unicode identifiers; and
- raw canonical JSON strings remain at the ambient ceiling.

Therefore a strict language-aware gap is a proof of impossibility, not a
failed candidate search. The 40 cases without such a gap are explicitly **not**
promoted to attainable; they remain unresolved until the correction packet
provides upper and attainer evidence.

## Falsified cases

| Case | Type / alternative | Published P2 | Legal-domain superset upper | Minimum gap |
|---:|---|---:|---:|---:|
| 1 | `CapacityMeasurementAckDeadlineExpiryResultEvidenceV1` | 524,735 | 3,132 | 521,603 |
| 2 | `CapacityMeasurementAckDeadlineExpirySpecV1` | 3,145,728 | 467 | 3,145,261 |
| 7 | `CapacityMeasurementCrossFieldConstraintDefinitionV1` | 3,145,728 | 2,261 | 3,143,467 |
| 8 | `CapacityMeasurementDispatchWindowEvidenceV1` | 524,288 | 928 | 523,360 |
| 9 | `CapacityMeasurementDueDecisionClockEvidenceV1` | 524,288 | 2,685 | 521,603 |
| 12 | `CapacityMeasurementFixedUIntMapEntryV1` | 3,145,728 | 291 | 3,145,437 |
| 18 | `CapacityMeasurementLocalShutdownSpecV2` | 3,145,728 | 1,092 | 3,144,636 |
| 19 | `CapacityMeasurementLogicalOutputFrameV1` | 3,145,728 | 206 | 3,145,522 |
| 21 | `CapacityMeasurementOperationDeclarationV1` | 3,145,728 | 2,099,068 | 1,046,660 |
| 22 | result body / `ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1` | 523,728 | 3,132 | 520,596 |
| 25 | result body / `SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2` | 523,724 | 36,277 | 487,447 |
| 28 | spec body / `ACK_DEADLINE_EXPIRY_SPEC_V1` | 2,096,781 | 467 | 2,096,314 |
| 30 | spec body / `LOCAL_SHUTDOWN_SPEC_V2` | 2,096,791 | 1,092 | 2,095,699 |
| 31 | spec body / `SUBSCRIPTION_DISPATCH_SPEC_V2` | 2,096,777 | 2,042 | 2,094,735 |
| 32 | `CapacityMeasurementOptionalTextValueV1` | 3,072 | 563 | 2,509 |
| 34 | `CapacityMeasurementStatusReasonPolicyDefinitionV1` | 3,145,728 | 22,571 | 3,123,157 |
| 36 | `CapacityMeasurementSubscriptionDispatchResultEvidenceV2` | 3,145,728 | 36,277 | 3,109,451 |
| 37 | `CapacityMeasurementSubscriptionDispatchSpecV2` | 3,145,728 | 2,042 | 3,143,686 |
| 42 | target value / `OPTIONAL_TEXT` | 3,072 | 563 | 2,509 |
| 44 | target value / `TEXT` | 3,072 | 538 | 2,534 |
| 45 | target value / `TEXT_LIST` | 3,072 | 2,091 | 981 |
| 48 | `CapacityMeasurementTextListValueV1` | 3,072 | 2,091 | 981 |
| 49 | `CapacityMeasurementTextValueV1` | 3,072 | 538 | 2,534 |
| 52 | `CapacityMeasurementValueConstraintDefinitionV1` | 3,145,728 | 2,727 | 3,143,001 |
| 59 | `OperationCounterSnapshotV1` | 2,048 | 1,312 | 736 |
| 60 | `SourceErrorDetailV1` | 2,048 | 1,071 | 977 |

Frozen census evidence:

| Property | Value |
|---|---|
| Falsification ID | `0b53bd2d79c5f923f1887f7e33f167625fd43753c22345074ae2768dec0d58ad` |
| Contradiction-vector SHA-256 | `3d1c35477e174cde53ab163c516dea9d7132a468bfa7c7954f1ca538317f8e5d` |
| Contradiction count | `26 / 66` |
| Not falsified by this test | `40 / 66` |

## Independent acceptance

The separate reviewer is:

`scripts/tests/review_raw_v8_step2_maximum_protocol_v2_intrinsic_template_attainability_v49f.py`

It does not import the analyzer. It runs it twice in isolated interpreters,
recomputes the semantic envelope, and independently derives the case-8 exact
upper directly from the 12 member schemas. It then validates the independently
constructed 928-octet record with the pinned 42-rule runtime.

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| Analyzer | `34,534` | `5af98367704e9ef695af050637ebb5027aeb516b5f74c971d6781ab7b232f4ff` |
| Analyzer tests | `8,925` | `302a80f00e15527fb58b213e0be78ca91230079f559d183d654d4a448fb4b9c2` |
| Independent reviewer | `18,415` | `90b484d48637d75985e183fb03d8f976883da7781368c1279c6803ae0be2448c` |
| Acceptance report | `2,137` | `a56bd57e795f5c6cda9eed5d8c9512392bff6e0a2637c5fe69fc42508c1ff9ea` |
| Acceptance tests | `6,694` | `dec9ff7c55ff53a6ac0a9659be921ec34d528ab659f10e5f76f9e5725ea2827b` |

Acceptance report ID:
`7dfd4073f40f1825356b32c3ed0ca7f291a4a179827882fbbedbdeb96030102e`.

The focused analyzer/reviewer matrix is `23 passed`. It covers all 26 frozen
bounds, exact case-8 construction, a differential typed-runtime check,
two-run deterministic CLIs, source-role isolation, authority-hash barriers,
semantic resealing, acceptance-overclaim mutations, and the explicit 40-case
nonclaim.

## Alternatives evaluated

| Alternative | Evaluation | Decision |
|---|---|---|
| Accept a legal witness shorter than P2 | Converts an exact-maximum protocol into an upper-bound-only protocol and violates P3 | Rejected |
| Apply hidden language corrections only inside the verifier | Makes the verifier, rather than a frozen authority, choose the claimed maximum | Rejected |
| Edit the accepted base seed/templates in place | Invalidates predecessor IDs and cascades through accepted preflight/F2 evidence | Rejected |
| Raise codec or resource limits until a witness fits | Cannot make a fixed RFC3339/UInt128/SHA language produce hundreds of thousands of extra bytes | Rejected |
| Hand-code 26 answers in the verifier | Couples proof and implementation and leaves the other 40 cases unproved | Rejected |
| Versioned intrinsic exactness delta with separate upper/attainer channels | Preserves predecessor evidence and makes every changed endpoint explicit and independently testable | Selected |

No web research is needed to decide this gate. The relevant primary sources
are the repository's byte-pinned schema, transfer programs, and campaign
contract; external literature cannot redefine their language domains or P3
equality rule.

## Correction architecture and next packet

`A4-R475-V1-C` is a correction umbrella, not permission to mutate the live
verifier. Its bounded sequence is:

1. **C1 — complete dependency census and correction contract.** Freeze every
   text-language, rule, identity, codec, union, and array dependency for all 66
   cases; specify the successor resolver and immutable predecessor boundary.
2. **C2 — dual exactness channels.** Produce a proof-carrying legal upper for
   every case and, from separate code, a P1-legal attainer. Language handling
   must use finite enumeration, closed built-in formulas, DFA dynamic
   programming, and a proved Unicode/profile program—not ambient relaxation.
3. **C3 — exactness join and versioned authority transition.** Accept a case
   only when the independently identified upper and attainer have the same
   problem authority and byte length. Publish a successor delta rather than
   editing the base seed or the accepted all-case contract in place.
4. **Return to V1.** Extend the versioned verifier only after C3 acceptance;
   accept exactly the corrected 66 intrinsic cases, preserve the byte-exact
   six-case roles and accepted V0 evidence, and keep the other 409 cases
   fail-closed.

The correction must preserve F0/F2 ceilings. If an exact channel cannot close
within those limits, the result remains `NO-GO`; limits may not be tuned from
the answer.

## Impact on accepted work

- `A4-R475-T` remains valid and is now enforcing its stated unattained-case
  policy.
- `A4-R475-V0` remains accepted for its actual foundation-only claim. Its
  42,659-byte source remains SHA-256
  `15adb9fd5c427c1e1e96ff630e13b36d3f385f12eaf68a388a5da7be48dbf5aa`.
- The accepted six-case producer, verifier, and runner remain byte exact.
  Their verifier remains 373,327 bytes with SHA-256
  `b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25`.
- No all-case producer, runner, campaign checkpoint, case result, or accepted
  publication was created.
- `A4-R475-V2` and every later all-case packet remain waiting.

The immediate execution pointer is now `A4-R475-V1-C` while formal Stage 1
remains `NO-GO`.

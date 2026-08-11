# Raw V8 Step-2 V2 case-435 exactness-join acceptance

**Date:** 2026-08-10  
**Sub-gate:** `A4-P6-C435-C3`  
**Decision:** `ACCEPTED`  
**Next bounded sub-gate:** `A4-P6-C435-D`  
**Stage 1:** `NO-GO`  
**Verifier expansion:** `HOLD`

## 1. Decision

`A4-P6-C435-C3` is accepted. A small, separately implemented equality join
consumes the frozen C1 exact-upper certificate and frozen C2 legal-attainer
certificate. It accepts only after independently reconstructing both channel
identities and confirming that they describe the same case, profile, scope,
target, raw authority, dependency manifest, canonicalization contract, and P1
application schedule.

The two independently accepted values are equal:

```text
C1 proved legal upper bound       = 257,887 canonical octets
C2 measured P1-legal attainer     = 257,887 canonical octets
therefore case-435 exact maximum  = 257,887 canonical octets
```

The C3 exactness-join certificate has identity:

```text
2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f
```

This closes the case-local exactness theorem. It does not yet change the
accepted seed, manifest, constructive boundary, qualification target, or pilot
authority. That versioned authority transition belongs exclusively to
`A4-P6-C435-D`; therefore `A4-P6-V` remains on hold and Stage 1 remains
`NO-GO`.

## 2. Accepted artifacts

| Artifact | Role | Bytes | SHA-256 |
|---|---|---:|---|
| `scripts/tests/join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py` | minimal identity-bound C1/C2 equality join | 16,018 | `236adccb8d80adcf16f834e6766e5b1085ed2664fa777a46e049f920eb1110e4` |
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_exactness_certificate_v49f.py` | independent channel and join-certificate reconstruction | 16,594 | `18cbe51ed71f3ef7b06f251f0e83178d9529af5e4360559b91363a4b76996226` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py` | positive, isolation, identity, equality, and hostile-mutation suite | 11,081 | `fdda11a22e29797e8878c8321d7d724a30e44cd73d1ffde2ab6857efbef17cc2` |

The JSON join certificate remains a deterministic derived output rather than a
checked-in source authority. Both programs validate the pinned raw files and
the four accepted channel source hashes before accepting a result. A modified
C1 or C2 program must therefore be reviewed and versioned rather than silently
re-sealing a successor certificate.

## 3. Frozen channel and problem identities

The join accepts exactly these channel certificates:

| Channel | Accepted certificate ID | Pre-join claim |
|---|---|---|
| C1 exact upper | `c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4` | exact upper proved; independent attainer not accepted |
| C2 legal attainer | `1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba` | P1-legal attainer constructed; exactness not claimed |

Both must bind dependency manifest
`d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c`
and the same seven raw-authority hashes. The case binding is frozen to case
435, profile position 369, `TargetObservationV2`, measured sequence ordinal
64, profile ID
`505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540`,
plan ID `9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a`,
and conditioning-program ID
`0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8`.

The independently reconstructed P1 schedule binds:

| Quantity | Result |
|---|---:|
| application invocations | 137 |
| charged rule evaluations | 12,531 |
| direct expression nodes | 125,431 |
| ordered instruction SHA-256 | `08955976b1ad455a7e18068ae8d8affe1316f50a56cf50dafd95dc0e0331b20e` |

## 4. Why a separate equality join is the correct method

Three implementation choices were evaluated:

1. let C1 import and validate the C2 witness;
2. let C2 import the C1 maximum and claim exactness;
3. keep both accepted channels unchanged and add a third, minimal join that
   validates their identities, common problem definition, dispositions, and
   numeric equality.

The first two approaches collapse the deliberately separate proof boundaries
and make shared defects harder to detect. The third was selected because it
preserves the independent upper and attainment arguments, adds little new
semantic surface, and exposes every required equality as a closed predicate.

The join does **not** require the C1 maximizing observation identity to equal
the C2 attainer observation identity. Such identity equality is corroborating
evidence, not a mathematical requirement: a sound proof that no legal value
exceeds `U`, plus any independently verified legal witness with length `U`, is
sufficient to prove that `U` is the exact maximum. Requiring byte-identical
witness construction would add coupling without strengthening the theorem.

No external literature search was necessary for this bounded sub-gate. It is
a repository-defined finite proof composition whose correctness is determined
by the frozen protocol authorities and direct falsification tests, not by an
empirical finance result.

## 5. Required join predicates

The accepted certificate freezes exactly eight predicates:

1. accepted channel identities match;
2. case, profile, scope, and target bindings are equal;
3. raw authority sets are equal;
4. dependency manifests are equal;
5. the application schedule is bound to the shared conditioning program;
6. the C1 upper channel proves its bound and still makes no attainer claim;
7. the C2 attainer channel is fully P1-legal and made no prior exactness claim;
8. the proved upper equals the measured legal-attainer canonical length.

The certificate then and only then emits
`exact_maximum_proved = true`, `exactness_claimed = true`, and
`exact_maximum_octets = 257887`.

## 6. Independent verification and falsification evidence

The checker imports neither C1, C2, nor the join implementation. It separately
validates both complete input certificate schemas and sealed identities,
reconstructs the raw and channel-source authorities, derives the case/program
binding and schedule from the seed, rebuilds the expected join projection, and
recomputes its semantic ID.

The focused suite passes 16 tests in 192.27 seconds. It regenerates a fresh C1
certificate and a fresh C2 legal attainer once, then covers:

- deterministic join and independent reconstruction;
- standard-library-only source boundaries with no local cross-imports;
- the explicit non-requirement for witness-identity equality;
- re-sealed upper and attainer substitutions;
- a separately reached unequal-length predicate failure;
- synchronized but incorrect case/profile changes across both channels;
- synchronized but incorrect raw-authority changes;
- schedule changes;
- premature exactness in C2 and a premature attainer claim in C1;
- a re-sealed successor/verifier-release mutation in the join;
- duplicate JSON members; and
- command-line interoperability between the join and checker.

The direct replay commands are:

```bash
python scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py \
  > /tmp/case435-c1-certificate.json
python scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py \
  > /tmp/case435-c2-certificate.json
python scripts/tests/join_raw_v8_step2_maximum_protocol_v2_case435_exactness_v49f.py \
  . /tmp/case435-c1-certificate.json /tmp/case435-c2-certificate.json \
  > /tmp/case435-c3-certificate.json
python scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_exactness_certificate_v49f.py \
  . /tmp/case435-c1-certificate.json /tmp/case435-c2-certificate.json \
  /tmp/case435-c3-certificate.json
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_case435_exactness_join_v49f.py
```

## 7. Nonclaims and successor contract

C3 proves only the exact application-aware maximum for the frozen case-435
problem. It does not prove the remaining 474 case results, change any accepted
authority, authorize the pilot, complete the independent verifier/producer,
or establish Stage 2, paper-trading, live-trading, or profitability readiness.

`A4-P6-C435-D` must now publish a versioned, exact-delta authority transition.
It must preserve every V1 authority as predecessor evidence, replace the
falsified case-435 structural-superset claim with the C3 exact theorem, bind the
new seed/manifest/boundary/target identities transitively, and prove that no
unrelated profile or case changes. Only after D is independently accepted may
`A4-P6-V` resume against the corrected six-case target.

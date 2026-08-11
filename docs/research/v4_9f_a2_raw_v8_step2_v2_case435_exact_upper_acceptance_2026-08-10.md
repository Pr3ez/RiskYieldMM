# Raw V8 Step-2 V2 case-435 exact-upper acceptance

**Date:** 2026-08-10  
**Sub-gate:** `A4-P6-C435-C1`  
**Decision:** `ACCEPTED`  
**Next bounded sub-gate:** `A4-P6-C435-C2`  
**Stage 1:** `NO-GO`  
**Verifier expansion:** `HOLD`

## 1. Decision

`A4-P6-C435-C1` is accepted. Under the frozen case-435 dependency manifest

```text
d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c
```

the exact application-aware legal upper bound for case 435 is:

```text
257,887 canonical octets
```

The portable upper certificate has identity:

```text
c01bba7c5f5f19c12957493c7a0989dc3ddbc42306c0f059ee922c18341e62b4
```

This accepts only the upper-bound channel. It does **not** accept a legal
attainer, does not complete the equality join, does not authorize changing the
accepted seed or constructive authorities, and does not resume `A4-P6-V`.
The certificate explicitly freezes
`independent_attainer_accepted = false`; `A4-P6-C435-C2` must construct and
measure the attainer independently.

## 2. Accepted artifacts

| Artifact | Role | Bytes | SHA-256 |
|---|---|---:|---|
| `scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py` | proof-carrying finite-domain upper solver | 63,596 | `fd151f412d8c51eec3de454b91bf34ab1c705d2d81dbb1a37504ac06efa74f6c` |
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py` | separate certificate verifier and independent recomputation oracle | 46,246 | `e19a00db0f989f3f3740e3314f179307362246efd5a69cea78d50e122fb6877d` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py` | positive, independence, determinism, and hostile-mutation acceptance suite | 11,757 | `2c62d573c87dc2f160d91ed8acdd309e46ef86f7fef2fd69232b8195c1d06dfc` |

The solver writes the complete portable JSON certificate to standard output.
No generated certificate file is accepted as a new authority: the verifier
reconstructs the result from the pinned sources on every invocation.

## 3. Frozen authority binding

Both programs fail closed on the following raw-source identities:

| Authority | SHA-256 |
|---|---|
| accepted V2 seed catalog | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Raw V8 Step-2 inventory | `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b` |
| structural registry | `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3` |
| literal authority | `aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2` |
| rule-application ledger | `979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282` |
| accepted rule-runtime source | `47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22` |
| accepted dependency analyzer | `f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30` |

The case binding is position 435, profile position 369, target type
`TargetObservationV2`, measured sequence ordinal 64, profile ID
`505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540`,
plan ID `9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a`,
and conditioning-program ID
`0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8`.

## 4. Why this method was selected

Three viable approaches were evaluated:

1. reuse the accepted rule runtime as the maximum oracle;
2. ask an optimizer or unconstrained search to find a large witness;
3. reduce every finite canonical-length domain to predicate-equivalent endpoint
   representatives, enumerate the closed status/method/reason/error branches,
   and emit a certificate independently replayed by a second implementation.

The first approach is retained only as a challenger because shared defects
would make its agreement non-independent. The second can find candidates but
does not by itself prove completeness or exactness. The third was selected
because the schema domains are finite or have frozen finite bounds, the rule
predicates observe only closed enums, cardinalities, equality classes, and
bounded scalar/text properties, and the dependency packet already proved the
only non-singleton field component. It therefore supplies a complete finite
quotient and an auditable certificate without trusting a stochastic search or
an opaque optimization backend.

No additional external research was needed for this bounded sub-gate: the
decision is a formal implementation question governed by the repository's
frozen schemas, rules, canonical codec, and accepted dependency proof. External
quantitative-finance evidence remains relevant to later modeling stages, not
to the byte-exact protocol proof here.

## 5. Exact derivation

The accepted conditional decomposition is:

```text
422 fixed non-context/non-field octets
+ 1,747 exact context octets
+ 2 field-array bracket octets
+ 184 field-array comma octets
+ 255,532 maximum field octets
= 257,887 canonical octets
```

The solver and checker both reconstruct:

| Quantity | Exact result |
|---|---:|
| fields | 185 |
| ordinary singleton components | 182 |
| coupled A1 fields | 3 |
| broad reduced field candidates | 4,089 |
| legal reduced field candidates | 2,971 |
| A1 Cartesian tuples | 9,261 |
| legal A1 tuples | 9,051 |
| maximizing A1 component octets | 4,111 |
| separator branches | 5 |

The A1 maximizing tuple does not activate the FIFO equality constraint. It is
nevertheless selected from the complete three-field Cartesian product after
the joint predicate is applied; the three fields are not treated as
unconditionally independent.

The five separator branches have exact observation bounds:

| Branch | Canonical octets |
|---|---:|
| exact marker | 257,887 |
| artifact-bound placeholder | 188,317 |
| observer-error placeholder | 188,317 |
| source-clock placeholder | 188,506 |
| target-boundary placeholder | 189,077 |

The exact-marker branch is therefore the unique maximum by length. Its
reconstructed observation has ID
`86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9`
and canonical SHA-256
`f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad`.
The full 67-observation separator lifecycle contains 63 preceding boundary
placeholders, one exact marker at sequence ordinal 64, and the two terminal
observations. Its root ID is
`572b4a11e1d4108faf55361b1c5dc165d4730e20e7c73c58a2b8b34822c913fb`.
This lifecycle demonstrates that the maximizing **upper-channel context** is
internally feasible; it is not the independent P1 attainer required by C2.

## 6. Independence boundary

The solver and checker are separate standard-library programs and import
neither each other nor the accepted rule runtime. They share the frozen raw
authorities because otherwise they would be proving different problems, but
their executable methods differ:

- the solver generates a deliberately broader reduced candidate set and then
  applies separately implemented intrinsic, descriptor, context, and A1
  predicates;
- the checker directly constructs only legal decision-table branches and
  independently rebuilds field winners, the A1 joint maximum, all separator
  branches, canonical bytes, semantic IDs, lifecycle hashes, and the final
  certificate identity.

The accepted runtime was used once as a non-authoritative challenger. It agreed
on 257,887 octets and the field/status distribution, but neither acceptance nor
the regression suite depends on that agreement.

## 7. Falsification and acceptance evidence

The dedicated suite passes 17 tests. It proves deterministic solver output,
file and pipe verifier equivalence, standard-library/cross-import isolation,
the exact composition and branch values, and independent replay. It also
rejects, even after the attacker recomputes the outer certificate identity:

- a one-octet upper-bound inflation;
- a forged field-sum or individual field maximum;
- a forged legal-candidate count;
- a forged A1 legal-tuple count;
- a forged placeholder-branch length;
- a forged lifecycle root;
- a premature `independent_attainer_accepted = true` claim;
- an omitted field record;
- authority-source drift;
- duplicate JSON members; and
- an unsealed case-binding mutation.

The direct acceptance command is:

```bash
python scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_case435_upper_v49f.py \
  | python scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_upper_certificate_v49f.py -
```

It returns certificate ID `c01bba7c…`, exact upper 257,887, 2,971 legal reduced
candidates, 9,051 legal A1 tuples, five branches, and next sub-gate
`A4-P6-C435-C2`.

## 8. Nonclaims and successor contract

This checkpoint does not claim that a 257,887-octet P1-legal retained witness
exists. C1 proves only that no legal case-435 observation can be longer under
the pinned authority and conditional factorization. It also makes no claim
about model quality, trading profitability, Stage 2 readiness, paper trading,
or live activation.

`A4-P6-C435-C2` must now be implemented from a separate source boundary. It
must construct the complete 67-observation retained context, execute the pinned
P1 application schedule, measure the retained witness canonical bytes, and
emit its own authority-bound attainment certificate without importing this
upper solver, this verifier, the stored upper value, or a stored maximizing
witness. Only `A4-P6-C435-C3` may join the two results, and it may accept
exactness only when all case/profile/scope/authority/schedule identities match
and the independently measured witness length equals 257,887 exactly.

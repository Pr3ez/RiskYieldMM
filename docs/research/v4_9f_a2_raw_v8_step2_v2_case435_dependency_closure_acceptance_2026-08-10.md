# Raw V8 Step-2 V2 case-435 dependency-closure acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-C435-B`  
**Decision:** `DEPENDENCY CLOSURE AND CONDITIONAL FACTORIZATION ACCEPTED`  
**Implementation state:** `NO-GO — EXACT OPTIMIZER AND INDEPENDENT ATTAINER NOT IMPLEMENTED`  
**Stage 1:** `NO-GO`

## 1. Decision

The complete case-435 schema, application, rule, complex-operator, identity,
and canonical-composition dependency surface is now machine-frozen. The
four-category factorization proposed by the predecessor design is valid only
as a **nested conditional decomposition**:

```text
fixed registry + marker contract + selector
                    |
root / complete sequence / measured context separator
                    |
       +------------+-------------------+
       |                                |
182 ordinary singleton fields     3-field A1 component
       +----------------+---------------+
                        |
       exact canonical composition + derived IDs
```

The fields are not unconditionally independent. Each field reads the measured
context, and the context is constrained by the complete root/selector/sequence
lifecycle. Any optimizer that maximizes fields first against a guessed context
is unsound. The accepted order is:

1. prove one separator state feasible under the complete lifecycle;
2. solve all field components exactly conditional on that separator;
3. compose exact canonical octets and recompute all deterministic identities;
4. maximize over the complete separator domain.

This closes `A4-P6-C435-B`. It does not derive the exact maximum. The next
bounded sub-gate is `A4-P6-C435-C1`: implement the proved-upper channel and its
portable certificate. `C2` then constructs the independent legal attainer;
`C3` performs the identity-bound exact-equality join.

## 2. New executable evidence

| Artifact | Role | Raw bytes | Raw SHA-256 |
|---|---|---:|---|
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py` | Independent authority reader, dependency-manifest constructor, graph proof, and fail-closed validator | 53,405 | `f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_dependency_closure_v49f.py` | Independent reconstruction, AST seal, micro-domain equivalence, drift, weakening, and premature-claim tests | 13,899 | `14a4aff4cd0ead03e0ee22a08f478c4f68817a5a0ca285b5194b05c4a58a1ace` |

The checker imports only Python standard-library modules. It does not import
the seed generator, rule runtime, maximum verifier, producer, candidate, or
legacy V1 implementation. The accepted rule runtime is parsed as inert source
data; its relevant transitive function and constant ASTs are sealed rather
than executed.

The focused result is:

```text
12 passed
```

## 3. Pinned predecessor authorities

| Authority | Raw SHA-256 | Use |
|---|---|---|
| Corrected V2 seed | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` | Exact case/program/scope/application schedule |
| V4 source inventory | `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b` | Profiles, fixed authorities, field registry, and embedded structural registry |
| Structural registry | `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3` | Type/value-schema/rule/application graph |
| Rule-literal authority | `aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2` | Exact target registry and marker contract |
| Rule-application ledger | `979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282` | Independent equality check for every selected rule/application descriptor |
| Accepted rule-runtime source | `47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22` | Static AST closure of complex-operator semantics; never executed by the checker |
| Case-435 falsification analyzer | `9c524159509c93d45e6e00ace592498c8bf61bfffab0f3d9167f265482f92b22` | Accepted proof dependency showing the global observation codec cap is non-binding |

No predecessor file above was modified.

## 4. Machine identities

| Record | SHA-256 identity |
|---|---|
| Dependency-closure audit | `56923275cd4422c3bc90115a6ee647b3b7142d1d800a855757d7c90924fd4583` |
| Complete dependency manifest | `d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c` |
| Conditional-factorization proof | `13dd74d6478f11f61d2f7665fc32025b288562b37a7ecd62ecf7595413145dcc` |
| Transitive runtime-function AST vector | `ab3c94ffba6effaa04c483dd941e0b26c46a6e86c0074ccf0022dee7f87348c4` |
| Loaded runtime-constant AST vector | `c35494f1760b7119e2e357b6cc513e2ef0599c1b6214129d6cfa864c86032e83` |

The manifest identity covers the full ordered records, not only these summary
counts.

## 5. Exact closure census

| Surface | Count |
|---|---:|
| Reachable external types | 32 |
| Reachable value schemas | 133 |
| Reachable intrinsic rules | 21 |
| Scheduled cross rules | 5 |
| Total unique selected rules | 26 |
| Unique selected rule-expression nodes | 754 |
| Complex operators | 9 |
| Transitive runtime functions | 24 |
| Loaded runtime constants | 9 |
| Target fields | 185 |
| Field-to-context separator edges | 185 |
| Cross-field decision edges | 3, the exact A1 clique |
| Conditional components | 183 |
| Ordinary singleton components | 182 |
| A1 coupled components | 1 containing 3 fields |

The three A1 fields are:

```text
a1.waiting_count
a1.waiting_kinds
a1.waiting_sequences
```

The exact fixed constraint activates only when all three fields are
`AVAILABLE`; it then requires count/list-length equality, identical index
pairing, no more than four items, and strictly increasing unique sequences.
No other frozen cross-field constraint exists in the target registry.

## 6. Why the factorization is valid

### 6.1 Complete application shape

Case 435 executes exactly these applications:

1. selector/marker-contract admission once;
2. observation/A1 aggregate validation for all 67 observations;
3. descriptor/context validation for 185 fields in each observation;
4. root-membership validation for all 67 observations; and
5. root/selector/lifecycle validation once.

The manifest binds their application IDs, rule IDs, invocation counts,
descriptors, rule ASTs, and input paths against both the structural registry
and the independently stored application ledger.

### 6.2 Local versus shared reads

- Field intrinsic, source-error identity, descriptor-policy, target-value, and
  context rules read one field, its fixed descriptor/registry authority, and
  the shared measured context.
- The A1 aggregate operator is the only legality predicate reading multiple
  target fields, and it resolves exactly the three frozen A1 IDs.
- Root membership reads shared root/context members only.
- Root lifecycle reads all observation contexts plus canonical observation
  identities. Recomputing an identity reads its payload but produces a fixed
  64-hex-character value; it is a deterministic projection, not a choice that
  couples two field domains.
- The selector and marker contract are fixed authorities for case 435.

The manifest seals seven deterministic SHA-256 projection surfaces: context,
source-error detail, field observation, observation, selector entry, selector,
and root. Every present value occupies exactly 66 canonical JSON octets. The
nullable source-error digest occupies either 4 octets (`null`) or 66 octets
and remains local to one field.

### 6.3 Exact composition

For any fixed feasible measured context, canonical observation length is:

```text
422
+ canonical_octets(context)
+ 2 array-bracket octets
+ 184 array-comma octets
+ sum(canonical_octets(field[i]) for i in 0..184)
```

The 422-octet constant is independently reconstructed by replacing only the
context and field-array values with `{}` and `[]` while retaining both
fixed-width observation/context IDs and all envelope members.

The observation-level `LT 262144` cap would normally be a global coupling.
Here it is proved non-binding by the accepted case-435 falsification: even its
deliberately enlarged legal-domain superset is only 260,909 octets. The new
checker binds that predecessor analysis ID
`b126fb9bef8439baf49c993c036c80a874a03ab0e8f6ab1be016d140dd5d0491`.

These facts establish the conditional product structure. They do not solve
the separator or any component maximum.

## 7. Alternatives reassessed

| Approach | Assessment | Decision |
|---|---|---|
| Unconditional per-field maximization | Ignores context-dependent applicability, method/role, checkpoint-marker, attempt, instrumentation, and clock-span predicates | Rejected as unsound |
| One monolithic Cartesian search | Exact in theory, but duplicates fixed authority work and is computationally intractable | Rejected |
| SMT/CP-SAT as final authority | Useful for discovering candidates and contradictions, but solver/version semantics do not provide the required portable independent certificate | Challenger only |
| Hand formula for case 435 | Difficult to audit and cannot safely generalize to the other 473 generic scope cases | Rejected as acceptance authority |
| Nested separator search plus exact conditional components | Preserves every shared dependency, isolates the sole A1 coupling, supports independent certificates, and generalizes through typed manifests | Selected |

The selected design is better than immediately coding the experimental
257,887-byte candidate because that candidate has not proved domain
completeness, separator optimality, or exact attainment. Its value is not an
accepted result and is intentionally absent from this packet's identities.

## 8. Solver contract for `A4-P6-C435-C1`

The next upper-bound implementation must use separate, checkable solvers:

1. **Separator solver:** close the exact root/67-observation/selector/context
   domain. Quotient values only where equal canonical length and identical
   predicate behavior are proved. Marker-ordinal and clock-span relations need
   explicit feasibility certificates, including the preceding 63 checkpoint
   observations.
2. **Scalar and union solver:** enumerate union/status/reason/attempt/method
   branches; evaluate safe-integer endpoints and decimal-width breakpoints;
   derive longest accepted strings from closed enums or pinned DFAs; reject an
   unresolved language.
3. **Collection solver:** prove list cardinality and item maxima, fixed-map key
   order, and exact comma/bracket costs.
4. **Local field solver:** enforce intrinsic, descriptor, value, context,
   identity, and 4,096-octet field-codec constraints together.
5. **A1 solver:** maximize the three coupled fields jointly under the frozen
   activation/cardinality/order contract.
6. **Composition/certificate:** recompute every local maximum, deterministic
   identity, context contribution, array syntax, and total canonical length.

An external solver may propose states, but a repository-owned independent
checker must replay a portable certificate without trusting stored maxima.

The attainer must be separate source code. It must construct the complete
67-observation retained context, run the pinned P1 application schedule, and
measure canonical bytes. It may share frozen data authorities with the upper
solver but not executable optimization code or a precomputed maximum/witness
answer.

## 9. Tests and falsification controls

The 12 focused checks cover:

- exact manifest/proof/report identities and all closure counts;
- independent schedule and recursive type/schema reconstruction;
- independent runtime-function AST hashing;
- deterministic CLI output and empty stderr;
- standard-library-only imports;
- full enumeration versus factorized optimization on a finite micro-domain
  (16 legal tuples, exact maximum 29 in both paths);
- rejection of a missing A1 edge;
- rejection of an extra cross-field edge;
- rejection of an operator read-contract weakening;
- rejection of an unconditional field-independence claim;
- rejection of a premature exact-maximum claim; and
- rejection of runtime-source drift.

Any unknown rule, operator, schema, field, fixed authority, dependency edge,
deterministic projection, or source drift remains fail closed.

## 10. Nonclaims

This packet does not derive the exact case-435 maximum, accept the exploratory
257,887-byte candidate, construct an independent legal attainer, modify the
accepted seed/manifest/boundary/target/verifier/producer/runner, resume
`A4-P6-V`, qualify the six-case pilot, close all 475 maximum cases, complete
Raw V8 Step 2, exit Stage 1, establish predictive edge, prove trading safety,
or claim profitability.

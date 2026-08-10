# Raw V8 Step-2 V2 case-435 independent-attainer acceptance

**Date:** 2026-08-10  
**Sub-gate:** `A4-P6-C435-C2`  
**Decision:** `ACCEPTED`  
**Next bounded sub-gate:** `A4-P6-C435-C3`  
**Stage 1:** `NO-GO`  
**Verifier expansion:** `HOLD`

## 1. Decision

`A4-P6-C435-C2` is accepted. A separate constructor, which imports neither C1
program nor any precomputed bound or witness, constructs a complete case-435
retained context and obtains a P1-legal measured observation of:

```text
257,887 canonical octets
```

The C2 attainment certificate has identity:

```text
1d801ba5b81a5e5ed27adfba2ff718fa24a7bd27e3cbf87ce5b603f653502dba
```

This accepts only the attainment channel. It does **not** claim exactness and
does not consume the C1 upper certificate. The certificate freezes
`exactness_claimed = false`; only `A4-P6-C435-C3` may compare the two frozen
channels and accept equality.

## 2. Accepted artifacts

| Artifact | Role | Bytes | SHA-256 |
|---|---|---:|---|
| `scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py` | independent longest-first retained-witness constructor and P1 executor | 55,880 | `ff0ca26e259f7ecbec8e2dde76eb6a4c6ec5974629ab5fc536f2d05b74e73f11` |
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py` | separately implemented certificate, identity, lifecycle, and P1 replay verifier | 31,130 | `fb89bd4d242f38e49d43ac06648b67415f7ed6c16007107d8454a6f7dfad4058` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py` | positive, independence, causal-shape, and hostile-mutation suite | 8,178 | `ed9aec8b9f4c7f347535d9e73552eef0cb8071152f860388a7a86b8d85ebdec7` |

The JSON certificate is a reproducible output, not a new checked-in authority.
The verifier consumes the complete retained witness and recomputes all relevant
identities, canonical bytes, schedule receipts, and work totals from pinned raw
sources.

## 3. Frozen authority and independence boundary

Both programs fail closed on the same seven raw authorities accepted by
`C435-B` and C1:

```text
d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c
```

| Authority | SHA-256 |
|---|---|
| V2 seed catalog | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Raw V8 Step-2 inventory | `de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b` |
| structural registry | `9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3` |
| literal authority | `aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2` |
| application ledger | `979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282` |
| accepted rule runtime | `47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22` |
| accepted dependency analyzer | `f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30` |

The constructor shares those problem authorities because an independent
attainer must solve the same frozen problem. It does not read the C1 solver,
C1 verifier, C1 certificate ID, C1 result, or C1 witness identity. Static tests
reject any such import or embedded result. The accepted rule runtime is used
only after local candidate selection, as the frozen P1 execution authority; it
is not queried to rank or optimize candidate values.

The checker imports neither constructor nor C1. It independently reads and
validates the complete certificate, recomputes all nested semantic identities,
reconstructs lifecycle joins, and re-executes P1.

## 4. Construction method and alternatives

Three approaches were considered:

1. copy the C1 maximizing witness;
2. let the accepted runtime search or prune the candidate domain;
3. derive bounded endpoint/status/method/reason/error candidates from the raw
   schemas, apply a local context-legality predicate and exhaustive A1 tuple
   relation, select deterministically, then ask the runtime only to execute the
   completed witness.

The first is circular and was rejected. The second weakens implementation
independence because the final legality oracle would also choose the witness.
The third was selected: construction and execution remain separate, all search
domains are closed by frozen authority, and the full accepted rule schedule is
still the final legality test.

The full replay caught and corrected an important integration defect during
development. OFF-mode outer fixtures cannot be rebound directly to the ON-mode
case-435 root because their field states remain
`INSTRUMENTATION_DISABLED`. C2 instead derives legal BEFORE, AFTER, and
AGGREGATE field envelopes for their actual roles, clears checkpoint-only
coordinates, and reseals every context, field, observation, and root identity.

No external literature search was necessary for this sub-gate. It is a finite,
repository-defined formal construction problem; external finance research does
not determine whether these exact frozen bytes satisfy the accepted protocol.

## 5. Reconstructed witness and P1 evidence

The retained sequence is exactly:

```text
1 BEFORE_OPERATION
+ 63 TARGET_BOUNDARY_NOT_REACHED checkpoint placeholders
+ 1 exact checkpoint at measured sequence ordinal 64
+ 1 AFTER_OPERATION
+ 1 OPERATION_AGGREGATE
= 67 observations
```

The measured observation is at one-based sequence position 65. Its identity is
`86f29eb6706b58d33db45d3a035e1f4b5bd78e50ba1347355d15d380e5856be9`
and its canonical SHA-256 is
`f29bb04a79ff2c1ecff867224f70ae7b45c0d7d9c94960a6c81652d6b7b74bad`.
The full retained root has ID
`65bc6b241b3ad861443401d3b101ad0b6eab9108a4653cdeef86b6f8a03e9147`
and canonical SHA-256
`aa682944ac87cdd7e4180347d285145a4b4d231a2246a3246a184ae4757a655d`.

The constructor derives:

| Quantity | Result |
|---|---:|
| measured legal field proposals | 3,144 |
| A1 Cartesian tuples | 10,164 |
| legal A1 tuples | 9,989 |
| BEFORE field proposals | 1,734 |
| AFTER field proposals | 2,022 |
| AGGREGATE field proposals | 1,776 |
| measured field canonical-octet sum | 255,532 |

The complete P1 execution is:

| Application segment | Invocations |
|---|---:|
| selector/marker contract | 1 |
| observation/aggregate registry | 67 |
| observation fields/registry | 67 |
| root/observation membership | 1 |
| root/selector lifecycle | 1 |
| **total** | **137** |

Both implementations derive 12,531 charged and completed rule evaluations,
125,431 direct expression nodes, and receipt-vector SHA-256
`71e39e33ccf923fb922d73336a4afba96051b741d1da5b3fc16af0b0cb95c44b`.
Every application accepts.

## 6. Falsification evidence

The dedicated suite passes 17 tests in 381.69 seconds. It performs one fresh
construction and one independent full-runtime replay, then rejects resealed
challengers before expensive replay where possible. Covered attacks include:

- extra certificate members;
- substituted raw-authority hashes;
- a false claim that the C1 bound was imported;
- premature exactness;
- changed measured size;
- changed selected-field measurement;
- omitted retained observations;
- substituted outer roles;
- changed schedule receipt ordering/name;
- duplicate JSON members; and
- an unsealed successor mutation.

It also freezes the full causal role sequence, 64-entry selector binding,
185-field measurement vector, C2 certificate identity, and static isolation
from C1 source paths and result literals.

The direct acceptance commands are:

```bash
python scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_case435_attainer_v49f.py \
  > /tmp/case435-c2-certificate.json

python scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py \
  . /tmp/case435-c2-certificate.json

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_case435_attainer_certificate_v49f.py
```

## 7. Nonclaims and successor contract

C2 proves that a P1-legal 257,887-octet retained witness exists under the
pinned case-435 authority. It does not, by itself, prove that no larger legal
witness exists. It does not authorize the pilot runner, seed/catalog changes,
Stage 2, paper trading, live trading, or any profitability claim.

`A4-P6-C435-C3` must be a small, separate equality-join implementation. It may
read only the frozen C1 upper certificate and C2 attainer certificate plus the
minimum shared authority binding. It must reject different case, profile,
scope, source, schedule, canonicalization, target type, measured ordinal, or
octet values. Exactness is accepted only if the C1 upper value equals the C2
measured legal-attainer value. Until that join passes, case 435 and Stage 1
remain `NO-GO`, and `A4-P6-V` remains on hold.

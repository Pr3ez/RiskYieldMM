# Raw V8 Step-2 V2 intrinsic dual-source freeze acceptance

**Date:** 2026-08-11  
**Sub-gate:** `A4-R475-V1-C2-S`  
**Decision:** `ACCEPTED`  
**Next bounded packet:** `A4-R475-V1-C2-U`  
**Stage 1:** `NO-GO`

## Decision

`A4-R475-V1-C2-S` is accepted as a pre-execution independence seal only.
Both complete channel source files and both closed output schemas were sealed
in one semantic manifest before either channel produced an official result.
The five future result paths remain absent and the independent reviewer
reports zero channel executions.

The accepted freeze identity is:

```text
d6e17e638a99449bc806b72cfefb850d6f64ed578dc5314a135b8e71fe5b008e
```

The independent acceptance-report identity is:

```text
18dcb2b97a13cb0a8912ad3bc152cb0e388740d386207fbad38dbbd19bef7ec5
```

This packet does not establish that either frozen implementation will
succeed. `C2-U` must execute and independently verify the legal-domain proof;
`C2-A` must later construct and replay P1 for all 66 witnesses. Any source or
schema correction now requires a new versioned `C2-S` and invalidates every
descendant output from this freeze.

## Why source freezing precedes execution

The C1 alternatives were reconsidered against the complete predecessor and
successor chain:

| Alternative | Failure mode | Decision |
|---|---|---|
| Freeze only CLI names and schemas | Either implementation can still change after observing the other channel | Rejected |
| One implementation with two modes | A shared defect can manufacture matching values | Rejected |
| Run U, then write A with an import ban | Human-level adaptation remains possible even if imports are absent | Rejected |
| Freeze both complete sources and both schemas, then run U and A in order | Later observations cannot change the already sealed opposite implementation | Selected |
| Execute either source during C2-S as a smoke test | Reveals a result before the joint seal and weakens the pre-execution claim | Rejected |

The attainer is allowed to compile and execute exactly one already accepted,
byte-pinned rule-runtime source, and only after local candidate construction.
That runtime performs final P1 validation; it is not allowed to search, rank,
or optimize candidates. The upper source neither loads that runtime nor any
project implementation. Neither source contains the opposite source or
result path.

No external literature search was used for this decision. This is a finite,
repository-defined source-independence and byte-authority problem. The primary
evidence is the accepted C1 contract, registry, rule authority, runtime, F0
limits, and canonical identity rules; external quantitative-finance research
cannot redefine those local bytes.

## Frozen source and schema identities

| Artifact | Bytes | SHA-256 / semantic ID |
|---|---:|---|
| standalone legal-upper source | 24,421 | `5ef8441d5ddb14642d2a90f688e5f0cf9e49384a18eb9c91b48e293eab526e8a` |
| standalone P1-attainer source | 34,062 | `971cac97399c839917a6d87e6726be8547d54e45af9687f2ac85b3d4b6b6e448` |
| upper output schema | 3,957 | SHA `ea4cab7e…`; schema ID `7e2af5b6…` |
| attainer output/shard schema | 5,863 | SHA `8b3f6be2…`; schema ID `20aa310f…` |
| source-freeze manifest | 9,861 | `57891c14624ed999e1b370a2478e41c99b23c6d0c471d9493c71c8381c40e3c5` |
| independent acceptance report | 2,268 | `62336198ed588159233d5637c44e04b8cbae464a7eb8cc87b574e89f76264c9a` |

Both sources cover the exact 11 derivation kinds present in C1. Their core AST
fingerprints are different:

```text
LEGAL_UPPER       4b2fb1d5463c2d8aa6174652b3e35d6866bb4bb94a0eb046d355f232e3f87f4b
P1_LEGAL_ATTAINER eaf7e544610c0ccf333b75f44c1dea1533fb523f73631f3932a69cf32a830586
```

The upper schema cannot carry witness bytes or attainer records. The attainer
schema cannot carry an upper record. Both root and per-case records reject
unknown members, freeze `exactness_claimed = false`, and bind their own source,
schema, C1, and C2-S identities.

## Transport and F0 design

The attainer transport was dimensioned before observing any channel result.
The 66 witnesses are assigned to three fixed 22-case shards. At the frozen
per-case ceiling, each shard has at most:

```text
22 × 524,288 = 11,534,336 witness-payload octets
```

Each shard therefore remains below the immutable 16,777,216-octet individual
file limit. The projected five-file result surface is 38,994,304 octets. The
source-freeze pinned-input projection is 7,969,945 octets in nine files,
strictly below the immutable 67,108,864-octet and 64-file limits.

The attainer transaction constructs and fsyncs three shards plus one root,
links shards first and the root last, and rolls back every published path on a
failure. The upper uses an absent-path exclusive publication. C2-S itself
publishes none of those paths.

## Pre-acceptance corrections

Static inspection of the actual 66-case language exposed two defects in the
first candidate source design:

1. `RAW_CANONICAL_JSON_STRING` has no leaf-local maximum; treating its nullable
   metadata as a numeric maximum would reject valid authority.
2. Some arrays permit 524,288 items; materializing the declared cardinality
   before applying the canonical-byte ceiling could consume excessive memory
   and could never be repaired by a one-item-at-a-time shrink loop.

The source was corrected before sealing. Raw strings now use the protocol
ceiling as a provisional construction budget, arrays derive a byte-fit
cardinality before allocation, finite item domains cap distinctness, and
oversized composites are reduced before reference synchronization and identity
resealing. This is source-design evidence only, not proof of P1 acceptance.

## Independent review and hostile tests

The independent reviewer imports neither generator nor channel source. It
reconstructs:

- four raw authorities totaling 7,639,498 octets;
- both source paths, raw hashes, exact import surfaces, source markers, and
  complete derivation-kind sets;
- two distinct core AST fingerprints;
- both output-schema semantic identities and closed root-member sets;
- five absent official output paths;
- the source-freeze semantic identity;
- exact input/output F0 projections; and
- the nonclaim and successor pointer.

The focused suite reports:

```text
16 passed in 0.68s
```

It rejects forbidden imports, missing source markers, placeholder code, stale
schema identities after relaxation, source changes, correlated core identity,
case-specific answer branches, source/result path crossover, resource
overclaims, and coherently resealed acceptance overclaims. Two independent
reviewer processes reproduce the checked-in report byte for byte.

## Accepted artifacts

- `scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py`
- `scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers_v49f.py`
- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_result_schema_v49f.json`
- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_result_schema_v49f.json`
- `scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.py`
- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.json`
- `scripts/tests/review_raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.py`
- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_acceptance_report_v49f.json`
- `tests/test_raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.py`

## Successor contract and nonclaims

`A4-R475-V1-C2-U` is now the only executable packet. It may execute only the
frozen legal-upper source and must independently verify all 66 proof records,
their dependency transcripts, method coverage, authority identities, and F0
usage. It must not execute or inspect the attainer source beyond the already
accepted C2-S hash, and it must not edit either source or schema.

C2-S accepts no upper, no witness, no exact maximum, no verifier expansion, no
producer, no campaign, and no Stage-1 completion. It makes no claim about
completed-bar authority, predictive edge, backtest performance, paper/live
readiness, trading safety, or profitability.

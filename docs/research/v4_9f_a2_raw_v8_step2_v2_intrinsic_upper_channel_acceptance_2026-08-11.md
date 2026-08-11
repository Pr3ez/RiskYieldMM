# Raw V8 Step-2 V2 intrinsic legal-upper channel acceptance

**Date:** 2026-08-11  
**Sub-gate:** `A4-R475-V1-C2-U`  
**Decision:** `ACCEPTED_LEGAL_DOMAIN_UPPER_CHANNEL_ONLY`  
**Next bounded packet:** `A4-R475-V1-C2-A`  
**Formal Stage 1 state:** `NO-GO`

## Decision

`A4-R475-V1-C2-U` is accepted as one proved legal-domain superset bound for
each of the 66 intrinsic-template cases. The frozen upper source published one
65,167-octet result atomically. A separately written reviewer reconstructed all
66 records, all 1,647 proof steps, every transcript identity, and the complete
six-method case census without importing the upper solver.

The accepted result identity is:

```text
b57d8d494524ce964330fa2046c4d66f0c8a854b7eaa8fe1abae3bb09e5f8d2d
```

The independent acceptance-report identity is:

```text
07ee9289eec657ff4907e00720fe29d449a6087b6ee5d4728a027fd8f5422123
```

This is not an exact-maximum acceptance. Nine cases still have the protocol
ceiling, 524,288 octets, as their legal-domain upper. Even a smaller proved
upper is not an attained maximum. `C2-A` must independently construct and run
P1 over one legal witness per case; `C3` may accept exactness only where all 66
attainer lengths equal these already sealed upper values under the same C1 and
C2-S identities.

## Why this execution and review sequence was selected

The alternatives were reconsidered before observing the result:

| Alternative | Failure mode | Decision |
|---|---|---|
| Execute first, then design checks around the values | Review can accidentally become answer-shaped | Rejected |
| Copy allowed inputs into a mini-repository, execute there, then promote the result | Strong path isolation, but adds a second non-frozen publisher and weakens the accepted source's exclusive publication contract | Rejected for the official run; retained for independent replay |
| Execute the frozen source directly without file-access evidence | Preserves publication identity but leaves only static evidence for the channel boundary | Rejected |
| Prewrite a distinct recursive/reverse-DP reviewer, establish an expected-red missing-output boundary, then execute the authoritative source once under a syscall trace | Preserves the frozen publisher, prevents answer-shaped review, and records the actual read surface | Selected |

Before execution, the new suite reported exactly:

```text
1 failed, 2 passed, 22 skipped
```

The one failure named only the absent official result and acceptance report.
The two executable checks proved source/reviewer separation. Result-dependent
semantic checks remained skipped until publication. The reviewer source was
not changed after the result was observed.

No external literature search was used. This is a finite, byte-pinned protocol
and filesystem-isolation question. The controlling evidence is the accepted
C1 dependency contract, C2-S source/schema seal, structural registry,
canonical identity rules, and immutable F0 limits; external finance research
cannot redefine those repository authorities.

## Authoritative execution

The source identity was rechecked immediately before execution:

```text
5ef8441d5ddb14642d2a90f688e5f0cf9e49384a18eb9c91b48e293eab526e8a
```

Both the official result and its exclusive temporary path were absent. The
source then ran once under a deterministic minimal environment with
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED=0`, `LC_ALL=C.UTF-8`, and `TZ=UTC`.
`strace -f -qq -e trace=%file` captured the file-access boundary while the
source retained ownership of its accepted absent-path exclusive
temp/fsync/link/unlink/fsync publication.

The trace contained only repository directory lookups plus these files:

- the frozen upper source;
- the C1 correction contract;
- the structural registry;
- the upper result schema;
- the C2-S freeze manifest;
- the exclusive upper temporary path; and
- the final upper result path.

There were zero trace matches for the attainer source, attainer root, or any
attainer witness shard. The process exited zero without stdout/stderr, the
temporary path was absent afterward, and the final path was a regular
non-symlink mode-`0600` file.

The result bytes are:

| Property | Value |
|---|---:|
| raw octets | 65,167 |
| SHA-256 | `29f9e1f760ae9ebd71a8a5731bb0767ca36cf6b47b2539e43876c63e816d2790` |
| semantic result ID | `b57d8d494524ce964330fa2046c4d66f0c8a854b7eaa8fe1abae3bb09e5f8d2d` |
| case records | 66 |
| proof steps | 1,647 |
| attainer-read true rows | 0 |
| exactness claimed | false |

## Independent reconstruction

The reviewer imports neither channel source. It reads the official result only
when the caller does not provide bytes, and otherwise reads exactly five
declared inputs: C1, the registry, C2-S, the upper schema, and the upper source
for static identity/isolation validation.

Its computational surface intentionally differs from the source:

- source: ordered postorder cell fold;
- reviewer: recursive memoized graph evaluation with explicit cycle and
  forward-reference rejection;
- source: forward DFA width propagation;
- reviewer: reverse exact-length recurrence from accepting states;
- both: independently recomputed finite-language, built-in, Unicode, record,
  array, nullable, union, object-reference, codec-residual, identity, and
  canonical-byte equations.

The reviewer reproduced this complete derivation census:

| Derivation kind | Steps |
|---|---:|
| `ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH` | 91 |
| `CODEC_INTERSECTION` | 160 |
| `EXACT_BOOLEAN` | 25 |
| `NULLABLE_BRANCH` | 145 |
| `OBJECT_REFERENCE` | 47 |
| `RECORD_MEMBER_FOLD` | 138 |
| `SAFE_INTEGER_BAND` | 247 |
| `TAGGED_UNION_BRANCH` | 22 |
| `TEXT_BOUNDED_LANGUAGE` | 183 |
| `TEXT_BUILTIN_BOUNDED` | 254 |
| `TEXT_FINITE` | 335 |

The independently derived method-to-case census is:

| Proof method | Cases |
|---|---:|
| `ASCII_DFA_DYNAMIC_PROGRAMMING` | 21 |
| `CLOSED_BUILTIN_FORMULA` | 51 |
| `CODEC_INTERSECTION` | 66 |
| `FINITE_ENUMERATION` | 58 |
| `PINNED_UNICODE_PROFILE_PROGRAM` | 18 |
| `RULE_AWARE_COMPOSITION` | 66 |

The 66-value upper vector has SHA-256
`0791b5d5b97249ba4fac3b187efbe66a5cb85ba7c8ca3839279831fe25e540f5`.
Fifty-seven cases are below the 524,288-octet protocol ceiling and nine equal
it. The minimum is 29 octets. Case 8 independently reproduces the prior exact
positive control at 928 octets; this agreement validates the corrected
language-aware path but does not transfer case-8 exactness to any other row.

## Hostile and reproducibility evidence

The final focused suite reports:

```text
25 passed in 2.83s
```

It includes:

- exact result and report identity reconstruction;
- exact reviewer read-surface instrumentation;
- producer/reviewer algorithm-surface separation;
- byte-identical double reviewer CLI replay;
- a fresh source execution in a temporary repository containing only the five
  allowed inputs, observed under `strace`, which reproduced the official result
  byte for byte and contained no attainer file;
- 14 coherently re-signed attacks over bounds, transcripts, methods, source and
  schema identities, row order, unknown members, state, packet, next pointer,
  attainer consumption, and exactness; and
- noncanonical and duplicate-member JSON rejection.

## F0 and transport

The actual upper execution used five pinned input files totaling 6,944,168
octets. This is below the immutable 64-file and 67,108,864-octet F0 limits. The
65,167-octet output is below both its predeclared 2,097,152-octet projection and
the immutable 16,777,216-octet individual-file limit. The limits were fixed by
C2-S before either channel result existed.

## Accepted artifacts

- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_result_v49f.json`
- `scripts/tests/review_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_v49f.py`
- `scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_acceptance_report_v49f.json`
- `tests/test_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_v49f.py`
- this acceptance document

The frozen upper source, upper schema, C1 contract, registry, and C2-S manifest
are consumed authorities, not artifacts newly accepted by C2-U.

## Successor contract and nonclaims

`A4-R475-V1-C2-A` is now the only executable packet. It may execute only the
already frozen attainer source. It must not read the upper source or the C2-U
result. It must independently construct, P1-validate, measure, shard, and
publish one legal witness per case under the C2-S transaction contract.

C2-U accepts no witness, no P1 success, no equality join, no exact maximum, no
authority delta, no verifier expansion, no producer, no campaign, and no
Stage-1 completion. It makes no claim about completed-bar authority,
predictive edge, backtest performance, paper/live readiness, trading safety,
or profitability.

# Raw V8 Step-2 V2 intrinsic correction contract acceptance

**Date:** 2026-08-11
**Gate:** `S1-A4 / A4-R475-V1-C`
**Accepted packets:** `A4-R475-V1-C1` and `A4-R475-V1-C1-A`
**Decision:** `ACCEPTED — CONTRACT AND DEPENDENCY INTERFACE ONLY`
**Next bounded packet:** `A4-R475-V1-C2-S`
**Stage 1:** `NO-GO`

## Executive decision

Accept the complete 66-case dependency census and the versioned correction
interface. Do not claim that any of the 66 maxima is accepted and do not edit
the accepted seed, all-case contract, V0 verifier, six-case producer,
six-case verifier, or six-case runner.

The contract closes the ambiguity exposed by `A4-R475-V1-F-A`: every frozen
intrinsic template is now represented by a closed postorder step program and
an explicit dependency surface covering value schemas, text languages, ASCII
DFAs, Unicode identifier profiles and sources, intrinsic rules, type
descriptors, identity contracts, arrays, tagged unions, and codec-coordinate
intersections. The 26 contradicted cases remain contradicted and the other 40
remain unresolved; no non-falsified case is promoted to attainable.

The next step is not upper-bound execution. `A4-R475-V1-C2-S` must first seal
the mutually independent upper-channel and attainer-channel sources and their
output schemas before either source is executed. This prevents code or human
adaptation to the other channel's observed output.

## Why C1 was required

The frozen templates contain enough structural information to calculate a P2
superset, but their relaxation records deliberately discard predicates. The
accepted falsification proves that some resulting endpoints are not in the
legal language. A corrected exactness system therefore needs an authority
that answers four questions before implementation:

1. Which dependencies can constrain each case?
2. Which exact source record and position owns each dependency?
3. Which code channel may consume the dependency and for what claim?
4. What identity and equality rule authorizes a corrected endpoint?

Without this contract, an upper implementation could silently omit a text
language or rule, an attainer could be designed after observing the bound, or
the verifier could choose a corrected endpoint itself. All three would weaken
the separation between authority, proof, implementation, and acceptance.

## Frozen authority boundary

The C1 generator reads eight pinned files. It imports no analyzer, runtime,
verifier, producer, runner, or seed generator.

| Authority | Purpose |
|---|---|
| Corrected V2 seed | 66 template and plan programs |
| Structural registry | schemas, languages, DFAs, Unicode profiles, rules, descriptors, identities, and codecs |
| Accepted all-case contract | ordered case ledger and campaign policy |
| Accepted V1-F-A report | immutable 26-case contradiction vector and nonclaim |
| Foundation-only V0 verifier | predecessor resolver/candidate-access boundary |
| Six-case producer | byte-exact predecessor regression authority |
| Six-case verifier | byte-exact predecessor regression authority |
| Six-case runner | byte-exact predecessor regression authority |

The pinned input is `15,869,888` bytes across 8 files, below the immutable
`67,108,864`-byte and 64-file F0 ceilings. The generated contract is
`5,436,266` bytes, below the immutable `16,777,216`-byte individual-file
ceiling. No limit was selected or changed after observing an answer.

## Complete dependency census

The contract freezes 66 ordered case records, 1,647 postorder step records,
and 1,806 per-case unique dependency records.

### Step programs

| Derivation kind | Count |
|---|---:|
| `TEXT_FINITE` | 335 |
| `TEXT_BUILTIN_BOUNDED` | 254 |
| `SAFE_INTEGER_BAND` | 247 |
| `TEXT_BOUNDED_LANGUAGE` | 183 |
| `CODEC_INTERSECTION` | 160 |
| `NULLABLE_BRANCH` | 145 |
| `RECORD_MEMBER_FOLD` | 138 |
| `ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH` | 91 |
| `OBJECT_REFERENCE` | 47 |
| `EXACT_BOOLEAN` | 25 |
| `TAGGED_UNION_BRANCH` | 22 |

### Per-case unique dependency records

| Dependency kind | Count |
|---|---:|
| `VALUE_SCHEMA` | 676 |
| `TEXT_LANGUAGE` | 404 |
| `TYPE_DESCRIPTOR` | 163 |
| `CODEC_COORDINATE_SET` | 160 |
| `UNICODE_SOURCE` | 108 |
| `ARRAY_BATCH` | 91 |
| `INTRINSIC_RULE` | 87 |
| `IDENTITY_CONTRACT` | 37 |
| `ASCII_DFA` | 35 |
| `UNICODE_IDENTIFIER_PROFILE` | 23 |
| `UNION_BRANCH` | 22 |

Counts are per-case unique records, not global unique authorities or raw
occurrences. For example, multiple identifier profiles within one case share
the same six pinned Unicode source records, so the source closure is not
artificially multiplied.

Case-vector SHA-256:
`d0e9a0a0ae157e598da1dc8130e30bca6189966d4eadc853eb8a1a0db1f9300b`.

## Correction-state semantics

Each case has exactly one of two states:

- `FROZEN_P2_ENDPOINT_CONTRADICTED` for the accepted 26-case vector;
- `EXACTNESS_UNRESOLVED_NOT_ACCEPTED` for the remaining 40 cases.

The second state is deliberately not called viable, attainable, or exact.
The V1-F-A method was a falsifier, not a complete optimizer. C2 must provide
separate upper and attainer evidence for all 66 cases, including case 8 whose
928-byte exact result is already known independently.

## Selected dual-channel architecture

The accepted successor order is:

1. `A4-R475-V1-C2-S` — freeze both channel sources and output schemas before
   any channel output exists;
2. `A4-R475-V1-C2-U` — execute the proof-carrying legal-upper channel for all
   66 cases;
3. `A4-R475-V1-C2-A` — execute the separately implemented full-P1 legal
   attainer channel for all 66 cases;
4. `A4-R475-V1-C3` — require exact problem-authority identity and equality of
   upper octets with independently measured attainer octets, then publish a
   versioned authority delta;
5. `A4-R475-V1` — extend the verifier against the accepted corrected
   authority, while preserving the V0 and six-case boundaries.

`C2-S` is a pre-execution independence seal. Both project sources and both
output schemas must be pinned before either channel runs. Each source must be
statically barred from importing, reading, or invoking the other source or
its outputs. Standard-library primitives and the same byte-pinned C1/schema
authorities may be used, but no shared project implementation may perform the
core optimization or witness construction for both channels.

The upper channel must prove that its result contains the full legal P1
domain. Its permitted method families are finite enumeration, closed
built-in formulas, ASCII-DFA dynamic programming, a pinned Unicode-profile
program, rule-aware composition, and codec intersection. Ambient relaxed-text
cells are forbidden.

The attainer channel must construct and fully validate one canonical P1-legal
witness for every case. It may not read an upper artifact or use an upper
endpoint as a construction target. C3 accepts exactness only when the two
independently identified channels bind the same problem authority and the
measured lengths are equal. Missing, unequal, or unresolved evidence remains
`NO-GO`.

## Alternatives evaluated

| Alternative | Assessment | Decision |
|---|---|---|
| Keep only the 26 contradiction rows | Does not close dependencies or prove the other 40 cases | Rejected |
| Store only dependency IDs and reread arbitrary live plan fields in C2 | Compact, but permits unsealed dependency drift and hidden omissions | Rejected |
| Copy the complete registry into every case | Self-contained but multiplies multi-megabyte authority data without adding identity strength | Rejected |
| Freeze normalized step programs plus exact source positions and canonical record hashes | Complete enough for independent reconstruction while retaining one pinned registry authority | Selected |
| Use one implementation in an “upper” and “attainer” mode | Correlated implementation defects could manufacture equality | Rejected |
| Run U then write A with only an import prohibition | Code can still be designed after observing U; human-level adaptation remains possible | Rejected |
| Freeze U and A sources and schemas before executing either | Makes later outputs unable to influence the already sealed opposite implementation | Selected |
| Edit the accepted seed/templates in place | Invalidates predecessor identities and accepted evidence | Rejected |

No external research was needed to choose between these alternatives. The
governing primary evidence is the repository's byte-pinned schema, plans,
contract equality rule, and accepted falsification. External literature
cannot redefine those local language or identity authorities.

## Independent acceptance

The independent reviewer does not import the generator. It reconstructs all
66 cases, all 1,647 steps, every one of the 1,806 dependency records, every
step/case semantic identity, the aggregate censuses, the 26/40 disposition,
the dual-channel boundary, F0 usage, and the successor order. It also runs the
generator's public check-mode CLI twice and requires identical successful,
silent results.

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| C1 generator | `38,248` | `b9db5b3b84c26ad20764d7e8bea0fc8aef19209c6d177c15356311068fc2ec8f` |
| C1 contract | `5,436,266` | `6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14` |
| C1 semantic tests | `12,744` | `b238a5b2d50d708c55ccf5ef9c512853a3ab0deca87c8e4a0a1c8c84ea657e2b` |
| Independent reviewer | `29,264` | `eae58edadedea7606af692b5d192245a2286137617f7e77545069d6748023303` |
| Acceptance report | `1,931` | `061d53c69b003cf528d596c1b736fbae58f23da071055fb7d8f321617f0f2303` |
| Acceptance tests | `7,639` | `2234e21d8b2ecb73b1ebfd9872fb6e455a80e3af1a48a53389c1fdd482b5fc7e` |

Contract ID:
`171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9`.

Acceptance report ID:
`e3cdc9ea250f3b3b296aeb02fc9a51f0aa615655ec8ee37c77a319855907dc84`.

The focused C1 generator/reviewer matrix is `22 passed`. Together with the
accepted V1-F-A analyzer/reviewer matrix, the combined correction matrix is
`45 passed` before adjacent predecessor regressions.

## Nonclaims and current pointer

C1 does not accept an upper certificate, an attainer, an exact maximum, a
successor authority delta, V1 verifier coverage, a producer, a runner, a
campaign, Stage 1, profitability, safety, or live readiness.

The sole mutable execution pointer is now `A4-R475-V1-C2-S`. Formal Stage 1
remains `NO-GO`.

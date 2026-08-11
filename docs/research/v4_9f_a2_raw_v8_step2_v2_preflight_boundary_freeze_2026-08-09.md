# Raw V8 Step-2 V2 dual-preflight boundary freeze

Date: 2026-08-09  
Status: **REFROZEN AND ACCEPTED S1-A2 SHARED DATA BOUNDARY**

> Refreeze notice: the S1-A2-A dry run exposed missing per-emission token
> metadata in the accepted seed. The
> [`event-metadata amendment`](v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md)
> corrected S1-A1. This document now carries the amended seed and contract
> identities; no expected result vector was introduced.

## 1. Decision

S1-A2 will use one small, identity-bound data contract shared by the two
preflights and their comparator. It contains no executable helper and no
expected 475-case answer vector.

The physical contract is:

```text
scripts/tests/raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.json
```

It freezes exactly five boundaries before either counter is written:

1. the sole readable seed file and all required root identities;
2. the semantic result, case, metric-summary, execution-envelope, and
   comparison schemas;
3. stable failure codes and exit classes;
4. F0 resource sources, process isolation, telemetry, and atomic output; and
5. source/import separation between A, B, and the comparator.

This is the smallest shared surface that makes disagreement interpretable.
Cell evaluation, event construction, hashing, metrics, traversal, and
aggregation remain independently implemented.

## 2. Why this boundary is required

Starting A and B before freezing the boundary caused the earlier organization
problem: each implementation could silently choose different input checks,
output fields, error handling, or resource measurements, and later comparator
work would become another semantic design phase.

Conversely, sharing an executable parser, evaluator, canonicalizer wrapper, or
metric helper would make apparent agreement circular. The selected split is:

```text
shared immutable data:
  accepted seed bytes + preflight boundary JSON

independent executable semantics:
  A iterative catalog interpreter
  B flat-ledger/prefix-sum counter

shared nonsemantic orchestration:
  comparator validates sources, launches isolated children, captures wait4
  telemetry, validates reports, and compares exact semantic bytes
```

## 3. Options reviewed

### Reuse the seed generator as a parser/evaluator — rejected

The generator already knows how it constructed the seed. Importing it would
let both preflights inherit the same mistakes and would violate the independent
consumer requirement.

### Share one Python validation/helper module — rejected

This reduces duplicate code but also creates one semantic failure point. A and
B may duplicate compact-canonical JSON and checked-integer logic; that
duplication is intentional evidence here.

### Let each implementation define its own report — rejected

Comparator normalization could conceal missing or reordered cases, type
changes, omitted metrics, and divergent failure meaning.

### Embed expected per-case counts in the contract — rejected

That would turn both preflights into answer copying. The contract includes only
input identities, schemas, policies, and caps.

### Child self-reported resource measurements — rejected

The child could omit work before/after its measurement window. The comparator
uses a parent-owned monotonic spawn-to-wait boundary and per-child Linux
`wait4` rusage. Resource telemetry is nonsemantic and cannot repair a semantic
disagreement.

## 4. Frozen input authority

The sole authorized input is the accepted S1-A1 seed:

| Field | Frozen value |
|---|---:|
| Repository path | `scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json` |
| Raw octets | 13,419,905 |
| Raw SHA-256 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Semantic catalog ID | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Verifier-owned cases | 475 |
| Maximum-row cases | 474 |

Each child must open that path exactly once with no symlink following, prove a
regular file, compare pre/post-read `fstat`, read exactly the accepted length,
require EOF, recompute the raw hash, parse strict canonical JSON, and validate
the catalog/root identities. It may not read the generator, external source
authorities, V1/pilot/producer artifacts, repository modules, or the other
implementation/result.

## 5. Frozen semantic result

Each implementation emits one atomic canonical-pretty semantic payload with:

- exact accepted input/version/root identities;
- exactly 475 ordered case results;
- the exact bound case record and logical plan ID for each case;
- exactly 18 ordered checked-UInt128 measurements per case;
- one exact derivation-event-stream SHA-256 per case;
- exactly 18 full-run metric summaries;
- one count-vector SHA-256 over case projections and summaries; and
- a separate semantic payload ID.

The boundary also freezes the semantic-payload, execution-envelope, and
comparison-payload version literals. A schema-valid report carrying any other
version is rejected.

Case positions, metric positions, member order, integer types, identities, and
status are fail-closed. The comparator requires canonical semantic payload
bytes from A and B to be identical, not merely approximately equivalent.

Execution telemetry is wrapped separately and excluded from semantic identity.
The comparison payload binds both implementation hashes, both semantic IDs,
the common count-vector digest, exact case/metric equality, resource status,
and `EXACT_AGREEMENT`.

## 6. Error and atomicity policy

The contract has 18 unique stable errors across invocation, input authority,
race/limit, canonicalization/schema/identity, arithmetic/semantic rejection,
resource enforcement, dependency isolation, output atomicity/schema, internal
fail-closed behavior, and comparator failures.

Success is exit zero with empty stdout/stderr and exactly one valid output.
Failure publishes no final output and emits one bounded single-line error. A
private temporary file is created with `O_EXCL`, written completely, fsynced,
hard-linked to the absent final name without replacement, unlinked, and the
parent directory fsynced. This uses standard `os` operations and avoids the
overwrite behavior of ordinary `rename`.

## 7. Resource and isolation policy

All 12 F0 platform caps are read from and cross-checked against the accepted
seed, including strict file/input/JSON limits and wall, CPU, RSS, temporary,
and staging ceilings.

The comparator launches each child without a shell using a fresh
`fork -> setrlimit -> execve` path, Python `-I -S -B`, a four-variable frozen
environment, a repository-root working directory, and bounded stdout/stderr
capture. It measures:

- monotonic nanoseconds from immediately before fork through `wait4` return;
- child user plus system CPU nanoseconds from that `wait4` result;
- Linux `ru_maxrss * 1024`; and
- maximum allocated `st_blocks * 512` in the private output directory.

The semantic result cannot change based on this telemetry. Any F0 excess is a
NO-GO result, not a reason to raise the cap locally.

## 8. Source independence

A, B, and the comparator have three distinct fixed paths. A and B must have
different device/inode pairs and raw hashes, may import only the exact standard-
library allowlist, and may not import local modules, dynamic import machinery,
network/process libraries, product code, tests, scripts, or one another.

Static enforcement is necessary but not sufficient. S1-A2 acceptance also
requires independent architecture review of the declared markers:

```text
A = ITERATIVE_CATALOG_INTERPRETER_V1
B = FLAT_LEDGER_PREFIX_SUM_V1
```

## 9. Frozen identity and current evidence

| Artifact | Value |
|---|---:|
| Contract semantic ID | `6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76` |
| Contract raw octets | 16,919 |
| Contract raw SHA-256 | `007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b` |
| Boundary tests | 13 passed, 0 failed |

The ID is SHA-256 over compact canonical bytes of the complete contract except
`contract_id`, under domain
`RiskYieldMMStep2PreflightExecutionContractV1V4_9F_RawV8`.

Reproduction:

```bash
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_contract_v49f.py
```

The hostile matrix rejects altered contract/seed/root identities, wrong case
or metric order, relaxed local imports, changed F0 values, self-reported RSS,
and duplicate error codes.

## 10. Dual implementation acceptance and next bounded action

A is frozen by
[`v4_9f_a2_raw_v8_step2_v2_preflight_a_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_a_acceptance_2026-08-09.md).
The independently authored flat-ledger B implementation is frozen by
[`v4_9f_a2_raw_v8_step2_v2_preflight_b_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_b_acceptance_2026-08-09.md).
Each 475-case implementation passed 6 focused tests. Their complete
1,702,217-byte semantic payloads agree exactly, including all 475 ordered case
records, all 18 metric summaries, the count-vector digest, and semantic ID.

The parent-owned comparator is accepted by
[`v4_9f_a2_raw_v8_step2_v2_preflight_comparator_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_preflight_comparator_acceptance_2026-08-09.md).
The combined S1-A2 decision is frozen by
[`v4_9f_a2_raw_v8_step2_v2_dual_preflight_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_dual_preflight_acceptance_2026-08-09.md).

## 11. Nonclaims

This boundary freeze plus the linked records accepts both independently
authored preflight sources, parent-owned comparator evidence, and direct exact
semantic agreement. It does not accept F1, final protocol V2/F2, a
constructive maximum, Raw V8 Step 2/3, A2-M, A2-E, Stage 1, offline Stage 2,
paper/live activation, predictive edge, trading safety, or profitability.

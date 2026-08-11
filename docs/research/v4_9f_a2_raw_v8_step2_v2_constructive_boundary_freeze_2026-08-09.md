# Raw V8 Step-2 V2 constructive verifier/producer boundary freeze

Date: 2026-08-09  
Gate: `S1-A4/A4-B0`  
Decision: **GO FOR THE V2-ONLY EXECUTION BOUNDARY — `A4-T` NEXT**

## 1. Accepted boundary

`A4-B0` is accepted. The machine authority is
[`raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json`](../../scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json)
under boundary ID
`bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed`.
It freezes the only permitted interface between the future separate producer,
independent verifier, and parent-owned six-case pilot runner.

The boundary consumes the accepted S1-A3 two-component authority without
editing either component:

```text
semantic component = accepted V2 seed catalog
limit/seal component = accepted finalization manifest
```

The producer may submit only candidate witness/context data or a local-shutdown
mutation. It may not submit an authoritative upper bound, derivation plan,
relaxation, certificate, resource count, objective result, or PASS decision.
The verifier reconstructs all of those values from the frozen authorities and
accepts only after independently proving P1, P2, and P3 or the complete local-
minimality theorem. The pilot runner owns process isolation and aggregation but
contains no proof semantics.

This accepts an execution contract, not either implementation or any maximum.

## 2. Legacy V1 audit and disposition

The retained
[`generate_raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.py`](../../scripts/tests/generate_raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.py)
is correctly a fail-closed historical bootstrap:

| Observation | Exact result |
|---|---|
| Raw octets | 76,224 |
| Raw SHA-256 | `450d4a64fd111ff01c58f7caad3d66112d334648577fdd320e97617a88c06f74` |
| Canonical `--check` | exit 2; rejects V1 |
| Canonical `--write` | exit 2; rejects V1 |
| Remaining executable path | reduced structural self-test under `test_output` only |
| Full frozen-scope maximum claim | none |
| V2 candidate/verifier role | prohibited |

The script pins the rejected 246,093-byte V1 protocol, uses V1 certificate and
identity domains, binds the V3 inventory, and deliberately does not execute
the accepted V2 recurrence, local transfers, or full frozen scopes. Its
structural output cannot receive pilot coverage credit. Importing it, executing
it, accepting its output, or relabelling any V1 path/tag/domain as V2 rejects.

The accepted V1 contradiction remains unchanged: row 62 requires at least
94,905 global coordinates and at least 94,906 prefix-chain nodes/depth against
immutable 65,536 caps. A new V2 producer cannot repair or reinterpret that
protocol.

## 3. Alternatives evaluated

### Adapt or subclass the V1 bootstrap — rejected

This would retain the rejected coordinate-chain semantics and blur historical
structural evidence with V2 constructive proof. It also violates the separate
V2 validator requirement.

### Let the producer emit the bound, plan, certificate, and resource report — rejected

That would make the alleged proof depend on the system being checked. A second
program comparing hashes or status fields would not independently establish
P2 or resource compliance.

### Share one recurrence/runtime helper between producer and verifier — rejected

Shared maximizing logic would turn common defects into agreement. Both roles
may read the same frozen data authorities, but they share no executable module.

### Candidate-only producer plus independent verifier and parent runner — selected

The producer supplies only data that can be rejected. The verifier derives the
complete mathematical and resource result. The parent runner freezes sources,
executes the roles through fixed isolated processes, proves candidate
immutability, enforces host limits, and publishes the pilot root last.

## 4. Two-component downstream identity mapping

The accepted compact-proof correction names a single downstream field
`maximum_protocol_sha256`, while S1-A3 intentionally uses two components. A4-B0
closes that ambiguity as follows:

```text
maximum_protocol_sha256
  = raw SHA-256 of the canonical S1-A3 finalization manifest
  = 0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0
```

This is a physical SHA-256, not a semantic ID. The manifest transitively binds
the seed, semantic/count evidence, comparison evidence, source tuple, and all
36 F2 limits. Candidate envelopes and receipts additionally carry and validate:

```text
seed_catalog_id
  = ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f

finalization_manifest_id
  = edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858
```

The proof-resource schema also requires one `resource_limit_catalog_id`. The
verifier derives it from the exact manifest records under the new closed
domain, rather than using the seed F0 catalog or accepting a producer value:

```text
F2 resource-limit catalog ID
  = 17a2258cde720b2868e9bb538fbd3d702c299a0db7d8fb5215938578d217d0fe
```

Its identity payload is exactly the catalog version, protocol version, seed
catalog ID, finalization-manifest ID, and the manifest's ordered 18 F2 records.

## 5. Producer candidate contract

One producer invocation handles one exact seed case position and creates one
closed candidate root. Its `candidate.json` binds:

```text
candidate version and canonicalization
protocol, seed, and finalization identities
case position, kind, and exact seed case binding
exact seed logical-count-plan ID
one tagged candidate payload
candidate identity
```

For cases 1–474 the payload contains only a witness record, nullable scope
context, and ordered content-addressed context-object entries. For case 475 it
contains only a proposed mutated spec and prospective result. Context objects
are separate exact compact-canonical record files; claimed IDs, paths, counts,
and hashes are untrusted inputs that the verifier recomputes.

The candidate schema explicitly forbids producer claims including:

- canonical or certified maximum length;
- upper-bound mode, safe relaxations, recurrence/plan IDs as proof, or a
  streamed derivation result;
- upper-bound/minimality certificates or resource reports;
- the winning local objective, mutation deltas, rejection coordinate, or
  verification status.

The closed candidate root is the only producer-to-verifier channel.

## 6. Independent verifier contract

The verifier processes one immutable candidate root and produces a separate
closed result root. It independently:

1. loads the seed, final manifest, and all 17 seed-bound authorities before
   opening candidate data;
2. resolves the exact case and logical plan from the seed;
3. derives the recurrence catalog, upper-bound mode, safe relaxations, state,
   cache keys, and all 18 metered resources;
4. derives the exact upper bound without a producer claim;
5. validates the retained witness/context or local mutation from raw bytes;
6. proves P1/P2/P3 or the exact local-shutdown minimality objective;
7. derives the certificate, F2-bound resource report, context closure, and
   every semantic identity; and
8. writes exactly one mathematical result plus a verification receipt.

Maximum rows retain the accepted 27-member V2 attainer schema. Case 475 retains
the accepted 21-member local-shutdown result schema. The resource report is
separate from the upper-bound certificate and does not charge its own encoding,
ID preimage, or hash. The enclosing artifact layer bounds those bytes.

## 7. Frozen replacement pilot

The replacement pilot uses six exact verifier-owned cases, not V1 mini-domains
or a componentwise synthetic row:

| Pilot | Case | Coverage |
|---:|---:|---|
| 1 | 5 | exhaustive Boolean canonical-length control |
| 2 | 24 | owner-member tagged union and owner codec |
| 3 | 54 | raw-string array cardinality, ordering, and escaping |
| 4 | 69 | exact local-shutdown outer-result application and codec |
| 5 | 435 | max64 root, full-67 context, 137 applications, safe-superset path |
| 6 | 475 | separate exact local minimality and single-mask rejection |

Each position and logical-plan ID is resolved against the accepted seed. The
selection is fixed before implementation and is not a claim that six cases
dominate the remaining 469. All six must pass; one failure makes the complete
pilot NO-GO. Two complete pilot runs must reproduce byte-identical candidate,
result, receipt, and manifest bytes.

Pilot results may be mathematically valid candidate rows, but the pilot
manifest never selects or authorizes the final 474-row publication.

## 8. Resource, filesystem, and independence enforcement

- Every case enforces all 18 manifest F2 per-case limits before its charged
  operation. The parent aggregates exactly the frozen SUM/MAXIMUM semantics and
  enforces every full-run F2 value.
- Wall, CPU, RSS, temporary storage, input/file count, parser, staging, and
  publication ceilings come only from the seed F0 catalogs. Pilot observations
  cannot raise either F0 or F2.
- Arithmetic uses checked UInt128 intermediates and safe-integer
  serialization.
- Inputs are component-opened beneath their root with no-follow/nonblocking
  semantics and must be direct regular, single-link, unique-inode files.
- Candidate and verified roots are separate, absent-before-write, root-last,
  synchronized, no-overwrite closures. Unexpected files, aliases, unstable
  sources, path escapes, noncanonical JSON, and post-link authority drift
  reject.
- The verifier and producer have distinct paths, source markers, device/inode
  identities, and hashes. They share no executable module, cannot import or
  inspect one another, cannot import production `riskyieldmm`, cannot execute
  subprocesses, and cannot use host `unicodedata` as authority.
- Only the parent pilot runner may execute the two fixed child paths. It owns
  `fork`/`setrlimit`/`execve`, `wait4` observation, watchdogs, cleanup, and
  final root publication; it contains no recurrence or legality logic.

## 9. Executable boundary evidence

The independent boundary suite is
[`test_raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.py`](../../tests/test_raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.py).
It validates the complete S1-A3 authority chain, all 17 seed authorities,
downstream field mappings, derived F2 catalog ID, closed schemas, exact pilot
positions/plans, V1 exclusion, resource/filesystem/independence policies, and
strict JSON.

It also reseals and rejects hostile mutations covering authority substitution,
wrong two-component mapping, F2→F0 substitution, producer proof claims,
missing resource reports, role/path collision, pilot duplication or plan
drift, limit tuning, shared code, production imports, symlink admission, and
legacy bootstrap reuse. Both V1 canonical modes remain fail-closed and leave
guarded paths unchanged.

Final current-tree evidence:

| Evidence | Exact result |
|---|---|
| Boundary JSON | 27,334 bytes; raw SHA-256 `05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b` |
| Independent boundary test | 30,465 bytes; raw SHA-256 `2e4ffbc6887d667582973a5e175e54bc1adcafe4e37889633e1d8b6ba0cf0d1f` |
| Boundary plus execution-control tests | 32 passed |
| Full seed/preflight/finalizer/boundary/control matrix | 212 passed in 366.80 seconds |
| Seed generator exact check | 13,419,905 bytes; seed ID `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Finalizer exact manifest check | exit 0; byte-identical regeneration |

## 10. State transition

```text
A4-B0  NEXT -> ACCEPTED
A4-T   WAITING -> NEXT
S1-A4  remains ACTIVE
Stage 1 remains NO-GO
offline Stage 2 remains BLOCKED on S1-R0
paper/live remains BLOCKED on S1-X
```

`A4-T` must now add fail-first implementation tests against this exact
boundary. They must pass hostile fixtures and fail only because the three V2
implementation paths are absent. Neither implementation may be written before
that fail-first state is observed.

## 11. Nonclaims

This boundary does not implement or accept the verifier, producer, or runner;
run the six-case pilot; prove any maximum; accept local case 475; publish the
474-row closure; complete Raw V8 Step 2/3, A2-M/A2-E, or Stage 1; unlock offline
Stage 2 or paper/live trading; establish provider behavior, predictive edge,
trading safety, or profitability.

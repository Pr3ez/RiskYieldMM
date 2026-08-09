# Raw V8 Step-2 V2 final-freeze design correction

Date: 2026-08-09  
Gate: `S1-A3`  
Decision: **REJECT LEGACY IN-PLACE PATCH; USE A TWO-COMPONENT FINAL AUTHORITY BUNDLE**

## 1. Outcome

S1-A3 cannot correctly continue by patching the 2026-08-02 candidate protocol
document. That design assumed the two preflights would later consume changed
final protocol bytes without source edits. The accepted S1-A2 implementation
has a different, stricter machine boundary:

- A and B accept exactly one seed JSON path, byte length, raw hash, semantic
  catalog ID, and contract ID;
- the shared contract declares that seed to be the sole authorized input;
- the comparator executes only that fixed seed/contract/source tuple; and
- the comparator durably publishes the closed comparison payload, while child
  semantic reports and execution envelopes remain private.

Changing the seed, contract, A, B, or comparator merely to imitate the old
patch plan would invalidate the just-accepted S1-A2 evidence. Conversely,
patching only the old Markdown would not create a machine-enforced final
authority.

The selected correction defines final V2 authority as a bundle:

```text
semantic component = the unchanged accepted S1-A1 seed catalog
limit/seal component = a new canonical finalization manifest
```

The semantic component remains the exact input challenged by A and B. The
manifest binds the accepted bytes and identities, the repeated semantic and
comparison seals, and the mechanically rounded F2 limits. A finalizer reruns
the accepted comparator plus one accepted semantic emitter, derives rather
than copies every F1 value, and proves the result fits the manifest.

## 2. Confirmed mismatch in the legacy plan

The historical candidate
[`v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_v2_freeze_2026-08-02.md`](v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_v2_freeze_2026-08-02.md)
still correctly describes the mathematical rule
`F2 = round_up(required_F1, unit)` and the requirement to rerun both
implementations. It is not a current physical authority:

- its status is `CANDIDATE — F0 DESIGN REVIEW FAILED; F1 NOT AUTHORIZED`;
- its source inventory and schemas predate the corrected 13,419,905-byte seed;
- its patch allowlist targets placeholders embedded in that Markdown;
- it expects report files that the accepted comparator deliberately keeps
  private; and
- it cannot be parsed by A, B, or the comparator.

The accepted programs prove the incompatibility directly:

| Consumer | Frozen input behavior |
|---|---|
| A | hard-pins seed path, 13,419,905 bytes, seed SHA/ID, and contract ID |
| B | independently hard-pins the same seed SHA/ID and contract ID |
| Comparator | hard-pins the contract, which names the seed as the sole input |

Therefore “patch old document, rerun unchanged consumers against the patched
document” is not executable. Treating it as complete would be documentation-
only acceptance.

## 3. Options evaluated

### Patch the historical Markdown — rejected

This would fill 36 F2 cells and source/report placeholders, but none of the
accepted executables reads that document. Its earlier review-failed status and
pre-correction source set would also remain internally contradictory.

### Add F2 members directly to the accepted seed — rejected

The seed is the accepted S1-A1/S1-A2 semantic input. Adding phase/status/F2
members changes its schema, raw hash, catalog ID, root identities, contract,
both child constants, comparator constants, and semantic payload. It converts
S1-A3 into a silent S1-A1/S1-A2 rewrite.

### Edit A and B to accept a new wrapped final file — rejected

This is implementable, but it changes both frozen source hashes and forces a
new dual-independence acceptance cycle for no counting benefit. The F2 limits
do not participate in count derivation; they constrain the accepted result.

### Check in the complete 1.7 MiB semantic payload — not selected

This is auditable but duplicates a deterministic derived artifact. The final
manifest needs the semantic raw hash, semantic ID, count-vector digest, and 18
summary values; a finalizer can reproduce them from A after the comparator has
proved A/B equality. Persisting the whole report is unnecessary unless later
operational requirements require offline inspection without execution.

### Unchanged semantic seed plus finalization manifest — selected

This preserves every accepted source and semantic identity, represents the
phase-changing F2 facts in a small closed object, and makes the old seed/final
invariance rule explicit: semantic counts are unchanged; only the limit/seal
component is new.

## 4. Minimal finalization-manifest schema

The manifest root will contain exactly these ordered logical members:

```text
finalization_manifest_version
finalization_status
canonicalization_version
protocol_version
protocol_counting_semantics_id
seed_authority
preflight_contract_authority
ordered_implementation_authorities
semantic_evidence
comparison_evidence
ordered_f2_limit_records
finalization_manifest_id
```

Required fixed literals:

```text
finalization_status = FINAL_V2_F2_FROZEN
canonicalization_version = riskyieldmm_canonical_json_v1
```

Authority records bind repository-relative path, raw octets, raw SHA-256, and
the applicable semantic ID or algorithm marker. The ordered implementation
records are A, B, then comparator; no source is represented only by a prose
link.

`semantic_evidence` binds:

```text
preflight_semantic_payload_version
raw_octets
raw_sha256
semantic_payload_id
semantic_count_vector_sha256
ordered_metric_evidence_records
```

Each metric evidence record contains position, name, aggregation,
`required_per_case`, and `required_full_run`. These values are derived from
the freshly emitted semantic payload; they are not an expected vector embedded
in finalizer source.

`comparison_evidence` binds the comparison version, raw octets, raw SHA-256,
comparison payload ID, `EXACT_AGREEMENT`, both source hashes, both semantic
IDs, the common count-vector digest, and all four exact-true acceptance flags.

The manifest ID is SHA-256 over compact-canonical JSON of every preceding
member under a new fixed domain. Unknown, missing, duplicate, reordered
semantic records, non-I-JSON values, or a noncanonical physical file reject.

## 5. Mechanically derived F2 table

For every row:

```text
f2 = ceil(required_f1 / rounding_unit) * rounding_unit
required_f1 <= f2 <= immutable_f0
```

No percentage headroom or discretionary adjustment is permitted.

| M | Required per case | Unit | F2 per case | Required full run | Unit | F2 full run |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 1 | 475 | 1 | 475 |
| 2 | 2,101,890 | 1,024 | 2,102,272 | 29,189,597 | 1,024 | 29,190,144 |
| 3 | 158 | 1,024 | 1,024 | 66,119 | 1,024 | 66,560 |
| 4 | 1,002 | 1,024 | 1,024 | 417,528 | 1,024 | 417,792 |
| 5 | 4,204,335 | 1,024 | 4,204,544 | 170,915,620 | 1,024 | 170,915,840 |
| 6 | 20 | 1,024 | 1,024 | 1,735 | 1,024 | 2,048 |
| 7 | 158 | 1,024 | 1,024 | 66,119 | 1,024 | 66,560 |
| 8 | 106,427 | 4,096 | 106,496 | 44,461,267 | 1,048,576 | 45,088,768 |
| 9 | 789,383 | 4,096 | 790,528 | 329,067,149 | 1,048,576 | 329,252,864 |
| 10 | 880,113 | 4,096 | 880,640 | 367,039,374 | 1,048,576 | 368,050,176 |
| 11 | 1,481,221 | 4,096 | 1,482,752 | 619,175,993 | 1,048,576 | 619,708,416 |
| 12 | 10 | 1,024 | 1,024 | 4,160 | 1,024 | 5,120 |
| 13 | 48,649 | 1,024 | 49,152 | 4,198,492 | 1,024 | 4,199,424 |
| 14 | 569 | 1,024 | 1,024 | 46,268 | 1,024 | 47,104 |
| 15 | 17 | 1 | 17 | 17 | 1 | 17 |
| 16 | 569 | 1 | 569 | 569 | 1 | 569 |
| 17 | 54,297 | 4,096 | 57,344 | 54,297 | 4,096 | 57,344 |
| 18 | 37,195 | 4,096 | 40,960 | 15,585,644 | 1,048,576 | 15,728,640 |

Every derived value fits its immutable seed F0 ceiling. Metric 18's full-run
F2 value equals the already frozen 15 MiB operational target and remains
strictly below the 16 MiB individual-file ceiling; this is a mechanical result,
not a tuned choice.

## 6. Finalizer execution boundary

The finalizer must not import A, B, comparator, generator, or product code. It
will use fixed-path no-shell child execution:

1. secure-read and identity-check the seed, contract, A, B, comparator, and
   checked manifest, with pre/post source snapshots;
2. run the accepted comparator in a private directory and require its exact
   closed `EXACT_AGREEMENT` result;
3. run accepted A once in a second private directory to obtain the common
   semantic payload;
4. require A's source hash, semantic ID, and count-vector digest to match the
   comparison payload and accepted S1-A2 seals;
5. derive all 18 required values from the semantic report, apply the seed's
   rounding units, and prove `F1 <= F2 <= F0`;
6. build or validate the canonical manifest;
7. remove all private child artifacts; and
8. atomically create the absent manifest on write, or compare exact bytes on
   check.

The child environment, Python isolation flags, wall/CPU/RSS/storage/diagnostic
caps, wait4 observations, watchdog, kill/reap behavior, and atomic publication
must be no weaker than the accepted comparator boundary. Execution telemetry
remains outside manifest identity.

## 7. Acceptance tests required before writing the manifest

Fail-first tests must reject:

- attempting to treat the historical review-failed Markdown as final
  machine authority;
- any changed seed, contract, A, B, comparator, semantic, or comparison seal;
- an implementation source that changes around execution;
- a copied/hard-coded 18-value vector in finalizer source instead of values
  derived from the emitted payload;
- wrong metric order/name/aggregation, wrong maximum-vs-sum projection,
  floor rounding, percentage headroom, a changed rounding unit, or F2 above F0;
- false comparison flags, differing semantic IDs/count vectors, noisy/nonzero
  children, partial output, resource excess, or leftover staging;
- wrong final status, duplicate/unknown/missing members, invalid manifest ID,
  noncanonical bytes, overwrite, symlink, or rollback failure; and
- any edit to A, B, comparator, seed, or the shared preflight contract after
  their accepted hashes are recorded.

The final acceptance run repeats the 121-test predecessor matrix, A's 6 tests,
B's 6 tests, comparator's 8 tests, the finalizer suite, generator no-drift,
Ruff/compile/diff checks, and exact manifest regeneration.

## 8. Ordered S1-A3 work

| Sub-gate | State | Exit condition |
|---|---|---|
| `A3-B0` final-bundle design correction | `SELECTED` | This document; legacy in-place patch explicitly rejected |
| `A3-T` fail-first manifest/finalizer tests | `NEXT` | Closed schema, derivation, drift, resource, atomicity, and hostile cases fail for the right reason |
| `A3-I` finalizer implementation | `WAITING` | No local imports; derives F1/F2; exact check/write; private cleanup |
| `A3-F` final manifest freeze | `WAITING` | Canonical bytes and ID frozen; no accepted predecessor changed |
| `A3-R` final rerun and acceptance | `WAITING` | Comparator/A reproduction, F2 fit, full regression, and read-only acceptance |

Only `S1-A3` is an active mutable top-level gate. These rows are its ordered
internal work, not parallel implementation gates.

## 9. Nonclaims

This design correction does not yet implement or accept the finalizer or
manifest. It does not accept S1-A3, F2, a verifier, producer, pilot,
constructive maximum, Raw V8 Step 2/3, transport-wide A2-M/A2-E, Stage 1,
offline Stage 2, paper/live trading, safety, predictive edge, or profitability.

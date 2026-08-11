# Raw V8 Step-2 V2 final-freeze acceptance

Date: 2026-08-09  
Decision: **GO FOR S1-A3 ONLY — ACTIVATE S1-A4 CONSTRUCTIVE MAXIMUM EVIDENCE**

## 1. Accepted boundary

`S1-A3` is accepted. The final V2 authority is the exact two-component bundle
selected by the
[`S1-A3 design correction`](v4_9f_a2_raw_v8_step2_v2_final_freeze_design_correction_2026-08-09.md):

1. the unchanged accepted `S1-A1` seed is the semantic component; and
2. the canonical finalization manifest is the limit/seal component.

The standalone finalizer executes the accepted comparator and preflight A from
fixed, identity-checked paths. It independently validates their closed JSON
outputs, requires exact A/B agreement, recomputes the 18 semantic summaries,
derives all 36 F2 limits from the observed F1 values and frozen rounding units,
proves every `F1 <= F2 <= F0` relation, and writes or checks the manifest using
an atomic no-overwrite boundary.

The accepted claim is deliberately narrow:

```text
for the unchanged accepted S1-A1 seed and S1-A2 execution boundary,
the identity-bound comparison and semantic evidence are reproduced,
and every final per-case/full-run F2 limit is the exact mechanical rounding
of the independently agreed F1 value within the immutable F0 ceiling
```

The committed-tree source identities of preflight A and its test differ from
the byte values printed in the original dated S1-A2 acceptance. That drift was
reconciled before finalization by the
[`S1-A2 source-identity amendment`](v4_9f_a2_raw_v8_step2_v2_preflight_source_identity_amendment_2026-08-09.md).
The current tuple reproduced the same semantic result; this acceptance uses
only the amended identities below.

## 2. Frozen authority and executable bytes

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| V2 seed catalog | 13,419,905 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| S1-A2 data contract | 16,919 | `007ed9a8d06b91f73708129b66a33eaf525e203d306426d05b8cd8bba9c7294b` |
| Preflight A | 97,254 | `fa02fcfce55e6e7b16ef90422ac079b8e34cbc1cf2c0d8422dd8b28639ec76e7` |
| Preflight B | 89,474 | `de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954` |
| Parent comparator | 52,732 | `e0527f10a4ccb18891d18b8910101066bbc01ab57eebc2e3b18338d7c6f4f793` |
| Standalone finalizer | 55,616 | `18572253070b04082502cd146d7fe0372447bcb8943fd5c27177a8e477fac4d2` |
| Finalizer tests | 34,555 | `0dae6c368b9ae89e92b8d416c9d5ec404f13cedf1976d37633827882adac63e2` |
| Finalization manifest | 15,560 | `0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0` |

The manifest is stored at mode `0600`. Its exact machine authority is
[`raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json`](../../scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json),
and its finalizer is
[`finalize_raw_v8_step2_maximum_protocol_v2_v49f.py`](../../scripts/tests/finalize_raw_v8_step2_maximum_protocol_v2_v49f.py).

## 3. Frozen semantic and comparison identities

| Authority | Identity |
|---|---|
| Seed catalog ID | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Preflight contract ID | `6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76` |
| Protocol counting-semantics ID | `34f6c285e1ce5c2b0496a63f6eda3ee15f72d6268f5ba9dbb0748e01e61d38fb` |
| Semantic payload raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081` |
| Semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b` |
| Semantic count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8` |
| Comparison payload raw SHA-256 | `44e1572ea8a9bfd19a876e80dcb027a503f9e720389a2671d02c37bc740f9b43` |
| Comparison payload ID | `8fca05661cbf728468b442466f613b7840b9c462cb2fd55302d34569fe243256` |
| Finalization manifest ID | `edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858` |

The semantic payload remains 1,702,217 canonical bytes and the comparison
payload remains 1,206 canonical bytes. All 475 case records, all 18 metric
summaries, the complete semantic bytes, and all resource-acceptance flags are
equal/true.

## 4. Final mechanically derived F2 limits

No limit was tuned after observing the result. For every row, the finalizer
uses the rounding unit already frozen by the seed:

```text
F2 = ceil(F1 / rounding_unit) * rounding_unit
F1 <= F2 <= F0
```

| M | Required per case F1 | Per-case F2 | Required full-run F1 | Full-run F2 |
|---:|---:|---:|---:|---:|
| 1 | 1 | 1 | 475 | 475 |
| 2 | 2,101,890 | 2,102,272 | 29,189,597 | 29,190,144 |
| 3 | 158 | 1,024 | 66,119 | 66,560 |
| 4 | 1,002 | 1,024 | 417,528 | 417,792 |
| 5 | 4,204,335 | 4,204,544 | 170,915,620 | 170,915,840 |
| 6 | 20 | 1,024 | 1,735 | 2,048 |
| 7 | 158 | 1,024 | 66,119 | 66,560 |
| 8 | 106,427 | 106,496 | 44,461,267 | 45,088,768 |
| 9 | 789,383 | 790,528 | 329,067,149 | 329,252,864 |
| 10 | 880,113 | 880,640 | 367,039,374 | 368,050,176 |
| 11 | 1,481,221 | 1,482,752 | 619,175,993 | 619,708,416 |
| 12 | 10 | 1,024 | 4,160 | 5,120 |
| 13 | 48,649 | 49,152 | 4,198,492 | 4,199,424 |
| 14 | 569 | 1,024 | 46,268 | 47,104 |
| 15 | 17 | 17 | 17 | 17 |
| 16 | 569 | 569 | 569 | 569 |
| 17 | 54,297 | 57,344 | 54,297 | 57,344 |
| 18 | 37,195 | 40,960 | 15,585,644 | 15,728,640 |

Metric 18's full-run F2 is exactly the previously frozen 15 MiB operational
target. This equality is a derived result, not evidence that the target was
changed to fit the run.

## 5. Finalizer architecture and fail-closed behavior

The finalizer has no local imports and contains no expected 18-row F1/F2
answer vector. It:

- secure-reads and identity-checks every source before execution, then repeats
  the source checks after execution;
- launches children with fixed `execve` arguments, an isolated environment,
  rlimits, private directories, wall watchdogs, and parent `wait4` resource
  observation;
- rejects noisy, nonzero, partial, duplicate, unknown, reordered, noncanonical,
  or oversized child output;
- recomputes all 475 cases and 18 summaries through independent schema and F2
  validation rather than trusting a child status field;
- removes private semantic/comparison artifacts and rejects temporary or
  diagnostic limit excess;
- creates an absent manifest atomically without overwrite or symlink following;
  and
- rolls back an unaccepted linked file if the post-link authority check fails.

The independent finalizer suite covers the accepted path plus strict parser,
schema, identity, F2, source-drift, noisy/nonzero/partial/extra-child-output,
parent-observed resource, atomic-overwrite, symlink, rollback, and invalid-CLI
mutations. Its first correct fail-first state was exactly one missing-finalizer
failure (`A3_T_FINALIZER_MISSING`); the completed suite passes 39 tests.

## 6. Fresh acceptance evidence

| Check | Result |
|---|---|
| S1-A1 seed/boundary/security predecessor matrix | 121 passed in 15.65 s |
| Preflight A focused suite | 6 passed in 111.36 s |
| Preflight B focused suite | 6 passed in 125.95 s |
| Comparator focused/real-child suite | 8 passed in 98.23 s |
| Finalizer focused/hostile suite | 39 passed in 3.98 s |
| Complete S1-A3 regression command | 182 passed in 368.39 s |
| Seed generator `--check` | exact 13,419,905-byte reproduction |
| Finalizer `--check-manifest` | two independent exit-0 exact checks; empty output |
| Final manifest physical checks | 15,560 bytes; mode `0600`; no staging residue |
| Final-tree control plus finalizer tests | 42 passed in 7.54 s; active gate `S1-A4` |
| Ruff format/check and Python compile | PASS |
| Changed-document relative-link audit | 228 links resolve across 8 files |
| Final-tree `git diff --check` | PASS |

The 182-test command is the union of the 121 accepted predecessor tests, the
6 A tests, 6 B tests, 8 comparator tests, 39 finalizer tests, and 2 execution-
control tests. It was run against the final frozen source and manifest bytes.

## 7. Falsifications and corrections retained

The accepted result did not assume that the dated S1-A2 record still described
the current tree. Exact-byte review found that preflight A and its test no
longer matched the old acceptance table. The current files were therefore
rerun through A, B, comparator, and the full matrix; the matching semantic
result and new comparison identity were frozen explicitly rather than silently
reusing stale prose.

Finalizer review also rejected weaker designs that trusted child status,
copied expected F2 answers, observed limits only inside a child, left private
artifacts behind, overwrote an existing manifest, or could leave a linked file
after a failed post-publication check.

## 8. State transition and next boundary

The canonical transition is:

```text
S1-A3  ACTIVE -> ACCEPTED
S1-A4  WAITING -> ACTIVE
Stage 1 remains NO-GO
offline Stage 2 remains BLOCKED on S1-R0
paper/live remains BLOCKED on S1-X
```

The next single bounded action is `A4-B0`: audit the retained
`generate_raw_v8_step2_external_schema_v2_maximum_protocol_pilot_v49f.py`
bootstrap, which explicitly implements only the rejected V1 structural self-
test, and freeze a V2-only verifier/producer/pilot boundary against this final
manifest before implementing the verifier, producer, or replacement pilot.

## 9. Nonclaims

This acceptance does not construct or verify a maximum witness. It does not
accept a verifier, producer, pilot, any of the 474 maximum rows, local case 475,
Raw V8 Step 2 or Step 3, transport-wide A2-M/A2-E, Stage 1, provider behavior,
completed-bar authority, offline Stage 2, paper/live readiness, predictive
edge, trading safety, or profitability.

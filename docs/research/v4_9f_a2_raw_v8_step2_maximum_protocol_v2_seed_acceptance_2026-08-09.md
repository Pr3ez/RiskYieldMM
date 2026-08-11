# Raw V8 Step-2 maximum protocol V2 seed acceptance

Date: 2026-08-09  
Historical decision: **GO for `S1-A1` only — SUPERSEDED**  
Current gate: **`S1-A2` dual feasibility preflight**

> Supersession notice (2026-08-09): S1-A2 boundary review proved that the
> serialized seed does not construct exact complete-case subjects or ordinary
> per-kernel transition expansions. See
> [`v4_9f_a2_raw_v8_step2_v2_full_case_execution_closure_correction_2026-08-09.md`](v4_9f_a2_raw_v8_step2_v2_full_case_execution_closure_correction_2026-08-09.md).
> The evidence below remains valid for the narrower properties it tested, but
> it no longer authorizes either full-case preflight. The corrected authority
> and current authorization are recorded by
> [`v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md).
> That corrected seed was subsequently amended to bind exact per-emission
> token metadata. The current identities and authorization are in the
> [`event-metadata amendment`](v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md).
> All byte identities and test counts below are predecessor evidence only.

## 1. Acceptance boundary

This record accepts one deterministic, secure, identity-closed V2 seed
catalog as the input authority for the two independent `S1-A2` feasibility
preflights. It closes `S1-A1`; it does not accept a constructive maximum, the
Raw V8 Step-2 runtime, Raw V8, A2-M, Stage 1, offline Stage 2, paper trading,
live trading, or profitability.

The accepted files are:

```text
scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py
scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json
scripts/tests/raw_v8_step2_cell_transfer_rule_catalog_v49f.json
scripts/tests/raw_v8_step2_case_event_grammar_v49f.json
scripts/tests/raw_v8_step2_case_event_hand_oracles_v49f.json
```

The seed catalog's `ordered_authority_binding_records` is the complete ordered
17-source manifest. Every source is pinned by repository-relative path, exact
octet count, and raw SHA-256; semantic IDs are additionally pinned where the
predecessor authority defines them.

## 2. Frozen identities and size

| Artifact | Octets | Raw SHA-256 / semantic identity |
|---|---:|---|
| V2 seed catalog | 13,346,796 | `b393360e632498666c78fa00a53fea233fe10763bbca8163c23ebbf645ace1d3` |
| Seed catalog semantic ID | — | `def13e2c06179c5a4a9e451ae8b8fe36f10326ffee39bf94625462047ec0b882` |
| Seed generator | — | `13289a1f049c8cbbe369ee459e6a83c4162a0416ec2d85d8e1001616692a23fa` |
| Cell-transfer rule catalog | 108,000 | `0d6efae04daa148d755ce49fe84b70d188cfd736257b3bb0714fb25876c357f2` |
| Case-event grammar | 63,431 | `b6e9f20ef413975674395ad8cb4880df28d4885e792b7a9cd12e87a5c33954ea` |
| Case-event hand oracles | 310,490 | `4e234065d43a02f69e6a4c6cdf89bff3656c07a6f66c909ddbba9c55ead703a4` |

The accepted catalog is 6,399,533 bytes smaller than the 19,746,329-byte
pre-compaction candidate. It has 2,381,844 bytes of headroom below the
15,728,640-byte operational target and 3,430,420 bytes below the strict
16,777,216-byte individual-file ceiling.

## 3. Closed implementation decisions

The accepted seed has:

- normalized identity-bound storage for 475 logical plans and compact
  case-plan references;
- 408 reconstructible profile programs with compact scope summaries and
  explicit schedule-authority references;
- a dual-channel profile contract separating P2 upper-bound derivation from
  exact retained P1/P3 attainment;
- a typed analytic case-69 intersection that independently derives and attains
  2,581 octets;
- 18 typed transfer-opcode contracts backed by 19 identity-bound rule ASTs,
  checked UInt128 arithmetic, signed-safe-integer endpoints, strict postorder
  child reads, and earlier-subrule-only calls;
- all eight independently reconstructed owner codec residuals;
- tagged ordinary/local cache-key, transition-token, result-cell, and
  step-commitment schemas, so case 475 has no fabricated ordinary step;
- a closed physical-transition/event/resource program, per-unit
  cell-before-commitment hash order, digest-only final-result ownership, and a
  cycle-free stream finalization;
- three complete hand oracles covering all thirteen required tags and all 18
  resource metrics, with fourteen mandatory mutation classes; and
- strict duplicate-free canonical JSON, bounded source resources, no-follow
  regular single-link reads, cross-source inode uniqueness, two complete
  source snapshots plus pre/post-publication revalidation, and atomic
  fsync/readback/path-identity-verified publication.

No owner choice remains open in either V2 design note.

## 4. Determinism evidence

The controlled sequence was:

```bash
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
```

All four commands reported the same byte count, raw SHA-256, and seed semantic
ID shown above. The output is a regular single-link file. No temporary output
remained.

## 5. Independent read-only review

After the candidate bytes were frozen, six standalone consumer suites read the
serialized catalog and its pinned authorities without importing the seed
generator. They independently reconstruct root/subcatalog identities, all 475
plan bindings, all 408 profile programs, recurrence programs, typed transfer
execution, case-69 intersection, owner residuals, event streams, subject
bytes/digests, live sets, and all hand-oracle metric vectors. The separate
source-security suite tests the generator's hostile-input and publication
boundary.

```bash
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_local_state_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_recurrence_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_profile_conditioning_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_cell_transfer_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_event_grammar_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_source_security_v49f.py
```

Result: **80 passed, 0 failed**. The first six serialized-catalog suites account
for 63 tests; source/publication security accounts for 17 tests. The negative
surface includes duplicate keys, floats/non-finite values, unsafe integers,
surrogates, noncanonical JSON, excessive depth/string size, snapshot drift,
symlink/hardlink aliases, unknown/extra AST members, wrong rule identities,
forward rule calls, output aliases, and the operational size cap.

This provides the required read-only GO against the frozen candidate. It does
not replace the two genuinely separate all-case counting implementations
required by `S1-A2`.

## 6. Scoped leftover and worktree review

The accepted S1-A1 scope has no known stale generated output, open decision,
failed focused test, formula-string substitute, output temporary, or size-cap
violation. `git diff --check` and targeted Ruff/compilation checks are required
on the final documented tree.

The repository worktree is intentionally large and mixed, with substantial
pre-existing Stage-1 implementation and documentation still uncommitted and
many files untracked. This narrow acceptance neither claims a clean worktree
nor accepts unrelated files. No unrelated change was removed, reset, staged,
committed, or published.

## 7. Next authorized work

`S1-A2` must implement exactly two independent, counting-only interpretations
over all 475 cases plus a comparator. Neither implementation may import the
seed generator or the other preflight, reuse the other's derived results,
construct witnesses, tune F0 limits, or patch a disagreement locally. Exact
agreement on every one of the 18 metrics and every case, within the immutable
F0 ceilings, is required before `S1-A3` can freeze the final V2 protocol.

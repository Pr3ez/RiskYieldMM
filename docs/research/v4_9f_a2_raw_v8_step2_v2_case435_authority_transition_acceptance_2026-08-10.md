# Raw V8 Step-2 V2 case-435 authority-transition acceptance

**Date:** 2026-08-10  
**Sub-gate:** `A4-P6-C435-D`  
**Decision:** `ACCEPTED`  
**Next bounded sub-gate:** `A4-P6-V`  
**Stage 1:** `NO-GO`  
**Verifier expansion:** `RELEASED FOR IMPLEMENTATION`, not accepted

## 1. Decision

`A4-P6-C435-D` is accepted. The frozen C3 theorem is now consumed by a
versioned, exact-delta authority chain without modifying any accepted V1
artifact:

```text
accepted seed + C3 theorem
  -> case-435 seed delta
  -> manifest delta
  -> constructive-boundary delta
  -> corrected six-case target delta
```

The effective resolver replaces exactly the falsified case-435 program, plan,
and case-plan binding. The remaining 474 cases and 407 profile-conditioning
programs resolve byte-for-byte to the physically pinned predecessor seed.
Using the shadowed predecessor case-435 record, adding a second override, or
falling back ambiguously is a rejection.

The corrected case-435 P2 program imports the accepted C3
`EXACT_ATTAINED_MAXIMUM` cell, verifies its 257,887-octet endpoint does not
exceed the predecessor 262,143-octet structural ceiling, and then feeds that
exact cell to the unchanged P1/P3 application replay and equality check. The
effective logical plan is `EXACT_LEGAL_DOMAIN`, has no safe-relaxation IDs,
and applies no cross-application deletion policy.

The accepted C3 proof-source identity is:

```text
2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f
```

## 2. Architecture decision

Four options were compared before publication.

| Option | Benefit | Material defect | Decision |
|---|---|---|---|
| Edit the accepted files in place | Small apparent diff | Destroys predecessor evidence and invalidates all pinned dependants | Rejected |
| Copy and rewrite the complete 13.4 MiB seed | Direct standalone successor | Duplicates almost entirely unchanged authority, obscures the one-case delta, and invites a false claim that predecessor preflight evidence covers a changed full seed | Rejected |
| One monolithic overlay | Compact | Cannot bind each downstream physical authority without either circular raw hashes or an externally implicit load order | Rejected |
| Four ordered exact-delta authorities | Compact, acyclic physical and semantic binding, explicit fallback, independently reversible | Requires the next verifier to implement the frozen resolver | **Selected** |

The selected chain is deliberately data-only. `A4-P6-V` must consume the
predecessor authorities plus these deltas in the frozen load order. It may not
silently reinterpret the old full files as corrected.

## 3. Frozen successor authorities

| Authority | Bytes | Raw SHA-256 | Semantic ID |
|---|---:|---|---|
| `scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json` | 22,976 | `5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da` | `7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b` |
| `scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json` | 2,192 | `daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf` | `6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c` |
| `scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json` | 4,806 | `208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c` | `7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d` |
| `scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_six_case_target_delta_v49f.json` | 4,768 | `394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b` | `a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072` |

The effective case-435 nested identities are:

```text
profile-conditioning program:
160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820

logical count plan:
343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8

F2 resource-limit catalog:
5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f
```

## 4. Implementation and independent verification

| Artifact | Role | Bytes | SHA-256 |
|---|---|---:|---|
| `scripts/tests/migrate_raw_v8_step2_maximum_protocol_v2_case435_authorities_v49f.py` | deterministic predecessor-to-successor migrator | 41,092 | `a0387ebb6722cc76777a3840994e46ad550816fac92ba687a62db47ce4e275c0` |
| `scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_authority_transition_v49f.py` | separate reversible-delta and transitive-authority checker | 36,506 | `8d56dbb3b7f382e28bd5f6d73abc03ce4ec064575f942062bd11d02a93015e0e` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_case435_authority_transition_v49f.py` | identity, determinism, isolation, and hostile-mutation suite | 17,879 | `a2f2b0dcabb4107133ce1afc5302f3386ae457a3390d10afc33cc0874317b879` |

The checker imports neither the migrator nor any producer/verifier. It:

1. verifies the physical and semantic identities of every predecessor;
2. verifies all eight accepted C1/C2/C3 source authorities;
3. recomputes every successor semantic identity;
4. reverses the case-435 program and plan edits and requires exact equality
   with their predecessor records;
5. recomputes the complete unaffected-program, unaffected-plan,
   unaffected-binding, case-universe, inherited-recipe, and inherited-boundary
   digests;
6. proves the four-file raw-hash and semantic-ID chain; and
7. releases only verifier implementation, while leaving producer and runner
   expansion waiting.

The focused suite passes 26 tests. Its re-sealed hostile cases reject:

- a second override;
- the old structural-superset plan mode;
- a changed exact-cell endpoint;
- structural P2 promoted back to the acceptance source;
- safe-relaxation reuse;
- false unaffected-record evidence;
- predecessor preflight evidence relabeled as successor evidence;
- altered F2 authority;
- premature producer release;
- target-gate substitution;
- an extra pilot case; and
- duplicate, floating, non-finite, BOM-prefixed, or invalid UTF-8 JSON.

## 5. F2 treatment

The old dual preflight and finalization manifest were computed against the
predecessor seed. D therefore does **not** call them a fresh preflight of the
case-435 exact proof program.

The successor manifest and boundary instead preserve all 18 predecessor F2
limits byte-exactly as immutable ceilings and derive a new authority ID over
their digest plus the successor seed and manifest IDs. During `A4-P6-V`, the
expanded verifier must meter its exact case-435 work against every per-case and
full-run ceiling. An excess is a controlled `NO-GO`; the limits may not be
raised or repaired from pilot observations.

This is stricter and more truthful than either silently inheriting a stale
preflight claim or reopening the accepted F2 ceilings before the real verifier
implementation exists.

## 6. Reproduction

```bash
python scripts/tests/migrate_raw_v8_step2_maximum_protocol_v2_case435_authorities_v49f.py \
  . --check
python scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_authority_transition_v49f.py \
  .
pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_case435_authority_transition_v49f.py
```

Expected focused result:

```text
26 passed
```

No external literature search was needed for D. This is a repository-defined
authority migration whose correctness depends on frozen bytes, semantic
identity construction, reversible exact deltas, and falsification tests. The
relevant evidence is the accepted C3 theorem and the repository's prior V3 to
V4 exact-migration precedent.

## 7. Successor contract and nonclaims

`A4-P6-V` is now the sole next bounded action. It must expand the independent
verifier against the corrected target, beginning with independently
constructed fixtures and hostile mutations for cases 24, 54, 69, 435, and
475. For case 435 it must resolve the exact-delta program, independently replay
P1, reproduce the 257,887-octet P2/P3 equality, and fit the immutable F2
ceilings.

This acceptance does not accept the expanded verifier, producer, runner,
six-case pilot, all-475 result set, Raw V8 Step 2, Stage 1, Stage 2,
paper/live trading, predictive edge, or profitability. The remaining 406
generic structural-superset profile programs still require their own exact
closure before the complete 475-case maximum claim.

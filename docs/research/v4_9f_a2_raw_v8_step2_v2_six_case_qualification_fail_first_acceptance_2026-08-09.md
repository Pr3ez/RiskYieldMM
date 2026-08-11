# Raw V8 Step-2 V2 six-case qualification fail-first acceptance

**Date:** 2026-08-09  
**Gate:** `S1-A4 / A4-P6-T`  
**Decision:** `ACCEPTED`  
**Next bounded gate at acceptance:** `A4-P6-V`  
**Stage 1:** `NO-GO`

> **Subsequent disposition, 2026-08-09:** the independent
> [case-435 attainability falsification](v4_9f_a2_raw_v8_step2_v2_case435_attainability_falsification_2026-08-09.md)
> proved that the frozen case-435 P3 equality is infeasible. `A4-P6-V` is now
> on hold and correction sub-gate `A4-P6-C435` is next. This document remains
> the historical acceptance record for the fail-first target infrastructure;
> it is not evidence that all six success conditions are attainable.

## Decision

The independent six-case qualification target is accepted as the executable
contract for expanding the bounded case-5 producer/verifier pair into the
frozen representative pilot. This packet accepts the target, not the missing
five implementations and not the parent runner.

The target is:

`tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py`

Its frozen physical identity is:

| Property | Value |
|---|---:|
| Raw octets | `60,279` |
| SHA-256 | `12c1ff23ca6a7b58ddcda205ae017af15d7eef5be799ca7385231777c443a886` |

## Frozen qualification surface

The target independently binds the accepted constructive boundary, corrected
V2 seed, and finalization manifest, then exercises the six ordered pilot cases:

| Pilot position | Case | Required stressor |
|---:|---:|---|
| 1 | 5 | Small Boolean exhaustive canonical length; accepted positive control |
| 2 | 24 | Owner-member tagged union and owner codec |
| 3 | 54 | Raw-string array cardinality, ordering, and escaping |
| 4 | 69 | Local-shutdown outer-result exact application and codec |
| 5 | 435 | MAX64 root, full 67-context, 137 applications, safe superset |
| 6 | 475 | Local-shutdown exact minimality and single-mask rejection |

It checks the exact case and plan bindings, all 18 immutable F2 resource
limits, candidate closure and semantic identities, record references,
maximum/local result and receipt identities, per-case resources, candidate
immutability, two-run determinism, runner source isolation, runner output
closure, and full-pilot F2 aggregation.

The target does not import the producer, verifier, parent runner, or rejected
V1 constructive implementation. It invokes implemented roles only through
their public subprocess interfaces. Expected results for the five new cases
are not copied from V1 or emitted by the current producer; they must be derived
from the frozen V2 authorities.

## Accepted fail-first result

The complete target result is exactly:

```text
6 failed, 13 passed, 2 skipped
```

The passing-only selection is exactly:

```text
13 passed, 2 skipped, 6 deselected
```

Case 5 completes producer to verifier twice with byte-identical output and an
unchanged candidate. The six intended failures are:

```text
A4_P6_CASE_24_PRODUCER_NOT_QUALIFIED
A4_P6_CASE_54_PRODUCER_NOT_QUALIFIED
A4_P6_CASE_69_PRODUCER_NOT_QUALIFIED
A4_P6_CASE_435_PRODUCER_NOT_QUALIFIED
A4_P6_CASE_475_PRODUCER_NOT_QUALIFIED
A4_P6_PARENT_RUNNER_MISSING
```

The five case failures terminate at the current producer's explicit
`ONLY_CANONICAL_CASE_5_IS_SUPPORTED` boundary. The two runner behavior tests
skip because the runner is intentionally absent. There are no unexpected
failures.

## Fresh regression evidence

| Check | Result |
|---|---|
| Complete A4-P6-T target | `13 passed, 2 skipped, 6 failed` in 13.98 s; all six failures exactly intended |
| Accepted target selection | `13 passed, 2 skipped, 6 deselected` in 11.79 s |
| Existing verifier + producer + control suites | `40 passed` in 38.84 s |
| Existing A4-T complete fail-first target | `61 passed, 2 skipped, 1 failed`; sole failure is absent parent runner |
| Existing A4-T accepted selection | `59 passed, 2 skipped, 3 deselected` |
| Final-tree predecessor-through-A4-P6-T matrix | `320 passed, 4 skipped, 9 deselected` in 439.17 s |
| Seed generator check | exact 13,419,905-byte reproduction; SHA-256 `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Finalizer manifest check | exit 0 with required empty output |
| Stage-1 execution-control suite | `8 passed` |
| Ruff format/check and Python compile | PASS |
| Changed-document relative-link audit | 257 links resolve across 13 files |
| Final-tree `git diff --check` | PASS |

## Runner convention frozen by this target

`A4-B0` freezes the parent-runner role and pilot policies but does not fully
specify an executable command line or physical output tree. This target owns
the following subordinate convention without changing the accepted boundary
identity:

- required arguments: `--repository-root`, `--boundary`, and exactly one of
  `--write-output-root` or `--check-output-root`;
- root manifest: `constructive_pilot_manifest.json`;
- per-case roots: `cases/0001-0005` through `cases/0006-0475`, each containing
  exactly `candidate/` and `verified/`;
- closed-root identity: SHA-256 of compact canonical ordered file records
  containing repository-relative path, raw octets, and raw SHA-256;
- publication: all-or-nothing, deterministic, bounded, and non-publication.

The future runner must satisfy this target. It must not weaken the boundary,
rewrite candidate bytes, absorb verifier semantics, or tune F2 limits.

## Nonclaims

This acceptance does not establish that:

- cases 24, 54, 69, 435, or 475 are constructively implemented;
- the current verifier accepts those cases;
- the parent pilot runner exists;
- the six-case pilot passes;
- all 475 cases are complete;
- `S1-A4` or Stage 1 is accepted; or
- any trading model is profitable or ready for paper/live activation.

## Next bounded action at acceptance: `A4-P6-V`

Extend only the independent verifier to cases 24, 54, 69, 435, and 475.
Verifier tests must construct their own closed candidate fixtures from frozen
V2 authorities and prove exact positive and hostile behavior without using
producer output or rejected-V1 answers. The producer and parent runner remain
unchanged during this sub-gate.

`A4-P6-V` exits only when those five independent fixtures are accepted with
exact identities/resources, corresponding hostile mutations fail closed, the
accepted case-5 path remains unchanged, and the six-case fail-first target
advances from producer-boundary failures to exactly the still-unimplemented
producer/runner boundary.

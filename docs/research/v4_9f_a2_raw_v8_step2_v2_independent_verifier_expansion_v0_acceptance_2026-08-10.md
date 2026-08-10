# Raw V8 Step-2 V2 independent-verifier expansion V0 acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-V0`  
**Decision:** `ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-V1` — intrinsic cases 24 and 54

## 1. Accepted claim

`A4-P6-V0` adds one explicit, fail-closed authority resolver to the already
accepted independent verifier. The same executable now selects exactly one of
two frozen authority modes:

1. predecessor constructive boundary `bdc7363a…`, retaining the accepted
   case-5 path; or
2. case-435 successor boundary delta `7d4c06f5…`, which first loads and accepts
   the predecessor authorities and then the exact ordered delta chain before it
   opens any candidate bytes.

The successor chain resolves case 435 to the accepted exact program
`160486e8…` and plan `343259e3…`, while every other case resolves byte-exactly
to its predecessor record. V0 deliberately implements no new case algorithm:
case 5 is the only executable positive control, while cases 24, 54, 69, 435,
and 475 remain stable `UNSUPPORTED_CASE` rejections for V1 through V4.

This acceptance is a resolver/read-barrier claim. It is not acceptance of case
435 execution, its successor F2 resource use, a producer expansion, a parent
runner, all-case construction, live readiness, or profitability.

## 2. Authority and isolation decisions

The accepted design uses one verifier source and one boundary-mode dispatcher.
It rejects unknown boundary paths and cross-mode candidate authority IDs. It
does not create a second verifier path, replace predecessor JSON in place, or
import any producer, migration utility, solver, certificate checker, or prior
acceptance checker.

Before candidate access, successor mode pins and rechecks:

- the predecessor boundary, seed, manifest, 17 seed authorities, verifier
  source, and three V1-exclusion authorities;
- the successor seed delta and all eight exactness-theorem source records;
- the successor manifest and boundary deltas;
- the predecessor six-case target source and successor target delta; and
- the accepted typed rule runtime by exact size and SHA-256.

The typed runtime is loaded as a future P1 execution authority but is not
executed or treated as a proof in V0. Later packets must replay the applicable
rules on retained candidate bytes.

## 3. Frozen effective bindings

| Binding | Accepted successor value |
|---|---|
| seed catalog | `7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b` |
| finalization manifest | `6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c` |
| maximum-protocol SHA-256 | `daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf` |
| constructive boundary | `7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d` |
| F2 resource catalog | `5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f` |
| case-435 program | `160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820` |
| case-435 plan | `343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8` |
| case-435 exactness join | `2abf00603826f93bb6a538511bbd49ee45096901edbf9bc63c7d0cefb9e7fc3f` |
| case-435 exact maximum | 257,887 canonical octets |

Successor-mode case 5 emits the successor seed, manifest, maximum-protocol,
and F2 identities while retaining its byte-exact predecessor case/plan,
29-octet legal attainer, derivation stream, and resource vector. All result,
certificate, report, and receipt identities are independently recomputed by
the acceptance test.

## 4. Immutable resource-envelope result

The verifier measures the actual pinned-authority footprint before candidate
access:

| Mode | Authority files | Pinned authority octets | F0 file headroom | F0 octet headroom |
|---|---:|---:|---:|---:|
| predecessor | 24 | 28,159,023 | 40 | 38,949,841 |
| successor | 38 | 28,752,433 | 26 | 38,356,431 |

Both modes remain within the immutable F0 ceilings of 64 files and 67,108,864
pinned input octets. No F0 or F2 limit was raised. Case-435 execution-specific
F2 requalification remains waiting for V3 because V0 does not execute or
accept case 435.

## 5. Evidence

Accepted implementation:

- `scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py`
  - 127,214 octets
  - SHA-256 `f85a47ebf5b82068268054bd466421cf6251521429bd8c25f4baeadce5568014`
- `tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py`
  - 13,463 octets
  - SHA-256 `49d116d91f78fb65c4b7449adc00075565b5824ea761b77f04dce06309045511`

Measured checks before ledger sealing:

```text
pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py
7 passed in 15.22s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py
12 passed in 24.21s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py \
  -k 'not test_a4_t_requires_frozen_role_implementation'
59 passed, 2 skipped, 3 deselected in 23.55s

pytest -q tests/test_raw_v8_step2_maximum_protocol_v2_six_case_qualification_fail_first_v49f.py \
  -k 'not test_remaining_pilot_pipeline_is_exact_deterministic_and_candidate_immutable and not test_parent_runner_exists_and_obeys_frozen_isolation_surface'
13 passed, 2 skipped, 6 deselected in 12.43s

ruff check scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py
All checks passed!

python -m py_compile scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v49f.py
exit 0

git diff --check
exit 0
```

The hostile matrix proves that a mutated successor seed delta rejects as
`AUTHORITY_INVALID` before a deliberately absent candidate root is observed.
It also rejects old IDs under the successor boundary, successor IDs under the
old boundary, and any non-frozen boundary selector without output.

Final sealing evidence after the control-ledger update:

```text
25-file accepted Stage 1 matrix (the canonical 24-file post-D matrix plus V0)
384 passed in 1421.70s (0:23:41)

unfiltered A4-T
1 failed, 61 passed, 2 skipped in 24.18s
sole failure: A4_T_PARENT_PILOT_RUNNER_MISSING

unfiltered A4-P6-T
6 failed, 13 passed, 2 skipped in 15.31s
sole failure set: cases 24/54/69/435/475 producer-not-qualified plus parent runner
```

Together with the two accepted filtered fail-first selections, the post-V0
green control surface is `456 passed, 4 skipped, 9 deselected`. The unfiltered
failures above are required ordered fail-first evidence, not repository
regressions.

## 6. Next action and stop conditions

Proceed only to `A4-P6-V1`: add independent retained-byte validation for the
two intrinsic pilot cases 24 and 54. V1 must preserve both V0 boundary modes,
use the accepted typed runtime only as a generic rule-execution authority,
remain within immutable F0/F2 limits, and leave cases 69, 435, and 475
unsupported.

Stop and reopen V0 if any pinned predecessor/delta/source identity changes, a
candidate can be opened before the full authority barrier, the old case-5
result changes under predecessor mode, the verifier needs a non-allowlisted
import, or any resource limit must be raised to pass.

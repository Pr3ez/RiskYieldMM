# Raw V8 Step-2 V2 independent-verifier acceptance

**Date:** 2026-08-10  
**Gate:** `S1-A4 / A4-P6-V-A`  
**Decision:** `ACCEPTED`  
**Formal verifier gate:** `A4-P6-V ACCEPTED`  
**Formal Stage 1 state:** `NO-GO`  
**Next bounded packet:** `A4-P6-P` — separate producer expansion

## 1. Accepted claim

`A4-P6-V-A` independently accepts the complete V0–V4 verifier surface for
the predecessor case-5 authority and the corrected successor cases 5, 24, 54,
69, 435, and 475. The acceptance reviewer reconstructs the authority closure,
recomputes the exact case/result/receipt/resource ledger, enforces all 18
immutable F2 ceilings, audits source isolation, and executes the exact pinned
V0–V4 test suite plus both expected-red producer/runner suites.

This closes formal verifier expansion `A4-P6-V`. It releases only the next
separate producer packet `A4-P6-P`. It does **not** accept producer expansion,
the parent runner, the six-case end-to-end pilot, all 475 result artifacts,
Raw V8 Step 2, Stage 1, paper/live readiness, predictive edge, trading safety,
or profitability.

## 2. Architecture decision

Three review strategies were challenged:

| Strategy | Benefit | Decisive weakness | Decision |
|---|---|---|---|
| Snapshot-only review | Fast and deterministic | Rechecks stored claims without proving the runtime still produces them | Rejected |
| Replay-only review | Exercises the runtime | Trusts pytest collection/names and does not independently reconstruct identities or F0/F2 ledgers | Rejected |
| Independent reconstruction plus pinned replay | Separates semantic reconstruction from runtime evidence and preserves exact expected-red boundaries | More execution time and a larger explicit acceptance contract | **Selected** |

The selected reviewer is standard-library-only and does not import the
verifier, producer, proof checkers, or reviewed pytest fixtures. It first
reconstructs the frozen bytes and ledgers, then launches exact child-process
replays under a closed deterministic environment. The report omits timings and
ambient values so two accepted runs produce identical bytes.

No external literature search was needed for this packet. The question is
repository-specific canonical identity, exact arithmetic, deterministic
execution, and fail-closed control behavior; external sources cannot validate
these local semantic IDs.

## 3. Frozen acceptance report

The accepted report is:

```text
scripts/tests/raw_v8_step2_maximum_protocol_v2_independent_verifier_acceptance_report_v49f.json
octets  22564
raw SHA-256  1adbc0b1ac3ca2e9c2ad805de6ba79f6ce1b8ea244d6a11e50c086f438c7c45c
semantic ID  1e20c2c1312abe6b3924c96e6979f046325a87d635f728007a157831381b1da1
decision  ACCEPTED
```

Its successor authority closure is exactly 39 regular files and 29,004,595
pinned octets. This leaves 25 files and 38,104,269 octets below immutable F0
limits of 64 files and 67,108,864 total pinned octets. The independently
reconstructed authority-closure digest is
`3e173b6c6441e0dfb695e5e118d69bdb151c13299008cb6e1f0efddaec2cbd10`.

## 4. Exact accepted case ledger

| Authority mode | Case | Maximum octets | Result ID | Receipt ID | Resource-report ID |
|---|---:|---:|---|---|---|
| predecessor constructive V1 | 5 | 29 | `ae6b76bc72b20531f8e72b5ccc40ef9450329d5d0165698a7230a982f5725272` | `2b270c5b6f5df06cd5b3c781642d4a8878d62be6e5014db95d1eaa72970150fd` | `e0bcabae55dba9f0b1e14b370c31aeb8ea93124a4ac2b2ac7754d4e1cbcbee37` |
| successor exact-delta V1 | 5 | 29 | `f3b8f9da535e87f242c7b26cfbc525b1c71521d2dc1aaade648624206e30845f` | `de9de4223d2a40d13a6c5ad903c4dc259f6d6e84feda3664c0968c7f6b52ceba` | `375939bb2e876af1460adffeacf1fb5c12393c2c45dc7926e8f083e3e5983cee` |
| successor exact-delta V1 | 24 | 523,738 | `2c9054a363632a7f0da2dace72677155df9bbf2f4527bc5ff3ab952f96d32876` | `46d69394ea4b0a1ef555b9cd0e097fe5827b67b9a64aa573595adba29e45510d` | `940cb2ddf33aafc5e87b2e1abc482c88db97d1b6e2750957629fba3c4f8c8107` |
| successor exact-delta V1 | 54 | 3,145,728 | `3fbbe19b69419aaedcfd0eed07e56422a99b07e6f14ec1252f3c46e275688ce1` | `2e516b7417a28f3330c1938c10451d347b33b5a8a11247656a8fa5f8d6106c81` | `bce3c4cc8a75d8127cd2ce444a694e2f87baf411d8eb3a852826b8ef92ecc451` |
| successor exact-delta V1 | 69 | 2,581 | `1a56290000608a5c877bdc9a73ef00600b4dcf261f5b1d85586f5d3339e3723e` | `fb83be220337d47d58da370a266a35df1918ab6d6e79f1e3aeea612300b4327e` | `48bd334db703f92b7341039e186604f620441ae175485f3b5e7a71a36d68e740` |
| successor packed-context V1 | 435 | 257,887 | `0ac5c1cb7e663b2259264144b4b45e61a0b163e1861d07ec7054072e3829866f` | `fd2d341d8bb8c79f72a97926599e8535c5bcb4694d839120f7852030bbfbc7dd` | `3a38d19959e0944c8353fde865fb2ae63119d4f289869fcfd601fd239b8b7be9` |
| successor packed-context V1 | 475 | 524,380 | `937e7a163426dc7015117004c03b8f8fc3fb3c9ad040c423f97b549974f20e73` | `eb6fdf156bb1b855a8fb4fadd8ebb10434c053493f91ce8fbcd5c2539ed10f0f` | `ffbb512dbe46fcc6cb9c94bfff2f21a246a0b4b00a118b60284c82f034b136d8` |

The predecessor and successor case-5 records deliberately have different
authority-bound result, receipt, and resource IDs while retaining the same
29-octet result and measured vector. This proves that the review does not
collapse the two authority modes into one implicit fixture.

## 5. F0/F2, isolation, and immutability evidence

For every one of the seven case records, the reviewer independently checks an
18-integer nonnegative resource vector and recomputes every margin against the
frozen successor F2 catalog. The acceptance tests then perturb each of the 18
coordinates to `limit - 1`, `limit`, and `limit + 1`: the first two accept and
the last rejects. No F0 or F2 value was raised.

The source audit proves that the verifier imports only `hashlib`, `json`,
`os`, `pathlib`, `stat`, `sys`, and `tempfile`; uses no dynamic code loading;
and imports no producer or proof checker. Ten pinned replay test artifacts are
also parsed to reject verifier imports. Candidate/context immutability is
confirmed by the pinned double-run and hostile replay suites. Alias, symlink,
hard-link, duplicate-member, float, non-finite, BOM, invalid-UTF-8, report-ID,
control, source-dependency, and parser-drift attacks all reject fail-closed.

## 6. Runtime and expected-red evidence

The report's exact child-process evidence is:

```text
V0-V4 pinned verifier replay
128 passed, 0 failed, 0 skipped across 10 pinned test artifacts

full A4-T expected-red
61 passed, 2 skipped, 1 failed
sole code: A4_T_PARENT_PILOT_RUNNER_MISSING

full A4-P6-T expected-red
13 passed, 2 skipped, 6 failed
codes: A4_P6_CASE_24_PRODUCER_NOT_QUALIFIED
       A4_P6_CASE_54_PRODUCER_NOT_QUALIFIED
       A4_P6_CASE_69_PRODUCER_NOT_QUALIFIED
       A4_P6_CASE_435_PRODUCER_NOT_QUALIFIED
       A4_P6_CASE_475_PRODUCER_NOT_QUALIFIED
       A4_P6_PARENT_RUNNER_MISSING
```

An unexpected green, count change, extra failure code, collection error, or
stderr output invalidates the report. Thus verifier acceptance cannot be
misread as producer or runner acceptance.

## 7. Accepted implementation artifacts

| Artifact | Octets | SHA-256 |
|---|---:|---|
| independent acceptance reviewer | 41,217 | `d254c9c49c57e2a4207a73d22e2b3ad4a303534249eef4a2373b5c124c2028e9` |
| hostile acceptance test | 9,703 | `d167ce6c98a6d48960cccbb95b94fddb7f5991adf5481408f3ed125aff2c75c7` |
| deterministic acceptance report | 22,564 | `1adbc0b1ac3ca2e9c2ad805de6ba79f6ce1b8ea244d6a11e50c086f438c7c45c` |
| accepted V4 verifier | 373,327 | `b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25` |

Focused acceptance evidence:

```text
37 passed in 839.20s (0:13:59)
```

The focused test regenerates the report into an isolated temporary path and
requires byte equality with the stored report. The first direct report run and
the focused regeneration therefore constitute two full, independent process
runs over the same frozen inputs.

Final integrated evidence:

```text
34-file Stage 1 core collection
542 tests collected

34-file Stage 1 core matrix
542 passed in 3018.68s (0:50:18)

Stage 1 control
STAGE1_CONTROL_OK; 44 passed in 384.93s

filtered A4-T
59 passed, 2 skipped, 3 deselected

full A4-T expected-red
61 passed, 2 skipped, 1 failed

filtered A4-P6-T
13 passed, 2 skipped, 6 deselected

full A4-P6-T expected-red
13 passed, 2 skipped, 6 failed

seed generator --check
13419905 bytes; raw SHA-256 a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f
```

The four V-A/control Python files are formatter-clean, lint-clean, and compile
cleanly. All changed Python files compile and pass Ruff when the three frozen
historical diagnostics (`B904`, `I001`, `UP035`) are explicitly excluded.
Eleven accepted V1–V4/context-pack files would be mechanically reformatted and
three carry those pre-existing diagnostics. Their exact bytes are already
authority/report-pinned; rewriting them during V-A sealing would invalidate
the accepted verifier and require full requalification. They remain explicit
frozen formatting debt for a successor version, not silently edited current
authority.

## 8. Advancement decision

`A4-P6-V-A` and formal verifier expansion `A4-P6-V` are accepted. The sole
next mutable packet is `A4-P6-P`, which must expand the separate producer for
cases 24, 54, 69, 435, and 475 without importing verifier answers or weakening
the accepted authority/F0/F2 contracts. The parent runner stays held until the
producer expansion is independently accepted.

Final `git diff --check` and the five-document local-link audit pass; no
reviewer staging directory, temporary acceptance report, or repository-local
temporary file remains. The worktree intentionally retains the cohesive,
uncommitted V1–V4/V-A checkpoint for later scoped publication; no unrelated
generated leftover was found. Formal Stage 1 remains `NO-GO`.

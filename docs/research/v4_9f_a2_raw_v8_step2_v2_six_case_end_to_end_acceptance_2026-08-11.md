# Raw V8 Step-2 V2 six-case end-to-end acceptance

Date: 2026-08-11  
Status: **A4-P6-E ACCEPTED — A4-R475 ACTIVE — A4-R475-T NEXT — FORMAL STAGE 1 NO-GO**

## 1. Decision

`A4-P6-E` is accepted. Two isolated executions of the frozen A4-P6-R reviewer
each reproduced the stored parent-runner acceptance report byte-for-byte. A
separate standard-library-only adjudicator reconstructed the predecessor
identities, exact six-case ledger, target qualification rule, and all 18 F2
aggregates without importing the reviewed roles or reviewer.

The frozen qualification rule is satisfied:

```text
ALL_SIX_CASES_PASS_TWICE_BYTE_IDENTICALLY_UNDER_IMMUTABLE_F2
```

This releases `A4-R475` for **versioned all-475 implementation followed by
execution**. It does not release an immediate run with the unchanged six-case
binaries.

## 2. Accepted artifacts

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| A4-P6-E reviewer | 34,288 | `a0a456b9689cabf369d0c7d57a2cfbaa7ecb9689518408541f24476e945ccc1c` |
| deterministic report | 16,064 | `8aab9f9be12edb028eae154f05c032b0d125865f37cad04e32862857a78b2d7e` |
| acceptance test | 8,755 | `89a34db383a2f3a07ac66f29ac0be2effb49ad38d0007282ff1fd0d29eb13af1` |
| frozen design | 7,484 | `70314ac6df805d35ef3c7a922208e1aedf7733334cfdaea8c9c7621de1dd2b30` |

Acceptance report semantic ID:

```text
c94c784f29a57fd8fc345cd49b90b7225e2a5697ff2077c8dd0b4b2115809d11
```

The report binds predecessor A4-P6-R report ID:

```text
ee39ba2ee328f20774ed3c678d6bf9edf4790a68a587c591828813c358f0ca9b
```

The accepted runner, producer, verifier, qualification, reviewer, report,
acceptance test, acceptance document, seed, target, boundary, manifest, and
producer-report bytes remain unchanged.

## 3. Independent replay evidence

The A4-P6-E runtime review observed:

```text
A4-P6-R reviewer replays:             2
effective parent transactions:         4
effective producer child runs:        24
effective verifier child runs:        24
reviewer output determinism:          VERIFIED
both outputs match frozen report:     VERIFIED
```

Each predecessor reviewer replay internally reconstructed two complete parent
transactions and reran the frozen seven-test runner qualification plus the
64-test three-role contract. Static preflight alone remained explicitly
`STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED` and kept `A4-P6-E` active.

## 4. Independently reconstructed release ledger

The accepted ordered pilot remains:

| Pilot | Case | Coverage |
|---:|---:|---|
| 1 | 5 | small Boolean exhaustive canonical length |
| 2 | 24 | owner member, tagged union, and owner codec |
| 3 | 54 | raw-string array cardinality, ordering, and escaping |
| 4 | 69 | local-shutdown outer result exact application and codec |
| 5 | 435 | max-64 root, full 67-object context, 137 applications, exact 257,887 |
| 6 | 475 | local-shutdown exact minimality and single-mask rejection |

Candidate, receipt, result, plan, closure, and resource identities agree
exactly across the frozen target, separate-producer report, parent-runner
report, and both fresh reviewer replays. Canonical hashes bind the complete
case ledger and F2 ledger, so a coherently re-sealed record mutation is not
accepted merely because its counts remain plausible.

## 5. Whole-run F2 evidence

The independently recomputed six-case vector is:

```text
[6, 4239080, 375, 2318, 8756229, 17, 375, 254204, 1840387,
 2057687, 3473350, 22, 12533, 139, 17, 137, 50016, 87245]
```

All 18 values fit the immutable finalization-manifest limits. Positions 15–17
retain `MAXIMUM` aggregation; every other position retains `SUM`. No observed
value changed, raised, inferred, or repaired a limit.

## 6. Release criteria

All eight closed criteria pass:

1. frozen predecessor artifact identities;
2. A4-P6-R report semantic identity;
3. exact six-case qualification rule;
4. two independent A4-P6-R reviewer replays;
5. transaction, immutability, read-only, rollback, and rejection evidence;
6. exact six-case target/producer/runner ledger agreement;
7. immutable 18-metric F2 reconciliation; and
8. explicit all-475 scope nonclaim and versioned release boundary.

Re-sealed changes to the gate, campaign surface, case ledger, replay count, or
F2 evidence reject even when the outer report identity is recomputed.

## 7. Critical campaign limitation

The seed universe contains:

```text
474 maximum-publication cases
1 local-minimality case
475 cases total
```

The accepted binaries support only six pilot positions. Therefore 469
non-pilot cases remain outside their current allowlists. Pilot F2 headroom does
not prove that the complete 475-case aggregate will fit.

`A4-R475` is consequently active for a new versioned implementation. The
accepted six-case sources are immutable predecessor/regression authorities;
they must not be edited in place to manufacture all-case support.

## 8. Next bounded packet

`A4-R475-T` must freeze the all-case campaign contract before implementation:

- exact 475-case ordering and case-kind coverage;
- versioned producer, verifier, and parent-runner role paths;
- all-case candidate/result schemas and authority dispatch;
- per-case and full-run F0/F2 enforcement;
- restart, checkpoint, rollback, partial-publication, and resume semantics;
- deterministic output-root and campaign-manifest identities;
- bounded concurrency and storage limits;
- fail-first tests proving the six-case binaries reject non-pilot cases; and
- acceptance conditions for every result plus complete aggregate evidence.

Only after `A4-R475-T` is accepted may new all-case role versions be
implemented or a complete campaign be started.

## 9. Test evidence and nonclaims

```text
fail-first:                      1 failed, 7 skipped
non-runtime acceptance checks:  7 passed, 1 deselected
full independent acceptance:    8 passed in 343.11s
```

This checkpoint accepts `A4-P6-E` and activates `A4-R475`. It does not accept
`A4-R475-T`, any all-case implementation, any complete 475-case output, Raw V8
Step 2, Stage 1, Stage 2, paper/live trading, predictive edge, safety, or
profitability. Formal Stage 1 remains `NO-GO`.

# Raw V8 Step-2 V2 parent pilot runner acceptance

Date: 2026-08-10  
Status: **A4-P6-R ACCEPTED — A4-P6-E NEXT — FORMAL STAGE 1 NO-GO**

## 1. Decision

The parent-owned six-case pilot runner is accepted at:

```text
scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py
```

It executes the accepted producer and independent verifier only through the
frozen isolated CLIs, under the packed successor boundary. It publishes one
complete parent root only after all six cases pass, candidate closures remain
unchanged, all result identities reconstruct, and all 18 whole-run F2 metrics
fit the immutable limits.

The runner is not a semantic proof implementation. It imports neither child,
contains none of the accepted candidate/receipt/result identity literals, and
does not read the producer acceptance report. The report is used only by the
separate acceptance reviewer as a historical independent ledger.

## 2. Accepted source and target

| Artifact | Raw octets | SHA-256 |
|---|---:|---|
| parent runner | 50,461 | `5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7` |
| runner qualification test | 17,493 | `431f3ea5f41c87a5635cb2b5b44f24c548ecc4983c8c3acd02a6b5ab2d7a976c` |
| independent reviewer | 25,387 | `22565dfb4456823377bcea41790888531f0def2d645c7dd4a2d6f272c0bd26eb` |
| acceptance report | 12,969 | `ae315492c9a7fa24968c3132e5e0f9982693175922db845312a74f3e61e0487a` |

Acceptance report semantic ID:

```text
ee39ba2ee328f20774ed3c678d6bf9edf4790a68a587c591828813c358f0ca9b
```

The producer and verifier remain byte-identical to their accepted sources:

- producer: 129,026 octets,
  `46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da`;
- verifier: 373,327 octets,
  `b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25`.

The runner selects cases `5, 24, 54, 69, 435, 475` from the versioned
successor target. Case 435 therefore uses corrected plan
`343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8`.
The predecessor target and its runner-absent result remain historical
expected-red evidence; they are not the active runner qualification.

## 3. Process and transaction guarantees

The accepted implementation provides:

- fixed `fork -> setrlimit -> execve -> wait4` child execution;
- Python isolation flags `-I -S -B` and a minimal deterministic environment;
- no shell, dynamic code loading, role imports, or shared executable code;
- frozen CPU, address-space, file-size, open-file, wall, temporary-storage,
  staging-storage, and diagnostic limits;
- bounded nonblocking diagnostic capture and process-group termination;
- source and parent-owned authority snapshots rechecked after every child and
  immediately before publication;
- complete candidate closure snapshots before and after verifier execution;
- strict regular-file, single-link, private-mode, canonical-JSON, identity,
  receipt/result binding, and closure reconstruction;
- one private sibling transaction for all six cases;
- complete rollback on child, resource, semantic, drift, or publication
  failure; and
- one root-last parent rename followed by directory `fsync`.

The storage observer initially exposed one legitimate atomic-publication race:
a private child path could disappear after enumeration and before `lstat`.
The final implementation tolerates only that transient `FileNotFoundError`
during concurrent storage observation. It still strictly validates the closed
root after `wait4`; symlinks, special files, aliases, wrong modes, missing
members, and unexpected members remain rejecting.

## 4. Determinism, check mode, and rejection evidence

The independent reviewer observed:

```text
direct parent transactions: 2
producer child runs:         12
verifier child runs:         12
byte determinism:            VERIFIED
candidate immutability:      VERIFIED
read-only check:             VERIFIED
all-or-nothing publication:  VERIFIED
```

The two parent roots had byte-identical manifests and complete closure
snapshots. Check mode reconstructed the current source authorities, six case
entries, all child/result links, manifest semantic identity, and all 18 F2
aggregates without changing a byte or mode.

Invalid CLI, a pre-existing write root, a malformed check root, and an
internally injected mid-transaction child failure all reject with no accepted
root, no repair, and no private leftover. The internal injection is a test
seam, not a public CLI flag.

## 5. Whole-run F2 reconciliation

| Metric | Aggregation | Six-case value | Frozen F2 full run |
|---|---|---:|---:|
| scope cases | SUM | 6 | 475 |
| logical descriptor occurrences | SUM | 4,239,080 | 29,190,144 |
| recurrence state entries | SUM | 375 | 66,560 |
| recurrence transition attempts | SUM | 2,318 | 417,792 |
| logical unbatched transition equivalents | SUM | 8,756,229 | 170,915,840 |
| recurrence batch applications | SUM | 17 | 2,048 |
| cache entries | SUM | 375 | 66,560 |
| cache-key canonical octets | SUM | 254,204 | 45,088,768 |
| derivation canonicalization input octets | SUM | 1,840,387 | 329,252,864 |
| derivation canonicalization output octets | SUM | 2,057,687 | 368,050,176 |
| derivation hash-preimage octets | SUM | 3,473,350 | 619,708,416 |
| intrinsic-rule evaluations | SUM | 22 | 5,120 |
| cross-rule evaluations | SUM | 12,533 | 4,199,424 |
| application evaluations | SUM | 139 | 47,104 |
| maximum derivation depth | MAXIMUM | 17 | 17 |
| maximum iteration depth | MAXIMUM | 137 | 569 |
| peak retained derivation octets | MAXIMUM | 50,016 | 57,344 |
| derivation-result canonical octets | SUM | 87,245 | 15,728,640 |

All values are reconstructed from independently verified result artifacts.
No pilot observation changed, raised, rounded, or repaired an F2 limit.

## 6. Test evidence

The frozen acceptance report records:

```text
runner qualification suite: 7 passed
frozen A4-T role contract:   64 passed
```

The qualification suite covers static separation, exact authority bytes,
two-run output validation, read-only check behavior, invalid and collision
paths, injected rollback, and leftover absence. The independent reviewer
separately launches two complete transactions and reconstructs the historical
case ledger and F2 vector rather than importing either the runner or its test.

## 7. Gate transition and nonclaims

`A4-P6-R` is accepted. The single mutable Stage-1 pointer moves to
`A4-P6-E`, the independent six-case end-to-end acceptance packet. That packet
must decide whether the complete successor pilot evidence is sufficient to
release the 475-case campaign; it may not re-implement or silently tune the
accepted runner, producer, verifier, or limits.

This checkpoint does not accept `A4-P6-E`, the 475-case result run, Raw V8
Step 2, Stage 1, Stage 2, paper/live trading, predictive edge, safety, or
profitability. Formal Stage 1 remains `NO-GO`.


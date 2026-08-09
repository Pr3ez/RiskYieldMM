# Raw V8 Step-2 V2 dual-preflight comparator acceptance

Date: 2026-08-09  
Status: **ACCEPTED A2-C — FINAL A2-E PACKET PENDING**

## 1. Decision

The fixed-path parent comparator is accepted for the S1-A2 preflight boundary.
It independently validates the identity-pinned contract, seed, A source, and B
source; proves source/import separation; launches both implementations through
the frozen isolated child boundary; validates both closed semantic payloads;
captures nonsemantic execution evidence through parent-owned `wait4`; and
requires exact semantic-byte agreement before publishing one final comparison
payload.

The accepted execution path is:

```text
secure-read and identity-check frozen contract, seed, A, B, comparator
  -> AST import/call/path and algorithm-marker checks
  -> distinct device/inode and source-hash checks
  -> pre-exec source drift check
  -> fork -> setrlimit -> execve Python -I -S -B
  -> bounded nonblocking stdout/stderr capture and monotonic watchdog
  -> wait4 CPU/RSS observation plus allocated-block storage observation
  -> post-exec source drift check
  -> independent closed payload/schema/identity/F0 validation
  -> exact A/B bytes, 475 cases, 18 summaries, count vector, semantic ID
  -> cleanup all private staging
  -> atomic no-overwrite publication of comparison payload
```

This closes `A2-C`. It does not close `A2-E` or `S1-A2`; those require the
combined frozen A/B/comparator packet, fresh predecessor/regression evidence,
the current execution-ledger update, and a scoped leftover audit.

## 2. Frozen implementation artifacts

| Artifact | Raw octets | Raw SHA-256 |
|---|---:|---|
| `scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py` | 52,732 | `e0527f10a4ccb18891d18b8910101066bbc01ab57eebc2e3b18338d7c6f4f793` |
| `tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py` | 10,113 | `3ed939f99c84e951dab94d265999a41e892370308c5e9f501ade489313edd029` |

The comparator imports only `ast`, `hashlib`, `json`, `os`, `pathlib`,
`resource`, `signal`, `sys`, and `time`, exactly within the frozen comparator
allowlist. It does not import repository code, test helpers, subprocess,
network libraries, dynamic import machinery, or either implementation.

## 3. Durable exact-agreement result

Two final-source CLI runs produced identical canonical-pretty comparison
bytes. The final directory contained exactly one mode-`0600` file and no
private staging residue.

| Observation | Value |
|---|---|
| Comparison status | `EXACT_AGREEMENT` |
| Comparison raw octets | 1,206 |
| Comparison raw SHA-256 | `1c09d456294f4c7271f9513c2ebac5de02324e60365ff29f26609482bdd6a8b0` |
| Comparison payload ID | `e5c8d49f7434f1f295c77dc7c625508d798f7ac872eacf0ff4c0ce0e18768c8d` |
| A source SHA-256 | `beaf9405b7281508c046ad4d0735a70971ea4121c27fadb92d6b6401ccfe9d25` |
| B source SHA-256 | `de618350fc5c5c48d998de7ae49449f9edca0eff25161bde07cf271c22e47954` |
| Common semantic raw octets | 1,702,217 |
| Common semantic raw SHA-256 | `27d583074ed3b684d969644222ce025791e85fd7f28578b1ef9ca6fd6e573081` |
| Common semantic payload ID | `d51f81fe078309ee817a4f7ab93be3891ef4fbb5aab45e41b8e0d60ce3103c1b` |
| Common count-vector SHA-256 | `a9d7cd1ce1cb0aa6dccb175a5a1c49e69f1e672e18a9b4419ccbcdfedc1f79a8` |

All four comparison booleans are exactly `true`: semantic bytes, all 475 case
records, all 18 metric summaries, and all resource limits.

Only the frozen comparison schema is published durably. Each child report is
constructed and validated in memory as exactly `semantic_payload` plus
`execution_envelope`. The boundary does not define another outer durable
wrapper schema, so the comparator does not invent one.

## 4. Parent-owned resource evidence

Final telemetry capture used CPython 3.12.12. Resource observations are not
part of semantic identity and can vary between runs.

| Observation | A | B | Frozen ceiling |
|---|---:|---:|---:|
| Wall nanoseconds | 55,499,309,063 | 42,677,045,446 | 14,400,000,000,000 |
| CPU nanoseconds | 55,475,453,000 | 42,662,703,999 | 28,800,000,000,000 |
| Peak RSS octets | 107,794,432 | 121,065,472 | 2,147,483,648 |
| Temporary storage octets | 1,703,936 | 1,703,936 | 4,294,967,296 |
| Semantic output octets | 1,702,217 | 1,702,217 | strictly below 16,777,216 |
| Stdout octets | 0 | 0 | 1,048,576 capture cap |
| Stderr octets | 0 | 0 | 1,048,576 capture cap |
| Exit code | 0 | 0 | 0 |

The empty diagnostic hashes are the standard SHA-256 of empty bytes,
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## 5. Failure and cleanup behavior

The comparator rejects and publishes nothing when any of these conditions is
observed:

- an altered contract, seed, source path, source inode, source hash, algorithm
  marker, import root, dynamic call, or additional repository path;
- source drift immediately before or after child execution;
- fork, limit, exec, watchdog, wait4, pipe, RSS, CPU, wall, temporary-storage,
  staging-storage, output-size, or diagnostic-capture failure;
- a nonzero/noisy child, missing/partial/extra output, noncanonical JSON,
  schema/type/order/identity error, or F0 overrun;
- any semantic-byte, case, metric, count-vector, or semantic-ID disagreement;
  or
- an existing output, nonprivate parent, symlink, atomic-link failure, or
  invalid published mode/size.

Parent-side observation exceptions kill and reap a still-running child before
returning. Publication failures attempt rollback and directory fsync; success
uses `O_EXCL` staging, fsync, hard-link no-replace, temporary unlink, and parent
directory fsync.

## 6. Acceptance evidence

```bash
ruff check \
  scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py

ruff format --check \
  scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py

python -m py_compile \
  scripts/tests/compare_raw_v8_step2_maximum_protocol_v2_preflights_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_preflight_comparator_v49f.py
```

Observed result:

```text
ruff check: All checks passed
ruff format --check: 2 files already formatted
py_compile: PASS
pytest: 8 passed in 100.59s
final CLI: exit 0, empty stdout, empty stderr
repeated comparison payload: byte-for-byte identical
```

The tests include hostile semantic mutation, deliberate raw-byte disagreement,
RSS overrun, same-source substitution, source-hash drift, no-overwrite, bounded
invalid invocation, exact comparison identity, and the real isolated A/B run.

## 7. Remaining limitations and nonclaims

- A and B can still share a mistaken interpretation of the same frozen seed;
  exact agreement does not mathematically prove the market-system design.
- `wait4.ru_maxrss` and allocated `st_blocks` are Linux observations of this
  run, not universal cross-platform measurements.
- A2-C is a counting-only feasibility gate. It constructs no maximum witness,
  changes no F0/F1/F2 authority, and activates no trading behavior.
- This record does not accept `A2-E`, `S1-A2`, `S1-A3`, constructive maximum
  evidence, Raw V8 Step 2/3, Stage 1, offline Stage 2, provider/live behavior,
  predictive edge, safety, or profitability.

## 8. Next bounded action

Run the complete frozen S1-A1/S1-A2 regression and drift matrix, reconcile the
Stage 1 execution control, audit scoped and unrelated leftovers, and publish
the combined read-only `A2-E` acceptance decision. Any predecessor drift or
test failure returns `S1-A2` to NO-GO rather than being waived.

# V4.9F-A2 Raw V8 Initializer Technical Acceptance

**Audit date:** 2026-07-26  
**Decision:** Technical **GO** for the initializer sub-slice only  
**Parent gate:** Raw V8 Step 3 remains **NO-GO**

## Scope

This audit accepts only construction, committed-state classification, and
reopen behavior for the private empty Raw V8 projection profile. It does not
accept lifecycle records, target receipt grammar, marker closure, generated
bounds, full Raw V7/adjacent regression reacceptance, Raw V8, A2-M, Stage 1,
production readiness, trading edge, or profitability.

The governing corrected protocol is
[`v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md`](v4_9f_a2_raw_v8_step3_projection_lifecycle_protocol_freeze_2026-07-25.md).

## Accepted implementation

The initializer now provides:

- one profile-neutral persistent provisioning lock pathname per lexical
  database pathname;
- a V8-only owned, non-group/world-writable parent-directory precondition;
- descriptor/path lock identity checks before use and on both normal and
  exceptional release;
- an exact zero-application-object classifier for crash-left uninitialized
  files;
- schema DDL and parameterized metadata in one `BEGIN IMMEDIATE` transaction;
- fresh-connection resolution of a lost COMMIT acknowledgement;
- explicit rollback of a failed COMMIT that leaves a transaction active;
- non-destructive V8 failure handling that preserves uncertain or corrupt
  files for later diagnosis;
- typed distinction between SQLite contention and corrupt/unreadable input;
- final main-path device/inode validation before constructor success and
  during runtime use;
- rejection of database-path replacement, hard-link aliases, and symlink
  aliases; and
- a Raw V7 no-op policy hook that preserves its historical writable-parent
  behavior.

Raw V8 requires the named main database to remain one regular file with one
link. Both the path identity and the provisioning-lock identity are checked
while their relevant authority is still held.

## Direct evidence

The final combined focused command passed:

```text
python -m pytest -q \
  tests/test_trading_physical_projection_v49f_v8_profile.py \
  tests/test_trading_physical_projection_v49f_schema_profile.py \
  tests/test_trading_physical_projection_v4.py

38 passed in 7.14s
```

Static checks passed:

```text
python -m ruff check \
  riskyieldmm/trading/physical_projection_v4.py \
  riskyieldmm/trading/physical_projection_v49f_v8.py \
  tests/test_trading_physical_projection_v49f_v8_profile.py

python -m py_compile \
  riskyieldmm/trading/physical_projection_v4.py \
  riskyieldmm/trading/physical_projection_v49f_v8.py \
  tests/test_trading_physical_projection_v49f_v8_profile.py
```

The adversarial matrix directly covers:

| Area | Evidence |
|---|---|
| Fresh/reopen | exact empty V8 surface, stable ledger identity, full verification |
| Profile isolation | private V8 surface; V7/V8 substitution rejects both ways |
| Pre-COMMIT faults | before schema, after schema, after metadata, before COMMIT |
| Post-COMMIT uncertainty | injected acknowledgement loss and unusable original connection resolve through fresh replay |
| Process death | real `os._exit` cuts at five initialization boundaries |
| Contention | active-transaction `SQLITE_BUSY` rolls back and a later opener initializes cleanly |
| Concurrency | two V8 creators converge; V7/V8 racers select exactly one profile |
| Forensics | partial schema and non-SQLite bytes are retained and rejected with typed errors |
| Path integrity | replacement after replay rejects while displaced A and replacement B both remain reopenable |
| Alias integrity | hard-link and symlink aliases reject; the canonical path remains valid |
| Lease integrity | broad permissions, writable V8 parent, lock inode replacement, and replacement plus body failure reject |
| Raw V7 preservation | exact schema/profile tests pass and V7 retains its no-op protected-parent hook |

An independent adversarial re-audit reproduced the final-path replacement,
hard-link, lock-loss, and Raw V7 writable-parent cases and returned technical
GO for this slice.

## Frozen candidate profile evidence

The current schema candidate remains:

| SQL text | UTF-8 bytes | SHA-256 |
|---|---:|---|
| Raw V7 base | 136,483 | `d4b311050f20f03159cd7d121421535e36f45a1d56d42022345ab9fdfcf088e5` |
| Raw V8 extension | 8,356 | `a2bd6ea860ad100f83c148f51ce045e6f3dc9bc899faf0cba42b02f0134e4e3f` |
| Raw V8 full SQL | 144,839 | `92f3b635aa9909c1bd859b6a9a7ca798ec0aae47c042c70cd619c49858c0fc03` |

The independently replayed candidate fingerprint is
`13e6fbb2e8c29153fb2f4856bcc544c5463fca0f0ac07fd9a9b07fbb7f648d81`.
These values must be regenerated if lifecycle correction changes the schema.

## Remaining gates

The initializer GO is intentionally narrow. Formal Step-3 progress still
requires:

1. complete Step-2 after the accepted canonical V3 parent/inventory by proving
   constructive byte maxima, closing work accounting/certification, and
   implementing production adapters and final compatibility;
2. rerun the exact 242-case Raw V7 direct inventory and the 558-case adjacent
   inventory on the final tree;
3. freeze causal target-span ownership and branch-exhaustive receipt grammar;
4. impose finite, pre-effect-enforceable ingress and local-shutdown work
   budgets;
5. complete operation-specific result lineage;
6. implement lifecycle records, persistence, recovery, marker/probe closure,
   and the independent bound generator; and
7. satisfy every remaining Step-3 acceptance row without leftovers.

The next active design gate is target-span ownership plus finite target
receipt/work bounds. No later lifecycle implementation should proceed until
that gate receives an independent GO.

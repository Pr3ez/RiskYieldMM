# V4.1 causal-selector protocol freeze

**Date:** 2026-07-14

**Status:** Implemented and focused-accepted; broader Stage 1 and live gates
remain open

**Predecessor:** `v4_physical_evidence_protocol_freeze_2026-07-14.md`

**Scope:** completed provider-originated 1-minute bars only

## Decision

V4.1 is a **fresh-genesis physical-projection revision**. It adds the
observation/provenance projection, causal selector, independent replay oracle,
and bounded selection-result commitment needed after the V4.0
storage-and-disposition slice.

It does not alter a V4.0 database in place and it does not inherit a V4.0
schema fingerprint, ledger identity, or protocol-profile identity. The new
record layer and projection use the explicit schema lineages
`riskyieldmm_physical_evidence_v4_1` and
`riskyieldmm_physical_projection_v4_1`. The implementation derives the schema
fingerprint, protocol-profile ID, and selection-query-spec ID from those exact
contracts; the acceptance artifact must record their tested values. A V4.0
database remains a reference fixture. A later migration gate may replay
verified history into a distinct V4.1 ledger, but migration is not part of
this slice.

```text
fresh V4.1 ledger genesis
-> immutable raw message and disposition
-> canonical derivation/revision plus typed observation/provenance projection
-> exact V4.1 cutoff and selector-policy binding
-> one transactionally stable dual-cutoff snapshot
-> indexed NOT EXISTS anti-successor selector
-> canonical ascending result tuple
-> independent canonical-record replay equality
-> bounded RFC9162 result commitment
```

The SQL selector and the replay oracle establish local deterministic query
correctness. The RFC9162 result tree commits the exact ordered tuple that was
selected. Neither mechanism is represented as a portable authenticated range
proof or as proof against a malicious SQLite store.

## Evidence grade

The following distinctions are binding:

- **External established mechanism:** SQLite transactions, `EXISTS`, window
  functions, indexes/query planning, and RFC9162 Merkle Tree Hash semantics.
- **Repository-specific frozen decision:** the dual clocks, UTC-grid rule,
  active-head definition, tie break, bounded fetch, replay algorithm boundary,
  leaf schema, and protocol binding.
- **Implementation checkpoint:** `physical_selection_v4.py` defines
  `PhysicalProtocolBindingV4`, `SelectionResultChunkV4`, and
  `ObservationSelectionProofV4`; `physical_projection_v4.py` persists and
  selects the V4.1 records.
- **Focused measured evidence:** the 22 selector-specific tests and the combined
  74-test V4 focused suite pass in the current workspace.
- **Broader evidence:** the repository-wide regression passes 1,320 tests with
  32 intentional skips; the remaining acceptance matrix,
  frozen-environment benchmarks, scale/soak tests, and health/gate transitions
  remain separate gates.
- **Deliberately not accepted here:** caller-supplied health, recovery, gate
  eligibility, live authority, or trading readiness.

## Implemented checkpoint

The focused selector/projection slice is implemented under these tested
identities:

```text
protocol_profile_id      = 3440bd2e529b4122a00e4aad75209ba89805e1fe91f8ff4bcc177899ae678e08
selection_query_spec_id  = 3af77e857ae32004a3077efda32c0448244ca270a13d08f06233574f708ac9bf
schema_fingerprint       = 549f22faf23ed70282257bfffa127c6ca94a9448e572478acd54eca8c01a43b3
```

The selector-specific command covering
`test_trading_physical_selection_v4_contracts.py` and
`test_trading_physical_selection_v4_projection.py` passed **22 tests**. The
combined focused V4 command covering those files plus
`test_trading_transparency_log.py`, `test_trading_physical_evidence_v4.py`, and
`test_trading_physical_projection_v4.py` passed **74 tests**. The focused plan
fixture proves use of `observation_revision_select_complete_bar_v4` for the
selector and `observation_revision_one_child_v4` for the anti-successor probe,
without a temporary ordering B-tree for the frozen production query shape.
The repository-wide suite passed **1,320 tests with 32 skipped**.

This is a functional selector checkpoint with repository regression coverage.
It is not the Stage 1 exit gate, a scale or live-authority certification, or
evidence of predictive edge or profitability.

## Frozen V4.1 protocol decisions

### 1. New lineage, not an in-place extension

V4.1 begins with a new empty canonical ledger and empty typed projection. The
following are new V4.1 identities and may not be copied from V4.0:

- ledger ID and genesis record;
- physical-projection schema version and fingerprint;
- protocol-profile ID;
- selection-query-spec ID;
- selector-policy IDs;
- record-kind registry containing derivation, revision, selection chunk, and
  selection proof records.

No `ALTER TABLE` upgrade, row copying, or reuse of an old fingerprint is an
accepted path for this functional slice. This rule prevents a partially
upgraded database from claiming the semantics of the completed selector.

### 2. Required observation and provenance projection

A normalized disposition is not selectable merely because it names an opaque
observation revision ID. In the same V4.1 database, admission must persist and
cross-check:

1. the canonical V3-compatible `ObservationDerivationV3` record;
2. the canonical V3-compatible `ObservationRevisionV3` record;
3. immutable typed derivation and revision rows;
4. the canonical `ProviderMessageDispositionV3` classifier provenance and
   `MessageDispositionV4` admission that name exactly those two records;
5. provenance from revision to derivation, disposition, physical message,
   capture segment, scope, and source receipt sequence;
6. the revision's logical observation key and optional direct parent;
7. the revision clocks, completion state, interval, source member, and value
   digest needed to reproduce eligibility without reparsing JSON.

For every canonical derivation/revision there is exactly one typed row, and
every typed row binds the canonical object identity and canonical content
hash. `UPDATE` and `DELETE` remain forbidden. A normalized disposition,
derivation, revision, provenance row, tree extension, and their canonical
receipts either commit together or none commit.

The projection independently verifies, rather than trusting the caller, that:

- the derivation has exactly the input message receipt named by the normalized
  occurrence;
- derivation output digest equals the revision value digest;
- disposition, derivation, revision, scope, adapter policy, source member,
  instrument mapping, asset, venue, contract, and timeframe agree;
- the revision's `source_receipt_sequence` names its canonical revision
  receipt, while `admission_receipt_sequence` names the later V4 disposition
  receipt that admits it to selection;
- a parent belongs to the same logical observation and is already admitted;
- correction chains are linear: one genesis, one current head, no fork, no
  re-parenting, and no skipped parent;
- `admission_receipt_sequence` strictly increases and `available_at_us` never
  decreases along a revision chain;
- a completed observation never regresses to provisional.

These constraints are prerequisites for the direct-successor selector; they
are not optional data-quality diagnostics.

### 3. Exact information cutoff

Each query binds one already committed `EvidenceCutoffV4`-lineage object and
uses both of its independent boundaries:

```text
revision.admission_receipt_sequence <= cutoff.cutoff_global_sequence
revision.available_at_us             <= cutoff.knowledge_cutoff_us
```

The protocol query spec calls the first field
`observation_admission_receipt_sequence`; its typed SQLite column is
`admission_receipt_sequence`.

Both comparisons are inclusive. Neither clock can substitute for the other:

- receipt sequence prevents a later ledger admission from being read through
  an earlier physical cutoff even if its semantic availability timestamp is
  old or backdated;
- availability prevents a record admitted by the ledger from becoming usable
  before its frozen information-availability time.

The selector additionally requires the same physical scope, source member,
dependency slot, and protocol binding. A cutoff ID, its receipt hash, the two
boundary values, and its ledger/scope identities are checked as one object;
callers may not submit detached integer cutoffs.

### 4. Eligible observation domain

The first V4.1 selector accepts only provider-originated completed one-minute
bar revisions. Every candidate must have:

```text
observation_kind    = BAR
completion_state    = COMPLETE
interval_us         = 60_000_000
bar_close_us        = bar_open_us + 60_000_000
bar_open_us mod 60_000_000 = 0
bar_close_us <= knowledge_cutoff_us
```

The grid origin is Unix epoch in UTC and intervals are half-open
`[bar_open_us, bar_close_us)`. Provisional or retracted bars, provider status
records, non-bar observations, off-grid bars, partially completed bars, and
derived higher-timeframe bars are outside this query specification. They fail
closed; they are not rounded, resampled, forward-filled, or silently skipped
into a valid window.

### 5. Active revision head

For an otherwise eligible revision `r`, the active head at the query cutoff is
defined by the absence of its direct child satisfying both cutoffs:

```sql
NOT EXISTS (
    SELECT 1
    FROM observation_revisions AS successor
    WHERE successor.parent_observation_revision_id = r.observation_revision_id
      AND successor.admission_receipt_sequence <= :cutoff_global_sequence
      AND successor.available_at_us <= :knowledge_cutoff_us
)
```

Checking the direct child is complete because admission enforces a linear,
monotone revision chain. If the direct child misses either inclusive boundary,
every descendant also misses at least that boundary. If the direct child
satisfies both, `r` is superseded. This equivalence must be property-tested
against full-chain traversal; it must not be assumed for unverified or legacy
rows.

### 6. Selector modes

V4.1 supports exactly three modes:

| Mode | Frozen result rule | Fail-closed condition |
|---|---|---|
| `EXACT_EVENT` | Active completed revision whose close equals the derived UTC-grid target close | Zero or more than one active row for the slot; age limit violated |
| `LATEST_AVAILABLE_ASOF` | Greatest eligible close at or before the target close, after the complete tie break | No eligible row; age/policy limit violated |
| `TRAILING_WINDOW` | Exactly `requested_count` active heads at the requested consecutive one-minute close slots ending at target close | Missing slot, duplicate slot, off-grid row, short window, or count outside `1..256` |

`TRAILING_WINDOW` is strict-grid only in this revision. Authoritative session
calendars and sparse-with-liveness selection require their own later query-spec
revision. `EXACT_EVENT` and `LATEST_AVAILABLE_ASOF` each require cardinality
one when selected. Any mode may return an explicit abstention proof with no
selected IDs and canonical reason codes. `TRAILING_WINDOW` is the persisted
wire name; contract code normalizes it to the existing in-process enum member
`DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS`.

### 7. Total ordering and bounded physical fetch

The canonical committed result order is ascending:

```text
bar_close_us ASC,
available_at_us ASC,
admission_receipt_sequence ASC,
observation_revision_id BLOB ASC
```

The raw 32-byte revision ID is the final total-order field; locale or textual
hex collation is never used. The complete tuple is frozen even where strict
chain and interval constraints make later fields redundant.

The optimized SQL path scans in the exact reverse order and uses a descending
bounded fetch. Trailing rows are reversed before continuity validation, and
every non-empty selected tuple is explicitly sorted into the frozen ascending
order before replay comparison, result serialization, or hashing. SQL fetch
order is therefore an optimization and never the canonical result order. The
bound tie-break-policy name is
`BAR_CLOSE_AVAILABLE_RECEIPT_REVISION_ID`.

The global result maximum is 256. `EXACT_EVENT` fetches at most two rows so a
duplicate active head becomes `EXACT_EVENT_MISSING_OR_AMBIGUOUS` rather than
being silently reduced to one. `LATEST_AVAILABLE_ASOF` fetches one row, and
`TRAILING_WINDOW` fetches the bound `requested_count`, which cannot exceed
256. The public contracts reject a requested count or result chunk of 257;
they never truncate it to 256. No caller-supplied SQL `LIMIT` is accepted.

### 8. Selected SQL shape and challengers

The implementation baseline is the correlated `NOT EXISTS` anti-successor
query over eligible history with a bounded descending result fetch and indexed
direct-parent lookup.

It was selected as the semantic baseline because it expresses the frozen rule
directly, retains the full revision row without aggregate reattachment, and
exploits the enforced direct-parent/monotone-chain invariant. It also gives the
independent replay oracle a structurally different implementation.

Two challengers remain mandatory benchmark alternatives, not silently
equivalent replacements:

| Candidate | Strength | Risk requiring measurement or extra proof |
|---|---|---|
| `NOT EXISTS` direct anti-successor | Closest expression of active-head semantics; bounded result fetch; direct indexed child probe | Eligible-history scan and correlated probe cost depend on indexes and data distribution |
| `ROW_NUMBER() OVER (PARTITION BY logical_observation_key ORDER BY ...)` | Compact latest-per-key formulation; useful independent performance challenger | May rank/materialize more history or require temporary sorting; final query still needs explicit output order |
| grouped `MAX` plus join-back | Familiar aggregate formulation | `MAX` on one clock does not identify the complete tie-broken row; join-back can duplicate ties and obscure dual-cutoff semantics |

Correctness is not chosen by a microbenchmark. All candidates must first
produce byte-identical canonical results on every adversarial fixture. A
challenger may replace the optimized SQL only through a recorded V4.1 protocol
implementation revision after it passes the same proof boundary, plan gate,
and frozen-environment benchmark.

### 9. Independent canonical replay

The slow replay oracle reconstructs query state from canonical ledger records
from genesis. It must not call the optimized SQL selector, consume its typed
candidate rows, reuse its anti-join helper, or trust its ordering.

The replay algorithm:

1. parses canonical `ObservationRevisionV3` records and independently filters
   them to the protocol-bound physical scope;
2. parses canonical `MessageDispositionV4` records and maps each observation
   revision to the disposition record's `first_receipt_sequence`, which is its
   admission receipt sequence;
3. applies the two inclusive cutoffs in ordinary application code;
4. marks a revision superseded when an eligible canonical child names it as
   parent;
5. applies the completed one-minute UTC-grid, mode, age, continuity, reason,
   and ascending-order rules.

Acceptance requires exact equality between SQL and replay for the ordered
revision IDs and canonical reason codes. The common contract code then derives
the status, result chunk, count, and root exactly once. The full-store
acceptance path must separately replay the receipt chain, canonical identities,
typed projection, and selection operation batches from genesis. A selector
mismatch fails closed as a projection verification error; the SQL answer is
not preferred merely because it is faster.

### 10. Bounded RFC9162 result commitment

V4.1 stores zero or one result chunk. A non-empty chunk contains the exact
canonical ascending tuple of at most 256 revision IDs. For zero-based ordinal
`i`, its application leaf input binds:

```json
{"domain":"RiskYieldMMPhysicalSelectionResultLeafV4","observation_revision_id":"<64 lowercase hex characters>","ordinal":0}
```

The result root is the RFC9162 Merkle Tree Hash over those application leaf
inputs in ordinal order:

```text
leaf_hash(d)    = SHA256(0x00 || d)
node_hash(l, r) = SHA256(0x01 || l || r)
empty_root      = SHA256("")
```

`SelectionResultChunkV4` binds chunk ordinal zero, physical scope ID,
`PhysicalProtocolBindingV4` ID, evidence cutoff ID, and the exact ordered
revision-ID tuple. Its serialized `selected_result_count` and
`selected_result_root` are deterministic functions of that tuple.
`ObservationSelectionProofV4` then binds the chunk ID, result count, and result
root without a circular request/proof identity. Duplicate IDs, ordinal gaps,
reordered IDs, tuple substitution, count/root disagreement, multiple chunks,
or more than 256 leaves are invalid.

Abstention has `selected_result_count = 0`, no chunk ID or revision-ID tuple,
canonical reason codes, and the exact RFC9162 empty root. A selected result has
count `1..256`, exactly one chunk, and no abstention reasons. There is no
cumulative list, pagination, or second chunk in V4.1.

This commitment proves the integrity and order of the result tuple presented
to the consumer. Ordinary RFC9162 membership does **not** prove that the SQL
range omitted no eligible row, that a preferred revision has no successor, or
that the database is honest. Local completeness remains the conjunction of
projection verification, deterministic SQL, and independent canonical replay.

### 11. Exact protocol binding

A V4.1 selection proof is valid only when all of the following are exact-equal
to registered immutable records:

- `PhysicalProtocolBindingV4`: physical scope, protocol/source/calendar
  manifests, feature schema, dependency slot, source-member ID and key,
  observation-selection policy, V4.1 query spec, mode, anchor lag, requested
  count, maximum age, continuity, 60-second interval, tie break, and freeze
  time;
- `SelectionResultChunkV4`, when selected: physical scope, protocol binding,
  evidence cutoff, chunk ordinal zero, and ordered revision IDs, with derived
  count and RFC9162 root;
- `ObservationSelectionProofV4`: physical scope, ledger, evidence cutoff ID,
  cutoff global sequence and receipt hash, knowledge cutoff, protocol binding,
  query spec, selection policy, dependency slot, source-member ID and key,
  observation cutoff, status, count, root, optional chunk, canonical reasons,
  and computation time.

The evidence cutoff ID resolves the bound tree size/root and the physical
scope resolves the primary adapter/classifier and instrument mapping. The
observation cutoff must exactly equal the evidence knowledge cutoff; target
close is deterministically derived from that cutoff, the 60-second interval,
and `anchor_lag_intervals`. A later physical gate may bind the resulting
`observation_selection_proof_id` into an `InformationSet`; the current proof
does not contain an `InformationSet` ID.

Changing any one of these values changes the enclosing selection-proof or
protocol-binding identity. A V3 proof, V4.0 cutoff without a V4.1 observation
projection, legacy evidence prefix, unregistered query specification, or
caller-assembled ID tuple cannot satisfy the binding.

The selector proof is still not a trading-admission gate. Exact binding stops
substitution; it does not independently establish health or economic
eligibility.

### 12. Transactionally stable selection snapshot

Cutoff resolution, typed candidate selection, canonical replay comparison,
result-chunk construction, and proof insertion occur under one explicit
transaction snapshot. When the proof is persisted, the store uses its
single-writer `BEGIN IMMEDIATE` path so no concurrent writer can advance the
projection between candidate selection and commitment.

The cutoff must pre-exist the transaction's new result records. Result records
receive later ledger sequences and cannot enter their own input set because
eligibility is capped by the bound cutoff global sequence. A failure in SQL,
replay, commitment, canonical insertion, or typed insertion rolls back the
entire result operation.

Readers never assemble a result from multiple implicit transactions or from
rows streamed while the same connection mutates the source tables.

### 13. Query-plan and benchmark evidence boundary

The semantic decision is frozen; its performance has not yet been established.
V4.1 therefore makes no current throughput, tail-latency, or 100,000-event
scale claim.

The implementation provides indexes or uniqueness indexes for:

- scope/source/timeframe/completion/grid close plus the reverse result order;
- unique direct-parent lookup and observation-key/cutoff traversal;
- logical observation key and revision-chain verification;
- canonical receipt/provenance joins.

`EXPLAIN QUERY PLAN` is used as acceptance evidence that the bounded-result
query and correlated successor probe use intended indexes and that a schema
change did not cause an accidental unbounded scan. Tests must match stable
semantic facts such as table/index use, not serialize SQLite's full human
description: SQLite explicitly warns that `EXPLAIN QUERY PLAN` output is for
interactive diagnosis and may change between releases.

Plan inspection is not a benchmark. The frozen acceptance environment must
record Python and SQLite versions, SQLite compile options, journal and sync
modes, filesystem, hardware, schema statistics/`ANALYZE` state, data volume,
revision depth and correction distribution, warm/cold cache protocol, and
concurrent-reader conditions. It must compare the three query shapes on
identical correctness-approved databases and report median, p95, p99, maximum,
rows visited where measurable, and database size. No latency threshold will be
invented after observing a failing run.

### 14. Health and physical-gate boundary

V4.1 does not accept a caller assertion that a cutoff or source is `HEALTHY`.
The existing `EvidenceCutoffV4` health fields are not sufficient to promote
selector output to a tradeable `InformationSet` because the deterministic
transition and recovery reducer has not yet been frozen and implemented.

The next physical subgate must freeze and test an explicit transition matrix
covering at least:

```text
prior state x disposition class x required status state x freshness/liveness
-> next state, reason codes, valid-until, recovery evidence, gate action
```

It must define blocker onset, persistence, recovery, cooldown, status absence,
staleness, gaps, conflicts, clock failures, and restart behavior. Health and
gate fields must be derived from canonical evidence; callers may request an
evaluation but may not choose its outcome.

Until that subgate passes:

- selection results are correctness/audit artifacts only;
- any production or paper-trading gate requiring healthy physical evidence
  fails closed or abstains;
- a caller-supplied `HEALTHY`, `SELECTED`, or gate-approved flag has no
  authority;
- no V4.1 artifact establishes live readiness, predictive edge, execution
  quality, profitability, or safety for capital.

## Why this is the selected design

The chosen design keeps the minimum trusted state needed for the next stages:

- dual cutoffs reproduce what the ledger had admitted and what was knowable;
- a strict completed 1-minute domain gives higher-timeframe aggregation a
  causal, auditable base without mixing partially completed candles;
- linear monotone correction chains make direct anti-successor selection both
  explicit and indexable;
- canonical ascending results decouple stable identity from a descending SQL
  optimization;
- the 256-result contract rejects a requested count or chunk of 257 instead of
  silently truncating;
- canonical replay catches projection, indexing, and query mistakes without
  sharing their implementation;
- the bounded result root lets later `InformationSet`, feature, model, and gate
  objects bind exactly what was consumed;
- fresh genesis avoids pretending that the narrower V4.0 projection already
  carried observation or selection semantics.

The design deliberately spends complexity on causal evidence and fail-closed
boundaries before model work. It does not claim that the chosen SQL shape is
the fastest, or that a cryptographic result root turns SQLite into an
authenticated range index.

## Acceptance matrix

| Area | Required evidence | Acceptance rule | Current status |
|---|---|---|---|
| V4.1 genesis | New ledger/schema/profile identities; empty-root fixtures; V4.0 open/reuse attack | V4.0 database cannot open or write as V4.1; V4.1 starts empty | Implemented; focused checkpoint passed; full row pending |
| Canonical/typed projection | Derivation, revision, provenance, disposition, and receipt fixtures | Exact canonical-to-typed bijection; immutable rows; atomic admission | Implemented; focused checkpoint passed; full row pending |
| Provenance | Wrong message, derivation, revision, scope, source member, mapping, or value digest mutations | Every mismatch rejected before commit | Implemented; focused checkpoint passed; full row pending |
| Revision chains | Genesis, correction, fork, skipped-parent, backward receipt/availability, completed-to-provisional fixtures | Only one linear monotone head per logical observation | Implemented; focused checkpoint passed; full row pending |
| Dual cutoffs | Admission-before/availability-after and availability-before/admission-after cases; inclusive boundary cases | A row is eligible only when both predicates hold | Implemented; focused checkpoint passed; full row pending |
| Completed UTC grid | Exact 1m, provisional, off-grid, wrong duration, future close, and HTF cases | Only completed epoch-aligned 1m provider bars enter | Implemented; focused checkpoint passed; full row pending |
| `EXACT_EVENT` | Missing, one, duplicate/corrupt active heads at target | Select exactly one or abstain/fail closed | Implemented; focused checkpoint passed; full row pending |
| `LATEST_AVAILABLE_ASOF` | Gaps, age boundary, ties, corrections around both cutoffs | Return the one greatest fully tie-broken eligible row or abstain | Implemented; focused checkpoint passed; full row pending |
| `TRAILING_WINDOW` | Counts 1 and 256; short, gapped, duplicate, off-grid, and requested-count 257 attacks | Exact consecutive grid and requested cardinality; reject 257 and never truncate | Implemented; focused checkpoint passed; full row pending |
| Canonical order | Reverse insertion, tied clocks, raw-BLOB ordering, descending SQL fetch | Committed/replayed tuple is byte-identical ascending order | Implemented; focused checkpoint passed; full row pending |
| SQL versus replay | Every cutoff boundary after every append; randomized chains and adversarial fixtures | Canonical reasons and ordered IDs are identical; common contracts derive status/chunk/count/root | Implemented; focused checkpoint passed; full row pending |
| Result commitment | Empty, 1, 256; omission, duplication, reorder, substitution, wrong ordinal/count/root; chunk size 257 | Exact RFC9162 root and one bounded chunk; every mutation rejected | Implemented; focused checkpoint passed; full row pending |
| Transaction snapshot | Concurrent append, injected failure after select/chunk/proof writes, reopen/retry | One stable snapshot; all-or-nothing result records; deterministic retry | Implemented; focused rollback/reopen passed; full row pending |
| Query plan | Recorded `EXPLAIN QUERY PLAN` for all modes and chain depths | Intended bounded-result and direct-parent indexes used; no accidental unbounded source scan | Named selector/successor indexes and no-temp-sort focused check passed; full plan matrix pending |
| Benchmark | Frozen environment; `NOT EXISTS`, `ROW_NUMBER`, and `MAX` challenger comparison | Correctness first; predeclared latency/scale gates pass without post-hoc threshold changes | Pending benchmark |
| Genesis verification | Full canonical receipt, projection, chain, selector-result, and root replay after reopen | Rebuild from genesis reproduces all identities and roots | Focused verify/reopen passed; full row pending |
| V3 compatibility | Existing V3.3 oracle and repository regression suite | No V3 semantic mutation or regression | Repository-wide suite passed: 1,320 tests, 32 skipped |
| Health transition reducer | Frozen blocker/recovery matrix and adversarial transition tests | Derived health only; no caller-selected healthy state | **Next subgate, not accepted here** |
| Physical trading gate | Exact binding plus derived health, liveness, status, and legacy-bypass attacks | V4.1 proof alone cannot authorize trading; all substitutions fail | **Next subgate, not accepted here** |

The selector/projection implementation slice has passed its focused checkpoint.
Stage 1 exit still requires every row marked pending to receive its broader
reproducible evidence while the health/gate boundary remains fail closed. Even
the completed matrix would prove protocol consistency, not a profitable
trading signal.

## Primary-source basis and limits

- SQLite defines [`EXISTS`](https://www.sqlite.org/lang_expr.html#the_exists_operator)
  as a Boolean test of whether a subquery returns a row. This supports the
  direct anti-successor expression; the active-head and dual-cutoff meaning are
  repository-specific.
- SQLite documents
  [`row_number()` and window ordering](https://www.sqlite.org/windowfunctions.html)
  and notes that window order does not itself determine final result order.
  This supports treating `ROW_NUMBER` as a challenger and retaining an explicit
  outer canonical order.
- SQLite's [query-planner documentation](https://www.sqlite.org/queryplanner.html)
  describes multi-column indexes and combined searching/sorting. Its
  [`EXPLAIN QUERY PLAN` documentation](https://www.sqlite.org/eqp.html) warns
  that the diagnostic output format may change. These sources justify plan
  inspection, not a latency claim.
- SQLite's [transaction documentation](https://www.sqlite.org/lang_transaction.html)
  and [isolation documentation](https://www.sqlite.org/isolation.html) define
  explicit transactions, the one-writer model, committed visibility, and
  snapshot behavior. They support the single-snapshot design; durability still
  depends on the separately frozen journal, sync, filesystem, and fault-test
  environment.
- [RFC 9162, Certificate Transparency Version 2.0](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1)
  defines the empty, leaf, and internal-node Merkle Tree Hash construction for
  an ordered list. V4.1 reuses that construction for a bounded application
  result tuple. RFC9162 does not define this selector, prove SQL range
  completeness, or authenticate SQLite projection semantics.

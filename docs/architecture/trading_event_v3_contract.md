# Trading Event V3 foundation contract

Status: implemented foundation; not yet connected to the legacy Analyst or RPF
pipelines; not a profitability or deployment claim.

This is the first gated implementation tranche from
`docs/research/trading_prediction_system_diagnosis_and_redesign_2026-07-14.md`.
It establishes one causal vocabulary for future historical replay, forward
paper trading, live evidence, split construction, and model trials.  It does
not change signal generation, position opening, UI behavior, or live trading.

## Design decision

The package uses dependency-free, frozen, slotted standard-library dataclasses
with explicit parsers and validators.

| Alternative | Decision | Reason |
|---|---|---|
| Loose dictionaries | Rejected for identity-bearing records | They permit missing/unknown keys, silent scalar coercion, nested mutation, and inconsistent hashing. Dictionaries remain boundary values only. |
| Pydantic models | Not selected for the protocol core | Pydantic is declared elsewhere in the repository but is absent from the active runtime. Its strict JSON mode still intentionally parses some strings into typed values, and frozen models provide only faux immutability for mutable nested values. It remains appropriate for API adapters later, not the dependency-free identity layer. |
| Frozen dataclasses | Selected | Exact constructors, no runtime dependency, predictable import surface, and explicit control over canonicalization and graph validation. Nested collections are tuples; manifest payloads are stored internally as canonical JSON text. |
| One monolithic trade row | Rejected | It lets future fills, barriers, outcomes, costs, or population weights rewrite the pre-outcome event identity. |
| Separate causal records | Selected | Information, eligibility, decision, barrier activation, outcome, and dependence assignment mature at different times and have different identity rules. |

Relevant primary documentation:

- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [Pydantic faux immutability](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability)

## Canonical identity protocol

`riskyieldmm_canonical_json_v1` is a deliberately smaller domain than general
JSON:

- UTF-8, compact JSON with lexicographically sorted object keys;
- no duplicate object keys;
- no binary floats, NaN, or infinity;
- integers restricted to the interoperable I-JSON range;
- financial values stored as canonical decimal strings, with at most 38
  significant digits and 18 fractional digits;
- exact RFC 3339 timestamps, normalized to UTC, with microsecond resolution;
- timestamp precision above six fractional digits is rejected rather than
  truncated;
- the unknown `-00:00` offset, naive times, datetime subclasses, and non-NFC
  identifiers are rejected;
- record/schema/domain names are included in every digest.

The protocol is inspired by [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html),
including its I-JSON and deterministic-ordering goals.  It is intentionally
not labelled full JCS: RFC 8785 relies on ECMAScript number serialization,
whereas this protocol prohibits floats in identity-bearing JSON and stores
exact financial numbers as strings.  This also closes Python `json` defaults
that otherwise accept non-finite numbers and repeated names; see the official
[Python JSON documentation](https://docs.python.org/3/library/json.html).

Golden bytes and SHA-256 vectors in the tests make a canonicalization change a
visible protocol migration rather than a silent ID rewrite.

## Causal record graph

```mermaid
flowchart LR
    D[InformationDependencyV3] --> I[InformationSetV3]
    I --> E[EligibilityDecisionV3]
    E --> V[DecisionEventV3]
    V --> A[BarrierActivationV3]
    A --> L[LabelOutcomeV3]
    V --> L
    L --> W[EventDependenceAssignmentV3]
    V --> W
```

### `InformationDependencyV3`

Binds one source revision and these clocks:

```text
source_event_ts
bar_open_ts
bar_close_ts
source_publish_ts (nullable only when the source does not provide it)
ingested_first_seen_ts
revision_received_ts
feature_available_ts
```

The accepted ordering requires a positive-duration bar, keeps the source event
inside that bar interval, and ensures that a completed observation,
publication, receipt, and feature readiness all precede the InformationSet
cutoff.  A future publication timestamp cannot be paired with an earlier
availability timestamp.

### `InformationSetV3`

Binds the exact source, calendar, universe snapshot, feature schema, causal
state checkpoints, raw revisions, cutoff, materialization hash, and data
quality.  It has two identifiers:

- `information_set_id`: semantic observation identity;
- `record_hash`: the exact materialization and certification attestation.

Eligibility binds both.  Therefore two feature materializations for the same
semantic inputs cannot be substituted under an existing eligibility/event
graph.  The future ledger writer must additionally reject a conflicting second
materialization as a determinism incident.

`NOMINAL_CURRENT_REVISION` is never point-in-time certified.  This prevents the
existing historical bars from being retroactively presented as first-seen
evidence.

### `EligibilityDecisionV3`

Represents only the deterministic primary-signal cohort decision:
`ELIGIBLE`, `INELIGIBLE`, or `ABSTAIN_DATA`.  It is not a portfolio, capital,
position, risk-budget, or order-acceptance decision.

The factory binds the exact InformationSet record and currently requires the
eligibility input-state hash to equal the feature-materialization hash.  An
eligible event cannot be produced from a stale, alternate, or differently
materialized feature record.

### `DecisionEventV3`

Contains only facts and policies frozen before entry:

- exact InformationSet and eligibility record hashes;
- scope and content-addressed primary candidate/policy;
- side, decision, order, entry-window clocks;
- action, label, barrier, and cost policy IDs;
- risk-unit distance, stop/target R multiples, and holding horizon;
- source vintage and certification.

Required order:

```text
InformationSet assembled
<= eligibility evaluated
<= decision
<= earliest order submission
< earliest executable entry
<= entry expiry
```

Fill price, stop/target prices, exit, score, model probability, portfolio
state, and realised PnL are deliberately absent from `decision_event_id`.

### `BarrierActivationV3`

Created only after an entry fill is observed.  It binds the exact entry
revision, price, time, activation clock, and deterministically computed stop
and target.  Stop and target must equal the pre-event risk unit multiplied by
the frozen stop/target R multiples.  This prevents an outcome label from
hindsight-selecting convenient barriers.

The record still needs the append-only receipt ledger in the next tranche to
prove that the activation was sealed before subsequent path resolution.

### `LabelOutcomeV3`

Appended later and linked to an unchanged decision and, for a filled event, the
exact barrier-activation record.  It models TP-first, SL-first, timeout,
ambiguous, no-fill, and cancelled outcomes; exact itemized conservative cost
deductions; path/evidence IDs; MAE/MFE/gap fields; and supersession.

The graph validator enforces:

- entry lies in the frozen entry window;
- execution mode matches historical, forward-paper, or live entry scenario;
- a timeout matures exactly at the frozen holding deadline;
- no-fill matures at entry expiry;
- label barrier evidence starts when the frozen barriers become active for a
  fill, or at earliest entry for an unfilled order; holding/PnL still begins at
  the actual fill;
- TP-first and SL-first records bind an explicit trigger time, trigger price,
  and evidence-revision ID; the trigger must reach the frozen barrier, and a
  nominal historical or forward-paper exit must respect the same geometry;
- exact LONG/SHORT gross basis-point return and R-multiple recomputation using
  decimal arithmetic and half-even rounding to `1e-8`;
- net return equals gross return minus itemized deductions;
- an ambiguous path cannot choose caller-supplied favourable bounds: its gross
  lower and upper bounds are recomputed from the frozen stop-first and
  target-first scenarios, while exit price, gross return, and R multiple use
  the conservative stop-first result.

Costs are currently explicitly conservative nonnegative deductions.  Maker
rebates and signed funding/borrow cash flows require a later signed economic
adjustment contract; they must not be smuggled in as negative costs.

### `EventDependenceAssignmentV3`

Overlap clusters, concurrency, and uniqueness weights are population-derived.
They therefore live outside the intrinsic label identity.  The assignment
binds the complete dependence interval from earliest entry through
`label_known_ts`, the dependence policy, event/outcome IDs, assignment clock,
and supersession.  The split engine must resolve these before certifying folds.

## Experiment-manifest graph

`ImmutableManifestV3` uses a five-field content-addressed envelope:

```text
canonicalization_version
schema_version
manifest_type
payload
manifest_id
```

Supported exact payload types are:

```text
SOURCE -> PROTOCOL -> SPLIT -> TRIAL_SPEC -> TRIAL_RESULT
```

Source snapshots carry a stable source-contract ID and parent snapshot.  This
allows prospective first-seen data to extend the frozen source lineage without
rewriting the protocol.  Protocols bind data/schema policies, signal and
eligibility policies, action/label/barrier/cost policies, evaluation
governance, code/workspace/environment, metrics, split policy, and holdout
policy.  Trial results bind the effective source, split, protocol, code,
workspace, and runtime environment; successful results must match the frozen
protocol.

The split-policy ID is itself derived from the exact purge policy, embargo
policy, and complete TRAIN/VALIDATION/CALIBRATION/POLICY/TEST role set.  A split
cannot silently substitute any of those components while retaining the
protocol's policy identity.

`validate_manifest_graph()` resolves types, source ancestry, clocks, protocol
and split agreement, parent-trial family/order, and successful-run bindings.
Parsing one manifest in isolation does not establish those properties.

The split payload contains an immutable cohort class (`DEVELOPMENT`,
`QUARANTINE_CANDIDATE`, or `FINAL_HOLDOUT`).  Mutable access/opening state is
reserved for the governance receipt ledger, so opening a holdout does not
rewrite split identity.  Every split binds the protocol's holdout-policy ID,
and the graph validator permits only one `FINAL_HOLDOUT` split per protocol in
a complete registry, preventing selection among multiple observed holdouts.

`validate_record_protocol_graph()` closes the boundary between the two graphs:
it validates the InformationSet/eligibility/event chain, resolves the selected
source lineage, and requires the frozen source, vintage, calendar, universe,
feature schema, eligibility, primary-signal, action, label, barrier, and cost
policies to match the protocol exactly.

## Mandatory persistence rule

`from_mapping()` proves only canonical syntax, local invariants, and content
hashes.  It never proves that referenced records exist or that a declared time
was truthful.  A certified ledger append must:

1. resolve the referenced InformationSet, eligibility, decision, activation,
   outcome, dependence, source, protocol, split, and trial records;
2. call every `validate_against()`, `validate_manifest_graph()`, and
   `validate_record_protocol_graph()` method;
3. enforce one authoritative active head per semantic key and acyclic,
   monotone supersession;
4. reject conflicting materializations and duplicate-key conflicting writes;
5. append a receipt containing sequence, received-at, object ID, previous hash,
   and record hash;
6. checkpoint/sign the receipt chain before a record is allowed to support a
   prospective holdout or pre-outcome claim.

A content hash detects changed content.  It does not prove when that content
first existed.  No current V3 record should be described as prospectively
sealed until that ledger tranche is implemented and tested.

## Explicit remaining gates

The foundation deliberately stops before pipeline migration.  The next gate
must implement and independently test:

1. append-only event/manifest receipt stores, active-head and idempotent-write
   rules, crash/concurrency recovery, and signed/checkpointed sealing;
2. source-bundle membership and feature-schema dependency slot/cardinality
   validation, including multi-source features;
3. calendar/action resolution proving the next eligible tradable bar and entry
   expiry for every supported asset/timeframe;
4. a revision-clocked path-evidence manifest plus an independent first-touch,
   gap, MAE/MFE, ambiguity, and label verifier;
5. an Arrow/Parquet physical schema and round-trip tests for every exact field;
6. signed funding/rebate/borrow adjustments if actual rather than conservative
   cost accounting is required;
7. deterministic cluster construction and interval-aware split certification;
8. adapters that produce identical V3 graphs from Analyst replay, forward
   paper, live inference, and RPF without changing current behavior during the
   shadow comparison.

Only after these pass should model baselines or feature expansion begin.

## Verification surface

- `tests/test_trading_event_contracts_v3.py`: canonical bytes, clocks,
  publication poison, nanosecond rejection, strict persisted scalars,
  certification, graph binding, barrier geometry, exact economics, timeout,
  ambiguity, no-fill, supersession, and separated dependence metadata.
- `tests/test_trading_manifests_v3.py`: exact schemas, deep immutability, golden
  IDs, status lifecycle, subsecond chronology, source lineage, protocol/split/
  trial graph checks, and frozen successful-run bindings.

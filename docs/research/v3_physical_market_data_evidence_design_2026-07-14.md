# V3.3 physical market-data evidence and promotion gate

Date: 2026-07-14  
Status: reference vertical-slice implementation checkpoint; acceptance and live promotion remain blocked  
Tracking: [RIS-270](https://linear.app/riskyieldmetamodelalgorithm/issue/RIS-270/implement-v33-physical-market-data-evidence-gate)

## Decision

V3.3 uses prospectively captured, bounded raw provider-message segments as its
authority. Normalized bars are deterministic derived observations. A trading
decision is eligible only when the ledger can reconstruct the selected rows
from a finite, healthy evidence prefix and reproduce the exact dependency
values and clocks carried by `InformationSetV3`.

This is the selected architecture:

```text
exact provider bytes
→ bounded immutable capture segment
→ exactly one immutable typed disposition per message occurrence
→ zero/one deterministic parser derivation and observation revision
→ finite evidence prefix and active revision heads
→ recomputed exact/latest/trailing selection proof
→ InformationSetV3 equality check
→ PASS or typed ABSTAIN physical gate
→ V3.2 action/candidate/decision graph
```

The code now exercises this reference graph through governance-ledger candidate
admission for the narrow Bybit fixture scope. It does not exercise an actual
paper/live activation: `ActionProtocolV3` currently supports only
`NEXT_SCHEDULED_BASE_BAR_OPEN`, while opaque legacy forward/live behavior has
not been migrated. It is a **reference implementation**, not a
live-ready ingestion subsystem or a completed V3.3 acceptance result. In
particular, its in-memory/full-history registry and cumulative prefix objects
are deliberately simple audit scaffolding. They must be replaced by bounded,
indexed, streaming structures before a continuous feed is allowed to use the
path.

Normalized-only tables remain useful query caches and nominal historical
research inputs. They cannot prove provider finality, first-seen time, omitted
messages, correction history, feed state, or the parser that produced a value.

External WORM storage or a transparency log can later attest that a committed
ledger prefix existed no later than an external acceptance time. It is a
security overlay, not an ingestion model: retroactive upload cannot turn a
historical download into prospective first-seen evidence.

## Why this gate is necessary

The current V3.2 contracts correctly bind logical source membership, clocks,
revision identity, slot cardinality, candidate grain, scheduled actions, and
ledger order. They do not prove that a declared row exists in captured provider
data or that a `LATEST_AVAILABLE_ASOF` or trailing window omitted nothing.

The physical audit found these production blockers:

| Severity | Confirmed implementation fact | Consequence |
|---|---|---|
| P0 | `Risk_Yield_Meta_Model_Analyst_0_0_1/forward_paper/sources.py:111-203` and `:386-459` call Bybit REST and infer completion from nominal close plus five seconds | No provider `confirm=true`, exact raw message, publication/revision, or stream-state proof |
| P0 | `Risk_Yield_Meta_Model_Analyst_0_0_1/forward_paper/service.py:332-346` instantiates the legacy `EventStore`, not `V3GovernanceLedger` | Forward signals/orders/fills bypass the V3 causal graph |
| P0 | `Risk_Yield_Meta_Model_Analyst_0_0_1/forward_paper/stream.py:795-834` reports a gap and can still submit the first later row to pending-order fill logic | An unproven recovery row can change realised PnL |
| Corrected in code; old artifacts P0 | `scripts/feature_engineering/htf_trading_calendar.py:368-399` still computes descriptive session-end fields from a segment maximum/`shift(-1)`, but `regression_feature_engineering/features/regime_calendar_state.py` no longer exposes `session_progress`, `minutes_to_close`, `session_close`, or `weekly_close` as model inputs | Every old feature root, catalog, diagnostic, or model containing those fields is quarantined and must be rebuilt; removal from current code does not rehabilitate historical results |
| P0 | `scripts/feature_engineering/materialize_canonical_ohlcv.py:257-290` chooses a provider collision winner and drops provider lineage | A canonical row cannot be bound back to exact provider bytes |
| P0 | `fetchingMultiAsset/asset_config.py:159-248` uses continuous/vendor aliases and Yahoo futures proxies | No exact executable listed-futures contract |
| P1 | Twelve Data can persist the active forming candle; Yahoo remains delayed/proxy data | Neither source can currently authorize a live trade |

Therefore no current asset is V3.3 trading-authorized. Existing charts, replay,
and paper results remain diagnostics until they pass this gate.

## Provider research conclusions

### Bybit

The official [Bybit public kline WebSocket specification](https://bybit-exchange.github.io/docs/v5/websocket/public/kline)
defines `confirm=true` as a closed candle and `confirm=false` as an open candle
that can continue updating. It supplies the bar start, millisecond end,
provider message timestamp, last-match timestamp, OHLCV, and turnover.
It does not document a kline update sequence or immutability guarantee.

Consequences:

- Every wire arrival must be retained before disposition/deduplication.
- `confirm=false` is captured but never selectable.
- The reference ledger now classifies every occurrence exactly once. An exact
  duplicate remains a distinct receipt occurrence with a typed duplicate
  disposition and does not create a second normalized revision.
- A different second `confirm=true` value creates a successor revision and an
  integrity incident; it never rewrites an earlier information prefix.
- Provider timestamps are event/publication metadata. Local durable ledger
  receipt time is the causal first-seen authority.
- The adapter treats the kline `end` value as inclusive and converts it to a
  half-open interval by adding one millisecond. That interpretation is inferred
  from Bybit's millisecond endpoint examples and candle layout; it is not an
  independent exchange guarantee. Golden fixtures lock the adapter rule and a
  provider contract change must fail closed.

The official [REST kline specification](https://bybit-exchange.github.io/docs/v5/market/kline)
has no completion flag and explicitly says the current unclosed candle's close
is the last traded price. REST is therefore reconciliation/recovery evidence,
not equivalent trading finality.

The [instrument-info endpoint](https://bybit-exchange.github.io/docs/v5/market/instrument)
supplies current instrument status and executable constraints. It is captured
prospectively and must say `Trading`; an unknown, stale, missing, prelaunch, or
non-trading status abstains. It is not treated as historical status history.

The [WebSocket connection guide](https://bybit-exchange.github.io/docs/v5/ws/connect)
warns that disconnection can occur at any time and recommends application
heartbeats. A pong proves connection liveness, not topic completeness. Bar
finality, continuity, connection generation, and freshness remain separate
checks. The [system-status endpoint](https://bybit-exchange.github.io/docs/v5/system-status)
is useful negative incident evidence, but Bybit states that short or immediately
recoverable interruptions may not be announced. An empty incident list cannot
alone make a feed healthy.

### Databento and futures

Databento distinguishes exchange event time, vendor receive time, and live
send time in its [common timestamp definitions](https://databento.com/docs/standards-and-conventions/common-fields-enums-types).
None is the time this application first durably received a later message.

The [Databento OHLCV schema](https://databento.com/docs/schemas-and-data-formats/ohlcv)
uses the interval start timestamp and emits no record for an interval with no
trade. Absence of a bar therefore cannot be interpreted as either a zero-volume
bar or a feed gap without independent liveness/status evidence. Databento's
live end-of-interval message can close a vendor publication interval, while
status, definition, symbol-mapping, and quality flags remain separate evidence.

Near-term futures design:

- Preserve raw DBN records and `ts_recv`, flags, status, definition, and live
  symbol mappings.
- Bind a continuous research alias to the concrete raw child contract known at
  the cutoff; never send the alias to execution.
- Pair an OHLCV record with the matching received end-of-interval evidence.
- Represent a legitimate no-record interval explicitly; never fabricate a
  candle.
- Eventually validate vendor bars against deterministically aggregated trades.

Direct CME MDP 3.0 would provide stronger packet sequence, dual-feed, and
recovery semantics, but its licensing and operational burden are not justified
until the Databento-backed shadow system demonstrates a concrete need.

## Architecture alternatives considered

| Alternative | Strength | Fatal limitation | Role |
|---|---|---|---|
| Versioned normalized rows only | Simple values/revisions and fast queries | Cannot reproduce provider parsing, captured omissions, raw corrections, or first-seen | Derived cache and nominal historical research only |
| Raw receipts plus deterministic derivation | Replays exact received bytes; preserves duplicates, corrections, finality/status, and causal selection | Proves what this collector recorded, not global provider truth | **V3.3 authority** |
| External WORM/transparency attestation | Independent prefix-existence and rollback resistance | Does not validate provider truth or normalization; late upload is late evidence | Optional later overlay |

Kafka, Flink, and Iceberg may be useful infrastructure later. Their retention,
watermark, snapshot, or exactly-once configurations do not themselves define
the evidence and causal-selection contract.

## Implemented contract surface

The physical schema is separate from existing V3.0/V3.1/V3.2 identities:

```text
riskyieldmm_physical_market_data_v1
```

### `ProviderAdapterPolicyV3`

Freezes one provider, endpoint, topic/schema, concrete instrument, transport,
parser and message-classifier release identifiers/hashes, the reviewed
feed-health reducer identity, source schema, availability/revision policies,
calendar, completion basis, freshness/clock limits, status requirement, and
permitted use:

```text
TRADING_AUTHORITY | RECONCILIATION_ONLY | RESEARCH_ONLY
```

The adapter policy ID is also the opt-in `source_contract_id`. Existing opaque
V3.2 source contracts remain readable but cannot pass V3.3 promotion.

The accepted parser version/hash pair is a **release allowlist** checked by the
contract. It does not attest which executable was loaded, which source tree was
built, or that those exact bytes processed a live message. Reproducible builds,
signed release provenance, and runtime executable attestation remain separate
promotion gates.

### `ProviderMessageEnvelopeV3` and `CaptureSegmentV3`

Each envelope stores exact raw bytes as canonical base64 plus their raw SHA-256,
collector wall and monotonic clocks, collector sequence, message kind, and any
provider clocks/sequence. Receipt identity includes the arrival occurrence, so
two identical deliveries remain distinct.

Segment construction enforces a conservative canonical-object budget below the
ledger's default one-megabyte object limit and forms a strict predecessor
chain. Collector sequences are contiguous, monotonic
clocks strictly increase within one boot domain, and connection-generation
changes are explicit.

Claim boundary: the segment proves what the collector persisted. It cannot
prove that an upstream network/provider emitted no unobserved message.

### `ProviderMessageDispositionV3`

Every captured message occurrence receives exactly one immutable disposition,
bound to its adapter policy, segment, raw-message receipt/hash, reviewed
classifier release, and classification clock. The finite implemented outcomes
are:

```text
NORMALIZED_OBSERVATION | EXACT_DUPLICATE
CONTROL_SUBSCRIPTION_ACK | CONTROL_PONG
PROVIDER_ERROR | EXPECTED_INSTRUMENT_STATUS_ABSENT
MALFORMED_PAYLOAD | UNSUPPORTED_SCHEMA | OUT_OF_SCOPE
RECEIPT_LAG_REJECTED | CLOCK_ORDERING_REJECTED | CONTENT_CONFLICT
```

A normalized outcome binds exactly one derivation and revision. A duplicate
binds the earliest prior same-policy occurrence with byte-identical payload. A
provider error binds a canonical diagnostic digest; non-observation outcomes
cannot hide a raw derivation. Ledger semantic compare-and-swap permits only one
disposition for a message receipt.

The prefix records all disposition IDs plus the deterministic unresolved
blocking subset. Neutral controls and exact duplicates do not create values or
block health. Malformed/schema/content/clock/lag/provider/status-absence
outcomes fail closed with typed health; only explicitly defined later complete
observations and reconnect/boot conditions clear recoverable blockers.

This closes the reference semantic gap for duplicate, control, rejected, and
no-output messages. It does not solve live scale: disposition IDs remain part
of the cumulative V3.3 prefix, and classification is not yet driven by a
crash-safe continuous collector.

### `ObservationDerivationV3`

Binds ordered raw receipt or child-observation inputs, transform and parameter
hashes, numeric/interval/sparse/calendar policies, exact output fields/values,
and output digest. The same structure supports raw-to-1m normalization and the
later completed-1m-to-HTF aggregation.

The unit reference replay calls the same parser/normalizer and proves identical
content identity for the same raw fixture. This is not operational live/replay
parity: the live collector, crash recovery, resubscription, bounded indexed
storage, and end-to-end decision paths are not yet implemented and compared.

### `ObservationRevisionV3`

Defines an immutable typed observation:

```text
BAR | INSTRUMENT_STATUS | SYSTEM_STATUS | FEED_HEALTH | HEARTBEAT
```

It carries the stable observation key, exact concrete scope, half-open bar
interval, event/publication clocks, durable/normalized/available clocks,
derivation ID, completion state/basis, ordered values, and predecessor revision.

Core invariants:

- durable append `<=` normalized `<=` available;
- a complete bar is unavailable before its close;
- OHLCV decimals and OHLC bounds are exact and internally valid;
- a successor cannot fork or change observation coordinates;
- correction availability never moves backwards;
- provisional/retracted observations are not selectable.

### `ObservationSelectionPolicyV3`

The generic V3.1 slot states exact/latest/trailing but not the exact anchor,
lookback count, or continuity rule. A physical observation slot therefore
requires one frozen selection policy specifying:

- cutoff anchor and interval lag;
- requested count;
- strict, authoritative-calendar, or sparse-with-liveness continuity;
- maximum age;
- deterministic availability/revision tie-break.

### `EvidencePrefixV3`

Closes the world relative to one governed ledger prefix. It binds the ledger
ID, global sequence and receipt hash, capture chain, every observation revision,
every message disposition and unresolved blocker, active revision heads, status
revisions, source-member key, mapping, cutoff, event watermark, physical
vintage, and typed health state.

Only `PROSPECTIVE_LIVE + HEALTHY + TRADING_AUTHORITY` can authorize a trade.
Historical imports and replay are never silently upgraded.

The ledger rejects a snapshot that omits a matching segment, disposition, or
revision already registered by its frozen cutoff. Every captured occurrence
must have exactly one disposition. Only a normalized disposition requires an
included derivation/revision; duplicates, reviewed controls, errors, and
rejections remain explicit no-output evidence. The unresolved subset must equal
the deterministic health reducer and therefore cannot be hidden to manufacture
a healthy prefix.

### `DependencySelectionProofV3`

Recomputes the selected active completed revisions from prefix + frozen policy
+ information cutoff:

- `EXACT_EVENT`: one completed interval at the frozen grid anchor;
- `LATEST_AVAILABLE_ASOF`: deterministic latest completed, available revision;
- `TRAILING_COMPLETED_OBSERVATIONS`: the frozen count after revision collapse,
  with required continuity and age.

The proof is either `SELECTED` or `ABSTAIN`; an abstention carries no rows.
Predecessor/successor boundary IDs make the excluded boundary inspectable.

### `PhysicalEvidenceGateV3`

Binds one exact `InformationSetV3`, every prefix, and every selection proof. It
recomputes equality for:

- revision ID and source/member scope;
- event, bar, publication, first-seen, revision, and availability clocks;
- ordered source fields and exact value digest;
- the complete selected dependency set;
- live first-seen vintage, point-in-time certification, and prefix health.

The result is `PASS` or typed `ABSTAIN`. A source explicitly governed by a
registered physical adapter policy requires a registered PASS decision-input
gate before candidate promotion. Legacy V3.2 sources remain readable and can
still traverse their legacy path; V3.3 is therefore opt-in compatibility, not
yet a production-wide outer gate. Forward-paper/live entry points must reject
the legacy bypass before any deployment claim.

## Ledger order and migration

V3.3 adds an `OBSERVATION` ledger channel. Static policies remain in `MANIFEST`;
raw/normalized/prefix/proof/gate records enter `OBSERVATION`.

```text
provider + selection policies
→ capture segment
→ observation derivation
→ observation revision
→ provider-message disposition (one per captured occurrence)
→ evidence-prefix compare-and-swap
→ physical source member/bundle/source manifest
→ dependency selection proof
→ InformationSetV3
→ PhysicalEvidenceGateV3
→ V3.2 candidate and later records
```

Migration rules:

1. Preserve all V3.2 ledgers and Parquet artifacts unchanged.
2. A physical source opts in only when `source_contract_id` resolves to a
   registered `ProviderAdapterPolicyV3`.
3. Physically governed source members use
   `semantic_content_root = evidence_prefix_id` and
   `artifact_hash = raw_receipt_root`.
4. Historical imports remain nominal/current-revision evidence. A ledger
   receipt created today cannot be backdated to a past decision cutoff.
5. Dual-write the legacy paper journal and V3.3 shadow path until exact
   replay/live parity and failover behavior are proven.
6. Do not auto-promote from shadow to paper/live execution.

## First reference vertical slice

The reference adapter-policy allowlist is intentionally limited to:

```text
Bybit mainnet linear BTCUSDT and ETHUSDT
1-minute public WebSocket kline
confirm=true
exact raw capture
prospective instrument status
strict 24/7 one-minute continuity
```

Higher timeframes will be derived only from exact completed one-minute child
revision IDs. A missing/nonfinal child, wrong boundary, gap, or child correction
creates an abstention/new HTF revision; it never mutates an earlier decision.

Unsupported until their own evidence adapters are complete:

- Bybit REST as completion authority;
- Twelve Data live authority;
- Yahoo live/execution authority;
- continuous futures aliases and Yahoo futures proxies;
- reciprocal USDJPY proxy execution;
- any source without exact concrete mapping, authoritative calendar, status,
  and freshness evidence.

BTCUSDT and ETHUSDT identify the only adapter-policy fixture scope currently
allowlisted. They are not yet trading-authorized assets: no crash-safe live
capture, long-running feed-health proof, operational paper hard gate, or
acceptance soak has passed.

## Acceptance matrix

Implemented/frozen tests cover:

- exact schema/round trip and content-ID tampering;
- raw base64/hash integrity;
- identical duplicate payloads retaining distinct occurrence IDs;
- contiguous collector sequence and explicit connection epochs;
- connection-generation lineage attacks covered by the pure validator, while
  duplicate/branched authoritative roots are closed by ledger semantic-head
  CAS;
- rejection of an unapproved parser release identity;
- rejection of unapproved classifier and feed-health policy identities;
- exhaustive classification of reviewed Bybit kline/status messages, strict
  subscription/pong controls, provider errors, missing status, malformed,
  unsupported, foreign, lagged, clock-uncertain, and conflicting payloads;
- exact duplicate binding to the earliest byte-identical normalized occurrence;
- ledger one-disposition-per-message compare-and-swap and prefix coverage;
- neutral controls preserving health, blocking outcomes forcing typed
  non-healthy prefixes and gate abstention, and deterministic reconnect
  recovery;
- wrong topic/symbol/timeframe and duplicate-key JSON rejection;
- Bybit `confirm=false` provisional versus `confirm=true` complete;
- replaying the raw message through the frozen parser;
- OHLCV and half-open interval validation;
- revision fork, coordinate mutation, and clock-regression rejection;
- raw provider-lag enforcement even when optional envelope metadata is absent;
- prospective/authoritative/final/fresh/status requirements for a healthy
  prefix, including active-status and supporting-policy scope;
- bounded health validity;
- canonical capture and prefix object-budget enforcement, including rejection
  of a realistic 4,096-record cumulative prefix shape;
- a current provisional tail may remain recorded but is never selected;
- source-member semantic/raw-root/count/coverage equality;
- exact/latest/trailing recomputation, prefix age, health expiry, and gap
  abstention;
- logical dependency clock/value equality;
- PASS versus typed ABSTAIN gate output;
- ledger prefix-omission/cutoff tamper rejection, exact proof registration,
  physical-gate-before-candidate ordering, and physical dependency-set equality;
- unverified timeframe aggregation failing closed;
- identical normalization identity from the same raw fixture through two
  invocations of the reference parser.

Required before V3.3 exit:

- replace cumulative prefix ID arrays and full-history reparsing with bounded
  evidence epochs, proof-capable Merkle commitments, typed SQL indexes,
  constant-size cutoffs, and streaming verification; immutable message
  dispositions are implemented in the reference path, but their cumulative ID
  array adds to the current P0 scale blocker;
- run deterministic high-rate/long-duration soak, restart, correction,
  duplicate, provisional-update, and object-budget tests against those bounded
  structures;
- add the remaining explicit negative fixtures for capture-root/subscription
  mutation, completion regression, same-slot selection-policy CAS, and every
  bounded-epoch/typed-index transition;
- live capture writer crash/fsync/restart fault tests;
- heartbeat/disconnect/reconnect/resubscription fixtures;
- conflicting duplicate confirmation and late correction fixtures in ledger;
- deterministic 1m-to-HTF aggregation across every supported boundary;
- Bybit system-status negative-evidence adapter;
- dual-write operational replay/live parity from captured fixture segments;
- forward-paper candidate/order/fill hard gate that forbids the legacy bypass;
- Databento DBN/EOI/status/definition/mapping adapter and concrete ES/NQ/GC/CL
  roll fixtures;
- external signed checkpoint/optional WORM prefix attestation;
- signed build/release provenance and runtime parser/collector identity evidence;
- full-suite, public-API, ledger-tamper, and worktree verification.

The scale gate is not cosmetic. Cumulative segment/disposition/revision/active
arrays necessarily hit the object ceiling. A direct synthetic measurement of
the present schema reached 899,945 canonical bytes at 3,352 paired records and
rejected 3,353 against the explicit 900,000-byte prefix limit. That shape is a
schema stress measurement, not a certified live-duration estimate; real
message/control/revision ratios vary. No duration is certified until the
bounded replacement passes an executable soak under the actual message mix.

The provisional bounded replacement and its decision/soak gates are specified
in
[`v3_4_bounded_physical_evidence_architecture_2026-07-14.md`](v3_4_bounded_physical_evidence_architecture_2026-07-14.md).

## What this does and does not achieve

This gate materially improves causal validity, reproducibility, and operational
safety. It prevents model experiments from claiming an edge using a bar that
was still forming, received after the decision, revised later, selected from an
incomplete prefix, stale, status-blocked, synthetic, or not tied to the concrete
instrument.

It does not create predictive signal, guarantee provider truth, simulate bid-
ask execution, or guarantee profitability. A complete physical gate is a
prerequisite for trustworthy experiments, not evidence that the strategy has
out-of-sample economic edge.

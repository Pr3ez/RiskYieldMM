# V3.2 Calendar and Action Resolution Design

Date: 2026-07-14  
Status: implemented V3.2 logical contract  
Scope: completed Stage 1 logical calendar/action sub-gate; physical market-data,
status, fill, label, storage, and split certification remain separate gates

## 1. Decision

V3.2 resolves the next eligible scheduled action **before** a primary-signal
candidate may exist:

```text
CalendarSourceArtifactV3
  -> CalendarScheduleSnapshotV3

InformationSetV3
  + CalendarScheduleSnapshotV3
  + ActionProtocolV3
  + InstrumentMappingV3
  + frozen signal-intent fields
  -> resolve_action_v3(...)
  -> ActionResolutionV3
  -> PrimarySignalCandidateV3
```

Only a successful `ActionResolutionV3` may be bound by a V3.2 candidate. An
abstained resolution has no invented entry timestamps and cannot be converted
into a candidate.

The first supported selection rule is deliberately narrow:

```text
NEXT_SCHEDULED_BASE_BAR_OPEN
```

The selected base-bar open must be strictly later than the order-ready clock,
and the complete entry window must fit both the authoritative schedule and the
effective executable-instrument mapping. The resolver does not infer sessions
from observed prices, fill through a closed interval, or use the completed
signal bar's close as an executable price.

This is the strongest defensible first implementation because it makes the
calendar decision deterministic and independently testable without pretending
that a schedule alone proves a live fill. It is not a profitability result or
a deployment certification.

## 2. Why the V3.1 boundary is insufficient

The V3.1 evidence graph correctly binds `calendar_manifest_id` into an
`InformationSetV3`, and `PrimarySignalCandidateV3` validates the ordering of
caller-provided action clocks. It does not yet prove that:

- the referenced calendar came from an identified authoritative artifact;
- the next timestamp is an open, matching-enabled interval for the venue and
  product;
- a futures alias resolves to the exact listed contract that could be traded;
- an early close, holiday, maintenance interval, or DST transition was applied;
- the chosen entry window fits the schedule and instrument mapping; or
- the action timestamps were derived rather than selected by the candidate
  caller.

The current legacy calendar layer is not acceptable as that proof.
`scripts/feature_engineering/htf_trading_calendar.py`:

- uses `crypto_24_7` as a generic calendar;
- infers futures sessions from gaps in fetched observations;
- removes timezone information from raw timestamps;
- splits sessions with a heuristic gap threshold; and
- creates zero-volume carry-forward bars inside inferred open segments.

Those rows remain useful as legacy continuity diagnostics. They must not
authorize a V3.2 action, certify a completed observation, or become an
executable price. `futures_session_observed` is therefore a migration input,
not an authoritative calendar.

## 3. Research findings

### 3.1 There is no single universal market calendar

Exchange schedules are venue-, market-, product-, and sometimes
instrument-specific. They contain phases with different order behavior rather
than a single Boolean `is_open`.

- CME publishes product-aware regular and holiday schedules on its official
  [Holiday and Trading Hours](https://www.cmegroup.com/trading-hours.html)
  page. The official
  [CME Globex Reference Guide](https://www.cmegroup.com/content/dam/cmegroup/globex/files/GlobexRefGd.pdf)
  explains that an evening session can start the next trading day and that
  pre-open, intervention, maintenance, and trading phases have different order
  behavior.
- NYSE publishes official
  [holidays and early closes](https://www.nyse.com/markets/hours-calendars)
  and separate
  [trading-session and auction times](https://www.nyse.com/trade/trading-information).
  Its
  [Pillar Integrated Feed specification](https://www.nyse.com/publicdocs/nyse/data/Pillar_Integrated_Feed_Client_Specification_v2.5c.pdf)
  states that halts and reopenings can occur at any time and can continue from
  one session into another.
- ISO 10383 supplies stable operating and segment market identifiers through
  the official
  [Market Identifier Code registry](https://www.iso20022.org/market-identifier-codes).

Consequently, the calendar key must include venue and product/security scope;
for listed derivatives it cannot be a generic `futures` calendar. A session or
exchange trade date must also remain distinct from UTC date and local civil
date.

### 3.2 A scheduled calendar is necessary but not sufficient for live action

The project's crypto scope is Bybit linear derivatives. Bybit provides three
different facts that must not be collapsed:

- the official
  [WebSocket kline contract](https://bybit-exchange.github.io/docs/v5/websocket/public/kline)
  says `confirm=true` means that a candle has closed and exposes bar start,
  end, system-generation, and last-matched-order timestamps;
- the
  [instrument-information endpoint](https://bybit-exchange.github.io/docs/v5/market/instrument)
  exposes instrument status, launch/delivery times, and auction phases; and
- the
  [system-status endpoint](https://bybit-exchange.github.io/docs/v5/system-status)
  reports maintenance and incidents, while explicitly warning that short
  interruptions or immediately reconnectable WebSocket disconnects may not be
  announced.

Therefore `24/7` describes a nominal schedule, not continuous proof of
tradability. Production support additionally requires a prospectively recorded
instrument/status journal, a feed-health rule, and completed-bar evidence. If
any required state is absent or stale, the scope must fail closed.

The FIX standard independently distinguishes security-specific state from
market/session state. Its
[Security Status and Trading Session Status specification](https://cdnws.fixtrading.org/wp-content/uploads/download-manager-files/FIX-5.0_SP2_VOL-3_w_Errata_20110818.pdf)
supports the same two-layer interpretation.

### 3.3 A continuous futures alias is not an executable contract identity

The current non-crypto inputs use Databento `GLBX.MDP3` continuous symbols:

```text
EURUSD -> 6E.v.0
USDJPY -> 6J.v.0, followed by reciprocal price transformation
GC     -> GC.v.0
CL     -> CL.v.0
ES     -> ES.v.0
NQ     -> NQ.v.0
```

Databento's official
[symbology specification](https://databento.com/docs/standards-and-conventions/symbology)
defines `[ROOT].[ROLL_RULE].[RANK]` as a symbol that maps to different actual
instruments over time. A volume rule such as `.v.0` ranks contracts using the
previous day's volume. Databento exposes effective-dated mappings to concrete
instrument IDs and raw symbols.

The continuous alias can identify a research price series, but an action must
bind the effective concrete listed contract. The mapping artifact, its
availability clock, and its effective interval are part of the action proof.
An entry window that crosses an unresolved roll or mapping boundary abstains.

### 3.4 UTC storage does not remove timezone-version risk

All canonical event instants should be UTC, but exchange-local schedule rules
must be compiled using a named IANA timezone and a frozen database version.

- Python's official
  [`zoneinfo` documentation](https://docs.python.org/3/library/zoneinfo.html)
  explains that it can read either system data or the first-party `tzdata`
  package and does not guarantee identical results when environments use
  different timezone data.
- The [IANA Time Zone Database](https://www.iana.org/time-zones) is revised as
  political bodies change offsets and daylight-saving rules.
- [RFC 3339](https://www.rfc-editor.org/info/rfc3339/) recommends UTC for
  interoperable timestamps, but a numeric UTC offset alone is not a durable
  representation of future exchange-local rules.

Every schedule snapshot must therefore bind the IANA zone key, tzdb version or
artifact digest, compiler version, and compiled UTC intervals. Updating tzdb
creates a new snapshot; it must not silently rewrite old resolutions.

## 4. Alternatives considered

| Alternative | Strength | Failure for this gate | Decision |
|---|---|---|---|
| Continue observed-gap inference | Already integrated and inexpensive | Converts missing data into market structure; cannot prove holidays, maintenance, DST, early close, or trade date | Rejected as authority |
| Hard-code weekday/session rules | Deterministic | Misses product exceptions, schedule changes, holidays, and unscheduled events | Rejected |
| Resolve directly from a Python calendar package at runtime | Convenient session APIs | Mutable dependency/output; community data cannot establish project-specific source provenance or live status | Rejected for identity; allowed only as a pinned compiler/test oracle |
| Use a commercial calendar API response directly | Broad coverage and detailed phases | Network and mutable-latest dependency; API schema version does not by itself provide a point-in-time data vintage | Conditional only after immutable download/ETag/content capture |
| Fetch exchange web pages during inference | Direct source | Nondeterministic, operationally fragile, and impossible to reproduce after a page changes | Rejected |
| Compile immutable source artifacts into content-addressed schedule snapshots, then resolve with a pure function | Deterministic, auditable, independently testable, compatible with V3.1 evidence | Requires explicit adapters and curation per supported scope | Selected |

Useful secondary tools remain deliberately subordinate:

- [`exchange_calendars`](https://github.com/gerrymanoim/exchange_calendars)
  offers UTC sessions, breaks, early closes, minute lookup, and explicit
  left/right boundary semantics, but its own implementation states that no
  accuracy guarantee is offered.
- [`pandas_market_calendars`](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html)
  supports early closes, breaks, and declared interruptions, but package data
  is not a live exchange-status feed and overlaps with the
  `exchange_calendars` lineage.
- [TradingHours.com](https://docs.tradinghours.com/) documents primary-source
  research, detailed phases, and DST support. Its
  [download endpoint](https://docs.tradinghours.com/4.x/endpoints/download)
  provides ETag and Last-Modified metadata. It is a viable paid secondary
  source only if the exact downloaded bytes, receipt clock, license-compatible
  provenance, and digest are preserved.
- [QuantLib calendars](https://quantlib-python-docs.readthedocs.io/en/latest/dates.html)
  are suitable for business-day and settlement calculations, not for this
  intraday matching/action proof.

## 5. Exact causal boundary

### 5.1 Time definitions

V3.2 keeps these concepts separate:

| Clock | Meaning |
|---|---|
| `source_event_ts` | When the exchange/provider says an observation occurred |
| `bar_open_ts` / `bar_close_ts` | Normalized half-open observation interval `[open, close)` |
| `ingested_first_seen_ts` | When this system first received the exact revision |
| `observation_cutoff_ts` | Latest information instant admitted to the `InformationSetV3` |
| `assembled_at` | When the information set was actually constructed |
| signal intent availability | When the frozen primary-signal intent was available to action resolution |
| order-ready clock | Earliest time computation and frozen submission delay have elapsed |
| selected grid open | First scheduled base-bar open strictly after order-ready |
| entry expiry | End of the frozen entry window, constrained by schedule and mapping |

Provider endpoints differ on whether an end timestamp is inclusive. Adapters
must normalize to `[open, close)` while retaining the original convention in
source metadata. A timestamped row is not considered complete merely because
the local wall clock passed its nominal end.

The current canonical JSON timestamp precision is microseconds. A physical
adapter receiving nanosecond exchange timestamps must preserve the native
integer timestamp and declared precision in its source artifact rather than
silently rounding it into an identity claim.

### 5.2 Resolution ordering

The pure resolver applies the following ordering:

```text
decision evidence is assembled
  -> frozen signal intent becomes available
  -> protocol computation/submission delay elapses
  -> order_ready_ts
  -> first scheduled base-bar open strictly greater than order_ready_ts
  -> complete entry window must fit schedule and instrument mapping
  -> RESOLVED or typed ABSTENTION
  -> only RESOLVED may become a candidate
```

Strictly-greater selection is intentional. If a 1-minute signal bar represents
`[12:00, 12:01)`, information about that complete bar cannot justify a fill at
the 12:01 boundary trade that occurred before computation and routing. With
bar-only historical data, the scheduled next-bar open is a conservative,
declared scenario; it is not proof that the exact opening print was fillable.

### 5.3 What is causal at this gate

For a point-in-time-certified resolution:

1. every information dependency was available by the information cutoff;
2. the calendar source artifact and schedule revision used by the resolver had
   been received before the decision was resolved;
3. the schedule's rules and exceptions were effective for the selected grid;
4. the instrument mapping was known and effective over the complete entry
   window;
5. the signal-intent and action protocol were frozen before resolution;
6. no future schedule revision, future roll mapping, or later observation is
   consulted; and
7. resolution is registered before a candidate can reference it.

Current-revision historical calendars without a contemporaneous receipt clock
remain `NOMINAL_CURRENT_REVISION`. They cannot be upgraded retroactively to a
live-first-seen claim.

## 6. V3.2 contracts

The implementation lives in the bounded calendar/action domain and uses the
following exact public names.

### 6.1 Enums

- `CalendarAuthority` identifies the authority class without treating every
  source as equivalent.
- `ActionSelectionRule` freezes the resolution algorithm; the first admitted
  rule is `NEXT_SCHEDULED_BASE_BAR_OPEN`.
- `ActionResolutionStatus` distinguishes a successful proof from abstention.
- `ActionAbstentionReason` supplies a stable, machine-testable reason instead
  of an exception-dependent string.
- `InstrumentPriceTransform` declares whether model prices are identical to
  executable-instrument prices. V3.2 does not authorize transformed execution
  semantics that have not been independently specified and tested.

### 6.2 Records

#### `CalendarSourceArtifactV3`

This is the immutable evidence for a schedule input. Its identity must bind,
at minimum, the source authority and locator, content digest, publication or
effective metadata where available, retrieval/first-seen clock, and parser
contract. An official page that changes produces another artifact.
The implemented V3.2 admission set is deliberately limited to a declared
`OFFICIAL_VENUE` whose authority name equals the calendar venue.
`OFFICIAL_REGULATOR`, `AUTHORIZED_VENDOR`, and `SECONDARY_REFERENCE` cannot
authorize action until an independent scoped authorization-evidence contract
is available. The logical record integrity-binds caller-declared metadata and
content/parser hashes; it does not independently authenticate a remote host,
signature, parser execution, or a claim that relabeled content is official.
The provider adapter must enforce a reviewed official-host/parser policy.

#### `TradingIntervalV3`

This is an embedded, content-addressed executable interval. It represents one
normalized half-open UTC interval and its stable session/trade-date context.
Intervals are ordered, non-overlapping, unique, and compatible with the
snapshot's base grid. The interval is schedule evidence, not a fill.

#### `CalendarScheduleSnapshotV3`

This binds one exact venue/product scope, source artifact, timezone/tzdb and
compiler semantics, base timeframe, and ordered interval set. The content
identity prevents a later holiday correction, timezone update, or interval
reordering from mutating an earlier resolution.

#### `ActionProtocolV3`

This freezes the selection rule, timing delays, base timeframe, entry-window
width, declared-official venue allowlist, and allowed action interpretation.
Parameter choices are protocol inputs, not values tuned on the final test or
supplied per candidate.

#### `InstrumentMappingV3`

This maps the model-facing asset/venue/contract scope to an executable venue
and concrete instrument for an effective interval. It declares the price
transform and binds its provenance. For continuous futures, the mapping must
resolve `.v.0` to the point-in-time concrete contract; the alias itself is not
the execution contract.

#### `ActionResolutionV3`

This is the deterministic result of `resolve_action_v3`. It binds the exact
information-set record, schedule snapshot, action protocol, instrument mapping,
and frozen signal intent. A resolved record identifies its selected interval
and derived action clocks. An abstained record carries its typed reason and no
fabricated successful-action identity.

### 6.3 Candidate integration

`PrimarySignalCandidateV3` must bind the exact resolution ID and record hash.
Its scope, signal-intent fields, action protocol, entry scenario, executable
contract, and action clocks must equal the referenced resolved record. A
candidate parser or manifest verifier must reject:

- a missing or abstained resolution;
- registration of the resolution after the candidate;
- a substituted schedule, mapping, protocol, or information-set record;
- clocks edited after resolution;
- a model asset paired with another executable contract; or
- two conflicting resolutions reused for one logical signal intent.

## 7. Pure resolver algorithm

`resolve_action_v3` must be deterministic and side-effect free. Conceptually:

```text
1. Parse and canonicalize every record and signal-intent field.
2. Verify exact scope and record-hash agreement with InformationSetV3.
3. Verify schedule source, calendar identity, venue, timeframe, vintage, and
   effective bounds.
4. Verify InstrumentMappingV3 covers the model scope and has an admitted price
   transform.
5. Compute order_ready_ts from the maximum admissible information/signal clock
   plus the frozen protocol delay.
6. Select the first TradingIntervalV3 grid open strictly after order_ready_ts.
7. At ledger admission, apply deterministic as-of revision selection to every
   resolved or abstained outcome. If a schedule-valid window exists, select the
   latest known calendar covering submission and that window, and the latest
   known mapping covering the window when one exists. If no schedule-valid
   window exists, select the latest known same-scope calendar covering
   submission when available, otherwise the latest known same-scope calendar,
   plus the latest known same-scope mapping. If a window exists but no mapping
   covers it, use the latest known same-scope mapping so a newer blocker cannot
   be bypassed. Future or non-overlapping successors do not stale an applicable
   parent.
8. Require the complete protocol entry window to remain inside the schedule
   and selected effective instrument mapping. A mapping gap abstains at this
   first schedule-valid window rather than shifting the action later.
9. If all conditions hold, emit one content-addressed resolved record.
10. Otherwise emit one content-addressed abstention with a stable reason.
```

There is no fallback to the nearest observed timestamp, no weekend arithmetic,
no silent mapping extension, and no synthetic bar insertion. Sorting input
records, using another host timezone, or rerunning the same records must not
change the result.

## 8. Current asset support matrix

`supported` below means supportable by the complete evidence chain, not merely
that historical price rows exist.

| Model asset | Current source/symbol | V3.2 position | Required evidence before support |
|---|---|---|---|
| `BTCUSDT` | Bybit linear `BTCUSDT` | Potentially supportable; not certified yet | Venue-specific Bybit schedule snapshot; `confirm=true` completion adapter; prospectively journaled instrument and system status; feed-health/staleness rule; identity executable mapping |
| `ETHUSDT` | Bybit linear `ETHUSDT` | Potentially supportable; not certified yet | Same requirements as BTCUSDT, independently tested for ETHUSDT |
| `EURUSD` | Databento `6E.v.0`, Yahoo `6E=F` tail | Unsupported until mapping | Point-in-time `.v.0` to concrete 6E contract mapping; product-specific CME schedule and status; roll-boundary tests; Yahoo tail cannot independently certify the action |
| `GC` | Databento `GC.v.0`, Yahoo `GC=F` tail | Unsupported until mapping | Concrete GC contract, COMEX/CME schedule snapshot, mapping availability and roll coverage, completed-bar/status adapter |
| `CL` | Databento `CL.v.0`, Yahoo `CL=F` tail | Unsupported until mapping | Concrete CL contract, NYMEX/CME schedule snapshot, mapping availability and roll coverage, completed-bar/status adapter |
| `ES` | Databento `ES.v.0`, Yahoo `ES=F` tail | Unsupported until mapping | Concrete ES contract, CME schedule snapshot, mapping availability and roll coverage, completed-bar/status adapter |
| `NQ` | Databento `NQ.v.0`, Yahoo `NQ=F` tail | Unsupported until mapping | Concrete NQ contract, CME schedule snapshot, mapping availability and roll coverage, completed-bar/status adapter |
| `USDJPY` | Databento `6J.v.0` / Yahoo `6J=F`, reciprocally transformed | Unsupported by this gate | In addition to concrete 6J mapping, requires an independently specified reciprocal execution, side, tick, barrier, cost, and fill contract; V3.2 must abstain rather than treat transformed USDJPY prices as directly tradable |

For reciprocal OHLC, a mathematical transform exchanges high and low and
reverses economic direction. Even if historical OHLC transformation is
arithmetically correct, an action in the transformed USDJPY-like series is not
an order in that synthetic instrument. Supporting it would require a separate
economic/execution specification. It is intentionally outside this gate.

No equity asset is currently in the core registry. The contracts are capable
of a future equity adapter, but NYSE or another venue is not `supported` until
its official schedule, security status, completed-bar source, and action
protocol pass the same tests.

## 9. Required tests and falsification

### 9.1 Contract and identity tests

- Exact-key parsing and canonical round trip for every V3.2 record.
- Recompute every content ID and record hash.
- Reject changed source bytes under the same artifact identity.
- Reject a schedule known before its exact source bytes were fully retrieved
  or extending beyond the artifact's effective interval.
- Reject any authority declaration other than `OFFICIAL_VENUE`, and reject a
  declared official-venue name that differs from the calendar venue.
- Reject interval reordering, duplicates, overlaps, invalid duration, invalid
  timezone metadata, and scope mismatch.
- Reject protocol or mapping substitution after resolution.
- Reject a candidate that references an abstention or changes resolved clocks.
- Ledger receipt ordering proves source artifact -> snapshot -> resolution ->
  candidate.

### 9.2 Causal clock tests

- The selected grid open is always strictly later than order-ready.
- Exact-boundary input does not reuse the boundary that is already too early.
- No completed current-bar close becomes an entry.
- A schedule or mapping first seen after the decision cannot certify it.
- Adding future observations or future schedule revisions leaves all prior
  resolution hashes unchanged.
- A full entry window, not only its first timestamp, fits schedule and mapping.
- Missing, stale, future-effective, or roll-crossing mappings abstain.
- An overlapping known successor stales its parent, while a future or
  non-overlapping successor leaves the applicable historical record valid.
- A newer blocking mapping cannot be bypassed by an older executable parent.
- A mapping gap at the first schedule-valid window cannot shift entry later.

### 9.3 Next physical-adapter calendar fixtures

These are Stage 1 physical-adapter exit requirements, not claims completed by
the generic V3.2 logical resolver:

- Bybit 1-minute and higher-timeframe bars with `confirm=false` and
  `confirm=true`.
- Bybit planned maintenance, incident, unannounced disconnect/feed-stale path,
  non-trading instrument, and auction/prelaunch status.
- CME Sunday-evening session mapped to the following exchange trade date.
- CME daily maintenance and product-specific schedules for 6E, 6J, GC, CL, ES,
  and NQ.
- CME holiday/early-close change and an effective-dated schedule amendment.
- U.S. spring and fall DST transitions using the pinned tzdb.
- A normal NYSE day, holiday, early close, exact close boundary, and halt fixture
  for future adapter conformance.

### 9.4 Current-pipeline negative controls

- The reviewed provider-adapter policy must never issue `OFFICIAL_VENUE`
  evidence from `futures_session_observed`; the logical enum/name checks alone
  do not authenticate the underlying host or parser.
- The reviewed provider-adapter policy must never certify a synthetic
  carry-forward row as official action evidence.
- Absence of a crypto candle is not automatically a closed market.
- Absence of a futures bar is not automatically maintenance.
- A Yahoo continuous-symbol tail cannot identify a listed execution contract.
- `USDJPY` reciprocal data always abstains under the first action protocol.

### 9.5 Next physical-adapter replay/live parity requirement

Given identical frozen artifact, schedule, action protocol, mapping,
information, `primary_signal_id`, signal policy/version, side, signal clocks,
`resolved_at`, and eligible-revision ledger prefix, replay, forward paper, and
live inference must produce the same action-resolution identity. Later
execution results may differ, but the fully specified pre-action proof may not.
This is a requirement for the next physical adapter, not a parity claim already
established by the generic logical resolver.

## 10. Gate acceptance criteria

This logical gate is complete only when:

1. the exact V3.2 record graph and pure resolver are implemented and exported;
2. `NEXT_SCHEDULED_BASE_BAR_OPEN` has one unambiguous half-open boundary rule;
3. every successful resolution binds an immutable source artifact, schedule,
   protocol, concrete instrument mapping, information record, and signal intent;
4. every governed unsuccessful case with a complete as-of input graph produces
   a typed abstention and no candidate; absence of required evidence fails
   admission rather than synthesizing a historical record;
5. candidate and manifest validation prohibit caller-selected action clocks;
6. adversarial identity, scope, future-poison, boundary, schedule, and mapping
   tests pass;
7. the reviewed provider adapter prevents legacy observed-session and
   synthetic rows from being declared official evidence; the logical contract
   itself rejects non-`OFFICIAL_VENUE` declarations and venue-name mismatch;
8. the full existing repository suite remains green; and
9. documentation and runtime status continue to distinguish logical schedule
   resolution from physical completion, venue availability, and fill proof.

Asset-specific promotion is stricter:

- Bybit BTCUSDT/ETHUSDT remain unsupported until completion, status, and
  feed-health adapters pass prospective replay/live parity.
- CME-backed aliases remain unsupported until exact point-in-time executable
  contract mappings and product calendars exist.
- USDJPY reciprocal execution remains unsupported unless a later protocol
  separately proves its economic and execution semantics.

## 11. Limits and next gate

Passing V3.2 proves a narrower statement:

> Under one immutable, declared schedule and instrument mapping, the selected
> scheduled base-bar entry window is the first one allowed by the frozen action
> protocol after the information and signal clocks.

It does not prove:

- that the venue was actually reachable or matching orders at that instant;
- that an unannounced halt or sub-ten-second outage did not occur;
- that the provider delivered a final, immutable candle at nominal close;
- that an order would be accepted, filled, or filled at the bar open;
- intra-bar TP/SL ordering;
- realistic spread, slippage, latency, queue priority, impact, or partial fill;
- historical point-in-time availability where no receipt journal exists; or
- predictive or after-cost trading edge.

The pure resolver can diagnose `MAPPING_NOT_KNOWN` when passed a mapping first
known after the information cutoff. The governance ledger intentionally cannot
admit that result: citing future evidence would make the no-trade record
noncausal and could poison the stable action key. Other governed mapping
abstentions can cite a same-scope record known by the cutoff: an explicit
non-executable blocker yields `MAPPING_NOT_EXECUTABLE`, while a known mapping
that misses the first schedule-valid window yields `MAPPING_WINDOW_MISSING`.
A later schema should add explicit mapping-absence evidence if canonical
auditing of the complete no-record state is operationally required.

The immediate next physical gate must add:

1. provider-specific completed-bar and first-seen evidence;
2. prospectively journaled venue/instrument status and feed health;
3. exact/latest/trailing physical row-inclusion and calendar-continuity proofs;
4. concrete futures symbology mapping capture and roll validation;
5. replay/live adapter parity without legacy behavior changes during shadow
   comparison; and
6. only then, the independent next-executable-entry and first-touch label
   verifier.

Model baselines and the compact Stage 3 feature redesign remain downstream of
these Stage 1 corrections. Calendar precision removes a class of false trades;
it cannot manufacture an economic signal that is absent from the data.

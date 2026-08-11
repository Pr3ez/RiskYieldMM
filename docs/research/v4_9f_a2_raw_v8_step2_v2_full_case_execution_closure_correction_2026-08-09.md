# Raw V8 Step-2 V2 full-case execution-closure correction

Date: 2026-08-09  
Status: **ACCEPTED CORRECTION — AMENDED; S1-A2 MAY BEGIN**

> Current-authority notice: the S1-A2-A dry run found one narrower omission
> after this correction was accepted: exact per-emission token metadata. The
> [`event-metadata amendment`](v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md)
> closes it. The original measurements retained below describe the predecessor
> correction checkpoint; the final paragraph in Section 6 records the current
> amended identities and evidence.

## 1. Decision

The 2026-08-09 S1-A1 acceptance is superseded for one narrow reason. The seed
closes the cell-transfer rules, event token schema, metric updates, local
controller, and three bounded hand oracles, but it does not close construction
of the exact event subjects for a complete ordinary case.

The defect was found while freezing the S1-A2 shared input boundary, before
either full-case counter was authored. This is a successful falsification, not
permission to fill the gap independently in the two preflights.

S1-A2 remains waiting until this correction is serialized, independently
tested, deterministically regenerated, and reaccepted as S1-A1.

## 2. Confirmed failure

The serialized seed currently has all three defects below.

1. `transition_expansion_contract.ordinary_run_source` names
   `RECURRENCE_KERNEL_CLOSED_TRANSITION_EXPANSION_PROGRAM`, but none of the 18
   kernel records, nor any event-catalog record keyed to those kernels,
   publishes that program.
2. Every case-event emission delegates subject bytes to
   `CASE_PROGRAM_EXACT_SUBJECT_COLLECTION`, but no constructor defines that
   collection for complete cases.
3. Variable-cardinality emissions such as transitions and batch applications
   carry placeholder `CONST_U128(1)` cardinalities, despite frozen steps whose
   physical counts are zero, one, or greater than one.

The executable falsification is:

```text
tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py
```

Observed fail-first result:

```text
1 passed, 3 failed
```

The passing test constructs two ordinary transition tokens that satisfy the
same currently serialized variant/member/null rules, have the same canonical
octet count, and therefore contribute the same values to M4, M5, M9, and M10.
They differ only by equal-width `input_symbol` values, so their subject hashes
and enclosing event-stream digests differ. The existing authority contains no
rule that selects one. Exact 18-metric agreement would consequently not prove
agreement on `logical_event_stream_sha256`.

## 3. Options reviewed

### 3.1 Let A and B infer the missing values — rejected

This would make agreement partly a consequence of shared human assumptions.
Disagreement would be uninterpretable, and agreement would not prove that
either implementation followed frozen semantics.

### 3.2 Store 475 fully expanded event traces in the seed — rejected

This would consume unnecessary input/storage headroom, make the counters copy
an answer instead of derive it, and move a large phase result into the seed.

### 3.3 Freeze one compact full-case construction program — selected

The event grammar will bind a compact program that derives exact subject
objects, cardinalities, ordering, logical-count distribution, live-set
observations, depth observations, final results, and stream finalization from
the already identity-bound plan, recurrence, profile, local-controller, and
metric records. It will contain no expected 475-case count vector.

Preflight A will interpret the existing low-level cell-transfer AST and build
events in a descriptor-forward loop. Preflight B will use separately authored
direct transfer equations and a flat unit ledger. The compact program is data;
no executable helper is shared.

## 4. Required closed construction

The corrected event grammar must publish exactly one
`full_case_execution_program` with these responsibilities.

### 4.1 Ordinary derivation units

- Select the plan's bound template and process `template_step_position` in
  ascending strict postorder.
- Evaluate each cell bottom-up at the recurrence arithmetic policy's published
  maximum ambient ceiling. Apply structured codec intersections only at their
  explicit node; do not infer top-down residual pruning.
- For profile-bound cases, execute the bound P2 program at the root before the
  root result cell is emitted. Case 69 intersects the structural root with the
  independently derived exact local-baseline cell; other generic P2 programs
  retain their declared structural superset.
- Emit one result cell and one cache insertion per template step.
- Derive transition-token cardinality from the bound kernel meter expression,
  never from an event-program placeholder.
- Distribute the step's logical-unbatched count across physical tokens with
  exact quotient/remainder division in physical ordinal order. The per-token
  counts must sum to the frozen step total and every emitted token must have
  physical multiplicity one.
- Emit exactly the stored physical batch count.

### 4.2 Local derivation unit

- Case 475 is one local controller derivation unit, not ordinary row 69.
- Emit the 12 ordered controller states as result cells and cache entries and
  the 11 ordered controller transitions one-to-one.
- Bind transition source/target IDs and components to the adjacent serialized
  controller records.
- Emit one commitment over the 12 ordered cell digests.
- Recompute the local metric-count program; do not copy its expected values as
  the counter result.

### 4.3 Exact canonical subjects

For all 16 event kinds, the program must bind:

- exact subject member order or exact raw-byte source;
- every member's value source;
- subject cardinality and order;
- event phase, per-kind ordinal, global ordinal, role, and subject ordinal;
- aggregation multiplicity, logical-unbatched count, and observed value; and
- compact canonical UTF-8 byte length and SHA-256 recomputation.

The recurrence cache-key, transition-token, result-cell, and commitment
constructors must populate every tagged-union member, including explicit nulls.
No `CASE_PROGRAM_EXACT_SUBJECT_COLLECTION` placeholder may remain.

### 4.4 Counts, depths, retention, and finalization

- M1–M18 are updated only through the frozen event-kind metric programs.
- Derivation depth is leaf one and parent one plus maximum child depth.
- Iteration depth uses the frozen per-kind rule, including binary-lift depth,
  sequential stream length, application schedule length, and the 11-transition
  local controller.
- The reverse-parent index controls raw cache-key/result-cell release. Full
  commitment preimages release immediately after their per-unit hash; required
  32-octet digests remain through final-result hashing.
- The final result contains only the root result-cell digest records and the
  complete ordered commitment-digest records.
- The stream preimage contains every pre-close token and excludes both terminal
  control tokens. The stream hash is the last case event.

## 5. Correction acceptance tests

The corrected S1-A1 seed is acceptable only if all of the following pass.

1. The new fail-first closure suite passes and rejects missing constructors,
   unresolved subject locators, altered transition distribution, wrong local
   adjacency, and placeholder cardinalities.
2. Existing bounded hand-oracle bytes and metric vectors either remain exact or
   are regenerated from a separately reviewed versioned oracle constructor;
   they are not silently edited.
3. Small transition distributions exhaust physical/logical combinations and
   reconcile sums without zero-count or overflow ambiguity.
4. Independent construction evidence covers the boundary without duplicating
   S1-A2: the separate typed cell-transfer interpreter covers every transfer
   family (including scalar, batch, stream, profile, case 69, and case 475);
   the three versioned hand oracles cover ordinary batch, stream/context, and
   local event/metric behavior; and fixed-byte probes pin both an ordinary
   tagged-subject bundle and the complete 12-state/11-transition local tagged-
   subject bundle. Exact two-implementation stream and 18-metric agreement for
   all 475 cases belongs to S1-A2 and is not claimed here.
5. Source-security, canonical JSON, identity, atomic-output, and operational
   seed-size checks remain green.
6. Write/check/write/check is byte-identical and the control ledger records the
   new bytes, hashes, pass count, and remaining headroom.

## 6. Acceptance result

The corrected authority passed on 2026-08-09. The fail-first closure baseline
of `1 passed, 3 failed` became `21 passed, 0 failed`; the complete read-only
seed, local-state, recurrence, profile-conditioning, cell-transfer, event,
execution-closure, and source-security matrix passed `101 passed, 0 failed`.

The ordinary reference bundle is 3,213 compact-canonical octets with SHA-256
`8944d523e6671c3f7725d702cf8e675b4ab23b1131369faa7556fe21c1901a8d`.
The complete local tagged-subject bundle is 30,205 octets with SHA-256
`32c359df8922b8e929906387ce5c5a23f7d75c2cbe10c18e85eab5ac50d9e40b`.
These probes caught and closed absent local endpoint member references before
acceptance.

The corrected external event grammar is 124,432 bytes with raw SHA-256
`c7a74e5813b23b602bdf6809630acd72a72b24a2886cea82c806095b578ce844`.
The generator SHA-256 is
`3ad1d5a305d75f3f7cf088dcf83cb0f3847f9d08333a52086ae03b24eabb53e4`.
Write/check/write/check reproduced one 13,412,458-byte seed with raw SHA-256
`42cafff72013298af9d05f0dbfed04098e3290be5fcfa3a5baced4d9750ef417`
and semantic catalog ID
`6b38221ee705b5dc2a220a2c35ac33c8d6d06db26b8d50d932e5dd28528f708d`.
Operational headroom is 2,316,182 bytes below the 15,728,640-byte target and
3,364,758 bytes below the strict 16,777,216-byte individual-file ceiling.

The authoritative acceptance record is
[`v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md`](v4_9f_a2_raw_v8_step2_maximum_protocol_v2_seed_correction_acceptance_2026-08-09.md).

The predecessor values above were superseded by the event-metadata amendment.
The current grammar is 131,015 bytes with raw SHA-256
`72bfd44ff159eb6904936ae32d0d25ab9b0c8536b87f5e93d055b521679401c8`;
the generator SHA-256 is
`47b4ecada8c661185e4087787b99e113b2366ff87ee06e951a21a85b9a4cab4f`.
The current seed is 13,419,905 bytes with raw SHA-256
`a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f`
and semantic ID
`ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f`.
The amended seed/security matrix passes 108 tests, and the complete amended
seed plus refrozen boundary matrix passes 121 tests. These current values are
normative for S1-A2; the earlier values remain reproducible historical
evidence only.

## 7. Nonclaims

This correction does not authorize either F1 preflight, the final V2 protocol,
a verifier, a maximum witness, Raw V8 Step 2/3 completion, Stage 1 completion,
paper/live trading, predictive edge, or profitability.

# Raw V8 Step-2 maximum-protocol V2 seed correction acceptance

Date: 2026-08-09  
Decision: **GO for S1-A1; activate S1-A2 — AMENDED**

> Amendment notice: an S1-A2-A dry run found that exact event-token metadata
> was not yet bound at each emission position. The
> [`event-metadata amendment`](v4_9f_a2_raw_v8_step2_v2_event_metadata_amendment_2026-08-09.md)
> closes that ambiguity and carries the current artifact identities. This
> record remains the accepted full-case construction baseline; values below
> have been refreshed to the amended authority.

## 1. Accepted boundary

This record accepts the corrected deterministic V2 seed as a closed input for
two independent, counting-only 475-case feasibility preflights. It supersedes
the execution-closure decision in the earlier provisional seed acceptance; it
does not erase the predecessor evidence that record established.

The correction closes the exact construction authority that the S1-A2 boundary
review falsified:

- all 18 recurrence kernels now bind one exact physical transition expansion;
- every physical transition receives one deterministic input symbol and one
  positive quotient/remainder share of the step's logical count;
- ordinary and local derivation-unit contexts are explicit and disjoint;
- all 16 event subject types bind ordered field sources or exact raw bytes;
- every event cardinality is the count of the exact constructed source list;
- the 12 local states, 11 adjacent transitions, initial/terminal selectors,
  result cells, cache keys, and commitment are exact;
- hash, retention, depth, rule/application, final-result, and stream programs
  bind their order and source material; and
- every emission binds its exact token subject role, subject-ordinal source,
  observed-value source, and ordinary/null logical-step source; and
- unresolved local catalog members and placeholder `CONST_U128(1)` event
  cardinalities are rejected.

No expected 475-case result vector is present in the seed.

## 2. Falsification and correction evidence

The independent fail-first suite originally produced:

```text
1 passed, 3 failed
```

It demonstrated that equal-width, schema-valid transition subjects could keep
the byte metrics unchanged while producing different subject and event-stream
hashes. During the correction's byte-oracle pass, it also exposed two local
commitment sources that named absent catalog members and a local descriptor
that depended on ordinary-only unit fields. Those findings were corrected
before acceptance.

The same closure suite now produces:

```text
21 passed, 0 failed
```

Its hostile cases reject missing, duplicated, reordered, or pointer-altered
kernel programs; host-chosen transition inputs; missing/duplicate subject
constructors; placeholder cardinality; incomplete unit context; absent local
endpoint sources; a wrong terminal-cell rule; and an invalid stream preimage.

## 3. Independent construction evidence

The acceptance boundary deliberately separates seed closure from S1-A2's
full-case differential execution:

1. The independently authored typed cell-transfer interpreter exercises the
   18 transfer families, checked UInt128 arithmetic, strict postorder, profile
   conditioning, case 69, and local-controller residuals.
2. Three versioned hand oracles independently recompute canonical subject
   bytes, event tokens, stream/final hashes, 18 resource metrics, and live-set
   snapshots for ordinary batch, stream/context, and local microfixtures.
3. The correction suite builds tagged subjects without importing the seed
   generator and pins:
   - an ordinary exact-boolean leaf bundle: 3,213 octets, SHA-256
     `8944d523e6671c3f7725d702cf8e675b4ab23b1131369faa7556fe21c1901a8d`;
   - the complete local 12-key/11-transition/12-cell/one-commitment bundle:
     30,205 octets, SHA-256
     `32c359df8922b8e929906387ce5c5a23f7d75c2cbe10c18e85eab5ac50d9e40b`.

Two independent exact event-stream and 18-metric results for every complete
case are the next gate, S1-A2. Moving that requirement here would duplicate
the two preflights and blur the gate boundary.

## 4. Frozen identities and size evidence

| Artifact or limit | Accepted value |
|---|---:|
| Event grammar bytes | 131,015 |
| Event grammar raw SHA-256 | `72bfd44ff159eb6904936ae32d0d25ab9b0c8536b87f5e93d055b521679401c8` |
| Generator SHA-256 | `47b4ecada8c661185e4087787b99e113b2366ff87ee06e951a21a85b9a4cab4f` |
| Seed catalog bytes | 13,419,905 |
| Seed catalog raw SHA-256 | `a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f` |
| Seed semantic catalog ID | `ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f` |
| Operational output target | <= 15,728,640 bytes |
| Operational headroom | 2,308,735 bytes |
| Strict individual-file upper bound | < 16,777,216 bytes |
| Strict-bound headroom | 3,357,311 bytes |

The stored artifact passed write/check/write/check with identical bytes, raw
hash, and semantic ID on both writes.

## 5. Reproduction commands and observed results

```bash
ruff format --check \
  scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py

ruff check \
  scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py

python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --write
python scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py --check

pytest -q \
  tests/test_raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_local_state_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_recurrence_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_profile_conditioning_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_cell_transfer_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_event_grammar_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_full_case_execution_closure_v49f.py \
  tests/test_raw_v8_step2_maximum_protocol_v2_source_security_v49f.py
```

Observed results:

```text
ruff format --check: 2 files already formatted
ruff check: All checks passed!
generator write/check/write/check: byte-identical on both cycles
focused seed/security acceptance matrix: 108 passed, 0 failed
```

## 6. Gate decision

`S1-A1` is `ACCEPTED` under the event-metadata amendment. `S1-A2` is the
single active mutable gate.

S1-A2 must treat the accepted seed as immutable input. A and B may share the
frozen input/output boundary and comparator schema, but they may not import the
generator or each other, reuse one execution helper, embed expected case
vectors, construct witnesses, tune F0 limits, or absorb disagreement by local
semantic patches. Any source drift or A/B disagreement is a falsification and
returns to a versioned correction.

## 7. Nonclaims

This GO does not accept either all-case preflight, final protocol V2, a
constructive maximum, a verifier or producer, Raw V8 Step 2/3, A2-M, A2-E,
Stage 1, offline Stage 2, paper/live activation, predictive edge, trading
safety, or profitability.

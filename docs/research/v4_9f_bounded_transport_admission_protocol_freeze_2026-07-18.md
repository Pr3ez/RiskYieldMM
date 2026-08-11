# V4.9F Bounded Transport Admission Protocol Freeze

**Date:** 2026-07-18

**Status:** Accepted bounded V4.9F-A1 local admission checkpoint. The broader
V4.9F capacity gate, public live factory, Stage 1 exit, and every operational
promotion gate remain closed.

**Roadmap position:** Stage 1 critical corrections, immediately after the
post-edit-revalidated V4.9E actor/provider/terminal checkpoint and before
durable saturation evidence, bounded parser turns, scalable actor state,
multi-session scheduling, provider qualification, privileged deployment, and
capacity/soak campaigns.

**Successor status (2026-07-20):** A1 remains the latest accepted checkpoint.
The successor
[`V4.9F-A2 measurement and enforcement protocol`](v4_9f_a2_measurement_and_enforcement_protocol_freeze_2026-07-20.md)
now defines an implemented but incomplete and unaccepted exploratory A2-M
boundary plus the evidence-integrity work that must precede its campaigns.

## 1. Decision

V4.9F is split into separately falsifiable internal slices:

```text
V4.9F-A1  signed single-session admission policy
          -> explicit FIFO tickets
          -> singleton command reservations
          -> cancellation-safe handoff
          -> two-phase shutdown barrier
          -> non-bypassable runtime helper grants

V4.9F-A2  measured high/low watermarks and durable saturation observation
          -> actor-ordered BACKPRESSURE convergence
          -> bounded parser work turns and control-output completion

V4.9F-A3  incremental actor hot-state reducer
          -> bounded live history/cache
          -> differential full-replay verification
          -> 10k/100k scaling and crash-prefix evidence

V4.9F-B   supervisor-owned multi-session queues
          -> empirically charged work units
          -> DRR challenger across independent scopes
          -> 100-scope capacity and fairness campaign
```

Only A1 is implemented in this checkpoint. These slices are implementation
boundaries, not independently production-ready protocols. A1 prevents an
unbounded number of coroutines from waiting invisibly on the V4.9E runtime
mutex. It does not yet prove that the actor, parser, SQLite projection, kernel
buffers, TLS buffers, provider, or complete multi-asset system has bounded
production capacity.

## 2. Confirmed starting failure mode

Before A1, four public actor-owned commands waited directly on one fair but
unbounded `asyncio.Lock`:

```text
process_next_ingress_v49d
dispatch_subscription_v49c
expire_ack_if_due_v49e
shutdown_current_v49e
```

That lock serialized execution but exposed no signed queue policy, maximum
outstanding count, work reservation, oldest age, rejection reason, admission
identity, cancellation lifecycle, shutdown barrier, or epoch. Queue delay was
also absent from diagnostics.

One ingress call can still parse every complete frame in its adopted RAW batch,
and every actor append can still validate/rebuild cumulative history. A1 does
not claim to close those A2/A3 scaling gaps.

## 3. Research synthesis and applicability

| Source | What it establishes | Limitation | Decision for RiskYieldMM |
|---|---|---|---|
| [Python 3.12 asyncio Queue](https://docs.python.org/3.12/library/asyncio-queue.html#asyncio.Queue) | A positive `maxsize` bounds FIFO item storage; a full non-blocking put raises; queue size is observable | Count only; no byte/work budget, durable order, command epoch, terminal barrier, or effect ownership | Do not use a background queue worker. Implement explicit caller-owned tickets around the current effect owner |
| [Python 3.12 asyncio synchronization](https://docs.python.org/3.12/library/asyncio-sync.html#asyncio.Lock) | Lock acquisition is fair among its waiters | Fairness on one lock is not capacity, freshness, cancellation outcome, or cross-session fairness | Retain the lock only as the execution mutex behind visible bounded admission |
| [Python task cancellation and timeouts](https://docs.python.org/3.12/library/asyncio-task.html#task-cancellation) | Cancellation is delivered cooperatively and may require cleanup; relative timeout cancellation can outlive the nominal timeout | It does not define transport-effect certainty | Remove or revoke only pre-entry tickets; after entry, preserve existing actor/owner uncertainty semantics |
| [RFC 6455 sections 5.4-5.5](https://www.rfc-editor.org/rfc/rfc6455.html#section-5.4) | Control frames can occur within fragmentation, remain wire-ordered, and must be handled; Ping latency motivates interjection | No numeric service deadline and no permission to overtake unread bytes | A2 may bound parser turns, but discovered Pong/Close output must complete before yield and must never overtake causal bytes |
| [websockets 16 memory guidance](https://websockets.readthedocs.io/en/16.0/topics/memory.html) | Persistently full buffers cause bufferbloat; bounded high/low watermarks propagate backpressure | High-level `max_queue` is not automatically present in this direct Sans-I/O/MemoryBIO integration | Measure and separately bound kernel, TLS, parser, RAW, event, actor, and database layers in A2/A3 |
| [Linux socket(7)](https://man7.org/linux/man-pages/man7/socket.7.html) | Kernel receive/send buffers are finite and reported sizes have Linux-specific accounting | Kernel buffers are not an application command queue or freshness deadline | Record them in later capacity campaigns; never treat A1 command limits as whole-system memory bounds |
| [Shreedhar and Varghese, Deficit Round Robin](https://openscholarship.wustl.edu/cse_research/339/) | DRR approximates throughput fairness for variable-size work with O(1) scheduling work | It is not a hard latency bound and does not define admission, durability, or project-specific costs | Evaluate only in V4.9F-B across independent sessions; never reorder commands or bytes within one session |

No source supplies correct numeric thresholds for this system. Queue age,
parser quantum, watermarks, and later DRR weights must come from frozen burst,
heartbeat, host-memory, database, and 100-scope workloads.

## 4. Alternatives rejected for A1

| Alternative | Reason rejected |
|---|---|
| Keep only the existing lock | Fair but invisible and unbounded; no admission rejection or diagnostics |
| Add a semaphore | Caps concurrent holders, which are already serialized, but does not provide exact FIFO tickets, per-kind reservations, shutdown ordering, or effect ownership |
| `asyncio.Queue(maxsize=N)` plus a worker | Moves effects to a background task, complicates caller cancellation and exception ownership, and still needs a separate causal ticket protocol |
| `asyncio.Condition` | Still requires an explicit FIFO and lifecycle; wakeups add avoidable grant races |
| Strict-priority shutdown or ACK queue | Could overtake earlier RAW/dispatch work and change the V4.9E causal outcome |
| Drop or coalesce durable work | Forbidden. Durable RAW, parser, actor, and transport obligations are never silently discarded |
| DRR inside one session | Variable-cost fairness does not justify reordering one session's causal command/byte stream |

## 5. Frozen A1 authority

`TransportCapacityPolicyV49F` is nested in the exact
`RuntimeEnvironmentManifestV4`. The runtime environment is a signed deployment
child, so its changed identity changes the deployment-bundle identity. The
verified capability carries `transport_capacity_policy_id_v49f`, and runtime
startup rechecks that exact ID against the instantiated gate.

The operational-manifest schema is therefore bumped from V4.9B to
`riskyieldmm_operational_manifest_v4_9f`. Old mappings are not silently
reinterpreted; they must be regenerated and signed under the new schema.

A policy commits:

- the exact A1 profile;
- exactly four active-plus-waiting singleton command slots;
- one frozen reservation weight for each command kind;
- the exact total work-accounting closure; and
- the maximum local queue wait in milliseconds.

The A1 work weights bound accounting and expose high-water diagnostics. They
are not yet empirical CPU, byte, latency, or database-cost estimates. A2/B may
replace them only through a new versioned signed policy and measured evidence.

An older deterministic admission without the nested policy retains the V4.9E
lock path for regression compatibility. It is not evidence of bounded
admission and cannot support promotion.

## 6. Frozen ticket order and lifecycle

The gate is event-loop-bound, in-memory, and deliberately not thread-safe,
matching asyncio's local concurrency model. It creates no worker task.

```text
WAITING -> GRANTED -> ENTERED -> RELEASED
    |          |
    +----------+----> CANCELLED (before caller effect entry only)
```

The gate assigns one increasing sequence and reserves count/work atomically
before its first `await`. Exactly one ticket may be outstanding for each kind:

```text
INGRESS
SUBSCRIPTION_DISPATCH
ACK_DEADLINE_EXPIRY
LOCAL_SHUTDOWN
```

This yields one active ticket and at most three waiters. Ingress or dispatch
pressure cannot consume the shutdown or ACK-deadline slot. Dedicated capacity
never grants priority: surviving tickets enter strictly by global admission
sequence.

Same-task reentry is rejected. A `ContextVar` lease marker is inherited by
child tasks, so a callback spawned inside an active command cannot reenter the
same runtime later. A different loop is rejected. Reconnect advances the gate
epoch only when the gate and execution mutex are quiescent; no old ticket can
execute in the next session epoch.

## 7. Two-phase shutdown barrier

Admitting `LOCAL_SHUTDOWN` creates a reversible reserved barrier at its sequence:

```text
shutdown ticket admitted
-> later tickets reject before effects
-> every earlier ticket keeps FIFO precedence
-> exact LOCAL_SHUTDOWN_COMMAND_STARTED becomes durable
-> runtime commits the barrier irreversibly
```

Cancellation, queue expiry, or validation failure before durable shutdown
command evidence clears only the reserved barrier. If the actor method returns
or its retained state proves the exact command exists, the runtime commits the
barrier. Later failures remain governed by V4.9E terminal convergence and the
barrier stays closed.

This distinction was added after an adversarial test reproduced a poisoning
failure where an invalid-state shutdown left a permanent barrier without any
durable shutdown event.

## 8. Cancellation, expiry, and physical deadlines

Pre-entry cancellation removes the exact waiting/granted ticket, releases only
its reservation, and promotes the next surviving sequence once. It authorizes
no socket read/write/abort, TLS mutation, governed clock sample, journal append,
runtime-state change, or termination. Closing the gate settles a queued
shutdown as a reversible reservation: it cannot leave either a barrier sequence
or a false committed-barrier diagnostic. Cancellation, timeout, and close are
exclusive pre-entry outcomes for counter accounting.

Granting a ticket is not effect entry. The awakened owner task samples the
event-loop clock again immediately before the context returns control to caller
code. If that actual entry boundary is later than the absolute local deadline,
the grant is revoked, capacity is released, and no caller effect runs. Queue
wait diagnostics use this actual entry time, not the earlier handoff time.

After `ENTERED`, cancellation belongs to the existing runtime, actor, TLS, and
socket effect/outcome contracts. The gate never labels an entered cancellation
as “no effect” and never shields the physical operation.

The A1 queue deadline uses only the local event-loop monotonic clock and only
decides whether caller effect code may start. It is not actor evidence and is
not mixed with governed `CLOCK_BOOTTIME` evidence.

The existing ingress and shutdown `timeout_seconds` still start after
admission. A true end-to-end admission-to-physical deadline requires a new
absolute governed deadline carried unchanged through runtime, actor, TLS, and
owner APIs. Subtracting event-loop time from governed BOOTTIME would be a clock
domain error, so A1 explicitly does not make that claim. ACK expiry already
uses its durable absolute deadline and rechecks it after admission.

## 9. Non-bypassable effect boundary

The runtime gate wraps the four public actor-owned commands before the existing
orchestration lock. The effect-capable private helpers
`_process_next_ingress_v49d_locked`,
`_dispatch_subscription_v49c_locked`,
`_commit_completed_application_message_v49e_locked`,
`_dispatch_automatic_protocol_output_v49d_locked`, and
`_send_local_websocket_close_v49e_locked` require the exact active grant before
mutation. The gate retains the issued grant object and checks object identity,
owner task, active context, lifecycle, epoch, sequence, policy, command kind,
reservation, and all local timestamps. An equal clone, field-forged object,
cross-task use, stale grant, or grant from another gate cannot authorize an
effect or terminal-barrier commit. Underscore naming is not treated as an
authority boundary.

Shutdown's internal ingress loop passes the active shutdown grant explicitly;
it does not reenter the public ingress queue. Direct helper calls without a
grant reject before owner, actor, parser, or projection mutation.

## 10. Local observability

The immutable snapshot exposes:

- admission epoch and policy ID;
- active sequence/kind;
- waiting sequences/kinds and oldest waiting age;
- current and maximum reserved work;
- current and maximum observed command count;
- last and maximum queue wait;
- duplicate, barrier, capacity, closed, timeout, cancellation, release, and
  close-before-entry counts; and
- terminal-barrier reservation/commit state.

These values are local diagnostics, not durable market or transport evidence.
A2 must define the durable saturation event and projection before any overload
terminal conclusion is accepted.

## 11. Implemented surfaces

Added:

- `riskyieldmm/trading/physical_transport_capacity_v49f.py`
- `tests/test_trading_physical_transport_capacity_v49f_contracts.py`
- `tests/test_trading_physical_transport_runtime_v49f_capacity.py`

Updated:

- `riskyieldmm/trading/operational_manifests_v4.py`
- `riskyieldmm/trading/physical_transport_runtime_v4.py`
- `tests/test_trading_operational_manifests_v4.py`
- `tests/test_trading_physical_transport_runtime_v49b.py`

No public live-factory export or construction path was opened.

## 12. Verification evidence

Final accepted evidence:

| Gate | Result |
|---|---:|
| Pure A1 policy/ticket/adversarial contracts after audit repair | 21 passed in 0.45 s |
| Signed-policy real Linux/TLS/runtime integration after audit repair | 3 passed in 46.99 s |
| Combined pure A1, operational-manifest, and live-factory-denial contracts | 85 passed in 1.88 s |
| Expanded manifest/artifact/runtime/actor/ingress/shutdown/timeout/legacy neighborhood | 144 passed in 632.73 s |
| Ruff on changed implementation/test surfaces | Passed |
| Python compilation on trading implementation and test surfaces | Passed |
| Verification-snapshot hashes after the full run | Unchanged |
| Full repository | 2,361 passed, 32 skipped, 3 known Python 3.12 multi-threaded-`fork()` deprecation warnings in 2,313.34 s |

The adversarial set includes FIFO order, exact singleton capacity, head/middle/
tail cancellation, granted-before-entry cancellation, grant-before-deadline but
entry-after-deadline rejection, fixed-seed cancellation stress, local deadline
expiry, wrong-loop use, same-task and inherited-child reentry, all-kind entered
exception cleanup, deterministic close, two-phase shutdown-barrier clearing/
commit, queued-shutdown close cleanup, equal-clone/forged/cross-task/stale grant
rejection, signed policy identity, all five direct private-helper bypasses,
duplicate live ingress, and preservation of the V4.9E regression neighborhood.

An independent read-only adversarial audit initially rejected A1 by reproducing
three defects: late caller entry after an on-time grant, a phantom committed
barrier after closing a queued shutdown, and forged/cloned grant acceptance.
The implementation and regression oracles above are the corrective result. A1
is not accepted merely because its first implementation passed its original
tests.

## 13. Acceptance and explicit nonclaims

A1 is accepted only as the bounded local admission checkpoint defined here.
The final full repository suite, formatting, lint, compilation, verification-
snapshot hashes, and `git diff --check` passed. This acceptance does not widen
the policy or promotion boundary.

Even after that acceptance, A1 will not establish:

- durable overload classification or BACKPRESSURE terminal evidence;
- bounded parser service time;
- bounded actor/database memory or append complexity;
- fairness or freshness across assets/sessions;
- provider behavior, certificate rollover, or network capacity;
- process-loss recovery of live TLS/socket objects;
- effective systemd/chronyd/clock exclusivity;
- a measured immutable production deployment;
- safe live or paper trading;
- predictive edge or profitability.

The public live factory remains closed.

## 14. Next decision gate

At this A1 checkpoint, the next decision was to freeze V4.9F-A2 before
implementation. The successor-status pointer above supersedes this historical
next-step statement. The comparison set was:

1. transient read pause versus hard freshness breach;
2. actor event shape and precedence for persistent saturation;
3. parser byte/frame/event/time quantum alternatives;
4. automatic Pong/Close completion before yield;
5. queue, TLS, kernel, actor, and SQLite watermark measurements; and
6. whether A2 and A3 should remain separate after benchmark evidence.

Do not start DRR or the 100-scope campaign until single-session parser and actor
costs are bounded and measurable; otherwise the scheduler would only distribute
unbounded work.

## 15. Worklog fallback

- Linear execution-log fallback: `RIS-274`
- A1 `START` comment: `e19bac5e-302f-4d28-a46a-a8c4c0646458`
- A1 corrective `IN_PROGRESS` comment: `c30f35ab-f799-4ecd-bafc-568ebf435e96`
- A1 `DONE` comment: `39118a89-bdc3-4953-b962-e6beb7485f5a`
- Dedicated issue creation: unavailable because the workspace is at its free
  issue limit
- Notion worklog connector: unavailable in this execution environment
- Repository worklog status: `DONE` for V4.9F-A1 only

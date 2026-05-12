# HTF Feature And Helper Temporal Audit

- **Date:** 2026-05-05
- **Scope:** HTF Python workflow, 1m model-facing feature stream, 4-class target, optimized features, helper features, and real-time reproducibility assumptions.

## Verdict

The HTF model-facing feature and helper stages are mostly causal and are aligned with the active `1m / target_4class` workflow. The optimizer trains and applies the rolling rank transform in chronological order, joins only the target column from labels, and generated optimized/helper artifacts do not contain label-only future fields.

The original unresolved item was higher-timeframe auxiliary broadcasts using timestamp flooring. That has now been addressed in phase 1-2 by adding source timestamp metadata and routing broadcasts through an availability-aware `merge_asof` aligner. Active OI, long/short, and funding columns are still configured to preserve current Bybit sampled/settled timestamp behavior; any future period-start aggregate source must declare an availability offset before it can be safely joined.

## Workflow Confirmed

The active multi-regime HTF workflow builds 8h, 24h, and 7d regimes, but the optimized/model-facing stage is currently:

| Component | Active setting | Evidence |
|---|---:|---|
| Optimized timeframe | `1m` | `scripts/feature_engineering/htf_multiregime_pipeline.py::_run_optimization` sets `timeframes=["1m"]`. |
| Target | `target_4class` | `_run_optimization` sets `targets=["target_4class"]`; helpers read/write under `1m/target_4class`. |
| Target type | Multiclass, 4 classes | `optimize_htf_features.py` maps `target_4class` to `multiclass`; current meta has `n_classes=4`. |
| Feature windows | Timeframe scaled | `compute_htf_features.py::get_window_scaling()` sets 1m windows to 60/120/240/480 bars and 15m windows to 4/8/16/32 bars. |
| Optimizer windows | Timeframe scaled | `rolling_rank_winsorize.py` uses 1m candidate windows 240/480/960 bars. |

Current optimizer metadata checked:

```text
data/htf_multiasset/btcusdt/htf_optimized/1m/optimized_target_4class_meta.json
timeframe=1m
target=target_4class
method=rolling_rank_winsorize
config=L=960, clip=(0.01,0.99), post=signed
target_type=multiclass
n_classes=4
n_batches=5856
total_rows=1405200
feature_cols=129
```

## Label Boundary

Future-looking calculations are present in the label stage by design:

- `close_end` and `end_return` use the batch end close.
- `compute_hybrid_distance_metrics()` scans future 15m bars inside the same batch.
- `compute_4class_labels()` uses those future distance metrics to assign `target_4class`.
- rows outside the allowed entry window are gated to `-1`.

This is acceptable because these columns are label artifacts, not live features. The optimizer joins labels with:

```text
timestamp, batch_id, target_4class
```

and filters valid target rows. It does not merge `close_end`, `end_return`, `remaining_bars`, or future-distance metrics into `X`.

Artifact schema check across sampled optimized/helper outputs found no label-only fields:

```text
data/htf_optimized*/.../1m/target_4class: label_only=[]
data/htf_with_helpers*/.../1m/target_4class: label_only=[]
```

Checked label-only field set:

```text
target_4class, target_breakfree, target_name, close_end, end_return,
dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low,
remaining_bars, bar_pos_15m
```

## Feature Causality

Core HTF feature calculations use standard causal rolling/lagged operations:

- no `shift(-...)` was found in the HTF feature pipeline files under audit;
- pandas/polars rolling windows are backward-looking by default;
- `_compute_past_distance_metrics()` uses `high[start:i]` and `low[start:i]`, excluding current/future rows;
- feature output is sorted by timestamp before streaming transforms.

The prediction-time convention must be explicit: row-level OHLCV features include the current row close/high/low. That is real-time reproducible only if prediction happens after that bar has closed. It is not valid for prediction at the bar open.

## Optimized Feature Stage

The rolling rank-winsorize optimizer is causal:

- `load_early_batches()` joins only `timestamp`, `batch_id`, and `target_4class`.
- data is sorted by `timestamp, batch_id` before validation and application.
- walk-forward validation trains on earlier rows and validates on later rows.
- `transform_streaming()` ranks each value against the existing buffer, then updates the buffer with the current row.
- application persists rolling state snapshots for incremental resume.

The current optimized artifacts preserve only feature columns and allowed metadata. They do not preserve the target column in model-facing output.

Cached optimizer configs are now guarded by a selection input signature covering
the early feature/label files, target, timeframe, validation settings, candidate
grid, output feature policy, and optimizer selection implementation version. If
that signature changes, grid search reruns before streaming application. If the
newly selected transform config differs from cached metadata, existing optimized
batches are rebuilt from the first batch rather than reused under the wrong
transform.

The grouped optimizer-selection speedup reuses causal raw rolling ranks by
window and applies each candidate's clipping/post-transform to those cached
ranks. Validation rank matrices are built with a Numba-parallel kernel that
preserves the original streaming buffer semantics, including NaN rows not
advancing the per-feature buffer. Focused regression coverage compares it
against the previous per-candidate validation path and requires identical best
config and scores.

## Speedup Parity Evidence

Implemented guarded speedups:

- opposite-family label windows precompute distance summaries when the active
  `opposite_family_first_half` shape is detected; otherwise the original
  row-scanning kernel is used;
- optimizer selection reuses causal rolling-rank validation arrays by window;
- rolling-rank validation arrays are computed in parallel across feature
  columns while preserving streaming parity;
- optimized output reuse is invalidated when selected transform config changes.

Focused validation:

```bash
python -m pytest \
  tests/test_htf_label_kernel_parity.py \
  tests/test_htf_optimizer_selection_parity.py \
  tests/test_htf_auxiliary_alignment.py \
  tests/test_htf_incremental_resume.py \
  tests/test_htf_multi_asset_pipeline.py \
  tests/test_htf_workflow_contract.py \
  -q
```

This suite validates label-distance parity, optimizer-selection parity, optimizer
resume safety, auxiliary as-of alignment, incremental resume behavior, and the
multi-asset HTF workflow contract.

## Helper Stage

Helper cache construction is mostly live-safe:

- helper inputs are restricted to raw OHLCV columns: `timestamp`, `batch_id`, `close`, `open`, `high`, `low`, `volume`;
- helper preparation derives returns from current/past close and rolling volatility;
- each helper fit uses `X_df.iloc[:chunk_start]`, so no prediction chunk or future rows enter fit;
- prediction transforms only the current chunk plus bounded past context for context-replay helpers;
- Kalman and EGARCH use streaming handoff instead of replaying already-seen context.

Current helper causality audit:

```text
test_output/htf_helper_causality_audit/20260505_100559
```

Summary:

| Helper | Prefix causality | Context replay | State handoff |
|---|---:|---:|---:|
| CUSUM | pass | differs with added past context | n/a |
| EGARCH | pass | n/a | pass |
| GARCH | pass | differs with added past context | n/a |
| Kalman | pass | n/a | pass |
| OU | pass | pass | n/a |

The CUSUM/GARCH context differences are not future leakage by themselves. They mean live inference must reproduce the same context-replay policy used offline.

Current helper metadata reports:

```text
helper_contract_version=2026-04-13-live-safe-helper-contract-v1
cusum=context_replay_v1
garch=context_replay_v1
ou=context_replay_v1
kalman=streaming_handoff_v1
egarch=streaming_handoff_v1
```

## Broadcast Availability Contract

`compute_htf_features.py::broadcast_higher_tf()` says it uses the last complete higher-timeframe bar, but the implementation floors the base timestamp to the higher-timeframe boundary and joins on that timestamp:

```text
df_base["_merge_ts"] = base_merge_ts.dt.floor(f"{high_mins}min")
df_high["_merge_ts"] = high_merge_ts
```

The active source-resolution plan is:

| Target TF | Source | Source TF | Method |
|---|---|---:|---|
| 1m | OHLCV | 1m | native |
| 1m | mark/index/premium | 1m | native |
| 1m | open interest | 5m | broadcast |
| 1m | long/short ratio | 5m | broadcast |
| 1m | funding rate | 8h | broadcast |
| 15m | OHLCV and aux prices | 15m | native |
| 15m | open interest | 15m | native |
| 15m | long/short ratio | 15m | native |
| 15m | funding rate | 8h | broadcast |

Local fetched files show mixed timestamp conventions:

- Bybit klines are stored from the API `start` field, so candle timestamps are period starts.
- 5m open interest starts at `2021-01-01 00:05:00`, consistent with a completed 5m value.
- 5m long/short ratio starts at `2021-01-01 00:00:00`, which needs an explicit endpoint availability assumption.
- funding starts at 8h event timestamps such as `2021-01-01 00:00:00`.

Therefore, the broadcast code is safe only if each broadcast source timestamp is
handled as an availability timestamp. The maintained path now records source
timestamp semantics and routes alignment through availability-aware as-of joins.
Synthetic coverage in `tests/test_htf_auxiliary_alignment.py` proves that a
period-start aggregate cannot be visible to 1m rows before its source period has
completed.

## Existing Validation Evidence

Pipeline validation artifact:

```text
test_output/htf_phase9_validation_all_regimes_after_fix.json
total_checks=474
failed_checks=0
```

Usability validation artifacts from 2026-05-04:

```text
test_output/htf_validation_usability/8h_latest.json
test_output/htf_validation_usability/24h_latest.json
test_output/htf_validation_usability/7d_latest.json
```

No all-null or constant-column failures were found in those reports. The only repeated high-null fields are long-window funding z-scores, which is expected from sparse 8h funding data and warmup history.

## Required Follow-Up

1. Add a strict publication-lag option for conservative live deployment comparisons if Bybit endpoint latency proves material.
2. Keep the optimized/helper label-only column guard in the mandatory smoke suite.
3. Keep `tests/test_htf_auxiliary_alignment.py` in the mandatory smoke suite for causal broadcast alignment.
4. Keep the live-inference convention explicit: predictions are made after the current 1m bar closes.

## Final Assessment

No confirmed label leakage was found in the model-facing optimized or helper artifacts. The 4-class target is future-looking by design and stays isolated in the label stage. The helper stack is causally fitted and has a reproducible state/context contract.

The auxiliary broadcast timestamp contract is now explicit per source in `compute_htf_features.py`. The remaining live-parity assumption is endpoint publication latency for sampled Bybit context streams; that should be tested separately before deploying strict real-time inference.

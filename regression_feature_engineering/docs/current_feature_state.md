# Current Regression Feature State

## Purpose

Keep one blunt source of truth for what `regression_feature_engineering/`
actually built, what works technically, and what has not improved prediction.

## Current Status

Status: technically valid feature artifacts exist, but the current
`regression_path_features_v1` feature set is **not predictively promoted**.

Current active next step: use the adaptive ranked-signal router instead of
hard-coding one branch per side:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_router
```

The router evaluates fixed UP/DOWN ranked-signal candidates using validation
evidence only, selects the best passing branch per prediction fold, and then
scores the unseen prediction batch. The underlying candidate model remains
ElasticNet relevance selection plus optional causal ROCKET plus CatBoostRanker.
It is documented in `rpf_ranked_signal_plan.md`.

2026-06-22 ranked-signal no-sequence baseline:

- command:
  `python -m regression_feature_engineering.walkforward.rank_signal`;
- runs:
  - UP:
    `test_output/rpf_ranked_signal/20260622_212507_rank_signal_btcusdt_8h_b_up/`;
  - DOWN:
    `test_output/rpf_ranked_signal/20260622_213040_rank_signal_btcusdt_8h_b_down/`;
- common setup:
  - `sequence_mode=none`;
  - `n_steps=30`;
  - `holdout_steps=10`;
  - side-specific evidence panel with `160` tabular candidates;
  - ElasticNet relevance selector before CatBoostRanker;
  - live-safe threshold plus causal signal budget;
- best UP tuning trial:
  - `train_batches=40`, `val_batches=5`;
  - `YetiRank`, `iterations=100`, `depth=3`, `learning_rate=0.01`;
  - mean selected features `20.9`;
  - tuning precision `0.500`, lift `1.070`, active-window rate `0.400`;
  - holdout precision `0.680`, lift `1.331`, active-window rate `0.500`;
  - holdout emitted `25` signals with `17 TP / 8 FP`;
- best DOWN tuning trial:
  - `train_batches=80`, `val_batches=10`;
  - `YetiRank`, `iterations=50`, `depth=3`, `learning_rate=0.03`;
  - mean selected features `39.35`;
  - tuning precision `0.578`, lift `1.575`, active-window rate `0.450`;
  - holdout precision `0.432`, lift `2.185`, active-window rate `0.900`;
  - holdout emitted `74` signals with `32 TP / 42 FP`;
- interpretation:
  - UP produced sparse higher-precision holdout signals but still missed
    high-target windows;
  - DOWN produced stronger lift and coverage, but too many false positives;
  - the next controlled test is `causal_rocket_v1` sequence memory using the
    same windows, tabular panels, and narrow search ranges.

2026-06-22 ranked-signal causal ROCKET A/B:

- runs:
  - UP:
    `test_output/rpf_ranked_signal/20260622_214036_rank_signal_btcusdt_8h_b_up/`;
  - DOWN:
    `test_output/rpf_ranked_signal/20260622_214751_rank_signal_btcusdt_8h_b_down/`;
- common setup:
  - same `30` frozen windows and `10` holdout windows as the no-sequence
    baseline;
  - same side-specific tabular evidence panels;
  - side-specific `selected_cnn_panel_160.json` as sequence input;
  - `sequence_mode=causal_rocket_v1`;
  - `sequence_length=16`;
  - `rocket_kernels=128`;
  - ROCKET generated `384` causal sequence features per fold from `160`
    sequence input features;
- UP holdout comparison:
  - no sequence: precision `0.680`, lift `1.331`, active-window rate `0.500`,
    high-target capture `0.571`, `17 TP / 8 FP`;
  - ROCKET: precision `0.568`, lift `1.111`, active-window rate `0.900`,
    high-target capture `0.714`, `21 TP / 16 FP`;
  - interpretation: ROCKET increased coverage and high-target capture for UP
    but doubled false positives and reduced precision/lift;
- DOWN holdout comparison:
  - no sequence: precision `0.432`, lift `2.185`, active-window rate `0.900`,
    high-target capture `0.750`, `32 TP / 42 FP`;
  - ROCKET: precision `0.139`, lift `0.702`, active-window rate `0.800`,
    high-target capture `0.250`, `5 TP / 31 FP`;
  - interpretation: ROCKET is rejected for DOWN in this configuration because
    holdout precision dropped below base rate and false discovery rose to
    `0.861`;
- decision:
  - do not widen `causal_rocket_v1` globally;
  - keep no-sequence as the current DOWN baseline;
  - for UP, ROCKET is only a diagnostic clue that sequence memory can improve
    coverage, but it needs stricter false-positive control before any wider
    run.

Next ranked-signal decision-control test:

- UP branch:
  - use `causal_rocket_v1`;
  - freeze the best ROCKET model shape from the A/B enough to isolate decision
    control;
  - test stricter thresholds and lower signal budgets:
    `threshold_quantile=0.95,0.975,0.99` and
    `max_signals_per_batch=1,2,3`;
  - purpose: keep the improved high-target capture from ROCKET while reducing
    false positives and recovering precision/lift;
- DOWN branch:
  - use `sequence_mode=none`;
  - freeze around the best no-sequence DOWN model shape;
  - test stricter thresholds and lower signal budgets:
    `threshold_quantile=0.95,0.975,0.99` and
    `max_signals_per_batch=1,3,5`;
  - purpose: preserve DOWN lift while reducing the `42` holdout false positives
    seen in the no-sequence baseline;
- success condition:
  - UP must beat the no-sequence UP holdout precision/lift or keep similar lift
    with materially better high-target capture and acceptable false discovery;
  - DOWN must keep lift above `1.20` and reduce false positives versus the
    current no-sequence holdout;
  - any config with precision below the local base rate is rejected regardless
    of active-window rate.

2026-06-22 ranked-signal decision-control result:

- runs:
  - UP:
    `test_output/rpf_ranked_signal/20260622_221932_rank_signal_btcusdt_8h_b_up/`;
  - DOWN:
    `test_output/rpf_ranked_signal/20260622_222610_rank_signal_btcusdt_8h_b_down/`;
- UP decision-control:
  - used `causal_rocket_v1`, `threshold_quantile=0.95`,
    `max_signals_per_batch=1`;
  - holdout emitted `9` signals with `5 TP / 4 FP`;
  - precision `0.556`, lift `1.088`, active-window rate `0.900`;
  - false-positive rate fell to `0.00341`, but precision/lift did not beat the
    no-sequence UP baseline (`0.680` precision, `1.331` lift);
  - decision: UP ROCKET decision-control is not promoted. It proves the signal
    budget can reduce false positives, but it discards too much useful signal.
- DOWN decision-control:
  - used `sequence_mode=none`, `threshold_quantile=0.95`,
    `max_signals_per_batch=1`;
  - holdout emitted `9` signals with `4 TP / 5 FP`;
  - precision `0.444`, lift `2.246`, active-window rate `0.900`;
  - false-positive rate improved from `0.02182` to `0.00260`;
  - cost per row improved from `0.2721` to `0.2067`;
  - high-target capture stayed `0.750`;
  - decision: this is the current best DOWN precision-control candidate.
    It has very low recall, but for the specialist ranked-signal objective it
    is cleaner than the wider DOWN baseline.

2026-06-23 UP ROCKET failure diagnosis:

- the ROCKET branch was mechanically valid:
  - `160` sequence-panel inputs;
  - `128` kernels;
  - `384` appended ROCKET features per fold;
  - train-only sequence scaling;
  - causal windows ending at the current row;
- failure mode:
  - ROCKET increased activation and high-target-window capture, but worsened
    score ordering quality;
  - UP no-sequence holdout offline top-5 precision averaged about `0.90`;
  - UP ROCKET holdout offline top-5 precision averaged about `0.68`;
  - ROCKET top-1 was positive in only `6/10` holdout windows, while
    no-sequence top-1 was positive in `10/10`;
  - bad ROCKET windows include low-positive-rate batches where top scores were
    negatives, especially `5850`, `5853`, and `5856`;
- likely cause:
  - ElasticNet selects only tabular features before sequence appending;
  - CatBoost then receives all ROCKET features without a second selection or
    branch regularization step;
  - `384` sequence features can dominate shallow ranker splits and add noisy
    score-scale drift;
- next diagnostic:
  - do not widen full ROCKET;
  - test smaller ROCKET branches (`16`, `32`, `64` kernels) on a longer
    `50`-window run;
  - in parallel, confirm UP no-sequence and DOWN no-sequence/control on the
    same longer windows.

2026-06-23 ranked-signal longer 50/20 confirmation:

- common setup:
  - `n_steps=50`;
  - `holdout_steps=20`;
  - the first `30` windows are Optuna/tuning windows and the latest `20`
    windows are reserved holdout;
  - frozen prediction batches split as tuning `5807..5836`, holdout
    `5837..5856`;
- UP no-sequence decision grid:
  - run:
    `test_output/rpf_ranked_signal/20260622_224229_rank_signal_btcusdt_8h_b_up/`;
  - best tuning config used `train_batches=40`, `val_batches=5`,
    `threshold_quantile=0.975`, `max_signals_per_batch=3`;
  - holdout emitted `21` signals with `12 TP / 9 FP`;
  - holdout precision `0.571`, base rate `0.552`, lift `1.036`;
  - active-window rate `0.350`, high-target capture `0.267`;
  - interpretation: this did not preserve the earlier no-sequence UP
    advantage on the larger holdout. It is weak because precision barely beats
    the local base rate.
- UP small ROCKET:
  - run:
    `test_output/rpf_ranked_signal/20260623_000231_rank_signal_btcusdt_8h_b_up/`;
  - best tuning config used `train_batches=40`, `val_batches=5`,
    `sequence_mode=causal_rocket_v1`, `sequence_length=16`,
    `rocket_kernels=32`, `threshold_quantile=0.95`,
    `max_signals_per_batch=2`;
  - holdout emitted `17` signals with `13 TP / 4 FP`;
  - holdout precision `0.765`, base rate `0.552`, lift `1.386`;
  - active-window rate `0.450`, high-target capture `0.467`;
  - interpretation: the small ROCKET branch fixed part of the earlier full
    ROCKET failure. It is now the strongest UP ranked-signal candidate, but it
    is still sparse and misses `0.533` of high-target windows.
- DOWN no-sequence control:
  - run:
    `test_output/rpf_ranked_signal/20260623_002707_rank_signal_btcusdt_8h_b_down/`;
  - best tuning config used `train_batches=80`, `val_batches=10`,
    `sequence_mode=none`, `threshold_quantile=0.95`,
    `max_signals_per_batch=3`;
  - holdout emitted `37` signals with `17 TP / 20 FP`;
  - holdout precision `0.459`, base rate `0.202`, lift `2.274`;
  - active-window rate `0.650`, high-target capture `0.571`;
  - interpretation: DOWN remains useful by lift and base-rate separation, but
    false discovery is still high at `0.541`. It is not a clean promoted
    signal yet.
- decision:
  - current best UP path: small `causal_rocket_v1` plus ElasticNet plus
    CatBoostRanker;
  - current best DOWN path: no-sequence ElasticNet plus CatBoostRanker;
  - do not retry full ROCKET for DOWN;
  - do not treat no-sequence UP as the current best after the larger holdout.

2026-06-23 side-asymmetry audit:

- reason for audit:
  - UP currently prefers small `causal_rocket_v1`, while DOWN prefers
    no-sequence tabular ranking;
  - this could be legitimate target asymmetry or a side-handling bug, so the
    code and artifacts were checked directly.
- code checks:
  - `rank_signal.py` derives relevance symmetrically:
    `up_extreme / (up_extreme + down_extreme)` for UP and
    `down_extreme / (up_extreme + down_extreme)` for DOWN;
  - binary labels are mirrored:
    `up_extreme >= 2 * down_extreme` for UP and
    `down_extreme >= 2 * up_extreme` for DOWN;
  - joined rows use exact `timestamp,batch_id`;
  - prediction decisions use timestamp-order causal threshold/budget, not
    future-batch top-k sorting;
  - `resolve_context(... target_col=UP_EXTREME)` is confusing in
    `rank_signal.py`, but current ranked-signal folds load both UP and DOWN
    extreme label columns directly, so it is not the cause of side asymmetry.
- label distribution checks on the same 50/20 split:
  - tuning windows `5807..5836`: UP rate `0.419`, DOWN rate `0.386`;
  - holdout windows `5837..5856`: UP rate `0.552`, DOWN rate `0.202`;
  - both-positive rate is `0.0`; labels are mutually exclusive under the
    `2x` rule;
  - holdout is therefore strongly UP-dominant, which makes a different UP/DOWN
    model branch plausible.
- panel checks:
  - UP and DOWN tabular panels each contain `160` unique features;
  - only `47` features overlap; Jaccard overlap is about `0.172`;
  - UP panel has more `up` token features, DOWN panel has more `down` token
    features, but both also contain neutral and opposite-side features;
  - opposite-side selected features are not automatically suspicious because
    ElasticNet coefficients can be positive or negative and can describe
    exhaustion/failure context.
- sequence checks:
  - full ROCKET used `128` kernels and appended `384` sequence features;
  - the improved UP small-ROCKET run used `32` kernels and appended `96`
    sequence features;
  - this supports the current explanation that full ROCKET was too wide/noisy,
    while a smaller sequence branch may add useful short-memory context for UP.
- conclusion:
  - no direct side inversion, label formula bug, or obvious join bug was found;
  - the different UP/DOWN branches are plausible given the asymmetric holdout
    label regime and side-specific panels;
  - still, this is not enough for promotion. The next validation must test the
    frozen UP-small-ROCKET and DOWN-no-sequence shapes across older
    chronological slices.

2026-06-23 adaptive router implementation:

- command:
  `python -m regression_feature_engineering.walkforward.rank_signal_router`;
- output root:
  `test_output/rpf_ranked_signal_router/`;
- router behavior:
  - evaluates fixed candidate branches per side on validation batches only;
  - selects the best passing candidate by validation `ranked_signal_quality`;
  - emits no signal for a side if every candidate fails validation gates;
  - prediction metrics are outer evaluation and never select the branch;
  - writes conflict diagnostics if UP and DOWN fire on the same timestamp;
- candidate set `default_v1`:
  - UP: no-sequence plus small ROCKET with `16`, `32`, and `64` kernels;
  - DOWN: no-sequence plus diagnostic small ROCKET with `16`, `32`, and `64`
    kernels;
- validation gates:
  - minimum validation signal count `3`;
  - minimum validation precision lift `1.10`;
  - maximum validation false discovery rate `0.60`;
  - minimum validation active-window rate `0.10`;
  - maximum validation zero-signal-window rate `0.90`;
- supporting change:
  - `rank_signal` now supports `--window-end-offset-steps`, so older
    chronological slices can be tested without always using the latest windows.

2026-06-23 adaptive router 240-window result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_020631_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `240` prediction windows, batches `5617..5856`, `20`-window reporting
  blocks, `default_v1` candidate set;
- UP summary:
  - rows `57,600`, base positive rate `0.3961`;
  - signals `185`, true/false positives `74/111`;
  - precision `0.4000`, precision lift `1.0100`;
  - active-window rate `0.3458`, zero-signal-window rate `0.6542`;
  - high-target capture `0.2388`;
  - result: not useful enough. Precision is essentially base-rate level.
- DOWN summary:
  - rows `57,600`, base positive rate `0.3753`;
  - signals `244`, true/false positives `124/120`;
  - precision `0.5082`, precision lift `1.3541`;
  - active-window rate `0.3458`, zero-signal-window rate `0.6542`;
  - high-target capture `0.3077`;
  - result: useful lift exists, but false discovery remains high and signal
    coverage is still sparse.
- branch selection:
  - UP selected candidates: `up_none_v1` `84` windows,
    `up_rocket_16_v1` `48`, `up_rocket_64_v1` `27`,
    `up_rocket_32_v1` `21`, no passing candidate `60`;
  - DOWN selected candidates: `down_none_v1` `76` windows,
    `down_rocket_16_diag_v1` `38`, `down_rocket_32_diag_v1` `31`,
    `down_rocket_64_diag_v1` `31`, no passing candidate `64`;
  - no UP/DOWN timestamp conflicts were emitted.
- validation-to-prediction check:
  - validation quality had near-zero correlation with prediction precision;
  - UP validation quality vs prediction precision correlation approximately
    `-0.035`;
  - DOWN validation quality vs prediction precision correlation approximately
    `0.013`;
  - conclusion: the router mechanics are valid, but the validation gates are
    not predictive enough. More broad runs should wait until candidate
    selection/gating is tightened.

2026-06-23 strict router-gate 120-window result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_102707_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `120` prediction windows, batches `5737..5856`;
- strict gates added:
  - validation precision lift `>= 1.25`;
  - validation false discovery rate `<= 0.50`;
  - validation active-window rate `>= 0.20`;
  - validation zero-signal-window rate `<= 0.80`;
  - validation active batch count `>= 2`;
  - validation lift-positive batch rate `>= 0.60`;
  - validation median active precision lift `>= 1.20`;
  - validation median active false discovery rate `<= 0.50`;
- result:
  - UP: base rate `0.4299`, signals `12`, `5 TP / 7 FP`,
    precision `0.4167`, lift `0.9692`, active-window rate `0.0417`;
  - DOWN: base rate `0.3333`, signals `15`, `3 TP / 12 FP`,
    precision `0.2000`, lift `0.6000`, active-window rate `0.0417`;
- comparison to the previous loose router on the exact same `5737..5856`
  prediction windows:
  - old UP: signals `98`, `43 TP / 55 FP`, precision `0.4388`,
    lift `1.0207`, active-window rate `0.3583`;
  - old DOWN: signals `116`, `58 TP / 58 FP`, precision `0.5000`,
    lift `1.5000`, active-window rate `0.3333`;
- interpretation:
  - the strict aggregate-plus-consistency gates are too restrictive and do not
    improve prediction quality;
  - pass rate fell to `0.125` per side, but selected windows were not better;
  - do not rerun this exact strict-gate configuration.

2026-06-23 router failure inspection:

- core finding:
  - the binary UP/DOWN targets are strongly batch-regime dominated;
  - row-level ranker precision mostly follows the prediction batch positive
    rate, not row-level selection skill;
  - active-window precision correlation with true batch base rate:
    UP approximately `0.842`, DOWN approximately `0.777`;
  - active-window rate had almost no correlation with true batch base rate
    (`-0.023` UP, `0.057` DOWN), so the router fires in bad and good batches
    at similar rates.
- batch target distribution over the 240-window loose-router span:
  - UP: `62` all-zero batches, `26` all-one batches, `152` mixed batches,
    mean positive rate `0.396`, std `0.383`;
  - DOWN: `64` all-zero batches, `18` all-one batches, `158` mixed batches,
    mean positive rate `0.375`, std `0.371`;
  - lag-1 batch positive-rate correlation was effectively zero:
    `0.014` UP and `-0.045` DOWN.
- row-selection lift on active windows:
  - UP median precision lift `1.00`;
  - DOWN median precision lift `1.017`;
  - this means row-level ranking is usually near base-rate performance, with
    occasional useful bursts but no stable transfer.
- validation-selection diagnosis:
  - validation quality buckets are not monotonic with prediction quality;
  - for UP and DOWN, the best prediction lift came from middle validation
    quality buckets, not from the highest validation quality bucket;
  - therefore simply tightening validation gates is not enough.
- artifact gap:
  - router currently writes prediction scores and candidate validation
    summaries, but not selected features, validation row scores, validation
    per-batch scores, or sequence diagnostics;
  - those artifacts are needed before deeper feature-level debugging.
- next engineering implication:
  - do not continue broad router sweeps yet;
  - first add richer router diagnostics;
  - then test whether batch-regime prediction is possible separately from
    row-level ranking.

2026-06-23 router diagnostic artifact preparation:

- added router outputs:
  - `candidate_validation_scores.parquet`;
  - `candidate_validation_window_metrics.parquet`;
  - `selected_features.parquet`;
  - `sequence_diagnostics.parquet`;
- smoke run:
  `test_output/rpf_ranked_signal_router/20260623_111515_rank_signal_router_btcusdt_8h_b/`;
- smoke artifact row counts:
  - validation scores: `28,800`;
  - validation window metrics: `120`;
  - selected features: `482`;
  - sequence diagnostics: `16`;
- validation:
  - focused router tests passed: `15 passed`;
 - `rank_signal.py` and `rank_signal_router.py` compile;
  - `git diff --check` passed for touched files.

2026-06-23 loose-router diagnostic 120-window result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_111705_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `120` prediction windows, batches `5737..5856`, loose `default_v1`
  validation gates, diagnostic artifacts enabled;
- artifact counts:
  - candidate validation rows: `960`;
  - candidate validation row scores: `1,728,000`;
  - candidate validation window metrics: `7,200`;
  - selected feature rows: `28,654`;
  - router prediction rows: `57,600`;
  - decision rows: `214`;
  - conflict rows: `0`;
- side summary:
  - UP: base rate `0.4299`, signals `98`, `43 TP / 55 FP`,
    precision `0.4388`, lift `1.0207`, active-window rate `0.3583`;
  - DOWN: base rate `0.3333`, signals `116`, `58 TP / 58 FP`,
    precision `0.5000`, lift `1.5000`, active-window rate `0.3333`;
- this exactly reproduces the earlier loose-router metrics on the same
  `5737..5856` windows, so the new diagnostic instrumentation did not alter
  prediction behavior.

Selected-candidate outcomes from this run:

| Side | Candidate | Windows | Signals | TP/FP | Precision | Lift |
|---|---:|---:|---:|---:|---:|---:|
| DOWN | `down_rocket_16_diag_v1` | `20` | `24` | `14/10` | `0.583` | `1.568` |
| DOWN | `down_none_v1` | `46` | `62` | `34/28` | `0.548` | `1.559` |
| DOWN | `down_rocket_64_diag_v1` | `13` | `24` | `10/14` | `0.417` | `1.373` |
| DOWN | `down_rocket_32_diag_v1` | `8` | `6` | `0/6` | `0.000` | `0.000` |
| UP | `up_none_v1` | `47` | `48` | `24/24` | `0.500` | `1.130` |
| UP | `up_rocket_64_v1` | `12` | `15` | `9/6` | `0.600` | `1.121` |
| UP | `up_rocket_32_v1` | `7` | `4` | `1/3` | `0.250` | `0.824` |
| UP | `up_rocket_16_v1` | `27` | `31` | `9/22` | `0.290` | `0.781` |

Validation-to-prediction transfer from selected candidates:

- validation precision/lift looks much stronger than prediction precision/lift;
- UP `up_none_v1` validation lift averaged about `2.01`, but prediction lift
  was only `1.13`;
- UP `up_rocket_16_v1` validation lift averaged about `1.56`, but prediction
  lift fell below base rate at `0.78`;
- DOWN `down_rocket_32_diag_v1` validation lift averaged about `1.71`, but
  prediction produced `0 TP / 6 FP`;
- interpretation:
  - validation selection is still overestimating next-batch transfer;
  - `up_rocket_16_v1`, `up_rocket_32_v1`, and
    `down_rocket_32_diag_v1` should be removed from the next default candidate
    set;
  - `up_none_v1`, `up_rocket_64_v1`, `down_none_v1`, and
    `down_rocket_16_diag_v1` are the only branches worth keeping for the next
    controlled router pass.

Feature-selection diagnostics from this run:

- ElasticNet-selected feature sets are not random:
  - DOWN candidates had mean consecutive selected-feature Jaccard around
    `0.66`;
  - UP ROCKET candidates had mean consecutive Jaccard around `0.63`;
  - UP no-sequence had lower but still structured Jaccard around `0.55`;
- selected features are concentrated in `conf`, `room`, `liq`, and `accept`
  families, with smaller `vol` participation;
- conclusion:
  - current failure is not primarily "ElasticNet picks random features";
  - the larger issue remains weak validation-to-prediction transfer and
    batch-regime dominance.

2026-06-23 prequential reliability router implementation:

- active transfer-fix path:
  `python -m regression_feature_engineering.walkforward.rank_signal_router`
  with `--selection-mode prequential_reliability_v1`;
- backward-compatible baseline:
  `--selection-mode validation_only` remains the default and preserves old
  router behavior;
- new candidate set:
  `--candidate-set pruned_reliability_v1`;
- active candidates:
  - UP: `up_none_v1`, `up_rocket_64_v1`;
  - DOWN: `down_none_v1`, `down_rocket_16_diag_v1`;
  - optional diagnostic only: `down_rocket_64_diag_v1` via
    `--include-diagnostic-candidates`;
- removed from active candidate selection:
  `up_rocket_16_v1`, `up_rocket_32_v1`,
  `down_rocket_32_diag_v1`;
- selection rule:
  - every candidate is still trained/validated/scored on the prediction batch;
  - current prediction-batch results are written as shadow diagnostics;
  - current selection can use only current validation sanity checks plus prior
    matured prediction-window reliability;
  - current prediction-batch labels are added to reliability memory only after
    the current routing decision;
  - if reliability history is insufficient, warmup policy is no signal.
- new artifacts:
  - `candidate_prediction_window_metrics.parquet`;
  - `candidate_reliability_state.parquet`;
  - `candidate_selection_audit.parquet`;
  - `reliability_block_summary.parquet`;
  - `batch_regime_diagnostics.parquet`;
  - optional `candidate_prediction_scores.parquet` when
    `--write-candidate-prediction-scores` is set.
- validation:
  - focused router tests passed: `11 passed`;
  - `rank_signal_router.py` compiles.
- runtime smoke:
  `test_output/rpf_ranked_signal_router/20260623_124709_rank_signal_router_btcusdt_8h_b/`;
  - `2` prediction windows, pruned candidates, prequential reliability mode;
  - first window emitted no selected signal because reliability history was
    empty;
  - second window selected `up_rocket_64_v1` after prior matured history became
    available;
  - new artifacts were written:
    `candidate_prediction_window_metrics.parquet`,
    `candidate_reliability_state.parquet`,
    `candidate_selection_audit.parquet`,
    `reliability_block_summary.parquet`,
    `batch_regime_diagnostics.parquet`.

2026-06-23 prequential reliability 40-window smoke result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_125201_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `40` latest prediction windows, pruned candidates,
  `selection_mode=prequential_reliability_v1`;
- artifact counts:
  - candidate validation rows: `160`;
  - candidate prediction window rows: `160`;
  - reliability state rows: `160`;
  - selection audit rows: `160`;
  - batch-regime diagnostic rows: `80`;
  - final decision rows: `14`;
  - conflicts: `0`.
- final routed result:
  - UP: `0` signals, base rate `0.4711`;
  - DOWN: `14` signals, `9 TP / 5 FP`, precision `0.6429`,
    base rate `0.3207`, lift `2.0044`, active-window rate `0.125`.
- shadow candidate result over the same 40 windows:
  - UP `up_rocket_64_v1`: `60` signals, `31 TP / 29 FP`,
    precision `0.5167`, lift `1.0966`;
  - UP `up_none_v1`: `48` signals, `24 TP / 24 FP`,
    precision `0.5000`, lift `1.0612`;
  - DOWN `down_none_v1`: `52` signals, `30 TP / 22 FP`,
    precision `0.5769`, lift `1.7988`;
  - DOWN `down_rocket_16_diag_v1`: `64` signals, `28 TP / 36 FP`,
    precision `0.4375`, lift `1.3641`.
- interpretation:
  - the reliability router is conservative but doing the intended job;
  - it suppressed UP because the lower-bound reliability did not pass;
  - it selected a smaller subset of DOWN signals than the shadow candidates,
    improving precision/lift and reducing false positives;
  - coverage is low, so this is not enough for promotion, but it is a valid
    improvement over validation-only branch selection.
- next required check:
  - run the same prequential reliability setup on an older `120`-window block
    with `--window-end-offset-steps 120`;
  - then run the latest `120`-window block;
  - compare whether DOWN reliability remains stable and whether UP remains
    correctly suppressed.

2026-06-23 prequential reliability older 120-window result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_130132_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `120` prediction windows, batches `5617..5736`,
  `--window-end-offset-steps 120`, pruned candidates,
  `selection_mode=prequential_reliability_v1`;
- final routed result:
  - UP: `8` signals, `0 TP / 8 FP`, precision `0.0000`,
    base rate `0.3622`, active-window rate `0.0333`;
  - DOWN: `24` signals, `13 TP / 11 FP`, precision `0.5417`,
    base rate `0.4173`, lift `1.2982`, active-window rate `0.0667`;
- shadow candidate result over the same 120 windows:
  - UP `up_rocket_64_v1`: `145` signals, `59 TP / 86 FP`,
    precision `0.4069`, lift `1.1233`;
  - UP `up_none_v1`: `115` signals, `35 TP / 80 FP`,
    precision `0.3043`, lift `0.8402`;
  - DOWN `down_rocket_16_diag_v1`: `208` signals, `103 TP / 105 FP`,
    precision `0.4952`, lift `1.1868`;
  - DOWN `down_none_v1`: `91` signals, `37 TP / 54 FP`,
    precision `0.4066`, lift `0.9744`.
- interpretation:
  - the reliability router remained conservative, but not reliable enough for
    this older period;
  - UP should have stayed fully suppressed, but `4` selected UP windows emitted
    `8` false positives;
  - DOWN retained some lift, but it fell below the desired `1.35` threshold and
    active-window rate was too low;
  - using only candidate-level rolling precision-lift is not sufficient;
  - next fix should add side-specific routing gates:
    - UP requires a stronger reliability lower bound or remains disabled;
    - DOWN should require candidate reliability plus a batch-regime/validation
      alignment check before firing.

Deeper failure inspection for the same older 120-window run:

- selected UP windows:
  - selected batches: `5640`, `5648`, `5720`, `5721`;
  - all selected UP rows were false positives;
  - actual prediction-batch UP positive rates were very low:
    `0.0583`, `0.0000`, `0.1333`, `0.0000`;
  - current validation looked good anyway:
    validation precision lift ranged from about `1.33` to `2.34`;
  - reliability lower-bound also barely passed:
    precision-lift LCB ranged from about `1.06` to `1.08`;
  - conclusion: UP reliability threshold was too loose, and validation did not
    detect immediate batch-regime collapse.
- selected DOWN windows:
  - apparent global routed DOWN lift was `1.298`, but this is misleading;
  - within selected DOWN windows, base positive rate was about `0.538` and
    selected-row precision was about `0.542`;
  - selected-window row lift was therefore only about `1.006`;
  - conclusion: most DOWN lift came from selecting higher-base windows, not
    from useful row ranking inside those windows.
- diagnostic correlations with next prediction-batch positive rate:
  - UP: past-20 mean `-0.13`, past-60 mean `-0.31`, current-validation base
    `0.02`, recent candidate lift `0.04`;
  - DOWN: past-20 mean `-0.14`, past-60 mean `-0.18`, current-validation base
    `-0.01`, recent candidate lift `0.12`;
  - conclusion: simple past positive-rate and validation positive-rate
    diagnostics do not predict the next batch base rate well enough.
- exact issue:
  - router reliability is currently measuring historical candidate outcomes
    against all windows;
  - it does not separately measure:
    1. whether candidate selects the right batches;
    2. whether row ranking beats the base rate inside selected batches;
  - this lets a branch look good globally while having little or no row-level
    edge once it fires.
- required next metric split:
  - `window_selection_lift`: positive-rate of selected/active windows versus
    all windows;
  - `selected_window_row_lift`: precision of selected rows versus base rate of
    the same selected/active windows;
  - promotion should require both, especially `selected_window_row_lift > 1`.

2026-06-23 router reliability row-lift gate implementation:

- implementation:
  `regression_feature_engineering/walkforward/rank_signal_router.py`;
- added reliability metrics:
  - `active_window_base_rate`;
  - `window_selection_lift`;
  - `selected_window_precision`;
  - `selected_window_precision_lcb`;
  - `selected_window_row_lift`;
  - `selected_window_row_lift_lcb`;
  - `selected_window_false_discovery_rate`;
- added reliability gates:
  - `--reliability-min-window-selection-lift`, default `1.0`;
  - `--reliability-min-selected-window-row-lift-lcb`, default `1.05`;
  - side-specific overrides for UP/DOWN precision-lift and row-lift lower
    bounds;
- artifact impact:
  - `candidate_reliability_state.parquet`, `selected_candidates.parquet`,
    `candidate_selection_audit.parquet`, `router_window_metrics.parquet`,
    `reliability_block_summary.parquet`, and `batch_regime_diagnostics.parquet`
    now include the row-lift split;
- validation:
  - `python -m pytest tests/test_rpf_rank_signal_router.py -q` passed
    (`13 passed`);
  - `python -m py_compile regression_feature_engineering/walkforward/rank_signal_router.py`
    passed.
- next run should repeat the older 120-window and latest 120-window reliability
  checks with the new row-lift gate before any new model branches are added.

2026-06-23 older 120-window row-lift gated router result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_133606_rank_signal_router_btcusdt_8h_b/`;
- scope:
  `120` prediction windows, batches `5617..5736`,
  `--window-end-offset-steps 120`,
  `selection_mode=prequential_reliability_v1`,
  `candidate_set=pruned_reliability_v1`,
  `--reliability-min-selected-window-row-lift-lcb 1.05`;
- final routed result:
  - UP: `0` signals; the new row-lift/reliability gates fully suppressed the
    previous false UP fires;
  - DOWN: `9` signals, `3 TP / 6 FP`, precision `0.3333`, base rate
    `0.4173`, lift `0.7989`, active-window rate `0.025`;
- change versus previous older 120-window prequential run:
  - decisions fell from `32` to `9`;
  - UP improved from `8` false positives to no signals;
  - DOWN worsened from `13 TP / 11 FP` to `3 TP / 6 FP`;
- selected active DOWN windows:
  - batch `5645`: actual DOWN positive rate `0.0`, produced `3` false
    positives;
  - batch `5711`: actual DOWN positive rate `1.0`, produced `3` true
    positives;
  - batch `5715`: actual DOWN positive rate `0.0`, produced `3` false
    positives;
- interpretation:
  - the row-lift gate is mechanically correct and rejects most weak history;
  - the remaining failures are dominated by full-batch regime/base-rate
    transfer, not within-batch row ranking;
  - prior row-lift reliability can still become stale before the next
    prediction batch;
  - current validation can still look acceptable before an all-negative
    prediction batch, so validation is not a sufficient veto.
- next required fix:
  - add an explicit batch-state/router veto before firing, using only
    prediction-time-safe diagnostics;
  - the veto should answer: "is this prediction batch likely to contain the
    side at all?";
  - row ranking should only run after the side/batch-state gate passes.

2026-06-23 batch-state gate implementation:

- implementation:
  `regression_feature_engineering/walkforward/rank_signal.py` and
  `regression_feature_engineering/walkforward/rank_signal_router.py`;
- added gate mode:
  `--batch-state-gate-mode logistic_prefix_v1`;
- behavior:
  - train a fold-local logistic batch-state model from train batches only;
  - batch-state target is whether the batch positive rate is at least
    `--batch-state-gate-min-positive-rate`;
  - use prefix summaries from the first
    `--batch-state-gate-prefix-rows` rows of each batch;
  - for prediction, use only the current prediction batch prefix as live-safe
    evidence;
  - suppress all row signals before the prefix;
  - suppress the whole side if gate probability is below
    `--batch-state-gate-probability-threshold`;
  - prediction-batch labels are stored only for diagnostics.
- artifacts now include:
  - `batch_state_gate_mode`;
  - `batch_state_gate_probability`;
  - `batch_state_gate_passed`;
  - `batch_state_gate_prefix_rows`;
  - `raw_decision_before_batch_state_gate`;
  - `batch_state_gate_prefix_warmup`.
- research basis:
  - selective classification / reject option supports abstaining when risk is
    high;
  - meta-labeling supports a second model to filter false positives from a
    primary signal;
  - concept-drift literature supports prequential, chronological adaptation.
- validation:
  - `python -m pytest tests/test_rpf_ranked_signal.py tests/test_rpf_rank_signal_router.py -q`
    passed (`25 passed`);
  - `python -m py_compile $(find regression_feature_engineering -name '*.py' -print)`
    passed;
  - 1-window router smoke with `logistic_prefix_v1` completed and wrote batch
    gate fields.
- next validation:
  - rerun the older `120`-window block with `logistic_prefix_v1`;
  - acceptance is not just fewer signals: DOWN must beat local base rate after
    the gate, and UP should remain suppressed unless row/gate reliability both
    pass.

2026-06-23 older 120-window batch-state-gated router result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_161709_rank_signal_router_btcusdt_8h_b/`;
- configuration:
  `candidate_set=pruned_reliability_v1`,
  `selection_mode=prequential_reliability_v1`,
  `--window-end-offset-steps 120`,
  `--outer-window-count 120`,
  `--reliability-min-selected-window-row-lift-lcb 1.05`,
  `--batch-state-gate-mode logistic_prefix_v1`,
  `--batch-state-gate-prefix-rows 60`,
  `--batch-state-gate-min-positive-rate 0.20`,
  `--batch-state-gate-probability-threshold 0.55`;
- final selected-router result:
  - UP: `0` signals;
  - DOWN: `0` signals;
  - `router_decisions.parquet` has `0` rows;
  - selected candidates appeared only twice, both DOWN
    `down_rocket_16_diag_v1`, and both selected prediction windows produced
    no final row signals.
- shadow candidate result after the batch-state gate:
  - `down_none_v1`: `23` signals, `13` TP / `10` FP, precision `0.565`,
    base rate `0.417`, precision lift `1.35`, active in `8/120` windows;
  - `down_rocket_16_diag_v1`: `100` signals, `49` TP / `51` FP,
    precision `0.490`, precision lift `1.17`;
  - `up_none_v1`: `22` signals, `10` TP / `12` FP, precision `0.455`,
    lift about `1.25`;
  - `up_rocket_64_v1`: `58` signals, `23` TP / `35` FP, precision `0.397`,
    lift about `1.10`.
- interpretation:
  - the batch-state gate is mechanically safe and no longer fires the final
    router into bad windows;
  - the current logistic prefix gate is not yet a strong batch-state detector:
    pass/fail windows had very similar average DOWN base rate, so its
    probability should be treated as diagnostic, not promotable;
  - `down_none_v1` is the most useful signal in this run, but the router did
    not select it because reliability gates require too much rolling signal
    history for a sparse specialist branch;
  - the next fix should focus on sparse-specialist routing thresholds and
    candidate reliability accounting, not new feature/model branches.

2026-06-23 older 120-window sparse-specialist reliability result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/`;
- change versus `20260623_161709`:
  - lowered reliability history requirements:
    `--reliability-min-history-windows 10`,
    `--reliability-min-signals 5`,
    `--reliability-min-active-windows 2`;
  - kept precision-lift, selected-window row-lift, false-discovery, and
    batch-state gates active.
- final selected-router result:
  - UP: `2` signals, `0` TP / `2` FP, precision `0.0`;
  - DOWN: `3` signals, `0` TP / `3` FP, precision `0.0`;
  - active windows:
    - UP selected `up_rocket_64_v1` on batch `5635`, but fired `2` false
      positives;
    - DOWN selected `down_none_v1` on batch `5706`, but fired `3` false
      positives.
- shadow candidate evidence remained unchanged and still identifies
  `down_none_v1` as the strongest branch:
  - `down_none_v1`: `23` signals, `13` TP / `10` FP, precision `0.565`,
    lift `1.35`, active in `8/120` windows;
  - `down_rocket_16_diag_v1`: precision `0.490`, lift `1.17`;
  - `up_none_v1`: precision `0.455`, lift about `1.25`;
  - `up_rocket_64_v1`: precision `0.397`, lift about `1.10`.
- interpretation:
  - relaxing sparse-history gates made candidates selectable, but selected
    prediction windows were the wrong windows;
  - the issue is no longer just "too strict reliability"; it is
    candidate-timing transfer;
  - aggregate candidate reliability is not enough for sparse specialists:
    the router also needs a current-window entry condition that is stronger
    than the current logistic prefix gate;
  - before adding new model branches, inspect `down_none_v1` active shadow
    windows versus selected false-positive windows to identify which
    prediction-time-safe diagnostics distinguish them.

2026-06-23 `down_none_v1` entry diagnostic:

- artifact:
  `test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/down_none_v1_entry_diagnostic.parquet`;
- report:
  `test_output/rpf_ranked_signal_router/20260623_165332_rank_signal_router_btcusdt_8h_b/down_none_v1_entry_diagnostic_report.md`;
- inspected `down_none_v1` active shadow windows:
  - batch `5624`: `2` TP / `0` FP, validation signals `0`;
  - batch `5628`: `0` TP / `3` FP, validation signals `9`;
  - batch `5669`: `3` TP / `0` FP, validation signals `0`;
  - batch `5671`: `3` TP / `0` FP, validation signals `0`;
  - batch `5686`: `3` TP / `0` FP, validation signals `0`;
  - batch `5696`: `0` TP / `3` FP, validation signals `3`;
  - batch `5706`: `0` TP / `3` FP, validation signals `6`;
  - batch `5719`: `2` TP / `1` FP, validation signals `12`.
- diagnostic rule, evaluated post-hoc:
  `candidate=down_none_v1`, validation candidate signal count `== 0`,
  batch-state gate passed;
- result on the active candidate windows:
  - selected batches: `5624`, `5669`, `5671`, `5686`;
  - `11` signals, `11` TP / `0` FP, precision `1.0`;
  - a stricter prefix condition also worked but dropped batch `5624`.
- interpretation:
  - for this sparse specialist, quiet validation should not automatically be
    treated as failure;
  - quiet validation appears to mean the candidate threshold is conservative,
    and a later prediction-batch breakout can be high quality;
  - this is one-block diagnostic evidence only, not promotion;
  - next implementation should add an explicit experimental
    `down_none_validation_quiet_v1` entry mode and replay both older and latest
    chronological blocks.

2026-06-23 `down_none_validation_quiet_v1` specialist entry implementation:

- implementation:
  `regression_feature_engineering/walkforward/rank_signal_router.py`;
- new CLI:
  `--specialist-entry-mode off|down_none_validation_quiet_v1`;
- default remains:
  `--specialist-entry-mode off`;
- behavior when enabled:
  - only applies to candidate `down_none_v1`;
  - only applies in `prequential_reliability_v1` mode;
  - allows final selection even when normal validation gates fail;
  - requires validation candidate signal count to be exactly `0`;
  - requires prediction-time-safe `batch_state_gate_passed=true`;
  - does not use current prediction labels;
  - final row decisions still come from the normal causal signal-budget policy.
- added output fields:
  - `specialist_entry_mode`;
  - `specialist_entry_passed`;
  - `specialist_entry_reason`.
- validation:
  - `python -m pytest tests/test_rpf_rank_signal_router.py -q`
    passed (`15 passed`);
  - `python -m py_compile regression_feature_engineering/walkforward/rank_signal_router.py`
    passed.
- next validation:
  - replay the same older `120`-window block with
    `--specialist-entry-mode down_none_validation_quiet_v1`;
  - then replay the latest `120`-window block with the same config;
  - promotion requires the older-block diagnostic behavior to survive outside
    the diagnostic block.

2026-06-23 older 120-window `down_none_validation_quiet_v1` replay result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/`;
- configuration:
  `candidate_set=pruned_reliability_v1`,
  `selection_mode=prequential_reliability_v1`,
  `specialist_entry_mode=down_none_validation_quiet_v1`,
  `--window-end-offset-steps 120`,
  reliability ordinary selection disabled via very high
  `--reliability-min-signals` and `--reliability-min-active-windows`;
- result:
  - UP: `0` signals;
  - DOWN: `11` signals, `11` TP / `0` FP, precision `1.0`;
  - DOWN base rate over the block: `0.4173`;
  - DOWN precision lift: `2.397`;
  - active DOWN window rate: `0.0333`;
  - conflict rows: `0`.
- active DOWN batches:
  - batch `5624`: `2` TP / `0` FP;
  - batch `5669`: `3` TP / `0` FP;
  - batch `5671`: `3` TP / `0` FP;
  - batch `5686`: `3` TP / `0` FP.
- interpretation:
  - the diagnostic rule reproduced exactly as live router output on the same
    older block;
  - this validates the plumbing and confirms that the previous diagnostic was
    not an artifact of post-hoc row sorting;
	- this still does not prove generalization, because the rule was discovered
	  on this block;
	- required next step is an untouched latest-block replay with identical
	  configuration except `--window-end-offset-steps 0`.

2026-06-23 latest 120-window `down_none_validation_quiet_v1` replay result:

- run:
  `test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b/`;
- configuration:
  `candidate_set=pruned_reliability_v1`,
  `selection_mode=prequential_reliability_v1`,
  `specialist_entry_mode=down_none_validation_quiet_v1`,
  `--window-end-offset-steps 0`,
  ordinary reliability selection disabled via very high
  `--reliability-min-signals` and `--reliability-min-active-windows`;
- result:
  - UP: `0` selected-router signals;
  - DOWN: `23` selected-router signals, `3` TP / `20` FP;
  - DOWN precision: `0.1304`;
  - DOWN base rate over the block: `0.3333`;
  - DOWN precision lift: `0.3913`;
  - DOWN active window rate: `0.0667`;
  - conflict rows: `0`.
- active DOWN batches:
  - batch `5777`: `0` TP / `3` FP;
  - batch `5793`: `0` TP / `3` FP;
  - batch `5808`: `0` TP / `3` FP;
  - batch `5813`: `0` TP / `3` FP;
  - batch `5834`: `3` TP / `0` FP;
  - batch `5846`: `0` TP / `3` FP;
  - batch `5847`: `0` TP / `2` FP;
  - batch `5849`: `0` TP / `3` FP.
- shadow candidate metrics on the same latest block:
  - `up_none_v1`: `12` signals, `9` TP / `3` FP, precision `0.75`,
    lift `1.7446`, active windows `4/120`;
  - `up_rocket_64_v1`: `40` signals, `20` TP / `20` FP, precision `0.50`,
    lift `1.1631`, active windows `25/120`;
  - `down_none_v1`: `50` signals, `15` TP / `35` FP, precision `0.30`,
    lift `0.90`, active windows `18/120`;
  - `down_rocket_16_diag_v1`: `69` signals, `26` TP / `43` FP,
    precision `0.3768`, lift `1.1304`, active windows `26/120`.
- interpretation:
  - the `down_none_validation_quiet_v1` specialist entry does not generalize
    from the older block to the latest block;
  - the older `11/11` result was a real sparse cluster, but the entry condition
    is regime-specific and must not be promoted;
  - the latest block still contains shadow signal, especially `up_none_v1` and
    weaker `down_rocket_16_diag_v1`, so the issue is router selection and
    regime transfer rather than total absence of RPF signal;
  - do not run more threshold tuning on this specialist rule unchanged;
  - next useful work is a cross-block regime/selection diagnostic comparing
    older high-quality windows against latest false-positive windows using only
    prediction-time-safe features and prior matured candidate outcomes.

2026-06-23 transfer diagnostic implementation and first run:

- new command:
  `python -m regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic`;
- output root:
  `test_output/rpf_ranked_signal_transfer_diagnostic/`;
- first real run:
  `test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/`;
- inputs:
  - older specialist replay:
    `test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/`;
  - latest specialist replay:
    `test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b/`;
  - candidates:
    `up_none_v1`, `up_rocket_64_v1`, `down_none_v1`,
    `down_rocket_16_diag_v1`.
- artifacts:
  - `candidate_transfer_table.parquet`: post-hoc outcome table for analysis;
  - `safe_context_features.parquet`: prediction-safe context features only;
  - `active_window_comparison.parquet`: active candidate windows only;
  - `transfer_report.md`: candidate aggregate report.
- safety check:
  - `safe_context_features.parquet` has `960` rows and excludes current
    prediction outcome columns such as TP/FP counts, precision, precision lift,
    base rate, current prediction positive rate, and `candidate_good/bad`;
  - `candidate_transfer_table.parquet` has `960` rows and includes post-hoc
    labels for diagnostic use only;
  - `active_window_comparison.parquet` has `157` active candidate windows.
- diagnostic labels:
  - `candidate_active`: candidate emitted at least one signal;
  - `candidate_good`: active, precision lift `>=1.20`, and false-discovery
    rate `<=0.50`;
  - `candidate_bad`: active and false-discovery rate `>0.60`.
- aggregate comparison from the first run:
  - latest `up_none_v1`: `12` signals, `9` TP / `3` FP, precision `0.75`,
    lift `1.7446`, `1` good active window and `1` bad active window;
  - latest `up_rocket_64_v1`: `40` signals, `20` TP / `20` FP,
    precision `0.50`, lift `1.1631`, `8` good active windows and `12` bad;
  - latest `down_none_v1`: `50` signals, `15` TP / `35` FP, precision `0.30`,
    lift `0.90`, `4` good active windows and `13` bad;
  - latest `down_rocket_16_diag_v1`: `69` signals, `26` TP / `43` FP,
    precision `0.3768`, lift `1.1304`, `9` good active windows and `15` bad;
  - older `down_none_v1`: `23` shadow signals, `13` TP / `10` FP,
    precision `0.5652`, lift `1.3546`, `4` good active windows and `3` bad.
- interpretation:
  - the diagnostic now gives a clean dataset for learning branch trust;
  - current prediction labels are separated from model-safe context;
  - `context_meta_router_v1` should not be implemented from intuition alone;
    first inspect which safe-context columns separate `candidate_good` from
    `candidate_bad` across blocks.

2026-06-23 transfer separator implementation and first run:

- new command:
  `python -m regression_feature_engineering.walkforward.rank_signal_transfer_separator`;
- first real run:
  `test_output/rpf_ranked_signal_transfer_separator/20260623_185104_rank_signal_transfer_separator/`;
- input:
  `test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/`;
- artifacts:
  - `feature_separation.parquet`;
  - `candidate_separator_summary.parquet`;
  - `separator_report.md`;
  - `separator_config.json`;
  - `stage_status.json`.
- analyzed rows:
  - active good/bad candidate rows: `133`;
  - safe feature count: `69`;
  - separator result rows: `403`;
  - group summaries: `7`.
- top separator by group:
  - global all-candidate separator:
    `recent_candidate_selected_window_row_lift_lcb`, best AUC `0.6905`;
  - DOWN `down_none_v1`:
    `recent_candidate_selected_window_row_lift`, best AUC `0.9381`,
    lower values were associated with good windows;
  - DOWN `down_rocket_16_diag_v1`:
    `reliability_precision_lift`, best AUC `0.7292`, lower values were
    associated with good windows;
  - UP `up_none_v1`:
    `reliability_active_window_rate`, best AUC `0.95`, lower values were
    associated with good windows;
  - UP `up_rocket_64_v1`:
    `score_mean`, best AUC `0.8033`, lower values were associated with good
    windows.
- interpretation:
  - candidate-specific separators are much stronger than the global separator;
  - this argues against one global router threshold;
  - the future `context_meta_router_v1` should be candidate-specific or at least
    side/candidate conditioned;
  - several strongest separators are counterintuitive: good windows often appear
    when prior reliability activity or selected-window row-lift is lower, which
    means naive "trust more recent active reliability" is not enough;
  - next step should be a dry-run meta-router simulator over existing transfer
    rows, not model retraining.

The corrected `causal_signal_budget` classifier smoke proves capped live-safe
signals work mechanically, but all UP/DOWN classifier trials are still rejected
by window stability. Treat `classify` and `classify_optuna` as historical
diagnostics unless a new plan explicitly reopens them.

2026-06-22 separate CNN-panel controlled run:

- runs:
  - UP:
    `test_output/rpf_clean_classification_optuna/20260622_163007_classification_cls_extreme_up_ge_2x_down_hvol_v2/`;
  - DOWN:
    `test_output/rpf_clean_classification_optuna/20260622_164702_classification_cls_extreme_down_ge_2x_up_hvol_v2/`;
- both runs used the intended combined model shape:
  `ElasticNet-selected tabular features + CNN embeddings from --sequence-panel-path -> CatBoost`;
- both runs used side-specific tabular panels and side-specific CNN diagnostic
  panels;
- both completed `6` trials and all trials were still rejected by
  `window_stability`, so no holdout promotion happened;
- best UP CNN trial:
  - objective `3.17799`;
  - precision `0.9091`;
  - recall `0.00446`;
  - false-positive rate `0.000391`;
  - predicted-positive rate `0.00229`;
  - zero-positive-window rate `0.85`;
  - missed-high-target-window rate `1.0`;
- comparable no-CNN UP capped run:
  - objective `2.77639`;
  - precision `0.75`;
  - recall `0.00669`;
  - false-positive rate `0.00196`;
  - predicted-positive rate `0.00417`;
  - zero-positive-window rate `0.80`;
- interpretation for UP: the separate CNN panel improved precision and
  false-positive control, but reduced coverage and still missed all
  high-target windows. Useful as evidence, not promotable.
- best DOWN CNN trial:
  - objective `-0.22234`;
  - precision `0.3056`;
  - recall `0.00625`;
  - false-positive rate `0.00823`;
  - predicted-positive rate `0.00750`;
  - zero-positive-window rate `0.80`;
  - missed-high-target-window rate `1.0`;
- comparable no-CNN DOWN capped run:
  - objective `1.51980`;
  - precision `0.50`;
  - recall `0.00284`;
  - false-positive rate `0.00165`;
  - predicted-positive rate `0.00208`;
  - zero-positive-window rate `0.90`;
- interpretation for DOWN: the separate CNN panel increased firing but
  worsened false-positive control and precision. This shape should not be
  widened for DOWN without changing objective or input construction.

2026-06-22 CNN input diagnostic:

- diagnostic CLI:
  `regression_feature_engineering/walkforward/cnn_feature_diagnostic.py`;
- diagnostic doc:
  `rpf_cnn_feature_diagnostic.md`;
- runs:
  - UP:
    `test_output/rpf_cnn_feature_diagnostics/20260622_162023_cnn_feature_diagnostic_cls_extreme_up_ge_2x_down_hvol_v2/`;
  - DOWN:
    `test_output/rpf_cnn_feature_diagnostics/20260622_162047_cnn_feature_diagnostic_cls_extreme_down_ge_2x_up_hvol_v2/`;
- both runs used `30` frozen prediction windows and all `2,530` manifest RPF
  columns as candidates;
- main result: the CNN branch should use a separate fast sequence-input panel,
  not the same slow context-heavy ElasticNet-selected tabular panel;
- best candidate families/timeframes are mostly `15m`, `1h`, and `4h`
  `structural_room`, `temporal_memory_transforms`, `spike_breakout`,
  `interaction_confluence`, and `acceptance_persistence`;
- `12h`/`1d`, `regime_calendar_state`, and low-variance slow context remain
  better suited to tabular regime state than to short-sequence memory;
- `classify` and `classify_optuna` now support `--sequence-panel-path`, which
  feeds a frozen diagnostic panel only into the CNN branch while ElasticNet
  keeps its own tabular candidate universe;
- this is post-hoc diagnostic evidence only. It does not promote a classifier
  because it uses held-out labels to identify candidate sequence inputs.

2026-06-22 capped evidence-panel smoke result:

- runs:
  - UP:
    `test_output/rpf_clean_classification_optuna/20260622_154234_classification_cls_extreme_up_ge_2x_down_hvol_v2/`;
  - DOWN:
    `test_output/rpf_clean_classification_optuna/20260622_154922_classification_cls_extreme_down_ge_2x_up_hvol_v2/`;
- both runs used `decision_policy=causal_signal_budget`; positive
  `--max-signals-grid 5,10,20` caps were active;
- `mask_jaccard=1.0` / `selected_feature_jaccard=1.0`, so selector-mask drift
  is not the current failure;
- all trials were rejected by `window_stability`, so holdout replay did not run;
- best UP tuning trial: `20` capped signals over `20` tuning windows,
  `15 TP / 5 FP`, precision `0.75`, recall `0.0067`, active windows `4/20`,
  missed high-target window rate `1.0`;
- best DOWN tuning trial: `10` capped signals over `20` tuning windows,
  `5 TP / 5 FP`, precision `0.50`, recall `0.0028`, active windows `2/20`,
  missed high-target window rate `1.0`;
- interpretation: causal caps removed whole-batch bursts, but the model now
  fires too rarely and misses nearly all high-target windows. This is not a
  promoted signal.

2026-06-22 selector-fix smoke result:

- latest evidence panels:
  - UP:
    `test_output/rpf_feature_panels/20260622_152701_evidence_panel_hybrid_direction_binary_cls_extreme_up_ge_2x_down_hvol_v2/selected_panel_160.json`;
  - DOWN:
    `test_output/rpf_feature_panels/20260622_152701_evidence_panel_hybrid_direction_binary_cls_extreme_down_ge_2x_up_hvol_v2/selected_panel_160.json`;
- latest optuna smokes:
  - UP:
    `test_output/rpf_clean_classification_optuna/20260622_152710_classification_cls_extreme_up_ge_2x_down_hvol_v2/`;
  - DOWN:
    `test_output/rpf_clean_classification_optuna/20260622_153026_classification_cls_extreme_down_ge_2x_up_hvol_v2/`;
- selector refit behavior is fixed: logged `mask_jaccard=1.0` and
  `selected_feature_jaccard=1.0` on the checked windows;
- side-aware panel composition improved: UP panel has far more UP-side than
  DOWN-side feature-name tokens, and DOWN panel has far more DOWN-side than
  UP-side tokens;
- prediction quality is still not promoted:
  - UP produced one high-precision burst in the best-looking trial but only
    `1/8` active tuning windows and was rejected by window stability;
  - DOWN trials remained unstable and false-positive heavy;
- command issue found: the run passed positive `--max-signals-grid` values
  while keeping `decision_policy=threshold_only`, so signal caps were ignored
  and the run did not test the intended capped live-safe policy;
- `classify_optuna` now defaults to `causal_signal_budget`, and the CLI rejects
  `threshold_only` with positive max-signal caps.

2026-06-22 binary walk-forward fix:

- killed the active DOWN evidence-panel Optuna run because completed trials
  were all rejected by window stability;
- failed artifacts retained for audit:
  - UP complete:
    `test_output/rpf_clean_classification_optuna/20260622_141708_classification_cls_extreme_up_ge_2x_down_hvol_v2/`;
  - DOWN partial:
    `test_output/rpf_clean_classification_optuna/20260622_144419_classification_cls_extreme_down_ge_2x_up_hvol_v2/`;
- UP evidence-panel run: `8/8` trials rejected; best-looking trial had one
  very good burst (`239 TP / 1 FP`) but only `2/20` active prediction windows
  and `18/20` zero-signal windows;
- DOWN evidence-panel partial run: `6/6` completed trials rejected; best
  partial trial had only `2/20` active prediction windows and `40 TP / 380 FP`;
- root cause found: threshold calibration used the `validation_train`
  ElasticNet mask, while prediction refit reran ElasticNet on
  `train+validation` and often changed the feature mask;
- `classify` and `classify_optuna` now default to
  `--selector-refit-mode validation_mask`, which freezes the
  validation-selected mask for final CatBoost refit;
- `train_val_reselect` remains available only as an explicit diagnostic mode;
- evidence-panel scoring now includes side-aware signed direction scores and
  side/opposite feature-name token scores, so DOWN panels are no longer ranked
  primarily by UP-looking absolute-correlation evidence.

The corrected walk-forward smoke for `BTCUSDT 8h/B`
`target_reg_distance_up_extreme_hvol_v2` showed:

```text
htf_only validation Spearman:            0.304247
regression_only validation Spearman:     0.059750
htf_plus_regression validation Spearman: 0.095225
```

This means the first corrected smoke favored the old HTF/helper feature set.
The new regression features from this workspace currently have technical
validity evidence, not production prediction-quality evidence.

## Scope

This document covers only features created by:

```text
regression_feature_engineering/
```

It does not cover old HTF/helper features under `htf_with_helpers`, except when
explaining feature-source comparisons.

## Source Of Truth

- Feature registry: `regression_feature_engineering/core/registry.py`
- Materializer: `regression_feature_engineering/materialize_features.py`
- Validator: `regression_feature_engineering/validate_features.py`
- Clean RPF walk-forward optimizer:
  `regression_feature_engineering/walkforward/`
- Clean optimizer contract: `clean_rpf_walkforward_reset.md`
- Binary classification experiment: `rpf_binary_classification_experiment.md`
- Active binary walk-forward process: `rpf_binary_walkforward_process.md`
- Binary prediction pipeline contract:
  `rpf_binary_prediction_pipeline_contract.md`
- Feature evidence panel workflow:
  `rpf_feature_evidence_panel_workflow.md`
- Current binary/regime experiment summary:
  `rpf_current_experiment_summary.md`
- Regime-gated prediction plan: `rpf_regime_gated_prediction_plan.md`
- Regime-gate implementation tracker:
  `rpf_regime_gate_implementation_todo.md`
- Signal-bank batch selection contract:
  `rpf_signal_bank_batch_selection.md`
- Separate target/gate decision-bank contract:
  `rpf_separate_decision_banks.md`
- Abandoned active-path deterministic EMA200 gate baseline:
  `regression_feature_engineering/walkforward/ema_gate.py`
- Abandoned active-path EMA200 regime batch-selection classifier mode:
  `rpf_ema_regime_batch_selection.md`
- Latest BTCUSDT `8h/B` RPF manifest:
  `data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/manifest.json`
- Latest corrected smoke grid:
  `test_output/stage1_regression_grid_search/20260602_081108/grid_summary.parquet`

## What This Does Not Decide

This document does not authorize promotion, feature deletion, or final model
selection. It records current state so we stop mixing engineering correctness
with predictive value.

## What Was Built Here

The active feature set is:

```text
regression_path_features_v1
```

For `BTCUSDT 8h/B`, the current generated root is:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
```

Current artifact evidence:

```text
generated_at: 2026-06-02T22:18:37 UTC
local mtime:  2026-06-03 00:18:37 Europe/Warsaw
rows:         2,810,755
features:     2,530 model-facing rpf_* columns
duplicates:   0
null features:0
```

Feature counts in the current `BTCUSDT 8h/B` root:

| Prefix | Count | Status | Meaning |
|---|---:|---|---|
| `rpf_align_` | 18 | diagnostic only | closed-bar alignment and timing checks |
| `rpf_vol_` | 29 | implemented, not promoted | volatility denominator and range-expansion state |
| `rpf_room_` | 180 | implemented, not promoted | prior high/low/value room and Donchian position |
| `rpf_accept_` | 201 | implemented, not promoted | directional acceptance and persistence |
| `rpf_mem_` | 693 | implemented, not promoted | lags, EWM, slopes, residuals, rank-position transforms |
| `rpf_chop_` | 180 | implemented, not promoted | wick rejection, failed breaks, path efficiency, and two-sided chop |
| `rpf_spike_` | 288 | implemented, not promoted | squeeze release, breakout/breakdown proximity, one-sided impulse, and tail-risk asymmetry |
| `rpf_liq_` | 162 | implemented, not promoted | volume z-score, turnover proxy, volume wake-up, up/down volume pressure, OBV/money-flow proxy, and zero-volume context |
| `rpf_regime_` | 209 | implemented, not promoted | UTC calendar cycle, session metadata, trend/range regime, volatility expansion flags |
| `rpf_conf_` | 270 | implemented, not promoted | compression-breakout, trend-acceptance, volume-impulse, clean-persistence, and room-pressure confluence |
| `rpf_xasset_` | 144 | implemented, not promoted | BTC/ETH relative return, range, correlation, pressure, common-direction, and relative participation context |
| `rpf_factor_` | 144 | engineering validated, not promoted | deterministic factor/anomaly proxies from causal component features |
| `rpf_seq_` | 30 | engineering validated, not promoted | deterministic multi-timeframe sequence-shape proxies from factor proxies |

## What The Feature Sources Mean

The corrected walk-forward runner compares three feature sources:

```text
htf_only
regression_only
htf_plus_regression
```

They are not the same thing.

`htf_only` reads the old merged Stage-1 HTF/helper dataset:

```text
data/htf_multiasset_merged/btcusdt/corexself/target_reg_distance_up_extreme_hvol_v2/8h_b/features/
```

That root was generated at:

```text
2026-06-02T03:28:31 UTC
```

It was built by `build_multiasset_stage1_dataset(...)` from:

```text
data/htf_multiasset/{asset}/htf_with_helpers/1m/target_4class/
data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m/
```

`regression_only` uses the same Stage-1 row and label authority, but replaces
model features with the target asset's `rpf_*` columns from:

```text
data/htf_multiasset/btcusdt/regression_path_features_v1/8h_b/1m/
```

`htf_plus_regression` uses the old merged HTF/helper features plus BTCUSDT
`rpf_*` features joined by exact `timestamp,batch_id`.

In v1, context-asset regression-path features are not joined. Context assets
only contribute through the old HTF/helper merged dataset.

## What Works Technically

The following is technically working:

- materialization of `BTCUSDT 8h/B` `regression_path_features_v1`;
- closed-bar alignment diagnostics;
- full-root row output with no duplicate keys;
- no null feature cells in the generated BTCUSDT `8h/B` root;
- feature catalog generation;
- validator full-root safety checks;
- sliced signal diagnostics for broad feature families;
- Stage-1 exact `timestamp,batch_id` join for target-asset `rpf_*`;
- Stage-1 RPF loading now uses `manifest.json` `feature_columns`, so
  `rpf_align_*` diagnostic metadata cannot enter model features;
- clean RPF default policy now uses all manifest model features with no
  feature-count cap;
- corrected grid output with separate validation and prediction metrics;
- clean RPF-native walk-forward package exists under
  `regression_feature_engineering/walkforward/`;
- the clean runner reads RPF feature batches directly, exact-joins hvol labels
  by `timestamp,batch_id`, freezes sparse windows, and writes stage artifacts
  under `test_output/rpf_clean_walkforward/`.
- the clean runner validates label-window metadata before training and writes
  per-window diagnostics to `window_metrics.parquet`;
- Optuna minimizes validation RMSE directly; rank, direction, tail, and p95
  metrics are diagnostics, not selection objectives;
- fixed family ablation is available through `feature_ablation`, while
  per-feature selection remains deferred.
- binary classification runs now write row-level `validation_scores.parquet`
  and `prediction_scores.parquet` for exact gate joins;
- binary classification code is organized under
  `regression_feature_engineering/walkforward/classification/`; the old
  `regression_feature_engineering/walkforward/classify.py` file is now only the
  stable command/import wrapper;
- binary classification now supports the explicit train-only dynamic selector
  `elasticnet_logistic_v1`; it fits sparse logistic ElasticNet on each fold's
  train rows, records `selected_features.parquet`, leaves validation and
  prediction rows out of selection, and feeds the selected train-standardized
  RPF columns into CatBoost for validation and prediction;
- binary classification now supports the opt-in causal sequence branch
  `--sequence-embedding-mode causal_cnn_v1`; it trains a small CNN inside each
  fold, appends embeddings to the CatBoost input, and remains disabled by
  default so tabular-only runs stay reproducible;
- failed or diagnostic walk-forward branches are quarantined under
  `regression_feature_engineering/walkforward/experimental/`; old module paths
  such as `ema_gate.py`, `regime_gate.py`, `signal_bank.py`,
  `decision_bank.py`, and `panel_select.py` remain compatibility wrappers only;
- the RPF-native regime gate command exists at
  `regression_feature_engineering/walkforward/regime_gate.py` and writes
  `events.jsonl`, `stage_status.json`, `trials.parquet`,
  `window_metrics.parquet`, `gate_scores.parquet`,
  `gated_decision_metrics.parquet`, `report.md`, and `best_config.json`.
- model-facing scale helpers now enforce causal bounded transforms for
  rolling z-scores and volatility-unit distances; existing RPF roots generated
  before this code change must be rematerialized before further walk-forward
  optimization.

Old Stage-1 regression optimizers remain available for historical comparison,
but they are not the active RPF optimization path.

The regime-gate command is currently `validated_plumbing`: the first
`future_up_dominant` smoke wrote all required artifacts under
`test_output/rpf_regime_gate/20260615_164318_regime_gate_future_up_dominant`
and produced exact row-level gate scores with no duplicate row keys. The smoke
trial was rejected for low prediction uniqueness and activated no rows, so no
gate has signal validation or promotion evidence yet.

The first 15-step gate sweep completed after refreshed UP/DOWN classifier runs
created row-level `prediction_scores.parquet`. The useful candidate so far is
`future_down_dominant` with `only_regime_calendar_state`: on the 15-step
overlap it reduced DOWN classifier false positives from `339` to `0`, while
retaining `60` of `261` true positives. This is strict and still experimental.
All current `future_up_dominant` gate scopes collapsed to zero active
classifier positives under the current high-false-positive-cost objective, so
they are not useful in this threshold shape.

The 50-step native confirmation of that DOWN calendar gate completed under:

```text
test_output/rpf_regime_gate/20260616_021308_regime_gate_future_down_dominant
```

It reduced DOWN classifier false positives from `1286` to `0`, but also reduced
true positives from `833` to `60`. The gate activated only `0.5%` of rows and
only one prediction batch (`5855`). Treat this as a high-precision suppressor
candidate, not a promoted regime gate. The next gate pass should add
anti-collapse threshold constraints before any wider confirmation.

A causal signal-bank window mode has been implemented but not validated. It
builds historical clean UP/DOWN batch banks from mature hvol v2 labels and
exposes these modes through the gate runner:

```text
chronological_recent
signal_bank
hybrid_recent_signal_bank
```

For prediction batch `P`, candidate train/validation batches must satisfy:

```text
label_window_batch_id_max <= P - 1 - label_maturity_embargo_batches
```

The next validation target is whether signal-bank or hybrid windows can keep
the DOWN gate's false-positive control while retaining materially more true
positives than the sparse chronological run.

The first pure `signal_bank` validation finished under:

```text
test_output/rpf_regime_gate/20260616_031453_regime_gate_future_down_dominant
```

The selection audit passed temporal safety: `0` train maturity violations and
`0` validation maturity violations across `50` prediction windows. However,
the signal result was worse than the chronological gate. The selected
signal-bank model produced only `31` true positives with `449` false positives
against `future_down_dominant`, and its gated classifier join suppressed all
DOWN classifier positives (`833 -> 0`). Treat pure clean-label signal-bank
sampling as rejected in this first configuration.
The first `hybrid_recent_signal_bank` DOWN run was interrupted after three
completed trials:

```text
test_output/rpf_regime_gate/20260616_043723_regime_gate_future_down_dominant
```

Partial evidence did not justify continuing unchanged:

```text
trial 0 validation decision cost per row: 0.343688
trial 1 validation decision cost per row: 0.344347
trial 2 validation decision cost per row: 0.349300
prediction false-positive rate:          0.01637
```

This was worse than the earlier sparse chronological DOWN calendar gate on the
available objective evidence, while already giving back some false positives.
Treat the hybrid run as interrupted exploratory evidence only.

Separate decision-bank planning has been implemented as a diagnostic path:

```bash
python -m regression_feature_engineering.walkforward.decision_bank
```

This builds two separate mature historical banks:

- target-event bank for the main UP/DOWN classifier;
- gate-trust bank from historical classifier true-positive and false-positive
  behavior.

This is different from the rejected pure signal-bank gate. The gate bank is
trained around the classifier's actual failure mode: when the classifier fires,
is it likely to be a true positive or a false positive?

The first UP and DOWN decision-bank probes finished with:

```text
target_bank_usable_window_rate: 1.0
gate_bank_usable_window_rate:   0.0
```

Interpretation: mature target-event banks exist, but the classifier-trust bank
is too sparse under the current thresholds. Decision-bank work is therefore
diagnostic only until the trust-bank definition is redesigned.

Abandoned EMA evidence:

As of 2026-06-17, EMA gates and EMA-regime batch selection are not part of the
active modeling path. Keep the artifacts below only to explain why this branch
was stopped and to reproduce old diagnostics if needed.

The deterministic EMA200 trend-gate baseline is implemented in:

```bash
python -m regression_feature_engineering.walkforward.ema_gate
```

The first run checked current 1m close versus the latest closed EMA200 for
`15m`, `1h`, `4h`, and `1d`:

```text
test_output/rpf_ema_gate/20260616_053103_ema200_gate
```

Result on the current 50-step UP/DOWN classifier score files:

- UP above 15m EMA reduced false positives but reduced precision and recall;
- UP above 1h/4h EMA changed nothing because existing UP positives already
  fired only in those intraday-above-EMA regimes;
- UP above 1d EMA suppressed all true positives in this window;
- DOWN below 1d EMA retained about `66%` of recall but precision fell;
- DOWN below 15m/1h/4h EMA removed all useful true positives.

Interpretation: EMA200 is a transparent regime diagnostic, but this first
deterministic gate is not promoted. It does not solve the current
false-positive/recall tradeoff and is not part of the active path.

The binary classifier still supports the abandoned EMA-regime mode for
reproducibility:

```bash
python -m regression_feature_engineering.walkforward.classify \
  --window-mode ema_regime_bank
```

This mode selects mature historical train/validation batches where rows are
mostly above EMA200 for the UP target or below EMA200 for the DOWN target. It
was useful as a plumbing exercise, but it is now abandoned for active modeling.
Do not run this path as the next modeling step unless a new plan explicitly
reopens EMA-regime selection. The historical contract and commands remain documented in
`rpf_ema_regime_batch_selection.md` for reproducibility.

The first implementation was corrected after an OOM: EMA inventory construction
now scans only the needed batch range and aggregates labels in small chunks
instead of joining the full label root at once. A one-step low-memory smoke
passed:

```text
test_output/rpf_clean_classification_smoke/20260616_055343_classification_cls_extreme_up_ge_2x_down_hvol_v2
```

Smoke artifacts:

```text
ema_regime_inventory_1h.parquet: 51 batch rows
window_ema_regime.parquet:      1 window row
trials.parquet:                 1 trial row
prediction_scores.parquet:      240 prediction rows
```

This is plumbing evidence only. The 50-step EMA UP/DOWN sweep is abandoned as
an active next step.

## Scale Audit

On 2026-06-04, a recent-window scale audit found that some model-facing RPF
columns were not practically normalized:

```text
sample:   BTCUSDT 8h/B recent 200 batches
artifact: test_output/rpf_feature_scale_audit/btcusdt_8h_b_recent200_feature_scale_audit.parquet
```

Main issue:

- raw rolling volatility z-scores could explode when prior rolling standard
  deviation was tiny;
- temporal-memory EWM/slope/residual features propagated those outliers;
- raw volatility-unit room/proximity/value-distance features could reach
  hundreds of volatility units.

Corrected code contract:

- rolling z-scores are clipped to a fixed finite range;
- positive volatility-unit magnitudes use fixed `[0,1]` compression;
- signed volatility-unit values use fixed `[-1,1]` compression;
- no full-dataset scaler or future-aware quantile normalization is used.

This is an implementation fix only. The generated root on disk keeps its old
values until `materialize_features` is rerun.

## Walk-Forward Readiness Check

On 2026-06-04, a readiness audit found and fixed one issue before larger
walk-forward runs:

- RPF batch files contain `2,548` `rpf_*` columns because `18` `rpf_align_*`
  diagnostic columns are stored beside `2,530` model-facing features.
- The RPF manifest correctly lists only `2,530` model features, but the
  walk-forward loader previously scanned numeric `rpf_*` columns directly.
- That meant a full-feature policy could expose boolean alignment metadata if
  it ignored the manifest contract.
- The loader now reads `manifest.json` `feature_columns`, rejects missing or
  non-numeric manifest features, and excludes diagnostics from all feature
  policies.

Live loader check:

```text
loaded model feature columns: 2,530
manifest feature columns:     2,530
diagnostic columns loaded:    0
```

Coverage check against the active Stage-1 merged root:

```text
valid sparse Stage-1 batches: 3,942
batch id range:               262..5856
missing RPF batches:          0
sample exact-join duplicate:  0
sample exact-join RPF nulls:  0
```

Historical one-step Stage-1 `ml_env` smoke:

```text
run id:  stage1_regression_btcusdt_8h_b_ctx_corexself_reg_distance_up_extreme_hvol_v2_live_feat_regression_only_smoke_rpf_readiness_1step_mlenv
source:  regression_only
policy:  target_specific_v2
steps:   1
rows:    240 prediction rows
features selected: 20
status:  completed and wrote predictions, validation predictions, step metrics,
         feature-policy detail, selected-feature frequency, and summary files
```

This one-step smoke is historical plumbing evidence only. It used
`target_specific_v2`, not the current clean RPF default. Its negative
prediction Spearman must not be used for model selection because it uses one
final prediction batch, very small training windows, and only five CatBoost
iterations.

Clean RPF-native readiness also passed for the first reset target:

```text
command: python -m regression_feature_engineering.walkforward.optimize --stage readiness
target:  target_reg_direction_extreme_up_share_hvol_v2
run:     test_output/rpf_clean_walkforward/20260604_100626_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524

model feature count:   2,530
available batches:     5,856
valid target rows:      1,405,427
target min/max:         0.0 / 1.0
target mean/std:        0.5041 / 0.3656
frozen windows:         5
train/val per window:   120 / 10 available batches
```

This is an RPF data-contract check only. It does not train CatBoost or promote
the target.

A one-trial clean baseline-probe smoke also completed after vectorizing the
rank-correlation feature-selection path:

```text
run:                test_output/rpf_clean_walkforward/20260604_101326_baseline_probe_btcusdt_8h_b_target_reg_direction_extreme_up_sha_f53c5ec0
iterations/depth:   10 / 3
validation Spearman:0.3489
validation RMSE:    0.3350
prediction std:     0.0
prediction unique:  1
status:             rejected:low_prediction_unique
```

This is good plumbing evidence because the trial rejection rule fired correctly.
It is not a useful model-quality result because the intentionally tiny model
collapsed on the prediction batch.

## What Does Not Work Yet

The current `rpf_*` features have not beaten the old HTF/helper features in the
first corrected walk-forward smoke.

Do not claim these features improve prediction until a validation-led
walk-forward run proves it.

The current evidence says:

- volatility and memory features can describe total path width;
- structural-room features are weak for direct up/down separation;
- acceptance/persistence features are technically clean but still modest;
- rejection/chop features are technically clean and show modest purpose-aligned
  signal, but still need walk-forward ablation;
- spike/breakout features are technically clean and show stronger
  purpose-aligned extreme-path signal, but still need walk-forward ablation;
- liquidity/volume-pressure features are technically clean and show modest
  participation and directional-spread signal, but still need walk-forward
  ablation;
- regime/calendar-state features are technically clean and show useful
  calendar/session/path-width context, but still need walk-forward ablation;
- cross-asset-context features are technically clean and show modest BTC/ETH
  relative-context signal, but still need walk-forward ablation;
- adding current `rpf_*` features to HTF features can make selection worse;
- Phase 12/13 static deterministic factor and sequence-shape proxies are
  materialized in the current root; all `rpf_factor_*` timeframe-prefix
  validations and the `rpf_seq_` validation passed, but the families are still
  not predictively promoted.

## Current Decision

Do not promote `regression_path_features_v1` as better than HTF-only.

Keep both binary direction targets for further work:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

Do not decide from global metrics alone. The current evidence says UP and DOWN
prediction quality is regime-dependent. The next model-research step is
stable regime-gated prediction, documented in
`rpf_regime_gated_prediction_plan.md`.

Use the corrected binary grids only after choosing an ablation or gating scope.
Inside each fold, validation is used for early stopping, best iteration, and
threshold selection; aggregate prediction-batch metrics score the trial. If a
candidate fails under regime-conditioned evaluation, revisit feature design
with concrete ablation evidence rather than dropping the target side outright.

## Binary Classification And Regime Diagnostics

RPF-native binary classification is implemented in:

```text
regression_feature_engineering/walkforward/classify.py
```

The active experimental binary targets are:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

They are derived from hvol v2 distance labels:

```text
UP positive:   up_extreme > 0 and up_extreme >= 2 * down_extreme
DOWN positive: down_extreme > 0 and down_extreme >= 2 * up_extreme
```

Current binary evidence:

- 15-step objective sweep was run for both targets, two feature scopes, and
  five validation objectives under
  `test_output/rpf_clean_classification_objective_15step/`;
- recomputed summary:
  `test_output/rpf_clean_classification_objective_15step/objective_15step_summary_recomputed.csv`;
- true 50-step UP/DOWN runs exist under
  `test_output/rpf_clean_classification/20260612_190751_classification_cls_extreme_up_ge_2x_down_hvol_v2/`
  and
  `test_output/rpf_clean_classification/20260612_203257_classification_cls_extreme_down_ge_2x_up_hvol_v2/`;
- OHLCV regime-quality diagnostics:
  `test_output/rpf_clean_classification/regime_target_quality_analysis/true50_regime_quality_report.md`;
- label/performance diagnostics:
  `test_output/rpf_clean_classification/label_quality_correlation_analysis/true50_label_quality_correlation_report.md`.

Interpretation:

- UP target is not discarded. It fires too conservatively and is most useful
  only inside supportive regimes. In actual up batches, its false-positive
  rate can be clean, but recall remains low.
- DOWN target is not globally superior in a production sense. It has stronger
  ranking in some runs, but its precision/recall/FPR also change materially by
  regime.
- Label diagnostics show that both classifiers struggle in ways tied to
  future path composition: up/down imbalance, share targets, and one-sided
  versus mixed path structure.
- Same-batch labels and actual prediction-batch returns are post-hoc
  diagnostics only. They must not become live features.

Next valid milestone:

```text
Can chronological recent walk-forward improve with train-only dynamic
ElasticNet feature selection feeding CatBoost before adding gates or special
batch banks?
```

That milestone must be checked for both UP and DOWN targets with a reserved
holdout slice, for example `--n-steps 50 --holdout-steps 20`. Do not combine it
with EMA-regime windows, learned gates, or signal/decision banks until the
plain chronological holdout comparison is understood.

Statistical normalization rule for this milestone:

- materialized RPF feature roots stay formula-normalized only;
- no global scaler is written into `data/`;
- for each walk-forward fold, the ElasticNet selector computes feature
  mean/std on train rows only;
- the selector may use a train-only ElasticNet prefilter candidate cap to rank
  columns by standardized class separation before the sparse ElasticNet fit;
- ElasticNet selects validation-model features from train-scaled rows only;
- CatBoost trains on selected train-scaled columns and scores validation;
- after validation decisions are made, the validation-selected feature mask is
  frozen by default;
- the final selector scaler is refit on train+validation rows for that frozen
  feature mask;
- the final CatBoost prediction model is refit on the same selected scaled
  train+validation columns and scores the held-out prediction batch;
- the old behavior, rerunning ElasticNet on train+validation, is available only
  with `--selector-refit-mode train_val_reselect` and must be treated as a
  separate experiment because threshold calibration may not transfer;
- prediction rows never fit or update a scaler.
- if `--holdout-steps` is set, the latest holdout windows are replayed only
  after the best tuning config is selected; holdout metrics are confirmation
  evidence and must not feed back into the same search.

Runtime note: the first ElasticNet/CatBoost smoke showed CatBoost fitting in
under one second per window while the full ElasticNet selector consumed most
of the runtime. A train-only prefilter such as
`--elasticnet-prefilter-features-choices 160` reduced a one-window smoke from
about 109 seconds to about 14 seconds without changing the causal contract.

2026-06-16 holdout-run interruption note:

- command shape: chronological recent, UP target,
  `--n-steps 50 --holdout-steps 20`, ElasticNet selector with
  `max_features=80`, `prefilter_features=160`, threshold grid
  `0.55,0.60,0.65,0.70`, false-positive cost `5`;
- completed tuning trials before interruption: `0`, `1`, and `2`;
- all completed trials selected threshold `0.55`;
- validation recall was only about `0.0078`, below the required
  `--min-validation-recall 0.05`;
- prediction positive rate was `0` for trials `0` and `2`, and about `0.033`
  for trial `1`;
- conclusion: this exact constraint/feature/model shape is too conservative
  for UP and should not be allowed to consume the full two-target run without
  adjustment.

The classifier now marks threshold-constraint failures as
`rejected:threshold_constraints` instead of `ok` with an objective penalty, and
writes `*.partial.parquet` files after each trial so interrupted long runs keep
structured evidence.

2026-06-17 DOWN chronological holdout attempt:

```text
run:
test_output/rpf_clean_classification/20260616_223950_classification_cls_extreme_down_ge_2x_up_hvol_v2

target:
target_cls_extreme_down_ge_2x_up_hvol_v2

shape:
chronological recent windows, `--n-steps 50 --holdout-steps 20`,
focused feature group
`group_structural_room+liquidity_volume_pressure+interaction_confluence`,
ElasticNet selector with `max_features=80`, `prefilter_features=160`,
CatBoost depth `2`, learning rate `0.01`, and threshold grid
`0.45,0.50,0.55`.
```

Result:

```text
holdout_summary.json:             not written
tuning windows executed:          30
accepted threshold windows:       17 / 30
status:                           rejected:threshold_constraints
validation precision / recall:    0.716 / 0.147
validation FPR:                   0.0369
prediction precision / recall:    0.336 / 0.087
prediction FPR:                   0.108
prediction decision cost / row:   0.6846
prediction AUC diagnostic:        0.3769
prediction zero-positive windows: 27
prediction all-positive windows:  3
```

Interpretation:

- the earlier 15-step DOWN diagnostic did not survive the wider tuning slice;
- the model alternates between no-signal windows and whole-batch-positive
  windows;
- the run correctly rejected itself before holdout, so there is no final
  confirmation evidence;
- do not rerun this exact configuration unchanged.

Next required classifier cleanup:

- tune the explicit per-window stability objective/gate before holdout;
- penalize zero-positive collapse, all-positive windows, high per-window FPR,
  and low threshold-pass rate;
- keep prediction-batch scoring and reserved holdout, but do not interpret
  aggregate prediction metrics without window-level checks.

2026-06-18 DOWN Optuna holdout replay:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_021113_classification_classification_cls_extreme_down_ge_2x_up_hvo

target:
classification_cls_extreme_down_ge_2x_up_hvol_v2

shape:
chronological recent windows, `--n-steps 50 --holdout-steps 20`,
focused feature group
`group_structural_room+liquidity_volume_pressure+interaction_confluence`,
ElasticNet selector with `max_features=160`, `prefilter_features=320`,
CatBoost depth `4`, learning rate `0.01`, false-positive cost `5`,
and `stable_prediction_quality`.
```

Holdout result:

```text
prediction precision:       0.365
precision lift:             1.80
prediction recall:          0.293
prediction FPR:             0.129
predicted-positive rate:    0.162
signal count:               779
TP / FP / FN / TN:          284 / 495 / 686 / 3335
zero-signal windows:        15 / 20
all-positive windows:       2 / 20
high-FPR windows:           4 / 20
high-cost windows:          5 / 20
```

Interpretation:

- the model can beat the local base rate when it fires, but it is not stable
  enough for promotion;
- the main remaining failure mode is not average precision, it is per-batch
  false-positive bursts;
- active next experiment is validation-selected `(threshold, decision_policy,
  max_signals_per_batch)`;
- `threshold_only` is live-safe and ignores positive signal caps;
- `causal_signal_budget` is live-safe when rows are processed in timestamp
  order;
- `batch_topk_offline` keeps only the top-probability rows in the full current
  batch and is diagnostic only, not a live row-by-row policy.
- keep supervised training/scoring on labeled eligible rows only; future CNN
  sequence context may use all causal rows, but supervised loss and scoring
  must remain anchored to labeled eligible rows.

2026-06-18 DOWN CNN plus signal-cap holdout replay:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_031616_classification_classification_cls_extreme_down_ge_2x_up_hvo

target:
classification_cls_extreme_down_ge_2x_up_hvol_v2

shape:
chronological recent windows, `--n-steps 50 --holdout-steps 20`,
focused feature group
`group_structural_room+liquidity_volume_pressure+interaction_confluence`,
ElasticNet selector with `max_features=160`, `prefilter_features=160`,
causal CNN embeddings with length `16` and embedding dim `8`,
CatBoost depth `2`, learning rate `0.01`, false-positive cost `5`,
and validation-selected `(threshold, max_signals_per_batch)`.
```

Holdout result:

```text
prediction precision:       0.375
precision lift:             1.86
prediction recall:          0.163
prediction FPR:             0.0687
decision cost / row:        0.443
predicted-positive rate:    0.0877
signal count:               421
TP / FP / FN / TN:          158 / 263 / 812 / 3567
zero-signal windows:        13 / 20
all-positive windows:       1 / 20
high-FPR windows:           1 / 20
high-cost windows:          2 / 20
```

Comparison to prior tabular DOWN holdout:

```text
FPR:                 0.129 -> 0.0687
decision cost / row: 0.659 -> 0.443
false positives:     495 -> 263
precision lift:      1.80 -> 1.86
recall:              0.293 -> 0.163
signals:             779 -> 421
```

Interpretation:

- CNN plus per-batch signal caps materially improved false-positive control
  and decision cost on untouched holdout;
- recall dropped sharply, so this is a cleaner DOWN suppressor, not yet a
  complete production signal;
- remaining failure modes are sparse firing and a small number of bad windows,
  especially batches with all-positive or high-FPR behavior;
- the matching UP run below completed the two-target CNN-cap comparison.

2026-06-18 UP CNN plus signal-cap holdout replay:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_173826_classification_classification_cls_extreme_up_ge_2x_down_hvo

target:
classification_cls_extreme_up_ge_2x_down_hvol_v2

shape:
chronological recent windows, `--n-steps 50 --holdout-steps 20`,
focused feature group
`group_structural_room+liquidity_volume_pressure+interaction_confluence`,
ElasticNet selector with `max_features=80`, `prefilter_features=320`,
causal CNN embeddings with length `16` and embedding dim `8`,
CatBoost depth `3`, learning rate `0.02`, false-positive cost `5`,
and validation-selected `(threshold, max_signals_per_batch)`.
```

Best tuning trial:

```text
trial:                      2
tuning objective:           -0.9547
tuning precision:           0.550
tuning precision lift:      1.31
tuning recall:              0.233
tuning FPR:                 0.137
tuning decision cost / row: 0.721
tuning TP / FP / FN / TN:   702 / 575 / 2316 / 3607
```

Reserved holdout result:

```text
prediction precision:       0.514
precision lift:             0.932
prediction recall:          0.126
prediction FPR:             0.146
decision cost / row:        0.810
predicted-positive rate:    0.135
signal count:               648
TP / FP / FN / TN:          333 / 315 / 2315 / 1837
zero-signal windows:        11 / 20
all-positive windows:       1 / 20
high-FPR windows:           2 / 20
high-cost windows:          4 / 20
```

UP holdout failure mode:

- holdout base positive rate was high at `0.552`; precision `0.514` is below
  that base rate, so the model did not add useful discrimination on this
  holdout;
- several almost-all-UP batches received no signals, while batch `5856` fired
  across the whole batch and produced `163` false positives;
- using the revised target-aware stability audit, `7 / 8` high-target UP
  windows were missed (`missed_high_target_window_rate=0.875`) and one
  low-target window fired across the whole batch
  (`low_target_all_positive_window_rate=0.143`);
- validation still looked clean (`0.950` precision, `0.0042` FPR), which means
  validation-selected thresholds and caps did not transfer well for UP;
- this exact UP CNN-cap configuration should not be promoted or rerun
  unchanged.

Two-target CNN-cap comparison on the same 50-step/20-holdout structure:

| Target | Precision | Lift | Recall | FPR | Cost / row | Signals | TP/FP/FN/TN | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|---|
| UP | `0.514` | `0.93` | `0.126` | `0.146` | `0.810` | `648` | `333/315/2315/1837` | rejected; below base-rate precision |
| DOWN | `0.375` | `1.86` | `0.163` | `0.0687` | `0.443` | `421` | `158/263/812/3567` | useful false-positive reduction, still sparse |

Current interpretation:

- CNN plus signal caps helped DOWN false-positive control but did not solve UP;
- the UP target is not dead, but this feature scope/objective does not handle
  high-UP-base-rate holdout windows;
- the objective/window-stability logic has now been revised to track missed
  high-target windows and low-target all-positive firing before the next run.

2026-06-18 UP target-aware stability rerun:

```text
run:
test_output/rpf_clean_classification_optuna/20260618_202138_classification_classification_cls_extreme_up_ge_2x_down_hvo

target:
classification_cls_extreme_up_ge_2x_down_hvol_v2

shape:
chronological recent windows, `--n-steps 30 --holdout-steps 10`,
focused feature group
`group_structural_room+liquidity_volume_pressure+interaction_confluence`,
ElasticNet selector, causal CNN embeddings, CatBoost,
target-aware stability gates enabled.
```

Best tuning trial:

```text
trial:                                  4
status:                                 rejected:window_stability
rejection reason:                       too_many_missed_high_target_windows
prediction precision:                   0.670
precision lift:                         1.43
prediction recall:                      0.172
prediction FPR:                         0.0743
decision cost / row:                    0.585
predicted-positive rate:                0.120
TP / FP / FN / TN:                      385 / 190 / 1858 / 2367
zero-signal windows:                    12 / 20
all-positive windows:                   1 / 20
missed high-target windows:             5 / 8
missed high-target window rate:         0.625
low-target all-positive window rate:    0.000
```

Interpretation:

- the target-aware objective improved aggregate UP precision, lift, FPR, and
  cost on the tuning windows compared with the earlier UP tuning slice;
- it correctly rejected itself before holdout because high-target UP windows
  were still missed too often;
- after this run, threshold/cap selection under `stable_prediction_quality`
  was changed to use the stable quality score instead of pure validation
  decision cost, and the score now includes a modest explicit recall term. The
  next rerun should check whether that reduces overly sparse validation
  decisions.

The classifier now writes stability-gate fields to `trials.parquet`:

```text
prediction_zero_positive_window_rate
prediction_all_positive_window_rate
prediction_high_fpr_window_rate
prediction_high_cost_window_rate
prediction_positive_rate_mean
prediction_high_target_window_rate
prediction_missed_high_target_window_rate
prediction_high_target_recall_mean
prediction_low_target_all_positive_window_rate
prediction_false_positive_rate_max
prediction_decision_cost_per_row_max
prediction_window_stability_pass
prediction_window_stability_reason
```

New CLI controls:

```text
--min-threshold-pass-rate
--max-prediction-zero-positive-window-rate
--max-prediction-all-positive-window-rate
--prediction-all-positive-rate-threshold
--max-prediction-high-fpr-window-rate
--max-prediction-window-false-positive-rate
--max-prediction-high-cost-window-rate
--max-prediction-window-decision-cost-per-row
--prediction-high-target-positive-rate-threshold
--min-prediction-high-target-window-recall
--min-prediction-high-target-window-signal-rate
--max-prediction-missed-high-target-window-rate
--prediction-low-target-positive-rate-threshold
--max-prediction-low-target-all-positive-window-rate
```

The active next modeling step should stay chronological and should not reopen
EMA gates or batch banks. The immediate need is to rerun the small UP-focused
Optuna check after the threshold-selection fix and compare whether
missed-high-target rates improve before widening.

## Rejection/Chop Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `rejection_chop` and validated by
narrow timeframe prefixes to avoid wide-diagnostic memory pressure.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_chop_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_chop_15m_` | 0.0843 | short-term path chop / failed breaks vs total extreme path width |
| `rpf_chop_1h_` | 0.0465 | weak path chop / failed-break signal |
| `rpf_chop_4h_` | 0.0509 | weak rejection/chop signal |
| `rpf_chop_8h_` | 0.0556 | weak reversal/rejection signal |
| `rpf_chop_12h_` | 0.1187 | upper rejection negatively associated with mean/total path width |
| `rpf_chop_1d_` | 0.1296 | upper rejection negatively associated with mean/total path width |

Interpretation:

- Long-timeframe upper rejection behaves like a persistence suppressor: higher
  rejection is associated with lower future mean/total path distance.
- Short-timeframe path chop behaves like a two-sided instability proxy: higher
  chop is associated with wider total extreme path movement.
- Directional up-vs-down separation remains modest. This family is useful
  context, not a standalone directional solution.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_rejection_chop_rpf_chop_1d/
```

## Spike/Breakout Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `spike_breakout` and validated by
narrow timeframe prefixes.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_spike_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_spike_15m_` | 0.1998 | downside breakout proximity vs total extreme path width |
| `rpf_spike_1h_` | 0.2364 | downside breakout proximity vs total extreme path width |
| `rpf_spike_4h_` | 0.2299 | downside breakout proximity vs total extreme path width |
| `rpf_spike_8h_` | 0.2381 | downside breakout proximity vs total extreme path width |
| `rpf_spike_12h_` | 0.2338 | downside breakout proximity vs total extreme path width |
| `rpf_spike_1d_` | 0.2304 | downside breakout proximity vs total extreme path width |

Interpretation:

- `rpf_spike_*` gives stronger sampled signal than `rpf_chop_*` for extreme
  path-width ranking.
- The strongest feature class is prior-channel breakout/breakdown proximity,
  especially downside proximity. This is purpose-aligned for extreme-distance
  targets but also indicates the family is currently more width/risk-state
  oriented than cleanly directional.
- Bin-spread checks show high breakout-proximity bins separating
  `target_extreme_total` by roughly `0.3` to `0.6` horizon-volatility units in
  the sampled validation.
- Directional up-vs-down separation remains modest; this family should be
  tested by walk-forward ablation, not promoted from correlation alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_spike_breakout_rpf_spike_1d/
```

## Liquidity/Volume Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `liquidity_volume_pressure` and
validated by narrow timeframe prefixes.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_liq_*` timeframe slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_liq_15m_` | 0.1132 | volume wake-up / relative activity negatively associated with total extreme path width |
| `rpf_liq_1h_` | 0.1311 | volume wake-up negatively associated with total extreme path width |
| `rpf_liq_4h_` | 0.1595 | volume wake-up negatively associated with total extreme path width |
| `rpf_liq_8h_` | 0.0925 | volume z-score negatively associated with total extreme path width |
| `rpf_liq_12h_` | 0.1190 | dollar-volume relative activity associated with total extreme path width |
| `rpf_liq_1d_` | 0.0558 | money-flow balance associated with mean total path width |

Directional high-low quintile spreads:

| Prefix | Feature | Target | High-Low Spread |
|---|---|---|---:|
| `rpf_liq_15m_` | `volume_pressure_balance_l48` | `target_extreme_up_minus_down` | 0.2382 |
| `rpf_liq_1h_` | `volume_pressure_balance_l48` | `target_extreme_up_minus_down` | 0.2148 |
| `rpf_liq_4h_` | `volume_pressure_balance_l4` | `target_extreme_up_minus_down` | 0.1616 |
| `rpf_liq_8h_` | `volume_pressure_balance_l4` | `target_extreme_up_minus_down` | 0.1754 |
| `rpf_liq_12h_` | `money_flow_balance_l4` | `target_extreme_up_minus_down` | 0.1015 |
| `rpf_liq_1d_` | `money_flow_balance_l4` | `target_extreme_up_minus_down` | 0.0793 |

Interpretation:

- The liquidity family is technically clean and useful as participation
  context.
- Relative volume/wake-up features mostly act like path-width or volatility
  state context in the sampled reports.
- Up/down volume-pressure balance creates directional quintile separation, but
  rank correlations are still modest. This family should be kept for
  controlled ablation, not promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_liquidity_rpf_liq_1d/
```

## Regime/Calendar Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `regime_calendar_state` and validated
by narrow calendar/timeframe prefixes. A single corrupted parquet batch
(`batch_2511.parquet`) was repaired by rebuilding that batch from the same
causal materializer path before rerunning the failed `12h` and `1d` reports.
All feature batches are now readable.

Safety result across every prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest absolute Spearman by `rpf_regime_*` slice:

| Prefix | Strongest Abs Spearman | Main Relationship |
|---|---:|---|
| `rpf_regime_utc_` | 0.2916 | UTC hour cycle negatively associated with total extreme path width |
| `rpf_regime_15m_` | 0.1603 | 15m volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_1h_` | 0.1803 | 1h volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_4h_` | 0.1770 | 4h volatility-relative regime negatively associated with total extreme path width |
| `rpf_regime_8h_` | 0.1473 | 8h session progress negatively associated with total extreme path width |
| `rpf_regime_12h_` | 0.1474 | 12h session progress negatively associated with total extreme path width |
| `rpf_regime_1d_` | 0.1473 | 1d session progress negatively associated with total extreme path width |

Interpretation:

- The regime/calendar family is technically clean and provides useful timing,
  session, and path-width context.
- The strongest signal is calendar/session-style context rather than clean
  up/down direction.
- This family should be kept for controlled ablation and interaction work, not
  promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_utc/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_regime_rpf_regime_1d/
```

## Interaction/Confluence Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `interaction_confluence` and
validated by narrow `rpf_conf_*` timeframe prefixes.

Phase 10 generated-root result:

```text
rows:                    2,810,755
model-facing features:   2,212
interaction features:    270
duplicate keys:          0
null feature cells:      0
readable batch files:    5,856 / 5,856
```

Safety result across every `rpf_conf_*` prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest sampled signal by `rpf_conf_*` slice:

| Prefix | Strongest Abs Spearman | Feature | Target | Best Quintile Spread | Spread Target |
|---|---:|---|---|---:|---|
| `rpf_conf_15m_` | 0.1200 | `up_squeeze_break_l16` | `target_extreme_total` | 0.2135 | `target_extreme_total` |
| `rpf_conf_1h_` | 0.0996 | `up_squeeze_break_l4` | `target_extreme_total` | 0.2162 | `target_extreme_up_minus_down` |
| `rpf_conf_4h_` | 0.1530 | `down_squeeze_break_l4` | `target_extreme_total` | 0.1850 | `target_extreme_up_minus_down` |
| `rpf_conf_8h_` | 0.0933 | `down_squeeze_break_l48` | `target_extreme_total` | 0.1879 | `target_extreme_up_minus_down` |
| `rpf_conf_12h_` | 0.0838 | `down_squeeze_break_l16` | `target_extreme_total` | 0.1551 | `target_extreme_up_minus_down` |
| `rpf_conf_1d_` | 0.1002 | `down_squeeze_break_l16` | `target_extreme_total` | 0.1593 | `target_extreme_up_minus_down` |

Interpretation:

- The confluence family is technically clean.
- The strongest rank signal remains path-width oriented, mostly
  squeeze-break relationships with `target_extreme_total`.
- Directional information is more visible in high-low quintile spreads,
  especially volume-impulse, clean-persistence, and squeeze-break balance
  features against `target_extreme_up_minus_down`.
- This family should be kept for controlled ablation and target-specific
  selection, not promoted alone.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_confluence_rpf_conf_1d/
```

## Cross-Asset Validation Result

The `BTCUSDT 8h/B` root was rebuilt with `cross_asset_context` and validated by
narrow `rpf_xasset_ethusdt_*` timeframe prefixes. For BTCUSDT, auto context
uses ETHUSDT.

Current generated-root result:

```text
rows:                    2,810,755
model-facing features:   2,356
cross-asset features:    144
duplicate keys:          0
null feature cells:      0
readable batch files:    5,856 / 5,856
```

Safety result across every `rpf_xasset_ethusdt_*` prefix:

```text
joined rows:             2,810,755
valid rows:              1,405,427
duplicate keys:          0
null feature cells:      0
infinite feature cells:  0
future-close violations: 0
```

Strongest sampled signal by `rpf_xasset_ethusdt_*` slice:

| Prefix | Strongest Abs Spearman | Feature | Target | Best Quintile Spread | Spread Target |
|---|---:|---|---|---:|---|
| `rpf_xasset_ethusdt_15m_` | 0.0481 | `corr_l16` | `target_extreme_total` | 0.1294 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_1h_` | 0.0384 | `context_pressure_l4` | `target_reg_distance_down_mean_low_hvol_v2` | 0.1412 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_4h_` | 0.0395 | `context_range_share_l4` | `target_extreme_total` | 0.1158 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_8h_` | 0.0424 | `corr_l48` | `target_mean_total` | 0.1150 | `target_extreme_up_minus_down` |
| `rpf_xasset_ethusdt_12h_` | 0.0495 | `volume_rel_spread_l4` | `target_extreme_total` | 0.1486 | `target_extreme_total` |
| `rpf_xasset_ethusdt_1d_` | 0.0581 | `corr_l48` | `target_mean_total` | 0.1358 | `target_extreme_total` |

Interpretation:

- The cross-asset family is technically clean and has no raw foreign
  price/volume model-facing columns.
- The sampled rank signal is modest; the strongest absolute Spearman is
  `0.0581`, mostly against total path-width or mean-total targets.
- Directional information appears more in quintile spreads than rank
  correlations, especially relative strength, relative volume, and context
  pressure against `target_extreme_up_minus_down`.
- Keep this family for controlled ablation and target-specific selection, not
  as a standalone promoted feature family.

Validation reports:

```text
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_15m/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_4h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_8h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_12h/
test_output/regression_feature_engineering_btcusdt_8h_b_xasset_rpf_xasset_ethusdt_1d/
```

## Clean Walk-Forward Optimizer State

The clean RPF walk-forward optimizer is organized as staged Optuna searches
instead of one broad all-parameter search.

Implemented optimizer stages:

```text
readiness -> baseline_probe -> geometry -> core_model -> sampling -> confirmation
```

Current status:

- `readiness` writes `readiness.json`, `batch_index.parquet`, and
  `frozen_windows.parquet`;
- all clean stages use RPF-only `feature_source=regression_only`;
- feature policy baseline is `all_manifest_features`, so every model-facing
  RPF manifest feature is used;
- `elasticnet_logistic_v1` is now available for binary classification as a
  dynamic train-only per-fold selector feeding CatBoost prediction;
- Optuna currently tunes only walk-forward geometry and CatBoost
  hyperparameters, selected by validation RMSE;
- feature-selection thresholds, selected-feature counts, dedupe thresholds,
  clipping quantiles, stability segments, and tail quantiles are deliberately
  not used or optimized yet;
- family ablation masks such as `only_volatility_state`,
  `minus_volatility_state`, and `group_volatility_state+structural_room` are
  fixed run inputs for later feature optimization;
- later stages can load a previous `best_config.json` or stage-specific lock
  file through `--base-run`;
- the walk-forward runner replays exact sparse windows from
  `frozen_windows.parquet`;
- CatBoost now records and validates staged parameters, including
  `has_time=true`, early stopping controls, and bootstrap/sampling options.
- long-running jobs now have live console progress and JSONL event logs:
  `events.jsonl` inside each clean stage run directory.

No staged Optuna result is promoted yet. The next valid evidence should come
from baseline-probe, geometry, and core-model smoke runs on `BTCUSDT 8h/B`
before any full confirmation run.

## Binary Specialist Signal Objective

As of 2026-06-22, the active RPF binary walk-forward path supports the
specialist signal-bank objective:

```text
stable_signal_quality
```

This is different from generic classification optimization. It is intended for
ElasticNet + optional causal CNN + CatBoost configurations that fire sparsely
but with high precision and repeated active batches.

The leak-safe fold flow remains:

```text
train
-> train-only ElasticNet selector/scaler
-> optional causal CNN embeddings fit only from train/train+validation rows
-> CatBoost classifier
-> validation threshold selection
-> freeze validation-selected feature mask
-> refit scaler and CatBoost on train+validation for that mask
-> prediction batch scoring
```

The new objective emphasizes:

- precision lift over the local base rate;
- low false-positive and false-discovery rates;
- active-window precision;
- repeated active signal windows;
- low signal churn;
- avoidance of all-positive/high-FPR/high-cost windows.

Recall is now treated as secondary for this objective. A model may be useful
with low recall if it repeatedly captures clean high-confidence signal clusters
without look-ahead.

No specialist model bank is promoted yet. Existing high-precision clusters
remain diagnostic until frozen configurations are replayed on longer untouched
holdout windows.

## Ranked-Signal Transfer Meta-Router Simulator

As of 2026-06-23, the next transfer-fix step is implemented as an offline
artifact-only simulator:

```bash
python -m regression_feature_engineering.walkforward.rank_signal_meta_router_simulator
```

It consumes the completed transfer diagnostic artifacts and trains simple
candidate-specific accept/reject rules from one matured source block, then
replays those rules on another block. It does not modify live router behavior.

First run:

```text
run: test_output/rpf_ranked_signal_meta_router_simulator/20260623_205856_rank_signal_meta_router_simulator/
input: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic/
train source block: older
test source block: latest
safe feature count: 69
trained candidate rules: 4
```

Older-trained rules:

| Side | Candidate | Rule Feature | Direction | Older Train Precision | Older Train Lift |
|---|---|---|---|---:|---:|
| DOWN | `down_none_v1` | `reliability_reliability_score` | lower good | 1.000 | 3.241 |
| DOWN | `down_rocket_16_diag_v1` | `reliability_selected_window_row_lift` | lower good | 1.000 | 4.898 |
| UP | `up_none_v1` | `threshold` | higher good | 1.000 | 2.753 |
| UP | `up_rocket_64_v1` | `score_mean` | lower good | 1.000 | 1.995 |

Replay result:

| Source | Side | Signals | TP | FP | Precision | Lift | FDR | Active Rate |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| older | DOWN | 8 | 8 | 0 | 1.000 | 2.397 | 0.000 | 0.025 |
| older | UP | 9 | 9 | 0 | 1.000 | 2.761 | 0.000 | 0.033 |
| latest | DOWN | 38 | 9 | 29 | 0.237 | 0.711 | 0.763 | 0.117 |
| latest | UP | 3 | 3 | 0 | 1.000 | 2.326 | 0.000 | 0.017 |

Interpretation:

- UP context filters transfer but are very sparse.
- `down_rocket_16_diag_v1` is sparse but transferred cleanly in the candidate
  acceptance table: 2 latest signals, 2 TP, 0 FP.
- `down_none_v1` still fails latest transfer and dominates the side-router
  summary with 29 false positives.
- Do not implement `context_meta_router_v1` directly from this first
  simulator. The next step should test a conservative candidate allow-list
  or add a candidate-specific reject rule for `down_none_v1`.

Conservative allow-list replay:

```text
run: test_output/rpf_ranked_signal_meta_router_simulator/20260623_210014_rank_signal_meta_router_simulator/
allowed candidates: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
excluded candidate: down_none_v1
```

Result:

| Source | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---:|---:|---:|---:|---:|---:|
| older | DOWN | 3 | 3 | 0 | 1.000 | 2.397 | 0.000 |
| older | UP | 9 | 9 | 0 | 1.000 | 2.761 | 0.000 |
| latest | DOWN | 2 | 2 | 0 | 1.000 | 3.000 | 0.000 |
| latest | UP | 3 | 3 | 0 | 1.000 | 2.326 | 0.000 |

Interpretation:

- The conservative allow-list is extremely sparse, but it removes the latest
  false-positive failure caused by `down_none_v1`.
- This is still a diagnostic replay over existing artifacts, not a promoted
  live router.
- The next real run should either replay this conservative candidate set on a
  different chronological block or implement a live router option that can
  exclude `down_none_v1` while preserving the same validation/prediction safety
  contract.

Implementation note:

- `rank_signal_router` now supports `--candidate-name-allowlist`.
- The default candidate-set behavior is unchanged when the flag is omitted.
- The conservative live-router candidate set is:

```text
up_none_v1,up_rocket_64_v1,down_rocket_16_diag_v1
```

This lets the live router reproduce the diagnostic allow-list without editing
candidate definitions or reintroducing `down_none_v1` latest-block failures.

Live allow-list router run:

```text
run: test_output/rpf_ranked_signal_router/20260623_210606_rank_signal_router_btcusdt_8h_b/
candidate allow-list: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
selection mode: prequential_reliability_v1
outer windows: 120
```

Result:

```text
final UP decisions:   0
final DOWN decisions: 0
```

Reason:

- `prequential_reliability_v1` remained too strict for this sparse allow-list;
- `239/240` side-window selections failed reliability;
- `152/240` side-window selections failed validation before reliability could
  select anything;
- candidate shadow outputs still fired, but validation-only shadow selection
  was not clean enough:
  - DOWN shadow validation-only: 58 signals, 27 TP, 31 FP, precision 0.466;
  - UP shadow validation-only: 84 signals, 39 TP, 45 FP, precision 0.464.

Follow-up artifact diagnostic:

```text
transfer diagnostic:
test_output/rpf_ranked_signal_transfer_diagnostic/20260623_212043_rank_signal_transfer_diagnostic/

meta-rule simulator:
test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
```

The same older-trained context rules applied to the live allow-list artifacts
produced:

| Source | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---:|---:|---:|---:|---:|---:|
| latest | DOWN | 9 | 6 | 3 | 0.667 | 2.000 | 0.333 |
| latest | UP | 17 | 14 | 3 | 0.824 | 1.916 | 0.176 |
| older | DOWN | 3 | 3 | 0 | 1.000 | 2.397 | 0.000 |
| older | UP | 9 | 9 | 0 | 1.000 | 2.761 | 0.000 |

Conclusion:

- Candidate allow-list alone is not enough.
- Validation-only selection is not enough.
- Default prequential reliability selection is too strict and emits no signals.
- The next implementation should add a live `context_rule_v1`/meta-router
  selection mode that applies candidate-specific prediction-safe context rules
  before final routing.

Live `context_rule_v1` status:

- implemented in `rank_signal_router`;
- requires `--context-rule-path`, pointing either to `meta_router_rules.parquet`
  or to a meta-router simulator run directory;
- default router behavior is unchanged unless
  `--selection-mode context_rule_v1` is explicitly used;
- selected candidates, router windows, row scores, and selection audit rows now
  include `context_rule_*` diagnostics.

Smoke run:

```text
run: test_output/rpf_ranked_signal_router/20260623_212951_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
outer windows: 5
context rules: test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
```

Smoke result:

```text
UP:   2 signals, 2 TP, 0 FP, precision 1.000, lift 2.603
DOWN: 0 signals
```

Interpretation: plumbing is valid and the router now applies candidate-specific
context rules live. The next run should replay the same mode over the latest
120-window block.

Latest 120-window live context-rule run:

```text
run: test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
candidate allow-list: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
context rules: test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
outer windows: 120
```

Result:

| Side | Signals | TP | FP | Precision | Lift | Active Window Rate | FDR |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP | 17 | 14 | 3 | 0.824 | 1.916 | 0.083 | 0.176 |
| DOWN | 9 | 6 | 3 | 0.667 | 2.000 | 0.025 | 0.333 |

Candidate detail:

- UP selected `up_rocket_64_v1` on 20 windows and fired 17 signals:
  14 TP / 3 FP.
- UP selected `up_none_v1` on 3 windows but fired 0 signals.
- DOWN selected `down_rocket_16_diag_v1` on 4 windows and fired 9 signals:
  6 TP / 3 FP.
- No UP/DOWN conflicts were produced.

Interpretation:

- This is the first live-router transfer run that gives useful precision on
  both sides after the previous zero-signal reliability run.
- The result is still sparse; recall remains intentionally tiny.
- The active question is now stability across older/shifted chronological
  blocks, not whether the latest 120-window transfer fix can fire.

Offset-240 120-window context-rule stability replay:

```text
run: test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b/
selection mode: context_rule_v1
candidate allow-list: up_none_v1, up_rocket_64_v1, down_rocket_16_diag_v1
context rules: test_output/rpf_ranked_signal_meta_router_simulator/20260623_212049_rank_signal_meta_router_simulator/
prediction batches: 5497..5616
outer windows: 120
window_end_offset_steps: 240
```

Result:

| Side | Signals | TP | FP | Precision | Lift | Active Window Rate | FDR |
|---|---:|---:|---:|---:|---:|---:|---:|
| UP | 24 | 9 | 15 | 0.375 | 1.199 | 0.092 | 0.625 |
| DOWN | 0 | 0 | 0 | - | - | 0.000 | - |

Interpretation:

- The latest-block context rules did not generalize to the offset-240 block.
- UP remained active but false discovery rose to `0.625`, so the signal is not
  stable enough to promote.
- DOWN emitted no signals even though the block DOWN base rate was high
  (`0.456`), so the current DOWN rule misses some older DOWN regimes.
- Do not tune these frozen rules on the latest block. The next valid step is a
  multi-block rule-bank/backtest workflow that trains context rules only on
  prior matured blocks and tests them on the next chronological block.

Implemented multi-block context rule-bank diagnostic:

```text
command: python -m regression_feature_engineering.walkforward.rank_signal_rule_bank
purpose: train context rules on prior matured router blocks, replay on the next
         chronological block, and reject rules that do not transfer forward.
```

First three-block inputs:

```text
offset240: test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b/
middle:    test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/
latest:    test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b/
```

All-prior rule bank:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_221017_rank_signal_rule_bank/
fold 0, train offset240 -> test middle:
  UP:   10 signals, 8 TP / 2 FP, precision 0.800, lift 2.209
  DOWN: 6 signals, 3 TP / 3 FP, precision 0.500, lift 1.198
fold 1, train offset240+middle -> test latest:
  UP:   113 signals, 56 TP / 57 FP, precision 0.496, lift 1.153
  DOWN: 0 signals
```

Rolling-one-block rule bank:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_221037_rank_signal_rule_bank/
fold 0, train offset240 -> test middle:
  UP:   10 signals, 8 TP / 2 FP, precision 0.800, lift 2.209
  DOWN: 6 signals, 3 TP / 3 FP, precision 0.500, lift 1.198
fold 1, train middle -> test latest:
  UP:   17 signals, 14 TP / 3 FP, precision 0.824, lift 1.916
  DOWN: 9 signals, 6 TP / 3 FP, precision 0.667, lift 2.000
```

Interpretation:

- all-prior rule training over-broadened UP and silenced DOWN on the latest
  block;
- rolling-one-block rule training adapted better and reproduced the useful
  latest-block context rules;
- this is promising but still only two forward transitions, so it is not enough
  to promote;
- next evidence must add at least one older block, then rerun the rolling
  rule-bank over four chronological blocks.

Four-block rolling rule-bank check:

```text
offset360: test_output/rpf_ranked_signal_router/20260623_221301_rank_signal_router_btcusdt_8h_b/
offset240: test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b/
middle:    test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b/
latest:    test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b/
rule bank: test_output/rpf_ranked_signal_rule_bank/20260623_221856_rank_signal_rule_bank/
```

Important caveat:

```text
offset360 requested 120 windows but only evaluated 40 windows:
prediction batches 5457..5496
```

Reason: the current readiness run exposes `400` frozen windows. With
`window_end_offset_steps=360`, only the oldest `40` windows remain. A true
120-window offset360 block requires a longer readiness run.

Rolling-one-block forward results:

| Train Block | Test Block | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| offset360 | offset240 | DOWN | 12 | 12 | 0 | 1.000 | 2.193 | 0.000 |
| offset360 | offset240 | UP | 8 | 4 | 4 | 0.500 | 1.599 | 0.500 |
| offset240 | middle | DOWN | 6 | 3 | 3 | 0.500 | 1.198 | 0.500 |
| offset240 | middle | UP | 10 | 8 | 2 | 0.800 | 2.209 | 0.200 |
| middle | latest | DOWN | 9 | 6 | 3 | 0.667 | 2.000 | 0.333 |
| middle | latest | UP | 17 | 14 | 3 | 0.824 | 1.916 | 0.176 |

Overall over the three forward transitions:

```text
DOWN: 27 signals, 21 TP / 6 FP, precision 0.778, lift 1.934
UP:   35 signals, 26 TP / 9 FP, precision 0.743, lift 2.017
```

Interpretation:

- rolling-one-block adaptation is the strongest router evidence so far;
- DOWN is especially clean in the first partial offset360->offset240 transition,
  but the first train block is only 40 windows, so do not over-trust it;
- next required validation is a longer readiness run, then repeat the same
  rolling rule-bank with full 120-window blocks.

Full-size four-block rolling rule-bank check:

```text
readiness: 520 frozen windows
offset360: test_output/rpf_ranked_signal_router/20260623_222640_rank_signal_router_btcusdt_8h_b/
offset240: test_output/rpf_ranked_signal_router/20260623_224001_rank_signal_router_btcusdt_8h_b/
middle:    test_output/rpf_ranked_signal_router/20260623_225326_rank_signal_router_btcusdt_8h_b/
latest:    test_output/rpf_ranked_signal_router/20260623_230650_rank_signal_router_btcusdt_8h_b/
rule bank: test_output/rpf_ranked_signal_rule_bank/20260623_232201_rank_signal_rule_bank/
```

All four router blocks now have full `120` prediction windows:

```text
offset360: batches 5377..5496
offset240: batches 5497..5616
middle:    batches 5617..5736
latest:    batches 5737..5856
```

Rolling-one-block rule-bank results:

| Train Block | Test Block | Side | Signals | TP | FP | Precision | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|
| offset360 | offset240 | DOWN | 9 | 4 | 5 | 0.444 | 0.974 | 0.556 |
| offset360 | offset240 | UP | 23 | 10 | 13 | 0.435 | 1.391 | 0.565 |
| offset240 | middle | DOWN | 31 | 22 | 9 | 0.710 | 1.701 | 0.290 |
| offset240 | middle | UP | 49 | 20 | 29 | 0.408 | 1.127 | 0.592 |
| middle | latest | DOWN | 53 | 23 | 30 | 0.434 | 1.302 | 0.566 |
| middle | latest | UP | 58 | 41 | 17 | 0.707 | 1.644 | 0.293 |

Overall:

```text
DOWN: 93 signals, 49 TP / 44 FP, precision 0.527, lift 1.310, FDR 0.473
UP:   130 signals, 71 TP / 59 FP, precision 0.546, lift 1.483, FDR 0.454
```

Interpretation:

- full-size rolling rule-bank validation still shows positive lift on both
  sides, so the context-rule idea is not dead;
- false discovery is too high (`0.45..0.47` overall), and two fold/side results
  are especially weak: `offset360 -> offset240 DOWN` and
  `offset240 -> middle UP`;
- this rejects live promotion of the current rule-bank objective;
- next implementation should make rule training more conservative by enforcing
  train-rule gates such as minimum precision/lift and maximum train FDR before
  a rule is eligible for forward replay.

Implemented conservative rule eligibility gates in
`rank_signal_rule_bank.py`.

New rule-bank gate parameters:

```text
--rule-min-train-signals
--rule-min-train-precision
--rule-min-train-precision-lcb
--rule-min-train-lift
--rule-max-train-fdr
--rule-max-train-active-rate
--rule-lcb-z
```

The command now writes:

```text
rule_bank_rule_candidates.parquet  # all fitted rules and reject reasons
rule_bank_rules.parquet            # only eligible replayed rules
```

Strict v1 gate rejected every rule:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_233131_rank_signal_rule_bank/
rule-min-train-signals: 10
rule-min-train-precision: 0.65
rule-min-train-precision-lcb: 0.50
rule-min-train-lift: 1.40
rule-max-train-fdr: 0.35
rule-max-train-active-rate: 0.12
result: 0 signals
```

Calibrated sparse conservative gate:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_233251_rank_signal_rule_bank/
rule-min-train-signals: 3
rule-min-train-precision: 0.65
rule-min-train-precision-lcb: 0.35
rule-min-train-lift: 1.40
rule-max-train-fdr: 0.35
rule-max-train-active-rate: 0.50
```

Result:

| Side | Signals | TP | FP | Precision | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOWN | 84 | 45 | 39 | 0.536 | 1.332 | 0.464 | 0.081 |
| UP | 81 | 51 | 30 | 0.630 | 1.710 | 0.370 | 0.111 |

Compared with the permissive full-size rule bank:

```text
DOWN permissive: 93 signals, precision 0.527, lift 1.310, FDR 0.473
DOWN gated:      84 signals, precision 0.536, lift 1.332, FDR 0.464

UP permissive:   130 signals, precision 0.546, lift 1.483, FDR 0.454
UP gated:        81 signals, precision 0.630, lift 1.710, FDR 0.370
```

Interpretation:

- conservative train-rule gates materially improved UP decision quality;
- DOWN barely improved and still has too many false positives;
- the next fix should be side-specific rule eligibility or side-specific rule
  objective. UP can use the sparse conservative gate; DOWN needs stronger
  current-block context separation before it is usable.

Implemented side-specific rule eligibility in `rank_signal_rule_bank`:

```text
--up-rule-min-train-signals
--up-rule-min-train-precision
--up-rule-min-train-precision-lcb
--up-rule-min-train-lift
--up-rule-max-train-fdr
--up-rule-max-train-active-rate
--up-rule-lcb-z

--down-rule-min-train-signals
--down-rule-min-train-precision
--down-rule-min-train-precision-lcb
--down-rule-min-train-lift
--down-rule-max-train-fdr
--down-rule-max-train-active-rate
--down-rule-lcb-z
```

Asymmetric sparse-UP / strict-DOWN replay:

```text
run: test_output/rpf_ranked_signal_rule_bank/20260623_234159_rank_signal_rule_bank/

UP gate:
  min signals 3, precision 0.65, precision LCB 0.35,
  lift 1.40, max FDR 0.35, max active rate 0.50

DOWN gate:
  min signals 10, precision 0.65, precision LCB 0.50,
  lift 1.40, max FDR 0.35, max active rate 0.50
```

Result:

| Side | Signals | TP | FP | Precision | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOWN | 31 | 22 | 9 | 0.710 | 1.764 | 0.290 | 0.031 |
| UP | 81 | 51 | 30 | 0.630 | 1.710 | 0.370 | 0.111 |

Interpretation:

- stricter DOWN gating removes the weak `offset360 -> offset240` and
  `middle -> latest` DOWN replays, keeping only the cleaner `offset240 ->
  middle` cluster;
- UP stays identical to the sparse conservative gate and remains the broader
  but still high-lift side;
- this is not production evidence because DOWN becomes very sparse and misses
  some DOWN regimes, but it proves the rule bank now supports different
  risk policies per side.

DOWN-focused safe-context separator diagnostic:

```text
run: test_output/rpf_ranked_signal_transfer_separator/20260624_161310_rank_signal_transfer_separator/
diagnostic source: test_output/rpf_ranked_signal_transfer_diagnostic/20260623_212043_rank_signal_transfer_diagnostic/
candidate: down_rocket_16_diag_v1
scope: active good/bad candidate windows only
```

Summary:

```text
analyzed rows: 81
tested safe features: 57
top separator: reliability_precision / reliability_selected_window_precision
top best AUC: 0.703
direction: lower_good
next separator: batch_state_gate_probability
best AUC: 0.698
direction: lower_good
```

Interpretation:

- the current safe-context fields separate good versus bad DOWN windows only
  moderately;
- the top directions are not intuitive enough to promote directly
  (`lower` prior precision/reliability looks better in this slice), which is a
  warning that this is mostly non-stationary block behavior rather than a clean
  stable regime feature;
- this supports the current strict DOWN gate as a defensive diagnostic, but it
  does not solve DOWN coverage;
- the next DOWN step should add or test better prediction-time-safe context
  features for the DOWN side, instead of loosening the existing strict gate.

Added enriched prediction-safe transfer context to
`rank_signal_transfer_diagnostic`:

```text
validation score-shape:
  validation_score_mean/std/min/max/q50/q90/q95/q99
  validation_margin_mean/std/min/max/q50/q90/q95/q99
  validation_margin_positive_rate

validation batch stability:
  validation_batch_base_rate_mean/std/min/max/range
  validation_batch_signal_rate_mean/std/max
  validation_batch_precision_lift_mean/median/std/max
  validation_batch_fdr_mean/median/max
  validation_batch_active_rate_observed
  validation_batch_high_fpr_rate

train-only selector profile:
  selected_feature_rows
  selected_abs_coef_sum/mean/std/max
  selected_top1_abs_coef_share
  selected_feature_train_std_mean/max
```

Enriched diagnostic runs:

```text
two-block diagnostic:
  test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162157_rank_signal_transfer_diagnostic/
  separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_162157_rank_signal_transfer_separator/

four-block diagnostic:
  test_output/rpf_ranked_signal_transfer_diagnostic/20260624_162103_rank_signal_transfer_diagnostic/
  separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_162115_rank_signal_transfer_separator/
```

Result:

```text
two-block enriched:
  top feature remains reliability_precision
  best AUC 0.703
  new validation-score features do not beat existing reliability fields

four-block enriched:
  top feature threshold
  best AUC 0.599
  best new feature validation_score_q95
  best AUC 0.599
```

Interpretation:

- artifact-derived validation score shape and ElasticNet selector profile did
  not solve DOWN transfer;
- on the full four-block span, DOWN good/bad separation is weak even with the
  enriched safe context;
- the next DOWN work should use genuinely different prediction-time-safe
  context, such as causal OHLCV/RPF regime state from prior rows or explicit
  row-level context conditioning, rather than more aggregate router metadata.

Added causal prior-RPF regime context to the transfer diagnostic:

```text
code path: regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic
trigger: --base-run <readiness_run> with --rpf-prior-context enabled
lookbacks: 20 and 60 prior available batches
families: all fixed RPF families from walkforward.ablation.FAMILY_PREFIXES
max features per family: 24
leak rule: prior context uses batch_id < router_pred_batch_id only
```

New context columns summarize prior batches only:

```text
prior_rpf_l{20,60}_{family}_available_batches
prior_rpf_l{20,60}_{family}_feature_count
prior_rpf_l{20,60}_{family}_mean_abs
prior_rpf_l{20,60}_{family}_std_abs
prior_rpf_l{20,60}_{family}_recent_shift_abs
prior_rpf_l{20,60}_{family}_mean
prior_rpf_l{20,60}_{family}_std_mean
```

Four-block diagnostic with prior-RPF context:

```text
diagnostic:
  test_output/rpf_ranked_signal_transfer_diagnostic/20260624_163148_rank_signal_transfer_diagnostic/
safe context rows: 1440
safe context cols: 301
prior RPF cols: 168
active rows: 765
good rows: 171
bad rows: 433
```

DOWN separator:

```text
separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_163220_rank_signal_transfer_separator/
candidate: down_rocket_16_diag_v1
active good/bad rows: 227
top feature: prior_rpf_l20_regime_calendar_state_std_mean
best AUC: 0.605
direction: lower_good
```

UP separator:

```text
separator:
  test_output/rpf_ranked_signal_transfer_separator/20260624_163242_rank_signal_transfer_separator/
candidates: up_none_v1, up_rocket_64_v1
active good/bad rows: 377
top feature overall: score_mean
best AUC overall: 0.730
top candidate feature: up_rocket_64_v1 score_mean
best candidate AUC: 0.770
direction: lower_good
```

Interpretation:

- simple prior RPF family-level context still does not solve DOWN transfer;
- the best DOWN separator remains weak on the full four-block span;
- UP has more usable separator structure, especially `up_rocket_64_v1`
  lower score-mean contexts;
- next work should not broaden candidates yet. The clean next step is to test
  whether these separator fields can improve the side-specific rule bank:
  keep UP sparse/conservative, and keep DOWN strict unless a stronger
  row-level or side-specific context objective is implemented.

Implemented row-level ranked-signal TP/FP diagnostic:

```text
command:
  python -m regression_feature_engineering.walkforward.rank_signal_row_diagnostic

purpose:
  inspect rows where a candidate actually fired a signal and separate post-hoc
  true positives from false positives using prediction-time-safe row context.

artifacts:
  row_signal_transfer_table.parquet      # includes TP/FP labels
  row_safe_context_features.parquet      # excludes target/outcome columns
  row_feature_separation.parquet
  row_separator_summary.parquet
  row_separator_report.md
```

Leak contract:

```text
safe row context includes model score fields and same-row RPF feature-family
summaries joined by exact timestamp,batch_id.

safe row context excludes:
  target_binary
  target_relevance
  signal_tp
  signal_fp
  signal_outcome
```

First DOWN row diagnostic:

```text
run:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/

inputs:
  test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b
  test_output/rpf_ranked_signal_router/20260623_180640_rank_signal_router_btcusdt_8h_b

side: down
candidate: down_rocket_16_diag_v1
source: candidate_prediction_scores
signal rows: 169
TP rows: 75
FP rows: 94
```

Raw block quality:

| Source | Signals | TP | FP | Precision |
|---|---:|---:|---:|---:|
| middle | 100 | 49 | 51 | 0.490 |
| latest | 69 | 26 | 43 | 0.377 |

Top row-level separator:

```text
feature: rank_score
best AUC: 0.688
direction: higher_good
TP mean: 0.0291
FP mean: 0.0221
```

Best RPF row-family separators:

```text
row_rpf_structural_room_mean_abs:
  best AUC 0.646, higher_good

row_rpf_sequence_embedding_layer_max_abs:
  best AUC 0.627, lower_good

row_rpf_cross_asset_context_positive_rate:
  best AUC 0.620, higher_good
```

Middle-to-latest one-step replay check:

```text
learned from middle signal rows, replayed on latest signal rows

row_rpf_cross_asset_context_mean_abs >= about 0.299:
  latest: 9 signals, 6 TP, 3 FP, precision 0.667

row_rpf_interaction_confluence_mean >= about 0.135:
  latest: 11 signals, 7 TP, 4 FP, precision 0.636
```

Interpretation:

- DOWN false positives are partly score-quality and row-context related;
- stricter row-level filters can improve latest precision, but only sparsely;
- this is still not enough to recover broad DOWN coverage;
- the next correct implementation is a controlled row-filter rule bank, not a
  new model branch. It should learn row filters on prior matured signal rows
  and replay them on the next block, with minimum signal-count and precision
  gates.

Implemented row-filter rule bank:

```text
command:
  python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank

purpose:
  train simple one-feature filters on prior matured signal rows and replay the
  best eligible row filters on the next chronological block.

artifacts:
  row_rule_bank_rule_candidates.parquet
  row_rule_bank_rules.parquet
  row_rule_bank_rule_acceptance.parquet
  row_rule_bank_candidate_acceptance.parquet
  row_rule_bank_fold_summary.parquet
  row_rule_bank_overall_summary.parquet
  row_rule_bank_report.md
```

Important implementation detail:

```text
The first version allowed every eligible row rule to union together and
therefore accepted all latest DOWN signals. This was fixed by adding
--max-rules-per-candidate, defaulting to 1, so a broad rule union cannot erase
the filter.
```

First corrected DOWN row-filter replay:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_192814_rank_signal_row_rule_bank/

source row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_185848_rank_signal_row_diagnostic/

train block: middle
test block: latest
side: down
candidate: down_rocket_16_diag_v1
max rules per candidate: 1
```

Learned rule:

```text
row_rpf_cross_asset_context_mean >= 0.3012844470752333

train:
  10 accepted rows, 10 TP, 0 FP
  precision 1.000
  lift 2.041

latest replay:
  9 signals, 6 TP, 3 FP
  precision 0.667
  FDR 0.333
```

Interpretation:

- the row-filter rule bank can clean DOWN signals better than aggregate
  candidate/window routing;
- coverage is still sparse, but this is a real validation-to-prediction
  transfer improvement on the tested middle-to-latest transition;
- this should become the next controlled validation path: rerun row diagnostics
  and row-rule-bank replay across more chronological blocks before wiring any
  row filter into the router.

Broader DOWN row-rule validation:

```text
row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_193124_rank_signal_row_diagnostic/

blocks:
  offset240, middle, latest

raw down_rocket_16_diag_v1 signal quality:
  offset240: 200 signals, 95 TP, 105 FP, precision 0.475
  middle:    100 signals, 49 TP,  51 FP, precision 0.490
  latest:     69 signals, 26 TP,  43 FP, precision 0.377
```

Initial broad one-rule replay using the old threshold-only `rule_score` failed:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193146_rank_signal_row_rule_bank/

overall:
  25 signals, 9 TP, 16 FP, precision 0.360

failure mode:
  the selected offset240->middle rule had high train lift but feature-level
  direction disagreement, so it was likely a narrow threshold coincidence.
```

Updated row-rule selector:

```text
new option:
  --rule-selection-score directional_lcb_v1

score uses train-only:
  precision lower bound
  accepted-row support
  false-discovery penalty
  feature-level AUC direction agreement
```

Broad replay with the new train-only selector:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_193705_rank_signal_row_rule_bank/

offset240 -> middle:
  rule: row_rpf_rejection_chop_max_abs <= 0.9583333333333334
  replay: 21 signals, 13 TP, 8 FP, precision 0.619

middle -> latest:
  rule: row_rpf_cross_asset_context_mean >= 0.3012844470752333
  replay: 9 signals, 6 TP, 3 FP, precision 0.667

overall:
  30 signals, 19 TP, 11 FP, precision 0.633, FDR 0.367
```

Interpretation:

- row-level DOWN filtering now shows transfer across two consecutive
  chronological transitions;
- the useful rule is not one static feature forever: the train-only selector
  changed from rejection/chop context to cross-asset context as the block
  changed;
- this is still diagnostic, not live router behavior;
- next correct step is to validate `directional_lcb_v1` on more blocks or wire
  it into a shadow row-filter router mode that never uses current prediction
  labels for current decisions.

Four-block DOWN row-rule validation:

```text
router blocks rerun with non-empty candidate_prediction_scores:
  offset360: test_output/rpf_ranked_signal_router/20260624_215759_rank_signal_router_btcusdt_8h_b
  offset240: test_output/rpf_ranked_signal_router/20260624_221618_rank_signal_router_btcusdt_8h_b
  middle:    test_output/rpf_ranked_signal_router/20260624_223415_rank_signal_router_btcusdt_8h_b
  latest:    test_output/rpf_ranked_signal_router/20260624_225218_rank_signal_router_btcusdt_8h_b

row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic/

row-rule replay:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_233936_rank_signal_row_rule_bank/
```

Raw `down_rocket_16_diag_v1` signal quality:

```text
offset360: 231 signals, 88 TP, 143 FP, precision 0.381
offset240: 200 signals, 95 TP, 105 FP, precision 0.475
middle:    208 signals, 103 TP, 105 FP, precision 0.495
latest:    172 signals, 68 TP, 104 FP, precision 0.395
```

`directional_lcb_v1` row-rule replay:

```text
offset360 -> offset240:
  rule: row_rpf_spike_breakout_mean_abs >= 0.20970151458052308
  replay: 39 signals, 20 TP, 19 FP, precision 0.513

offset240 -> middle:
  rule: row_rpf_rejection_chop_max_abs <= 0.9583333333333334
  replay: 53 signals, 35 TP, 18 FP, precision 0.660

middle -> latest:
  rule: row_rpf_interaction_confluence_positive_rate >= 0.6666666666666666
  replay: 49 signals, 14 TP, 35 FP, precision 0.286

overall:
  141 signals, 69 TP, 72 FP, precision 0.489
```

Interpretation:

- the new selector improved offset360->offset240 and offset240->middle;
- it failed on middle->latest and made latest worse than raw precision;
- all-eligible diagnostic replay showed there were better middle-trained
  rules for latest, for example:

```text
row_rpf_unsupervised_factor_layer_positive_rate >= 1.0:
  latest 18 signals, 11 TP, 7 FP, precision 0.611

row_rpf_structural_room_mean_abs >= 0.411443:
  latest 25 signals, 14 TP, 11 FP, precision 0.560
```

Conclusion:

```text
directional_lcb_v1 is not enough as the final row-rule selector.
The next correct implementation is row-rule prequential reliability: evaluate
all eligible row rules as shadow rules, mature their next-block performance,
and prefer rules/families with prior out-of-sample reliability instead of only
current train-block score.
```

Implemented row-rule prequential reliability:

```text
command:
  python -m regression_feature_engineering.walkforward.rank_signal_row_rule_bank

new mode:
  --row-rule-selection-mode prequential_reliability_v1

new artifacts:
  row_rule_bank_shadow_rule_acceptance.parquet
  row_rule_bank_rule_reliability.parquet
  row_rule_bank_selection_audit.parquet
```

Contract:

```text
1. Train eligible row rules on current train block.
2. Shadow-score all eligible rules on the next block.
3. Current block labels are not used to select current rules.
4. After the block matures, shadow rule outcomes update reliability memory.
5. Future rules can be selected only if their feature/direction or
   family/direction has prior matured reliability.
```

First real prequential replay:

```text
run:
  test_output/rpf_ranked_signal_row_rule_bank/20260624_235147_rank_signal_row_rule_bank/

row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic/

mode:
  prequential_reliability_v1

reliability key:
  feature_direction

warmup:
  no_signal
```

Result:

```text
selected only fold 2 because earlier folds had no matured reliability yet

middle -> latest:
  selected rule:
    row_rpf_rejection_chop_max_abs <= 0.994176

  prior reliability:
    53 signals, 35 TP, 18 FP
    precision 0.660
    FDR 0.340

  latest replay:
    52 signals, 22 TP, 30 FP
    precision 0.423
    FDR 0.577
```

Comparison:

```text
raw latest candidate:
  68/172 = 0.395 precision

static directional_lcb_v1 latest:
  14/49 = 0.286 precision

prequential reliability latest:
  22/52 = 0.423 precision
```

Interpretation:

- prequential reliability fixed the worst static-selector failure;
- the improvement is small and still not good enough for promotion;
- the method needs more chronological blocks because with four blocks and
  no-signal warmup it can only make one mature reliability-selected decision;
- family-level reliability produced the same selected rule in this first test.

Eight-block 60-window prequential validation:

```text
router blocks:
  offsets: 420, 360, 300, 240, 180, 120, 60, 0
  window count per block: 60
  all wrote non-empty candidate_prediction_scores

row diagnostic:
  test_output/rpf_ranked_signal_row_diagnostic/20260627_125952_rank_signal_row_diagnostic/

feature-direction reliability:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_130019_rank_signal_row_rule_bank/

family-direction reliability:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_130034_rank_signal_row_rule_bank/
```

Raw `down_rocket_16_diag_v1` signal quality across the eight blocks:

```text
overall:
  811 signals, 354 TP, 457 FP, precision 0.436

block precision:
  offset420: 0.402
  offset360: 0.366
  offset300: 0.516
  offset240: 0.439
  offset180: 0.547
  middle:    0.441
  offset60:  0.375
  latest:    0.413
```

Feature-direction prequential reliability:

```text
latest comparison artifact:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131037_rank_signal_row_rule_bank/

filtered:
  69 signals, 40 TP, 29 FP
  precision 0.580
  FDR 0.420

same-block raw baseline:
  487 signals, 218 TP, 269 FP
  precision 0.448

precision lift:
  1.30x
```

Per-block feature-direction replay:

```text
offset300 -> offset240:
  24 signals, 15 TP, 9 FP, precision 0.625, lift 1.42x

offset240 -> offset180:
  8 signals, 5 TP, 3 FP, precision 0.625, lift 1.14x

offset180 -> middle:
  11 signals, 8 TP, 3 FP, precision 0.727, lift 1.65x

middle -> offset60:
  4 signals, 2 TP, 2 FP, precision 0.500, lift 1.33x

offset60 -> latest:
  22 signals, 10 TP, 12 FP, precision 0.455, lift 1.10x
```

Family-direction prequential reliability:

```text
latest comparison artifact:
  test_output/rpf_ranked_signal_row_rule_bank/20260627_131053_rank_signal_row_rule_bank/

filtered:
  116 signals, 66 TP, 50 FP
  precision 0.569
  FDR 0.431

same-block raw baseline:
  580 signals, 266 TP, 314 FP
  precision 0.459

precision lift:
  1.24x
```

Interpretation:

- feature-direction reliability is more conservative and slightly cleaner;
- family-direction reliability fires earlier and more often, but one block
  underperformed raw precision;
- both are real improvements over the raw DOWN candidate, but still sparse;
- the active next direction is to treat feature-direction reliability as the
  preferred row-filter mode and evaluate it on more history / integrate it as a
  shadow router gate before promotion.

Implementation update:

```text
row_rule_bank now writes raw-vs-filtered comparison artifacts:
  row_rule_bank_fold_comparison.parquet
  row_rule_bank_overall_comparison.parquet

The Markdown report includes:
  fold raw comparison
  overall raw comparison
```

These artifacts make the row-filter gate a reproducible shadow comparison
rather than a manual post-hoc calculation.

2026-06-27 router shadow row-rule gate implementation:

```text
command:
  python -m regression_feature_engineering.walkforward.rank_signal_router

new optional mode:
  --row-rule-gate-mode prequential_reliability_v1

default shadow side/candidate:
  side: down
  candidate: down_rocket_16_diag_v1
```

What changed:

- the normal router outputs remain unchanged:
  `router_prediction_scores.parquet` and `router_decisions.parquet` are still
  raw selected-router decisions;
- the row-rule gate is written as separate shadow artifacts:
  `row_rule_gate_signal_rows.parquet`,
  `row_rule_gate_rules.parquet`,
  `row_rule_gate_decisions.parquet`,
  `row_rule_gate_fold_comparison.parquet`, and
  `row_rule_gate_overall_comparison.parquet`;
- the gate uses candidate prediction scores, live-safe same-row RPF context,
  and prior matured block reliability only;
- current prediction labels are used only after maturity for future
  row-rule reliability and for output diagnostics;
- `block000`, `block001`, ... source blocks are supported, so a single long
  router run can replay row rules prequentially without manually creating
  separate diagnostic runs.

Validation:

```text
python -m pytest tests/test_rpf_rank_signal_router.py \
  tests/test_rpf_rank_signal_row_rule_bank.py -q

result:
  39 passed
```

Next real run:

- rerun the ranked-signal router over a long block with
  `--row-rule-gate-mode prequential_reliability_v1`;
- compare `row_rule_gate_overall_comparison.parquet` against raw
  `candidate_prediction_scores.parquet`;
- do not treat the row gate as promoted until the integrated router shadow
  result reproduces the earlier eight-block diagnostic lift.

Integrated router shadow-gate result:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_133550_rank_signal_router_btcusdt_8h_b/

setup:
  outer windows: 480
  block size: 60
  row-rule mode: prequential_reliability_v1
  row-rule key: feature_direction
  shadow side/candidate: down / down_rocket_16_diag_v1
```

Normal selected-router decisions remained weak:

```text
UP:
  3 signals, 3 TP / 0 FP, precision 1.000

DOWN:
  62 signals, 25 TP / 37 FP, precision 0.403
  down_none_v1 selected rows: 47 signals, 19 TP / 28 FP, precision 0.404
  down_rocket_16_diag_v1 selected rows: 15 signals, 6 TP / 9 FP, precision 0.400
```

Shadow raw candidate baseline:

```text
down_rocket_16_diag_v1:
  811 signals, 354 TP / 457 FP, precision 0.436
```

Integrated shadow row-rule gate:

```text
filtered:
  69 signals, 40 TP / 29 FP
  precision 0.580
  FDR 0.420

same selected-block raw baseline:
  487 signals, 218 TP / 269 FP
  precision 0.448

precision lift vs raw:
  1.295x

signal retention vs raw:
  0.142
```

Per mature block:

```text
block003: 24 signals, 15 TP / 9 FP, precision 0.625, lift 1.423x
block004:  8 signals,  5 TP / 3 FP, precision 0.625, lift 1.142x
block005: 11 signals,  8 TP / 3 FP, precision 0.727, lift 1.648x
block006:  4 signals,  2 TP / 2 FP, precision 0.500, lift 1.333x
block007: 22 signals, 10 TP / 12 FP, precision 0.455, lift 1.100x
```

Interpretation:

- the integrated router shadow gate reproduced the eight-block diagnostic
  result;
- row filtering is improving DOWN row precision versus the same candidate raw
  decisions;
- the normal router selection layer is still not useful enough;
- the next implementation step should make the row-rule gate an explicit
  active decision output for the DOWN `down_rocket_16_diag_v1` branch while
  keeping raw router decisions and shadow comparisons for audit.

Implemented active row-rule decision output:

```text
rank_signal_router option:
  --row-rule-gate-output-mode active_down_candidate
```

This does not replace normal router outputs. It adds:

```text
row_rule_active_prediction_scores.parquet
row_rule_active_decisions.parquet
row_rule_active_window_metrics.parquet
row_rule_active_block_summary.parquet
row_rule_active_side_summary.json
```

Contract:

- uses the configured raw candidate score rows, currently
  `down_rocket_16_diag_v1`;
- preserves `raw_candidate_decision`;
- sets active `decision=1` only for rows accepted by the mature row-rule gate;
- computes active metrics on the full candidate prediction row universe, not
  only on accepted rows;
- keeps `router_decisions.parquet` and `row_rule_gate_*` shadow artifacts
  unchanged for audit.

Validation:

```text
python -m pytest tests/test_rpf_rank_signal_router.py \
  tests/test_rpf_rank_signal_row_rule_bank.py -q

result:
  40 passed
```

Active row-rule decision validation:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_150157_rank_signal_router_btcusdt_8h_b/

mode:
  --row-rule-gate-output-mode active_down_candidate
```

Normal router outputs stayed unchanged:

```text
DOWN normal router:
  62 signals, 25 TP / 37 FP
  precision 0.403
  FDR 0.597
```

Active row-rule output:

```text
DOWN active row-rule candidate:
  69 signals, 40 TP / 29 FP
  precision 0.580
  FDR 0.420
  false-positive rate 0.000420
  active-window rate 0.0542
  precision lift vs full DOWN base rate 1.445x
```

Same-block raw comparison remains:

```text
same-block raw candidate:
  487 signals, 218 TP / 269 FP
  precision 0.448

active row-rule lift vs same-block raw:
  1.295x

signal retention vs same-block raw:
  0.142
```

Interpretation:

- the active output mode is mechanically correct;
- it preserves `raw_candidate_decision` and writes decisions only where the
  mature row-rule gate accepts a row;
- it improves DOWN precision materially versus both the normal router and the
  raw candidate;
- it remains sparse and should be validated on more history before promotion.

Longer readiness prepared:

```text
run:
  test_output/rpf_clean_walkforward/20260627_162728_readiness_btcusdt_8h_b_target_reg_direction_extreme_up_sha_2d5c0524/

windows:
  1000

prediction batch range:
  4857..5856

label window safety:
  pass
```

Next validation should use `960` outer windows with `60`-window blocks. This
creates `16` equal chronological blocks, which is enough to test whether the
active row-rule path survives more regimes instead of only the latest
`480`-window slice.

960-window active row-rule stress test:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_162925_rank_signal_router_btcusdt_8h_b/

setup:
  outer windows: 960
  blocks: 16 x 60 windows
  candidate allowlist: up_none_v1, down_rocket_16_diag_v1
  row-rule output: active_down_candidate
```

Normal router DOWN:

```text
24 signals, 6 TP / 18 FP
precision 0.250
FDR 0.750
```

Active row-rule DOWN:

```text
144 signals, 55 TP / 89 FP
precision 0.382
FDR 0.618
precision lift vs full DOWN base rate 0.981x
```

Same-block raw candidate baseline:

```text
795 signals, 326 TP / 469 FP
precision 0.410
```

Active row-rule versus same-block raw:

```text
precision lift vs raw: 0.931x
signal retention:      0.181
TP retention:          0.169
FP retention:          0.190
```

Block evidence:

```text
good blocks:
  block009 precision 0.500, lift 1.367x
  block012 precision 0.625, lift 1.142x
  block015 precision 0.727, lift 1.761x

bad blocks:
  block005 precision 0.346, lift 0.865x
  block006 precision 0.000, lift 0.000x
  block011 precision 0.143, lift 0.325x
  block013 precision 0.439, lift 0.995x
  block014 precision 0.000, lift 0.000x
```

Interpretation:

- the active row-rule path is not robust over 960 windows;
- the previous 480-window win was real but local;
- current prequential row-rule reliability is too stale across regimes;
- selected rules can pass historical reliability but fail the next block
  badly, especially after adding older history;
- do not promote this active row-rule gate yet.

Next implementation direction:

- add recency-limited row-rule reliability, e.g. use only the last `N` matured
  folds or exponential decay, instead of all prior shadow history;
- add a rule-level current-train sanity gate that requires the selected rule to
  be strong in the immediately previous block, not just historically reliable;
- rerun 960-window validation only after stale-rule selection is fixed.

Implemented recency-limit option:

```text
--row-rule-gate-reliability-lookback-folds N
```

Default `0` preserves the previous behavior and uses all prior matured folds.
Positive values use only the last `N` matured row-rule folds when computing
rule reliability. The next validation should rerun the same 960-window test
with `N=3` and `N=5` to check whether stale historical rules were the real
source of the transfer failure.

960-window recency-limited reliability result:

```text
runs:
  lookback=3:
    test_output/rpf_ranked_signal_router/20260627_174917_rank_signal_router_btcusdt_8h_b/
  lookback=5:
    test_output/rpf_ranked_signal_router/20260627_190215_rank_signal_router_btcusdt_8h_b/

baseline all-history active row-rule:
  144 signals, 55 TP / 89 FP
  precision 0.382
  FDR 0.618
  precision lift vs full DOWN base 0.981x

lookback=3:
  111 signals, 55 TP / 56 FP
  precision 0.495
  FDR 0.505
  precision lift vs full DOWN base 1.272x
  precision lift vs raw gate-signal rows 1.221x

lookback=5:
  116 signals, 49 TP / 67 FP
  precision 0.422
  FDR 0.578
  precision lift vs full DOWN base 1.085x
  precision lift vs raw gate-signal rows 1.041x
```

Interpretation:

- recency-limited reliability is a real improvement;
- `lookback=3` is clearly better than all-history and `lookback=5`;
- it still does not satisfy a strict promotion target because FDR remains
  slightly above `0.50`;
- the remaining failure is weak reliability-LCB acceptance: bad early blocks
  passed with `reliability_precision_lcb` around `0.52-0.54`.

Post-hoc threshold diagnostic on the `lookback=3` run:

```text
actual lookback=3:
  111 signals, 55 TP / 56 FP, precision 0.495

if reliability_precision_lcb >= 0.55:
  38 signals, 24 TP / 14 FP, precision 0.632

if reliability_false_discovery_rate <= 0.35:
  38 signals, 24 TP / 14 FP, precision 0.632
```

Next validation:

- keep `--row-rule-gate-reliability-lookback-folds 3`;
- raise `--row-rule-gate-reliability-min-precision-lcb` from `0.45` to `0.55`;
- optionally set `--row-rule-gate-reliability-max-fdr 0.35`;
- rerun the same 960-window span and compare active precision, FDR, and block
  stability.

960-window strict recency reliability result:

```text
run:
  test_output/rpf_ranked_signal_router/20260627_202223_rank_signal_router_btcusdt_8h_b/

setup:
  row-rule reliability lookback folds: 3
  row-rule reliability min precision LCB: 0.55
  row-rule reliability max FDR: 0.35
  candidate allowlist: up_none_v1, down_rocket_16_diag_v1
  active output: down_rocket_16_diag_v1 row-rule gate

active row-rule DOWN:
  38 signals
  24 TP / 14 FP
  precision 0.632
  FDR 0.368
  precision lift vs full DOWN base 1.622x
  precision lift vs raw gate-signal rows 1.556x
  signal retention vs raw 0.026

normal router DOWN:
  24 signals
  6 TP / 18 FP
  precision 0.250

raw row-rule gate signal rows:
  1476 signals
  599 TP / 877 FP
  precision 0.406
```

Active blocks:

```text
block011: 24 signals, 15 TP / 9 FP, precision 0.625
block014:  4 signals,  2 TP / 2 FP, precision 0.500
block015: 10 signals,  7 TP / 3 FP, precision 0.700
```

Interpretation:

- strict recency reliability is the current best DOWN precision result over
  the 960-window span;
- it removed the worst early stale-rule blocks from the `lookback=3` run;
- it is very sparse, with only `38` active signals over `960` prediction
  batches;
- this is useful as a high-precision specialist signal, not a broad directional
  predictor;
- next work should test whether this sparse signal remains stable on older
  chronological slices or adjacent windows, not tune model complexity.

Offset transfer validation:

```text
runs:
  latest offset=0:
    test_output/rpf_ranked_signal_router/20260627_202223_rank_signal_router_btcusdt_8h_b/
  offset=480:
    test_output/rpf_ranked_signal_router/20260627_214027_rank_signal_router_btcusdt_8h_b/
  offset=960:
    test_output/rpf_ranked_signal_router/20260627_225304_rank_signal_router_btcusdt_8h_b/

latest offset=0:
  pred batches 4897..5856
  38 signals, 24 TP / 14 FP
  precision 0.632
  FDR 0.368

offset=480:
  pred batches 4417..5376
  15 signals, 6 TP / 9 FP
  precision 0.400
  FDR 0.600

offset=960:
  pred batches 3937..4896
  9 signals, 0 TP / 9 FP
  precision 0.000
  FDR 1.000
```

Interpretation:

- the strict DOWN row-rule specialist does not transfer to older slices;
- the same failed period appears in both older offset tests:
  `pred_batch_id 4657..4716`;
- the failed rule was:
  `row_rpf_liquidity_volume_pressure_mean_abs lower_good <= 0.3223715487502642`;
- latest successful strict signals used only `higher_good` row rules.

Post-hoc direction filter across the three 960-window spans:

```text
actual strict rules:
  62 signals, 30 TP / 32 FP
  precision 0.484
  FDR 0.516

higher_good rules only:
  44 signals, 30 TP / 14 FP
  precision 0.682
  FDR 0.318
```

Next implementation:

- add an explicit row-rule direction filter;
- rerun the same offset `0`, `480`, and `960` transfer check with:
  `--row-rule-gate-allowed-directions higher_good`;
- if this holds, treat the DOWN specialist as a directional row-rule family,
  not as a generic row-rule gate.

Higher-good direction-filter transfer result:

```text
runs:
  offset=0:
    test_output/rpf_ranked_signal_router/20260628_001251_rank_signal_router_btcusdt_8h_b/
  offset=480:
    test_output/rpf_ranked_signal_router/20260628_013625_rank_signal_router_btcusdt_8h_b/
  offset=960:
    test_output/rpf_ranked_signal_router/20260628_025919_rank_signal_router_btcusdt_8h_b/

offset=0 latest, pred batches 4897..5856:
  38 signals, 24 TP / 14 FP
  precision 0.632
  FDR 0.368
  lift vs full DOWN base 1.622x

offset=480 bridge, pred batches 4417..5376:
  25 signals, 13 TP / 12 FP
  precision 0.520
  FDR 0.480
  lift vs full DOWN base 1.371x

offset=960 older, pred batches 3937..4896:
  19 signals, 7 TP / 12 FP
  precision 0.368
  FDR 0.632
  lift vs full DOWN base 0.976x
```

Interpretation:

- `higher_good` improves the bridge slice and combined precision, but it does
  not solve chronological transfer;
- the older non-overlapping slice still underperforms the local DOWN base rate;
- the same problematic batch window `4657..4716` remains weak even with
  `higher_good`, now via `row_rpf_rejection_chop_mean_abs higher_good`;
- the strict row-rule specialist is not promotable as a stable model rule.

Combined offset `0/480/960` comparison:

```text
strict any-direction:
  62 signals, 30 TP / 32 FP
  precision 0.484
  FDR 0.516

strict higher-good:
  82 signals, 44 TP / 38 FP
  precision 0.537
  FDR 0.463
```

Decision:

- keep `higher_good` as a useful row-rule diagnostic;
- do not promote the row-rule specialist as-is;
- next work must explain the bad `4657..4716` regime using safe context
  diagnostics before adding another gate threshold.

Safe-context diagnostic result:

```text
run:
  test_output/rpf_ranked_signal_context_diagnostic/20260628_044337_rank_signal_context_diagnostic/

inputs:
  higher-good offset=0, offset=480, offset=960 router runs

active blocks analysed:
  6

combined active row-rule output:
  82 signals
  44 TP / 38 FP
  precision 0.537
  base rate 0.379
  lift 1.416x

block labels:
  good: 3
  bad: 2
  neutral_active: 1
```

Important separators:

- bad blocks are the repeated `row_rpf_rejection_chop_mean_abs higher_good`
  rule in `offset480/block004` and `offset960/block012`;
- good blocks are mostly liquidity-volume-pressure rules plus one rank-score
  block;
- good blocks had higher `rule_score`, `selection_score`,
  `reliability_score`, `train_lift`, and `reliability_precision_lcb`;
- the diagnostic intentionally separates `context_rows.parquet` from
  `specialist_block_outcomes.parquet`, so current TP/FP labels do not leak into
  context features.

Current decision:

- do not add more CatBoost/ROCKET/CNN tuning yet;
- next implementation should use the context diagnostic to suppress or
  separately treat the `rejection_chop` row-rule family before another long
  replay;
- any adaptive rule must be validated on offset blocks, not only on the latest
  slice.

Implemented next control knob:

```text
--row-rule-gate-allowed-families
--row-rule-gate-blocked-families
```

Default behavior is unchanged. The next validation should replay the same
strict higher-good offset tests with:

```text
--row-rule-gate-blocked-families rejection_chop
```

Purpose:

- test whether the repeated bad `rejection_chop` context is the main transfer
  failure;
- keep the known useful `liquidity_volume_pressure` and `rank_score` contexts
  eligible;
- reject the filter if it only removes signals without improving older-block
  precision lift.

Rejection-chop block replay result:

```text
runs:
  offset=0:
    test_output/rpf_ranked_signal_router/20260628_045015_rank_signal_router_btcusdt_8h_b/
  offset=480:
    test_output/rpf_ranked_signal_router/20260628_061237_rank_signal_router_btcusdt_8h_b/
  offset=960:
    test_output/rpf_ranked_signal_router/20260628_073452_rank_signal_router_btcusdt_8h_b/

configuration delta:
  --row-rule-gate-allowed-directions higher_good
  --row-rule-gate-blocked-families rejection_chop

offset=0:
  38 signals, 24 TP / 14 FP
  precision 0.632
  FDR 0.368
  lift 1.622x

offset=480:
  6 signals, 6 TP / 0 FP
  precision 1.000
  FDR 0.000
  lift 2.636x

offset=960:
  0 signals
```

Combined comparison against higher-good without family block:

```text
higher_good baseline:
  82 signals, 44 TP / 38 FP
  precision 0.537
  FDR 0.463
  lift 1.404x
  active blocks 6

higher_good excluding rejection_chop:
  44 signals, 30 TP / 14 FP
  precision 0.682
  FDR 0.318
  lift 1.784x
  active blocks 4
```

Context diagnostic:

```text
run:
  test_output/rpf_ranked_signal_context_diagnostic/20260628_090320_rank_signal_context_diagnostic/

active blocks: 4
good blocks:   3
bad blocks:    0
signals:       44
precision:     0.682
lift:          1.811x
```

Decision:

- blocking `rejection_chop` is a valid false-positive suppression rule;
- it is not yet a complete adaptive router because offset `960` produced no
  signals;
- current useful rule families are `liquidity_volume_pressure`, `rank_score`,
  and possibly `interaction_confluence` as a neutral/high-lift but lower
  precision context;
- next step should evaluate whether the same safe families repeat on a longer
  non-overlapping history, or whether we need a separate discovery pass for
  older regimes rather than more global model tuning.

UP target tracking correction:

```text
target:
  target_cls_extreme_up_ge_2x_down_hvol_v2

problem:
  the latest row-rule transfer work changed only the DOWN side.
```

Why focus drift happened:

- both UP and DOWN stayed in the router artifacts;
- the row-rule gate was implemented as an explicit DOWN active-output path:
  `--row-rule-gate-output-mode active_down_candidate`;
- the active row-rule work targeted:
  `side=down`, `candidate=down_rocket_16_diag_v1`;
- the latest offset replay also used:
  `--candidate-name-allowlist up_none_v1,down_rocket_16_diag_v1`;
- this excluded `up_rocket_64_v1`, even though earlier ranked-signal evidence
  said it was the stronger UP specialist candidate in several runs.

Therefore the latest UP numbers are not a complete UP optimization result.
They are only the UP behavior that remained active while the DOWN row-rule
gate was being tested.

Latest UP behavior from the three rejection-chop-blocked router runs:

```text
runs:
  offset=0:
    test_output/rpf_ranked_signal_router/20260628_045015_rank_signal_router_btcusdt_8h_b/
  offset=480:
    test_output/rpf_ranked_signal_router/20260628_061237_rank_signal_router_btcusdt_8h_b/
  offset=960:
    test_output/rpf_ranked_signal_router/20260628_073452_rank_signal_router_btcusdt_8h_b/

UP candidate available in these runs:
  up_none_v1 only

UP selected-router decisions:
  offset=0:
    21 signals, 9 TP / 12 FP
    precision 0.429
    base rate 0.375
    lift 1.142x
    active 60-batch blocks 3 / 16

  offset=480:
    21 signals, 6 TP / 15 FP
    precision 0.286
    base rate 0.385
    lift 0.742x
    active 60-batch blocks 3 / 16

  offset=960:
    3 signals, 0 TP / 3 FP
    precision 0.000
    base rate 0.400
    lift 0.000x
    active 60-batch blocks 1 / 16

combined:
  45 signals, 15 TP / 30 FP
  precision 0.333
  approximate base rate 0.387
  lift about 0.86x
  active blocks 7 / 48
```

UP shadow `up_none_v1` was broad and weakly above base, but not a sparse
high-precision specialist:

```text
offset=0:
  916 shadow signals, precision 0.392, lift 1.044x

offset=480:
  880 shadow signals, precision 0.423, lift 1.098x

offset=960:
  803 shadow signals, precision 0.428, lift 1.070x
```

Earlier UP evidence that must not be lost:

```text
small ROCKET UP ranked-signal run:
  run: test_output/rpf_ranked_signal/20260623_000231_rank_signal_btcusdt_8h_b_up/
  17 signals, 13 TP / 4 FP
  precision 0.765
  lift 1.386x

sparse conservative UP rule bank:
  run: test_output/rpf_ranked_signal_rule_bank/20260623_234159_rank_signal_rule_bank/
  81 signals, 51 TP / 30 FP
  precision 0.630
  lift 1.710x
  FDR 0.370

UP transfer separator:
  run: test_output/rpf_ranked_signal_transfer_separator/20260624_163242_rank_signal_transfer_separator/
  strongest UP candidate separator:
    up_rocket_64_v1 score_mean
    direction: lower_good
    best candidate AUC: 0.770
```

UP current decision:

- current latest `up_none_v1` selected-router output is not useful;
- UP has prior usable evidence, but it was not included in the latest
  DOWN-focused row-rule replay;
- next UP work must explicitly include `up_rocket_64_v1`;
- UP needs its own context/rule diagnostic path, not reuse of the DOWN
  `rejection_chop` decision.

2026-06-28 dual-target tracking update:

```text
new doc:
  regression_feature_engineering/docs/rpf_dual_target_tracking.md

code update:
  rank_signal_router now supports:
    --row-rule-gate-output-mode active_candidate

purpose:
  allow UP and DOWN row-rule active specialist checks with the same mechanism.
```

Current dual-target contract:

```text
UP target:
  target_cls_extreme_up_ge_2x_down_hvol_v2
  required active candidate:
    up_rocket_64_v1
  first rule direction to test:
    lower_good

DOWN target:
  target_cls_extreme_down_ge_2x_up_hvol_v2
  required active candidate:
    down_rocket_16_diag_v1
  first rule direction to test:
    higher_good
  first blocked family:
    rejection_chop
```

The old `active_down_candidate` output mode remains available only for
historical reproduction. New dual-target work must use `active_candidate`.

Next commands are recorded in:

```text
regression_feature_engineering/docs/rpf_dual_target_tracking.md
```

Run order:

1. `120`-window smoke for UP and DOWN.
2. `960`-window latest and older non-overlapping replays for UP and DOWN.
3. Compare signal frequency, active days, precision, lift, and FDR for both
   sides before adding stricter filters.

2026-06-28 regime/change diagnostic implementation:

```text
new command:
  python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic

new plan doc:
  regression_feature_engineering/docs/rpf_regime_change_detection_plan.md
```

Purpose:

```text
diagnose whether ranked-signal quality is conditional on prediction-safe
latent regimes and change-risk alarms before changing router behavior
```

Implementation contract:

- consumes completed `rank_signal_router` runs;
- builds `regime_context.parquet` from safe context only;
- excludes current prediction outcomes from regime context;
- assigns regimes using prior windows only;
- uses `hmmlearn.GaussianHMM` if available;
- falls back to a chronological Gaussian-mixture Markov proxy when `hmmlearn`
  is unavailable;
- writes CUSUM/Page-Hinkley style change alarms from safe context features;
- writes current prediction outcomes only to analysis artifacts.

Artifacts:

```text
events.jsonl
stage_status.json
regime_diagnostic_config.json
regime_context.parquet
change_point_events.parquet
regime_signal_quality.parquet
hmm_state_metrics.parquet
regime_transfer_report.md
```

Local smoke completed:

```text
run:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_140527_rank_signal_regime_diagnostic/

input:
  test_output/rpf_ranked_signal_router/20260628_102938_rank_signal_router_btcusdt_8h_b/

side/candidate:
  up / up_rocket_64_v1

result:
  context rows:       960
  change events:      1644
  state metric rows:  2
```

Smoke state split:

```text
state 0:
  431 windows
  580 signals
  precision 0.426
  lift 1.114
  FDR 0.574

state 1:
  509 windows
  697 signals
  precision 0.387
  lift 1.052
  FDR 0.613
```

Interpretation:

- the command works on real router artifacts;
- the first UP smoke shows only modest state separation;
- this is not yet a promotion signal;
- next run should use the full UP/DOWN latest and older router blocks listed in
  `rpf_regime_change_detection_plan.md`;
- if states or change alarms do not materially separate precision/lift/FDR,
  the regime layer should not be promoted into the router.

Follow-up implementation correction:

```text
rank_signal_regime_diagnostic now sorts router input runs chronologically by
window_end_offset_steps before fitting past-only regime history.
```

Reason:

```text
offset 0 is the latest block and larger offsets are older blocks. Regime
history must use older blocks before latest blocks even if the CLI arguments
are pasted in a different order.
```

Corrected full UP/DOWN regime diagnostic:

```text
run:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_142013_rank_signal_regime_diagnostic/

model mode:
  gmm_markov

inputs:
  latest UP/DOWN 960-window router runs
  older UP/DOWN 960-window router runs

source order:
  offset 960 first
  offset 0 second
```

State quality summary:

```text
DOWN down_rocket_16_diag_v1:
  state 0: precision 0.365, lift 0.955, FDR 0.635
  state 1: precision 0.397, lift 1.035, FDR 0.603
  state 2: precision 0.399, lift 1.045, FDR 0.601

UP up_rocket_64_v1:
  state 0: precision 0.399, lift 1.122, FDR 0.601
  state 1: precision 0.434, lift 1.083, FDR 0.566
  state 2: precision 0.402, lift 0.988, FDR 0.598
```

Change-risk summary after Page-Hinkley reset-on-alarm fix:

```text
total change events:
  327

DOWN CUSUM windows:
  no CUSUM:  precision 0.396, lift 1.030, FDR 0.604
  CUSUM:     precision 0.351, lift 0.944, FDR 0.649

UP CUSUM windows:
  no CUSUM:  precision 0.414, lift 1.069, FDR 0.586
  CUSUM:     precision 0.441, lift 1.113, FDR 0.559

UP Page-Hinkley windows:
  no PH:     precision 0.418, lift 1.076, FDR 0.582
  PH:        precision 0.313, lift 0.885, FDR 0.688
```

Interpretation:

- latent state alone is not strong enough for router promotion;
- DOWN state `0` and DOWN CUSUM windows are risk contexts;
- UP state `2` and UP Page-Hinkley windows are risk contexts;
- CUSUM is side-specific: bad for DOWN, not bad for UP in this run;
- next work should create explicit `state+change` summary artifacts and then
  test a small regime-aware suppression rule, not a broad new model sweep.

2026-06-28 regime-target matching extension:

```text
updated command:
  python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic

new artifacts:
  regime_target_match.parquet
  regime_change_target_match.parquet
  change_risk_target_match.parquet
  regime_suppression_candidates.parquet

latest run:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_142856_rank_signal_regime_diagnostic/
```

Purpose:

```text
explicitly answer which regimes are favorable or dangerous for each target,
then use change-point context to avoid false positives
```

Result:

```text
favorable regime states:
  none under current thresholds

avoid regime states:
  DOWN state 0, state 1, state 2
  UP state 0, state 2

neutral regime states:
  UP state 1
```

Important nuance:

- `UP state 0` has lift `1.122`, but FDR is `0.601`, so it is not accepted as
  favorable under the current false-positive-focused rule.
- DOWN has no clean favorable state; all DOWN states remain too high-FDR or too
  close to base rate.
- UP legacy CUSUM-alias windows were labeled favorable in this historical run:

```text
UP + legacy has_cusum=true:
  143 signals
  precision 0.441
  lift 1.113
  FDR 0.559
```

Top suppression contexts:

```text
DOWN legacy has_cusum=true:
  202 signals
  lift 0.944
  FDR 0.649

DOWN state 0:
  901 signals
  lift 0.955
  FDR 0.635

UP state 2:
  859 signals
  lift 0.988
  FDR 0.598
```

Decision:

- regime matching is useful mainly for false-positive suppression so far;
- it does not yet identify broad high-quality target regimes;
- the next router experiment should be a shadow suppression replay:
  suppress DOWN in state `0` or explicit CUSUM detector windows, and suppress
  UP in state `2` and Page-Hinkley-risk windows;
- do not promote this into active routing until the shadow replay proves higher
  precision without collapsing signal frequency.

Important correction:

```text
has_cusum was a stale generic alias in the historical 2026-06-28 artifacts.
Clean HMM/CUSUM work must use explicit flags only:
has_market_context_zshift_v1, has_market_context_recursive_cusum_v1,
has_hmm_transition_cusum_v1, has_hmm_state_change_marker.
```

2026-06-28 regime suppression simulator:

```text
new command:
  python -m regression_feature_engineering.walkforward.rank_signal_regime_suppression_simulator

run:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_143451_rank_signal_regime_suppression_simulator/
```

Rule replayed:

```text
UP:
  suppress regime_state=2
  suppress has_page_hinkley=true

DOWN:
  suppress regime_state=0
  suppress legacy has_cusum=true
```

Overall result:

```text
DOWN:
  signals:   3015 -> 1977
  precision: 0.393 -> 0.408
  lift:      1.024 -> 1.064
  FDR:       0.607 -> 0.592
  FP reduction: 36.1%

UP:
  signals:   2678 -> 1777
  precision: 0.416 -> 0.427
  lift:      1.072 -> 1.100
  FDR:       0.584 -> 0.573
  FP reduction: 34.9%
```

Interpretation:

- suppression improves both sides, so regime/change-risk context is useful;
- improvement is modest, not a breakthrough;
- signal retention is about two thirds, so this is still a risk filter rather
  than a complete strategy;
- next work should compare stricter/looser suppression sets before adding this
  to `rank_signal_router`.

2026-06-28 market-regime context separation:

```text
updated command:
  python -m regression_feature_engineering.walkforward.rank_signal_regime_diagnostic

new mode:
  --regime-context-mode combined
```

Feature separation is now explicit:

```text
prediction/ranker:
  side-specific RPF panel
  -> train-only ElasticNet relevance selection
  -> optional causal sequence embeddings
  -> CatBoostRanker

regime detection:
  router/model context
  + prior-batch market-state aggregates from stable RPF families
  -> train-history-only scaler/PCA/HMM or GMM proxy

change-risk detection:
  small router context series
  + market aggregate shift/z-score series
  -> CUSUM/Page-Hinkley diagnostics
```

Default market-regime families:

```text
volatility_state
temporal_memory_transforms
regime_calendar_state
rejection_chop
liquidity_volume_pressure
structural_room
```

Important rule:

```text
Market-regime context excludes the current prediction batch by default.
It uses prior available batches only, so it can be replayed like a live
batch-start risk context instead of leaking full future-batch state.
```

2026-06-28 combined market-regime diagnostic:

```text
run:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_150140_rank_signal_regime_diagnostic/

context rows:        3,840
market rows:         3,840
change events:       12,479
state metric rows:   6
candidate sides:     UP and DOWN
favorable states:    0
avoid states:        3
```

Overall candidate quality before suppression:

```text
DOWN down_rocket_16_diag_v1:
  signals:   3,015
  precision: 0.393
  lift:      1.024
  FDR:       0.607

UP up_rocket_64_v1:
  signals:   2,678
  precision: 0.416
  lift:      1.072
  FDR:       0.584
```

State quality:

```text
DOWN:
  state 0: lift 1.023, FDR 0.606, weak avoid
  state 1: lift 0.971, FDR 0.637, strongest avoid
  state 2: lift 1.041, FDR 0.596, neutral

UP:
  state 0: lift 1.086, FDR 0.567, neutral
  state 1: lift 1.055, FDR 0.580, neutral
  state 2: lift 1.043, FDR 0.611, avoid
```

Important positive clue:

```text
UP has_any_change=false:
  signals:   352
  precision: 0.426
  lift:      1.137
  FDR:       0.574
```

This is the first useful UP-specific change-risk clue: UP quality is better in
quiet/no-change windows.

State-only suppression replay from the combined diagnostic:

```text
rule A:
  suppress UP state 2
  suppress DOWN state 1

DOWN:
  signals:   3,015 -> 2,073
  precision: 0.393 -> 0.406
  lift:      1.024 -> 1.059
  FDR:       0.607 -> 0.594
  retention: 68.8%

UP:
  signals:   2,678 -> 1,762
  precision: 0.416 -> 0.430
  lift:      1.072 -> 1.108
  FDR:       0.584 -> 0.570
  retention: 65.8%

rule B:
  suppress UP state 2
  suppress DOWN states 0,1

DOWN:
  signals:   3,015 -> 1,279
  precision: 0.393 -> 0.414
  lift:      1.024 -> 1.079
  FDR:       0.607 -> 0.586
  retention: 42.4%
```

Interpretation:

- combined market context improves suppression slightly versus router-only
  context, but still not enough for promotion;
- DOWN `state 1` is the cleaner avoid rule;
- DOWN `state 0` adds precision but removes too much coverage;
- UP `state 2` suppression is useful, and `has_any_change=false` should be
  tested as a positive allow-context rather than only suppression.

## Live-Style Regime Replay Fix

Status as of 2026-06-28:

```text
fixed:
  live_combined regime mode now builds and joins prior-market context
  live-safe regime context excludes current prediction-batch score summaries
  suppression simulator now supports prequential replay
  regime diagnostic supports regime model refit intervals for practical backtests

new tests:
  tests/test_rpf_rank_signal_regime_diagnostic.py
  tests/test_rpf_rank_signal_regime_suppression_simulator.py
```

Why this mattered:

```text
The previous static suppression replay was post-hoc. It could choose suppress
contexts from the same full span it evaluated. That is useful for diagnostics,
but it is not a live-style test.

The corrected prequential replay learns avoid contexts only from prior matured
windows, applies them to the current window, then matures the current outcome
afterward.
```

Corrected live-context diagnostic:

```text
run:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_175452_rank_signal_regime_diagnostic/

mode:
  regime_context_mode=live_combined
  live_safe_context=true
  market_context_rows=3,840
  model_mode=gmm_markov
  regime_refit_interval_windows=20
  market_regime_max_features_per_family=16
```

Corrected prequential suppression replay:

```text
run:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_175635_rank_signal_regime_suppression_simulator/

DOWN down_rocket_16_diag_v1:
  signals:   3,015 -> 641
  precision: 0.393 -> 0.441
  lift:      1.024 -> 1.151
  FDR:       0.607 -> 0.559
  retention: 21.3%

UP up_rocket_64_v1:
  signals:   2,678 -> 890
  precision: 0.416 -> 0.438
  lift:      1.072 -> 1.130
  FDR:       0.584 -> 0.562
  retention: 33.2%
```

Important interpretation:

- The corrected live-style replay does improve aggregate precision/lift and
  reduces false positives, so regime/change context is not useless.
- The cost is large signal loss; this is a risk filter, not yet a complete
  trading decision layer.
- UP remains mixed by chronological block: one block worsened after
  suppression, one block improved. UP needs side-specific allow contexts, not
  only avoid suppression.
- `live_combined` with `model_mode=auto` is too slow if it refits HMM every
  window. Use `--regime-refit-interval-windows` for backtests or
  `--model-mode gmm_markov` for fast iteration.

## Regime Replay Source Correction

Status as of 2026-06-28:

The previous regime suppression replay used `candidate_prediction_window_metrics`
by default. That artifact is a **shadow candidate** stream: it scores what a
candidate branch would have done independently. It is useful for diagnostics,
but it is not the actual live router-selected decision stream.

Implemented correction:

```text
rank_signal_regime_diagnostic:
  added --prediction-source candidate_shadow|router_selected|row_rule_active|effective_selected
  default is effective_selected
  new router runs write effective_window_metrics.parquet directly
  historical effective_selected uses row_rule_active when active row-rule output
  exists, otherwise router_selected
  candidate_shadow must be requested explicitly for branch diagnostics
  router_selected loads router_window_metrics.parquet
  row_rule_active loads row_rule_active_window_metrics.parquet
  router_selected preserves no-signal selected windows for the matching side
```

`rank_signal_router` now also writes:

```text
effective_prediction_scores.parquet
effective_decisions.parquet
effective_window_metrics.parquet
effective_block_summary.parquet
effective_side_summary.json
effective_artifact_source.json
```

These artifacts are the canonical selected stream for new runs.

Additional implementation corrections from the same audit:

```text
rank_signal_router:
  report.md now shows Effective Selected Summary before Base Router Summary
  writes effective_conflict_diagnostics.parquet

rank_signal_regime_diagnostic:
  regime_signal_quality.parquet preserves requested_prediction_source and
  resolved prediction_source
  GMM/HMM regime state IDs are canonicalized after each fit by train-cluster
  centroid order to reduce state-label permutation across refits

rank_signal_regime_suppression_simulator:
  prequential change-risk suppression ignores change_flag=False contexts
  regime suppression candidates exclude false change-flag contexts
```

Impact:

```text
old regime/suppression runs before these fixes are diagnostic history only;
rerun regime diagnostics before drawing new conclusions from regime/change
suppression.
```

Base router-selected live-stream diagnostic:

```text
diagnostic:
  test_output/rpf_ranked_signal_regime_diagnostic/20260628_192232_rank_signal_regime_diagnostic/

suppression:
  test_output/rpf_ranked_signal_regime_suppression_simulator/20260628_192425_rank_signal_regime_suppression_simulator/

prediction_source:
  router_selected
```

Base router-selected results:

```text
DOWN down_rocket_16_diag_v1:
  windows:   1,920
  signals:   29 -> 29
  precision: 0.207 -> 0.207
  lift:      0.540 -> 0.540
  FDR:       0.793 -> 0.793

UP up_rocket_64_v1:
  windows:   1,920
  signals:   21 -> 21
  precision: 0.333 -> 0.333
  lift:      0.860 -> 0.860
  FDR:       0.667 -> 0.667
```

Block-level base router-selected results:

```text
UP blocks:
  7 signals,  2 TP / 5 FP, precision 0.286, lift 0.761
  14 signals, 5 TP / 9 FP, precision 0.357, lift 0.892

DOWN blocks:
  24 signals, 6 TP / 18 FP, precision 0.250, lift 0.642
  5 signals,  0 TP / 5 FP,  precision 0.000, lift 0.000
```

Correct interpretation:

- the `3,015 -> 641` DOWN and `2,678 -> 890` UP replay was shadow-candidate
  evidence, not live router-selected evidence;
- base router-selected signals are extremely sparse and below the local base
  rate on both sides;
- however, the latest router runs also used `row_rule_gate_output_mode=active_candidate`.
  In those runs the effective active stream is `row_rule_active_*`, not
  `router_*`.

Effective active stream across the same four 960-window runs:

```text
UP row_rule_active:
  windows:   1,920
  signals:   206
  TP / FP:   87 / 119
  precision: 0.422
  base rate: 0.388
  lift:      1.089
  FDR:       0.578
  active-window rate: 0.061

DOWN row_rule_active:
  windows:   1,920
  signals:   204
  TP / FP:   95 / 109
  precision: 0.466
  base rate: 0.383
  lift:      1.214
  FDR:       0.534
  active-window rate: 0.043
```

Corrected conclusion:

- the base router/admission stream is broken;
- the row-rule active stream is the only current effective output that beats
  base rate, but precision and signal frequency are still too weak for
  promotion;
- future diagnostics must use `effective_selected` unless they intentionally
  compare a specific internal stream.

## RPF Clean Implementation Notebook

Added:

```text
notebooks/rpf_walkforward_control.ipynb
```

Purpose:

- keep one clean operational path from readiness to router evaluation;
- reject old router runs that do not write explicit `effective_*` artifacts;
- inspect only effective selected output as current selected performance;
- include executable readiness/router/HMM-regime/CUSUM-change diagnostic stages
  inside the notebook;
- launch heavy stages only when explicit run flags are enabled;
- keep historical classifier/gate/bank/suppression branches out of the active
  notebook.

Clean regime/change contract inside the notebook:

```text
router effective selected output for strategy-performance inspection
candidate-shadow output for regime/candidate research
-> HMM market-regime diagnostic
-> CUSUM-only change-point diagnostic
-> manual validation checklist
```

The notebook requires fresh regime artifacts created with:

```text
--prediction-source candidate_shadow
--model-mode hmm
--regime-context-mode market_context
--change-feature-set market_context
--change-detectors cusum
```

This keeps responsibilities separate:

```text
effective selected output = current strategy-performance table
candidate shadow output   = regime/candidate diagnostic table
market_context            = HMM/CUSUM input features
prediction outcomes       = matured analysis labels only
```

HMM context is built from prediction-time-safe prior RPF market aggregates.
The market HMM is assigned once per chronological prediction window and then
joined back to UP/DOWN candidate rows for outcome analysis. CUSUM is also run
once on market-context windows, then copied to candidate rows. Prediction
labels and current prediction outcomes remain output diagnostics, not HMM or
CUSUM inputs.

The notebook router stage now uses `--outer-window-count 240` so
`--regime-min-history-windows 80` can produce real HMM states. Short 40-window
diagnostics are plumbing smoke tests only.

The HMM implementation uses `hmmlearn` from the configured `$PY` environment.
The notebook checks that dependency before printing the Stage 3 command.

Heavy notebook execution is controlled by:

```text
RUN_FULL_WORKFLOW
RUN_READINESS
RUN_ROUTER
RUN_REGIME_DIAGNOSTIC
RUN_VALIDATION
RUN_WORKTREE_CHECK
```

When a heavy stage runs, the notebook streams the output in the cell and writes
a log under:

```text
test_output/rpf_walkforward_notebook_logs/
```

The notebook also includes HMM/CUSUM optimization checks after Stage 3:

```text
HMM coverage and state stability
HMM state market-feature profiles
CUSUM event frequency and feature triggers
CUSUM candidate-separation table
regime/CUSUM actionability summary
```

These checks answer whether the regime layer is capturing usable
prediction-time-safe market context. They do not promote a strategy by
themselves. Current strategy performance still comes only from the effective
selected router output.

The notebook is for fresh implementation work. Markdown docs remain the source
of truth for decisions and interpretation.

## 2026-07-01 HMM/CUSUM Research Lock

Research notes are now captured in:

```text
regression_feature_engineering/docs/rpf_hmm_cusum_ranker_research.md
```

Current decision:

```text
HMM = persistent market-context state detector.
CUSUM = sequential change-risk detector.
CatBoostRanker = row scorer.
Regime/change layer = selective router/gate, not a replacement predictor.
```

The current clean notebook HMM is directionally correct as a diagnostic:
train-only scaler/PCA/HMM, prior market-context inputs, one state per
chronological prediction window, no current prediction labels in inputs.

The current clean notebook change layer now separates three detector families:

```text
market_context_zshift_v1
market_context_recursive_cusum_v1
hmm_transition_cusum_v1
```

Detector artifacts must keep explicit detector names. Rows where both market
z-shift and recursive CUSUM fire are written as separate detector rows, not a
comma-joined detector. The notebook fails fast if stale mixed detector names are
loaded.

Latest corrected diagnostic run:

```text
test_output/rpf_ranked_signal_regime_diagnostic/20260701_012737_rank_signal_regime_diagnostic/
```

Validation result:

```text
change_point_events.parquet:
  market_context_zshift_v1             windows=90
  market_context_recursive_cusum_v1    windows=205

hmm_transition_events.parquet:
  hmm_transition_cusum_v1              windows=34

HMM state changes:
  total state-change windows                    26
  with market change alarm                      23
  with HMM-transition recursive CUSUM alarm      8
  with direct HMM state-change marker           26
```

The direct HMM state-change marker is an interpretation aid, not the same thing
as HMM-transition CUSUM. The notebook now reports them separately.

The next implementation should test whether these detectors reliably identify:

```text
market feature shocks before false positives
HMM posterior/entropy/transition instability before regime changes
```

Only after that should `regime_aware_router_v1` use the regime/change layer to
allow, suppress, or reduce signal budget for UP and DOWN candidates.

## 2026-07-01 HMM/CUSUM Correction Implementation

Implemented the research-backed correction in the active RPF notebook/module
path:

```text
notebooks/rpf_walkforward_control.ipynb
regression_feature_engineering/walkforward/rank_signal_regime_diagnostic.py
tests/test_rpf_rank_signal_regime_diagnostic.py
```

Clean regime runs now require:

```text
--prediction-source candidate_shadow
--regime-context-mode market_context
--model-mode hmm
--hmm-selection-mode bic_v1
--hmm-state-count-choices 2,3,4
--hmm-filter-mode causal_forward_v1
--change-feature-set market_context
--change-detectors market_context_zshift_v1,market_context_recursive_cusum_v1,hmm_transition_cusum_v1
--cusum-standardization rolling_robust_z_v1
--cusum-target-event-rate-min 0.05
--cusum-target-event-rate-max 0.25
```

Correction details:

- HMM filtering now uses the full prior train-window sequence plus the current
  market vector, then takes the final filtered posterior.
- HMM state count can be selected by BIC over `2,3,4`, with model-selection
  rows written for audit.
- HMM artifacts now include selected state count, likelihood/AIC/BIC, posterior
  entropy, transition matrix, expected state duration, and current observation
  likelihood.
- Recursive market CUSUM uses rolling prior-only robust z-score
  standardization by default.
- Recursive CUSUM calibration writes target event-rate metadata; current labels
  are not used for thresholding.
- Direct HMM state-change markers are written as `hmm_state_change_marker`;
  `hmm_transition_cusum_v1` is reserved for recursive CUSUM alarms over HMM
  posterior/transition-risk features.
- The notebook fails stale regime runs that miss new HMM/CUSUM artifacts or
  were generated with the old fixed-state/old-standardization contract.

New artifacts required by the notebook:

```text
hmm_filter_diagnostics.parquet
hmm_model_selection.parquet
hmm_transition_matrix.parquet
cusum_calibration.parquet
regime_input_features.parquet
regime_gate_context_metrics.parquet
regime_gate_decisions.parquet
```

2026-07-01 cleanup/fix lock:

```text
regime_input_features.parquet is now required and audits every candidate
market-context column as included or excluded.
```

Active HMM/CUSUM model inputs are restricted to prediction-safe market-context
features from approved market families. Meta/control/instrumentation columns
such as `market_context_last_batch_id`, lookback settings, row/feature counts,
finite-rate counters, labels, candidate outcomes, and router outcomes are
excluded before scaler/PCA/HMM/CUSUM fitting.

HMM state identity is now keyed by selected state count:

```text
regime_state_key = k{regime_selected_state_count}_s{regime_state}
```

State-level artifacts must group by `regime_state_key`, not raw
`regime_state`, because BIC-selected K=2/K=3/K=4 states are different latent
state spaces. HMM health fields now include self-transition probability,
expected duration, posterior confidence/entropy, and a degenerate-state flag.

Actionable CUSUM/change flags are explicit only:

```text
has_market_context_recursive_cusum_v1
has_hmm_transition_cusum_v1
```

Diagnostic/interpretable flags remain separate:

```text
has_market_context_zshift_v1
has_hmm_state_change_marker
```

The stale generic `has_cusum` alias must not appear in actionable target-match
or suppression artifacts. If it appears, the notebook treats the run as stale.

Regime gate simulation is now a prior-only replay. For each side/candidate and
window it learns context allow/suppress decisions only from prior matured
windows, then writes the current outcome after the decision. Tested context
keys include `regime_state_key`, recursive CUSUM, HMM-transition CUSUM, and
state+CUSUM combinations. The gate can only allow or suppress in this fix pass.

Router audit rows now carry per-candidate rejection fields:

```text
candidate_passed_validation
candidate_passed_reliability
candidate_passed_selection
candidate_rejected_reason
selected_candidate_name
selection_mode
```

If no branch is selected, no candidate row may claim
`candidate_passed_selection=True`. This is required to diagnose no-signal
windows without guessing whether validation, reliability, warmup, or history
blocked the candidate.

Notebook/state artifacts remain diagnostic until they show:

```text
no disallowed regime inputs
no mixed HMM state ids
recursive CUSUM event rate inside 5%..25%
gate replay improves lift for at least one UP and one DOWN branch
signal frequency remains practical
```

Validation passed for the code contract:

```text
python -m pytest tests/test_rpf_rank_signal_regime_diagnostic.py tests/test_rpf_rank_signal_router.py -q
python -m py_compile $(find regression_feature_engineering -name '*.py' -print)
python -m ruff check regression_feature_engineering/walkforward/rank_signal_regime_diagnostic.py tests/test_rpf_rank_signal_regime_diagnostic.py
git diff --check
```

Older regime diagnostic runs before this correction remain historical evidence
only. Rerun the notebook regime stage before drawing any new conclusion about
HMM/CUSUM gating quality.

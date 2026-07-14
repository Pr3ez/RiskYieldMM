# Analyst CUSUM meta-label candidate validation

Date: 2026-07-13
Tracking: Linear `RIS-262`
Status: **CANDIDATE ONLY — NOT PROMOTED — NOT PROFIT EVIDENCE**

## Result

The audited v2 pipeline successfully trained an L2-logistic secondary model for
the question `P(TP before failure and net positive | fresh causal CUSUM setup)`.
CUSUM still determines trade side; the secondary model cannot widen a stop,
increase size, block a protective exit, or route an order.

The pooled probability result is better than its causal training-prevalence
control, but the improvement is small and heterogeneous. It does not establish
a profitable strategy or justify an entry gate.

| Metric | v2 logistic | Causal base rate | Improvement |
| --- | ---: | ---: | ---: |
| OOF rows | 64,029 | 64,029 | — |
| Brier score | 0.129518 | 0.130772 | 0.001254 |
| Log loss | 0.426061 | 0.430811 | 0.004750 |
| PR-AUC | 0.198832 | 0.153624 | 1.285x prevalence lift |

Dataset: 65,096 mature events, 10,070 economic positives (15.47%), with
35,975 STOP, 10,110 TARGET, 18,961 TIMEOUT, and 50 AMBIGUOUS outcomes. The
evaluation used 128 fitted expanding-window folds.

## Immutable artifact

- Model version: `cusum-meta-logistic-all56-20260710-v2`
- Checksum: `25154c48fb042b61c73cd49bc1d1bb3a69da1982eb2a91bd4a570f7027c5a129`
- Local artifact: `models/analyst_cusum_meta/cusum-meta-logistic-all56-20260710-v2.artifact.json`
- Full machine report: `models/analyst_cusum_meta/cusum-meta-logistic-all56-20260710-v2.report.json`
- Human report: `models/analyst_cusum_meta/cusum-meta-logistic-all56-20260710-v2.report.md`

The model directory is intentionally git-ignored. The artifact declares:

```text
candidate_only=true
auto_promoted=false
walk_forward.deployment_eligible=false
deployment_scope.eligible_selections=[]
```

The shared runtime validator rejects it in `gate` mode for every selection.
It may be inspected only in historical/live shadow mode.

## Causal contract fixes completed before v2

- Explicit `online.available_at` and `cusum.available_at`, with
  `source <= available <= decision` enforced and persisted.
- Actual observation time in forward-paper labels; historical canonical replay
  is honestly identified as a nominal-close-plus-five-second scenario.
- A 24-hour historical label-maturity embargo inside every walk-forward fold.
- Timeout counted on accepted finalized bars in the selected timeframe.
- Final constituent-minute horizontal touches resolved before timeout.
- Immutable filled bracket ownership; later strategy reversals are suppressed.
- Entry execution cost embedded once, with only nonembedded cost deducted from
  the barrier result.
- Versionless/legacy persisted barrier payloads rejected fail-closed.
- Unknown minute paths cancel shadow labels. Protected replay reconciles flat
  at the next observed open and marks the performance path invalid rather than
  inventing TP/SL order.
- Candidate-only/unpromoted/broad-scope artifacts cannot bypass the central
  exact-selection deployment check through a direct replay call.

## Coverage boundary

Training rows by timeframe:

| Timeframe | Rows | Interpretation |
| --- | ---: | --- |
| 1m | 62,058 | Dominates the pooled result |
| 15m | 2,469 | Usable for research; subgroup support varies materially |
| 1h | 375 | Crypto only; subgroup performance is worse than base rate |
| 4h | 104 | Crypto only; too sparse and worse than base rate |
| 8h | 47 | Crypto only; far too sparse |
| 12h | 31 | Crypto only; far too sparse and worse than base rate |
| 1d | 12 | Crypto only; unusable and much worse than base rate |

All six provider-session assets have rows at 1m/15m, but zero at 1h and above.
The current `futures_session_observed` calendar is inferred from provider
timestamps; it cannot prove whether a missing interval was a scheduled closure
or an outage. V2 therefore rejects sparse target candles and resets/cancels
across those gaps. This is the correct fail-closed result. An authoritative
exchange calendar or journaled live source is required before higher-timeframe
session labels can be certified.

The pooled result is also not uniformly positive: EURUSD has worse subgroup
Brier than its causal base-rate control, while 1h, 4h, 12h, and 1d aggregate
subgroups are worse. No all-asset/all-timeframe edge is claimed.

## Historical-clock boundary

Canonical parquet does not store the historical time each bar or revision was
first observed. V2 uses a declared `nominal close + 5 seconds` scenario and a
24-hour fold embargo. This reduces leakage risk but does not recreate as-was
live information. Promotion evidence must come from append-only forward-paper
events containing actual `first_seen_at` and later matured labels.

## Next admissible experiment

1. Configure v2 for **shadow display only** and collect immutable predictions
   and labels without changing the baseline paper positions.
2. Require an untouched time holdout and per-selection minimum support.
3. Fit probability calibration on independent data and inspect reliability by
   asset/timeframe.
4. Compare identical primary events with and without the frozen probability
   rule after costs; include coverage, rejection rate, drawdown, and uncertainty.
5. Only then consider a separate paper-gated cohort. Real routing remains out
   of scope.

## Local live verification snapshot

The chart server was restarted on port `8765` with v2 configured for shadow
inspection. A fixed historical BTCUSDT/15m request loaded the artifact and
produced 124 candidate events, but all 124 scores were correctly unavailable
because those decisions predated `artifact.created_at`. A `gate` request
returned HTTP 400 with `artifact_candidate_only`. This proves the UI/API does
not retrospectively paint a newly trained score onto history.

The existing forward-paper process was deliberately not restarted or mutated.
At `2026-07-13T21:40:05Z` it was healthy on the append-only v2 baseline cohort,
but BTCUSDT/1m showed `-2.2407%` net return over 60 round trips versus
`-0.0139%` gross, with `2.2299%` of initial equity consumed by the normalized
fee/slippage assumptions. This is not a v2 meta-model result; it demonstrates
why reduced false positives and a new, isolated shadow cohort are necessary.
The current chart reports no forward meta-shadow events because that older
process was started without the new artifact and code contract.

No result in this document guarantees future profit.

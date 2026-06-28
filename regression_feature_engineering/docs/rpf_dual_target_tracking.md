# RPF Dual-Target Tracking

## Purpose

Keep UP and DOWN binary RPF signal research tracked together.

The active targets are:

```text
UP:   target_cls_extreme_up_ge_2x_down_hvol_v2
DOWN: target_cls_extreme_down_ge_2x_up_hvol_v2
```

The active model family remains:

```text
RPF features
-> train-only scaler
-> ElasticNet relevance selector
-> optional causal ROCKET sequence features
-> CatBoostRanker grouped by batch_id
-> live-safe timestamp-order decision policy
-> side-specific context / row-rule filter
```

## Current Decision

Do not run a DOWN-only row-rule experiment and call it a dual-target result.

The latest strict row-rule replay was useful for DOWN false-positive
suppression, but it did not cover UP correctly because it used:

```text
--row-rule-gate-output-mode active_down_candidate
--row-rule-gate-side down
--candidate-name-allowlist up_none_v1,down_rocket_16_diag_v1
```

That excluded `up_rocket_64_v1`, even though earlier UP evidence says it is the
stronger UP specialist candidate.

The router now supports a side-generic active output mode:

```text
--row-rule-gate-output-mode active_candidate
```

Use this for both UP and DOWN active specialist checks.

## Evidence Ledger

### UP

Useful historical UP evidence:

```text
small ROCKET UP ranked signal:
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
  candidate: up_rocket_64_v1
  feature: score_mean
  direction: lower_good
  best candidate AUC: 0.770
```

Current UP requirement:

```text
UP active checks must include up_rocket_64_v1.
up_none_v1 alone is not a valid UP optimization result.
```

### DOWN

Useful historical DOWN evidence:

```text
DOWN classifier holdout:
  run: test_output/rpf_clean_classification_optuna/20260618_031616_classification_classification_cls_extreme_down_ge_2x_up_hvo/
  precision 0.375
  lift 1.86
  signal count 421

DOWN ranked signal:
  run: test_output/rpf_ranked_signal/20260623_002707_rank_signal_btcusdt_8h_b_down/
  37 signals, 17 TP / 20 FP
  precision 0.459
  lift 2.274

DOWN strict row-rule specialist with rejection_chop blocked:
  runs:
    test_output/rpf_ranked_signal_router/20260628_045015_rank_signal_router_btcusdt_8h_b/
    test_output/rpf_ranked_signal_router/20260628_061237_rank_signal_router_btcusdt_8h_b/
    test_output/rpf_ranked_signal_router/20260628_073452_rank_signal_router_btcusdt_8h_b/
  combined:
    44 signals, 30 TP / 14 FP
    precision 0.682
    lift 1.784x
```

Current DOWN requirement:

```text
DOWN active checks should keep down_rocket_16_diag_v1.
The rejection_chop family remains blocked unless a new diagnostic reopens it.
```

## Trading-Frequency Reality Check

The latest 960-window run spans roughly:

```text
2025-06-21 to 2026-05-06
```

That is about 320 calendar days. A strategy targeting at least a couple trades
per week needs roughly:

```text
minimum useful diagnostic target: 90+ signals per 960-window span
better target:                   150-300 signals per 960-window span
```

Current strict DOWN row-rule output:

```text
38 signals in the latest 960-window span
```

So the current strict row-rule is a high-precision specialist, not a complete
trading strategy.

Future scoring must track:

```text
signals
active batches
active days
signals per week
silent week count
precision
precision lift versus local base rate
false discovery rate
decision cost per signal
```

## Required Run Discipline

Every active dual-target replay must record:

```text
readiness run
UP tabular panel
UP sequence panel
DOWN tabular panel
DOWN sequence panel
UP candidate(s)
DOWN candidate(s)
window count
window end offset
active output mode
row-rule directions/families
signal frequency
precision/lift/FDR
```

Do not compare runs as equivalent if any of these changed.

## Next Validation Commands

Run from repository root:

```bash
cd /media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM

export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
export READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
export UP_PANEL="$(ls -td test_output/rpf_feature_panels/*up_ge_2x_down*/selected_panel_160.json | head -1)"
export DOWN_PANEL="$(ls -td test_output/rpf_feature_panels/*down_ge_2x_up*/selected_panel_160.json | head -1)"
export UP_SEQ_PANEL="$(ls -td test_output/rpf_cnn_feature_diagnostics/*up_ge_2x_down*/selected_cnn_panel_160.json | head -1)"
export DOWN_SEQ_PANEL="$(ls -td test_output/rpf_cnn_feature_diagnostics/*down_ge_2x_up*/selected_cnn_panel_160.json | head -1)"

mkdir -p test_output/rpf_ranked_signal_router_logs

"$PY" - <<'PY'
from pathlib import Path
import os
import polars as pl

run = Path(os.environ["READINESS_RUN"])
windows = pl.read_parquet(run / "frozen_windows.parquet")
print("READINESS_RUN=", run)
print("windows=", windows.height)
print("pred_batch_id=", int(windows["pred_batch_id"].min()), int(windows["pred_batch_id"].max()))
if windows.height < 960:
    raise SystemExit("Need a readiness run with at least 960 windows")
PY
```

### Smoke: Both Targets, 120 Windows

Purpose:

```text
verify active_candidate works for UP and DOWN before long runs
```

Command:

```bash
for SIDE in up down
do
  if [ "$SIDE" = "up" ]; then
    CANDIDATE="up_rocket_64_v1"
    DIRECTIONS="lower_good"
    BLOCKED_FAMILIES=""
  else
    CANDIDATE="down_rocket_16_diag_v1"
    DIRECTIONS="higher_good"
    BLOCKED_FAMILIES="rejection_chop"
  fi

  "$PY" -m regression_feature_engineering.walkforward.rank_signal_router \
    --asset BTCUSDT \
    --root 8h/B \
    --base-run "$READINESS_RUN" \
    --up-tabular-panel-path "$UP_PANEL" \
    --up-sequence-panel-path "$UP_SEQ_PANEL" \
    --down-tabular-panel-path "$DOWN_PANEL" \
    --down-sequence-panel-path "$DOWN_SEQ_PANEL" \
    --candidate-set pruned_reliability_v1 \
    --candidate-name-allowlist "$CANDIDATE" \
    --selection-mode prequential_reliability_v1 \
    --outer-window-count 120 \
    --evaluation-block-size 60 \
    --task-type CPU \
    --thread-count 8 \
    --write-candidate-prediction-scores \
    --row-rule-gate-mode prequential_reliability_v1 \
    --row-rule-gate-output-mode active_candidate \
    --row-rule-gate-side "$SIDE" \
    --row-rule-gate-candidate-name "$CANDIDATE" \
    --row-rule-gate-block-size 60 \
    --row-rule-gate-allowed-directions "$DIRECTIONS" \
    --row-rule-gate-blocked-families "$BLOCKED_FAMILIES" \
    --row-rule-gate-reliability-lookback-folds 3 \
    --row-rule-gate-reliability-min-history-folds 1 \
    --row-rule-gate-reliability-min-signals 5 \
    --row-rule-gate-reliability-min-precision-lcb 0.40 \
    --row-rule-gate-reliability-max-fdr 0.50 \
    --log-every-windows 20 \
    2>&1 | tee "test_output/rpf_ranked_signal_router_logs/${SIDE}_active_candidate_smoke_120.log"
done
```

### Main Replay: Latest And Older Non-Overlapping Slices

Purpose:

```text
measure UP and DOWN active specialists over two non-overlapping 960-window spans
```

Command:

```bash
for OFFSET in 0 960
do
  for SIDE in up down
  do
    if [ "$SIDE" = "up" ]; then
      CANDIDATE="up_rocket_64_v1"
      DIRECTIONS="lower_good"
      BLOCKED_FAMILIES=""
    else
      CANDIDATE="down_rocket_16_diag_v1"
      DIRECTIONS="higher_good"
      BLOCKED_FAMILIES="rejection_chop"
    fi

    "$PY" -m regression_feature_engineering.walkforward.rank_signal_router \
      --asset BTCUSDT \
      --root 8h/B \
      --base-run "$READINESS_RUN" \
      --up-tabular-panel-path "$UP_PANEL" \
      --up-sequence-panel-path "$UP_SEQ_PANEL" \
      --down-tabular-panel-path "$DOWN_PANEL" \
      --down-sequence-panel-path "$DOWN_SEQ_PANEL" \
      --candidate-set pruned_reliability_v1 \
      --candidate-name-allowlist "$CANDIDATE" \
      --selection-mode prequential_reliability_v1 \
      --outer-window-count 960 \
      --window-end-offset-steps "$OFFSET" \
      --evaluation-block-size 60 \
      --task-type CPU \
      --thread-count 8 \
      --write-candidate-prediction-scores \
      --row-rule-gate-mode prequential_reliability_v1 \
      --row-rule-gate-output-mode active_candidate \
      --row-rule-gate-side "$SIDE" \
      --row-rule-gate-candidate-name "$CANDIDATE" \
      --row-rule-gate-block-size 60 \
      --row-rule-gate-allowed-directions "$DIRECTIONS" \
      --row-rule-gate-blocked-families "$BLOCKED_FAMILIES" \
      --row-rule-gate-reliability-lookback-folds 3 \
      --row-rule-gate-reliability-min-history-folds 1 \
      --row-rule-gate-reliability-min-signals 5 \
      --row-rule-gate-reliability-min-precision-lcb 0.40 \
      --row-rule-gate-reliability-max-fdr 0.50 \
      --log-every-windows 60 \
      2>&1 | tee "test_output/rpf_ranked_signal_router_logs/${SIDE}_active_candidate_offset${OFFSET}_960.log"
  done
done
```

### Summary After Runs

```bash
"$PY" - <<'PY'
from pathlib import Path
import json

runs = sorted(
    Path("test_output/rpf_ranked_signal_router").glob("*rank_signal_router_btcusdt_8h_b"),
    key=lambda p: p.stat().st_mtime,
    reverse=True,
)[:8]

for run in reversed(runs):
    cfg = json.loads((run / "router_config.json").read_text())
    side = (cfg.get("row_rule_gate") or {}).get("side")
    candidate = (cfg.get("row_rule_gate") or {}).get("candidate_name")
    offset = cfg.get("window_end_offset_steps")
    summary_path = run / "row_rule_active_side_summary.json"
    if not summary_path.exists():
        continue
    summary = json.loads(summary_path.read_text()).get(side, {})
    print()
    print(run)
    print("offset=", offset, "side=", side, "candidate=", candidate)
    print("signals=", summary.get("predicted_positive_count"))
    print("tp/fp=", summary.get("true_positive_count"), summary.get("false_positive_count"))
    print("precision=", summary.get("precision"))
    print("lift=", summary.get("precision_lift"))
    print("fdr=", summary.get("false_discovery_rate"))
    print("active_window_rate=", summary.get("active_window_rate"))
PY
```

## Acceptance

This pass is useful only if it answers all of these:

```text
Does UP still show edge when up_rocket_64_v1 is restored?
Does DOWN keep precision when rejection_chop is blocked?
How many signals per 960-window span does each side produce?
Are signals clustered or frequent enough to support a real trading workflow?
Does either side beat local base rate on both latest and older spans?
```

If both sides remain too sparse, the next implementation must optimize for a
minimum coverage contract instead of adding stricter filters.

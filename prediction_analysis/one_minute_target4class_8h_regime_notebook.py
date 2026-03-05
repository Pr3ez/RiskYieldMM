#%%
"""Notebook-style analysis for 8h regime pipeline (1m/target_4class).

Open this file in VS Code/Jupyter-compatible editor and run cell-by-cell.
It keeps pipeline execution and artifact review in one place.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from IPython.display import display as ipy_display
except Exception:
    ipy_display = None


#%%
# Configuration
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "prediction_analysis" / "one_minute_target4class_8h_regime_pipeline.py"
OUTPUT_BASE = PROJECT_ROOT / "prediction_analysis" / "one_minute_target4class_8h_regime_outputs"

RUN_PIPELINE = False
RUN_HORIZON_SWEEP = False
OUTPUT_TAG = "notebook_run"
OUTPUT_TAG_PREFIX = "notebook_h"

# Data scope
BATCHES_TAIL = 3600
HOLDOUT_BATCHES = 500
TREND_HORIZON_STEPS = 1
WF_GAP_STEPS = 1
LOOKBACK_GRID = "21,90,270,540,all"
WF_RETRAIN_EVERY = 1
METHODS = "rule_threshold_v1,gmm3_state_mapper,hmm3_state_mapper,supervised_3class_v1,two_head_bull_bear_v1"
THRESHOLD_GRID = "0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85,0.90"
HORIZON_SWEEP = [1, 2, 3, 4, 6, 9, 12, 21]

# Optional tracking metadata for new runs
LINEAR_ISSUE_URL = ""
NOTION_PAGE_URL = ""


#%%
def run_pipeline(output_tag: str | None = None, horizon_steps: int | None = None) -> Path:
    """Execute the CLI pipeline and return output run directory path."""
    tag = OUTPUT_TAG if output_tag is None else output_tag
    horizon = TREND_HORIZON_STEPS if horizon_steps is None else int(horizon_steps)
    cmd = [
        "python",
        str(SCRIPT_PATH),
        "--project-root",
        str(PROJECT_ROOT),
        "--batches-tail",
        str(BATCHES_TAIL),
        "--holdout-batches",
        str(HOLDOUT_BATCHES),
        "--trend-horizon-steps",
        str(horizon),
        "--wf-gap-steps",
        str(max(WF_GAP_STEPS, horizon)),
        "--lookback-grid",
        LOOKBACK_GRID,
        "--wf-retrain-every",
        str(WF_RETRAIN_EVERY),
        "--methods",
        METHODS,
        "--direction-threshold-grid",
        THRESHOLD_GRID,
        "--output-tag",
        tag,
        "--verbose",
    ]

    if LINEAR_ISSUE_URL.strip():
        cmd.extend(["--linear-issue-url", LINEAR_ISSUE_URL.strip()])
    if NOTION_PAGE_URL.strip():
        cmd.extend(["--notion-page-url", NOTION_PAGE_URL.strip()])

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)

    runs = sorted(OUTPUT_BASE.glob(f"*_{tag}"))
    if not runs:
        raise FileNotFoundError(f"No run found under {OUTPUT_BASE} for tag={tag}")
    return runs[-1]


def latest_run_path() -> Path:
    runs = sorted([p for p in OUTPUT_BASE.iterdir() if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs found in {OUTPUT_BASE}")
    return runs[-1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def show_table(df: pd.DataFrame) -> None:
    if ipy_display is not None:
        ipy_display(df)
    else:
        print(df.to_string(index=False))


#%%
# Optional execution cell
if RUN_PIPELINE:
    RUN_DIR = run_pipeline()
else:
    RUN_DIR = latest_run_path()

print("Using run:", RUN_DIR)


#%%
# Optional horizon sweep cell (runs pipeline once per horizon and summarizes)
if RUN_HORIZON_SWEEP:
    sweep_rows: list[dict[str, Any]] = []
    for h in HORIZON_SWEEP:
        tag = f"{OUTPUT_TAG_PREFIX}{h}"
        run_dir = run_pipeline(output_tag=tag, horizon_steps=h)
        summary_h = load_json(run_dir / "summary.json")
        holdout_h = summary_h.get("holdout_metrics", {})
        sweep_rows.append(
            {
                "horizon_8h_steps": h,
                "run_dir": str(run_dir),
                "status": summary_h.get("status"),
                "safe_accuracy": holdout_h.get("directional_active_safe_accuracy"),
                "coverage": holdout_h.get("coverage"),
                "active_batches": holdout_h.get("active_batches"),
                "opposite_fp_rate_active": holdout_h.get("opposite_fp_rate_active"),
                "batches_per_signal": holdout_h.get("batches_per_signal"),
            }
        )
    sweep_df = pd.DataFrame(sweep_rows).sort_values(["safe_accuracy", "coverage"], ascending=[False, False])
    show_table(sweep_df)


#%%
# Load artifacts
summary = load_json(RUN_DIR / "summary.json")
contract = load_json(RUN_DIR / "dataset_contract.json")
leakage = load_json(RUN_DIR / "leakage_guard_report.json")
final_op = load_json(RUN_DIR / "final_operating_point.json")
holdout = load_json(RUN_DIR / "holdout_metrics.json")

method_grid = pd.read_csv(RUN_DIR / "method_grid_results.csv")
regime_pred = pd.read_parquet(RUN_DIR / "regime_predictions_by_batch.parquet")
aligned = pd.read_parquet(RUN_DIR / "aligned_batch_dataset.parquet")

print("Summary status:", summary.get("status"))
print("Contract pass:", contract.get("pass"))
print("Leakage pass:", leakage.get("global", {}).get("pass"))


#%%
# High-level run summary
print("\nSelected operating point:")
print(json.dumps(final_op.get("selected", {}), indent=2))

print("\nHoldout metrics:")
for key in [
    "holdout_batches",
    "active_batches",
    "coverage",
    "directional_active_safe_accuracy",
    "opposite_fp_rate_active",
    "opposite_fp_rate_covered",
    "batches_per_signal",
    "trend_horizon_steps",
    "effective_gap_steps",
    "truth_label_col",
    "p_up_given_bull",
    "p_down_given_bear",
    "regime_coverage_bull",
    "regime_coverage_bear",
    "regime_coverage_chop",
]:
    print(f"{key}: {holdout.get(key)}")


#%%
# Method leaderboard
leader_cols = [
    "method",
    "lookback",
    "threshold",
    "directional_active_safe_accuracy",
    "coverage",
    "active_batches",
    "opposite_fp_rate_active",
    "opposite_fp_rate_covered",
    "feasible",
]

safe_top = method_grid.sort_values(
    ["directional_active_safe_accuracy", "coverage"],
    ascending=[False, False],
)[leader_cols].head(15)

coverage_top = method_grid.sort_values(
    ["coverage", "directional_active_safe_accuracy"],
    ascending=[False, False],
)[leader_cols].head(15)

print("Top by safe accuracy")
show_table(safe_top)

print("Top by coverage")
show_table(coverage_top)


#%%
# Per-method best rows
best_rows = []
for method_name, g in method_grid.groupby("method"):
    row = g.sort_values(
        ["directional_active_safe_accuracy", "coverage"],
        ascending=[False, False],
    ).head(1)
    best_rows.append(row)

best_by_method = pd.concat(best_rows, ignore_index=True)[leader_cols].sort_values("method")
print("Best row per method")
show_table(best_by_method)


#%%
# OHLC audit: compare predicted regime/signal vs actual future 8h close direction
# This checks alignment to actual price movement.
a8 = pd.read_parquet(PROJECT_ROOT / "data" / "analysis_8h.parquet", columns=["timestamp", "RAW_close"])
a8 = a8.sort_values("timestamp").reset_index(drop=True)
h = int(holdout.get("trend_horizon_steps", TREND_HORIZON_STEPS))
a8["next_close"] = a8["RAW_close"].shift(-h)
a8["close_dir"] = np.where(
    a8["next_close"] > a8["RAW_close"],
    1,
    np.where(a8["next_close"] < a8["RAW_close"], 0, np.nan),
)

audit = regime_pred.merge(
    a8[["timestamp", "close_dir"]],
    left_on="batch_start_ts_utc",
    right_on="timestamp",
    how="left",
)

audit_h = audit[(audit["is_holdout"] == True) & (audit["close_dir"].isin([0, 1]))].copy()

print("Holdout rows for OHLC audit:", len(audit_h))
print(f"OHLC audit horizon (8h steps): {h}")
for reg in ["bull", "bear", "chop"]:
    sub = audit_h[audit_h["regime_pred"] == reg]
    if len(sub) == 0:
        continue
    up = (sub["close_dir"] == 1).mean()
    down = (sub["close_dir"] == 0).mean()
    print(f"{reg}: n={len(sub)} up_share={up:.4f} down_share={down:.4f}")

act = audit_h[audit_h["is_active"] == True]
if len(act) > 0:
    acc = (act["signal_dir"] == act["close_dir"]).mean()
    opp = (act["signal_dir"] != act["close_dir"]).mean()
    cov = len(act) / len(audit_h)
    cadence = len(audit_h) / len(act)
    print(f"active_accuracy_vs_close={acc:.4f}")
    print(f"active_opp_rate_vs_close={opp:.4f}")
    print(f"active_coverage={cov:.4f}")
    print(f"cadence_batches_per_signal={cadence:.4f}")
else:
    print("No active rows in holdout")


#%%
# Save a compact markdown snapshot next to run artifacts
report_path = RUN_DIR / "notebook_review_summary.md"
lines = []
lines.append("# Notebook Review Summary")
lines.append("")
lines.append(f"- Run: `{RUN_DIR}`")
lines.append(f"- Status: `{summary.get('status')}`")
lines.append(f"- Selected: `{final_op.get('selected', {})}`")
lines.append("")
lines.append("## Holdout")
for key in [
    "holdout_batches",
    "active_batches",
    "coverage",
    "directional_active_safe_accuracy",
    "opposite_fp_rate_active",
    "opposite_fp_rate_covered",
    "batches_per_signal",
    "trend_horizon_steps",
    "effective_gap_steps",
    "truth_label_col",
]:
    lines.append(f"- {key}: {holdout.get(key)}")

report_path.write_text("\n".join(lines), encoding="utf-8")
print("Wrote:", report_path)

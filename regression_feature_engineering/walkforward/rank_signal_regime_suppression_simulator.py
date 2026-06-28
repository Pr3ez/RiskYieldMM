"""Offline regime/change-risk suppression replay for ranked-signal diagnostics.

This command consumes a completed ``rank_signal_regime_diagnostic`` run and
simulates window-level suppression rules.  It does not retrain the ranker and
does not change router behavior.  Its purpose is to test whether regime/change
contexts are useful false-positive filters before implementing a live router
mode.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_regime_diagnostic import change_flags_by_window
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import markdown_value
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_regime_suppression_simulator"


def main() -> int:
    args = parse_args()
    regime_run = Path(args.regime_run)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_regime_suppression_simulator")

    windows = build_suppression_windows(
        regime_run,
        up_states=parse_int_set(args.suppress_up_states),
        down_states=parse_int_set(args.suppress_down_states),
        up_change_flags=parse_name_set(args.suppress_up_change_flags),
        down_change_flags=parse_name_set(args.suppress_down_change_flags),
    )
    summary = suppression_summary(windows)

    write_rows_parquet(run_root / "suppression_window_metrics.parquet", windows.to_dicts())
    write_rows_parquet(run_root / "suppression_summary.parquet", summary.to_dicts())
    write_suppression_report(run_root / "suppression_report.md", regime_run=regime_run, summary=summary)
    write_json(
        run_root / "suppression_simulator_config.json",
        {
            "regime_run": str(regime_run),
            "suppress_up_states": sorted(parse_int_set(args.suppress_up_states)),
            "suppress_down_states": sorted(parse_int_set(args.suppress_down_states)),
            "suppress_up_change_flags": sorted(parse_name_set(args.suppress_up_change_flags)),
            "suppress_down_change_flags": sorted(parse_name_set(args.suppress_down_change_flags)),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_regime_suppression_simulator",
        status="complete",
        summary={
            "window_rows": windows.height,
            "summary_rows": summary.height,
            "suppressed_windows": int(windows["suppressed"].sum()) if "suppressed" in windows.columns else 0,
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-regime-suppress] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay regime/change-risk suppression rules offline.")
    parser.add_argument("--regime-run", required=True)
    parser.add_argument("--suppress-up-states", default="2")
    parser.add_argument("--suppress-down-states", default="0")
    parser.add_argument("--suppress-up-change-flags", default="has_page_hinkley")
    parser.add_argument("--suppress-down-change-flags", default="has_cusum")
    return parser.parse_args()


def parse_int_set(value: str | None) -> set[int]:
    out: set[int] = set()
    for item in str(value or "").split(","):
        item = item.strip()
        if item:
            out.add(int(item))
    return out


def parse_name_set(value: str | None) -> set[str]:
    return {item.strip() for item in str(value or "").split(",") if item.strip()}


def build_suppression_windows(
    regime_run: Path,
    *,
    up_states: set[int],
    down_states: set[int],
    up_change_flags: set[str],
    down_change_flags: set[str],
) -> pl.DataFrame:
    quality_path = regime_run / "regime_signal_quality.parquet"
    changes_path = regime_run / "change_point_events.parquet"
    if not quality_path.exists():
        raise FileNotFoundError(f"Missing regime quality artifact: {quality_path}")
    quality = pl.read_parquet(quality_path)
    changes = pl.read_parquet(changes_path) if changes_path.exists() else pl.DataFrame()
    flags = change_flags_by_window(changes)
    joined = join_change_flags(quality, flags)
    rows = [
        suppression_window_row(
            row,
            up_states=up_states,
            down_states=down_states,
            up_change_flags=up_change_flags,
            down_change_flags=down_change_flags,
        )
        for row in joined.to_dicts()
    ]
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def join_change_flags(quality: pl.DataFrame, flags: pl.DataFrame) -> pl.DataFrame:
    if flags.is_empty():
        return quality.with_columns(
            pl.lit(0).alias("change_event_count"),
            pl.lit(0).alias("cusum_count"),
            pl.lit(0).alias("page_hinkley_count"),
            pl.lit(False).alias("has_any_change"),
            pl.lit(False).alias("has_cusum"),
            pl.lit(False).alias("has_page_hinkley"),
        )
    join_keys = [
        col
        for col in ["source_run", "side", "candidate_name", "step_idx", "pred_batch_id"]
        if col in quality.columns and col in flags.columns
    ]
    return (
        quality.join(flags, on=join_keys, how="left")
        .with_columns(
            pl.col("change_event_count").fill_null(0),
            pl.col("cusum_count").fill_null(0),
            pl.col("page_hinkley_count").fill_null(0),
            pl.col("has_any_change").fill_null(False),
            pl.col("has_cusum").fill_null(False),
            pl.col("has_page_hinkley").fill_null(False),
        )
    )


def suppression_window_row(
    row: dict[str, Any],
    *,
    up_states: set[int],
    down_states: set[int],
    up_change_flags: set[str],
    down_change_flags: set[str],
) -> dict[str, Any]:
    side = str(row.get("side"))
    regime_state = row.get("regime_state")
    state = int(regime_state) if regime_state is not None else None
    state_rules = up_states if side == "up" else down_states
    change_rules = up_change_flags if side == "up" else down_change_flags

    reasons: list[str] = []
    if state is not None and state in state_rules:
        reasons.append(f"regime_state={state}")
    for flag in sorted(change_rules):
        if bool(row.get(flag)):
            reasons.append(f"{flag}=true")
    suppressed = bool(reasons)

    signals_before = int(row.get("predicted_positive_count") or 0)
    tp_before = int(row.get("true_positive_count") or 0)
    fp_before = int(row.get("false_positive_count") or 0)
    signals_after = 0 if suppressed else signals_before
    tp_after = 0 if suppressed else tp_before
    fp_after = 0 if suppressed else fp_before
    out = dict(row)
    out.update(
        {
            "suppressed": suppressed,
            "suppression_reason": ",".join(reasons),
            "predicted_positive_count_before": signals_before,
            "true_positive_count_before": tp_before,
            "false_positive_count_before": fp_before,
            "predicted_positive_count_after": signals_after,
            "true_positive_count_after": tp_after,
            "false_positive_count_after": fp_after,
            "suppressed_signal_count": signals_before if suppressed else 0,
            "suppressed_true_positive_count": tp_before if suppressed else 0,
            "suppressed_false_positive_count": fp_before if suppressed else 0,
            "active_window_after": signals_after > 0,
        }
    )
    return out


def suppression_summary(windows: pl.DataFrame) -> pl.DataFrame:
    if windows.is_empty():
        return pl.DataFrame()
    overall = aggregate(windows, group_cols=["side", "candidate_name"]).with_columns(pl.lit("overall").alias("scope"))
    by_run = aggregate(windows, group_cols=["source_run", "side", "candidate_name"]).with_columns(
        pl.lit("source_run").alias("scope")
    )
    return pl.concat([overall, by_run], how="diagonal_relaxed").sort(
        ["scope", "side", "candidate_name", "source_run"], nulls_last=True
    )


def aggregate(windows: pl.DataFrame, *, group_cols: list[str]) -> pl.DataFrame:
    grouped = (
        windows.group_by(group_cols)
        .agg(
            pl.len().alias("windows"),
            pl.col("suppressed").sum().alias("suppressed_windows"),
            pl.col("rows").fill_null(0).sum().alias("rows"),
            pl.col("positive_count").fill_null(0).sum().alias("positives"),
            pl.col("predicted_positive_count_before").sum().alias("signals_before"),
            pl.col("true_positive_count_before").sum().alias("tp_before"),
            pl.col("false_positive_count_before").sum().alias("fp_before"),
            pl.col("predicted_positive_count_after").sum().alias("signals_after"),
            pl.col("true_positive_count_after").sum().alias("tp_after"),
            pl.col("false_positive_count_after").sum().alias("fp_after"),
            pl.col("suppressed_signal_count").sum().alias("suppressed_signals"),
            pl.col("suppressed_true_positive_count").sum().alias("suppressed_tp"),
            pl.col("suppressed_false_positive_count").sum().alias("suppressed_fp"),
        )
        .with_columns(
            (pl.col("tp_before") / pl.col("signals_before")).alias("precision_before"),
            (pl.col("fp_before") / pl.col("signals_before")).alias("fdr_before"),
            (pl.col("tp_after") / pl.col("signals_after")).alias("precision_after"),
            (pl.col("fp_after") / pl.col("signals_after")).alias("fdr_after"),
            (pl.col("positives") / pl.col("rows")).alias("base_rate"),
            ((pl.col("tp_before") / pl.col("signals_before")) / (pl.col("positives") / pl.col("rows"))).alias(
                "lift_before"
            ),
            ((pl.col("tp_after") / pl.col("signals_after")) / (pl.col("positives") / pl.col("rows"))).alias(
                "lift_after"
            ),
            (pl.col("signals_after") / pl.col("signals_before")).alias("signal_retention"),
            (pl.col("tp_after") / pl.col("tp_before")).alias("tp_retention"),
            (1.0 - (pl.col("fp_after") / pl.col("fp_before"))).alias("fp_reduction"),
            (pl.col("suppressed_windows") / pl.col("windows")).alias("suppressed_window_rate"),
        )
    )
    return grouped


def write_suppression_report(path: Path, *, regime_run: Path, summary: pl.DataFrame) -> None:
    lines = [
        "# RPF Regime Suppression Simulator",
        "",
        "## Purpose",
        "",
        "Offline replay of regime/change-risk suppression rules. This does not change router decisions.",
        "",
        f"- regime diagnostic run: `{regime_run}`",
        "",
        "## Summary",
        "",
        "| Scope | Side | Candidate | Windows | Suppressed | Signals Before | Signals After | Precision Before | Precision After | Lift Before | Lift After | FDR Before | FDR After | FP Reduction |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.to_dicts():
        lines.append(
            "| {scope} | {side} | {candidate_name} | {windows} | {suppressed_windows} | "
            "{signals_before} | {signals_after} | {precision_before} | {precision_after} | "
            "{lift_before} | {lift_after} | {fdr_before} | {fdr_after} | {fp_reduction} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Useful suppression should raise precision/lift and reduce FDR without collapsing signals.",
            "- If signal retention is too low, this is a risk filter only, not a complete trading workflow.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_regime_suppression_simulator"


if __name__ == "__main__":
    raise SystemExit(main())

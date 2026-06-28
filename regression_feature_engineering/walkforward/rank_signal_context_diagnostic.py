"""Safe-context diagnostics for row-rule ranked-signal router blocks.

This command consumes completed ``rank_signal_router`` runs and builds two
separate tables:

* ``context_rows.parquet`` contains only information available before the
  evaluated block matures.
* ``specialist_block_outcomes.parquet`` contains post-hoc outcomes used only to
  label good and bad blocks.

The goal is to explain why a row-rule specialist transfers in some
chronological blocks and fails in others without leaking current prediction
labels into the future router input space.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_row_rule_bank import row_rule_feature_family
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import markdown_value
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_context_diagnostic"

OUTCOME_COLUMNS = {
    "rows",
    "positive_count",
    "negative_count",
    "predicted_positive_count",
    "true_positive_count",
    "false_positive_count",
    "false_negative_count",
    "true_negative_count",
    "precision",
    "recall",
    "false_positive_rate",
    "false_discovery_rate",
    "predicted_positive_rate",
    "base_positive_rate",
    "precision_lift",
    "decision_cost",
    "decision_cost_per_row",
    "decision_cost_per_signal",
    "active_window_rate",
    "zero_signal_window_rate",
    "high_target_window_count",
    "high_target_window_capture_rate",
    "missed_high_target_window_rate",
    "high_false_positive_window_rate",
    "ranked_signal_quality",
    "raw_signals",
    "raw_tp",
    "raw_fp",
    "raw_precision",
    "raw_false_discovery_rate",
    "precision_lift_vs_raw",
    "signal_retention_vs_raw",
    "tp_retention_vs_raw",
    "fp_retention_vs_raw",
    "active_block",
    "good_block",
    "bad_block",
    "block_label",
    "block_label_reason",
}

SAFE_CONTEXT_COLUMNS = [
    "source_run",
    "source_block",
    "window_end_offset_steps",
    "outer_window_count",
    "selection_mode",
    "candidate_set",
    "row_rule_gate_mode",
    "row_rule_gate_output_mode",
    "row_rule_gate_side",
    "row_rule_gate_candidate_name",
    "row_rule_gate_block_size",
    "row_rule_gate_key",
    "row_rule_gate_allowed_directions",
    "row_rule_gate_rule_selection_score",
    "row_rule_gate_max_rules_per_candidate",
    "row_rule_gate_reliability_min_history_folds",
    "row_rule_gate_reliability_min_signals",
    "row_rule_gate_reliability_min_precision_lcb",
    "row_rule_gate_reliability_max_false_discovery_rate",
    "row_rule_gate_reliability_lookback_folds",
    "side",
    "candidate_name",
    "block_idx",
    "test_block",
    "pred_batch_start",
    "pred_batch_end",
    "selected_rule_count",
    "feature",
    "feature_family",
    "direction",
    "threshold",
    "train_rows",
    "train_accepted_rows",
    "train_tp",
    "train_fp",
    "train_precision",
    "train_base_precision",
    "train_lift",
    "train_false_discovery_rate",
    "train_precision_lcb",
    "train_accepted_rate",
    "rule_score",
    "feature_auc",
    "feature_auc_abs",
    "feature_auc_direction",
    "direction_agreement",
    "directional_lcb_score",
    "row_rule_selection_mode",
    "selection_score",
    "selection_reject_reasons",
    "reliability_key_mode",
    "reliability_history_folds",
    "reliability_signals",
    "reliability_tp",
    "reliability_fp",
    "reliability_precision",
    "reliability_precision_lcb",
    "reliability_false_discovery_rate",
    "reliability_score",
    "reliability_feature_family",
    "selected_feature_count_mean",
    "raw_signal_context_available",
]


def main() -> int:
    args = parse_args()
    router_runs = tuple(Path(item) for item in args.router_run)
    if not router_runs:
        raise ValueError("At least one --router-run is required")

    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_context_diagnostic")

    context, outcomes, comparison = build_context_diagnostic(
        router_runs=router_runs,
        side=str(args.side),
        candidate_name=str(args.candidate_name),
        include_zero_signal_blocks=bool(args.include_zero_signal_blocks),
        good_min_precision=float(args.good_min_precision),
        good_min_precision_lift=float(args.good_min_precision_lift),
        bad_max_false_discovery_rate=float(args.bad_max_false_discovery_rate),
    )

    write_rows_parquet(run_root / "context_rows.parquet", context.to_dicts())
    write_rows_parquet(run_root / "specialist_block_outcomes.parquet", outcomes.to_dicts())
    write_rows_parquet(run_root / "good_bad_context_comparison.parquet", comparison.to_dicts())
    write_context_report(
        run_root / "context_report.md",
        router_runs=router_runs,
        context=context,
        outcomes=outcomes,
        comparison=comparison,
        report_top_n=int(args.report_top_n),
    )
    write_json(
        run_root / "context_diagnostic_config.json",
        {
            "router_runs": [str(path) for path in router_runs],
            "side": str(args.side),
            "candidate_name": str(args.candidate_name),
            "include_zero_signal_blocks": bool(args.include_zero_signal_blocks),
            "good_min_precision": float(args.good_min_precision),
            "good_min_precision_lift": float(args.good_min_precision_lift),
            "bad_max_false_discovery_rate": float(args.bad_max_false_discovery_rate),
            "safe_context_columns": SAFE_CONTEXT_COLUMNS,
            "excluded_outcome_columns": sorted(OUTCOME_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_context_diagnostic",
        status="complete",
        summary=summarize_outcomes(outcomes),
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-context] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build safe-context diagnostics for row-rule router transfer.")
    parser.add_argument("--router-run", action="append", required=True)
    parser.add_argument("--side", default="down")
    parser.add_argument("--candidate-name", default="down_rocket_16_diag_v1")
    parser.add_argument("--include-zero-signal-blocks", action="store_true")
    parser.add_argument("--good-min-precision", type=float, default=0.60)
    parser.add_argument("--good-min-precision-lift", type=float, default=1.20)
    parser.add_argument("--bad-max-false-discovery-rate", type=float, default=0.50)
    parser.add_argument("--report-top-n", type=int, default=30)
    return parser.parse_args()


def build_context_diagnostic(
    *,
    router_runs: tuple[Path, ...],
    side: str,
    candidate_name: str,
    include_zero_signal_blocks: bool,
    good_min_precision: float,
    good_min_precision_lift: float,
    bad_max_false_discovery_rate: float,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    frames = [
        load_router_run_context(
            run,
            side=side,
            candidate_name=candidate_name,
            include_zero_signal_blocks=include_zero_signal_blocks,
            good_min_precision=good_min_precision,
            good_min_precision_lift=good_min_precision_lift,
            bad_max_false_discovery_rate=bad_max_false_discovery_rate,
        )
        for run in router_runs
    ]
    frames = [frame for frame in frames if not frame.is_empty()]
    combined = pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()
    if combined.is_empty():
        return pl.DataFrame(), pl.DataFrame(), pl.DataFrame()

    context = safe_context_from_rows(combined)
    outcomes = outcome_rows_from_rows(combined)
    comparison = compare_good_bad_context(context.join(outcomes, on=join_keys(context, outcomes), how="inner"))
    return context, outcomes, comparison


def load_router_run_context(
    router_run: Path,
    *,
    side: str,
    candidate_name: str,
    include_zero_signal_blocks: bool,
    good_min_precision: float,
    good_min_precision_lift: float,
    bad_max_false_discovery_rate: float,
) -> pl.DataFrame:
    if not router_run.exists():
        raise FileNotFoundError(f"Router run does not exist: {router_run}")
    required = [
        router_run / "router_config.json",
        router_run / "row_rule_active_block_summary.parquet",
        router_run / "row_rule_gate_selection_audit.parquet",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required router row-rule artifacts in {router_run}: {missing}")

    config = json.loads((router_run / "router_config.json").read_text())
    block_summary = pl.read_parquet(router_run / "row_rule_active_block_summary.parquet")
    block_summary = block_summary.filter(pl.col("side") == side)
    if "predicted_positive_count" in block_summary.columns and not include_zero_signal_blocks:
        block_summary = block_summary.filter(pl.col("predicted_positive_count").fill_null(0) > 0)
    if block_summary.is_empty():
        return pl.DataFrame()
    block_summary = block_summary.with_columns(
        pl.col("block_idx").cast(pl.Int64, strict=False).alias("_block_idx"),
    ).with_columns(
        pl.col("_block_idx")
        .map_elements(lambda value: f"block{int(value):03d}" if value is not None else None, return_dtype=pl.String)
        .alias("test_block"),
    )

    selected = selected_rule_context(pl.read_parquet(router_run / "row_rule_gate_selection_audit.parquet"), side, candidate_name)
    fold_comparison = fold_comparison_context(router_run, side, candidate_name)
    source_context = router_config_context(router_run, config)

    out = (
        block_summary.join(selected, on=["side", "test_block"], how="left", suffix="_rule")
        .join(fold_comparison, on=["side", "test_block"], how="left", suffix="_raw")
        .with_columns([pl.lit(value).alias(name) for name, value in source_context.items()])
        .with_columns(
            pl.lit(str(candidate_name)).alias("candidate_name"),
            (pl.col("predicted_positive_count").fill_null(0) > 0).alias("active_block"),
        )
    )
    out = out.with_columns(
        (
            pl.col("active_block")
            & (pl.col("precision").fill_null(0.0) >= float(good_min_precision))
            & (pl.col("precision_lift").fill_null(0.0) >= float(good_min_precision_lift))
        ).alias("good_block"),
        (
            pl.col("active_block")
            & (pl.col("false_discovery_rate").fill_null(1.0) > float(bad_max_false_discovery_rate))
        ).alias("bad_block"),
    )
    return out.with_columns(
        pl.when(pl.col("good_block"))
        .then(pl.lit("good"))
        .when(pl.col("bad_block"))
        .then(pl.lit("bad"))
        .when(pl.col("active_block"))
        .then(pl.lit("neutral_active"))
        .otherwise(pl.lit("inactive"))
        .alias("block_label"),
        pl.when(pl.col("good_block"))
        .then(pl.lit("active_precision_and_lift_pass"))
        .when(pl.col("bad_block"))
        .then(pl.lit("active_high_false_discovery_rate"))
        .when(pl.col("active_block"))
        .then(pl.lit("active_neutral_or_mixed"))
        .otherwise(pl.lit("inactive"))
        .alias("block_label_reason"),
    )


def selected_rule_context(audit: pl.DataFrame, side: str, candidate_name: str) -> pl.DataFrame:
    if audit.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "test_block": pl.String})
    out = audit.filter(
        (pl.col("side") == side)
        & (pl.col("candidate_name") == candidate_name)
        & pl.col("selected").fill_null(False)
    )
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "test_block": pl.String})
    out = out.with_columns(
        pl.col("feature").map_elements(row_rule_feature_family, return_dtype=pl.String).alias("feature_family"),
        pl.col("selection_score").cast(pl.Float64, strict=False).alias("_selection_score"),
    ).sort(["side", "test_block", "_selection_score"], descending=[False, False, True])
    context_cols = [
        "side",
        "candidate_name",
        "test_block",
        "feature",
        "feature_family",
        "direction",
        "threshold",
        "train_rows",
        "train_accepted_rows",
        "train_tp",
        "train_fp",
        "train_precision",
        "train_base_precision",
        "train_lift",
        "train_false_discovery_rate",
        "train_precision_lcb",
        "train_accepted_rate",
        "rule_score",
        "feature_auc",
        "feature_auc_abs",
        "feature_auc_direction",
        "direction_agreement",
        "directional_lcb_score",
        "row_rule_selection_mode",
        "selection_score",
        "selection_reject_reasons",
        "reliability_key_mode",
        "reliability_history_folds",
        "reliability_signals",
        "reliability_tp",
        "reliability_fp",
        "reliability_precision",
        "reliability_precision_lcb",
        "reliability_false_discovery_rate",
        "reliability_score",
        "reliability_feature_family",
    ]
    return out.group_by(["side", "test_block"], maintain_order=True).agg(
        pl.len().alias("selected_rule_count"),
        *[pl.first(col).alias(col) for col in context_cols if col not in {"side", "test_block"} and col in out.columns],
    )


def fold_comparison_context(router_run: Path, side: str, candidate_name: str) -> pl.DataFrame:
    path = router_run / "row_rule_gate_fold_comparison.parquet"
    if not path.exists():
        return pl.DataFrame(schema={"side": pl.String, "test_block": pl.String})
    frame = pl.read_parquet(path)
    if frame.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "test_block": pl.String})
    keep = [
        "side",
        "candidate_name",
        "test_block",
        "raw_signals",
        "raw_tp",
        "raw_fp",
        "raw_precision",
        "raw_false_discovery_rate",
        "precision_lift_vs_raw",
        "signal_retention_vs_raw",
        "tp_retention_vs_raw",
        "fp_retention_vs_raw",
    ]
    out = frame.filter((pl.col("side") == side) & (pl.col("candidate_name") == candidate_name))
    if out.is_empty():
        return pl.DataFrame(schema={"side": pl.String, "test_block": pl.String})
    return out.select([col for col in keep if col in out.columns]).with_columns(
        pl.lit(True).alias("raw_signal_context_available")
    )


def router_config_context(router_run: Path, config: dict[str, Any]) -> dict[str, Any]:
    offset = int(config.get("window_end_offset_steps") or 0)
    row_gate = config.get("row_rule_gate") or {}
    reliability = row_gate.get("reliability") or {}
    return {
        "source_run": str(router_run),
        "source_block": "latest" if offset == 0 else f"offset{offset}",
        "window_end_offset_steps": offset,
        "outer_window_count": config.get("outer_window_count"),
        "selection_mode": config.get("selection_mode"),
        "candidate_set": config.get("candidate_set"),
        "row_rule_gate_mode": row_gate.get("mode"),
        "row_rule_gate_output_mode": row_gate.get("output_mode"),
        "row_rule_gate_side": row_gate.get("side"),
        "row_rule_gate_candidate_name": row_gate.get("candidate_name"),
        "row_rule_gate_block_size": row_gate.get("block_size"),
        "row_rule_gate_key": row_gate.get("key"),
        "row_rule_gate_allowed_directions": ",".join(row_gate.get("allowed_directions") or []),
        "row_rule_gate_rule_selection_score": row_gate.get("rule_selection_score"),
        "row_rule_gate_max_rules_per_candidate": row_gate.get("max_rules_per_candidate"),
        "row_rule_gate_reliability_min_history_folds": reliability.get("min_history_folds"),
        "row_rule_gate_reliability_min_signals": reliability.get("min_signals"),
        "row_rule_gate_reliability_min_precision_lcb": reliability.get("min_precision_lcb"),
        "row_rule_gate_reliability_max_false_discovery_rate": reliability.get("max_false_discovery_rate"),
        "row_rule_gate_reliability_lookback_folds": reliability.get("lookback_folds"),
    }


def safe_context_from_rows(rows: pl.DataFrame) -> pl.DataFrame:
    safe_cols = [col for col in SAFE_CONTEXT_COLUMNS if col in rows.columns and col not in OUTCOME_COLUMNS]
    out = rows.select(safe_cols)
    leaked = set(out.columns) & OUTCOME_COLUMNS
    if leaked:
        raise ValueError(f"Safe context leaked outcome columns: {sorted(leaked)}")
    return out


def outcome_rows_from_rows(rows: pl.DataFrame) -> pl.DataFrame:
    keep = [
        "source_run",
        "source_block",
        "side",
        "candidate_name",
        "block_idx",
        "test_block",
        "pred_batch_start",
        "pred_batch_end",
        "rows",
        "positive_count",
        "negative_count",
        "predicted_positive_count",
        "true_positive_count",
        "false_positive_count",
        "false_negative_count",
        "true_negative_count",
        "precision",
        "recall",
        "false_positive_rate",
        "false_discovery_rate",
        "predicted_positive_rate",
        "base_positive_rate",
        "precision_lift",
        "decision_cost",
        "decision_cost_per_row",
        "decision_cost_per_signal",
        "raw_signals",
        "raw_tp",
        "raw_fp",
        "raw_precision",
        "raw_false_discovery_rate",
        "precision_lift_vs_raw",
        "signal_retention_vs_raw",
        "tp_retention_vs_raw",
        "fp_retention_vs_raw",
        "active_block",
        "good_block",
        "bad_block",
        "block_label",
        "block_label_reason",
    ]
    return rows.select([col for col in keep if col in rows.columns])


def join_keys(left: pl.DataFrame, right: pl.DataFrame) -> list[str]:
    keys = ["source_run", "source_block", "side", "candidate_name", "block_idx", "test_block"]
    return [key for key in keys if key in left.columns and key in right.columns]


def compare_good_bad_context(joined: pl.DataFrame) -> pl.DataFrame:
    if joined.is_empty() or "good_block" not in joined.columns or "bad_block" not in joined.columns:
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    context_cols = [col for col in SAFE_CONTEXT_COLUMNS if col in joined.columns]
    for col in context_cols:
        if col in OUTCOME_COLUMNS:
            continue
        dtype = joined.schema[col]
        if dtype in {
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
            pl.Boolean,
        }:
            rows.append(numeric_comparison_row(joined, col))
        elif col in {"feature", "feature_family", "direction", "source_block", "row_rule_gate_allowed_directions"}:
            rows.extend(categorical_comparison_rows(joined, col))
    return pl.DataFrame(rows, infer_schema_length=None) if rows else pl.DataFrame()


def numeric_comparison_row(df: pl.DataFrame, col: str) -> dict[str, Any]:
    good = df.filter(pl.col("good_block")).select(pl.col(col).cast(pl.Float64, strict=False).alias(col))
    bad = df.filter(pl.col("bad_block")).select(pl.col(col).cast(pl.Float64, strict=False).alias(col))
    good_values = good[col].drop_nulls().to_list() if col in good.columns else []
    bad_values = bad[col].drop_nulls().to_list() if col in bad.columns else []
    good_mean = mean_or_none(good_values)
    bad_mean = mean_or_none(bad_values)
    delta = None if good_mean is None or bad_mean is None else float(good_mean - bad_mean)
    return {
        "comparison_type": "numeric",
        "feature": col,
        "category": None,
        "good_count": len(good_values),
        "bad_count": len(bad_values),
        "good_mean": good_mean,
        "bad_mean": bad_mean,
        "delta_good_minus_bad": delta,
        "abs_delta": abs(delta) if delta is not None else None,
        "good_rate": None,
        "bad_rate": None,
        "rate_delta": None,
    }


def categorical_comparison_rows(df: pl.DataFrame, col: str) -> list[dict[str, Any]]:
    good = df.filter(pl.col("good_block"))
    bad = df.filter(pl.col("bad_block"))
    good_total = good.height
    bad_total = bad.height
    values = sorted(
        {
            str(value)
            for value in df[col].drop_nulls().unique().to_list()
            if value is not None and str(value) != ""
        }
    )
    rows: list[dict[str, Any]] = []
    for value in values:
        good_count = good.filter(pl.col(col).cast(pl.String) == value).height if good_total else 0
        bad_count = bad.filter(pl.col(col).cast(pl.String) == value).height if bad_total else 0
        good_rate = good_count / good_total if good_total else None
        bad_rate = bad_count / bad_total if bad_total else None
        delta = None if good_rate is None or bad_rate is None else float(good_rate - bad_rate)
        rows.append(
            {
                "comparison_type": "categorical",
                "feature": col,
                "category": value,
                "good_count": good_count,
                "bad_count": bad_count,
                "good_mean": None,
                "bad_mean": None,
                "delta_good_minus_bad": None,
                "abs_delta": abs(delta) if delta is not None else None,
                "good_rate": good_rate,
                "bad_rate": bad_rate,
                "rate_delta": delta,
            }
        )
    return rows


def mean_or_none(values: list[Any]) -> float | None:
    finite: list[float] = []
    for value in values:
        try:
            x = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(x):
            finite.append(x)
    if not finite:
        return None
    return float(sum(finite) / len(finite))


def summarize_outcomes(outcomes: pl.DataFrame) -> dict[str, Any]:
    if outcomes.is_empty():
        return {"rows": 0}
    signals = int(outcomes["predicted_positive_count"].fill_null(0).sum()) if "predicted_positive_count" in outcomes.columns else 0
    tp = int(outcomes["true_positive_count"].fill_null(0).sum()) if "true_positive_count" in outcomes.columns else 0
    fp = int(outcomes["false_positive_count"].fill_null(0).sum()) if "false_positive_count" in outcomes.columns else 0
    positives = int(outcomes["positive_count"].fill_null(0).sum()) if "positive_count" in outcomes.columns else 0
    rows = int(outcomes["rows"].fill_null(0).sum()) if "rows" in outcomes.columns else 0
    precision = tp / signals if signals else None
    base_rate = positives / rows if rows else None
    return {
        "rows": outcomes.height,
        "signals": signals,
        "true_positives": tp,
        "false_positives": fp,
        "precision": precision,
        "base_rate": base_rate,
        "precision_lift": precision / base_rate if precision is not None and base_rate else None,
        "good_blocks": int(outcomes["good_block"].sum()) if "good_block" in outcomes.columns else 0,
        "bad_blocks": int(outcomes["bad_block"].sum()) if "bad_block" in outcomes.columns else 0,
        "active_blocks": int(outcomes["active_block"].sum()) if "active_block" in outcomes.columns else 0,
    }


def write_context_report(
    path: Path,
    *,
    router_runs: tuple[Path, ...],
    context: pl.DataFrame,
    outcomes: pl.DataFrame,
    comparison: pl.DataFrame,
    report_top_n: int,
) -> None:
    summary = summarize_outcomes(outcomes)
    lines = [
        "# RPF Ranked Signal Context Diagnostic",
        "",
        "## Purpose",
        "",
        "Compare safe row-rule context against matured outcomes across completed router runs.",
        "",
        "## Inputs",
        "",
    ]
    lines.extend([f"- `{path_}`" for path_ in router_runs])
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- context rows: `{context.height}`",
            f"- outcome rows: `{outcomes.height}`",
            f"- active blocks: `{markdown_value(summary.get('active_blocks'))}`",
            f"- good blocks: `{markdown_value(summary.get('good_blocks'))}`",
            f"- bad blocks: `{markdown_value(summary.get('bad_blocks'))}`",
            f"- signals: `{markdown_value(summary.get('signals'))}`",
            f"- precision: `{markdown_value(summary.get('precision'))}`",
            f"- base rate: `{markdown_value(summary.get('base_rate'))}`",
            f"- precision lift: `{markdown_value(summary.get('precision_lift'))}`",
            "",
            "## Strongest Context Separators",
            "",
            "| Type | Feature | Category | Good Mean/Rate | Bad Mean/Rate | Delta |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    if not comparison.is_empty():
        top = comparison.sort("abs_delta", descending=True, nulls_last=True).head(max(0, int(report_top_n)))
        for row in top.to_dicts():
            left = row.get("good_mean") if row.get("comparison_type") == "numeric" else row.get("good_rate")
            right = row.get("bad_mean") if row.get("comparison_type") == "numeric" else row.get("bad_rate")
            delta = row.get("delta_good_minus_bad") if row.get("comparison_type") == "numeric" else row.get("rate_delta")
            lines.append(
                "| {comparison_type} | `{feature}` | {category} | {left} | {right} | {delta} |".format(
                    comparison_type=markdown_value(row.get("comparison_type")),
                    feature=markdown_value(row.get("feature")),
                    category=markdown_value(row.get("category")),
                    left=markdown_value(left),
                    right=markdown_value(right),
                    delta=markdown_value(delta),
                )
            )
    lines.extend(
        [
            "",
            "## Leakage Rule",
            "",
            "- `context_rows.parquet` excludes current TP/FP/precision/base-rate outcome columns.",
            "- `specialist_block_outcomes.parquet` contains matured labels and must only be used after the block matures.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_context_diagnostic"


if __name__ == "__main__":
    raise SystemExit(main())

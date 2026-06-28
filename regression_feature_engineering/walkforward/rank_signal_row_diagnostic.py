"""Row-level diagnostics for RPF ranked-signal TP/FP separation.

This command consumes completed ``rank_signal_router`` runs and analyzes rows
where a candidate or router actually fired a signal.  Current prediction labels
are used only as post-hoc TP/FP labels; safe context features are restricted to
model scores and live-safe RPF feature values at the same timestamp.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES
from regression_feature_engineering.walkforward.classification.targets import UP_EXTREME
from regression_feature_engineering.walkforward.data import resolve_context
from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_transfer_separator import (
    empty_result_frame,
    markdown_value,
    score_feature,
    summarize_separator_results,
)
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_row_diagnostic"

SCORE_SOURCE_CANDIDATE = "candidate_prediction_scores"
SCORE_SOURCE_ROUTER = "router_decisions"
SCORE_SOURCE_AUTO = "auto"
SCORE_SOURCES = (SCORE_SOURCE_AUTO, SCORE_SOURCE_CANDIDATE, SCORE_SOURCE_ROUTER)

OUTCOME_COLUMNS = {
    "target_binary",
    "target_relevance",
    "signal_tp",
    "signal_fp",
    "signal_outcome",
}

IDENTITY_COLUMNS = {
    "source_run",
    "source_block",
    "side",
    "candidate_name",
    "router_step_idx",
    "router_pred_batch_id",
    "step_idx",
    "pred_batch_id",
    "timestamp",
    "batch_id",
    "target_col",
    "split",
    "candidate_status",
    "candidate_fail_reasons",
    "decision_policy",
    "score_source",
}


@dataclass(frozen=True)
class RouterInput:
    run_path: Path
    source_block: str


def main() -> int:
    args = parse_args()
    router_runs = [Path(value) for value in args.router_run]
    if not router_runs:
        raise ValueError("At least one --router-run is required")
    candidate_names = parse_optional_csv(args.candidate_names)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_row_diagnostic")

    inputs = [RouterInput(run, source_block_for_router_run(run)) for run in router_runs]
    rows = load_signal_rows(
        inputs,
        side=str(args.side),
        candidate_names=candidate_names,
        score_source=str(args.score_source),
    )
    if rows.is_empty():
        raise ValueError("No signal rows matched the requested side/candidates/source")
    asset, root = infer_asset_root(inputs)
    context = resolve_context(project_root=PROJECT_ROOT, asset=asset, root=root, target_col=UP_EXTREME)
    rpf_context = build_row_rpf_context(
        context,
        rows.select(["timestamp", "batch_id"]).unique(),
        max_features_per_family=int(args.rpf_max_features_per_family),
    )
    enriched = rows.join(rpf_context, on=["timestamp", "batch_id"], how="left")
    safe = safe_row_context_features(enriched)
    separator_frame = safe.join(
        enriched.select(
            [
                *[col for col in JOIN_KEYS if col in safe.columns and col in enriched.columns],
                "signal_tp",
                "signal_fp",
            ]
        ),
        on=[col for col in JOIN_KEYS if col in safe.columns and col in enriched.columns],
        how="inner",
    )
    feature_columns = safe_numeric_feature_columns(separator_frame)
    separation = row_separator_results(
        separator_frame,
        feature_columns=feature_columns,
        min_tp_rows=int(args.min_tp_rows),
        min_fp_rows=int(args.min_fp_rows),
    )
    separation_frame = (
        pl.DataFrame([row.__dict__ for row in separation], infer_schema_length=None)
        if separation
        else empty_result_frame()
    )
    summary_rows = summarize_separator_results(separation_frame)

    write_rows_parquet(run_root / "row_signal_transfer_table.parquet", enriched.to_dicts())
    write_rows_parquet(run_root / "row_safe_context_features.parquet", safe.to_dicts())
    write_rows_parquet(run_root / "row_feature_separation.parquet", separation_frame.to_dicts())
    write_rows_parquet(run_root / "row_separator_summary.parquet", summary_rows)
    write_row_report(
        run_root / "row_separator_report.md",
        inputs=inputs,
        rows=enriched,
        separation_frame=separation_frame,
        summary_rows=summary_rows,
        top_n=int(args.report_top_n),
    )
    write_json(
        run_root / "row_diagnostic_config.json",
        {
            "router_run": [str(run) for run in router_runs],
            "side": str(args.side),
            "candidate_names": list(candidate_names),
            "score_source": str(args.score_source),
            "rpf_max_features_per_family": int(args.rpf_max_features_per_family),
            "safe_columns": safe.columns,
            "outcome_columns": sorted(OUTCOME_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_row_diagnostic",
        status="complete",
        summary={
            "signal_rows": enriched.height,
            "tp_rows": int(enriched["signal_tp"].sum()),
            "fp_rows": int(enriched["signal_fp"].sum()),
            "safe_context_columns": len(safe.columns),
            "tested_features": len(feature_columns),
            "separator_rows": separation_frame.height,
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-row-diagnostic] done run={run_root}", flush=True)
    return 0


JOIN_KEYS = [
    "source_run",
    "source_block",
    "side",
    "candidate_name",
    "router_step_idx",
    "router_pred_batch_id",
    "timestamp",
    "batch_id",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze row-level RPF ranked-signal TP/FP separators.")
    parser.add_argument("--router-run", action="append", required=True)
    parser.add_argument("--side", choices=("up", "down"), default="down")
    parser.add_argument("--candidate-names", default="")
    parser.add_argument("--score-source", choices=SCORE_SOURCES, default=SCORE_SOURCE_AUTO)
    parser.add_argument("--rpf-max-features-per-family", type=int, default=24)
    parser.add_argument("--min-tp-rows", type=int, default=2)
    parser.add_argument("--min-fp-rows", type=int, default=2)
    parser.add_argument("--report-top-n", type=int, default=30)
    return parser.parse_args()


def parse_optional_csv(raw: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(raw or "").split(",") if item.strip()))


def load_signal_rows(
    inputs: list[RouterInput],
    *,
    side: str,
    candidate_names: tuple[str, ...],
    score_source: str,
) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    for item in inputs:
        source = resolve_score_source(item.run_path, score_source)
        frame = read_router_score_source(item.run_path, source)
        if frame.is_empty():
            continue
        frame = normalize_score_rows(frame, source=source, item=item)
        frame = frame.filter((pl.col("side") == side) & (pl.col("decision").fill_null(0) == 1))
        if candidate_names:
            frame = frame.filter(pl.col("candidate_name").is_in(candidate_names))
        if not frame.is_empty():
            frames.append(frame)
    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames, how="diagonal_relaxed")
    return add_signal_outcome_labels(out).sort(["source_block", "side", "candidate_name", "router_pred_batch_id", "timestamp"])


def resolve_score_source(run: Path, requested: str) -> str:
    if requested != SCORE_SOURCE_AUTO:
        return requested
    candidate_path = Path(run) / "candidate_prediction_scores.parquet"
    if candidate_path.exists():
        sample = pl.read_parquet(candidate_path, n_rows=1)
        if "empty" not in sample.columns:
            return SCORE_SOURCE_CANDIDATE
    return SCORE_SOURCE_ROUTER


def read_router_score_source(run: Path, source: str) -> pl.DataFrame:
    if source == SCORE_SOURCE_CANDIDATE:
        path = Path(run) / "candidate_prediction_scores.parquet"
    elif source == SCORE_SOURCE_ROUTER:
        path = Path(run) / "router_decisions.parquet"
    else:
        raise ValueError(f"Unsupported score source: {source}")
    if not path.exists():
        return pl.DataFrame()
    frame = pl.read_parquet(path)
    if "empty" in frame.columns and frame.width == 1:
        return pl.DataFrame()
    return frame


def normalize_score_rows(df: pl.DataFrame, *, source: str, item: RouterInput) -> pl.DataFrame:
    out = df
    if "candidate_name" not in out.columns and "selected_candidate" in out.columns:
        out = out.rename({"selected_candidate": "candidate_name"})
    if "router_step_idx" not in out.columns and "step_idx" in out.columns:
        out = out.with_columns(pl.col("step_idx").alias("router_step_idx"))
    if "router_pred_batch_id" not in out.columns and "pred_batch_id" in out.columns:
        out = out.with_columns(pl.col("pred_batch_id").alias("router_pred_batch_id"))
    if "margin" not in out.columns and {"rank_score", "threshold"} <= set(out.columns):
        out = out.with_columns((pl.col("rank_score") - pl.col("threshold")).alias("margin"))
    return out.with_columns(
        pl.lit(str(item.run_path)).alias("source_run"),
        pl.lit(str(item.source_block)).alias("source_block"),
        pl.lit(str(source)).alias("score_source"),
    )


def add_signal_outcome_labels(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        (pl.col("target_binary").fill_null(0).cast(pl.Int8) == 1).alias("signal_tp"),
        (pl.col("target_binary").fill_null(0).cast(pl.Int8) == 0).alias("signal_fp"),
        pl.when(pl.col("target_binary").fill_null(0).cast(pl.Int8) == 1)
        .then(pl.lit("tp"))
        .otherwise(pl.lit("fp"))
        .alias("signal_outcome"),
    )


def infer_asset_root(inputs: list[RouterInput]) -> tuple[str, str]:
    for item in inputs:
        config_path = Path(item.run_path) / "router_config.json"
        if not config_path.exists():
            continue
        payload = json.loads(config_path.read_text())
        asset = str(payload.get("asset") or "").strip()
        root = str(payload.get("root") or "").strip()
        if asset and root:
            return asset, root
    raise FileNotFoundError("Cannot infer asset/root from router_config.json")


def source_block_for_router_run(run: Path) -> str:
    config_path = Path(run) / "router_config.json"
    if not config_path.exists():
        return Path(run).name
    payload = json.loads(config_path.read_text())
    offset = int(payload.get("window_end_offset_steps", 0) or 0)
    if offset == 0:
        return "latest"
    if offset == 120:
        return "middle"
    return f"offset{offset}"


def build_row_rpf_context(
    context: Any,
    keys: pl.DataFrame,
    *,
    max_features_per_family: int,
) -> pl.DataFrame:
    if keys.is_empty():
        return pl.DataFrame()
    family_columns = select_row_context_features(
        context.manifest.feature_columns,
        max_features_per_family=max_features_per_family,
    )
    read_columns = sorted({feature for columns in family_columns.values() for feature in columns})
    frames: list[pl.DataFrame] = []
    for batch_id in sorted({int(value) for value in keys["batch_id"].to_list()}):
        batch_keys = keys.filter(pl.col("batch_id") == batch_id)
        path = context.feature_root / f"batch_{batch_id:04d}.parquet"
        if not path.exists():
            continue
        batch = pl.read_parquet(path, columns=["timestamp", "batch_id", *read_columns])
        joined = batch_keys.join(batch, on=["timestamp", "batch_id"], how="left")
        frames.append(add_row_family_context(joined, family_columns).select(["timestamp", "batch_id", *row_context_columns(family_columns)]))
    return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()


def select_row_context_features(feature_columns: tuple[str, ...], *, max_features_per_family: int) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    limit = max(1, int(max_features_per_family))
    for family, prefixes in FAMILY_PREFIXES.items():
        selected = tuple(feature for feature in feature_columns if feature.startswith(prefixes))[:limit]
        if selected:
            out[family] = selected
    return out


def row_context_columns(family_columns: dict[str, tuple[str, ...]]) -> list[str]:
    cols: list[str] = []
    for family in family_columns:
        cols.extend(
            [
                f"row_rpf_{family}_feature_count",
                f"row_rpf_{family}_mean_abs",
                f"row_rpf_{family}_max_abs",
                f"row_rpf_{family}_mean",
                f"row_rpf_{family}_positive_rate",
            ]
        )
    return cols


def add_row_family_context(frame: pl.DataFrame, family_columns: dict[str, tuple[str, ...]]) -> pl.DataFrame:
    out = frame
    exprs: list[pl.Expr] = []
    for family, columns in family_columns.items():
        available = [col for col in columns if col in out.columns]
        if not available:
            continue
        abs_cols = [pl.col(col).cast(pl.Float64, strict=False).abs() for col in available]
        raw_cols = [pl.col(col).cast(pl.Float64, strict=False) for col in available]
        positive_cols = [pl.when(pl.col(col).cast(pl.Float64, strict=False) > 0.0).then(1.0).otherwise(0.0) for col in available]
        exprs.extend(
            [
                pl.lit(len(available)).alias(f"row_rpf_{family}_feature_count"),
                pl.mean_horizontal(abs_cols).alias(f"row_rpf_{family}_mean_abs"),
                pl.max_horizontal(abs_cols).alias(f"row_rpf_{family}_max_abs"),
                pl.mean_horizontal(raw_cols).alias(f"row_rpf_{family}_mean"),
                (pl.sum_horizontal(positive_cols) / float(len(available))).alias(f"row_rpf_{family}_positive_rate"),
            ]
        )
    return out.with_columns(exprs) if exprs else out


def safe_row_context_features(df: pl.DataFrame) -> pl.DataFrame:
    safe_cols = [col for col in df.columns if col not in OUTCOME_COLUMNS]
    out = df.select(safe_cols)
    leaked = OUTCOME_COLUMNS & set(out.columns)
    if leaked:
        raise ValueError(f"Safe row context leaked outcome columns: {sorted(leaked)}")
    return out


def safe_numeric_feature_columns(df: pl.DataFrame) -> list[str]:
    allowed = {
        pl.Boolean,
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
    }
    blocked = IDENTITY_COLUMNS | OUTCOME_COLUMNS | {"decision", "raw_decision_before_batch_state_gate"}
    return [name for name, dtype in df.schema.items() if name not in blocked and dtype in allowed]


def row_separator_results(
    df: pl.DataFrame,
    *,
    feature_columns: list[str],
    min_tp_rows: int,
    min_fp_rows: int,
) -> list[Any]:
    results: list[Any] = []
    if df.is_empty():
        return results
    groups: list[tuple[str, str, str, pl.DataFrame]] = [("all", "all", "all", df)]
    for side in sorted(df["side"].unique().to_list()):
        groups.append(("side", str(side), "all", df.filter(pl.col("side") == side)))
    for item in df.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts():
        side = str(item["side"])
        candidate = str(item["candidate_name"])
        groups.append(("candidate", side, candidate, df.filter((pl.col("side") == side) & (pl.col("candidate_name") == candidate))))
    for scope, side, candidate, frame in groups:
        tp_mask = frame["signal_tp"].fill_null(False).to_numpy()
        fp_mask = frame["signal_fp"].fill_null(False).to_numpy()
        if int(tp_mask.sum()) < int(min_tp_rows) or int(fp_mask.sum()) < int(min_fp_rows):
            continue
        for feature in feature_columns:
            result = score_feature(
                frame,
                feature=feature,
                group_scope=scope,
                side=side,
                candidate_name=candidate,
                good_mask=tp_mask,
                bad_mask=fp_mask,
            )
            if result is not None:
                results.append(result)
    return sorted(results, key=lambda row: (row.score is not None, row.score or -1.0), reverse=True)


def write_row_report(
    path: Path,
    *,
    inputs: list[RouterInput],
    rows: pl.DataFrame,
    separation_frame: pl.DataFrame,
    summary_rows: list[dict[str, Any]],
    top_n: int,
) -> None:
    by_candidate = (
        rows.group_by(["source_block", "side", "candidate_name"])
        .agg(
            pl.len().alias("signals"),
            pl.col("signal_tp").sum().alias("tp"),
            pl.col("signal_fp").sum().alias("fp"),
        )
        .with_columns((pl.col("tp") / pl.col("signals")).alias("precision"))
        .sort(["source_block", "side", "candidate_name"])
    )
    lines = [
        "# RPF Ranked Signal Row Diagnostic",
        "",
        "## Scope",
        "",
        f"- router runs: `{len(inputs)}`",
        f"- signal rows: `{rows.height}`",
        f"- TP rows: `{int(rows['signal_tp'].sum())}`",
        f"- FP rows: `{int(rows['signal_fp'].sum())}`",
        "",
        "## Candidate Signal Summary",
        "",
        "| Source | Side | Candidate | Signals | TP | FP | Precision |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in by_candidate.to_dicts():
        lines.append(
            "| {source_block} | {side} | {candidate_name} | {signals} | {tp} | {fp} | {precision} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Separator Summary",
            "",
            "| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |",
            "|---|---|---|---:|---|---:|---:|---|---:|",
        ]
    )
    for row in summary_rows:
        lines.append(
            "| {group_scope} | {side} | {candidate_name} | {tested_features} | `{top_feature}` | {top_score} | "
            "{top_best_auc} | {top_direction} | {top_standardized_diff} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(["", f"## Top {int(top_n)} Row Separators", ""])
    lines.extend(
        [
            "| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | TP Mean | FP Mean | Std Diff |",
            "|---|---|---|---|---:|---:|---|---:|---:|---:|",
        ]
    )
    top = separation_frame.sort("score", descending=True).head(max(1, int(top_n))).to_dicts() if not separation_frame.is_empty() else []
    for row in top:
        lines.append(
            "| {group_scope} | {side} | {candidate_name} | `{feature}` | {score} | {best_auc} | {direction} | "
            "{good_mean} | {bad_mean} | {standardized_diff} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation Rules",
            "",
            "- This is row-level separator evidence only.",
            "- `row_safe_context_features.parquet` excludes target/outcome columns.",
            "- TP/FP labels are post-hoc diagnostics and must not be used as current-window inputs.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_row_diagnostic"


if __name__ == "__main__":
    raise SystemExit(main())

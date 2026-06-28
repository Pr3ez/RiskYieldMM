"""Separator analysis for RPF ranked-signal transfer diagnostics.

This command consumes a completed ``rank_signal_transfer_diagnostic`` run and
scores prediction-safe context fields by how well they separate post-hoc good
candidate windows from bad candidate windows.  It does not train or deploy a
router; it produces evidence for deciding whether a future context meta-router
has enough stable signal to justify implementation.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import CURRENT_LABEL_COLUMNS
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_transfer_separator"

JOIN_KEYS = [
    "source_block",
    "source_role",
    "source_run",
    "side",
    "candidate_name",
    "router_step_idx",
    "router_pred_batch_id",
]

IDENTITY_COLUMNS = {
    *JOIN_KEYS,
    "diagnostic",
    "status",
    "candidate_fail_reasons",
    "batch_state_gate_mode",
    "batch_state_gate_status",
    "validation_status",
    "validation_fail_reasons",
    "selection_mode",
    "selection_rejected_reason",
    "specialist_entry_mode",
    "specialist_entry_reason",
    "reliability_reliability_status",
    "reliability_reliability_fail_reasons",
}

LABEL_COLUMNS = [
    "candidate_active",
    "candidate_good",
    "candidate_bad",
    "candidate_good_reason",
    "predicted_positive_count",
    "true_positive_count",
    "false_positive_count",
    "positive_count",
    "precision",
    "false_discovery_rate",
    "precision_lift",
    "base_positive_rate",
]


@dataclass(frozen=True)
class SeparationResult:
    group_scope: str
    side: str
    candidate_name: str
    feature: str
    feature_type: str
    rows: int
    good_rows: int
    bad_rows: int
    missing_rows: int
    good_mean: float | None
    bad_mean: float | None
    mean_diff: float | None
    abs_mean_diff: float | None
    standardized_diff: float | None
    auc_good_high: float | None
    best_auc: float | None
    direction: str | None
    score: float | None


def main() -> int:
    args = parse_args()
    diagnostic_run = Path(args.diagnostic_run)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_transfer_separator", diagnostic_run=str(diagnostic_run))

    joined = load_joined_separator_frame(diagnostic_run)
    candidate_names = parse_optional_csv(args.candidate_names)
    if candidate_names:
        joined = joined.filter(pl.col("candidate_name").is_in(candidate_names))
    if bool(args.active_only):
        joined = joined.filter(pl.col("candidate_active").fill_null(False))
    if bool(args.good_bad_only):
        joined = joined.filter(pl.col("candidate_good").fill_null(False) | pl.col("candidate_bad").fill_null(False))

    feature_columns = safe_numeric_feature_columns(joined)
    results = separator_results(
        joined,
        feature_columns=feature_columns,
        min_good_rows=int(args.min_good_rows),
        min_bad_rows=int(args.min_bad_rows),
    )
    result_frame = pl.DataFrame([row.__dict__ for row in results], infer_schema_length=None) if results else empty_result_frame()
    summary_rows = summarize_separator_results(result_frame)

    write_rows_parquet(run_root / "feature_separation.parquet", result_frame.to_dicts())
    write_rows_parquet(run_root / "candidate_separator_summary.parquet", summary_rows)
    write_separator_report(
        run_root / "separator_report.md",
        diagnostic_run=diagnostic_run,
        joined=joined,
        result_frame=result_frame,
        summary_rows=summary_rows,
        top_n=int(args.report_top_n),
    )
    write_json(
        run_root / "separator_config.json",
        {
            "diagnostic_run": str(diagnostic_run),
            "candidate_names": list(candidate_names),
            "active_only": bool(args.active_only),
            "good_bad_only": bool(args.good_bad_only),
            "min_good_rows": int(args.min_good_rows),
            "min_bad_rows": int(args.min_bad_rows),
            "feature_columns": feature_columns,
            "excluded_columns": sorted(IDENTITY_COLUMNS | CURRENT_LABEL_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_transfer_separator",
        status="complete",
        summary={
            "diagnostic_run": str(diagnostic_run),
            "joined_rows": joined.height,
            "feature_count": len(feature_columns),
            "result_rows": result_frame.height,
            "summary_rows": len(summary_rows),
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-separator] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze safe context separators for ranked-signal transfer.")
    parser.add_argument("--diagnostic-run", required=True)
    parser.add_argument("--candidate-names", default="")
    parser.add_argument("--active-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--good-bad-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-good-rows", type=int, default=2)
    parser.add_argument("--min-bad-rows", type=int, default=2)
    parser.add_argument("--report-top-n", type=int, default=20)
    return parser.parse_args()


def load_joined_separator_frame(diagnostic_run: Path) -> pl.DataFrame:
    safe_path = diagnostic_run / "safe_context_features.parquet"
    transfer_path = diagnostic_run / "candidate_transfer_table.parquet"
    if not safe_path.exists() or not transfer_path.exists():
        raise FileNotFoundError(f"Missing diagnostic artifacts in {diagnostic_run}")
    safe = pl.read_parquet(safe_path)
    leaked = set(safe.columns) & CURRENT_LABEL_COLUMNS
    if leaked:
        raise ValueError(f"safe_context_features contains current-label columns: {sorted(leaked)}")
    transfer = pl.read_parquet(transfer_path)
    label_cols = [col for col in LABEL_COLUMNS if col in transfer.columns]
    keys = [col for col in JOIN_KEYS if col in safe.columns and col in transfer.columns]
    if not keys:
        raise ValueError("No join keys shared by safe context and transfer table")
    labels = transfer.select([*keys, *label_cols])
    return safe.join(labels, on=keys, how="inner")


def safe_numeric_feature_columns(df: pl.DataFrame) -> list[str]:
    allowed_dtypes = {
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
    blocked = IDENTITY_COLUMNS | CURRENT_LABEL_COLUMNS | set(LABEL_COLUMNS)
    out: list[str] = []
    for name, dtype in df.schema.items():
        if name in blocked:
            continue
        if dtype in allowed_dtypes:
            out.append(name)
    return out


def separator_results(
    df: pl.DataFrame,
    *,
    feature_columns: list[str],
    min_good_rows: int,
    min_bad_rows: int,
) -> list[SeparationResult]:
    results: list[SeparationResult] = []
    groups: list[tuple[str, str, str, pl.DataFrame]] = [("all", "all", "all", df)]
    for side in sorted(df["side"].unique().to_list()) if "side" in df.columns and df.height else []:
        groups.append(("side", str(side), "all", df.filter(pl.col("side") == side)))
    for item in df.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts() if df.height else []:
        side = str(item["side"])
        candidate = str(item["candidate_name"])
        groups.append(
            (
                "candidate",
                side,
                candidate,
                df.filter((pl.col("side") == side) & (pl.col("candidate_name") == candidate)),
            )
        )

    for scope, side, candidate_name, frame in groups:
        if frame.is_empty():
            continue
        good_mask = frame["candidate_good"].fill_null(False).to_numpy()
        bad_mask = frame["candidate_bad"].fill_null(False).to_numpy()
        if int(good_mask.sum()) < int(min_good_rows) or int(bad_mask.sum()) < int(min_bad_rows):
            continue
        for feature in feature_columns:
            result = score_feature(
                frame,
                feature=feature,
                group_scope=scope,
                side=side,
                candidate_name=candidate_name,
                good_mask=good_mask,
                bad_mask=bad_mask,
            )
            if result is not None:
                results.append(result)
    return sorted(results, key=lambda row: (row.score is not None, row.score or -1.0), reverse=True)


def score_feature(
    frame: pl.DataFrame,
    *,
    feature: str,
    group_scope: str,
    side: str,
    candidate_name: str,
    good_mask: np.ndarray,
    bad_mask: np.ndarray,
) -> SeparationResult | None:
    values = feature_values(frame[feature])
    label_mask = good_mask | bad_mask
    x = values[label_mask]
    y = good_mask[label_mask].astype(int)
    finite = np.isfinite(x)
    x = x[finite]
    y = y[finite]
    if x.size == 0 or np.unique(x).size <= 1 or np.unique(y).size != 2:
        return None
    good_values = x[y == 1]
    bad_values = x[y == 0]
    if good_values.size == 0 or bad_values.size == 0:
        return None
    good_mean = float(np.mean(good_values))
    bad_mean = float(np.mean(bad_values))
    mean_diff = good_mean - bad_mean
    pooled = pooled_std(good_values, bad_values)
    standardized = mean_diff / pooled if pooled and pooled > 0 else None
    auc = auc_score(x, y)
    best_auc = max(auc, 1.0 - auc) if auc is not None else None
    direction = "higher_good" if auc is not None and auc >= 0.5 else "lower_good"
    score = None
    if best_auc is not None:
        score = 2.0 * abs(best_auc - 0.5)
        if standardized is not None:
            score += min(2.0, abs(float(standardized))) * 0.25
    return SeparationResult(
        group_scope=group_scope,
        side=side,
        candidate_name=candidate_name,
        feature=feature,
        feature_type=str(frame.schema[feature]),
        rows=int(x.size),
        good_rows=int(good_values.size),
        bad_rows=int(bad_values.size),
        missing_rows=int(label_mask.sum() - x.size),
        good_mean=good_mean,
        bad_mean=bad_mean,
        mean_diff=float(mean_diff),
        abs_mean_diff=float(abs(mean_diff)),
        standardized_diff=None if standardized is None else float(standardized),
        auc_good_high=None if auc is None else float(auc),
        best_auc=None if best_auc is None else float(best_auc),
        direction=direction,
        score=None if score is None else float(score),
    )


def feature_values(series: pl.Series) -> np.ndarray:
    if series.dtype == pl.Boolean:
        return series.cast(pl.Int8).to_numpy().astype(float)
    return series.cast(pl.Float64, strict=False).to_numpy().astype(float)


def pooled_std(a: np.ndarray, b: np.ndarray) -> float | None:
    if a.size + b.size <= 2:
        return None
    var_a = float(np.var(a, ddof=1)) if a.size > 1 else 0.0
    var_b = float(np.var(b, ddof=1)) if b.size > 1 else 0.0
    denom = a.size + b.size - 2
    if denom <= 0:
        return None
    return math.sqrt(((a.size - 1) * var_a + (b.size - 1) * var_b) / denom)


def auc_score(values: np.ndarray, labels: np.ndarray) -> float | None:
    positives = values[labels == 1]
    negatives = values[labels == 0]
    if positives.size == 0 or negatives.size == 0:
        return None
    wins = 0.0
    for value in positives:
        wins += float(np.sum(value > negatives))
        wins += 0.5 * float(np.sum(value == negatives))
    return wins / float(positives.size * negatives.size)


def summarize_separator_results(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return (
        frame.sort("score", descending=True)
        .group_by(["group_scope", "side", "candidate_name"], maintain_order=True)
        .agg(
            pl.len().alias("tested_features"),
            pl.col("feature").first().alias("top_feature"),
            pl.col("score").first().alias("top_score"),
            pl.col("best_auc").first().alias("top_best_auc"),
            pl.col("direction").first().alias("top_direction"),
            pl.col("standardized_diff").first().alias("top_standardized_diff"),
        )
        .sort(["group_scope", "side", "candidate_name"])
        .to_dicts()
    )


def write_separator_report(
    path: Path,
    *,
    diagnostic_run: Path,
    joined: pl.DataFrame,
    result_frame: pl.DataFrame,
    summary_rows: list[dict[str, Any]],
    top_n: int,
) -> None:
    lines = [
        "# RPF Ranked Signal Transfer Separator Report",
        "",
        "## Scope",
        "",
        f"- diagnostic run: `{diagnostic_run}`",
        f"- analyzed rows: `{joined.height}`",
        f"- separator rows: `{result_frame.height}`",
        "",
        "## Group Summary",
        "",
        "| Scope | Side | Candidate | Tested Features | Top Feature | Score | Best AUC | Direction | Std Diff |",
        "|---|---|---|---:|---|---:|---:|---|---:|",
    ]
    for row in summary_rows:
        lines.append(
            "| {group_scope} | {side} | {candidate_name} | {tested_features} | `{top_feature}` | {top_score} | "
            "{top_best_auc} | {top_direction} | {top_standardized_diff} |".format(
                **{key: markdown_value(value) for key, value in row.items()}
            )
        )
    lines.extend(["", f"## Top {int(top_n)} Separators", ""])
    lines.extend(
        [
            "| Scope | Side | Candidate | Feature | Score | Best AUC | Direction | Good Mean | Bad Mean | Std Diff |",
            "|---|---|---|---|---:|---:|---|---:|---:|---:|",
        ]
    )
    top = result_frame.sort("score", descending=True).head(max(1, int(top_n))).to_dicts() if not result_frame.is_empty() else []
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
            "## Interpretation",
            "",
            "- This is separator evidence only; it does not prove a deployable meta-router.",
            "- Features are from `safe_context_features.parquet`; current prediction labels are used only as post-hoc labels.",
            "- A high score means the field separated `candidate_good` from `candidate_bad` on the compared blocks.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def markdown_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        return f"{value:.6g}"
    return str(value)


def empty_result_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "group_scope": pl.String,
            "side": pl.String,
            "candidate_name": pl.String,
            "feature": pl.String,
            "score": pl.Float64,
        }
    )


def parse_optional_csv(raw: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(raw or "").split(",") if item.strip()))


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_transfer_separator"


if __name__ == "__main__":
    raise SystemExit(main())

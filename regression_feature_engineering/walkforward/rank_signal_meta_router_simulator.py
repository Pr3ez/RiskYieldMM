"""Dry-run context meta-router simulator for RPF ranked-signal candidates.

This command consumes completed transfer diagnostics.  It trains simple
candidate-specific accept/reject rules from one matured source block and replays
them on another block.  It is intentionally offline and diagnostic: it does not
modify the live router and never uses the test block to fit thresholds.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.rank_signal import write_rows_parquet
from regression_feature_engineering.walkforward.rank_signal_transfer_separator import (
    safe_numeric_feature_columns,
    separator_results,
)
from regression_feature_engineering.walkforward.rank_signal_transfer_diagnostic import CURRENT_LABEL_COLUMNS
from regression_feature_engineering.walkforward.reports import append_event, write_json, write_stage_status
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_ranked_signal_meta_router_simulator"


@dataclass(frozen=True)
class CandidateRule:
    side: str
    candidate_name: str
    feature: str
    direction: str
    threshold: float
    train_score: float
    train_windows: int
    train_good_rows: int
    train_bad_rows: int
    train_accepted_windows: int
    train_signals: int
    train_precision: float | None
    train_lift: float | None
    train_false_discovery_rate: float | None
    separator_best_auc: float | None
    separator_score: float | None


def main() -> int:
    args = parse_args()
    diagnostic_run = Path(args.diagnostic_run)
    run_root = run_root_for_args()
    run_root.mkdir(parents=True, exist_ok=True)
    events_path = run_root / "events.jsonl"
    append_event(events_path, "stage_start", command="rank_signal_meta_router_simulator", diagnostic_run=str(diagnostic_run))

    frame = load_transfer_frame(diagnostic_run)
    candidate_names = parse_optional_csv(args.candidate_names)
    if candidate_names:
        frame = frame.filter(pl.col("candidate_name").is_in(candidate_names))
    feature_columns = safe_numeric_feature_columns(frame)

    rules = train_candidate_rules(
        frame,
        feature_columns=feature_columns,
        train_source_block=str(args.train_source_block),
        min_train_good_rows=int(args.min_train_good_rows),
        min_train_bad_rows=int(args.min_train_bad_rows),
        min_train_signals=int(args.min_train_signals),
    )
    acceptance = apply_candidate_rules(frame, rules)
    candidate_summary = summarize_candidate_acceptance(acceptance)
    side_windows = simulate_side_router(acceptance)
    side_summary = summarize_side_router(side_windows)

    write_rows_parquet(run_root / "meta_router_rules.parquet", [rule.__dict__ for rule in rules])
    write_rows_parquet(run_root / "candidate_acceptance_windows.parquet", acceptance.to_dicts())
    write_rows_parquet(run_root / "candidate_acceptance_summary.parquet", candidate_summary)
    write_rows_parquet(run_root / "side_router_simulation_windows.parquet", side_windows.to_dicts())
    write_rows_parquet(run_root / "side_router_simulation_summary.parquet", side_summary)
    write_simulator_report(
        run_root / "meta_router_simulation_report.md",
        diagnostic_run=diagnostic_run,
        train_source_block=str(args.train_source_block),
        test_source_block=str(args.test_source_block),
        rules=rules,
        candidate_summary=candidate_summary,
        side_summary=side_summary,
    )
    write_json(
        run_root / "simulator_config.json",
        {
            "diagnostic_run": str(diagnostic_run),
            "candidate_names": list(candidate_names),
            "train_source_block": str(args.train_source_block),
            "test_source_block": str(args.test_source_block),
            "min_train_good_rows": int(args.min_train_good_rows),
            "min_train_bad_rows": int(args.min_train_bad_rows),
            "min_train_signals": int(args.min_train_signals),
            "feature_columns": feature_columns,
            "excluded_current_label_columns": sorted(CURRENT_LABEL_COLUMNS),
        },
    )
    write_stage_status(
        run_root / "stage_status.json",
        stage="rank_signal_meta_router_simulator",
        status="complete",
        summary={
            "diagnostic_run": str(diagnostic_run),
            "train_source_block": str(args.train_source_block),
            "test_source_block": str(args.test_source_block),
            "input_rows": frame.height,
            "feature_count": len(feature_columns),
            "rule_count": len(rules),
            "candidate_acceptance_rows": acceptance.height,
            "side_router_rows": side_windows.height,
        },
    )
    append_event(events_path, "stage_done", run=str(run_root))
    print(f"[rpf-meta-router-sim] done run={run_root}", flush=True)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run RPF ranked-signal context meta-router rules.")
    parser.add_argument("--diagnostic-run", required=True)
    parser.add_argument("--candidate-names", default="")
    parser.add_argument("--train-source-block", default="older")
    parser.add_argument("--test-source-block", default="latest")
    parser.add_argument("--min-train-good-rows", type=int, default=2)
    parser.add_argument("--min-train-bad-rows", type=int, default=2)
    parser.add_argument("--min-train-signals", type=int, default=3)
    return parser.parse_args()


def load_transfer_frame(diagnostic_run: Path) -> pl.DataFrame:
    safe_path = diagnostic_run / "safe_context_features.parquet"
    transfer_path = diagnostic_run / "candidate_transfer_table.parquet"
    if not safe_path.exists() or not transfer_path.exists():
        raise FileNotFoundError(f"Missing transfer diagnostic artifacts in {diagnostic_run}")
    safe = pl.read_parquet(safe_path)
    leaked = set(safe.columns) & CURRENT_LABEL_COLUMNS
    if leaked:
        raise ValueError(f"safe_context_features contains current-label columns: {sorted(leaked)}")
    transfer = pl.read_parquet(transfer_path)
    label_cols = [
        "candidate_active",
        "candidate_good",
        "candidate_bad",
        "candidate_good_reason",
        "predicted_positive_count",
        "true_positive_count",
        "false_positive_count",
        "positive_count",
        "negative_count",
        "rows",
        "precision",
        "false_discovery_rate",
        "precision_lift",
        "base_positive_rate",
    ]
    keys = [
        "source_block",
        "source_role",
        "source_run",
        "side",
        "candidate_name",
        "router_step_idx",
        "router_pred_batch_id",
    ]
    labels = transfer.select([col for col in [*keys, *label_cols] if col in transfer.columns])
    return safe.join(labels, on=keys, how="inner")


def train_candidate_rules(
    frame: pl.DataFrame,
    *,
    feature_columns: list[str],
    train_source_block: str,
    min_train_good_rows: int,
    min_train_bad_rows: int,
    min_train_signals: int,
) -> list[CandidateRule]:
    train = frame.filter(pl.col("source_block") == train_source_block)
    train_active_labels = train.filter(pl.col("candidate_good").fill_null(False) | pl.col("candidate_bad").fill_null(False))
    sep = separator_results(
        train_active_labels,
        feature_columns=feature_columns,
        min_good_rows=int(min_train_good_rows),
        min_bad_rows=int(min_train_bad_rows),
    )
    candidates = train.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts()
    rules: list[CandidateRule] = []
    for candidate in candidates:
        side = str(candidate["side"])
        name = str(candidate["candidate_name"])
        candidate_sep = [
            row
            for row in sep
            if row.group_scope == "candidate" and row.side == side and row.candidate_name == name
        ]
        candidate_frame = train.filter((pl.col("side") == side) & (pl.col("candidate_name") == name))
        for sep_row in candidate_sep:
            rule = optimize_threshold_for_feature(
                candidate_frame,
                feature=str(sep_row.feature),
                direction=str(sep_row.direction),
                min_train_signals=int(min_train_signals),
                separator_best_auc=sep_row.best_auc,
                separator_score=sep_row.score,
            )
            if rule is not None:
                rules.append(rule)
                break
    return rules


def optimize_threshold_for_feature(
    frame: pl.DataFrame,
    *,
    feature: str,
    direction: str,
    min_train_signals: int,
    separator_best_auc: float | None,
    separator_score: float | None,
) -> CandidateRule | None:
    if frame.is_empty() or feature not in frame.columns:
        return None
    values = feature_values(frame[feature])
    finite = np.isfinite(values)
    unique = np.unique(values[finite])
    if unique.size == 0:
        return None
    thresholds = threshold_candidates(unique)
    best: tuple[float, float, dict[str, Any]] | None = None
    for threshold in thresholds:
        accepted = rule_accept_mask(values, direction=direction, threshold=float(threshold))
        metrics = aggregate_rows(frame.filter(pl.Series("_accepted", accepted)))
        if int(metrics["signals"]) < int(min_train_signals):
            continue
        score = rule_score(metrics)
        margin = abs(float(threshold))
        if best is None or (score, -margin) > (best[0], -best[1]):
            best = (score, margin, metrics)
    if best is None:
        return None
    score, _, metrics = best
    side = str(frame["side"][0])
    candidate_name = str(frame["candidate_name"][0])
    good_rows = int(frame["candidate_good"].fill_null(False).sum())
    bad_rows = int(frame["candidate_bad"].fill_null(False).sum())
    threshold = best_threshold_for_score(frame, feature=feature, direction=direction, min_train_signals=min_train_signals)
    if threshold is None:
        return None
    return CandidateRule(
        side=side,
        candidate_name=candidate_name,
        feature=feature,
        direction=direction,
        threshold=float(threshold),
        train_score=float(score),
        train_windows=int(frame.height),
        train_good_rows=good_rows,
        train_bad_rows=bad_rows,
        train_accepted_windows=int(metrics["accepted_windows"]),
        train_signals=int(metrics["signals"]),
        train_precision=metrics["precision"],
        train_lift=metrics["lift"],
        train_false_discovery_rate=metrics["false_discovery_rate"],
        separator_best_auc=separator_best_auc,
        separator_score=separator_score,
    )


def best_threshold_for_score(
    frame: pl.DataFrame,
    *,
    feature: str,
    direction: str,
    min_train_signals: int,
) -> float | None:
    values = feature_values(frame[feature])
    unique = np.unique(values[np.isfinite(values)])
    best: tuple[float, float] | None = None
    for threshold in threshold_candidates(unique):
        accepted = rule_accept_mask(values, direction=direction, threshold=float(threshold))
        metrics = aggregate_rows(frame.filter(pl.Series("_accepted", accepted)))
        if int(metrics["signals"]) < int(min_train_signals):
            continue
        score = rule_score(metrics)
        if best is None or score > best[0]:
            best = (score, float(threshold))
    return best[1] if best else None


def apply_candidate_rules(frame: pl.DataFrame, rules: list[CandidateRule]) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    rule_rows = { (rule.side, rule.candidate_name): rule for rule in rules }
    outputs: list[pl.DataFrame] = []
    for item in frame.select(["side", "candidate_name"]).unique().sort(["side", "candidate_name"]).to_dicts():
        side = str(item["side"])
        candidate = str(item["candidate_name"])
        subset = frame.filter((pl.col("side") == side) & (pl.col("candidate_name") == candidate))
        rule = rule_rows.get((side, candidate))
        if rule is None:
            outputs.append(
                subset.with_columns(
                    pl.lit(False).alias("meta_accept"),
                    pl.lit(None).cast(pl.String).alias("meta_rule_feature"),
                    pl.lit(None).cast(pl.String).alias("meta_rule_direction"),
                    pl.lit(None).cast(pl.Float64).alias("meta_rule_threshold"),
                    pl.lit(None).cast(pl.Float64).alias("meta_rule_margin"),
                    pl.lit(None).cast(pl.Float64).alias("meta_rule_train_score"),
                )
            )
            continue
        values = feature_values(subset[rule.feature])
        accept = rule_accept_mask(values, direction=rule.direction, threshold=rule.threshold)
        margin = rule_margin(values, direction=rule.direction, threshold=rule.threshold)
        outputs.append(
            subset.with_columns(
                pl.Series("meta_accept", accept),
                pl.lit(rule.feature).alias("meta_rule_feature"),
                pl.lit(rule.direction).alias("meta_rule_direction"),
                pl.lit(float(rule.threshold)).alias("meta_rule_threshold"),
                pl.Series("meta_rule_margin", margin),
                pl.lit(float(rule.train_score)).alias("meta_rule_train_score"),
            )
        )
    return pl.concat(outputs, how="diagonal_relaxed").sort(["source_block", "side", "candidate_name", "router_pred_batch_id"])


def simulate_side_router(acceptance: pl.DataFrame) -> pl.DataFrame:
    if acceptance.is_empty():
        return pl.DataFrame()
    rows: list[dict[str, Any]] = []
    keys = acceptance.select(["source_block", "side", "router_pred_batch_id"]).unique().sort(["source_block", "side", "router_pred_batch_id"])
    for key in keys.to_dicts():
        block = str(key["source_block"])
        side = str(key["side"])
        batch = int(key["router_pred_batch_id"])
        subset = acceptance.filter(
            (pl.col("source_block") == block)
            & (pl.col("side") == side)
            & (pl.col("router_pred_batch_id") == batch)
            & pl.col("meta_accept").fill_null(False)
        )
        if subset.is_empty():
            base = acceptance.filter(
                (pl.col("source_block") == block)
                & (pl.col("side") == side)
                & (pl.col("router_pred_batch_id") == batch)
            ).head(1)
            row = base.to_dicts()[0] if base.height else {}
            rows.append(empty_side_window_row(block, side, batch, row))
            continue
        selected = (
            subset.sort(["meta_rule_margin", "meta_rule_train_score", "candidate_name"], descending=[True, True, False])
            .head(1)
            .to_dicts()[0]
        )
        rows.append(side_window_row_from_candidate(selected))
    return pl.DataFrame(rows, infer_schema_length=None)


def summarize_candidate_acceptance(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return [
        {
            "summary_type": "candidate_acceptance",
            **row,
            **aggregate_rows(
                frame.filter(
                    (pl.col("source_block") == row["source_block"])
                    & (pl.col("side") == row["side"])
                    & (pl.col("candidate_name") == row["candidate_name"])
                    & pl.col("meta_accept").fill_null(False)
                )
            ),
        }
        for row in frame.select(["source_block", "side", "candidate_name"]).unique().sort(["source_block", "side", "candidate_name"]).to_dicts()
    ]


def summarize_side_router(frame: pl.DataFrame) -> list[dict[str, Any]]:
    if frame.is_empty():
        return []
    return [
        {
            "summary_type": "side_router",
            **row,
            **aggregate_rows(
                frame.filter((pl.col("source_block") == row["source_block"]) & (pl.col("side") == row["side"]))
            ),
        }
        for row in frame.select(["source_block", "side"]).unique().sort(["source_block", "side"]).to_dicts()
    ]


def side_window_row_from_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_block": row.get("source_block"),
        "side": row.get("side"),
        "router_pred_batch_id": row.get("router_pred_batch_id"),
        "selected_candidate": row.get("candidate_name"),
        "meta_accept": bool(row.get("meta_accept")),
        "meta_rule_feature": row.get("meta_rule_feature"),
        "meta_rule_direction": row.get("meta_rule_direction"),
        "meta_rule_threshold": row.get("meta_rule_threshold"),
        "meta_rule_margin": row.get("meta_rule_margin"),
        "predicted_positive_count": int(row.get("predicted_positive_count") or 0),
        "true_positive_count": int(row.get("true_positive_count") or 0),
        "false_positive_count": int(row.get("false_positive_count") or 0),
        "positive_count": int(row.get("positive_count") or 0),
        "rows": int(row.get("rows") or 0),
        "candidate_good": bool(row.get("candidate_good")),
        "candidate_bad": bool(row.get("candidate_bad")),
    }


def empty_side_window_row(block: str, side: str, batch: int, base: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_block": block,
        "side": side,
        "router_pred_batch_id": batch,
        "selected_candidate": None,
        "meta_accept": False,
        "meta_rule_feature": None,
        "meta_rule_direction": None,
        "meta_rule_threshold": None,
        "meta_rule_margin": None,
        "predicted_positive_count": 0,
        "true_positive_count": 0,
        "false_positive_count": 0,
        "positive_count": int(base.get("positive_count") or 0),
        "rows": int(base.get("rows") or 0),
        "candidate_good": False,
        "candidate_bad": False,
    }


def aggregate_rows(frame: pl.DataFrame) -> dict[str, Any]:
    if frame.is_empty():
        return {
            "windows": 0,
            "accepted_windows": 0,
            "signals": 0,
            "true_positives": 0,
            "false_positives": 0,
            "positives": 0,
            "rows": 0,
            "precision": None,
            "base_rate": None,
            "lift": None,
            "false_discovery_rate": None,
            "active_rate": 0.0,
        }
    windows = int(frame.height)
    signals = int(frame["predicted_positive_count"].fill_null(0).sum()) if "predicted_positive_count" in frame.columns else 0
    tp = int(frame["true_positive_count"].fill_null(0).sum()) if "true_positive_count" in frame.columns else 0
    fp = int(frame["false_positive_count"].fill_null(0).sum()) if "false_positive_count" in frame.columns else 0
    positives = int(frame["positive_count"].fill_null(0).sum()) if "positive_count" in frame.columns else 0
    row_count = int(frame["rows"].fill_null(0).sum()) if "rows" in frame.columns else 0
    precision = safe_ratio(tp, signals)
    base_rate = safe_ratio(positives, row_count)
    lift = safe_ratio(precision, base_rate) if precision is not None and base_rate and base_rate > 0 else None
    fdr = safe_ratio(fp, signals)
    active_windows = int((frame["predicted_positive_count"].fill_null(0) > 0).sum()) if "predicted_positive_count" in frame.columns else 0
    return {
        "windows": windows,
        "accepted_windows": windows,
        "signals": signals,
        "true_positives": tp,
        "false_positives": fp,
        "positives": positives,
        "rows": row_count,
        "precision": precision,
        "base_rate": base_rate,
        "lift": lift,
        "false_discovery_rate": fdr,
        "active_rate": safe_ratio(active_windows, windows) or 0.0,
    }


def rule_score(metrics: dict[str, Any]) -> float:
    precision = finite(metrics.get("precision"), 0.0)
    lift = finite(metrics.get("lift"), 0.0)
    fdr = finite(metrics.get("false_discovery_rate"), 1.0)
    active = finite(metrics.get("active_rate"), 0.0)
    return float(2.0 * max(0.0, lift - 1.0) + precision - 1.5 * fdr + 0.2 * active)


def rule_accept_mask(values: np.ndarray, *, direction: str, threshold: float) -> np.ndarray:
    if direction == "higher_good":
        return np.isfinite(values) & (values >= float(threshold))
    if direction == "lower_good":
        return np.isfinite(values) & (values <= float(threshold))
    raise ValueError(f"Unsupported rule direction: {direction}")


def rule_margin(values: np.ndarray, *, direction: str, threshold: float) -> np.ndarray:
    if direction == "higher_good":
        return values - float(threshold)
    if direction == "lower_good":
        return float(threshold) - values
    raise ValueError(f"Unsupported rule direction: {direction}")


def threshold_candidates(unique_values: np.ndarray) -> np.ndarray:
    values = np.asarray(unique_values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size <= 1:
        return values
    values = np.unique(values)
    midpoints = (values[:-1] + values[1:]) / 2.0
    return np.unique(np.concatenate([values, midpoints]))


def feature_values(series: pl.Series) -> np.ndarray:
    if series.dtype == pl.Boolean:
        return series.cast(pl.Int8).to_numpy().astype(float)
    return series.cast(pl.Float64, strict=False).to_numpy().astype(float)


def safe_ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator is None or float(denominator) == 0.0:
        return None
    return float(numerator) / float(denominator)


def finite(value: Any, default: float) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if math.isfinite(out) else float(default)


def write_simulator_report(
    path: Path,
    *,
    diagnostic_run: Path,
    train_source_block: str,
    test_source_block: str,
    rules: list[CandidateRule],
    candidate_summary: list[dict[str, Any]],
    side_summary: list[dict[str, Any]],
) -> None:
    lines = [
        "# RPF Ranked Signal Meta-Router Simulator",
        "",
        "## Scope",
        "",
        f"- diagnostic run: `{diagnostic_run}`",
        f"- train source block: `{train_source_block}`",
        f"- test source block: `{test_source_block}`",
        f"- trained candidate rules: `{len(rules)}`",
        "",
        "## Rules",
        "",
        "| Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for rule in rules:
        lines.append(
            f"| {rule.side} | {rule.candidate_name} | `{rule.feature}` | {rule.direction} | "
            f"{fmt(rule.threshold)} | {rule.train_signals} | {fmt(rule.train_precision)} | {fmt(rule.train_lift)} |"
        )
    lines.extend(["", "## Candidate Acceptance Summary", ""])
    lines.extend(summary_table(candidate_summary))
    lines.extend(["", "## Side Router Summary", ""])
    lines.extend(summary_table(side_summary))
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This is an offline dry-run only.",
            "- Rules are fit on the configured train source block and replayed on other blocks.",
            "- Current prediction labels are used only for matured outcome scoring, never for fitting test-block rules.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def summary_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Source | Side | Candidate | Windows | Signals | TP | FP | Precision | Base Rate | Lift | FDR |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {source_block} | {side} | {candidate_name} | {windows} | {signals} | {true_positives} | "
            "{false_positives} | {precision} | {base_rate} | {lift} | {false_discovery_rate} |".format(
                source_block=row.get("source_block"),
                side=row.get("side"),
                candidate_name=row.get("candidate_name", "selected_side_router"),
                windows=row.get("windows"),
                signals=row.get("signals"),
                true_positives=row.get("true_positives"),
                false_positives=row.get("false_positives"),
                precision=fmt(row.get("precision")),
                base_rate=fmt(row.get("base_rate")),
                lift=fmt(row.get("lift")),
                false_discovery_rate=fmt(row.get("false_discovery_rate")),
            )
        )
    return lines


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    try:
        out = float(value)
    except Exception:
        return str(value)
    return f"{out:.6g}" if math.isfinite(out) else "-"


def parse_optional_csv(raw: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in str(raw or "").split(",") if item.strip()))


def run_root_for_args() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OUTPUT_ROOT / f"{timestamp}_rank_signal_meta_router_simulator"


if __name__ == "__main__":
    raise SystemExit(main())

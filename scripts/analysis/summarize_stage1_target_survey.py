"""Summarize held-out Stage-1 predictions for experimental target comparisons.

The Stage-1 runner stores prediction payloads for every prediction batch and
may store more than one candidate action per batch. This script evaluates only
the action selected by that batch's `stage1_step_summary.json`, then restricts
baseline-versus-candidate comparisons to common prediction batches.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
CLASS_NAMES = ("DOWN_BALANCED", "DOWN_EXPANSION", "UP_BALANCED", "UP_EXPANSION")
N_CLASSES = len(CLASS_NAMES)


@dataclass(frozen=True)
class RunSpec:
    name: str
    run_id: str
    target_col: str


@dataclass(frozen=True)
class LoadedPredictions:
    frame: pl.DataFrame
    attempted_steps: int
    scorable_steps: int
    no_winner_steps: tuple[int, ...]
    missing_artifact_steps: tuple[int, ...]
    fail_reasons: dict[str, int]


def _run_dir(project_root: Path, run_id: str) -> Path:
    return project_root / "data" / "htf_backtest_results" / run_id


def _unit_dir(project_root: Path, spec: RunSpec) -> Path:
    return _run_dir(project_root, spec.run_id) / "catboost" / "1m" / spec.target_col


def load_selected_predictions(project_root: Path, spec: RunSpec) -> LoadedPredictions:
    """Load one selected held-out prediction payload per completed step."""
    unit_dir = _unit_dir(project_root, spec)
    if not unit_dir.exists():
        raise FileNotFoundError(f"Stage-1 unit directory not found: {unit_dir}")

    selected: list[pl.DataFrame] = []
    attempted_steps = 0
    no_winner_steps: list[int] = []
    missing_artifact_steps: list[int] = []
    fail_reasons: dict[str, int] = {}
    for batch_dir in sorted(unit_dir.glob("batch_*"), key=lambda p: int(p.name.split("_")[-1])):
        stage1_dir = batch_dir / "stage1"
        summary_path = stage1_dir / "stage1_step_summary.json"
        predictions_path = stage1_dir / "stage1_pred_batch_predictions.parquet"
        if not summary_path.exists() or not predictions_path.exists():
            missing_artifact_steps.append(int(batch_dir.name.split("_")[-1]))
            continue
        summary = json.loads(summary_path.read_text())
        attempted_steps += 1
        pred_batch = int(summary["pred_batch"])
        for reason, count in (summary.get("fail_reasons") or {}).items():
            fail_reasons[str(reason)] = fail_reasons.get(str(reason), 0) + int(count)
        winner = summary.get("winner_combo_key")
        if winner is None:
            no_winner_steps.append(pred_batch)
            continue
        winner_key = str(winner)
        frame = pl.read_parquet(predictions_path)
        if "scope" in frame.columns:
            frame = frame.filter(pl.col("scope") == "pred_batch")
        frame = frame.filter(pl.col("action_key") == winner_key)
        if frame.is_empty():
            raise ValueError(
                f"Selected action {winner_key} has no prediction rows in {predictions_path}"
            )
        if frame.select(["timestamp", "batch_id"]).n_unique() != len(frame):
            raise ValueError(f"Duplicate selected prediction timestamp,batch_id rows: {predictions_path}")
        selected.append(
            frame.select(
                [
                    pl.lit(spec.name).alias("run_name"),
                    pl.lit(spec.run_id).alias("run_id"),
                    pl.lit(spec.target_col).alias("target_col"),
                    pl.lit(pred_batch).cast(pl.Int64).alias("pred_batch"),
                    pl.col("timestamp"),
                    pl.col("batch_id"),
                    pl.col("action_key"),
                    pl.col("y_true").cast(pl.Int32),
                    pl.col("y_pred").cast(pl.Int32),
                    *(pl.col(f"prob_class_{idx}").cast(pl.Float64) for idx in range(N_CLASSES)),
                ]
            )
        )
    if not selected:
        raise FileNotFoundError(f"No complete selected prediction payloads in {unit_dir}")
    frame = pl.concat(selected).sort(["pred_batch", "timestamp", "batch_id"])
    return LoadedPredictions(
        frame=frame,
        attempted_steps=attempted_steps,
        scorable_steps=int(frame["pred_batch"].n_unique()),
        no_winner_steps=tuple(no_winner_steps),
        missing_artifact_steps=tuple(missing_artifact_steps),
        fail_reasons=fail_reasons,
    )


def compute_metrics(frame: pl.DataFrame) -> dict[str, Any]:
    """Compute four-class and direction-sensitive prediction metrics."""
    if frame.is_empty():
        return {
            "rows": 0,
            "steps": 0,
            "accuracy": None,
            "macro_f1": None,
            "direction_accuracy": None,
            "cross_direction_error": None,
            "logloss": None,
            "brier_score": None,
            "confusion_matrix": [],
            "direction_confusion_matrix": [],
            "step_summary": {},
        }

    y_true = frame["y_true"].to_numpy().astype(np.int32, copy=False)
    y_pred = frame["y_pred"].to_numpy().astype(np.int32, copy=False)
    probabilities = frame.select([f"prob_class_{idx}" for idx in range(N_CLASSES)]).to_numpy()
    probabilities = np.clip(probabilities, 1e-12, 1.0)
    probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
    y_true_dir = (y_true >= 2).astype(np.int8, copy=False)
    y_pred_dir = (y_pred >= 2).astype(np.int8, copy=False)
    one_hot = np.eye(N_CLASSES, dtype=np.float64)[y_true]

    per_step: list[dict[str, float | int]] = []
    for pred_batch, part in frame.partition_by("pred_batch", as_dict=True).items():
        batch = int(pred_batch[0] if isinstance(pred_batch, tuple) else pred_batch)
        part_true = part["y_true"].to_numpy().astype(np.int32, copy=False)
        part_pred = part["y_pred"].to_numpy().astype(np.int32, copy=False)
        same_direction = (part_true >= 2) == (part_pred >= 2)
        per_step.append(
            {
                "pred_batch": batch,
                "rows": len(part),
                "accuracy": float(accuracy_score(part_true, part_pred)),
                "macro_f1": float(
                    f1_score(part_true, part_pred, labels=list(range(N_CLASSES)), average="macro", zero_division=0)
                ),
                "direction_accuracy": float(same_direction.mean()),
                "cross_direction_error": float(1.0 - same_direction.mean()),
            }
        )
    per_step.sort(key=lambda row: int(row["pred_batch"]))
    direction_values = np.array([row["direction_accuracy"] for row in per_step], dtype=float)
    worst_steps = sorted(per_step, key=lambda row: (float(row["direction_accuracy"]), int(row["pred_batch"])))[:5]

    return {
        "rows": len(frame),
        "steps": frame["pred_batch"].n_unique(),
        "batch_min": int(frame["pred_batch"].min()),
        "batch_max": int(frame["pred_batch"].max()),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "macro_f1": float(
            f1_score(y_true, y_pred, labels=list(range(N_CLASSES)), average="macro", zero_division=0)
        ),
        "direction_accuracy": float((y_true_dir == y_pred_dir).mean()),
        "cross_direction_error": float((y_true_dir != y_pred_dir).mean()),
        "logloss": float(log_loss(y_true, probabilities, labels=list(range(N_CLASSES)))),
        "brier_score": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=list(range(N_CLASSES))).tolist(),
        "direction_confusion_matrix": confusion_matrix(y_true_dir, y_pred_dir, labels=[0, 1]).tolist(),
        "step_summary": {
            "mean_accuracy": float(np.mean([row["accuracy"] for row in per_step])),
            "mean_macro_f1": float(np.mean([row["macro_f1"] for row in per_step])),
            "mean_direction_accuracy": float(direction_values.mean()),
            "median_direction_accuracy": float(np.median(direction_values)),
            "min_direction_accuracy": float(direction_values.min()),
            "steps_below_50pct_direction_accuracy": int((direction_values < 0.50).sum()),
            "worst_steps": worst_steps,
        },
    }


def _fmt(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{float(value):.4f}"


def _metric_row(name: str, metrics: dict[str, Any]) -> str:
    return (
        f"| {name} | {metrics['steps']} | {metrics['rows']:,} | "
        f"{_fmt(metrics['accuracy'])} | {_fmt(metrics['macro_f1'])} | "
        f"{_fmt(metrics['direction_accuracy'])} | {_fmt(metrics['cross_direction_error'])} | "
        f"{_fmt(metrics['logloss'])} | {_fmt(metrics['brier_score'])} |"
    )


def _metric_delta_row(
    *,
    candidate_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any],
) -> str:
    def delta(metric: str) -> str:
        cand = candidate_metrics.get(metric)
        base = baseline_metrics.get(metric)
        if cand is None or base is None:
            return "-"
        return f"{float(cand) - float(base):+.4f}"

    return (
        "| Candidate - baseline | "
        f"{delta('accuracy')} | {delta('macro_f1')} | "
        f"{delta('direction_accuracy')} | {delta('cross_direction_error')} | "
        f"{delta('logloss')} | {delta('brier_score')} |"
    )


def _matrix_lines(matrix: list[list[int]]) -> list[str]:
    return ["```text", *[str(row) for row in matrix], "```"]


def write_report(
    *,
    report_path: Path,
    baseline: RunSpec,
    candidate: RunSpec,
    baseline_full: dict[str, Any],
    candidate_full: dict[str, Any],
    baseline_common: dict[str, Any],
    candidate_common: dict[str, Any],
    common_batches: list[int],
    baseline_loaded: LoadedPredictions,
    candidate_loaded: LoadedPredictions,
) -> None:
    full_comparable = (
        baseline_full["steps"] == candidate_full["steps"]
        and common_batches
        and len(common_batches) == candidate_full["steps"]
    )
    lines = [
        "# BTCUSDT 8h/B Target Survey: Completed-Run Metrics",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Scope: Stage-1 held-out selected-action prediction payloads, no TA flags, "
        "no anomaly overlay, `core-ex-target` context.",
        "",
        "## Coverage",
        "",
        "| Run | Target | Steps | Batch Range | Rows |",
        "|---|---|---:|---|---:|",
        f"| Baseline | `{baseline.target_col}` | {baseline_full['steps']} | "
        f"{baseline_full.get('batch_min')}..{baseline_full.get('batch_max')} | {baseline_full['rows']:,} |",
        f"| Candidate | `{candidate.target_col}` | {candidate_full['steps']} | "
        f"{candidate_full.get('batch_min')}..{candidate_full.get('batch_max')} | {candidate_full['rows']:,} |",
        "",
        "Executed/scorable coverage:",
        "",
        "| Run | Executed Steps | Scorable Selected-Model Steps | No-Winner Steps |",
        "|---|---:|---:|---:|",
        f"| Baseline | {baseline_loaded.attempted_steps} | {baseline_loaded.scorable_steps} | {len(baseline_loaded.no_winner_steps)} |",
        f"| Candidate | {candidate_loaded.attempted_steps} | {candidate_loaded.scorable_steps} | {len(candidate_loaded.no_winner_steps)} |",
        "",
    ]
    if full_comparable:
        lines.append("The full runs cover identical prediction batches and are directly comparable.")
    else:
        lines.extend(
            [
                "**Full-run comparison is not yet fair:** the baseline does not cover the "
                "candidate's full prediction-batch set. Only the overlapping batches below "
                "are a direct comparison.",
                "",
                f"Common prediction batches: `{common_batches}`",
            ]
        )
    if candidate_loaded.no_winner_steps:
        lines.extend(
            [
                "",
                "**Candidate coverage warning:** some requested Stage-1 steps produced no "
                "winner and no scorable prediction because all grid combinations failed. "
                "Review the recorded failure reasons below before comparing full-run metrics.",
                "",
                f"Candidate no-winner steps: `{len(candidate_loaded.no_winner_steps)}`",
                "",
                "Most frequent recorded failure reasons:",
                "",
            ]
        )
        top_reasons = sorted(
            candidate_loaded.fail_reasons.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
        lines.extend([f"- `{reason}`: {count}" for reason, count in top_reasons])
    lines.extend(
        [
            "",
            "## Candidate Scorable Full-Scope Metrics",
            "",
            "| Run | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            _metric_row(candidate.target_col, candidate_full),
            "",
            "Candidate confusion matrix, rows=true class and columns=predicted class:",
            "",
            *_matrix_lines(candidate_full["confusion_matrix"]),
            "",
            "Candidate direction confusion matrix, rows=true direction `[DOWN, UP]`:",
            "",
            *_matrix_lines(candidate_full["direction_confusion_matrix"]),
            "",
            "Candidate step stability:",
            "",
            f"- Mean step direction accuracy: `{_fmt(candidate_full['step_summary']['mean_direction_accuracy'])}`",
            f"- Median step direction accuracy: `{_fmt(candidate_full['step_summary']['median_direction_accuracy'])}`",
            f"- Minimum step direction accuracy: `{_fmt(candidate_full['step_summary']['min_direction_accuracy'])}`",
            f"- Steps below 50% direction accuracy: `{candidate_full['step_summary']['steps_below_50pct_direction_accuracy']}/{candidate_full['steps']}`",
            "",
            "Worst five candidate steps by direction accuracy:",
            "",
            "| Batch | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in candidate_full["step_summary"]["worst_steps"]:
        lines.append(
            f"| {row['pred_batch']} | {row['rows']} | {_fmt(row['accuracy'])} | "
            f"{_fmt(row['macro_f1'])} | {_fmt(row['direction_accuracy'])} | "
            f"{_fmt(row['cross_direction_error'])} |"
        )
    lines.extend(
        [
            "",
            "## Direct Overlap Comparison",
            "",
            "| Target | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            _metric_row(baseline.target_col, baseline_common),
            _metric_row(candidate.target_col, candidate_common),
            "",
            "Metric deltas on overlapping prediction batches:",
            "",
            "| Comparison | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |",
            "|---|---:|---:|---:|---:|---:|---:|",
            _metric_delta_row(
                candidate_metrics=candidate_common,
                baseline_metrics=baseline_common,
            ),
            "",
            "## Decision",
            "",
        ]
    )
    if full_comparable:
        accuracy_up = float(candidate_common["accuracy"]) > float(baseline_common["accuracy"])
        macro_f1_up = float(candidate_common["macro_f1"]) >= float(baseline_common["macro_f1"])
        direction_up = float(candidate_common["direction_accuracy"]) >= float(
            baseline_common["direction_accuracy"]
        )
        cross_error_down = float(candidate_common["cross_direction_error"]) <= float(
            baseline_common["cross_direction_error"]
        )
        if accuracy_up and macro_f1_up and direction_up and cross_error_down:
            lines.append(
                "Promote the candidate to the next validation stage. It improves or "
                "matches the required direction-sensitive acceptance metrics over the "
                "complete comparable scope."
            )
        else:
            lines.extend(
                [
                    "Do not promote the candidate as the default Stage-1 target yet. "
                    "The full runs are directly comparable, and the candidate improves "
                    "plain four-class accuracy and macro F1, but it does not pass the "
                    "direction-sensitive acceptance gate.",
                    "",
                    "Required acceptance gate:",
                    "",
                    "- accuracy up",
                    "- macro F1 stable or up",
                    "- direction accuracy stable or up",
                    "- cross-direction error stable or down",
                    "",
                    "Use this result as evidence that `tb_atr_wide_v2` improves class "
                    "separability, then continue with target diagnostics focused on "
                    "direction mistakes before applying anomaly overlays or expanding "
                    "to other roots.",
                ]
            )
    else:
        lines.extend(
            [
                "Do not promote the candidate based on this comparison yet. The candidate "
                "has a completed 250-step result, but legacy has only two matching steps. "
                "Run the legacy target over the same 250-step scope, then rerun this report.",
                "",
                "Required legacy baseline command:",
                "",
                "```bash",
                "python scripts/analysis/htf_stage1_regime_family_walkforward.py \\",
                "  --build-merged-dataset \\",
                "  --stage1-target-col target_4class \\",
                "  --target-assets BTCUSDT \\",
                "  --context-assets core-ex-target \\",
                "  --roots 8h/B \\",
                "  --n-steps 250 \\",
                "  --resume-mode skip_completed \\",
                "  --runtime-mode routine",
                "```",
            ]
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Stage-1 target-survey held-out predictions.")
    parser.add_argument(
        "--baseline-run-id",
        default="stage1_catboost_btcusdt_8h_b_ctx_corexself_live",
    )
    parser.add_argument("--baseline-target-col", default="target_4class")
    parser.add_argument(
        "--candidate-run-id",
        default="stage1_catboost_btcusdt_8h_b_ctx_corexself_target_tb_atr_wide_v2_live",
    )
    parser.add_argument("--candidate-target-col", default="target_4class_tb_atr_wide_v2")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=PROJECT_ROOT
        / "docs"
        / "research"
        / "tb-target-survey-8h-b-btcusdt-comparison-2026-05-26.md",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=PROJECT_ROOT
        / "test_output"
        / "stage1_target_survey_metrics"
        / "btcusdt_8h_b_tb_atr_wide_v2_metrics.json",
    )
    args = parser.parse_args()

    baseline = RunSpec("baseline", args.baseline_run_id, args.baseline_target_col)
    candidate = RunSpec("candidate", args.candidate_run_id, args.candidate_target_col)
    baseline_loaded = load_selected_predictions(PROJECT_ROOT, baseline)
    candidate_loaded = load_selected_predictions(PROJECT_ROOT, candidate)
    baseline_frame = baseline_loaded.frame
    candidate_frame = candidate_loaded.frame
    baseline_batches = set(baseline_frame["pred_batch"].unique().to_list())
    candidate_batches = set(candidate_frame["pred_batch"].unique().to_list())
    common_batches = sorted(int(batch) for batch in baseline_batches & candidate_batches)
    if not common_batches:
        raise ValueError("Baseline and candidate runs have no shared prediction batches.")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline": {
            "run_id": baseline.run_id,
            "target_col": baseline.target_col,
            "attempted_steps": baseline_loaded.attempted_steps,
            "scorable_steps": baseline_loaded.scorable_steps,
            "no_winner_steps": list(baseline_loaded.no_winner_steps),
            "full": compute_metrics(baseline_frame),
            "common_batches": compute_metrics(
                baseline_frame.filter(pl.col("pred_batch").is_in(common_batches))
            ),
        },
        "candidate": {
            "run_id": candidate.run_id,
            "target_col": candidate.target_col,
            "attempted_steps": candidate_loaded.attempted_steps,
            "scorable_steps": candidate_loaded.scorable_steps,
            "no_winner_steps": list(candidate_loaded.no_winner_steps),
            "fail_reasons": candidate_loaded.fail_reasons,
            "full": compute_metrics(candidate_frame),
            "common_batches": compute_metrics(
                candidate_frame.filter(pl.col("pred_batch").is_in(common_batches))
            ),
        },
        "comparison": {
            "common_batches": common_batches,
            "full_batch_coverage_equal": baseline_batches == candidate_batches,
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(output, indent=2))
    write_report(
        report_path=args.report_path,
        baseline=baseline,
        candidate=candidate,
        baseline_full=output["baseline"]["full"],
        candidate_full=output["candidate"]["full"],
        baseline_common=output["baseline"]["common_batches"],
        candidate_common=output["candidate"]["common_batches"],
        common_batches=common_batches,
        baseline_loaded=baseline_loaded,
        candidate_loaded=candidate_loaded,
    )
    print(
        f"Candidate scorable steps: {candidate_loaded.scorable_steps}/"
        f"{candidate_loaded.attempted_steps}"
    )
    print(
        f"Baseline scorable steps: {baseline_loaded.scorable_steps}/"
        f"{baseline_loaded.attempted_steps}"
    )
    print(f"Common batches: {common_batches}")
    print(f"Candidate direction accuracy: {output['candidate']['full']['direction_accuracy']:.4f}")
    print(f"Candidate cross-direction error: {output['candidate']['full']['cross_direction_error']:.4f}")
    print(f"Report: {args.report_path}")
    print(f"JSON: {args.json_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

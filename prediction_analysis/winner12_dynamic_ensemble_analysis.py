#!/usr/bin/env python3
"""Dynamic ensemble analysis over winner-12 configs per prediction batch.

This script combines:
  1) `winner12_predictions_filtered.parquet` from probability analysis
  2) `winner12_heuristic_probability_matrix.parquet` from heuristic analysis

It evaluates whether using top-K posterior combos as a weighted ensemble can
improve metrics vs a single top-1 combo pick.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _resolve_latest_run(base: Path) -> Path:
    runs = sorted([p for p in base.glob("*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs found in: {base}")
    return runs[-1].resolve()


def _resolve_run_dir(
    base: Path,
    run_dir: str | None,
) -> Path:
    if run_dir:
        direct = Path(run_dir).expanduser()
        if direct.exists():
            return direct.resolve()
        child = base / run_dir
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(f"Run dir not found: {run_dir!r} (checked {direct}, {child})")
    return _resolve_latest_run(base)


def _parse_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise ValueError(f"unit must be <timeframe>/<target>, got {unit!r}")
    return unit.split("/", 1)


def _compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = np.asarray(y_pred, dtype=np.int32)
    if y_true.size == 0:
        return {
            "accuracy": 0.0,
            "macro_recall": 0.0,
            "macro_f1": 0.0,
            "cross_direction_error": 0.0,
        }

    acc = float(np.mean(y_true == y_pred))
    recalls = []
    f1s = []
    for c in range(4):
        true_c = y_true == c
        pred_c = y_pred == c
        tp = int(np.sum(true_c & pred_c))
        fp = int(np.sum((~true_c) & pred_c))
        support = int(np.sum(true_c))
        recall = float(tp / support) if support > 0 else 0.0
        precision = float(tp / (tp + fp)) if (tp + fp) > 0 else 0.0
        f1 = (
            float(2.0 * precision * recall / (precision + recall))
            if (precision + recall) > 0
            else 0.0
        )
        recalls.append(recall)
        f1s.append(f1)

    true_up = y_true >= 2
    true_down = y_true <= 1
    pred_up = y_pred >= 2
    pred_down = y_pred <= 1
    cross_err = float(np.mean((true_up & pred_down) | (true_down & pred_up)))
    return {
        "accuracy": acc,
        "macro_recall": float(np.mean(recalls)),
        "macro_f1": float(np.mean(f1s)),
        "cross_direction_error": cross_err,
    }


def _normalize_weights(weights: list[tuple[str, float]]) -> list[tuple[str, float]]:
    arr = np.asarray([max(0.0, float(w)) for _, w in weights], dtype=np.float64)
    s = float(arr.sum())
    if s <= 0:
        arr = np.full_like(arr, 1.0 / len(arr))
    else:
        arr = arr / s
    return [(weights[i][0], float(arr[i])) for i in range(len(weights))]


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    heuristic_run_dir: str | None,
    top_k: int,
    posterior_min: float,
    min_combos: int,
    output_dir: Path,
) -> dict[str, Any]:
    tf, target = _parse_unit(unit)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    prob_base = project_root / "prediction_analysis" / "winner12_probability_outputs"
    heur_base = project_root / "prediction_analysis" / "winner12_live_probability_outputs"
    prob_dir = _resolve_run_dir(prob_base, probability_run_dir)
    heur_dir = _resolve_run_dir(heur_base, heuristic_run_dir)

    pred_rows_path = prob_dir / "winner12_predictions_filtered.parquet"
    matrix_path = heur_dir / "winner12_heuristic_probability_matrix.parquet"
    winners_path = unit_dir / "winners_all_steps.parquet"
    if not pred_rows_path.exists():
        raise FileNotFoundError(f"Missing: {pred_rows_path}")
    if not matrix_path.exists():
        raise FileNotFoundError(f"Missing: {matrix_path}")
    if not winners_path.exists():
        raise FileNotFoundError(f"Missing: {winners_path}")

    pred_rows = pl.read_parquet(pred_rows_path).sort(
        ["pred_batch", "action_key", "timestamp", "batch_id"]
    )
    matrix = pl.read_parquet(matrix_path).sort(["pred_batch", "posterior_prob"], descending=[False, True])
    winners = (
        pl.read_parquet(winners_path)
        .drop_nulls(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .select(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .unique(subset=["pred_batch"], keep="last")
        .sort("pred_batch")
    )

    required_pred_cols = {
        "pred_batch",
        "timestamp",
        "batch_id",
        "action_key",
        "y_true",
        "y_pred",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    }
    missing_pred = sorted(list(required_pred_cols - set(pred_rows.columns)))
    if missing_pred:
        raise ValueError(f"Missing columns in {pred_rows_path}: {missing_pred}")

    required_matrix_cols = {"pred_batch", "action_key", "posterior_prob"}
    missing_m = sorted(list(required_matrix_cols - set(matrix.columns)))
    if missing_m:
        raise ValueError(f"Missing columns in {matrix_path}: {missing_m}")

    winners_map = {
        int(r["pred_batch"]): (str(r["winner_combo_key"]), float(r["winner_accuracy"]))
        for r in winners.to_dicts()
    }

    top_k = int(max(1, top_k))
    min_combos = int(max(1, min(min_combos, top_k)))
    posterior_min = float(max(0.0, min(1.0, posterior_min)))

    batch_rows = []
    row_frames: list[pl.DataFrame] = []
    by_batch = pred_rows.group_by("pred_batch", maintain_order=True)
    for key, batch_pred in by_batch:
        pred_batch = int(key[0])
        m = (
            matrix.filter(pl.col("pred_batch") == pred_batch)
            .select(["action_key", "posterior_prob"])
            .sort("posterior_prob", descending=True)
        )
        if m.is_empty():
            continue

        top_list = m.head(top_k).to_dicts()
        selected = [r for r in top_list if float(r["posterior_prob"]) >= posterior_min]
        if len(selected) < min_combos:
            selected = top_list[:min_combos]
        if len(selected) == 0:
            selected = top_list[:1]

        selected_weights = _normalize_weights(
            [(str(r["action_key"]), float(r["posterior_prob"])) for r in selected]
        )
        selected_keys = [k for k, _ in selected_weights]
        weights_df = pl.DataFrame(
            {"action_key": selected_keys, "weight": [w for _, w in selected_weights]}
        )

        # Single-model baseline: top1 posterior
        top1_combo = str(top_list[0]["action_key"])
        top1_df = batch_pred.filter(pl.col("action_key") == top1_combo).select(
            ["pred_batch", "timestamp", "batch_id", "y_true", "y_pred"]
        )
        y_true_top1 = top1_df["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred_top1 = top1_df["y_pred"].to_numpy().astype(np.int32, copy=False)
        top1_metrics = _compute_metrics(y_true_top1, y_pred_top1)

        # Ensemble over selected combos
        ens_input = batch_pred.join(weights_df, on="action_key", how="inner")
        ens_rows = (
            ens_input.group_by(["pred_batch", "timestamp", "batch_id", "y_true"])
            .agg(
                [
                    (pl.col("prob_class_0") * pl.col("weight")).sum().alias("w0"),
                    (pl.col("prob_class_1") * pl.col("weight")).sum().alias("w1"),
                    (pl.col("prob_class_2") * pl.col("weight")).sum().alias("w2"),
                    (pl.col("prob_class_3") * pl.col("weight")).sum().alias("w3"),
                    pl.col("weight").sum().alias("weight_sum"),
                    pl.col("action_key").n_unique().alias("selected_combos_present"),
                ]
            )
            .with_columns(
                [
                    (pl.col("w0") / pl.col("weight_sum")).alias("p0"),
                    (pl.col("w1") / pl.col("weight_sum")).alias("p1"),
                    (pl.col("w2") / pl.col("weight_sum")).alias("p2"),
                    (pl.col("w3") / pl.col("weight_sum")).alias("p3"),
                ]
            )
            .with_columns(pl.max_horizontal(["p0", "p1", "p2", "p3"]).alias("pmax"))
            .with_columns(
                pl.when(pl.col("p0") == pl.col("pmax"))
                .then(0)
                .when(pl.col("p1") == pl.col("pmax"))
                .then(1)
                .when(pl.col("p2") == pl.col("pmax"))
                .then(2)
                .otherwise(3)
                .alias("y_pred_ensemble")
            )
            .with_columns(
                [
                    pl.lit(top1_combo).alias("top1_combo"),
                    pl.lit("|".join(selected_keys)).alias("selected_combos"),
                    pl.lit("|".join([f"{k}:{w:.6f}" for k, w in selected_weights])).alias(
                        "selected_weights"
                    ),
                    pl.lit(float(top_list[0]["posterior_prob"])).alias("top1_posterior"),
                ]
            )
            .sort(["timestamp", "batch_id"])
        )

        y_true_ens = ens_rows["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred_ens = ens_rows["y_pred_ensemble"].to_numpy().astype(np.int32, copy=False)
        ens_metrics = _compute_metrics(y_true_ens, y_pred_ens)

        winner_combo, winner_acc = winners_map.get(pred_batch, (None, None))
        row_frames.append(ens_rows)
        batch_rows.append(
            {
                "pred_batch": pred_batch,
                "rows": int(len(ens_rows)),
                "top1_combo": top1_combo,
                "selected_combos_count": int(len(selected_keys)),
                "selected_combos": "|".join(selected_keys),
                "selected_weights": "|".join([f"{k}:{w:.6f}" for k, w in selected_weights]),
                "top1_posterior": float(top_list[0]["posterior_prob"]),
                "winner_combo_key": winner_combo,
                "winner_accuracy": winner_acc,
                "top1_accuracy": float(top1_metrics["accuracy"]),
                "top1_macro_f1": float(top1_metrics["macro_f1"]),
                "top1_cross_direction_error": float(top1_metrics["cross_direction_error"]),
                "ensemble_accuracy": float(ens_metrics["accuracy"]),
                "ensemble_macro_f1": float(ens_metrics["macro_f1"]),
                "ensemble_cross_direction_error": float(
                    ens_metrics["cross_direction_error"]
                ),
                "delta_accuracy": float(ens_metrics["accuracy"] - top1_metrics["accuracy"]),
                "delta_macro_f1": float(ens_metrics["macro_f1"] - top1_metrics["macro_f1"]),
                "delta_cross_direction_error": float(
                    ens_metrics["cross_direction_error"]
                    - top1_metrics["cross_direction_error"]
                ),
                "ensemble_beats_top1_accuracy": bool(
                    ens_metrics["accuracy"] > top1_metrics["accuracy"]
                ),
                "ensemble_beats_top1_macro_f1": bool(
                    ens_metrics["macro_f1"] > top1_metrics["macro_f1"]
                ),
                "ensemble_better_cross_direction_error": bool(
                    ens_metrics["cross_direction_error"]
                    < top1_metrics["cross_direction_error"]
                ),
            }
        )

    if not batch_rows:
        raise ValueError("No batch rows produced. Check source files and filters.")

    batch_metrics_df = pl.DataFrame(batch_rows).sort("pred_batch")
    row_predictions_df = pl.concat(row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "source": {
            "probability_run_dir": str(prob_dir),
            "heuristic_run_dir": str(heur_dir),
            "pred_rows_path": str(pred_rows_path),
            "matrix_path": str(matrix_path),
            "winners_path": str(winners_path),
        },
        "selection_config": {
            "top_k": top_k,
            "posterior_min": posterior_min,
            "min_combos": min_combos,
        },
        "rows": {
            "batches": int(len(batch_metrics_df)),
            "ensemble_rows": int(len(row_predictions_df)),
        },
        "metrics": {
            "mean_top1_accuracy": float(batch_metrics_df["top1_accuracy"].mean()),
            "mean_ensemble_accuracy": float(batch_metrics_df["ensemble_accuracy"].mean()),
            "mean_delta_accuracy": float(batch_metrics_df["delta_accuracy"].mean()),
            "mean_top1_macro_f1": float(batch_metrics_df["top1_macro_f1"].mean()),
            "mean_ensemble_macro_f1": float(batch_metrics_df["ensemble_macro_f1"].mean()),
            "mean_delta_macro_f1": float(batch_metrics_df["delta_macro_f1"].mean()),
            "mean_top1_cross_direction_error": float(
                batch_metrics_df["top1_cross_direction_error"].mean()
            ),
            "mean_ensemble_cross_direction_error": float(
                batch_metrics_df["ensemble_cross_direction_error"].mean()
            ),
            "mean_delta_cross_direction_error": float(
                batch_metrics_df["delta_cross_direction_error"].mean()
            ),
            "share_ensemble_beats_top1_accuracy": float(
                batch_metrics_df["ensemble_beats_top1_accuracy"]
                .cast(pl.Int8, strict=False)
                .mean()
            ),
            "share_ensemble_beats_top1_macro_f1": float(
                batch_metrics_df["ensemble_beats_top1_macro_f1"]
                .cast(pl.Int8, strict=False)
                .mean()
            ),
            "share_ensemble_better_cross_direction_error": float(
                batch_metrics_df["ensemble_better_cross_direction_error"]
                .cast(pl.Int8, strict=False)
                .mean()
            ),
        },
    }

    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    batch_metrics_parquet = out_run / "winner12_dynamic_ensemble_batch_metrics.parquet"
    batch_metrics_csv = out_run / "winner12_dynamic_ensemble_batch_metrics.csv"
    row_predictions_parquet = out_run / "winner12_dynamic_ensemble_row_predictions.parquet"
    row_predictions_csv = out_run / "winner12_dynamic_ensemble_row_predictions.csv"
    summary_json = out_run / "winner12_dynamic_ensemble_summary.json"

    batch_metrics_df.write_parquet(batch_metrics_parquet)
    batch_metrics_df.write_csv(batch_metrics_csv)
    row_predictions_df.write_parquet(row_predictions_parquet)
    row_predictions_df.write_csv(row_predictions_csv)

    summary["artifacts"] = {
        "winner12_dynamic_ensemble_batch_metrics_parquet": str(batch_metrics_parquet),
        "winner12_dynamic_ensemble_batch_metrics_csv": str(batch_metrics_csv),
        "winner12_dynamic_ensemble_row_predictions_parquet": str(row_predictions_parquet),
        "winner12_dynamic_ensemble_row_predictions_csv": str(row_predictions_csv),
        "winner12_dynamic_ensemble_summary_json": str(summary_json),
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Evaluate dynamic top-K posterior ensemble over winner-12 combos."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--heuristic-run-dir", type=str, default=None)
    p.add_argument("--top-k", type=int, default=3)
    p.add_argument("--posterior-min", type=float, default=0.0)
    p.add_argument("--min-combos", type=int, default=2)
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Default: <project_root>/prediction_analysis/"
            "winner12_dynamic_ensemble_outputs"
        ),
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_dynamic_ensemble_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        heuristic_run_dir=args.heuristic_run_dir,
        top_k=int(args.top_k),
        posterior_min=float(args.posterior_min),
        min_combos=int(args.min_combos),
        output_dir=output_dir,
    )

    m = summary["metrics"]
    print("Winner-12 dynamic ensemble analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(
        "  Accuracy: "
        f"top1_mean={m['mean_top1_accuracy']:.4f}, "
        f"ensemble_mean={m['mean_ensemble_accuracy']:.4f}, "
        f"delta={m['mean_delta_accuracy']:+.4f}"
    )
    print(
        "  Macro-F1: "
        f"top1_mean={m['mean_top1_macro_f1']:.4f}, "
        f"ensemble_mean={m['mean_ensemble_macro_f1']:.4f}, "
        f"delta={m['mean_delta_macro_f1']:+.4f}"
    )
    print(
        "  Cross-dir-error: "
        f"top1_mean={m['mean_top1_cross_direction_error']:.4f}, "
        f"ensemble_mean={m['mean_ensemble_cross_direction_error']:.4f}, "
        f"delta={m['mean_delta_cross_direction_error']:+.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()


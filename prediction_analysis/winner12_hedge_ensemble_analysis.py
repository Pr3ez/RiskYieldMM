#!/usr/bin/env python3
"""Online expert-weighted ensemble (Hedge) over winner-12 combo predictions.

This script uses stored prediction rows from:
  prediction_analysis/winner12_probability_outputs/<run>/winner12_predictions_filtered.parquet

It runs a live-style sequential update:
  - At batch t: build ensemble using weights learned up to batch t-1.
  - After batch t closes: update expert weights from batch-t losses.
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


def _resolve_run_dir(base: Path, run_dir: str | None) -> Path:
    if run_dir:
        direct = Path(run_dir).expanduser()
        if direct.exists():
            return direct.resolve()
        child = base / run_dir
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"Run dir not found: {run_dir!r} (checked {direct}, {child})"
        )
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


def _prob_true_expr(eps: float) -> pl.Expr:
    return (
        pl.when(pl.col("y_true") == 0)
        .then(pl.col("prob_class_0"))
        .when(pl.col("y_true") == 1)
        .then(pl.col("prob_class_1"))
        .when(pl.col("y_true") == 2)
        .then(pl.col("prob_class_2"))
        .otherwise(pl.col("prob_class_3"))
        .clip(lower_bound=float(eps), upper_bound=1.0)
        .alias("prob_true")
    )


def _softmax_weights(log_weights: dict[str, float], keys: list[str]) -> dict[str, float]:
    arr = np.asarray([float(log_weights[k]) for k in keys], dtype=np.float64)
    arr = arr - float(np.max(arr))
    e = np.exp(arr)
    s = float(np.sum(e))
    if s <= 0.0 or (not np.isfinite(s)):
        u = 1.0 / len(keys)
        return {k: u for k in keys}
    e = e / s
    return {keys[i]: float(e[i]) for i in range(len(keys))}


def _argmax_class_expr(prefix: str, output_col: str) -> pl.Expr:
    c0 = f"{prefix}0"
    c1 = f"{prefix}1"
    c2 = f"{prefix}2"
    c3 = f"{prefix}3"
    pmax = f"{prefix}max"
    return (
        pl.when(pl.col(c0) == pl.col(pmax))
        .then(0)
        .when(pl.col(c1) == pl.col(pmax))
        .then(1)
        .when(pl.col(c2) == pl.col(pmax))
        .then(2)
        .otherwise(3)
        .alias(output_col)
    )


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    eta: float,
    loss_type: str,
    output_dir: Path,
) -> dict[str, Any]:
    tf, target = _parse_unit(unit)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    prob_base = project_root / "prediction_analysis" / "winner12_probability_outputs"
    prob_dir = _resolve_run_dir(prob_base, probability_run_dir)

    pred_rows_path = prob_dir / "winner12_predictions_filtered.parquet"
    winners_path = unit_dir / "winners_all_steps.parquet"
    if not pred_rows_path.exists():
        raise FileNotFoundError(f"Missing: {pred_rows_path}")
    if not winners_path.exists():
        raise FileNotFoundError(f"Missing: {winners_path}")

    pred_rows = pl.read_parquet(pred_rows_path).sort(
        ["pred_batch", "action_key", "timestamp", "batch_id"]
    )
    winners = (
        pl.read_parquet(winners_path)
        .drop_nulls(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .select(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .unique(subset=["pred_batch"], keep="last")
        .sort("pred_batch")
    )
    winners_map = {
        int(r["pred_batch"]): (str(r["winner_combo_key"]), float(r["winner_accuracy"]))
        for r in winners.to_dicts()
    }

    required = {
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
    missing = sorted(list(required - set(pred_rows.columns)))
    if missing:
        raise ValueError(f"Missing columns in {pred_rows_path}: {missing}")

    combo_keys = sorted(pred_rows["action_key"].unique().to_list())
    if not combo_keys:
        raise ValueError("No combos found in prediction rows.")

    eta = float(max(0.0, eta))
    loss_type = str(loss_type).strip().lower()
    if loss_type not in {"nll", "error"}:
        raise ValueError(f"Unsupported loss_type={loss_type!r}, expected one of: nll,error")

    log_weights = {k: 0.0 for k in combo_keys}
    batch_rows: list[dict[str, Any]] = []
    weight_rows: list[dict[str, Any]] = []
    row_frames: list[pl.DataFrame] = []

    by_batch = pred_rows.group_by("pred_batch", maintain_order=True)
    for key, batch_pred in by_batch:
        pred_batch = int(key[0])
        present_keys = sorted(batch_pred["action_key"].unique().to_list())
        weight_before_map = _softmax_weights(log_weights, present_keys)
        wdf = pl.DataFrame(
            {
                "action_key": present_keys,
                "weight_before": [weight_before_map[k] for k in present_keys],
            }
        )

        weighted = batch_pred.join(wdf, on="action_key", how="inner")

        # Hedge weighted ensemble
        hedge_rows = (
            weighted.group_by(["pred_batch", "timestamp", "batch_id", "y_true"])
            .agg(
                [
                    (pl.col("prob_class_0") * pl.col("weight_before")).sum().alias("hw0"),
                    (pl.col("prob_class_1") * pl.col("weight_before")).sum().alias("hw1"),
                    (pl.col("prob_class_2") * pl.col("weight_before")).sum().alias("hw2"),
                    (pl.col("prob_class_3") * pl.col("weight_before")).sum().alias("hw3"),
                    pl.col("weight_before").sum().alias("weight_sum"),
                    pl.col("action_key").n_unique().alias("combos_present"),
                ]
            )
            .with_columns(
                [
                    (pl.col("hw0") / pl.col("weight_sum")).alias("hedge_p0"),
                    (pl.col("hw1") / pl.col("weight_sum")).alias("hedge_p1"),
                    (pl.col("hw2") / pl.col("weight_sum")).alias("hedge_p2"),
                    (pl.col("hw3") / pl.col("weight_sum")).alias("hedge_p3"),
                ]
            )
            .with_columns(
                pl.max_horizontal(["hedge_p0", "hedge_p1", "hedge_p2", "hedge_p3"]).alias(
                    "hedge_pmax"
                )
            )
            .with_columns(_argmax_class_expr("hedge_p", "y_pred_hedge"))
            .sort(["timestamp", "batch_id"])
        )

        # Uniform ensemble baseline
        uniform_rows = (
            batch_pred.group_by(["pred_batch", "timestamp", "batch_id", "y_true"])
            .agg(
                [
                    pl.col("prob_class_0").mean().alias("uniform_p0"),
                    pl.col("prob_class_1").mean().alias("uniform_p1"),
                    pl.col("prob_class_2").mean().alias("uniform_p2"),
                    pl.col("prob_class_3").mean().alias("uniform_p3"),
                ]
            )
            .with_columns(
                pl.max_horizontal(
                    ["uniform_p0", "uniform_p1", "uniform_p2", "uniform_p3"]
                ).alias("uniform_pmax")
            )
            .with_columns(_argmax_class_expr("uniform_p", "y_pred_uniform"))
            .select(["pred_batch", "timestamp", "batch_id", "y_pred_uniform"])
            .sort(["timestamp", "batch_id"])
        )

        # Top-weight single combo baseline
        top_combo = max(
            present_keys,
            key=lambda k: (float(weight_before_map[k]), k),
        )
        top_combo_rows = (
            batch_pred.filter(pl.col("action_key") == top_combo)
            .select(["pred_batch", "timestamp", "batch_id", "y_pred"])
            .rename({"y_pred": "y_pred_top_combo"})
            .sort(["timestamp", "batch_id"])
        )

        row_batch = (
            hedge_rows.join(uniform_rows, on=["pred_batch", "timestamp", "batch_id"], how="left")
            .join(top_combo_rows, on=["pred_batch", "timestamp", "batch_id"], how="left")
            .with_columns(
                [
                    pl.lit(top_combo).alias("top_weight_combo"),
                    pl.lit(float(weight_before_map[top_combo])).alias("top_weight_before"),
                ]
            )
        )
        row_frames.append(row_batch)

        y_true = row_batch["y_true"].to_numpy().astype(np.int32, copy=False)
        y_pred_hedge = row_batch["y_pred_hedge"].to_numpy().astype(np.int32, copy=False)
        y_pred_uniform = row_batch["y_pred_uniform"].to_numpy().astype(np.int32, copy=False)
        y_pred_top_combo = row_batch["y_pred_top_combo"].to_numpy().astype(
            np.int32, copy=False
        )

        hedge_metrics = _compute_metrics(y_true, y_pred_hedge)
        uniform_metrics = _compute_metrics(y_true, y_pred_uniform)
        top_combo_metrics = _compute_metrics(y_true, y_pred_top_combo)

        combo_batch_acc = (
            batch_pred.group_by("action_key")
            .agg((pl.col("y_true") == pl.col("y_pred")).mean().alias("accuracy"))
            .sort(["accuracy", "action_key"], descending=[True, False])
        )
        oracle_combo = str(combo_batch_acc.item(0, "action_key"))
        oracle_acc = float(combo_batch_acc.item(0, "accuracy"))

        # Losses used to update expert weights after observing this batch
        with_prob_true = batch_pred.with_columns(_prob_true_expr(eps=1e-12))
        loss_df = with_prob_true.group_by("action_key").agg(
            [
                (-(pl.col("prob_true")).log()).mean().alias("loss_nll"),
                (pl.col("y_true") != pl.col("y_pred")).mean().alias("loss_error"),
                pl.len().alias("rows"),
            ]
        )
        loss_map = {
            str(r["action_key"]): (
                float(r["loss_nll"]) if loss_type == "nll" else float(r["loss_error"])
            )
            for r in loss_df.to_dicts()
        }

        for k in present_keys:
            log_weights[k] = float(log_weights[k]) - eta * float(loss_map.get(k, 0.0))

        # Stabilize exponent range by shifting max to zero
        max_logw = max(float(v) for v in log_weights.values())
        for k in combo_keys:
            log_weights[k] = float(log_weights[k]) - max_logw

        weight_after_map = _softmax_weights(log_weights, combo_keys)
        for k in combo_keys:
            weight_rows.append(
                {
                    "pred_batch": pred_batch,
                    "action_key": k,
                    "weight_before": float(weight_before_map.get(k, 0.0)),
                    "weight_after": float(weight_after_map.get(k, 0.0)),
                    "batch_loss_used": float(loss_map.get(k, 0.0)),
                    "batch_loss_nll": float(
                        loss_df.filter(pl.col("action_key") == k)
                        .select("loss_nll")
                        .item(0, 0)
                        if k in loss_map
                        else np.nan
                    ),
                    "batch_loss_error": float(
                        loss_df.filter(pl.col("action_key") == k)
                        .select("loss_error")
                        .item(0, 0)
                        if k in loss_map
                        else np.nan
                    ),
                    "eta": eta,
                    "loss_type": loss_type,
                }
            )

        winner_combo, winner_acc = winners_map.get(pred_batch, (None, None))
        batch_rows.append(
            {
                "pred_batch": pred_batch,
                "rows": int(len(row_batch)),
                "combos_present": int(len(present_keys)),
                "winner_combo_key": winner_combo,
                "winner_accuracy": winner_acc,
                "top_weight_combo": top_combo,
                "top_weight_before": float(weight_before_map[top_combo]),
                "oracle_best_combo": oracle_combo,
                "oracle_best_combo_accuracy": oracle_acc,
                "hedge_accuracy": float(hedge_metrics["accuracy"]),
                "hedge_macro_recall": float(hedge_metrics["macro_recall"]),
                "hedge_macro_f1": float(hedge_metrics["macro_f1"]),
                "hedge_cross_direction_error": float(hedge_metrics["cross_direction_error"]),
                "uniform_accuracy": float(uniform_metrics["accuracy"]),
                "uniform_macro_f1": float(uniform_metrics["macro_f1"]),
                "uniform_cross_direction_error": float(
                    uniform_metrics["cross_direction_error"]
                ),
                "top_combo_accuracy": float(top_combo_metrics["accuracy"]),
                "top_combo_macro_f1": float(top_combo_metrics["macro_f1"]),
                "top_combo_cross_direction_error": float(
                    top_combo_metrics["cross_direction_error"]
                ),
                "delta_hedge_vs_uniform_accuracy": float(
                    hedge_metrics["accuracy"] - uniform_metrics["accuracy"]
                ),
                "delta_hedge_vs_top_combo_accuracy": float(
                    hedge_metrics["accuracy"] - top_combo_metrics["accuracy"]
                ),
                "delta_hedge_vs_oracle_accuracy": float(
                    hedge_metrics["accuracy"] - oracle_acc
                ),
                "delta_hedge_vs_uniform_macro_f1": float(
                    hedge_metrics["macro_f1"] - uniform_metrics["macro_f1"]
                ),
                "delta_hedge_vs_top_combo_macro_f1": float(
                    hedge_metrics["macro_f1"] - top_combo_metrics["macro_f1"]
                ),
                "delta_hedge_vs_uniform_cross_direction_error": float(
                    hedge_metrics["cross_direction_error"]
                    - uniform_metrics["cross_direction_error"]
                ),
                "delta_hedge_vs_top_combo_cross_direction_error": float(
                    hedge_metrics["cross_direction_error"]
                    - top_combo_metrics["cross_direction_error"]
                ),
                "hedge_beats_uniform_accuracy": bool(
                    hedge_metrics["accuracy"] > uniform_metrics["accuracy"]
                ),
                "hedge_beats_top_combo_accuracy": bool(
                    hedge_metrics["accuracy"] > top_combo_metrics["accuracy"]
                ),
            }
        )

    if not batch_rows:
        raise ValueError("No batch metrics produced. Check source files.")

    batch_metrics_df = pl.DataFrame(batch_rows).sort("pred_batch")
    weight_history_df = pl.DataFrame(weight_rows).sort(["pred_batch", "action_key"])
    row_predictions_df = pl.concat(row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )

    final_weights = (
        weight_history_df.filter(
            pl.col("pred_batch") == int(batch_metrics_df["pred_batch"].max())
        )
        .select(["action_key", "weight_after"])
        .sort("weight_after", descending=True)
    )

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "source": {
            "probability_run_dir": str(prob_dir),
            "pred_rows_path": str(pred_rows_path),
            "winners_path": str(winners_path),
        },
        "config": {
            "eta": eta,
            "loss_type": loss_type,
            "combos": combo_keys,
        },
        "rows": {
            "batches": int(len(batch_metrics_df)),
            "row_predictions": int(len(row_predictions_df)),
            "weight_history_rows": int(len(weight_history_df)),
        },
        "metrics": {
            "mean_hedge_accuracy": float(batch_metrics_df["hedge_accuracy"].mean()),
            "mean_uniform_accuracy": float(batch_metrics_df["uniform_accuracy"].mean()),
            "mean_top_combo_accuracy": float(batch_metrics_df["top_combo_accuracy"].mean()),
            "mean_oracle_best_combo_accuracy": float(
                batch_metrics_df["oracle_best_combo_accuracy"].mean()
            ),
            "mean_hedge_macro_f1": float(batch_metrics_df["hedge_macro_f1"].mean()),
            "mean_uniform_macro_f1": float(batch_metrics_df["uniform_macro_f1"].mean()),
            "mean_top_combo_macro_f1": float(batch_metrics_df["top_combo_macro_f1"].mean()),
            "mean_hedge_cross_direction_error": float(
                batch_metrics_df["hedge_cross_direction_error"].mean()
            ),
            "mean_uniform_cross_direction_error": float(
                batch_metrics_df["uniform_cross_direction_error"].mean()
            ),
            "mean_top_combo_cross_direction_error": float(
                batch_metrics_df["top_combo_cross_direction_error"].mean()
            ),
            "mean_delta_hedge_vs_uniform_accuracy": float(
                batch_metrics_df["delta_hedge_vs_uniform_accuracy"].mean()
            ),
            "mean_delta_hedge_vs_top_combo_accuracy": float(
                batch_metrics_df["delta_hedge_vs_top_combo_accuracy"].mean()
            ),
            "mean_delta_hedge_vs_uniform_macro_f1": float(
                batch_metrics_df["delta_hedge_vs_uniform_macro_f1"].mean()
            ),
            "mean_delta_hedge_vs_top_combo_macro_f1": float(
                batch_metrics_df["delta_hedge_vs_top_combo_macro_f1"].mean()
            ),
            "share_hedge_beats_uniform_accuracy": float(
                batch_metrics_df["hedge_beats_uniform_accuracy"]
                .cast(pl.Int8, strict=False)
                .mean()
            ),
            "share_hedge_beats_top_combo_accuracy": float(
                batch_metrics_df["hedge_beats_top_combo_accuracy"]
                .cast(pl.Int8, strict=False)
                .mean()
            ),
        },
        "final_weights_top12": final_weights.to_dicts(),
    }

    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    batch_metrics_parquet = out_run / "winner12_hedge_batch_metrics.parquet"
    batch_metrics_csv = out_run / "winner12_hedge_batch_metrics.csv"
    row_predictions_parquet = out_run / "winner12_hedge_row_predictions.parquet"
    row_predictions_csv = out_run / "winner12_hedge_row_predictions.csv"
    weight_history_parquet = out_run / "winner12_hedge_weight_history.parquet"
    weight_history_csv = out_run / "winner12_hedge_weight_history.csv"
    summary_json = out_run / "winner12_hedge_summary.json"

    batch_metrics_df.write_parquet(batch_metrics_parquet)
    batch_metrics_df.write_csv(batch_metrics_csv)
    row_predictions_df.write_parquet(row_predictions_parquet)
    row_predictions_df.write_csv(row_predictions_csv)
    weight_history_df.write_parquet(weight_history_parquet)
    weight_history_df.write_csv(weight_history_csv)

    summary["artifacts"] = {
        "winner12_hedge_batch_metrics_parquet": str(batch_metrics_parquet),
        "winner12_hedge_batch_metrics_csv": str(batch_metrics_csv),
        "winner12_hedge_row_predictions_parquet": str(row_predictions_parquet),
        "winner12_hedge_row_predictions_csv": str(row_predictions_csv),
        "winner12_hedge_weight_history_parquet": str(weight_history_parquet),
        "winner12_hedge_weight_history_csv": str(weight_history_csv),
        "winner12_hedge_summary_json": str(summary_json),
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Online Hedge ensemble analysis over winner-12 predictions."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--eta", type=float, default=2.0)
    p.add_argument("--loss-type", type=str, default="nll", choices=["nll", "error"])
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Default: <project_root>/prediction_analysis/winner12_hedge_outputs",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_hedge_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        eta=float(args.eta),
        loss_type=str(args.loss_type),
        output_dir=output_dir,
    )

    m = summary["metrics"]
    print("Winner-12 Hedge ensemble analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(f"  eta={summary['config']['eta']:.4f} | loss_type={summary['config']['loss_type']}")
    print(
        "  Accuracy: "
        f"hedge={m['mean_hedge_accuracy']:.4f}, "
        f"uniform={m['mean_uniform_accuracy']:.4f}, "
        f"top_combo={m['mean_top_combo_accuracy']:.4f}, "
        f"oracle={m['mean_oracle_best_combo_accuracy']:.4f}"
    )
    print(
        "  Macro-F1: "
        f"hedge={m['mean_hedge_macro_f1']:.4f}, "
        f"uniform={m['mean_uniform_macro_f1']:.4f}, "
        f"top_combo={m['mean_top_combo_macro_f1']:.4f}"
    )
    print(
        "  Cross-dir-error: "
        f"hedge={m['mean_hedge_cross_direction_error']:.4f}, "
        f"uniform={m['mean_uniform_cross_direction_error']:.4f}, "
        f"top_combo={m['mean_top_combo_cross_direction_error']:.4f}"
    )
    print(
        "  Hedge lift shares: "
        f"vs_uniform={m['share_hedge_beats_uniform_accuracy']:.4f}, "
        f"vs_top_combo={m['share_hedge_beats_top_combo_accuracy']:.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()


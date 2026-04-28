#!/usr/bin/env python3
"""Walk-forward stacking meta-learner over winner-12 combo probabilities.

Approach:
  - Build row-level live-safe features from 12 combo probability vectors.
  - Train a multinomial logistic model on past batches only.
  - Predict the next batch (walk-forward), no lookahead.
  - Compare against uniform 12-combo probability ensemble.
"""

from __future__ import annotations

import argparse
import json
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


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


def _argmax_4(p0: np.ndarray, p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> np.ndarray:
    mat = np.column_stack([p0, p1, p2, p3]).astype(np.float64, copy=False)
    return np.argmax(mat, axis=1).astype(np.int32, copy=False)


def _fit_model(
    X: np.ndarray,
    y: np.ndarray,
    *,
    c_value: float,
    max_iter: int,
    random_seed: int,
) -> Pipeline:
    pipe = Pipeline(
        steps=[
            ("scaler", StandardScaler(with_mean=True, with_std=True)),
            (
                "clf",
                LogisticRegression(
                    solver="lbfgs",
                    C=float(max(1e-6, c_value)),
                    max_iter=int(max(50, max_iter)),
                    random_state=int(random_seed),
                ),
            ),
        ]
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        pipe.fit(X, y)
    return pipe


def _batch_metrics_table(
    *,
    pred_batches: np.ndarray,
    y_true: np.ndarray,
    y_pred_model: np.ndarray,
    y_pred_uniform: np.ndarray,
    oracle_map: dict[int, tuple[str, float]],
    winner_map: dict[int, tuple[str, float]],
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for pb in sorted(np.unique(pred_batches).tolist()):
        mask = pred_batches == pb
        yt = y_true[mask]
        ym = y_pred_model[mask]
        yu = y_pred_uniform[mask]
        mm = _compute_metrics(yt, ym)
        mu = _compute_metrics(yt, yu)
        oracle_combo, oracle_acc = oracle_map.get(int(pb), (None, np.nan))
        winner_combo, winner_acc = winner_map.get(int(pb), (None, np.nan))
        rows.append(
            {
                "pred_batch": int(pb),
                "rows": int(np.sum(mask)),
                "winner_combo_key": winner_combo,
                "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
                "oracle_best_combo": oracle_combo,
                "oracle_best_combo_accuracy": float(oracle_acc)
                if oracle_acc == oracle_acc
                else None,
                "model_accuracy": float(mm["accuracy"]),
                "uniform_accuracy": float(mu["accuracy"]),
                "model_macro_f1": float(mm["macro_f1"]),
                "uniform_macro_f1": float(mu["macro_f1"]),
                "model_cross_direction_error": float(mm["cross_direction_error"]),
                "uniform_cross_direction_error": float(mu["cross_direction_error"]),
                "delta_accuracy_model_vs_uniform": float(mm["accuracy"] - mu["accuracy"]),
                "delta_macro_f1_model_vs_uniform": float(mm["macro_f1"] - mu["macro_f1"]),
                "delta_cross_direction_error_model_vs_uniform": float(
                    mm["cross_direction_error"] - mu["cross_direction_error"]
                ),
                "delta_accuracy_model_vs_oracle": float(mm["accuracy"] - float(oracle_acc))
                if oracle_acc == oracle_acc
                else None,
                "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
            }
        )
    return pl.DataFrame(rows).sort("pred_batch")


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    holdout_steps: int,
    wf_warmup_steps: int,
    wf_retrain_every_steps: int,
    max_train_batches: int | None,
    c_value: float,
    max_iter: int,
    random_seed: int,
    output_dir: Path,
    verbose: bool,
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
    required_cols = {
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
    missing_cols = sorted(list(required_cols - set(pred_rows.columns)))
    if missing_cols:
        raise ValueError(f"Missing columns in {pred_rows_path}: {missing_cols}")

    winners = (
        pl.read_parquet(winners_path)
        .drop_nulls(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .select(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .unique(subset=["pred_batch"], keep="last")
        .sort("pred_batch")
    )
    winner_map = {
        int(r["pred_batch"]): (str(r["winner_combo_key"]), float(r["winner_accuracy"]))
        for r in winners.to_dicts()
    }

    combo_keys = sorted(pred_rows["action_key"].unique().to_list())
    combo_count = len(combo_keys)
    if combo_count == 0:
        raise ValueError("No combos found in prediction rows.")

    if verbose:
        print(f"[Stacking] rows={len(pred_rows)} combos={combo_count} source={pred_rows_path}")

    # Build oracle reference by batch (best single combo hindsight).
    oracle_df = (
        pred_rows.group_by(["pred_batch", "action_key"])
        .agg((pl.col("y_true") == pl.col("y_pred")).mean().alias("combo_accuracy"))
        .sort(["pred_batch", "combo_accuracy", "action_key"], descending=[False, True, False])
        .group_by("pred_batch")
        .agg(
            [
                pl.col("action_key").first().alias("oracle_best_combo"),
                pl.col("combo_accuracy").first().alias("oracle_best_combo_accuracy"),
            ]
        )
        .sort("pred_batch")
    )
    oracle_map = {
        int(r["pred_batch"]): (
            str(r["oracle_best_combo"]),
            float(r["oracle_best_combo_accuracy"]),
        )
        for r in oracle_df.to_dicts()
    }

    # Build row-level feature table, one row per (batch,timestamp,batch_id).
    agg_exprs: list[pl.Expr] = [
        pl.col("y_true").first().alias("y_true"),
        pl.col("action_key").n_unique().alias("combos_present"),
    ]
    for combo in combo_keys:
        for c in range(4):
            agg_exprs.append(
                pl.col(f"prob_class_{c}")
                .filter(pl.col("action_key") == combo)
                .first()
                .alias(f"{combo}_p{c}")
            )

    row_df = (
        pred_rows.group_by(["pred_batch", "timestamp", "batch_id"], maintain_order=True)
        .agg(agg_exprs)
        .filter(pl.col("combos_present") == combo_count)
        .sort(["pred_batch", "timestamp", "batch_id"])
    )
    if row_df.is_empty():
        raise ValueError("No row-level features after filtering for full combo coverage.")

    for c in range(4):
        cols = [f"{combo}_p{c}" for combo in combo_keys]
        row_df = row_df.with_columns(pl.mean_horizontal(cols).alias(f"uniform_p{c}"))
    row_df = row_df.with_columns(
        pl.max_horizontal(["uniform_p0", "uniform_p1", "uniform_p2", "uniform_p3"]).alias(
            "uniform_pmax"
        )
    )
    row_df = row_df.with_columns(
        pl.when(pl.col("uniform_p0") == pl.col("uniform_pmax"))
        .then(0)
        .when(pl.col("uniform_p1") == pl.col("uniform_pmax"))
        .then(1)
        .when(pl.col("uniform_p2") == pl.col("uniform_pmax"))
        .then(2)
        .otherwise(3)
        .alias("y_pred_uniform")
    )

    feature_cols = [f"{combo}_p{c}" for combo in combo_keys for c in range(4)]
    for col in feature_cols:
        if col not in row_df.columns:
            raise ValueError(f"Missing feature column: {col}")

    # Prepare arrays.
    X = row_df.select(feature_cols).to_numpy().astype(np.float32, copy=False)
    y = row_df["y_true"].to_numpy().astype(np.int32, copy=False)
    pred_batches = row_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
    uniform_pred = row_df["y_pred_uniform"].to_numpy().astype(np.int32, copy=False)
    timestamps = row_df["timestamp"].to_numpy()
    batch_ids = row_df["batch_id"].to_numpy().astype(np.int32, copy=False)

    uniq_batches = np.asarray(sorted(np.unique(pred_batches).tolist()), dtype=np.int32)
    n_batches = int(len(uniq_batches))
    if n_batches < 10:
        raise ValueError(f"Not enough batches: {n_batches}")

    holdout_steps = int(max(1, min(holdout_steps, n_batches - 1)))
    train_batches_static = uniq_batches[:-holdout_steps]
    holdout_batches = uniq_batches[-holdout_steps:]

    train_mask_static = np.isin(pred_batches, train_batches_static)
    holdout_mask = np.isin(pred_batches, holdout_batches)

    t0 = time.time()
    holdout_model = _fit_model(
        X[train_mask_static],
        y[train_mask_static],
        c_value=float(c_value),
        max_iter=int(max_iter),
        random_seed=int(random_seed),
    )
    holdout_fit_s = time.time() - t0
    holdout_pred = holdout_model.predict(X[holdout_mask]).astype(np.int32, copy=False)
    holdout_uniform = uniform_pred[holdout_mask]
    holdout_y = y[holdout_mask]
    holdout_batches_arr = pred_batches[holdout_mask]

    holdout_metrics_model = _compute_metrics(holdout_y, holdout_pred)
    holdout_metrics_uniform = _compute_metrics(holdout_y, holdout_uniform)
    holdout_batch_df = _batch_metrics_table(
        pred_batches=holdout_batches_arr,
        y_true=holdout_y,
        y_pred_model=holdout_pred,
        y_pred_uniform=holdout_uniform,
        oracle_map=oracle_map,
        winner_map=winner_map,
    ).with_columns(pl.lit("holdout").alias("mode"))

    holdout_row_df = pl.DataFrame(
        {
            "pred_batch": holdout_batches_arr,
            "timestamp": timestamps[holdout_mask],
            "batch_id": batch_ids[holdout_mask],
            "y_true": holdout_y,
            "y_pred_model": holdout_pred,
            "y_pred_uniform": holdout_uniform,
        }
    ).sort(["pred_batch", "timestamp", "batch_id"])

    # Walk-forward evaluation (live-style).
    wf_warmup_steps = int(max(1, min(wf_warmup_steps, n_batches - 1)))
    wf_retrain_every_steps = int(max(1, wf_retrain_every_steps))
    max_train_batches = (
        None if (max_train_batches is None or max_train_batches <= 0) else int(max_train_batches)
    )

    idx_by_batch: dict[int, np.ndarray] = {
        int(pb): np.where(pred_batches == int(pb))[0] for pb in uniq_batches.tolist()
    }

    wf_pred_batches: list[int] = []
    wf_y_true: list[np.ndarray] = []
    wf_y_pred: list[np.ndarray] = []
    wf_y_pred_uniform: list[np.ndarray] = []
    wf_row_frames: list[pl.DataFrame] = []

    curr_model: Pipeline | None = None
    retrain_counter = 0
    wf_batch_rows: list[dict[str, Any]] = []

    for i in range(wf_warmup_steps, n_batches):
        pb = int(uniq_batches[i])
        hist_batches = uniq_batches[:i]
        if max_train_batches is not None and len(hist_batches) > max_train_batches:
            hist_batches = hist_batches[-max_train_batches:]

        should_retrain = curr_model is None or ((i - wf_warmup_steps) % wf_retrain_every_steps == 0)
        fit_s = 0.0
        if should_retrain:
            t_fit = time.time()
            train_mask = np.isin(pred_batches, hist_batches)
            curr_model = _fit_model(
                X[train_mask],
                y[train_mask],
                c_value=float(c_value),
                max_iter=int(max_iter),
                random_seed=int(random_seed),
            )
            fit_s = time.time() - t_fit
            retrain_counter += 1

        pred_idx = idx_by_batch[pb]
        pred_true = y[pred_idx]
        pred_uniform = uniform_pred[pred_idx]
        pred_model = curr_model.predict(X[pred_idx]).astype(np.int32, copy=False)

        wf_pred_batches.append(pb)
        wf_y_true.append(pred_true)
        wf_y_pred.append(pred_model)
        wf_y_pred_uniform.append(pred_uniform)

        mm = _compute_metrics(pred_true, pred_model)
        mu = _compute_metrics(pred_true, pred_uniform)
        oracle_combo, oracle_acc = oracle_map.get(pb, (None, np.nan))
        winner_combo, winner_acc = winner_map.get(pb, (None, np.nan))
        wf_batch_rows.append(
            {
                "pred_batch": pb,
                "rows": int(len(pred_idx)),
                "winner_combo_key": winner_combo,
                "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
                "oracle_best_combo": oracle_combo,
                "oracle_best_combo_accuracy": float(oracle_acc)
                if oracle_acc == oracle_acc
                else None,
                "model_accuracy": float(mm["accuracy"]),
                "uniform_accuracy": float(mu["accuracy"]),
                "model_macro_f1": float(mm["macro_f1"]),
                "uniform_macro_f1": float(mu["macro_f1"]),
                "model_cross_direction_error": float(mm["cross_direction_error"]),
                "uniform_cross_direction_error": float(mu["cross_direction_error"]),
                "delta_accuracy_model_vs_uniform": float(mm["accuracy"] - mu["accuracy"]),
                "delta_macro_f1_model_vs_uniform": float(mm["macro_f1"] - mu["macro_f1"]),
                "delta_cross_direction_error_model_vs_uniform": float(
                    mm["cross_direction_error"] - mu["cross_direction_error"]
                ),
                "delta_accuracy_model_vs_oracle": float(mm["accuracy"] - float(oracle_acc))
                if oracle_acc == oracle_acc
                else None,
                "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
                "retrained_this_step": bool(should_retrain),
                "fit_time_s": float(fit_s),
                "train_batches_used": int(len(hist_batches)),
            }
        )

        wf_row_frames.append(
            pl.DataFrame(
                {
                    "pred_batch": np.full(len(pred_idx), pb, dtype=np.int32),
                    "timestamp": timestamps[pred_idx],
                    "batch_id": batch_ids[pred_idx],
                    "y_true": pred_true,
                    "y_pred_model": pred_model,
                    "y_pred_uniform": pred_uniform,
                }
            )
        )

        if verbose and ((i - wf_warmup_steps + 1) % 25 == 0):
            done = i - wf_warmup_steps + 1
            total = n_batches - wf_warmup_steps
            print(
                f"[Stacking][WF] step={done}/{total} pred_batch={pb} "
                f"retrained={int(should_retrain)} model_acc={mm['accuracy']:.4f}"
            )

    wf_y_true_all = np.concatenate(wf_y_true).astype(np.int32, copy=False)
    wf_y_pred_all = np.concatenate(wf_y_pred).astype(np.int32, copy=False)
    wf_uniform_all = np.concatenate(wf_y_pred_uniform).astype(np.int32, copy=False)
    wf_metrics_model = _compute_metrics(wf_y_true_all, wf_y_pred_all)
    wf_metrics_uniform = _compute_metrics(wf_y_true_all, wf_uniform_all)

    wf_batch_df = pl.DataFrame(wf_batch_rows).sort("pred_batch").with_columns(
        pl.lit("walkforward").alias("mode")
    )
    wf_row_df = pl.concat(wf_row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )

    # Save artifacts.
    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    feature_table_parquet = out_run / "winner12_stacking_feature_table.parquet"
    feature_columns_json = out_run / "winner12_stacking_feature_columns.json"
    holdout_batch_parquet = out_run / "winner12_stacking_holdout_batch_metrics.parquet"
    holdout_batch_csv = out_run / "winner12_stacking_holdout_batch_metrics.csv"
    holdout_rows_parquet = out_run / "winner12_stacking_holdout_row_predictions.parquet"
    wf_batch_parquet = out_run / "winner12_stacking_walkforward_batch_metrics.parquet"
    wf_batch_csv = out_run / "winner12_stacking_walkforward_batch_metrics.csv"
    wf_rows_parquet = out_run / "winner12_stacking_walkforward_row_predictions.parquet"
    summary_json = out_run / "winner12_stacking_summary.json"

    row_df.write_parquet(feature_table_parquet)
    holdout_batch_df.write_parquet(holdout_batch_parquet)
    holdout_batch_df.write_csv(holdout_batch_csv)
    holdout_row_df.write_parquet(holdout_rows_parquet)
    wf_batch_df.write_parquet(wf_batch_parquet)
    wf_batch_df.write_csv(wf_batch_csv)
    wf_row_df.write_parquet(wf_rows_parquet)

    with open(feature_columns_json, "w") as f:
        json.dump({"feature_columns": feature_cols}, f, indent=2)

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
            "holdout_steps": int(holdout_steps),
            "wf_warmup_steps": int(wf_warmup_steps),
            "wf_retrain_every_steps": int(wf_retrain_every_steps),
            "max_train_batches": int(max_train_batches) if max_train_batches else None,
            "logreg_c": float(c_value),
            "logreg_max_iter": int(max_iter),
            "random_seed": int(random_seed),
            "feature_count": int(len(feature_cols)),
            "combo_count": int(combo_count),
        },
        "rows": {
            "pred_rows_long": int(len(pred_rows)),
            "row_feature_rows": int(len(row_df)),
            "holdout_rows": int(len(holdout_row_df)),
            "walkforward_rows": int(len(wf_row_df)),
            "batches_total": int(n_batches),
            "batches_holdout": int(len(holdout_batches)),
            "batches_walkforward": int(len(wf_batch_df)),
        },
        "metrics": {
            "holdout": {
                "model": holdout_metrics_model,
                "uniform": holdout_metrics_uniform,
                "mean_delta_accuracy_model_vs_uniform": float(
                    holdout_batch_df["delta_accuracy_model_vs_uniform"].mean()
                ),
                "share_model_beats_uniform_accuracy": float(
                    holdout_batch_df["model_beats_uniform_accuracy"]
                    .cast(pl.Int8, strict=False)
                    .mean()
                ),
                "fit_time_s": float(holdout_fit_s),
            },
            "walkforward": {
                "model": wf_metrics_model,
                "uniform": wf_metrics_uniform,
                "mean_delta_accuracy_model_vs_uniform": float(
                    wf_batch_df["delta_accuracy_model_vs_uniform"].mean()
                ),
                "share_model_beats_uniform_accuracy": float(
                    wf_batch_df["model_beats_uniform_accuracy"]
                    .cast(pl.Int8, strict=False)
                    .mean()
                ),
                "retrain_count": int(retrain_counter),
                "mean_fit_time_s_when_retrain": float(
                    wf_batch_df.filter(pl.col("retrained_this_step"))
                    .select("fit_time_s")
                    .item()
                )
                if retrain_counter == 1
                else float(
                    wf_batch_df.filter(pl.col("retrained_this_step"))["fit_time_s"].mean()
                ),
            },
        },
        "artifacts": {
            "winner12_stacking_feature_table_parquet": str(feature_table_parquet),
            "winner12_stacking_feature_columns_json": str(feature_columns_json),
            "winner12_stacking_holdout_batch_metrics_parquet": str(holdout_batch_parquet),
            "winner12_stacking_holdout_batch_metrics_csv": str(holdout_batch_csv),
            "winner12_stacking_holdout_row_predictions_parquet": str(holdout_rows_parquet),
            "winner12_stacking_walkforward_batch_metrics_parquet": str(wf_batch_parquet),
            "winner12_stacking_walkforward_batch_metrics_csv": str(wf_batch_csv),
            "winner12_stacking_walkforward_row_predictions_parquet": str(wf_rows_parquet),
            "winner12_stacking_summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Walk-forward stacking meta-learner over winner-12 probabilities."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--holdout-steps", type=int, default=200)
    p.add_argument("--wf-warmup-steps", type=int, default=120)
    p.add_argument("--wf-retrain-every-steps", type=int, default=25)
    p.add_argument("--max-train-batches", type=int, default=0)
    p.add_argument("--c-value", type=float, default=1.0)
    p.add_argument("--max-iter", type=int, default=120)
    p.add_argument("--random-seed", type=int, default=42)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Default: <project_root>/prediction_analysis/winner12_stacking_outputs",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_stacking_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        holdout_steps=int(args.holdout_steps),
        wf_warmup_steps=int(args.wf_warmup_steps),
        wf_retrain_every_steps=int(args.wf_retrain_every_steps),
        max_train_batches=int(args.max_train_batches),
        c_value=float(args.c_value),
        max_iter=int(args.max_iter),
        random_seed=int(args.random_seed),
        output_dir=output_dir,
        verbose=bool(args.verbose),
    )

    hm = summary["metrics"]["holdout"]
    wm = summary["metrics"]["walkforward"]
    print("Winner-12 stacking meta analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(
        "  Holdout accuracy: "
        f"model={hm['model']['accuracy']:.4f}, "
        f"uniform={hm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Holdout macro_f1: "
        f"model={hm['model']['macro_f1']:.4f}, "
        f"uniform={hm['uniform']['macro_f1']:.4f}"
    )
    print(
        "  Walk-forward accuracy: "
        f"model={wm['model']['accuracy']:.4f}, "
        f"uniform={wm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Walk-forward macro_f1: "
        f"model={wm['model']['macro_f1']:.4f}, "
        f"uniform={wm['uniform']['macro_f1']:.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()

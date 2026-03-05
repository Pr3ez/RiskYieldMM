#!/usr/bin/env python3
"""Per-class specialist ensemble over winner-12 combos (live-style).

Method:
  - For each class, choose top specialist combos using past class recall.
  - Weight specialists by class recall.
  - At inference, class score is weighted sum of combo probabilities for that class.
"""

from __future__ import annotations

import argparse
import json
import time
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


def _fit_class_specialists(
    *,
    combo_pred: np.ndarray,  # [n_rows, combo_count]
    y_true: np.ndarray,  # [n_rows]
    specialists_per_class: int,
    recall_power: float,
    min_recall_floor: float,
) -> tuple[dict[int, tuple[np.ndarray, np.ndarray]], np.ndarray, np.ndarray]:
    combo_count = int(combo_pred.shape[1])
    k = int(max(1, min(specialists_per_class, combo_count)))
    rp = float(max(0.1, recall_power))
    floor = float(max(0.0, min(1.0, min_recall_floor)))

    # Fallback global specialist pool by overall accuracy
    global_acc = np.mean(combo_pred == y_true[:, None], axis=0)
    g_order = np.argsort(-global_acc, kind="mergesort")
    g_sel = g_order[:k]
    g_raw = np.power(np.clip(global_acc[g_sel] - floor, 1e-6, None), rp)
    g_w = g_raw / float(np.sum(g_raw))

    specialists: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    class_recall_matrix = np.zeros((4, combo_count), dtype=np.float64)
    class_support = np.zeros(4, dtype=np.int64)

    for c in range(4):
        mask = y_true == c
        support = int(np.sum(mask))
        class_support[c] = support
        if support <= 0:
            specialists[c] = (g_sel.astype(np.int32, copy=False), g_w.astype(np.float64, copy=False))
            continue
        recall_c = np.mean(combo_pred[mask] == c, axis=0)
        class_recall_matrix[c] = recall_c
        order = np.argsort(-recall_c, kind="mergesort")
        sel = order[:k]
        raw = np.power(np.clip(recall_c[sel] - floor, 1e-6, None), rp)
        sw = raw / float(np.sum(raw))
        specialists[c] = (sel.astype(np.int32, copy=False), sw.astype(np.float64, copy=False))

    return specialists, class_recall_matrix, class_support


def _predict_class_specialists(
    *,
    X_probs: np.ndarray,  # [n_rows, combo_count, 4]
    specialists: dict[int, tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    n_rows = int(X_probs.shape[0])
    score = np.zeros((n_rows, 4), dtype=np.float64)
    for c in range(4):
        idx, w = specialists[c]
        score[:, c] = np.tensordot(X_probs[:, idx, c], w, axes=(1, 0))
    y_pred = np.argmax(score, axis=1).astype(np.int32, copy=False)
    return y_pred, score


def _build_batch_metrics(
    *,
    pred_batches: np.ndarray,
    y_true: np.ndarray,
    y_pred_model: np.ndarray,
    y_pred_uniform: np.ndarray,
    winner_map: dict[int, tuple[str, float]],
    oracle_map: dict[int, tuple[str, float]],
    extra_by_batch: dict[str, dict[int, Any]] | None = None,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for pb in sorted(np.unique(pred_batches).tolist()):
        m = pred_batches == pb
        yt = y_true[m]
        ym = y_pred_model[m]
        yu = y_pred_uniform[m]
        mm = _compute_metrics(yt, ym)
        mu = _compute_metrics(yt, yu)
        winner_combo, winner_acc = winner_map.get(int(pb), (None, np.nan))
        oracle_combo, oracle_acc = oracle_map.get(int(pb), (None, np.nan))
        row = {
            "pred_batch": int(pb),
            "rows": int(np.sum(m)),
            "winner_combo_key": winner_combo,
            "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
            "oracle_best_combo": oracle_combo,
            "oracle_best_combo_accuracy": float(oracle_acc) if oracle_acc == oracle_acc else None,
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
            "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
        }
        if extra_by_batch:
            for k, mapping in extra_by_batch.items():
                row[k] = mapping.get(int(pb))
        rows.append(row)
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
    specialists_per_class: int,
    recall_power: float,
    min_recall_floor: float,
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
    req = {
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
    miss = sorted(list(req - set(pred_rows.columns)))
    if miss:
        raise ValueError(f"Missing columns in {pred_rows_path}: {miss}")

    combo_keys = sorted(pred_rows["action_key"].unique().to_list())
    combo_count = len(combo_keys)
    if combo_count == 0:
        raise ValueError("No combos in prediction rows.")
    if verbose:
        print(f"[ClassSpec] rows={len(pred_rows)} combos={combo_count} source={pred_rows_path}")

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

    # Row-level wide table
    agg_wide: list[pl.Expr] = [
        pl.col("y_true").first().alias("y_true"),
        pl.col("action_key").n_unique().alias("combos_present"),
    ]
    for combo in combo_keys:
        for c in range(4):
            agg_wide.append(
                pl.col(f"prob_class_{c}")
                .filter(pl.col("action_key") == combo)
                .first()
                .alias(f"{combo}_p{c}")
            )
    row_df = (
        pred_rows.group_by(["pred_batch", "timestamp", "batch_id"], maintain_order=True)
        .agg(agg_wide)
        .filter(pl.col("combos_present") == combo_count)
        .sort(["pred_batch", "timestamp", "batch_id"])
    )
    if row_df.is_empty():
        raise ValueError("No rows after full combo coverage filter.")

    # Uniform baseline
    for c in range(4):
        cols = [f"{combo}_p{c}" for combo in combo_keys]
        row_df = row_df.with_columns(pl.mean_horizontal(cols).alias(f"uniform_p{c}"))
    row_df = row_df.with_columns(
        pl.max_horizontal(["uniform_p0", "uniform_p1", "uniform_p2", "uniform_p3"]).alias(
            "uniform_pmax"
        )
    ).with_columns(
        pl.when(pl.col("uniform_p0") == pl.col("uniform_pmax"))
        .then(0)
        .when(pl.col("uniform_p1") == pl.col("uniform_pmax"))
        .then(1)
        .when(pl.col("uniform_p2") == pl.col("uniform_pmax"))
        .then(2)
        .otherwise(3)
        .alias("y_pred_uniform")
    )

    prob_feature_cols = [f"{combo}_p{c}" for combo in combo_keys for c in range(4)]
    X_flat = row_df.select(prob_feature_cols).to_numpy().astype(np.float32, copy=False)
    X_probs = X_flat.reshape((-1, combo_count, 4))
    combo_pred = np.argmax(X_probs, axis=2).astype(np.int32, copy=False)
    y_true = row_df["y_true"].to_numpy().astype(np.int32, copy=False)
    y_uniform = row_df["y_pred_uniform"].to_numpy().astype(np.int32, copy=False)
    pred_batches = row_df["pred_batch"].to_numpy().astype(np.int32, copy=False)
    timestamps = row_df["timestamp"].to_numpy()
    batch_ids = row_df["batch_id"].to_numpy().astype(np.int32, copy=False)

    uniq_batches = np.asarray(sorted(np.unique(pred_batches).tolist()), dtype=np.int32)
    n_batches = int(len(uniq_batches))
    holdout_steps = int(max(1, min(holdout_steps, n_batches - 1)))
    wf_warmup_steps = int(max(1, min(wf_warmup_steps, n_batches - 1)))
    wf_retrain_every_steps = int(max(1, wf_retrain_every_steps))
    max_train_batches = (
        None if (max_train_batches is None or max_train_batches <= 0) else int(max_train_batches)
    )

    # Static holdout fit
    train_batches_static = uniq_batches[:-holdout_steps]
    holdout_batches = uniq_batches[-holdout_steps:]
    train_mask_static = np.isin(pred_batches, train_batches_static)
    holdout_mask = np.isin(pred_batches, holdout_batches)

    t_fit = time.time()
    specialists_static, class_recall_static, class_support_static = _fit_class_specialists(
        combo_pred=combo_pred[train_mask_static],
        y_true=y_true[train_mask_static],
        specialists_per_class=int(specialists_per_class),
        recall_power=float(recall_power),
        min_recall_floor=float(min_recall_floor),
    )
    fit_static_s = time.time() - t_fit

    y_pred_holdout, score_holdout = _predict_class_specialists(
        X_probs=X_probs[holdout_mask],
        specialists=specialists_static,
    )
    holdout_metrics_model = _compute_metrics(y_true[holdout_mask], y_pred_holdout)
    holdout_metrics_uniform = _compute_metrics(y_true[holdout_mask], y_uniform[holdout_mask])

    holdout_batch_df = _build_batch_metrics(
        pred_batches=pred_batches[holdout_mask],
        y_true=y_true[holdout_mask],
        y_pred_model=y_pred_holdout,
        y_pred_uniform=y_uniform[holdout_mask],
        winner_map=winner_map,
        oracle_map=oracle_map,
    ).with_columns(pl.lit("holdout").alias("mode"))

    holdout_row_df = pl.DataFrame(
        {
            "pred_batch": pred_batches[holdout_mask],
            "timestamp": timestamps[holdout_mask],
            "batch_id": batch_ids[holdout_mask],
            "y_true": y_true[holdout_mask],
            "y_pred_model": y_pred_holdout,
            "y_pred_uniform": y_uniform[holdout_mask],
            "score_c0": score_holdout[:, 0],
            "score_c1": score_holdout[:, 1],
            "score_c2": score_holdout[:, 2],
            "score_c3": score_holdout[:, 3],
        }
    ).sort(["pred_batch", "timestamp", "batch_id"])

    # Walk-forward
    idx_by_batch = {int(pb): np.where(pred_batches == int(pb))[0] for pb in uniq_batches.tolist()}
    wf_batch_rows: list[dict[str, Any]] = []
    wf_row_frames: list[pl.DataFrame] = []
    history_rows: list[dict[str, Any]] = []
    retrain_count = 0
    current_spec: dict[int, tuple[np.ndarray, np.ndarray]] | None = None

    wf_true_list: list[np.ndarray] = []
    wf_pred_model_list: list[np.ndarray] = []
    wf_pred_uniform_list: list[np.ndarray] = []

    for i in range(wf_warmup_steps, n_batches):
        pb = int(uniq_batches[i])
        hist_batches = uniq_batches[:i]
        if max_train_batches is not None and len(hist_batches) > max_train_batches:
            hist_batches = hist_batches[-max_train_batches:]

        train_idx = np.where(np.isin(pred_batches, hist_batches))[0]
        pred_idx = idx_by_batch[pb]
        should_retrain = current_spec is None or ((i - wf_warmup_steps) % wf_retrain_every_steps == 0)
        fit_s = 0.0
        if should_retrain:
            t0 = time.time()
            current_spec, class_recall_now, class_support_now = _fit_class_specialists(
                combo_pred=combo_pred[train_idx],
                y_true=y_true[train_idx],
                specialists_per_class=int(specialists_per_class),
                recall_power=float(recall_power),
                min_recall_floor=float(min_recall_floor),
            )
            fit_s = time.time() - t0
            retrain_count += 1
            for c in range(4):
                idx_c, w_c = current_spec[c]
                history_rows.append(
                    {
                        "pred_batch": pb,
                        "history_type": "walkforward_retrain",
                        "class_id": int(c),
                        "train_batches_used": int(len(hist_batches)),
                        "class_support": int(class_support_now[c]),
                        "selected_combos": "|".join([combo_keys[j] for j in idx_c]),
                        "selected_count": int(len(idx_c)),
                        "weights": "|".join(
                            [f"{combo_keys[idx_c[k]]}:{w_c[k]:.6f}" for k in range(len(idx_c))]
                        ),
                        "fit_time_s": float(fit_s),
                    }
                )

        assert current_spec is not None
        pred_model, pred_score = _predict_class_specialists(
            X_probs=X_probs[pred_idx],
            specialists=current_spec,
        )
        yt = y_true[pred_idx]
        yu = y_uniform[pred_idx]
        mm = _compute_metrics(yt, pred_model)
        mu = _compute_metrics(yt, yu)

        wf_true_list.append(yt)
        wf_pred_model_list.append(pred_model)
        wf_pred_uniform_list.append(yu)

        winner_combo, winner_acc = winner_map.get(pb, (None, np.nan))
        oracle_combo, oracle_acc = oracle_map.get(pb, (None, np.nan))
        selected_c0 = "|".join([combo_keys[j] for j in current_spec[0][0]])
        selected_c1 = "|".join([combo_keys[j] for j in current_spec[1][0]])
        selected_c2 = "|".join([combo_keys[j] for j in current_spec[2][0]])
        selected_c3 = "|".join([combo_keys[j] for j in current_spec[3][0]])
        wf_batch_rows.append(
            {
                "pred_batch": pb,
                "rows": int(len(pred_idx)),
                "winner_combo_key": winner_combo,
                "winner_accuracy": float(winner_acc) if winner_acc == winner_acc else None,
                "oracle_best_combo": oracle_combo,
                "oracle_best_combo_accuracy": float(oracle_acc) if oracle_acc == oracle_acc else None,
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
                "model_beats_uniform_accuracy": bool(mm["accuracy"] > mu["accuracy"]),
                "selected_class0": selected_c0,
                "selected_class1": selected_c1,
                "selected_class2": selected_c2,
                "selected_class3": selected_c3,
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
                    "y_true": yt,
                    "y_pred_model": pred_model,
                    "y_pred_uniform": yu,
                    "score_c0": pred_score[:, 0],
                    "score_c1": pred_score[:, 1],
                    "score_c2": pred_score[:, 2],
                    "score_c3": pred_score[:, 3],
                }
            )
        )

        if verbose and ((i - wf_warmup_steps + 1) % 25 == 0):
            done = i - wf_warmup_steps + 1
            total = n_batches - wf_warmup_steps
            print(
                f"[ClassSpec][WF] step={done}/{total} pred_batch={pb} "
                f"retrain={int(should_retrain)} model_acc={mm['accuracy']:.4f}"
            )

    wf_true = np.concatenate(wf_true_list).astype(np.int32, copy=False)
    wf_pred_model = np.concatenate(wf_pred_model_list).astype(np.int32, copy=False)
    wf_pred_uniform = np.concatenate(wf_pred_uniform_list).astype(np.int32, copy=False)
    wf_metrics_model = _compute_metrics(wf_true, wf_pred_model)
    wf_metrics_uniform = _compute_metrics(wf_true, wf_pred_uniform)

    wf_batch_df = pl.DataFrame(wf_batch_rows).sort("pred_batch").with_columns(
        pl.lit("walkforward").alias("mode")
    )
    wf_row_df = pl.concat(wf_row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )

    # History rows for static holdout fit
    for c in range(4):
        idx_c, w_c = specialists_static[c]
        history_rows.insert(
            c,
            {
                "pred_batch": int(holdout_batches[0]),
                "history_type": "holdout_static_fit",
                "class_id": int(c),
                "train_batches_used": int(len(train_batches_static)),
                "class_support": int(class_support_static[c]),
                "selected_combos": "|".join([combo_keys[j] for j in idx_c]),
                "selected_count": int(len(idx_c)),
                "weights": "|".join([f"{combo_keys[idx_c[k]]}:{w_c[k]:.6f}" for k in range(len(idx_c))]),
                "fit_time_s": float(fit_static_s),
            },
        )
    history_df = pl.DataFrame(history_rows).sort(["pred_batch", "history_type", "class_id"])

    # Save
    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    holdout_batch_parquet = out_run / "winner12_classspec_holdout_batch_metrics.parquet"
    holdout_batch_csv = out_run / "winner12_classspec_holdout_batch_metrics.csv"
    holdout_rows_parquet = out_run / "winner12_classspec_holdout_row_predictions.parquet"
    wf_batch_parquet = out_run / "winner12_classspec_walkforward_batch_metrics.parquet"
    wf_batch_csv = out_run / "winner12_classspec_walkforward_batch_metrics.csv"
    wf_rows_parquet = out_run / "winner12_classspec_walkforward_row_predictions.parquet"
    history_parquet = out_run / "winner12_classspec_model_history.parquet"
    history_csv = out_run / "winner12_classspec_model_history.csv"
    summary_json = out_run / "winner12_classspec_summary.json"

    holdout_batch_df.write_parquet(holdout_batch_parquet)
    holdout_batch_df.write_csv(holdout_batch_csv)
    holdout_row_df.write_parquet(holdout_rows_parquet)
    wf_batch_df.write_parquet(wf_batch_parquet)
    wf_batch_df.write_csv(wf_batch_csv)
    wf_row_df.write_parquet(wf_rows_parquet)
    history_df.write_parquet(history_parquet)
    history_df.write_csv(history_csv)

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
            "specialists_per_class": int(specialists_per_class),
            "recall_power": float(recall_power),
            "min_recall_floor": float(min_recall_floor),
            "combo_count": int(combo_count),
            "combos": combo_keys,
        },
        "rows": {
            "pred_rows_long": int(len(pred_rows)),
            "row_feature_rows": int(len(row_df)),
            "holdout_rows": int(len(holdout_row_df)),
            "walkforward_rows": int(len(wf_row_df)),
            "batches_total": int(n_batches),
            "batches_holdout": int(len(holdout_batches)),
            "batches_walkforward": int(len(wf_batch_df)),
            "history_rows": int(len(history_df)),
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
                "retrain_count": int(retrain_count),
                "mean_fit_time_s_when_retrain": float(
                    wf_batch_df.filter(pl.col("retrained_this_step"))["fit_time_s"].mean()
                ),
            },
        },
        "artifacts": {
            "winner12_classspec_holdout_batch_metrics_parquet": str(holdout_batch_parquet),
            "winner12_classspec_holdout_batch_metrics_csv": str(holdout_batch_csv),
            "winner12_classspec_holdout_row_predictions_parquet": str(holdout_rows_parquet),
            "winner12_classspec_walkforward_batch_metrics_parquet": str(wf_batch_parquet),
            "winner12_classspec_walkforward_batch_metrics_csv": str(wf_batch_csv),
            "winner12_classspec_walkforward_row_predictions_parquet": str(wf_rows_parquet),
            "winner12_classspec_model_history_parquet": str(history_parquet),
            "winner12_classspec_model_history_csv": str(history_csv),
            "winner12_classspec_summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Per-class specialist analysis over winner-12 predictions."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--holdout-steps", type=int, default=200)
    p.add_argument("--wf-warmup-steps", type=int, default=120)
    p.add_argument("--wf-retrain-every-steps", type=int, default=25)
    p.add_argument("--max-train-batches", type=int, default=300)
    p.add_argument("--specialists-per-class", type=int, default=4)
    p.add_argument("--recall-power", type=float, default=1.0)
    p.add_argument("--min-recall-floor", type=float, default=0.20)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Default: <project_root>/prediction_analysis/winner12_class_specialist_outputs",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_class_specialist_outputs"
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
        specialists_per_class=int(args.specialists_per_class),
        recall_power=float(args.recall_power),
        min_recall_floor=float(args.min_recall_floor),
        output_dir=output_dir,
        verbose=bool(args.verbose),
    )

    hm = summary["metrics"]["holdout"]
    wm = summary["metrics"]["walkforward"]
    print("Winner-12 per-class specialist analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(
        "  Holdout accuracy: "
        f"model={hm['model']['accuracy']:.4f}, uniform={hm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Holdout macro_f1: "
        f"model={hm['model']['macro_f1']:.4f}, uniform={hm['uniform']['macro_f1']:.4f}"
    )
    print(
        "  Walk-forward accuracy: "
        f"model={wm['model']['accuracy']:.4f}, uniform={wm['uniform']['accuracy']:.4f}"
    )
    print(
        "  Walk-forward macro_f1: "
        f"model={wm['model']['macro_f1']:.4f}, uniform={wm['uniform']['macro_f1']:.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()


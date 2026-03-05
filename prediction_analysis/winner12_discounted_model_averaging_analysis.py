#!/usr/bin/env python3
"""Discounted model averaging (DMA-style) over winner-12 combos.

Live-style flow per pred_batch:
1) Predict with current combo weights.
2) Evaluate realized batch losses per combo (after outcomes are known).
3) Update combo weights with discounting + exponential loss penalty.
4) Optionally combine multiple discount factors (gamma grid) via meta-weights.
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


def _parse_gamma_grid(text: str) -> list[float]:
    vals = []
    for x in str(text).split(","):
        x = x.strip()
        if not x:
            continue
        v = float(x)
        if not (0.0 < v <= 1.0):
            raise ValueError(f"gamma must be in (0,1], got {v}")
        vals.append(v)
    if not vals:
        raise ValueError("gamma_grid is empty")
    return vals


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


def _normalized_entropy(p: np.ndarray) -> float:
    p = np.asarray(p, dtype=np.float64)
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    h = float(-np.sum(p * np.log(p)))
    return float(h / np.log(len(p))) if len(p) > 1 else 0.0


def _combo_batch_arrays(
    *,
    sub: pl.DataFrame,
    combo_keys: list[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return y_true, probs[n_rows,m,4], combo_pred[n_rows,m], row_ts, row_bid."""
    sub = sub.sort(["timestamp", "batch_id", "action_key"])
    combos = {str(k[0]): df.sort(["timestamp", "batch_id"]) for k, df in sub.group_by("action_key", maintain_order=True)}
    missing = [k for k in combo_keys if k not in combos]
    if missing:
        raise ValueError(f"Missing combos in batch: {missing}")

    first = combos[combo_keys[0]]
    n_rows = len(first)
    row_ts = first["timestamp"].to_numpy()
    row_bid = first["batch_id"].to_numpy().astype(np.int32, copy=False)
    y_true = first["y_true"].to_numpy().astype(np.int32, copy=False)

    m = len(combo_keys)
    probs = np.zeros((n_rows, m, 4), dtype=np.float64)
    combo_pred = np.zeros((n_rows, m), dtype=np.int32)
    for j, key in enumerate(combo_keys):
        df = combos[key]
        if len(df) != n_rows:
            raise ValueError(f"Combo {key} row mismatch: {len(df)} != {n_rows}")
        # Alignment guard
        if not np.array_equal(df["batch_id"].to_numpy().astype(np.int32, copy=False), row_bid):
            raise ValueError(f"Combo {key} row order mismatch on batch_id")
        p0 = df["prob_class_0"].to_numpy().astype(np.float64, copy=False)
        p1 = df["prob_class_1"].to_numpy().astype(np.float64, copy=False)
        p2 = df["prob_class_2"].to_numpy().astype(np.float64, copy=False)
        p3 = df["prob_class_3"].to_numpy().astype(np.float64, copy=False)
        probs[:, j, 0] = p0
        probs[:, j, 1] = p1
        probs[:, j, 2] = p2
        probs[:, j, 3] = p3
        combo_pred[:, j] = np.argmax(np.column_stack([p0, p1, p2, p3]), axis=1)
    return y_true, probs, combo_pred, row_ts, row_bid


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    gamma_grid: list[float],
    eta_model: float,
    eta_gamma: float,
    gamma_meta_discount: float,
    combo_loss_acc_weight: float,
    combo_loss_cde_weight: float,
    meta_loss_type: str,
    meta_loss_acc_weight: float,
    meta_loss_cde_weight: float,
    holdout_steps: int,
    min_weight_floor: float,
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
        ["pred_batch", "timestamp", "batch_id", "action_key"]
    )
    req = {
        "pred_batch",
        "timestamp",
        "batch_id",
        "action_key",
        "y_true",
        "prob_class_0",
        "prob_class_1",
        "prob_class_2",
        "prob_class_3",
    }
    miss = sorted(list(req - set(pred_rows.columns)))
    if miss:
        raise ValueError(f"Missing columns in {pred_rows_path}: {miss}")

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
    m = len(combo_keys)
    g_vals = list(gamma_grid)
    g_count = len(g_vals)
    if m == 0:
        raise ValueError("No combos found.")

    # Init weights (combo-level per gamma, and meta-gamma weights).
    combo_weights = np.full((g_count, m), 1.0 / m, dtype=np.float64)
    gamma_weights = np.full(g_count, 1.0 / g_count, dtype=np.float64)

    eta_model = float(max(0.0, eta_model))
    eta_gamma = float(max(0.0, eta_gamma))
    gamma_meta_discount = float(max(0.0, min(1.0, gamma_meta_discount)))
    min_weight_floor = float(max(1e-12, min_weight_floor))
    meta_loss_type = str(meta_loss_type).strip().lower()
    if meta_loss_type not in {"acc_cde", "nll"}:
        raise ValueError("meta_loss_type must be one of: acc_cde,nll")

    batch_rows: list[dict[str, Any]] = []
    row_frames: list[pl.DataFrame] = []
    gamma_hist_rows: list[dict[str, Any]] = []
    combo_hist_rows: list[dict[str, Any]] = []
    effective_rows: list[dict[str, Any]] = []

    for key, sub in pred_rows.group_by("pred_batch", maintain_order=True):
        pred_batch = int(key[0])
        y_true, probs, combo_pred, row_ts, row_bid = _combo_batch_arrays(
            sub=sub, combo_keys=combo_keys
        )
        n_rows = int(y_true.size)

        # Per-combo realized loss on current batch
        combo_acc = np.mean(combo_pred == y_true[:, None], axis=0)
        true_up = y_true >= 2
        true_down = y_true <= 1
        pred_up = combo_pred >= 2
        pred_down = combo_pred <= 1
        combo_cde = np.mean((true_up[:, None] & pred_down) | (true_down[:, None] & pred_up), axis=0)
        combo_loss = (
            float(combo_loss_acc_weight) * (1.0 - combo_acc)
            + float(combo_loss_cde_weight) * combo_cde
        )

        # Candidate ensembles for each gamma model
        ens_prob_by_gamma = np.zeros((g_count, n_rows, 4), dtype=np.float64)
        gamma_loss = np.zeros(g_count, dtype=np.float64)
        for gi in range(g_count):
            ens_prob_by_gamma[gi] = np.tensordot(probs, combo_weights[gi], axes=(1, 0))
            y_pred_g = np.argmax(ens_prob_by_gamma[gi], axis=1)
            met_g = _compute_metrics(y_true, y_pred_g)
            if meta_loss_type == "nll":
                pt = ens_prob_by_gamma[gi][np.arange(n_rows), y_true]
                gamma_loss[gi] = float(-np.mean(np.log(np.clip(pt, 1e-12, 1.0))))
            else:
                gamma_loss[gi] = (
                    float(meta_loss_acc_weight) * (1.0 - float(met_g["accuracy"]))
                    + float(meta_loss_cde_weight) * float(met_g["cross_direction_error"])
                )

        # Final mixture over gamma models
        final_prob = np.tensordot(gamma_weights, ens_prob_by_gamma, axes=(0, 0))
        y_pred_dma = np.argmax(final_prob, axis=1).astype(np.int32, copy=False)
        dma_metrics = _compute_metrics(y_true, y_pred_dma)

        uniform_prob = np.mean(probs, axis=1)
        y_pred_uniform = np.argmax(uniform_prob, axis=1).astype(np.int32, copy=False)
        uniform_metrics = _compute_metrics(y_true, y_pred_uniform)

        # Effective combo weights after gamma-mixture
        effective_combo_w = np.tensordot(gamma_weights, combo_weights, axes=(0, 0))
        top_gamma_idx = int(np.argmax(gamma_weights))
        top_combo_idx = int(np.argmax(effective_combo_w))
        gamma_entropy = _normalized_entropy(gamma_weights)
        combo_entropy = _normalized_entropy(effective_combo_w)
        winner_combo, winner_acc = winner_map.get(pred_batch, (None, None))

        batch_rows.append(
            {
                "pred_batch": pred_batch,
                "rows": n_rows,
                "winner_combo_key": winner_combo,
                "winner_accuracy": winner_acc,
                "dma_accuracy": float(dma_metrics["accuracy"]),
                "dma_macro_f1": float(dma_metrics["macro_f1"]),
                "dma_cross_direction_error": float(dma_metrics["cross_direction_error"]),
                "uniform_accuracy": float(uniform_metrics["accuracy"]),
                "uniform_macro_f1": float(uniform_metrics["macro_f1"]),
                "uniform_cross_direction_error": float(uniform_metrics["cross_direction_error"]),
                "delta_accuracy_dma_vs_uniform": float(
                    dma_metrics["accuracy"] - uniform_metrics["accuracy"]
                ),
                "delta_macro_f1_dma_vs_uniform": float(
                    dma_metrics["macro_f1"] - uniform_metrics["macro_f1"]
                ),
                "delta_cross_direction_error_dma_vs_uniform": float(
                    dma_metrics["cross_direction_error"] - uniform_metrics["cross_direction_error"]
                ),
                "dma_beats_uniform_accuracy": bool(
                    dma_metrics["accuracy"] > uniform_metrics["accuracy"]
                ),
                "top_gamma": float(g_vals[top_gamma_idx]),
                "top_gamma_weight": float(gamma_weights[top_gamma_idx]),
                "top_combo": str(combo_keys[top_combo_idx]),
                "top_combo_weight": float(effective_combo_w[top_combo_idx]),
                "gamma_entropy_norm": float(gamma_entropy),
                "combo_entropy_norm": float(combo_entropy),
            }
        )

        # Row-level outputs (prediction only; no future leakage)
        ts = row_ts
        bid = row_bid
        pmax = np.max(final_prob, axis=1)
        sorted_prob = np.sort(final_prob, axis=1)
        pmargin = sorted_prob[:, -1] - sorted_prob[:, -2]
        row_frames.append(
            pl.DataFrame(
                {
                    "pred_batch": np.full(n_rows, pred_batch, dtype=np.int32),
                    "timestamp": ts,
                    "batch_id": bid,
                    "y_true": y_true,
                    "y_pred_dma": y_pred_dma,
                    "y_pred_uniform": y_pred_uniform,
                    "p_dma_c0": final_prob[:, 0],
                    "p_dma_c1": final_prob[:, 1],
                    "p_dma_c2": final_prob[:, 2],
                    "p_dma_c3": final_prob[:, 3],
                    "p_dma_max": pmax,
                    "p_dma_margin": pmargin,
                }
            )
        )

        # Histories before update
        for gi, gv in enumerate(g_vals):
            gamma_hist_rows.append(
                {
                    "pred_batch": pred_batch,
                    "gamma": float(gv),
                    "gamma_weight_before": float(gamma_weights[gi]),
                    "gamma_loss": float(gamma_loss[gi]),
                }
            )
            for ci, ck in enumerate(combo_keys):
                combo_hist_rows.append(
                    {
                        "pred_batch": pred_batch,
                        "gamma": float(gv),
                        "action_key": ck,
                        "combo_weight_before": float(combo_weights[gi, ci]),
                        "combo_loss": float(combo_loss[ci]),
                        "combo_accuracy": float(combo_acc[ci]),
                        "combo_cross_direction_error": float(combo_cde[ci]),
                    }
                )
        for ci, ck in enumerate(combo_keys):
            effective_rows.append(
                {
                    "pred_batch": pred_batch,
                    "action_key": ck,
                    "effective_weight_before_update": float(effective_combo_w[ci]),
                }
            )

        # Update combo weights per gamma model
        combo_weights_new = np.zeros_like(combo_weights)
        for gi, gv in enumerate(g_vals):
            w_old = np.clip(combo_weights[gi], min_weight_floor, None)
            w_new = (w_old ** float(gv)) * np.exp(-eta_model * combo_loss)
            w_new = np.clip(w_new, min_weight_floor, None)
            w_new = w_new / float(np.sum(w_new))
            combo_weights_new[gi] = w_new

        # Update gamma meta-weights
        g_old = np.clip(gamma_weights, min_weight_floor, None)
        g_new = (g_old ** gamma_meta_discount) * np.exp(-eta_gamma * gamma_loss)
        g_new = np.clip(g_new, min_weight_floor, None)
        g_new = g_new / float(np.sum(g_new))

        # Append after-update weights into last appended rows
        # (fast post-write update by slice index)
        g_start = len(gamma_hist_rows) - g_count
        for gi in range(g_count):
            gamma_hist_rows[g_start + gi]["gamma_weight_after"] = float(g_new[gi])

        c_start = len(combo_hist_rows) - (g_count * m)
        idx = c_start
        for gi in range(g_count):
            for ci in range(m):
                combo_hist_rows[idx]["combo_weight_after"] = float(combo_weights_new[gi, ci])
                idx += 1

        e_start = len(effective_rows) - m
        eff_after = np.tensordot(g_new, combo_weights_new, axes=(0, 0))
        for ci in range(m):
            effective_rows[e_start + ci]["effective_weight_after_update"] = float(eff_after[ci])

        combo_weights = combo_weights_new
        gamma_weights = g_new

        if verbose and (pred_batch % 25 == 0):
            print(
                f"[DMA] pred_batch={pred_batch} "
                f"dma_acc={dma_metrics['accuracy']:.4f} "
                f"uniform_acc={uniform_metrics['accuracy']:.4f} "
                f"top_gamma={g_vals[top_gamma_idx]:.4f}"
            )

    batch_df = pl.DataFrame(batch_rows).sort("pred_batch")
    row_df = pl.concat(row_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id"]
    )
    gamma_hist_df = pl.DataFrame(gamma_hist_rows).sort(["pred_batch", "gamma"])
    combo_hist_df = pl.DataFrame(combo_hist_rows).sort(["pred_batch", "gamma", "action_key"])
    effective_df = pl.DataFrame(effective_rows).sort(["pred_batch", "action_key"])

    holdout_steps = int(max(1, min(int(holdout_steps), len(batch_df))))
    holdout_df = batch_df.tail(holdout_steps)

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
            "gamma_grid": [float(x) for x in g_vals],
            "eta_model": float(eta_model),
            "eta_gamma": float(eta_gamma),
            "gamma_meta_discount": float(gamma_meta_discount),
            "combo_loss_acc_weight": float(combo_loss_acc_weight),
            "combo_loss_cde_weight": float(combo_loss_cde_weight),
            "meta_loss_type": meta_loss_type,
            "meta_loss_acc_weight": float(meta_loss_acc_weight),
            "meta_loss_cde_weight": float(meta_loss_cde_weight),
            "holdout_steps": int(holdout_steps),
            "min_weight_floor": float(min_weight_floor),
            "combo_count": int(m),
            "gamma_count": int(g_count),
        },
        "rows": {
            "batches": int(len(batch_df)),
            "row_predictions": int(len(row_df)),
            "gamma_history_rows": int(len(gamma_hist_df)),
            "combo_history_rows": int(len(combo_hist_df)),
            "effective_weight_rows": int(len(effective_df)),
        },
        "metrics": {
            "all_batches": {
                "dma_accuracy": float(batch_df["dma_accuracy"].mean()),
                "uniform_accuracy": float(batch_df["uniform_accuracy"].mean()),
                "delta_accuracy_dma_vs_uniform": float(
                    batch_df["delta_accuracy_dma_vs_uniform"].mean()
                ),
                "dma_macro_f1": float(batch_df["dma_macro_f1"].mean()),
                "uniform_macro_f1": float(batch_df["uniform_macro_f1"].mean()),
                "delta_macro_f1_dma_vs_uniform": float(
                    batch_df["delta_macro_f1_dma_vs_uniform"].mean()
                ),
                "dma_cross_direction_error": float(
                    batch_df["dma_cross_direction_error"].mean()
                ),
                "uniform_cross_direction_error": float(
                    batch_df["uniform_cross_direction_error"].mean()
                ),
                "delta_cross_direction_error_dma_vs_uniform": float(
                    batch_df["delta_cross_direction_error_dma_vs_uniform"].mean()
                ),
                "share_dma_beats_uniform_accuracy": float(
                    batch_df["dma_beats_uniform_accuracy"].cast(pl.Int8, strict=False).mean()
                ),
            },
            "holdout_last_steps": {
                "steps": int(holdout_steps),
                "dma_accuracy": float(holdout_df["dma_accuracy"].mean()),
                "uniform_accuracy": float(holdout_df["uniform_accuracy"].mean()),
                "delta_accuracy_dma_vs_uniform": float(
                    holdout_df["delta_accuracy_dma_vs_uniform"].mean()
                ),
                "dma_macro_f1": float(holdout_df["dma_macro_f1"].mean()),
                "uniform_macro_f1": float(holdout_df["uniform_macro_f1"].mean()),
                "delta_macro_f1_dma_vs_uniform": float(
                    holdout_df["delta_macro_f1_dma_vs_uniform"].mean()
                ),
                "dma_cross_direction_error": float(
                    holdout_df["dma_cross_direction_error"].mean()
                ),
                "uniform_cross_direction_error": float(
                    holdout_df["uniform_cross_direction_error"].mean()
                ),
                "delta_cross_direction_error_dma_vs_uniform": float(
                    holdout_df["delta_cross_direction_error_dma_vs_uniform"].mean()
                ),
                "share_dma_beats_uniform_accuracy": float(
                    holdout_df["dma_beats_uniform_accuracy"]
                    .cast(pl.Int8, strict=False)
                    .mean()
                ),
            },
        },
        "final_state": {
            "gamma_weights": {
                str(g_vals[i]): float(gamma_weights[i]) for i in range(g_count)
            },
            "top5_effective_combo_weights": (
                effective_df.filter(
                    pl.col("pred_batch") == int(batch_df["pred_batch"].max())
                )
                .sort("effective_weight_after_update", descending=True)
                .head(5)
                .to_dicts()
            ),
        },
    }

    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    batch_parquet = out_run / "winner12_dma_batch_metrics.parquet"
    batch_csv = out_run / "winner12_dma_batch_metrics.csv"
    row_parquet = out_run / "winner12_dma_row_predictions.parquet"
    row_csv = out_run / "winner12_dma_row_predictions.csv"
    gamma_parquet = out_run / "winner12_dma_gamma_weight_history.parquet"
    gamma_csv = out_run / "winner12_dma_gamma_weight_history.csv"
    combo_parquet = out_run / "winner12_dma_combo_weight_history.parquet"
    combo_csv = out_run / "winner12_dma_combo_weight_history.csv"
    eff_parquet = out_run / "winner12_dma_effective_combo_weights.parquet"
    eff_csv = out_run / "winner12_dma_effective_combo_weights.csv"
    summary_json = out_run / "winner12_dma_summary.json"

    batch_df.write_parquet(batch_parquet)
    batch_df.write_csv(batch_csv)
    row_df.write_parquet(row_parquet)
    row_df.write_csv(row_csv)
    gamma_hist_df.write_parquet(gamma_parquet)
    gamma_hist_df.write_csv(gamma_csv)
    combo_hist_df.write_parquet(combo_parquet)
    combo_hist_df.write_csv(combo_csv)
    effective_df.write_parquet(eff_parquet)
    effective_df.write_csv(eff_csv)

    summary["artifacts"] = {
        "winner12_dma_batch_metrics_parquet": str(batch_parquet),
        "winner12_dma_batch_metrics_csv": str(batch_csv),
        "winner12_dma_row_predictions_parquet": str(row_parquet),
        "winner12_dma_row_predictions_csv": str(row_csv),
        "winner12_dma_gamma_weight_history_parquet": str(gamma_parquet),
        "winner12_dma_gamma_weight_history_csv": str(gamma_csv),
        "winner12_dma_combo_weight_history_parquet": str(combo_parquet),
        "winner12_dma_combo_weight_history_csv": str(combo_csv),
        "winner12_dma_effective_combo_weights_parquet": str(eff_parquet),
        "winner12_dma_effective_combo_weights_csv": str(eff_csv),
        "winner12_dma_summary_json": str(summary_json),
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Discounted model averaging over winner-12 combo probabilities."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--gamma-grid", type=str, default="0.90,0.95,0.975,0.99")
    p.add_argument("--eta-model", type=float, default=4.0)
    p.add_argument("--eta-gamma", type=float, default=2.0)
    p.add_argument("--gamma-meta-discount", type=float, default=0.995)
    p.add_argument("--combo-loss-acc-weight", type=float, default=0.7)
    p.add_argument("--combo-loss-cde-weight", type=float, default=0.3)
    p.add_argument("--meta-loss-type", type=str, default="acc_cde", choices=["acc_cde", "nll"])
    p.add_argument("--meta-loss-acc-weight", type=float, default=0.7)
    p.add_argument("--meta-loss-cde-weight", type=float, default=0.3)
    p.add_argument("--holdout-steps", type=int, default=200)
    p.add_argument("--min-weight-floor", type=float, default=1e-8)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Default: <project_root>/prediction_analysis/"
            "winner12_discounted_model_averaging_outputs"
        ),
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root
        / "prediction_analysis"
        / "winner12_discounted_model_averaging_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        gamma_grid=_parse_gamma_grid(args.gamma_grid),
        eta_model=float(args.eta_model),
        eta_gamma=float(args.eta_gamma),
        gamma_meta_discount=float(args.gamma_meta_discount),
        combo_loss_acc_weight=float(args.combo_loss_acc_weight),
        combo_loss_cde_weight=float(args.combo_loss_cde_weight),
        meta_loss_type=str(args.meta_loss_type),
        meta_loss_acc_weight=float(args.meta_loss_acc_weight),
        meta_loss_cde_weight=float(args.meta_loss_cde_weight),
        holdout_steps=int(args.holdout_steps),
        min_weight_floor=float(args.min_weight_floor),
        output_dir=output_dir,
        verbose=bool(args.verbose),
    )

    allm = summary["metrics"]["all_batches"]
    holdm = summary["metrics"]["holdout_last_steps"]
    print("Winner-12 discounted model averaging complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(
        "  All batches accuracy: "
        f"dma={allm['dma_accuracy']:.4f}, uniform={allm['uniform_accuracy']:.4f}, "
        f"delta={allm['delta_accuracy_dma_vs_uniform']:+.4f}"
    )
    print(
        "  Holdout accuracy: "
        f"dma={holdm['dma_accuracy']:.4f}, uniform={holdm['uniform_accuracy']:.4f}, "
        f"delta={holdm['delta_accuracy_dma_vs_uniform']:+.4f}"
    )
    print(
        "  All batches macro_f1: "
        f"dma={allm['dma_macro_f1']:.4f}, uniform={allm['uniform_macro_f1']:.4f}, "
        f"delta={allm['delta_macro_f1_dma_vs_uniform']:+.4f}"
    )
    print(
        "  All batches cross-direction-error: "
        f"dma={allm['dma_cross_direction_error']:.4f}, "
        f"uniform={allm['uniform_cross_direction_error']:.4f}, "
        f"delta={allm['delta_cross_direction_error_dma_vs_uniform']:+.4f}"
    )
    print("  Final gamma weights:", summary["final_state"]["gamma_weights"])
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()

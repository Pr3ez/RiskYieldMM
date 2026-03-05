#!/usr/bin/env python3
"""Causal risk-first gate optimizer for sparse EWAF outputs.

Optimizes asymmetric UP/DOWN thresholds with history-only walk-forward selection
and cadence target penalty.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

LABEL_UP = 0
LABEL_DOWN = 1
LABEL_HOLD = 2


def _parse_grid(spec: str) -> list[float]:
    vals = sorted({float(x.strip()) for x in str(spec).split(",") if x.strip()})
    if not vals:
        raise ValueError("Grid must not be empty")
    return vals


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Risk-first causal gate optimizer over EWAF predictions.")
    p.add_argument("--predictions-parquet", required=True)
    p.add_argument("--method-name", default="online_sparse_ewaf_brier")
    p.add_argument("--output-dir", default="prediction_analysis/multitimeframe_cross_target_validation")
    p.add_argument("--output-tag", default="")
    p.add_argument("--lookback-grid", default="120,240,480,960,all")
    p.add_argument("--val-tail-ratio", type=float, default=0.20)
    p.add_argument("--recalibrate-every-batches", type=int, default=25)
    p.add_argument("--min-history-rows", type=int, default=640)
    p.add_argument("--theta-up-grid", default="0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85")
    p.add_argument("--theta-down-grid", default="0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80,0.85")
    p.add_argument("--w-opp-active", type=float, default=4.0)
    p.add_argument("--w-opp-covered", type=float, default=2.0)
    p.add_argument("--w-safe", type=float, default=1.0)
    p.add_argument("--w-cadence", type=float, default=2.0)
    p.add_argument("--cadence-min-batches", type=float, default=10.0)
    p.add_argument("--cadence-max-batches", type=float, default=15.0)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    if not (0.0 < float(args.val_tail_ratio) < 0.5):
        raise ValueError("--val-tail-ratio must be in (0, 0.5)")
    if int(args.recalibrate_every_batches) < 1:
        raise ValueError("--recalibrate-every-batches must be >= 1")
    if int(args.min_history_rows) < 32:
        raise ValueError("--min-history-rows must be >= 32")
    if float(args.cadence_min_batches) <= 0 or float(args.cadence_max_batches) <= float(args.cadence_min_batches):
        raise ValueError("Invalid cadence bounds")

    lookbacks: list[int] = []
    for tok in str(args.lookback_grid).split(","):
        t = tok.strip().lower()
        if not t:
            continue
        if t == "all":
            lookbacks.append(-1)
        else:
            lookbacks.append(int(t))
    if not lookbacks:
        raise ValueError("--lookback-grid empty")
    args.lookbacks = lookbacks
    args.theta_up_vals = _parse_grid(args.theta_up_grid)
    args.theta_down_vals = _parse_grid(args.theta_down_grid)
    return args


def _risk_metrics(y: np.ndarray, y4: np.ndarray, pred: np.ndarray, batch_ids: np.ndarray) -> dict[str, float]:
    active = pred != LABEL_HOLD
    active_n = int(active.sum())
    opposite = ((y == LABEL_UP) & (pred == LABEL_DOWN)) | ((y == LABEL_DOWN) & (pred == LABEL_UP))

    opp_cov = float(opposite.mean()) if len(y) > 0 else 0.0
    opp_active = float(opposite[active].mean()) if active_n > 0 else 0.0

    safe_up = np.isin(y4, np.array([0, 2], dtype=int))
    safe_down = np.isin(y4, np.array([1, 3], dtype=int))
    safe_correct = ((pred == LABEL_UP) & safe_up) | ((pred == LABEL_DOWN) & safe_down)
    safe_acc = float(safe_correct[active].mean()) if active_n > 0 else 0.0

    # cadence as batches per signal
    uniq_batches = np.unique(batch_ids)
    batch_active = 0
    for b in uniq_batches:
        if np.any(pred[batch_ids == b] != LABEL_HOLD):
            batch_active += 1
    n_batches = len(uniq_batches)
    bps = float(n_batches / batch_active) if batch_active > 0 else float("inf")

    return {
        "opposite_fp_rate_active": opp_active,
        "opposite_fp_rate_covered": opp_cov,
        "directional_active_safe_accuracy": safe_acc,
        "batches_per_signal": bps,
        "active_batch_rate": float(batch_active / max(1, n_batches)),
    }


def _cadence_penalty(bps: float, low: float, high: float) -> float:
    if not np.isfinite(bps):
        return 1.0
    if bps < low:
        return float((low - bps) / low)
    if bps > high:
        return float((bps - high) / high)
    return 0.0


def _gate(base_pred: np.ndarray, up_score: np.ndarray, down_score: np.ndarray, th_up: float, th_down: float) -> np.ndarray:
    out = np.full(base_pred.shape[0], LABEL_HOLD, dtype=np.int64)
    up_ok = (base_pred == LABEL_UP) & (up_score >= th_up)
    dn_ok = (base_pred == LABEL_DOWN) & (down_score >= th_down)
    out[up_ok] = LABEL_UP
    out[dn_ok] = LABEL_DOWN
    return out


def _fit_thresholds(
    y: np.ndarray,
    y4: np.ndarray,
    base_pred: np.ndarray,
    up_score: np.ndarray,
    down_score: np.ndarray,
    batch_ids: np.ndarray,
    args: argparse.Namespace,
) -> tuple[float, float, float]:
    best = (float("inf"), 0.80, 0.80)

    for th_up in args.theta_up_vals:
        for th_down in args.theta_down_vals:
            pred = _gate(base_pred, up_score, down_score, th_up, th_down)
            m = _risk_metrics(y, y4, pred, batch_ids)
            cpen = _cadence_penalty(
                m["batches_per_signal"],
                float(args.cadence_min_batches),
                float(args.cadence_max_batches),
            )
            score = (
                float(args.w_opp_active) * m["opposite_fp_rate_active"]
                + float(args.w_opp_covered) * m["opposite_fp_rate_covered"]
                + float(args.w_safe) * (1.0 - m["directional_active_safe_accuracy"])
                + float(args.w_cadence) * cpen
            )
            if score < best[0]:
                best = (float(score), float(th_up), float(th_down))

    return best


def main() -> None:
    args = parse_args()

    pred_path = Path(args.predictions_parquet).expanduser().resolve()
    if not pred_path.exists():
        raise FileNotFoundError(f"Missing {pred_path}")

    df = pl.read_parquet(pred_path)
    if "method_name" in df.columns:
        df = df.filter(pl.col("method_name") == str(args.method_name))
    if df.height == 0:
        raise RuntimeError(f"No rows for method {args.method_name}")

    needed = {
        "pred_batch",
        "anchor_15m_ts",
        "truth_final",
        "pred_final",
        "prob_bf_up",
        "prob_bf_down",
        "prob_4dir_up",
        "prob_4dir_down",
    }
    miss = sorted(needed - set(df.columns))
    if miss:
        raise ValueError(f"Missing required columns: {miss}")

    # truth_final4 is optional in causal benchmark; reconstruct if absent from truth_final/4dir impossible.
    if "truth_final4" not in df.columns:
        # fallback: treat HOLD as both hold-side neutral in safe metric by mapping hold->2 and directional->same.
        df = df.with_columns(
            pl.when(pl.col("truth_final") == LABEL_UP)
            .then(pl.lit(0))
            .when(pl.col("truth_final") == LABEL_DOWN)
            .then(pl.lit(1))
            .otherwise(pl.lit(2))
            .alias("truth_final4")
        )

    df = df.sort(["pred_batch", "anchor_15m_ts"])

    pred_batch = df["pred_batch"].to_numpy().astype(np.int64)
    y = df["truth_final"].to_numpy().astype(np.int64)
    y4 = df["truth_final4"].to_numpy().astype(np.int64)
    base_pred = df["pred_final"].to_numpy().astype(np.int64)

    up_score = (df["prob_bf_up"].to_numpy().astype(np.float64) * df["prob_4dir_up"].to_numpy().astype(np.float64))
    down_score = (df["prob_bf_down"].to_numpy().astype(np.float64) * df["prob_4dir_down"].to_numpy().astype(np.float64))

    uniq_batches = np.array(sorted(np.unique(pred_batch)), dtype=np.int64)
    batch_to_idx = {int(b): i for i, b in enumerate(uniq_batches)}

    gated_pred = np.full(df.height, LABEL_HOLD, dtype=np.int64)
    sel_rows: list[dict[str, float | int | str]] = []

    cur_th_up = 0.80
    cur_th_down = 0.80
    cur_lb = -1

    for i, b in enumerate(uniq_batches):
        cur_mask = pred_batch == b

        should_recal = i == 0 or (i % int(args.recalibrate_every_batches) == 0)
        if should_recal and i > 0:
            best_global: tuple[float, float, float, int] | None = None
            for lb in args.lookbacks:
                lo_i = 0 if lb == -1 else max(0, i - int(lb))
                hist_batches = uniq_batches[lo_i:i]
                hist_mask = np.isin(pred_batch, hist_batches)
                if int(hist_mask.sum()) < int(args.min_history_rows):
                    continue

                # tail split inside history only
                hist_idx = np.flatnonzero(hist_mask)
                n_hist = hist_idx.shape[0]
                val_n = max(64, int(math.ceil(n_hist * float(args.val_tail_ratio))))
                val_n = min(val_n, max(32, n_hist - 64))
                val_idx = hist_idx[-val_n:]

                fit_y = y[val_idx]
                fit_y4 = y4[val_idx]
                fit_base = base_pred[val_idx]
                fit_up = up_score[val_idx]
                fit_down = down_score[val_idx]
                fit_batch = pred_batch[val_idx]

                score, th_up, th_down = _fit_thresholds(
                    fit_y,
                    fit_y4,
                    fit_base,
                    fit_up,
                    fit_down,
                    fit_batch,
                    args,
                )
                cand = (score, th_up, th_down, int(lb))
                if best_global is None or cand[0] < best_global[0]:
                    best_global = cand

            if best_global is not None:
                _, cur_th_up, cur_th_down, cur_lb = best_global

        cur_pred = _gate(base_pred[cur_mask], up_score[cur_mask], down_score[cur_mask], cur_th_up, cur_th_down)
        gated_pred[cur_mask] = cur_pred

        sel_rows.append(
            {
                "pred_batch": int(b),
                "threshold_up": float(cur_th_up),
                "threshold_down": float(cur_th_down),
                "lookback_batches": int(cur_lb),
                "recalibrated": bool(should_recal),
            }
        )

        if args.verbose and ((i + 1) % 100 == 0 or i == len(uniq_batches) - 1):
            print(
                f"[gate] batch {i+1}/{len(uniq_batches)} pred_batch={int(b)} "
                f"th_up={cur_th_up:.3f} th_dn={cur_th_down:.3f} lb={cur_lb}"
            )

    out = df.with_columns(pl.Series("pred_final_gated", gated_pred))

    met = _risk_metrics(y, y4, gated_pred, pred_batch)
    cadence_hit = bool(float(args.cadence_min_batches) <= met["batches_per_signal"] <= float(args.cadence_max_batches))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = Path(args.output_dir).expanduser().resolve() / (f"{stamp}_{tag}" if tag else stamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    pred_out = out_dir / "gated_predictions.parquet"
    sel_out = out_dir / "threshold_selection_by_batch.parquet"
    out.write_parquet(pred_out)
    pl.DataFrame(sel_rows).write_parquet(sel_out)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "input_predictions": str(pred_path),
        "method_name": str(args.method_name),
        "config": {
            "lookbacks": list(args.lookbacks),
            "theta_up_grid": list(args.theta_up_vals),
            "theta_down_grid": list(args.theta_down_vals),
            "recalibrate_every_batches": int(args.recalibrate_every_batches),
            "val_tail_ratio": float(args.val_tail_ratio),
            "min_history_rows": int(args.min_history_rows),
            "weights": {
                "opp_active": float(args.w_opp_active),
                "opp_covered": float(args.w_opp_covered),
                "safe": float(args.w_safe),
                "cadence": float(args.w_cadence),
            },
            "cadence_target": [float(args.cadence_min_batches), float(args.cadence_max_batches)],
        },
        "metrics": {
            **met,
            "cadence_target_hit": cadence_hit,
        },
        "artifacts": {
            "gated_predictions_parquet": str(pred_out),
            "threshold_selection_by_batch_parquet": str(sel_out),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

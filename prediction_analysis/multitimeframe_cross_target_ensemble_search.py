#!/usr/bin/env python3
"""Multi-target multi-timeframe ensemble search (production-style walk-forward).

This script is analysis-only. It uses stored prediction probabilities to build:
- target_breakfree_cross_timeframe ensemble (UP/DOWN/HOLD)
- target_4class_cross_timeframe ensemble (UP/DOWN direction)
- final cross-target ensemble (UP/DOWN/HOLD)

It compares alignment modes, weight methods, and final fusion rules under strict
walk-forward evaluation (no winner knowledge at inference).
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_OUTPUT_DIR = "prediction_analysis/multitimeframe_cross_target_outputs"
DEFAULT_ALIGNMENTS = ["same_period_close", "anchor_mean"]
DEFAULT_WEIGHT_METHODS = [
    "uniform",
    "winner_weighted",
    "history_acc_ewma",
    "history_logloss_ewma",
    "diversity_weighted",
    "history_brier_ewma",
    "kalman_score_filter",
    "acc_logloss_blend",
    "winner_history_blend",
    "dma_logscore",
    "ewaf_brier_share",
]
DEFAULT_FINAL_RULES = [
    "agreement_hold",
    "weighted_band",
    "breakfree_gate_weighted",
    "strict_agreement_margin",
    "dual_ova_thresholds",
    "specialist_rare_gate",
]
TIMEFRAME_W = {"1m": 15.0, "5m": 3.0, "15m": 1.0}
ROW_EXPECTED_BY_TIMEFRAME = {"1m": 15, "5m": 3, "15m": 1}
TARGET_BREAKFREE = "target_breakfree"
TARGET_4CLASS = "target_4class"

# Final label space
UP = 0
DOWN = 1
HOLD = 2
NO_SIGNAL = -1
LABEL_NAME = {UP: "UP", DOWN: "DOWN", HOLD: "HOLD", NO_SIGNAL: "NO_SIGNAL"}

TRUTH_UP = 0
TRUTH_DOWN = 1
TRUTH_HOLD_UP = 2
TRUTH_HOLD_DOWN = 3
TRUTH4_LABEL_NAME = {
    TRUTH_UP: "UP",
    TRUTH_DOWN: "DOWN",
    TRUTH_HOLD_UP: "HOLD_UP",
    TRUTH_HOLD_DOWN: "HOLD_DOWN",
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Cross-target multi-timeframe ensemble search (walk-forward)."
    )
    p.add_argument("--project-root", type=str, default=str(DEFAULT_PROJECT_ROOT))
    p.add_argument(
        "--ensemble-run-dir",
        type=str,
        default="",
        help=(
            "Path to multitimeframe_ensemble_outputs run directory. "
            "Default: latest run."
        ),
    )
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--output-tag", type=str, default="")
    p.add_argument(
        "--alignment-modes",
        type=str,
        default=",".join(DEFAULT_ALIGNMENTS),
        help="Comma-separated: same_period_close,anchor_mean",
    )
    p.add_argument(
        "--eval-mode",
        type=str,
        default="walkforward",
        choices=["walkforward"],
    )
    p.add_argument("--wf-warmup-batches", type=int, default=120)
    p.add_argument("--wf-recalibrate-every", type=int, default=5)
    p.add_argument(
        "--candidate-pool-mode",
        type=str,
        default="hybrid_staged",
        choices=["hybrid_staged"],
    )
    p.add_argument(
        "--weight-methods",
        type=str,
        default=",".join(DEFAULT_WEIGHT_METHODS),
    )
    p.add_argument(
        "--kalman-process-noise",
        type=float,
        default=0.005,
        help=(
            "Process noise for kalman_score_filter candidate-skill smoother. "
            "Higher values adapt faster to regime shifts."
        ),
    )
    p.add_argument(
        "--kalman-measurement-noise",
        type=float,
        default=0.05,
        help=(
            "Measurement noise for kalman_score_filter candidate-skill smoother. "
            "Higher values smooth more aggressively."
        ),
    )
    p.add_argument(
        "--dma-forgetting-factor",
        type=float,
        default=0.995,
        help=(
            "Forgetting factor for dma_logscore model weights. "
            "Lower values adapt faster; 1.0 means no forgetting."
        ),
    )
    p.add_argument(
        "--dma-fixed-share-alpha",
        type=float,
        default=0.01,
        help=(
            "Fixed-share mixing for dma_logscore to avoid weight collapse. "
            "0 disables mixing."
        ),
    )
    p.add_argument(
        "--ewaf-brier-eta",
        type=float,
        default=4.0,
        help=(
            "Learning rate for ewaf_brier_share online weight updates. "
            "Higher values react faster to recent Brier-loss differences."
        ),
    )
    p.add_argument(
        "--final-rules",
        type=str,
        default=",".join(DEFAULT_FINAL_RULES),
    )
    p.add_argument(
        "--hold-band-grid",
        type=str,
        default="0.00:0.20:0.01",
        help="start:end:step inclusive",
    )
    p.add_argument(
        "--ova-threshold-grid",
        type=str,
        default="0.45:0.80:0.02",
        help="UP/DOWN one-vs-all threshold grid: start:end:step inclusive",
    )
    p.add_argument(
        "--tau-objective",
        type=str,
        default="macro_f1",
        choices=["macro_f1", "risk_aware"],
        help=(
            "Objective used to pick tau in band-based final rules. "
            "'risk_aware' penalizes directional false positives."
        ),
    )
    p.add_argument(
        "--tau-fp-penalty",
        type=float,
        default=0.75,
        help="Penalty weight for directional FP rate in tau-objective risk_aware mode.",
    )
    p.add_argument(
        "--tau-opposite-fp-penalty",
        type=float,
        default=1.50,
        help="Penalty weight for opposite-direction FP rate in tau-objective risk_aware mode.",
    )
    p.add_argument(
        "--tau-hold-side-penalty",
        type=float,
        default=1.00,
        help=(
            "Penalty weight for hold-side cross-direction errors "
            "(hold_up->down or hold_down->up) in tau-objective risk_aware mode."
        ),
    )
    p.add_argument(
        "--tau-opposite-active-penalty",
        type=float,
        default=0.0,
        help=(
            "Penalty weight for opposite-direction error rate among active predictions "
            "(UP/DOWN only) in tau-objective risk_aware mode."
        ),
    )
    p.add_argument(
        "--tau-min-active-coverage",
        type=float,
        default=0.0,
        help=(
            "Minimum directional active coverage required when selecting tau. "
            "If no tau satisfies this floor, fallback to unconstrained best."
        ),
    )
    p.add_argument(
        "--specialist-min-support",
        type=int,
        default=20,
        help="Minimum history support count for a candidate-direction specialist profile.",
    )
    p.add_argument(
        "--specialist-min-safe-accuracy",
        type=float,
        default=0.65,
        help=(
            "Minimum history safe accuracy for specialist activation. "
            "Safe accuracy counts directional prediction as correct on matching hold-side truth."
        ),
    )
    p.add_argument(
        "--specialist-max-opposite-rate",
        type=float,
        default=0.15,
        help="Maximum allowed opposite-direction rate for specialist activation.",
    )
    p.add_argument(
        "--specialist-min-votes",
        type=int,
        default=2,
        help="Minimum active specialist votes required to emit UP or DOWN.",
    )
    p.add_argument(
        "--specialist-recency-decay",
        type=float,
        default=0.995,
        help="Recency decay for specialist history profiling (newest sample has weight 1).",
    )
    p.add_argument("--min-candidates-per-unit", type=int, default=4)
    p.add_argument("--max-prune-iterations", type=int, default=200)
    p.add_argument(
        "--selection-lookback-grid",
        type=str,
        default="all",
        help=(
            "Comma-separated selection lookback windows in anchors, e.g. 120,180,240,all. "
            "Used only for candidate selection stage; all means full history."
        ),
    )
    p.add_argument(
        "--selection-validation-tail-ratio",
        type=float,
        default=0.20,
        help=(
            "Tail fraction of selection window used for lookback ranking validation. "
            "Set 0 to disable and rank lookbacks on in-window fit objective."
        ),
    )
    p.add_argument(
        "--selection-min-history",
        type=int,
        default=64,
        help="Minimum anchor rows required in selection train window for a lookback candidate.",
    )
    p.add_argument(
        "--rank-min-active-coverage",
        type=float,
        default=0.0,
        help=(
            "Minimum directional active coverage required for best-setup ranking. "
            "If no methods satisfy it, ranking falls back to all methods."
        ),
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--progress-every-batches",
        type=int,
        default=25,
        help=(
            "Batch cadence for walk-forward progress heartbeat per method/rule. "
            "Set 0 to disable heartbeat prints."
        ),
    )
    p.add_argument(
        "--selection-progress-every-calibs",
        type=int,
        default=1,
        help=(
            "Calibration cadence for selection-stage progress heartbeat. "
            "Set 0 to disable selection heartbeat prints."
        ),
    )
    p.add_argument(
        "--progress-log-file",
        type=str,
        default="live_progress.log",
        help=(
            "Progress log filename inside output run dir. "
            "Set empty string to disable file logging."
        ),
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _parse_csv_list(raw: str, allowed: set[str]) -> list[str]:
    vals = [x.strip() for x in str(raw).split(",") if x.strip()]
    out: list[str] = []
    for v in vals:
        if v not in allowed:
            raise ValueError(f"Invalid value {v!r}; allowed={sorted(allowed)}")
        if v not in out:
            out.append(v)
    if not out:
        raise ValueError("List cannot be empty")
    return out


def _parse_lookback_grid(raw: str) -> list[int]:
    vals = [x.strip().lower() for x in str(raw).split(",") if x.strip()]
    out: list[int] = []
    for v in vals:
        if v == "all":
            if -1 not in out:
                out.append(-1)
            continue
        try:
            iv = int(v)
        except Exception as exc:
            raise ValueError(f"Invalid selection lookback value: {v!r}") from exc
        if iv <= 0:
            raise ValueError(f"Lookback must be positive or 'all', got {iv}")
        if iv not in out:
            out.append(iv)
    if not out:
        raise ValueError("selection-lookback-grid cannot be empty")
    return out


def _parse_hold_band_grid(raw: str) -> np.ndarray:
    try:
        start_s, end_s, step_s = str(raw).split(":")
        start = float(start_s)
        end = float(end_s)
        step = float(step_s)
    except Exception as exc:
        raise ValueError(f"Invalid hold band grid: {raw!r}") from exc
    if step <= 0 or end < start:
        raise ValueError(f"Invalid hold band range: {raw!r}")
    vals = np.arange(start, end + step * 0.5, step, dtype=np.float64)
    vals = np.unique(np.round(vals, 10))
    return vals


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    def _s(x: Any) -> Any:
        if isinstance(x, dict):
            return {str(k): _s(v) for k, v in x.items()}
        if isinstance(x, list):
            return [_s(v) for v in x]
        if isinstance(x, tuple):
            return [_s(v) for v in x]
        if isinstance(x, np.generic):
            return _s(x.item())
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return x

    path.write_text(json.dumps(_s(payload), indent=2, ensure_ascii=False), encoding="utf-8")


def _format_eta(seconds: float) -> str:
    if not np.isfinite(seconds) or seconds < 0:
        return "n/a"
    s = int(round(float(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    if m > 0:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def _progress_event(
    *,
    message: str,
    verbose: bool,
    progress_log_path: Path | None,
    payload: dict[str, Any] | None = None,
    force_print: bool = False,
) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {message}"
    if force_print or verbose:
        print(line, flush=True)
    if progress_log_path is not None:
        progress_log_path.parent.mkdir(parents=True, exist_ok=True)
        with progress_log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            if payload is not None:
                rec = {"ts_utc": ts, **payload}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _resolve_ensemble_run_dir(project_root: Path, ensemble_run_dir_arg: str) -> Path:
    if ensemble_run_dir_arg:
        p = Path(ensemble_run_dir_arg).expanduser()
        if p.exists():
            return p.resolve()
        raise FileNotFoundError(f"ensemble run dir not found: {ensemble_run_dir_arg}")
    root = project_root / "prediction_analysis" / "multitimeframe_ensemble_outputs"
    runs = sorted([d for d in root.glob("*") if d.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs found in {root}")
    return runs[-1].resolve()


def _load_candidate_sets(path: Path) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for unit, meta in data.items():
        action_keys = [str(v) for v in meta.get("action_keys", [])]
        if len(action_keys) != 12:
            raise ValueError(f"{unit} candidate count is {len(action_keys)}, expected 12")
        if len(set(action_keys)) != 12:
            raise ValueError(f"{unit} candidates contain duplicates")
        winner_wins = {str(k): int(v) for k, v in meta.get("winner_wins", {}).items()}
        out[unit] = {
            "source": str(meta.get("source", "")),
            "action_keys": action_keys,
            "winner_wins": winner_wins,
        }
    required_units = {
        "1m/target_4class",
        "1m/target_breakfree",
        "5m/target_4class",
        "5m/target_breakfree",
        "15m/target_4class",
        "15m/target_breakfree",
    }
    missing = sorted(required_units - set(out.keys()))
    if missing:
        raise ValueError(f"Missing required units in candidate set: {missing}")
    return out


def _prepare_truth_table(unit_rows: pl.DataFrame) -> pl.DataFrame:
    key_cols = ["pred_batch", "anchor_15m_ts"]

    truth_b = (
        unit_rows.filter(pl.col("unit") == "15m/target_breakfree")
        .group_by(key_cols)
        .agg(pl.col("y_true").first().alias("y_true_breakfree"))
        .with_columns(
            pl.when(pl.col("y_true_breakfree") == 0)
            .then(pl.lit(UP))
            .when(pl.col("y_true_breakfree") == 1)
            .then(pl.lit(DOWN))
            .when(pl.col("y_true_breakfree") == 2)
            .then(pl.lit(HOLD))
            .otherwise(pl.lit(NO_SIGNAL))
            .alias("truth_breakfree")
        )
        .select(key_cols + ["truth_breakfree"])
    )

    truth_4 = (
        unit_rows.filter(pl.col("unit") == "15m/target_4class")
        .group_by(key_cols)
        .agg(pl.col("y_true").first().alias("y_true_4class"))
        .with_columns(
            pl.when(pl.col("y_true_4class").is_in([2, 3]))
            .then(pl.lit(UP))
            .when(pl.col("y_true_4class").is_in([0, 1]))
            .then(pl.lit(DOWN))
            .otherwise(pl.lit(NO_SIGNAL))
            .alias("truth_4dir")
        )
        .select(key_cols + ["truth_4dir"])
    )

    truth = (
        truth_b.join(truth_4, on=key_cols, how="inner")
        .with_columns(pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False))
        .sort(key_cols)
    )
    if truth.is_empty():
        raise RuntimeError("Truth table is empty")
    return truth


def _compose_truth4_labels(truth_breakfree: np.ndarray, truth_4dir: np.ndarray) -> np.ndarray:
    out = np.full(truth_breakfree.shape[0], -1, dtype=np.int16)
    up_mask = truth_breakfree == UP
    down_mask = truth_breakfree == DOWN
    hold_up = (truth_breakfree == HOLD) & (truth_4dir == UP)
    hold_down = (truth_breakfree == HOLD) & (truth_4dir == DOWN)
    out[up_mask] = TRUTH_UP
    out[down_mask] = TRUTH_DOWN
    out[hold_up] = TRUTH_HOLD_UP
    out[hold_down] = TRUTH_HOLD_DOWN
    return out


def _build_anchor_candidate_probs(unit_rows: pl.DataFrame, mode: str) -> pl.DataFrame:
    base_cols = [
        "pred_batch",
        "anchor_15m_ts",
        "unit",
        "timeframe",
        "target",
        "action_key",
    ]

    if mode == "anchor_mean":
        out = (
            unit_rows.group_by(base_cols)
            .agg(
                [
                    pl.len().alias("row_count"),
                    pl.col("p_up").mean().alias("p_up"),
                    pl.col("p_down").mean().alias("p_down"),
                    pl.col("p_neutral").mean().alias("p_hold"),
                ]
            )
            .with_columns(
                pl.col("timeframe")
                .replace_strict(ROW_EXPECTED_BY_TIMEFRAME)
                .cast(pl.Int64)
                .alias("row_count_expected")
            )
            .with_columns((pl.col("row_count") == pl.col("row_count_expected")).alias("row_count_match"))
            .with_columns(pl.lit("anchor_mean").alias("alignment_mode"))
            .sort(["pred_batch", "anchor_15m_ts", "unit", "action_key"])
        )
        return out.with_columns(pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False))

    if mode == "same_period_close":
        key_cols = base_cols
        ordered = (
            unit_rows.sort(
                [
                    "pred_batch",
                    "anchor_15m_ts",
                    "unit",
                    "action_key",
                    "timestamp",
                    "batch_id",
                ],
                descending=[False, False, False, False, False, False],
            )
            .with_columns(
                [
                    pl.col("timestamp").cum_count().over(key_cols).alias("row_pos"),
                    pl.len().over(key_cols).alias("row_count"),
                ]
            )
            .with_columns(
                pl.col("timeframe")
                .replace_strict(ROW_EXPECTED_BY_TIMEFRAME)
                .cast(pl.Int64)
                .alias("row_count_expected")
            )
            .filter(pl.col("row_pos") == pl.col("row_count_expected"))
            .select(
                key_cols
                + [
                    "row_count",
                    "row_count_expected",
                    pl.col("p_up").alias("p_up"),
                    pl.col("p_down").alias("p_down"),
                    pl.col("p_neutral").alias("p_hold"),
                ]
            )
            .with_columns((pl.col("row_count") == pl.col("row_count_expected")).alias("row_count_match"))
            .with_columns(pl.lit("same_period_close").alias("alignment_mode"))
            .sort(["pred_batch", "anchor_15m_ts", "unit", "action_key"])
        )
        return ordered.with_columns(pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False))

    raise ValueError(f"Unsupported alignment mode: {mode}")


def _macro_f1_from_confusion(conf: np.ndarray) -> float:
    f1s: list[float] = []
    n_classes = conf.shape[0]
    for i in range(n_classes):
        tp = float(conf[i, i])
        fp = float(conf[:, i].sum() - tp)
        fn = float(conf[i, :].sum() - tp)
        p = tp / (tp + fp) if tp + fp > 0 else 0.0
        r = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = (2.0 * p * r / (p + r)) if p + r > 0 else 0.0
        f1s.append(f1)
    return float(np.mean(f1s)) if f1s else 0.0


def _build_confusion(y_true: np.ndarray, y_pred: np.ndarray, labels: list[int]) -> np.ndarray:
    conf = np.zeros((len(labels), len(labels)), dtype=np.int64)
    idx = {v: i for i, v in enumerate(labels)}
    for t, p in zip(y_true.tolist(), y_pred.tolist()):
        if t in idx and p in idx:
            conf[idx[t], idx[p]] += 1
    return conf


def _compute_standard_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    valid = y_true >= 0
    y_true_v = y_true[valid]
    y_pred_v = y_pred[valid]
    eligible = int(y_true_v.size)
    covered_mask = y_pred_v >= 0
    covered = int(covered_mask.sum())
    coverage = float(covered / eligible) if eligible else 0.0

    if covered == 0:
        return {
            "eligible_count": eligible,
            "covered_count": 0,
            "coverage": coverage,
            "accuracy_covered": 0.0,
            "macro_f1": 0.0,
            "balanced_accuracy": 0.0,
            "directional_balanced_recall": 0.0,
            "precision_up": 0.0,
            "precision_down": 0.0,
            "precision_hold": 0.0,
            "recall_up": 0.0,
            "recall_down": 0.0,
            "recall_hold": 0.0,
            "f1_up": 0.0,
            "f1_down": 0.0,
            "f1_hold": 0.0,
            "confusion": np.zeros((3, 3), dtype=np.int64),
        }

    yt = y_true_v[covered_mask]
    yp = y_pred_v[covered_mask]
    conf = _build_confusion(yt, yp, labels=[UP, DOWN, HOLD])

    acc = float((yt == yp).mean()) if yt.size else 0.0

    precisions: dict[int, float] = {}
    recalls: dict[int, float] = {}
    f1s: dict[int, float] = {}
    for cls in [UP, DOWN, HOLD]:
        i = {UP: 0, DOWN: 1, HOLD: 2}[cls]
        tp = float(conf[i, i])
        fp = float(conf[:, i].sum() - tp)
        fn = float(conf[i, :].sum() - tp)
        p = tp / (tp + fp) if tp + fp > 0 else 0.0
        r = tp / (tp + fn) if tp + fn > 0 else 0.0
        f1 = (2.0 * p * r / (p + r)) if p + r > 0 else 0.0
        precisions[cls] = p
        recalls[cls] = r
        f1s[cls] = f1

    macro_f1 = float(np.mean([f1s[UP], f1s[DOWN], f1s[HOLD]]))
    bal_acc = float(np.mean([recalls[UP], recalls[DOWN], recalls[HOLD]]))
    dir_bal = float(np.mean([recalls[UP], recalls[DOWN]]))

    return {
        "eligible_count": eligible,
        "covered_count": covered,
        "coverage": coverage,
        "accuracy_covered": acc,
        "macro_f1": macro_f1,
        "balanced_accuracy": bal_acc,
        "directional_balanced_recall": dir_bal,
        "precision_up": precisions[UP],
        "precision_down": precisions[DOWN],
        "precision_hold": precisions[HOLD],
        "recall_up": recalls[UP],
        "recall_down": recalls[DOWN],
        "recall_hold": recalls[HOLD],
        "f1_up": f1s[UP],
        "f1_down": f1s[DOWN],
        "f1_hold": f1s[HOLD],
        "confusion": conf,
    }


def _compute_custom_cost(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    valid = y_true >= 0
    yt = y_true[valid]
    yp = y_pred[valid]
    n = int(yt.size)
    if n == 0:
        return {
            "mean_cost": 0.0,
            "utility": 1.0,
            "count_correct": 0,
            "count_opposite_direction": 0,
            "count_hold_mismatch": 0,
            "count_no_signal": 0,
            "cost_sum": 0.0,
        }

    no_signal_mask = yp == NO_SIGNAL
    yp_cost = yp.copy()
    yp_cost[no_signal_mask] = HOLD

    correct = yp_cost == yt
    opposite = ((yt == UP) & (yp_cost == DOWN)) | ((yt == DOWN) & (yp_cost == UP))
    hold_mismatch = ~correct & ~opposite

    costs = np.where(correct, 0.0, np.where(opposite, 2.0, 1.0))
    mean_cost = float(costs.mean())
    utility = float(1.0 - (mean_cost / 2.0))

    return {
        "mean_cost": mean_cost,
        "utility": utility,
        "count_correct": int(correct.sum()),
        "count_opposite_direction": int(opposite.sum()),
        "count_hold_mismatch": int(hold_mismatch.sum()),
        "count_no_signal": int(no_signal_mask.sum()),
        "cost_sum": float(costs.sum()),
    }


def _compute_custom_cost_truth4(y_true4: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    valid = y_true4 >= 0
    yt = y_true4[valid]
    yp = y_pred[valid]
    n = int(yt.size)
    if n == 0:
        return {
            "mean_cost": 0.0,
            "utility": 1.0,
            "count_correct": 0,
            "count_opposite_direction": 0,
            "count_hold_mismatch": 0,
            "count_no_signal": 0,
            "cost_sum": 0.0,
        }

    no_signal_mask = yp == NO_SIGNAL
    yp_eval = yp.copy()
    yp_eval[no_signal_mask] = HOLD

    truth_up_side = (yt == TRUTH_UP) | (yt == TRUTH_HOLD_UP)
    truth_down_side = (yt == TRUTH_DOWN) | (yt == TRUTH_HOLD_DOWN)

    pred_up = yp_eval == UP
    pred_down = yp_eval == DOWN
    pred_hold = yp_eval == HOLD

    correct = pred_hold | (pred_up & truth_up_side) | (pred_down & truth_down_side)
    opposite = (pred_up & truth_down_side) | (pred_down & truth_up_side)
    hold_mismatch = ~correct & ~opposite

    costs = np.where(correct, 0.0, np.where(opposite, 2.0, 1.0))
    mean_cost = float(costs.mean())
    utility = float(1.0 - (mean_cost / 2.0))

    return {
        "mean_cost": mean_cost,
        "utility": utility,
        "count_correct": int(correct.sum()),
        "count_opposite_direction": int(opposite.sum()),
        "count_hold_mismatch": int(hold_mismatch.sum()),
        "count_no_signal": int(no_signal_mask.sum()),
        "cost_sum": float(costs.sum()),
    }


def _directional_fp_stats(conf: np.ndarray, covered_count: int) -> dict[str, float | int]:
    # conf rows are truth [UP, DOWN, HOLD], columns are predictions [UP, DOWN, HOLD]
    fp_up = int(conf[DOWN, UP] + conf[HOLD, UP])
    fp_down = int(conf[UP, DOWN] + conf[HOLD, DOWN])
    opposite_fp_up = int(conf[DOWN, UP])
    opposite_fp_down = int(conf[UP, DOWN])
    opposite_fp_total = int(opposite_fp_up + opposite_fp_down)
    hold_to_direction_fp = int(conf[HOLD, UP] + conf[HOLD, DOWN])
    directional_fp_total = int(fp_up + fp_down)
    pred_up_count = int(conf[:, UP].sum())
    pred_down_count = int(conf[:, DOWN].sum())
    directional_pred_count = int(pred_up_count + pred_down_count)
    denom_cov = max(int(covered_count), 1)
    denom_dir = max(int(directional_pred_count), 1)
    # opposite direction errors are weighted x2, hold->direction weighted x1.
    directional_fp_risk_score = float(
        (2 * opposite_fp_total + hold_to_direction_fp) / float(denom_cov)
    )
    return {
        "fp_up": fp_up,
        "fp_down": fp_down,
        "opposite_fp_up": opposite_fp_up,
        "opposite_fp_down": opposite_fp_down,
        "opposite_fp_total": opposite_fp_total,
        "hold_to_direction_fp": hold_to_direction_fp,
        "directional_fp_total": directional_fp_total,
        "pred_up_count": pred_up_count,
        "pred_down_count": pred_down_count,
        "directional_pred_count": directional_pred_count,
        "fp_up_rate_covered": float(fp_up / denom_cov),
        "fp_down_rate_covered": float(fp_down / denom_cov),
        "directional_fp_rate_covered": float(directional_fp_total / denom_cov),
        "directional_fp_rate_directional_preds": float(directional_fp_total / denom_dir),
        "opposite_fp_rate_covered": float(opposite_fp_total / denom_cov),
        "directional_fp_risk_score": directional_fp_risk_score,
    }


def _hold_side_metrics(
    truth_breakfree: np.ndarray,
    truth_4dir: np.ndarray,
    pred_final: np.ndarray,
) -> dict[str, float | int]:
    if truth_breakfree.size == 0:
        return {
            "hold_up_truth_count": 0,
            "hold_down_truth_count": 0,
            "hold_up_ok_count": 0,
            "hold_down_ok_count": 0,
            "hold_up_bad_down_count": 0,
            "hold_down_bad_up_count": 0,
            "hold_side_cross_error_count": 0,
            "hold_side_cross_error_rate_covered": 0.0,
            "hold_up_bad_down_rate_within_hold_up": 0.0,
            "hold_down_bad_up_rate_within_hold_down": 0.0,
        }

    pred_eval = pred_final.copy()
    pred_eval[pred_eval == NO_SIGNAL] = HOLD

    hold_up_mask = (truth_breakfree == HOLD) & (truth_4dir == UP)
    hold_down_mask = (truth_breakfree == HOLD) & (truth_4dir == DOWN)

    hold_up_truth_count = int(np.sum(hold_up_mask))
    hold_down_truth_count = int(np.sum(hold_down_mask))

    hold_up_ok = int(np.sum(hold_up_mask & ((pred_eval == UP) | (pred_eval == HOLD))))
    hold_down_ok = int(np.sum(hold_down_mask & ((pred_eval == DOWN) | (pred_eval == HOLD))))
    hold_up_bad_down = int(np.sum(hold_up_mask & (pred_eval == DOWN)))
    hold_down_bad_up = int(np.sum(hold_down_mask & (pred_eval == UP)))

    hold_side_cross_error_count = int(hold_up_bad_down + hold_down_bad_up)
    denom_all = max(int(pred_eval.size), 1)
    denom_hold_up = max(hold_up_truth_count, 1)
    denom_hold_down = max(hold_down_truth_count, 1)

    return {
        "hold_up_truth_count": hold_up_truth_count,
        "hold_down_truth_count": hold_down_truth_count,
        "hold_up_ok_count": hold_up_ok,
        "hold_down_ok_count": hold_down_ok,
        "hold_up_bad_down_count": hold_up_bad_down,
        "hold_down_bad_up_count": hold_down_bad_up,
        "hold_side_cross_error_count": hold_side_cross_error_count,
        "hold_side_cross_error_rate_covered": float(hold_side_cross_error_count / denom_all),
        "hold_up_bad_down_rate_within_hold_up": float(hold_up_bad_down / denom_hold_up),
        "hold_down_bad_up_rate_within_hold_down": float(hold_down_bad_up / denom_hold_down),
    }


def _compute_directional_hold_eval(
    truth_final4: np.ndarray,
    pred_final: np.ndarray,
) -> dict[str, float | int]:
    valid_mask = truth_final4 >= 0
    yt = truth_final4[valid_mask]
    yp = pred_final[valid_mask].copy()
    n = int(yt.size)
    if n == 0:
        return {
            "eligible_count": 0,
            "covered_count": 0,
            "coverage": 0.0,
            "directional_safe_accuracy": 0.0,
            "directional_active_accuracy": 0.0,
            "directional_active_coverage": 0.0,
            "opposite_fp_rate_covered": 0.0,
            "directional_fp_rate_covered": 0.0,
            "fp_up": 0,
            "fp_down": 0,
            "opposite_fp_up": 0,
            "opposite_fp_down": 0,
            "opposite_fp_total": 0,
            "directional_pred_count": 0,
            "pred_up_count": 0,
            "pred_down_count": 0,
            "pred_hold_count": 0,
        }

    yp[yp == NO_SIGNAL] = HOLD
    pred_up = yp == UP
    pred_down = yp == DOWN
    pred_hold = yp == HOLD

    truth_up_side = (yt == TRUTH_UP) | (yt == TRUTH_HOLD_UP)
    truth_down_side = (yt == TRUTH_DOWN) | (yt == TRUTH_HOLD_DOWN)

    directional_pred = pred_up | pred_down
    directional_tp = (pred_up & truth_up_side) | (pred_down & truth_down_side)
    opposite = (pred_up & truth_down_side) | (pred_down & truth_up_side)
    compatible = pred_hold | directional_tp

    fp_up = int(np.sum(pred_up & truth_down_side))
    fp_down = int(np.sum(pred_down & truth_up_side))
    opposite_fp_up = int(np.sum(pred_up & ((yt == TRUTH_DOWN) | (yt == TRUTH_HOLD_DOWN))))
    opposite_fp_down = int(np.sum(pred_down & ((yt == TRUTH_UP) | (yt == TRUTH_HOLD_UP))))
    opposite_total = int(opposite_fp_up + opposite_fp_down)

    covered = int(n)
    directional_count = int(np.sum(directional_pred))
    pred_up_count = int(np.sum(pred_up))
    pred_down_count = int(np.sum(pred_down))
    pred_hold_count = int(np.sum(pred_hold))

    denom_cov = max(covered, 1)
    denom_dir = max(directional_count, 1)

    return {
        "eligible_count": int(n),
        "covered_count": int(covered),
        "coverage": 1.0,
        "directional_safe_accuracy": float(np.sum(compatible) / denom_cov),
        "directional_active_accuracy": float(np.sum(directional_tp) / denom_dir),
        "directional_active_coverage": float(directional_count / denom_cov),
        "opposite_fp_rate_covered": float(opposite_total / denom_cov),
        "directional_fp_rate_covered": float((fp_up + fp_down) / denom_cov),
        "fp_up": int(fp_up),
        "fp_down": int(fp_down),
        "opposite_fp_up": int(opposite_fp_up),
        "opposite_fp_down": int(opposite_fp_down),
        "opposite_fp_total": int(opposite_total),
        "directional_pred_count": int(directional_count),
        "pred_up_count": int(pred_up_count),
        "pred_down_count": int(pred_down_count),
        "pred_hold_count": int(pred_hold_count),
    }


def _build_truth4_pred3_confusion(y_true4: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    conf = np.zeros((4, 3), dtype=np.int64)
    yt = y_true4[y_true4 >= 0]
    yp = y_pred[y_true4 >= 0].copy()
    yp[yp == NO_SIGNAL] = HOLD
    truth_idx = {
        TRUTH_UP: 0,
        TRUTH_DOWN: 1,
        TRUTH_HOLD_UP: 2,
        TRUTH_HOLD_DOWN: 3,
    }
    pred_idx = {UP: 0, DOWN: 1, HOLD: 2}
    for t, p in zip(yt.tolist(), yp.tolist()):
        ti = truth_idx.get(int(t))
        pi = pred_idx.get(int(p))
        if ti is not None and pi is not None:
            conf[ti, pi] += 1
    return conf


def _batch_block_bootstrap_ci(
    sub: pl.DataFrame,
    *,
    seed: int,
    n_bootstrap: int = 300,
) -> dict[str, float | None]:
    if sub.is_empty() or n_bootstrap <= 0:
        return {
            "directional_active_accuracy_ci95_low": None,
            "directional_active_accuracy_ci95_high": None,
            "custom_mean_cost_ci95_low": None,
            "custom_mean_cost_ci95_high": None,
        }

    grouped = (
        sub.sort(["pred_batch", "anchor_15m_ts"])
        .group_by("pred_batch", maintain_order=True)
        .agg(
            [
                pl.col("truth_final4").alias("truth_final4_list"),
                pl.col("pred_final").alias("pred_final_list"),
            ]
        )
    )
    truth_blocks = [np.asarray(v, dtype=np.int16) for v in grouped["truth_final4_list"].to_list()]
    pred_blocks = [np.asarray(v, dtype=np.int16) for v in grouped["pred_final_list"].to_list()]
    n_blocks = len(truth_blocks)
    if n_blocks == 0:
        return {
            "directional_active_accuracy_ci95_low": None,
            "directional_active_accuracy_ci95_high": None,
            "custom_mean_cost_ci95_low": None,
            "custom_mean_cost_ci95_high": None,
        }

    rng = np.random.default_rng(int(seed))
    daa = np.zeros(int(n_bootstrap), dtype=np.float64)
    cst = np.zeros(int(n_bootstrap), dtype=np.float64)
    for i in range(int(n_bootstrap)):
        idx = rng.integers(0, n_blocks, size=n_blocks)
        yt = np.concatenate([truth_blocks[int(j)] for j in idx])
        yp = np.concatenate([pred_blocks[int(j)] for j in idx])
        ev = _compute_directional_hold_eval(yt, yp)
        daa[i] = float(ev["directional_active_accuracy"])
        cst[i] = float(_compute_custom_cost_truth4(yt, yp)["mean_cost"])

    return {
        "directional_active_accuracy_ci95_low": float(np.quantile(daa, 0.025)),
        "directional_active_accuracy_ci95_high": float(np.quantile(daa, 0.975)),
        "custom_mean_cost_ci95_low": float(np.quantile(cst, 0.025)),
        "custom_mean_cost_ci95_high": float(np.quantile(cst, 0.975)),
    }


@dataclass
class AlignmentData:
    mode: str
    anchors: pl.DataFrame
    p_up: np.ndarray
    p_down: np.ndarray
    p_hold: np.ndarray
    available: np.ndarray
    pred_breakfree: np.ndarray
    pred_dir4: np.ndarray
    pred_direction: np.ndarray
    candidate_ids: list[str]
    candidate_units: np.ndarray
    candidate_targets: np.ndarray
    timeframe_weights: np.ndarray
    winner_wins: np.ndarray
    batch_order: list[int]
    batch_ranges: dict[int, tuple[int, int]]


def _argmax3(up: np.ndarray, down: np.ndarray, hold: np.ndarray) -> np.ndarray:
    arr = np.stack([up, down, hold], axis=1)
    pred = np.argmax(arr, axis=1).astype(np.int16)
    nan_mask = ~np.isfinite(arr).any(axis=1)
    pred[nan_mask] = NO_SIGNAL
    return pred


def _argmax2(up: np.ndarray, down: np.ndarray) -> np.ndarray:
    arr = np.stack([up, down], axis=1)
    pred = np.argmax(arr, axis=1).astype(np.int16)
    nan_mask = ~np.isfinite(arr).any(axis=1)
    pred[nan_mask] = NO_SIGNAL
    return pred


def _build_alignment_data(
    *,
    aligned_df: pl.DataFrame,
    candidate_meta: pl.DataFrame,
    anchor_truth: pl.DataFrame,
    mode: str,
) -> AlignmentData:
    anchors = (
        anchor_truth.select(["pred_batch", "anchor_15m_ts", "truth_breakfree", "truth_4dir"])
        .sort(["pred_batch", "anchor_15m_ts"])
        .with_row_index("anchor_idx")
    )

    candidate_index = candidate_meta.with_row_index("candidate_idx")

    adf = (
        aligned_df.filter(pl.col("alignment_mode") == mode)
        .with_columns(pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id"))
        .join(candidate_index.select(["candidate_id", "candidate_idx"]), on="candidate_id", how="inner")
        .join(anchors.select(["anchor_idx", "pred_batch", "anchor_15m_ts"]), on=["pred_batch", "anchor_15m_ts"], how="inner")
        .select(
            [
                "anchor_idx",
                "candidate_idx",
                "p_up",
                "p_down",
                "p_hold",
                "row_count",
                "row_count_expected",
                "row_count_match",
            ]
        )
        .sort(["anchor_idx", "candidate_idx"])
        .unique(subset=["anchor_idx", "candidate_idx"], keep="first")
    )

    n_a = int(anchors.height)
    n_c = int(candidate_index.height)

    p_up = np.full((n_a, n_c), np.nan, dtype=np.float32)
    p_down = np.full((n_a, n_c), np.nan, dtype=np.float32)
    p_hold = np.full((n_a, n_c), np.nan, dtype=np.float32)

    a_idx = adf["anchor_idx"].to_numpy()
    c_idx = adf["candidate_idx"].to_numpy()
    p_up[a_idx, c_idx] = adf["p_up"].cast(pl.Float32).to_numpy()
    p_down[a_idx, c_idx] = adf["p_down"].cast(pl.Float32).to_numpy()
    p_hold[a_idx, c_idx] = adf["p_hold"].cast(pl.Float32).to_numpy()
    available = np.isfinite(p_up)

    pred_breakfree = _argmax3(
        np.where(available, p_up, np.nan),
        np.where(available, p_down, np.nan),
        np.where(available, p_hold, np.nan),
    )
    pred_dir4 = _argmax2(np.where(available, p_up, np.nan), np.where(available, p_down, np.nan))
    candidate_targets = np.array(candidate_index["target"].to_list(), dtype=object)
    break_mask = candidate_targets == TARGET_BREAKFREE
    pred_direction = pred_dir4.copy()
    if np.any(break_mask):
        pred_direction[:, break_mask] = pred_breakfree[:, break_mask]

    batch_order = anchors["pred_batch"].unique(maintain_order=True).to_list()
    batch_ranges: dict[int, tuple[int, int]] = {}
    for b in batch_order:
        bdf = anchors.filter(pl.col("pred_batch") == b)
        start = int(bdf["anchor_idx"].min())
        end = int(bdf["anchor_idx"].max()) + 1
        batch_ranges[int(b)] = (start, end)

    return AlignmentData(
        mode=mode,
        anchors=anchors,
        p_up=p_up,
        p_down=p_down,
        p_hold=p_hold,
        available=available,
        pred_breakfree=pred_breakfree,
        pred_dir4=pred_dir4,
        pred_direction=pred_direction,
        candidate_ids=candidate_index["candidate_id"].to_list(),
        candidate_units=np.array(candidate_index["unit"].to_list(), dtype=object),
        candidate_targets=candidate_targets,
        timeframe_weights=np.array([TIMEFRAME_W[str(v)] for v in candidate_index["timeframe"].to_list()], dtype=np.float32),
        winner_wins=np.array(candidate_index["winner_wins"].to_list(), dtype=np.float32),
        batch_order=[int(x) for x in batch_order],
        batch_ranges=batch_ranges,
    )


def _ensemble_target(
    *,
    data: AlignmentData,
    anchor_slice: slice,
    selected_idx: np.ndarray,
    base_weights: np.ndarray,
    target_mode: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = anchor_slice.stop - anchor_slice.start
    if n <= 0:
        return (
            np.empty(0, dtype=np.int16),
            np.empty(0, dtype=np.float32),
            np.empty(0, dtype=np.float32),
            np.empty(0, dtype=np.float32),
        )

    if selected_idx.size == 0:
        return (
            np.full(n, NO_SIGNAL, dtype=np.int16),
            np.full(n, np.nan, dtype=np.float32),
            np.full(n, np.nan, dtype=np.float32),
            np.full(n, np.nan, dtype=np.float32),
        )

    ws = base_weights[selected_idx] * data.timeframe_weights[selected_idx]
    up = data.p_up[anchor_slice, :][:, selected_idx]
    down = data.p_down[anchor_slice, :][:, selected_idx]
    hold = data.p_hold[anchor_slice, :][:, selected_idx]
    avail = data.available[anchor_slice, :][:, selected_idx]

    wmat = ws.reshape(1, -1) * avail.astype(np.float32)
    den = wmat.sum(axis=1)

    up_num = np.sum(np.where(avail, up, 0.0) * ws.reshape(1, -1), axis=1)
    down_num = np.sum(np.where(avail, down, 0.0) * ws.reshape(1, -1), axis=1)
    hold_num = np.sum(np.where(avail, hold, 0.0) * ws.reshape(1, -1), axis=1)

    p_up = np.where(den > 0, up_num / den, np.nan)
    p_down = np.where(den > 0, down_num / den, np.nan)
    p_hold = np.where(den > 0, hold_num / den, np.nan)

    if target_mode == TARGET_BREAKFREE:
        pred = _argmax3(p_up, p_down, p_hold)
    elif target_mode == TARGET_4CLASS:
        pred = _argmax2(p_up, p_down)
    else:
        raise ValueError(target_mode)

    pred = pred.astype(np.int16)
    pred[den <= 0] = NO_SIGNAL
    return pred, p_up.astype(np.float32), p_down.astype(np.float32), p_hold.astype(np.float32)


def _compose_final(
    *,
    rule: str,
    pred_breakfree: np.ndarray,
    pred_4dir: np.ndarray,
    score_breakfree: np.ndarray,
    score_4dir: np.ndarray,
    tau: float,
    tau_up: float | None = None,
    tau_down: float | None = None,
    prob_up_break: np.ndarray | None = None,
    prob_down_break: np.ndarray | None = None,
    prob_up_4: np.ndarray | None = None,
    prob_down_4: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    n = pred_breakfree.size
    final_pred = np.full(n, NO_SIGNAL, dtype=np.int16)
    score_final = np.full(n, np.nan, dtype=np.float32)

    if rule == "agreement_hold":
        hold_mask = pred_breakfree == HOLD
        agree_up = (pred_breakfree == UP) & (pred_4dir == UP)
        agree_down = (pred_breakfree == DOWN) & (pred_4dir == DOWN)
        disagree_dir = (
            ((pred_breakfree == UP) & (pred_4dir == DOWN))
            | ((pred_breakfree == DOWN) & (pred_4dir == UP))
            | ((pred_breakfree == UP) & (pred_4dir == NO_SIGNAL))
            | ((pred_breakfree == DOWN) & (pred_4dir == NO_SIGNAL))
        )

        final_pred[hold_mask] = HOLD
        final_pred[agree_up] = UP
        final_pred[agree_down] = DOWN
        final_pred[disagree_dir] = HOLD
        score_final = 0.5 * (score_breakfree + score_4dir)
        return final_pred, score_final.astype(np.float32)

    if rule == "weighted_band":
        score = 0.5 * (score_breakfree + score_4dir)
        score_final = score.astype(np.float32)
        valid = np.isfinite(score)
        final_pred[valid & (score > tau)] = UP
        final_pred[valid & (score < -tau)] = DOWN
        final_pred[valid & (np.abs(score) <= tau)] = HOLD
        # if breakfree explicitly says HOLD, force HOLD when available
        hold_force = (pred_breakfree == HOLD) & valid
        final_pred[hold_force] = HOLD
        return final_pred, score_final

    if rule == "breakfree_gate_weighted":
        score = 0.65 * score_breakfree + 0.35 * score_4dir
        score_final = score.astype(np.float32)
        valid = np.isfinite(score)
        # breakfree HOLD is a hard gate.
        final_pred[valid & (pred_breakfree == HOLD)] = HOLD
        active = valid & (pred_breakfree != HOLD)
        final_pred[active & (score > tau)] = UP
        final_pred[active & (score < -tau)] = DOWN
        final_pred[active & (np.abs(score) <= tau)] = HOLD
        return final_pred, score_final

    if rule == "strict_agreement_margin":
        score_final = (0.5 * (score_breakfree + score_4dir)).astype(np.float32)
        valid = np.isfinite(score_breakfree) & np.isfinite(score_4dir)
        agree_up = (pred_breakfree == UP) & (pred_4dir == UP)
        agree_down = (pred_breakfree == DOWN) & (pred_4dir == DOWN)
        agree = agree_up | agree_down
        strong = (np.abs(score_breakfree) >= tau) & (np.abs(score_4dir) >= tau)
        final_pred[valid & (pred_breakfree == HOLD)] = HOLD
        final_pred[valid & agree & strong & agree_up] = UP
        final_pred[valid & agree & strong & agree_down] = DOWN
        final_pred[valid & (~agree | ~strong)] = HOLD
        return final_pred, score_final

    if rule == "dual_ova_thresholds":
        if (
            prob_up_break is not None
            and prob_down_break is not None
            and prob_up_4 is not None
            and prob_down_4 is not None
        ):
            up_score = 0.5 * (prob_up_break + prob_up_4)
            down_score = 0.5 * (prob_down_break + prob_down_4)
            valid = (
                np.isfinite(prob_up_break)
                & np.isfinite(prob_down_break)
                & np.isfinite(prob_up_4)
                & np.isfinite(prob_down_4)
            )
        else:
            valid = np.isfinite(score_breakfree) & np.isfinite(score_4dir)
            up_break = 0.5 * (score_breakfree + 1.0)
            up_4 = 0.5 * (score_4dir + 1.0)
            dn_break = 0.5 * (-score_breakfree + 1.0)
            dn_4 = 0.5 * (-score_4dir + 1.0)
            up_score = 0.5 * (up_break + up_4)
            down_score = 0.5 * (dn_break + dn_4)
        score_final = (up_score - down_score).astype(np.float32)

        tau_up_eff = float(tau if tau_up is None else tau_up)
        tau_down_eff = float(tau if tau_down is None else tau_down)

        up_fire = valid & (up_score >= tau_up_eff) & (up_score > down_score)
        down_fire = valid & (down_score >= tau_down_eff) & (down_score > up_score)
        hold_force = valid & (pred_breakfree == HOLD)

        final_pred[valid] = HOLD
        final_pred[up_fire & (~down_fire)] = UP
        final_pred[down_fire & (~up_fire)] = DOWN
        final_pred[hold_force] = HOLD
        return final_pred, score_final

    if rule == "specialist_rare_gate":
        if prob_up_break is None or prob_down_break is None:
            raise ValueError("specialist_rare_gate requires specialist up/down scores")
        up_score = np.where(np.isfinite(prob_up_break), prob_up_break, 0.0)
        down_score = np.where(np.isfinite(prob_down_break), prob_down_break, 0.0)
        any_score = np.isfinite(prob_up_break) | np.isfinite(prob_down_break)
        score_final = (up_score - down_score).astype(np.float32)

        final_pred[any_score] = HOLD
        up_fire = any_score & (up_score >= float(tau)) & (up_score > down_score)
        down_fire = any_score & (down_score >= float(tau)) & (down_score > up_score)
        final_pred[up_fire] = UP
        final_pred[down_fire] = DOWN
        final_pred[any_score & (pred_breakfree == HOLD)] = HOLD
        return final_pred, score_final

    raise ValueError(f"Unknown final rule: {rule}")


def _objective_target(
    *,
    data: AlignmentData,
    history_start: int,
    history_end: int,
    selected_idx: np.ndarray,
    target_mode: str,
) -> float:
    hs = max(0, min(int(history_start), int(history_end)))
    he = int(history_end)
    if he - hs <= 0:
        return 0.0
    base = np.ones(len(data.candidate_ids), dtype=np.float32)
    pred, _, _, _ = _ensemble_target(
        data=data,
        anchor_slice=slice(hs, he),
        selected_idx=selected_idx,
        base_weights=base,
        target_mode=target_mode,
    )

    if target_mode == TARGET_BREAKFREE:
        truth = data.anchors["truth_breakfree"].to_numpy()[hs:he].astype(np.int16)
        pred_eval = pred.copy()
        pred_eval[pred_eval == NO_SIGNAL] = HOLD
        conf = _build_confusion(truth, pred_eval, labels=[UP, DOWN, HOLD])
        return _macro_f1_from_confusion(conf)

    truth2 = data.anchors["truth_4dir"].to_numpy()[hs:he].astype(np.int16)
    valid = truth2 >= 0
    yt = truth2[valid]
    yp = pred[valid].copy()
    yp[yp == NO_SIGNAL] = DOWN
    conf = _build_confusion(yt, yp, labels=[UP, DOWN])
    return _macro_f1_from_confusion(conf)


def _objective_final(
    *,
    data: AlignmentData,
    history_start: int,
    history_end: int,
    selected_break: np.ndarray,
    selected_4dir: np.ndarray,
) -> float:
    hs = max(0, min(int(history_start), int(history_end)))
    he = int(history_end)
    if he - hs <= 0:
        return 0.0

    base = np.ones(len(data.candidate_ids), dtype=np.float32)
    pb, ub, db, _ = _ensemble_target(
        data=data,
        anchor_slice=slice(hs, he),
        selected_idx=selected_break,
        base_weights=base,
        target_mode=TARGET_BREAKFREE,
    )
    p4, u4, d4, _ = _ensemble_target(
        data=data,
        anchor_slice=slice(hs, he),
        selected_idx=selected_4dir,
        base_weights=base,
        target_mode=TARGET_4CLASS,
    )
    fb, _ = _compose_final(
        rule="agreement_hold",
        pred_breakfree=pb,
        pred_4dir=p4,
        score_breakfree=ub - db,
        score_4dir=u4 - d4,
        tau=0.0,
    )
    truth = data.anchors["truth_breakfree"].to_numpy()[hs:he].astype(np.int16)
    pred_eval = fb.copy()
    pred_eval[pred_eval == NO_SIGNAL] = HOLD
    conf = _build_confusion(truth, pred_eval, labels=[UP, DOWN, HOLD])
    return _macro_f1_from_confusion(conf)


def _can_remove(
    *,
    remove_idx: int,
    selected: np.ndarray,
    candidate_units: np.ndarray,
    min_per_unit: int,
    core_units: set[str],
) -> bool:
    unit = str(candidate_units[remove_idx])
    if unit not in core_units:
        return True
    unit_count = int(np.sum(candidate_units[selected] == unit))
    return (unit_count - 1) >= min_per_unit


def _hybrid_staged_selection(
    *,
    data: AlignmentData,
    history_start: int,
    history_end: int,
    min_per_unit: int,
    max_prune_iterations: int,
    verbose: bool,
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    logs: list[dict[str, Any]] = []

    units_b = {
        "1m/target_breakfree",
        "5m/target_breakfree",
        "15m/target_breakfree",
    }
    units_4 = {
        "1m/target_4class",
        "5m/target_4class",
        "15m/target_4class",
    }

    idx_all = np.arange(len(data.candidate_ids), dtype=np.int32)
    idx_b = idx_all[data.candidate_targets == TARGET_BREAKFREE]
    idx_4 = idx_all[data.candidate_targets == TARGET_4CLASS]

    selected_b = idx_b.copy()
    selected_4 = idx_4.copy()

    def _prune_target(selected: np.ndarray, target_mode: str, core_units: set[str], stage_name: str) -> np.ndarray:
        selected_local = selected.copy()
        iter_no = 0
        while iter_no < max_prune_iterations:
            iter_no += 1
            base_obj = _objective_target(
                data=data,
                history_start=history_start,
                history_end=history_end,
                selected_idx=selected_local,
                target_mode=target_mode,
            )
            best_idx = None
            best_obj = base_obj

            for c in selected_local.tolist():
                if not _can_remove(
                    remove_idx=int(c),
                    selected=selected_local,
                    candidate_units=data.candidate_units,
                    min_per_unit=min_per_unit,
                    core_units=core_units,
                ):
                    continue
                trial = selected_local[selected_local != c]
                obj = _objective_target(
                    data=data,
                    history_start=history_start,
                    history_end=history_end,
                    selected_idx=trial,
                    target_mode=target_mode,
                )
                if obj > best_obj + 1e-12:
                    best_obj = obj
                    best_idx = int(c)

            if best_idx is None:
                break

            selected_local = selected_local[selected_local != best_idx]
            logs.append(
                {
                    "stage": stage_name,
                    "target_mode": target_mode,
                    "op": "remove",
                    "candidate_id": data.candidate_ids[best_idx],
                    "unit": str(data.candidate_units[best_idx]),
                    "objective_before": float(base_obj),
                    "objective_after": float(best_obj),
                    "delta": float(best_obj - base_obj),
                }
            )

        return selected_local

    # Stage A: target-only prune
    selected_b = _prune_target(
        selected=selected_b,
        target_mode=TARGET_BREAKFREE,
        core_units=units_b,
        stage_name="A_target_only_prune",
    )
    selected_4 = _prune_target(
        selected=selected_4,
        target_mode=TARGET_4CLASS,
        core_units=units_4,
        stage_name="A_target_only_prune",
    )

    # Stage B: cross-target augmentation (greedy positive-delta additions)
    def _augment(
        selected: np.ndarray,
        target_mode: str,
        opposite_pool: np.ndarray,
    ) -> np.ndarray:
        selected_local = selected.copy()
        order = sorted(
            [int(c) for c in opposite_pool],
            key=lambda c: (-float(data.winner_wins[c]), data.candidate_ids[c]),
        )
        improved = True
        while improved:
            improved = False
            base_obj = _objective_target(
                data=data,
                history_start=history_start,
                history_end=history_end,
                selected_idx=selected_local,
                target_mode=target_mode,
            )
            best_idx = None
            best_obj = base_obj
            for c in order:
                if c in selected_local:
                    continue
                trial = np.sort(np.append(selected_local, c))
                obj = _objective_target(
                    data=data,
                    history_start=history_start,
                    history_end=history_end,
                    selected_idx=trial,
                    target_mode=target_mode,
                )
                if obj > best_obj + 1e-12:
                    best_obj = obj
                    best_idx = c
            if best_idx is not None:
                selected_local = np.sort(np.append(selected_local, best_idx))
                logs.append(
                    {
                        "stage": "B_cross_target_augment",
                        "target_mode": target_mode,
                        "op": "add",
                        "candidate_id": data.candidate_ids[int(best_idx)],
                        "unit": str(data.candidate_units[int(best_idx)]),
                        "objective_before": float(base_obj),
                        "objective_after": float(best_obj),
                        "delta": float(best_obj - base_obj),
                    }
                )
                improved = True
        return selected_local

    selected_b = _augment(selected_b, TARGET_BREAKFREE, idx_4)
    selected_4 = _augment(selected_4, TARGET_4CLASS, idx_b)

    # Stage C: global backward prune on final objective
    iter_no = 0
    while iter_no < max_prune_iterations:
        iter_no += 1
        base_obj = _objective_final(
            data=data,
            history_start=history_start,
            history_end=history_end,
            selected_break=selected_b,
            selected_4dir=selected_4,
        )
        best_obj = base_obj
        best_remove: tuple[str, int] | None = None

        for c in selected_b.tolist():
            if not _can_remove(
                remove_idx=int(c),
                selected=selected_b,
                candidate_units=data.candidate_units,
                min_per_unit=min_per_unit,
                core_units=units_b,
            ):
                continue
            trial_b = selected_b[selected_b != c]
            obj = _objective_final(
                data=data,
                history_start=history_start,
                history_end=history_end,
                selected_break=trial_b,
                selected_4dir=selected_4,
            )
            if obj > best_obj + 1e-12:
                best_obj = obj
                best_remove = ("breakfree", int(c))

        for c in selected_4.tolist():
            if not _can_remove(
                remove_idx=int(c),
                selected=selected_4,
                candidate_units=data.candidate_units,
                min_per_unit=min_per_unit,
                core_units=units_4,
            ):
                continue
            trial_4 = selected_4[selected_4 != c]
            obj = _objective_final(
                data=data,
                history_start=history_start,
                history_end=history_end,
                selected_break=selected_b,
                selected_4dir=trial_4,
            )
            if obj > best_obj + 1e-12:
                best_obj = obj
                best_remove = ("dir4", int(c))

        if best_remove is None:
            break

        which, cid = best_remove
        if which == "breakfree":
            selected_b = selected_b[selected_b != cid]
        else:
            selected_4 = selected_4[selected_4 != cid]

        logs.append(
            {
                "stage": "C_global_prune",
                "target_mode": which,
                "op": "remove",
                "candidate_id": data.candidate_ids[cid],
                "unit": str(data.candidate_units[cid]),
                "objective_before": float(base_obj),
                "objective_after": float(best_obj),
                "delta": float(best_obj - base_obj),
            }
        )

    if verbose:
        print(
            f"  [selection/{data.mode}] breakfree={selected_b.size} dir4={selected_4.size} logs={len(logs)}"
            ,
            flush=True,
        )

    return np.sort(selected_b), np.sort(selected_4), logs


def _compute_recency_weights(n: int, decay: float = 0.995) -> np.ndarray:
    if n <= 0:
        return np.empty(0, dtype=np.float64)
    # Newest sample gets weight 1.0
    return decay ** np.arange(n - 1, -1, -1, dtype=np.float64)


def _kalman_filter_last_estimate(
    observations: np.ndarray,
    *,
    prior_mean: float,
    process_noise: float,
    measurement_noise: float,
) -> float:
    """Return final scalar Kalman estimate for a bounded [0,1] quality stream.

    This is used on history-only candidate quality observations (e.g., p_true),
    so it is leakage-safe in walk-forward when observations are restricted to t'<t.
    """
    if observations.size == 0:
        return float(np.clip(prior_mean, 0.0, 1.0))

    q = float(max(process_noise, 1e-9))
    r = float(max(measurement_noise, 1e-9))
    x = float(np.clip(prior_mean, 0.0, 1.0))
    p = 1.0

    for z in observations.astype(np.float64):
        if not np.isfinite(z):
            continue
        # Predict
        p = p + q
        # Update
        k = p / (p + r)
        x = x + k * (float(z) - x)
        p = (1.0 - k) * p

    return float(np.clip(x, 0.0, 1.0))


def _compute_method_weights(
    *,
    data: AlignmentData,
    target_mode: str,
    selected_idx: np.ndarray,
    history_end: int,
    method: str,
    kalman_process_noise: float,
    kalman_measurement_noise: float,
    dma_forgetting_factor: float,
    dma_fixed_share_alpha: float,
    ewaf_brier_eta: float,
) -> np.ndarray:
    n_total = len(data.candidate_ids)
    weights = np.zeros(n_total, dtype=np.float64)
    if selected_idx.size == 0:
        return weights

    # Static baselines
    winner_base = np.maximum(data.winner_wins.astype(np.float64) + 1.0, 1.0)

    if method == "uniform":
        weights[selected_idx] = 1.0
    elif method == "winner_weighted":
        weights[selected_idx] = winner_base[selected_idx]
    else:
        if history_end <= 0:
            weights[selected_idx] = winner_base[selected_idx]
        else:
            rw = _compute_recency_weights(history_end, decay=0.995)

            if target_mode == TARGET_BREAKFREE:
                truth = data.anchors["truth_breakfree"].to_numpy()[:history_end].astype(np.int16)
                pred = data.pred_breakfree[:history_end, :]
            else:
                truth = data.anchors["truth_4dir"].to_numpy()[:history_end].astype(np.int16)
                pred = data.pred_dir4[:history_end, :]

            avail = data.available[:history_end, :]

            # Winner-weighted majority prediction for diversity reference.
            maj_w = winner_base[selected_idx].copy()
            maj_w = maj_w / np.sum(maj_w)
            if target_mode == TARGET_BREAKFREE:
                p_up = data.p_up[:history_end, :][:, selected_idx]
                p_down = data.p_down[:history_end, :][:, selected_idx]
                p_hold = data.p_hold[:history_end, :][:, selected_idx]
                av = data.available[:history_end, :][:, selected_idx]
                up_num = np.sum(np.where(av, p_up, 0.0) * maj_w.reshape(1, -1), axis=1)
                dn_num = np.sum(np.where(av, p_down, 0.0) * maj_w.reshape(1, -1), axis=1)
                hd_num = np.sum(np.where(av, p_hold, 0.0) * maj_w.reshape(1, -1), axis=1)
                den = np.sum(av.astype(np.float64) * maj_w.reshape(1, -1), axis=1)
                mup = np.where(den > 0, up_num / den, np.nan)
                mdn = np.where(den > 0, dn_num / den, np.nan)
                mhd = np.where(den > 0, hd_num / den, np.nan)
                maj_pred = _argmax3(mup, mdn, mhd)
            else:
                p_up = data.p_up[:history_end, :][:, selected_idx]
                p_down = data.p_down[:history_end, :][:, selected_idx]
                av = data.available[:history_end, :][:, selected_idx]
                up_num = np.sum(np.where(av, p_up, 0.0) * maj_w.reshape(1, -1), axis=1)
                dn_num = np.sum(np.where(av, p_down, 0.0) * maj_w.reshape(1, -1), axis=1)
                den = np.sum(av.astype(np.float64) * maj_w.reshape(1, -1), axis=1)
                mup = np.where(den > 0, up_num / den, np.nan)
                mdn = np.where(den > 0, dn_num / den, np.nan)
                maj_pred = _argmax2(mup, mdn)

            for c in selected_idx.tolist():
                c = int(c)
                m = avail[:, c] & (truth >= 0) & (pred[:, c] >= 0)
                if not np.any(m):
                    weights[c] = 0.01
                    continue

                rw_m = rw[m]
                if rw_m.sum() <= 0:
                    rw_m = np.ones_like(rw_m)

                correct = (pred[m, c] == truth[m]).astype(np.float64)
                acc = float(np.sum(correct * rw_m) / np.sum(rw_m))
                prior_w = float(winner_base[c] / np.sum(winner_base[selected_idx]))

                if target_mode == TARGET_BREAKFREE:
                    t = truth[m]
                    p_true = np.where(
                        t == UP,
                        data.p_up[:history_end, c][m],
                        np.where(t == DOWN, data.p_down[:history_end, c][m], data.p_hold[:history_end, c][m]),
                    )
                    p_true = np.clip(p_true.astype(np.float64), 1e-9, 1.0)
                    ll = -np.log(p_true)
                    y_up = (t == UP).astype(np.float64)
                    y_dn = (t == DOWN).astype(np.float64)
                    y_hd = (t == HOLD).astype(np.float64)
                    pu = np.clip(data.p_up[:history_end, c][m].astype(np.float64), 0.0, 1.0)
                    pd = np.clip(data.p_down[:history_end, c][m].astype(np.float64), 0.0, 1.0)
                    ph = np.clip(data.p_hold[:history_end, c][m].astype(np.float64), 0.0, 1.0)
                    brier = (pu - y_up) ** 2 + (pd - y_dn) ** 2 + (ph - y_hd) ** 2
                else:
                    t = truth[m]
                    p_true = np.where(
                        t == UP,
                        data.p_up[:history_end, c][m],
                        data.p_down[:history_end, c][m],
                    )
                    p_true = np.clip(p_true.astype(np.float64), 1e-9, 1.0)
                    ll = -np.log(p_true)
                    y_up = (t == UP).astype(np.float64)
                    y_dn = (t == DOWN).astype(np.float64)
                    pu = np.clip(data.p_up[:history_end, c][m].astype(np.float64), 0.0, 1.0)
                    pd = np.clip(data.p_down[:history_end, c][m].astype(np.float64), 0.0, 1.0)
                    brier = (pu - y_up) ** 2 + (pd - y_dn) ** 2

                loss = float(np.sum(ll * rw_m) / np.sum(rw_m))
                exp_logloss = float(np.exp(-loss))
                brier_score = float(np.sum(brier * rw_m) / np.sum(rw_m))
                exp_brier = float(np.exp(-brier_score))

                if method == "history_acc_ewma":
                    weights[c] = max(acc, 0.01)
                    continue

                if method == "history_logloss_ewma":
                    weights[c] = max(exp_logloss, 0.01)
                    continue

                if method == "history_brier_ewma":
                    weights[c] = max(exp_brier, 0.01)
                    continue

                if method == "kalman_score_filter":
                    # History-only candidate quality smoothing with scalar Kalman filter.
                    # Uses p_true sequence from anchors before current batch.
                    kal_est = _kalman_filter_last_estimate(
                        p_true.astype(np.float64),
                        prior_mean=float(np.clip(exp_brier, 0.01, 0.99)),
                        process_noise=float(kalman_process_noise),
                        measurement_noise=float(kalman_measurement_noise),
                    )
                    # Stabilize low-support candidates by blending with exp_brier baseline.
                    support = int(np.sum(m))
                    support_frac = float(min(1.0, support / 32.0))
                    blended = support_frac * kal_est + (1.0 - support_frac) * exp_brier
                    weights[c] = max(float(blended), 0.01)
                    continue

                if method == "acc_logloss_blend":
                    weights[c] = max(float(np.sqrt(max(acc, 0.0) * max(exp_logloss, 0.0))), 0.01)
                    continue

                if method == "winner_history_blend":
                    weights[c] = max(0.5 * prior_w + 0.5 * exp_logloss, 0.01)
                    continue

                if method in {"dma_logscore", "ewaf_brier_share"}:
                    # Handled in vectorized DMA block below after per-candidate stats loop.
                    continue

                if method == "diversity_weighted":
                    md = maj_pred[m]
                    pc = pred[m, c]
                    dmask = md >= 0
                    if np.any(dmask):
                        rw_d = rw_m[dmask]
                        if rw_d.sum() <= 0:
                            rw_d = np.ones_like(rw_d)
                        div = float(np.sum((pc[dmask] != md[dmask]).astype(np.float64) * rw_d) / np.sum(rw_d))
                    else:
                        div = 0.0
                    weights[c] = max(acc, 0.01) * (0.5 + div)
                    continue

                raise ValueError(f"Unknown weight method: {method}")

            if method == "dma_logscore":
                # Dynamic Model Averaging (forgetting-factor + fixed-share):
                # w_t(c) ∝ [w_{t-1}(c)]^lambda * p(y_t | c), computed strictly on t<history_end.
                # We use candidate predictive probabilities for the observed class label.
                csel = np.asarray(selected_idx, dtype=np.int32)
                k = int(csel.size)
                if k > 0:
                    lam = float(np.clip(dma_forgetting_factor, 0.90, 1.0))
                    alpha = float(np.clip(dma_fixed_share_alpha, 0.0, 0.25))
                    w = winner_base[csel].astype(np.float64)
                    s0 = float(np.sum(w))
                    if s0 <= 0:
                        w = np.full(k, 1.0 / max(k, 1), dtype=np.float64)
                    else:
                        w = w / s0

                    av_hist = avail[:, csel]
                    pu_hist = data.p_up[:history_end, :][:, csel]
                    pd_hist = data.p_down[:history_end, :][:, csel]
                    ph_hist = data.p_hold[:history_end, :][:, csel]

                    for t in range(int(history_end)):
                        # Forgetting + fixed-share before incorporating new evidence.
                        w = np.power(np.clip(w, 1e-12, None), lam)
                        if alpha > 0.0:
                            w = (1.0 - alpha) * w + (alpha / float(k))

                        yt = int(truth[t])
                        if yt < 0:
                            sw = float(np.sum(w))
                            w = (w / sw) if sw > 0 else np.full(k, 1.0 / float(k), dtype=np.float64)
                            continue

                        av_t = av_hist[t]
                        if target_mode == TARGET_BREAKFREE:
                            if yt == UP:
                                like = np.where(av_t, pu_hist[t], 1.0)
                            elif yt == DOWN:
                                like = np.where(av_t, pd_hist[t], 1.0)
                            else:
                                like = np.where(av_t, ph_hist[t], 1.0)
                        else:
                            if yt == UP:
                                like = np.where(av_t, pu_hist[t], 1.0)
                            else:
                                like = np.where(av_t, pd_hist[t], 1.0)
                        w = w * np.clip(like.astype(np.float64), 1e-9, 1.0)
                        sw = float(np.sum(w))
                        w = (w / sw) if sw > 0 else np.full(k, 1.0 / float(k), dtype=np.float64)

                    weights[csel] = np.maximum(w, 1e-6)
            elif method == "ewaf_brier_share":
                # Exponential Weights / Aggregating Algorithm on Brier loss with
                # forgetting-factor and fixed-share mixing for regime shifts.
                csel = np.asarray(selected_idx, dtype=np.int32)
                k = int(csel.size)
                if k > 0:
                    lam = float(np.clip(dma_forgetting_factor, 0.90, 1.0))
                    alpha = float(np.clip(dma_fixed_share_alpha, 0.0, 0.25))
                    eta = float(np.clip(ewaf_brier_eta, 0.1, 20.0))

                    w = winner_base[csel].astype(np.float64)
                    s0 = float(np.sum(w))
                    if s0 <= 0:
                        w = np.full(k, 1.0 / max(k, 1), dtype=np.float64)
                    else:
                        w = w / s0

                    av_hist = avail[:, csel]
                    pu_hist = np.clip(data.p_up[:history_end, :][:, csel], 0.0, 1.0)
                    pd_hist = np.clip(data.p_down[:history_end, :][:, csel], 0.0, 1.0)
                    ph_hist = np.clip(data.p_hold[:history_end, :][:, csel], 0.0, 1.0)

                    for t in range(int(history_end)):
                        w = np.power(np.clip(w, 1e-12, None), lam)
                        if alpha > 0.0:
                            w = (1.0 - alpha) * w + (alpha / float(k))

                        yt = int(truth[t])
                        if yt < 0:
                            sw = float(np.sum(w))
                            w = (w / sw) if sw > 0 else np.full(k, 1.0 / float(k), dtype=np.float64)
                            continue

                        av_t = av_hist[t]
                        if target_mode == TARGET_BREAKFREE:
                            y_up = 1.0 if yt == UP else 0.0
                            y_dn = 1.0 if yt == DOWN else 0.0
                            y_hd = 1.0 if yt == HOLD else 0.0
                            brier_t = (
                                (pu_hist[t] - y_up) ** 2
                                + (pd_hist[t] - y_dn) ** 2
                                + (ph_hist[t] - y_hd) ** 2
                            )
                        else:
                            y_up = 1.0 if yt == UP else 0.0
                            y_dn = 1.0 if yt == DOWN else 0.0
                            brier_t = (pu_hist[t] - y_up) ** 2 + (pd_hist[t] - y_dn) ** 2

                        # Missing candidate row on this anchor -> neutral (no update).
                        mult = np.where(av_t, np.exp(-eta * brier_t), 1.0)
                        w = w * np.clip(mult.astype(np.float64), 1e-12, None)
                        sw = float(np.sum(w))
                        w = (w / sw) if sw > 0 else np.full(k, 1.0 / float(k), dtype=np.float64)

                    weights[csel] = np.maximum(w, 1e-6)

    s = float(np.sum(weights[selected_idx]))
    if s <= 0:
        weights[selected_idx] = 1.0 / float(selected_idx.size)
    else:
        weights[selected_idx] = weights[selected_idx] / s
    return weights.astype(np.float64)


def _fit_specialist_quality(
    *,
    data: AlignmentData,
    history_end: int,
    selected_idx: np.ndarray,
    min_support: int,
    min_safe_accuracy: float,
    max_opposite_rate: float,
    recency_decay: float,
) -> tuple[np.ndarray, np.ndarray]:
    n_total = len(data.candidate_ids)
    q_up = np.zeros(n_total, dtype=np.float64)
    q_down = np.zeros(n_total, dtype=np.float64)
    if history_end <= 0 or selected_idx.size == 0:
        return q_up, q_down

    decay = float(np.clip(recency_decay, 0.90, 1.0))
    rw = _compute_recency_weights(history_end, decay=decay)
    if rw.size == 0:
        return q_up, q_down

    truth_b = data.anchors["truth_breakfree"].to_numpy()[:history_end].astype(np.int16)
    truth_4 = data.anchors["truth_4dir"].to_numpy()[:history_end].astype(np.int16)
    truth4 = _compose_truth4_labels(truth_b, truth_4)
    truth_up_side = (truth4 == TRUTH_UP) | (truth4 == TRUTH_HOLD_UP)
    truth_down_side = (truth4 == TRUTH_DOWN) | (truth4 == TRUTH_HOLD_DOWN)

    pred_hist = data.pred_direction[:history_end, :]
    avail_hist = data.available[:history_end, :]

    for cid in selected_idx.tolist():
        c = int(cid)
        pred_c = pred_hist[:, c]
        avail_c = avail_hist[:, c]

        m_up = avail_c & (pred_c == UP)
        support_up = int(np.sum(m_up))
        if support_up >= int(min_support):
            w = rw[m_up]
            den = float(np.sum(w))
            if den > 0:
                safe_up = float(np.sum(w * truth_up_side[m_up].astype(np.float64)) / den)
                opp_up = float(np.sum(w * truth_down_side[m_up].astype(np.float64)) / den)
                if safe_up >= float(min_safe_accuracy) and opp_up <= float(max_opposite_rate):
                    q_up[c] = max(0.0, safe_up - opp_up) * math.log1p(float(support_up))

        m_down = avail_c & (pred_c == DOWN)
        support_down = int(np.sum(m_down))
        if support_down >= int(min_support):
            w = rw[m_down]
            den = float(np.sum(w))
            if den > 0:
                safe_down = float(np.sum(w * truth_down_side[m_down].astype(np.float64)) / den)
                opp_down = float(np.sum(w * truth_up_side[m_down].astype(np.float64)) / den)
                if safe_down >= float(min_safe_accuracy) and opp_down <= float(max_opposite_rate):
                    q_down[c] = max(0.0, safe_down - opp_down) * math.log1p(float(support_down))

    max_up = float(np.max(q_up))
    max_down = float(np.max(q_down))
    if max_up > 0:
        q_up = q_up / max_up
    if max_down > 0:
        q_down = q_down / max_down
    return q_up, q_down


def _score_specialist_slice(
    *,
    data: AlignmentData,
    anchor_slice: slice,
    selected_idx: np.ndarray,
    quality_up: np.ndarray,
    quality_down: np.ndarray,
    min_votes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = int(anchor_slice.stop - anchor_slice.start)
    if n <= 0:
        return (
            np.empty(0, dtype=np.float32),
            np.empty(0, dtype=np.float32),
            np.empty(0, dtype=np.int16),
            np.empty(0, dtype=np.int16),
        )
    if selected_idx.size == 0:
        return (
            np.full(n, np.nan, dtype=np.float32),
            np.full(n, np.nan, dtype=np.float32),
            np.zeros(n, dtype=np.int16),
            np.zeros(n, dtype=np.int16),
        )

    selected_mask = np.zeros(len(data.candidate_ids), dtype=bool)
    selected_mask[selected_idx] = True

    margins = (data.p_up[anchor_slice, :] - data.p_down[anchor_slice, :]).astype(np.float64)
    avail = data.available[anchor_slice, :]
    pred_dir = data.pred_direction[anchor_slice, :]

    w_up = np.where(selected_mask, quality_up, 0.0).astype(np.float64) * data.timeframe_weights.astype(np.float64)
    w_down = np.where(selected_mask, quality_down, 0.0).astype(np.float64) * data.timeframe_weights.astype(np.float64)

    up_mask = avail & (pred_dir == UP) & (w_up.reshape(1, -1) > 0)
    down_mask = avail & (pred_dir == DOWN) & (w_down.reshape(1, -1) > 0)

    up_votes = np.sum(up_mask, axis=1).astype(np.int16)
    down_votes = np.sum(down_mask, axis=1).astype(np.int16)

    up_den = np.sum(up_mask.astype(np.float64) * w_up.reshape(1, -1), axis=1)
    down_den = np.sum(down_mask.astype(np.float64) * w_down.reshape(1, -1), axis=1)

    up_strength = np.clip(margins, 0.0, None)
    down_strength = np.clip(-margins, 0.0, None)
    up_num = np.sum(np.where(up_mask, up_strength, 0.0) * w_up.reshape(1, -1), axis=1)
    down_num = np.sum(np.where(down_mask, down_strength, 0.0) * w_down.reshape(1, -1), axis=1)

    min_votes_eff = max(int(min_votes), 1)
    up_score = np.full(n, np.nan, dtype=np.float64)
    down_score = np.full(n, np.nan, dtype=np.float64)
    up_where = (up_den > 0) & (up_votes >= min_votes_eff)
    down_where = (down_den > 0) & (down_votes >= min_votes_eff)
    np.divide(up_num, up_den, out=up_score, where=up_where)
    np.divide(down_num, down_den, out=down_score, where=down_where)
    return (
        up_score.astype(np.float32),
        down_score.astype(np.float32),
        up_votes,
        down_votes,
    )


def _select_tau(
    *,
    score_break: np.ndarray,
    score_4: np.ndarray,
    pred_break: np.ndarray,
    pred_4: np.ndarray,
    truth_breakfree: np.ndarray,
    truth_4dir: np.ndarray,
    tau_grid: np.ndarray,
    final_rule: str,
    tau_objective: str,
    tau_fp_penalty: float,
    tau_opposite_fp_penalty: float,
    tau_hold_side_penalty: float,
    tau_opposite_active_penalty: float,
    tau_min_active_coverage: float,
    specialist_up: np.ndarray | None = None,
    specialist_down: np.ndarray | None = None,
) -> float:
    best_tau = float(tau_grid[0])
    best_score = -float("inf")
    best_macro = -1.0
    best_cost = float("inf")
    best_safe = -1.0
    best_dir_cov = -1.0
    best_cov = -1.0
    best_dfp = float("inf")
    best_opp = float("inf")
    best_opp_active = float("inf")
    best_hold_side = float("inf")
    truth4 = _compose_truth4_labels(truth_breakfree, truth_4dir)

    best_feasible_tau: float | None = None
    best_feasible_key: tuple[float, ...] | None = None

    for tau in tau_grid.tolist():
        prob_up_break = None
        prob_down_break = None
        if final_rule == "specialist_rare_gate":
            prob_up_break = specialist_up
            prob_down_break = specialist_down
        pred, _ = _compose_final(
            rule=final_rule,
            pred_breakfree=pred_break,
            pred_4dir=pred_4,
            score_breakfree=score_break,
            score_4dir=score_4,
            tau=float(tau),
            prob_up_break=prob_up_break,
            prob_down_break=prob_down_break,
        )
        ev = _compute_directional_hold_eval(truth4, pred)
        c = _compute_custom_cost_truth4(truth4, pred)
        hs = _hold_side_metrics(truth_breakfree, truth_4dir, pred)
        dfp = float(ev["directional_fp_rate_covered"])
        opp = float(ev["opposite_fp_rate_covered"])
        opp_active = float(ev["opposite_fp_total"] / max(int(ev["directional_pred_count"]), 1))
        hold_side = float(hs["hold_side_cross_error_rate_covered"])
        dir_acc = float(ev["directional_active_accuracy"])
        dir_cov = float(ev["directional_active_coverage"])

        if tau_objective == "risk_aware":
            score = float(
                dir_acc
                - float(tau_fp_penalty) * dfp
                - float(tau_opposite_fp_penalty) * opp
                - float(tau_hold_side_penalty) * hold_side
                - float(tau_opposite_active_penalty) * opp_active
            )
            tau_tiebreak = float(tau)  # prefer larger hold band under ties in risk mode
        else:
            score = float(dir_acc)
            tau_tiebreak = -float(tau)  # legacy preference toward smaller band under ties

        key = (
            score,
            dir_acc,
            dir_cov,
            -float(c["mean_cost"]),
            -dfp,
            -opp,
            -opp_active,
            -hold_side,
            float(ev["directional_safe_accuracy"]),
            float(ev["coverage"]),
            tau_tiebreak,
        )
        best_key = (
            best_score,
            best_macro,
            best_dir_cov,
            -best_cost,
            -best_dfp,
            -best_opp,
            -best_opp_active,
            -best_hold_side,
            best_safe,
            best_cov,
            best_tau,
        )
        if key > best_key:
            best_tau = float(tau)
            best_score = float(score)
            best_macro = float(dir_acc)
            best_dir_cov = float(dir_cov)
            best_cost = float(c["mean_cost"])
            best_safe = float(ev["directional_safe_accuracy"])
            best_cov = float(ev["coverage"])
            best_dfp = float(dfp)
            best_opp = float(opp)
            best_opp_active = float(opp_active)
            best_hold_side = float(hold_side)

        if dir_cov >= float(tau_min_active_coverage):
            if best_feasible_key is None or key > best_feasible_key:
                best_feasible_key = key
                best_feasible_tau = float(tau)

    if best_feasible_tau is not None:
        return float(best_feasible_tau)
    return float(best_tau)


def _select_dual_thresholds(
    *,
    prob_up_break: np.ndarray,
    prob_down_break: np.ndarray,
    prob_up_4: np.ndarray,
    prob_down_4: np.ndarray,
    pred_break: np.ndarray,
    pred_4: np.ndarray,
    truth_breakfree: np.ndarray,
    truth_4dir: np.ndarray,
    ova_threshold_grid: np.ndarray,
    tau_objective: str,
    tau_fp_penalty: float,
    tau_opposite_fp_penalty: float,
    tau_hold_side_penalty: float,
    tau_opposite_active_penalty: float,
    tau_min_active_coverage: float,
) -> tuple[float, float]:
    best_tau_up = float(ova_threshold_grid[0])
    best_tau_down = float(ova_threshold_grid[0])
    best_score = -float("inf")
    best_dir_acc = -1.0
    best_dir_cov = -1.0
    best_cost = float("inf")
    best_opp = float("inf")
    best_opp_active = float("inf")
    best_dfp = float("inf")
    best_hold_side = float("inf")

    best_feasible_pair: tuple[float, float] | None = None
    best_feasible_key: tuple[float, ...] | None = None

    truth4 = _compose_truth4_labels(truth_breakfree, truth_4dir)
    for tau_up in ova_threshold_grid.tolist():
        for tau_down in ova_threshold_grid.tolist():
            pred, _ = _compose_final(
                rule="dual_ova_thresholds",
                pred_breakfree=pred_break,
                pred_4dir=pred_4,
                score_breakfree=prob_up_break - prob_down_break,
                score_4dir=prob_up_4 - prob_down_4,
                tau=0.0,
                tau_up=float(tau_up),
                tau_down=float(tau_down),
                prob_up_break=prob_up_break,
                prob_down_break=prob_down_break,
                prob_up_4=prob_up_4,
                prob_down_4=prob_down_4,
            )
            ev = _compute_directional_hold_eval(truth4, pred)
            c = _compute_custom_cost_truth4(truth4, pred)
            hs = _hold_side_metrics(truth_breakfree, truth_4dir, pred)

            dfp = float(ev["directional_fp_rate_covered"])
            opp = float(ev["opposite_fp_rate_covered"])
            hold_side = float(hs["hold_side_cross_error_rate_covered"])
            dir_acc = float(ev["directional_active_accuracy"])
            dir_cov = float(ev["directional_active_coverage"])
            opp_active = float(ev["opposite_fp_total"] / max(int(ev["directional_pred_count"]), 1))

            if tau_objective == "risk_aware":
                score = float(
                    dir_acc
                    - float(tau_fp_penalty) * dfp
                    - float(tau_opposite_fp_penalty) * opp
                    - float(tau_hold_side_penalty) * hold_side
                    - float(tau_opposite_active_penalty) * opp_active
                )
            else:
                score = float(dir_acc)

            key = (
                score,
                dir_acc,
                dir_cov,
                -float(c["mean_cost"]),
                -dfp,
                -opp,
                -opp_active,
                -hold_side,
                -float(tau_up + tau_down),
                -float(abs(tau_up - tau_down)),
            )
            best_key = (
                best_score,
                best_dir_acc,
                best_dir_cov,
                -best_cost,
                -best_dfp,
                -best_opp,
                -best_opp_active,
                -best_hold_side,
                -float(best_tau_up + best_tau_down),
                -float(abs(best_tau_up - best_tau_down)),
            )
            if key > best_key:
                best_score = float(score)
                best_dir_acc = float(dir_acc)
                best_dir_cov = float(dir_cov)
                best_cost = float(c["mean_cost"])
                best_dfp = float(dfp)
                best_opp = float(opp)
                best_opp_active = float(opp_active)
                best_hold_side = float(hold_side)
                best_tau_up = float(tau_up)
                best_tau_down = float(tau_down)

            if dir_cov >= float(tau_min_active_coverage):
                if best_feasible_key is None or key > best_feasible_key:
                    best_feasible_key = key
                    best_feasible_pair = (float(tau_up), float(tau_down))

    if best_feasible_pair is not None:
        return best_feasible_pair
    return float(best_tau_up), float(best_tau_down)


def _run_walkforward_combo(
    *,
    data: AlignmentData,
    selection_schedule: dict[int, tuple[np.ndarray, np.ndarray]],
    weight_method: str,
    final_rule: str,
    tau_grid: np.ndarray,
    ova_threshold_grid: np.ndarray,
    tau_objective: str,
    tau_fp_penalty: float,
    tau_opposite_fp_penalty: float,
    tau_hold_side_penalty: float,
    tau_opposite_active_penalty: float,
    tau_min_active_coverage: float,
    specialist_min_support: int,
    specialist_min_safe_accuracy: float,
    specialist_max_opposite_rate: float,
    specialist_min_votes: int,
    specialist_recency_decay: float,
    kalman_process_noise: float,
    kalman_measurement_noise: float,
    dma_forgetting_factor: float,
    dma_fixed_share_alpha: float,
    ewaf_brier_eta: float,
    warmup_batches: int,
    recalibrate_every: int,
    progress_every_batches: int,
    verbose: bool,
    progress_log_path: Path | None,
) -> tuple[pl.DataFrame, pl.DataFrame, list[dict[str, Any]]]:
    batch_order = data.batch_order
    if warmup_batches >= len(batch_order):
        raise ValueError(
            f"warmup_batches={warmup_batches} must be < total_batches={len(batch_order)}"
        )

    rows_final: list[dict[str, Any]] = []
    rows_target: list[dict[str, Any]] = []
    calib_logs: list[dict[str, Any]] = []

    current_weights_b = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_weights_4 = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_specialist_up = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_specialist_down = np.zeros(len(data.candidate_ids), dtype=np.float64)
    current_selected_union = np.empty(0, dtype=np.int32)
    current_tau = float(tau_grid[0])
    current_tau_up = float(ova_threshold_grid[0])
    current_tau_down = float(ova_threshold_grid[0])
    last_calib_batch = None
    current_selected_break = np.empty(0, dtype=np.int32)
    current_selected_4dir = np.empty(0, dtype=np.int32)
    wf_t0 = time.perf_counter()
    pred_total = max(int(len(batch_order) - warmup_batches), 1)

    for i, batch in enumerate(batch_order):
        start, end = data.batch_ranges[int(batch)]
        if i < warmup_batches:
            continue

        if int(batch) in selection_schedule:
            current_selected_break, current_selected_4dir = selection_schedule[int(batch)]
            current_selected_union = np.sort(
                np.unique(np.concatenate([current_selected_break, current_selected_4dir]))
            )

        hist_end = start
        if current_selected_union.size == 0:
            current_selected_union = np.sort(
                np.unique(np.concatenate([current_selected_break, current_selected_4dir]))
            )
        should_calib = (i == warmup_batches) or (((i - warmup_batches) % recalibrate_every) == 0)
        pred_idx = int(i - warmup_batches + 1)

        if should_calib:
            _progress_event(
                message=(
                    f"[wf/{data.mode}/{weight_method}/{final_rule}] "
                    f"calib_start batch={int(batch)} pred_idx={pred_idx}/{pred_total} "
                    f"history_end={int(hist_end)} selected_break={int(current_selected_break.size)} "
                    f"selected_4dir={int(current_selected_4dir.size)}"
                ),
                verbose=verbose,
                progress_log_path=progress_log_path,
                payload={
                    "event": "wf_calib_start",
                    "alignment_mode": data.mode,
                    "weight_method": weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "pred_idx": int(pred_idx),
                    "pred_total": int(pred_total),
                    "history_end_anchor": int(hist_end),
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                },
                force_print=verbose,
            )
            current_weights_b = _compute_method_weights(
                data=data,
                target_mode=TARGET_BREAKFREE,
                selected_idx=current_selected_break,
                history_end=hist_end,
                method=weight_method,
                kalman_process_noise=float(kalman_process_noise),
                kalman_measurement_noise=float(kalman_measurement_noise),
                dma_forgetting_factor=float(dma_forgetting_factor),
                dma_fixed_share_alpha=float(dma_fixed_share_alpha),
                ewaf_brier_eta=float(ewaf_brier_eta),
            )
            current_weights_4 = _compute_method_weights(
                data=data,
                target_mode=TARGET_4CLASS,
                selected_idx=current_selected_4dir,
                history_end=hist_end,
                method=weight_method,
                kalman_process_noise=float(kalman_process_noise),
                kalman_measurement_noise=float(kalman_measurement_noise),
                dma_forgetting_factor=float(dma_forgetting_factor),
                dma_fixed_share_alpha=float(dma_fixed_share_alpha),
                ewaf_brier_eta=float(ewaf_brier_eta),
            )

            if final_rule in {
                "weighted_band",
                "breakfree_gate_weighted",
                "strict_agreement_margin",
                "dual_ova_thresholds",
                "specialist_rare_gate",
            }:
                hb_pred_b, hb_up_b, hb_dn_b, _ = _ensemble_target(
                    data=data,
                    anchor_slice=slice(0, hist_end),
                    selected_idx=current_selected_break,
                    base_weights=current_weights_b,
                    target_mode=TARGET_BREAKFREE,
                )
                hb_pred_4, hb_up_4, hb_dn_4, _ = _ensemble_target(
                    data=data,
                    anchor_slice=slice(0, hist_end),
                    selected_idx=current_selected_4dir,
                    base_weights=current_weights_4,
                    target_mode=TARGET_4CLASS,
                )
                truth_hist = data.anchors["truth_breakfree"].to_numpy()[:hist_end].astype(np.int16)
                truth_hist_4 = data.anchors["truth_4dir"].to_numpy()[:hist_end].astype(np.int16)
                if final_rule == "dual_ova_thresholds":
                    current_tau_up, current_tau_down = _select_dual_thresholds(
                        prob_up_break=hb_up_b,
                        prob_down_break=hb_dn_b,
                        prob_up_4=hb_up_4,
                        prob_down_4=hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        ova_threshold_grid=ova_threshold_grid,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                    )
                    current_tau = 0.0
                elif final_rule == "specialist_rare_gate":
                    current_specialist_up, current_specialist_down = _fit_specialist_quality(
                        data=data,
                        history_end=hist_end,
                        selected_idx=current_selected_union,
                        min_support=int(specialist_min_support),
                        min_safe_accuracy=float(specialist_min_safe_accuracy),
                        max_opposite_rate=float(specialist_max_opposite_rate),
                        recency_decay=float(specialist_recency_decay),
                    )
                    sp_up_hist, sp_down_hist, _, _ = _score_specialist_slice(
                        data=data,
                        anchor_slice=slice(0, hist_end),
                        selected_idx=current_selected_union,
                        quality_up=current_specialist_up,
                        quality_down=current_specialist_down,
                        min_votes=int(specialist_min_votes),
                    )
                    current_tau = _select_tau(
                        score_break=hb_up_b - hb_dn_b,
                        score_4=hb_up_4 - hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        tau_grid=tau_grid,
                        final_rule=final_rule,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                        specialist_up=sp_up_hist,
                        specialist_down=sp_down_hist,
                    )
                    current_tau_up = float(current_tau)
                    current_tau_down = float(current_tau)
                else:
                    current_tau = _select_tau(
                        score_break=hb_up_b - hb_dn_b,
                        score_4=hb_up_4 - hb_dn_4,
                        pred_break=hb_pred_b,
                        pred_4=hb_pred_4,
                        truth_breakfree=truth_hist,
                        truth_4dir=truth_hist_4,
                        tau_grid=tau_grid,
                        final_rule=final_rule,
                        tau_objective=tau_objective,
                        tau_fp_penalty=float(tau_fp_penalty),
                        tau_opposite_fp_penalty=float(tau_opposite_fp_penalty),
                        tau_hold_side_penalty=float(tau_hold_side_penalty),
                        tau_opposite_active_penalty=float(tau_opposite_active_penalty),
                        tau_min_active_coverage=float(tau_min_active_coverage),
                    )
                    current_tau_up = float(current_tau)
                    current_tau_down = float(current_tau)
            else:
                current_tau = float(tau_grid[0])
                current_tau_up = float(current_tau)
                current_tau_down = float(current_tau)

            last_calib_batch = int(batch)
            calib_logs.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": weight_method,
                    "final_rule": final_rule,
                    "calib_batch": int(batch),
                    "history_end_anchor": int(hist_end),
                    "history_max_batch": int(batch_order[i - 1]) if i > 0 else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_active_up_count": int(np.sum(current_specialist_up > 0)),
                    "specialist_active_down_count": int(np.sum(current_specialist_down > 0)),
                }
            )
            _progress_event(
                message=(
                    f"[wf/{data.mode}/{weight_method}/{final_rule}] "
                    f"calib_done batch={int(batch)} tau={float(current_tau):.4f} "
                    f"tau_up={float(current_tau_up):.4f} tau_down={float(current_tau_down):.4f}"
                ),
                verbose=verbose,
                progress_log_path=progress_log_path,
                payload={
                    "event": "wf_calib_done",
                    "alignment_mode": data.mode,
                    "weight_method": weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                },
                force_print=verbose,
            )

        pb, ub, db, hb = _ensemble_target(
            data=data,
            anchor_slice=slice(start, end),
            selected_idx=current_selected_break,
            base_weights=current_weights_b,
            target_mode=TARGET_BREAKFREE,
        )
        p4, u4, d4, _ = _ensemble_target(
            data=data,
            anchor_slice=slice(start, end),
            selected_idx=current_selected_4dir,
            base_weights=current_weights_4,
            target_mode=TARGET_4CLASS,
        )

        score_b = ub - db
        score_4 = u4 - d4

        specialist_up_slice: np.ndarray | None = None
        specialist_down_slice: np.ndarray | None = None
        specialist_up_votes = np.zeros(end - start, dtype=np.int16)
        specialist_down_votes = np.zeros(end - start, dtype=np.int16)
        if final_rule == "specialist_rare_gate":
            specialist_up_slice, specialist_down_slice, specialist_up_votes, specialist_down_votes = _score_specialist_slice(
                data=data,
                anchor_slice=slice(start, end),
                selected_idx=current_selected_union,
                quality_up=current_specialist_up,
                quality_down=current_specialist_down,
                min_votes=int(specialist_min_votes),
            )

        final_pred, score_final = _compose_final(
            rule=final_rule,
            pred_breakfree=pb,
            pred_4dir=p4,
            score_breakfree=score_b,
            score_4dir=score_4,
            tau=current_tau,
            tau_up=current_tau_up,
            tau_down=current_tau_down,
            prob_up_break=specialist_up_slice if final_rule == "specialist_rare_gate" else ub,
            prob_down_break=specialist_down_slice if final_rule == "specialist_rare_gate" else db,
            prob_up_4=u4,
            prob_down_4=d4,
        )

        truth_b = data.anchors["truth_breakfree"].to_numpy()[start:end].astype(np.int16)
        truth_4 = data.anchors["truth_4dir"].to_numpy()[start:end].astype(np.int16)
        truth4 = _compose_truth4_labels(truth_b, truth_4)
        anchor_ts = data.anchors["anchor_15m_ts"].to_list()[start:end]

        for j in range(end - start):
            rows_target.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_breakfree": float(score_b[j]) if np.isfinite(score_b[j]) else None,
                    "score_4dir": float(score_4[j]) if np.isfinite(score_4[j]) else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "calib_batch": int(last_calib_batch) if last_calib_batch is not None else None,
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_up_votes": int(specialist_up_votes[j]),
                    "specialist_down_votes": int(specialist_down_votes[j]),
                }
            )

            rows_final.append(
                {
                    "alignment_mode": data.mode,
                    "weight_method": weight_method,
                    "final_rule": final_rule,
                    "pred_batch": int(batch),
                    "anchor_15m_ts": anchor_ts[j],
                    "truth_final": int(truth_b[j]),
                    "truth_final4": int(truth4[j]),
                    "truth_breakfree": int(truth_b[j]),
                    "truth_4dir": int(truth_4[j]),
                    "pred_final": int(final_pred[j]),
                    "pred_breakfree": int(pb[j]),
                    "pred_4dir": int(p4[j]),
                    "score_final": float(score_final[j]) if np.isfinite(score_final[j]) else None,
                    "tau": float(current_tau),
                    "tau_up": float(current_tau_up),
                    "tau_down": float(current_tau_down),
                    "calib_batch": int(last_calib_batch) if last_calib_batch is not None else None,
                    "selected_break_count": int(current_selected_break.size),
                    "selected_4dir_count": int(current_selected_4dir.size),
                    "specialist_up_votes": int(specialist_up_votes[j]),
                    "specialist_down_votes": int(specialist_down_votes[j]),
                }
            )

        if int(progress_every_batches) > 0:
            should_heartbeat = (
                pred_idx == 1
                or pred_idx == pred_total
                or (pred_idx % int(progress_every_batches) == 0)
            )
            if should_heartbeat:
                elapsed = float(time.perf_counter() - wf_t0)
                rate = elapsed / max(pred_idx, 1)
                eta = rate * max(pred_total - pred_idx, 0)
                _progress_event(
                    message=(
                        f"[wf/{data.mode}/{weight_method}/{final_rule}] "
                        f"batch={int(batch)} pred_idx={pred_idx}/{pred_total} "
                        f"tau={float(current_tau):.4f} tau_up={float(current_tau_up):.4f} tau_down={float(current_tau_down):.4f} "
                        f"elapsed={_format_eta(elapsed)} eta={_format_eta(eta)}"
                    ),
                    verbose=verbose,
                    progress_log_path=progress_log_path,
                    payload={
                        "event": "wf_heartbeat",
                        "alignment_mode": data.mode,
                        "weight_method": weight_method,
                        "final_rule": final_rule,
                        "pred_batch": int(batch),
                        "pred_idx": int(pred_idx),
                        "pred_total": int(pred_total),
                        "tau": float(current_tau),
                        "tau_up": float(current_tau_up),
                        "tau_down": float(current_tau_down),
                        "elapsed_s": float(elapsed),
                        "eta_s": float(eta),
                    },
                    force_print=verbose,
                )

    final_df = pl.DataFrame(rows_final)
    target_df = pl.DataFrame(rows_target)
    return target_df, final_df, calib_logs


def _metrics_from_predictions(
    df: pl.DataFrame, *, seed: int = 42
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    group_cols = ["alignment_mode", "weight_method", "final_rule"]

    method_rows: list[dict[str, Any]] = []
    conf_rows: list[dict[str, Any]] = []
    cost_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []

    for key, sub in df.group_by(group_cols, maintain_order=True):
        align, wm, fr = str(key[0]), str(key[1]), str(key[2])
        yt4 = sub["truth_final4"].to_numpy().astype(np.int16)
        yp = sub["pred_final"].to_numpy().astype(np.int16)
        yb = sub["truth_breakfree"].to_numpy().astype(np.int16)
        y4 = sub["truth_4dir"].to_numpy().astype(np.int16)

        ev = _compute_directional_hold_eval(yt4, yp)
        cost = _compute_custom_cost_truth4(yt4, yp)
        conf = _build_truth4_pred3_confusion(yt4, yp)
        hs_stats = _hold_side_metrics(yb, y4, yp)

        yt_legacy = sub["truth_final"].to_numpy().astype(np.int16)
        legacy = _compute_standard_metrics(yt_legacy, yp)

        covered_count = max(int(ev["covered_count"]), 1)
        pred_up_count = int(ev["pred_up_count"])
        pred_down_count = int(ev["pred_down_count"])
        directional_pred_count = max(int(ev["directional_pred_count"]), 1)
        directional_fp_total = int(ev["fp_up"]) + int(ev["fp_down"])
        hold_side_rate = float(hs_stats["hold_side_cross_error_rate_covered"])
        directional_fp_risk_score = float(2.0 * float(ev["opposite_fp_rate_covered"]) + hold_side_rate)

        precision_up_side = float(
            (conf[0, 0] + conf[2, 0]) / max(pred_up_count, 1)
        )
        precision_down_side = float(
            (conf[1, 1] + conf[3, 1]) / max(pred_down_count, 1)
        )
        precision_hold_safe = float(
            (conf[:, 2].sum()) / max(int(ev["pred_hold_count"]), 1)
        )

        seed_offset = sum(ord(ch) for ch in f"{align}|{wm}|{fr}")
        ci = _batch_block_bootstrap_ci(
            sub, seed=int(seed) + int(seed_offset), n_bootstrap=300
        )
        batch_local: list[float] = []
        batch_cost_local: list[float] = []
        for bkey, bdf in sub.group_by("pred_batch", maintain_order=True):
            _ = bkey
            yt_b_local = bdf["truth_final4"].to_numpy().astype(np.int16)
            yp_b_local = bdf["pred_final"].to_numpy().astype(np.int16)
            ev_b = _compute_directional_hold_eval(yt_b_local, yp_b_local)
            batch_local.append(float(ev_b["directional_active_accuracy"]))
            batch_cost_local.append(float(_compute_custom_cost_truth4(yt_b_local, yp_b_local)["mean_cost"]))
        bmf1 = np.asarray(batch_local, dtype=np.float64) if batch_local else np.asarray([], dtype=np.float64)
        bcost = (
            np.asarray(batch_cost_local, dtype=np.float64)
            if batch_cost_local
            else np.asarray([], dtype=np.float64)
        )

        method_rows.append(
            {
                "alignment_mode": align,
                "weight_method": wm,
                "final_rule": fr,
                # Primary metrics under truth domain: UP/DOWN/HOLD_UP/HOLD_DOWN.
                "macro_f1": float(ev["directional_active_accuracy"]),
                "balanced_accuracy": float(ev["directional_safe_accuracy"]),
                "directional_balanced_recall": float(ev["directional_active_accuracy"]),
                "accuracy_covered": float(ev["directional_safe_accuracy"]),
                "coverage": float(ev["coverage"]),
                "eligible_count": int(ev["eligible_count"]),
                "covered_count": int(ev["covered_count"]),
                "no_signal_rate": float(1.0 - float(ev["coverage"])),
                "precision_up": precision_up_side,
                "precision_down": precision_down_side,
                "precision_hold": precision_hold_safe,
                "recall_up": float("nan"),
                "recall_down": float("nan"),
                "recall_hold": float("nan"),
                "f1_up": float("nan"),
                "f1_down": float("nan"),
                "f1_hold": float("nan"),
                "directional_safe_accuracy": float(ev["directional_safe_accuracy"]),
                "directional_active_accuracy": float(ev["directional_active_accuracy"]),
                "directional_active_coverage": float(ev["directional_active_coverage"]),
                "legacy_macro_f1": float(legacy["macro_f1"]),
                "legacy_balanced_accuracy": float(legacy["balanced_accuracy"]),
                "legacy_directional_balanced_recall": float(legacy["directional_balanced_recall"]),
                "legacy_accuracy_covered": float(legacy["accuracy_covered"]),
                "custom_mean_cost": float(cost["mean_cost"]),
                "custom_utility": float(cost["utility"]),
                "fp_up": int(ev["fp_up"]),
                "fp_down": int(ev["fp_down"]),
                "opposite_fp_up": int(ev["opposite_fp_up"]),
                "opposite_fp_down": int(ev["opposite_fp_down"]),
                "opposite_fp_total": int(ev["opposite_fp_total"]),
                "hold_to_direction_fp": int(0),
                "directional_fp_total": int(directional_fp_total),
                "pred_up_count": int(pred_up_count),
                "pred_down_count": int(pred_down_count),
                "directional_pred_count": int(ev["directional_pred_count"]),
                "fp_up_rate_covered": float(float(ev["fp_up"]) / covered_count),
                "fp_down_rate_covered": float(float(ev["fp_down"]) / covered_count),
                "directional_fp_rate_covered": float(ev["directional_fp_rate_covered"]),
                "directional_fp_rate_directional_preds": float(
                    float(directional_fp_total) / float(directional_pred_count)
                ),
                "opposite_direction_rate": float(ev["opposite_fp_rate_covered"]),
                "opposite_fp_rate_covered": float(ev["opposite_fp_rate_covered"]),
                "opposite_fp_rate_active": float(
                    float(ev["opposite_fp_total"]) / float(directional_pred_count)
                ),
                "directional_fp_risk_score": directional_fp_risk_score,
                "hold_up_truth_count": int(hs_stats["hold_up_truth_count"]),
                "hold_down_truth_count": int(hs_stats["hold_down_truth_count"]),
                "hold_up_ok_count": int(hs_stats["hold_up_ok_count"]),
                "hold_down_ok_count": int(hs_stats["hold_down_ok_count"]),
                "hold_up_bad_down_count": int(hs_stats["hold_up_bad_down_count"]),
                "hold_down_bad_up_count": int(hs_stats["hold_down_bad_up_count"]),
                "hold_side_cross_error_count": int(hs_stats["hold_side_cross_error_count"]),
                "hold_side_cross_error_rate_covered": float(
                    hs_stats["hold_side_cross_error_rate_covered"]
                ),
                "hold_up_bad_down_rate_within_hold_up": float(
                    hs_stats["hold_up_bad_down_rate_within_hold_up"]
                ),
                "hold_down_bad_up_rate_within_hold_down": float(
                    hs_stats["hold_down_bad_up_rate_within_hold_down"]
                ),
                "hold_mismatch_rate": float(
                    cost["count_hold_mismatch"] / covered_count
                ),
                "directional_active_accuracy_ci95_low": ci["directional_active_accuracy_ci95_low"],
                "directional_active_accuracy_ci95_high": ci["directional_active_accuracy_ci95_high"],
                "custom_mean_cost_ci95_low": ci["custom_mean_cost_ci95_low"],
                "custom_mean_cost_ci95_high": ci["custom_mean_cost_ci95_high"],
                "batch_macro_f1_p10": float(np.quantile(bmf1, 0.10)) if bmf1.size else None,
                "batch_macro_f1_p50": float(np.quantile(bmf1, 0.50)) if bmf1.size else None,
                "batch_macro_f1_p90": float(np.quantile(bmf1, 0.90)) if bmf1.size else None,
                "batch_cost_p10": float(np.quantile(bcost, 0.10)) if bcost.size else None,
                "batch_cost_p50": float(np.quantile(bcost, 0.50)) if bcost.size else None,
                "batch_cost_p90": float(np.quantile(bcost, 0.90)) if bcost.size else None,
            }
        )
        for ti, t in enumerate([TRUTH_UP, TRUTH_DOWN, TRUTH_HOLD_UP, TRUTH_HOLD_DOWN]):
            for pi, p in enumerate([UP, DOWN, HOLD]):
                conf_rows.append(
                    {
                        "alignment_mode": align,
                        "weight_method": wm,
                        "final_rule": fr,
                        "truth_label": TRUTH4_LABEL_NAME[t],
                        "pred_label": LABEL_NAME[p],
                        "count": int(conf[ti, pi]),
                    }
                )

        cost_rows.append(
            {
                "alignment_mode": align,
                "weight_method": wm,
                "final_rule": fr,
                "count_correct": int(cost["count_correct"]),
                "count_opposite_direction": int(cost["count_opposite_direction"]),
                "count_hold_mismatch": int(cost["count_hold_mismatch"]),
                "count_no_signal": int(cost["count_no_signal"]),
                "mean_cost": float(cost["mean_cost"]),
                "utility": float(cost["utility"]),
                "cost_sum": float(cost["cost_sum"]),
            }
        )

        for bkey, bdf in sub.group_by("pred_batch", maintain_order=True):
            b = int(bkey[0] if isinstance(bkey, tuple) else bkey)
            yt_b = bdf["truth_final4"].to_numpy().astype(np.int16)
            yp_b = bdf["pred_final"].to_numpy().astype(np.int16)
            ev_b = _compute_directional_hold_eval(yt_b, yp_b)
            cost_b = _compute_custom_cost_truth4(yt_b, yp_b)
            batch_rows.append(
                {
                    "alignment_mode": align,
                    "weight_method": wm,
                    "final_rule": fr,
                    "pred_batch": b,
                    "macro_f1": float(ev_b["directional_active_accuracy"]),
                    "balanced_accuracy": float(ev_b["directional_safe_accuracy"]),
                    "directional_balanced_recall": float(ev_b["directional_active_accuracy"]),
                    "accuracy_covered": float(ev_b["directional_safe_accuracy"]),
                    "coverage": float(ev_b["coverage"]),
                    "directional_safe_accuracy": float(ev_b["directional_safe_accuracy"]),
                    "directional_active_accuracy": float(ev_b["directional_active_accuracy"]),
                    "directional_active_coverage": float(ev_b["directional_active_coverage"]),
                    "opposite_fp_rate_covered": float(ev_b["opposite_fp_rate_covered"]),
                    "custom_mean_cost": float(cost_b["mean_cost"]),
                    "custom_utility": float(cost_b["utility"]),
                }
            )

    method_df = pl.DataFrame(method_rows)
    if not method_df.is_empty():
        method_df = method_df.sort(
            [
                "directional_active_accuracy",
                "opposite_fp_rate_active",
                "opposite_fp_rate_covered",
                "directional_fp_rate_covered",
                "hold_side_cross_error_rate_covered",
                "macro_f1",
                "custom_mean_cost",
                "directional_active_coverage",
                "coverage",
                "alignment_mode",
                "weight_method",
                "final_rule",
            ],
            descending=[True, False, False, False, False, True, False, True, True, False, False, False],
        ).with_row_index("rank", offset=1)

        risk_rank_df = (
            method_df.sort(
                [
                    "directional_fp_risk_score",
                    "opposite_fp_rate_active",
                    "opposite_fp_rate_covered",
                    "directional_fp_rate_covered",
                    "hold_side_cross_error_rate_covered",
                    "directional_active_accuracy",
                    "custom_mean_cost",
                    "directional_active_coverage",
                    "coverage",
                    "alignment_mode",
                    "weight_method",
                    "final_rule",
                ],
                descending=[False, False, False, False, False, True, False, True, True, False, False, False],
            )
            .with_row_index("rank_risk", offset=1)
            .select(["alignment_mode", "weight_method", "final_rule", "rank_risk"])
        )
        method_df = method_df.join(
            risk_rank_df,
            on=["alignment_mode", "weight_method", "final_rule"],
            how="left",
        ).sort("rank")

    conf_df = pl.DataFrame(conf_rows)
    cost_df = pl.DataFrame(cost_rows)
    batch_df = pl.DataFrame(batch_rows)
    return method_df, conf_df, cost_df, batch_df


def _window_metrics(batch_df: pl.DataFrame, windows: list[int]) -> pl.DataFrame:
    if batch_df.is_empty():
        return pl.DataFrame()

    rows: list[dict[str, Any]] = []
    group_cols = ["alignment_mode", "weight_method", "final_rule"]
    for key, sub in batch_df.group_by(group_cols, maintain_order=True):
        align, wm, fr = str(key[0]), str(key[1]), str(key[2])
        sub = sub.sort("pred_batch")
        batches = sub["pred_batch"].to_numpy().astype(np.int64)
        mf1 = sub["macro_f1"].to_numpy().astype(np.float64)
        cov = sub["coverage"].to_numpy().astype(np.float64)
        cst = sub["custom_mean_cost"].to_numpy().astype(np.float64)

        n = len(batches)
        for w in windows:
            if n < w:
                continue
            for i in range(0, n - w + 1):
                j = i + w
                rows.append(
                    {
                        "alignment_mode": align,
                        "weight_method": wm,
                        "final_rule": fr,
                        "window_size_batches": int(w),
                        "window_start_batch": int(batches[i]),
                        "window_end_batch": int(batches[j - 1]),
                        "macro_f1_mean": float(np.mean(mf1[i:j])),
                        "coverage_mean": float(np.mean(cov[i:j])),
                        "custom_mean_cost_mean": float(np.mean(cst[i:j])),
                    }
                )

    return pl.DataFrame(rows)


def main() -> None:
    args = _parse_args()

    project_root = Path(args.project_root).expanduser().resolve()
    ensemble_run_dir = _resolve_ensemble_run_dir(project_root, str(args.ensemble_run_dir))

    alignment_modes = _parse_csv_list(
        str(args.alignment_modes),
        allowed={"same_period_close", "anchor_mean"},
    )
    weight_methods = _parse_csv_list(
        str(args.weight_methods),
        allowed=set(DEFAULT_WEIGHT_METHODS),
    )
    final_rules = _parse_csv_list(
        str(args.final_rules),
        allowed={
            "agreement_hold",
            "weighted_band",
            "breakfree_gate_weighted",
            "strict_agreement_margin",
            "dual_ova_thresholds",
            "specialist_rare_gate",
        },
    )
    tau_grid = _parse_hold_band_grid(str(args.hold_band_grid))
    ova_threshold_grid = _parse_hold_band_grid(str(args.ova_threshold_grid))
    if float(args.tau_fp_penalty) < 0.0:
        raise ValueError("--tau-fp-penalty must be >= 0")
    if float(args.tau_opposite_fp_penalty) < 0.0:
        raise ValueError("--tau-opposite-fp-penalty must be >= 0")
    if float(args.tau_hold_side_penalty) < 0.0:
        raise ValueError("--tau-hold-side-penalty must be >= 0")
    if float(args.tau_opposite_active_penalty) < 0.0:
        raise ValueError("--tau-opposite-active-penalty must be >= 0")
    if not (0.0 <= float(args.tau_min_active_coverage) <= 1.0):
        raise ValueError("--tau-min-active-coverage must be in [0, 1]")
    if not (0.0 <= float(args.rank_min_active_coverage) <= 1.0):
        raise ValueError("--rank-min-active-coverage must be in [0, 1]")
    if int(args.specialist_min_support) < 1:
        raise ValueError("--specialist-min-support must be >= 1")
    if not (0.0 <= float(args.specialist_min_safe_accuracy) <= 1.0):
        raise ValueError("--specialist-min-safe-accuracy must be in [0, 1]")
    if not (0.0 <= float(args.specialist_max_opposite_rate) <= 1.0):
        raise ValueError("--specialist-max-opposite-rate must be in [0, 1]")
    if int(args.specialist_min_votes) < 1:
        raise ValueError("--specialist-min-votes must be >= 1")
    if not (0.0 < float(args.specialist_recency_decay) <= 1.0):
        raise ValueError("--specialist-recency-decay must be in (0, 1]")
    if not (0.90 <= float(args.dma_forgetting_factor) <= 1.0):
        raise ValueError("--dma-forgetting-factor must be in [0.90, 1.0]")
    if not (0.0 <= float(args.dma_fixed_share_alpha) < 1.0):
        raise ValueError("--dma-fixed-share-alpha must be in [0, 1)")
    if not (float(args.ewaf_brier_eta) > 0.0):
        raise ValueError("--ewaf-brier-eta must be > 0")
    selection_lookback_grid = _parse_lookback_grid(str(args.selection_lookback_grid))
    selection_validation_tail_ratio = float(args.selection_validation_tail_ratio)
    if not (0.0 <= selection_validation_tail_ratio < 1.0):
        raise ValueError("--selection-validation-tail-ratio must be in [0, 1)")
    selection_min_history = int(args.selection_min_history)
    if selection_min_history < 1:
        raise ValueError("--selection-min-history must be >= 1")
    if int(args.progress_every_batches) < 0:
        raise ValueError("--progress-every-batches must be >= 0")
    if int(args.selection_progress_every_calibs) < 0:
        raise ValueError("--selection-progress-every-calibs must be >= 0")

    unit_rows_path = ensemble_run_dir / "unit_prediction_rows_dedup.parquet"
    candidate_sets_path = ensemble_run_dir / "candidate_sets_by_unit.json"
    summary_path = ensemble_run_dir / "summary.json"

    if not unit_rows_path.exists():
        raise FileNotFoundError(f"Missing input: {unit_rows_path}")
    if not candidate_sets_path.exists():
        raise FileNotFoundError(f"Missing input: {candidate_sets_path}")

    unit_rows = pl.read_parquet(unit_rows_path)
    candidate_sets = _load_candidate_sets(candidate_sets_path)
    run_summary = (
        json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    )

    now = datetime.now(timezone.utc)
    out_name = now.strftime("%Y%m%d_%H%M%S") + (f"_{args.output_tag}" if args.output_tag else "")
    out_dir = (project_root / args.output_dir / out_name).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    if args.verbose:
        print("Cross-target multi-timeframe ensemble search")
        print(f"  ensemble_run_dir: {ensemble_run_dir}")
        print(f"  output_dir: {out_dir}")
        print(f"  alignments: {alignment_modes}")
        print(f"  weight_methods: {weight_methods}")
        print(f"  final_rules: {final_rules}")
        print(f"  tau_objective: {args.tau_objective}")
        print(f"  tau_fp_penalty: {float(args.tau_fp_penalty):.4f}")
        print(f"  tau_opposite_fp_penalty: {float(args.tau_opposite_fp_penalty):.4f}")
        print(f"  tau_hold_side_penalty: {float(args.tau_hold_side_penalty):.4f}")
        print(f"  tau_opposite_active_penalty: {float(args.tau_opposite_active_penalty):.4f}")
        print(f"  tau_min_active_coverage: {float(args.tau_min_active_coverage):.4f}")
        print(f"  rank_min_active_coverage: {float(args.rank_min_active_coverage):.4f}")
        print(f"  ova_threshold_grid: {str(args.ova_threshold_grid)}")
        print(f"  specialist_min_support: {int(args.specialist_min_support)}")
        print(f"  specialist_min_safe_accuracy: {float(args.specialist_min_safe_accuracy):.4f}")
        print(f"  specialist_max_opposite_rate: {float(args.specialist_max_opposite_rate):.4f}")
        print(f"  specialist_min_votes: {int(args.specialist_min_votes)}")
        print(f"  specialist_recency_decay: {float(args.specialist_recency_decay):.4f}")
        print(f"  dma_forgetting_factor: {float(args.dma_forgetting_factor):.4f}")
        print(f"  dma_fixed_share_alpha: {float(args.dma_fixed_share_alpha):.4f}")
        print(f"  ewaf_brier_eta: {float(args.ewaf_brier_eta):.4f}")
        print(f"  selection_lookback_grid: {selection_lookback_grid}")
        print(f"  selection_validation_tail_ratio: {selection_validation_tail_ratio:.4f}")
        print(f"  selection_min_history: {selection_min_history}")
        print(f"  progress_every_batches: {int(args.progress_every_batches)}")
        print(f"  selection_progress_every_calibs: {int(args.selection_progress_every_calibs)}")
        print(f"  progress_log_file: {str(args.progress_log_file)}")

    # Build candidate metadata table
    meta_rows: list[dict[str, Any]] = []
    for unit, meta in candidate_sets.items():
        tf, target = unit.split("/", 1)
        wins = meta.get("winner_wins", {})
        for action_key in meta["action_keys"]:
            cid = f"{unit}::{action_key}"
            meta_rows.append(
                {
                    "candidate_id": cid,
                    "unit": unit,
                    "timeframe": tf,
                    "target": target,
                    "action_key": action_key,
                    "winner_wins": int(wins.get(action_key, 0)),
                }
            )
    candidate_meta = pl.DataFrame(meta_rows).sort(["unit", "action_key"])

    # Keep only candidate universe rows
    candidate_set = set(candidate_meta["candidate_id"].to_list())
    unit_rows = unit_rows.with_columns(
        pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
    ).filter(pl.col("candidate_id").is_in(list(candidate_set)))

    # Truth table and alignment-level source tables
    anchor_truth = _prepare_truth_table(unit_rows)

    aligned_frames: list[pl.DataFrame] = []
    row_diag_rows: list[dict[str, Any]] = []
    for mode in alignment_modes:
        mode_df = _build_anchor_candidate_probs(unit_rows, mode)
        mode_df = mode_df.join(
            anchor_truth.select(["pred_batch", "anchor_15m_ts"]),
            on=["pred_batch", "anchor_15m_ts"],
            how="inner",
        )
        mode_df = mode_df.with_columns(
            pl.concat_str([pl.col("unit"), pl.lit("::"), pl.col("action_key")]).alias("candidate_id")
        ).filter(pl.col("candidate_id").is_in(list(candidate_set)))

        aligned_frames.append(mode_df)

        diag = (
            mode_df.group_by(["unit", "timeframe"])
            .agg(
                [
                    pl.len().alias("rows"),
                    pl.col("row_count").min().alias("row_count_min"),
                    pl.col("row_count").median().alias("row_count_median"),
                    pl.col("row_count").max().alias("row_count_max"),
                    pl.col("row_count_match").mean().alias("row_count_match_rate"),
                ]
            )
            .with_columns(pl.lit(mode).alias("alignment_mode"))
        )
        row_diag_rows.extend(diag.to_dicts())

    anchor_aligned_df = pl.concat(aligned_frames, how="diagonal_relaxed").sort(
        ["alignment_mode", "pred_batch", "anchor_15m_ts", "unit", "action_key"]
    )

    # Build per-alignment matrix representation
    alignment_data: dict[str, AlignmentData] = {}
    selection_by_alignment: dict[str, dict[str, Any]] = {}
    selection_schedule_by_alignment: dict[str, dict[int, tuple[np.ndarray, np.ndarray]]] = {}
    pruning_logs_all: list[dict[str, Any]] = []
    progress_log_path: Path | None = None
    progress_log_name = str(args.progress_log_file).strip()
    if progress_log_name:
        progress_log_path = out_dir / progress_log_name
        if progress_log_path.exists():
            progress_log_path.unlink()
    _progress_event(
        message="run_start cross-target ensemble search",
        verbose=bool(args.verbose),
        progress_log_path=progress_log_path,
        payload={
            "event": "run_start",
            "ensemble_run_dir": str(ensemble_run_dir),
            "output_dir": str(out_dir),
            "alignment_modes": alignment_modes,
            "weight_methods": weight_methods,
            "final_rules": final_rules,
        },
        force_print=bool(args.verbose),
    )

    # Warmup boundary by batch index
    batch_order_global = (
        anchor_truth["pred_batch"].unique(maintain_order=True).to_list()
    )
    if args.wf_warmup_batches >= len(batch_order_global):
        raise ValueError(
            f"wf_warmup_batches={args.wf_warmup_batches} must be < total batches={len(batch_order_global)}"
        )

    for mode in alignment_modes:
        mode_t0 = time.perf_counter()
        data_mode = _build_alignment_data(
            aligned_df=anchor_aligned_df,
            candidate_meta=candidate_meta,
            anchor_truth=anchor_truth,
            mode=mode,
        )
        alignment_data[mode] = data_mode

        schedule: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        schedule_meta: list[dict[str, Any]] = []
        lookback_trials_meta: list[dict[str, Any]] = []
        selection_points = [
            int(b)
            for ii, b in enumerate(data_mode.batch_order)
            if ii >= int(args.wf_warmup_batches)
            and (
                ii == int(args.wf_warmup_batches)
                or ((ii - int(args.wf_warmup_batches)) % int(args.wf_recalibrate_every) == 0)
            )
        ]
        selection_total = int(len(selection_points))
        selection_done = 0
        selection_t0 = time.perf_counter()
        _progress_event(
            message=(
                f"[selection/{mode}] start "
                f"batch_total={len(data_mode.batch_order)} "
                f"selection_points={selection_total}"
            ),
            verbose=bool(args.verbose),
            progress_log_path=progress_log_path,
            payload={
                "event": "selection_start",
                "alignment_mode": mode,
                "batch_total": int(len(data_mode.batch_order)),
                "selection_points": int(selection_total),
            },
            force_print=bool(args.verbose),
        )
        for i, batch in enumerate(data_mode.batch_order):
            if i < int(args.wf_warmup_batches):
                continue
            if i == int(args.wf_warmup_batches) or (
                ((i - int(args.wf_warmup_batches)) % int(args.wf_recalibrate_every)) == 0
            ):
                selection_done += 1
                history_end = data_mode.batch_ranges[int(batch)][0]
                if int(args.selection_progress_every_calibs) > 0:
                    if (
                        selection_done == 1
                        or selection_done == selection_total
                        or (selection_done % int(args.selection_progress_every_calibs) == 0)
                    ):
                        elapsed_sel = float(time.perf_counter() - selection_t0)
                        rate_sel = elapsed_sel / max(selection_done, 1)
                        eta_sel = rate_sel * max(selection_total - selection_done, 0)
                        _progress_event(
                            message=(
                                f"[selection/{mode}] calib={selection_done}/{selection_total} "
                                f"batch={int(batch)} history_end={int(history_end)} "
                                f"elapsed={_format_eta(elapsed_sel)} eta={_format_eta(eta_sel)}"
                            ),
                            verbose=bool(args.verbose),
                            progress_log_path=progress_log_path,
                            payload={
                                "event": "selection_heartbeat",
                                "alignment_mode": mode,
                                "selection_done": int(selection_done),
                                "selection_total": int(selection_total),
                                "pred_batch": int(batch),
                                "history_end_anchor": int(history_end),
                                "elapsed_s": float(elapsed_sel),
                                "eta_s": float(eta_sel),
                            },
                            force_print=bool(args.verbose),
                        )
                best_selection: dict[str, Any] | None = None

                for requested_lookback in selection_lookback_grid:
                    effective_lookback = (
                        int(history_end) if requested_lookback < 0 else min(int(requested_lookback), int(history_end))
                    )
                    if effective_lookback < selection_min_history:
                        lookback_trials_meta.append(
                            {
                                "alignment_mode": mode,
                                "calib_batch": int(batch),
                                "history_end_anchor": int(history_end),
                                "lookback_requested": int(requested_lookback),
                                "lookback_effective": int(effective_lookback),
                                "status": "skipped_too_short",
                            }
                        )
                        continue

                    history_start = int(history_end - effective_lookback)
                    train_start = int(history_start)
                    train_end = int(history_end)
                    eval_start = int(history_start)
                    eval_end = int(history_end)
                    score_basis = "train"

                    if selection_validation_tail_ratio > 0.0:
                        val_len = max(1, int(round(effective_lookback * selection_validation_tail_ratio)))
                        val_len = min(val_len, effective_lookback - 1)
                        candidate_train_end = int(history_end - val_len)
                        if (candidate_train_end - history_start) < selection_min_history:
                            lookback_trials_meta.append(
                                {
                                    "alignment_mode": mode,
                                    "calib_batch": int(batch),
                                    "history_end_anchor": int(history_end),
                                    "lookback_requested": int(requested_lookback),
                                    "lookback_effective": int(effective_lookback),
                                    "status": "skipped_train_tail_too_short",
                                    "train_anchors": int(candidate_train_end - history_start),
                                    "validation_anchors": int(val_len),
                                }
                            )
                            continue
                        train_start = int(history_start)
                        train_end = int(candidate_train_end)
                        eval_start = int(candidate_train_end)
                        eval_end = int(history_end)
                        score_basis = "validation"

                    sb, s4, logs = _hybrid_staged_selection(
                        data=data_mode,
                        history_start=train_start,
                        history_end=train_end,
                        min_per_unit=int(args.min_candidates_per_unit),
                        max_prune_iterations=int(args.max_prune_iterations),
                        verbose=bool(args.verbose),
                    )
                    score_train = _objective_final(
                        data=data_mode,
                        history_start=train_start,
                        history_end=train_end,
                        selected_break=sb,
                        selected_4dir=s4,
                    )
                    score_eval = _objective_final(
                        data=data_mode,
                        history_start=eval_start,
                        history_end=eval_end,
                        selected_break=sb,
                        selected_4dir=s4,
                    )
                    tie_break = (
                        float(score_eval if score_basis == "validation" else score_train),
                        float(-effective_lookback),
                        float(-1 if requested_lookback < 0 else 0),
                    )
                    lookback_trials_meta.append(
                        {
                            "alignment_mode": mode,
                            "calib_batch": int(batch),
                            "history_end_anchor": int(history_end),
                            "lookback_requested": int(requested_lookback),
                            "lookback_effective": int(effective_lookback),
                            "history_start_anchor": int(history_start),
                            "train_start_anchor": int(train_start),
                            "train_end_anchor": int(train_end),
                            "eval_start_anchor": int(eval_start),
                            "eval_end_anchor": int(eval_end),
                            "score_basis": score_basis,
                            "score_train": float(score_train),
                            "score_eval": float(score_eval),
                            "selected_break_count": int(sb.size),
                            "selected_4class_count": int(s4.size),
                            "status": "ok",
                        }
                    )

                    if (best_selection is None) or (tie_break > best_selection["tie_break"]):
                        best_selection = {
                            "requested": int(requested_lookback),
                            "effective": int(effective_lookback),
                            "history_start": int(history_start),
                            "train_start": int(train_start),
                            "train_end": int(train_end),
                            "eval_start": int(eval_start),
                            "eval_end": int(eval_end),
                            "score_basis": str(score_basis),
                            "score_train": float(score_train),
                            "score_eval": float(score_eval),
                            "selected_break": sb,
                            "selected_4class": s4,
                            "logs": logs,
                            "tie_break": tie_break,
                        }

                if best_selection is None:
                    fallback_start = max(0, int(history_end - max(int(selection_min_history), 1)))
                    sb, s4, logs = _hybrid_staged_selection(
                        data=data_mode,
                        history_start=fallback_start,
                        history_end=int(history_end),
                        min_per_unit=int(args.min_candidates_per_unit),
                        max_prune_iterations=int(args.max_prune_iterations),
                        verbose=bool(args.verbose),
                    )
                    score_train = _objective_final(
                        data=data_mode,
                        history_start=fallback_start,
                        history_end=int(history_end),
                        selected_break=sb,
                        selected_4dir=s4,
                    )
                    best_selection = {
                        "requested": -1,
                        "effective": int(history_end - fallback_start),
                        "history_start": int(fallback_start),
                        "train_start": int(fallback_start),
                        "train_end": int(history_end),
                        "eval_start": int(fallback_start),
                        "eval_end": int(history_end),
                        "score_basis": "fallback_train",
                        "score_train": float(score_train),
                        "score_eval": float(score_train),
                        "selected_break": sb,
                        "selected_4class": s4,
                        "logs": logs,
                        "tie_break": (float(score_train), float(-(history_end - fallback_start)), 1.0),
                    }
                    lookback_trials_meta.append(
                        {
                            "alignment_mode": mode,
                            "calib_batch": int(batch),
                            "history_end_anchor": int(history_end),
                            "lookback_requested": -1,
                            "lookback_effective": int(history_end - fallback_start),
                            "history_start_anchor": int(fallback_start),
                            "train_start_anchor": int(fallback_start),
                            "train_end_anchor": int(history_end),
                            "eval_start_anchor": int(fallback_start),
                            "eval_end_anchor": int(history_end),
                            "score_basis": "fallback_train",
                            "score_train": float(score_train),
                            "score_eval": float(score_train),
                            "selected_break_count": int(sb.size),
                            "selected_4class_count": int(s4.size),
                            "status": "fallback",
                        }
                    )

                sb_best = best_selection["selected_break"]
                s4_best = best_selection["selected_4class"]
                schedule[int(batch)] = (sb_best, s4_best)
                schedule_meta.append(
                    {
                        "calib_batch": int(batch),
                        "history_end_anchor": int(history_end),
                        "lookback_requested": int(best_selection["requested"]),
                        "lookback_effective": int(best_selection["effective"]),
                        "history_start_anchor": int(best_selection["history_start"]),
                        "train_start_anchor": int(best_selection["train_start"]),
                        "train_end_anchor": int(best_selection["train_end"]),
                        "eval_start_anchor": int(best_selection["eval_start"]),
                        "eval_end_anchor": int(best_selection["eval_end"]),
                        "score_basis": str(best_selection["score_basis"]),
                        "score_train": float(best_selection["score_train"]),
                        "score_eval": float(best_selection["score_eval"]),
                        "selected_breakfree": [data_mode.candidate_ids[int(v)] for v in sb_best.tolist()],
                        "selected_4class": [data_mode.candidate_ids[int(v)] for v in s4_best.tolist()],
                    }
                )
                for row in best_selection["logs"]:
                    row["alignment_mode"] = mode
                    row["history_start_anchor"] = int(best_selection["train_start"])
                    row["history_end_anchor"] = int(best_selection["train_end"])
                    row["selection_eval_start_anchor"] = int(best_selection["eval_start"])
                    row["selection_eval_end_anchor"] = int(best_selection["eval_end"])
                    row["lookback_requested"] = int(best_selection["requested"])
                    row["lookback_effective"] = int(best_selection["effective"])
                    row["selection_score_basis"] = str(best_selection["score_basis"])
                    row["selection_score_train"] = float(best_selection["score_train"])
                    row["selection_score_eval"] = float(best_selection["score_eval"])
                    row["warmup_boundary_batch"] = int(data_mode.batch_order[int(args.wf_warmup_batches)])
                    row["selection_calib_batch"] = int(batch)
                    pruning_logs_all.append(row)

                _progress_event(
                    message=(
                        f"[selection/{mode}] calib_done batch={int(batch)} "
                        f"lookback={int(best_selection['effective'])} "
                        f"score_eval={float(best_selection['score_eval']):.4f} "
                        f"break={int(sb_best.size)} dir4={int(s4_best.size)}"
                    ),
                    verbose=bool(args.verbose),
                    progress_log_path=progress_log_path,
                    payload={
                        "event": "selection_calib_done",
                        "alignment_mode": mode,
                        "pred_batch": int(batch),
                        "lookback_requested": int(best_selection["requested"]),
                        "lookback_effective": int(best_selection["effective"]),
                        "score_basis": str(best_selection["score_basis"]),
                        "score_train": float(best_selection["score_train"]),
                        "score_eval": float(best_selection["score_eval"]),
                        "selected_break_count": int(sb_best.size),
                        "selected_4class_count": int(s4_best.size),
                    },
                    force_print=bool(args.verbose),
                )

        if not schedule:
            raise RuntimeError(f"No selection schedule generated for alignment {mode}")

        selection_schedule_by_alignment[mode] = schedule
        selection_by_alignment[mode] = {
            "warmup_boundary_batch": int(data_mode.batch_order[int(args.wf_warmup_batches)]),
            "schedule": schedule_meta,
            "lookback_trials": lookback_trials_meta,
        }
        _progress_event(
            message=(
                f"[selection/{mode}] done "
                f"calibrations={selection_total} "
                f"runtime={_format_eta(float(time.perf_counter() - mode_t0))}"
            ),
            verbose=bool(args.verbose),
            progress_log_path=progress_log_path,
            payload={
                "event": "selection_done",
                "alignment_mode": mode,
                "calibrations": int(selection_total),
                "runtime_s": float(time.perf_counter() - mode_t0),
            },
            force_print=bool(args.verbose),
        )

    # Walk-forward evaluation for all method/rule combos
    target_pred_frames: list[pl.DataFrame] = []
    final_pred_frames: list[pl.DataFrame] = []
    calib_rows_all: list[dict[str, Any]] = []
    combo_total = int(len(alignment_modes) * len(weight_methods) * len(final_rules))
    combo_done = 0
    combo_t0 = time.perf_counter()

    for mode in alignment_modes:
        d = alignment_data[mode]
        schedule = selection_schedule_by_alignment[mode]

        for wm in weight_methods:
            for fr in final_rules:
                combo_done += 1
                combo_one_t0 = time.perf_counter()
                elapsed_combo = float(time.perf_counter() - combo_t0)
                rate_combo = elapsed_combo / max(combo_done - 1, 1) if combo_done > 1 else 0.0
                eta_combo = rate_combo * max(combo_total - combo_done, 0)
                _progress_event(
                    message=(
                        f"[wf] combo_start {combo_done}/{combo_total} "
                        f"alignment={mode} weight={wm} rule={fr} "
                        f"eta={_format_eta(eta_combo)}"
                    ),
                    verbose=bool(args.verbose),
                    progress_log_path=progress_log_path,
                    payload={
                        "event": "combo_start",
                        "combo_done": int(combo_done),
                        "combo_total": int(combo_total),
                        "alignment_mode": mode,
                        "weight_method": wm,
                        "final_rule": fr,
                        "elapsed_s": float(elapsed_combo),
                        "eta_s": float(eta_combo),
                    },
                    force_print=bool(args.verbose),
                )
                tdf, fdf, calib = _run_walkforward_combo(
                    data=d,
                    selection_schedule=schedule,
                    weight_method=wm,
                    final_rule=fr,
                    tau_grid=tau_grid,
                    ova_threshold_grid=ova_threshold_grid,
                    tau_objective=str(args.tau_objective),
                    tau_fp_penalty=float(args.tau_fp_penalty),
                    tau_opposite_fp_penalty=float(args.tau_opposite_fp_penalty),
                    tau_hold_side_penalty=float(args.tau_hold_side_penalty),
                    tau_opposite_active_penalty=float(args.tau_opposite_active_penalty),
                    tau_min_active_coverage=float(args.tau_min_active_coverage),
                    specialist_min_support=int(args.specialist_min_support),
                    specialist_min_safe_accuracy=float(args.specialist_min_safe_accuracy),
                    specialist_max_opposite_rate=float(args.specialist_max_opposite_rate),
                    specialist_min_votes=int(args.specialist_min_votes),
                    specialist_recency_decay=float(args.specialist_recency_decay),
                    kalman_process_noise=float(args.kalman_process_noise),
                    kalman_measurement_noise=float(args.kalman_measurement_noise),
                    dma_forgetting_factor=float(args.dma_forgetting_factor),
                    dma_fixed_share_alpha=float(args.dma_fixed_share_alpha),
                    ewaf_brier_eta=float(args.ewaf_brier_eta),
                    warmup_batches=int(args.wf_warmup_batches),
                    recalibrate_every=int(args.wf_recalibrate_every),
                    progress_every_batches=int(args.progress_every_batches),
                    verbose=bool(args.verbose),
                    progress_log_path=progress_log_path,
                )
                target_pred_frames.append(tdf)
                final_pred_frames.append(fdf)
                calib_rows_all.extend(calib)
                _progress_event(
                    message=(
                        f"[wf] combo_done {combo_done}/{combo_total} "
                        f"alignment={mode} weight={wm} rule={fr} "
                        f"rows={int(len(fdf))} runtime={_format_eta(float(time.perf_counter() - combo_one_t0))}"
                    ),
                    verbose=bool(args.verbose),
                    progress_log_path=progress_log_path,
                    payload={
                        "event": "combo_done",
                        "combo_done": int(combo_done),
                        "combo_total": int(combo_total),
                        "alignment_mode": mode,
                        "weight_method": wm,
                        "final_rule": fr,
                        "final_rows": int(len(fdf)),
                        "runtime_s": float(time.perf_counter() - combo_one_t0),
                    },
                    force_print=bool(args.verbose),
                )

    target_pred_df = pl.concat(target_pred_frames, how="diagonal_relaxed")
    final_pred_df = pl.concat(final_pred_frames, how="diagonal_relaxed")

    # Leakage checks (history-only):
    # 1) Calibration history max batch must be strictly earlier than the calibration batch.
    # 2) Calibration batch used for inference must not be in the future of predicted batch.
    leakage_guard_passed = True
    if calib_rows_all:
        calib_guard_df = pl.DataFrame(calib_rows_all)
        if {"history_max_batch", "calib_batch"} <= set(calib_guard_df.columns):
            bad_hist = calib_guard_df.filter(
                pl.col("history_max_batch").is_not_null()
                & (pl.col("history_max_batch") >= pl.col("calib_batch"))
            )
            leakage_guard_passed = leakage_guard_passed and bad_hist.is_empty()
    if not final_pred_df.is_empty() and "calib_batch" in final_pred_df.columns:
        bad_future = final_pred_df.filter(
            pl.col("calib_batch").is_not_null() & (pl.col("calib_batch") > pl.col("pred_batch"))
        )
        leakage_guard_passed = leakage_guard_passed and bad_future.is_empty()

    method_df, conf_df, cost_df, batch_df = _metrics_from_predictions(
        final_pred_df, seed=int(args.seed)
    )
    window_df = _window_metrics(batch_df, windows=[12, 24])

    # best setup
    if method_df.is_empty():
        raise RuntimeError("No method rows produced")
    ranking_pool = method_df.filter(
        pl.col("directional_active_coverage") >= float(args.rank_min_active_coverage)
    )
    if ranking_pool.is_empty():
        ranking_pool = method_df

    best_row = ranking_pool.sort(
        [
            "directional_active_accuracy",
            "opposite_fp_rate_active",
            "opposite_fp_rate_covered",
            "directional_fp_rate_covered",
            "hold_side_cross_error_rate_covered",
            "custom_mean_cost",
            "directional_active_coverage",
            "coverage",
        ],
        descending=[True, False, False, False, False, False, True, True],
    ).row(0, named=True)
    best_row_risk = ranking_pool.sort(
        [
            "directional_fp_risk_score",
            "opposite_fp_rate_active",
            "opposite_fp_rate_covered",
            "directional_fp_rate_covered",
            "hold_side_cross_error_rate_covered",
            "directional_active_accuracy",
            "custom_mean_cost",
            "directional_active_coverage",
            "coverage",
        ],
        descending=[False, False, False, False, False, True, False, True, True],
    ).row(0, named=True)
    best_alignment = str(best_row["alignment_mode"])
    best_setup = {
        "alignment_mode": best_alignment,
        "weight_method": str(best_row["weight_method"]),
        "final_rule": str(best_row["final_rule"]),
        "selection": selection_by_alignment[best_alignment],
    }
    best_alignment_risk = str(best_row_risk["alignment_mode"])
    best_setup_risk = {
        "alignment_mode": best_alignment_risk,
        "weight_method": str(best_row_risk["weight_method"]),
        "final_rule": str(best_row_risk["final_rule"]),
        "selection": selection_by_alignment[best_alignment_risk],
    }

    # Save artifacts
    path_anchor = out_dir / "anchor_aligned_candidate_probs.parquet"
    path_target = out_dir / "target_ensemble_predictions_walkforward.parquet"
    path_final = out_dir / "final_ensemble_predictions_walkforward.parquet"
    path_method = out_dir / "method_comparison_table.parquet"
    path_method_csv = out_dir / "method_comparison_table.csv"
    path_plog = out_dir / "pruning_log.parquet"
    path_plog_csv = out_dir / "pruning_log.csv"
    path_conf = out_dir / "final_confusion_standard.parquet"
    path_cost = out_dir / "final_confusion_custom_cost.parquet"
    path_batch = out_dir / "evaluation_by_batch.parquet"
    path_batch_csv = out_dir / "evaluation_by_batch.csv"
    path_window = out_dir / "evaluation_by_window.parquet"
    path_window_csv = out_dir / "evaluation_by_window.csv"
    path_calib = out_dir / "calibration_provenance.parquet"
    path_calib_csv = out_dir / "calibration_provenance.csv"
    path_best = out_dir / "best_setup_candidates.json"
    path_cfg = out_dir / "resolved_config.json"
    path_summary = out_dir / "summary.json"

    anchor_aligned_df.write_parquet(path_anchor)
    target_pred_df.write_parquet(path_target)
    final_pred_df.write_parquet(path_final)
    method_df.write_parquet(path_method)
    method_df.write_csv(path_method_csv)

    plog_df = pl.DataFrame(pruning_logs_all)
    if not plog_df.is_empty():
        plog_df.write_parquet(path_plog)
        plog_df.write_csv(path_plog_csv)
    else:
        pl.DataFrame([]).write_parquet(path_plog)
        pl.DataFrame([]).write_csv(path_plog_csv)

    conf_df.write_parquet(path_conf)
    cost_df.write_parquet(path_cost)
    batch_df.write_parquet(path_batch)
    batch_df.write_csv(path_batch_csv)
    window_df.write_parquet(path_window)
    window_df.write_csv(path_window_csv)
    calib_df = pl.DataFrame(calib_rows_all).sort(
        ["alignment_mode", "weight_method", "final_rule", "calib_batch"]
    )
    calib_df.write_parquet(path_calib)
    calib_df.write_csv(path_calib_csv)

    _write_json(path_best, best_setup)

    resolved_cfg = {
        "project_root": str(project_root),
        "input_ensemble_run_dir": str(ensemble_run_dir),
        "args": {
            "alignment_modes": alignment_modes,
            "weight_methods": weight_methods,
            "final_rules": final_rules,
            "hold_band_grid": str(args.hold_band_grid),
            "ova_threshold_grid": str(args.ova_threshold_grid),
            "wf_warmup_batches": int(args.wf_warmup_batches),
            "wf_recalibrate_every": int(args.wf_recalibrate_every),
            "candidate_pool_mode": str(args.candidate_pool_mode),
            "min_candidates_per_unit": int(args.min_candidates_per_unit),
            "max_prune_iterations": int(args.max_prune_iterations),
            "selection_lookback_grid": selection_lookback_grid,
            "selection_validation_tail_ratio": float(selection_validation_tail_ratio),
            "selection_min_history": int(selection_min_history),
            "tau_objective": str(args.tau_objective),
            "tau_fp_penalty": float(args.tau_fp_penalty),
            "tau_opposite_fp_penalty": float(args.tau_opposite_fp_penalty),
            "tau_hold_side_penalty": float(args.tau_hold_side_penalty),
            "tau_opposite_active_penalty": float(args.tau_opposite_active_penalty),
            "tau_min_active_coverage": float(args.tau_min_active_coverage),
            "rank_min_active_coverage": float(args.rank_min_active_coverage),
            "specialist_min_support": int(args.specialist_min_support),
            "specialist_min_safe_accuracy": float(args.specialist_min_safe_accuracy),
            "specialist_max_opposite_rate": float(args.specialist_max_opposite_rate),
            "specialist_min_votes": int(args.specialist_min_votes),
            "specialist_recency_decay": float(args.specialist_recency_decay),
            "kalman_process_noise": float(args.kalman_process_noise),
            "kalman_measurement_noise": float(args.kalman_measurement_noise),
            "dma_forgetting_factor": float(args.dma_forgetting_factor),
            "dma_fixed_share_alpha": float(args.dma_fixed_share_alpha),
            "ewaf_brier_eta": float(args.ewaf_brier_eta),
        },
    }
    _write_json(path_cfg, resolved_cfg)

    summary = {
        "run_timestamp_utc": now.isoformat(),
        "input": {
            "ensemble_run_dir": str(ensemble_run_dir),
            "unit_prediction_rows_path": str(unit_rows_path),
            "candidate_sets_path": str(candidate_sets_path),
        },
        "counts": {
            "unit_prediction_rows": int(unit_rows.height),
            "anchor_truth_rows": int(anchor_truth.height),
            "anchor_aligned_candidate_rows": int(anchor_aligned_df.height),
            "target_prediction_rows": int(target_pred_df.height),
            "final_prediction_rows": int(final_pred_df.height),
            "method_rows": int(method_df.height),
            "method_rows_after_rank_coverage_filter": int(ranking_pool.height),
            "pruning_log_rows": int(plog_df.height),
            "batch_metric_rows": int(batch_df.height),
            "window_metric_rows": int(window_df.height),
            "calibration_rows": int(len(calib_rows_all)),
        },
        "row_count_diagnostics": row_diag_rows,
        "selection_by_alignment": selection_by_alignment,
        "leakage_checks": {
            "wf_calibration_uses_history_only": bool(leakage_guard_passed),
        },
        "best_setup": best_setup,
        "best_metrics": best_row,
        "best_setup_risk_guard": best_setup_risk,
        "best_metrics_risk_guard": best_row_risk,
        "artifacts": {
            "resolved_config_json": str(path_cfg),
            "anchor_aligned_candidate_probs_parquet": str(path_anchor),
            "target_ensemble_predictions_walkforward_parquet": str(path_target),
            "final_ensemble_predictions_walkforward_parquet": str(path_final),
            "method_comparison_table_parquet": str(path_method),
            "method_comparison_table_csv": str(path_method_csv),
            "pruning_log_parquet": str(path_plog),
            "pruning_log_csv": str(path_plog_csv),
            "final_confusion_standard_parquet": str(path_conf),
            "final_confusion_custom_cost_parquet": str(path_cost),
            "evaluation_by_batch_parquet": str(path_batch),
            "evaluation_by_batch_csv": str(path_batch_csv),
            "evaluation_by_window_parquet": str(path_window),
            "evaluation_by_window_csv": str(path_window_csv),
            "calibration_provenance_parquet": str(path_calib),
            "calibration_provenance_csv": str(path_calib_csv),
            "live_progress_log": str(progress_log_path) if progress_log_path is not None else None,
            "best_setup_candidates_json": str(path_best),
            "summary_json": str(path_summary),
        },
        "source_summary_snapshot": run_summary,
    }
    _write_json(path_summary, summary)

    print("Completed cross-target ensemble search.")
    print(f"  Input run: {ensemble_run_dir}")
    print(f"  Output: {out_dir}")
    print(
        "  Best:",
        f"alignment={best_row['alignment_mode']}",
        f"weight={best_row['weight_method']}",
        f"rule={best_row['final_rule']}",
        f"macro_f1={best_row['macro_f1']:.4f}",
        f"cost={best_row['custom_mean_cost']:.4f}",
        f"coverage={best_row['coverage']:.4f}",
    )
    print(
        "  Best risk-guard:",
        f"alignment={best_row_risk['alignment_mode']}",
        f"weight={best_row_risk['weight_method']}",
        f"rule={best_row_risk['final_rule']}",
        f"fp_risk={best_row_risk['directional_fp_risk_score']:.4f}",
        f"opp_fp_rate={best_row_risk['opposite_fp_rate_covered']:.4f}",
        f"hold_side_err={best_row_risk['hold_side_cross_error_rate_covered']:.4f}",
        f"macro_f1={best_row_risk['macro_f1']:.4f}",
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Select UP and DOWN specialist configs separately from cross-target WF outputs.

This is analysis-only. It reads one existing cross-target run directory and:
1) Ranks every (weight_method, final_rule) config for UP specialist quality.
2) Ranks every (weight_method, final_rule) config for DOWN specialist quality.
3) Selects best UP config and best DOWN config under user constraints.
4) Builds a dual-specialist final stream:
   - UP if UP-specialist signals and DOWN-specialist does not
   - DOWN if DOWN-specialist signals and UP-specialist does not
   - HOLD otherwise
5) Writes artifacts and summary metrics for production comparison.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_INPUT_ROOT = "prediction_analysis/multitimeframe_cross_target_outputs"
DEFAULT_OUTPUT_ROOT = "prediction_analysis/multitimeframe_cross_target_specialist_outputs"

UP = 0
DOWN = 1
HOLD = 2

TRUTH_UP = 0
TRUTH_DOWN = 1
TRUTH_HOLD_UP = 2
TRUTH_HOLD_DOWN = 3


@dataclass(frozen=True)
class DirectionSpec:
    name: str
    signal_label: int
    truth_same_direction: int
    truth_hold_same: int
    truth_opposite: int
    truth_hold_opposite: int


UP_SPEC = DirectionSpec(
    name="up",
    signal_label=UP,
    truth_same_direction=TRUTH_UP,
    truth_hold_same=TRUTH_HOLD_UP,
    truth_opposite=TRUTH_DOWN,
    truth_hold_opposite=TRUTH_HOLD_DOWN,
)
DOWN_SPEC = DirectionSpec(
    name="down",
    signal_label=DOWN,
    truth_same_direction=TRUTH_DOWN,
    truth_hold_same=TRUTH_HOLD_DOWN,
    truth_opposite=TRUTH_UP,
    truth_hold_opposite=TRUTH_HOLD_UP,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="UP/DOWN specialist config selection from cross-target walk-forward outputs."
    )
    p.add_argument("--project-root", type=str, default=str(DEFAULT_PROJECT_ROOT))
    p.add_argument(
        "--cross-target-run-dir",
        type=str,
        default="",
        help="Path to one multitimeframe_cross_target_outputs run dir. Default: latest.",
    )
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--output-tag", type=str, default="")
    p.add_argument(
        "--alignment-mode",
        type=str,
        default="same_period_close",
        choices=["same_period_close", "anchor_mean"],
    )
    p.add_argument("--min-signal-rate-up", type=float, default=0.10)
    p.add_argument("--min-signal-rate-down", type=float, default=0.10)
    p.add_argument("--min-safe-precision-up", type=float, default=0.50)
    p.add_argument("--min-safe-precision-down", type=float, default=0.50)
    p.add_argument(
        "--objective-opposite-penalty",
        type=float,
        default=2.0,
        help="Penalty on opposite-direction rate among specialist signals.",
    )
    p.add_argument(
        "--objective-hold-side-penalty",
        type=float,
        default=1.0,
        help="Penalty on hold-side cross error rate among specialist signals.",
    )
    p.add_argument(
        "--objective-signal-rate-weight",
        type=float,
        default=0.20,
        help="Reward on signal rate to avoid trivial ultra-rare selectors.",
    )
    p.add_argument(
        "--max-up-specialists",
        type=int,
        default=4,
        help="Max UP specialists to combine in the final dual-specialist search.",
    )
    p.add_argument(
        "--max-down-specialists",
        type=int,
        default=4,
        help="Max DOWN specialists to combine in the final dual-specialist search.",
    )
    p.add_argument(
        "--specialist-k-grid-up",
        type=str,
        default="1,2,3,4",
        help="Comma list for UP specialist count search.",
    )
    p.add_argument(
        "--specialist-k-grid-down",
        type=str,
        default="1,2,3,4",
        help="Comma list for DOWN specialist count search.",
    )
    p.add_argument(
        "--min-up-votes-grid",
        type=str,
        default="1,2",
        help="Comma list for min UP votes required to emit UP.",
    )
    p.add_argument(
        "--min-down-votes-grid",
        type=str,
        default="1,2",
        help="Comma list for min DOWN votes required to emit DOWN.",
    )
    p.add_argument(
        "--max-overlap-same-side",
        type=float,
        default=0.90,
        help="Max Jaccard overlap allowed between same-side specialists during selection.",
    )
    p.add_argument(
        "--final-objective-opposite-penalty",
        type=float,
        default=2.0,
        help="Penalty on opposite-direction errors in final specialist-combo objective.",
    )
    p.add_argument(
        "--final-objective-hold-side-penalty",
        type=float,
        default=1.0,
        help="Penalty on hold-side cross-direction errors in final combo objective.",
    )
    p.add_argument(
        "--final-objective-coverage-weight",
        type=float,
        default=0.25,
        help="Reward weight on active directional coverage in final combo objective.",
    )
    p.add_argument(
        "--final-min-active-coverage",
        type=float,
        default=0.10,
        help="Constraint: minimum active directional coverage for final combo selection.",
    )
    p.add_argument(
        "--final-max-opposite-rate",
        type=float,
        default=0.08,
        help="Constraint: maximum opposite-direction rate on covered rows for final combo selection. Negative disables.",
    )
    p.add_argument(
        "--final-max-hold-side-rate",
        type=float,
        default=0.03,
        help="Constraint: maximum hold-side cross-error rate on covered rows for final combo selection. Negative disables.",
    )
    p.add_argument(
        "--subset-search-mode",
        type=str,
        default="beam",
        choices=["greedy", "beam"],
        help="Subset builder for UP/DOWN specialist pools before final pairing.",
    )
    p.add_argument(
        "--beam-width-up",
        type=int,
        default=96,
        help="Beam width for UP subset search.",
    )
    p.add_argument(
        "--beam-width-down",
        type=int,
        default=96,
        help="Beam width for DOWN subset search.",
    )
    p.add_argument(
        "--beam-keep-per-k-up",
        type=int,
        default=8,
        help="How many UP subsets to retain per k into pairing pool.",
    )
    p.add_argument(
        "--beam-keep-per-k-down",
        type=int,
        default=8,
        help="How many DOWN subsets to retain per k into pairing pool.",
    )
    p.add_argument(
        "--pair-top-up",
        type=int,
        default=0,
        help="Limit top UP subsets used in final pairing. 0 = auto by combo cap.",
    )
    p.add_argument(
        "--pair-top-down",
        type=int,
        default=0,
        help="Limit top DOWN subsets used in final pairing. 0 = auto by combo cap.",
    )
    p.add_argument(
        "--pair-max-combos",
        type=int,
        default=300000,
        help="Max estimated UP/DOWN thresholded pair combos to evaluate.",
    )
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    if not (0.0 <= args.min_signal_rate_up <= 1.0):
        raise ValueError("--min-signal-rate-up must be in [0,1]")
    if not (0.0 <= args.min_signal_rate_down <= 1.0):
        raise ValueError("--min-signal-rate-down must be in [0,1]")
    if not (0.0 <= args.min_safe_precision_up <= 1.0):
        raise ValueError("--min-safe-precision-up must be in [0,1]")
    if not (0.0 <= args.min_safe_precision_down <= 1.0):
        raise ValueError("--min-safe-precision-down must be in [0,1]")
    if args.max_up_specialists <= 0:
        raise ValueError("--max-up-specialists must be > 0")
    if args.max_down_specialists <= 0:
        raise ValueError("--max-down-specialists must be > 0")
    if not (0.0 <= args.max_overlap_same_side <= 1.0):
        raise ValueError("--max-overlap-same-side must be in [0,1]")
    if not (0.0 <= args.final_min_active_coverage <= 1.0):
        raise ValueError("--final-min-active-coverage must be in [0,1]")
    if args.beam_width_up <= 0 or args.beam_width_down <= 0:
        raise ValueError("--beam-width-up/down must be > 0")
    if args.beam_keep_per_k_up <= 0 or args.beam_keep_per_k_down <= 0:
        raise ValueError("--beam-keep-per-k-up/down must be > 0")
    if args.pair_max_combos <= 0:
        raise ValueError("--pair-max-combos must be > 0")
    return args


def _latest_run_dir(base: Path) -> Path:
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name[:2] == "20"]
    if not dirs:
        raise FileNotFoundError(f"No run dirs under: {base}")
    return sorted(dirs)[-1]


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def _parse_int_grid(raw: str, fallback_max: int) -> list[int]:
    vals: list[int] = []
    for tok in str(raw).split(","):
        tok = tok.strip()
        if not tok:
            continue
        vals.append(int(tok))
    vals = sorted(set(v for v in vals if v > 0))
    if not vals:
        vals = list(range(1, fallback_max + 1))
    return vals


def _config_id(weight_method: str, final_rule: str) -> str:
    return f"{weight_method}||{final_rule}"


def _config_id_split(config_id: str) -> tuple[str, str]:
    if "||" not in config_id:
        return config_id, ""
    a, b = config_id.split("||", 1)
    return a, b


def _jaccard(a: np.ndarray, b: np.ndarray) -> float:
    inter = float(np.logical_and(a, b).sum())
    union = float(np.logical_or(a, b).sum())
    return _safe_div(inter, union)


def _specialist_metrics_for_group(
    pred: np.ndarray,
    truth4: np.ndarray,
    spec: DirectionSpec,
    opposite_penalty: float,
    hold_side_penalty: float,
    signal_rate_weight: float,
) -> dict[str, float]:
    n = int(pred.size)
    signal = pred == spec.signal_label
    signal_count = int(signal.sum())
    signal_rate = _safe_div(signal_count, n)
    safe_truth = (truth4 == spec.truth_same_direction) | (truth4 == spec.truth_hold_same)
    strict_truth = truth4 == spec.truth_same_direction
    opposite_truth = truth4 == spec.truth_opposite
    hold_side_truth = truth4 == spec.truth_hold_opposite
    safe_truth_count = int(safe_truth.sum())
    if signal_count > 0:
        safe_precision = float(safe_truth[signal].mean())
        strict_precision = float(strict_truth[signal].mean())
        opposite_rate_signal = float(opposite_truth[signal].mean())
        hold_side_rate_signal = float(hold_side_truth[signal].mean())
    else:
        safe_precision = 0.0
        strict_precision = 0.0
        opposite_rate_signal = 0.0
        hold_side_rate_signal = 0.0
    safe_recall = _safe_div(float((signal & safe_truth).sum()), safe_truth_count)
    objective = (
        safe_precision
        - opposite_penalty * opposite_rate_signal
        - hold_side_penalty * hold_side_rate_signal
        + signal_rate_weight * signal_rate
    )
    return {
        "anchor_rows": n,
        "signal_count": signal_count,
        "signal_rate": signal_rate,
        "safe_precision": safe_precision,
        "strict_precision": strict_precision,
        "safe_recall": safe_recall,
        "opposite_rate_signal": opposite_rate_signal,
        "hold_side_rate_signal": hold_side_rate_signal,
        "objective": objective,
    }


def _build_specialist_table(
    df: pl.DataFrame,
    spec: DirectionSpec,
    opposite_penalty: float,
    hold_side_penalty: float,
    signal_rate_weight: float,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    key_cols = ["alignment_mode", "weight_method", "final_rule"]
    groups = df.partition_by(key_cols, as_dict=True, maintain_order=False)
    for key, g in groups.items():
        if isinstance(key, tuple):
            alignment_mode, weight_method, final_rule = key
        else:
            # Fallback if Polars changes dictionary key semantics.
            alignment_mode = g["alignment_mode"][0]
            weight_method = g["weight_method"][0]
            final_rule = g["final_rule"][0]
        metrics = _specialist_metrics_for_group(
            pred=g["pred_final"].to_numpy(),
            truth4=g["truth_final4"].to_numpy(),
            spec=spec,
            opposite_penalty=opposite_penalty,
            hold_side_penalty=hold_side_penalty,
            signal_rate_weight=signal_rate_weight,
        )
        rows.append(
            {
                "alignment_mode": str(alignment_mode),
                "weight_method": str(weight_method),
                "final_rule": str(final_rule),
                "config_id": _config_id(str(weight_method), str(final_rule)),
                **metrics,
            }
        )
    return pl.DataFrame(rows)


def _select_specialist_config(
    table: pl.DataFrame,
    min_signal_rate: float,
    min_safe_precision: float,
) -> dict[str, Any]:
    constrained = table.filter(
        (pl.col("signal_count") > 0)
        & (pl.col("signal_rate") >= min_signal_rate)
        & (pl.col("safe_precision") >= min_safe_precision)
    )
    fallback_used = False
    reason = "constraints_satisfied"
    if constrained.is_empty():
        constrained = table.filter(pl.col("signal_count") > 0)
        fallback_used = True
        reason = "fallback_no_rows_met_constraints"
    if constrained.is_empty():
        raise RuntimeError("No config produced any specialist signals.")

    ranked = constrained.sort(
        [
            "objective",
            "safe_precision",
            "signal_rate",
            "opposite_rate_signal",
            "hold_side_rate_signal",
            "weight_method",
            "final_rule",
        ],
        descending=[True, True, True, False, False, False, False],
    )
    top = ranked.row(0, named=True)
    top["fallback_used"] = fallback_used
    top["selection_reason"] = reason
    return top


def _macro_f1_3class(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    labels = [UP, DOWN, HOLD]
    f1s: list[float] = []
    for c in labels:
        tp = int(((y_true == c) & (y_pred == c)).sum())
        fp = int(((y_true != c) & (y_pred == c)).sum())
        fn = int(((y_true == c) & (y_pred != c)).sum())
        p = _safe_div(tp, tp + fp)
        r = _safe_div(tp, tp + fn)
        f1 = _safe_div(2.0 * p * r, p + r) if (p + r) > 0 else 0.0
        f1s.append(float(f1))
    return float(np.mean(f1s))


def _custom_cost(y_true_final: np.ndarray, y_pred: np.ndarray) -> float:
    # Cost: correct=0, opposite-direction=2, hold-vs-direction mismatch=1
    opposite = ((y_true_final == UP) & (y_pred == DOWN)) | (
        (y_true_final == DOWN) & (y_pred == UP)
    )
    hold_mismatch = (
        ((y_true_final == HOLD) & (y_pred != HOLD))
        | ((y_true_final != HOLD) & (y_pred == HOLD))
    ) & (~opposite)
    cost = np.zeros_like(y_pred, dtype=np.float64)
    cost[hold_mismatch] = 1.0
    cost[opposite] = 2.0
    return float(cost.mean())


def _evaluate_final_stream(df: pl.DataFrame, pred_col: str) -> dict[str, Any]:
    y_true_final = df["truth_final"].to_numpy()
    y_true4 = df["truth_final4"].to_numpy()
    y_pred = df[pred_col].to_numpy()

    active = (y_pred == UP) | (y_pred == DOWN)
    active_count = int(active.sum())
    n = int(y_pred.size)
    active_cov = _safe_div(active_count, n)

    safe_ok = ((y_pred == UP) & np.isin(y_true4, [TRUTH_UP, TRUTH_HOLD_UP])) | (
        (y_pred == DOWN) & np.isin(y_true4, [TRUTH_DOWN, TRUTH_HOLD_DOWN])
    )
    strict_ok = ((y_pred == UP) & (y_true4 == TRUTH_UP)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_DOWN)
    )
    active_safe_acc = _safe_div(float((safe_ok & active).sum()), active_count)
    active_strict_acc = _safe_div(float((strict_ok & active).sum()), active_count)

    opposite_total = ((y_pred == UP) & (y_true4 == TRUTH_DOWN)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_UP)
    )
    hold_side_total = ((y_pred == UP) & (y_true4 == TRUTH_HOLD_DOWN)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_HOLD_UP)
    )

    macro_f1_3class = _macro_f1_3class(y_true_final, y_pred)
    return {
        "rows": n,
        "macro_f1_3class": macro_f1_3class,
        # Backward-friendly alias; for this workflow directional metrics below are primary.
        "macro_f1": macro_f1_3class,
        "custom_mean_cost": _custom_cost(y_true_final, y_pred),
        "directional_active_coverage": active_cov,
        "directional_active_safe_accuracy": active_safe_acc,
        "directional_active_strict_accuracy": active_strict_acc,
        "opposite_fp_rate_covered": float(opposite_total.mean()),
        "hold_side_cross_error_rate_covered": float(hold_side_total.mean()),
        "pred_up_rate": float((y_pred == UP).mean()),
        "pred_down_rate": float((y_pred == DOWN).mean()),
        "pred_hold_rate": float((y_pred == HOLD).mean()),
    }


def _build_single_config_stream(
    df: pl.DataFrame,
    *,
    alignment_mode: str,
    weight_method: str,
    final_rule: str,
) -> pl.DataFrame:
    out = df.filter(
        (pl.col("alignment_mode") == alignment_mode)
        & (pl.col("weight_method") == weight_method)
        & (pl.col("final_rule") == final_rule)
    ).select(
        [
            "pred_batch",
            "anchor_15m_ts",
            "truth_final",
            "truth_final4",
            "truth_breakfree",
            "truth_4dir",
            "pred_final",
            "score_final",
        ]
    )
    if out.is_empty():
        raise RuntimeError(
            f"No rows for config alignment={alignment_mode} weight={weight_method} rule={final_rule}"
        )
    return out


def _build_signal_matrices(
    df: pl.DataFrame,
) -> tuple[pl.DataFrame, np.ndarray, np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    keys = [
        "pred_batch",
        "anchor_15m_ts",
        "truth_final",
        "truth_final4",
        "truth_breakfree",
        "truth_4dir",
    ]
    base = (
        df.select(keys)
        .unique()
        .sort(["pred_batch", "anchor_15m_ts"])
        .with_row_index("anchor_idx")
    )

    truth_final = base["truth_final"].to_numpy()
    truth4 = base["truth_final4"].to_numpy()

    cfg_rows = (
        df.select(["pred_batch", "anchor_15m_ts", "weight_method", "final_rule", "pred_final"])
        .with_columns(
            [
                pl.concat_str(
                    [pl.col("weight_method"), pl.lit("||"), pl.col("final_rule")]
                ).alias("config_id"),
                (pl.col("pred_final") == UP).alias("up_signal"),
                (pl.col("pred_final") == DOWN).alias("down_signal"),
            ]
        )
        .join(base.select(["anchor_idx", "pred_batch", "anchor_15m_ts"]), on=["pred_batch", "anchor_15m_ts"], how="inner")
        .select(["config_id", "anchor_idx", "up_signal", "down_signal"])
    )

    n = base.height
    up_map: dict[str, np.ndarray] = {}
    down_map: dict[str, np.ndarray] = {}
    for config_id, g in cfg_rows.partition_by("config_id", as_dict=True, maintain_order=False).items():
        cid = str(config_id if not isinstance(config_id, tuple) else config_id[0])
        gg = g.sort("anchor_idx")
        if gg.height != n:
            # Strictness: if one config misses anchors, pad as no-signal.
            vec_up = np.zeros(n, dtype=bool)
            vec_down = np.zeros(n, dtype=bool)
            idx = gg["anchor_idx"].to_numpy()
            vec_up[idx] = gg["up_signal"].to_numpy()
            vec_down[idx] = gg["down_signal"].to_numpy()
        else:
            vec_up = gg["up_signal"].to_numpy()
            vec_down = gg["down_signal"].to_numpy()
        up_map[cid] = vec_up
        down_map[cid] = vec_down
    return base, truth_final, truth4, up_map, down_map


def _select_diverse_specialists(
    ranked_ids: list[str],
    signal_map: dict[str, np.ndarray],
    k: int,
    max_overlap: float,
) -> list[str]:
    selected: list[str] = []
    for cid in ranked_ids:
        sig = signal_map.get(cid)
        if sig is None or not sig.any():
            continue
        accept = True
        for sid in selected:
            if _jaccard(sig, signal_map[sid]) > max_overlap:
                accept = False
                break
        if accept:
            selected.append(cid)
        if len(selected) >= k:
            break
    if len(selected) < k:
        for cid in ranked_ids:
            if cid in selected:
                continue
            sig = signal_map.get(cid)
            if sig is None or not sig.any():
                continue
            selected.append(cid)
            if len(selected) >= k:
                break
    return selected


def _evaluate_final_arrays(
    y_true_final: np.ndarray, y_true4: np.ndarray, y_pred: np.ndarray
) -> dict[str, Any]:
    active = (y_pred == UP) | (y_pred == DOWN)
    active_count = int(active.sum())
    n = int(y_pred.size)
    active_cov = _safe_div(active_count, n)

    safe_ok = ((y_pred == UP) & np.isin(y_true4, [TRUTH_UP, TRUTH_HOLD_UP])) | (
        (y_pred == DOWN) & np.isin(y_true4, [TRUTH_DOWN, TRUTH_HOLD_DOWN])
    )
    strict_ok = ((y_pred == UP) & (y_true4 == TRUTH_UP)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_DOWN)
    )
    active_safe_acc = _safe_div(float((safe_ok & active).sum()), active_count)
    active_strict_acc = _safe_div(float((strict_ok & active).sum()), active_count)

    opposite_total = ((y_pred == UP) & (y_true4 == TRUTH_DOWN)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_UP)
    )
    hold_side_total = ((y_pred == UP) & (y_true4 == TRUTH_HOLD_DOWN)) | (
        (y_pred == DOWN) & (y_true4 == TRUTH_HOLD_UP)
    )
    macro_f1_3class = _macro_f1_3class(y_true_final, y_pred)
    return {
        "rows": n,
        "macro_f1_3class": macro_f1_3class,
        "macro_f1": macro_f1_3class,
        "custom_mean_cost": _custom_cost(y_true_final, y_pred),
        "directional_active_coverage": active_cov,
        "directional_active_safe_accuracy": active_safe_acc,
        "directional_active_strict_accuracy": active_strict_acc,
        "opposite_fp_rate_covered": float(opposite_total.mean()),
        "hold_side_cross_error_rate_covered": float(hold_side_total.mean()),
        "pred_up_rate": float((y_pred == UP).mean()),
        "pred_down_rate": float((y_pred == DOWN).mean()),
        "pred_hold_rate": float((y_pred == HOLD).mean()),
    }


def _objective_final_combo(
    metrics: dict[str, Any],
    *,
    opposite_penalty: float,
    hold_side_penalty: float,
    coverage_weight: float,
) -> float:
    return float(
        metrics["directional_active_safe_accuracy"]
        - opposite_penalty * metrics["opposite_fp_rate_covered"]
        - hold_side_penalty * metrics["hold_side_cross_error_rate_covered"]
        + coverage_weight * metrics["directional_active_coverage"]
    )


def _specialist_metrics_from_signal(
    signal: np.ndarray,
    truth4: np.ndarray,
    spec: DirectionSpec,
    opposite_penalty: float,
    hold_side_penalty: float,
    signal_rate_weight: float,
) -> dict[str, float]:
    n = int(signal.size)
    signal_count = int(signal.sum())
    signal_rate = _safe_div(signal_count, n)
    safe_truth = (truth4 == spec.truth_same_direction) | (truth4 == spec.truth_hold_same)
    strict_truth = truth4 == spec.truth_same_direction
    opposite_truth = truth4 == spec.truth_opposite
    hold_side_truth = truth4 == spec.truth_hold_opposite
    safe_truth_count = int(safe_truth.sum())

    if signal_count > 0:
        safe_precision = float(safe_truth[signal].mean())
        strict_precision = float(strict_truth[signal].mean())
        opposite_rate_signal = float(opposite_truth[signal].mean())
        hold_side_rate_signal = float(hold_side_truth[signal].mean())
    else:
        safe_precision = 0.0
        strict_precision = 0.0
        opposite_rate_signal = 0.0
        hold_side_rate_signal = 0.0

    safe_recall = _safe_div(float((signal & safe_truth).sum()), safe_truth_count)
    objective = (
        safe_precision
        - opposite_penalty * opposite_rate_signal
        - hold_side_penalty * hold_side_rate_signal
        + signal_rate_weight * signal_rate
    )
    return {
        "anchor_rows": n,
        "signal_count": signal_count,
        "signal_rate": signal_rate,
        "safe_precision": safe_precision,
        "strict_precision": strict_precision,
        "safe_recall": safe_recall,
        "opposite_rate_signal": opposite_rate_signal,
        "hold_side_rate_signal": hold_side_rate_signal,
        "objective": objective,
    }


def _choose_best_vote_threshold(
    *,
    votes: np.ndarray,
    allowed_thresholds: list[int],
    truth4: np.ndarray,
    spec: DirectionSpec,
    min_signal_rate: float,
    min_safe_precision: float,
    opposite_penalty: float,
    hold_side_penalty: float,
    signal_rate_weight: float,
) -> tuple[int, dict[str, float], bool]:
    rows: list[tuple[int, dict[str, float]]] = []
    for thr in allowed_thresholds:
        signal = votes >= int(thr)
        m = _specialist_metrics_from_signal(
            signal,
            truth4,
            spec,
            opposite_penalty=opposite_penalty,
            hold_side_penalty=hold_side_penalty,
            signal_rate_weight=signal_rate_weight,
        )
        rows.append((int(thr), m))

    constrained = [
        (thr, m)
        for (thr, m) in rows
        if m["signal_count"] > 0
        and m["signal_rate"] >= min_signal_rate
        and m["safe_precision"] >= min_safe_precision
    ]
    fallback_used = False
    if not constrained:
        constrained = [(thr, m) for (thr, m) in rows if m["signal_count"] > 0]
        fallback_used = True
    if not constrained:
        # No signals for any threshold; return the smallest threshold.
        thr = int(allowed_thresholds[0])
        m = rows[0][1]
        return thr, m, True

    constrained.sort(
        key=lambda x: (
            x[1]["objective"],
            x[1]["safe_precision"],
            x[1]["signal_rate"],
            -x[1]["opposite_rate_signal"],
            -x[1]["hold_side_rate_signal"],
            -x[0],  # deterministic tie-break: prefer smaller threshold
        ),
        reverse=True,
    )
    return int(constrained[0][0]), constrained[0][1], fallback_used


def _subset_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        float(row["objective"]),
        float(row["safe_precision"]),
        float(row["signal_rate"]),
        -float(row["opposite_rate_signal"]),
        -float(row["hold_side_rate_signal"]),
        tuple(row["config_ids"]),
    )


def _build_side_candidates_beam(
    *,
    ranked_ids: list[str],
    signal_map: dict[str, np.ndarray],
    truth4: np.ndarray,
    spec: DirectionSpec,
    max_k: int,
    beam_width: int,
    keep_per_k: int,
    vote_grid: list[int],
    min_signal_rate: float,
    min_safe_precision: float,
    opposite_penalty: float,
    hold_side_penalty: float,
    signal_rate_weight: float,
) -> list[dict[str, Any]]:
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for cid in ranked_ids:
        if cid in seen:
            continue
        sig = signal_map.get(cid)
        if sig is None:
            continue
        if not bool(sig.any()):
            continue
        seen.add(cid)
        ordered_ids.append(cid)
    if not ordered_ids:
        return []

    max_k = min(max_k, len(ordered_ids))
    x = np.column_stack([signal_map[cid] for cid in ordered_ids]).astype(np.int16)
    n_cfg = x.shape[1]

    candidates_by_k: dict[int, list[dict[str, Any]]] = {}
    frontier: list[tuple[tuple[int, ...], np.ndarray]] = [
        ((idx,), x[:, idx].copy()) for idx in range(n_cfg)
    ]

    for k in range(1, max_k + 1):
        scored: list[dict[str, Any]] = []
        for subset_idx, votes in frontier:
            allowed_thresholds = [v for v in vote_grid if v <= len(subset_idx)]
            if not allowed_thresholds:
                continue
            best_vote, metrics, fb = _choose_best_vote_threshold(
                votes=votes,
                allowed_thresholds=allowed_thresholds,
                truth4=truth4,
                spec=spec,
                min_signal_rate=min_signal_rate,
                min_safe_precision=min_safe_precision,
                opposite_penalty=opposite_penalty,
                hold_side_penalty=hold_side_penalty,
                signal_rate_weight=signal_rate_weight,
            )
            scored.append(
                {
                    "k": len(subset_idx),
                    "subset_idx": subset_idx,
                    "config_ids": [ordered_ids[i] for i in subset_idx],
                    "votes": votes,
                    "min_votes": int(best_vote),
                    "fallback_used": bool(fb),
                    **metrics,
                }
            )

        if not scored:
            break
        scored.sort(key=_subset_sort_key, reverse=True)
        candidates_by_k[k] = scored[:keep_per_k]
        expand_from = scored[:beam_width]

        next_frontier: list[tuple[tuple[int, ...], np.ndarray]] = []
        seen_subsets: set[tuple[int, ...]] = set()
        for row in expand_from:
            subset_idx = tuple(row["subset_idx"])
            votes = row["votes"]
            subset_set = set(subset_idx)
            for j in range(n_cfg):
                if j in subset_set:
                    continue
                nxt = tuple(sorted(subset_idx + (j,)))
                if nxt in seen_subsets:
                    continue
                seen_subsets.add(nxt)
                next_frontier.append((nxt, votes + x[:, j]))
        frontier = next_frontier
        if not frontier:
            break

    pool: list[dict[str, Any]] = []
    for k in sorted(candidates_by_k):
        pool.extend(candidates_by_k[k])
    pool.sort(key=_subset_sort_key, reverse=True)
    return pool


def _estimate_pair_combos(
    up_pool: list[dict[str, Any]],
    down_pool: list[dict[str, Any]],
    up_vote_grid: list[int],
    down_vote_grid: list[int],
) -> int:
    up_cnt = [sum(1 for v in up_vote_grid if v <= int(x["k"])) for x in up_pool]
    dn_cnt = [sum(1 for v in down_vote_grid if v <= int(x["k"])) for x in down_pool]
    total = 0
    for u in up_cnt:
        for d in dn_cnt:
            total += int(u * d)
    return int(total)


def _build_vote_ladder(
    *,
    votes: np.ndarray,
    truth4: np.ndarray,
    spec: DirectionSpec,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    n = int(votes.size)
    max_votes = int(votes.max()) if n > 0 else 0
    safe_truth = (truth4 == spec.truth_same_direction) | (truth4 == spec.truth_hold_same)
    strict_truth = truth4 == spec.truth_same_direction
    opposite_truth = truth4 == spec.truth_opposite
    hold_side_truth = truth4 == spec.truth_hold_opposite
    for min_votes in range(1, max_votes + 1):
        signal = votes >= min_votes
        signal_count = int(signal.sum())
        if signal_count > 0:
            safe_precision = float(safe_truth[signal].mean())
            strict_precision = float(strict_truth[signal].mean())
            opposite_rate_signal = float(opposite_truth[signal].mean())
            hold_side_rate_signal = float(hold_side_truth[signal].mean())
        else:
            safe_precision = 0.0
            strict_precision = 0.0
            opposite_rate_signal = 0.0
            hold_side_rate_signal = 0.0
        rows.append(
            {
                "direction": spec.name,
                "min_votes": int(min_votes),
                "signal_count": int(signal_count),
                "signal_rate": _safe_div(signal_count, n),
                "safe_precision": safe_precision,
                "strict_precision": strict_precision,
                "opposite_rate_signal": opposite_rate_signal,
                "hold_side_rate_signal": hold_side_rate_signal,
            }
        )
    return pl.DataFrame(rows)


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).resolve()
    input_root = (project_root / DEFAULT_INPUT_ROOT).resolve()
    output_root = (project_root / args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    run_dir = (
        Path(args.cross_target_run_dir).resolve()
        if args.cross_target_run_dir
        else _latest_run_dir(input_root)
    )
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.output_tag}" if args.output_tag else ""
    out_dir = output_root / f"{ts}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=False)

    pred_path = run_dir / "final_ensemble_predictions_walkforward.parquet"
    if not pred_path.exists():
        raise FileNotFoundError(f"Missing file: {pred_path}")
    df = pl.read_parquet(pred_path)
    need_cols = {
        "alignment_mode",
        "weight_method",
        "final_rule",
        "pred_batch",
        "anchor_15m_ts",
        "truth_final",
        "truth_final4",
        "truth_breakfree",
        "truth_4dir",
        "pred_final",
        "score_final",
    }
    missing = need_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {pred_path}: {sorted(missing)}")

    df = df.filter(pl.col("alignment_mode") == args.alignment_mode).sort(
        ["weight_method", "final_rule", "pred_batch", "anchor_15m_ts"]
    )
    if df.is_empty():
        raise RuntimeError(f"No rows for alignment_mode={args.alignment_mode}")

    if args.verbose:
        print("UP/DOWN specialist search")
        print(f"  input_run: {run_dir}")
        print(f"  output_dir: {out_dir}")
        print(f"  alignment_mode: {args.alignment_mode}")
        print(f"  rows: {df.height}")

    up_table = _build_specialist_table(
        df,
        spec=UP_SPEC,
        opposite_penalty=args.objective_opposite_penalty,
        hold_side_penalty=args.objective_hold_side_penalty,
        signal_rate_weight=args.objective_signal_rate_weight,
    )
    down_table = _build_specialist_table(
        df,
        spec=DOWN_SPEC,
        opposite_penalty=args.objective_opposite_penalty,
        hold_side_penalty=args.objective_hold_side_penalty,
        signal_rate_weight=args.objective_signal_rate_weight,
    )

    up_best = _select_specialist_config(
        up_table,
        min_signal_rate=args.min_signal_rate_up,
        min_safe_precision=args.min_safe_precision_up,
    )
    down_best = _select_specialist_config(
        down_table,
        min_signal_rate=args.min_signal_rate_down,
        min_safe_precision=args.min_safe_precision_down,
    )

    up_stream = _build_single_config_stream(
        df,
        alignment_mode=args.alignment_mode,
        weight_method=str(up_best["weight_method"]),
        final_rule=str(up_best["final_rule"]),
    ).rename({"pred_final": "pred_up_raw", "score_final": "score_up"})

    down_stream = _build_single_config_stream(
        df,
        alignment_mode=args.alignment_mode,
        weight_method=str(down_best["weight_method"]),
        final_rule=str(down_best["final_rule"]),
    ).rename({"pred_final": "pred_down_raw", "score_final": "score_down"})

    join_keys = [
        "pred_batch",
        "anchor_15m_ts",
        "truth_final",
        "truth_final4",
        "truth_breakfree",
        "truth_4dir",
    ]
    dual = up_stream.join(down_stream, on=join_keys, how="inner")
    dual = dual.with_columns(
        [
            (pl.col("pred_up_raw") == UP).alias("up_signal"),
            (pl.col("pred_down_raw") == DOWN).alias("down_signal"),
        ]
    ).with_columns(
        [
            pl.when(pl.col("up_signal") & (~pl.col("down_signal")))
            .then(pl.lit(UP))
            .when((~pl.col("up_signal")) & pl.col("down_signal"))
            .then(pl.lit(DOWN))
            .otherwise(pl.lit(HOLD))
            .alias("pred_dual_specialist"),
            (pl.col("up_signal") & pl.col("down_signal")).alias("conflict_both_signals"),
        ]
    )

    dual_eval = _evaluate_final_stream(dual, pred_col="pred_dual_specialist")
    up_eval = _evaluate_final_stream(dual, pred_col="pred_up_raw")
    down_eval = _evaluate_final_stream(dual, pred_col="pred_down_raw")

    baseline_eval: dict[str, Any] | None = None
    summary_path = run_dir / "summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            best = summary.get("best_setup", {})
            if best:
                baseline_stream = _build_single_config_stream(
                    df,
                    alignment_mode=args.alignment_mode,
                    weight_method=str(best.get("weight_method")),
                    final_rule=str(best.get("final_rule")),
                ).rename({"pred_final": "pred_baseline"})
                baseline_eval = _evaluate_final_stream(
                    baseline_stream, pred_col="pred_baseline"
                )
        except Exception:
            baseline_eval = None

    # Multi-specialist optimization (UP and DOWN independently, then combined).
    base_anchors, y_true_final, y_true4, up_signal_map, down_signal_map = _build_signal_matrices(
        df
    )
    up_ranked_ids = (
        up_table.sort(
            [
                "objective",
                "safe_precision",
                "signal_rate",
                "opposite_rate_signal",
                "hold_side_rate_signal",
                "config_id",
            ],
            descending=[True, True, True, False, False, False],
        )["config_id"]
        .to_list()
    )
    down_ranked_ids = (
        down_table.sort(
            [
                "objective",
                "safe_precision",
                "signal_rate",
                "opposite_rate_signal",
                "hold_side_rate_signal",
                "config_id",
            ],
            descending=[True, True, True, False, False, False],
        )["config_id"]
        .to_list()
    )

    up_k_grid = [
        k
        for k in _parse_int_grid(args.specialist_k_grid_up, args.max_up_specialists)
        if k <= args.max_up_specialists
    ]
    down_k_grid = [
        k
        for k in _parse_int_grid(args.specialist_k_grid_down, args.max_down_specialists)
        if k <= args.max_down_specialists
    ]
    up_vote_grid = _parse_int_grid(args.min_up_votes_grid, args.max_up_specialists)
    down_vote_grid = _parse_int_grid(args.min_down_votes_grid, args.max_down_specialists)

    up_pool: list[dict[str, Any]] = []
    down_pool: list[dict[str, Any]] = []
    if args.subset_search_mode == "beam":
        up_pool = _build_side_candidates_beam(
            ranked_ids=up_ranked_ids,
            signal_map=up_signal_map,
            truth4=y_true4,
            spec=UP_SPEC,
            max_k=args.max_up_specialists,
            beam_width=args.beam_width_up,
            keep_per_k=args.beam_keep_per_k_up,
            vote_grid=up_vote_grid,
            min_signal_rate=args.min_signal_rate_up,
            min_safe_precision=args.min_safe_precision_up,
            opposite_penalty=args.objective_opposite_penalty,
            hold_side_penalty=args.objective_hold_side_penalty,
            signal_rate_weight=args.objective_signal_rate_weight,
        )
        down_pool = _build_side_candidates_beam(
            ranked_ids=down_ranked_ids,
            signal_map=down_signal_map,
            truth4=y_true4,
            spec=DOWN_SPEC,
            max_k=args.max_down_specialists,
            beam_width=args.beam_width_down,
            keep_per_k=args.beam_keep_per_k_down,
            vote_grid=down_vote_grid,
            min_signal_rate=args.min_signal_rate_down,
            min_safe_precision=args.min_safe_precision_down,
            opposite_penalty=args.objective_opposite_penalty,
            hold_side_penalty=args.objective_hold_side_penalty,
            signal_rate_weight=args.objective_signal_rate_weight,
        )
    else:
        for up_k in up_k_grid:
            sel_up = _select_diverse_specialists(
                up_ranked_ids, up_signal_map, up_k, args.max_overlap_same_side
            )
            if not sel_up:
                continue
            votes = np.column_stack([up_signal_map[cid] for cid in sel_up]).sum(axis=1)
            allowed = [v for v in up_vote_grid if v <= len(sel_up)]
            if not allowed:
                continue
            best_vote, metrics, fb = _choose_best_vote_threshold(
                votes=votes,
                allowed_thresholds=allowed,
                truth4=y_true4,
                spec=UP_SPEC,
                min_signal_rate=args.min_signal_rate_up,
                min_safe_precision=args.min_safe_precision_up,
                opposite_penalty=args.objective_opposite_penalty,
                hold_side_penalty=args.objective_hold_side_penalty,
                signal_rate_weight=args.objective_signal_rate_weight,
            )
            up_pool.append(
                {
                    "k": len(sel_up),
                    "config_ids": sel_up,
                    "votes": votes,
                    "min_votes": best_vote,
                    "fallback_used": fb,
                    **metrics,
                }
            )
        for down_k in down_k_grid:
            sel_down = _select_diverse_specialists(
                down_ranked_ids, down_signal_map, down_k, args.max_overlap_same_side
            )
            if not sel_down:
                continue
            votes = np.column_stack([down_signal_map[cid] for cid in sel_down]).sum(axis=1)
            allowed = [v for v in down_vote_grid if v <= len(sel_down)]
            if not allowed:
                continue
            best_vote, metrics, fb = _choose_best_vote_threshold(
                votes=votes,
                allowed_thresholds=allowed,
                truth4=y_true4,
                spec=DOWN_SPEC,
                min_signal_rate=args.min_signal_rate_down,
                min_safe_precision=args.min_safe_precision_down,
                opposite_penalty=args.objective_opposite_penalty,
                hold_side_penalty=args.objective_hold_side_penalty,
                signal_rate_weight=args.objective_signal_rate_weight,
            )
            down_pool.append(
                {
                    "k": len(sel_down),
                    "config_ids": sel_down,
                    "votes": votes,
                    "min_votes": best_vote,
                    "fallback_used": fb,
                    **metrics,
                }
            )
        up_pool.sort(key=_subset_sort_key, reverse=True)
        down_pool.sort(key=_subset_sort_key, reverse=True)

    if not up_pool or not down_pool:
        raise RuntimeError("No UP/DOWN specialist subset candidates generated.")

    up_pool_df = pl.DataFrame(
        [
            {
                "k": int(x["k"]),
                "config_ids": json.dumps(list(x["config_ids"])),
                "min_votes": int(x["min_votes"]),
                "fallback_used": bool(x["fallback_used"]),
                "objective": float(x["objective"]),
                "safe_precision": float(x["safe_precision"]),
                "signal_rate": float(x["signal_rate"]),
                "opposite_rate_signal": float(x["opposite_rate_signal"]),
                "hold_side_rate_signal": float(x["hold_side_rate_signal"]),
            }
            for x in up_pool
        ]
    )
    down_pool_df = pl.DataFrame(
        [
            {
                "k": int(x["k"]),
                "config_ids": json.dumps(list(x["config_ids"])),
                "min_votes": int(x["min_votes"]),
                "fallback_used": bool(x["fallback_used"]),
                "objective": float(x["objective"]),
                "safe_precision": float(x["safe_precision"]),
                "signal_rate": float(x["signal_rate"]),
                "opposite_rate_signal": float(x["opposite_rate_signal"]),
                "hold_side_rate_signal": float(x["hold_side_rate_signal"]),
            }
            for x in down_pool
        ]
    )

    pair_up_n = min(int(args.pair_top_up), len(up_pool)) if args.pair_top_up > 0 else len(up_pool)
    pair_down_n = (
        min(int(args.pair_top_down), len(down_pool))
        if args.pair_top_down > 0
        else len(down_pool)
    )
    while True:
        est = _estimate_pair_combos(
            up_pool[:pair_up_n], down_pool[:pair_down_n], up_vote_grid, down_vote_grid
        )
        if est <= int(args.pair_max_combos):
            break
        if pair_up_n <= 1 and pair_down_n <= 1:
            break
        if pair_up_n >= pair_down_n and pair_up_n > 1:
            pair_up_n -= 1
        elif pair_down_n > 1:
            pair_down_n -= 1

    selected_up_pool = up_pool[:pair_up_n]
    selected_down_pool = down_pool[:pair_down_n]
    pair_combo_estimate = _estimate_pair_combos(
        selected_up_pool, selected_down_pool, up_vote_grid, down_vote_grid
    )
    if args.verbose:
        print(
            "  pairing_pool: "
            f"up={len(selected_up_pool)}/{len(up_pool)} "
            f"down={len(selected_down_pool)}/{len(down_pool)} "
            f"estimated_combos={pair_combo_estimate}"
        )

    grid_rows: list[dict[str, Any]] = []
    for up_idx, up_c in enumerate(selected_up_pool):
        up_votes = up_c["votes"]
        up_cfgs = list(up_c["config_ids"])
        up_allowed = [v for v in up_vote_grid if v <= len(up_cfgs)]
        for down_idx, down_c in enumerate(selected_down_pool):
            down_votes = down_c["votes"]
            down_cfgs = list(down_c["config_ids"])
            down_allowed = [v for v in down_vote_grid if v <= len(down_cfgs)]
            for min_up_votes in up_allowed:
                up_active = up_votes >= int(min_up_votes)
                for min_down_votes in down_allowed:
                    down_active = down_votes >= int(min_down_votes)
                    y_pred = np.full(y_true_final.shape[0], HOLD, dtype=np.int8)
                    y_pred[up_active & (~down_active)] = UP
                    y_pred[(~up_active) & down_active] = DOWN
                    metrics = _evaluate_final_arrays(y_true_final, y_true4, y_pred)
                    objective = _objective_final_combo(
                        metrics,
                        opposite_penalty=args.final_objective_opposite_penalty,
                        hold_side_penalty=args.final_objective_hold_side_penalty,
                        coverage_weight=args.final_objective_coverage_weight,
                    )
                    pass_cov = (
                        metrics["directional_active_coverage"] >= args.final_min_active_coverage
                    )
                    pass_opp = (
                        True
                        if args.final_max_opposite_rate < 0
                        else metrics["opposite_fp_rate_covered"] <= args.final_max_opposite_rate
                    )
                    pass_hold = (
                        True
                        if args.final_max_hold_side_rate < 0
                        else metrics["hold_side_cross_error_rate_covered"] <= args.final_max_hold_side_rate
                    )
                    grid_rows.append(
                        {
                            "up_pool_rank": int(up_idx + 1),
                            "down_pool_rank": int(down_idx + 1),
                            "up_k": int(len(up_cfgs)),
                            "down_k": int(len(down_cfgs)),
                            "min_up_votes": int(min_up_votes),
                            "min_down_votes": int(min_down_votes),
                            "up_configs": json.dumps(up_cfgs),
                            "down_configs": json.dumps(down_cfgs),
                            "pass_constraints": bool(pass_cov and pass_opp and pass_hold),
                            "objective_final": float(objective),
                            **metrics,
                        }
                    )

    if not grid_rows:
        raise RuntimeError("No specialist-combo candidates evaluated.")
    grid_df = pl.DataFrame(grid_rows).sort(
        [
            "pass_constraints",
            "objective_final",
            "directional_active_safe_accuracy",
            "directional_active_coverage",
            "opposite_fp_rate_covered",
            "hold_side_cross_error_rate_covered",
        ],
        descending=[True, True, True, True, False, False],
    )
    best_combo_row = grid_df.row(0, named=True)
    used_constraint_fallback = not bool(best_combo_row["pass_constraints"])
    if used_constraint_fallback:
        # If no row satisfies constraints, select best unconstrained by objective.
        unconstrained = grid_df.sort(
            [
                "objective_final",
                "directional_active_safe_accuracy",
                "directional_active_coverage",
                "opposite_fp_rate_covered",
                "hold_side_cross_error_rate_covered",
            ],
            descending=[True, True, True, False, False],
        )
        best_combo_row = unconstrained.row(0, named=True)

    max_specialists_row: dict[str, Any] | None = None
    pass_df = grid_df.filter(pl.col("pass_constraints"))
    if not pass_df.is_empty():
        pass_df = pass_df.with_columns((pl.col("up_k") + pl.col("down_k")).alias("total_specialists"))
        max_total = int(pass_df["total_specialists"].max())
        max_specialists_row = (
            pass_df.filter(pl.col("total_specialists") == max_total)
            .sort(
                [
                    "objective_final",
                    "directional_active_safe_accuracy",
                    "directional_active_coverage",
                    "opposite_fp_rate_covered",
                    "hold_side_cross_error_rate_covered",
                ],
                descending=[True, True, True, False, False],
            )
            .row(0, named=True)
        )

    best_up_list = json.loads(str(best_combo_row["up_configs"]))
    best_down_list = json.loads(str(best_combo_row["down_configs"]))
    up_vote_best = int(best_combo_row["min_up_votes"])
    down_vote_best = int(best_combo_row["min_down_votes"])
    up_votes_best = np.column_stack([up_signal_map[cid] for cid in best_up_list]).sum(axis=1)
    down_votes_best = np.column_stack([down_signal_map[cid] for cid in best_down_list]).sum(axis=1)
    up_active_best = up_votes_best >= up_vote_best
    down_active_best = down_votes_best >= down_vote_best
    pred_multi = np.full(y_true_final.shape[0], HOLD, dtype=np.int8)
    pred_multi[up_active_best & (~down_active_best)] = UP
    pred_multi[(~up_active_best) & down_active_best] = DOWN
    conflict_multi = up_active_best & down_active_best
    multi_eval = _evaluate_final_arrays(y_true_final, y_true4, pred_multi)
    multi_eval["objective_final"] = float(best_combo_row["objective_final"])

    # Write artifacts
    up_table.sort(
        [
            "objective",
            "safe_precision",
            "signal_rate",
            "opposite_rate_signal",
            "hold_side_rate_signal",
            "weight_method",
            "final_rule",
        ],
        descending=[True, True, True, False, False, False, False],
    ).write_parquet(out_dir / "per_config_up_metrics.parquet")
    up_table.write_csv(out_dir / "per_config_up_metrics.csv")

    down_table.sort(
        [
            "objective",
            "safe_precision",
            "signal_rate",
            "opposite_rate_signal",
            "hold_side_rate_signal",
            "weight_method",
            "final_rule",
        ],
        descending=[True, True, True, False, False, False, False],
    ).write_parquet(out_dir / "per_config_down_metrics.parquet")
    down_table.write_csv(out_dir / "per_config_down_metrics.csv")
    up_pool_df.write_parquet(out_dir / "up_subset_pool.parquet")
    up_pool_df.write_csv(out_dir / "up_subset_pool.csv")
    down_pool_df.write_parquet(out_dir / "down_subset_pool.parquet")
    down_pool_df.write_csv(out_dir / "down_subset_pool.csv")

    grid_df.write_parquet(out_dir / "specialist_combo_grid.parquet")
    grid_df.write_csv(out_dir / "specialist_combo_grid.csv")

    dual.write_parquet(out_dir / "dual_specialist_predictions.parquet")
    dual.select(
        [
            "pred_batch",
            "anchor_15m_ts",
            "truth_final",
            "truth_final4",
            "pred_up_raw",
            "pred_down_raw",
            "up_signal",
            "down_signal",
            "conflict_both_signals",
            "pred_dual_specialist",
            "score_up",
            "score_down",
        ]
    ).write_csv(out_dir / "dual_specialist_predictions.csv")

    base_multi = base_anchors.select(
        ["pred_batch", "anchor_15m_ts", "truth_final", "truth_final4", "truth_breakfree", "truth_4dir"]
    )
    multi_df = base_multi.with_columns(
        [
            pl.Series("up_votes", up_votes_best.astype(np.int64)),
            pl.Series("down_votes", down_votes_best.astype(np.int64)),
            pl.Series("up_signal", up_active_best),
            pl.Series("down_signal", down_active_best),
            pl.Series("conflict_both_signals", conflict_multi),
            pl.Series("pred_dual_multi_specialist", pred_multi.astype(np.int8)),
        ]
    )
    multi_df.write_parquet(out_dir / "dual_multi_specialist_predictions.parquet")
    multi_df.write_csv(out_dir / "dual_multi_specialist_predictions.csv")

    up_vote_ladder = _build_vote_ladder(votes=up_votes_best, truth4=y_true4, spec=UP_SPEC)
    down_vote_ladder = _build_vote_ladder(votes=down_votes_best, truth4=y_true4, spec=DOWN_SPEC)
    up_vote_ladder.write_parquet(out_dir / "up_vote_specialist_ladder.parquet")
    up_vote_ladder.write_csv(out_dir / "up_vote_specialist_ladder.csv")
    down_vote_ladder.write_parquet(out_dir / "down_vote_specialist_ladder.parquet")
    down_vote_ladder.write_csv(out_dir / "down_vote_specialist_ladder.csv")

    (out_dir / "selected_up_config.json").write_text(
        json.dumps(up_best, indent=2), encoding="utf-8"
    )
    (out_dir / "selected_down_config.json").write_text(
        json.dumps(down_best, indent=2), encoding="utf-8"
    )
    (out_dir / "selected_up_specialists.json").write_text(
        json.dumps(
            {
                "selected_config_ids": best_up_list,
                "selected_configs": [
                    {"weight_method": _config_id_split(cid)[0], "final_rule": _config_id_split(cid)[1]}
                    for cid in best_up_list
                ],
                "min_votes": up_vote_best,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (out_dir / "selected_down_specialists.json").write_text(
        json.dumps(
            {
                "selected_config_ids": best_down_list,
                "selected_configs": [
                    {"weight_method": _config_id_split(cid)[0], "final_rule": _config_id_split(cid)[1]}
                    for cid in best_down_list
                ],
                "min_votes": down_vote_best,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    config_resolved = {
        "project_root": str(project_root),
        "input_run_dir": str(run_dir),
        "alignment_mode": args.alignment_mode,
        "min_signal_rate_up": args.min_signal_rate_up,
        "min_signal_rate_down": args.min_signal_rate_down,
        "min_safe_precision_up": args.min_safe_precision_up,
        "min_safe_precision_down": args.min_safe_precision_down,
        "objective_opposite_penalty": args.objective_opposite_penalty,
        "objective_hold_side_penalty": args.objective_hold_side_penalty,
        "objective_signal_rate_weight": args.objective_signal_rate_weight,
        "max_up_specialists": args.max_up_specialists,
        "max_down_specialists": args.max_down_specialists,
        "subset_search_mode": args.subset_search_mode,
        "beam_width_up": args.beam_width_up,
        "beam_width_down": args.beam_width_down,
        "beam_keep_per_k_up": args.beam_keep_per_k_up,
        "beam_keep_per_k_down": args.beam_keep_per_k_down,
        "pair_top_up": args.pair_top_up,
        "pair_top_down": args.pair_top_down,
        "pair_max_combos": args.pair_max_combos,
        "specialist_k_grid_up": up_k_grid,
        "specialist_k_grid_down": down_k_grid,
        "min_up_votes_grid": up_vote_grid,
        "min_down_votes_grid": down_vote_grid,
        "max_overlap_same_side": args.max_overlap_same_side,
        "final_objective_opposite_penalty": args.final_objective_opposite_penalty,
        "final_objective_hold_side_penalty": args.final_objective_hold_side_penalty,
        "final_objective_coverage_weight": args.final_objective_coverage_weight,
        "final_min_active_coverage": args.final_min_active_coverage,
        "final_max_opposite_rate": args.final_max_opposite_rate,
        "final_max_hold_side_rate": args.final_max_hold_side_rate,
    }
    (out_dir / "config_resolved.json").write_text(
        json.dumps(config_resolved, indent=2), encoding="utf-8"
    )

    summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": config_resolved,
        "counts": {
            "input_rows": int(df.height),
            "up_configs": int(up_table.height),
            "down_configs": int(down_table.height),
            "dual_rows": int(dual.height),
            "up_subset_pool_rows": int(up_pool_df.height),
            "down_subset_pool_rows": int(down_pool_df.height),
            "up_subset_pool_selected": int(len(selected_up_pool)),
            "down_subset_pool_selected": int(len(selected_down_pool)),
            "pair_combo_estimate": int(pair_combo_estimate),
            "specialist_combo_rows": int(grid_df.height),
        },
        "selected_up_config": up_best,
        "selected_down_config": down_best,
        "selected_up_specialists": {
            "config_ids": best_up_list,
            "min_votes": up_vote_best,
        },
        "selected_down_specialists": {
            "config_ids": best_down_list,
            "min_votes": down_vote_best,
        },
        "constraint_fallback_used_for_combo": used_constraint_fallback,
        "max_specialists_combo_under_constraints": max_specialists_row,
        "evaluation": {
            "dual_specialist": dual_eval,
            "dual_multi_specialist": multi_eval,
            "up_selected_stream": up_eval,
            "down_selected_stream": down_eval,
            "baseline_single_best_setup_if_available": baseline_eval,
        },
        "artifacts": {
            "per_config_up_metrics_parquet": str(out_dir / "per_config_up_metrics.parquet"),
            "per_config_down_metrics_parquet": str(
                out_dir / "per_config_down_metrics.parquet"
            ),
            "up_subset_pool_parquet": str(out_dir / "up_subset_pool.parquet"),
            "down_subset_pool_parquet": str(out_dir / "down_subset_pool.parquet"),
            "dual_specialist_predictions_parquet": str(
                out_dir / "dual_specialist_predictions.parquet"
            ),
            "dual_multi_specialist_predictions_parquet": str(
                out_dir / "dual_multi_specialist_predictions.parquet"
            ),
            "up_vote_specialist_ladder_parquet": str(
                out_dir / "up_vote_specialist_ladder.parquet"
            ),
            "down_vote_specialist_ladder_parquet": str(
                out_dir / "down_vote_specialist_ladder.parquet"
            ),
            "specialist_combo_grid_parquet": str(out_dir / "specialist_combo_grid.parquet"),
            "selected_up_config_json": str(out_dir / "selected_up_config.json"),
            "selected_down_config_json": str(out_dir / "selected_down_config.json"),
            "selected_up_specialists_json": str(out_dir / "selected_up_specialists.json"),
            "selected_down_specialists_json": str(out_dir / "selected_down_specialists.json"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.verbose:
        print("Completed specialist selection.")
        print(f"  output: {out_dir}")
        print(
            "  selected_up: "
            f"{up_best['weight_method']} + {up_best['final_rule']} "
            f"(signal_rate={up_best['signal_rate']:.4f}, safe_precision={up_best['safe_precision']:.4f})"
        )
        print(
            "  selected_down: "
            f"{down_best['weight_method']} + {down_best['final_rule']} "
            f"(signal_rate={down_best['signal_rate']:.4f}, safe_precision={down_best['safe_precision']:.4f})"
        )
        print(
            "  dual_specialist: "
            f"macro_f1={dual_eval['macro_f1']:.4f} "
            f"opp_fp_rate={dual_eval['opposite_fp_rate_covered']:.4f} "
            f"active_cov={dual_eval['directional_active_coverage']:.4f}"
        )
        print(
            "  dual_multi_specialist: "
            f"macro_f1={multi_eval['macro_f1']:.4f} "
            f"opp_fp_rate={multi_eval['opposite_fp_rate_covered']:.4f} "
            f"active_cov={multi_eval['directional_active_coverage']:.4f} "
            f"up_k={len(best_up_list)} down_k={len(best_down_list)} "
            f"up_votes={up_vote_best} down_votes={down_vote_best}"
        )


if __name__ == "__main__":
    main()

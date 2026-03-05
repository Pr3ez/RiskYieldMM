#!/usr/bin/env python3
"""Greedy subset pruning for multi-timeframe direction ensemble.

Goal:
- Check whether removing some configs (from 12 per unit) improves
  one ensembled output across all steps.
- Uses artifacts produced by multitimeframe_direction_ensemble_analysis.py.
- Analysis-only; no mutation of Stage-1 artifacts.
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
DEFAULT_OUTPUT_DIR = "prediction_analysis/multitimeframe_subset_pruning_outputs"
DEFAULT_REQUIRED_UNITS = [
    "1m/target_4class",
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]
TARGET_4 = "target_4class"
TARGET_B = "target_breakfree"


@dataclass
class EvalResult:
    objective: float
    metrics: dict[str, Any]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Greedy subset pruning over multi-timeframe candidate configs."
    )
    p.add_argument(
        "--project-root",
        type=str,
        default=str(DEFAULT_PROJECT_ROOT),
    )
    p.add_argument(
        "--ensemble-run-dir",
        type=str,
        default="",
        help=(
            "Path to multitimeframe_ensemble_outputs run dir. "
            "Default: latest run under output root."
        ),
    )
    p.add_argument(
        "--alignment-mode",
        type=str,
        default="both",
        choices=["anchor_mean", "same_period_close", "both"],
    )
    p.add_argument(
        "--variant",
        type=str,
        default="both",
        choices=["uniform", "winner_weighted", "both"],
    )
    p.add_argument(
        "--objective-truth",
        type=str,
        default="both",
        choices=["truth_a", "truth_b", "both"],
    )
    p.add_argument(
        "--min-candidates-per-unit",
        type=int,
        default=4,
    )
    p.add_argument(
        "--max-removals-total",
        type=int,
        default=48,
    )
    p.add_argument(
        "--risk-min-coverage",
        type=float,
        default=0.25,
        help="Minimum coverage required when selecting risk-guard operating point.",
    )
    p.add_argument(
        "--risk-quantile-step",
        type=float,
        default=0.1,
        help="Quantile step for risk-guard threshold grid (0<step<=0.5).",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
    )
    p.add_argument(
        "--output-tag",
        type=str,
        default="",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
    )
    return p.parse_args()


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
        if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
            return None
        return x

    path.write_text(json.dumps(_s(payload), indent=2, ensure_ascii=False), encoding="utf-8")


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
    units = sorted(data.keys())
    if sorted(DEFAULT_REQUIRED_UNITS) != units:
        raise ValueError(
            f"candidate_sets_by_unit units mismatch. expected={sorted(DEFAULT_REQUIRED_UNITS)} got={units}"
        )
    out: dict[str, dict[str, Any]] = {}
    for unit, meta in data.items():
        action_keys = [str(v) for v in meta.get("action_keys", [])]
        if len(action_keys) != 12:
            raise ValueError(f"{unit} has {len(action_keys)} candidates, expected 12")
        winner_wins = {str(k): int(v) for k, v in meta.get("winner_wins", {}).items()}
        out[unit] = {
            "action_keys": action_keys,
            "winner_wins": winner_wins,
        }
    return out


def _prepare_truths(unit_rows: pl.DataFrame) -> pl.DataFrame:
    key_cols = ["pred_batch", "anchor_15m_ts"]
    truth4 = (
        unit_rows.filter(pl.col("unit") == "15m/target_4class")
        .group_by(key_cols)
        .agg([pl.col("y_true").first().alias("y_true_4class")])
        .with_columns(
            pl.when(pl.col("y_true_4class").is_in([0, 1]))
            .then(pl.lit("DOWN"))
            .when(pl.col("y_true_4class").is_in([2, 3]))
            .then(pl.lit("UP"))
            .otherwise(pl.lit("UNKNOWN"))
            .alias("truth_a_direction")
        )
    )
    truthb = (
        unit_rows.filter(pl.col("unit") == "15m/target_breakfree")
        .group_by(key_cols)
        .agg([pl.col("y_true").first().alias("y_true_breakfree")])
        .with_columns(
            pl.when(pl.col("y_true_breakfree") == 0)
            .then(pl.lit("UP"))
            .when(pl.col("y_true_breakfree") == 1)
            .then(pl.lit("DOWN"))
            .when(pl.col("y_true_breakfree") == 2)
            .then(pl.lit("NEUTRAL"))
            .otherwise(pl.lit("UNKNOWN"))
            .alias("truth_b_direction")
        )
    )
    truth = truth4.join(
        truthb.select(["pred_batch", "anchor_15m_ts", "truth_b_direction"]),
        on=key_cols,
        how="inner",
    ).with_columns(
        pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False)
    ).sort(key_cols)
    if truth.is_empty():
        raise RuntimeError("truth table is empty")
    return truth


def _metric_from_score(df: pl.DataFrame, truth_col: str) -> dict[str, float]:
    eligible = df.filter(pl.col(truth_col).is_in(["UP", "DOWN"]))
    n = int(eligible.height)
    if n == 0:
        return {
            "eligible": 0,
            "covered": 0,
            "coverage_rate": 0.0,
            "hit_rate": 0.0,
            "balanced_recall": 0.0,
        }
    covered = eligible.filter(pl.col("pred_direction").is_in(["UP", "DOWN"]))
    covered_n = int(covered.height)
    cov = float(covered_n) / float(n)
    hit = (
        float((covered["pred_direction"] == covered[truth_col]).sum()) / float(covered_n)
        if covered_n > 0
        else 0.0
    )
    recs: list[float] = []
    for d in ("UP", "DOWN"):
        den = int((eligible[truth_col] == d).sum())
        if den > 0:
            num = int(((eligible[truth_col] == d) & (eligible["pred_direction"] == d)).sum())
            recs.append(float(num) / float(den))
    br = float(np.mean(recs)) if recs else 0.0
    return {
        "eligible": n,
        "covered": covered_n,
        "coverage_rate": cov,
        "hit_rate": hit,
        "balanced_recall": br,
    }


def _compute_grouped_unit_scores(
    *,
    anchor_scores_mode: pl.DataFrame,
    selected_by_unit: dict[str, list[str]],
    variant: str,
    winner_wins_by_unit: dict[str, dict[str, int]],
) -> pl.DataFrame:
    rows: list[dict[str, str]] = []
    for unit, keys in selected_by_unit.items():
        rows.extend({"unit": unit, "action_key": k} for k in keys)
    selected_df = pl.DataFrame(rows)
    df = (
        anchor_scores_mode.with_columns(
            pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False)
        )
        .join(selected_df, on=["unit", "action_key"], how="inner")
    )
    if df.is_empty():
        return pl.DataFrame(
            schema={
                "pred_batch": pl.Int64,
                "anchor_15m_ts": pl.Datetime("us"),
                "unit": pl.Utf8,
                "timeframe": pl.Utf8,
                "target": pl.Utf8,
                "unit_score": pl.Float64,
                "candidate_count": pl.Int64,
            }
        )

    if variant == "uniform":
        return (
            df.group_by(["pred_batch", "anchor_15m_ts", "unit", "timeframe", "target"])
            .agg(
                [
                    pl.col("dir_score_anchor").mean().alias("unit_score"),
                    pl.col("action_key").n_unique().alias("candidate_count"),
                ]
            )
            .sort(["pred_batch", "anchor_15m_ts", "unit"])
        )

    w_rows: list[dict[str, Any]] = []
    for unit, keys in selected_by_unit.items():
        wins = winner_wins_by_unit[unit]
        for k in keys:
            w_rows.append({"unit": unit, "action_key": k, "w": float(wins.get(k, 0) + 1)})
    w_df = pl.DataFrame(w_rows)
    return (
        df.join(w_df, on=["unit", "action_key"], how="left")
        .group_by(["pred_batch", "anchor_15m_ts", "unit", "timeframe", "target"])
        .agg(
            [
                (pl.col("dir_score_anchor") * pl.col("w")).sum().alias("num"),
                pl.col("w").sum().alias("den"),
                pl.col("action_key").n_unique().alias("candidate_count"),
            ]
        )
        .with_columns(
            pl.when(pl.col("den") > 0)
            .then(pl.col("num") / pl.col("den"))
            .otherwise(None)
            .alias("unit_score")
        )
        .select(
            [
                "pred_batch",
                "anchor_15m_ts",
                "unit",
                "timeframe",
                "target",
                "unit_score",
                "candidate_count",
            ]
        )
        .sort(["pred_batch", "anchor_15m_ts", "unit"])
    )


def _evaluate_subset(
    *,
    anchor_scores_mode: pl.DataFrame,
    truth_df: pl.DataFrame,
    selected_by_unit: dict[str, list[str]],
    variant: str,
    winner_wins_by_unit: dict[str, dict[str, int]],
    objective_truth: str,
) -> EvalResult:
    grouped = _compute_grouped_unit_scores(
        anchor_scores_mode=anchor_scores_mode,
        selected_by_unit=selected_by_unit,
        variant=variant,
        winner_wins_by_unit=winner_wins_by_unit,
    )
    if grouped.is_empty():
        return EvalResult(0.0, {})

    target_rows: list[pl.DataFrame] = []
    for target in (TARGET_4, TARGET_B):
        pivot = (
            grouped.filter(pl.col("target") == target)
            .pivot(
                index=["pred_batch", "anchor_15m_ts", "target"],
                on="timeframe",
                values="unit_score",
                aggregate_function="first",
            )
        )
        for tf in ("1m", "5m", "15m"):
            if tf not in pivot.columns:
                pivot = pivot.with_columns(pl.lit(None).cast(pl.Float64).alias(tf))
        pivot = pivot.with_columns(
            pl.when(
                pl.col("1m").is_not_null() & pl.col("5m").is_not_null() & pl.col("15m").is_not_null()
            )
            .then((pl.lit(15.0) * pl.col("1m") + pl.lit(3.0) * pl.col("5m") + pl.col("15m")) / pl.lit(19.0))
            .otherwise(None)
            .alias("score_target")
        )
        target_rows.append(pivot.select(["pred_batch", "anchor_15m_ts", "target", "score_target"]))
    target_scores = pl.concat(target_rows, how="diagonal_relaxed")
    t4 = target_scores.filter(pl.col("target") == TARGET_4).select(
        ["pred_batch", "anchor_15m_ts", pl.col("score_target").alias("score_4")]
    )
    tb = target_scores.filter(pl.col("target") == TARGET_B).select(
        ["pred_batch", "anchor_15m_ts", pl.col("score_target").alias("score_b")]
    )
    all_scores = (
        t4.join(tb, on=["pred_batch", "anchor_15m_ts"], how="inner")
        .with_columns(
            pl.when(pl.col("score_4").is_not_null() & pl.col("score_b").is_not_null())
            .then((pl.col("score_4") + pl.col("score_b")) * 0.5)
            .otherwise(None)
            .alias("score_all")
        )
        .with_columns(
            pl.when(pl.col("score_all") > 0)
            .then(pl.lit("UP"))
            .when(pl.col("score_all") < 0)
            .then(pl.lit("DOWN"))
            .otherwise(pl.lit("NO_SIGNAL"))
            .alias("pred_direction")
        )
    )
    eval_df = all_scores.join(
        truth_df.select(["pred_batch", "anchor_15m_ts", "truth_a_direction", "truth_b_direction"]),
        on=["pred_batch", "anchor_15m_ts"],
        how="inner",
    )
    m_a = _metric_from_score(eval_df, "truth_a_direction")
    m_b = _metric_from_score(eval_df, "truth_b_direction")
    if objective_truth == "truth_a":
        obj = m_a["hit_rate"]
    elif objective_truth == "truth_b":
        obj = m_b["hit_rate"]
    else:
        obj = 0.5 * m_a["hit_rate"] + 0.5 * m_b["hit_rate"]
    metrics = {
        "truth_a": m_a,
        "truth_b": m_b,
        "objective": float(obj),
        "anchors_scored": int(eval_df.height),
    }
    return EvalResult(float(obj), metrics)


def _build_anchor_diagnostics_for_selection(
    *,
    anchor_scores_mode: pl.DataFrame,
    truth_df: pl.DataFrame,
    selected_by_unit: dict[str, list[str]],
    variant: str,
    winner_wins_by_unit: dict[str, dict[str, int]],
) -> pl.DataFrame:
    grouped = _compute_grouped_unit_scores(
        anchor_scores_mode=anchor_scores_mode,
        selected_by_unit=selected_by_unit,
        variant=variant,
        winner_wins_by_unit=winner_wins_by_unit,
    )
    if grouped.is_empty():
        return pl.DataFrame()

    unit_pred = grouped.with_columns(
        pl.when(pl.col("unit_score") > 0)
        .then(pl.lit("UP"))
        .when(pl.col("unit_score") < 0)
        .then(pl.lit("DOWN"))
        .otherwise(pl.lit("NO_SIGNAL"))
        .alias("unit_pred_direction")
    )
    unit_pivot = unit_pred.pivot(
        index=["pred_batch", "anchor_15m_ts"],
        on="unit",
        values="unit_pred_direction",
        aggregate_function="first",
    )
    for unit in DEFAULT_REQUIRED_UNITS:
        if unit not in unit_pivot.columns:
            unit_pivot = unit_pivot.with_columns(pl.lit("NO_SIGNAL").alias(unit))

    target_rows: list[pl.DataFrame] = []
    for target in (TARGET_4, TARGET_B):
        pivot = (
            grouped.filter(pl.col("target") == target)
            .pivot(
                index=["pred_batch", "anchor_15m_ts", "target"],
                on="timeframe",
                values="unit_score",
                aggregate_function="first",
            )
        )
        for tf in ("1m", "5m", "15m"):
            if tf not in pivot.columns:
                pivot = pivot.with_columns(pl.lit(None).cast(pl.Float64).alias(tf))
        pivot = pivot.with_columns(
            pl.when(
                pl.col("1m").is_not_null()
                & pl.col("5m").is_not_null()
                & pl.col("15m").is_not_null()
            )
            .then(
                (pl.lit(15.0) * pl.col("1m") + pl.lit(3.0) * pl.col("5m") + pl.col("15m"))
                / pl.lit(19.0)
            )
            .otherwise(None)
            .alias("score_target")
        ).with_columns(
            pl.when(pl.col("score_target") > 0)
            .then(pl.lit("UP"))
            .when(pl.col("score_target") < 0)
            .then(pl.lit("DOWN"))
            .otherwise(pl.lit("NO_SIGNAL"))
            .alias("pred_dir_target")
        )
        target_rows.append(
            pivot.select(
                [
                    "pred_batch",
                    "anchor_15m_ts",
                    "target",
                    "score_target",
                    "pred_dir_target",
                ]
            )
        )
    target_scores = pl.concat(target_rows, how="diagonal_relaxed")
    t4 = target_scores.filter(pl.col("target") == TARGET_4).select(
        [
            "pred_batch",
            "anchor_15m_ts",
            pl.col("score_target").alias("score_4"),
            pl.col("pred_dir_target").alias("pred_dir_4"),
        ]
    )
    tb = target_scores.filter(pl.col("target") == TARGET_B).select(
        [
            "pred_batch",
            "anchor_15m_ts",
            pl.col("score_target").alias("score_b"),
            pl.col("pred_dir_target").alias("pred_dir_b"),
        ]
    )
    all_scores = (
        t4.join(tb, on=["pred_batch", "anchor_15m_ts"], how="inner")
        .with_columns(
            pl.when(pl.col("score_4").is_not_null() & pl.col("score_b").is_not_null())
            .then((pl.col("score_4") + pl.col("score_b")) * 0.5)
            .otherwise(None)
            .alias("score_all")
        )
        .with_columns(
            [
                pl.when(pl.col("score_all") > 0)
                .then(pl.lit("UP"))
                .when(pl.col("score_all") < 0)
                .then(pl.lit("DOWN"))
                .otherwise(pl.lit("NO_SIGNAL"))
                .alias("pred_direction"),
                pl.col("score_all").abs().alias("abs_score_all"),
                pl.when(
                    (pl.col("pred_dir_4") == "UP") & (pl.col("pred_dir_b") == "UP")
                )
                .then(pl.lit("agree_up"))
                .when(
                    (pl.col("pred_dir_4") == "DOWN") & (pl.col("pred_dir_b") == "DOWN")
                )
                .then(pl.lit("agree_down"))
                .when(
                    (pl.col("pred_dir_4") == "UP") & (pl.col("pred_dir_b") == "DOWN")
                )
                .then(pl.lit("conflict_4_up_break_down"))
                .when(
                    (pl.col("pred_dir_4") == "DOWN") & (pl.col("pred_dir_b") == "UP")
                )
                .then(pl.lit("conflict_4_down_break_up"))
                .otherwise(pl.lit("any_nosignal"))
                .alias("cross_target_conflict"),
            ]
        )
    )

    out = (
        all_scores.join(unit_pivot, on=["pred_batch", "anchor_15m_ts"], how="left")
        .join(
            truth_df.select(
                ["pred_batch", "anchor_15m_ts", "truth_a_direction", "truth_b_direction"]
            ),
            on=["pred_batch", "anchor_15m_ts"],
            how="inner",
        )
        .sort(["pred_batch", "anchor_15m_ts"])
    )

    # Pairwise agreement over 6 unit streams (UP/DOWN only).
    rows: list[dict[str, Any]] = []
    units = list(DEFAULT_REQUIRED_UNITS)
    pairs = [(i, j) for i in range(len(units)) for j in range(i + 1, len(units))]
    for r in out.iter_rows(named=True):
        dirs = [str(r.get(u, "NO_SIGNAL")) for u in units]
        pair_cov = 0
        pair_same = 0
        pair_conf = 0
        n_up = 0
        n_down = 0
        n_nosig = 0
        for d in dirs:
            if d == "UP":
                n_up += 1
            elif d == "DOWN":
                n_down += 1
            else:
                n_nosig += 1
        for i, j in pairs:
            a = dirs[i]
            b = dirs[j]
            if a in {"UP", "DOWN"} and b in {"UP", "DOWN"}:
                pair_cov += 1
                if a == b:
                    pair_same += 1
                else:
                    pair_conf += 1
        rows.append(
            {
                "pred_batch": int(r["pred_batch"]),
                "anchor_15m_ts": r["anchor_15m_ts"],
                "pairwise_covered_pairs": int(pair_cov),
                "pairwise_same_direction_rate": (float(pair_same) / float(pair_cov)) if pair_cov > 0 else None,
                "pairwise_conflict_rate": (float(pair_conf) / float(pair_cov)) if pair_cov > 0 else None,
                "all6_same_direction": bool(n_up == 6 or n_down == 6),
                "n_up": int(n_up),
                "n_down": int(n_down),
                "n_no_signal": int(n_nosig),
            }
        )
    agree_df = pl.DataFrame(rows)
    out = out.join(agree_df, on=["pred_batch", "anchor_15m_ts"], how="left").with_columns(
        [
            (
                pl.col("pred_direction").is_in(["UP", "DOWN"])
                & pl.col("truth_a_direction").is_in(["UP", "DOWN"])
                & (pl.col("pred_direction") == pl.col("truth_a_direction"))
            ).alias("hit_truth_a"),
            (
                pl.col("pred_direction").is_in(["UP", "DOWN"])
                & pl.col("truth_b_direction").is_in(["UP", "DOWN"])
                & (pl.col("pred_direction") == pl.col("truth_b_direction"))
            ).alias("hit_truth_b"),
        ]
    )
    return out


def _build_risk_guard_grid(
    *,
    anchor_diag: pl.DataFrame,
    quantile_step: float,
) -> pl.DataFrame:
    step = float(quantile_step)
    if step <= 0 or step > 0.5:
        raise ValueError(f"risk quantile step must be in (0, 0.5], got {step}")
    if anchor_diag.is_empty():
        return pl.DataFrame()

    arr_abs = anchor_diag["abs_score_all"].to_numpy()
    arr_agree = anchor_diag["pairwise_same_direction_rate"].fill_null(0.0).to_numpy()
    arr_pred = anchor_diag["pred_direction"].to_numpy()
    arr_a = anchor_diag["truth_a_direction"].to_numpy()
    arr_b = anchor_diag["truth_b_direction"].to_numpy()

    qvals = np.arange(0.0, 1.0 + 1e-9, step)
    thr_abs = sorted(set(float(np.quantile(arr_abs, q)) for q in qvals))
    thr_agree = sorted(set(float(np.quantile(arr_agree, q)) for q in qvals))

    elig_a = np.isin(arr_a, ["UP", "DOWN"])
    elig_b = np.isin(arr_b, ["UP", "DOWN"])
    pred_ok = np.isin(arr_pred, ["UP", "DOWN"])
    rows: list[dict[str, Any]] = []
    for ta in thr_abs:
        for tg in thr_agree:
            mask = pred_ok & (arr_abs >= ta) & (arr_agree >= tg)

            cov_a = float(np.sum(mask & elig_a)) / float(np.sum(elig_a)) if np.sum(elig_a) else 0.0
            cov_b = float(np.sum(mask & elig_b)) / float(np.sum(elig_b)) if np.sum(elig_b) else 0.0

            den_a = int(np.sum(mask & elig_a))
            den_b = int(np.sum(mask & elig_b))
            hit_a = (
                float(np.sum(mask & elig_a & (arr_pred == arr_a))) / float(den_a)
                if den_a > 0
                else 0.0
            )
            hit_b = (
                float(np.sum(mask & elig_b & (arr_pred == arr_b))) / float(den_b)
                if den_b > 0
                else 0.0
            )
            rows.append(
                {
                    "threshold_abs_score": float(ta),
                    "threshold_pairwise_agree": float(tg),
                    "covered_a": int(den_a),
                    "covered_b": int(den_b),
                    "coverage_a": float(cov_a),
                    "coverage_b": float(cov_b),
                    "hit_rate_a": float(hit_a),
                    "hit_rate_b": float(hit_b),
                    "hit_rate_avg": float(0.5 * (hit_a + hit_b)),
                    "coverage_avg": float(0.5 * (cov_a + cov_b)),
                }
            )
    return pl.DataFrame(rows).sort(
        ["hit_rate_avg", "coverage_avg"], descending=[True, True]
    )


def _select_best_risk_guard(
    *,
    risk_grid: pl.DataFrame,
    min_coverage: float,
) -> dict[str, Any] | None:
    if risk_grid.is_empty():
        return None
    feasible = risk_grid.filter(
        (pl.col("coverage_a") >= float(min_coverage))
        & (pl.col("coverage_b") >= float(min_coverage))
    )
    pick = feasible if not feasible.is_empty() else risk_grid
    best = pick.sort(
        ["hit_rate_avg", "coverage_avg", "threshold_abs_score", "threshold_pairwise_agree"],
        descending=[True, True, False, False],
    ).head(1)
    return best.to_dicts()[0] if best.height else None


def _state_key(selected_by_unit: dict[str, list[str]], variant: str, alignment_mode: str, objective_truth: str) -> tuple:
    return (
        alignment_mode,
        variant,
        objective_truth,
        tuple((u, tuple(sorted(v))) for u, v in sorted(selected_by_unit.items())),
    )


def _greedy_prune(
    *,
    anchor_scores_mode: pl.DataFrame,
    truth_df: pl.DataFrame,
    selected_init: dict[str, list[str]],
    winner_wins_by_unit: dict[str, dict[str, int]],
    variant: str,
    objective_truth: str,
    min_candidates_per_unit: int,
    max_removals_total: int,
    verbose: bool,
) -> tuple[dict[str, list[str]], list[dict[str, Any]], EvalResult, EvalResult]:
    cache: dict[tuple, EvalResult] = {}

    def eval_state(sel: dict[str, list[str]]) -> EvalResult:
        key = _state_key(sel, variant=variant, alignment_mode="", objective_truth=objective_truth)
        if key in cache:
            return cache[key]
        out = _evaluate_subset(
            anchor_scores_mode=anchor_scores_mode,
            truth_df=truth_df,
            selected_by_unit=sel,
            variant=variant,
            winner_wins_by_unit=winner_wins_by_unit,
            objective_truth=objective_truth,
        )
        cache[key] = out
        return out

    selected = {u: list(v) for u, v in selected_init.items()}
    full_eval = eval_state(selected)
    current = full_eval
    logs: list[dict[str, Any]] = []
    step = 0
    while step < max_removals_total:
        best_delta = 0.0
        best: tuple[str, str, EvalResult] | None = None
        for unit in sorted(selected.keys()):
            keys = sorted(selected[unit])
            if len(keys) <= min_candidates_per_unit:
                continue
            for k in keys:
                trial = {u: list(v) for u, v in selected.items()}
                trial[unit] = [x for x in trial[unit] if x != k]
                res = eval_state(trial)
                delta = float(res.objective - current.objective)
                if delta > best_delta + 1e-12:
                    best_delta = delta
                    best = (unit, k, res)
        if best is None:
            break
        unit, k, res = best
        step += 1
        selected[unit] = [x for x in selected[unit] if x != k]
        logs.append(
            {
                "step": step,
                "removed_unit": unit,
                "removed_action_key": k,
                "objective_before": current.objective,
                "objective_after": res.objective,
                "objective_delta": float(res.objective - current.objective),
                "remaining_in_unit": len(selected[unit]),
            }
        )
        current = res
        if verbose:
            print(
                f"  step={step} remove={unit}:{k} delta={logs[-1]['objective_delta']:.6f} "
                f"obj={current.objective:.6f}"
            )
    return selected, logs, full_eval, current


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    run_dir = _resolve_ensemble_run_dir(project_root, str(args.ensemble_run_dir))
    out_base = Path(args.output_dir)
    if not out_base.is_absolute():
        out_base = project_root / out_base
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = out_base / (f"{ts}_{tag}" if tag else ts)
    out_dir.mkdir(parents=True, exist_ok=False)

    print("Multi-timeframe subset pruning analysis")
    print(f"  ensemble_run_dir: {run_dir}")
    print(f"  output_dir: {out_dir}")

    candidate_sets = _load_candidate_sets(run_dir / "candidate_sets_by_unit.json")
    selected_init = {u: list(m["action_keys"]) for u, m in candidate_sets.items()}
    winner_wins_by_unit = {u: dict(m["winner_wins"]) for u, m in candidate_sets.items()}

    anchor_scores = pl.read_parquet(run_dir / "anchor_candidate_scores.parquet")
    unit_rows = pl.read_parquet(run_dir / "unit_prediction_rows_dedup.parquet")
    truth_df = _prepare_truths(unit_rows)

    alignments = (
        ["anchor_mean", "same_period_close"]
        if str(args.alignment_mode) == "both"
        else [str(args.alignment_mode)]
    )
    variants = ["uniform", "winner_weighted"] if str(args.variant) == "both" else [str(args.variant)]

    summary_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    selected_payload: dict[str, Any] = {}
    anchor_diag_by_key: dict[str, pl.DataFrame] = {}
    risk_grid_by_key: dict[str, pl.DataFrame] = {}

    for alignment_mode in alignments:
        mode_df = anchor_scores.filter(pl.col("alignment_mode") == alignment_mode)
        if mode_df.is_empty():
            continue
        for variant in variants:
            print(
                f"\nOptimize alignment={alignment_mode} variant={variant} "
                f"objective_truth={args.objective_truth}"
            )
            sel, logs, full_eval, final_eval = _greedy_prune(
                anchor_scores_mode=mode_df,
                truth_df=truth_df,
                selected_init=selected_init,
                winner_wins_by_unit=winner_wins_by_unit,
                variant=variant,
                objective_truth=str(args.objective_truth),
                min_candidates_per_unit=int(args.min_candidates_per_unit),
                max_removals_total=int(args.max_removals_total),
                verbose=bool(args.verbose),
            )
            key = f"{alignment_mode}::{variant}"
            anchor_diag = _build_anchor_diagnostics_for_selection(
                anchor_scores_mode=mode_df,
                truth_df=truth_df,
                selected_by_unit=sel,
                variant=variant,
                winner_wins_by_unit=winner_wins_by_unit,
            )
            risk_grid = _build_risk_guard_grid(
                anchor_diag=anchor_diag,
                quantile_step=float(args.risk_quantile_step),
            )
            best_guard = _select_best_risk_guard(
                risk_grid=risk_grid,
                min_coverage=float(args.risk_min_coverage),
            )

            selected_payload[key] = {
                "selected_by_unit": sel,
                "full_eval": full_eval.metrics,
                "final_eval": final_eval.metrics,
                "removed_count": len(logs),
                "risk_guard_best": best_guard,
            }
            anchor_diag_by_key[key] = anchor_diag
            risk_grid_by_key[key] = risk_grid
            summary_rows.append(
                {
                    "alignment_mode": alignment_mode,
                    "variant": variant,
                    "objective_truth": str(args.objective_truth),
                    "full_objective": float(full_eval.objective),
                    "final_objective": float(final_eval.objective),
                    "objective_gain": float(final_eval.objective - full_eval.objective),
                    "removed_count": int(len(logs)),
                    "truth_a_hit_full": float(full_eval.metrics["truth_a"]["hit_rate"]),
                    "truth_a_hit_final": float(final_eval.metrics["truth_a"]["hit_rate"]),
                    "truth_b_hit_full": float(full_eval.metrics["truth_b"]["hit_rate"]),
                    "truth_b_hit_final": float(final_eval.metrics["truth_b"]["hit_rate"]),
                    "truth_a_cov_final": float(final_eval.metrics["truth_a"]["coverage_rate"]),
                    "truth_b_cov_final": float(final_eval.metrics["truth_b"]["coverage_rate"]),
                    "risk_guard_best_hit_avg": (
                        float(best_guard["hit_rate_avg"]) if best_guard is not None else None
                    ),
                    "risk_guard_best_cov_avg": (
                        float(best_guard["coverage_avg"]) if best_guard is not None else None
                    ),
                    "risk_guard_best_thr_abs": (
                        float(best_guard["threshold_abs_score"])
                        if best_guard is not None
                        else None
                    ),
                    "risk_guard_best_thr_agree": (
                        float(best_guard["threshold_pairwise_agree"])
                        if best_guard is not None
                        else None
                    ),
                }
            )
            for r in logs:
                log_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "variant": variant,
                        **r,
                    }
                )

    summary_df = pl.DataFrame(summary_rows).sort(
        ["objective_gain", "final_objective"], descending=[True, True]
    )
    logs_df = pl.DataFrame(log_rows) if log_rows else pl.DataFrame()

    summary_path = out_dir / "subset_pruning_summary.parquet"
    logs_path = out_dir / "subset_pruning_removal_log.parquet"
    summary_csv = out_dir / "subset_pruning_summary.csv"
    logs_csv = out_dir / "subset_pruning_removal_log.csv"
    selected_json = out_dir / "subset_pruning_selected_candidates.json"
    run_summary_json = out_dir / "subset_pruning_run_summary.json"
    detail_dir = out_dir / "subset_pruning_details"
    detail_dir.mkdir(parents=True, exist_ok=True)

    summary_df.write_parquet(summary_path)
    summary_df.write_csv(summary_csv)
    if logs_df.height > 0:
        logs_df.write_parquet(logs_path)
        logs_df.write_csv(logs_csv)
    _write_json(selected_json, selected_payload)

    detail_artifacts: dict[str, dict[str, str | None]] = {}
    for key in sorted(anchor_diag_by_key.keys()):
        safe = key.replace("::", "__")
        anchor_pq = detail_dir / f"{safe}_anchor_diagnostics.parquet"
        anchor_csv = detail_dir / f"{safe}_anchor_diagnostics.csv"
        risk_pq = detail_dir / f"{safe}_risk_guard_grid.parquet"
        risk_csv = detail_dir / f"{safe}_risk_guard_grid.csv"
        anchor_diag_by_key[key].write_parquet(anchor_pq)
        anchor_diag_by_key[key].write_csv(anchor_csv)
        if risk_grid_by_key[key].height > 0:
            risk_grid_by_key[key].write_parquet(risk_pq)
            risk_grid_by_key[key].write_csv(risk_csv)
            risk_pq_str = str(risk_pq)
            risk_csv_str = str(risk_csv)
        else:
            risk_pq_str = None
            risk_csv_str = None
        detail_artifacts[key] = {
            "anchor_diagnostics_parquet": str(anchor_pq),
            "anchor_diagnostics_csv": str(anchor_csv),
            "risk_guard_grid_parquet": risk_pq_str,
            "risk_guard_grid_csv": risk_csv_str,
        }

    best = summary_df.head(1).to_dicts()
    _write_json(
        run_summary_json,
        {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "input_ensemble_run_dir": str(run_dir),
            "config": {
                "alignment_mode": str(args.alignment_mode),
                "variant": str(args.variant),
                "objective_truth": str(args.objective_truth),
                "min_candidates_per_unit": int(args.min_candidates_per_unit),
                "max_removals_total": int(args.max_removals_total),
                "risk_min_coverage": float(args.risk_min_coverage),
                "risk_quantile_step": float(args.risk_quantile_step),
            },
            "rows": {
                "summary_rows": int(summary_df.height),
                "removal_log_rows": int(logs_df.height),
            },
            "best_row": best[0] if best else None,
            "detail_artifacts_by_key": detail_artifacts,
            "artifacts": {
                "subset_pruning_summary_parquet": str(summary_path),
                "subset_pruning_summary_csv": str(summary_csv),
                "subset_pruning_removal_log_parquet": str(logs_path) if logs_df.height > 0 else None,
                "subset_pruning_removal_log_csv": str(logs_csv) if logs_df.height > 0 else None,
                "subset_pruning_selected_candidates_json": str(selected_json),
                "subset_pruning_detail_dir": str(detail_dir),
                "subset_pruning_run_summary_json": str(run_summary_json),
            },
        },
    )

    print("\nCompleted.")
    print(f"  summary rows: {summary_df.height}")
    print(f"  removal log rows: {logs_df.height}")
    if summary_df.height > 0:
        print(f"  best: {summary_df.head(1).to_dicts()[0]}")
    print(f"  saved: {run_summary_json}")


if __name__ == "__main__":
    main()

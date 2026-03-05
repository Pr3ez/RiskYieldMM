#!/usr/bin/env python3
"""Directional quality audit for Stage-1 candidates.

Builds per-candidate directional risk diagnostics, rolling stability, diversity matrix,
and two shortlists for downstream ensemble benchmarking.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

DEFAULT_PROJECT_ROOT = Path("/media/przem/linux_data/RiskYieldMM (Copy)")
DEFAULT_OUTPUT_ROOT = "prediction_analysis/candidate_directional_quality_outputs"
EXPECTED_UNITS = [
    "1m/target_4class",
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]


@dataclass(frozen=True)
class RunContext:
    project_root: Path
    run_id: str
    model_name: str
    candidate_search_run_dir: Path


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit candidate directional quality and build shortlists")
    p.add_argument("--project-root", type=str, default=str(DEFAULT_PROJECT_ROOT))
    p.add_argument(
        "--candidate-search-run-dir",
        type=str,
        default="",
        help="Path to candidate_search_v2 run dir. Default: latest under data/.../candidate_search_v2.",
    )
    p.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_ROOT)
    p.add_argument("--output-tag", type=str, default="")
    p.add_argument("--units", nargs="*", default=EXPECTED_UNITS)
    p.add_argument("--rolling-window-batches", type=int, default=100)
    p.add_argument("--high-acc-threshold", type=float, default=0.60)
    p.add_argument("--risk-core-k", type=int, default=18)
    p.add_argument("--coverage-extension-k", type=int, default=18)
    p.add_argument("--max-overlap", type=float, default=0.85)
    p.add_argument("--min-rows-per-candidate", type=int, default=5000)
    p.add_argument("--linear-issue-url", type=str, default="")
    p.add_argument("--notion-page-url", type=str, default="")
    p.add_argument("--run-command", type=str, default="")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def _normalize_units(raw_units: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_units:
        for part in str(raw).split(","):
            unit = part.strip()
            if not unit:
                continue
            if "/" not in unit:
                raise ValueError(f"Invalid unit: {unit!r}")
            if unit not in seen:
                seen.add(unit)
                out.append(unit)
    return out


def _resolve_candidate_run_dir(project_root: Path, candidate_run_dir_arg: str) -> Path:
    root = (
        project_root
        / "data"
        / "htf_backtest_results"
        / "stage1_catboost_live"
        / "catboost"
        / "candidate_search_v2"
    )
    if candidate_run_dir_arg:
        p = Path(candidate_run_dir_arg).expanduser()
        if p.exists():
            return p.resolve()
        p2 = root / candidate_run_dir_arg
        if p2.exists():
            return p2.resolve()
        raise FileNotFoundError(f"candidate run dir not found: {candidate_run_dir_arg}")
    runs = sorted([p for p in root.glob("run_*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs under {root}")
    return runs[-1].resolve()


def _load_run_context(project_root: Path, run_dir: Path) -> RunContext:
    summary_path = run_dir / "candidate_search_run_summary_v2.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing run summary: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run_id = str(summary.get("run_id", "stage1_catboost_live"))
    model_name = str(summary.get("model_name", "catboost"))
    return RunContext(
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        candidate_search_run_dir=run_dir,
    )


def _load_candidate12_by_unit(run_dir: Path, units: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for unit in units:
        tf, target = unit.split("/", 1)
        p = run_dir / tf / target / "candidate12_v2.parquet"
        if not p.exists():
            raise FileNotFoundError(f"Missing candidate12 file for {unit}: {p}")
        df = pl.read_parquet(p).select("action_key").drop_nulls().unique().sort("action_key")
        keys = [str(v) for v in df["action_key"].to_list()]
        if len(keys) != 12:
            raise ValueError(f"{unit} candidate12 size must be 12, got {len(keys)}")
        out[unit] = keys
    if set(units) != set(EXPECTED_UNITS):
        missing = sorted(set(EXPECTED_UNITS) - set(units))
        if missing:
            raise ValueError(f"Missing required units: {missing}")
    return out


def _unit_stage1_pred_glob(ctx: RunContext, unit: str) -> str:
    tf, target = unit.split("/", 1)
    return str(
        ctx.project_root
        / "data"
        / "htf_backtest_results"
        / ctx.run_id
        / ctx.model_name
        / tf
        / target
        / "batch_*"
        / "stage1"
        / "stage1_pred_batch_predictions.parquet"
    )


def _row_level_directional_metrics_for_unit(ctx: RunContext, unit: str) -> pl.DataFrame:
    tf, target = unit.split("/", 1)
    glob_path = _unit_stage1_pred_glob(ctx, unit)

    base = (
        pl.scan_parquet(glob_path, missing_columns="insert")
        .filter(pl.col("scope") == "pred_batch")
        .with_columns(
            [
                pl.col("batch_id").cast(pl.Int64).alias("pred_batch"),
                pl.col("action_key").cast(pl.Utf8),
                pl.col("y_true").cast(pl.Int64),
                pl.col("y_pred").cast(pl.Int64),
                pl.col("prob_class_0").cast(pl.Float64),
                pl.col("prob_class_1").cast(pl.Float64),
                pl.col("prob_class_2").cast(pl.Float64),
            ]
        )
    )

    if target == "target_breakfree":
        y_true_dir = (
            pl.when(pl.col("y_true") == 0)
            .then(pl.lit("UP"))
            .when(pl.col("y_true") == 1)
            .then(pl.lit("DOWN"))
            .otherwise(pl.lit("HOLD"))
        )
        y_pred_dir = (
            pl.when(pl.col("y_pred") == 0)
            .then(pl.lit("UP"))
            .when(pl.col("y_pred") == 1)
            .then(pl.lit("DOWN"))
            .otherwise(pl.lit("HOLD"))
        )

        p_true = (
            pl.when(pl.col("y_true") == 0)
            .then(pl.col("prob_class_0"))
            .when(pl.col("y_true") == 1)
            .then(pl.col("prob_class_1"))
            .otherwise(pl.col("prob_class_2"))
        )

        brier = (
            (pl.col("prob_class_0") - (pl.col("y_true") == 0).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_1") - (pl.col("y_true") == 1).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_2") - (pl.col("y_true") == 2).cast(pl.Float64)).pow(2)
        )

        work = base.with_columns(
            [
                pl.lit(unit).alias("unit"),
                y_true_dir.alias("truth_dir"),
                y_pred_dir.alias("pred_dir"),
                p_true.clip(1e-12, 1.0).log().mul(-1.0).alias("logloss_row"),
                brier.alias("brier_row"),
            ]
        ).with_columns(
            [
                (
                    ((pl.col("y_true") == 0) & (pl.col("y_pred") == 1))
                    | ((pl.col("y_true") == 1) & (pl.col("y_pred") == 0))
                )
                .cast(pl.Int64)
                .alias("opposite_row"),
                (
                    ((pl.col("y_true") == 2) & (pl.col("y_pred").is_in([0, 1])))
                    | ((pl.col("y_true").is_in([0, 1])) & (pl.col("y_pred") == 2))
                )
                .cast(pl.Int64)
                .alias("hold_side_row"),
                (pl.col("y_pred").is_in([0, 1])).cast(pl.Int64).alias("active_pred_row"),
                (
                    (pl.col("y_true").is_in([0, 1]))
                    & (pl.col("y_pred").is_in([0, 1]))
                    & (pl.col("y_true") == pl.col("y_pred"))
                )
                .cast(pl.Int64)
                .alias("directional_correct_row"),
                (pl.col("y_true") == pl.col("y_pred")).cast(pl.Int64).alias("exact_correct_row"),
                (pl.col("pred_dir") == "UP").cast(pl.Int64).alias("pred_up_row"),
                (pl.col("pred_dir") == "DOWN").cast(pl.Int64).alias("pred_down_row"),
                (pl.col("pred_dir") == "HOLD").cast(pl.Int64).alias("pred_hold_row"),
            ]
        )
    elif target == "target_4class":
        base_4 = base.with_columns(pl.col("prob_class_3").cast(pl.Float64))

        y_true_dir = (
            pl.when(pl.col("y_true").is_in([2, 3]))
            .then(pl.lit("UP"))
            .otherwise(pl.lit("DOWN"))
        )
        y_pred_dir = (
            pl.when(pl.col("y_pred").is_in([2, 3]))
            .then(pl.lit("UP"))
            .otherwise(pl.lit("DOWN"))
        )

        p_true = (
            pl.when(pl.col("y_true") == 0)
            .then(pl.col("prob_class_0"))
            .when(pl.col("y_true") == 1)
            .then(pl.col("prob_class_1"))
            .when(pl.col("y_true") == 2)
            .then(pl.col("prob_class_2"))
            .otherwise(pl.col("prob_class_3"))
        )

        brier = (
            (pl.col("prob_class_0") - (pl.col("y_true") == 0).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_1") - (pl.col("y_true") == 1).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_2") - (pl.col("y_true") == 2).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_3") - (pl.col("y_true") == 3).cast(pl.Float64)).pow(2)
        )

        work = base_4.with_columns(
            [
                pl.lit(unit).alias("unit"),
                y_true_dir.alias("truth_dir"),
                y_pred_dir.alias("pred_dir"),
                p_true.clip(1e-12, 1.0).log().mul(-1.0).alias("logloss_row"),
                brier.alias("brier_row"),
            ]
        ).with_columns(
            [
                (pl.col("truth_dir") != pl.col("pred_dir")).cast(pl.Int64).alias("opposite_row"),
                pl.lit(0).cast(pl.Int64).alias("hold_side_row"),
                pl.lit(1).cast(pl.Int64).alias("active_pred_row"),
                (pl.col("truth_dir") == pl.col("pred_dir")).cast(pl.Int64).alias(
                    "directional_correct_row"
                ),
                (pl.col("y_true") == pl.col("y_pred")).cast(pl.Int64).alias("exact_correct_row"),
                (pl.col("pred_dir") == "UP").cast(pl.Int64).alias("pred_up_row"),
                (pl.col("pred_dir") == "DOWN").cast(pl.Int64).alias("pred_down_row"),
                pl.lit(0).cast(pl.Int64).alias("pred_hold_row"),
            ]
        )
    else:
        raise ValueError(f"Unsupported target: {target}")

    agg = (
        work.group_by("action_key")
        .agg(
            [
                pl.first("unit").alias("unit"),
                pl.len().alias("rows_total"),
                pl.col("pred_batch").n_unique().alias("batches_seen"),
                pl.mean("exact_correct_row").alias("accuracy_exact"),
                pl.mean("directional_correct_row").alias("directional_active_accuracy"),
                pl.mean("active_pred_row").alias("directional_active_coverage"),
                pl.mean("opposite_row").alias("opposite_direction_rate"),
                pl.mean("hold_side_row").alias("hold_side_cross_error_rate"),
                pl.mean("logloss_row").alias("logloss_mean"),
                pl.mean("brier_row").alias("brier_mean"),
                pl.mean("pred_up_row").alias("pred_up_share"),
                pl.mean("pred_down_row").alias("pred_down_share"),
                pl.mean("pred_hold_row").alias("pred_hold_share"),
            ]
        )
        .with_columns(
            [
                (
                    pl.col("opposite_direction_rate")
                    + pl.col("hold_side_cross_error_rate")
                    + 0.20 * pl.col("logloss_mean")
                    + 0.20 * pl.col("brier_mean")
                    - 0.10 * pl.col("directional_active_accuracy")
                ).alias("risk_score"),
                (
                    pl.col("directional_active_coverage") * pl.col("directional_active_accuracy")
                    - 0.75 * pl.col("opposite_direction_rate")
                    - 0.50 * pl.col("hold_side_cross_error_rate")
                ).alias("coverage_gain_score"),
            ]
        )
        .sort("risk_score")
        .collect()
    )
    return agg


def _build_combo_metrics_from_stage1(ctx: RunContext, unit: str) -> pl.DataFrame:
    tf, target = unit.split("/", 1)
    glob_path = _unit_stage1_pred_glob(ctx, unit)
    base = (
        pl.scan_parquet(glob_path, missing_columns="insert")
        .filter(pl.col("scope") == "pred_batch")
        .with_columns(
            [
                pl.col("batch_id").cast(pl.Int64).alias("pred_batch"),
                pl.col("action_key").cast(pl.Utf8),
                pl.col("y_true").cast(pl.Int64),
                pl.col("y_pred").cast(pl.Int64),
                pl.col("prob_class_0").cast(pl.Float64),
                pl.col("prob_class_1").cast(pl.Float64),
                pl.col("prob_class_2").cast(pl.Float64),
            ]
        )
    )

    if target == "target_breakfree":
        p_true = (
            pl.when(pl.col("y_true") == 0)
            .then(pl.col("prob_class_0"))
            .when(pl.col("y_true") == 1)
            .then(pl.col("prob_class_1"))
            .otherwise(pl.col("prob_class_2"))
        )
        cross = (
            ((pl.col("y_true") == 0) & (pl.col("y_pred") == 1))
            | ((pl.col("y_true") == 1) & (pl.col("y_pred") == 0))
        ).cast(pl.Float64)
        brier = (
            (pl.col("prob_class_0") - (pl.col("y_true") == 0).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_1") - (pl.col("y_true") == 1).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_2") - (pl.col("y_true") == 2).cast(pl.Float64)).pow(2)
        )
    else:
        base_4 = base.with_columns(pl.col("prob_class_3").cast(pl.Float64))
        p_true = (
            pl.when(pl.col("y_true") == 0)
            .then(pl.col("prob_class_0"))
            .when(pl.col("y_true") == 1)
            .then(pl.col("prob_class_1"))
            .when(pl.col("y_true") == 2)
            .then(pl.col("prob_class_2"))
            .otherwise(pl.col("prob_class_3"))
        )
        cross = (
            (pl.col("y_true").is_in([2, 3])) != (pl.col("y_pred").is_in([2, 3]))
        ).cast(pl.Float64)
        brier = (
            (pl.col("prob_class_0") - (pl.col("y_true") == 0).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_1") - (pl.col("y_true") == 1).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_2") - (pl.col("y_true") == 2).cast(pl.Float64)).pow(2)
            + (pl.col("prob_class_3") - (pl.col("y_true") == 3).cast(pl.Float64)).pow(2)
        )

    metrics = (
        (base if target == "target_breakfree" else base_4).with_columns(
            [
                (pl.col("y_true") == pl.col("y_pred")).cast(pl.Float64).alias("acc_row"),
                cross.alias("cross_row"),
                p_true.clip(1e-12, 1.0).log().mul(-1.0).alias("logloss_row"),
                brier.alias("brier_row"),
            ]
        )
        .group_by(["pred_batch", "action_key"])
        .agg(
            [
                pl.mean("acc_row").alias("accuracy"),
                pl.mean("cross_row").alias("cross_direction_error"),
                pl.mean("logloss_row").alias("logloss"),
                pl.mean("brier_row").alias("brier_score"),
            ]
        )
        .sort(["pred_batch", "action_key"])
        .collect()
    )
    return metrics


def _load_combo_stats(run_dir: Path, unit: str, metrics_df: pl.DataFrame) -> pl.DataFrame:
    tf, target = unit.split("/", 1)
    p = run_dir / tf / target / "combo_stats_all_tested_v2.parquet"
    if p.exists():
        return pl.read_parquet(p)
    # Fallback from per-batch metrics when combo_stats artifact is unavailable.
    return (
        metrics_df.group_by("action_key")
        .agg(
            [
                pl.len().alias("steps_seen"),
                pl.mean("accuracy").alias("all_steps_accuracy_mean"),
                pl.mean("cross_direction_error").alias("all_steps_cross_direction_error_mean"),
                pl.mean("logloss").alias("all_steps_logloss_mean"),
                pl.mean("brier_score").alias("all_steps_brier_score_mean"),
            ]
        )
        .sort("action_key")
    )


def _load_combo_metrics(run_dir: Path, unit: str, ctx: RunContext) -> pl.DataFrame:
    tf, target = unit.split("/", 1)
    p = run_dir / tf / target / "combo_metrics_all_tested_v2.parquet"
    if p.exists():
        return pl.read_parquet(p)
    return _build_combo_metrics_from_stage1(ctx, unit)


def _rolling_stability_for_unit(
    metrics_df: pl.DataFrame,
    unit: str,
    window_batches: int,
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    cols_needed = ["pred_batch", "action_key", "accuracy", "cross_direction_error", "logloss", "brier_score"]
    for col in cols_needed:
        if col not in metrics_df.columns:
            raise ValueError(f"{unit} missing column in combo_metrics: {col}")

    actions = sorted({str(v) for v in metrics_df["action_key"].to_list() if v is not None})
    for action in actions:
        sub = (
            metrics_df.filter(pl.col("action_key") == action)
            .select(cols_needed)
            .sort("pred_batch")
        )
        if sub.is_empty():
            continue
        n = int(sub.height)
        w = min(int(window_batches), n)

        first = sub.head(w)
        last = sub.tail(w)

        acc_first = float(first["accuracy"].mean())
        acc_last = float(last["accuracy"].mean())
        opp_first = float(first["cross_direction_error"].mean())
        opp_last = float(last["cross_direction_error"].mean())
        log_first = float(first["logloss"].mean())
        log_last = float(last["logloss"].mean())
        brier_first = float(first["brier_score"].mean())
        brier_last = float(last["brier_score"].mean())

        rows.append(
            {
                "unit": unit,
                "action_key": action,
                "steps_seen": n,
                "window_batches": int(w),
                "pred_batch_first": int(sub["pred_batch"][0]),
                "pred_batch_last": int(sub["pred_batch"][n - 1]),
                "accuracy_first_window": acc_first,
                "accuracy_last_window": acc_last,
                "accuracy_delta_last_minus_first": float(acc_last - acc_first),
                "opposite_proxy_first_window": opp_first,
                "opposite_proxy_last_window": opp_last,
                "opposite_proxy_delta_last_minus_first": float(opp_last - opp_first),
                "logloss_first_window": log_first,
                "logloss_last_window": log_last,
                "logloss_delta_last_minus_first": float(log_last - log_first),
                "brier_first_window": brier_first,
                "brier_last_window": brier_last,
                "brier_delta_last_minus_first": float(brier_last - brier_first),
            }
        )

    if not rows:
        return pl.DataFrame(
            schema={
                "unit": pl.Utf8,
                "action_key": pl.Utf8,
                "steps_seen": pl.Int64,
                "window_batches": pl.Int64,
                "pred_batch_first": pl.Int64,
                "pred_batch_last": pl.Int64,
                "accuracy_first_window": pl.Float64,
                "accuracy_last_window": pl.Float64,
                "accuracy_delta_last_minus_first": pl.Float64,
                "opposite_proxy_first_window": pl.Float64,
                "opposite_proxy_last_window": pl.Float64,
                "opposite_proxy_delta_last_minus_first": pl.Float64,
                "logloss_first_window": pl.Float64,
                "logloss_last_window": pl.Float64,
                "logloss_delta_last_minus_first": pl.Float64,
                "brier_first_window": pl.Float64,
                "brier_last_window": pl.Float64,
                "brier_delta_last_minus_first": pl.Float64,
            }
        )
    return pl.DataFrame(rows).sort(["unit", "accuracy_delta_last_minus_first", "action_key"])


def _spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 3 or y.size < 3:
        return 0.0
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return 0.0

    def _rank(a: np.ndarray) -> np.ndarray:
        order = np.argsort(a, kind="mergesort")
        ranks = np.empty_like(order, dtype=np.float64)
        ranks[order] = np.arange(len(a), dtype=np.float64)
        return ranks

    rx = _rank(x)
    ry = _rank(y)
    corr = np.corrcoef(rx, ry)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)


def _diversity_matrix_for_unit(
    metrics_df: pl.DataFrame,
    unit: str,
    candidate12_keys: list[str],
    high_acc_threshold: float,
) -> pl.DataFrame:
    base = (
        metrics_df.filter(pl.col("action_key").is_in(candidate12_keys))
        .select(["pred_batch", "action_key", "accuracy"])
        .sort(["action_key", "pred_batch"])
    )
    if base.is_empty():
        return pl.DataFrame(
            schema={
                "unit": pl.Utf8,
                "action_key_a": pl.Utf8,
                "action_key_b": pl.Utf8,
                "jaccard_high_acc": pl.Float64,
                "spearman_accuracy": pl.Float64,
                "diversity_score": pl.Float64,
            }
        )

    actions = sorted(candidate12_keys)
    by_action: dict[str, pl.DataFrame] = {
        a: base.filter(pl.col("action_key") == a).sort("pred_batch") for a in actions
    }

    high_sets: dict[str, set[int]] = {}
    for a, df in by_action.items():
        s = {
            int(v)
            for v in df.filter(pl.col("accuracy") >= float(high_acc_threshold))["pred_batch"].to_list()
        }
        high_sets[a] = s

    rows: list[dict[str, Any]] = []
    for i, a in enumerate(actions):
        for b in actions[i + 1 :]:
            da = by_action[a]
            db = by_action[b]
            inter = da.join(db, on="pred_batch", how="inner", suffix="_b")

            if inter.is_empty():
                corr = 0.0
            else:
                xa = inter["accuracy"].to_numpy().astype(np.float64)
                yb = inter["accuracy_b"].to_numpy().astype(np.float64)
                corr = _spearman_corr(xa, yb)

            sa = high_sets[a]
            sb = high_sets[b]
            union = sa | sb
            inter_set = sa & sb
            jaccard = float(len(inter_set) / len(union)) if union else 0.0
            corr_dissim = float((1.0 - corr) / 2.0)
            diversity = float(0.5 * (1.0 - jaccard) + 0.5 * corr_dissim)

            rows.append(
                {
                    "unit": unit,
                    "action_key_a": a,
                    "action_key_b": b,
                    "jaccard_high_acc": jaccard,
                    "spearman_accuracy": corr,
                    "diversity_score": diversity,
                }
            )

    return pl.DataFrame(rows).sort(["unit", "diversity_score"], descending=[False, True])


def _pair_overlap(
    diversity_df: pl.DataFrame,
    unit: str,
    a: str,
    b: str,
) -> float:
    if a == b:
        return 1.0
    if diversity_df.is_empty():
        return 0.0

    sub = diversity_df.filter(
        (pl.col("unit") == unit)
        & (
            ((pl.col("action_key_a") == a) & (pl.col("action_key_b") == b))
            | ((pl.col("action_key_a") == b) & (pl.col("action_key_b") == a))
        )
    )
    if sub.is_empty():
        return 0.0
    return float(sub["jaccard_high_acc"][0])


def _build_shortlists(
    risk_df: pl.DataFrame,
    diversity_df: pl.DataFrame,
    risk_core_k: int,
    coverage_extension_k: int,
    max_overlap: float,
    min_rows: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = risk_df.filter(pl.col("rows_total") >= int(min_rows)).sort(
        ["risk_score", "opposite_direction_rate", "hold_side_cross_error_rate", "logloss_mean"]
    )

    risk_core = base.head(int(risk_core_k)).to_dicts()

    picked = {(str(r["unit"]), str(r["action_key"])) for r in risk_core}
    extension_rows: list[dict[str, Any]] = []

    remaining = (
        base.filter(
            ~pl.struct(["unit", "action_key"]).is_in(
                [
                    {"unit": u, "action_key": a}
                    for u, a in sorted(picked)
                ]
            )
        )
        .sort(["coverage_gain_score", "directional_active_coverage"], descending=True)
        .to_dicts()
    )

    for row in remaining:
        unit = str(row["unit"])
        action = str(row["action_key"])
        overlaps = [
            _pair_overlap(diversity_df, unit, action, a)
            for (u, a) in picked
            if u == unit
        ]
        max_seen = max(overlaps) if overlaps else 0.0
        if max_seen > float(max_overlap):
            continue
        extension_rows.append(row)
        picked.add((unit, action))
        if len(extension_rows) >= int(coverage_extension_k):
            break

    return risk_core, extension_rows


def _git_commit(project_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def _write_tracking_context(
    out_dir: Path,
    *,
    project_root: Path,
    run_command: str,
    linear_issue_url: str,
    notion_page_url: str,
    candidate_search_run_dir: Path,
) -> Path:
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(project_root),
        "git_commit": _git_commit(project_root),
        "run_command": str(run_command),
        "linear_issue_url": str(linear_issue_url),
        "notion_page_url": str(notion_page_url),
        "candidate_search_run_dir": str(candidate_search_run_dir),
    }
    path = out_dir / "tracking_context.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    raise TypeError(f"Unsupported JSON type: {type(value)!r}")


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    units = _normalize_units(list(args.units))
    if set(units) != set(EXPECTED_UNITS):
        missing = sorted(set(EXPECTED_UNITS) - set(units))
        extra = sorted(set(units) - set(EXPECTED_UNITS))
        raise ValueError(f"Units must match required 6. missing={missing} extra={extra}")

    if int(args.rolling_window_batches) <= 0:
        raise ValueError("--rolling-window-batches must be > 0")
    if int(args.risk_core_k) <= 0 or int(args.coverage_extension_k) <= 0:
        raise ValueError("--risk-core-k and --coverage-extension-k must be > 0")
    if not (0.0 <= float(args.max_overlap) <= 1.0):
        raise ValueError("--max-overlap must be in [0,1]")

    run_dir = _resolve_candidate_run_dir(project_root, str(args.candidate_search_run_dir))
    ctx = _load_run_context(project_root, run_dir)
    candidate12 = _load_candidate12_by_unit(run_dir, units)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = project_root / str(args.output_dir) / (f"{stamp}_{tag}" if tag else stamp)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Candidate directional quality audit")
    print(f"  candidate_search_run_dir: {run_dir}")
    print(f"  output_dir: {out_dir}")

    risk_tables: list[pl.DataFrame] = []
    rolling_tables: list[pl.DataFrame] = []
    diversity_tables: list[pl.DataFrame] = []

    for unit in units:
        if bool(args.verbose):
            print(f"\n[{unit}] computing row-level directional risk metrics...")
        risk_df = _row_level_directional_metrics_for_unit(ctx, unit)

        metrics_df = _load_combo_metrics(run_dir, unit, ctx)
        stats_df = _load_combo_stats(run_dir, unit, metrics_df)
        # Attach winner-share and all-step aggregate stats when available.
        join_cols = [
            "action_key",
            "winner_share",
            "winner_wins",
            "all_steps_accuracy_mean",
            "all_steps_cross_direction_error_mean",
            "all_steps_logloss_mean",
            "all_steps_brier_score_mean",
        ]
        join_cols = [c for c in join_cols if c in stats_df.columns]
        if "action_key" in join_cols:
            risk_df = risk_df.join(stats_df.select(join_cols), on="action_key", how="left")
        risk_tables.append(risk_df)

        rolling_df = _rolling_stability_for_unit(
            metrics_df=metrics_df,
            unit=unit,
            window_batches=int(args.rolling_window_batches),
        )
        rolling_tables.append(rolling_df)

        diversity_df = _diversity_matrix_for_unit(
            metrics_df=metrics_df,
            unit=unit,
            candidate12_keys=candidate12[unit],
            high_acc_threshold=float(args.high_acc_threshold),
        )
        diversity_tables.append(diversity_df)

    risk_all = pl.concat(risk_tables, how="vertical").sort(
        ["risk_score", "unit", "action_key"]
    )
    rolling_all = pl.concat(rolling_tables, how="vertical").sort(
        ["unit", "accuracy_delta_last_minus_first", "action_key"]
    )
    diversity_all = pl.concat(diversity_tables, how="vertical").sort(
        ["unit", "diversity_score"], descending=[False, True]
    )

    risk_core, coverage_extension = _build_shortlists(
        risk_df=risk_all,
        diversity_df=diversity_all,
        risk_core_k=int(args.risk_core_k),
        coverage_extension_k=int(args.coverage_extension_k),
        max_overlap=float(args.max_overlap),
        min_rows=int(args.min_rows_per_candidate),
    )

    path_risk = out_dir / "per_unit_directional_risk_table.parquet"
    path_risk_csv = out_dir / "per_unit_directional_risk_table.csv"
    risk_all.write_parquet(path_risk)
    risk_all.write_csv(path_risk_csv)

    path_roll = out_dir / "rolling_stability_report.parquet"
    path_roll_csv = out_dir / "rolling_stability_report.csv"
    rolling_all.write_parquet(path_roll)
    rolling_all.write_csv(path_roll_csv)

    path_div = out_dir / "diversity_matrix.parquet"
    path_div_csv = out_dir / "diversity_matrix.csv"
    diversity_all.write_parquet(path_div)
    diversity_all.write_csv(path_div_csv)

    path_core = out_dir / "risk_core_shortlist.json"
    path_ext = out_dir / "coverage_extension_shortlist.json"
    path_core.write_text(json.dumps({"candidates": risk_core}, indent=2, default=_json_default), encoding="utf-8")
    path_ext.write_text(
        json.dumps({"candidates": coverage_extension}, indent=2, default=_json_default),
        encoding="utf-8",
    )

    tracking_path = _write_tracking_context(
        out_dir,
        project_root=project_root,
        run_command=(str(args.run_command).strip() or " ".join(sys.argv)),
        linear_issue_url=str(args.linear_issue_url),
        notion_page_url=str(args.notion_page_url),
        candidate_search_run_dir=run_dir,
    )

    summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "project_root": str(project_root),
            "candidate_search_run_dir": str(run_dir),
            "units": units,
            "rolling_window_batches": int(args.rolling_window_batches),
            "high_acc_threshold": float(args.high_acc_threshold),
            "risk_core_k": int(args.risk_core_k),
            "coverage_extension_k": int(args.coverage_extension_k),
            "max_overlap": float(args.max_overlap),
            "min_rows_per_candidate": int(args.min_rows_per_candidate),
        },
        "counts": {
            "risk_rows": int(risk_all.height),
            "rolling_rows": int(rolling_all.height),
            "diversity_rows": int(diversity_all.height),
            "risk_core_count": int(len(risk_core)),
            "coverage_extension_count": int(len(coverage_extension)),
        },
        "artifacts": {
            "per_unit_directional_risk_table_parquet": str(path_risk),
            "per_unit_directional_risk_table_csv": str(path_risk_csv),
            "rolling_stability_report_parquet": str(path_roll),
            "rolling_stability_report_csv": str(path_roll_csv),
            "diversity_matrix_parquet": str(path_div),
            "diversity_matrix_csv": str(path_div_csv),
            "risk_core_shortlist_json": str(path_core),
            "coverage_extension_shortlist_json": str(path_ext),
            "tracking_context_json": str(tracking_path),
        },
    }
    path_summary = out_dir / "summary.json"
    path_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nCompleted.")
    print(f"  summary: {path_summary}")
    print(f"  risk_core candidates: {len(risk_core)}")
    print(f"  coverage_extension candidates: {len(coverage_extension)}")


if __name__ == "__main__":
    main()

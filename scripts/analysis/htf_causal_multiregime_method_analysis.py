#!/usr/bin/env python3
"""Run no-lookahead ensemble-method analysis across six HTF regime/family roots.

This script uses the latest Stage-1 walk-forward outputs as the source of truth.
It rebuilds the minimal winner/combo-match artifacts needed by the older
winner12 analysis helpers, but only for a fixed combo universe that is already
present on every step of the new multiregime runs.

Important scope notes:
- Includes only methods that can be evaluated without lookahead under the
  current six-root setup.
- Excludes hindsight/oracle methods and methods whose current implementation
  uses full-run future winner transitions for live selection.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRED_ANALYSIS_DIR = PROJECT_ROOT / "prediction_analysis"
if str(PRED_ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(PRED_ANALYSIS_DIR))

from winner12_discounted_model_averaging_analysis import (  # type: ignore
    run_analysis as run_dma_analysis,
)
from winner12_diversity_subset_analysis import run_analysis as run_diversity_analysis  # type: ignore
from winner12_hedge_ensemble_analysis import run_analysis as run_hedge_analysis  # type: ignore
from winner12_per_class_specialist_analysis import run_analysis as run_classspec_analysis  # type: ignore
from winner12_probability_analysis import run_analysis as run_probability_analysis  # type: ignore
from winner12_regime_router_analysis import run_analysis as run_router_analysis  # type: ignore
from winner12_stacking_meta_analysis import run_analysis as run_stacking_analysis  # type: ignore


ROOTS: dict[str, dict[str, str]] = {
    "8h/B": {
        "run_id": "stage1_catboost_8h_b_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_8h_b_live/catboost/1m/target_4class",
    },
    "8h/C": {
        "run_id": "stage1_catboost_8h_c_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_8h_c_live/catboost/1m/target_4class",
    },
    "24h/B": {
        "run_id": "stage1_catboost_24h_b_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_24h_b_live/catboost/1m/target_4class",
    },
    "24h/C": {
        "run_id": "stage1_catboost_24h_c_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_24h_c_live/catboost/1m/target_4class",
    },
    "7d/B": {
        "run_id": "stage1_catboost_7d_b_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_7d_b_live/catboost/1m/target_4class",
    },
    "7d/C": {
        "run_id": "stage1_catboost_7d_c_live",
        "unit_dir": "data/htf_backtest_results/stage1_catboost_7d_c_live/catboost/1m/target_4class",
    },
}

SAFE_METHOD_NOTES = {
    "uniform_argmax_class": "Safe direct baseline over current-step combo probabilities.",
    "uniform_direction_sum": "Safe direct direction baseline from summed current-step class probabilities.",
    "all_agree_class": "Safe abstention baseline; predicts only when all combos agree on class.",
    "all_agree_direction": "Safe abstention baseline; predicts only when all combos agree on direction.",
    "hedge_online": "Safe online expert-weight update; uses realized batch loss only after prediction.",
    "diversity_subset": "Safe walk-forward subset selector using past-only accuracy/disagreement.",
    "per_class_specialist": "Safe walk-forward specialist weighting using past-only class recalls.",
    "regime_router": "Safe walk-forward router using past-only row-level consensus features.",
    "stacking_meta": "Safe walk-forward logistic meta-learner over combo probabilities.",
    "discounted_model_averaging": "Safe online discounted model averaging over combo probabilities.",
}

EXCLUDED_METHODS = {
    "winner_combo_class": "Oracle hindsight winner selected with same-step realized truth.",
    "weighted_majority_class": "Historical implementation used full-run capability weights, not causal per-step weights.",
    "weighted_majority_direction": "Historical implementation used full-run capability weights, not causal per-step weights.",
    "dynamic_topk": "Current heuristic posterior implementation uses full-run winner transitions/priors.",
}


@dataclass(frozen=True)
class MethodArtifact:
    method_family: str
    config_id: str
    row_path: Path
    prediction_type: str
    prediction_col: str
    extra: dict[str, Any]


def _argmax_expr(prefix: str, out_col: str) -> pl.Expr:
    return (
        pl.when(pl.col(f"{prefix}0") >= pl.max_horizontal([f"{prefix}0", f"{prefix}1", f"{prefix}2", f"{prefix}3"]))
        .then(0)
        .when(pl.col(f"{prefix}1") >= pl.max_horizontal([f"{prefix}0", f"{prefix}1", f"{prefix}2", f"{prefix}3"]))
        .then(1)
        .when(pl.col(f"{prefix}2") >= pl.max_horizontal([f"{prefix}0", f"{prefix}1", f"{prefix}2", f"{prefix}3"]))
        .then(2)
        .otherwise(3)
        .alias(out_col)
    )


def _timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _build_winners_artifact(unit_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    action_sets: set[tuple[str, ...]] = set()
    for batch_dir in sorted([p for p in unit_dir.glob("batch_*") if p.is_dir()]):
        summary_path = batch_dir / "stage1" / "stage1_step_summary.json"
        combo_idx_path = batch_dir / "stage1" / "stage1_combo_index.parquet"
        if not summary_path.exists() or not combo_idx_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        pred_batch = int(summary.get("pred_batch") or batch_dir.name.split("_")[1])
        winner_combo_key = str(summary["winner_combo_key"])
        rows.append(
            {
                "pred_batch": pred_batch,
                "winner_combo_key": winner_combo_key,
                "winner_accuracy": float(summary["winner_accuracy"]),
                "winner_macro_f1": float(summary.get("winner_macro_f1") or 0.0),
                "winner_cross_direction_error": float(
                    summary.get("winner_cross_direction_error") or 0.0
                ),
            }
        )
        combo_idx = pl.read_parquet(combo_idx_path)
        action_sets.add(tuple(sorted(set(combo_idx["action_key"].to_list()))))

    if not rows:
        raise ValueError(f"No Stage-1 step summaries found under {unit_dir}")

    winners_df = pl.DataFrame(rows).sort("pred_batch")
    winners_parquet = unit_dir / "winners_all_steps.parquet"
    winners_csv = unit_dir / "winners_all_steps.csv"
    winners_df.write_parquet(winners_parquet)
    winners_df.write_csv(winners_csv)

    counts = (
        winners_df.group_by("winner_combo_key")
        .len()
        .sort(["len", "winner_combo_key"], descending=[True, False])
    )
    summary = {
        "rows": int(winners_df.height),
        "winner_combo_count": int(counts.height),
        "winner_combos": counts["winner_combo_key"].to_list(),
        "winner_combo_counts": counts.to_dicts(),
        "fixed_action_set_count": int(len(action_sets)),
        "winners_all_steps_parquet": str(winners_parquet),
        "winners_all_steps_csv": str(winners_csv),
    }
    (unit_dir / "winners_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def _build_combo_match_pred_rows(unit_dir: Path, combo_match_dir: Path) -> Path:
    frames: list[pl.DataFrame] = []
    for batch_dir in sorted([p for p in unit_dir.glob("batch_*") if p.is_dir()]):
        pred_path = batch_dir / "stage1" / "stage1_pred_batch_predictions.parquet"
        if not pred_path.exists():
            continue
        pred_batch = int(batch_dir.name.split("_")[1])
        pred_df = pl.read_parquet(pred_path)
        if "scope" in pred_df.columns:
            pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
        if pred_df.is_empty():
            continue
        if "pred_batch" not in pred_df.columns:
            pred_df = pred_df.with_columns(pl.lit(pred_batch).cast(pl.Int32).alias("pred_batch"))
        needed = [
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
        ]
        missing = sorted(set(needed) - set(pred_df.columns))
        if missing:
            raise ValueError(f"Missing columns in {pred_path}: {missing}")
        frames.append(pred_df.select(needed))

    if not frames:
        raise ValueError(f"No pred-batch payloads found under {unit_dir}")

    pred_rows = (
        pl.concat(frames, how="diagonal_relaxed")
        .sort(["pred_batch", "action_key", "timestamp", "batch_id"])
        .unique(
            subset=["pred_batch", "action_key", "timestamp", "batch_id"],
            keep="first",
        )
        .sort(["pred_batch", "action_key", "timestamp", "batch_id"])
    )
    combo_match_dir.mkdir(parents=True, exist_ok=True)
    out_path = combo_match_dir / "winner12_prediction_rows_pred_dedup.parquet"
    pred_rows.write_parquet(out_path)
    return out_path


def _write_combo_match_pred_rows(pred_rows: pl.DataFrame, combo_match_dir: Path) -> Path:
    combo_match_dir.mkdir(parents=True, exist_ok=True)
    out_path = combo_match_dir / "winner12_prediction_rows_pred_dedup.parquet"
    pred_rows.sort(["pred_batch", "action_key", "timestamp", "batch_id"]).write_parquet(out_path)
    return out_path


def _complete_combo_batches(pred_rows: pl.DataFrame, combo_universe: list[str]) -> tuple[set[int], list[dict[str, Any]]]:
    expected = set(combo_universe)
    if not expected:
        return set(), []

    counts = (
        pred_rows.select(["pred_batch", "action_key"])
        .unique()
        .group_by("pred_batch")
        .agg(pl.col("action_key").sort().alias("combos"))
        .sort("pred_batch")
    )

    complete: set[int] = set()
    incomplete_rows: list[dict[str, Any]] = []
    for row in counts.iter_rows(named=True):
        pred_batch = int(row["pred_batch"])
        combos = list(row["combos"])
        missing = sorted(expected - set(combos))
        extra = sorted(set(combos) - expected)
        if not missing and not extra:
            complete.add(pred_batch)
        else:
            incomplete_rows.append(
                {
                    "pred_batch": pred_batch,
                    "combo_count": len(combos),
                    "missing_combos": missing,
                    "extra_combos": extra,
                }
            )
    return complete, incomplete_rows


def _build_direct_baseline_rows(pred_rows: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    row_key = ["pred_batch", "timestamp", "batch_id", "y_true"]

    uniform = (
        pred_rows.group_by(row_key)
        .agg(
            [
                pl.col("prob_class_0").mean().alias("p0"),
                pl.col("prob_class_1").mean().alias("p1"),
                pl.col("prob_class_2").mean().alias("p2"),
                pl.col("prob_class_3").mean().alias("p3"),
            ]
        )
        .with_columns(
            [
                (pl.col("p0") + pl.col("p1")).alias("p_down"),
                (pl.col("p2") + pl.col("p3")).alias("p_up"),
            ]
        )
        .with_columns(
            [
                _argmax_expr("p", "y_pred_model"),
                (pl.col("p_up") >= pl.col("p_down")).cast(pl.Int8).alias("pred_dir_model"),
            ]
        )
        .sort(["pred_batch", "timestamp", "batch_id"])
    )

    with_dir = pred_rows.with_columns(
        (pl.col("y_pred") >= 2).cast(pl.Int8).alias("pred_dir")
    )
    all_agree = (
        with_dir.group_by(row_key)
        .agg(
            [
                pl.col("y_pred").n_unique().alias("class_nuniq"),
                pl.col("y_pred").first().alias("class_first"),
                pl.col("pred_dir").n_unique().alias("dir_nuniq"),
                pl.col("pred_dir").first().alias("dir_first"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("class_nuniq") == 1)
                .then(pl.col("class_first"))
                .otherwise(None)
                .alias("y_pred_model"),
                pl.when(pl.col("dir_nuniq") == 1)
                .then(pl.col("dir_first"))
                .otherwise(None)
                .alias("pred_dir_model"),
            ]
        )
        .sort(["pred_batch", "timestamp", "batch_id"])
    )

    uniform_path = out_dir / "uniform_direct_rows.parquet"
    agree_path = out_dir / "all_agree_rows.parquet"
    uniform.write_parquet(uniform_path)
    all_agree.write_parquet(agree_path)
    return {
        "uniform": uniform_path,
        "all_agree": agree_path,
    }


def _directional_metrics(
    *,
    df: pl.DataFrame,
    prediction_type: str,
    prediction_col: str,
    eval_batches: set[int],
) -> dict[str, Any]:
    eval_df = df.filter(pl.col("pred_batch").is_in(sorted(eval_batches)))
    total_rows = int(eval_df.height)
    total_steps = int(eval_df["pred_batch"].n_unique()) if total_rows else 0

    if prediction_type == "class":
        active = eval_df.filter(pl.col(prediction_col).is_not_null())
        if active.is_empty():
            return {
                "rows_total": total_rows,
                "rows_active": 0,
                "row_coverage": 0.0,
                "steps_total": total_steps,
                "steps_active": 0,
                "step_coverage": 0.0,
                "class_accuracy": None,
                "directional_accuracy": None,
            }
        active = active.with_columns(
            [
                (pl.col("y_true") >= 2).cast(pl.Int8).alias("true_dir"),
                (pl.col(prediction_col) >= 2).cast(pl.Int8).alias("pred_dir"),
            ]
        )
        class_acc = float((active["y_true"] == active[prediction_col]).mean())
        dir_acc = float((active["true_dir"] == active["pred_dir"]).mean())
    else:
        active = eval_df.filter(pl.col(prediction_col).is_not_null())
        if active.is_empty():
            return {
                "rows_total": total_rows,
                "rows_active": 0,
                "row_coverage": 0.0,
                "steps_total": total_steps,
                "steps_active": 0,
                "step_coverage": 0.0,
                "class_accuracy": None,
                "directional_accuracy": None,
            }
        active = active.with_columns((pl.col("y_true") >= 2).cast(pl.Int8).alias("true_dir"))
        class_acc = None
        dir_acc = float((active["true_dir"] == active[prediction_col]).mean())

    rows_active = int(active.height)
    steps_active = int(active["pred_batch"].n_unique()) if rows_active else 0
    return {
        "rows_total": total_rows,
        "rows_active": rows_active,
        "row_coverage": float(rows_active / total_rows) if total_rows else 0.0,
        "steps_total": total_steps,
        "steps_active": steps_active,
        "step_coverage": float(steps_active / total_steps) if total_steps else 0.0,
        "class_accuracy": class_acc,
        "directional_accuracy": dir_acc,
    }


def _collect_eval_batches(
    artifacts: list[MethodArtifact], *, required_batches: set[int] | None = None
) -> set[int]:
    batch_sets: list[set[int]] = []
    for art in artifacts:
        df = pl.read_parquet(art.row_path).select("pred_batch").unique()
        batch_sets.append(set(int(v) for v in df["pred_batch"].to_list()))
    if not batch_sets:
        return set()
    common = set.intersection(*batch_sets)
    if required_batches is not None:
        common &= set(required_batches)
    return set(sorted(common))


def _score_artifacts(
    *,
    root_name: str,
    artifacts: list[MethodArtifact],
    eval_batches: set[int],
) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for art in artifacts:
        df = pl.read_parquet(art.row_path)
        metrics = _directional_metrics(
            df=df,
            prediction_type=art.prediction_type,
            prediction_col=art.prediction_col,
            eval_batches=eval_batches,
        )
        rows.append(
            {
                "root": root_name,
                "method_family": art.method_family,
                "config_id": art.config_id,
                "prediction_type": art.prediction_type,
                "prediction_col": art.prediction_col,
                "row_path": str(art.row_path),
                **metrics,
                **art.extra,
            }
        )
    return pl.DataFrame(rows)


def _rank_family_best(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    ranked = []
    for family in sorted(df["method_family"].unique().to_list()):
        sub = df.filter(pl.col("method_family") == family).to_dicts()
        sub.sort(
            key=lambda r: (
                -float(r["directional_accuracy"] if r["directional_accuracy"] is not None else -1.0),
                -float(r["row_coverage"]),
                -float(r["class_accuracy"] if r["class_accuracy"] is not None else -1.0),
                str(r["config_id"]),
            )
        )
        ranked.append(sub[0])
    return pl.DataFrame(ranked).sort(["root", "directional_accuracy"], descending=[False, True])


def _run_safe_methods_for_root(
    *,
    project_root: Path,
    root_name: str,
    run_id: str,
    unit_dir: Path,
    root_out_dir: Path,
) -> dict[str, Any]:
    combo_dir = unit_dir / "combo_match_analysis" / f"causal_eval_{_timestamp_tag()}"
    pred_rows_path = _build_combo_match_pred_rows(unit_dir, combo_dir)
    pred_rows = pl.read_parquet(pred_rows_path)

    winners_summary = _build_winners_artifact(unit_dir)
    combo_universe = list(winners_summary["winner_combos"])
    expected_winners = int(len(combo_universe))
    complete_combo_batches, incomplete_combo_batches = _complete_combo_batches(
        pred_rows, combo_universe
    )
    if incomplete_combo_batches:
        pred_rows = pred_rows.filter(pl.col("pred_batch").is_in(sorted(complete_combo_batches)))
        pred_rows_path = _write_combo_match_pred_rows(pred_rows, combo_dir)

    direct_paths = _build_direct_baseline_rows(pred_rows, root_out_dir / "direct_methods")

    prob_summary = run_probability_analysis(
        project_root=project_root,
        run_id=run_id,
        model_name="catboost",
        unit="1m/target_4class",
        combo_match_dir=str(combo_dir),
        expected_winners=expected_winners,
        output_dir=root_out_dir / "winner12_probability_outputs",
    )
    prob_dir = Path(prob_summary["artifacts"]["winner12_predictions_filtered_parquet"]).parent

    artifacts: list[MethodArtifact] = [
        MethodArtifact(
            method_family="uniform_argmax_class",
            config_id="direct",
            row_path=direct_paths["uniform"],
            prediction_type="class",
            prediction_col="y_pred_model",
            extra={"note": SAFE_METHOD_NOTES["uniform_argmax_class"]},
        ),
        MethodArtifact(
            method_family="uniform_direction_sum",
            config_id="direct",
            row_path=direct_paths["uniform"],
            prediction_type="direction",
            prediction_col="pred_dir_model",
            extra={"note": SAFE_METHOD_NOTES["uniform_direction_sum"]},
        ),
        MethodArtifact(
            method_family="all_agree_class",
            config_id="direct",
            row_path=direct_paths["all_agree"],
            prediction_type="class",
            prediction_col="y_pred_model",
            extra={"note": SAFE_METHOD_NOTES["all_agree_class"]},
        ),
        MethodArtifact(
            method_family="all_agree_direction",
            config_id="direct",
            row_path=direct_paths["all_agree"],
            prediction_type="direction",
            prediction_col="pred_dir_model",
            extra={"note": SAFE_METHOD_NOTES["all_agree_direction"]},
        ),
    ]

    hedge_grid = [
        {"eta": 0.05, "loss_type": "nll"},
        {"eta": 0.10, "loss_type": "nll"},
        {"eta": 0.50, "loss_type": "nll"},
        {"eta": 0.50, "loss_type": "error"},
        {"eta": 1.00, "loss_type": "error"},
    ]
    for params in hedge_grid:
        summary = run_hedge_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            eta=float(params["eta"]),
            loss_type=str(params["loss_type"]),
            output_dir=root_out_dir / "winner12_hedge_outputs",
        )
        row_path = Path(summary["artifacts"]["winner12_hedge_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="hedge_online",
                config_id=f"eta={params['eta']}_loss={params['loss_type']}",
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_hedge",
                extra={"note": SAFE_METHOD_NOTES["hedge_online"]},
            )
        )

    diversity_grid = [
        {"subset_size": 3, "alpha_accuracy": 0.55, "weight_power": 1.0},
        {"subset_size": 4, "alpha_accuracy": 0.65, "weight_power": 1.0},
        {"subset_size": 5, "alpha_accuracy": 0.75, "weight_power": 1.0},
        {"subset_size": 4, "alpha_accuracy": 0.55, "weight_power": 1.2},
    ]
    for params in diversity_grid:
        summary = run_diversity_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            holdout_steps=200,
            wf_warmup_steps=120,
            wf_retrain_every_steps=25,
            max_train_batches=300,
            subset_size=int(params["subset_size"]),
            alpha_accuracy=float(params["alpha_accuracy"]),
            weight_power=float(params["weight_power"]),
            output_dir=root_out_dir / "winner12_diversity_outputs",
            verbose=False,
        )
        row_path = Path(summary["artifacts"]["winner12_diversity_walkforward_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="diversity_subset",
                config_id=(
                    f"subset={params['subset_size']}_alpha={params['alpha_accuracy']}"
                    f"_pow={params['weight_power']}"
                ),
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_model",
                extra={"note": SAFE_METHOD_NOTES["diversity_subset"]},
            )
        )

    classspec_grid = [
        {"specialists_per_class": 3, "recall_power": 1.0, "min_recall_floor": 0.20},
        {"specialists_per_class": 4, "recall_power": 1.0, "min_recall_floor": 0.20},
        {"specialists_per_class": 5, "recall_power": 1.2, "min_recall_floor": 0.20},
        {"specialists_per_class": 4, "recall_power": 1.0, "min_recall_floor": 0.15},
    ]
    for params in classspec_grid:
        summary = run_classspec_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            holdout_steps=200,
            wf_warmup_steps=120,
            wf_retrain_every_steps=25,
            max_train_batches=300,
            specialists_per_class=int(params["specialists_per_class"]),
            recall_power=float(params["recall_power"]),
            min_recall_floor=float(params["min_recall_floor"]),
            output_dir=root_out_dir / "winner12_classspec_outputs",
            verbose=False,
        )
        row_path = Path(summary["artifacts"]["winner12_classspec_walkforward_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="per_class_specialist",
                config_id=(
                    f"spc={params['specialists_per_class']}_rp={params['recall_power']}"
                    f"_floor={params['min_recall_floor']}"
                ),
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_model",
                extra={"note": SAFE_METHOD_NOTES["per_class_specialist"]},
            )
        )

    router_grid = [
        {"n_regimes": 3, "specialists_per_regime": 3, "min_rows_per_regime": 800},
        {"n_regimes": 4, "specialists_per_regime": 4, "min_rows_per_regime": 1000},
        {"n_regimes": 5, "specialists_per_regime": 4, "min_rows_per_regime": 1200},
    ]
    for params in router_grid:
        summary = run_router_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            holdout_steps=200,
            wf_warmup_steps=120,
            wf_retrain_every_steps=25,
            max_train_batches=300,
            n_regimes=int(params["n_regimes"]),
            specialists_per_regime=int(params["specialists_per_regime"]),
            min_rows_per_regime=int(params["min_rows_per_regime"]),
            random_seed=42,
            output_dir=root_out_dir / "winner12_router_outputs",
            verbose=False,
        )
        row_path = Path(summary["artifacts"]["winner12_router_walkforward_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="regime_router",
                config_id=(
                    f"reg={params['n_regimes']}_spr={params['specialists_per_regime']}"
                    f"_min={params['min_rows_per_regime']}"
                ),
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_model",
                extra={"note": SAFE_METHOD_NOTES["regime_router"]},
            )
        )

    stacking_grid = [
        {"c_value": 0.5, "max_iter": 120},
        {"c_value": 1.0, "max_iter": 120},
        {"c_value": 2.0, "max_iter": 180},
    ]
    for params in stacking_grid:
        summary = run_stacking_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            holdout_steps=200,
            wf_warmup_steps=120,
            wf_retrain_every_steps=25,
            max_train_batches=0,
            c_value=float(params["c_value"]),
            max_iter=int(params["max_iter"]),
            random_seed=42,
            output_dir=root_out_dir / "winner12_stacking_outputs",
            verbose=False,
        )
        row_path = Path(summary["artifacts"]["winner12_stacking_walkforward_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="stacking_meta",
                config_id=f"c={params['c_value']}_iter={params['max_iter']}",
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_model",
                extra={"note": SAFE_METHOD_NOTES["stacking_meta"]},
            )
        )

    dma_grid = [
        {
            "gamma_grid": [0.90, 0.95, 0.975, 0.99],
            "eta_model": 4.0,
            "eta_gamma": 2.0,
            "meta_loss_type": "acc_cde",
        },
        {
            "gamma_grid": [0.90, 0.95, 0.975, 0.99],
            "eta_model": 2.0,
            "eta_gamma": 1.0,
            "meta_loss_type": "acc_cde",
        },
        {
            "gamma_grid": [0.90, 0.95, 0.975, 0.99],
            "eta_model": 4.0,
            "eta_gamma": 2.0,
            "meta_loss_type": "nll",
        },
    ]
    for params in dma_grid:
        summary = run_dma_analysis(
            project_root=project_root,
            run_id=run_id,
            model_name="catboost",
            unit="1m/target_4class",
            probability_run_dir=str(prob_dir),
            gamma_grid=list(params["gamma_grid"]),
            eta_model=float(params["eta_model"]),
            eta_gamma=float(params["eta_gamma"]),
            gamma_meta_discount=0.995,
            combo_loss_acc_weight=0.7,
            combo_loss_cde_weight=0.3,
            meta_loss_type=str(params["meta_loss_type"]),
            meta_loss_acc_weight=0.7,
            meta_loss_cde_weight=0.3,
            holdout_steps=200,
            min_weight_floor=1e-8,
            output_dir=root_out_dir / "winner12_dma_outputs",
            verbose=False,
        )
        row_path = Path(summary["artifacts"]["winner12_dma_row_predictions_parquet"])
        artifacts.append(
            MethodArtifact(
                method_family="discounted_model_averaging",
                config_id=(
                    f"eta_model={params['eta_model']}_eta_gamma={params['eta_gamma']}"
                    f"_loss={params['meta_loss_type']}"
                ),
                row_path=row_path,
                prediction_type="class",
                prediction_col="y_pred_dma",
                extra={"note": SAFE_METHOD_NOTES["discounted_model_averaging"]},
            )
        )

    eval_batches = _collect_eval_batches(artifacts, required_batches=complete_combo_batches)
    scored_df = _score_artifacts(root_name=root_name, artifacts=artifacts, eval_batches=eval_batches)
    best_df = _rank_family_best(scored_df)

    meta = {
        "root": root_name,
        "run_id": run_id,
        "unit_dir": str(unit_dir),
        "combo_match_pred_rows": str(pred_rows_path),
        "probability_run_dir": str(prob_dir),
        "excluded_methods": EXCLUDED_METHODS,
        "combo_universe": combo_universe,
        "combo_count": int(len(combo_universe)),
        "complete_combo_batches_count": int(len(complete_combo_batches)),
        "incomplete_combo_batches_count": int(len(incomplete_combo_batches)),
        "incomplete_combo_batches": incomplete_combo_batches,
        "eval_batches_common_count": int(len(eval_batches)),
        "eval_batches_common_min": int(min(eval_batches)) if eval_batches else None,
        "eval_batches_common_max": int(max(eval_batches)) if eval_batches else None,
    }
    return {
        "meta": meta,
        "scored_df": scored_df,
        "best_df": best_df,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run safe no-lookahead method analysis across 8h/24h/7d and B/C roots."
    )
    parser.add_argument("--project-root", type=str, default=str(PROJECT_ROOT))
    parser.add_argument(
        "--output-dir",
        type=str,
        default="test_output/htf_causal_multiregime_method_analysis",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    output_root = (project_root / args.output_dir / _timestamp_tag()).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    all_scored: list[pl.DataFrame] = []
    all_best: list[pl.DataFrame] = []
    per_root_meta: dict[str, Any] = {}

    for root_name, cfg in ROOTS.items():
        unit_dir = (project_root / cfg["unit_dir"]).resolve()
        root_slug = root_name.lower().replace("/", "_")
        root_out_dir = output_root / root_slug
        if args.verbose:
            print(f"[Run] {root_name} -> {root_out_dir}")
        result = _run_safe_methods_for_root(
            project_root=project_root,
            root_name=root_name,
            run_id=cfg["run_id"],
            unit_dir=unit_dir,
            root_out_dir=root_out_dir,
        )
        per_root_meta[root_name] = result["meta"]
        all_scored.append(result["scored_df"])
        all_best.append(result["best_df"])

    scored_df = pl.concat(all_scored, how="diagonal_relaxed").sort(
        ["root", "directional_accuracy", "row_coverage", "method_family", "config_id"],
        descending=[False, True, True, False, False],
    )
    best_df = pl.concat(all_best, how="diagonal_relaxed").sort(
        ["root", "directional_accuracy", "row_coverage", "method_family"],
        descending=[False, True, True, False],
    )
    leaderboard_df = (
        scored_df.sort(
            ["root", "directional_accuracy", "row_coverage", "class_accuracy"],
            descending=[False, True, True, True],
        )
        if not scored_df.is_empty()
        else scored_df
    )

    summary_rows = []
    for root_name, meta in per_root_meta.items():
        best_root = best_df.filter(pl.col("root") == root_name)
        summary_rows.append(
            {
                "root": root_name,
                "combo_count": meta["combo_count"],
                "eval_batches_common_count": meta["eval_batches_common_count"],
                "best_method_family": best_root["method_family"][0] if len(best_root) else None,
                "best_config_id": best_root["config_id"][0] if len(best_root) else None,
                "best_directional_accuracy": float(best_root["directional_accuracy"][0])
                if len(best_root)
                else None,
                "best_row_coverage": float(best_root["row_coverage"][0]) if len(best_root) else None,
            }
        )
    summary_df = pl.DataFrame(summary_rows).sort("root")

    scored_path = output_root / "all_method_scores.parquet"
    scored_csv = output_root / "all_method_scores.csv"
    best_path = output_root / "best_per_family.parquet"
    best_csv = output_root / "best_per_family.csv"
    leaderboard_path = output_root / "leaderboard.parquet"
    leaderboard_csv = output_root / "leaderboard.csv"
    summary_json = output_root / "summary.json"
    summary_table_csv = output_root / "summary_table.csv"

    scored_df.write_parquet(scored_path)
    scored_df.write_csv(scored_csv)
    best_df.write_parquet(best_path)
    best_df.write_csv(best_csv)
    leaderboard_df.write_parquet(leaderboard_path)
    leaderboard_df.write_csv(leaderboard_csv)
    summary_df.write_csv(summary_table_csv)

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(output_root),
        "roots": per_root_meta,
        "excluded_methods": EXCLUDED_METHODS,
        "artifacts": {
            "all_method_scores_parquet": str(scored_path),
            "all_method_scores_csv": str(scored_csv),
            "best_per_family_parquet": str(best_path),
            "best_per_family_csv": str(best_csv),
            "leaderboard_parquet": str(leaderboard_path),
            "leaderboard_csv": str(leaderboard_csv),
            "summary_table_csv": str(summary_table_csv),
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("HTF causal multiregime method analysis complete")
    print(f"  Output root: {output_root}")
    for row in summary_rows:
        print(
            f"  {row['root']}: best={row['best_method_family']} "
            f"dir_acc={row['best_directional_accuracy']:.4f} "
            f"coverage={row['best_row_coverage']:.4f}"
        )
    print("  Summary JSON:", summary_json)


if __name__ == "__main__":
    main()

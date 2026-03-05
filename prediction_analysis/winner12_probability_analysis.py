#!/usr/bin/env python3
"""Analyze probability behavior of 12 winner combos per prediction batch.

This script reads Stage-1 combo-match artifacts for:
  run_id=stage1_catboost_live, unit=1m/target_4class (default)

It produces per-batch/per-combo probability and quality summaries so you can
inspect how each winner combo behaves through time.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _resolve_combo_match_dir(unit_dir: Path, combo_match_dir: str | None) -> Path:
    combo_root = unit_dir / "combo_match_analysis"
    if not combo_root.exists():
        raise FileNotFoundError(f"combo_match_analysis directory not found: {combo_root}")

    if combo_match_dir:
        direct = Path(combo_match_dir).expanduser()
        if direct.exists():
            return direct.resolve()
        child = combo_root / combo_match_dir
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"combo_match_dir not found: {combo_match_dir!r} "
            f"(checked {direct} and {child})"
        )

    runs = sorted([p for p in combo_root.glob("*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No combo-match runs found in: {combo_root}")
    return runs[-1].resolve()


def _parse_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise ValueError(f"unit must be in <timeframe>/<target> format, got: {unit!r}")
    tf, target = unit.split("/", 1)
    return tf, target


def _load_winner_keys(
    winners_path: Path,
    expected_winners: int,
) -> list[str]:
    winners_df = pl.read_parquet(winners_path)
    if winners_df.is_empty() or "winner_combo_key" not in winners_df.columns:
        raise ValueError(f"winners file invalid or empty: {winners_path}")

    winners = (
        winners_df.drop_nulls(["winner_combo_key"])
        .group_by("winner_combo_key")
        .len()
        .sort(["len", "winner_combo_key"], descending=[True, False])
    )
    keys = winners["winner_combo_key"].cast(pl.Utf8).to_list()
    if len(keys) < expected_winners:
        raise ValueError(
            f"Found only {len(keys)} unique winner combos in {winners_path}, "
            f"expected at least {expected_winners}."
        )
    return keys[:expected_winners]


def _required_cols_check(df: pl.DataFrame, required_cols: set[str], file_path: Path) -> None:
    missing = sorted(list(required_cols - set(df.columns)))
    if missing:
        raise ValueError(f"Missing required columns in {file_path}: {missing}")


def _build_prob_expr_from_class_col(class_col: str) -> pl.Expr:
    return (
        pl.when(pl.col(class_col) == 0)
        .then(pl.col("prob_class_0"))
        .when(pl.col(class_col) == 1)
        .then(pl.col("prob_class_1"))
        .when(pl.col(class_col) == 2)
        .then(pl.col("prob_class_2"))
        .otherwise(pl.col("prob_class_3"))
    )


def _ensure_all_combo_columns(
    wide_df: pl.DataFrame,
    combo_keys: list[str],
    fill_value: float = 0.0,
) -> pl.DataFrame:
    out = wide_df
    for key in combo_keys:
        if key not in out.columns:
            out = out.with_columns(pl.lit(fill_value).alias(key))
    return out.select(["pred_batch"] + combo_keys).sort("pred_batch")


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    combo_match_dir: str | None,
    expected_winners: int,
    output_dir: Path,
) -> dict[str, Any]:
    tf, target = _parse_unit(unit)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    winners_path = unit_dir / "winners_all_steps.parquet"
    if not winners_path.exists():
        raise FileNotFoundError(f"Missing winners file: {winners_path}")

    combo_run_dir = _resolve_combo_match_dir(unit_dir=unit_dir, combo_match_dir=combo_match_dir)
    pred_path = combo_run_dir / "winner12_prediction_rows_pred_dedup.parquet"
    if not pred_path.exists():
        raise FileNotFoundError(
            f"Missing prediction rows artifact: {pred_path}. "
            "Run Cell 14C first or pass a valid combo-match directory."
        )

    winner_keys = _load_winner_keys(
        winners_path=winners_path,
        expected_winners=int(expected_winners),
    )
    winner_set = set(winner_keys)

    pred_df = pl.read_parquet(pred_path)
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
    _required_cols_check(pred_df, required_cols, pred_path)

    filtered = (
        pred_df.with_columns(pl.col("action_key").cast(pl.Utf8, strict=False))
        .filter(pl.col("action_key").is_in(list(winner_set)))
        .sort(["pred_batch", "action_key", "timestamp", "batch_id"])
    )
    if filtered.is_empty():
        raise ValueError(f"No rows left after filtering to winner keys from {winners_path}")

    enriched = filtered.with_columns(
        [
            _build_prob_expr_from_class_col("y_pred").alias("prob_pred_class"),
            _build_prob_expr_from_class_col("y_true").alias("prob_true_class"),
            pl.max_horizontal(
                ["prob_class_0", "prob_class_1", "prob_class_2", "prob_class_3"]
            ).alias("prob_max"),
            (
                -(
                    (
                        pl.when(pl.col("prob_class_0") > 0)
                        .then(pl.col("prob_class_0") * pl.col("prob_class_0").log())
                        .otherwise(0.0)
                    )
                    + (
                        pl.when(pl.col("prob_class_1") > 0)
                        .then(pl.col("prob_class_1") * pl.col("prob_class_1").log())
                        .otherwise(0.0)
                    )
                    + (
                        pl.when(pl.col("prob_class_2") > 0)
                        .then(pl.col("prob_class_2") * pl.col("prob_class_2").log())
                        .otherwise(0.0)
                    )
                    + (
                        pl.when(pl.col("prob_class_3") > 0)
                        .then(pl.col("prob_class_3") * pl.col("prob_class_3").log())
                        .otherwise(0.0)
                    )
                )
                / pl.lit(float(1.3862943611198906))
            ).alias("entropy_norm"),
            (pl.col("y_true") == pl.col("y_pred")).alias("is_correct"),
            (
                ((pl.col("y_true") <= 1) & (pl.col("y_pred") >= 2))
                | ((pl.col("y_true") >= 2) & (pl.col("y_pred") <= 1))
            ).alias("is_cross_direction_error"),
        ]
    )

    combo_batch_metrics = (
        enriched.group_by(["pred_batch", "action_key"])
        .agg(
            [
                pl.len().alias("rows"),
                pl.col("is_correct").mean().alias("accuracy"),
                pl.col("is_cross_direction_error")
                .mean()
                .alias("cross_direction_error"),
                pl.col("prob_pred_class").mean().alias("mean_prob_pred_class"),
                pl.col("prob_true_class").mean().alias("mean_prob_true_class"),
                pl.col("prob_max").mean().alias("mean_prob_max"),
                pl.col("prob_max").std(ddof=1).fill_null(0.0).alias("std_prob_max"),
                pl.col("entropy_norm").mean().alias("mean_entropy_norm"),
                pl.col("prob_class_0").mean().alias("mean_prob_class_0"),
                pl.col("prob_class_1").mean().alias("mean_prob_class_1"),
                pl.col("prob_class_2").mean().alias("mean_prob_class_2"),
                pl.col("prob_class_3").mean().alias("mean_prob_class_3"),
                (pl.col("y_pred") == 0).mean().alias("share_pred_class_0"),
                (pl.col("y_pred") == 1).mean().alias("share_pred_class_1"),
                (pl.col("y_pred") == 2).mean().alias("share_pred_class_2"),
                (pl.col("y_pred") == 3).mean().alias("share_pred_class_3"),
            ]
        )
        .sort(["pred_batch", "action_key"])
    )

    best_combo_by_accuracy = (
        combo_batch_metrics.sort(
            ["pred_batch", "accuracy", "mean_prob_pred_class", "action_key"],
            descending=[False, True, True, False],
        )
        .unique(subset=["pred_batch"], keep="first")
        .select(
            [
                "pred_batch",
                pl.col("action_key").alias("best_combo_by_accuracy"),
                pl.col("accuracy").alias("best_accuracy"),
                pl.col("mean_prob_pred_class").alias("best_mean_prob_pred_class"),
            ]
        )
    )

    batch_summary = (
        combo_batch_metrics.group_by("pred_batch")
        .agg(
            [
                pl.col("action_key").n_unique().alias("combos_present"),
                pl.col("accuracy").mean().alias("mean_accuracy"),
                pl.col("accuracy").std(ddof=1).fill_null(0.0).alias("std_accuracy"),
                pl.col("mean_prob_pred_class")
                .mean()
                .alias("mean_prob_pred_class_over_combos"),
                pl.col("mean_prob_pred_class")
                .std(ddof=1)
                .fill_null(0.0)
                .alias("std_prob_pred_class_over_combos"),
                pl.col("mean_prob_max").mean().alias("mean_prob_max_over_combos"),
                pl.col("cross_direction_error")
                .mean()
                .alias("mean_cross_direction_error"),
            ]
        )
        .join(best_combo_by_accuracy, on="pred_batch", how="left")
        .sort("pred_batch")
    )

    prob_pred_wide = combo_batch_metrics.pivot(
        index="pred_batch",
        values="mean_prob_pred_class",
        on="action_key",
    )
    prob_pred_wide = _ensure_all_combo_columns(prob_pred_wide, winner_keys, fill_value=0.0)

    accuracy_wide = combo_batch_metrics.pivot(
        index="pred_batch",
        values="accuracy",
        on="action_key",
    )
    accuracy_wide = _ensure_all_combo_columns(accuracy_wide, winner_keys, fill_value=0.0)

    run_out = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_out.mkdir(parents=True, exist_ok=True)

    filtered_path = run_out / "winner12_predictions_filtered.parquet"
    combo_metrics_parquet = run_out / "winner12_combo_batch_probability_metrics.parquet"
    combo_metrics_csv = run_out / "winner12_combo_batch_probability_metrics.csv"
    batch_summary_parquet = run_out / "winner12_batch_probability_summary.parquet"
    batch_summary_csv = run_out / "winner12_batch_probability_summary.csv"
    prob_wide_parquet = run_out / "winner12_prob_pred_class_wide.parquet"
    prob_wide_csv = run_out / "winner12_prob_pred_class_wide.csv"
    acc_wide_parquet = run_out / "winner12_accuracy_wide.parquet"
    acc_wide_csv = run_out / "winner12_accuracy_wide.csv"
    summary_json = run_out / "winner12_probability_analysis_summary.json"

    filtered.write_parquet(filtered_path)
    combo_batch_metrics.write_parquet(combo_metrics_parquet)
    combo_batch_metrics.write_csv(combo_metrics_csv)
    batch_summary.write_parquet(batch_summary_parquet)
    batch_summary.write_csv(batch_summary_csv)
    prob_pred_wide.write_parquet(prob_wide_parquet)
    prob_pred_wide.write_csv(prob_wide_csv)
    accuracy_wide.write_parquet(acc_wide_parquet)
    accuracy_wide.write_csv(acc_wide_csv)

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "source": {
            "winners_path": str(winners_path),
            "combo_match_dir": str(combo_run_dir),
            "prediction_rows_path": str(pred_path),
        },
        "winners": {
            "expected_count": int(expected_winners),
            "used_count": int(len(winner_keys)),
            "winner_keys": winner_keys,
        },
        "rows": {
            "filtered_prediction_rows": int(len(filtered)),
            "combo_batch_metric_rows": int(len(combo_batch_metrics)),
            "batch_summary_rows": int(len(batch_summary)),
        },
        "coverage": {
            "pred_batch_min": int(batch_summary["pred_batch"].min()),
            "pred_batch_max": int(batch_summary["pred_batch"].max()),
            "combos_present_min": int(batch_summary["combos_present"].min()),
            "combos_present_max": int(batch_summary["combos_present"].max()),
        },
        "artifacts": {
            "winner12_predictions_filtered_parquet": str(filtered_path),
            "winner12_combo_batch_probability_metrics_parquet": str(combo_metrics_parquet),
            "winner12_combo_batch_probability_metrics_csv": str(combo_metrics_csv),
            "winner12_batch_probability_summary_parquet": str(batch_summary_parquet),
            "winner12_batch_probability_summary_csv": str(batch_summary_csv),
            "winner12_prob_pred_class_wide_parquet": str(prob_wide_parquet),
            "winner12_prob_pred_class_wide_csv": str(prob_wide_csv),
            "winner12_accuracy_wide_parquet": str(acc_wide_parquet),
            "winner12_accuracy_wide_csv": str(acc_wide_csv),
            "summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Analyze probability behavior of winner-12 combos per prediction batch."
    )
    p.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Repo root path. Default: auto-detected from script location.",
    )
    p.add_argument(
        "--run-id",
        type=str,
        default="stage1_catboost_live",
        help="Stage-1 run id.",
    )
    p.add_argument(
        "--model-name",
        type=str,
        default="catboost",
        help="Model directory name under run.",
    )
    p.add_argument(
        "--unit",
        type=str,
        default="1m/target_4class",
        help="Unit in format <timeframe>/<target>.",
    )
    p.add_argument(
        "--combo-match-dir",
        type=str,
        default=None,
        help=(
            "Optional combo_match_analysis run directory (absolute path or child name). "
            "Default: latest run."
        ),
    )
    p.add_argument(
        "--expected-winners",
        type=int,
        default=12,
        help="Expected number of winner combos to analyze.",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Output base directory. "
            "Default: <project_root>/prediction_analysis/winner12_probability_outputs"
        ),
    )
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_probability_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        combo_match_dir=args.combo_match_dir,
        expected_winners=int(args.expected_winners),
        output_dir=output_dir,
    )

    print("Winner-12 probability analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(f"  Source combo-match dir: {summary['source']['combo_match_dir']}")
    print(
        "  Rows: "
        f"filtered={summary['rows']['filtered_prediction_rows']}, "
        f"combo_batch={summary['rows']['combo_batch_metric_rows']}, "
        f"batch={summary['rows']['batch_summary_rows']}"
    )
    print(
        "  Coverage: "
        f"pred_batch={summary['coverage']['pred_batch_min']}..{summary['coverage']['pred_batch_max']}, "
        f"combos_present(min/max)={summary['coverage']['combos_present_min']}/"
        f"{summary['coverage']['combos_present_max']}"
    )
    print("  Artifacts:")
    for key, path in summary["artifacts"].items():
        print(f"    {key}: {path}")


if __name__ == "__main__":
    main()


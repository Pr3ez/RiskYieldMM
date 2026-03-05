#!/usr/bin/env python3
"""Heuristic winner-probability analysis for 12 configs per prediction batch.

This script consumes outputs from:
  prediction_analysis/winner12_probability_analysis.py

It builds per-batch probabilities for each combo (12 winners), estimates which
combo is currently winning, and evaluates retrospective quality against stored
winner labels.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _parse_unit(unit: str) -> tuple[str, str]:
    if "/" not in unit:
        raise ValueError(f"unit must be <timeframe>/<target>, got {unit!r}")
    return unit.split("/", 1)


def _resolve_analysis_run_dir(
    *,
    project_root: Path,
    analysis_run_dir: str | None,
) -> Path:
    base = project_root / "prediction_analysis" / "winner12_probability_outputs"
    if not base.exists():
        raise FileNotFoundError(f"Missing analysis base dir: {base}")

    if analysis_run_dir:
        direct = Path(analysis_run_dir).expanduser()
        if direct.exists():
            return direct.resolve()
        child = base / analysis_run_dir
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"analysis_run_dir not found: {analysis_run_dir!r} "
            f"(checked {direct} and {child})"
        )

    runs = sorted([p for p in base.glob("*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No runs found in {base}")
    return runs[-1].resolve()


def _safe_softmax(scores: np.ndarray, temperature: float) -> np.ndarray:
    t = float(max(1e-8, temperature))
    z = np.asarray(scores, dtype=np.float64) / t
    z = z - np.max(z)
    e = np.exp(z)
    s = float(np.sum(e))
    if s <= 0 or (not math.isfinite(s)):
        return np.full_like(e, 1.0 / len(e), dtype=np.float64)
    return e / s


def _build_transition_matrix(
    *,
    combo_keys: list[str],
    transition_df: pl.DataFrame,
    stationary_prior: dict[str, float],
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    keys_set = set(combo_keys)

    if transition_df.is_empty():
        for prev in combo_keys:
            out[prev] = dict(stationary_prior)
        return out

    grouped = transition_df.group_by("prev_winner_combo_key", maintain_order=True)
    for prev_key, sub in grouped:
        prev = str(prev_key[0])
        if prev not in keys_set:
            continue
        sub = sub.filter(pl.col("winner_combo_key").is_in(combo_keys))
        if sub.is_empty():
            out[prev] = dict(stationary_prior)
            continue
        total = float(sub["len"].sum())
        if total <= 0:
            out[prev] = dict(stationary_prior)
            continue
        row = {k: 0.0 for k in combo_keys}
        for r in sub.to_dicts():
            row[str(r["winner_combo_key"])] = float(r["len"]) / total
        out[prev] = row

    for prev in combo_keys:
        if prev not in out:
            out[prev] = dict(stationary_prior)
    return out


def _build_bin_label(value: float, width: float) -> str:
    left = math.floor(max(0.0, min(1.0, value)) / width) * width
    right = min(1.0, left + width)
    return f"[{left:.2f},{right:.2f})" if right < 1.0 else f"[{left:.2f},1.00]"


def run_analysis(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    analysis_run_dir: str | None,
    prior_blend: float,
    softmax_temperature: float,
    w_prob_pred_class: float,
    w_prob_max: float,
    w_entropy_inverse: float,
    w_std_penalty: float,
    confidence_bin_width: float,
    min_history_for_expectation: int,
    output_dir: Path,
) -> dict[str, Any]:
    tf, target = _parse_unit(unit)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    src_dir = _resolve_analysis_run_dir(
        project_root=project_root,
        analysis_run_dir=analysis_run_dir,
    )

    combo_metrics_path = src_dir / "winner12_combo_batch_probability_metrics.parquet"
    if not combo_metrics_path.exists():
        raise FileNotFoundError(f"Missing required file: {combo_metrics_path}")
    combo_metrics = pl.read_parquet(combo_metrics_path).sort(["pred_batch", "action_key"])
    if combo_metrics.is_empty():
        raise ValueError(f"No rows in {combo_metrics_path}")

    winners_path = unit_dir / "winners_all_steps.parquet"
    if not winners_path.exists():
        raise FileNotFoundError(f"Missing winners file: {winners_path}")
    winners_df = (
        pl.read_parquet(winners_path)
        .drop_nulls(["pred_batch", "winner_combo_key"])
        .select(["pred_batch", "winner_combo_key", "winner_accuracy"])
        .with_columns(
            [
                pl.col("pred_batch").cast(pl.Int32, strict=False),
                pl.col("winner_combo_key").cast(pl.Utf8, strict=False),
                pl.col("winner_accuracy").cast(pl.Float64, strict=False),
            ]
        )
        .unique(subset=["pred_batch"], keep="last")
        .sort("pred_batch")
    )

    transition_path = unit_dir / "winners_transition_stats.csv"
    transition_df = (
        pl.read_csv(transition_path)
        if transition_path.exists()
        else pl.DataFrame(
            schema={
                "prev_winner_combo_key": pl.Utf8,
                "winner_combo_key": pl.Utf8,
                "len": pl.Int64,
            }
        )
    )
    if not transition_df.is_empty():
        transition_df = transition_df.with_columns(
            [
                pl.col("prev_winner_combo_key").cast(pl.Utf8, strict=False),
                pl.col("winner_combo_key").cast(pl.Utf8, strict=False),
                pl.col("len").cast(pl.Float64, strict=False),
            ]
        )

    combo_keys = sorted(combo_metrics["action_key"].unique().to_list())
    if len(combo_keys) != 12:
        raise ValueError(
            f"Expected 12 combos in combo metrics, got {len(combo_keys)}: {combo_keys}"
        )

    stationary = (
        winners_df.group_by("winner_combo_key")
        .len()
        .with_columns((pl.col("len") / pl.sum("len")).alias("prior"))
        .select(["winner_combo_key", "prior"])
    )
    stationary_prior: dict[str, float] = {k: 0.0 for k in combo_keys}
    for row in stationary.to_dicts():
        key = str(row["winner_combo_key"])
        if key in stationary_prior:
            stationary_prior[key] = float(row["prior"])
    total_prior = float(sum(stationary_prior.values()))
    if total_prior <= 0:
        stationary_prior = {k: 1.0 / len(combo_keys) for k in combo_keys}
    else:
        stationary_prior = {k: v / total_prior for k, v in stationary_prior.items()}

    transition = _build_transition_matrix(
        combo_keys=combo_keys,
        transition_df=transition_df,
        stationary_prior=stationary_prior,
    )

    winners_map = {
        int(r["pred_batch"]): {
            "winner_combo_key": str(r["winner_combo_key"]),
            "winner_accuracy": float(r["winner_accuracy"]),
        }
        for r in winners_df.to_dicts()
    }

    # Batch loop
    matrix_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []
    prev_predicted_combo: str | None = None

    by_batch = combo_metrics.group_by("pred_batch", maintain_order=True)
    for key, sub in by_batch:
        pred_batch = int(key[0])
        sub = sub.sort("action_key")
        value_map = {str(r["action_key"]): r for r in sub.to_dicts()}

        # Heuristic live-safe likelihood score
        score = []
        for combo in combo_keys:
            row = value_map.get(combo)
            if row is None:
                score.append(float("-inf"))
                continue
            s = (
                float(w_prob_pred_class) * float(row["mean_prob_pred_class"])
                + float(w_prob_max) * float(row["mean_prob_max"])
                + float(w_entropy_inverse) * (1.0 - float(row["mean_entropy_norm"]))
                - float(w_std_penalty) * float(row["std_prob_max"])
            )
            score.append(float(s))
        score_arr = np.asarray(score, dtype=np.float64)
        likelihood = _safe_softmax(score_arr, temperature=float(softmax_temperature))

        if prev_predicted_combo is None:
            prior_arr = np.asarray(
                [stationary_prior[c] for c in combo_keys], dtype=np.float64
            )
            prior_source = "stationary"
        else:
            prior_row = transition.get(prev_predicted_combo, stationary_prior)
            prior_arr = np.asarray([prior_row[c] for c in combo_keys], dtype=np.float64)
            prior_source = f"transition_from:{prev_predicted_combo}"

        blend = float(max(0.0, min(1.0, prior_blend)))
        posterior = blend * likelihood + (1.0 - blend) * prior_arr
        p_sum = float(np.sum(posterior))
        if p_sum <= 0 or (not math.isfinite(p_sum)):
            posterior = np.asarray([1.0 / len(combo_keys)] * len(combo_keys))
        else:
            posterior = posterior / p_sum

        order = np.argsort(-posterior, kind="mergesort")
        top1_idx = int(order[0])
        top2_idx = int(order[1]) if len(order) > 1 else int(order[0])
        predicted_combo = combo_keys[top1_idx]
        posterior_max = float(posterior[top1_idx])
        posterior_margin = float(posterior[top1_idx] - posterior[top2_idx])
        top3 = [combo_keys[int(i)] for i in order[:3]]

        truth = winners_map.get(pred_batch)
        true_combo = str(truth["winner_combo_key"]) if truth is not None else None
        true_winner_acc = float(truth["winner_accuracy"]) if truth is not None else None
        hit_top1 = bool(true_combo == predicted_combo) if true_combo is not None else None
        hit_top3 = bool(true_combo in top3) if true_combo is not None else None

        pred_combo_row = value_map.get(predicted_combo, {})
        realized_acc_pred_combo = (
            float(pred_combo_row["accuracy"]) if pred_combo_row else None
        )
        realized_cross_err_pred_combo = (
            float(pred_combo_row["cross_direction_error"]) if pred_combo_row else None
        )

        for i, combo in enumerate(combo_keys):
            row = value_map.get(combo, {})
            matrix_rows.append(
                {
                    "pred_batch": pred_batch,
                    "action_key": combo,
                    "score_likelihood": float(score_arr[i]),
                    "likelihood_prob": float(likelihood[i]),
                    "prior_prob": float(prior_arr[i]),
                    "posterior_prob": float(posterior[i]),
                    "mean_prob_pred_class": float(row.get("mean_prob_pred_class", np.nan)),
                    "mean_prob_max": float(row.get("mean_prob_max", np.nan)),
                    "mean_entropy_norm": float(row.get("mean_entropy_norm", np.nan)),
                    "std_prob_max": float(row.get("std_prob_max", np.nan)),
                }
            )

        batch_rows.append(
            {
                "pred_batch": pred_batch,
                "predicted_winner_combo": predicted_combo,
                "prior_source": prior_source,
                "posterior_max": posterior_max,
                "posterior_margin": posterior_margin,
                "top3_predicted_combos": "|".join(top3),
                "true_winner_combo_key": true_combo,
                "hit_top1": hit_top1,
                "hit_top3": hit_top3,
                "true_winner_accuracy": true_winner_acc,
                "realized_accuracy_predicted_combo": realized_acc_pred_combo,
                "realized_cross_direction_error_predicted_combo": realized_cross_err_pred_combo,
            }
        )
        prev_predicted_combo = predicted_combo

    matrix_df = pl.DataFrame(matrix_rows).sort(["pred_batch", "action_key"])
    batch_df = pl.DataFrame(batch_rows).sort("pred_batch")

    # Confidence bins (fixed width), plus walk-forward expected accuracy estimate.
    bin_width = float(max(0.01, min(0.5, confidence_bin_width)))
    batch_df = batch_df.with_columns(
        pl.col("posterior_max")
        .map_elements(lambda v: _build_bin_label(float(v), bin_width), return_dtype=pl.Utf8)
        .alias("confidence_bin")
    )

    # Walk-forward expectation from prior history only
    rows = batch_df.to_dicts()
    history_by_bin: dict[str, list[float]] = {}
    global_history: list[float] = []
    wf_expected = []
    min_hist = int(max(1, min_history_for_expectation))
    for i, r in enumerate(rows):
        bin_key = str(r["confidence_bin"])
        if i < min_hist or (len(global_history) < min_hist):
            wf_expected.append(None)
        else:
            candidates = history_by_bin.get(bin_key, [])
            if len(candidates) >= max(5, min_hist // 4):
                wf_expected.append(float(np.mean(candidates)))
            else:
                wf_expected.append(float(np.mean(global_history)) if global_history else None)

        value = r.get("realized_accuracy_predicted_combo")
        if value is not None and np.isfinite(float(value)):
            fv = float(value)
            global_history.append(fv)
            history_by_bin.setdefault(bin_key, []).append(fv)

    batch_df = batch_df.with_columns(
        pl.Series("expected_accuracy_estimate_wf", wf_expected).cast(
            pl.Float64, strict=False
        )
    )

    calibration_df = (
        batch_df.group_by("confidence_bin")
        .agg(
            [
                pl.len().alias("batches"),
                pl.col("posterior_max").min().alias("posterior_min"),
                pl.col("posterior_max").max().alias("posterior_max"),
                pl.col("hit_top1")
                .cast(pl.Int8, strict=False)
                .mean()
                .alias("hit_top1_rate"),
                pl.col("hit_top3")
                .cast(pl.Int8, strict=False)
                .mean()
                .alias("hit_top3_rate"),
                pl.col("realized_accuracy_predicted_combo")
                .mean()
                .alias("mean_realized_accuracy_predicted_combo"),
                pl.col("true_winner_accuracy").mean().alias("mean_true_winner_accuracy"),
            ]
        )
        .sort("posterior_min")
    )

    overall = {
        "batches": int(len(batch_df)),
        "top1_hit_rate": float(
            batch_df["hit_top1"].cast(pl.Int8, strict=False).mean()
            if "hit_top1" in batch_df.columns
            else 0.0
        ),
        "top3_hit_rate": float(
            batch_df["hit_top3"].cast(pl.Int8, strict=False).mean()
            if "hit_top3" in batch_df.columns
            else 0.0
        ),
        "mean_realized_accuracy_predicted_combo": float(
            batch_df["realized_accuracy_predicted_combo"].mean()
        ),
        "mean_true_winner_accuracy": float(batch_df["true_winner_accuracy"].mean()),
        "mean_posterior_max": float(batch_df["posterior_max"].mean()),
    }

    out_run = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_run.mkdir(parents=True, exist_ok=True)

    matrix_parquet = out_run / "winner12_heuristic_probability_matrix.parquet"
    matrix_csv = out_run / "winner12_heuristic_probability_matrix.csv"
    batch_parquet = out_run / "winner12_heuristic_batch_predictions.parquet"
    batch_csv = out_run / "winner12_heuristic_batch_predictions.csv"
    calib_parquet = out_run / "winner12_heuristic_confidence_calibration.parquet"
    calib_csv = out_run / "winner12_heuristic_confidence_calibration.csv"
    summary_json = out_run / "winner12_heuristic_summary.json"

    matrix_df.write_parquet(matrix_parquet)
    matrix_df.write_csv(matrix_csv)
    batch_df.write_parquet(batch_parquet)
    batch_df.write_csv(batch_csv)
    calibration_df.write_parquet(calib_parquet)
    calibration_df.write_csv(calib_csv)

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "source": {
            "analysis_run_dir": str(src_dir),
            "combo_metrics_path": str(combo_metrics_path),
            "winners_path": str(winners_path),
            "transitions_path": str(transition_path),
        },
        "heuristic_config": {
            "prior_blend": float(prior_blend),
            "softmax_temperature": float(softmax_temperature),
            "weights": {
                "mean_prob_pred_class": float(w_prob_pred_class),
                "mean_prob_max": float(w_prob_max),
                "inverse_entropy": float(w_entropy_inverse),
                "std_prob_penalty": float(w_std_penalty),
            },
            "confidence_bin_width": float(bin_width),
            "min_history_for_expectation": int(min_hist),
        },
        "combos": combo_keys,
        "overall": overall,
        "artifacts": {
            "winner12_heuristic_probability_matrix_parquet": str(matrix_parquet),
            "winner12_heuristic_probability_matrix_csv": str(matrix_csv),
            "winner12_heuristic_batch_predictions_parquet": str(batch_parquet),
            "winner12_heuristic_batch_predictions_csv": str(batch_csv),
            "winner12_heuristic_confidence_calibration_parquet": str(calib_parquet),
            "winner12_heuristic_confidence_calibration_csv": str(calib_csv),
            "winner12_heuristic_summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Heuristic probability analysis for winner-12 configs."
    )
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument(
        "--analysis-run-dir",
        type=str,
        default=None,
        help="Path or child folder in prediction_analysis/winner12_probability_outputs",
    )
    p.add_argument("--prior-blend", type=float, default=0.8)
    p.add_argument("--softmax-temperature", type=float, default=0.15)
    p.add_argument("--w-prob-pred-class", type=float, default=0.45)
    p.add_argument("--w-prob-max", type=float, default=0.35)
    p.add_argument("--w-entropy-inverse", type=float, default=0.15)
    p.add_argument("--w-std-penalty", type=float, default=0.05)
    p.add_argument("--confidence-bin-width", type=float, default=0.05)
    p.add_argument("--min-history-for-expectation", type=int, default=40)
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Default: <project_root>/prediction_analysis/"
            "winner12_live_probability_outputs"
        ),
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_live_probability_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = run_analysis(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        analysis_run_dir=args.analysis_run_dir,
        prior_blend=float(args.prior_blend),
        softmax_temperature=float(args.softmax_temperature),
        w_prob_pred_class=float(args.w_prob_pred_class),
        w_prob_max=float(args.w_prob_max),
        w_entropy_inverse=float(args.w_entropy_inverse),
        w_std_penalty=float(args.w_std_penalty),
        confidence_bin_width=float(args.confidence_bin_width),
        min_history_for_expectation=int(args.min_history_for_expectation),
        output_dir=output_dir,
    )

    print("Winner-12 live heuristic analysis complete")
    print(f"  Run: {summary['run_id']} | Unit: {summary['unit']}")
    print(f"  Source analysis run: {summary['source']['analysis_run_dir']}")
    print(
        "  Overall: "
        f"top1_hit_rate={summary['overall']['top1_hit_rate']:.4f}, "
        f"top3_hit_rate={summary['overall']['top3_hit_rate']:.4f}, "
        f"mean_realized_accuracy_pred_combo="
        f"{summary['overall']['mean_realized_accuracy_predicted_combo']:.4f}"
    )
    print("  Artifacts:")
    for k, v in summary["artifacts"].items():
        print(f"    {k}: {v}")


if __name__ == "__main__":
    main()


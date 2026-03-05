#!/usr/bin/env python3
"""Parameter sweep across winner-12 ensemble methods.

Methods included:
  - dynamic_topk (posterior top-K)
  - hedge_online
  - regime_router
  - diversity_subset
  - per_class_specialist
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

# Ensure local script imports work whether executed as module or as a file.
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from winner12_per_class_specialist_analysis import (
    run_analysis as run_class_specialist,
)
from winner12_diversity_subset_analysis import (
    run_analysis as run_diversity_subset,
)
from winner12_dynamic_ensemble_analysis import (
    run_analysis as run_dynamic_topk,
)
from winner12_hedge_ensemble_analysis import (
    run_analysis as run_hedge_online,
)
from winner12_regime_router_analysis import (
    run_analysis as run_regime_router,
)


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(cli_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _metric_row_from_summary(
    *,
    method: str,
    params: dict[str, Any],
    summary: dict[str, Any],
    runtime_s: float,
) -> dict[str, Any]:
    if method == "dynamic_topk":
        m = summary["metrics"]
        return {
            "method": method,
            "params_json": json.dumps(params, sort_keys=True),
            "eval_scope": "all_batches",
            "baseline_name": "top1_posterior",
            "primary_accuracy": float(m["mean_ensemble_accuracy"]),
            "primary_macro_f1": float(m["mean_ensemble_macro_f1"]),
            "primary_cross_direction_error": float(m["mean_ensemble_cross_direction_error"]),
            "baseline_accuracy": float(m["mean_top1_accuracy"]),
            "baseline_macro_f1": float(m["mean_top1_macro_f1"]),
            "baseline_cross_direction_error": float(m["mean_top1_cross_direction_error"]),
            "delta_accuracy": float(m["mean_delta_accuracy"]),
            "delta_macro_f1": float(m["mean_delta_macro_f1"]),
            "delta_cross_direction_error": float(m["mean_delta_cross_direction_error"]),
            "holdout_accuracy": None,
            "holdout_macro_f1": None,
            "holdout_cross_direction_error": None,
            "summary_json": str(summary["artifacts"]["winner12_dynamic_ensemble_summary_json"]),
            "runtime_s": float(runtime_s),
            "status": "ok",
            "error": None,
        }

    if method == "hedge_online":
        m = summary["metrics"]
        return {
            "method": method,
            "params_json": json.dumps(params, sort_keys=True),
            "eval_scope": "all_batches",
            "baseline_name": "uniform_12",
            "primary_accuracy": float(m["mean_hedge_accuracy"]),
            "primary_macro_f1": float(m["mean_hedge_macro_f1"]),
            "primary_cross_direction_error": float(m["mean_hedge_cross_direction_error"]),
            "baseline_accuracy": float(m["mean_uniform_accuracy"]),
            "baseline_macro_f1": float(m["mean_uniform_macro_f1"]),
            "baseline_cross_direction_error": float(m["mean_uniform_cross_direction_error"]),
            "delta_accuracy": float(m["mean_delta_hedge_vs_uniform_accuracy"]),
            "delta_macro_f1": float(m["mean_delta_hedge_vs_uniform_macro_f1"]),
            "delta_cross_direction_error": float(
                m["mean_hedge_cross_direction_error"] - m["mean_uniform_cross_direction_error"]
            ),
            "holdout_accuracy": None,
            "holdout_macro_f1": None,
            "holdout_cross_direction_error": None,
            "summary_json": str(summary["artifacts"]["winner12_hedge_summary_json"]),
            "runtime_s": float(runtime_s),
            "status": "ok",
            "error": None,
        }

    # Methods below are evaluated mainly on walk-forward
    wm = summary["metrics"]["walkforward"]
    hm = summary["metrics"]["holdout"]
    mm = wm["model"]
    ub = wm["uniform"]
    return {
        "method": method,
        "params_json": json.dumps(params, sort_keys=True),
        "eval_scope": "walkforward",
        "baseline_name": "uniform_12",
        "primary_accuracy": float(mm["accuracy"]),
        "primary_macro_f1": float(mm["macro_f1"]),
        "primary_cross_direction_error": float(mm["cross_direction_error"]),
        "baseline_accuracy": float(ub["accuracy"]),
        "baseline_macro_f1": float(ub["macro_f1"]),
        "baseline_cross_direction_error": float(ub["cross_direction_error"]),
        "delta_accuracy": float(mm["accuracy"] - ub["accuracy"]),
        "delta_macro_f1": float(mm["macro_f1"] - ub["macro_f1"]),
        "delta_cross_direction_error": float(mm["cross_direction_error"] - ub["cross_direction_error"]),
        "holdout_accuracy": float(hm["model"]["accuracy"]),
        "holdout_macro_f1": float(hm["model"]["macro_f1"]),
        "holdout_cross_direction_error": float(hm["model"]["cross_direction_error"]),
        "summary_json": str(next(v for k, v in summary["artifacts"].items() if k.endswith("_summary_json"))),
        "runtime_s": float(runtime_s),
        "status": "ok",
        "error": None,
    }


def _error_row(
    *,
    method: str,
    params: dict[str, Any],
    runtime_s: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "method": method,
        "params_json": json.dumps(params, sort_keys=True),
        "eval_scope": None,
        "baseline_name": None,
        "primary_accuracy": None,
        "primary_macro_f1": None,
        "primary_cross_direction_error": None,
        "baseline_accuracy": None,
        "baseline_macro_f1": None,
        "baseline_cross_direction_error": None,
        "delta_accuracy": None,
        "delta_macro_f1": None,
        "delta_cross_direction_error": None,
        "holdout_accuracy": None,
        "holdout_macro_f1": None,
        "holdout_cross_direction_error": None,
        "summary_json": None,
        "runtime_s": float(runtime_s),
        "status": "error",
        "error": repr(exc),
    }


def _best_per_method(df: pl.DataFrame) -> pl.DataFrame:
    ok = df.filter(pl.col("status") == "ok")
    out_rows: list[dict[str, Any]] = []
    for method in sorted(ok["method"].unique().to_list()):
        sub = ok.filter(pl.col("method") == method).to_dicts()
        sub_sorted = sorted(
            sub,
            key=lambda r: (
                float(r["delta_accuracy"]),
                float(r["primary_accuracy"]),
                float(r["delta_macro_f1"]),
                -float(r["delta_cross_direction_error"]),
            ),
            reverse=True,
        )
        out_rows.append(sub_sorted[0])
    return pl.DataFrame(out_rows).sort("method")


def run_sweep(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    probability_run_dir: str | None,
    heuristic_run_dir: str | None,
    output_dir: Path,
    verbose: bool,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    method_base = run_dir / "method_runs"
    method_base.mkdir(parents=True, exist_ok=True)

    grids: dict[str, list[dict[str, Any]]] = {
        "dynamic_topk": [
            {"top_k": 2, "posterior_min": 0.00, "min_combos": 2},
            {"top_k": 3, "posterior_min": 0.00, "min_combos": 2},
            {"top_k": 4, "posterior_min": 0.00, "min_combos": 2},
            {"top_k": 3, "posterior_min": 0.05, "min_combos": 2},
            {"top_k": 4, "posterior_min": 0.05, "min_combos": 2},
            {"top_k": 5, "posterior_min": 0.05, "min_combos": 3},
        ],
        "hedge_online": [
            {"eta": 0.05, "loss_type": "nll"},
            {"eta": 0.10, "loss_type": "nll"},
            {"eta": 0.50, "loss_type": "nll"},
            {"eta": 0.50, "loss_type": "error"},
            {"eta": 1.00, "loss_type": "error"},
        ],
        "regime_router": [
            {"n_regimes": 3, "specialists_per_regime": 3, "min_rows_per_regime": 800},
            {"n_regimes": 4, "specialists_per_regime": 4, "min_rows_per_regime": 1000},
            {"n_regimes": 5, "specialists_per_regime": 4, "min_rows_per_regime": 1200},
        ],
        "diversity_subset": [
            {"subset_size": 3, "alpha_accuracy": 0.55, "weight_power": 1.0},
            {"subset_size": 4, "alpha_accuracy": 0.65, "weight_power": 1.0},
            {"subset_size": 5, "alpha_accuracy": 0.75, "weight_power": 1.0},
            {"subset_size": 4, "alpha_accuracy": 0.55, "weight_power": 1.2},
        ],
        "per_class_specialist": [
            {"specialists_per_class": 3, "recall_power": 1.0, "min_recall_floor": 0.20},
            {"specialists_per_class": 4, "recall_power": 1.0, "min_recall_floor": 0.20},
            {"specialists_per_class": 5, "recall_power": 1.2, "min_recall_floor": 0.20},
            {"specialists_per_class": 4, "recall_power": 1.0, "min_recall_floor": 0.15},
        ],
    }

    rows: list[dict[str, Any]] = []
    run_count = 0

    for method, configs in grids.items():
        for params in configs:
            run_count += 1
            t0 = time.time()
            try:
                if verbose:
                    print(f"[Sweep] method={method} params={params}")

                if method == "dynamic_topk":
                    summary = run_dynamic_topk(
                        project_root=project_root,
                        run_id=run_id,
                        model_name=model_name,
                        unit=unit,
                        probability_run_dir=probability_run_dir,
                        heuristic_run_dir=heuristic_run_dir,
                        top_k=int(params["top_k"]),
                        posterior_min=float(params["posterior_min"]),
                        min_combos=int(params["min_combos"]),
                        output_dir=method_base / method,
                    )
                elif method == "hedge_online":
                    summary = run_hedge_online(
                        project_root=project_root,
                        run_id=run_id,
                        model_name=model_name,
                        unit=unit,
                        probability_run_dir=probability_run_dir,
                        eta=float(params["eta"]),
                        loss_type=str(params["loss_type"]),
                        output_dir=method_base / method,
                    )
                elif method == "regime_router":
                    summary = run_regime_router(
                        project_root=project_root,
                        run_id=run_id,
                        model_name=model_name,
                        unit=unit,
                        probability_run_dir=probability_run_dir,
                        holdout_steps=200,
                        wf_warmup_steps=120,
                        wf_retrain_every_steps=25,
                        max_train_batches=300,
                        n_regimes=int(params["n_regimes"]),
                        specialists_per_regime=int(params["specialists_per_regime"]),
                        min_rows_per_regime=int(params["min_rows_per_regime"]),
                        random_seed=42,
                        output_dir=method_base / method,
                        verbose=False,
                    )
                elif method == "diversity_subset":
                    summary = run_diversity_subset(
                        project_root=project_root,
                        run_id=run_id,
                        model_name=model_name,
                        unit=unit,
                        probability_run_dir=probability_run_dir,
                        holdout_steps=200,
                        wf_warmup_steps=120,
                        wf_retrain_every_steps=25,
                        max_train_batches=300,
                        subset_size=int(params["subset_size"]),
                        alpha_accuracy=float(params["alpha_accuracy"]),
                        weight_power=float(params["weight_power"]),
                        output_dir=method_base / method,
                        verbose=False,
                    )
                elif method == "per_class_specialist":
                    summary = run_class_specialist(
                        project_root=project_root,
                        run_id=run_id,
                        model_name=model_name,
                        unit=unit,
                        probability_run_dir=probability_run_dir,
                        holdout_steps=200,
                        wf_warmup_steps=120,
                        wf_retrain_every_steps=25,
                        max_train_batches=300,
                        specialists_per_class=int(params["specialists_per_class"]),
                        recall_power=float(params["recall_power"]),
                        min_recall_floor=float(params["min_recall_floor"]),
                        output_dir=method_base / method,
                        verbose=False,
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")

                rows.append(
                    _metric_row_from_summary(
                        method=method,
                        params=params,
                        summary=summary,
                        runtime_s=(time.time() - t0),
                    )
                )
            except Exception as exc:
                rows.append(
                    _error_row(
                        method=method,
                        params=params,
                        runtime_s=(time.time() - t0),
                        exc=exc,
                    )
                )

    results_df = pl.DataFrame(rows)
    best_df = _best_per_method(results_df) if len(results_df) > 0 else pl.DataFrame([])
    ok_df = results_df.filter(pl.col("status") == "ok")

    leaderboard_df = (
        ok_df.sort(
            ["delta_accuracy", "primary_accuracy", "delta_macro_f1", "delta_cross_direction_error"],
            descending=[True, True, True, False],
        )
        if len(ok_df) > 0
        else pl.DataFrame([])
    )

    results_parquet = run_dir / "winner12_method_sweep_results.parquet"
    results_csv = run_dir / "winner12_method_sweep_results.csv"
    best_parquet = run_dir / "winner12_method_sweep_best_per_method.parquet"
    best_csv = run_dir / "winner12_method_sweep_best_per_method.csv"
    leaderboard_parquet = run_dir / "winner12_method_sweep_leaderboard.parquet"
    leaderboard_csv = run_dir / "winner12_method_sweep_leaderboard.csv"
    summary_json = run_dir / "winner12_method_sweep_summary.json"

    results_df.write_parquet(results_parquet)
    results_df.write_csv(results_csv)
    if len(best_df) > 0:
        best_df.write_parquet(best_parquet)
        best_df.write_csv(best_csv)
    if len(leaderboard_df) > 0:
        leaderboard_df.write_parquet(leaderboard_parquet)
        leaderboard_df.write_csv(leaderboard_csv)

    summary = {
        "run_id": run_id,
        "unit": unit,
        "model_name": model_name,
        "grid_counts": {k: len(v) for k, v in grids.items()},
        "total_runs": int(run_count),
        "ok_runs": int(len(ok_df)),
        "error_runs": int(len(results_df) - len(ok_df)),
        "artifacts": {
            "winner12_method_sweep_results_parquet": str(results_parquet),
            "winner12_method_sweep_results_csv": str(results_csv),
            "winner12_method_sweep_best_per_method_parquet": str(best_parquet),
            "winner12_method_sweep_best_per_method_csv": str(best_csv),
            "winner12_method_sweep_leaderboard_parquet": str(leaderboard_parquet),
            "winner12_method_sweep_leaderboard_csv": str(leaderboard_csv),
            "winner12_method_sweep_summary_json": str(summary_json),
        },
    }
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    return {
        "summary": summary,
        "results_df": results_df,
        "best_df": best_df,
        "leaderboard_df": leaderboard_df,
        "run_dir": run_dir,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Winner-12 multi-method parameter sweep.")
    p.add_argument("--project-root", type=str, default=None)
    p.add_argument("--run-id", type=str, default="stage1_catboost_live")
    p.add_argument("--model-name", type=str, default="catboost")
    p.add_argument("--unit", type=str, default="1m/target_4class")
    p.add_argument("--probability-run-dir", type=str, default=None)
    p.add_argument("--heuristic-run-dir", type=str, default=None)
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Default: <project_root>/prediction_analysis/winner12_method_sweep_outputs",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    project_root = _resolve_project_root(args.project_root)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "prediction_analysis" / "winner12_method_sweep_outputs"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    result = run_sweep(
        project_root=project_root,
        run_id=args.run_id,
        model_name=args.model_name,
        unit=args.unit,
        probability_run_dir=args.probability_run_dir,
        heuristic_run_dir=args.heuristic_run_dir,
        output_dir=output_dir,
        verbose=bool(args.verbose),
    )

    summary = result["summary"]
    best_df: pl.DataFrame = result["best_df"]
    print("Winner-12 method sweep complete")
    print(f"  total_runs={summary['total_runs']} ok={summary['ok_runs']} error={summary['error_runs']}")
    if len(best_df) > 0:
        print("\nBest per method (by delta_accuracy):")
        print(
            best_df.select(
                [
                    "method",
                    "primary_accuracy",
                    "baseline_accuracy",
                    "delta_accuracy",
                    "primary_macro_f1",
                    "delta_macro_f1",
                    "primary_cross_direction_error",
                    "delta_cross_direction_error",
                    "params_json",
                ]
            )
        )
    print("\nArtifacts:")
    for k, v in summary["artifacts"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

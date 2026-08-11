from __future__ import annotations

import argparse
import json
import math
import sys
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.analysis.htf_stage1_regression_walkforward import (  # noqa: E402
    FEATURE_POLICY_TARGET_SPECIFIC_V1,
    FEATURE_POLICY_TARGET_SPECIFIC_V2,
    FEATURE_SOURCE_MODES,
    REGRESSION_FEATURE_SET,
    FeaturePolicyConfig,
    FeatureSourceConfig,
    resolve_or_build_dataset,
    run_regression_walkforward,
)
from scripts.analysis.materialize_stage1_regression_targets import all_target_cols  # noqa: E402
from scripts.htf_backtest.catboost.stage1_multiasset_dataset import (  # noqa: E402
    MULTIASSET_MERGED_ROOT,
    STAGE1_MULTIASSET_ROOT_LAYOUTS,
    parse_stage1_target_assets,
)
from scripts.project_paths import ensure_project_root_on_path  # noqa: E402


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "stage1_regression_grid_search"


def iter_grid(args: argparse.Namespace) -> list[dict[str, Any]]:
    """Return deterministic grid rows for the requested search space."""

    rows: list[dict[str, Any]] = []
    feature_source_modes = _parse_str_list(args.feature_source_modes)
    for feature_source_mode in feature_source_modes:
        if feature_source_mode not in FEATURE_SOURCE_MODES:
            raise ValueError(
                f"Unsupported feature source mode {feature_source_mode!r}; "
                f"expected one of {list(FEATURE_SOURCE_MODES)}"
            )
    for lookback_batches in _parse_int_list(args.lookback_grid):
        for val_batches in _parse_int_list(args.val_grid):
            if int(val_batches) >= int(lookback_batches):
                continue
            for max_features in _parse_int_list(args.max_features_grid):
                for min_abs_spearman in _parse_float_list(args.min_abs_spearman_grid):
                    for dedupe_corr_threshold in _parse_float_list(args.dedupe_corr_grid):
                        for iterations in _parse_int_list(args.iterations_grid):
                            for depth in _parse_int_list(args.depth_grid):
                                for learning_rate in _parse_float_list(args.learning_rate_grid):
                                    for feature_source_mode in feature_source_modes:
                                        rows.append(
                                            {
                                                "feature_source_mode": feature_source_mode,
                                                "lookback_batches": int(lookback_batches),
                                                "val_batches": int(val_batches),
                                                "max_features": int(max_features),
                                                "min_abs_spearman": float(min_abs_spearman),
                                                "dedupe_corr_threshold": float(dedupe_corr_threshold),
                                                "iterations": int(iterations),
                                                "depth": int(depth),
                                                "learning_rate": float(learning_rate),
                                            }
                                        )
    return rows


def main() -> int:
    args = _parse_args()
    run_root = Path(args.output_dir) / _run_slug()
    run_root.mkdir(parents=True, exist_ok=True)

    target_assets = parse_stage1_target_assets(args.target_assets)
    roots = tuple(args.roots)
    target_cols = _parse_target_cols(args.stage1_target_cols)
    grid_rows = iter_grid(args)
    max_configs_per_target = _resolve_max_configs_per_target(args)
    if max_configs_per_target is not None:
        grid_rows = grid_rows[: int(max_configs_per_target)]

    if args.plan_only:
        total_planned = len(target_assets) * len(roots) * len(target_cols) * len(grid_rows)
        if args.max_runs_total is not None:
            total_planned = min(total_planned, int(args.max_runs_total))
        print(
            f"Plan only: assets={target_assets} roots={roots} targets={target_cols} "
            f"configs_per_target={len(grid_rows)} planned_runs={total_planned}"
        )
        return 0

    result_rows: list[dict[str, Any]] = []
    total_started = 0
    stop_requested = False
    for target_asset in target_assets:
        for root_key in roots:
            for target_col in target_cols:
                if stop_requested:
                    break
                target_args = copy(args)
                target_args.stage1_target_col = target_col
                dataset = resolve_or_build_dataset(
                    target_args,
                    target_asset=target_asset,
                    root_key=root_key,
                )
                for idx, config in enumerate(grid_rows):
                    if args.max_runs_total is not None and total_started >= int(args.max_runs_total):
                        stop_requested = True
                        break
                    total_started += 1
                    suffix = _config_suffix(idx, config)
                    print(
                        f"RUN {target_asset} {root_key} {target_col} "
                        f"{suffix} feature_source={config['feature_source_mode']}"
                    )
                    try:
                        payload = run_regression_walkforward(
                            dataset=dataset,
                            n_steps=int(args.n_steps),
                            lookback_batches=int(config["lookback_batches"]),
                            val_batches=int(config["val_batches"]),
                            embargo_batches=int(args.embargo_batches),
                            iterations=int(config["iterations"]),
                            depth=int(config["depth"]),
                            learning_rate=float(config["learning_rate"]),
                            task_type=str(args.task_type),
                            thread_count=int(args.thread_count),
                            feature_policy_config=FeaturePolicyConfig(
                                policy=str(args.feature_policy),
                                max_features=int(config["max_features"]),
                                min_abs_spearman=float(config["min_abs_spearman"]),
                                dedupe_corr_threshold=float(config["dedupe_corr_threshold"]),
                                clip_quantiles=_parse_clip_quantiles(args.clip_quantiles),
                                min_selected_features=int(args.min_selected_features),
                                stability_segments=int(args.stability_segments),
                                tail_quantile=float(args.tail_quantile),
                            ),
                            feature_source_config=FeatureSourceConfig(
                                mode=str(config["feature_source_mode"]),
                                regression_feature_set=str(args.regression_feature_set),
                                data_root=PROJECT_ROOT / "data",
                            ),
                            run_suffix=suffix,
                            output_root=Path(args.walkforward_output_dir),
                        )
                        selection_metrics = payload["selection_metrics"]
                        validation_metrics = payload["validation_metrics"]
                        prediction_metrics = payload["prediction_metrics"]
                        row = {
                            "status": "ok",
                            "target_asset": target_asset,
                            "root": root_key,
                            "target_col": target_col,
                            "run_id": payload["run_id"],
                            "summary_path": payload["outputs"]["summary"],
                            "n_completed_steps": payload["n_completed_steps"],
                            "optimization_decision_basis": payload["optimization_decision_basis"],
                            **config,
                            **{f"metric_{key}": value for key, value in selection_metrics.items()},
                            **{f"selection_metric_{key}": value for key, value in selection_metrics.items()},
                            **{f"validation_metric_{key}": value for key, value in validation_metrics.items()},
                            **{f"prediction_metric_{key}": value for key, value in prediction_metrics.items()},
                        }
                        print(
                            f"DONE {payload['run_id']} "
                            f"val_rmse={_fmt(validation_metrics.get('rmse'))} "
                            f"val_spearman={_fmt(validation_metrics.get('spearman'))} "
                            f"pred_spearman={_fmt(prediction_metrics.get('spearman'))}"
                        )
                    except Exception as exc:
                        row = {
                            "status": "error",
                            "target_asset": target_asset,
                            "root": root_key,
                            "target_col": target_col,
                            "run_id": None,
                            "summary_path": None,
                            "n_completed_steps": 0,
                            **config,
                            "error": str(exc),
                        }
                        print(f"ERROR {target_asset} {root_key} {target_col} {suffix}: {exc}")
                        if args.fail_fast:
                            raise
                    result_rows.append(row)
                    _write_results(run_root, result_rows)
            if stop_requested:
                break
        if stop_requested:
            break
    _write_results(run_root, result_rows)
    print(f"Grid summary: {run_root / 'grid_summary.csv'}")
    return 0


def _write_results(run_root: Path, rows: list[dict[str, Any]]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "grid_summary.json").write_text(json.dumps(rows, indent=2, default=str))
    if rows:
        frame = pl.DataFrame(rows)
        frame.write_parquet(run_root / "grid_summary.parquet")
        frame.write_csv(run_root / "grid_summary.csv")


def _config_suffix(idx: int, config: dict[str, Any]) -> str:
    lr = str(config["learning_rate"]).replace(".", "p")
    ms = str(config["min_abs_spearman"]).replace(".", "p")
    dd = str(config["dedupe_corr_threshold"]).replace(".", "p")
    return (
        f"grid{idx:03d}_fs_{config['feature_source_mode']}"
        f"_lb{config['lookback_batches']}_val{config['val_batches']}"
        f"_mf{config['max_features']}_ms{ms}_dedupe{dd}"
        f"_it{config['iterations']}_d{config['depth']}_lr{lr}"
    )


def _run_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_target_cols(raw: str) -> tuple[str, ...]:
    allowed = set(all_target_cols())
    values = tuple(_parse_str_list(raw))
    unknown = [value for value in values if value not in allowed]
    if unknown:
        raise ValueError(f"Unknown regression target columns: {unknown}")
    return values


def _parse_str_list(raw: str) -> list[str]:
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _parse_int_list(raw: str) -> list[int]:
    return [int(value) for value in _parse_str_list(raw)]


def _parse_float_list(raw: str) -> list[float]:
    return [float(value) for value in _parse_str_list(raw)]


def _parse_clip_quantiles(raw: str) -> tuple[float, float]:
    values = _parse_float_list(raw)
    if len(values) != 2:
        raise ValueError("--clip-quantiles must be two comma-separated floats")
    low, high = values
    if not (0.0 <= low < high <= 1.0):
        raise ValueError("--clip-quantiles must satisfy 0 <= low < high <= 1")
    return low, high


def _resolve_max_configs_per_target(args: argparse.Namespace) -> int | None:
    if args.max_configs_per_target is not None:
        return int(args.max_configs_per_target)
    if args.max_runs is not None:
        print(
            "WARNING: --max-runs is deprecated and now maps to "
            "--max-configs-per-target. Use --max-runs-total for a true global cap."
        )
        return int(args.max_runs)
    return None


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return "-"
    return f"{value:.6g}"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grid search wrapper for Stage-1 regression walk-forward."
    )
    parser.add_argument("--build-merged-dataset", action="store_true")
    parser.add_argument("--target-assets", default="BTCUSDT")
    parser.add_argument("--context-assets", default=None)
    parser.add_argument("--roots", nargs="*", choices=sorted(STAGE1_MULTIASSET_ROOT_LAYOUTS), default=["8h/B"])
    parser.add_argument(
        "--stage1-target-cols",
        default="target_reg_distance_up_extreme_hvol_v2",
        help="Comma-separated regression target columns.",
    )
    parser.add_argument("--multiasset-dataset-dir", type=Path, default=PROJECT_ROOT / "data" / MULTIASSET_MERGED_ROOT)
    parser.add_argument("--merged-batch-min", type=int, default=None)
    parser.add_argument("--merged-batch-max", type=int, default=None)
    parser.add_argument("--merged-batch-limit", type=int, default=None)
    parser.add_argument(
        "--feature-source-modes",
        default="htf_only,regression_only,htf_plus_regression",
    )
    parser.add_argument("--regression-feature-set", default=REGRESSION_FEATURE_SET)
    parser.add_argument(
        "--feature-policy",
        choices=[
            FEATURE_POLICY_TARGET_SPECIFIC_V1,
            FEATURE_POLICY_TARGET_SPECIFIC_V2,
        ],
        default=FEATURE_POLICY_TARGET_SPECIFIC_V2,
    )
    parser.add_argument("--lookback-grid", default="80,120,180")
    parser.add_argument("--val-grid", default="10,20")
    parser.add_argument("--max-features-grid", default="100,150,300")
    parser.add_argument("--min-abs-spearman-grid", default="0.02,0.03,0.05")
    parser.add_argument("--min-selected-features", type=int, default=20)
    parser.add_argument("--stability-segments", type=int, default=5)
    parser.add_argument("--tail-quantile", type=float, default=0.80)
    parser.add_argument("--dedupe-corr-grid", default="0.98,0.995")
    parser.add_argument("--iterations-grid", default="200,300")
    parser.add_argument("--depth-grid", default="4,6")
    parser.add_argument("--learning-rate-grid", default="0.03,0.05")
    parser.add_argument("--clip-quantiles", default="0.001,0.999")
    parser.add_argument("--n-steps", type=int, default=20)
    parser.add_argument("--embargo-batches", type=int, default=0)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--walkforward-output-dir", type=Path, default=PROJECT_ROOT / "test_output" / "stage1_regression_walkforward")
    parser.add_argument("--max-configs-per-target", type=int, default=None)
    parser.add_argument("--max-runs-total", type=int, default=None)
    parser.add_argument("--max-runs", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())

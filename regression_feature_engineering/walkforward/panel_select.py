"""Build frozen RPF feature panels with CatBoost SHAP recursive selection."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from regression_feature_engineering.walkforward.ablation import FAMILY_PREFIXES, select_ablation_features
from regression_feature_engineering.walkforward.config import load_clean_config, merge_config
from regression_feature_engineering.walkforward.data import frame_to_numpy, load_joined_batches, resolve_context
from regression_feature_engineering.walkforward.model import build_catboost_params
from regression_feature_engineering.walkforward.windows import read_windows
from scripts.project_paths import ensure_project_root_on_path


PROJECT_ROOT = ensure_project_root_on_path(Path(__file__))
OUTPUT_ROOT = PROJECT_ROOT / "test_output" / "rpf_feature_panels"
DEFAULT_CANDIDATE_TARGETS: dict[str, tuple[str, ...]] = {
    "target_reg_direction_extreme_up_share_hvol_v2": (
        "target_extreme_up_minus_down",
        "target_extreme_up_down_ratio",
    ),
    "target_reg_direction_mean_up_share_hvol_v2": (
        "target_mean_up_minus_down",
    ),
}


def main() -> int:
    args = _parse_args()
    config = load_clean_config(args.config)
    config = merge_config(
        config,
        asset=args.asset or config.asset,
        root=args.root or config.root,
        target_col=args.target_col or config.target_col,
        feature_ablation=args.feature_ablation or config.feature_ablation,
    )
    context = resolve_context(
        project_root=PROJECT_ROOT,
        asset=config.asset,
        root=config.root,
        target_col=config.target_col,
    )
    run_root = _run_root(args, config.target_col)
    run_root.mkdir(parents=True, exist_ok=True)
    print(
        "[rpf-panel] start "
        f"asset={config.asset} root={config.root} target={config.target_col} run={run_root}",
        flush=True,
    )
    candidate_targets = _candidate_targets(args.candidate_targets, config.target_col)
    feature_universe = select_ablation_features(context.manifest.feature_columns, config.feature_ablation)
    candidates, source_paths = build_candidate_pool(
        diagnostics_root=args.diagnostics_root,
        asset=config.asset,
        root_id=context.root_id,
        manifest_features=feature_universe,
        candidate_targets=candidate_targets,
        candidate_limit=int(args.candidate_limit),
        per_family_limit=int(args.per_family_limit),
        min_abs_spearman=float(args.min_abs_spearman),
        min_bin_spread_abs=float(args.min_bin_spread_abs),
    )
    if candidates.is_empty():
        raise ValueError("No RPF candidate features survived diagnostic prefiltering")
    candidate_features = tuple(str(value) for value in candidates["feature"].to_list())
    if len(candidate_features) < int(args.num_features_to_select):
        raise ValueError(
            f"Candidate pool has {len(candidate_features)} features, "
            f"below num_features_to_select={args.num_features_to_select}"
        )
    windows = read_windows(Path(args.base_run) / "frozen_windows.parquet")
    if not windows:
        raise ValueError(f"Base run has no frozen windows: {args.base_run}")
    window = windows[int(args.window_index)]
    train = load_joined_batches(context, window.train_batch_ids, feature_columns=candidate_features)
    val = load_joined_batches(context, window.val_batch_ids, feature_columns=candidate_features)
    X_train, y_train, _ = frame_to_numpy(train, target_col=context.target_col, feature_columns=candidate_features)
    X_val, y_val, _ = frame_to_numpy(val, target_col=context.target_col, feature_columns=candidate_features)
    if X_train.size == 0 or X_val.size == 0:
        raise ValueError("Empty SHAP selection model matrix")
    selection = run_catboost_shap_selection(
        X_train=X_train,
        y_train=y_train,
        X_val=X_val,
        y_val=y_val,
        feature_names=candidate_features,
        num_features_to_select=int(args.num_features_to_select),
        steps=int(args.selection_steps),
        shap_calc_type=str(args.shap_calc_type),
        task_type=str(args.task_type),
        thread_count=int(args.thread_count),
        model_config=config.model,
    )
    selected_features = tuple(str(value) for value in selection["selected_features_names"])
    candidates.write_parquet(run_root / "candidate_pool.parquet")
    panel = {
        "schema_version": "rpf_frozen_panel_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "asset": config.asset,
        "root": config.root,
        "root_id": context.root_id,
        "target_col": config.target_col,
        "feature_set": config.feature_set,
        "target_variant": config.target_variant,
        "feature_ablation": config.feature_ablation,
        "selection_algorithm": "RecursiveByShapValues",
        "shap_calc_type": str(args.shap_calc_type),
        "candidate_targets": list(candidate_targets),
        "candidate_feature_count": len(candidate_features),
        "selected_feature_count": len(selected_features),
        "selected_features": list(selected_features),
        "candidate_features": list(candidate_features),
        "base_run": str(args.base_run),
        "window_index": int(args.window_index),
        "window": {
            "step_idx": int(window.step_idx),
            "pred_batch_id": int(window.pred_batch_id),
            "train_batch_ids": list(window.train_batch_ids),
            "val_batch_ids": list(window.val_batch_ids),
            "train_start_ts": None if window.train_start_ts is None else str(window.train_start_ts),
            "train_end_ts": None if window.train_end_ts is None else str(window.train_end_ts),
            "val_start_ts": None if window.val_start_ts is None else str(window.val_start_ts),
            "val_end_ts": None if window.val_end_ts is None else str(window.val_end_ts),
        },
        "model_config": asdict(config.model),
        "source_diagnostics": [str(path) for path in source_paths],
        "catboost_summary": selection["raw_summary"],
    }
    panel_path = run_root / f"selected_panel_{len(selected_features)}.json"
    panel_path.write_text(json.dumps(panel, indent=2, default=str) + "\n")
    (run_root / "selected_panel.md").write_text(_panel_markdown(panel, candidates))
    print(
        "[rpf-panel] done "
        f"candidates={len(candidate_features)} selected={len(selected_features)} panel={panel_path}",
        flush=True,
    )
    return 0


def build_candidate_pool(
    *,
    diagnostics_root: Path,
    asset: str,
    root_id: str,
    manifest_features: tuple[str, ...],
    candidate_targets: tuple[str, ...],
    candidate_limit: int,
    per_family_limit: int,
    min_abs_spearman: float,
    min_bin_spread_abs: float,
) -> tuple[pl.DataFrame, tuple[Path, ...]]:
    paths = _diagnostic_paths(diagnostics_root, asset=asset, root_id=root_id, name="feature_target_correlations.parquet")
    if not paths:
        raise FileNotFoundError(f"No feature_target_correlations.parquet found under {diagnostics_root}")
    manifest_set = set(manifest_features)
    corr_frames: list[pl.DataFrame] = []
    for path in paths:
        frame = pl.read_parquet(path)
        if not {"feature", "target", "spearman", "abs_spearman"}.issubset(frame.columns):
            continue
        corr_frames.append(
            frame.with_columns(
                pl.lit(str(path)).alias("correlation_source_path"),
                pl.lit(path.stat().st_mtime).alias("correlation_source_mtime"),
            )
        )
    corr = pl.concat(corr_frames, how="vertical") if corr_frames else pl.DataFrame()
    if corr.is_empty():
        raise ValueError("Correlation diagnostics are empty")
    target_set = set(candidate_targets)
    filtered = (
        corr.filter(pl.col("feature").is_in(manifest_set))
        .filter(pl.col("target").is_in(target_set))
        .filter(pl.col("abs_spearman").fill_null(0.0) >= float(min_abs_spearman))
        .with_columns(
            pl.col("feature").map_elements(_feature_family, return_dtype=pl.Utf8).alias("family"),
            (pl.col("abs_spearman").fill_null(0.0) + 0.25 * pl.col("pearson").abs().fill_null(0.0)).alias("correlation_score"),
        )
        .sort(["feature", "correlation_score"], descending=[False, True])
        .unique(subset=["feature"], keep="first", maintain_order=True)
    )
    spread = _load_best_bin_spreads(
        diagnostics_root=diagnostics_root,
        asset=asset,
        root_id=root_id,
        manifest_set=manifest_set,
        candidate_targets=target_set,
        min_bin_spread_abs=float(min_bin_spread_abs),
    )
    if not spread.is_empty():
        filtered = filtered.join(spread, on="feature", how="left")
    else:
        filtered = filtered.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("bin_spread_abs"),
            pl.lit(None, dtype=pl.Utf8).alias("bin_spread_target"),
        )
    scored = filtered.with_columns(
        (
            pl.col("correlation_score").fill_null(0.0)
            + 0.10 * pl.col("bin_spread_abs").fill_null(0.0)
        ).alias("candidate_score")
    )
    rows: list[dict[str, Any]] = []
    for _, group in scored.sort("candidate_score", descending=True).group_by("family", maintain_order=True):
        rows.extend(group.sort("candidate_score", descending=True).head(per_family_limit).to_dicts())
    selected = (
        pl.DataFrame(rows, infer_schema_length=None)
        .sort("candidate_score", descending=True)
        .head(candidate_limit)
    )
    return selected, tuple(paths)


def run_catboost_shap_selection(
    *,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    feature_names: tuple[str, ...],
    num_features_to_select: int,
    steps: int,
    shap_calc_type: str,
    task_type: str,
    thread_count: int,
    model_config: Any,
) -> dict[str, Any]:
    try:
        from catboost import CatBoostRegressor, EFeaturesSelectionAlgorithm, EShapCalcType, Pool
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for SHAP panel selection") from exc
    params = build_catboost_params(model_config, task_type=task_type, thread_count=thread_count)
    train_pool = Pool(X_train, y_train, feature_names=list(feature_names))
    val_pool = Pool(X_val, y_val, feature_names=list(feature_names))
    shap_type = getattr(EShapCalcType, shap_calc_type)
    model = CatBoostRegressor(**params)
    try:
        summary = model.select_features(
            train_pool,
            eval_set=val_pool,
            features_for_select=list(range(len(feature_names))),
            num_features_to_select=int(num_features_to_select),
            steps=int(steps),
            algorithm=EFeaturesSelectionAlgorithm.RecursiveByShapValues,
            shap_calc_type=shap_type,
            train_final_model=False,
            logging_level="Silent",
            plot=False,
        )
    except Exception:
        if str(params.get("task_type")).upper() != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostRegressor(**params)
        summary = model.select_features(
            train_pool,
            eval_set=val_pool,
            features_for_select=list(range(len(feature_names))),
            num_features_to_select=int(num_features_to_select),
            steps=int(steps),
            algorithm=EFeaturesSelectionAlgorithm.RecursiveByShapValues,
            shap_calc_type=shap_type,
            train_final_model=False,
            logging_level="Silent",
            plot=False,
        )
    selected_names = summary.get("selected_features_names")
    if not selected_names:
        selected_names = [feature_names[int(index)] for index in summary.get("selected_features", [])]
    return {
        "selected_features_names": list(selected_names),
        "raw_summary": _jsonable(summary),
    }


def _load_best_bin_spreads(
    *,
    diagnostics_root: Path,
    asset: str,
    root_id: str,
    manifest_set: set[str],
    candidate_targets: set[str],
    min_bin_spread_abs: float,
) -> pl.DataFrame:
    paths = _diagnostic_paths(diagnostics_root, asset=asset, root_id=root_id, name="feature_bin_spreads.parquet")
    frames: list[pl.DataFrame] = []
    for path in paths:
        frame = pl.read_parquet(path)
        if not {"feature", "target", "high_minus_low"}.issubset(frame.columns):
            continue
        frames.append(
            frame.with_columns(
                pl.lit(str(path)).alias("bin_spread_source_path"),
                pl.lit(path.stat().st_mtime).alias("bin_spread_source_mtime"),
            )
        )
    if not frames:
        return pl.DataFrame(schema={"feature": pl.Utf8, "bin_spread_abs": pl.Float64, "bin_spread_target": pl.Utf8})
    spread = (
        pl.concat(frames, how="vertical")
        .filter(pl.col("feature").is_in(manifest_set))
        .filter(pl.col("target").is_in(candidate_targets))
        .with_columns(pl.col("high_minus_low").abs().alias("bin_spread_abs"))
        .filter(pl.col("bin_spread_abs").fill_null(0.0) >= float(min_bin_spread_abs))
        .sort(["feature", "bin_spread_abs"], descending=[False, True])
        .unique(subset=["feature"], keep="first", maintain_order=True)
        .select(
            [
                "feature",
                "target",
                "high_minus_low",
                "bin_spread_abs",
                "bin_spread_source_path",
                "bin_spread_source_mtime",
            ]
        )
        .rename({"target": "bin_spread_target"})
    )
    return spread


def _diagnostic_paths(diagnostics_root: Path, *, asset: str, root_id: str, name: str) -> tuple[Path, ...]:
    asset_slug = asset.lower()
    root_token = root_id.lower()
    patterns = (
        f"regression_feature_engineering_{asset_slug}_{root_token}*/**/{name}",
        f"regression_feature_engineering_{asset_slug}_all_roots/**/{name}",
    )
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(Path(diagnostics_root).glob(pattern))
    return tuple(sorted(set(paths), key=lambda path: str(path)))


def _candidate_targets(raw: str | None, target_col: str) -> tuple[str, ...]:
    if raw:
        return tuple(value.strip() for value in raw.split(",") if value.strip())
    return DEFAULT_CANDIDATE_TARGETS.get(target_col, (target_col,))


def _feature_family(feature: str) -> str:
    for family, prefixes in FAMILY_PREFIXES.items():
        if feature.startswith(prefixes):
            return family
    return "unknown"


def _run_root(args: argparse.Namespace, target_col: str) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_slug = target_col.replace("target_", "")[:40]
    return Path(args.output_dir) / f"{now}_shap_panel_{target_slug}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _panel_markdown(panel: dict[str, Any], candidates: pl.DataFrame) -> str:
    lines = [
        "# RPF Frozen SHAP Panel",
        "",
        f"- asset: `{panel['asset']}`",
        f"- root: `{panel['root']}`",
        f"- target: `{panel['target_col']}`",
        f"- candidate features: `{panel['candidate_feature_count']}`",
        f"- selected features: `{panel['selected_feature_count']}`",
        f"- algorithm: `{panel['selection_algorithm']}`",
        f"- shap calc type: `{panel['shap_calc_type']}`",
        "",
        "## Selected Features",
        "",
    ]
    lines.extend(f"- `{feature}`" for feature in panel["selected_features"])
    family_counts = (
        candidates.filter(pl.col("feature").is_in(panel["selected_features"]))
        .group_by("family")
        .len()
        .sort("len", descending=True)
        .to_dicts()
    )
    lines.extend(["", "## Selected Family Counts", ""])
    lines.extend(f"- `{row['family']}`: `{row['len']}`" for row in family_counts)
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a frozen RPF feature panel with CatBoost SHAP RFE.")
    parser.add_argument("--asset", default=None)
    parser.add_argument("--root", default=None)
    parser.add_argument("--target-col", default=None)
    parser.add_argument("--feature-ablation", default=None)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--diagnostics-root", type=Path, default=PROJECT_ROOT / "test_output")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--candidate-targets", default=None)
    parser.add_argument("--candidate-limit", type=int, default=240)
    parser.add_argument("--per-family-limit", type=int, default=40)
    parser.add_argument("--min-abs-spearman", type=float, default=0.02)
    parser.add_argument("--min-bin-spread-abs", type=float, default=0.0)
    parser.add_argument("--num-features-to-select", type=int, default=80)
    parser.add_argument("--selection-steps", type=int, default=3)
    parser.add_argument("--shap-calc-type", choices=["Approximate", "Regular", "Exact"], default="Exact")
    parser.add_argument("--window-index", type=int, default=0)
    parser.add_argument("--task-type", choices=["CPU", "GPU"], default="CPU")
    parser.add_argument("--thread-count", type=int, default=-1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())

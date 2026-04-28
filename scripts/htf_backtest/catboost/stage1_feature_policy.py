from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from .stage1_v2_contract import (
    STAGE1_V2_FIXED_POLICY_ARTIFACT_CONTRACT_VERSION,
    STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS,
    STAGE1_V2_STEP_ARTIFACTS,
)


@dataclass(frozen=True)
class Stage1V2FixedPolicyConfig:
    support_min_selected_steps: int = 40
    support_min_improved_steps: int = 10
    core_selection_rate_min: float = 0.80
    core_delta_accuracy_selected_lift_min: float = 0.0
    core_delta_cde_selected_lift_min: float = 0.0
    conditional_improved_selection_lift_min: float = 0.10
    conditional_delta_accuracy_selected_lift_min: float = 0.0
    conditional_delta_cde_selected_lift_min: float = 0.0
    avoid_selection_rate_min: float = 0.80
    avoid_delta_accuracy_selected_lift_max: float = 0.0
    avoid_delta_cde_selected_lift_max: float = 0.0
    min_features_keep: int = 24
    max_features_keep: int | None = None
    refresh_stride_steps: int = 25


def build_stage1_v2_fixed_policy_config(
    config: Stage1V2FixedPolicyConfig | dict[str, Any] | None = None,
) -> Stage1V2FixedPolicyConfig:
    if config is None:
        cfg = Stage1V2FixedPolicyConfig()
    elif isinstance(config, Stage1V2FixedPolicyConfig):
        cfg = config
    elif isinstance(config, dict):
        cfg = Stage1V2FixedPolicyConfig(**config)
    else:
        raise TypeError(
            "fixed_policy_config must be None, dict, or Stage1V2FixedPolicyConfig"
        )

    if int(cfg.support_min_selected_steps) < 1:
        raise ValueError("support_min_selected_steps must be >= 1")
    if int(cfg.support_min_improved_steps) < 1:
        raise ValueError("support_min_improved_steps must be >= 1")
    if not (0.0 <= float(cfg.core_selection_rate_min) <= 1.0):
        raise ValueError("core_selection_rate_min must be in [0, 1]")
    if not (0.0 <= float(cfg.conditional_improved_selection_lift_min) <= 1.0):
        raise ValueError("conditional_improved_selection_lift_min must be in [0, 1]")
    if not (0.0 <= float(cfg.avoid_selection_rate_min) <= 1.0):
        raise ValueError("avoid_selection_rate_min must be in [0, 1]")
    if int(cfg.min_features_keep) < 1:
        raise ValueError("min_features_keep must be >= 1")
    if cfg.max_features_keep is not None and int(cfg.max_features_keep) < int(
        cfg.min_features_keep
    ):
        raise ValueError("max_features_keep must be >= min_features_keep")
    if int(cfg.refresh_stride_steps) < 1:
        raise ValueError("refresh_stride_steps must be >= 1")

    return Stage1V2FixedPolicyConfig(
        support_min_selected_steps=int(cfg.support_min_selected_steps),
        support_min_improved_steps=int(cfg.support_min_improved_steps),
        core_selection_rate_min=float(cfg.core_selection_rate_min),
        core_delta_accuracy_selected_lift_min=float(
            cfg.core_delta_accuracy_selected_lift_min
        ),
        core_delta_cde_selected_lift_min=float(cfg.core_delta_cde_selected_lift_min),
        conditional_improved_selection_lift_min=float(
            cfg.conditional_improved_selection_lift_min
        ),
        conditional_delta_accuracy_selected_lift_min=float(
            cfg.conditional_delta_accuracy_selected_lift_min
        ),
        conditional_delta_cde_selected_lift_min=float(
            cfg.conditional_delta_cde_selected_lift_min
        ),
        avoid_selection_rate_min=float(cfg.avoid_selection_rate_min),
        avoid_delta_accuracy_selected_lift_max=float(
            cfg.avoid_delta_accuracy_selected_lift_max
        ),
        avoid_delta_cde_selected_lift_max=float(
            cfg.avoid_delta_cde_selected_lift_max
        ),
        min_features_keep=int(cfg.min_features_keep),
        max_features_keep=(
            None if cfg.max_features_keep is None else int(cfg.max_features_keep)
        ),
        refresh_stride_steps=int(cfg.refresh_stride_steps),
    )


def _resolve_run_dir(run_id_or_path: str | Path, project_root: Path) -> Path:
    path = Path(run_id_or_path)
    if path.exists():
        return path.resolve()
    run_dir = project_root / "data" / "htf_backtest_results" / str(run_id_or_path)
    if not run_dir.exists():
        raise FileNotFoundError(f"Stage-1 run not found: {run_id_or_path}")
    return run_dir.resolve()


def _required_policy_step_paths(step_dir: Path) -> dict[str, Path]:
    v2_dir = step_dir / "stage1_v2"
    return {
        "batch_metadata": step_dir / "batch_metadata.json",
        "combo_metrics": v2_dir / STAGE1_V2_STEP_ARTIFACTS["combo_metrics"],
        "feature_importance_steps": v2_dir
        / STAGE1_V2_STEP_ARTIFACTS["feature_importance_steps"],
        "selected_features": v2_dir / STAGE1_V2_STEP_ARTIFACTS["selected_features"],
        "summary": v2_dir / STAGE1_V2_STEP_ARTIFACTS["summary"],
    }


def _collect_completed_step_dirs(run_dir: Path) -> tuple[list[Path], list[dict[str, Any]]]:
    target_root = run_dir / "catboost"
    if not target_root.exists():
        return [], []

    completed: list[Path] = []
    incomplete: list[dict[str, Any]] = []
    for batch_meta in sorted(target_root.glob("*/target_*/batch_*/batch_metadata.json")):
        step_dir = batch_meta.parent
        files = _required_policy_step_paths(step_dir)
        missing = [name for name, path in files.items() if not path.exists()]
        if missing:
            incomplete.append(
                {
                    "step_dir": str(step_dir),
                    "pred_batch": int(step_dir.name.split("_")[1]),
                    "missing": missing,
                }
            )
            continue
        completed.append(step_dir)
    return completed, incomplete


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)


def _infer_root_context(run_dir: Path, run_config: dict[str, Any]) -> dict[str, Any]:
    run_id = str(run_config.get("run_id", run_dir.name))
    units = list(run_config.get("execution_units", []))
    first_unit = units[0] if units else {}
    match = re.search(
        r"stage1_catboost_(?P<regime>[^_]+)_(?P<family>[^_]+)_v2_live",
        run_id,
    )
    regime = match.group("regime") if match else None
    family = match.group("family").upper() if match else None
    return {
        "run_id": run_id,
        "regime": regime,
        "family": family,
        "timeframe": first_unit.get("timeframe"),
        "target": first_unit.get("target"),
        "feature_target": first_unit.get("feature_target"),
        "features_dir": first_unit.get("features_dir"),
        "labels_dir": first_unit.get("labels_dir"),
        "run_description": run_config.get("run_description"),
    }


def _build_per_combo_feature_stats(
    combo_paths: list[str],
    feature_paths: list[str],
) -> tuple[pl.DataFrame, pl.DataFrame]:
    combo_df = (
        pl.scan_parquet(combo_paths)
        .with_columns(
            [
                (pl.col("filtered_accuracy") - pl.col("baseline_accuracy")).alias(
                    "delta_accuracy"
                ),
                (
                    pl.col("baseline_cross_direction_error")
                    - pl.col("filtered_cross_direction_error")
                ).alias("delta_cde_improve"),
            ]
        )
        .collect()
    )

    joined = pl.scan_parquet(feature_paths).join(
        combo_df.lazy().select(
            [
                "pred_batch",
                "action_key",
                "combo_id",
                "apply_pruned_step",
                "improved_step",
                "delta_accuracy",
                "delta_cde_improve",
                "n_features_used",
                "selected_keep_count_request",
                "fold_count",
                "val_batches_per_fold",
                "train_batches_per_fold",
            ]
        ),
        on=["pred_batch", "action_key", "combo_id"],
        how="left",
    )

    per_combo_feature = (
        joined.group_by(["action_key", "feature"])
        .agg(
            [
                pl.len().alias("combo_steps"),
                pl.col("is_selected_step").cast(pl.Int64).sum().alias("selected_steps"),
                pl.col("apply_pruned_step")
                .cast(pl.Int64)
                .sum()
                .alias("accepted_pruned_steps"),
                pl.when(pl.col("improved_step"))
                .then(1)
                .otherwise(0)
                .sum()
                .alias("improved_steps"),
                pl.when(pl.col("improved_step") & pl.col("is_selected_step"))
                .then(1)
                .otherwise(0)
                .sum()
                .alias("selected_improved_steps"),
                pl.when((~pl.col("improved_step")) & pl.col("is_selected_step"))
                .then(1)
                .otherwise(0)
                .sum()
                .alias("selected_non_improved_steps"),
                pl.when(pl.col("apply_pruned_step") & pl.col("is_selected_step"))
                .then(1)
                .otherwise(0)
                .sum()
                .alias("selected_accepted_pruned_steps"),
                pl.col("importance")
                .filter(pl.col("is_selected_step"))
                .mean()
                .alias("importance_mean_selected"),
                pl.col("fold_vote_frac")
                .filter(pl.col("is_selected_step"))
                .mean()
                .alias("fold_vote_frac_mean_selected"),
                pl.col("delta_accuracy")
                .filter(pl.col("is_selected_step"))
                .mean()
                .alias("delta_accuracy_mean_selected"),
                pl.col("delta_accuracy")
                .filter(~pl.col("is_selected_step"))
                .mean()
                .alias("delta_accuracy_mean_not_selected"),
                pl.col("delta_cde_improve")
                .filter(pl.col("is_selected_step"))
                .mean()
                .alias("delta_cde_mean_selected"),
                pl.col("delta_cde_improve")
                .filter(~pl.col("is_selected_step"))
                .mean()
                .alias("delta_cde_mean_not_selected"),
                pl.col("n_features_used")
                .filter(pl.col("is_selected_step"))
                .mean()
                .alias("mean_mask_size_when_selected"),
            ]
        )
        .with_columns(
            [
                (pl.col("selected_steps") / pl.col("combo_steps")).alias(
                    "selection_rate_all"
                ),
                pl.when(pl.col("improved_steps") > 0)
                .then(pl.col("selected_improved_steps") / pl.col("improved_steps"))
                .otherwise(None)
                .alias("selection_rate_improved"),
                pl.when((pl.col("combo_steps") - pl.col("improved_steps")) > 0)
                .then(
                    pl.col("selected_non_improved_steps")
                    / (pl.col("combo_steps") - pl.col("improved_steps"))
                )
                .otherwise(None)
                .alias("selection_rate_non_improved"),
                pl.when(pl.col("accepted_pruned_steps") > 0)
                .then(
                    pl.col("selected_accepted_pruned_steps")
                    / pl.col("accepted_pruned_steps")
                )
                .otherwise(None)
                .alias("selection_rate_accepted_pruned"),
                (
                    pl.col("delta_accuracy_mean_selected")
                    - pl.col("delta_accuracy_mean_not_selected")
                ).alias("delta_accuracy_selected_lift"),
                (
                    pl.col("delta_cde_mean_selected")
                    - pl.col("delta_cde_mean_not_selected")
                ).alias("delta_cde_selected_lift"),
            ]
        )
        .with_columns(
            [
                (
                    pl.col("selection_rate_improved")
                    - pl.col("selection_rate_non_improved")
                ).alias("improved_selection_lift")
            ]
        )
        .sort(["action_key", "feature"])
        .collect()
    )

    combo_summary = (
        combo_df.group_by(
            ["action_key", "fold_count", "val_batches_per_fold", "train_batches_per_fold"]
        )
        .agg(
            [
                pl.len().alias("steps_seen"),
                pl.col("apply_pruned_step")
                .cast(pl.Int64)
                .sum()
                .alias("apply_pruned_steps"),
                pl.col("improved_step")
                .cast(pl.Int64)
                .sum()
                .alias("improved_steps"),
                pl.col("n_features_used")
                .filter(pl.col("apply_pruned_step") & pl.col("n_features_used").is_not_null())
                .median()
                .alias("accepted_mask_size_median"),
                pl.col("n_features_used")
                .filter(pl.col("apply_pruned_step") & pl.col("n_features_used").is_not_null())
                .mean()
                .alias("accepted_mask_size_mean"),
                pl.col("selected_keep_count_request")
                .filter(pl.col("selected_keep_count_request").is_not_null())
                .median()
                .alias("selected_keep_count_request_median"),
                pl.col("baseline_accuracy").mean().alias("baseline_accuracy_mean"),
                pl.col("filtered_accuracy").mean().alias("filtered_accuracy_mean"),
                pl.col("delta_accuracy").mean().alias("delta_accuracy_mean"),
                pl.col("baseline_cross_direction_error")
                .mean()
                .alias("baseline_cde_mean"),
                pl.col("filtered_cross_direction_error")
                .mean()
                .alias("filtered_cde_mean"),
                pl.col("delta_cde_improve").mean().alias("delta_cde_improve_mean"),
            ]
        )
        .sort("action_key")
    )
    return per_combo_feature, combo_summary


def _bool_positive(value: Any, threshold: float) -> bool:
    if value is None:
        return False
    return float(value) >= float(threshold)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _target_keep_count(combo_row: dict[str, Any], cfg: Stage1V2FixedPolicyConfig) -> int:
    candidate = combo_row.get("accepted_mask_size_median")
    if candidate is None:
        candidate = combo_row.get("selected_keep_count_request_median")
    if candidate is None:
        candidate = cfg.min_features_keep
    keep_count = int(round(float(candidate)))
    keep_count = max(int(cfg.min_features_keep), keep_count)
    if cfg.max_features_keep is not None:
        keep_count = min(keep_count, int(cfg.max_features_keep))
    return keep_count


def _feature_sort_tuple(row: dict[str, Any], bucket: str) -> tuple[Any, ...]:
    bucket_rank = {"core_keep": 0, "conditional_keep": 1, "neutral": 2, "avoid": 3}
    return (
        int(bucket_rank.get(bucket, 9)),
        -_safe_float(row.get("improved_selection_lift")),
        -_safe_float(row.get("delta_accuracy_selected_lift")),
        -_safe_float(row.get("delta_cde_selected_lift")),
        -_safe_float(row.get("selection_rate_all")),
        -_safe_float(row.get("importance_mean_selected")),
        str(row.get("feature", "")),
    )


def _mask_hash(mask: list[str]) -> str:
    payload = "\n".join(str(f) for f in mask).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _build_combo_policy(
    *,
    action_key: str,
    feature_rows: list[dict[str, Any]],
    combo_row: dict[str, Any],
    cfg: Stage1V2FixedPolicyConfig,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    target_keep_count = _target_keep_count(combo_row, cfg)
    bucket_by_feature: dict[str, str] = {}
    row_by_feature = {str(row["feature"]): row for row in feature_rows}

    core_keep: list[str] = []
    conditional_keep: list[str] = []
    avoid: list[str] = []

    for row in feature_rows:
        feature_name = str(row["feature"])
        selected_steps = int(row.get("selected_steps", 0) or 0)
        improved_steps = int(row.get("selected_improved_steps", 0) or 0)
        selection_rate_all = _safe_float(row.get("selection_rate_all"))
        acc_lift = _safe_float(row.get("delta_accuracy_selected_lift"))
        cde_lift = _safe_float(row.get("delta_cde_selected_lift"))
        improved_selection_lift = _safe_float(row.get("improved_selection_lift"))

        is_avoid = (
            selected_steps >= int(cfg.support_min_selected_steps)
            and selection_rate_all >= float(cfg.avoid_selection_rate_min)
            and acc_lift <= float(cfg.avoid_delta_accuracy_selected_lift_max)
            and cde_lift <= float(cfg.avoid_delta_cde_selected_lift_max)
        )
        if is_avoid:
            avoid.append(feature_name)
            bucket_by_feature[feature_name] = "avoid"
            continue

        is_core = (
            selected_steps >= int(cfg.support_min_selected_steps)
            and selection_rate_all >= float(cfg.core_selection_rate_min)
            and (
                _bool_positive(
                    acc_lift,
                    float(cfg.core_delta_accuracy_selected_lift_min),
                )
                or _bool_positive(
                    cde_lift,
                    float(cfg.core_delta_cde_selected_lift_min),
                )
            )
        )
        if is_core:
            core_keep.append(feature_name)
            bucket_by_feature[feature_name] = "core_keep"
            continue

        is_conditional = (
            improved_steps >= int(cfg.support_min_improved_steps)
            and improved_selection_lift
            >= float(cfg.conditional_improved_selection_lift_min)
            and (
                _bool_positive(
                    acc_lift,
                    float(cfg.conditional_delta_accuracy_selected_lift_min),
                )
                or _bool_positive(
                    cde_lift,
                    float(cfg.conditional_delta_cde_selected_lift_min),
                )
            )
        )
        if is_conditional:
            conditional_keep.append(feature_name)
            bucket_by_feature[feature_name] = "conditional_keep"
        else:
            bucket_by_feature[feature_name] = "neutral"

    ordered_candidates = sorted(
        [f for f in row_by_feature if bucket_by_feature.get(f) != "avoid"],
        key=lambda feature_name: _feature_sort_tuple(
            row_by_feature[feature_name],
            bucket_by_feature.get(feature_name, "neutral"),
        ),
    )

    final_mask = ordered_candidates[: int(target_keep_count)]
    if len(final_mask) < int(cfg.min_features_keep):
        fallback_avoid = sorted(
            avoid,
            key=lambda feature_name: _feature_sort_tuple(
                row_by_feature[feature_name],
                "avoid",
            ),
        )
        for feature_name in fallback_avoid:
            if feature_name in final_mask:
                continue
            final_mask.append(feature_name)
            if len(final_mask) >= int(cfg.min_features_keep):
                break

    final_mask = final_mask[: int(target_keep_count)]
    final_mask_set = set(final_mask)
    final_mask_rows = []
    for feature_name in final_mask:
        row = dict(row_by_feature[feature_name])
        row["action_key"] = str(action_key)
        row["feature"] = str(feature_name)
        row["policy_bucket"] = str(bucket_by_feature.get(feature_name, "neutral"))
        row["mask_role"] = "final_keep"
        final_mask_rows.append(row)

    combo_policy = {
        "mask_version": f"{action_key}_fixed_policy_v1",
        "mask_hash": _mask_hash(final_mask),
        "fold_count": int(combo_row.get("fold_count", 0) or 0),
        "val_batches_per_fold": int(combo_row.get("val_batches_per_fold", 0) or 0),
        "train_batches_per_fold": int(combo_row.get("train_batches_per_fold", 0) or 0),
        "target_keep_count": int(target_keep_count),
        "final_mask_count": int(len(final_mask)),
        "core_keep_count": int(sum(1 for f in final_mask if bucket_by_feature.get(f) == "core_keep")),
        "conditional_keep_count": int(
            sum(1 for f in final_mask if bucket_by_feature.get(f) == "conditional_keep")
        ),
        "neutral_keep_count": int(sum(1 for f in final_mask if bucket_by_feature.get(f) == "neutral")),
        "avoid_count": int(len(avoid)),
        "core_keep": [
            f for f in core_keep if f in final_mask_set
        ],
        "conditional_keep": [
            f for f in conditional_keep if f in final_mask_set
        ],
        "avoid": list(sorted(avoid)),
        "final_mask": list(final_mask),
        "support": {
            "steps_seen": int(combo_row.get("steps_seen", 0) or 0),
            "apply_pruned_steps": int(combo_row.get("apply_pruned_steps", 0) or 0),
            "improved_steps": int(combo_row.get("improved_steps", 0) or 0),
            "accepted_mask_size_median": combo_row.get("accepted_mask_size_median"),
            "accepted_mask_size_mean": combo_row.get("accepted_mask_size_mean"),
            "selected_keep_count_request_median": combo_row.get(
                "selected_keep_count_request_median"
            ),
        },
        "historical_means": {
            "baseline_accuracy": combo_row.get("baseline_accuracy_mean"),
            "filtered_accuracy": combo_row.get("filtered_accuracy_mean"),
            "delta_accuracy": combo_row.get("delta_accuracy_mean"),
            "baseline_cross_direction_error": combo_row.get("baseline_cde_mean"),
            "filtered_cross_direction_error": combo_row.get("filtered_cde_mean"),
            "delta_cross_direction_error_improve": combo_row.get(
                "delta_cde_improve_mean"
            ),
        },
    }
    return combo_policy, final_mask_rows


def build_stage1_v2_feature_policy(
    *,
    run_id_or_path: str | Path,
    project_root: str | Path,
    output_dir: str | Path | None = None,
    policy_version: str | None = None,
    config: Stage1V2FixedPolicyConfig | dict[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    run_dir = _resolve_run_dir(run_id_or_path, project_root)
    output_dir = run_dir if output_dir is None else Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = build_stage1_v2_fixed_policy_config(config)
    run_config = _read_json(run_dir / "run_config.json")
    root_context = _infer_root_context(run_dir, run_config)
    completed_steps, incomplete_steps = _collect_completed_step_dirs(run_dir)
    if not completed_steps:
        raise ValueError("No completed Stage-1-v2 steps with required artifacts were found.")

    combo_paths = [
        str((_required_policy_step_paths(step_dir)["combo_metrics"]).resolve())
        for step_dir in completed_steps
    ]
    feature_paths = [
        str((_required_policy_step_paths(step_dir)["feature_importance_steps"]).resolve())
        for step_dir in completed_steps
    ]
    per_combo_feature_stats, combo_summary = _build_per_combo_feature_stats(
        combo_paths=combo_paths,
        feature_paths=feature_paths,
    )

    completed_pred_batches = sorted(
        int(step_dir.name.split("_")[1]) for step_dir in completed_steps
    )
    if not policy_version:
        policy_version = (
            f"{root_context['run_id']}_fixed_policy_"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        )

    details_dir = output_dir / STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS["details_dir"]
    details_dir.mkdir(parents=True, exist_ok=True)

    combo_policies: dict[str, Any] = {}
    combo_policy_rows: list[dict[str, Any]] = []
    final_mask_rows: list[dict[str, Any]] = []
    for combo_row in combo_summary.to_dicts():
        action_key = str(combo_row["action_key"])
        feature_rows = (
            per_combo_feature_stats.filter(pl.col("action_key") == action_key)
            .sort(["selection_rate_all", "importance_mean_selected"], descending=[True, True])
            .to_dicts()
        )
        combo_policy, combo_final_mask_rows = _build_combo_policy(
            action_key=action_key,
            feature_rows=feature_rows,
            combo_row=combo_row,
            cfg=cfg,
        )
        combo_policies[action_key] = combo_policy
        combo_policy_rows.append(
            {
                "action_key": action_key,
                "mask_version": combo_policy["mask_version"],
                "mask_hash": combo_policy["mask_hash"],
                "fold_count": combo_policy["fold_count"],
                "val_batches_per_fold": combo_policy["val_batches_per_fold"],
                "train_batches_per_fold": combo_policy["train_batches_per_fold"],
                "target_keep_count": combo_policy["target_keep_count"],
                "final_mask_count": combo_policy["final_mask_count"],
                "core_keep_count": combo_policy["core_keep_count"],
                "conditional_keep_count": combo_policy["conditional_keep_count"],
                "neutral_keep_count": combo_policy["neutral_keep_count"],
                "avoid_count": combo_policy["avoid_count"],
                "steps_seen": combo_policy["support"]["steps_seen"],
                "apply_pruned_steps": combo_policy["support"]["apply_pruned_steps"],
                "improved_steps": combo_policy["support"]["improved_steps"],
                "baseline_accuracy_mean": combo_policy["historical_means"][
                    "baseline_accuracy"
                ],
                "filtered_accuracy_mean": combo_policy["historical_means"][
                    "filtered_accuracy"
                ],
                "delta_accuracy_mean": combo_policy["historical_means"][
                    "delta_accuracy"
                ],
                "baseline_cde_mean": combo_policy["historical_means"][
                    "baseline_cross_direction_error"
                ],
                "filtered_cde_mean": combo_policy["historical_means"][
                    "filtered_cross_direction_error"
                ],
                "delta_cde_improve_mean": combo_policy["historical_means"][
                    "delta_cross_direction_error_improve"
                ],
            }
        )
        final_mask_rows.extend(combo_final_mask_rows)

    per_combo_feature_path = details_dir / "per_combo_feature_stats.parquet"
    per_combo_feature_stats.write_parquet(per_combo_feature_path)
    per_combo_feature_stats.write_csv(details_dir / "per_combo_feature_stats.csv")

    combo_policy_df = pl.DataFrame(combo_policy_rows).sort("action_key")
    combo_policy_path = details_dir / "combo_policy_summary.parquet"
    combo_policy_df.write_parquet(combo_policy_path)
    combo_policy_df.write_csv(details_dir / "combo_policy_summary.csv")

    final_mask_df = pl.DataFrame(final_mask_rows).sort(["action_key", "policy_bucket", "feature"])
    final_mask_path = details_dir / "final_mask_features.parquet"
    final_mask_df.write_parquet(final_mask_path)
    final_mask_df.write_csv(details_dir / "final_mask_features.csv")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_contract_version": STAGE1_V2_FIXED_POLICY_ARTIFACT_CONTRACT_VERSION,
        "policy_version": str(policy_version),
        "source_run_id": str(root_context["run_id"]),
        "source_run_dir": str(run_dir),
        "root": {
            "regime": root_context.get("regime"),
            "family": root_context.get("family"),
            "timeframe": root_context.get("timeframe"),
            "target": root_context.get("target"),
            "feature_target": root_context.get("feature_target"),
            "features_dir": root_context.get("features_dir"),
            "labels_dir": root_context.get("labels_dir"),
        },
        "build_scope": {
            "completed_step_count": int(len(completed_steps)),
            "incomplete_step_count": int(len(incomplete_steps)),
            "pred_batch_min": int(min(completed_pred_batches)),
            "pred_batch_max": int(max(completed_pred_batches)),
            "completed_pred_batches": completed_pred_batches,
            "refresh_stride_steps": int(cfg.refresh_stride_steps),
        },
        "policy_rules": asdict(cfg),
        "stage1_v2_selector_config": run_config.get("stage1_v2_selector_config"),
        "combos": combo_policies,
    }

    registry_path = output_dir / STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS["registry"]
    with open(registry_path, "w") as f:
        json.dump(summary, f, indent=2)

    build_summary = {
        "generated_at": summary["generated_at"],
        "artifact_contract_version": STAGE1_V2_FIXED_POLICY_ARTIFACT_CONTRACT_VERSION,
        "policy_version": str(policy_version),
        "source_run_id": str(root_context["run_id"]),
        "source_run_dir": str(run_dir),
        "completed_step_count": int(len(completed_steps)),
        "incomplete_step_count": int(len(incomplete_steps)),
        "combo_count": int(combo_policy_df.height),
        "feature_count": int(
            per_combo_feature_stats.select(pl.col("feature").n_unique()).item()
        ),
        "artifacts": {
            "registry": str(registry_path),
            "per_combo_feature_stats": str(per_combo_feature_path),
            "combo_policy_summary": str(combo_policy_path),
            "final_mask_features": str(final_mask_path),
        },
        "incomplete_steps": incomplete_steps,
    }
    build_summary_path = output_dir / STAGE1_V2_FIXED_POLICY_ROOT_ARTIFACTS["build_summary"]
    with open(build_summary_path, "w") as f:
        json.dump(build_summary, f, indent=2)

    return {
        "summary": build_summary,
        "registry_path": str(registry_path),
        "build_summary_path": str(build_summary_path),
        "per_combo_feature_stats_path": str(per_combo_feature_path),
        "combo_policy_summary_path": str(combo_policy_path),
        "final_mask_features_path": str(final_mask_path),
    }


__all__ = [
    "Stage1V2FixedPolicyConfig",
    "build_stage1_v2_feature_policy",
    "build_stage1_v2_fixed_policy_config",
]

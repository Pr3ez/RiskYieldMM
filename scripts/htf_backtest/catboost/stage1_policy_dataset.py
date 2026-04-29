"""
Stage-1 Policy Dataset Builder (CatBoost)
=========================================

Build an offline state/action/reward dataset for autoregressive or RL-style
optimizer-policy training from Stage-1 artifacts.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl

from scripts.project_paths import resolve_project_root

from .stage1_reward import build_stage1_reward_table, load_stage1_reward_metadata


def _resolve_stage1_run_dir(run_id_or_path: str | Path, project_root: Path) -> Path:
    maybe_path = Path(run_id_or_path)
    if maybe_path.exists():
        return maybe_path
    run_dir = project_root / "data" / "htf_backtest_results" / str(run_id_or_path)
    if run_dir.exists():
        return run_dir
    raise FileNotFoundError(
        f"Stage-1 run not found from '{run_id_or_path}'. "
        f"Checked '{maybe_path}' and '{run_dir}'."
    )


def _collect_context_rows(run_dir: Path, model_name: str) -> pl.DataFrame:
    model_dir = run_dir / model_name
    if not model_dir.exists():
        raise FileNotFoundError(f"Model directory not found: {model_dir}")

    rows: list[pl.DataFrame] = []
    for tf_dir in sorted(model_dir.iterdir()):
        if not tf_dir.is_dir():
            continue
        tf = tf_dir.name
        for target_dir in sorted(tf_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            target = target_dir.name
            unit = f"{tf}/{target}"
            for batch_dir in sorted(target_dir.glob("batch_*")):
                try:
                    step_id = int(batch_dir.name.split("_")[1])
                except Exception:
                    continue
                ctx_path = batch_dir / "stage1" / "stage1_predecision_context.parquet"
                if not ctx_path.exists():
                    continue
                ctx = pl.read_parquet(ctx_path)
                if ctx.is_empty():
                    continue
                rows.append(
                    ctx.with_columns(
                        [
                            pl.lit(unit).alias("unit"),
                            pl.lit(tf).alias("timeframe"),
                            pl.lit(target).alias("target"),
                            pl.lit(int(step_id)).alias("step"),
                        ]
                    )
                )

    if not rows:
        return pl.DataFrame()
    return pl.concat(rows, how="diagonal").sort(["unit", "step"])


def _build_step_best(events_df: pl.DataFrame) -> pl.DataFrame:
    if events_df.is_empty():
        return pl.DataFrame()
    best_df = (
        events_df.sort(
            ["unit", "step", "selected_reward", "combo_id"],
            descending=[False, False, True, False],
        )
        .group_by(["unit", "timeframe", "target", "step"], maintain_order=True)
        .first()
        .rename(
            {
                "combo_id": "best_combo_id",
                "action_key": "best_action_key",
                "fold_count": "best_fold_count",
                "val_batches_per_fold": "best_val_batches_per_fold",
                "train_batches_per_fold": "best_train_batches_per_fold",
                "selected_reward": "best_selected_reward",
                "reward_validation": "best_reward_validation",
                "reward_prediction": "best_reward_prediction",
            }
        )
        .sort(["unit", "step"])
    )
    return best_df


def _attach_lag_features(step_best_df: pl.DataFrame, context_lags: int) -> pl.DataFrame:
    if step_best_df.is_empty() or context_lags <= 0:
        return step_best_df

    lagged = step_best_df
    for lag in range(1, int(context_lags) + 1):
        lagged = lagged.with_columns(
            [
                pl.col("best_combo_id").shift(lag).over("unit").alias(f"lag{lag}_best_combo_id"),
                pl.col("best_fold_count").shift(lag).over("unit").alias(f"lag{lag}_best_fold_count"),
                pl.col("best_val_batches_per_fold")
                .shift(lag)
                .over("unit")
                .alias(f"lag{lag}_best_val_batches_per_fold"),
                pl.col("best_train_batches_per_fold")
                .shift(lag)
                .over("unit")
                .alias(f"lag{lag}_best_train_batches_per_fold"),
                pl.col("best_selected_reward")
                .shift(lag)
                .over("unit")
                .alias(f"lag{lag}_best_selected_reward"),
            ]
        )
    return lagged


def build_stage1_policy_dataset(
    *,
    run_id_or_path: str | Path,
    project_root: str | Path | None = None,
    model_name: str = "catboost",
    reward_metadata_path: str | Path | None = None,
    selection_source: str = "prediction",
    reward_weights: dict[str, float] | None = None,
    context_lags: int = 3,
    write_latest: bool = True,
) -> dict[str, Any]:
    """
    Build stage-1 policy dataset from reward table + predecision context.

    If reward metadata does not exist, it is generated first from the same run.
    """
    project_root_path = (
        Path(project_root).expanduser().resolve()
        if project_root is not None
        else resolve_project_root(Path(__file__))
    )
    run_dir = _resolve_stage1_run_dir(run_id_or_path, project_root=project_root_path)
    run_id = run_dir.name

    meta_root = project_root_path / "data" / "htf_backtest_results" / "stage1_meta" / model_name
    out_dir = meta_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    if reward_metadata_path is None:
        reward_metadata_path = out_dir / "reward_metadata.json"

    reward_metadata_path = Path(reward_metadata_path)
    if not reward_metadata_path.exists():
        reward_meta = build_stage1_reward_table(
            run_id_or_path=run_dir,
            project_root=project_root_path,
            model_name=model_name,
            selection_source=selection_source,
            reward_weights=reward_weights,
            write_latest=write_latest,
        )
    else:
        reward_meta = load_stage1_reward_metadata(reward_metadata_path)

    reward_table_path = Path(reward_meta["artifacts"]["reward_table"])
    reward_df = pl.read_parquet(reward_table_path)
    if reward_df.is_empty():
        raise ValueError("Reward table is empty; cannot build policy dataset")

    context_df = _collect_context_rows(run_dir=run_dir, model_name=model_name)
    if context_df.is_empty():
        raise ValueError("No stage1_predecision_context.parquet files found")

    keys = ["unit", "timeframe", "target", "step"]
    events_df = reward_df.join(context_df, on=keys, how="left")

    step_best_df = _build_step_best(events_df)
    step_best_lagged_df = _attach_lag_features(step_best_df, context_lags=int(context_lags))

    lag_cols = [
        c
        for c in step_best_lagged_df.columns
        if c.startswith("lag") and c not in keys
    ]
    if lag_cols:
        events_df = events_df.join(
            step_best_lagged_df.select(keys + lag_cols),
            on=keys,
            how="left",
        )

    events_df = events_df.sort(["unit", "step", "combo_id"]).with_columns(
        [
            pl.col("step").rank("dense").over("unit").cast(pl.Int32).alias("step_order"),
            pl.col("selection_source").fill_null(str(selection_source)).alias("selection_source"),
        ]
    )

    state_cols = [
        c
        for c in context_df.columns
        if c not in {"unit", "timeframe", "target", "step"}
    ]
    action_cols = [
        "combo_id",
        "action_key",
        "fold_count",
        "val_batches_per_fold",
        "train_batches_per_fold",
    ]
    reward_cols = [
        "selected_reward",
        "reward_validation",
        "reward_prediction",
        "val_macro_f1",
        "val_cross_direction_error",
        "pred_macro_f1",
        "pred_cross_direction_error",
        "reward_rank",
        "is_step_best",
    ]

    events_path = out_dir / "policy_events.parquet"
    step_best_path = out_dir / "policy_step_best.parquet"
    events_df.write_parquet(events_path)
    step_best_lagged_df.write_parquet(step_best_path)

    metadata: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_run_id": run_id,
        "source_run_path": str(run_dir),
        "model_name": model_name,
        "context_lags": int(context_lags),
        "row_count_events": int(len(events_df)),
        "row_count_step_best": int(len(step_best_lagged_df)),
        "unit_count": int(events_df["unit"].n_unique()),
        "state_columns": state_cols,
        "action_columns": action_cols,
        "reward_columns": reward_cols,
        "artifacts": {
            "reward_table": str(reward_table_path),
            "policy_events": str(events_path),
            "policy_step_best": str(step_best_path),
        },
    }

    metadata_path = out_dir / "policy_dataset_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    if write_latest:
        latest_path = meta_root / "latest_policy_dataset_metadata.json"
        shutil.copyfile(metadata_path, latest_path)
        metadata["artifacts"]["latest_policy_dataset_metadata"] = str(latest_path)

    return metadata


__all__ = ["build_stage1_policy_dataset"]

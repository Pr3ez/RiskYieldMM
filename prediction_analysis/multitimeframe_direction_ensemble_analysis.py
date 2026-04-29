#!/usr/bin/env python3
"""Multi-timeframe direction ensemble analysis (all targets + all timeframes).

Analysis-only script:
- Loads prediction payloads for 6 units:
  1m/target_4class, 1m/target_breakfree,
  5m/target_4class, 5m/target_breakfree,
  15m/target_4class, 15m/target_breakfree
- Uses 12 candidates per unit
- Aligns all rows to 15m anchors
- Builds unit ensembles (uniform + winner_weighted)
- Builds target fusion (1m+5m+15m) and all-target fusion
- Evaluates directional quality against dual truths:
  - 15m/target_4class direction
  - 15m/target_breakfree direction (class 2 neutral excluded)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

_REPO_BOOTSTRAP_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_BOOTSTRAP_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_BOOTSTRAP_ROOT))

from scripts.project_paths import resolve_project_root  # noqa: E402

DEFAULT_PROJECT_ROOT = resolve_project_root(Path(__file__))
DEFAULT_RUN_ID = "stage1_catboost_live"
DEFAULT_MODEL_NAME = "catboost"
DEFAULT_SOURCE_SCOPE = "current+archive"
DEFAULT_OUTPUT_DIR = "prediction_analysis/multitimeframe_ensemble_outputs"
DEFAULT_UNITS = [
    "1m/target_4class",
    "1m/target_breakfree",
    "5m/target_4class",
    "5m/target_breakfree",
    "15m/target_4class",
    "15m/target_breakfree",
]
REQUIRED_UNITS_SET = set(DEFAULT_UNITS)
ROW_EXPECTED_BY_TIMEFRAME = {"1m": 15, "5m": 3, "15m": 1}
TARGETS = ["target_4class", "target_breakfree"]
VARIANTS = ["uniform", "winner_weighted"]
TRUTH_A = "truth_a_15m_target_4class"
TRUTH_B = "truth_b_15m_target_breakfree"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-timeframe directional ensemble analysis."
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=str(DEFAULT_PROJECT_ROOT),
        help=f"Project root (default: {DEFAULT_PROJECT_ROOT})",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=DEFAULT_RUN_ID,
        help=f"Stage-1 run id (default: {DEFAULT_RUN_ID})",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help=f"Model folder (default: {DEFAULT_MODEL_NAME})",
    )
    parser.add_argument(
        "--candidate-run-dir",
        type=str,
        default="",
        help=(
            "Candidate search run dir path or name under candidate_search_v2. "
            "Default: latest run containing 'post_backfill', else latest run."
        ),
    )
    parser.add_argument(
        "--candidate-sets-json",
        type=str,
        default="",
        help=(
            "Optional JSON file with explicit candidate action_keys per unit. "
            "When provided, overrides resolved candidate sets for listed units. "
            "Schema: {\"<unit>\": {\"action_keys\": [...12...], \"winner_wins\": {...optional...}}}"
        ),
    )
    parser.add_argument(
        "--source-scope",
        type=str,
        default=DEFAULT_SOURCE_SCOPE,
        choices=["current", "archive", "current+archive"],
        help=f"Prediction source scope (default: {DEFAULT_SOURCE_SCOPE})",
    )
    parser.add_argument(
        "--units",
        nargs="*",
        default=DEFAULT_UNITS,
        help="Units to analyze. Must include all required 6 units.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--output-tag",
        type=str,
        default="",
        help="Optional output run suffix.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose progress logs.",
    )
    parser.add_argument(
        "--live-walkforward",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run production-style walk-forward ensemble evaluation "
            "(history-only weights, no winner knowledge per current batch). "
            "Default: enabled."
        ),
    )
    parser.add_argument(
        "--live-beta-prior",
        type=float,
        default=1.0,
        help="Beta prior alpha=beta for online candidate-direction hit-rate weights.",
    )
    parser.add_argument(
        "--live-min-history",
        type=int,
        default=0,
        help=(
            "Minimum seen anchors per candidate before applying online weights; "
            "below this threshold, uniform fallback is used."
        ),
    )
    parser.add_argument(
        "--anchor-row-alignment",
        type=str,
        default="both",
        choices=["mean", "period_close", "both"],
        help=(
            "How to build per-15m candidate score from intraperiod rows: "
            "mean=average all rows in anchor; "
            "period_close=use closing row in anchor (1m=15th, 5m=3rd, 15m=1st); "
            "both=compute both and compare."
        ),
    )
    return parser.parse_args()


def _normalize_units(raw_units: list[str]) -> list[str]:
    units: list[str] = []
    for raw in raw_units:
        for part in str(raw).split(","):
            unit = part.strip()
            if not unit:
                continue
            if "/" not in unit:
                raise ValueError(f"Invalid unit format: {unit!r}")
            units.append(unit)
    seen: set[str] = set()
    out: list[str] = []
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            out.append(unit)
    return out


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    def sanitize(x: Any) -> Any:
        if isinstance(x, dict):
            return {str(k): sanitize(v) for k, v in x.items()}
        if isinstance(x, list):
            return [sanitize(v) for v in x]
        if isinstance(x, tuple):
            return [sanitize(v) for v in x]
        if isinstance(x, np.generic):
            return sanitize(x.item())
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return None
        return x

    with open(path, "w", encoding="utf-8") as f:
        json.dump(sanitize(payload), f, indent=2, ensure_ascii=False)


def _resolve_candidate_run_dir(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    candidate_run_dir_arg: str,
) -> Path:
    search_root = (
        project_root
        / "data"
        / "htf_backtest_results"
        / run_id
        / model_name
        / "candidate_search_v2"
    )
    if not search_root.exists():
        raise FileNotFoundError(f"candidate_search_v2 root not found: {search_root}")

    if candidate_run_dir_arg:
        direct = Path(candidate_run_dir_arg).expanduser()
        if direct.exists():
            return direct.resolve()
        child = search_root / candidate_run_dir_arg
        if child.exists():
            return child.resolve()
        raise FileNotFoundError(
            f"candidate run dir not found: {candidate_run_dir_arg!r} "
            f"(checked {direct} and {child})"
        )

    runs = sorted([p for p in search_root.glob("run_*") if p.is_dir()])
    if not runs:
        raise FileNotFoundError(f"No candidate_search_v2 runs found in {search_root}")
    post_backfill = [p for p in runs if "post_backfill" in p.name]
    if post_backfill:
        return post_backfill[-1].resolve()
    return runs[-1].resolve()


def _iter_snapshot_paths(step_stage1_dir: Path, source_scope: str):
    include_current = source_scope in {"current", "current+archive"}
    include_archive = source_scope in {"archive", "current+archive"}
    if include_current:
        combo_path = step_stage1_dir / "stage1_combo_index.parquet"
        pred_path = step_stage1_dir / "stage1_pred_batch_predictions.parquet"
        if combo_path.exists() and pred_path.exists():
            yield "current", combo_path, pred_path
    if include_archive:
        archive_root = step_stage1_dir / "archive_legacy"
        if archive_root.exists():
            for snap_dir in sorted([p for p in archive_root.iterdir() if p.is_dir()]):
                combo_path = snap_dir / "stage1_combo_index.parquet"
                pred_path = snap_dir / "stage1_pred_batch_predictions.parquet"
                if combo_path.exists() and pred_path.exists():
                    yield f"archive:{snap_dir.name}", combo_path, pred_path


def _resolve_candidate_sets(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    candidate_run_dir: Path,
    units: list[str],
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    for unit in units:
        tf, target = unit.split("/", 1)
        if unit == "1m/target_4class":
            winners_path = (
                project_root
                / "data"
                / "htf_backtest_results"
                / run_id
                / model_name
                / "1m"
                / "target_4class"
                / "winners_all_steps.parquet"
            )
            if not winners_path.exists():
                raise FileNotFoundError(f"Missing winners file: {winners_path}")
            winners = pl.read_parquet(winners_path)
            if "winner_combo_key" not in winners.columns:
                raise ValueError(f"{winners_path} missing winner_combo_key")
            freq = (
                winners.drop_nulls(["winner_combo_key"])
                .group_by("winner_combo_key")
                .len()
                .sort(["len", "winner_combo_key"], descending=[True, False])
            )
            if freq.height < 12:
                raise ValueError(
                    f"1m/target_4class has only {freq.height} winners, expected >=12"
                )
            top = freq.head(12)
            action_keys = [str(v) for v in top["winner_combo_key"].to_list()]
            winner_wins = {
                str(r["winner_combo_key"]): int(r["len"])
                for r in top.iter_rows(named=True)
            }
            out[unit] = {
                "source": "winners_all_steps_top12",
                "action_keys": action_keys,
                "winner_wins": winner_wins,
            }
            continue

        cand_path = candidate_run_dir / tf / target / "candidate12_v2.parquet"
        if not cand_path.exists():
            raise FileNotFoundError(f"Missing candidate file for {unit}: {cand_path}")
        cand = pl.read_parquet(cand_path).sort("candidate_rank")
        required_cols = {"action_key", "winner_wins"}
        missing_cols = sorted(required_cols - set(cand.columns))
        if missing_cols:
            raise ValueError(f"{cand_path} missing columns: {missing_cols}")
        action_keys = [str(v) for v in cand["action_key"].to_list()]
        if len(action_keys) != 12:
            raise ValueError(f"{unit} candidate count is {len(action_keys)}, expected 12")
        if len(set(action_keys)) != 12:
            raise ValueError(f"{unit} candidate set contains duplicates")
        winner_wins = {
            str(r["action_key"]): int(r["winner_wins"] or 0)
            for r in cand.iter_rows(named=True)
        }
        out[unit] = {
            "source": str(cand_path),
            "action_keys": action_keys,
            "winner_wins": winner_wins,
        }
    return out


def _apply_candidate_set_overrides(
    *,
    candidate_sets: dict[str, dict[str, Any]],
    candidate_sets_json_arg: str,
    units: list[str],
) -> dict[str, dict[str, Any]]:
    if not str(candidate_sets_json_arg).strip():
        return candidate_sets

    override_path = Path(str(candidate_sets_json_arg)).expanduser().resolve()
    if not override_path.exists():
        raise FileNotFoundError(f"candidate sets JSON not found: {override_path}")
    with open(override_path, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("candidate sets JSON must be an object keyed by unit")

    out = {k: dict(v) for k, v in candidate_sets.items()}
    for unit in units:
        node = payload.get(unit)
        if node is None:
            continue
        if not isinstance(node, dict):
            raise ValueError(f"override for {unit} must be an object")

        action_keys_raw = node.get("action_keys")
        if not isinstance(action_keys_raw, list):
            raise ValueError(f"override for {unit} missing action_keys list")
        action_keys = [str(v) for v in action_keys_raw]
        if len(action_keys) != 12:
            raise ValueError(f"override for {unit} has {len(action_keys)} action_keys, expected 12")
        if len(set(action_keys)) != 12:
            raise ValueError(f"override for {unit} action_keys contain duplicates")

        winner_wins_raw = node.get("winner_wins")
        if winner_wins_raw is not None and not isinstance(winner_wins_raw, dict):
            raise ValueError(f"override for {unit} winner_wins must be object when provided")

        base_wins = {str(k): int(v) for k, v in out[unit].get("winner_wins", {}).items()}
        resolved_wins = {k: int(base_wins.get(k, 0)) for k in action_keys}
        if isinstance(winner_wins_raw, dict):
            for k in action_keys:
                if k in winner_wins_raw:
                    resolved_wins[k] = int(winner_wins_raw.get(k) or 0)

        out[unit] = {
            "source": f"override_json:{override_path}",
            "action_keys": action_keys,
            "winner_wins": resolved_wins,
        }
    return out


def _load_unit_prediction_rows(
    *,
    project_root: Path,
    run_id: str,
    model_name: str,
    unit: str,
    action_keys: list[str],
    source_scope: str,
    verbose: bool,
) -> pl.DataFrame:
    tf, target = unit.split("/", 1)
    unit_dir = (
        project_root / "data" / "htf_backtest_results" / run_id / model_name / tf / target
    )
    if not unit_dir.exists():
        raise FileNotFoundError(f"Unit directory not found: {unit_dir}")

    action_set = set(action_keys)
    batch_dirs = sorted(
        [p for p in unit_dir.glob("batch_*") if p.is_dir()],
        key=lambda p: int(p.name.split("_")[1]),
    )

    frames: list[pl.DataFrame] = []
    for idx, batch_dir in enumerate(batch_dirs, start=1):
        pred_batch = int(batch_dir.name.split("_")[1])
        stage1_dir = batch_dir / "stage1"

        step_frames: list[pl.DataFrame] = []
        for snap_idx, (snap_label, combo_path, pred_path) in enumerate(
            _iter_snapshot_paths(stage1_dir, source_scope=source_scope)
        ):
            try:
                combo_df = pl.read_parquet(combo_path)
                pred_df = pl.read_parquet(pred_path)
            except Exception:
                continue
            if pred_df.is_empty() or combo_df.is_empty():
                continue
            if "scope" in pred_df.columns:
                pred_df = pred_df.filter(pl.col("scope") == "pred_batch")
            if pred_df.is_empty():
                continue

            if not {"combo_id", "action_key"}.issubset(set(combo_df.columns)):
                continue
            if not {"combo_id", "y_true", "y_pred", "timestamp", "batch_id"}.issubset(
                set(pred_df.columns)
            ):
                continue

            combo_map = (
                combo_df.select(["combo_id", "action_key"])
                .with_columns(
                    [
                        pl.col("combo_id").cast(pl.Int64, strict=False),
                        pl.col("action_key").cast(pl.Utf8, strict=False),
                    ]
                )
                .drop_nulls(["combo_id", "action_key"])
                .unique(subset=["combo_id"], keep="first")
            )
            pred_df = pred_df.with_columns(pl.col("combo_id").cast(pl.Int64, strict=False))
            if "action_key" in pred_df.columns:
                pred_df = pred_df.with_columns(
                    pl.col("action_key").cast(pl.Utf8, strict=False)
                ).join(combo_map, on="combo_id", how="left", suffix="_idx")
                pred_df = pred_df.with_columns(
                    pl.coalesce([pl.col("action_key"), pl.col("action_key_idx")]).alias(
                        "action_key"
                    )
                ).drop("action_key_idx")
            else:
                pred_df = pred_df.join(combo_map, on="combo_id", how="left")

            pred_df = pred_df.filter(pl.col("action_key").is_in(list(action_set)))
            if pred_df.is_empty():
                continue

            cols = [
                "timestamp",
                "batch_id",
                "action_key",
                "y_true",
                "y_pred",
            ]
            for c in ["prob_class_0", "prob_class_1", "prob_class_2", "prob_class_3"]:
                if c in pred_df.columns:
                    cols.append(c)
            take = pred_df.select(cols)

            for c in ["prob_class_0", "prob_class_1", "prob_class_2", "prob_class_3"]:
                if c not in take.columns:
                    take = take.with_columns(pl.lit(0.0).alias(c))

            take = take.with_columns(
                [
                    pl.lit(int(pred_batch)).alias("pred_batch"),
                    pl.lit(str(unit)).alias("unit"),
                    pl.lit(str(tf)).alias("timeframe"),
                    pl.lit(str(target)).alias("target"),
                    pl.lit(str(snap_label)).alias("snapshot_source"),
                    pl.lit(int(snap_idx)).alias("snapshot_rank"),
                ]
            ).select(
                [
                    "pred_batch",
                    "timestamp",
                    "batch_id",
                    "unit",
                    "timeframe",
                    "target",
                    "action_key",
                    "y_true",
                    "y_pred",
                    "prob_class_0",
                    "prob_class_1",
                    "prob_class_2",
                    "prob_class_3",
                    "snapshot_source",
                    "snapshot_rank",
                ]
            )
            step_frames.append(take)

        if step_frames:
            step_df = pl.concat(step_frames, how="diagonal_relaxed")
            step_df = (
                step_df.sort(
                    ["pred_batch", "timestamp", "batch_id", "action_key", "snapshot_rank"],
                    descending=[False, False, False, False, False],
                )
                .unique(
                    subset=["pred_batch", "timestamp", "batch_id", "action_key"],
                    keep="first",
                )
                .drop("snapshot_rank")
            )
            frames.append(step_df)

        if verbose and (idx == 1 or idx % 100 == 0 or idx == len(batch_dirs)):
            print(f"[{unit}] loaded step {idx}/{len(batch_dirs)}")

    if not frames:
        return pl.DataFrame(
            schema={
                "pred_batch": pl.Int64,
                "timestamp": pl.Datetime("ms"),
                "batch_id": pl.Int64,
                "unit": pl.Utf8,
                "timeframe": pl.Utf8,
                "target": pl.Utf8,
                "action_key": pl.Utf8,
                "y_true": pl.Int64,
                "y_pred": pl.Int64,
                "prob_class_0": pl.Float64,
                "prob_class_1": pl.Float64,
                "prob_class_2": pl.Float64,
                "prob_class_3": pl.Float64,
                "snapshot_source": pl.Utf8,
            }
        )

    df = pl.concat(frames, how="diagonal_relaxed")
    df = (
        df.sort(
            ["pred_batch", "timestamp", "batch_id", "action_key", "snapshot_source"],
            descending=[False, False, False, False, False],
        )
        .unique(
            subset=["pred_batch", "timestamp", "batch_id", "action_key"],
            keep="first",
        )
        .with_columns(
            [
                pl.col("pred_batch").cast(pl.Int64, strict=False),
                pl.col("batch_id").cast(pl.Int64, strict=False),
                pl.col("y_true").cast(pl.Int64, strict=False),
                pl.col("y_pred").cast(pl.Int64, strict=False),
                pl.col("action_key").cast(pl.Utf8, strict=False),
            ]
        )
        .sort(["pred_batch", "timestamp", "batch_id", "action_key"])
    )
    return df


def _add_direction_columns(df: pl.DataFrame) -> pl.DataFrame:
    out = df.with_columns(
        [
            pl.col("timestamp").dt.truncate("15m").alias("anchor_15m_ts"),
            pl.lit(0.0).alias("p_up"),
            pl.lit(0.0).alias("p_down"),
            pl.lit(0.0).alias("p_neutral"),
            pl.lit("UNKNOWN").alias("y_true_direction"),
            pl.lit("UNKNOWN").alias("y_pred_direction"),
        ]
    )

    out = out.with_columns(
        [
            pl.when(pl.col("target") == "target_4class")
            .then(pl.col("prob_class_2") + pl.col("prob_class_3"))
            .otherwise(pl.col("prob_class_0"))
            .alias("p_up"),
            pl.when(pl.col("target") == "target_4class")
            .then(pl.col("prob_class_0") + pl.col("prob_class_1"))
            .otherwise(pl.col("prob_class_1"))
            .alias("p_down"),
            pl.when(pl.col("target") == "target_breakfree")
            .then(pl.col("prob_class_2"))
            .otherwise(pl.lit(0.0))
            .alias("p_neutral"),
        ]
    )

    out = out.with_columns(
        [
            (
                pl.when((pl.col("target") == "target_4class") & pl.col("y_true").is_in([0, 1]))
                .then(pl.lit("DOWN"))
                .when((pl.col("target") == "target_4class") & pl.col("y_true").is_in([2, 3]))
                .then(pl.lit("UP"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_true") == 0))
                .then(pl.lit("UP"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_true") == 1))
                .then(pl.lit("DOWN"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_true") == 2))
                .then(pl.lit("NEUTRAL"))
                .otherwise(pl.lit("UNKNOWN"))
            ).alias("y_true_direction"),
            (
                pl.when((pl.col("target") == "target_4class") & pl.col("y_pred").is_in([0, 1]))
                .then(pl.lit("DOWN"))
                .when((pl.col("target") == "target_4class") & pl.col("y_pred").is_in([2, 3]))
                .then(pl.lit("UP"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_pred") == 0))
                .then(pl.lit("UP"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_pred") == 1))
                .then(pl.lit("DOWN"))
                .when((pl.col("target") == "target_breakfree") & (pl.col("y_pred") == 2))
                .then(pl.lit("NEUTRAL"))
                .otherwise(pl.lit("UNKNOWN"))
            ).alias("y_pred_direction"),
        ]
    )
    out = out.with_columns((pl.col("p_up") - pl.col("p_down")).alias("dir_score_row"))
    return out


def _build_anchor_candidate_scores(
    *,
    unit_rows: pl.DataFrame,
    mode: str,
) -> pl.DataFrame:
    if mode == "mean":
        out = (
            unit_rows.group_by(
                ["pred_batch", "anchor_15m_ts", "unit", "timeframe", "target", "action_key"]
            )
            .agg(
                [
                    pl.len().alias("row_count"),
                    pl.col("dir_score_row").mean().alias("dir_score_anchor"),
                    pl.col("p_up").mean().alias("p_up_mean"),
                    pl.col("p_down").mean().alias("p_down_mean"),
                    pl.col("p_neutral").mean().alias("p_neutral_mean"),
                ]
            )
            .with_columns(
                [
                    pl.col("timeframe")
                    .replace_strict(ROW_EXPECTED_BY_TIMEFRAME)
                    .cast(pl.Int64)
                    .alias("row_count_expected"),
                ]
            )
            .with_columns(
                (pl.col("row_count") == pl.col("row_count_expected")).alias(
                    "row_count_match"
                )
            )
            .sort(["pred_batch", "anchor_15m_ts", "unit", "action_key"])
            .with_columns(pl.lit("anchor_mean").alias("alignment_mode"))
        )
        return _normalize_anchor_ts(out)

    if mode == "period_close":
        key_cols = ["pred_batch", "anchor_15m_ts", "unit", "timeframe", "target", "action_key"]
        ordered = (
            unit_rows.sort(
                ["pred_batch", "anchor_15m_ts", "unit", "action_key", "timestamp", "batch_id"],
                descending=[False, False, False, False, False, False],
            )
            .with_columns(
                [
                    pl.col("timestamp").cum_count().over(key_cols).alias("row_pos"),
                    pl.len().over(key_cols).alias("row_count"),
                ]
            )
            .with_columns(
                pl.col("timeframe")
                .replace_strict(ROW_EXPECTED_BY_TIMEFRAME)
                .cast(pl.Int64)
                .alias("row_count_expected")
            )
            .filter(pl.col("row_pos") == pl.col("row_count_expected"))
            .select(
                key_cols
                + [
                    "row_count",
                    "row_count_expected",
                    "dir_score_row",
                    "p_up",
                    "p_down",
                    "p_neutral",
                ]
            )
            .rename(
                {
                    "dir_score_row": "dir_score_anchor",
                    "p_up": "p_up_mean",
                    "p_down": "p_down_mean",
                    "p_neutral": "p_neutral_mean",
                }
            )
            .with_columns(
                [
                    (pl.col("row_count") == pl.col("row_count_expected")).alias(
                        "row_count_match"
                    ),
                    pl.lit("same_period_close").alias("alignment_mode"),
                ]
            )
            .sort(["pred_batch", "anchor_15m_ts", "unit", "action_key"])
        )
        return _normalize_anchor_ts(ordered)

    raise ValueError(f"Unsupported anchor candidate mode: {mode}")


def _build_static_streams_from_candidate_scores(
    *,
    anchor_candidate_scores: pl.DataFrame,
    weights_df: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    anchor_with_weights = anchor_candidate_scores.join(
        weights_df, on=["unit", "action_key"], how="left"
    )
    if anchor_with_weights.filter(pl.col("weight_uniform").is_null()).height > 0:
        raise RuntimeError("Missing weights for some unit/action rows.")

    grouped = (
        anchor_with_weights.group_by(
            [
                "alignment_mode",
                "pred_batch",
                "anchor_15m_ts",
                "unit",
                "timeframe",
                "target",
            ]
        )
        .agg(
            [
                pl.col("action_key").n_unique().alias("candidate_count_present"),
                pl.len().alias("candidate_rows_present"),
                pl.col("row_count").sum().alias("row_count_total"),
                pl.col("row_count_expected").first().alias("row_count_expected_per_candidate"),
                pl.col("weight_uniform").sum().alias("weight_uniform_sum_present"),
                pl.col("weight_winner").sum().alias("weight_winner_sum_present"),
                (pl.col("dir_score_anchor") * pl.col("weight_uniform")).sum().alias("uniform_num"),
                (pl.col("dir_score_anchor") * pl.col("weight_winner")).sum().alias("winner_num"),
            ]
        )
        .with_columns(
            [
                (pl.col("row_count_expected_per_candidate") * pl.lit(12)).alias("row_count_expected_total"),
                (pl.col("candidate_count_present") / pl.lit(12.0)).alias("candidate_coverage_rate"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("weight_uniform_sum_present") > 0)
                .then(pl.col("uniform_num") / pl.col("weight_uniform_sum_present"))
                .otherwise(None)
                .alias("score_uniform"),
                pl.when(pl.col("weight_winner_sum_present") > 0)
                .then(pl.col("winner_num") / pl.col("weight_winner_sum_present"))
                .otherwise(None)
                .alias("score_winner_weighted"),
            ]
        )
    )

    unit_uniform = grouped.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "unit",
            "timeframe",
            "target",
            pl.lit("uniform").alias("variant"),
            pl.col("score_uniform").alias("ensemble_score"),
            "candidate_count_present",
            "candidate_rows_present",
            "candidate_coverage_rate",
            "row_count_total",
            "row_count_expected_total",
        ]
    )
    unit_weighted = grouped.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "unit",
            "timeframe",
            "target",
            pl.lit("winner_weighted").alias("variant"),
            pl.col("score_winner_weighted").alias("ensemble_score"),
            "candidate_count_present",
            "candidate_rows_present",
            "candidate_coverage_rate",
            "row_count_total",
            "row_count_expected_total",
        ]
    )
    anchor_unit_ensemble = pl.concat([unit_uniform, unit_weighted], how="diagonal_relaxed").with_columns(
        [
            _score_to_direction_expr("ensemble_score").alias("pred_direction"),
            pl.col("ensemble_score").abs().alias("abs_score"),
        ]
    ).sort(["alignment_mode", "pred_batch", "anchor_15m_ts", "variant", "unit"])
    anchor_unit_ensemble = _normalize_anchor_ts(anchor_unit_ensemble)

    target_rows: list[pl.DataFrame] = []
    for alignment_mode in (
        anchor_unit_ensemble.select("alignment_mode")
        .unique()
        .sort("alignment_mode")["alignment_mode"]
        .to_list()
    ):
        for target in TARGETS:
            sub = anchor_unit_ensemble.filter(
                (pl.col("alignment_mode") == alignment_mode) & (pl.col("target") == target)
            )
            for variant in VARIANTS:
                sv = sub.filter(pl.col("variant") == variant)
                pivot = sv.pivot(
                    index=[
                        "alignment_mode",
                        "pred_batch",
                        "anchor_15m_ts",
                        "target",
                        "variant",
                    ],
                    on="timeframe",
                    values="ensemble_score",
                    aggregate_function="first",
                )
                for tf in ["1m", "5m", "15m"]:
                    if tf not in pivot.columns:
                        pivot = pivot.with_columns(pl.lit(None).cast(pl.Float64).alias(tf))
                pivot = pivot.with_columns(
                    [
                        (
                            pl.col("1m").is_not_null()
                            + pl.col("5m").is_not_null()
                            + pl.col("15m").is_not_null()
                        )
                        .cast(pl.Int64)
                        .alias("timeframes_present"),
                    ]
                ).with_columns(
                    [
                        pl.when(pl.col("timeframes_present") == 3)
                        .then(
                            (
                                pl.lit(15.0) * pl.col("1m")
                                + pl.lit(3.0) * pl.col("5m")
                                + pl.col("15m")
                            )
                            / pl.lit(19.0)
                        )
                        .otherwise(None)
                        .alias("score_target")
                    ]
                ).with_columns(
                    [
                        _score_to_direction_expr("score_target").alias("pred_direction"),
                        pl.col("score_target").abs().alias("abs_score"),
                    ]
                )
                target_rows.append(pivot)

    anchor_target_fusion = pl.concat(target_rows, how="diagonal_relaxed").sort(
        ["alignment_mode", "pred_batch", "anchor_15m_ts", "target", "variant"]
    )
    anchor_target_fusion = _normalize_anchor_ts(anchor_target_fusion)

    t4 = anchor_target_fusion.filter(pl.col("target") == "target_4class").select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "variant",
            pl.col("score_target").alias("score_4class"),
            pl.col("pred_direction").alias("dir_4class"),
        ]
    )
    tb = anchor_target_fusion.filter(pl.col("target") == "target_breakfree").select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "variant",
            pl.col("score_target").alias("score_breakfree"),
            pl.col("pred_direction").alias("dir_breakfree"),
        ]
    )
    anchor_all_fusion = (
        t4.join(
            tb,
            on=["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"],
            how="inner",
        )
        .with_columns(
            [
                ((pl.col("score_4class") + pl.col("score_breakfree")) * pl.lit(0.5)).alias(
                    "score_all"
                ),
            ]
        )
        .with_columns(
            [
                _score_to_direction_expr("score_all").alias("pred_direction"),
                pl.col("score_all").abs().alias("abs_score"),
            ]
        )
        .sort(["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"])
    )
    anchor_all_fusion = _normalize_anchor_ts(anchor_all_fusion)

    stream_unit = anchor_unit_ensemble.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            pl.lit("unit").alias("stream_level"),
            pl.col("unit").alias("stream_name"),
            "variant",
            "target",
            "timeframe",
            pl.col("ensemble_score").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_target = anchor_target_fusion.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            pl.lit("target").alias("stream_level"),
            pl.concat_str([pl.lit("target::"), pl.col("target")]).alias("stream_name"),
            "variant",
            "target",
            pl.lit(None).cast(pl.Utf8).alias("timeframe"),
            pl.col("score_target").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_all = anchor_all_fusion.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            pl.lit("all").alias("stream_level"),
            pl.lit("all_targets").alias("stream_name"),
            "variant",
            pl.lit("all_targets").alias("target"),
            pl.lit(None).cast(pl.Utf8).alias("timeframe"),
            pl.col("score_all").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_scores = pl.concat([stream_unit, stream_target, stream_all], how="diagonal_relaxed").sort(
        ["alignment_mode", "stream_level", "stream_name", "variant", "pred_batch", "anchor_15m_ts"]
    )
    return anchor_unit_ensemble, anchor_target_fusion, anchor_all_fusion, stream_scores


def _build_weights(candidate_sets: dict[str, dict[str, Any]]) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for unit, meta in candidate_sets.items():
        action_keys = list(meta["action_keys"])
        wins = meta.get("winner_wins", {})
        uniform = 1.0 / float(len(action_keys))
        denom = sum(float(wins.get(k, 0)) + 1.0 for k in action_keys)
        for k in action_keys:
            winner_weight = (float(wins.get(k, 0)) + 1.0) / float(denom)
            rows.append(
                {
                    "unit": unit,
                    "action_key": str(k),
                    "weight_uniform": float(uniform),
                    "weight_winner": float(winner_weight),
                    "winner_wins": int(wins.get(k, 0)),
                }
            )
    return pl.DataFrame(rows).sort(["unit", "action_key"])


def _score_to_direction_expr(col_name: str) -> pl.Expr:
    return (
        pl.when(pl.col(col_name) > 0.0)
        .then(pl.lit("UP"))
        .when(pl.col(col_name) < 0.0)
        .then(pl.lit("DOWN"))
        .otherwise(pl.lit("NO_SIGNAL"))
    )


def _normalize_anchor_ts(df: pl.DataFrame) -> pl.DataFrame:
    if "anchor_15m_ts" not in df.columns:
        return df
    return df.with_columns(
        pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False)
    )


def _prepare_anchor_truths(unit_rows: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, Any]]:
    truth4 = (
        unit_rows.filter(pl.col("unit") == "15m/target_4class")
        .group_by(["pred_batch", "anchor_15m_ts"])
        .agg(
            [
                pl.col("y_true").n_unique().alias("y_true_n_unique"),
                pl.col("y_true").first().alias("y_true_4class"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("y_true_4class").is_in([0, 1]))
                .then(pl.lit("DOWN"))
                .when(pl.col("y_true_4class").is_in([2, 3]))
                .then(pl.lit("UP"))
                .otherwise(pl.lit("UNKNOWN"))
                .alias("truth_a_direction")
            ]
        )
    )
    truthb = (
        unit_rows.filter(pl.col("unit") == "15m/target_breakfree")
        .group_by(["pred_batch", "anchor_15m_ts"])
        .agg(
            [
                pl.col("y_true").n_unique().alias("y_true_n_unique_breakfree"),
                pl.col("y_true").first().alias("y_true_breakfree"),
            ]
        )
        .with_columns(
            [
                pl.when(pl.col("y_true_breakfree") == 0)
                .then(pl.lit("UP"))
                .when(pl.col("y_true_breakfree") == 1)
                .then(pl.lit("DOWN"))
                .when(pl.col("y_true_breakfree") == 2)
                .then(pl.lit("NEUTRAL"))
                .otherwise(pl.lit("UNKNOWN"))
                .alias("truth_b_direction")
            ]
        )
    )

    anchor_truth = truth4.join(
        truthb.select(
            [
                "pred_batch",
                "anchor_15m_ts",
                "truth_b_direction",
                "y_true_n_unique_breakfree",
            ]
        ),
        on=["pred_batch", "anchor_15m_ts"],
        how="inner",
    ).sort(["pred_batch", "anchor_15m_ts"])

    diagnostics = {
        "anchor_universe_count": int(anchor_truth.height),
        "truth_4class_label_conflicts": int((truth4["y_true_n_unique"] > 1).sum())
        if truth4.height
        else 0,
        "truth_breakfree_label_conflicts": int(
            (truthb["y_true_n_unique_breakfree"] > 1).sum()
        )
        if truthb.height
        else 0,
        "truth_b_neutral_count": int((anchor_truth["truth_b_direction"] == "NEUTRAL").sum())
        if anchor_truth.height
        else 0,
    }
    return anchor_truth, diagnostics


def _evaluate_stream(
    *,
    eval_df: pl.DataFrame,
    stream_name: str,
    stream_level: str,
    variant: str,
    truth_name: str,
) -> dict[str, Any]:
    if truth_name == TRUTH_A:
        truth_col = "truth_a_direction"
        eligible = eval_df.filter(pl.col(truth_col).is_in(["UP", "DOWN"]))
    elif truth_name == TRUTH_B:
        truth_col = "truth_b_direction"
        eligible = eval_df.filter(pl.col(truth_col).is_in(["UP", "DOWN"]))
    else:
        raise ValueError(f"Unknown truth: {truth_name}")

    n = int(eligible.height)
    if n == 0:
        return {
            "stream_level": stream_level,
            "stream_name": stream_name,
            "variant": variant,
            "truth_name": truth_name,
            "eligible_count": 0,
            "covered_count": 0,
            "coverage_rate": 0.0,
            "directional_accuracy_on_covered": None,
            "conditional_hit_rate": None,
            "miss_rate": None,
            "abstain_rate": None,
            "recall_up": None,
            "recall_down": None,
            "balanced_directional_recall": None,
            "mean_abs_score": None,
        }

    covered = eligible.filter(pl.col("pred_direction").is_in(["UP", "DOWN"]))
    covered_n = int(covered.height)
    correct_n = (
        int((covered["pred_direction"] == covered[truth_col]).sum()) if covered_n > 0 else 0
    )
    wrong_n = int(covered_n - correct_n)
    accuracy_cov = (float(correct_n) / float(covered_n)) if covered_n > 0 else None
    coverage_rate = float(covered_n) / float(n)
    miss_rate = float(wrong_n) / float(n)
    abstain_rate = float(n - covered_n) / float(n)

    def recall_for(direction: str) -> float | None:
        den = int((eligible[truth_col] == direction).sum())
        if den == 0:
            return None
        num = int(((eligible[truth_col] == direction) & (eligible["pred_direction"] == direction)).sum())
        return float(num) / float(den)

    recall_up = recall_for("UP")
    recall_down = recall_for("DOWN")
    recall_values = [v for v in [recall_up, recall_down] if v is not None]
    balanced_recall = float(np.mean(recall_values)) if recall_values else None

    return {
        "stream_level": stream_level,
        "stream_name": stream_name,
        "variant": variant,
        "truth_name": truth_name,
        "eligible_count": n,
        "covered_count": covered_n,
        "coverage_rate": coverage_rate,
        "directional_accuracy_on_covered": accuracy_cov,
        "conditional_hit_rate": accuracy_cov,
        "miss_rate": miss_rate,
        "abstain_rate": abstain_rate,
        "recall_up": recall_up,
        "recall_down": recall_down,
        "balanced_directional_recall": balanced_recall,
        "mean_abs_score": (
            None
            if ("abs_score" not in eligible.columns or n <= 0)
            else (
                None
                if eligible["abs_score"].mean() is None
                else float(eligible["abs_score"].mean())
            )
        ),
    }


def _confidence_bins(stream_df: pl.DataFrame, truth_col: str) -> list[dict[str, Any]]:
    eligible = stream_df.filter(pl.col(truth_col).is_in(["UP", "DOWN"]))
    if eligible.height < 10:
        return []
    arr = eligible["abs_score"].to_numpy()
    if arr.size == 0:
        return []
    edges = np.quantile(arr, np.linspace(0.0, 1.0, 11))
    edges = np.unique(edges)
    if edges.size < 2:
        return []
    # Ensure rightmost edge includes max value.
    edges[0] = -np.inf
    edges[-1] = np.inf
    bins = np.digitize(arr, edges[1:-1], right=True) + 1
    rows: list[dict[str, Any]] = []
    pred = eligible["pred_direction"].to_numpy()
    truth = eligible[truth_col].to_numpy()
    for b in sorted(set(int(v) for v in bins.tolist())):
        idx = bins == b
        if not idx.any():
            continue
        n = int(idx.sum())
        pred_b = pred[idx]
        truth_b = truth[idx]
        covered_mask = np.isin(pred_b, ["UP", "DOWN"])
        covered_n = int(covered_mask.sum())
        correct_n = int(np.sum(pred_b[covered_mask] == truth_b[covered_mask])) if covered_n > 0 else 0
        rows.append(
            {
                "bin_idx": int(b),
                "bin_count": n,
                "covered_count": covered_n,
                "coverage_rate": float(covered_n) / float(n),
                "conditional_hit_rate": (float(correct_n) / float(covered_n)) if covered_n > 0 else None,
                "hit_rate_total": float(correct_n) / float(n),
                "abs_score_min": float(np.min(arr[idx])),
                "abs_score_max": float(np.max(arr[idx])),
                "abs_score_mean": float(np.mean(arr[idx])),
            }
        )
    return rows


def _evaluate_stream_scores(
    *,
    stream_scores: pl.DataFrame,
    anchor_truth: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    eval_base = stream_scores.join(
        anchor_truth.select(
            ["pred_batch", "anchor_15m_ts", "truth_a_direction", "truth_b_direction"]
        ),
        on=["pred_batch", "anchor_15m_ts"],
        how="left",
    )

    eval_rows: list[dict[str, Any]] = []
    eval_batch_frames: list[pl.DataFrame] = []
    conf_rows: list[dict[str, Any]] = []
    group_keys = ["stream_level", "stream_name", "variant"]
    if "alignment_mode" in eval_base.columns:
        group_keys = ["alignment_mode"] + group_keys

    grouped_streams = eval_base.group_by(group_keys, maintain_order=True)
    for key, sub in grouped_streams:
        if "alignment_mode" in eval_base.columns:
            alignment_mode = str(key[0])
            stream_level = str(key[1])
            stream_name = str(key[2])
            variant = str(key[3])
        else:
            alignment_mode = "anchor_mean"
            stream_level = str(key[0])
            stream_name = str(key[1])
            variant = str(key[2])

        for truth_name in [TRUTH_A, TRUTH_B]:
            row = _evaluate_stream(
                eval_df=sub,
                stream_name=stream_name,
                stream_level=stream_level,
                variant=variant,
                truth_name=truth_name,
            )
            row["alignment_mode"] = alignment_mode
            eval_rows.append(row)

            truth_col = "truth_a_direction" if truth_name == TRUTH_A else "truth_b_direction"
            bins = _confidence_bins(sub, truth_col=truth_col)
            for b in bins:
                conf_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "stream_level": stream_level,
                        "stream_name": stream_name,
                        "variant": variant,
                        "truth_name": truth_name,
                        **b,
                    }
                )

            batch_rows: list[dict[str, Any]] = []
            for bkey, bdf in sub.group_by("pred_batch", maintain_order=True):
                pred_batch = int(bkey[0] if isinstance(bkey, tuple) else bkey)
                m = _evaluate_stream(
                    eval_df=bdf,
                    stream_name=stream_name,
                    stream_level=stream_level,
                    variant=variant,
                    truth_name=truth_name,
                )
                m["alignment_mode"] = alignment_mode
                m["pred_batch"] = pred_batch
                batch_rows.append(m)
            eval_batch_frames.append(pl.DataFrame(batch_rows))

    evaluation_dual = pl.DataFrame(eval_rows).sort(
        ["alignment_mode", "truth_name", "stream_level", "stream_name", "variant"]
    )
    evaluation_by_batch = pl.concat(eval_batch_frames, how="diagonal_relaxed").sort(
        [
            "alignment_mode",
            "truth_name",
            "stream_level",
            "stream_name",
            "variant",
            "pred_batch",
        ]
    )
    confidence_bins = (
        pl.DataFrame(conf_rows).sort(
            [
                "alignment_mode",
                "truth_name",
                "stream_level",
                "stream_name",
                "variant",
                "bin_idx",
            ]
        )
        if conf_rows
        else pl.DataFrame(
            schema={
                "alignment_mode": pl.Utf8,
                "stream_level": pl.Utf8,
                "stream_name": pl.Utf8,
                "variant": pl.Utf8,
                "truth_name": pl.Utf8,
                "bin_idx": pl.Int64,
                "bin_count": pl.Int64,
                "covered_count": pl.Int64,
                "coverage_rate": pl.Float64,
                "conditional_hit_rate": pl.Float64,
                "hit_rate_total": pl.Float64,
                "abs_score_min": pl.Float64,
                "abs_score_max": pl.Float64,
                "abs_score_mean": pl.Float64,
            }
        )
    )
    return evaluation_dual, evaluation_by_batch, confidence_bins


def _build_live_walkforward_ensembles(
    *,
    anchor_candidate_scores: pl.DataFrame,
    anchor_truth: pl.DataFrame,
    candidate_sets: dict[str, dict[str, Any]],
    beta_prior: float,
    min_history: int,
    alignment_mode: str,
) -> dict[str, pl.DataFrame]:
    live_variants = ["live_uniform", "live_online_beta"]
    truth_rows = (
        anchor_truth.sort(["pred_batch", "anchor_15m_ts"]).to_dicts()
        if not anchor_truth.is_empty()
        else []
    )

    grouped = (
        anchor_candidate_scores.sort(
            ["pred_batch", "anchor_15m_ts", "unit", "action_key"],
            descending=[False, False, False, False],
        )
        .group_by(
            ["pred_batch", "anchor_15m_ts", "unit", "timeframe", "target"],
            maintain_order=True,
        )
        .agg(
            [
                pl.col("action_key").alias("action_keys"),
                pl.col("dir_score_anchor").alias("dir_scores"),
                pl.col("row_count").alias("row_counts"),
                pl.col("row_count_expected").first().alias(
                    "row_count_expected_per_candidate"
                ),
            ]
        )
        .sort(["pred_batch", "anchor_15m_ts", "unit"])
    )

    anchor_unit_map: dict[tuple[int, Any], dict[str, dict[str, Any]]] = {}
    for r in grouped.iter_rows(named=True):
        key = (int(r["pred_batch"]), r["anchor_15m_ts"])
        anchor_unit_map.setdefault(key, {})[str(r["unit"])] = r

    unit_stats: dict[str, dict[str, dict[str, int]]] = {}
    for unit, meta in candidate_sets.items():
        unit_stats[unit] = {
            str(action_key): {"wins": 0, "seen": 0}
            for action_key in meta["action_keys"]
        }

    unit_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []

    for tr in truth_rows:
        pred_batch = int(tr["pred_batch"])
        anchor_ts = tr["anchor_15m_ts"]
        truth_a = str(tr["truth_a_direction"])
        truth_b = str(tr["truth_b_direction"])
        key = (pred_batch, anchor_ts)
        units_here = anchor_unit_map.get(key, {})

        variant_unit_scores: dict[str, dict[tuple[str, str], float | None]] = {
            v: {} for v in live_variants
        }

        for unit in sorted(REQUIRED_UNITS_SET):
            row = units_here.get(unit)
            if row is None:
                continue
            action_keys = [str(v) for v in row.get("action_keys", [])]
            dir_scores = [float(v) for v in row.get("dir_scores", [])]
            row_counts = [int(v) for v in row.get("row_counts", [])]
            timeframe = str(row["timeframe"])
            target = str(row["target"])
            if not action_keys or not dir_scores:
                continue
            if len(action_keys) != len(dir_scores):
                continue

            n = len(action_keys)
            uniform_weights = np.full(n, 1.0 / float(n), dtype=np.float64)

            online_raw: list[float] = []
            for action_key in action_keys:
                st = unit_stats.get(unit, {}).get(action_key, {"wins": 0, "seen": 0})
                seen = int(st.get("seen", 0))
                wins = int(st.get("wins", 0))
                if seen < int(min_history):
                    online_raw.append(1.0)
                else:
                    online_raw.append(
                        (float(wins) + float(beta_prior))
                        / (float(seen) + 2.0 * float(beta_prior))
                    )
            online_raw_arr = np.asarray(online_raw, dtype=np.float64)
            online_den = float(online_raw_arr.sum())
            if online_den <= 0:
                online_weights = uniform_weights
            else:
                online_weights = online_raw_arr / online_den

            score_arr = np.asarray(dir_scores, dtype=np.float64)
            score_uniform = float(np.dot(uniform_weights, score_arr))
            score_online = float(np.dot(online_weights, score_arr))

            candidate_coverage_rate = float(n) / 12.0
            row_count_total = int(sum(row_counts))
            row_count_expected_total = int(row["row_count_expected_per_candidate"]) * 12

            for variant, score in (
                ("live_uniform", score_uniform),
                ("live_online_beta", score_online),
            ):
                pred_dir = "UP" if score > 0 else "DOWN" if score < 0 else "NO_SIGNAL"
                unit_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "pred_batch": pred_batch,
                        "anchor_15m_ts": anchor_ts,
                        "unit": unit,
                        "timeframe": timeframe,
                        "target": target,
                        "variant": variant,
                        "ensemble_score": score,
                        "pred_direction": pred_dir,
                        "abs_score": abs(score),
                        "candidate_count_present": n,
                        "candidate_coverage_rate": candidate_coverage_rate,
                        "row_count_total": row_count_total,
                        "row_count_expected_total": row_count_expected_total,
                    }
                )
                variant_unit_scores[variant][(target, timeframe)] = score

        for variant in live_variants:
            score_4 = None
            score_b = None
            for target in TARGETS:
                s1 = variant_unit_scores[variant].get((target, "1m"))
                s5 = variant_unit_scores[variant].get((target, "5m"))
                s15 = variant_unit_scores[variant].get((target, "15m"))
                present = sum(v is not None for v in [s1, s5, s15])
                if s1 is not None and s5 is not None and s15 is not None:
                    score_target = (15.0 * float(s1) + 3.0 * float(s5) + float(s15)) / 19.0
                else:
                    score_target = None
                pred_dir = (
                    "UP"
                    if (score_target is not None and score_target > 0)
                    else "DOWN"
                    if (score_target is not None and score_target < 0)
                    else "NO_SIGNAL"
                )
                target_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "pred_batch": pred_batch,
                        "anchor_15m_ts": anchor_ts,
                        "target": target,
                        "variant": variant,
                        "score_target": score_target,
                        "pred_direction": pred_dir,
                        "abs_score": abs(float(score_target)) if score_target is not None else 0.0,
                        "timeframes_present": int(present),
                    }
                )
                if target == "target_4class":
                    score_4 = score_target
                elif target == "target_breakfree":
                    score_b = score_target

            if score_4 is not None and score_b is not None:
                score_all = 0.5 * float(score_4) + 0.5 * float(score_b)
            else:
                score_all = None
            all_pred_dir = (
                "UP"
                if (score_all is not None and score_all > 0)
                else "DOWN"
                if (score_all is not None and score_all < 0)
                else "NO_SIGNAL"
            )
            all_rows.append(
                {
                    "alignment_mode": alignment_mode,
                    "pred_batch": pred_batch,
                    "anchor_15m_ts": anchor_ts,
                    "variant": variant,
                    "score_4class": score_4,
                    "score_breakfree": score_b,
                    "score_all": score_all,
                    "pred_direction": all_pred_dir,
                    "abs_score": abs(float(score_all)) if score_all is not None else 0.0,
                }
            )

        for unit, row in units_here.items():
            action_keys = [str(v) for v in row.get("action_keys", [])]
            dir_scores = [float(v) for v in row.get("dir_scores", [])]
            if len(action_keys) != len(dir_scores):
                continue
            target = str(row["target"])
            truth_dir = truth_a if target == "target_4class" else truth_b
            if truth_dir not in {"UP", "DOWN"}:
                continue
            for action_key, sc in zip(action_keys, dir_scores):
                pred_dir = "UP" if sc > 0 else "DOWN" if sc < 0 else "NO_SIGNAL"
                if pred_dir not in {"UP", "DOWN"}:
                    continue
                st = unit_stats.setdefault(unit, {}).setdefault(
                    action_key, {"wins": 0, "seen": 0}
                )
                st["seen"] += 1
                if pred_dir == truth_dir:
                    st["wins"] += 1

    live_unit_df = (
        pl.DataFrame(unit_rows)
        .with_columns(
            [
                pl.col("pred_batch").cast(pl.Int64, strict=False),
                pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False),
            ]
        )
        .sort(["pred_batch", "anchor_15m_ts", "variant", "unit"])
        if unit_rows
        else pl.DataFrame(
            schema={
                "alignment_mode": pl.Utf8,
                "pred_batch": pl.Int64,
                "anchor_15m_ts": pl.Datetime("us"),
                "unit": pl.Utf8,
                "timeframe": pl.Utf8,
                "target": pl.Utf8,
                "variant": pl.Utf8,
                "ensemble_score": pl.Float64,
                "pred_direction": pl.Utf8,
                "abs_score": pl.Float64,
                "candidate_count_present": pl.Int64,
                "candidate_coverage_rate": pl.Float64,
                "row_count_total": pl.Int64,
                "row_count_expected_total": pl.Int64,
            }
        )
    )
    live_target_df = (
        pl.DataFrame(target_rows)
        .with_columns(
            [
                pl.col("pred_batch").cast(pl.Int64, strict=False),
                pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False),
            ]
        )
        .sort(["pred_batch", "anchor_15m_ts", "target", "variant"])
        if target_rows
        else pl.DataFrame(
            schema={
                "alignment_mode": pl.Utf8,
                "pred_batch": pl.Int64,
                "anchor_15m_ts": pl.Datetime("us"),
                "target": pl.Utf8,
                "variant": pl.Utf8,
                "score_target": pl.Float64,
                "pred_direction": pl.Utf8,
                "abs_score": pl.Float64,
                "timeframes_present": pl.Int64,
            }
        )
    )
    live_all_df = (
        pl.DataFrame(all_rows)
        .with_columns(
            [
                pl.col("pred_batch").cast(pl.Int64, strict=False),
                pl.col("anchor_15m_ts").cast(pl.Datetime("us"), strict=False),
            ]
        )
        .sort(["pred_batch", "anchor_15m_ts", "variant"])
        if all_rows
        else pl.DataFrame(
            schema={
                "alignment_mode": pl.Utf8,
                "pred_batch": pl.Int64,
                "anchor_15m_ts": pl.Datetime("us"),
                "variant": pl.Utf8,
                "score_4class": pl.Float64,
                "score_breakfree": pl.Float64,
                "score_all": pl.Float64,
                "pred_direction": pl.Utf8,
                "abs_score": pl.Float64,
            }
        )
    )

    stream_live_unit = live_unit_df.select(
        [
            "pred_batch",
            "anchor_15m_ts",
            "alignment_mode",
            pl.lit("unit").alias("stream_level"),
            pl.col("unit").alias("stream_name"),
            "variant",
            "target",
            "timeframe",
            pl.col("ensemble_score").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_live_target = live_target_df.select(
        [
            "pred_batch",
            "anchor_15m_ts",
            "alignment_mode",
            pl.lit("target").alias("stream_level"),
            pl.concat_str([pl.lit("target::"), pl.col("target")]).alias("stream_name"),
            "variant",
            "target",
            pl.lit(None).cast(pl.Utf8).alias("timeframe"),
            pl.col("score_target").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_live_all = live_all_df.select(
        [
            "pred_batch",
            "anchor_15m_ts",
            "alignment_mode",
            pl.lit("all").alias("stream_level"),
            pl.lit("all_targets").alias("stream_name"),
            "variant",
            pl.lit("all_targets").alias("target"),
            pl.lit(None).cast(pl.Utf8).alias("timeframe"),
            pl.col("score_all").alias("score"),
            "pred_direction",
            "abs_score",
        ]
    )
    stream_live_scores = pl.concat(
        [stream_live_unit, stream_live_target, stream_live_all], how="diagonal_relaxed"
    ).sort(
        [
            "alignment_mode",
            "stream_level",
            "stream_name",
            "variant",
            "pred_batch",
            "anchor_15m_ts",
        ]
    )

    live_eval_dual, live_eval_by_batch, live_conf_bins = _evaluate_stream_scores(
        stream_scores=stream_live_scores, anchor_truth=anchor_truth
    )

    return {
        "unit_scores": live_unit_df,
        "target_scores": live_target_df,
        "all_scores": live_all_df,
        "stream_scores": stream_live_scores,
        "evaluation_dual": live_eval_dual,
        "evaluation_by_batch": live_eval_by_batch,
        "confidence_bins": live_conf_bins,
    }


def main() -> None:
    args = _parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    run_id = str(args.run_id)
    model_name = str(args.model_name)
    source_scope = str(args.source_scope)
    units = _normalize_units(list(args.units))
    verbose = bool(args.verbose)

    if set(units) != REQUIRED_UNITS_SET:
        raise ValueError(
            "This analysis requires exactly these 6 units: "
            f"{sorted(REQUIRED_UNITS_SET)}"
        )

    candidate_run_dir = _resolve_candidate_run_dir(
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        candidate_run_dir_arg=str(args.candidate_run_dir),
    )

    out_base = Path(args.output_dir)
    if not out_base.is_absolute():
        out_base = project_root / out_base
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = str(args.output_tag).strip().replace(" ", "_")
    out_dir = out_base / (f"{ts}_{tag}" if tag else ts)
    out_dir.mkdir(parents=True, exist_ok=False)

    print("Multi-timeframe direction ensemble analysis")
    print(f"  project_root: {project_root}")
    print(f"  run/model: {run_id}/{model_name}")
    print(f"  candidate_run_dir: {candidate_run_dir}")
    print(f"  source_scope: {source_scope}")
    print(f"  output_dir: {out_dir}")

    candidate_sets = _resolve_candidate_sets(
        project_root=project_root,
        run_id=run_id,
        model_name=model_name,
        candidate_run_dir=candidate_run_dir,
        units=units,
    )
    candidate_sets = _apply_candidate_set_overrides(
        candidate_sets=candidate_sets,
        candidate_sets_json_arg=str(args.candidate_sets_json),
        units=units,
    )

    # --- Load and deduplicate prediction rows per unit ---
    unit_frames: list[pl.DataFrame] = []
    for unit in units:
        action_keys = list(candidate_sets[unit]["action_keys"])
        print(f"\nLoading unit rows: {unit} (candidates={len(action_keys)})")
        df_unit = _load_unit_prediction_rows(
            project_root=project_root,
            run_id=run_id,
            model_name=model_name,
            unit=unit,
            action_keys=action_keys,
            source_scope=source_scope,
            verbose=verbose,
        )
        if df_unit.is_empty():
            raise RuntimeError(f"No prediction rows loaded for unit: {unit}")
        df_unit = _add_direction_columns(df_unit)
        unit_frames.append(df_unit)
        print(f"  loaded rows: {len(df_unit):,}")

    unit_rows = pl.concat(unit_frames, how="diagonal_relaxed").sort(
        ["pred_batch", "timestamp", "batch_id", "unit", "action_key"]
    )

    selected_alignment_modes = (
        ["mean", "period_close"]
        if str(args.anchor_row_alignment) == "both"
        else [str(args.anchor_row_alignment)]
    )
    print(f"\nAnchor row alignment modes: {selected_alignment_modes}")

    # --- Candidate scores per 15m anchor ---
    anchor_candidate_scores_parts: list[pl.DataFrame] = []
    anchor_candidate_scores_by_mode: dict[str, pl.DataFrame] = {}
    for mode in selected_alignment_modes:
        part = _build_anchor_candidate_scores(unit_rows=unit_rows, mode=mode)
        anchor_candidate_scores_parts.append(part)
        mode_label = "anchor_mean" if mode == "mean" else "same_period_close"
        anchor_candidate_scores_by_mode[mode_label] = part
    anchor_candidate_scores = pl.concat(anchor_candidate_scores_parts, how="diagonal_relaxed").sort(
        ["alignment_mode", "pred_batch", "anchor_15m_ts", "unit", "action_key"]
    )

    # --- Weights and per-unit ensemble ---
    weights_df = _build_weights(candidate_sets)
    (
        anchor_unit_ensemble,
        anchor_target_fusion,
        anchor_all_fusion,
        stream_scores,
    ) = _build_static_streams_from_candidate_scores(
        anchor_candidate_scores=anchor_candidate_scores,
        weights_df=weights_df,
    )

    # --- Truth tables and anchor universe ---
    anchor_truth, truth_diag = _prepare_anchor_truths(unit_rows)
    if anchor_truth.is_empty():
        raise RuntimeError("Anchor truth table is empty.")
    anchor_truth = _normalize_anchor_ts(anchor_truth)

    # Filter to anchor universe for eval-related outputs
    anchor_keys = anchor_truth.select(["pred_batch", "anchor_15m_ts"]).unique()
    anchor_unit_eval = anchor_unit_ensemble.join(anchor_keys, on=["pred_batch", "anchor_15m_ts"], how="inner")
    anchor_target_eval = anchor_target_fusion.join(anchor_keys, on=["pred_batch", "anchor_15m_ts"], how="inner")
    anchor_all_eval = anchor_all_fusion.join(anchor_keys, on=["pred_batch", "anchor_15m_ts"], how="inner")

    # --- Build stream score table (unit + target + all) ---
    stream_scores = stream_scores.join(
        anchor_keys, on=["pred_batch", "anchor_15m_ts"], how="inner"
    )

    # --- Evaluation (dual truth) ---
    evaluation_dual, evaluation_by_batch, confidence_bins = _evaluate_stream_scores(
        stream_scores=stream_scores,
        anchor_truth=anchor_truth,
    )

    # --- Agreement diagnostics (unit streams only) ---
    unit_dir_df = anchor_unit_eval.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "variant",
            "unit",
            "pred_direction",
        ]
    )
    unit_pivot = unit_dir_df.pivot(
        index=["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"],
        on="unit",
        values="pred_direction",
        aggregate_function="first",
    ).sort(["alignment_mode", "variant", "pred_batch", "anchor_15m_ts"])

    pair_rows: list[dict[str, Any]] = []
    anchor_agree_rows: list[dict[str, Any]] = []
    unit_cols = sorted(REQUIRED_UNITS_SET)
    for alignment_mode in (
        unit_pivot.select("alignment_mode")
        .unique()
        .sort("alignment_mode")["alignment_mode"]
        .to_list()
    ):
        for variant in VARIANTS:
            pv = unit_pivot.filter(
                (pl.col("alignment_mode") == alignment_mode)
                & (pl.col("variant") == variant)
            )
            if pv.is_empty():
                continue

            # Per-anchor summary
            for row in pv.iter_rows(named=True):
                dirs = [str(row.get(c, "NO_SIGNAL")) for c in unit_cols]
                n_up = sum(1 for d in dirs if d == "UP")
                n_down = sum(1 for d in dirs if d == "DOWN")
                n_nosig = sum(1 for d in dirs if d == "NO_SIGNAL")
                pair_cov = 0
                pair_same_cov = 0
                pair_conflict = 0
                for a, b in combinations(unit_cols, 2):
                    da = str(row.get(a, "NO_SIGNAL"))
                    db = str(row.get(b, "NO_SIGNAL"))
                    if da in {"UP", "DOWN"} and db in {"UP", "DOWN"}:
                        pair_cov += 1
                        if da == db:
                            pair_same_cov += 1
                        else:
                            pair_conflict += 1
                anchor_agree_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "pred_batch": int(row["pred_batch"]),
                        "anchor_15m_ts": row["anchor_15m_ts"],
                        "variant": variant,
                        "n_up": n_up,
                        "n_down": n_down,
                        "n_no_signal": n_nosig,
                        "all_stream_same_direction": bool(n_up == 6 or n_down == 6),
                        "pairwise_covered_pairs": int(pair_cov),
                        "pairwise_same_direction_rate_covered": (
                            float(pair_same_cov) / float(pair_cov)
                            if pair_cov > 0
                            else None
                        ),
                        "pairwise_conflict_rate_covered": (
                            float(pair_conflict) / float(pair_cov)
                            if pair_cov > 0
                            else None
                        ),
                    }
                )

            # Global pair matrix
            for a, b in combinations(unit_cols, 2):
                pair_df = pv.select(
                    [
                        pl.col("pred_batch"),
                        pl.col("anchor_15m_ts"),
                        pl.col(a).alias("dir_a"),
                        pl.col(b).alias("dir_b"),
                    ]
                )
                n_all = int(pair_df.height)
                n_same_all = (
                    int((pair_df["dir_a"] == pair_df["dir_b"]).sum()) if n_all > 0 else 0
                )
                covered_mask = pair_df["dir_a"].is_in(["UP", "DOWN"]) & pair_df[
                    "dir_b"
                ].is_in(["UP", "DOWN"])
                pair_cov = int(covered_mask.sum())
                if pair_cov > 0:
                    covered_df = pair_df.filter(covered_mask)
                    same_cov = int((covered_df["dir_a"] == covered_df["dir_b"]).sum())
                    conflict_cov = int((covered_df["dir_a"] != covered_df["dir_b"]).sum())
                    same_cov_rate = float(same_cov) / float(pair_cov)
                    conflict_cov_rate = float(conflict_cov) / float(pair_cov)
                else:
                    same_cov_rate = None
                    conflict_cov_rate = None
                pair_rows.append(
                    {
                        "alignment_mode": alignment_mode,
                        "variant": variant,
                        "unit_a": a,
                        "unit_b": b,
                        "anchor_count": n_all,
                        "same_direction_rate_all": float(n_same_all) / float(n_all)
                        if n_all > 0
                        else None,
                        "covered_anchor_count": pair_cov,
                        "same_direction_rate_covered": same_cov_rate,
                        "conflict_rate_covered": conflict_cov_rate,
                    }
                )

    agreement_matrix_pairwise = pl.DataFrame(pair_rows).sort(
        ["alignment_mode", "variant", "unit_a", "unit_b"]
    )
    agreement_anchor_summary = pl.DataFrame(anchor_agree_rows).sort(
        ["alignment_mode", "variant", "pred_batch", "anchor_15m_ts"]
    )

    # Add cross-target conflict labels to anchor summary
    target_dirs = anchor_target_eval.select(
        [
            "alignment_mode",
            "pred_batch",
            "anchor_15m_ts",
            "variant",
            "target",
            "pred_direction",
        ]
    ).pivot(
        index=["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"],
        on="target",
        values="pred_direction",
        aggregate_function="first",
    )
    for target in TARGETS:
        if target not in target_dirs.columns:
            target_dirs = target_dirs.with_columns(pl.lit("NO_SIGNAL").alias(target))
    target_dirs = target_dirs.with_columns(
        [
            pl.when(
                (pl.col("target_4class") == "UP") & (pl.col("target_breakfree") == "UP")
            )
            .then(pl.lit("agree_up"))
            .when(
                (pl.col("target_4class") == "DOWN") & (pl.col("target_breakfree") == "DOWN")
            )
            .then(pl.lit("agree_down"))
            .when(
                (pl.col("target_4class") == "UP") & (pl.col("target_breakfree") == "DOWN")
            )
            .then(pl.lit("conflict_4_up_break_down"))
            .when(
                (pl.col("target_4class") == "DOWN") & (pl.col("target_breakfree") == "UP")
            )
            .then(pl.lit("conflict_4_down_break_up"))
            .otherwise(pl.lit("any_nosignal"))
            .alias("cross_target_conflict_category")
        ]
    )
    agreement_anchor_summary = agreement_anchor_summary.join(
        target_dirs.select(
            [
                "alignment_mode",
                "pred_batch",
                "anchor_15m_ts",
                "variant",
                pl.col("target_4class").alias("target_4class_direction"),
                pl.col("target_breakfree").alias("target_breakfree_direction"),
                "cross_target_conflict_category",
            ]
        ),
        on=["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"],
        how="left",
    )

    # --- Production-style walk-forward (winner-unknown) ---
    live_outputs: dict[str, pl.DataFrame] | None = None
    if bool(args.live_walkforward):
        print("\nRunning live walk-forward ensemble (winner-unknown current batch)...")
        live_parts: list[dict[str, pl.DataFrame]] = []
        for mode_label, mode_df in anchor_candidate_scores_by_mode.items():
            live_parts.append(
                _build_live_walkforward_ensembles(
                    anchor_candidate_scores=mode_df,
                    anchor_truth=anchor_truth,
                    candidate_sets=candidate_sets,
                    beta_prior=float(args.live_beta_prior),
                    min_history=int(args.live_min_history),
                    alignment_mode=mode_label,
                )
            )
        live_outputs = {
            "unit_scores": pl.concat(
                [p["unit_scores"] for p in live_parts], how="diagonal_relaxed"
            ).sort(["alignment_mode", "pred_batch", "anchor_15m_ts", "variant", "unit"]),
            "target_scores": pl.concat(
                [p["target_scores"] for p in live_parts], how="diagonal_relaxed"
            ).sort(
                [
                    "alignment_mode",
                    "pred_batch",
                    "anchor_15m_ts",
                    "target",
                    "variant",
                ]
            ),
            "all_scores": pl.concat(
                [p["all_scores"] for p in live_parts], how="diagonal_relaxed"
            ).sort(["alignment_mode", "pred_batch", "anchor_15m_ts", "variant"]),
            "stream_scores": pl.concat(
                [p["stream_scores"] for p in live_parts], how="diagonal_relaxed"
            ).sort(
                [
                    "alignment_mode",
                    "stream_level",
                    "stream_name",
                    "variant",
                    "pred_batch",
                    "anchor_15m_ts",
                ]
            ),
            "evaluation_dual": pl.concat(
                [p["evaluation_dual"] for p in live_parts], how="diagonal_relaxed"
            ).sort(
                [
                    "alignment_mode",
                    "truth_name",
                    "stream_level",
                    "stream_name",
                    "variant",
                ]
            ),
            "evaluation_by_batch": pl.concat(
                [p["evaluation_by_batch"] for p in live_parts],
                how="diagonal_relaxed",
            ).sort(
                [
                    "alignment_mode",
                    "truth_name",
                    "stream_level",
                    "stream_name",
                    "variant",
                    "pred_batch",
                ]
            ),
            "confidence_bins": pl.concat(
                [p["confidence_bins"] for p in live_parts], how="diagonal_relaxed"
            ).sort(
                [
                    "alignment_mode",
                    "truth_name",
                    "stream_level",
                    "stream_name",
                    "variant",
                    "bin_idx",
                ]
            ),
        }
        print(
            "  live streams rows: "
            f"unit={live_outputs['unit_scores'].height:,}, "
            f"target={live_outputs['target_scores'].height:,}, "
            f"all={live_outputs['all_scores'].height:,}"
        )

    # --- Write artifacts ---
    config_resolved_path = out_dir / "config_resolved.json"
    candidate_sets_path = out_dir / "candidate_sets_by_unit.json"
    unit_rows_path = out_dir / "unit_prediction_rows_dedup.parquet"
    anchor_candidate_path = out_dir / "anchor_candidate_scores.parquet"
    anchor_unit_path = out_dir / "anchor_unit_ensemble_scores.parquet"
    anchor_target_path = out_dir / "anchor_target_fusion_scores.parquet"
    anchor_all_path = out_dir / "anchor_all_target_fusion_scores.parquet"
    agreement_matrix_path = out_dir / "agreement_matrix_pairwise.parquet"
    agreement_anchor_path = out_dir / "agreement_anchor_summary.parquet"
    evaluation_dual_path = out_dir / "evaluation_dual_report.parquet"
    evaluation_batch_path = out_dir / "evaluation_by_batch.parquet"
    confidence_bins_path = out_dir / "confidence_bins_report.parquet"

    live_unit_path = out_dir / "live_anchor_unit_ensemble_scores.parquet"
    live_target_path = out_dir / "live_anchor_target_fusion_scores.parquet"
    live_all_path = out_dir / "live_anchor_all_target_fusion_scores.parquet"
    live_stream_path = out_dir / "live_stream_scores.parquet"
    live_eval_dual_path = out_dir / "live_evaluation_dual_report.parquet"
    live_eval_batch_path = out_dir / "live_evaluation_by_batch.parquet"
    live_conf_bins_path = out_dir / "live_confidence_bins_report.parquet"

    summary_path = out_dir / "summary.json"

    unit_rows.write_parquet(unit_rows_path)
    anchor_candidate_scores.write_parquet(anchor_candidate_path)
    anchor_unit_ensemble.write_parquet(anchor_unit_path)
    anchor_target_fusion.write_parquet(anchor_target_path)
    anchor_all_fusion.write_parquet(anchor_all_path)
    agreement_matrix_pairwise.write_parquet(agreement_matrix_path)
    agreement_anchor_summary.write_parquet(agreement_anchor_path)
    evaluation_dual.write_parquet(evaluation_dual_path)
    evaluation_by_batch.write_parquet(evaluation_batch_path)
    confidence_bins.write_parquet(confidence_bins_path)

    if live_outputs is not None:
        live_outputs["unit_scores"].write_parquet(live_unit_path)
        live_outputs["target_scores"].write_parquet(live_target_path)
        live_outputs["all_scores"].write_parquet(live_all_path)
        live_outputs["stream_scores"].write_parquet(live_stream_path)
        live_outputs["evaluation_dual"].write_parquet(live_eval_dual_path)
        live_outputs["evaluation_by_batch"].write_parquet(live_eval_batch_path)
        live_outputs["confidence_bins"].write_parquet(live_conf_bins_path)

    # Optional CSV mirrors
    evaluation_dual_csv = out_dir / "evaluation_dual_report.csv"
    evaluation_batch_csv = out_dir / "evaluation_by_batch.csv"
    agreement_anchor_csv = out_dir / "agreement_anchor_summary.csv"
    live_evaluation_dual_csv = out_dir / "live_evaluation_dual_report.csv"
    live_evaluation_batch_csv = out_dir / "live_evaluation_by_batch.csv"
    evaluation_dual.write_csv(evaluation_dual_csv)
    evaluation_by_batch.write_csv(evaluation_batch_csv)
    agreement_anchor_summary.write_csv(agreement_anchor_csv)
    if live_outputs is not None:
        live_outputs["evaluation_dual"].write_csv(live_evaluation_dual_csv)
        live_outputs["evaluation_by_batch"].write_csv(live_evaluation_batch_csv)

    candidate_sets_json = {
        unit: {
            "source": meta["source"],
            "action_keys": list(meta["action_keys"]),
            "winner_wins": {k: int(v) for k, v in meta["winner_wins"].items()},
            "weights": {
                k: {
                    "uniform": float(1.0 / 12.0),
                    "winner_weighted": float(
                        (float(meta["winner_wins"].get(k, 0)) + 1.0)
                        / sum(float(meta["winner_wins"].get(j, 0)) + 1.0 for j in meta["action_keys"])
                    ),
                }
                for k in meta["action_keys"]
            },
        }
        for unit, meta in candidate_sets.items()
    }

    _write_json(
        config_resolved_path,
        {
            "project_root": str(project_root),
            "run_id": run_id,
            "model_name": model_name,
            "candidate_run_dir": str(candidate_run_dir),
            "candidate_sets_json": str(args.candidate_sets_json),
            "source_scope": source_scope,
            "units": units,
            "targets": TARGETS,
            "variants": VARIANTS,
            "timeframe_row_weights": {"1m": 15, "5m": 3, "15m": 1},
            "all_target_weights": {"target_4class": 0.5, "target_breakfree": 0.5},
            "breakfree_neutral_policy": "exclude_class_2_from_truth_b_denominator",
            "alignment": "timestamp_floor_15m_same_interval",
            "anchor_row_alignment": str(args.anchor_row_alignment),
            "anchor_row_alignment_modes": list(anchor_candidate_scores_by_mode.keys()),
            "live_walkforward_enabled": bool(args.live_walkforward),
            "live_beta_prior": float(args.live_beta_prior),
            "live_min_history": int(args.live_min_history),
        },
    )
    _write_json(candidate_sets_path, candidate_sets_json)

    row_match_diag = (
        anchor_candidate_scores.group_by(["alignment_mode", "unit", "timeframe"])
        .agg(
            [
                pl.len().alias("anchor_candidate_rows"),
                (pl.col("row_count_match")).sum().alias("row_count_match_rows"),
                (pl.col("row_count_match").cast(pl.Float64)).mean().alias("row_count_match_rate"),
                pl.col("row_count").min().alias("row_count_min"),
                pl.col("row_count").max().alias("row_count_max"),
            ]
        )
        .sort(["alignment_mode", "unit", "timeframe"])
    )

    top_streams = (
        evaluation_dual.filter(pl.col("conditional_hit_rate").is_not_null())
        .sort(
            ["alignment_mode", "truth_name", "conditional_hit_rate", "coverage_rate"],
            descending=[False, False, True, True],
        )
        .group_by(["alignment_mode", "truth_name"])
        .head(5)
    )

    summary = {
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "project_root": str(project_root),
            "run_id": run_id,
            "model_name": model_name,
            "candidate_run_dir": str(candidate_run_dir),
            "candidate_sets_json": str(args.candidate_sets_json),
            "source_scope": source_scope,
            "units": units,
            "anchor_row_alignment": str(args.anchor_row_alignment),
            "anchor_row_alignment_modes": list(anchor_candidate_scores_by_mode.keys()),
            "live_walkforward_enabled": bool(args.live_walkforward),
            "live_beta_prior": float(args.live_beta_prior),
            "live_min_history": int(args.live_min_history),
        },
        "counts": {
            "unit_prediction_rows_dedup": int(unit_rows.height),
            "anchor_candidate_scores": int(anchor_candidate_scores.height),
            "anchor_unit_ensemble_scores": int(anchor_unit_ensemble.height),
            "anchor_target_fusion_scores": int(anchor_target_fusion.height),
            "anchor_all_target_fusion_scores": int(anchor_all_fusion.height),
            "evaluation_rows": int(evaluation_dual.height),
            "evaluation_by_batch_rows": int(evaluation_by_batch.height),
            "confidence_bin_rows": int(confidence_bins.height),
            "anchor_universe": int(truth_diag["anchor_universe_count"]),
            "live_anchor_unit_ensemble_scores": int(live_outputs["unit_scores"].height)
            if live_outputs is not None
            else 0,
            "live_anchor_target_fusion_scores": int(
                live_outputs["target_scores"].height
            )
            if live_outputs is not None
            else 0,
            "live_anchor_all_target_fusion_scores": int(live_outputs["all_scores"].height)
            if live_outputs is not None
            else 0,
            "live_evaluation_rows": int(live_outputs["evaluation_dual"].height)
            if live_outputs is not None
            else 0,
            "live_evaluation_by_batch_rows": int(
                live_outputs["evaluation_by_batch"].height
            )
            if live_outputs is not None
            else 0,
        },
        "truth_diagnostics": truth_diag,
        "row_count_diagnostics": row_match_diag.to_dicts(),
        "top_streams_by_truth": top_streams.to_dicts(),
        "live_top_streams_by_truth": (
            live_outputs["evaluation_dual"]
            .filter(pl.col("conditional_hit_rate").is_not_null())
            .sort(
                [
                    "alignment_mode",
                    "truth_name",
                    "conditional_hit_rate",
                    "coverage_rate",
                ],
                descending=[False, False, True, True],
            )
            .group_by(["alignment_mode", "truth_name"])
            .head(5)
            .to_dicts()
            if live_outputs is not None
            else []
        ),
        "agreement_overview": (
            agreement_anchor_summary.group_by(["alignment_mode", "variant"])
            .agg(
                [
                    pl.col("all_stream_same_direction").mean().alias("all_stream_same_direction_rate"),
                    (pl.col("cross_target_conflict_category") == "conflict_4_up_break_down")
                    .mean()
                    .alias("rate_conflict_4_up_break_down"),
                    (pl.col("cross_target_conflict_category") == "conflict_4_down_break_up")
                    .mean()
                    .alias("rate_conflict_4_down_break_up"),
                ]
            )
            .to_dicts()
        ),
        "artifacts": {
            "config_resolved_json": str(config_resolved_path),
            "candidate_sets_by_unit_json": str(candidate_sets_path),
            "unit_prediction_rows_dedup_parquet": str(unit_rows_path),
            "anchor_candidate_scores_parquet": str(anchor_candidate_path),
            "anchor_unit_ensemble_scores_parquet": str(anchor_unit_path),
            "anchor_target_fusion_scores_parquet": str(anchor_target_path),
            "anchor_all_target_fusion_scores_parquet": str(anchor_all_path),
            "agreement_matrix_pairwise_parquet": str(agreement_matrix_path),
            "agreement_anchor_summary_parquet": str(agreement_anchor_path),
            "evaluation_dual_report_parquet": str(evaluation_dual_path),
            "evaluation_by_batch_parquet": str(evaluation_batch_path),
            "confidence_bins_report_parquet": str(confidence_bins_path),
            "evaluation_dual_report_csv": str(evaluation_dual_csv),
            "evaluation_by_batch_csv": str(evaluation_batch_csv),
            "agreement_anchor_summary_csv": str(agreement_anchor_csv),
            "live_anchor_unit_ensemble_scores_parquet": str(live_unit_path)
            if live_outputs is not None
            else None,
            "live_anchor_target_fusion_scores_parquet": str(live_target_path)
            if live_outputs is not None
            else None,
            "live_anchor_all_target_fusion_scores_parquet": str(live_all_path)
            if live_outputs is not None
            else None,
            "live_stream_scores_parquet": str(live_stream_path)
            if live_outputs is not None
            else None,
            "live_evaluation_dual_report_parquet": str(live_eval_dual_path)
            if live_outputs is not None
            else None,
            "live_evaluation_by_batch_parquet": str(live_eval_batch_path)
            if live_outputs is not None
            else None,
            "live_confidence_bins_report_parquet": str(live_conf_bins_path)
            if live_outputs is not None
            else None,
            "live_evaluation_dual_report_csv": str(live_evaluation_dual_csv)
            if live_outputs is not None
            else None,
            "live_evaluation_by_batch_csv": str(live_evaluation_batch_csv)
            if live_outputs is not None
            else None,
            "summary_json": str(summary_path),
        },
    }
    _write_json(summary_path, summary)

    print("\nCompleted.")
    print(f"  Anchor universe: {truth_diag['anchor_universe_count']}")
    print(f"  Unit rows: {unit_rows.height:,}")
    print(f"  Evaluation rows: {evaluation_dual.height:,}")
    if live_outputs is not None:
        print(
            "  Live evaluation rows: "
            f"{live_outputs['evaluation_dual'].height:,}"
        )
    print("  Saved:")
    print(f"    {summary_path}")


if __name__ == "__main__":
    main()

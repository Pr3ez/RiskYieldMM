from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = PROJECT_ROOT / "data" / "htf_backtest_results"
DEFAULT_TEST_OUTPUT = PROJECT_ROOT / "test_output"

SELECTED_PREDICTION_FILE = "stage1_v2_pred_batch_predictions_selected.parquet"
COMBO_METRICS_FILE = "stage1_v2_combo_metrics.parquet"

LOSS_ALIAS_MAP = {
    "filtered_cde": "filtered_cde",
    "direction_error": "filtered_cde",
    "class_error": "class_error",
    "macro_f1_error": "macro_f1_error",
    "multiclass_brier": "multiclass_brier",
    "multiclass_logloss": "multiclass_logloss",
    "composite": "composite",
}

OBJECTIVE_DIRECTIONS = {
    "mean_filtered_cde": "min",
    "mean_direction_accuracy": "max",
    "mean_accuracy": "max",
    "mean_macro_f1": "max",
    "mean_rank": "min",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate Stage-1-v2 walkforward-safe combo selectors that rank combos "
            "by discounted past loss on fixed-policy replay artifacts."
        )
    )
    parser.add_argument("--run-id", type=str, help="Run id under data/htf_backtest_results/.")
    parser.add_argument("--run-path", type=str, help="Absolute or relative run directory path.")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional explicit output directory. Defaults under test_output/.",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.70,
        help="Chronological outer-train fraction for the final train/test evaluation split.",
    )
    parser.add_argument(
        "--policy-selection-mode",
        type=str,
        default="nested",
        choices=["nested", "train_ready"],
        help=(
            "How to choose the best policy from the candidate grid. "
            "'nested' uses an inner chronological train/validation split inside the outer train window. "
            "'train_ready' reproduces the previous behavior and chooses directly on the outer-train ready split."
        ),
    )
    parser.add_argument(
        "--inner-train-frac",
        type=float,
        default=0.70,
        help=(
            "When policy-selection-mode=nested, chronological fraction of the outer-train window "
            "used as inner-train. The remainder becomes inner validation."
        ),
    )
    parser.add_argument(
        "--loss-names",
        nargs="+",
        default=[
            "filtered_cde",
            "class_error",
            "macro_f1_error",
            "multiclass_brier",
            "multiclass_logloss",
            "composite",
        ],
        help="Update losses to evaluate. direction_error is an alias for filtered_cde.",
    )
    parser.add_argument(
        "--discount-factors",
        nargs="+",
        type=float,
        default=[0.50, 0.70, 0.85, 0.95, 0.98],
        help=(
            "Exponential discount factors for past losses. Higher means longer memory. "
            "Each value must be in [0, 1)."
        ),
    )
    parser.add_argument(
        "--min-history-steps",
        type=int,
        default=3,
        help=(
            "Minimum prior realized steps before a combo is marked ready. "
            "Early selections still run, but ready-only metrics ignore the cold-start region."
        ),
    )
    parser.add_argument(
        "--select-best-by",
        type=str,
        default="mean_filtered_cde",
        choices=sorted(OBJECTIVE_DIRECTIONS.keys()),
        help="Metric used on the train-ready split to choose the best policy from the grid.",
    )
    parser.add_argument(
        "--persist-all-policy-timelines",
        action="store_true",
        help="Write one timeline parquet/csv for every evaluated policy, not only the best one.",
    )
    parser.add_argument(
        "--probability-epsilon",
        type=float,
        default=1e-12,
        help="Clipping epsilon for per-row multiclass log-loss.",
    )
    parser.add_argument(
        "--composite-filtered-cde-weight",
        type=float,
        default=0.60,
        help="Composite update-loss weight for filtered cross-direction error.",
    )
    parser.add_argument(
        "--composite-class-error-weight",
        type=float,
        default=0.25,
        help="Composite update-loss weight for class error (1 - filtered accuracy).",
    )
    parser.add_argument(
        "--composite-macro-f1-error-weight",
        type=float,
        default=0.15,
        help="Composite update-loss weight for macro-F1 error (1 - filtered macro F1).",
    )
    parser.add_argument(
        "--composite-brier-weight",
        type=float,
        default=0.0,
        help="Composite update-loss weight for normalized multiclass Brier loss.",
    )
    parser.add_argument(
        "--composite-logloss-weight",
        type=float,
        default=0.0,
        help="Composite update-loss weight for multiclass log-loss.",
    )
    return parser.parse_args()


def _resolve_run_dir(args: argparse.Namespace) -> Path:
    if bool(args.run_id) == bool(args.run_path):
        raise SystemExit("Exactly one of --run-id or --run-path must be provided.")
    if args.run_id:
        run_dir = RESULTS_ROOT / str(args.run_id)
    else:
        candidate = Path(str(args.run_path))
        run_dir = candidate if candidate.is_absolute() else (PROJECT_ROOT / candidate)
    run_dir = run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")
    return run_dir


def _default_output_dir(run_dir: Path) -> Path:
    return DEFAULT_TEST_OUTPUT / f"stage1_v2_loss_discounted_selector_audit_{run_dir.name}"


def _batch_sort_key(path: Path) -> tuple[int, str]:
    try:
        batch_token = path.parent.parent.name
        batch_num = int(batch_token.split("_", 1)[1])
    except Exception:
        batch_num = -1
    return batch_num, str(path)


def _discover_files(run_dir: Path, file_name: str) -> list[Path]:
    paths = sorted(
        run_dir.glob(f"catboost/*/*/batch_*/stage1_v2/{file_name}"),
        key=_batch_sort_key,
    )
    if not paths:
        raise SystemExit(f"No files named {file_name} found under: {run_dir}")
    return paths


def _normalize_loss_names(loss_names: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for raw in loss_names:
        key = str(raw).strip().lower()
        if key not in LOSS_ALIAS_MAP:
            valid = ", ".join(sorted(LOSS_ALIAS_MAP))
            raise SystemExit(f"Unsupported loss name '{raw}'. Valid names: {valid}")
        canonical = LOSS_ALIAS_MAP[key]
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _validate_discount_factors(values: Iterable[float]) -> list[float]:
    factors: list[float] = []
    for raw in values:
        val = float(raw)
        if not (0.0 <= val < 1.0):
            raise SystemExit(f"Discount factor must be in [0, 1): {raw}")
        if val not in factors:
            factors.append(val)
    if not factors:
        raise SystemExit("At least one discount factor is required.")
    return factors


def _train_test_split(pred_batches: list[int], train_frac: float) -> tuple[set[int], set[int]]:
    pred_batches = sorted(pred_batches)
    n_steps = len(pred_batches)
    if n_steps < 2:
        raise SystemExit("Need at least 2 pred batches for a train/test split.")
    split_idx = max(1, min(n_steps - 1, int(math.floor(n_steps * train_frac))))
    train_batches = set(pred_batches[:split_idx])
    test_batches = set(pred_batches[split_idx:])
    return train_batches, test_batches


def _load_combo_metrics(paths: Iterable[Path]) -> pd.DataFrame:
    frames: list[pl.DataFrame] = []
    columns = [
        "pred_batch",
        "action_key",
        "combo_id",
        "filtered_rank",
        "filtered_accuracy",
        "filtered_cross_direction_error",
        "filtered_macro_f1",
        "n_features_used",
        "improved_step",
        "selection_applied",
        "apply_pruned_step",
    ]
    for path in paths:
        df = pl.read_parquet(path, columns=columns)
        if not df.is_empty():
            frames.append(df)
    if not frames:
        raise SystemExit("Combo metric inputs were discovered, but all were empty.")
    pdf = (
        pl.concat(frames, how="vertical_relaxed")
        .sort(["pred_batch", "action_key"])
        .to_pandas()
    )
    pdf["filtered_cde"] = pdf["filtered_cross_direction_error"].astype(float)
    pdf["direction_accuracy"] = 1.0 - pdf["filtered_cde"]
    pdf["class_error"] = 1.0 - pdf["filtered_accuracy"].astype(float)
    pdf["macro_f1_error"] = 1.0 - pdf["filtered_macro_f1"].astype(float)
    return pdf


def _load_probabilistic_step_losses(paths: Iterable[Path], probability_epsilon: float) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    prob_cols = [f"prob_class_{idx}" for idx in range(4)]
    eye = np.eye(4, dtype=np.float64)
    eps = float(probability_epsilon)

    for path in paths:
        df = pl.read_parquet(
            path,
            columns=["pred_batch", "action_key", "y_true", *prob_cols],
        )
        if df.is_empty():
            continue
        pdf = df.to_pandas()
        probs = pdf[prob_cols].to_numpy(dtype=np.float64, copy=False)
        y_true = pdf["y_true"].to_numpy(dtype=np.int64, copy=False)
        if probs.shape[0] == 0:
            continue
        clipped_true_prob = np.clip(probs[np.arange(len(y_true)), y_true], eps, 1.0)
        logloss = -np.log(clipped_true_prob)
        one_hot = eye[y_true]
        # Normalized multiclass Brier: mean squared error across the 4 classes.
        brier = np.square(probs - one_hot).mean(axis=1)
        row_df = pd.DataFrame(
            {
                "pred_batch": pdf["pred_batch"].to_numpy(copy=False),
                "action_key": pdf["action_key"].to_numpy(copy=False),
                "multiclass_logloss": logloss,
                "multiclass_brier": brier,
            }
        )
        step_df = (
            row_df.groupby(["pred_batch", "action_key"], as_index=False)
            .agg(
                multiclass_logloss=("multiclass_logloss", "mean"),
                multiclass_brier=("multiclass_brier", "mean"),
            )
            .sort_values(["pred_batch", "action_key"])
            .reset_index(drop=True)
        )
        frames.append(step_df)

    if not frames:
        raise SystemExit("Prediction row inputs were discovered, but all were empty.")
    return (
        pd.concat(frames, axis=0, ignore_index=True)
        .sort_values(["pred_batch", "action_key"])
        .reset_index(drop=True)
    )


def _build_step_combo_frame(
    run_dir: Path,
    probability_epsilon: float,
    needed_losses: set[str],
) -> pd.DataFrame:
    metric_paths = _discover_files(run_dir, COMBO_METRICS_FILE)
    metric_df = _load_combo_metrics(metric_paths)

    if {"multiclass_brier", "multiclass_logloss", "composite"} & needed_losses:
        pred_paths = _discover_files(run_dir, SELECTED_PREDICTION_FILE)
        prob_df = _load_probabilistic_step_losses(pred_paths, probability_epsilon)
        metric_df = metric_df.merge(
            prob_df,
            on=["pred_batch", "action_key"],
            how="left",
            validate="one_to_one",
        )
    else:
        metric_df["multiclass_logloss"] = np.nan
        metric_df["multiclass_brier"] = np.nan

    composite_components = [
        ("filtered_cde", "filtered_cde"),
        ("class_error", "class_error"),
        ("macro_f1_error", "macro_f1_error"),
        ("multiclass_brier", "multiclass_brier"),
        ("multiclass_logloss", "multiclass_logloss"),
    ]
    for _, col_name in composite_components:
        if col_name not in metric_df.columns:
            metric_df[col_name] = np.nan

    return metric_df.sort_values(["pred_batch", "action_key"]).reset_index(drop=True)


def _add_composite_loss(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    weights = {
        "filtered_cde": float(args.composite_filtered_cde_weight),
        "class_error": float(args.composite_class_error_weight),
        "macro_f1_error": float(args.composite_macro_f1_error_weight),
        "multiclass_brier": float(args.composite_brier_weight),
        "multiclass_logloss": float(args.composite_logloss_weight),
    }
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        raise SystemExit("Composite loss weights must sum to a positive value.")

    composite = np.zeros(len(df), dtype=np.float64)
    for col_name, weight in weights.items():
        if weight == 0.0:
            continue
        values = df[col_name].astype(float).to_numpy(copy=False)
        if np.isnan(values).any():
            raise SystemExit(
                f"Composite loss requires '{col_name}', but it contains missing values."
            )
        composite += weight * values
    df = df.copy()
    df["composite"] = composite / total_weight
    return df


def _write_df(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        pl.from_pandas(df).write_parquet(parquet_path)


def _summarize_timeline(timeline: pd.DataFrame) -> dict[str, float | int]:
    if timeline.empty:
        return {
            "steps": 0,
            "mean_filtered_cde": float("nan"),
            "mean_direction_accuracy": float("nan"),
            "mean_accuracy": float("nan"),
            "mean_macro_f1": float("nan"),
            "mean_rank": float("nan"),
            "top1_capture_rate": float("nan"),
            "top2_capture_rate": float("nan"),
            "mean_cde_regret_vs_oracle": float("nan"),
            "mean_accuracy_gap_vs_oracle": float("nan"),
            "mean_macro_f1_gap_vs_oracle": float("nan"),
            "selection_switch_rate": float("nan"),
            "unique_selected_combo_count": 0,
        }
    selected = timeline["selected_action_key"].astype(str)
    switch_rate = (
        float((selected != selected.shift(1)).iloc[1:].mean())
        if len(timeline) > 1
        else 0.0
    )
    return {
        "steps": int(len(timeline)),
        "mean_filtered_cde": float(timeline["selected_filtered_cde"].mean()),
        "mean_direction_accuracy": float(timeline["selected_direction_accuracy"].mean()),
        "mean_accuracy": float(timeline["selected_accuracy"].mean()),
        "mean_macro_f1": float(timeline["selected_macro_f1"].mean()),
        "mean_rank": float(timeline["selected_rank"].mean()),
        "top1_capture_rate": float((timeline["selected_rank"] == 1).mean()),
        "top2_capture_rate": float((timeline["selected_rank"] <= 2).mean()),
        "mean_cde_regret_vs_oracle": float(timeline["cde_regret_vs_oracle"].mean()),
        "mean_accuracy_gap_vs_oracle": float(
            timeline["accuracy_gap_vs_oracle"].mean()
        ),
        "mean_macro_f1_gap_vs_oracle": float(
            timeline["macro_f1_gap_vs_oracle"].mean()
        ),
        "selection_switch_rate": switch_rate,
        "unique_selected_combo_count": int(selected.nunique()),
    }


def _slice_timeline(
    timeline: pd.DataFrame,
    pred_batches: set[int] | None = None,
    ready_only: bool = False,
) -> pd.DataFrame:
    sliced = timeline
    if pred_batches is not None:
        sliced = sliced[sliced["pred_batch"].isin(pred_batches)]
    if ready_only:
        sliced = sliced[sliced["selector_ready"]]
    return sliced.copy()


def _policy_summary_row(
    timeline: pd.DataFrame,
    loss_name: str,
    discount_factor: float,
    split_batches_map: dict[str, set[int] | None],
    selection_mode: str,
) -> dict[str, float | int | str]:
    row: dict[str, float | int | str] = {
        "policy_id": f"{loss_name}__discount_{discount_factor:.4f}",
        "update_loss_name": loss_name,
        "discount_factor": float(discount_factor),
        "policy_selection_mode": str(selection_mode),
    }
    for split_name, split_batches in split_batches_map.items():
        for ready_suffix, ready_only in [("", False), ("_ready", True)]:
            split_df = _slice_timeline(timeline, split_batches, ready_only=ready_only)
            metrics = _summarize_timeline(split_df)
            for metric_name, value in metrics.items():
                row[f"{split_name}{ready_suffix}_{metric_name}"] = value
    return row


def _best_row_by_objective(
    df: pd.DataFrame,
    objective: str,
    preferred_split_prefixes: list[str],
) -> pd.Series:
    direction = OBJECTIVE_DIRECTIONS[objective]
    usable = df.copy().reset_index(drop=True)
    score_col: str | None = None
    used_split: str | None = None
    for prefix in preferred_split_prefixes:
        candidate_col = f"{prefix}_{objective}"
        if candidate_col in usable.columns and usable[candidate_col].notna().sum() > 0:
            score_col = candidate_col
            used_split = prefix
            break
    if score_col is None or used_split is None:
        raise SystemExit(
            f"Could not resolve any usable policy-selection column for objective '{objective}'."
        )

    sort_cols = [score_col]
    ascending = [direction == "min"]

    tie_cols: list[tuple[str, bool]] = []
    cde_col = f"{used_split}_mean_filtered_cde"
    rank_col = f"{used_split}_mean_rank"
    top1_col = f"{used_split}_top1_capture_rate"
    if cde_col != score_col and cde_col in usable.columns:
        tie_cols.append((cde_col, True))
    if rank_col != score_col and rank_col in usable.columns:
        tie_cols.append((rank_col, True))
    if top1_col != score_col and top1_col in usable.columns:
        tie_cols.append((top1_col, False))
    for col_name, is_ascending in tie_cols:
        sort_cols.append(col_name)
        ascending.append(is_ascending)
    sort_cols.append("policy_id")
    ascending.append(True)

    ordered = usable.sort_values(sort_cols, ascending=ascending)
    best = ordered.iloc[0].copy()
    best["selection_split_used"] = used_split
    best["selection_score_column"] = score_col
    return best


def _build_oracle_timeline(step_df: pd.DataFrame) -> pd.DataFrame:
    oracle = (
        step_df.sort_values(["pred_batch", "filtered_rank", "action_key"])
        .groupby("pred_batch", as_index=False)
        .head(1)
        .sort_values("pred_batch")
        .reset_index(drop=True)
    )
    oracle = oracle.rename(
        columns={
            "action_key": "oracle_action_key",
            "filtered_cde": "oracle_filtered_cde",
            "direction_accuracy": "oracle_direction_accuracy",
            "filtered_accuracy": "oracle_accuracy",
            "filtered_macro_f1": "oracle_macro_f1",
            "filtered_rank": "oracle_rank",
        }
    )
    return oracle[
        [
            "pred_batch",
            "oracle_action_key",
            "oracle_filtered_cde",
            "oracle_direction_accuracy",
            "oracle_accuracy",
            "oracle_macro_f1",
            "oracle_rank",
        ]
    ]


def _build_oracle_selected_timeline(oracle_timeline: pd.DataFrame) -> pd.DataFrame:
    timeline = oracle_timeline.rename(
        columns={
            "oracle_action_key": "selected_action_key",
            "oracle_filtered_cde": "selected_filtered_cde",
            "oracle_direction_accuracy": "selected_direction_accuracy",
            "oracle_accuracy": "selected_accuracy",
            "oracle_macro_f1": "selected_macro_f1",
            "oracle_rank": "selected_rank",
        }
    ).copy()
    timeline["selector_ready"] = True
    timeline["selected_pre_step_loss_score"] = np.nan
    timeline["selected_pre_step_seen_steps"] = np.nan
    timeline["selected_realized_update_loss"] = np.nan
    timeline["selected_combo_id"] = np.nan
    timeline["selected_n_features_used"] = np.nan
    timeline["selected_improved_step"] = False
    timeline["step_idx"] = np.arange(1, len(timeline) + 1)
    timeline["oracle_action_key"] = timeline["selected_action_key"]
    timeline["oracle_filtered_cde"] = timeline["selected_filtered_cde"]
    timeline["oracle_direction_accuracy"] = timeline["selected_direction_accuracy"]
    timeline["oracle_accuracy"] = timeline["selected_accuracy"]
    timeline["oracle_macro_f1"] = timeline["selected_macro_f1"]
    timeline["oracle_rank"] = timeline["selected_rank"]
    timeline["cde_regret_vs_oracle"] = 0.0
    timeline["accuracy_gap_vs_oracle"] = 0.0
    timeline["macro_f1_gap_vs_oracle"] = 0.0
    return timeline.sort_values("pred_batch").reset_index(drop=True)


def _build_static_best_timeline(
    step_df: pd.DataFrame,
    train_batches: set[int],
    objective: str,
) -> tuple[str, pd.DataFrame]:
    train_df = step_df[step_df["pred_batch"].isin(train_batches)].copy()
    train_ready_df = train_df[train_df["pred_batch"].isin(train_batches)].copy()
    score_source = train_ready_df if not train_ready_df.empty else train_df
    score_col = objective.replace("mean_", "")
    group = score_source.groupby("action_key", as_index=False).agg(
        filtered_cde=("filtered_cde", "mean"),
        direction_accuracy=("direction_accuracy", "mean"),
        accuracy=("filtered_accuracy", "mean"),
        macro_f1=("filtered_macro_f1", "mean"),
        rank=("filtered_rank", "mean"),
    )
    metric_col_map = {
        "mean_filtered_cde": "filtered_cde",
        "mean_direction_accuracy": "direction_accuracy",
        "mean_accuracy": "accuracy",
        "mean_macro_f1": "macro_f1",
        "mean_rank": "rank",
    }
    metric_col = metric_col_map[objective]
    ascending = OBJECTIVE_DIRECTIONS[objective] == "min"
    best_action_key = (
        group.sort_values([metric_col, "action_key"], ascending=[ascending, True])
        .iloc[0]["action_key"]
    )
    timeline = step_df[step_df["action_key"] == str(best_action_key)].copy()
    return str(best_action_key), timeline.sort_values("pred_batch").reset_index(drop=True)


def _attach_oracle_metrics(
    selected_timeline: pd.DataFrame,
    oracle_timeline: pd.DataFrame,
) -> pd.DataFrame:
    timeline = (
        selected_timeline.merge(
            oracle_timeline, on="pred_batch", how="left", validate="one_to_one"
        )
        .sort_values("pred_batch")
        .reset_index(drop=True)
    )
    timeline["cde_regret_vs_oracle"] = (
        timeline["selected_filtered_cde"] - timeline["oracle_filtered_cde"]
    )
    timeline["accuracy_gap_vs_oracle"] = (
        timeline["selected_accuracy"] - timeline["oracle_accuracy"]
    )
    timeline["macro_f1_gap_vs_oracle"] = (
        timeline["selected_macro_f1"] - timeline["oracle_macro_f1"]
    )
    return timeline


def _run_loss_discounted_policy(
    step_df: pd.DataFrame,
    loss_name: str,
    discount_factor: float,
    min_history_steps: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pred_batches = sorted(step_df["pred_batch"].unique().tolist())
    batch_rows = {
        batch: grp.sort_values(["action_key"]).reset_index(drop=True)
        for batch, grp in step_df.groupby("pred_batch", sort=True)
    }

    combo_state: dict[str, dict[str, float | int]] = {}
    selected_rows: list[dict[str, object]] = []
    score_rows: list[dict[str, object]] = []

    for step_idx, pred_batch in enumerate(pred_batches, start=1):
        batch_df = batch_rows[pred_batch]
        candidate_rows: list[dict[str, object]] = []
        all_ready = True

        for row in batch_df.itertuples(index=False):
            action_key = str(row.action_key)
            state = combo_state.setdefault(
                action_key,
                {"discounted_loss_sum": 0.0, "discounted_weight": 0.0, "seen_steps": 0},
            )
            seen_steps = int(state["seen_steps"])
            discounted_weight = float(state["discounted_weight"])
            pre_step_score = (
                float(state["discounted_loss_sum"]) / discounted_weight
                if discounted_weight > 0.0
                else np.nan
            )
            ready = seen_steps >= min_history_steps
            all_ready = all_ready and ready
            candidate_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "action_key": action_key,
                    "combo_id": int(row.combo_id),
                    "pre_step_seen_steps": seen_steps,
                    "pre_step_discounted_weight": discounted_weight,
                    "pre_step_loss_score": pre_step_score,
                    "candidate_ready": ready,
                    "realized_update_loss": float(getattr(row, loss_name)),
                    "filtered_cde": float(row.filtered_cde),
                    "direction_accuracy": float(row.direction_accuracy),
                    "filtered_accuracy": float(row.filtered_accuracy),
                    "filtered_macro_f1": float(row.filtered_macro_f1),
                    "filtered_rank": float(row.filtered_rank),
                    "n_features_used": float(row.n_features_used),
                    "improved_step": bool(row.improved_step),
                }
            )

        chosen = min(
            candidate_rows,
            key=lambda item: (
                0 if item["candidate_ready"] else 1,
                0 if pd.notna(item["pre_step_loss_score"]) else 1,
                float(item["pre_step_loss_score"])
                if pd.notna(item["pre_step_loss_score"])
                else 0.0,
                str(item["action_key"]),
            ),
        )

        for item in candidate_rows:
            action_key = str(item["action_key"])
            state = combo_state[action_key]
            old_sum = float(state["discounted_loss_sum"])
            old_weight = float(state["discounted_weight"])
            realized_loss = float(item["realized_update_loss"])
            new_sum = discount_factor * old_sum + realized_loss
            new_weight = discount_factor * old_weight + 1.0
            state["discounted_loss_sum"] = new_sum
            state["discounted_weight"] = new_weight
            state["seen_steps"] = int(state["seen_steps"]) + 1
            post_step_score = new_sum / new_weight
            score_rows.append(
                {
                    "pred_batch": int(pred_batch),
                    "step_idx": int(step_idx),
                    "action_key": action_key,
                    "combo_id": int(item["combo_id"]),
                    "candidate_ready": bool(item["candidate_ready"]),
                    "selector_ready": bool(all_ready),
                    "selected_flag": bool(action_key == str(chosen["action_key"])),
                    "pre_step_seen_steps": int(item["pre_step_seen_steps"]),
                    "pre_step_discounted_weight": float(item["pre_step_discounted_weight"]),
                    "pre_step_loss_score": float(item["pre_step_loss_score"])
                    if pd.notna(item["pre_step_loss_score"])
                    else np.nan,
                    "realized_update_loss": realized_loss,
                    "post_step_loss_score": float(post_step_score),
                    "filtered_cde": float(item["filtered_cde"]),
                    "direction_accuracy": float(item["direction_accuracy"]),
                    "filtered_accuracy": float(item["filtered_accuracy"]),
                    "filtered_macro_f1": float(item["filtered_macro_f1"]),
                    "filtered_rank": float(item["filtered_rank"]),
                    "n_features_used": float(item["n_features_used"]),
                    "improved_step": bool(item["improved_step"]),
                }
            )

        selected_rows.append(
            {
                "pred_batch": int(pred_batch),
                "step_idx": int(step_idx),
                "selected_action_key": str(chosen["action_key"]),
                "selected_combo_id": int(chosen["combo_id"]),
                "selector_ready": bool(all_ready),
                "selected_pre_step_loss_score": float(chosen["pre_step_loss_score"])
                if pd.notna(chosen["pre_step_loss_score"])
                else np.nan,
                "selected_pre_step_seen_steps": int(chosen["pre_step_seen_steps"]),
                "selected_realized_update_loss": float(chosen["realized_update_loss"]),
                "selected_filtered_cde": float(chosen["filtered_cde"]),
                "selected_direction_accuracy": float(chosen["direction_accuracy"]),
                "selected_accuracy": float(chosen["filtered_accuracy"]),
                "selected_macro_f1": float(chosen["filtered_macro_f1"]),
                "selected_rank": float(chosen["filtered_rank"]),
                "selected_n_features_used": float(chosen["n_features_used"]),
                "selected_improved_step": bool(chosen["improved_step"]),
            }
        )

    return (
        pd.DataFrame(selected_rows).sort_values("pred_batch").reset_index(drop=True),
        pd.DataFrame(score_rows).sort_values(["pred_batch", "action_key"]).reset_index(drop=True),
    )


def main() -> int:
    args = _parse_args()
    run_dir = _resolve_run_dir(args)
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(run_dir).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    normalized_losses = _normalize_loss_names(args.loss_names)
    discount_factors = _validate_discount_factors(args.discount_factors)
    step_df = _build_step_combo_frame(
        run_dir=run_dir,
        probability_epsilon=float(args.probability_epsilon),
        needed_losses=set(normalized_losses),
    )
    step_df = _add_composite_loss(step_df, args)

    pred_batches = sorted(step_df["pred_batch"].unique().tolist())
    train_batches, test_batches = _train_test_split(pred_batches, float(args.train_frac))
    train_batch_list = sorted(train_batches)
    split_batches_map: dict[str, set[int] | None] = {
        "all": None,
        "train": train_batches,
        "test": test_batches,
    }
    preferred_split_prefixes = ["train_ready", "train"]
    inner_train_batches: set[int] | None = None
    inner_val_batches: set[int] | None = None
    if str(args.policy_selection_mode) == "nested":
        inner_train_batches, inner_val_batches = _train_test_split(
            train_batch_list, float(args.inner_train_frac)
        )
        split_batches_map["inner_train"] = inner_train_batches
        split_batches_map["inner_val"] = inner_val_batches
        preferred_split_prefixes = ["inner_val_ready", "inner_val"]
    combo_count = int(step_df["action_key"].nunique())
    step_count = int(len(pred_batches))

    oracle_timeline = _build_oracle_timeline(step_df)
    oracle_selected_timeline = _build_oracle_selected_timeline(oracle_timeline)
    static_best_combo, static_best_timeline = _build_static_best_timeline(
        step_df, train_batches=train_batches, objective=args.select_best_by
    )
    static_best_timeline = static_best_timeline.rename(
        columns={
            "action_key": "selected_action_key",
            "combo_id": "selected_combo_id",
            "filtered_cde": "selected_filtered_cde",
            "direction_accuracy": "selected_direction_accuracy",
            "filtered_accuracy": "selected_accuracy",
            "filtered_macro_f1": "selected_macro_f1",
            "filtered_rank": "selected_rank",
            "n_features_used": "selected_n_features_used",
            "improved_step": "selected_improved_step",
        }
    )
    static_best_timeline["selector_ready"] = True
    static_best_timeline["selected_pre_step_loss_score"] = np.nan
    static_best_timeline["selected_pre_step_seen_steps"] = np.nan
    static_best_timeline["selected_realized_update_loss"] = np.nan
    static_best_timeline["step_idx"] = np.arange(1, len(static_best_timeline) + 1)
    static_best_timeline = _attach_oracle_metrics(static_best_timeline, oracle_timeline)

    policy_rows: list[dict[str, object]] = []
    policy_timelines: dict[str, pd.DataFrame] = {}
    policy_score_panels: dict[str, pd.DataFrame] = {}

    for loss_name in normalized_losses:
        if loss_name not in step_df.columns:
            raise SystemExit(f"Update loss column missing from step frame: {loss_name}")
        if step_df[loss_name].isna().any():
            raise SystemExit(f"Update loss '{loss_name}' contains missing values.")
        for discount_factor in discount_factors:
            selected_timeline, score_panel = _run_loss_discounted_policy(
                step_df=step_df,
                loss_name=loss_name,
                discount_factor=float(discount_factor),
                min_history_steps=max(0, int(args.min_history_steps)),
            )
            selected_timeline = _attach_oracle_metrics(selected_timeline, oracle_timeline)
            policy_id = f"{loss_name}__discount_{float(discount_factor):.4f}"
            policy_timelines[policy_id] = selected_timeline
            policy_score_panels[policy_id] = score_panel
            policy_summary = _policy_summary_row(
                timeline=selected_timeline,
                loss_name=loss_name,
                discount_factor=float(discount_factor),
                split_batches_map=split_batches_map,
                selection_mode=str(args.policy_selection_mode),
            )
            policy_rows.append(policy_summary)

            if args.persist_all_policy_timelines:
                safe_policy_id = policy_id.replace(".", "p")
                _write_df(
                    selected_timeline,
                    output_dir / "policy_timelines" / f"{safe_policy_id}.csv",
                    output_dir / "policy_timelines" / f"{safe_policy_id}.parquet",
                )
                _write_df(
                    score_panel,
                    output_dir / "policy_score_panels" / f"{safe_policy_id}.csv",
                    output_dir / "policy_score_panels" / f"{safe_policy_id}.parquet",
                )

    policy_df = pd.DataFrame(policy_rows)
    if policy_df.empty:
        raise SystemExit("No policies were evaluated.")
    best_policy = _best_row_by_objective(
        policy_df,
        objective=str(args.select_best_by),
        preferred_split_prefixes=preferred_split_prefixes,
    )
    best_loss_name = str(best_policy["update_loss_name"])
    best_discount_factor = float(best_policy["discount_factor"])
    best_policy_id = f"{best_loss_name}__discount_{best_discount_factor:.4f}"
    best_timeline = policy_timelines[best_policy_id]
    best_scores = policy_score_panels[best_policy_id]

    best_summary_row = policy_df[
        (policy_df["update_loss_name"] == best_loss_name)
        & (policy_df["discount_factor"] == best_discount_factor)
    ].iloc[0]

    full_pool_metrics = {
        "all": _summarize_timeline(oracle_selected_timeline),
        "train": _summarize_timeline(_slice_timeline(oracle_selected_timeline, train_batches)),
        "test": _summarize_timeline(_slice_timeline(oracle_selected_timeline, test_batches)),
    }

    static_summary = {
        "action_key": static_best_combo,
        "all": _summarize_timeline(static_best_timeline),
        "train": _summarize_timeline(_slice_timeline(static_best_timeline, train_batches)),
        "test": _summarize_timeline(_slice_timeline(static_best_timeline, test_batches)),
    }

    summary = {
        "run_id": run_dir.name,
        "run_path": str(run_dir),
        "combo_count": combo_count,
        "step_count": step_count,
        "policy_selection_mode": str(args.policy_selection_mode),
        "train_step_count": int(len(train_batches)),
        "test_step_count": int(len(test_batches)),
        "inner_train_step_count": (
            int(len(inner_train_batches)) if inner_train_batches is not None else None
        ),
        "inner_val_step_count": (
            int(len(inner_val_batches)) if inner_val_batches is not None else None
        ),
        "min_history_steps": int(args.min_history_steps),
        "selection_objective": str(args.select_best_by),
        "selection_split_used": str(best_policy["selection_split_used"]),
        "evaluated_loss_names": normalized_losses,
        "evaluated_discount_factors": [float(x) for x in discount_factors],
        "policy_count": int(len(policy_df)),
        "best_policy": {
            "policy_id": str(best_summary_row["policy_id"]),
            "update_loss_name": best_loss_name,
            "discount_factor": best_discount_factor,
            "selection_score_column": str(best_policy["selection_score_column"]),
            "selection_score_value": float(best_summary_row[str(best_policy["selection_score_column"])]),
            "inner_val_ready_mean_filtered_cde": (
                float(best_summary_row["inner_val_ready_mean_filtered_cde"])
                if "inner_val_ready_mean_filtered_cde" in best_summary_row
                and pd.notna(best_summary_row["inner_val_ready_mean_filtered_cde"])
                else None
            ),
            "train_ready_mean_filtered_cde": float(best_summary_row["train_ready_mean_filtered_cde"]),
            "test_ready_mean_filtered_cde": float(best_summary_row["test_ready_mean_filtered_cde"]),
            "train_ready_mean_accuracy": float(best_summary_row["train_ready_mean_accuracy"]),
            "test_ready_mean_accuracy": float(best_summary_row["test_ready_mean_accuracy"]),
            "train_ready_mean_rank": float(best_summary_row["train_ready_mean_rank"]),
            "test_ready_mean_rank": float(best_summary_row["test_ready_mean_rank"]),
            "test_ready_top1_capture_rate": float(best_summary_row["test_ready_top1_capture_rate"]),
            "test_ready_top2_capture_rate": float(best_summary_row["test_ready_top2_capture_rate"]),
        },
        "static_best_combo": static_summary,
        "full_pool_oracle": full_pool_metrics,
    }

    sort_score_col = str(best_policy["selection_score_column"])
    sort_direction_is_min = OBJECTIVE_DIRECTIONS[str(args.select_best_by)] == "min"
    sort_cols = [sort_score_col]
    sort_ascending = [sort_direction_is_min]
    if sort_score_col != "test_ready_mean_filtered_cde":
        sort_cols.append("test_ready_mean_filtered_cde")
        sort_ascending.append(True)
    sort_cols.append("policy_id")
    sort_ascending.append(True)

    _write_df(
        policy_df.sort_values(
            sort_cols,
            ascending=sort_ascending,
        ),
        output_dir / "policy_grid_summary.csv",
        output_dir / "policy_grid_summary.parquet",
    )
    _write_df(
        best_timeline,
        output_dir / "best_policy_selected_timeline.csv",
        output_dir / "best_policy_selected_timeline.parquet",
    )
    _write_df(
        best_scores,
        output_dir / "best_policy_score_panel.csv",
        output_dir / "best_policy_score_panel.parquet",
    )
    _write_df(
        static_best_timeline,
        output_dir / "static_best_combo_timeline.csv",
        output_dir / "static_best_combo_timeline.parquet",
    )
    _write_df(
        oracle_timeline,
        output_dir / "full_pool_oracle_timeline.csv",
        output_dir / "full_pool_oracle_timeline.parquet",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nArtifacts written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analysis.htf_stage1_v2_loss_discounted_selector_audit import (  # noqa: E402
    DEFAULT_TEST_OUTPUT,
    OBJECTIVE_DIRECTIONS,
    _add_composite_loss,
    _attach_oracle_metrics,
    _best_row_by_objective,
    _build_oracle_selected_timeline,
    _build_oracle_timeline,
    _build_static_best_timeline,
    _build_step_combo_frame,
    _normalize_loss_names,
    _policy_summary_row,
    _resolve_run_dir,
    _run_loss_discounted_policy,
    _slice_timeline,
    _summarize_timeline,
    _train_test_split,
    _validate_discount_factors,
    _write_df,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a rolling-window robustness audit for the Stage-1-v2 loss-discounted "
            "selector on fixed-policy replay artifacts."
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
        "--window-size",
        type=int,
        default=300,
        help="Number of chronological steps per rolling window.",
    )
    parser.add_argument(
        "--window-stride",
        type=int,
        default=50,
        help="Step stride between rolling windows.",
    )
    parser.add_argument(
        "--train-frac",
        type=float,
        default=0.70,
        help="Chronological outer-train fraction inside each rolling window.",
    )
    parser.add_argument(
        "--policy-selection-mode",
        type=str,
        default="nested",
        choices=["nested", "train_ready"],
        help=(
            "How to choose the best policy inside each window. "
            "'nested' uses an inner train/validation split inside the outer train segment."
        ),
    )
    parser.add_argument(
        "--inner-train-frac",
        type=float,
        default=0.70,
        help="When nested mode is used, chronological inner-train fraction inside the outer train.",
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
        help="Update losses to evaluate.",
    )
    parser.add_argument(
        "--discount-factors",
        nargs="+",
        type=float,
        default=[0.50, 0.70, 0.85, 0.95, 0.98],
        help="Discount factors to evaluate for each loss family.",
    )
    parser.add_argument(
        "--min-history-steps",
        type=int,
        default=3,
        help="Minimum prior realized steps before a combo is considered ready.",
    )
    parser.add_argument(
        "--select-best-by",
        type=str,
        default="mean_filtered_cde",
        choices=sorted(OBJECTIVE_DIRECTIONS.keys()),
        help="Metric used to choose the policy inside each window.",
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
        help="Composite update-loss weight for class error.",
    )
    parser.add_argument(
        "--composite-macro-f1-error-weight",
        type=float,
        default=0.15,
        help="Composite update-loss weight for macro-F1 error.",
    )
    parser.add_argument(
        "--composite-brier-weight",
        type=float,
        default=0.0,
        help="Composite update-loss weight for multiclass Brier loss.",
    )
    parser.add_argument(
        "--composite-logloss-weight",
        type=float,
        default=0.0,
        help="Composite update-loss weight for multiclass log-loss.",
    )
    return parser.parse_args()


def _default_output_dir(run_dir: Path) -> Path:
    return DEFAULT_TEST_OUTPUT / f"stage1_v2_loss_discounted_selector_rolling_audit_{run_dir.name}"


def _window_start_positions(total_steps: int, window_size: int, stride: int) -> list[int]:
    if window_size < 2:
        raise SystemExit("window_size must be at least 2.")
    if stride < 1:
        raise SystemExit("window_stride must be at least 1.")
    if window_size > total_steps:
        raise SystemExit(
            f"window_size={window_size} exceeds available step count={total_steps}."
        )
    starts = list(range(0, total_steps - window_size + 1, stride))
    last_start = total_steps - window_size
    if starts[-1] != last_start:
        starts.append(last_start)
    return starts


def _prepare_static_timeline(
    window_step_df: pd.DataFrame,
    train_batches: set[int],
    oracle_timeline: pd.DataFrame,
    objective: str,
) -> tuple[str, pd.DataFrame]:
    static_best_combo, static_best_timeline = _build_static_best_timeline(
        window_step_df, train_batches=train_batches, objective=objective
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
    static_best_timeline["selected_pre_step_loss_score"] = pd.NA
    static_best_timeline["selected_pre_step_seen_steps"] = pd.NA
    static_best_timeline["selected_realized_update_loss"] = pd.NA
    static_best_timeline["step_idx"] = range(1, len(static_best_timeline) + 1)
    static_best_timeline = _attach_oracle_metrics(static_best_timeline, oracle_timeline)
    return static_best_combo, static_best_timeline


def _frequency_table(
    window_df: pd.DataFrame,
    key_cols: list[str],
    count_col_name: str,
) -> pd.DataFrame:
    if window_df.empty:
        return pd.DataFrame(columns=[*key_cols, count_col_name, "share"])
    out = (
        window_df.groupby(key_cols, dropna=False)
        .size()
        .reset_index(name=count_col_name)
        .sort_values([count_col_name, *key_cols], ascending=[False, *([True] * len(key_cols))])
        .reset_index(drop=True)
    )
    out["share"] = out[count_col_name] / float(len(window_df))
    return out


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
    starts = _window_start_positions(
        total_steps=len(pred_batches),
        window_size=int(args.window_size),
        stride=int(args.window_stride),
    )

    window_rows: list[dict[str, object]] = []
    policy_grid_frames: list[pd.DataFrame] = []

    for window_idx, start in enumerate(starts, start=1):
        window_batches = pred_batches[start : start + int(args.window_size)]
        window_batch_set = set(window_batches)
        window_step_df = (
            step_df[step_df["pred_batch"].isin(window_batch_set)]
            .sort_values(["pred_batch", "action_key"])
            .reset_index(drop=True)
        )
        outer_train_batches, outer_test_batches = _train_test_split(
            window_batches, float(args.train_frac)
        )
        split_batches_map: dict[str, set[int] | None] = {
            "all": None,
            "outer_train": outer_train_batches,
            "outer_test": outer_test_batches,
        }
        preferred_split_prefixes = ["outer_train_ready", "outer_train"]
        inner_train_batches: set[int] | None = None
        inner_val_batches: set[int] | None = None
        if str(args.policy_selection_mode) == "nested":
            inner_train_batches, inner_val_batches = _train_test_split(
                sorted(outer_train_batches), float(args.inner_train_frac)
            )
            split_batches_map["inner_train"] = inner_train_batches
            split_batches_map["inner_val"] = inner_val_batches
            preferred_split_prefixes = ["inner_val_ready", "inner_val"]

        oracle_timeline = _build_oracle_timeline(window_step_df)
        oracle_selected_timeline = _build_oracle_selected_timeline(oracle_timeline)
        static_best_combo, static_best_timeline = _prepare_static_timeline(
            window_step_df=window_step_df,
            train_batches=outer_train_batches,
            oracle_timeline=oracle_timeline,
            objective=str(args.select_best_by),
        )

        policy_rows: list[dict[str, object]] = []
        policy_timelines: dict[str, pd.DataFrame] = {}

        for loss_name in normalized_losses:
            if loss_name not in window_step_df.columns:
                raise SystemExit(f"Update loss column missing from step frame: {loss_name}")
            if window_step_df[loss_name].isna().any():
                raise SystemExit(f"Update loss '{loss_name}' contains missing values.")
            for discount_factor in discount_factors:
                selected_timeline, _ = _run_loss_discounted_policy(
                    step_df=window_step_df,
                    loss_name=loss_name,
                    discount_factor=float(discount_factor),
                    min_history_steps=max(0, int(args.min_history_steps)),
                )
                selected_timeline = _attach_oracle_metrics(selected_timeline, oracle_timeline)
                policy_id = f"{loss_name}__discount_{float(discount_factor):.4f}"
                policy_timelines[policy_id] = selected_timeline
                policy_summary = _policy_summary_row(
                    timeline=selected_timeline,
                    loss_name=loss_name,
                    discount_factor=float(discount_factor),
                    split_batches_map=split_batches_map,
                    selection_mode=str(args.policy_selection_mode),
                )
                policy_rows.append(policy_summary)

        window_policy_df = pd.DataFrame(policy_rows)
        if window_policy_df.empty:
            raise SystemExit(f"No policies evaluated for window {window_idx}.")

        selected_policy = _best_row_by_objective(
            window_policy_df,
            objective=str(args.select_best_by),
            preferred_split_prefixes=preferred_split_prefixes,
        )
        ex_post_best_policy = _best_row_by_objective(
            window_policy_df,
            objective=str(args.select_best_by),
            preferred_split_prefixes=["outer_test_ready", "outer_test"],
        )

        selected_policy_id = str(selected_policy["policy_id"])
        ex_post_best_policy_id = str(ex_post_best_policy["policy_id"])
        selected_timeline = policy_timelines[selected_policy_id]
        ex_post_best_timeline = policy_timelines[ex_post_best_policy_id]

        outer_test_selected_summary = _summarize_timeline(
            _slice_timeline(selected_timeline, outer_test_batches, ready_only=True)
        )
        outer_test_ex_post_summary = _summarize_timeline(
            _slice_timeline(ex_post_best_timeline, outer_test_batches, ready_only=True)
        )
        outer_test_static_summary = _summarize_timeline(
            _slice_timeline(static_best_timeline, outer_test_batches, ready_only=False)
        )
        outer_test_oracle_summary = _summarize_timeline(
            _slice_timeline(oracle_selected_timeline, outer_test_batches, ready_only=False)
        )

        window_policy_df = window_policy_df.copy()
        window_policy_df["window_idx"] = int(window_idx)
        window_policy_df["window_start_batch"] = int(window_batches[0])
        window_policy_df["window_end_batch"] = int(window_batches[-1])
        window_policy_df["selected_policy_flag"] = (
            window_policy_df["policy_id"].astype(str) == selected_policy_id
        )
        window_policy_df["ex_post_best_policy_flag"] = (
            window_policy_df["policy_id"].astype(str) == ex_post_best_policy_id
        )
        policy_grid_frames.append(window_policy_df)

        window_rows.append(
            {
                "window_idx": int(window_idx),
                "window_start_batch": int(window_batches[0]),
                "window_end_batch": int(window_batches[-1]),
                "window_step_count": int(len(window_batches)),
                "outer_train_step_count": int(len(outer_train_batches)),
                "outer_test_step_count": int(len(outer_test_batches)),
                "inner_train_step_count": (
                    int(len(inner_train_batches)) if inner_train_batches is not None else None
                ),
                "inner_val_step_count": (
                    int(len(inner_val_batches)) if inner_val_batches is not None else None
                ),
                "selected_policy_id": selected_policy_id,
                "selected_update_loss_name": str(selected_policy["update_loss_name"]),
                "selected_discount_factor": float(selected_policy["discount_factor"]),
                "selected_selection_split_used": str(selected_policy["selection_split_used"]),
                "selected_selection_score_column": str(selected_policy["selection_score_column"]),
                "selected_selection_score_value": float(
                    selected_policy[str(selected_policy["selection_score_column"])]
                ),
                "ex_post_best_policy_id": ex_post_best_policy_id,
                "ex_post_best_update_loss_name": str(ex_post_best_policy["update_loss_name"]),
                "ex_post_best_discount_factor": float(ex_post_best_policy["discount_factor"]),
                "selected_matches_ex_post_best": bool(
                    selected_policy_id == ex_post_best_policy_id
                ),
                "static_best_combo_action_key": str(static_best_combo),
                "selected_outer_test_mean_filtered_cde": float(
                    outer_test_selected_summary["mean_filtered_cde"]
                ),
                "selected_outer_test_mean_accuracy": float(
                    outer_test_selected_summary["mean_accuracy"]
                ),
                "selected_outer_test_mean_rank": float(
                    outer_test_selected_summary["mean_rank"]
                ),
                "selected_outer_test_top1_capture_rate": float(
                    outer_test_selected_summary["top1_capture_rate"]
                ),
                "selected_outer_test_top2_capture_rate": float(
                    outer_test_selected_summary["top2_capture_rate"]
                ),
                "ex_post_outer_test_mean_filtered_cde": float(
                    outer_test_ex_post_summary["mean_filtered_cde"]
                ),
                "ex_post_outer_test_mean_accuracy": float(
                    outer_test_ex_post_summary["mean_accuracy"]
                ),
                "ex_post_outer_test_mean_rank": float(
                    outer_test_ex_post_summary["mean_rank"]
                ),
                "ex_post_outer_test_top1_capture_rate": float(
                    outer_test_ex_post_summary["top1_capture_rate"]
                ),
                "ex_post_outer_test_top2_capture_rate": float(
                    outer_test_ex_post_summary["top2_capture_rate"]
                ),
                "static_outer_test_mean_filtered_cde": float(
                    outer_test_static_summary["mean_filtered_cde"]
                ),
                "static_outer_test_mean_accuracy": float(
                    outer_test_static_summary["mean_accuracy"]
                ),
                "static_outer_test_mean_rank": float(
                    outer_test_static_summary["mean_rank"]
                ),
                "static_outer_test_top1_capture_rate": float(
                    outer_test_static_summary["top1_capture_rate"]
                ),
                "static_outer_test_top2_capture_rate": float(
                    outer_test_static_summary["top2_capture_rate"]
                ),
                "oracle_outer_test_mean_filtered_cde": float(
                    outer_test_oracle_summary["mean_filtered_cde"]
                ),
                "oracle_outer_test_mean_accuracy": float(
                    outer_test_oracle_summary["mean_accuracy"]
                ),
                "oracle_outer_test_mean_rank": float(
                    outer_test_oracle_summary["mean_rank"]
                ),
                "selected_vs_static_cde_gap": float(
                    outer_test_selected_summary["mean_filtered_cde"]
                    - outer_test_static_summary["mean_filtered_cde"]
                ),
                "selected_vs_static_accuracy_gap": float(
                    outer_test_selected_summary["mean_accuracy"]
                    - outer_test_static_summary["mean_accuracy"]
                ),
                "selected_vs_ex_post_cde_gap": float(
                    outer_test_selected_summary["mean_filtered_cde"]
                    - outer_test_ex_post_summary["mean_filtered_cde"]
                ),
                "selected_vs_ex_post_accuracy_gap": float(
                    outer_test_selected_summary["mean_accuracy"]
                    - outer_test_ex_post_summary["mean_accuracy"]
                ),
                "ex_post_vs_static_cde_gap": float(
                    outer_test_ex_post_summary["mean_filtered_cde"]
                    - outer_test_static_summary["mean_filtered_cde"]
                ),
                "ex_post_vs_static_accuracy_gap": float(
                    outer_test_ex_post_summary["mean_accuracy"]
                    - outer_test_static_summary["mean_accuracy"]
                ),
            }
        )

    window_summary_df = pd.DataFrame(window_rows).sort_values("window_idx").reset_index(drop=True)
    window_policy_grid_df = (
        pd.concat(policy_grid_frames, axis=0, ignore_index=True)
        .sort_values(["window_idx", "policy_id"])
        .reset_index(drop=True)
    )

    selected_policy_frequency_df = _frequency_table(
        window_summary_df,
        ["selected_policy_id", "selected_update_loss_name", "selected_discount_factor"],
        "selected_window_count",
    )
    ex_post_policy_frequency_df = _frequency_table(
        window_summary_df,
        ["ex_post_best_policy_id", "ex_post_best_update_loss_name", "ex_post_best_discount_factor"],
        "ex_post_best_window_count",
    )
    selected_family_frequency_df = _frequency_table(
        window_summary_df,
        ["selected_update_loss_name"],
        "selected_window_count",
    )
    ex_post_family_frequency_df = _frequency_table(
        window_summary_df,
        ["ex_post_best_update_loss_name"],
        "ex_post_best_window_count",
    )

    summary = {
        "run_id": run_dir.name,
        "run_path": str(run_dir),
        "policy_selection_mode": str(args.policy_selection_mode),
        "selection_objective": str(args.select_best_by),
        "window_size": int(args.window_size),
        "window_stride": int(args.window_stride),
        "window_count": int(len(window_summary_df)),
        "loss_names": normalized_losses,
        "discount_factors": [float(x) for x in discount_factors],
        "window_test_cde": {
            "selected_mean": float(window_summary_df["selected_outer_test_mean_filtered_cde"].mean()),
            "selected_median": float(
                window_summary_df["selected_outer_test_mean_filtered_cde"].median()
            ),
            "ex_post_mean": float(window_summary_df["ex_post_outer_test_mean_filtered_cde"].mean()),
            "static_mean": float(window_summary_df["static_outer_test_mean_filtered_cde"].mean()),
            "oracle_mean": float(window_summary_df["oracle_outer_test_mean_filtered_cde"].mean()),
        },
        "window_test_accuracy": {
            "selected_mean": float(window_summary_df["selected_outer_test_mean_accuracy"].mean()),
            "ex_post_mean": float(window_summary_df["ex_post_outer_test_mean_accuracy"].mean()),
            "static_mean": float(window_summary_df["static_outer_test_mean_accuracy"].mean()),
            "oracle_mean": float(window_summary_df["oracle_outer_test_mean_accuracy"].mean()),
        },
        "stability": {
            "selected_matches_ex_post_rate": float(
                window_summary_df["selected_matches_ex_post_best"].mean()
            ),
            "selected_beats_static_cde_rate": float(
                (window_summary_df["selected_vs_static_cde_gap"] < 0.0).mean()
            ),
            "ex_post_beats_static_cde_rate": float(
                (window_summary_df["ex_post_vs_static_cde_gap"] < 0.0).mean()
            ),
            "selected_unique_policy_count": int(
                window_summary_df["selected_policy_id"].nunique()
            ),
            "ex_post_unique_policy_count": int(
                window_summary_df["ex_post_best_policy_id"].nunique()
            ),
            "selected_unique_family_count": int(
                window_summary_df["selected_update_loss_name"].nunique()
            ),
            "ex_post_unique_family_count": int(
                window_summary_df["ex_post_best_update_loss_name"].nunique()
            ),
        },
        "selected_family_frequency": selected_family_frequency_df.to_dict(orient="records"),
        "ex_post_family_frequency": ex_post_family_frequency_df.to_dict(orient="records"),
    }

    _write_df(
        window_summary_df,
        output_dir / "window_summary.csv",
        output_dir / "window_summary.parquet",
    )
    _write_df(
        window_policy_grid_df,
        output_dir / "window_policy_grid.csv",
        output_dir / "window_policy_grid.parquet",
    )
    _write_df(
        selected_policy_frequency_df,
        output_dir / "selected_policy_frequency.csv",
        output_dir / "selected_policy_frequency.parquet",
    )
    _write_df(
        ex_post_policy_frequency_df,
        output_dir / "ex_post_best_policy_frequency.csv",
        output_dir / "ex_post_best_policy_frequency.parquet",
    )
    _write_df(
        selected_family_frequency_df,
        output_dir / "selected_family_frequency.csv",
        output_dir / "selected_family_frequency.parquet",
    )
    _write_df(
        ex_post_family_frequency_df,
        output_dir / "ex_post_best_family_frequency.csv",
        output_dir / "ex_post_best_family_frequency.parquet",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nArtifacts written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

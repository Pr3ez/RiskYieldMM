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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build step-level pairwise disagreement and train/test stability artifacts "
            "from Stage-1-v2 fixed-policy prediction outputs."
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
        help="Chronological train fraction used to fit pairwise disagreement rules.",
    )
    parser.add_argument(
        "--disagreement-mode",
        type=str,
        default="direction",
        choices=["direction", "class"],
        help=(
            "How to define step-level combo disagreement. "
            "'direction' uses majority up/down direction, "
            "'class' uses majority exact 4-class label."
        ),
    )
    parser.add_argument(
        "--min-train-disagreement-steps",
        type=int,
        default=12,
        help="Minimum train disagreement steps for a pair to be evaluated as viable.",
    )
    parser.add_argument(
        "--min-test-disagreement-steps",
        type=int,
        default=6,
        help="Minimum held-out disagreement steps for a pair to be evaluated as viable.",
    )
    parser.add_argument(
        "--min-train-win-rate",
        type=float,
        default=0.60,
        help="Minimum train win rate for the dominant side.",
    )
    parser.add_argument(
        "--min-test-win-rate",
        type=float,
        default=0.55,
        help="Minimum held-out win rate for the train-selected dominant side.",
    )
    parser.add_argument(
        "--min-wilson-lower-bound",
        type=float,
        default=0.50,
        help="Minimum held-out Wilson lower bound for the dominant side win rate.",
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
    return DEFAULT_TEST_OUTPUT / f"stage1_v2_step_disagreement_audit_{run_dir.name}"


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


def _load_step_prediction_summary(paths: Iterable[Path]) -> pd.DataFrame:
    frames: list[pl.DataFrame] = []
    for path in paths:
        df = pl.read_parquet(
            path,
            columns=["pred_batch", "action_key", "y_pred", "timestamp"],
        )
        if df.is_empty():
            continue
        frames.append(df)
    if not frames:
        raise SystemExit("Prediction summary inputs were discovered, but all were empty.")
    pdf = (
        pl.concat(frames, how="vertical_relaxed")
        .sort(["pred_batch", "action_key", "timestamp"])
        .to_pandas()
    )
    pdf["pred_dir"] = (pdf["y_pred"] >= 2).astype(np.int8, copy=False)

    base = (
        pdf.groupby(["pred_batch", "action_key"], as_index=False)
        .agg(
            pred_rows=("y_pred", "size"),
            pred_up_rate=("pred_dir", "mean"),
            pred_up_count=("pred_dir", "sum"),
            step_start_ts=("timestamp", "min"),
            step_end_ts=("timestamp", "max"),
        )
        .sort_values(["pred_batch", "action_key"])
        .reset_index(drop=True)
    )

    class_counts = (
        pdf.groupby(["pred_batch", "action_key", "y_pred"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=[0, 1, 2, 3], fill_value=0)
        .sort_index()
    )
    class_count_values = class_counts.to_numpy(dtype=np.int32, copy=False)
    majority_class_count = class_count_values.max(axis=1)
    majority_class_idx = class_count_values.argmax(axis=1)
    majority_class_ties = (
        class_count_values == majority_class_count[:, None]
    ).sum(axis=1) > 1
    majority_class = majority_class_idx.astype(np.float64, copy=False)
    majority_class[majority_class_ties] = np.nan

    class_summary = class_counts.reset_index()[["pred_batch", "action_key"]].copy()
    class_summary["pred_class_0_count"] = class_counts[0].to_numpy(dtype=np.int32, copy=False)
    class_summary["pred_class_1_count"] = class_counts[1].to_numpy(dtype=np.int32, copy=False)
    class_summary["pred_class_2_count"] = class_counts[2].to_numpy(dtype=np.int32, copy=False)
    class_summary["pred_class_3_count"] = class_counts[3].to_numpy(dtype=np.int32, copy=False)
    class_summary["majority_class_count"] = majority_class_count
    class_summary["majority_class_tie"] = majority_class_ties
    class_summary["majority_class"] = majority_class

    merged = base.merge(
        class_summary,
        on=["pred_batch", "action_key"],
        how="left",
        validate="one_to_one",
    )
    merged["majority_class_share"] = (
        merged["majority_class_count"] / merged["pred_rows"]
    )
    merged["majority_direction"] = np.where(
        merged["pred_up_rate"] > 0.5,
        1,
        np.where(merged["pred_up_rate"] < 0.5, 0, np.nan),
    )
    merged["majority_margin_abs"] = (merged["pred_up_rate"] - 0.5).abs()
    return merged


def _load_combo_metrics(paths: Iterable[Path]) -> pd.DataFrame:
    frames: list[pl.DataFrame] = []
    columns = [
        "pred_batch",
        "action_key",
        "filtered_rank",
        "filtered_accuracy",
        "filtered_cross_direction_error",
        "filtered_macro_f1",
        "n_features_used",
        "improved_step",
    ]
    for path in paths:
        df = pl.read_parquet(path, columns=columns)
        if not df.is_empty():
            frames.append(df)
    if not frames:
        raise SystemExit("Combo metric inputs were discovered, but all were empty.")
    return pl.concat(frames, how="vertical_relaxed").sort(["pred_batch", "action_key"]).to_pandas()


def _build_step_combo_frame(run_dir: Path) -> pd.DataFrame:
    pred_paths = _discover_files(run_dir, SELECTED_PREDICTION_FILE)
    metric_paths = _discover_files(run_dir, COMBO_METRICS_FILE)
    pred_df = _load_step_prediction_summary(pred_paths)
    metric_df = _load_combo_metrics(metric_paths)
    merged = pred_df.merge(metric_df, on=["pred_batch", "action_key"], how="inner", validate="one_to_one")
    if merged.empty:
        raise SystemExit("Merged step/combo frame is empty.")
    return merged.sort_values(["pred_batch", "action_key"]).reset_index(drop=True)


def _choose_pair_winner(row_a: pd.Series, row_b: pd.Series) -> tuple[str | None, float | None]:
    rank_a = row_a.get("filtered_rank")
    rank_b = row_b.get("filtered_rank")
    if pd.notna(rank_a) and pd.notna(rank_b) and float(rank_a) != float(rank_b):
        return (str(row_a["action_key"]), float(rank_b) - float(rank_a)) if float(rank_a) < float(rank_b) else (str(row_b["action_key"]), float(rank_a) - float(rank_b))

    acc_a = float(row_a["filtered_accuracy"])
    acc_b = float(row_b["filtered_accuracy"])
    if not math.isclose(acc_a, acc_b):
        return (str(row_a["action_key"]), acc_a - acc_b) if acc_a > acc_b else (str(row_b["action_key"]), acc_b - acc_a)

    cde_a = float(row_a["filtered_cross_direction_error"])
    cde_b = float(row_b["filtered_cross_direction_error"])
    if not math.isclose(cde_a, cde_b):
        return (str(row_a["action_key"]), cde_b - cde_a) if cde_a < cde_b else (str(row_b["action_key"]), cde_a - cde_b)

    f1_a = float(row_a["filtered_macro_f1"])
    f1_b = float(row_b["filtered_macro_f1"])
    if not math.isclose(f1_a, f1_b):
        return (str(row_a["action_key"]), f1_a - f1_b) if f1_a > f1_b else (str(row_b["action_key"]), f1_b - f1_a)

    return None, None


def _wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float | None:
    if n <= 0:
        return None
    p = wins / n
    denom = 1.0 + z**2 / n
    center = p + z**2 / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    return float((center - margin) / denom)


def _train_test_split(pred_batches: list[int], train_frac: float) -> tuple[set[int], set[int]]:
    pred_batches = sorted(pred_batches)
    n_steps = len(pred_batches)
    if n_steps < 2:
        raise SystemExit("Need at least 2 pred batches for a train/test split.")
    split_idx = max(1, min(n_steps - 1, int(math.floor(n_steps * train_frac))))
    train_batches = set(pred_batches[:split_idx])
    test_batches = set(pred_batches[split_idx:])
    return train_batches, test_batches


def _build_pair_disagreement_rows(step_combo_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for pred_batch, grp in step_combo_df.groupby("pred_batch", sort=True):
        grp = grp.sort_values("action_key").reset_index(drop=True)
        records = [row for _, row in grp.iterrows()]
        for idx, row_a in enumerate(records):
            for row_b in records[idx + 1 :]:
                majority_a = row_a["majority_direction"]
                majority_b = row_b["majority_direction"]
                pair_winner, pair_margin = _choose_pair_winner(row_a, row_b)
                rows.append(
                    {
                        "pred_batch": int(pred_batch),
                        "combo_a": str(row_a["action_key"]),
                        "combo_b": str(row_b["action_key"]),
                        "majority_direction_a": None if pd.isna(majority_a) else int(majority_a),
                        "majority_direction_b": None if pd.isna(majority_b) else int(majority_b),
                        "direction_disagree_step": bool(
                            pd.notna(majority_a)
                            and pd.notna(majority_b)
                            and int(majority_a) != int(majority_b)
                        ),
                        "pred_up_rate_a": float(row_a["pred_up_rate"]),
                        "pred_up_rate_b": float(row_b["pred_up_rate"]),
                        "majority_margin_abs_a": float(row_a["majority_margin_abs"]),
                        "majority_margin_abs_b": float(row_b["majority_margin_abs"]),
                        "majority_class_a": None
                        if pd.isna(row_a["majority_class"])
                        else int(row_a["majority_class"]),
                        "majority_class_b": None
                        if pd.isna(row_b["majority_class"])
                        else int(row_b["majority_class"]),
                        "majority_class_share_a": float(row_a["majority_class_share"]),
                        "majority_class_share_b": float(row_b["majority_class_share"]),
                        "majority_class_tie_a": bool(row_a["majority_class_tie"]),
                        "majority_class_tie_b": bool(row_b["majority_class_tie"]),
                        "class_disagree_step": bool(
                            pd.notna(row_a["majority_class"])
                            and pd.notna(row_b["majority_class"])
                            and int(row_a["majority_class"]) != int(row_b["majority_class"])
                        ),
                        "rank_a": float(row_a["filtered_rank"]),
                        "rank_b": float(row_b["filtered_rank"]),
                        "filtered_accuracy_a": float(row_a["filtered_accuracy"]),
                        "filtered_accuracy_b": float(row_b["filtered_accuracy"]),
                        "filtered_cde_a": float(row_a["filtered_cross_direction_error"]),
                        "filtered_cde_b": float(row_b["filtered_cross_direction_error"]),
                        "filtered_macro_f1_a": float(row_a["filtered_macro_f1"]),
                        "filtered_macro_f1_b": float(row_b["filtered_macro_f1"]),
                        "pair_winner": pair_winner,
                        "pair_winner_margin": pair_margin,
                        "accuracy_edge_a_minus_b": float(row_a["filtered_accuracy"] - row_b["filtered_accuracy"]),
                        "cde_edge_a_minus_b": float(row_b["filtered_cross_direction_error"] - row_a["filtered_cross_direction_error"]),
                        "macro_f1_edge_a_minus_b": float(row_a["filtered_macro_f1"] - row_b["filtered_macro_f1"]),
                    }
                )
    return pd.DataFrame(rows).sort_values(["pred_batch", "combo_a", "combo_b"]).reset_index(drop=True)


def _summarize_pairs(
    disagreement_df: pd.DataFrame,
    train_batches: set[int],
    test_batches: set[int],
    disagreement_mode: str,
    min_train_steps: int,
    min_test_steps: int,
    min_train_win_rate: float,
    min_test_win_rate: float,
    min_wilson_lb: float,
) -> pd.DataFrame:
    if disagreement_mode not in {"direction", "class"}:
        raise ValueError("disagreement_mode must be 'direction' or 'class'")
    disagreement_col = (
        "direction_disagree_step" if disagreement_mode == "direction" else "class_disagree_step"
    )
    rows: list[dict[str, object]] = []
    for (combo_a, combo_b), grp in disagreement_df.groupby(["combo_a", "combo_b"], sort=True):
        train = grp[grp["pred_batch"].isin(train_batches)]
        test = grp[grp["pred_batch"].isin(test_batches)]
        train_dis = train[train[disagreement_col]]
        test_dis = test[test[disagreement_col]]

        train_wins_a = int((train_dis["pair_winner"] == combo_a).sum())
        train_wins_b = int((train_dis["pair_winner"] == combo_b).sum())
        train_steps = int(len(train_dis))
        test_steps = int(len(test_dis))

        dominant_side = None
        dominant_train_wins = 0
        dominant_train_win_rate = None
        if train_steps > 0:
            if train_wins_a > train_wins_b:
                dominant_side = combo_a
                dominant_train_wins = train_wins_a
            elif train_wins_b > train_wins_a:
                dominant_side = combo_b
                dominant_train_wins = train_wins_b
            if dominant_side is not None:
                dominant_train_win_rate = float(dominant_train_wins / train_steps)

        test_rule_wins = None
        test_rule_win_rate = None
        test_rule_wilson_lb = None
        test_mean_accuracy_edge = None
        test_mean_cde_edge = None
        sign_stable = False
        if dominant_side is not None and test_steps > 0:
            test_rule_wins = int((test_dis["pair_winner"] == dominant_side).sum())
            test_rule_win_rate = float(test_rule_wins / test_steps)
            test_rule_wilson_lb = _wilson_lower_bound(test_rule_wins, test_steps)
            sign_stable = bool(test_rule_wins > (test_steps - test_rule_wins))

            if dominant_side == combo_a:
                test_mean_accuracy_edge = float(test_dis["accuracy_edge_a_minus_b"].mean())
                test_mean_cde_edge = float(test_dis["cde_edge_a_minus_b"].mean())
            else:
                test_mean_accuracy_edge = float((-test_dis["accuracy_edge_a_minus_b"]).mean())
                test_mean_cde_edge = float((-test_dis["cde_edge_a_minus_b"]).mean())

        stable_useful = bool(
            dominant_side is not None
            and train_steps >= min_train_steps
            and test_steps >= min_test_steps
            and dominant_train_win_rate is not None
            and dominant_train_win_rate >= min_train_win_rate
            and test_rule_win_rate is not None
            and test_rule_win_rate >= min_test_win_rate
            and test_rule_wilson_lb is not None
            and test_rule_wilson_lb >= min_wilson_lb
            and sign_stable
        )

        rows.append(
            {
                "combo_a": combo_a,
                "combo_b": combo_b,
                "disagreement_mode": disagreement_mode,
                "train_steps_total": int(len(train)),
                "test_steps_total": int(len(test)),
                "train_disagreement_steps": train_steps,
                "test_disagreement_steps": test_steps,
                "train_disagreement_rate": float(train_steps / len(train)) if len(train) else None,
                "test_disagreement_rate": float(test_steps / len(test)) if len(test) else None,
                "train_wins_a": train_wins_a,
                "train_wins_b": train_wins_b,
                "train_dominant_side": dominant_side,
                "train_dominant_win_rate": dominant_train_win_rate,
                "test_rule_wins": test_rule_wins,
                "test_rule_win_rate": test_rule_win_rate,
                "test_rule_wilson_lb": test_rule_wilson_lb,
                "test_sign_stable": sign_stable,
                "test_mean_accuracy_edge_for_train_side": test_mean_accuracy_edge,
                "test_mean_cde_edge_for_train_side": test_mean_cde_edge,
                "stable_useful_pair": stable_useful,
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["stable_useful_pair", "test_rule_win_rate", "train_dominant_win_rate"],
        ascending=[False, False, False],
        na_position="last",
    )


def _summarize_combo_meta_readiness(pair_summary_df: pd.DataFrame) -> pd.DataFrame:
    combos = sorted(set(pair_summary_df["combo_a"]).union(pair_summary_df["combo_b"]))
    rows: list[dict[str, object]] = []
    for combo in combos:
        related = pair_summary_df[
            (pair_summary_df["combo_a"] == combo) | (pair_summary_df["combo_b"] == combo)
        ].copy()
        if related.empty:
            continue
        stable = related[related["stable_useful_pair"]]
        rows.append(
            {
                "action_key": combo,
                "pair_count": int(len(related)),
                "stable_useful_pair_count": int(len(stable)),
                "stable_useful_pair_rate": float(len(stable) / len(related)),
                "mean_test_rule_win_rate": (
                    float(related["test_rule_win_rate"].dropna().mean())
                    if related["test_rule_win_rate"].notna().any()
                    else None
                ),
                "mean_test_rule_wilson_lb": (
                    float(related["test_rule_wilson_lb"].dropna().mean())
                    if related["test_rule_wilson_lb"].notna().any()
                    else None
                ),
                "mean_test_accuracy_edge": (
                    float(related["test_mean_accuracy_edge_for_train_side"].dropna().mean())
                    if related["test_mean_accuracy_edge_for_train_side"].notna().any()
                    else None
                ),
                "mean_test_cde_edge": (
                    float(related["test_mean_cde_edge_for_train_side"].dropna().mean())
                    if related["test_mean_cde_edge_for_train_side"].notna().any()
                    else None
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["stable_useful_pair_count", "mean_test_rule_win_rate"],
        ascending=[False, False],
        na_position="last",
    )


def _build_summary(
    run_dir: Path,
    step_combo_df: pd.DataFrame,
    disagreement_df: pd.DataFrame,
    pair_summary_df: pd.DataFrame,
    combo_readiness_df: pd.DataFrame,
    train_batches: set[int],
    test_batches: set[int],
    disagreement_mode: str,
) -> dict[str, object]:
    stable_pairs = pair_summary_df[pair_summary_df["stable_useful_pair"]]
    return {
        "run_id": run_dir.name,
        "run_path": str(run_dir),
        "disagreement_mode": disagreement_mode,
        "combo_count": int(step_combo_df["action_key"].nunique()),
        "step_count": int(step_combo_df["pred_batch"].nunique()),
        "pair_count": int(len(pair_summary_df)),
        "train_step_count": int(len(train_batches)),
        "test_step_count": int(len(test_batches)),
        "mean_train_disagreement_rate": float(pair_summary_df["train_disagreement_rate"].dropna().mean()),
        "mean_test_disagreement_rate": float(pair_summary_df["test_disagreement_rate"].dropna().mean()),
        "stable_useful_pair_count": int(len(stable_pairs)),
        "stable_useful_pair_rate": float(len(stable_pairs) / len(pair_summary_df)) if len(pair_summary_df) else None,
        "top_stable_pairs": stable_pairs.head(8).to_dict(orient="records"),
        "top_combo_readiness": combo_readiness_df.head(8).to_dict(orient="records"),
        "disagreement_rows": int(len(disagreement_df)),
    }


def _write_df(df: pd.DataFrame, csv_path: Path, parquet_path: Path | None = None) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    if parquet_path is not None:
        pl.from_pandas(df).write_parquet(parquet_path)


def main() -> int:
    args = _parse_args()
    run_dir = _resolve_run_dir(args)
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir else _default_output_dir(run_dir).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    step_combo_df = _build_step_combo_frame(run_dir)
    pred_batches = sorted(int(v) for v in step_combo_df["pred_batch"].unique())
    train_batches, test_batches = _train_test_split(pred_batches, float(args.train_frac))

    disagreement_df = _build_pair_disagreement_rows(step_combo_df)
    pair_summary_df = _summarize_pairs(
        disagreement_df=disagreement_df,
        train_batches=train_batches,
        test_batches=test_batches,
        disagreement_mode=str(args.disagreement_mode),
        min_train_steps=int(args.min_train_disagreement_steps),
        min_test_steps=int(args.min_test_disagreement_steps),
        min_train_win_rate=float(args.min_train_win_rate),
        min_test_win_rate=float(args.min_test_win_rate),
        min_wilson_lb=float(args.min_wilson_lower_bound),
    )
    combo_readiness_df = _summarize_combo_meta_readiness(pair_summary_df)
    summary = _build_summary(
        run_dir=run_dir,
        step_combo_df=step_combo_df,
        disagreement_df=disagreement_df,
        pair_summary_df=pair_summary_df,
        combo_readiness_df=combo_readiness_df,
        train_batches=train_batches,
        test_batches=test_batches,
        disagreement_mode=str(args.disagreement_mode),
    )

    _write_df(
        step_combo_df,
        output_dir / "step_combo_metrics.csv",
        output_dir / "step_combo_metrics.parquet",
    )
    _write_df(
        disagreement_df,
        output_dir / "step_pair_disagreements.csv",
        output_dir / "step_pair_disagreements.parquet",
    )
    _write_df(
        pair_summary_df,
        output_dir / "pair_stability_summary.csv",
        output_dir / "pair_stability_summary.parquet",
    )
    _write_df(
        combo_readiness_df,
        output_dir / "combo_meta_feature_readiness.csv",
        output_dir / "combo_meta_feature_readiness.parquet",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps(summary, indent=2))
    print(f"\nArtifacts written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
